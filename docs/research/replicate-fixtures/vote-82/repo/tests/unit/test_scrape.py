"""Unit tests for ``usvote.scrape``.

These run fully offline. Two real Archives pages were captured once via
:func:`usvote.scrape.snapshot_page` and live under ``tests/fixtures/``; the tests
replay them through the ``fetch`` seam so link/table extraction is exercised
against authentic HTML without touching the network. Crafted inline fetches cover
the structural error paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4.element import Tag

from tests._helpers import FIXTURES_DIR
from usvote.scrape import (
    ARCHIVE_URL_BASE,
    ARCHIVE_URL_DOMAIN,
    Fetch,
    ScrapeError,
    _snapshot_filename,
    fetch_from_dir,
    get_html_tables,
    scrape_election_links,
    scrape_raw_election_tables,
    snapshot_page,
)

INDEX_URL = ARCHIVE_URL_DOMAIN + ARCHIVE_URL_BASE
YEAR_2020_URL = f"{ARCHIVE_URL_DOMAIN}/electoral-college/2020"


@pytest.fixture
def fixture_fetch() -> Fetch:
    """A fetch that replays the saved Archives pages in ``tests/fixtures/``."""
    return fetch_from_dir(FIXTURES_DIR)


def make_fetch(markup: bytes | str) -> Fetch:
    """A fetch that returns the same markup for any URL."""
    data = markup.encode() if isinstance(markup, str) else markup

    def _fetch(_url: str) -> bytes:
        return data

    return _fetch


# --- get_html_tables -------------------------------------------------------


def test_get_html_tables_single_returns_first_table(fixture_fetch: Fetch) -> None:
    table = get_html_tables(INDEX_URL, fetch=fixture_fetch)
    assert isinstance(table, Tag)
    assert table.name == "table"


def test_get_html_tables_find_all_returns_two_year_tables(
    fixture_fetch: Fetch,
) -> None:
    # Every year page publishes exactly two tables (Table 1 + Table 2).
    tables = get_html_tables(YEAR_2020_URL, find_all=True, fetch=fixture_fetch)
    assert isinstance(tables, list)
    assert len(tables) == 2
    assert all(t.name == "table" for t in tables)


def test_get_html_tables_missing_div_raises(fixture_fetch: Fetch) -> None:
    with pytest.raises(ScrapeError, match="No <div id='no-such-div'>"):
        get_html_tables(INDEX_URL, "no-such-div", fetch=fixture_fetch)


def test_get_html_tables_missing_table_raises() -> None:
    fetch = make_fetch("<div id='main-col'><p>no table here</p></div>")
    with pytest.raises(ScrapeError, match="No <table>"):
        get_html_tables("http://x", fetch=fetch)


# --- scrape_election_links -------------------------------------------------


def test_scrape_election_links_from_index_fixture(fixture_fetch: Fetch) -> None:
    links = scrape_election_links(fetch=fixture_fetch)
    # The captured index spans 1789 through 2024 (60 elections).
    assert len(links) == 60
    assert links[0] == f"{ARCHIVE_URL_DOMAIN}/electoral-college/1789"
    assert f"{ARCHIVE_URL_DOMAIN}/electoral-college/2020" in links
    # Every link is absolute and rooted at the Archives domain.
    assert all(link.startswith(ARCHIVE_URL_DOMAIN + "/electoral-college/") for link in links)


def test_scrape_election_links_default_url(fixture_fetch: Fetch) -> None:
    # fixture_fetch is URL-sensitive (fetch_from_dir), so this passes only if the
    # default domain/base compose into INDEX_URL, whose slug resolves to the saved
    # index fixture — i.e. it pins the default Archives URL, not just "any fetch".
    assert scrape_election_links(fetch=fixture_fetch)


# --- scrape_raw_election_tables --------------------------------------------


def test_scrape_raw_election_tables_keys_by_year(fixture_fetch: Fetch) -> None:
    tables = scrape_raw_election_tables(
        [YEAR_2020_URL], {2020}, fetch=fixture_fetch
    )
    assert list(tables.keys()) == [2020]
    assert len(tables[2020]) == 2


def test_scrape_raw_election_tables_skips_unknown_year(
    fixture_fetch: Fetch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = scrape_raw_election_tables(
        [YEAR_2020_URL], {1984}, fetch=fixture_fetch
    )
    assert tables == {}
    out = capsys.readouterr().out
    assert "2020" in out
    assert "does not match a US election year" in out


# --- snapshot seam ---------------------------------------------------------


def test_snapshot_filename_is_stable_and_slugged() -> None:
    assert _snapshot_filename(INDEX_URL) == "www_archives_gov_electoral_college_results.html"
    assert _snapshot_filename(YEAR_2020_URL) == "www_archives_gov_electoral_college_2020.html"


def test_snapshot_then_fetch_from_dir_roundtrip(tmp_path: Path) -> None:
    fetch = make_fetch("<html><body>captured</body></html>")
    dest = snapshot_page("https://example.com/page", tmp_path, fetch=fetch)

    assert dest.exists()
    assert dest.parent == tmp_path
    # A page saved under one name is found again by fetch_from_dir.
    replay = fetch_from_dir(tmp_path)
    assert replay("https://example.com/page") == b"<html><body>captured</body></html>"
