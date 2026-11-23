"""End-to-end API integration test over the shared synthetic snapshot (E8-S5, #99).

Drives the *running* app with FastAPI's ``TestClient`` across every ``/v1`` surface in one
walk — ``/health`` → ``/v1/meta`` → ``/v1/elections`` → ``/v1/elections/{year}`` (+ sibling
``summary``) → ``/v1/states/{usps}`` → ``/v1/candidates/{slug}`` — asserting the real
``{data, meta}`` envelope, the content-hash **ETag** + conditional-304, human provenance,
and that the fixture's 2016 **EC-winner-≠-PV-winner flip** is observable through the
national summary.

It runs in CI: the snapshot is built from an in-memory synthetic frame via
:func:`usvote.snapshot.build_snapshot`, so there is **no live Postgres** (D028). The
``client`` fixture is the shared one in ``tests/unit/conftest.py``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_envelope(body: dict) -> None:
    """Every ``{data, meta}`` response: ``meta.count == len(data)`` and MIT/CC0 provenance."""
    assert "data" in body and "meta" in body
    assert isinstance(body["data"], list)
    assert body["meta"]["count"] == len(body["data"])
    prov = body["meta"]["provenance"]
    assert prov["source"] == "MIT"
    assert prov["license"] == "CC0-1.0"
    assert prov["snapshot_version"]


def test_health_then_meta_then_data_walk(client: TestClient) -> None:
    # 1. /health — no envelope, but the loaded snapshot's coverage + source.
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["snapshot_loaded"] is True
    assert health["coverage"] == {"year_min": 2016, "year_max": 2020}
    assert health["source"] == "MIT"

    # 2. /v1/meta — provenance + the content-hash ETag.
    meta_resp = client.get("/v1/meta")
    assert meta_resp.status_code == 200
    version = meta_resp.json()["provenance"]["snapshot_version"]
    assert meta_resp.headers["etag"] == f'"{version}"'

    # 3. /v1/elections — the covered years, envelope intact.
    elections = client.get("/v1/elections").json()
    _assert_envelope(elections)
    assert [item["year"] for item in elections["data"]] == [2016, 2020]

    # 4. /v1/elections/{year} — per-state rows (public field names) + sibling summary.
    year_body = client.get("/v1/elections/2020").json()
    _assert_envelope(year_body)
    assert len(year_body["data"]) == 4  # 2 states x 2 candidates; summary not counted
    assert len(year_body["summary"]) == 2
    row = year_body["data"][0]
    assert "electoral_votes" in row and "popular_votes" in row
    assert "candidate_id" not in row  # D006: internal id never surfaced

    # 5. /v1/states/{usps} and /v1/candidates/{slug} — cross-year slices.
    tx = client.get("/v1/states/TX").json()
    _assert_envelope(tx)
    assert {r["state_usps"] for r in tx["data"]} == {"TX"}
    assert {r["year"] for r in tx["data"]} == {2016, 2020}

    cand = client.get("/v1/candidates/cand-a").json()
    _assert_envelope(cand)
    assert {r["candidate_slug"] for r in cand["data"]} == {"cand-a"}


def test_conditional_get_304_end_to_end(client: TestClient) -> None:
    """A repeat GET with the served ETag short-circuits to a bodyless 304."""
    first = client.get("/v1/elections/2016")
    etag = first.headers["etag"]
    again = client.get("/v1/elections/2016", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


def test_2016_flip_is_observable_through_summary(client: TestClient) -> None:
    """The fixture's 2016 flip: the took-office candidate leads the EC but trails the PV.

    This is the "EC winner ≠ PV winner" case the API exists to expose (2000/2016-shaped),
    asserted end-to-end through the precomputed national roll-up.
    """
    summary = client.get("/v1/elections/2016/summary").json()
    _assert_envelope(summary)
    by_slug = {r["candidate_slug"]: r for r in summary["data"]}
    took_office = by_slug["cand-b"]
    rival = by_slug["cand-a"]

    assert took_office["took_office"] is True
    assert rival["took_office"] is False
    # Won the Electoral College...
    assert took_office["national_electoral_votes"] > rival["national_electoral_votes"]
    # ...but lost the popular vote — the flip.
    assert took_office["national_pv_votes"] < rival["national_pv_votes"]
    assert took_office["national_pv_votes"] == 13_000_000
    assert rival["national_pv_votes"] == 18_000_000
