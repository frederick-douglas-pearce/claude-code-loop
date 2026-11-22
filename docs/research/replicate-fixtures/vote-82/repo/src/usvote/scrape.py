"""Scrape stage — walk the National Archives site and fetch raw HTML.

Maps to notebook Section 2 (the network-facing half). This module is the *only*
place live network access belongs: it fetches the Archives results index and the
two HTML tables published per election year, so every downstream stage (parse,
transform, load) can run offline against saved HTML.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S1 (#23). The three
notebook functions land here unchanged in behavior — ``get_html_tables``,
``scrape_election_links``, ``scrape_raw_election_tables`` — with two additions:

- a **fetch seam** (:data:`Fetch`, defaulting to :func:`fetch_url`). Live network
  access is confined to :func:`fetch_url`; inject an alternative fetch to run the
  same parsing against saved HTML. This is how parse/transform tests stay offline.
- a **snapshot seam** (:func:`snapshot_page` / :func:`fetch_from_dir`) that lets a
  developer save Archives pages into ``tests/fixtures/`` and replay them.

One intentional behavior change from the notebook (mirroring the ``db.py`` port's
typed-exception choice): a missing ``<div>``/``<table>`` now raises
:class:`ScrapeError` rather than surfacing as a bare ``AttributeError``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Container, Iterable
from pathlib import Path
from typing import Literal, overload

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

# Archives site parameters (notebook Section 1.3). Exposed as defaults so callers
# and tests need not repeat them.
ARCHIVE_URL_DOMAIN = "https://www.archives.gov"
ARCHIVE_URL_BASE = "/electoral-college/results"

# Seconds to wait on the live network fetch before giving up. Bounded so a
# stalled server can't wedge a ~60-URL scrape indefinitely.
FETCH_TIMEOUT_SECONDS = 30

# A Fetch maps a URL to that page's raw markup (bytes). The default hits the
# network; tests and snapshot replay inject one that reads saved HTML instead.
#
# NOTE: this seam stays EC-local, and both PV sources have now settled the
# question of whether it should be shared. An earlier note here anticipated
# extracting it into a usvote/_fetch.py once usvote/ucsb/ (E4) and usvote/mit/
# (E5) landed, on the premise they would want the same machinery. They did not:
# MIT ships a local CSV and needs no fetch seam at all (usvote/mit/read.py),
# and UCSB's seam is a different shape -- it must surface HTTP status (its
# 403/429 halt reads it) and keep the body on an error status, encoding
# presidency.ucsb.edu's robots policy rather than plain "fetch a URL"
# (usvote/ucsb/scrape.py). With no duplicated knowledge to factor out, the
# extraction would buy indirection only. D006's actual constraint -- that a PV
# source must not import *from* this EC spine -- holds either way, and does.
# EC parse/transform tests (#25/#26) may reuse this
# seam (fetch_from_dir + get_html_tables) to replay a saved Archives page into
# <table> elements offline -- that is the tested snapshot->table path, so
# re-deriving fixture file paths in those tests would only duplicate it. (This
# in-spine reuse is fine; it is the future ucsb/mit sources reaching *into* the
# EC spine that D006 forbids.)
Fetch = Callable[[str], bytes]


class ScrapeError(RuntimeError):
    """Raised when an Archives page lacks the expected ``<div>``/``<table>``.

    The notebook read the structure directly and would surface a missing element
    as an ``AttributeError`` (``None.find_all(...)``). Raising a typed, message-
    carrying exception instead names the URL and the element that was missing.
    """


def fetch_url(url: str) -> bytes:
    """Fetch ``url`` over HTTP and return the raw response body.

    The package's single point of live network access. Every scrape function
    takes a ``fetch`` seam defaulting here; inject :func:`fetch_from_dir` (or any
    :data:`Fetch`) to run the identical parsing against saved HTML.
    """
    return requests.get(url, timeout=FETCH_TIMEOUT_SECONDS).content


@overload
def get_html_tables(
    url: str,
    div_id: str = ...,
    *,
    find_all: Literal[False] = ...,
    fetch: Fetch = ...,
) -> Tag: ...


@overload
def get_html_tables(
    url: str,
    div_id: str = ...,
    *,
    find_all: Literal[True],
    fetch: Fetch = ...,
) -> list[Tag]: ...


def get_html_tables(
    url: str,
    div_id: str = "main-col",
    *,
    find_all: bool = False,
    fetch: Fetch = fetch_url,
) -> Tag | list[Tag]:
    """Fetch ``url`` and return the ``<table>`` element(s) under ``<div id=...>``.

    With ``find_all=False`` (default) returns the first table; with
    ``find_all=True`` returns every table in the div. Raises :class:`ScrapeError`
    if the div — or, for the single-table case, its table — is absent. Note that
    ``find_all=True`` returns an empty list (not an error) for a div with no
    tables, matching the notebook; the parse stage (#25) is the first to depend
    on two tables being present.
    """
    soup = BeautifulSoup(fetch(url), "html.parser")
    div = soup.find("div", id=div_id)
    if not isinstance(div, Tag):
        raise ScrapeError(f"No <div id={div_id!r}> found at {url}")
    if find_all:
        return div.find_all("table")
    table = div.find("table")
    if not isinstance(table, Tag):
        raise ScrapeError(f"No <table> under <div id={div_id!r}> at {url}")
    return table


def scrape_election_links(
    archive_url_domain: str = ARCHIVE_URL_DOMAIN,
    archive_url_base: str = ARCHIVE_URL_BASE,
    *,
    fetch: Fetch = fetch_url,
) -> list[str]:
    """Return the absolute per-year Archives links from the results index."""
    link_table = get_html_tables(archive_url_domain + archive_url_base, fetch=fetch)
    return [archive_url_domain + _href(a) for a in link_table.find_all("a")]


def scrape_raw_election_tables(
    election_links: Iterable[str],
    us_election_years: Container[int],
    *,
    fetch: Fetch = fetch_url,
) -> dict[int, list[Tag]]:
    """Fetch the raw HTML tables for each election-year link.

    Keyed by year; a link whose trailing year is not a recognized US election
    year is reported (matching the notebook) and skipped.
    """
    raw_election_tables: dict[int, list[Tag]] = {}
    for link in election_links:
        link_year = int(link.split("/")[-1])
        if link_year in us_election_years:
            raw_election_tables[link_year] = get_html_tables(
                link, find_all=True, fetch=fetch
            )
        else:
            print(
                f"Error: The link year, {link_year}, parsed from the following "
                f"link does not match a US election year: \n{link}"
            )
    return raw_election_tables


# --- snapshot seam ---------------------------------------------------------
# Save Archives pages to disk once, then replay them offline. snapshot_page and
# fetch_from_dir share _snapshot_filename so a page saved under one name is found
# again by the other — a thin file cache keyed by URL.


def _href(anchor: Tag) -> str:
    """Return an anchor's ``href`` as a string (bs4 may type it as a list)."""
    href = anchor["href"]
    return href if isinstance(href, str) else href[0]


def _snapshot_filename(url: str) -> str:
    """Derive a stable ``.html`` filename from a URL (scheme stripped, slugged)."""
    slug = re.sub(r"[^0-9A-Za-z]+", "_", url.split("://", 1)[-1]).strip("_")
    return f"{slug}.html"


def snapshot_page(url: str, dest_dir: str | Path, *, fetch: Fetch = fetch_url) -> Path:
    """Fetch ``url`` and save its markup under ``dest_dir``; return the path.

    The developer seam for capturing Archives pages into ``tests/fixtures/``.
    Pair with :func:`fetch_from_dir` to replay the saved page offline.
    """
    dest = Path(dest_dir) / _snapshot_filename(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(fetch(url))
    return dest


def fetch_from_dir(source_dir: str | Path) -> Fetch:
    """Build a :data:`Fetch` that reads saved pages from ``source_dir``.

    Resolves each URL to the filename :func:`snapshot_page` would have written,
    so scrape functions run fully offline against snapshotted HTML.
    """
    base = Path(source_dir)

    def _fetch(url: str) -> bytes:
        return (base / _snapshot_filename(url)).read_bytes()

    return _fetch
