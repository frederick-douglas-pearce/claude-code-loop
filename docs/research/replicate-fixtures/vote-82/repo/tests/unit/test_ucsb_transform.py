"""Unit tests for :mod:`usvote.ucsb.transform` — UCSB PV facts + the roster (#36).

Offline, per CLAUDE.md: the parsed input is built by hand, and the EC spine arrives
through the module's DI seam — from ``tests._helpers.ec_participation_frame`` (the
committed Archives roster snapshot) for the real-shape cases, and from small
hand-built frames for the failure cases.

The suite is organized around what can go **quietly wrong**, since this stage's whole
reason for existing is the inner-join silent-drop hazard that sum validators cannot
see:

- a state label that never reconciles and becomes a phantom (``TestCanonicalization``);
- an absence silently modeled as a vote, or a vote silently lost (``TestTwoWayAssert``);
- a contradiction resolved by the roster builder before anything checks it
  (``TestContradictions``);
- the year scope drifting away from the EC spine (``TestYearScope``).

``TestRealShapes`` runs the whole transform against the real 1824/1864/1876 rosters,
which are the only years with any structural content — 1824 has six legislature-chosen
states, 1864 has eleven non-participating ones, and everything from 1880 on is
uniform.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pandas as pd
import pytest

import usvote.years
from tests._helpers import (
    EC_GETTERS_FIXTURE,
    EC_ROSTER_FIXTURE,
    ec_getters_frame,
    ec_participation_frame,
)
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
)
from usvote.ucsb.parse import (
    STATUS_LEGISLATURE_CHOSEN,
    ParsedUCSBYear,
    UCSBCandidateColumn,
    UCSBCDRow,
    UCSBStateRow,
    UCSBStatusRow,
    UCSBVoteCell,
)
from usvote.ucsb.reconcile import (
    UCSB_CANDIDATE_RECONCILIATIONS,
    UCSB_NON_GETTER_COLUMNS,
    reconcile_ucsb,
)
from usvote.ucsb.transform import (
    RELIABILITY_EXACT,
    RELIABILITY_UNRELIABLE,
    SOURCE_UCSB,
    UCSB_NONPARTICIPATING_STATES,
    UCSB_STATE_RECONCILIATIONS,
    UCSBMissingYearError,
    UCSBRosterError,
    UCSBTransformError,
    assert_absence_matches_zero_ev,
    assert_no_zero_votes,
    assert_note_only_on_absence,
    assert_pv_columns,
    assert_pv_grain,
    transform_ucsb,
    ucsb_ingest_years,
)

SRC_UCSB = Path(__file__).resolve().parents[2] / "src" / "usvote" / "ucsb"


# --- builders ---------------------------------------------------------------
def _candidates(*names: str, other: str | None = None) -> list[UCSBCandidateColumn]:
    cols = [
        UCSBCandidateColumn(col_ind=i + 1, name=n, party="Whig", is_other=False)
        for i, n in enumerate(names)
    ]
    if other is not None:
        cols.append(
            UCSBCandidateColumn(
                col_ind=len(cols) + 1, name=other, party=None, is_other=True
            )
        )
    return cols


def _state_row(label: str, total: int, *votes: int | None) -> UCSBStateRow:
    """A state row whose published percents are exactly consistent with its votes."""
    return UCSBStateRow(
        state_label=label,
        state_total_votes=total,
        cells=[
            UCSBVoteCell(
                col_ind=i + 1,
                votes=v,
                percent=None if v is None else round(v / total * 100, 2),
            )
            for i, v in enumerate(votes)
        ],
    )


def _cd_row(label: str, parent: str, total: int, *votes: int | None) -> UCSBCDRow:
    return UCSBCDRow(**_state_row(label, total, *votes), parent_state_label=parent)


def _year(
    year: int,
    *,
    candidates: list[UCSBCandidateColumn] | None = None,
    state_rows: list[UCSBStateRow] | None = None,
    status_rows: list[UCSBStatusRow] | None = None,
    cd_rows: list[UCSBCDRow] | None = None,
) -> ParsedUCSBYear:
    cands = candidates if candidates is not None else _candidates("A. CANDIDATE")
    return ParsedUCSBYear(
        year=year,
        layout="L1",
        group_count=len(cands),
        candidates=cands,
        state_rows=state_rows if state_rows is not None else [],
        cd_rows=cd_rows or [],
        status_rows=status_rows or [],
        totals=None,
    )


def _status_row(
    label: str, note: str = "electors chosen by state legislature"
) -> UCSBStatusRow:
    return UCSBStatusRow(
        state_label=label, pv_status=STATUS_LEGISLATURE_CHOSEN, note=note
    )


def _ec(*rows: tuple[int, str | None, bool, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "year": y,
                "state": s,
                "is_total": t,
                "total_electoral_votes": ev,
            }
            for y, s, t, ev in rows
        ]
    )


# --- year scope -------------------------------------------------------------
class TestYearScope:
    def test_scope_is_the_ec_spine_minus_no_popular_vote_years(self) -> None:
        years = ucsb_ingest_years()
        assert min(years) == 1824
        assert max(years) == 2024
        assert len(years) == 49

    def test_reconstruction_years_excluded_via_the_ec_spine(self) -> None:
        # Not by a local literal — see the grep test below.
        assert 1868 not in ucsb_ingest_years()
        assert 1872 not in ucsb_ingest_years()

    def test_pre_1824_no_popular_vote_years_excluded(self) -> None:
        assert not ucsb_ingest_years() & {1789, 1792, 1820}

    def test_no_ucsb_code_path_hardcodes_the_reconstruction_years(self) -> None:
        """The D024 §6 requirement, enforced structurally rather than by convention.

        The exclusion must stay *derived* from ``UNSUPPORTED_EC_YEARS`` so #57 lifting
        the gate admits both years with no change here; a duplicated literal would
        silently keep them excluded forever.

        Checked over **executable code** via the AST, not by grepping the file. The
        literals legitimately appear in two places D024 requires: the ``1868`` keys of
        :data:`UCSB_NONPARTICIPATING_STATES` (which retains all 14 entries — the facts
        are catalogued, only the *ingest* is deferred) and the prose explaining why.
        Those are data and documentation; what must never exist is a year-scope
        decision written as a literal.
        """
        for path in SRC_UCSB.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                literals = {
                    child.value
                    for child in ast.walk(node)
                    if isinstance(child, ast.Constant) and isinstance(child.value, int)
                }
                assert not literals & {1868, 1872}, (
                    f"{path.name}:{node.name} hardcodes a Reconstruction year; derive "
                    f"the year scope from ec_ingest_years() instead (D024 §6)"
                )

    def test_lifting_the_ec_gate_admits_both_years_with_no_change_here(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates #57 landing — the self-healing property the derivation buys.

        Stronger than any grep: it asserts the *behaviour* D024 §6 promises, so a future
        refactor that reintroduces a local exclusion fails here even if it never writes
        the digits.
        """
        monkeypatch.setattr(usvote.years, "UNSUPPORTED_EC_YEARS", frozenset())
        assert {1868, 1872} <= ucsb_ingest_years()

    def test_missing_in_scope_year_raises_its_own_error(self) -> None:
        """One absent page must not read as ~40 mismatched states."""
        ec = _ec((1824, "Delaware", False, 3))
        with pytest.raises(UCSBMissingYearError, match="1824"):
            transform_ucsb([], ec, years={1824})


