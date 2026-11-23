"""Live-Postgres integration test for ``usvote.db.DBC``.

Excluded by default via the ``integration`` marker; run with
``pytest -m integration`` against a real database. Config and the skip-if-unset
guard come from the shared ``integration_db_config`` fixture in
``tests/conftest.py``. Split out of the ``DBC`` unit tests so the offline suite
carries no live-DB code path.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from usvote.db import DBC


@pytest.mark.integration
def test_roundtrip_against_real_postgres(integration_db_config: dict[str, Any]) -> None:
    """Smoke test against a real database (config + skip from the shared fixture)."""
    dbc = DBC(integration_db_config)
    try:
        dbc.create_schema("usvote_test", replace=True)
        dbc.create_table("usvote_test", "t", [("id", "integer")])
        dbc.insert_df_into_table("usvote_test", "t", pd.DataFrame({"id": [1, 2]}))
        out = dbc.select_query_to_df("SELECT id FROM usvote_test.t ORDER BY id")
        assert out["id"].tolist() == [1, 2]
    finally:
        dbc.delete_schema("usvote_test", option="Cascade")
        dbc.close_connection()
