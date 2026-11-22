"""Shared pytest fixtures.

Only fixtures live here — pytest discovers them automatically for every test
under ``tests/`` (including ``tests/unit/`` and ``tests/integration/``), so no
import is needed at the call site. Plain, importable helpers (the recording
fake connection, ``make_dbc``, ``fake_state_geo``, ``STATE_NAMES``,
``FIXTURES_DIR``) live in ``tests/_helpers.py`` and are imported explicitly.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests._helpers import RecordingConnection


@pytest.fixture
def recording_conn() -> RecordingConnection:
    """A fresh fake connection whose ``.executed`` list captures SQL strings."""
    return RecordingConnection()


@pytest.fixture
def integration_db_config() -> dict[str, Any]:
    """Live-Postgres connection config from ``USVOTE_TEST_DB_*`` env vars.

    Skips the test if ``USVOTE_TEST_DB_NAME`` is unset, so the ``integration``
    marker can run locally without hard-coded credentials. Shared by every
    live-database test.
    """
    dbname = os.environ.get("USVOTE_TEST_DB_NAME")
    if not dbname:
        pytest.skip("USVOTE_TEST_DB_NAME not set; skipping live-Postgres test")
    return {
        "host": os.environ.get("USVOTE_TEST_DB_HOST", "localhost"),
        "port": int(os.environ.get("USVOTE_TEST_DB_PORT", "5432")),
        "dbname": dbname,
        "user": os.environ.get("USVOTE_TEST_DB_USER", "postgres"),
        "password": os.environ.get("USVOTE_TEST_DB_PASSWORD", ""),
    }
