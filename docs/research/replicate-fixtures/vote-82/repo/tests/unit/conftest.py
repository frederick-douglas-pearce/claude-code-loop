"""Shared pytest fixtures for the unit suite — the API snapshot scaffolding (#99).

These consolidate the ``snapshot_path`` / ``settings`` / ``client`` fixtures that
``test_api_app`` (#96), ``test_api_endpoints`` (#97), and ``test_api_openapi`` (#98)
each used to define identically. The snapshot is **built at test time** from the shared
synthetic frame (:func:`tests.fixtures.api_snapshot.synthetic_ec_pv_frame`) through the
real :func:`usvote.snapshot.build_snapshot` writer, so it needs **no live Postgres**
(D028) and cannot drift from the snapshot schema.

A test that needs a bespoke frame can override the ``synthetic_frame`` fixture locally;
the ``snapshot_path`` / ``settings`` / ``client`` chain then rebuilds from it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import SNAPSHOT_TS, synthetic_ec_pv_frame
from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.snapshot import build_snapshot


@pytest.fixture
def synthetic_frame() -> pd.DataFrame:
    """The canonical synthetic ``ec_pv_redistributable`` frame (override to customize)."""
    return synthetic_ec_pv_frame()


@pytest.fixture
def snapshot_path(tmp_path: Path, synthetic_frame: pd.DataFrame) -> str:
    """A real SQLite snapshot built from ``synthetic_frame`` — no live DB."""
    out = str(tmp_path / "snapshot.sqlite")
    build_snapshot(synthetic_frame, out, build_timestamp=SNAPSHOT_TS)
    return out


@pytest.fixture
def settings(snapshot_path: str) -> ApiSettings:
    return ApiSettings(snapshot_path=snapshot_path, cors_origins=["http://localhost:5173"])


@pytest.fixture
def client(settings: ApiSettings) -> Iterator[TestClient]:
    # ``with`` runs the lifespan, so app.state.repository is opened (no live DB).
    with TestClient(create_app(settings)) as c:
        yield c
