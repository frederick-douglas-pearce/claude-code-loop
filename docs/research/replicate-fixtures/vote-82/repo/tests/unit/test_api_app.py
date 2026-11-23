"""Unit tests for the FastAPI app skeleton (``usvote.api``, E8-S2 #96).

All offline, **no live DB** — the whole point of D028. The shared synthetic
``ec_pv_redistributable``-shaped frame (``tests/fixtures/api_snapshot.py``) is
materialized into a real SQLite snapshot via :func:`usvote.snapshot.build_snapshot`
(tests may touch the build stack; only ``src/usvote/api/`` may not — see
``test_api_import_graph``), and the app serves that file. The ``snapshot_path`` /
``settings`` / ``client`` fixtures come from ``tests/unit/conftest.py`` (#99). The app
never opens Postgres, which is exactly what "starts and answers with Postgres stopped"
means in a unit context.

Covered: startup fails loud on a missing/mismatched snapshot (not a request-time 500);
``/health`` reports status + version/coverage and is uncached; ``/v1/meta`` carries the
content-hash ETag + ``Cache-Control`` and honors a conditional ``If-None-Match`` (304);
CORS echoes an allow-listed origin and never a silent ``*``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import SNAPSHOT_TS, synthetic_ec_pv_frame
from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.api.repository import SnapshotError, SnapshotRepository
from usvote.config import ConfigError
from usvote.snapshot import build_snapshot

# --- startup / config -------------------------------------------------------


def test_missing_snapshot_raises_config_error_at_startup(tmp_path: Path) -> None:
    """An unset/absent snapshot fails at app build, not as a request-time 500."""
    with pytest.raises(ConfigError):
        create_app(ApiSettings.from_env({"USVOTE_API_SNAPSHOT_PATH": ""}))
    absent = str(tmp_path / "nope.sqlite")
    with pytest.raises(ConfigError):
        create_app(ApiSettings.from_env({"USVOTE_API_SNAPSHOT_PATH": absent}))


def test_opens_snapshot_path_with_spaces(tmp_path: Path) -> None:
    """A path with a space (or other URI-special char) must still open read-only.

    Guards the SQLite URI construction: a raw f-string would leave the space unencoded
    and mis-parse the ``?mode=ro`` query; ``Path.as_uri`` percent-encodes it.
    """
    spaced = tmp_path / "My Snapshots"
    spaced.mkdir()
    out = str(spaced / "snap.sqlite")
    build_snapshot(synthetic_ec_pv_frame(), out, build_timestamp=SNAPSHOT_TS)
    repo = SnapshotRepository.open(out)
    assert repo.meta().year_min == 2016


def test_schema_version_mismatch_fails_loud_at_open(
    snapshot_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot built for a different schema_version must not silently mis-serve."""
    monkeypatch.setattr(
        "usvote.api.repository.SNAPSHOT_SCHEMA_VERSION", 999, raising=True
    )
    with pytest.raises(SnapshotError, match="schema_version"):
        SnapshotRepository.open(snapshot_path)


# --- /health ----------------------------------------------------------------


def test_health_reports_status_and_snapshot_meta(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["snapshot_loaded"] is True
    assert body["snapshot_version"]  # the content hash from the build
    assert body["coverage"] == {"year_min": 2016, "year_max": 2020}
    assert body["source"] == "MIT"


def test_health_is_uncached_and_has_no_etag(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.headers["cache-control"] == "no-store"
    assert "etag" not in resp.headers


# --- /v1/meta + freshness ---------------------------------------------------


def test_v1_meta_carries_etag_and_cache_control(client: TestClient) -> None:
    resp = client.get("/v1/meta")
    assert resp.status_code == 200
    assert resp.headers["cache-control"].startswith("public, max-age=3600")
    etag = resp.headers["etag"]
    assert etag == f'"{resp.json()["provenance"]["snapshot_version"]}"'


def test_v1_meta_carries_human_provenance(client: TestClient) -> None:
    """/v1/meta spells out the source/license and the redistributable boundary (#98)."""
    prov = client.get("/v1/meta").json()["provenance"]
    assert prov["source"] == "MIT"
    assert prov["source_name"] == "MIT Election Lab"
    assert prov["license"] == "CC0-1.0"
    assert prov["license_url"].startswith("http")
    assert "UCSB" in prov["redistributable_note"]


def test_conditional_get_returns_304_when_version_matches(client: TestClient) -> None:
    etag = client.get("/v1/meta").headers["etag"]
    resp = client.get("/v1/meta", headers={"If-None-Match": etag})
    assert resp.status_code == 304
    assert resp.content == b""
    assert resp.headers["etag"] == etag


def test_conditional_get_returns_200_when_version_differs(client: TestClient) -> None:
    resp = client.get("/v1/meta", headers={"If-None-Match": '"stale-version"'})
    assert resp.status_code == 200


# --- CORS -------------------------------------------------------------------


def test_cors_echoes_allowlisted_origin_without_credentials(client: TestClient) -> None:
    resp = client.get("/v1/meta", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    # Credentials mode is off (read-only public data): never advertise it, so an
    # explicit `*` can't degrade into reflect-any-origin-with-credentials (D031).
    assert "access-control-allow-credentials" not in resp.headers


def test_cors_does_not_echo_unlisted_origin(client: TestClient) -> None:
    resp = client.get("/v1/meta", headers={"Origin": "https://evil.example"})
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"
    assert resp.headers.get("access-control-allow-origin") != "*"
