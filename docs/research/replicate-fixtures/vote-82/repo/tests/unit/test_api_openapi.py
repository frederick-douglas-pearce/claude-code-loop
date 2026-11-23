"""OpenAPI polish: metadata, tags, examples, live coverage window, /docs + /redoc (#98).

All offline, **no live DB** (D028): the shared synthetic snapshot (built from
``tests/fixtures/api_snapshot.py`` by ``tests/unit/conftest.py``, #99) is served, and the
assertions read ``/openapi.json`` + the doc HTML. The coverage-window assertion uses the
fixture's span (2016–2020), distinct from the production 1976–2024 window, so a stale
hard-coded span would be caught.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import SNAPSHOT_TS, synthetic_ec_pv_frame
from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.snapshot import build_snapshot

# --- top-level metadata -----------------------------------------------------


def test_openapi_info_has_public_metadata(client: TestClient) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["title"] == "US Presidential Vote API"
    assert info["version"] == "0.2.0"
    assert info["summary"]
    desc = info["description"]
    # The thesis + what the dataset is.
    assert "Electoral College" in desc and "popular vote" in desc
    # Provenance / licensing is prominent, and the redistributable boundary is explicit.
    assert "MIT Election Lab" in desc
    assert "CC0" in desc
    assert "UCSB" in desc
    # Points a first-time developer at the docs.
    assert "/docs" in desc and "/redoc" in desc


def test_openapi_contact_and_license(client: TestClient) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["contact"]["url"].startswith("https://github.com/")
    assert info["license"]["name"].startswith("CC0")
    assert info["license"]["url"].startswith("http")


def test_openapi_description_reflects_live_coverage_window(client: TestClient) -> None:
    """The headline coverage line is filled from the loaded snapshot, not hard-coded."""
    desc = client.get("/openapi.json").json()["info"]["description"]
    assert "2016–2020" in desc
    assert "{coverage_window}" not in desc  # placeholder was substituted


def test_openapi_without_lifespan_serves_static_fallback(tmp_path: Path) -> None:
    """Building the schema before startup (no open repository) must not raise.

    Guards the fallback in ``_install_live_openapi``: an offline
    ``create_app(...).openapi()`` (no lifespan, so ``app.state.repository`` is absent)
    serves the fully-rendered static description instead of crashing.
    """
    out = str(tmp_path / "snapshot.sqlite")
    build_snapshot(synthetic_ec_pv_frame(), out, build_timestamp=SNAPSHOT_TS)
    settings = ApiSettings(snapshot_path=out, cors_origins=["http://localhost:5173"])
    app = create_app(settings)  # no `with TestClient` → lifespan not run
    desc = app.openapi()["info"]["description"]
    assert "{coverage_window}" not in desc  # static fallback is fully rendered
    assert "Electoral College" in desc


# --- tags -------------------------------------------------------------------


def test_openapi_tags_are_grouped_and_described(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    tags = {t["name"]: t.get("description", "") for t in schema["tags"]}
    for name in ("Elections", "States", "Candidates", "Meta", "Ops"):
        assert name in tags, name
        assert tags[name], f"tag {name} has no description"


def test_endpoints_carry_the_right_tags(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/v1/elections"]["get"]["tags"] == ["Elections"]
    assert paths["/v1/states/{usps}"]["get"]["tags"] == ["States"]
    assert paths["/v1/candidates/{slug}"]["get"]["tags"] == ["Candidates"]
    assert paths["/v1/meta"]["get"]["tags"] == ["Meta"]
    assert paths["/health"]["get"]["tags"] == ["Ops"]


# --- examples ---------------------------------------------------------------


def test_response_schemas_carry_examples(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("EcPvRow", "NationalSummaryRow", "Provenance", "Meta", "ErrorBody"):
        assert schemas[name].get("examples"), f"{name} ships no OpenAPI example"


# --- interactive docs render ------------------------------------------------


def test_swagger_ui_renders(client: TestClient) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_redoc_renders(client: TestClient) -> None:
    resp = client.get("/redoc")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
