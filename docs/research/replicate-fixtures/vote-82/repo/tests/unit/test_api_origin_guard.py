"""Origin lock-down guard (E8-S7, #101 / D034).

The guard is opt-in + fail-open: unset secret ⇒ no enforcement (the local/CI default);
set ⇒ ``/v1`` requires the Cloudflare-injected secret header, ``/health`` stays exempt.
Both postures are asserted here, plus the observable ``/health`` field.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.api.origin_guard import ORIGIN_SECRET_HEADER

_SECRET = "cloudflare-origin-token-abc123"


@pytest.fixture
def enforced_client(snapshot_path: str) -> Iterator[TestClient]:
    """A client whose app has the origin guard ENFORCED (secret configured)."""
    settings = ApiSettings(snapshot_path=snapshot_path, origin_secret=_SECRET)
    with TestClient(create_app(settings)) as c:
        yield c


# --- fail-open (the default `client` fixture carries no secret) ---------------


def test_open_by_default_allows_v1_without_header(client: TestClient) -> None:
    resp = client.get("/v1/meta")
    assert resp.status_code == 200


def test_health_reports_open_when_unset(client: TestClient) -> None:
    assert client.get("/health").json()["origin_guard"] == "open"


# --- enforced ----------------------------------------------------------------


def test_enforced_rejects_v1_without_header(enforced_client: TestClient) -> None:
    resp = enforced_client.get("/v1/meta")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden_origin"
    # A rejection is never cached (it is not a representation of the resource).
    assert resp.headers["cache-control"] == "no-store"


def test_enforced_rejects_wrong_secret(enforced_client: TestClient) -> None:
    resp = enforced_client.get("/v1/meta", headers={ORIGIN_SECRET_HEADER: "nope"})
    assert resp.status_code == 403


def test_enforced_allows_v1_with_correct_secret(enforced_client: TestClient) -> None:
    resp = enforced_client.get("/v1/meta", headers={ORIGIN_SECRET_HEADER: _SECRET})
    assert resp.status_code == 200


def test_enforced_non_ascii_header_is_403_not_500(enforced_client: TestClient) -> None:
    # A non-ASCII secret header must be a clean 403, not a 500. Sent as raw *bytes*
    # (as a real client would): uvicorn/Starlette decode header bytes as latin-1, so the
    # guard sees a non-ASCII str — and str hmac.compare_digest raises TypeError (→ 500).
    # The guard compares bytes to avoid that (regression for the code-review finding).
    resp = enforced_client.get(
        "/v1/meta", headers={ORIGIN_SECRET_HEADER: b"\xff\xfe\x80"}
    )
    assert resp.status_code == 403


def test_enforced_covers_data_routes(enforced_client: TestClient) -> None:
    # A data route (not just /meta) is protected too — the synthetic frame has 2016.
    assert enforced_client.get("/v1/elections/2016").status_code == 403
    ok = enforced_client.get(
        "/v1/elections/2016", headers={ORIGIN_SECRET_HEADER: _SECRET}
    )
    assert ok.status_code == 200


def test_enforced_exempts_health(enforced_client: TestClient) -> None:
    # Cloud Run probes + the D033 container smoke test never traverse Cloudflare, so
    # /health must answer without the secret — and report the enforced posture.
    resp = enforced_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["origin_guard"] == "enforced"