# --- canonicalization -------------------------------------------------------
class TestCanonicalization:
    def test_dc_abbreviation_maps_to_the_canonical_name(self) -> None:
        parsed = [_year(1964, state_rows=[_state_row("Dist. of Col.", 100, 100)])]
        ec = _ec((1964, "District of Columbia", False, 3))
        pv, roster = transform_ucsb(parsed, ec, years={1964})
        assert pv["state"].tolist() == ["District of Columbia"]
        assert roster["state"].tolist() == ["District of Columbia"]

    def test_1852_new_jersey_typo_maps_to_the_canonical_name(self) -> None:
        parsed = [_year(1852, state_rows=[_state_row("New jersey", 100, 100)])]
        ec = _ec((1852, "New Jersey", False, 7))
        pv, _ = transform_ucsb(parsed, ec, years={1852})
        assert pv["state"].tolist() == ["New Jersey"]

    def test_unmapped_label_raises_rather_than_becoming_a_phantom(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Notional", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23))
        with pytest.raises(UCSBTransformError, match="no canonical reconciliation"):
            transform_ucsb(parsed, ec, years={1900})

    def test_status_row_labels_are_canonicalized_too(self) -> None:
        """A status row keyed on a verbatim label would miss its roster state."""
        parsed = [
            _year(
                1964,
                state_rows=[_state_row("Ohio", 100, 100)],
                status_rows=[_status_row("Dist. of Col.")],
            )
        ]
        ec = _ec(
            (1964, "Ohio", False, 26), (1964, "District of Columbia", False, 3)
        )
        _, roster = transform_ucsb(parsed, ec, years={1964})
        dc = roster[roster["state"] == "District of Columbia"].iloc[0]
        assert dc["pv_status"] == PV_STATUS_LEGISLATURE_CHOSEN

    def test_map_is_exhaustive_over_the_canonical_state_names(self) -> None:
        # Every RHS must be a real canonical state name, and the two known variants
        # must both be present (the DC pair is the one that spans eras).
        assert UCSB_STATE_RECONCILIATIONS["Dist. of Col."] == "District of Columbia"
        assert UCSB_STATE_RECONCILIATIONS["District of Columbia"] == "District of Columbia"
        assert UCSB_STATE_RECONCILIATIONS["New jersey"] == "New Jersey"
        assert len(set(UCSB_STATE_RECONCILIATIONS.values())) == 51


# --- fact building ----------------------------------------------------------
class TestPVFacts:
    def test_columns_are_exactly_the_shared_shape_in_order(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 60, 40)],
                        candidates=_candidates("ALPHA", "BETA"))]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert list(pv.columns) == list(SHARED_PV_COLUMNS)

    def test_absent_cell_produces_no_row_and_never_a_zero(self) -> None:
        """D024 §2: absence is an omitted row, never a 0."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100, None)],
                        candidates=_candidates("ALPHA", "BETA"))]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["candidate"].tolist() == ["ALPHA"]
        assert not (pv["candidate_votes"] == 0).any()

    def test_other_aggregate_column_is_dropped(self) -> None:
        parsed = [
            _year(
                2020,
                candidates=_candidates("ALPHA", other="OTHERS"),
                state_rows=[_state_row("Ohio", 100, 90, 10)],
            )
        ]
        pv, _ = transform_ucsb(parsed, _ec((2020, "Ohio", False, 18)), years={2020})
        assert pv["candidate"].tolist() == ["ALPHA"]
        # ...but its votes remain represented in the state total, as MIT's do.
        assert pv["state_total_votes"].tolist() == [100]

    def test_cd_rows_are_dropped_so_the_vote_is_not_double_counted(self) -> None:
        cd = _cd_row("CD-1", "Nebraska", 40, 40)
        parsed = [_year(2020, state_rows=[_state_row("Nebraska", 100, 100)], cd_rows=[cd])]
        pv, _ = transform_ucsb(parsed, _ec((2020, "Nebraska", False, 5)), years={2020})
        assert pv["candidate_votes"].sum() == 100

    def test_candidate_names_stay_ucsb_native(self) -> None:
        # Reconciliation onto the canonical EC name is #38's.
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)],
                        candidates=_candidates("WILLIAM McKINLEY"))]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["candidate"].tolist() == ["WILLIAM McKINLEY"]

    def test_provenance_stamped_on_every_row(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        pv, roster = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert (pv["source"] == SOURCE_UCSB).all()
        assert (roster["source"] == SOURCE_UCSB).all()

    def test_vote_columns_are_integer(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pd.api.types.is_integer_dtype(pv["candidate_votes"])
        assert pd.api.types.is_integer_dtype(pv["state_total_votes"])

    def test_votes_exceeding_the_state_total_raise(self) -> None:
        row = _state_row("Ohio", 100, 60, 60)
        parsed = [_year(1900, state_rows=[row], candidates=_candidates("A", "B"))]
        with pytest.raises(UCSBTransformError, match="exceed the state total"):
            transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})


class TestReliability:
    def test_consistent_cell_is_exact(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["reliability"].tolist() == [RELIABILITY_EXACT]

    def test_published_percent_contradicting_the_votes_is_unreliable(self) -> None:
        """The 1860 VT / 1968 UT shape: the page disagrees with itself.

        We cannot know which of the two published numbers is wrong, so the *record*
        is flagged — pinning ``exact`` would assert something demonstrably false.
        """
        row = _state_row("Ohio", 100, 50)
        row["cells"][0]["percent"] = 4.16  # published; 50/100 is 50.0
        parsed = [_year(1900, state_rows=[row])]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["reliability"].tolist() == [RELIABILITY_UNRELIABLE]

    def test_rounding_slack_is_not_flagged(self) -> None:
        row = _state_row("Ohio", 3, 1)
        row["cells"][0]["percent"] = 33.3  # 1/3 = 33.33...
        parsed = [_year(1900, state_rows=[row])]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["reliability"].tolist() == [RELIABILITY_EXACT]

    def test_missing_percent_is_not_treated_as_a_contradiction(self) -> None:
        row = _state_row("Ohio", 100, 50)
        row["cells"][0]["percent"] = None
        parsed = [_year(1900, state_rows=[row])]
        pv, _ = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert pv["reliability"].tolist() == [RELIABILITY_EXACT]


# --- roster -----------------------------------------------------------------
class TestRoster:
    def test_roster_is_complete_not_an_exceptions_table(self) -> None:
        """Ordinary states get a row too — that is what makes absence detectable."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23), (1900, "Iowa", False, 13))
        parsed[0]["state_rows"].append(_state_row("Iowa", 50, 50))
        _, roster = transform_ucsb(parsed, ec, years={1900})
        assert sorted(roster["state"]) == ["Iowa", "Ohio"]
        assert set(roster["pv_status"]) == {PV_STATUS_POPULAR_VOTE}

    def test_columns_are_exactly_the_roster_shape(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        _, roster = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert list(roster.columns) == list(ROSTER_COLUMNS)

    def test_totals_rows_are_excluded_from_the_roster(self) -> None:
        """``votes.state`` is NULL on totals rows; a naive DISTINCT yields a NULL state."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23), (1900, None, True, 447))
        _, roster = transform_ucsb(parsed, ec, years={1900})
        assert roster["state"].tolist() == ["Ohio"]
        assert roster["state"].notna().all()

    def test_legislature_chosen_carries_the_verbatim_note(self) -> None:
        note = "3 electors chosen by state legislature and awarded to R. B. Hayes"
        parsed = [_year(1876, state_rows=[_state_row("Ohio", 100, 100)],
                        status_rows=[_status_row("Colorado", note)])]
        ec = _ec((1876, "Ohio", False, 22), (1876, "Colorado", False, 3))
        _, roster = transform_ucsb(parsed, ec, years={1876})
        colorado = roster[roster["state"] == "Colorado"].iloc[0]
        assert colorado["pv_status"] == PV_STATUS_LEGISLATURE_CHOSEN
        assert colorado["note"] == note

    def test_not_participating_comes_from_the_constant(self) -> None:
        parsed = [_year(1864, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1864, "Ohio", False, 21), (1864, "Alabama", False, 0))
        _, roster = transform_ucsb(parsed, ec, years={1864})
        alabama = roster[roster["state"] == "Alabama"].iloc[0]
        assert alabama["pv_status"] == PV_STATUS_NOT_PARTICIPATING
        assert "Seceded" in alabama["note"]

    def test_popular_vote_is_the_residual(self) -> None:
        parsed = [_year(1864, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1864, "Ohio", False, 21), (1864, "Alabama", False, 0))
        _, roster = transform_ucsb(parsed, ec, years={1864})
        assert roster[roster["state"] == "Ohio"].iloc[0]["pv_status"] == (
            PV_STATUS_POPULAR_VOTE
        )

    def test_note_is_null_on_ordinary_rows(self) -> None:
        """Keeps the non-redistributable verbatim text confined to absence rows."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        _, roster = transform_ucsb(parsed, _ec((1900, "Ohio", False, 23)), years={1900})
        assert roster["note"].isna().all()

    def test_empty_roster_for_an_in_scope_year_raises_the_roster_error(self) -> None:
        """A distinct failure from "a state mismatched" — different cause, different fix."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1896, "Ohio", False, 23))  # spine loaded for the WRONG year
        with pytest.raises(UCSBRosterError, match="pipeline-sequencing failure"):
            transform_ucsb(parsed, ec, years={1900})

    def test_empty_roster_beats_a_status_contradiction_when_the_spine_is_missing(
        self,
    ) -> None:
        """A year with legislature rows and no spine must report the sequencing failure,
        not blame UCSB and the Archives for disagreeing about participation."""
        parsed = [
            _year(
                1824,
                state_rows=[_state_row("Ohio", 100, 100)],
                status_rows=[_status_row("Delaware")],
            )
        ]
        ec = _ec((1820, "Ohio", False, 8))  # spine loaded for the WRONG year
        with pytest.raises(UCSBRosterError, match="pipeline-sequencing failure"):
            transform_ucsb(parsed, ec, years={1824})

    def test_participation_frame_missing_a_column_raises(self) -> None:
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23)).drop(columns=["is_total"])
        with pytest.raises(UCSBRosterError, match="missing column"):
            transform_ucsb(parsed, ec, years={1900})

    def test_nonparticipating_constant_keeps_all_fourteen_entries(self) -> None:
        """All 14 are catalogued; only in-scope years are consumed (D024 §6).

        1868's three are deferred behind #57, not deleted — deferring an ingest is not
        hiding a fact. This count flips 11 -> 14 automatically when #57 lands.
        """
        assert len(UCSB_NONPARTICIPATING_STATES) == 14
        in_scope = ucsb_ingest_years()
        consumed = {k for k in UCSB_NONPARTICIPATING_STATES if k[0] in in_scope}
        assert len(consumed) == 11
        assert {k[0] for k in consumed} == {1864}

    def test_every_in_scope_constant_entry_produces_a_roster_row(self) -> None:
        parsed = [_year(1864, state_rows=[_state_row("Ohio", 100, 100)])]
        expected = [k[1] for k in UCSB_NONPARTICIPATING_STATES if k[0] == 1864]
        ec = _ec((1864, "Ohio", False, 21), *[(1864, s, False, 0) for s in expected])
        _, roster = transform_ucsb(parsed, ec, years={1864})
        marked = roster[roster["pv_status"] == PV_STATUS_NOT_PARTICIPATING]
        assert sorted(marked["state"]) == sorted(expected)


# --- the two-way assert -----------------------------------------------------
class TestTwoWayAssert:
    def test_popular_vote_state_with_no_facts_raises(self) -> None:
        """The silent-drop case: the roster expects votes, the facts have none."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23), (1900, "Iowa", False, 13))
        with pytest.raises(UCSBRosterError, match="have no vote rows"):
            transform_ucsb(parsed, ec, years={1900})

    def test_absence_state_carrying_votes_raises(self) -> None:
        parsed = [
            _year(
                1876,
                state_rows=[_state_row("Ohio", 100, 100)],
                status_rows=[_status_row("Colorado")],
            )
        ]
        parsed[0]["state_rows"].append(_state_row("Colorado", 50, 50))
        ec = _ec((1876, "Ohio", False, 22), (1876, "Colorado", False, 3))
        # Caught even earlier, as a contradiction on the inputs.
        with pytest.raises(UCSBTransformError, match="both popular-vote rows"):
            transform_ucsb(parsed, ec, years={1876})

    def test_phantom_state_absent_from_the_roster_raises(self) -> None:
        """The check no sum validator can replace."""
        parsed = [
            _year(
                1900,
                state_rows=[_state_row("Ohio", 100, 100), _state_row("Iowa", 50, 50)],
            )
        ]
        ec = _ec((1900, "Ohio", False, 23))
        with pytest.raises(UCSBRosterError, match="absent from"):
            transform_ucsb(parsed, ec, years={1900})

    def test_other_sources_rows_do_not_trip_the_ucsb_assert(self) -> None:
        """``dwh.pv_votes`` holds MIT rows too (D021) — the assert is source-scoped."""
        from usvote.pv.status import assert_roster_covers_facts

        pv = pd.DataFrame([
            {"source": "UCSB", "year": 1900, "state": "Ohio"},
            {"source": "MIT", "year": 1900, "state": "Nowhere"},
        ])
        roster = pd.DataFrame([{
            "source": "UCSB", "year": 1900, "state": "Ohio",
            "pv_status": PV_STATUS_POPULAR_VOTE, "note": None,
        }])
        assert_roster_covers_facts(pv, roster, source="UCSB", years={1900})

    def test_unprocessed_years_are_not_reported_as_violations(self) -> None:
        from usvote.pv.status import assert_roster_covers_facts

        pv = pd.DataFrame([{"source": "UCSB", "year": 1900, "state": "Ohio"}])
        roster = pd.DataFrame([
            {"source": "UCSB", "year": 1900, "state": "Ohio",
             "pv_status": PV_STATUS_POPULAR_VOTE, "note": None},
            {"source": "UCSB", "year": 1904, "state": "Iowa",
             "pv_status": PV_STATUS_POPULAR_VOTE, "note": None},
        ])
        # 1904 has a roster row and no facts, but was not processed.
        assert_roster_covers_facts(pv, roster, source="UCSB", years={1900})


# --- contradictions ---------------------------------------------------------
class TestContradictions:
    def test_legislature_state_absent_from_the_roster_raises(self) -> None:
        parsed = [
            _year(
                1876,
                state_rows=[_state_row("Ohio", 100, 100)],
                status_rows=[_status_row("Colorado")],
            )
        ]
        ec = _ec((1876, "Ohio", False, 22))
        with pytest.raises(UCSBRosterError, match="absent from the EC roster"):
            transform_ucsb(parsed, ec, years={1876})

    def test_state_both_flagged_and_nonparticipating_raises(self) -> None:
        """Must be caught on the *inputs* — the builder would resolve it silently."""
        parsed = [
            _year(
                1864,
                state_rows=[_state_row("Ohio", 100, 100)],
                status_rows=[_status_row("Alabama")],
            )
        ]
        ec = _ec((1864, "Ohio", False, 21), (1864, "Alabama", False, 0))
        with pytest.raises(UCSBTransformError, match="cannot both"):
            transform_ucsb(parsed, ec, years={1864})

    def test_nonparticipating_state_with_votes_raises(self) -> None:
        parsed = [
            _year(
                1864,
                state_rows=[_state_row("Ohio", 100, 100), _state_row("Alabama", 50, 50)],
            )
        ]
        ec = _ec((1864, "Ohio", False, 21), (1864, "Alabama", False, 0))
        with pytest.raises(UCSBTransformError, match="but have UCSB popular-vote rows"):
            transform_ucsb(parsed, ec, years={1864})

    def test_canonicalization_reopened_overlap_is_re_asserted(self) -> None:
        """#35 checks this on VERBATIM labels; the map is many-to-one.

        ``New jersey`` as a vote row beside ``New Jersey`` as a status row passes the
        parser's guard and collapses onto one state here.
        """
        parsed = [
            _year(
                1852,
                state_rows=[_state_row("New jersey", 100, 100)],
                status_rows=[_status_row("New Jersey")],
            )
        ]
        ec = _ec((1852, "New Jersey", False, 7))
        with pytest.raises(UCSBTransformError, match="once labels are canonicalized"):
            transform_ucsb(parsed, ec, years={1852})

    def test_two_labels_collapsing_to_one_state_raise_rather_than_double_count(self) -> None:
        parsed = [
            _year(
                1964,
                state_rows=[
                    _state_row("Dist. of Col.", 100, 100),
                    _state_row("District of Columbia", 50, 50),
                ],
            )
        ]
        ec = _ec((1964, "District of Columbia", False, 3))
        with pytest.raises(UCSBTransformError, match="duplicate canonical state"):
            transform_ucsb(parsed, ec, years={1964})


# --- the EV==0 cross-check --------------------------------------------------
class TestZeroElectoralVoteCrossCheck:
    def test_nonparticipating_state_with_electoral_votes_raises(self) -> None:
        """Validates our constant against the authority (D024 §5)."""
        parsed = [_year(1864, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1864, "Ohio", False, 21), (1864, "Alabama", False, 9))
        with pytest.raises(UCSBRosterError, match="took no part"):
            transform_ucsb(parsed, ec, years={1864})

    def test_zero_ev_state_classified_popular_vote_raises_pointing_at_the_spine(self) -> None:
        parsed = [
            _year(
                1900,
                state_rows=[_state_row("Ohio", 100, 100), _state_row("Iowa", 50, 50)],
            )
        ]
        ec = _ec((1900, "Ohio", False, 23), (1900, "Iowa", False, 0))
        with pytest.raises(UCSBRosterError, match="change in the EC spine"):
            transform_ucsb(parsed, ec, years={1900})

    def test_legislature_chosen_states_may_carry_electoral_votes(self) -> None:
        """1876 Colorado cast 3 EV while holding no popular vote — not a contradiction."""
        parsed = [_year(1876, state_rows=[_state_row("Ohio", 100, 100)],
                        status_rows=[_status_row("Colorado")])]
        ec = _ec((1876, "Ohio", False, 22), (1876, "Colorado", False, 3))
        _, roster = transform_ucsb(parsed, ec, years={1876})
        assert roster[roster["state"] == "Colorado"].iloc[0]["pv_status"] == (
            PV_STATUS_LEGISLATURE_CHOSEN
        )


# --- real Archives roster shapes --------------------------------------------
class TestRealShapes:
    """The whole transform against the real EC rosters for the structural years.

    1824 (24 states, six legislature-chosen) and 1864 (36 states, eleven
    non-participating) are the only years with content the synthetic cases cannot
    reproduce; everything from 1880 on is uniform.
    """

    def test_1824_roster_matches_the_real_archives_shape(self) -> None:
        legislature = [
            "Delaware", "Georgia", "Louisiana", "New York", "South Carolina", "Vermont",
        ]
        voting = [
            s for s in _roster_states(1824) if s not in legislature
        ]
        parsed = [
            _year(
                1824,
                state_rows=[_state_row(s, 100, 100) for s in voting],
                status_rows=[_status_row(s) for s in legislature],
            )
        ]
        _, roster = transform_ucsb(
            parsed, ec_participation_frame([1824]), years={1824}
        )
        assert len(roster) == 24
        assert sorted(
            roster[roster["pv_status"] == PV_STATUS_LEGISLATURE_CHOSEN]["state"]
        ) == legislature

    def test_1864_roster_marks_exactly_the_eleven_confederate_states(self) -> None:
        nonparticipating = [k[1] for k in UCSB_NONPARTICIPATING_STATES if k[0] == 1864]
        voting = [s for s in _roster_states(1864) if s not in nonparticipating]
        parsed = [_year(1864, state_rows=[_state_row(s, 100, 100) for s in voting])]
        _, roster = transform_ucsb(
            parsed, ec_participation_frame([1864]), years={1864}
        )
        assert len(roster) == 36
        assert len(voting) == 25
        marked = roster[roster["pv_status"] == PV_STATUS_NOT_PARTICIPATING]
        assert sorted(marked["state"]) == sorted(nonparticipating)

    def test_fixture_is_test_input_only_and_never_read_from_src(self) -> None:
        """It must not become a second source of participation truth (D006)."""
        src = Path(__file__).resolve().parents[2] / "src"
        for path in src.rglob("*.py"):
            assert EC_ROSTER_FIXTURE.name not in path.read_text(encoding="utf-8")

    def test_fixture_carries_no_electoral_vote_counts(self) -> None:
        """D024 §5: the EC fact is the single source of electoral-vote truth."""
        entries = json.loads(EC_ROSTER_FIXTURE.read_text(encoding="utf-8"))["years"]
        for entry in entries.values():
            assert set(entry) == {"states", "zero_ev_states"}

    def test_getter_fixture_is_test_input_only_and_never_read_from_src(self) -> None:
        """The witness must not become the reconcile map's own source (D006 circularity)."""
        src = Path(__file__).resolve().parents[2] / "src"
        for path in src.rglob("*.py"):
            assert EC_GETTERS_FIXTURE.name not in path.read_text(encoding="utf-8")

    def test_getter_fixture_carries_no_electoral_vote_counts(self) -> None:
        """D024 §5: getter identity only, never counts (each year is a list of names)."""
        entries = json.loads(EC_GETTERS_FIXTURE.read_text(encoding="utf-8"))["years"]
        for names in entries.values():
            assert isinstance(names, list)
            assert all(isinstance(n, str) for n in names)


def _roster_states(year: int) -> list[str]:
    entries = json.loads(EC_ROSTER_FIXTURE.read_text(encoding="utf-8"))["years"]
    return list(entries[str(year)]["states"])


class TestDefensiveGuards:
    """The validators a well-formed transform can never trip, exercised directly.

    Each guards an invariant the transform currently upholds by construction, which is
    exactly why they need their own tests: reached only through ``transform_ucsb`` they
    would sit at 0% coverage, and an unexercised guard is one nobody notices breaking
    during a later refactor (the melt growing a ``fillna(0)``, say).
    """

    def test_null_is_total_raises(self) -> None:
        """A DB read can hand back object-dtype ``is_total`` with nulls (#37's seam)."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23))
        ec["is_total"] = ec["is_total"].astype("object")
        ec.loc[0, "is_total"] = None
        with pytest.raises(UCSBRosterError, match="null `is_total`"):
            transform_ucsb(parsed, ec, years={1900})

    def test_string_is_total_raises_rather_than_emptying_the_roster(self) -> None:
        """'t'/'f' strings are both truthy under ``.astype(bool)`` — every row would read
        as a total and the roster would silently come back empty."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23), (1900, None, True, 99))
        ec["is_total"] = ec["is_total"].map({False: "f", True: "t"})
        with pytest.raises(UCSBRosterError, match="is not boolean"):
            transform_ucsb(parsed, ec, years={1900})

    def test_object_column_of_real_bools_is_accepted(self) -> None:
        """psycopg2 yields Python bools in an object column — that must still pass."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23))
        ec["is_total"] = ec["is_total"].astype("object")
        pv, _ = transform_ucsb(parsed, ec, years={1900})
        assert pv["state"].tolist() == ["Ohio"]

    def test_null_total_electoral_votes_raises_typed_not_valueerror(self) -> None:
        """A NULL EV would otherwise crash at ``int(NaN)`` with an untyped ValueError."""
        parsed = [_year(1900, state_rows=[_state_row("Ohio", 100, 100)])]
        ec = _ec((1900, "Ohio", False, 23))
        ec["total_electoral_votes"] = ec["total_electoral_votes"].astype("float")
        ec.loc[0, "total_electoral_votes"] = float("nan")
        with pytest.raises(UCSBRosterError, match="null `total_electoral_votes`"):
            transform_ucsb(parsed, ec, years={1900})

    def test_duplicate_parsed_year_raises_rather_than_dropping_the_first(self) -> None:
        parsed = [
            _year(1900, state_rows=[_state_row("Ohio", 100, 100)]),
            _year(1900, state_rows=[_state_row("Iowa", 50, 50)]),
        ]
        ec = _ec((1900, "Ohio", False, 23), (1900, "Iowa", False, 13))
        with pytest.raises(UCSBTransformError, match="more than one parsed UCSB page"):
            transform_ucsb(parsed, ec, years={1900})

    def test_null_candidate_column_raises(self) -> None:
        """`candidate` is a key column — its non-null check must not be omitted."""
        frame = pd.DataFrame([{
            "source": SOURCE_UCSB, "year": 1900, "state": "Ohio", "candidate": None,
            "party": None, "candidate_votes": 1, "state_total_votes": 1,
            "reliability": RELIABILITY_EXACT,
        }])
        with pytest.raises(UCSBTransformError, match=r"'candidate' has null value\(s\)"):
            assert_pv_columns(frame)

    def test_duplicate_pv_grain_raises(self) -> None:
        frame = pd.DataFrame([
            {"year": 1900, "state": "Ohio", "candidate": "A"},
            {"year": 1900, "state": "Ohio", "candidate": "A"},
        ])
        with pytest.raises(UCSBTransformError, match="grain violated"):
            assert_pv_grain(frame)

    def test_zero_vote_row_raises(self) -> None:
        """D024 §2's central finding, guarded at the frame that reaches the DB."""
        frame = pd.DataFrame([
            {"year": 1900, "state": "Ohio", "candidate": "A", "candidate_votes": 0}
        ])
        with pytest.raises(UCSBTransformError, match="Absence is"):
            assert_no_zero_votes(frame)

    def test_wrong_columns_raise(self) -> None:
        frame = pd.DataFrame(columns=list(reversed(SHARED_PV_COLUMNS)))
        with pytest.raises(UCSBTransformError, match="!= shared PV shape"):
            assert_pv_columns(frame)

    def test_null_key_column_raises(self) -> None:
        frame = pd.DataFrame([{
            "source": SOURCE_UCSB, "year": 1900, "state": None, "candidate": "A",
            "party": None, "candidate_votes": 1, "state_total_votes": 1,
            "reliability": RELIABILITY_EXACT,
        }])
        with pytest.raises(UCSBTransformError, match=r"has null value\(s\)"):
            assert_pv_columns(frame)

    def test_float_vote_column_raises(self) -> None:
        """A float count would silently round into the ``integer`` DDL column."""
        frame = pd.DataFrame([{
            "source": SOURCE_UCSB, "year": 1900, "state": "Ohio", "candidate": "A",
            "party": None, "candidate_votes": 1.5, "state_total_votes": 2,
            "reliability": RELIABILITY_EXACT,
        }])
        with pytest.raises(UCSBTransformError, match="must be integer"):
            assert_pv_columns(frame)

    def test_note_on_a_popular_vote_row_raises(self) -> None:
        """Keeps non-redistributable verbatim UCSB text off ordinary rows."""
        roster = pd.DataFrame([{
            "source": SOURCE_UCSB, "year": 1900, "state": "Ohio",
            "pv_status": PV_STATUS_POPULAR_VOTE, "note": "verbatim UCSB prose",
        }])
        with pytest.raises(UCSBTransformError, match="carry a note"):
            assert_note_only_on_absence(roster)

    def test_roster_state_absent_from_the_spine_is_skipped_not_crashed(self) -> None:
        """The EV cross-check tolerates a roster row it has no EV figure for.

        Unreachable from ``transform_ucsb`` (the roster is built *from* that mapping),
        but #37 may hand the assert a roster read back from the DB.
        """
        roster = pd.DataFrame([{
            "source": SOURCE_UCSB, "year": 1900, "state": "Atlantis",
            "pv_status": PV_STATUS_POPULAR_VOTE, "note": None,
        }])
        assert_absence_matches_zero_ev(roster, {1900: {"Ohio": 23}})


_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


@pytest.fixture(scope="module")
def real_corpus_result() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Transform the whole real snapshot once, against the committed EC rosters."""
    from usvote.ucsb.parse import parse_election_years

    years = ucsb_ingest_years()
    html = {
        year: (Path(_CORPUS) / f"{year}.html").read_text(
            encoding="utf-8", errors="replace"
        )
        for year in years
    }
    return transform_ucsb(parse_election_years(html), ec_participation_frame(years))


@pytest.fixture(scope="module")
def real_corpus_reconciled(
    real_corpus_result: tuple[pd.DataFrame, pd.DataFrame],
) -> pd.DataFrame:
    """Reconcile the whole real snapshot against the committed EC-getter witness (#38)."""
    pv, roster = real_corpus_result
    years = ucsb_ingest_years()
    return reconcile_ucsb(pv, roster, ec_getters_frame(years), years=years)


@pytest.mark.skipif(
    not _CORPUS,
    reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo",
)
class TestRealCorpus:
    """The acceptance check the synthetics cannot deliver: all 49 in-scope years.

    Skipped whenever the snapshot is absent, so CI stays green and never touches UCSB
    (D014/D016/D022) — the same contract as ``test_ucsb_parse.TestRealCorpus``. The EC
    side comes from the committed Archives roster snapshot, so this stays offline; it
    is the only test that runs the two-way assert over the real corpus against real
    rosters, which is what proves the guard passes on the data we actually have rather
    than only on fixtures built to satisfy it.
    """

    def test_every_in_scope_year_transforms_and_the_assert_passes(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        pv, roster = real_corpus_result
        assert set(pv["year"]) == ucsb_ingest_years()
        assert set(roster["year"]) == ucsb_ingest_years()

    def test_seventeen_legislature_chosen_rows_reach_the_roster(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        """18 in the corpus, 17 in the roster — 1868 FL is outside the EC spine.

        Not a regression: the count moves to 18 when #57 admits 1868. Stated at the
        layer it measures (see ``docs/ucsb-html-formats.md`` §4 case 1).
        """
        _, roster = real_corpus_result
        legislature = roster[roster["pv_status"] == PV_STATUS_LEGISLATURE_CHOSEN]
        assert len(legislature) == 17
        assert 1868 not in set(legislature["year"])

    def test_eleven_non_participating_rows_reach_the_roster(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        _, roster = real_corpus_result
        marked = roster[roster["pv_status"] == PV_STATUS_NOT_PARTICIPATING]
        assert len(marked) == 11
        assert set(marked["year"]) == {1864}

    def test_state_labels_are_all_canonical(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        pv, roster = real_corpus_result
        canonical = set(UCSB_STATE_RECONCILIATIONS.values())
        assert set(pv["state"]) <= canonical
        assert set(roster["state"]) <= canonical
        assert "Dist. of Col." not in set(pv["state"])

    def test_reliability_flags_only_self_contradicting_cells(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        """Four cells corpus-wide, each a published percent contradicting its votes.

        1860 VT/VA/WI each repeat the *next* candidate's percent in the Douglas cell
        (4.16, 44.46, 0.58) while their votes sum exactly to the state total; 1968 UT
        publishes 31.1 where 156,665/422,568 is 37.1. Every other 1860 state agrees to
        0.00pp, which is what shows these are isolated source typos rather than a
        column misalignment. Catalogued in ``docs/corrections.md``.
        """
        pv, _ = real_corpus_result
        flagged = pv[pv["reliability"] == RELIABILITY_UNRELIABLE]
        assert sorted(
            flagged[["year", "state"]].itertuples(index=False, name=None)
        ) == [
            (1860, "Vermont"),
            (1860, "Virginia"),
            (1860, "Wisconsin"),
            (1968, "Utah"),
        ]

    def test_no_row_carries_zero_votes(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        pv, _ = real_corpus_result
        assert not (pv["candidate_votes"] == 0).any()

    def test_notes_appear_only_on_absence_rows(
        self, real_corpus_result: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        _, roster = real_corpus_result
        assert roster["note"].notna().sum() == 28  # 17 legislature + 11 not-participating
        assert set(roster.loc[roster["note"].notna(), "pv_status"]) == {
            PV_STATUS_LEGISLATURE_CHOSEN,
            PV_STATUS_NOT_PARTICIPATING,
        }

    # --- reconcile (#38): the only run of reconcile over all 49 in-scope years ---
    def test_reconcile_passes_all_guards_over_the_whole_corpus(
        self, real_corpus_reconciled: pd.DataFrame
    ) -> None:
        # reconcile_ucsb builds and asserts internally (coverage, completeness, grain,
        # two-way roster) — reaching here at all proves every guard held on real data.
        out = real_corpus_reconciled
        assert set(out["year"]) == ucsb_ingest_years()
        assert not out.duplicated(["year", "state", "candidate"]).any()

    def test_every_candidate_is_a_canonical_ec_name(
        self, real_corpus_reconciled: pd.DataFrame
    ) -> None:
        # After reconcile no UCSB-native ALLCAPS spelling survives; every name is an EC
        # getter for its year, per the independent witness.
        out = real_corpus_reconciled
        getter_keys = set(
            ec_getters_frame(ucsb_ingest_years())
            .itertuples(index=False, name=None)
        )
        getter_keys = {(y, c) for y, c, _ in getter_keys}
        for year, name in out[["year", "candidate"]].itertuples(index=False, name=None):
            assert (year, name) in getter_keys

    def test_d007_drops_the_eight_non_getter_columns(
        self,
        real_corpus_result: tuple[pd.DataFrame, pd.DataFrame],
        real_corpus_reconciled: pd.DataFrame,
    ) -> None:
        # Every UCSB column is classified (mapped or dropped); the drops are exactly the
        # eight zero-EV minors, and reconcile removes their rows.
        pv, _ = real_corpus_result
        native = {
            (int(y), c) for y, c in pv[["year", "candidate"]].itertuples(index=False, name=None)
        }
        assert native == set(UCSB_CANDIDATE_RECONCILIATIONS) | UCSB_NON_GETTER_COLUMNS
        assert len(real_corpus_reconciled) < len(pv)
