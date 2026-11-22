"""Live-Postgres integration test for the full EC load path.

Excluded by default via the ``integration`` marker; run with
``pytest -m integration`` against a real database. Drives the *whole pipeline*
over the 2016 + 2020 Archives fixtures into Postgres and asserts row counts +
grain (PK uniqueness, FK containment). It lives with ``load`` rather than
``pipeline`` because the load into a real database is what it verifies; see
``run_ec_pipeline`` for the wiring. Config and the skip-if-unset guard come from
the shared ``integration_db_config`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._helpers import FIXTURES_DIR, fake_state_geo
from usvote.db import DBC
from usvote.load import SCHEMA, TABLE_NAMES


@pytest.mark.integration
def test_fixture_slice_loads_into_real_postgres(
    integration_db_config: dict[str, Any],
) -> None:
    """Drive the 2016 + 2020 fixture slice through the whole pipeline into Postgres.

    Replays the Archives fixtures offline (``fetch_from_dir``) and injects the fake
    state-geo frame (``load_geo``), so no network or TIGER shapefile is needed —
    only a live database (config + skip from the shared ``integration_db_config``
    fixture).
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # The fixture dir names pages by year; a link-index fixture drives the two
        # snapshotted years (2016, 2020) through the real scrape->load spine.
        candidates_df, state_df, votes_df = run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        counts = {
            t: dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{t}"
            )["n"].iloc[0]
            for t in TABLE_NAMES
        }
        # Every built frame lands in full.
        assert counts["state"] == len(state_df) == 51
        assert counts["candidate"] == len(candidates_df)
        assert counts["votes"] == len(votes_df)

        # Grain: primary keys are unique (a broken grain would have raised on the
        # PK constraint at insert, but assert explicitly for a clear signal).
        for table, pk in (("candidate", "candidate_id"), ("votes", "votes_id")):
            dup = dbc.select_query_to_df(
                f"SELECT {pk} FROM {SCHEMA}.{table} "
                f"GROUP BY {pk} HAVING count(*) > 1"
            )
            assert dup.empty, f"{table}.{pk} not unique"

        # FK containment: every votes.candidate_id resolves to a candidate, and
        # every non-null votes.state resolves to a state.
        orphan_cand = dbc.select_query_to_df(
            f"SELECT v.candidate_id FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.candidate c USING (candidate_id) "
            f"WHERE c.candidate_id IS NULL"
        )
        assert orphan_cand.empty
        orphan_state = dbc.select_query_to_df(
            f"SELECT v.state FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.state s USING (state) "
            f"WHERE v.state IS NOT NULL AND s.state IS NULL"
        )
        assert orphan_state.empty
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
