"""Unit tests for :mod:`usvote.ucsb.scrape` — the ported UCSB snapshot (#34).

**No test here touches the network**, which is an acceptance criterion of #34 rather
than a stylistic preference: the real 60-election snapshot already exists and a CI run
must never re-fetch it from UCSB. Two seams keep that true — ``fetch`` (injected fakes
return canned responses) and ``sleep`` (recorded, so honoring ``Crawl-delay: 10`` costs
the suite no wall-clock).

The politeness behaviors D023 says must survive the port get **two layers** of coverage,
because the seam alone cannot see all of them:

- Above the seam, ``TestSnapshotElections`` drives the loop with fake fetches: the halt,
  the skip, the delay, the manifest.
- Below it, ``TestFetchUrl`` exercises the real :func:`~usvote.ucsb.scrape.fetch_url`
  against a fake ``urlopen``. This is where the truthful User-Agent and the
  ``HTTPError`` -> status mapping live, and neither is observable from an injected
  ``FetchResult`` — a fake returning ``status=403`` proves the loop halts on a 403, not
  that a real 403 *becomes* one. Since ``HTTPError`` subclasses ``URLError``, an
  inverted ``except`` order would silently disarm the halt while the loop tests stayed
  green: exactly D023's "invisible until the site blocks us."
"""

from __future__ import annotations

import hashlib
import io
from email.message import Message
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError

import pytest

from usvote import config
from usvote.ucsb import scrape
from usvote.ucsb.config import UCSB_HTML_DIR_VAR

# A stand-in for the saved index: the real page links each election several times over,
# in markup far bulkier than this, but enumeration only ever reads the hrefs. Contains a
# duplicate (1824) and an unsorted order to pin de-duplication and sorting.
INDEX_HTML = """
<div class="view-content">
  <span class="field-content"><a href="/statistics/elections/1876">1876</a></span>
  <span class="field-content"><a href="/statistics/elections/1824">1824</a></span>
  <span class="field-content"><a href="/statistics/elections/2024">2024</a></span>
  <span class="field-content"><a href="/statistics/elections/1824">1824</a></span>
  <a href="/statistics/elections">Elections index</a>
  <a href="/about">About</a>
</div>
"""


class FakeFetch:
    """A :data:`~usvote.ucsb.scrape.Fetch` returning canned responses, recording URLs.

    Defaults to a 200 carrying the year's own markup, so a test only has to name the
    years it wants to behave *differently* (a block, a transport error).
    """

    def __init__(self, responses: dict[str, scrape.FetchResult] | None = None) -> None:
        self.responses = responses or {}
        self.urls: list[str] = []

    def __call__(self, url: str) -> scrape.FetchResult:
        self.urls.append(url)
        year = url.rsplit("/", 1)[-1]
        return self.responses.get(
            year, scrape.FetchResult(200, f"<html>{year}</html>".encode())
        )


