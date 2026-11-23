"""Live-Postgres integration tests for the #68 PV union (``usvote.pv`` D017 views).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database. Two tests, split deliberately by what
each needs:

- **``test_union_views_resolve_a_synthetic_overlap``** — the crux, and **not** gated on
  the UCSB corpus. It seeds the EC spine (for the ``pv_votes.state`` FK), then loads a
  small **fabricated** two-source union straight into ``dwh.pv_votes`` — an overlap key
  (MIT + UCSB), a pre-1976 key (UCSB only), and a modern MIT-only key — and asserts the
  live views resolve exactly as D017 requires. The rows are invented (D022 forbids real
  UCSB *bytes*, not the string ``'UCSB'``), so the precedence-resolution and
  public-surface leak-guard checks run against real Postgres with only a database
  available. The pure ``resolve_preferred`` oracle proves the same resolution offline in
  ``tests/unit/test_pv_views.py``; this confirms the emitted SQL agrees with it.

- **``test_union_over_a_real_two_source_load``** — the end-to-end check, doubly gated
  (``integration`` + ``USVOTE_UCSB_HTML_DIR``): it runs the real MIT and UCSB pipelines
  for 2016+2020 and asserts the overlap resolves to MIT and no UCSB row reaches
  ``pv_redistributable``, over genuinely reconciled data.

Config + skip-if-unset come from the shared ``integration_db_config`` fixture.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, fake_state_geo
from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.load import build_pv_union, load_pv_records
from usvote.pv.schema import PV_TABLE, SHARED_PV_COLUMNS
from usvote.pv.source import PV_SOURCE_TABLE, SOURCE_MIT, SOURCE_UCSB
from usvote.pv.views import (
    PV_PREFERRED_VIEW,
    PV_REDISTRIBUTABLE_VIEW,
    PV_UCSB_VIEW,
    assert_single_row_per_key,
)

_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


def _synthetic_row(
    source: str, year: int, state: str, candidate: str, votes: int
) -> dict[str, Any]:
    return {
        "source": source, "year": year, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes,
        "state_total_votes": votes * 2, "reliability": "exact",
    }


def _synthetic_union() -> pd.DataFrame:
    """A fabricated two-source union — invented counts, real (seeded) state names so the
    ``pv_votes.state`` FK resolves. No real UCSB data (D022)."""
    return pd.DataFrame(
        [
            _synthetic_row(SOURCE_MIT, 2016, "Ohio", "Synthetic A", 100),   # overlap
            _synthetic_row(SOURCE_UCSB, 2016, "Ohio", "Synthetic A", 111),  # overlap
            _synthetic_row(SOURCE_UCSB, 1900, "Ohio", "Synthetic B", 50),   # pre-1976
            _synthetic_row(SOURCE_MIT, 2016, "Iowa", "Synthetic C", 70),    # MIT-only
        ]
    )[list(SHARED_PV_COLUMNS)]


@pytest.mark.integration
def test_union_views_resolve_a_synthetic_overlap(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine, load a fabricated two-source union, assert the live views."""
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the EC spine (dwh.state is the pv_votes.state FK target). fake_state_geo
        #    provides every US state, so the fabricated Ohio/Iowa rows resolve.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        # 2. Load the fabricated union straight into pv_votes (both sources, overlap kept
        #    — exactly what the two real source loads produce), then build the views.
        load_pv_records(dbc, _synthetic_union(), replace=False)
        build_pv_union(dbc)

        # pv_source seeded with the two D017 rows.
        n_src = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_SOURCE_TABLE}"
        )["n"].iloc[0]
        assert n_src == 2

        # pv_preferred: exactly one row per (year, state, candidate)...
        dupes = dbc.select_query_to_df(
            f"SELECT year, state, candidate FROM {SCHEMA}.{PV_PREFERRED_VIEW} "
            f"GROUP BY year, state, candidate HAVING count(*) > 1"
        )
        assert dupes.empty
        # ...and it is the same data the offline oracle would resolve.
        assert_single_row_per_key(
            dbc.select_query_to_df(f"SELECT * FROM {SCHEMA}.{PV_PREFERRED_VIEW}")
        )

        pref = dbc.select_query_to_df(
            f"SELECT year, state, candidate, source, candidate_votes "
            f"FROM {SCHEMA}.{PV_PREFERRED_VIEW} ORDER BY year, state, candidate"
        )
        resolved = {
            (r.year, r.state, r.candidate): (r.source, r.candidate_votes)
            for r in pref.itertuples()
        }
        assert resolved[(2016, "Ohio", "Synthetic A")] == (SOURCE_MIT, 100)  # MIT wins
        assert resolved[(1900, "Ohio", "Synthetic B")] == (SOURCE_UCSB, 50)  # UCSB earlier
        assert resolved[(2016, "Iowa", "Synthetic C")] == (SOURCE_MIT, 70)   # MIT-only

        # pv_redistributable: the public-surface leak guard — NOT one UCSB row, and it
        # coincides with pv_preferred across the overlap.
        n_ucsb_public = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}'"
        )["n"].iloc[0]
        assert n_ucsb_public == 0
        overlap_public = dbc.select_query_to_df(
            f"SELECT source, candidate_votes FROM {SCHEMA}.{PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE year = 2016 AND state = 'Ohio' AND candidate = 'Synthetic A'"
        )
        assert overlap_public.values.tolist() == [[SOURCE_MIT, 100]]
        # The pre-1976 UCSB-only key is honestly absent from the public surface (D005).
        pre76_public = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{PV_REDISTRIBUTABLE_VIEW} WHERE year = 1900"
        )
        assert pre76_public.empty

        # pv_ucsb: the control — UCSB rows only, including the overlap's UCSB value.
        ucsb_sources = set(
            dbc.select_query_to_df(
                f"SELECT DISTINCT source FROM {SCHEMA}.{PV_UCSB_VIEW}"
            )["source"]
        )
        assert ucsb_sources == {SOURCE_UCSB}
        overlap_ucsb = dbc.select_query_to_df(
            f"SELECT candidate_votes FROM {SCHEMA}.{PV_UCSB_VIEW} "
            f"WHERE year = 2016 AND state = 'Ohio' AND candidate = 'Synthetic A'"
        )["candidate_votes"].iloc[0]
        assert overlap_ucsb == 111

        # Provenance coverage: every pv_votes.source has a pv_source row (the guard the
        # deliberately-absent FK leaves to a check — an orphan source would be silently
        # dropped by the pv_preferred join).
        orphan_src = dbc.select_query_to_df(
            f"SELECT DISTINCT p.source FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.{PV_SOURCE_TABLE} s USING (source) "
            f"WHERE s.source IS NULL"
        )
        assert orphan_src.empty
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
@pytest.mark.skipif(
    not _CORPUS,
    reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo (D022)",
)
def test_union_over_a_real_two_source_load(
    integration_db_config: dict[str, Any],
) -> None:
    """End-to-end: real MIT + real UCSB for 2016+2020, then the D017 views.

    The only check that resolves the views over genuinely reconciled two-source data.
    Doubly gated so CI never touches the UCSB snapshot (D022).
    """
    from usvote.mit.pipeline import run_mit_pipeline
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir
    from usvote.ucsb.pipeline import run_ucsb_pipeline

    years = {2016, 2020}
    dbc = DBC(integration_db_config)
    try:
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years=years,
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )
        # Both real sources load into the one pv_votes (the raw union), then build views.
        run_mit_pipeline(dbc, path=MIT_FUSION_SAMPLE_CSV, years={2016}, replace=False)
        run_ucsb_pipeline(dbc, _CORPUS, years=years, replace=False)
        build_pv_union(dbc)

        # pv_preferred is single-row-per-key over real data.
        dupes = dbc.select_query_to_df(
            f"SELECT year, state, candidate FROM {SCHEMA}.{PV_PREFERRED_VIEW} "
            f"GROUP BY year, state, candidate HAVING count(*) > 1"
        )
        assert dupes.empty

        # Wherever both sources cover the same 2016 key, pv_preferred picks MIT. The
        # overlap keys are the (state, candidate) pairs present under both sources;
        # every one of them must resolve to MIT in the view.
        overlap = f"""
            SELECT m.state, m.candidate
            FROM {SCHEMA}.{PV_TABLE} m
            WHERE m.source = '{SOURCE_MIT}' AND m.year = 2016
            INTERSECT
            SELECT u.state, u.candidate
            FROM {SCHEMA}.{PV_TABLE} u
            WHERE u.source = '{SOURCE_UCSB}' AND u.year = 2016
        """
        both = dbc.select_query_to_df(overlap)
        # The 2016 fusion sample (NY Clinton/Trump) and real UCSB 2016 both reconcile to
        # the same canonical (state, candidate), so the overlap MUST be non-empty. Assert
        # it — otherwise the precedence check below would never run and the test would
        # pass vacuously, defeating the one check meant to prove MIT precedence on real
        # data (an empty overlap signals the MIT/UCSB reconciliations disagree on the key).
        assert not both.empty, (
            "expected a non-empty MIT/UCSB 2016 overlap; an empty one makes the "
            "precedence assertion vacuous — check the two sources' candidate "
            "reconciliations agree on the canonical (state, candidate) key"
        )
        preferred_sources = dbc.select_query_to_df(
            f"SELECT DISTINCT source FROM {SCHEMA}.{PV_PREFERRED_VIEW} p "
            f"WHERE p.year = 2016 AND (p.state, p.candidate) IN ({overlap})"
        )
        assert set(preferred_sources["source"]) == {SOURCE_MIT}

        # No UCSB row ever reaches the public surface, over real data.
        n_ucsb_public = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}'"
        )["n"].iloc[0]
        assert n_ucsb_public == 0
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
