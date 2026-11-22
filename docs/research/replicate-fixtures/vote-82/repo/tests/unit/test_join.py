"""Unit tests for the EC-left EC<->PV join (``usvote.join``, #69 / D026).

Two kinds of check, both offline (mirroring ``tests/unit/test_pv_views.py``):

- **SQL structure** — the builder emits the EC-left join D026 mandates (reads a *resolved*
  PV view, never the raw ``pv_votes`` union; EC ``votes`` on the left; the national-EV
  window SUM), threads the schema, and shapes both views.
- **Frame oracle** — :func:`usvote.join.join_ec_pv` on a small, fabricated **dense** EC +
  PV scenario: a winner+PV, a **loser** (real 0-EV EC row) with PV, a getter with no PV
  (NULL PV), a split-vote state (each getter keeps its real count), and the guards
  (no-fan-out, PV↔EC anti-join, winner-has-PV).

The oracle is the same policy the live view runs; the live behavioral check is in
``tests/integration/test_ec_pv_join.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.join import (
    EC_PV_COLUMNS,
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
    JoinError,
    assert_no_fan_out,
    assert_pv_matches_ec,
    assert_winners_have_pv,
    build_ec_pv_join_sql,
    join_ec_pv,
)
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, build_pv_source_frame
from usvote.pv.views import PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW

# --- SQL structure ----------------------------------------------------------


def test_view_names_are_prefixed_apart_from_the_resolved_pv_views() -> None:
    assert EC_PV_PREFERRED_VIEW == "ec_pv_preferred"
    assert EC_PV_REDISTRIBUTABLE_VIEW == "ec_pv_redistributable"
    assert EC_PV_PREFERRED_VIEW != PV_PREFERRED_VIEW


def test_builder_reads_a_resolved_view_never_the_raw_union() -> None:
    # D017/D026: the join MUST read a resolved single-row series, never dwh.pv_votes.
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    assert "LEFT JOIN dwh.pv_preferred p" in sql
    assert "pv_votes" not in sql


def test_builder_is_ec_left_at_the_state_grain() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    # EC votes on the left; PV left-joined so losers (0-EV EC rows) are never dropped.
    assert "FROM dwh.votes v" in sql
    assert "LEFT JOIN dwh.pv_preferred p" in sql
    assert "FULL OUTER" not in sql
    # State grain: the national is_total rows are excluded.
    assert "WHERE v.state IS NOT NULL" in sql
    # PV attaches on (year, state, canonical name).
    assert "p.candidate = c.name" in sql


def test_builder_national_ev_is_a_window_sum() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    # national_electoral_votes is a window SUM over the candidate's state rows — exact on
    # the dense fact, needs no is_total join.
    assert (
        "sum(v.president_electoral_votes) OVER (PARTITION BY v.year, v.candidate_id)"
        in sql
    )


def test_builder_carries_redistributable_from_pv_source() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW)
    assert "LEFT JOIN dwh.pv_source s ON s.source = p.source" in sql
    assert "s.redistributable" in sql


def test_builder_targets_the_redistributable_view() -> None:
    sql = build_ec_pv_join_sql(PV_REDISTRIBUTABLE_VIEW)
    assert "LEFT JOIN dwh.pv_redistributable p" in sql


def test_builder_threads_the_schema() -> None:
    sql = build_ec_pv_join_sql(PV_PREFERRED_VIEW, schema="mart", pv_schema="mart")
    assert "mart.votes" in sql
    assert "mart.pv_preferred" in sql
    assert "mart.pv_source" in sql


# --- frame oracle: a fabricated DENSE EC + PV scenario ----------------------

# Candidate dim. Every PV candidate is an EC getter (D007/D025), so all resolve here.
_CANDIDATES = pd.DataFrame(
    [
        {"candidate_id": 1, "name": "Winner A"},
        {"candidate_id": 2, "name": "Loser B"},
        {"candidate_id": 4, "name": "Faithless F"},
    ]
)


def _votes() -> pd.DataFrame:
    """A fabricated **dense** ``dwh.votes``: every getter has a row in every state (0 for
    a loser), plus the national is_total rows.

    2020: A wins Texas (38) and Washington (11); B wins California (55); **Nebraska is
    split** A=4 / B=1; F is a faithless getter with 1 EV in Washington and no PV. Every
    (state, candidate) pair is present — losers as explicit 0-EV rows.
    """
    # National rank/took_office are broadcast onto EVERY row per candidate (as the real
    # transform does): A rank 2, B rank 1 (took office), F rank 3.
    rank = {1: 2, 2: 1, 4: 3}
    took = {1: False, 2: True, 4: False}
    # (state, cid, total_ev, president_ev) — every state lists every candidate.
    state_cells = [
        ("Texas", 1, 38, 38), ("Texas", 2, 38, 0), ("Texas", 4, 38, 0),
        ("California", 1, 55, 0), ("California", 2, 55, 55), ("California", 4, 55, 0),
        ("Nebraska", 1, 5, 4), ("Nebraska", 2, 5, 1), ("Nebraska", 4, 5, 0),  # split
        ("Washington", 1, 12, 11), ("Washington", 2, 12, 0), ("Washington", 4, 12, 1),
    ]
    rows = [
        {
            "year": 2020, "state": s, "is_total": False, "candidate_id": c,
            "total_electoral_votes": tev, "president_electoral_votes": pev,
            "president_electoral_rank": rank[c], "took_office": took[c],
        }
        for (s, c, tev, pev) in state_cells
    ]
    # National is_total rows: A=53, B=56, F=1 (same broadcast rank/took_office).
    for cid, nev in [(1, 53), (2, 56), (4, 1)]:
        rows.append({
            "year": 2020, "state": None, "is_total": True, "candidate_id": cid,
            "total_electoral_votes": 538, "president_electoral_votes": nev,
            "president_electoral_rank": rank[cid], "took_office": took[cid],
        })
    return pd.DataFrame(rows)


def _pv_row(state: str, candidate: str, votes: int, total: int) -> dict:
    return {
        "source": SOURCE_MIT, "year": 2020, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes, "state_total_votes": total,
        "reliability": "exact",
    }


def _pv() -> pd.DataFrame:
    """Resolved PV: both majors in every contested state; no PV for faithless F."""
    return pd.DataFrame([
        _pv_row("Texas", "Winner A", 100, 250),
        _pv_row("Texas", "Loser B", 150, 250),        # loser with PV (EC 0-row)
        _pv_row("California", "Winner A", 80, 200),    # loser with PV (EC 0-row)
        _pv_row("California", "Loser B", 120, 200),
        _pv_row("Nebraska", "Winner A", 30, 60),
        _pv_row("Nebraska", "Loser B", 28, 60),        # split — EC 1, not 0
        _pv_row("Washington", "Winner A", 40, 70),
        _pv_row("Washington", "Loser B", 25, 70),      # loser with PV (EC 0-row)
    ])[list(SHARED_PV_COLUMNS)]


def _joined() -> pd.DataFrame:
    return join_ec_pv(_votes(), _CANDIDATES, _pv(), build_pv_source_frame())


def _by_key(joined: pd.DataFrame) -> dict[tuple, pd.Series]:
    return {(r.year, r.state, r.candidate): r for r in joined.itertuples()}


def test_oracle_output_is_on_the_declared_shape_and_grain() -> None:
    joined = _joined()
    assert list(joined.columns) == list(EC_PV_COLUMNS)
    # Every EC state row survives: 4 states x 3 getters = 12 rows (is_total excluded).
    assert len(joined) == 12
    assert_no_fan_out(joined)  # does not raise


def test_split_state_keeps_each_getters_real_ec_votes() -> None:
    # A split-vote state must keep each candidate's real EC count (not a 0). Nebraska:
    # A=4, B=1, both from real EC rows, summing to the state's allotment.
    rows = _by_key(_joined())
    ne_a = rows[(2020, "Nebraska", "Winner A")]
    ne_b = rows[(2020, "Nebraska", "Loser B")]
    assert ne_a.president_electoral_votes == 4
    assert ne_b.president_electoral_votes == 1
    assert ne_a.president_electoral_votes + ne_b.president_electoral_votes == 5


def test_loser_row_keeps_zero_ec_with_pv_and_national_context() -> None:
    # Loser B in Texas: a real EC 0-row (not dropped), PV attached, and the national
    # context (B's national 56 EV / rank 1 / took_office) present for flip detection.
    r = _by_key(_joined())[(2020, "Texas", "Loser B")]
    assert r.president_electoral_votes == 0
    assert r.candidate_votes == 150
    assert r.candidate_id == 2
    assert r.national_electoral_votes == 56
    assert r.president_electoral_rank == 1
    assert bool(r.took_office)


def test_national_ev_is_the_sum_of_state_votes() -> None:
    # national_electoral_votes = window sum of the candidate's state EVs. Winner A:
    # 38 (TX) + 0 (CA) + 4 (NE) + 11 (WA) = 53, carried onto every A row.
    rows = _by_key(_joined())
    for state in ("Texas", "California", "Nebraska", "Washington"):
        assert rows[(2020, state, "Winner A")].national_electoral_votes == 53


def test_getter_without_pv_is_an_honest_null_gap() -> None:
    # Faithless F won 1 EV in Washington but has no PV → EC actual, PV NULL (D005 gap).
    r = _by_key(_joined())[(2020, "Washington", "Faithless F")]
    assert r.president_electoral_votes == 1
    assert pd.isna(r.candidate_votes)
    assert pd.isna(r.state_total_votes)


def test_winner_plus_pv_carries_the_provided_denominator() -> None:
    # Winner A in Texas: EC actual + PV, and state_total_votes carried so a margin pins to
    # the source's provided denominator, not a re-sum (D017).
    r = _by_key(_joined())[(2020, "Texas", "Winner A")]
    assert r.president_electoral_votes == 38
    assert r.candidate_votes == 100
    assert r.state_total_votes == 250
    assert r.source == SOURCE_MIT
    assert bool(r.redistributable)


def test_oracle_without_pv_source_leaves_redistributable_null() -> None:
    joined = join_ec_pv(_votes(), _CANDIDATES, _pv())
    assert joined["redistributable"].isna().all()


# --- guards -----------------------------------------------------------------


def _ec_keys() -> set[tuple[int, str, str]]:
    """The (year, state, canonical-name) keys of the EC state fact — the anti-join RHS."""
    v = _votes()
    v = v[v["state"].notna()].merge(_CANDIDATES, on="candidate_id")
    return {(int(r.year), r.state, r.name) for r in v.itertuples()}


def test_anti_join_passes_when_every_pv_row_matches_an_ec_row() -> None:
    assert_pv_matches_ec(_pv(), _ec_keys())  # does not raise


def test_anti_join_raises_on_a_pv_row_with_no_ec_match() -> None:
    # A reconciled PV name/state that matches no EC votes row would be silently dropped by
    # the EC-left join — the guard fails loud instead.
    bad = pd.concat([_pv(), pd.DataFrame([_pv_row("Texas", "Ghost", 1, 2)])])
    with pytest.raises(JoinError, match="Ghost"):
        assert_pv_matches_ec(bad, _ec_keys())


def test_no_fan_out_raises_on_a_duplicated_key() -> None:
    joined = _joined()
    dup = pd.concat([joined, joined.iloc[[0]]], ignore_index=True)
    with pytest.raises(JoinError, match="fanned out"):
        assert_no_fan_out(dup)


def test_winner_has_pv_raises_on_a_reconciliation_miss() -> None:
    # Faithless F won 1 EV in Washington (a PV-covered year) with no PV. Unexempted, that
    # reads as a name-reconciliation miss and must fail loud.
    with pytest.raises(JoinError, match="no matching PV"):
        assert_winners_have_pv(_joined())


def test_winner_has_pv_passes_with_the_getter_exempted() -> None:
    # Exempt the legitimately-PV-less faithless getter → the guard is quiet, and returns
    # the count of in-window EC-**winner** rows it inspected (rows with pev > 0: A in
    # TX/NE/WA, B in CA/NE, F in WA = 6) — the vacuity floor a caller asserts against.
    inspected = assert_winners_have_pv(_joined(), exemptions={(2020, "Faithless F")})
    assert inspected == 6


def test_winner_has_pv_ignores_a_loser_without_pv() -> None:
    # A *loser* (0-EV row) with no PV must NOT be flagged — only winners (pev > 0) are
    # required to have PV (a regional candidate legitimately lacks PV where they lost).
    votes = _votes()
    # Drop Loser B's California PV so (2020, California, Loser B) — but B WON California
    # (55 EV), so use a genuine loser: drop Winner A's California PV (A lost CA, EC 0).
    pv = _pv()
    pv = pv[~((pv["state"] == "California") & (pv["candidate"] == "Winner A"))]
    joined = join_ec_pv(votes, _CANDIDATES, pv, build_pv_source_frame())
    # A/California is a 0-EV loser now missing PV — the guard must stay quiet (only F,
    # a winner, would flag, so exempt it).
    assert_winners_have_pv(joined, exemptions={(2020, "Faithless F")})
