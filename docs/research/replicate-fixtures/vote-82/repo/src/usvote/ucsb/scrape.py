"""Scrape stage — snapshot the UCSB per-election popular-vote pages to disk.

The UCSB analogue of the EC :mod:`usvote.scrape` stage, and the only place in this
subpackage where live network access belongs: it saves one raw ``{year}.html`` per
election into a local directory so every downstream stage (parse, transform, load)
runs offline against saved HTML. Ported from the standalone ``_snapshot_ucsb.py``
that produced the existing 60-election snapshot on 2026-07-06 (E4-S1 #34, per D023).

**The politeness contract is the point of this module.** UCSB is a public academic
archive doing us a favor, and the behaviors below are what make re-running this scrape
ethically and operationally safe. They were ported deliberately rather than
reimplemented, because a rewrite loses them *silently* — no test that merely asks "did
we get the HTML" would notice, and the loss stays invisible until the site blocks us,
at which point the damage to our access and to the archive's goodwill is already done:

- **Honors the site's** ``Crawl-delay: 10`` between fetches (see
  :data:`CRAWL_DELAY_SECONDS`).
- **Identifies truthfully** as :data:`USER_AGENT` — matching robots.txt's
  ``User-agent: *``, explicitly *not* ClaudeBot. We are what we say we are.
- **Enumerates year URLs from the already-saved index**, so no page is fetched to
  discover what to fetch (:func:`enumerate_year_urls`).
- **Skips what it already has**, so a re-run costs the server nothing.
- **Halts immediately on 403/429** (:data:`BLOCKED_STATUSES`) — if the server says stop,
  we stop that instant rather than working through the remaining years.
- **Writes a per-year sha256** :data:`MANIFEST_FILENAME` so the snapshot's integrity and
  provenance are checkable after the fact.

Modifying this module means keeping every one of those true.

**The snapshot data never enters this repository** (D022/D023): UCSB grants no reuse
rights and this repo is public, so the directory lives outside the tree, located via
``USVOTE_UCSB_HTML_DIR`` (:mod:`usvote.ucsb.config`). Only this code is versioned —
which is what makes the un-backed-up snapshot re-fetchable rather than irreplaceable.

**Bootstrap (a deliberate limitation).** Enumeration reads an index page that must
already be saved, so this module cannot snapshot into a directory that has no
``_index_elections.html`` — it raises :class:`UCSBScrapeError` rather than fetching the
index itself. That is the original script's behavior, kept on purpose: the index is the
page most likely to have been restructured by the next refresh (2028), and
auto-fetching it would turn "UCSB changed their markup" into a silent green no-op —
*Enumerated 0 election pages*, exit 0 — instead of a human noticing. The one-time manual
step (which carries the same truthful User-Agent) is documented in the ``ConfigError``
and :class:`UCSBScrapeError` messages, where a fresh machine will actually meet it.

**On the fetch seam.** :data:`Fetch` is UCSB-local rather than shared with the EC
scrape's ``Fetch``. The two look similar but encode different knowledge: EC's is "fetch
a URL" (bytes, status discarded); this one is "fetch a URL *under presidency.ucsb.edu's
robots policy*" — it must surface the status code the 403/429 halt reads, and the body
even on an error status. Keeping the seam local is about that difference in meaning, not
about avoiding the EC package: a shared ``Fetch`` would have to carry both contracts.

To be precise, since the narrower claim is easy to over-read: D006 makes the EC spine
**authoritative**, so a PV source importing *domain facts* from it is not merely allowed
but required — :func:`usvote.ucsb.transform.ucsb_ingest_years` derives its year scope
from :func:`usvote.years.ec_ingest_years` for exactly that reason (D024 §6), and the
roster derives from the EC ``votes`` fact. What must not happen is the reverse: the EC
spine must never depend on a PV source.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from usvote.ucsb.config import ucsb_html_dir_from_env

#: The American Presidency Project's origin and its election-statistics index path.
UCSB_BASE_URL = "https://www.presidency.ucsb.edu"
ELECTIONS_INDEX_PATH = "/statistics/elections"

#: Sent on every request. Truthful by design: it names this project and its purpose, so
#: UCSB's operators can identify the traffic and contact us. It matches robots.txt's
#: ``User-agent: *`` rules -- it is deliberately not ClaudeBot, which those rules govern
#: separately and which this scrape is not.
USER_AGENT = "us-presidential-vote-analysis-research/0.1 (personal academic research)"

#: Seconds between fetches, from the site's robots.txt ``Crawl-delay: 10`` for
#: ``User-agent: *``. A full 60-election run therefore takes ~10 minutes. That is the
#: intended cost, not an inefficiency to tune away.
CRAWL_DELAY_SECONDS = 10

#: Seconds to wait on a single page before giving up, so a stalled server cannot wedge
#: the run. Generous: one slow page is not worth abandoning a polite pass over.
FETCH_TIMEOUT_SECONDS = 60

#: Statuses that mean "the server is telling us to stop" -- 403 Forbidden and 429 Too
#: Many Requests. Both halt the run immediately (see :func:`snapshot_elections`).
BLOCKED_STATUSES = frozenset({403, 429})

#: The saved index page enumeration reads, and the sha256 manifest describing the
#: snapshot. Both sit alongside the ``{year}.html`` pages in the snapshot directory.
INDEX_FILENAME = "_index_elections.html"
MANIFEST_FILENAME = "manifest.json"

# Election-page links as they appear in the index's markup, e.g.
# `<a href="/statistics/elections/1824">`.
_YEAR_LINK_RE = re.compile(rf"{ELECTIONS_INDEX_PATH}/(\d{{4}})")


class UCSBScrapeError(RuntimeError):
    """Raised when the snapshot directory cannot seed a run.

    Mirrors the EC :class:`usvote.scrape.ScrapeError` and
    :class:`usvote.mit.read.MITReadError` — a typed, message-carrying failure at the
    ingest boundary rather than a bare ``FileNotFoundError`` surfacing from a read.
    Covers a missing index page and an index that yields no election links (the shape
    an upstream redesign would take).
    """


class FetchResult(NamedTuple):
    """One page fetch: its HTTP status, its body, and any transport-level error.

    Carries more than the EC seam's bare ``bytes`` because the politeness rules need it:
    ``status`` drives the 403/429 halt, and ``body`` is retained even for an error
    status so the response is snapshotted verbatim rather than discarded. ``error`` is
    set only for a transport failure (no HTTP response at all — DNS, refused
    connection, timeout), which is logged and skipped rather than halting the run.
    """

    status: int | None
    body: bytes
    error: str | None = None


#: A Fetch maps a URL to the fetched page. The default hits the live network; tests
#: inject one that returns canned responses, so a test run can never re-fetch the
#: snapshot (an AC of #34: CI must not touch UCSB).
Fetch = Callable[[str], FetchResult]


def fetch_url(url: str) -> FetchResult:
    """Fetch ``url`` over HTTP with the truthful :data:`USER_AGENT`; never raises.

    The subpackage's single point of live network access, and the one place the UA is
    attached. Every HTTP outcome is returned as a :class:`FetchResult` rather than
    raised, so :func:`snapshot_elections` can decide — from the status alone — whether
    to save, skip, or halt.
    """
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None) or response.getcode()
            return FetchResult(status, response.read())
    except HTTPError as exc:
        # MUST precede the OSError branch: HTTPError subclasses URLError subclasses
        # OSError, so catching OSError first would swallow every error status --
        # including the 403/429 the halt depends on -- as a transport error, silently
        # disarming it.
        return FetchResult(exc.code, exc.read())
    except OSError as exc:
        # Every non-HTTP failure: URLError (DNS, refused connection) raised during
        # connect, but ALSO the bare OSError family raised during response.read() --
        # a read timeout (socket.timeout is TimeoutError, an OSError sibling of
        # URLError, so `except URLError` would miss it) or a connection reset
        # mid-body. All mean "no usable response"; log and continue, never crash the
        # run over one page.
        return FetchResult(None, b"", str(exc))


def enumerate_year_urls(index_html: str) -> list[tuple[str, str]]:
    """Return sorted ``(year, url)`` pairs for every election linked from the index.

    Reads the *saved* index markup, so discovering what to fetch costs the server
    nothing. Years stay **strings**: they are used as filename stems and as manifest
    keys, and JSON object keys are strings — an ``int`` year would miss every existing
    manifest entry on lookup and silently re-scrape all 60 pages. De-duplicated because
    the index links each election more than once.
    """
    years = sorted(set(_YEAR_LINK_RE.findall(index_html)))
    return [(year, f"{UCSB_BASE_URL}{ELECTIONS_INDEX_PATH}/{year}") for year in years]


def read_manifest(html_dir: str | Path) -> dict[str, Any]:
    """Return the snapshot manifest, or an empty one if it does not exist yet.

    Raises :class:`UCSBScrapeError` if the file exists but is not valid JSON, rather
    than letting a bare ``JSONDecodeError`` abort the run — a corrupt manifest is a
    recoverable, message-worthy state (see :func:`write_manifest` on why it should be
    rare), not a stack trace.
    """
    path = Path(html_dir) / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UCSBScrapeError(
            f"The manifest at {path} is not valid JSON: {exc}. Inspect or remove it "
            f"and re-run — note that removing it forces a full re-scrape, since the "
            f"manifest is what records which pages are already saved."
        ) from exc
    return manifest


def write_manifest(html_dir: str | Path, manifest: Mapping[str, Any]) -> None:
    """Write ``manifest`` to the snapshot directory, sorted and indented, atomically.

    Sorted keys and indentation keep it diffable and human-readable — it is the
    snapshot's provenance record, not an internal cache file.

    The write goes to a sibling temp file that is then atomically swapped into place
    via :meth:`Path.replace` (an ``os.rename`` on the same filesystem). This matters
    because the manifest is rewritten after *every* page precisely so an interrupted
    run leaves an accurate record: a plain truncate-then-write would defeat that goal,
    since a crash mid-write would leave a half-written file that the next
    :func:`read_manifest` cannot parse. The swap guarantees the on-disk manifest is
    always either the old complete version or the new complete version, never a partial
    one.
    """
    directory = Path(html_dir)
    path = directory / MANIFEST_FILENAME
    tmp = directory / f"{MANIFEST_FILENAME}.tmp"
    tmp.write_text(
        json.dumps(dict(manifest), indent=2, sort_keys=True), encoding="utf-8"
    )
    tmp.replace(path)


def read_snapshot_html(
    html_dir: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[int, str]:
    """Read the saved snapshot into the ``{year: html}`` mapping the parser consumes.

    The read counterpart of :func:`snapshot_elections`: it turns the on-disk snapshot
    (``{year}.html`` pages + ``manifest.json``) into the ``Mapping[int, str]``
    :func:`usvote.ucsb.parse.parse_election_years` requires — the one place under
    ``src/`` that assembles it (the ``#37`` pipeline seam; tests previously built it ad
    hoc). ``html_dir`` resolves from ``USVOTE_UCSB_HTML_DIR`` when ``None``, exactly as
    :func:`snapshot_elections` does.

    **Only ``http_status == 200`` pages are returned.** A page the server answered
    404/403/etc. was saved verbatim (the manifest records what the server said), but it
    is not usable markup and must never reach the parser. Skipping it here means the
    year is simply absent from the mapping.

    ``years`` narrows to a subset (int years); ``None`` returns every 200 page. A
    requested year that is missing or non-200 is **not** raised on here — it falls
    through absent, and :func:`usvote.ucsb.transform._scope_years` raises the
    ``UCSBMissingYearError`` that names it with the actionable "re-run the snapshot or
    narrow ``years``" guidance. Raising here too would be a second guard for one
    condition, and the worse-worded one would fire first.

    Raises :class:`UCSBScrapeError` only for a structurally broken snapshot: a 200
    manifest entry whose ``{year}.html`` file is missing from disk (the manifest and the
    directory disagree — a corrupt snapshot, not an absent year).
    """
    directory = Path(_resolve_html_dir(html_dir, environ))
    manifest = read_manifest(directory)
    wanted = None if years is None else {int(y) for y in years}

    html_by_year: dict[int, str] = {}
    for raw_year, entry in manifest.items():
        if not isinstance(entry, Mapping) or entry.get("http_status") != 200:
            continue
        year = int(raw_year)
        if wanted is not None and year not in wanted:
            continue
        page = directory / entry.get("file", f"{year}.html")
        if not page.exists():
            raise UCSBScrapeError(
                f"manifest records {page.name} at HTTP 200 for {year}, but the file is "
                f"missing from {directory}. The snapshot and its manifest disagree; "
                f"re-run `python -m usvote.ucsb` to repair it."
            )
        # Match the verbatim-bytes snapshot's tolerance: decode replacing any stray
        # bytes rather than aborting the whole read on one malformed page (as
        # `_read_index` does for the index).
        html_by_year[year] = page.read_text(encoding="utf-8", errors="replace")
    return html_by_year


def snapshot_elections(
    html_dir: str | Path | None = None,
    *,
    fetch: Fetch = fetch_url,
    sleep: Callable[[float], None] = time.sleep,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Snapshot every UCSB election page into ``html_dir``; return the manifest.

    When ``html_dir`` is ``None`` the directory is resolved from
    ``USVOTE_UCSB_HTML_DIR`` via :func:`usvote.ucsb.config.ucsb_html_dir_from_env`
    (pass ``environ`` to drive that in tests; it defaults to the process environment).

    Walks the years enumerated from the saved index, in order, honoring the module's
    politeness contract: it waits :data:`CRAWL_DELAY_SECONDS` between fetches (but never
    before the first, and never for a page it already has), saves each response verbatim
    alongside its sha256, and **stops the run entirely** the moment the server answers
    403/429. A transport error is recorded and skipped, since it says nothing about the
    server's willingness to serve us. The manifest is rewritten after every page so an
    interrupted run leaves an accurate record.

    Raises :class:`UCSBScrapeError` if the index is missing or yields no links, and
    :class:`~usvote.config.ConfigError` if the env var is unset or points nowhere.
    """
    directory = Path(_resolve_html_dir(html_dir, environ))
    year_urls = enumerate_year_urls(_read_index(directory))
    manifest = read_manifest(directory)
    total = len(year_urls)
    print(f"Enumerated {total} election pages: {year_urls[0][0]}..{year_urls[-1][0]}")

    fetched = 0
    for position, (year, url) in enumerate(year_urls, start=1):
        progress = f"[{position}/{total}] {year}"
        page = directory / f"{year}.html"
        if page.exists() and manifest.get(year, {}).get("http_status") == 200:
            print(f"{progress}: skip (already have)")
            continue

        # Between fetches only: the first costs no wait, and a skipped page never
        # touched the server, so it owes it no delay either.
        if fetched:
            sleep(CRAWL_DELAY_SECONDS)
        result = fetch(url)

        if result.error is not None:
            print(f"{progress}: {result.error} -- logging, continuing")
            manifest[year] = _error_entry(url, None, result.error)
            write_manifest(directory, manifest)
            continue

        if result.status in BLOCKED_STATUSES:
            print(
                f"{progress}: HTTP {result.status} -> BLOCKED, "
                f"stopping to respect server"
            )
            manifest[year] = _error_entry(url, result.status, "blocked")
            write_manifest(directory, manifest)
            break

        # Any other status (200, or an oddity like 404) is saved verbatim: the manifest
        # records what the server actually said, and parse decides what is usable.
        page.write_bytes(result.body)
        manifest[year] = {
            "url": url,
            "file": page.name,
            "http_status": result.status,
            "bytes": len(result.body),
            "sha256": hashlib.sha256(result.body).hexdigest(),
            "timestamp": _now(),
        }
        fetched += 1
        print(f"{progress}: {result.status} {len(result.body)}b saved")
        write_manifest(directory, manifest)

    write_manifest(directory, manifest)
    ok = sum(1 for entry in manifest.values() if entry.get("http_status") == 200)
    print(f"DONE. {ok}/{total} pages at 200. {fetched} fetched this run.")
    return manifest


