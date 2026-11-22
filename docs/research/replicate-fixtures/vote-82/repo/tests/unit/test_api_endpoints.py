"""Unit tests for the ``/v1`` data endpoints (``usvote.api.routes``, E8-S3 #97).

All offline, **no live DB** (D028): the shared synthetic ``ec_pv_redistributable``-shaped
frame (``tests/fixtures/api_snapshot.py``) is materialized into a real SQLite snapshot via
:func:`usvote.snapshot.build_snapshot`, and the app serves that file. The
``snapshot_path`` / ``settings`` / ``client`` fixtures come from ``tests/unit/conftest.py``
(#99). Covers each endpoint's happy path, the ``state`` / ``candidate`` / ``year_from`` /
``year_to`` filters, 404 (unknown / out-of-window identifier) vs. 200-empty (empty filter),
422 (bad / inverted params), the ETag / 304 freshness — including the architect's
*404-not-304* case — the server-side cap failing loud, and the D006 / D030 guards (no
``candidate_id``, no non-MIT row reachable).

The shared 2020 rows match this story's original fixture, so the value-specific rollup
assertions below are unchanged; 2016 is the shared flip year (structural assertions only
here — the flip itself is asserted in ``test_api_e2e``).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from usvote.api import create_app
from usvote.api.config import ApiSettings

# --- list years -------------------------------------------------------------


def test_list_elections_returns_years_with_counts(client: TestClient) -> None:
    body = client.get("/v1/elections").json()
    assert [item["year"] for item in body["data"]] == [2016, 2020]
    assert all(item["candidate_count"] == 2 for item in body["data"])
    assert body["meta"]["count"] == 2
    prov = body["meta"]["provenance"]
    assert prov["source"] == "MIT"
    assert prov["source_name"] == "MIT Election Lab"
    assert prov["license"] == "CC0-1.0"
    assert prov["license_url"]
    assert "UCSB" in prov["redistributable_note"]
    assert prov["coverage"] == {"year_min": 2016, "year_max": 2020}
    assert prov["snapshot_version"]


def test_list_elections_year_filter(client: TestClient) -> None:
    body = client.get("/v1/elections", params={"year_from": 2020}).json()
    assert [item["year"] for item in body["data"]] == [2020]
    assert body["meta"]["count"] == 1


# --- one election -----------------------------------------------------------


def test_get_election_returns_rows_and_summary(client: TestClient) -> None:
    body = client.get("/v1/elections/2020").json()
    assert body["meta"]["count"] == 4  # 2 states x 2 candidates; summary not counted
    assert len(body["data"]) == 4
    assert len(body["summary"]) == 2
    row = body["data"][0]
    # Public field names, not the internal snapshot columns.
    assert "electoral_votes" in row
    assert "popular_votes" in row
    assert "state_popular_total" in row
    assert "state_electoral_votes" in row
    assert "president_electoral_votes" not in row
    assert "candidate_id" not in row


def test_get_election_state_filter(client: TestClient) -> None:
    body = client.get("/v1/elections/2020", params={"state": "TX"}).json()
    assert len(body["data"]) == 2
    assert {r["state_usps"] for r in body["data"]} == {"TX"}


def test_get_election_candidate_filter(client: TestClient) -> None:
    body = client.get("/v1/elections/2020", params={"candidate": "cand-b"}).json()
    assert len(body["data"]) == 2
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}


def test_get_election_empty_filter_is_200(client: TestClient) -> None:
    """A filter that matches nothing on a known year is a 200 empty, not a 404."""
    resp = client.get("/v1/elections/2020", params={"state": "FL"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["count"] == 0


def test_get_election_unknown_year_404(client: TestClient) -> None:
    resp = client.get("/v1/elections/1800")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "year_not_found"
    assert "1800" in body["error"]["message"]
    assert resp.headers["cache-control"] == "no-store"
    assert "etag" not in resp.headers


# --- national summary -------------------------------------------------------


def test_get_election_summary_reads_rollup(client: TestClient) -> None:
    body = client.get("/v1/elections/2020/summary").json()
    assert body["meta"]["count"] == 2
    by_slug = {r["candidate_slug"]: r for r in body["data"]}
    winner = by_slug["cand-b"]
    assert winner["national_electoral_votes"] == 55
    assert winner["took_office"] is True
    assert winner["national_pv_votes"] == 6_000_000 + 11_000_000
    assert winner["national_pv_denominator"] == 11_000_000 + 17_000_000
    # No hybrid / flip / margin fields (E8-S8).
    assert "margin" not in winner
    assert "hybrid" not in winner


def test_get_summary_unknown_year_404(client: TestClient) -> None:
    resp = client.get("/v1/elections/1900/summary")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "year_not_found"


def test_summary_ignores_row_filters_on_the_year_endpoint(client: TestClient) -> None:
    """The national ``summary`` is not narrowed by a ``data`` filter (documented)."""
    body = client.get("/v1/elections/2020", params={"candidate": "cand-b"}).json()
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}
    # summary still lists every candidate — it's the national roll-up for the year.
    assert {r["candidate_slug"] for r in body["summary"]} == {"cand-a", "cand-b"}


# --- one state --------------------------------------------------------------


def test_get_state_across_years(client: TestClient) -> None:
    body = client.get("/v1/states/CA").json()
    assert {r["state_usps"] for r in body["data"]} == {"CA"}
    assert {r["year"] for r in body["data"]} == {2016, 2020}
    assert body["meta"]["count"] == 4


def test_get_state_is_case_insensitive(client: TestClient) -> None:
    assert client.get("/v1/states/ca").json()["meta"]["count"] == 4


def test_get_state_year_window(client: TestClient) -> None:
    body = client.get("/v1/states/CA", params={"year_from": 2020}).json()
    assert {r["year"] for r in body["data"]} == {2020}


def test_get_state_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/states/ZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "state_not_found"


# --- one candidate ----------------------------------------------------------


def test_get_candidate_across_years(client: TestClient) -> None:
    body = client.get("/v1/candidates/cand-b").json()
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}
    assert body["meta"]["count"] == 4


def test_get_candidate_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/candidates/nobody")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "candidate_not_found"


# --- validation (422) -------------------------------------------------------


def test_inverted_year_window_is_422(client: TestClient) -> None:
    resp = client.get("/v1/states/CA", params={"year_from": 2020, "year_to": 2016})
    assert resp.status_code == 422


def test_non_integer_year_path_is_422(client: TestClient) -> None:
    assert client.get("/v1/elections/notayear").status_code == 422


def test_non_integer_query_param_is_422(client: TestClient) -> None:
    resp = client.get("/v1/states/CA", params={"year_from": "abc"})
    assert resp.status_code == 422


# --- freshness / caching ----------------------------------------------------


def test_data_endpoint_carries_etag_and_cache_control(client: TestClient) -> None:
    resp = client.get("/v1/elections/2020")
    assert resp.headers["cache-control"].startswith("public, max-age=3600")
    assert resp.headers["etag"]


def test_conditional_get_304_on_existing_resource(client: TestClient) -> None:
    etag = client.get("/v1/elections/2020").headers["etag"]
    resp = client.get("/v1/elections/2020", headers={"If-None-Match": etag})
    assert resp.status_code == 304
    assert resp.content == b""


def test_conditional_get_unknown_year_is_404_not_304(client: TestClient) -> None:
    """A conditional GET to an unknown resource must 404, never 304 (architect note)."""
    etag = client.get("/v1/elections/2020").headers["etag"]
    resp = client.get("/v1/elections/1800", headers={"If-None-Match": etag})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "year_not_found"
    assert resp.headers["cache-control"] == "no-store"


# --- D006 / D030 guards -----------------------------------------------------


def test_no_endpoint_exposes_candidate_id(client: TestClient) -> None:
    for path in (
        "/v1/elections",
        "/v1/elections/2020",
        "/v1/elections/2020/summary",
        "/v1/states/CA",
        "/v1/candidates/cand-a",
    ):
        assert "candidate_id" not in client.get(path).text, path


# The "no served row is non-MIT" sweep now lives in test_api_redistributable_guard.py
# (full year/state/candidate sweep), superseding the old three-path spot-check here.


# --- server-side cap fails loud, never truncates ----------------------------


def test_row_cap_fails_loud(settings: ApiSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exceeding MAX_ROWS raises (500), never silently truncates."""
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 1, raising=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        resp = c.get("/v1/states/CA")  # 4 rows > cap of 1
        assert resp.status_code == 500
