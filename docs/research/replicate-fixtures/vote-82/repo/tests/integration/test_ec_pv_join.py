"""Live-Postgres integration tests for the EC-left EC<->PV join (#69 / D026).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database. The join uses a window SUM and a
LEFT JOIN over a resolved view, so the live view is where the emitted SQL is proven to
behave like the pure oracle in ``tests/unit/test_join.py``.

Two tests, split by what each needs:

- **``test_join_resolves_a_synthetic_participant_set``** — the crux, **not** gated on the
  UCSB corpus. It seeds the real EC spine for 2016+2020, then loads a small **fabricated**
  PV union that reuses **real** canonical candidate/state names (so the D026 reciprocal
  anti-join precondition passes) — a winner+PV, a loser (a real 0-EV EC row) with PV, and
  a UCSB analysis-only row — and asserts the live
  ``ec_pv_preferred``/``ec_pv_redistributable`` views resolve exactly as D026 requires
  (no fan-out; loser EC 0 with PV; the UCSB row never on the redistributable surface).
  The counts are invented; only the names are real (D022 forbids UCSB *bytes*, not the
  string ``'UCSB'``).

- **``test_join_over_a_real_two_source_load``** — end-to-end, doubly gated
  (``integration`` + ``USVOTE_UCSB_HTML_DIR``): real MIT + UCSB for 2016+2020, then the
  join views, asserting no fan-out and the redistributable leak-guard over reconciled data.

Config + skip-if-unset come from the shared ``integration_db_config`` fixture.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, fake_state_geo
from usvote.db import DBC
from usvote.getters import EC_GETTERS_WITHOUT_POPULAR_VOTE
from usvote.join import (
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
    JoinError,
    assert_db_pv_matches_ec,
    assert_winners_have_pv,
    create_ec_pv_views,
)
from usvote.load import SCHEMA
from usvote.pv.load import build_pv_union, load_pv_records
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB
from usvote.pv.views import PV_PREFERRED_VIEW

_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


def _top_two_getters(dbc: DBC, year: int) -> tuple[str, str]:
    """The two highest-EV getters that year (winner, runner-up) by canonical name.

    Used to build a fabricated PV over *real* names: the runner-up is a getter who won
    no EC votes in some state the winner took (a loser-in-state), so a PV row for them
    there exercises the guarded EC-0 fill on live data.
    """
    got = dbc.select_query_to_df(
        f"SELECT c.name FROM {SCHEMA}.votes v "
        f"JOIN {SCHEMA}.candidate c ON v.candidate_id = c.candidate_id "
        f"WHERE v.is_total AND v.year = {year} "
        f"ORDER BY v.president_electoral_votes DESC LIMIT 2"
    )
    return got["name"].iloc[0], got["name"].iloc[1]


def _pv_row(
    source: str, year: int, state: str, candidate: str, votes: int
) -> dict[str, Any]:
    return {
        "source": source, "year": year, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes,
        "state_total_votes": votes * 2, "reliability": "exact",
    }


@pytest.mark.integration
def test_join_resolves_a_synthetic_participant_set(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine, load a fabricated PV over real names, assert the live views."""
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the real EC spine for 2016+2020.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        winner16, loser16 = _top_two_getters(dbc, 2016)   # Trump won Texas; runner-up did not
        _winner20, loser20 = _top_two_getters(dbc, 2020)  # Biden won California; runner-up did not
        # Fail fast if the fixtures ever shift the setup's assumptions out from under the
        # assertions (a tie or a data change): the two must be distinct getters, and the
        # ev==0 / ev>0 checks below are what actually encode "loser lost / winner won".
        assert winner16 != loser16 and loser16 != loser20

        # 2. Fabricated PV over REAL names: a winner+PV and a loser (a real 0-EV EC row,
        #    2016 Texas), plus a UCSB analysis-only loser (2020 California).
        union = pd.DataFrame([
            _pv_row(SOURCE_MIT, 2016, "Texas", winner16, 4_500_000),   # winner + PV
            _pv_row(SOURCE_MIT, 2016, "Texas", loser16, 3_800_000),    # loser, EC 0-row
            _pv_row(SOURCE_UCSB, 2020, "California", loser20, 6_000_000),  # UCSB analysis-only
        ])[list(SHARED_PV_COLUMNS)]
        load_pv_records(dbc, union, replace=False)
        build_pv_union(dbc)
        create_ec_pv_views(dbc)

        # No fan-out: one row per (year, state, candidate) in both views.
        for view in (EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW):
            dupes = dbc.select_query_to_df(
                f"SELECT year, state, candidate FROM {SCHEMA}.{view} "
                f"GROUP BY year, state, candidate HAVING count(*) > 1"
            )
            assert dupes.empty, f"{view} fanned out"

        # Loser: the 2016 Texas runner-up has a real EC 0-row (dense fact), PV attached —
        # exactly the row an EC-left join keeps (and the sparse-premise draft mis-handled).
        loser = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, candidate_votes AS cv, source "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND state = 'Texas' AND candidate = '{loser16}'"
        )
        assert loser["ev"].iloc[0] == 0
        assert loser["cv"].iloc[0] == 3_800_000
        assert loser["source"].iloc[0] == SOURCE_MIT

        # Winner+PV: the 2016 Texas winner has EC votes (EV > 0) and the PV attached.
        winner = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, candidate_votes AS cv "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND state = 'Texas' AND candidate = '{winner16}'"
        )
        assert winner["ev"].iloc[0] > 0
        assert winner["cv"].iloc[0] == 4_500_000

        # national_electoral_votes is a window SUM over the candidate's state rows — the
        # one non-trivial piece of live SQL. Verify it directly: it must be CONSTANT across
        # winner16's state rows (one DISTINCT value — a wrong PARTITION would give per-state
        # values) and equal the published national total on that candidate's is_total row.
        natl_view = dbc.select_query_to_df(
            f"SELECT DISTINCT national_electoral_votes AS n "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND candidate = '{winner16}'"
        )
        natl_ec = dbc.select_query_to_df(
            f"SELECT v.president_electoral_votes AS n FROM {SCHEMA}.votes v "
            f"JOIN {SCHEMA}.candidate c ON v.candidate_id = c.candidate_id "
            f"WHERE v.is_total AND v.year = 2016 AND c.name = '{winner16}'"
        )
        assert len(natl_view) == 1                       # constant across state rows
        assert natl_view["n"].iloc[0] == natl_ec["n"].iloc[0]  # == published national total

        # The UCSB analysis-only row IS in the preferred series (as UCSB), tagged
        # redistributable = false — a loser with EC 0.
        ucsb_pref = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, source, redistributable "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2020 AND state = 'California' AND candidate = '{loser20}'"
        )
        assert ucsb_pref["ev"].iloc[0] == 0
        assert ucsb_pref["source"].iloc[0] == SOURCE_UCSB
        assert not bool(ucsb_pref["redistributable"].iloc[0])

        # The public surface: NO UCSB row, and NO redistributable = false row ever.
        leak = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}' OR redistributable = false"
        )
        assert leak["n"].iloc[0] == 0
        # The EC row (2020, CA, loser20) still appears on the public surface — EC-left keeps
        # every EC state row — but the UCSB PV must NOT attach: its candidate_votes/source
        # stay NULL (pv_redistributable excludes UCSB), so the 6M UCSB votes never leak.
        pub = dbc.select_query_to_df(
            f"SELECT candidate_votes AS cv, source FROM "
            f"{SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE year = 2020 AND state = 'California' AND candidate = '{loser20}'"
        )
        assert len(pub) == 1
        assert pd.isna(pub["cv"].iloc[0])
        assert pd.isna(pub["source"].iloc[0])

        # Reciprocal anti-join precondition: a PV row matching no EC votes row (an orphan
        # candidate) must fail loud — the EC-left join would otherwise silently drop it
        # (the guard the join owns, docs/canonical-keys.md). Inject one and confirm the
        # live guard raises.
        orphan = pd.DataFrame([
            _pv_row(SOURCE_MIT, 2016, "Texas", "Nonexistent Q. Candidate", 1),
        ])[list(SHARED_PV_COLUMNS)]
        load_pv_records(dbc, orphan, replace=False)
        with pytest.raises(JoinError, match="match no EC votes row"):
            assert_db_pv_matches_ec(dbc, PV_PREFERRED_VIEW)
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
def test_winner_has_pv_runs_end_to_end_on_the_live_view(
    integration_db_config: dict[str, Any],
) -> None:
    """Exercise the winner-has-PV guard end-to-end on a live ``ec_pv_preferred`` view.

    The real-corpus wiring below is UCSB-gated (skipped in CI), so this **ungated** test is
    what actually proves the guard's mechanics against real DB-typed columns: it fabricates
    PV for every EC state winner in the seeded spine, then checks both directions — the
    **raise** path (one major winner deliberately left PV-less) and the **pass** path (all
    winners covered), with the inspected-count vacuity floor. Real names, invented counts
    (D022-safe: the string ``'MIT'``, not UCSB bytes).
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )
        # Every EC state winner (>0 EV): (year, state, canonical name).
        winners = dbc.select_query_to_df(
            f"SELECT v.year, v.state, c.name AS candidate FROM {SCHEMA}.votes v "
            f"JOIN {SCHEMA}.candidate c ON v.candidate_id = c.candidate_id "
            f"WHERE v.state IS NOT NULL AND v.president_electoral_votes > 0"
        )
        # Deliberately omit one unambiguous major winner (2020 California = Biden) so the
        # guard has exactly one miss to name.
        winner20 = _top_two_getters(dbc, 2020)[0]
        omit = (
            (winners["year"] == 2020)
            & (winners["state"] == "California")
            & (winners["candidate"] == winner20)
        )
        assert omit.sum() == 1, "expected exactly one 2020 California winner to omit"
        kept = winners.loc[~omit]

        pv = pd.DataFrame([
            _pv_row(SOURCE_MIT, int(r.year), r.state, r.candidate, 1_000)
            for r in kept.itertuples()
        ])[list(SHARED_PV_COLUMNS)]
        load_pv_records(dbc, pv, replace=False)
        build_pv_union(dbc)
        create_ec_pv_views(dbc)

        # Raise path: the omitted winner (Biden/CA) is an EC winner with no PV → fails loud,
        # naming it. Exemptions cover the faithless getters (who here do have fabricated PV).
        frame = dbc.select_query_to_df(f"SELECT * FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW}")
        with pytest.raises(JoinError, match=re.escape(winner20)):
            assert_winners_have_pv(frame, exemptions=EC_GETTERS_WITHOUT_POPULAR_VOTE)

        # Pass path: load the omitted winner's PV (the view reflects it live — no rebuild),
        # then every winner has PV; the guard passes and inspects every winner row.
        load_pv_records(
            dbc,
            pd.DataFrame([
                _pv_row(SOURCE_MIT, 2020, "California", winner20, 1_000)
            ])[list(SHARED_PV_COLUMNS)],
            replace=False,
        )
        frame2 = dbc.select_query_to_df(f"SELECT * FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW}")
        inspected = assert_winners_have_pv(
            frame2, exemptions=EC_GETTERS_WITHOUT_POPULAR_VOTE
        )
        assert inspected == len(winners) > 50  # non-vacuous: ~100+ winner rows across 2016+2020
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
@pytest.mark.skipif(
    not _CORPUS,
    reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo (D022)",
)
def test_join_over_a_real_two_source_load(
    integration_db_config: dict[str, Any],
) -> None:
    """End-to-end: real MIT + real UCSB for 2016+2020, then the D026 join views.

    The only check that resolves the join over genuinely reconciled two-source data, and
    it drives the **shipped** whole-warehouse path (:func:`usvote.warehouse.run_warehouse`,
    #84b) rather than a hand-wired stage sequence — so the tested path is the shipped path.
    ``run_warehouse`` threads one ``years={2016, 2020}`` to every source. The fusion
    sample carries 2000 + 2016 rows, but MIT's ``year.isin(years)`` filter drops 2000 and
    the sample has no 2020, so MIT still loads exactly its 2016 New York rows — the same
    result as the old ``years={2016}`` wiring, now via the shared warehouse scope. Doubly
    gated so CI never touches the UCSB snapshot (D022).
    """
    from usvote.scrape import fetch_from_dir
    from usvote.warehouse import SOURCE_EC as WH_EC
    from usvote.warehouse import SOURCE_MIT as WH_MIT
    from usvote.warehouse import SOURCE_UCSB as WH_UCSB
    from usvote.warehouse import run_warehouse

    years = {2016, 2020}
    dbc = DBC(integration_db_config)
    try:
        result = run_warehouse(
            dbc,
            "unused.shp",
            MIT_FUSION_SAMPLE_CSV,
            ucsb_html_dir=_CORPUS,
            years=years,
            replace=True,
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )
        # The build receipt: all three sources loaded, join views (re)built.
        assert result.sources_loaded == frozenset({WH_EC, WH_MIT, WH_UCSB})
        assert result.views_built is True

        # No fan-out over real reconciled data (the raw-union double-count guard, live).
        for view in (EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW):
            dupes = dbc.select_query_to_df(
                f"SELECT year, state, candidate FROM {SCHEMA}.{view} "
                f"GROUP BY year, state, candidate HAVING count(*) > 1"
            )
            assert dupes.empty, f"{view} fanned out"

        # Losers are kept: a getter who won no EC votes in a state they contested is a real
        # 0-EV EC row with PV attached — the dense-fact rows the EC-left join preserves.
        losers = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE candidate_votes IS NOT NULL AND president_electoral_votes = 0"
        )
        assert losers["n"].iloc[0] > 0

        # The public surface never carries a non-redistributable row, over real data.
        leak = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}' OR redistributable = false"
        )
        assert leak["n"].iloc[0] == 0

        # Winner-has-PV coverage over the ANALYSIS series (the D026 crux guard, on real
        # reconciled data — the one path that catches a name-reconciliation miss where an
        # EC winner silently fails to match PV). Run on ec_pv_preferred only: UCSB is dense
        # across both corpus years, so the check is non-vacuous; ec_pv_redistributable
        # (MIT = the NY-only fusion sample here) would need a huge exemption set and is
        # deferred to E8 when the full MIT load lands. Exempt only the getters that
        # legitimately held no popular vote (the 2016 faithless set for this corpus).
        preferred = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW}"
        )
        # Scope guard: the exemption set is curated for the 2016/2020 corpus, so fail loud
        # if a future corpus widening slips a year past it (rather than exempting silently).
        assert {int(y) for y in preferred["year"]} <= years, (
            "ec_pv_preferred carries a year outside the loaded corpus; widen the "
            "winner-has-PV exemption scope deliberately (EC_GETTERS_WITHOUT_POPULAR_VOTE)"
        )
        # A first real run may flag a genuine UCSB coverage gap — treat a modern flag as a
        # reconciliation miss to FIX, not an exemption to add (per the architect).
        inspected = assert_winners_have_pv(
            preferred, exemptions=EC_GETTERS_WITHOUT_POPULAR_VOTE
        )
        # Vacuity floor: 2016+2020 have ~100+ EC-winner state rows; a guard that inspected
        # near-zero would pass vacuously (mirrors this file's ``assert not both.empty``).
        assert inspected >= 50, f"winner-has-PV inspected only {inspected} rows (vacuous?)"
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
def test_warehouse_builds_the_redistributable_core_end_to_end(
    integration_db_config: dict[str, Any],
) -> None:
    """Drive ``run_warehouse`` over EC fixtures + the MIT fusion sample, no UCSB.

    The **ungated** end-to-end check of the shipped whole-warehouse path (#84b): it
    exercises ``run_warehouse``'s real sequencing — EC spine, MIT PV, the D024 explicit
    UCSB skip (``ucsb_html_dir=None``), then the always-rebuilt join views — against a
    live DB with no UCSB corpus. This is what proves the ``replace=True`` schema rebuild
    still leaves the EC<->PV views in place (the #84b blocking fix): without the final
    ``rebuild_views`` step the ``DROP SCHEMA ... CASCADE`` would leave no
    ``ec_pv_preferred`` to query.
    """
    from usvote.scrape import fetch_from_dir
    from usvote.warehouse import SOURCE_EC as WH_EC
    from usvote.warehouse import SOURCE_MIT as WH_MIT
    from usvote.warehouse import run_warehouse

    dbc = DBC(integration_db_config)
    try:
        result = run_warehouse(
            dbc,
            "unused.shp",
            MIT_FUSION_SAMPLE_CSV,
            ucsb_html_dir=None,  # explicit skip — the redistributable EC + MIT core only
            years={2016, 2020},
            replace=True,
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )
        # Receipt: only EC + MIT loaded, UCSB counts None, views built.
        assert result.sources_loaded == frozenset({WH_EC, WH_MIT})
        assert result.ucsb_pv_rows is None and result.ucsb_roster_rows is None
        assert result.ec_rows > 0 and result.mit_rows > 0
        assert result.views_built is True

        # The blocking fix, proven live: the join views survive the replace=True schema
        # rebuild because run_warehouse rebuilt them. Query one and confirm it resolves.
        preferred = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW}"
        )
        assert preferred["n"].iloc[0] > 0
        # No fan-out on the redistributable public surface over the EC + MIT core.
        dupes = dbc.select_query_to_df(
            f"SELECT year, state, candidate FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"GROUP BY year, state, candidate HAVING count(*) > 1"
        )
        assert dupes.empty
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
