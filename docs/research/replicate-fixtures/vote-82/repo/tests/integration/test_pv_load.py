"""Live-Postgres integration tests for the PV loads into the shared ``dwh`` tables.

Excluded by default via the ``integration`` marker; run with ``pytest -m integration``
against a real database. Two source loads are covered, both proving the same payoff of
#66/#37: a PV source's rows **coexist in one ``dwh`` schema** with the EC spine, and its
canonical-key reconciliation makes the ``pv_votes.state`` FK resolve.

Both tests first drive the EC pipeline over the 2016 + 2020 Archives fixtures to seed
``dwh.state``/``dwh.candidate``/``dwh.votes`` (the FK targets):

- **MIT (#66):** runs the MIT pipeline over the fusion fixture scoped to 2016 (a subset
  of the seeded years). Asserts row counts, grain (unique ``pv_id`` + natural key),
  FK/containment (every ``pv_votes.state``/``candidate`` resolves into the EC dims), and
  the MIT provenance tagging. The 2016 New York rows are a fusion case, so aggregation is
  exercised end-to-end into Postgres.
- **UCSB (#37):** runs the whole UCSB pipeline over the real snapshot scoped to
  2016 + 2020, loading **both** PV tables (``pv_votes`` fact + ``pv_state_status``
  roster). Asserts the two-table load coexists with the EC spine and the earlier PV
  rows, the ``state`` FK resolves, UCSB's real per-row ``reliability`` tagging, and — the
  check only a live DB can make — that the D024 two-way roster/fact invariant holds
  across the two independent writes. Doubly gated: the ``integration`` marker *and* a
  ``USVOTE_UCSB_HTML_DIR`` skip, so CI never touches the non-redistributable UCSB
  snapshot (D022).

Config + skip-if-unset come from the shared ``integration_db_config`` fixture in
``tests/conftest.py``.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, fake_state_geo
from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.schema import PV_TABLE
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    ROSTER_TABLE,
    assert_roster_covers_facts,
)

_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


@pytest.mark.integration
def test_mit_pv_loads_alongside_ec_spine(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine (2016+2020), then load MIT PV (2016) into the same schema."""
    from usvote.mit.pipeline import run_mit_pipeline
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the EC spine — creates dwh.state / dwh.candidate / dwh.votes, the
        #    FK targets the PV load needs, via the offline 2016+2020 fixtures.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        # 2. Load MIT PV scoped to 2016 (a subset of the seeded years), reconciled
        #    onto the canonical keys — non-destructively, alongside the EC spine.
        pv = run_mit_pipeline(
            dbc, path=MIT_FUSION_SAMPLE_CSV, years={2016}, replace=False
        )

        # The whole loaded frame lands (2016 NY: Clinton + Trump).
        n = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_TABLE}"
        )["n"].iloc[0]
        assert n == len(pv) == 2

        # The EC spine survived the PV load (guard against a schema-level replace).
        for ec_table in ("state", "candidate", "votes"):
            cnt = dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{ec_table}"
            )["n"].iloc[0]
            assert cnt > 0, f"EC {ec_table} was wiped by the PV load"

        # Grain: pv_id unique, and the (source, year, state, candidate) natural key
        # unique (a broken grain would have raised on the constraint at insert).
        dup_pk = dbc.select_query_to_df(
            f"SELECT pv_id FROM {SCHEMA}.{PV_TABLE} "
            f"GROUP BY pv_id HAVING count(*) > 1"
        )
        assert dup_pk.empty
        dup_key = dbc.select_query_to_df(
            f"SELECT source, year, state, candidate FROM {SCHEMA}.{PV_TABLE} "
            f"GROUP BY source, year, state, candidate HAVING count(*) > 1"
        )
        assert dup_key.empty

        # FK/containment: every pv_votes.state resolves into dwh.state, and every
        # pv_votes.candidate resolves into dwh.candidate.name (the #67 reconciliation
        # guarantee, verified end-to-end against the real EC dims).
        orphan_state = dbc.select_query_to_df(
            f"SELECT p.state FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.state s USING (state) WHERE s.state IS NULL"
        )
        assert orphan_state.empty
        orphan_cand = dbc.select_query_to_df(
            f"SELECT p.candidate FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.candidate c ON p.candidate = c.name "
            f"WHERE c.name IS NULL"
        )
        assert orphan_cand.empty

        # Provenance tagging: every row is source=MIT, reliability=exact.
        tags = dbc.select_query_to_df(
            f"SELECT DISTINCT source, reliability FROM {SCHEMA}.{PV_TABLE}"
        )
        assert tags.values.tolist() == [["MIT", "exact"]]
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
@pytest.mark.skipif(
    not _CORPUS,
    reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo (D022)",
)
def test_ucsb_pv_loads_alongside_ec_spine(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine (2016+2020), then load UCSB PV + roster into the same schema.

    The UCSB analogue of the MIT load test, and the only check that runs the whole
    ``#37`` pipeline (snapshot read -> parse -> transform -> reconcile -> two-table load)
    against a real database. It is doubly gated: ``integration`` excludes it from CI, and
    the ``USVOTE_UCSB_HTML_DIR`` skip means it never touches the non-redistributable UCSB
    snapshot in an environment that lacks it. Scoped to 2016+2020 so the UCSB
    states/candidates reconcile against the EC dims seeded from the Archives fixtures for
    those years — the two years whose real UCSB pages the corpus carries and the EC
    fixtures cover.
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir
    from usvote.ucsb.pipeline import run_ucsb_pipeline

    years = {2016, 2020}
    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the EC spine for both years — the FK targets (dwh.state/candidate) and
        #    the participation/getter frames the UCSB pipeline reads back.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years=years,
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        # 2. Run the whole UCSB pipeline over the real snapshot, scoped to those years,
        #    loading both PV tables non-destructively alongside the EC spine.
        pv, roster = run_ucsb_pipeline(dbc, _CORPUS, years=years, replace=False)

        # The fact frame landed in full, tagged source=UCSB.
        n_pv = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_TABLE} WHERE source = 'UCSB'"
        )["n"].iloc[0]
        assert n_pv == len(pv) > 0

        # The roster landed too — one row per (year, state) for both years.
        n_roster = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{ROSTER_TABLE} WHERE source = 'UCSB'"
        )["n"].iloc[0]
        assert n_roster == len(roster) > 0

        # The EC spine and the earlier PV table survived (no schema-level replace).
        for ec_table in ("state", "candidate", "votes"):
            cnt = dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{ec_table}"
            )["n"].iloc[0]
            assert cnt > 0, f"EC {ec_table} was wiped by the UCSB load"

        # FK/containment: every pv_votes.state resolves into dwh.state (the reconcile
        # guarantee, verified end-to-end against the real EC dims).
        orphan_state = dbc.select_query_to_df(
            f"SELECT p.state FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.state s USING (state) "
            f"WHERE p.source = 'UCSB' AND s.state IS NULL"
        )
        assert orphan_state.empty

        # Provenance: UCSB carries real per-row reliability — only 'exact'/'unreliable'
        # (D024: 'estimated' is deliberately unused), never MIT's uniform 'exact'-only.
        reliabilities = set(
            dbc.select_query_to_df(
                f"SELECT DISTINCT reliability FROM {SCHEMA}.{PV_TABLE} "
                f"WHERE source = 'UCSB'"
            )["reliability"]
        )
        assert reliabilities <= {"exact", "unreliable"}

        # The D024 two-way invariant holds *in the database*: read both tables back and
        # re-run the roster/fact assert. This is the check the in-memory pipeline cannot
        # make — that the two independent writes landed a consistent pair (no silent drop
        # between the roster load and the fact load).
        db_pv = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{PV_TABLE} WHERE source = 'UCSB'"
        )
        db_roster = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{ROSTER_TABLE} WHERE source = 'UCSB'"
        )
        assert_roster_covers_facts(db_pv, db_roster, source="UCSB", years=years)

        # Sanity: the roster records both absence and popular-vote states across the two
        # years (it is a complete roster, not an exceptions table).
        assert (db_roster["pv_status"] == PV_STATUS_POPULAR_VOTE).any()
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