class RecordingSleep:
    """Records every delay instead of taking it, so tests do not wait 10s per page."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    """An otherwise-empty snapshot directory holding just the saved index."""
    (tmp_path / scrape.INDEX_FILENAME).write_text(INDEX_HTML, encoding="utf-8")
    return tmp_path


def read_manifest(directory: Path) -> dict[str, Any]:
    return scrape.read_manifest(directory)


class TestEnumerateYearUrls:
    def test_returns_sorted_deduplicated_year_url_pairs(self) -> None:
        assert scrape.enumerate_year_urls(INDEX_HTML) == [
            ("1824", "https://www.presidency.ucsb.edu/statistics/elections/1824"),
            ("1876", "https://www.presidency.ucsb.edu/statistics/elections/1876"),
            ("2024", "https://www.presidency.ucsb.edu/statistics/elections/2024"),
        ]

    def test_years_are_strings(self) -> None:
        # Not cosmetic: years are manifest keys, and JSON object keys are strings. An
        # int year would miss every existing entry on lookup, so skip-if-already-have
        # would silently never fire and a re-run would re-scrape all 60 pages.
        assert all(isinstance(year, str) for year, _ in scrape.enumerate_year_urls(INDEX_HTML))

    def test_ignores_non_election_links(self) -> None:
        years = [year for year, _ in scrape.enumerate_year_urls(INDEX_HTML)]
        assert "elections" not in years and "about" not in years

    def test_empty_index_yields_nothing(self) -> None:
        assert scrape.enumerate_year_urls("<html><body>No links</body></html>") == []


class TestManifestIO:
    def test_missing_manifest_reads_as_empty(self, tmp_path: Path) -> None:
        assert scrape.read_manifest(tmp_path) == {}

    def test_write_then_read_round_trips(self, tmp_path: Path) -> None:
        manifest = {"1824": {"http_status": 200, "bytes": 42}}
        scrape.write_manifest(tmp_path, manifest)
        assert scrape.read_manifest(tmp_path) == manifest

    def test_write_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        scrape.write_manifest(tmp_path, {"1824": {"http_status": 200}})
        # The atomic swap must consume its temp file, not litter the snapshot dir.
        assert [p.name for p in tmp_path.iterdir()] == [scrape.MANIFEST_FILENAME]

    def test_write_replaces_in_place_without_a_partial_state(
        self, tmp_path: Path
    ) -> None:
        # The whole point of the temp-file swap: an existing manifest is only ever
        # replaced by a complete new one. Overwriting a populated manifest still leaves
        # exactly one valid file.
        scrape.write_manifest(tmp_path, {"1824": {"http_status": 200}})
        scrape.write_manifest(tmp_path, {"1824": {"http_status": 200}, "1876": {}})
        assert scrape.read_manifest(tmp_path) == {
            "1824": {"http_status": 200},
            "1876": {},
        }

    def test_corrupt_manifest_raises_typed_error_not_a_bare_decode_error(
        self, tmp_path: Path
    ) -> None:
        # A truncated manifest (e.g. a kill mid-write on a pre-atomic build, or a bad
        # manual edit) must fail with actionable guidance, not abort the run with a raw
        # JSONDecodeError.
        (tmp_path / scrape.MANIFEST_FILENAME).write_text('{"1824": {"http_stat')
        with pytest.raises(scrape.UCSBScrapeError, match="not valid JSON"):
            scrape.read_manifest(tmp_path)


class TestSnapshotElections:
    def test_saves_every_page_and_writes_a_manifest(self, snapshot_dir: Path) -> None:
        manifest = scrape.snapshot_elections(
            snapshot_dir, fetch=FakeFetch(), sleep=RecordingSleep()
        )

        assert (snapshot_dir / "1824.html").read_bytes() == b"<html>1824</html>"
        assert sorted(manifest) == ["1824", "1876", "2024"]
        assert read_manifest(snapshot_dir) == manifest

    def test_manifest_entry_carries_full_provenance(self, snapshot_dir: Path) -> None:
        scrape.snapshot_elections(
            snapshot_dir, fetch=FakeFetch(), sleep=RecordingSleep()
        )
        entry = read_manifest(snapshot_dir)["1824"]

        body = b"<html>1824</html>"
        assert entry["url"] == "https://www.presidency.ucsb.edu/statistics/elections/1824"
        assert entry["file"] == "1824.html"
        assert entry["http_status"] == 200
        assert entry["bytes"] == len(body)
        assert entry["sha256"] == hashlib.sha256(body).hexdigest()
        assert entry["timestamp"]

    def test_sha256_is_of_the_bytes_actually_saved(self, snapshot_dir: Path) -> None:
        # The manifest is the snapshot's integrity record; a digest of anything but the
        # saved file would make it decorative.
        scrape.snapshot_elections(
            snapshot_dir, fetch=FakeFetch(), sleep=RecordingSleep()
        )
        for year, entry in read_manifest(snapshot_dir).items():
            saved = (snapshot_dir / f"{year}.html").read_bytes()
            assert entry["sha256"] == hashlib.sha256(saved).hexdigest()

    def test_honors_crawl_delay_between_fetches_but_not_before_the_first(
        self, snapshot_dir: Path
    ) -> None:
        sleep = RecordingSleep()
        scrape.snapshot_elections(snapshot_dir, fetch=FakeFetch(), sleep=sleep)

        # Three pages, two gaps -- the delay is a courtesy between requests, not a toll
        # on starting.
        assert sleep.delays == [scrape.CRAWL_DELAY_SECONDS] * 2

    def test_skips_pages_already_snapshotted(self, snapshot_dir: Path) -> None:
        scrape.snapshot_elections(
            snapshot_dir, fetch=FakeFetch(), sleep=RecordingSleep()
        )

        refetch = FakeFetch()
        sleep = RecordingSleep()
        scrape.snapshot_elections(snapshot_dir, fetch=refetch, sleep=sleep)

        # A re-run over a complete snapshot must cost the server nothing at all.
        assert refetch.urls == []
        assert sleep.delays == []

    def test_skipped_pages_owe_no_delay_but_fetched_ones_still_do(
        self, snapshot_dir: Path
    ) -> None:
        (snapshot_dir / "1824.html").write_bytes(b"<html>1824</html>")
        scrape.write_manifest(snapshot_dir, {"1824": {"http_status": 200}})

        fetch = FakeFetch()
        sleep = RecordingSleep()
        scrape.snapshot_elections(snapshot_dir, fetch=fetch, sleep=sleep)

        # 1824 is skipped; 1876 is the run's first real fetch (no delay) and 2024 its
        # second (one delay). A skip must not "use up" the gap the next fetch owes.
        assert [url.rsplit("/", 1)[-1] for url in fetch.urls] == ["1876", "2024"]
        assert sleep.delays == [scrape.CRAWL_DELAY_SECONDS]

    def test_refetches_a_page_whose_previous_status_was_not_200(
        self, snapshot_dir: Path
    ) -> None:
        (snapshot_dir / "1824.html").write_bytes(b"<html>stale 500</html>")
        scrape.write_manifest(snapshot_dir, {"1824": {"http_status": 500}})

        fetch = FakeFetch()
        scrape.snapshot_elections(snapshot_dir, fetch=fetch, sleep=RecordingSleep())

        assert "1824" in [url.rsplit("/", 1)[-1] for url in fetch.urls]
        assert (snapshot_dir / "1824.html").read_bytes() == b"<html>1824</html>"

    @pytest.mark.parametrize("status", sorted(scrape.BLOCKED_STATUSES))
    def test_halts_immediately_when_the_server_says_stop(
        self, snapshot_dir: Path, status: int
    ) -> None:
        # 1824 sorts first, so a block there must stop the run before 1876 and 2024 are
        # ever requested -- "halt", not "skip and carry on".
        fetch = FakeFetch({"1824": scrape.FetchResult(status, b"denied")})
        sleep = RecordingSleep()

        manifest = scrape.snapshot_elections(snapshot_dir, fetch=fetch, sleep=sleep)

        assert len(fetch.urls) == 1
        assert manifest["1824"] == {
            "url": "https://www.presidency.ucsb.edu/statistics/elections/1824",
            "http_status": status,
            "timestamp": manifest["1824"]["timestamp"],
            "error": "blocked",
        }
        assert not (snapshot_dir / "1824.html").exists()
        assert sorted(read_manifest(snapshot_dir)) == ["1824"]

    def test_a_block_mid_run_keeps_what_was_already_saved(
        self, snapshot_dir: Path
    ) -> None:
        fetch = FakeFetch({"1876": scrape.FetchResult(429, b"slow down")})
        manifest = scrape.snapshot_elections(
            snapshot_dir, fetch=fetch, sleep=RecordingSleep()
        )

        assert (snapshot_dir / "1824.html").exists()
        assert manifest["1876"]["error"] == "blocked"
        assert "2024" not in manifest
        assert not (snapshot_dir / "2024.html").exists()

    def test_transport_error_is_logged_and_the_run_continues(
        self, snapshot_dir: Path
    ) -> None:
        # A refused connection says nothing about the server's willingness to serve us,
        # so unlike a 403 it is not a reason to abandon the pass.
        fetch = FakeFetch({"1824": scrape.FetchResult(None, b"", "timed out")})
        manifest = scrape.snapshot_elections(
            snapshot_dir, fetch=fetch, sleep=RecordingSleep()
        )

        assert manifest["1824"]["error"] == "timed out"
        assert manifest["1824"]["http_status"] is None
        assert not (snapshot_dir / "1824.html").exists()
        assert (snapshot_dir / "1876.html").exists()
        assert (snapshot_dir / "2024.html").exists()

    def test_non_blocking_error_status_is_saved_verbatim(
        self, snapshot_dir: Path
    ) -> None:
        fetch = FakeFetch({"1824": scrape.FetchResult(404, b"<html>gone</html>")})
        manifest = scrape.snapshot_elections(
            snapshot_dir, fetch=fetch, sleep=RecordingSleep()
        )

        # Recorded honestly rather than dropped: the manifest says what the server said.
        assert (snapshot_dir / "1824.html").read_bytes() == b"<html>gone</html>"
        assert manifest["1824"]["http_status"] == 404
        assert len(fetch.urls) == 3

    def test_manifest_is_written_after_each_page_not_only_at_the_end(
        self, snapshot_dir: Path
    ) -> None:
        # An interrupted run must leave an accurate record of what it managed to save.
        observed: list[list[str]] = []

        def fetch_recording_manifest(url: str) -> scrape.FetchResult:
            observed.append(sorted(read_manifest(snapshot_dir)))
            return FakeFetch()(url)

        scrape.snapshot_elections(
            snapshot_dir, fetch=fetch_recording_manifest, sleep=RecordingSleep()
        )

        assert observed == [[], ["1824"], ["1824", "1876"]]


class TestSnapshotElectionsConfig:
    def test_resolves_the_directory_from_the_environment(
        self, snapshot_dir: Path
    ) -> None:
        scrape.snapshot_elections(
            fetch=FakeFetch(),
            sleep=RecordingSleep(),
            environ={UCSB_HTML_DIR_VAR: str(snapshot_dir)},
        )
        assert (snapshot_dir / "1824.html").exists()

    def test_unset_env_var_raises_config_error(self) -> None:
        with pytest.raises(config.ConfigError, match=UCSB_HTML_DIR_VAR):
            scrape.snapshot_elections(fetch=FakeFetch(), sleep=RecordingSleep(), environ={})

    def test_explicit_dir_beats_the_environment(self, snapshot_dir: Path) -> None:
        scrape.snapshot_elections(
            snapshot_dir,
            fetch=FakeFetch(),
            sleep=RecordingSleep(),
            environ={UCSB_HTML_DIR_VAR: "/no/such/ucsb_raw"},
        )
        assert (snapshot_dir / "1824.html").exists()

    def test_missing_index_raises_with_the_bootstrap_command(
        self, tmp_path: Path
    ) -> None:
        # The deliberate bootstrap gap: this module never fetches the index itself, so
        # the error has to hand the reader the polite command that fixes it.
        with pytest.raises(scrape.UCSBScrapeError) as excinfo:
            scrape.snapshot_elections(
                tmp_path, fetch=FakeFetch(), sleep=RecordingSleep()
            )
        assert f"-A '{scrape.USER_AGENT}'" in str(excinfo.value)

    def test_index_without_election_links_raises(self, tmp_path: Path) -> None:
        # The shape an upstream redesign takes. Failing loudly beats "Enumerated 0
        # election pages, exit 0", which reads as success.
        (tmp_path / scrape.INDEX_FILENAME).write_text("<html>Moved</html>")
        fetch = FakeFetch()

        with pytest.raises(scrape.UCSBScrapeError, match="links no election years"):
            scrape.snapshot_elections(tmp_path, fetch=fetch, sleep=RecordingSleep())
        assert fetch.urls == []


def _write_page(directory: Path, year: int, html: str) -> None:
    (directory / f"{year}.html").write_text(html, encoding="utf-8")


def _manifest_entry(year: int, status: int) -> dict[str, Any]:
    return {"url": f".../{year}", "file": f"{year}.html", "http_status": status}


class TestReadSnapshotHtml:
    """The read counterpart of the snapshot — ``{year: html}`` for the parser (#37)."""

    def test_reads_200_pages_into_an_int_keyed_mapping(self, tmp_path: Path) -> None:
        _write_page(tmp_path, 1824, "<html>1824</html>")
        _write_page(tmp_path, 1876, "<html>1876</html>")
        scrape.write_manifest(
            tmp_path, {"1824": _manifest_entry(1824, 200), "1876": _manifest_entry(1876, 200)}
        )
        assert scrape.read_snapshot_html(tmp_path) == {
            1824: "<html>1824</html>",
            1876: "<html>1876</html>",
        }

    def test_skips_non_200_pages(self, tmp_path: Path) -> None:
        # A saved 404/403 page is not usable markup and must never reach the parser;
        # the year is simply absent from the mapping (the transform then names it).
        _write_page(tmp_path, 1824, "<html>1824</html>")
        _write_page(tmp_path, 1900, "<html>not found</html>")
        scrape.write_manifest(
            tmp_path, {"1824": _manifest_entry(1824, 200), "1900": _manifest_entry(1900, 404)}
        )
        assert scrape.read_snapshot_html(tmp_path) == {1824: "<html>1824</html>"}

    def test_years_filter_narrows_the_mapping(self, tmp_path: Path) -> None:
        for year in (1824, 1876, 2020):
            _write_page(tmp_path, year, f"<html>{year}</html>")
        scrape.write_manifest(
            tmp_path, {str(y): _manifest_entry(y, 200) for y in (1824, 1876, 2020)}
        )
        assert set(scrape.read_snapshot_html(tmp_path, years={1876, 2020})) == {1876, 2020}

    def test_missing_in_scope_year_is_not_raised_here(self, tmp_path: Path) -> None:
        # A requested year with no 200 page falls through absent — the transform's
        # _scope_years owns the actionable UCSBMissingYearError, so raising here too
        # would be a second guard for one condition with the worse-worded one firing.
        _write_page(tmp_path, 1824, "<html>1824</html>")
        scrape.write_manifest(tmp_path, {"1824": _manifest_entry(1824, 200)})
        assert scrape.read_snapshot_html(tmp_path, years={1824, 1900}) == {
            1824: "<html>1824</html>"
        }

    def test_200_entry_with_no_file_on_disk_raises(self, tmp_path: Path) -> None:
        # The manifest and the directory disagree — a corrupt snapshot, distinct from an
        # absent year, so it raises rather than falling through.
        scrape.write_manifest(tmp_path, {"1824": _manifest_entry(1824, 200)})
        with pytest.raises(scrape.UCSBScrapeError, match="missing from"):
            scrape.read_snapshot_html(tmp_path)

    def test_empty_manifest_reads_as_empty_mapping(self, tmp_path: Path) -> None:
        assert scrape.read_snapshot_html(tmp_path) == {}

    def test_resolves_the_directory_from_the_environment(self, tmp_path: Path) -> None:
        _write_page(tmp_path, 1824, "<html>1824</html>")
        scrape.write_manifest(tmp_path, {"1824": _manifest_entry(1824, 200)})
        assert scrape.read_snapshot_html(
            environ={UCSB_HTML_DIR_VAR: str(tmp_path)}
        ) == {1824: "<html>1824</html>"}


class FakeResponse:
    """A minimal stand-in for the ``http.client.HTTPResponse`` ``urlopen`` returns."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status


class TestFetchUrl:
    """Cover the live-fetch function itself, below the injected ``Fetch`` seam.

    ``urlopen`` is patched at the ``usvote.ucsb.scrape`` lookup site, so these run the
    real header construction and error handling without opening a socket.
    """

    def test_sends_the_truthful_user_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The politeness AC most easily lost in a refactor, and invisible from above the
        # seam: an injected fake never sees a header. UCSB's operators identify our
        # traffic by this string.
        requests: list[Any] = []

        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            requests.append(request)
            return FakeResponse(200, b"<html>ok</html>")

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        scrape.fetch_url("https://www.presidency.ucsb.edu/statistics/elections/1824")

        request = requests[0]
        assert request.get_header("User-agent") == scrape.USER_AGENT
        assert "ClaudeBot" not in request.get_header("User-agent")

    def test_returns_status_and_body_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            scrape, "urlopen", lambda *a, **k: FakeResponse(200, b"<html>ok</html>")
        )
        assert scrape.fetch_url("https://example.test/1824") == scrape.FetchResult(
            200, b"<html>ok</html>", None
        )

    def test_passes_a_bounded_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        timeouts: list[float] = []

        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            timeouts.append(timeout)
            return FakeResponse(200, b"")

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        scrape.fetch_url("https://example.test/1824")

        # Unbounded, one stalled page could wedge the whole polite pass.
        assert timeouts == [scrape.FETCH_TIMEOUT_SECONDS]

    @pytest.mark.parametrize("status", sorted(scrape.BLOCKED_STATUSES))
    def test_http_error_status_reaches_the_caller_as_a_status(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        # The load-bearing half of the 403/429 halt. urllib raises these as HTTPError,
        # and HTTPError subclasses URLError -- so if the except order here ever
        # inverted, every blocked response would arrive as a transport error, the run
        # would keep hammering a server that just said stop, and the loop tests would
        # not notice.
        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            raise HTTPError(
                request.full_url, status, "Forbidden", Message(), io.BytesIO(b"denied")
            )

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        result = scrape.fetch_url("https://example.test/1824")

        assert result.status == status
        assert result.error is None
        assert result.status in scrape.BLOCKED_STATUSES

    def test_http_error_body_is_preserved(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            raise HTTPError(
                request.full_url,
                404,
                "Not Found",
                Message(),
                io.BytesIO(b"<html>gone</html>"),
            )

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        assert scrape.fetch_url("https://example.test/1824") == scrape.FetchResult(
            404, b"<html>gone</html>", None
        )

    def test_transport_failure_becomes_an_error_result_not_an_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            raise URLError("connection refused")

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        result = scrape.fetch_url("https://example.test/1824")

        assert result.status is None
        assert result.body == b""
        assert "connection refused" in str(result.error)

    @pytest.mark.parametrize(
        "exc",
        [
            TimeoutError("timed out"),  # socket.timeout during response.read()
            ConnectionResetError("reset by peer"),  # dropped mid-body
        ],
    )
    def test_read_phase_os_errors_are_caught_not_propagated(
        self, monkeypatch: pytest.MonkeyPatch, exc: OSError
    ) -> None:
        # These fire during response.read(), outside urllib's URLError-wrapping, and
        # are OSError siblings of URLError -- so an `except URLError` would let them
        # crash the whole scrape mid-run. Over a 60-page live pass one slow or flaky
        # page must degrade to a logged skip, never abort the run.
        def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
            raise exc

        monkeypatch.setattr(scrape, "urlopen", fake_urlopen)
        result = scrape.fetch_url("https://example.test/1824")

        assert result.status is None
        assert result.body == b""
        assert str(exc) in str(result.error)