def _resolve_html_dir(
    html_dir: str | Path | None, environ: Mapping[str, str] | None
) -> str | Path:
    """Return ``html_dir``, or resolve it from the environment when not given."""
    if html_dir is not None:
        return html_dir
    return (
        ucsb_html_dir_from_env(environ)
        if environ is not None
        else ucsb_html_dir_from_env()
    )


def _read_index(directory: Path) -> str:
    """Return the saved index markup, or raise :class:`UCSBScrapeError`."""
    index_path = directory / INDEX_FILENAME
    try:
        markup = index_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise UCSBScrapeError(
            f"No saved index at {index_path}. This module does not fetch the index "
            f"itself — save it once, identifying truthfully:\n"
            f"  curl -A '{USER_AGENT}' {UCSB_BASE_URL}{ELECTIONS_INDEX_PATH} "
            f'-o "{index_path}"'
        ) from exc
    if not _YEAR_LINK_RE.search(markup):
        raise UCSBScrapeError(
            f"The saved index at {index_path} links no election years "
            f"(expected hrefs like '{ELECTIONS_INDEX_PATH}/1824'). Re-save it and "
            f"check whether UCSB restructured the page."
        )
    return markup


def _error_entry(url: str, status: int | None, error: str) -> dict[str, Any]:
    """Build a manifest entry for a page that was not saved."""
    return {"url": url, "http_status": status, "timestamp": _now(), "error": error}


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for manifest provenance."""
    return datetime.now(UTC).isoformat()
