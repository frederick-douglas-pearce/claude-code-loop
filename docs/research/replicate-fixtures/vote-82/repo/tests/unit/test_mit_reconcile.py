"""Unit tests for :mod:`usvote.mit.reconcile` — MIT names -> canonical keys (#67).

Offline, and the map RHS is checked against **independent authorities**, not a copy of
itself: the state targets against the shared ``STATE_NAMES`` SSOT, and the candidate
targets against the real National Archives HTML fixtures parsed through the actual EC
parse path (2016/2020/2024 — the in-window years snapshotted in ``tests/fixtures``).
A ``transform_mit -> reconcile_mit`` seam test on the MIT sample fixture ties the map
*keys* to what the transform actually emits. The remaining checks lock the two-Bushes
non-collision, value uniqueness, and every :class:`MITReconcileError` guard.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, STATE_NAMES
from usvote.mit.read import load_mit_president_csv
from usvote.mit.reconcile import (
    MIT_CANDIDATE_RECONCILIATIONS,
    MIT_STATE_RECONCILIATIONS,
    MITReconcileError,
    reconcile_mit,
)
from usvote.mit.transform import transform_mit
from usvote.parse import parse_table1
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.scrape import fetch_from_dir, get_html_tables
from usvote.transform import CANDIDATE_NAME_FIXES, PARTY_NAME_FIXES


def ec_canonical_president_names(year: int) -> list[str]:
    """Return a fixture year's EC canonical president names via the real parse path.

    Parses Table 1 from the snapshotted Archives HTML and applies the same name
    corrections the EC candidate dim applies (``PARTY_NAME_FIXES`` then
    ``CANDIDATE_NAME_FIXES``), so the result is exactly the canonical ``name`` the MIT
    map's RHS must match — derived from the authority, never hand-copied here.
    """
    tables = get_html_tables(
        f"https://www.archives.gov/electoral-college/{year}",
        find_all=True,
        fetch=fetch_from_dir(FIXTURES_DIR),
    )
    names = []
    for cand in parse_table1(tables[0].find_all("tr")):
        raw = cand["president_candidate_name"]
        corrected = PARTY_NAME_FIXES.get(raw, raw)
        corrected = CANDIDATE_NAME_FIXES.get(corrected, {}).get("name", corrected)
        names.append(corrected)
    return names


def make_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Build a valid D018 ``SHARED_PV_COLUMNS`` frame from partial rows.

    Each row must carry ``year``/``state``/``candidate``; provenance and vote columns
    default to plausible constants (reconcile ignores everything but state/candidate,
    but the shape guard requires the full column set with no nulls).
    """
    filled = [
        {
            "source": "MIT",
            "year": r["year"],
            "state": r["state"],
            "candidate": r["candidate"],
            "party": r.get("party", "DEMOCRAT"),
            "candidate_votes": r.get("candidate_votes", 100),
            "state_total_votes": r.get("state_total_votes", 200),
            "reliability": "exact",
        }
        for r in rows
    ]
    return pd.DataFrame(filled)[list(SHARED_PV_COLUMNS)]


class TestCandidateMap:
    @pytest.mark.parametrize("year", [2016, 2020, 2024])
    def test_rhs_matches_archives_fixtures(self, year: int) -> None:
        # Authority-backed (not a self-copy): every EC canonical president name for an
        # in-window fixture year, derived through the real Archives-parse path, must be
        # a value in the MIT map. Breaks the tautology of asserting the map equals a
        # hand-copy of itself — a wrong RHS (e.g. "Kamala Harris" without the "D.")
        # fails here because the fixture-derived name is not among the map's values.
        canonical_values = set(MIT_CANDIDATE_RECONCILIATIONS.values())
        for name in ec_canonical_president_names(year):
            assert name in canonical_values, (
                f"{year} EC name {name!r} is not an RHS value of the MIT map"
            )

    def test_map_values_are_unique(self) -> None:
        # No two MIT nominees may reconcile to the same canonical name (that would
        # double-count them in any single year they overlap — the grain hazard at the
        # map level rather than the frame level).
        values = list(MIT_CANDIDATE_RECONCILIATIONS.values())
        assert len(values) == len(set(values))

    def test_keys_are_mit_native_format(self) -> None:
        # LHS keys are the "LAST, FIRST ..." ALLCAPS strings MIT emits; a lowercase or
        # comma-less key signals the map drifted from the transform's output form.
        for key in MIT_CANDIDATE_RECONCILIATIONS:
            assert key == key.upper() and "," in key

    @pytest.mark.parametrize(
        ("mit_name", "canonical"),
        [
            ("CARTER, JIMMY", "Jimmy Carter"),        # early year
            ("FORD, GERALD", "Gerald R. Ford"),       # EC adds a middle initial
            ("OBAMA, BARACK H.", "Barack Obama"),     # MIT middle initial dropped
            ("CLINTON, BILL", "William J. Clinton"),  # given-name substitution
            ("GORE, AL", "Albert Gore Jr."),          # given name + suffix
            ("DOLE, ROBERT", "Robert Dole"),          # Bob->Robert EC correction
            ("HARRIS, KAMALA D.", "Kamala D. Harris"),  # most recent year
        ],
    )
    def test_representative_candidate_reconciliations(
        self, mit_name: str, canonical: str
    ) -> None:
        out = reconcile_mit(make_frame([{"year": 2000, "state": "OHIO", "candidate": mit_name}]))
        assert out.iloc[0]["candidate"] == canonical

    def test_two_bushes_map_to_distinct_names(self) -> None:
        # The same-name-collision hazard (docs/canonical-keys.md): a future edit must
        # not collapse the elder and younger Bush onto one canonical name.
        elder = MIT_CANDIDATE_RECONCILIATIONS["BUSH, GEORGE H.W."]
        younger = MIT_CANDIDATE_RECONCILIATIONS["BUSH, GEORGE W."]
        assert elder == "George Bush"
        assert younger == "George W. Bush"
        assert elder != younger

    def test_map_covers_exactly_18_nominees(self) -> None:
        assert len(MIT_CANDIDATE_RECONCILIATIONS) == 18


class TestStateMap:
    def test_rhs_matches_canonical_state_names(self) -> None:
        # Authority-backed: the state targets must equal the shared 50-states-plus-DC
        # SSOT the EC parse/transform tests use (tests._helpers.STATE_NAMES), not a
        # copy defined in this file. Catches a mis-spelled or missing jurisdiction
        # (e.g. "District Of Columbia") independently of the reconcile map itself.
        assert set(MIT_STATE_RECONCILIATIONS.values()) == STATE_NAMES
        assert len(MIT_STATE_RECONCILIATIONS) == len(STATE_NAMES) == 51

    def test_all_states_reconcile(self) -> None:
        rows = [
            {"year": 2020, "state": s, "candidate": "BIDEN, JOSEPH R. JR"}
            for s in MIT_STATE_RECONCILIATIONS
        ]
        out = reconcile_mit(make_frame(rows))
        assert set(out["state"]) == set(MIT_STATE_RECONCILIATIONS.values())

    def test_dc_lowercase_of_not_titlecase(self) -> None:
        # .title() would wrongly yield "District Of Columbia"; the map must not.
        out = reconcile_mit(
            make_frame([{"year": 2020, "state": "DISTRICT OF COLUMBIA",
                         "candidate": "BIDEN, JOSEPH R. JR"}])
        )
        assert out.iloc[0]["state"] == "District of Columbia"


class TestShapePreserved:
    def test_columns_grain_and_row_count_unchanged(self) -> None:
        frame = make_frame([
            {"year": 2016, "state": "MICHIGAN", "candidate": "TRUMP, DONALD J."},
            {"year": 2016, "state": "MICHIGAN", "candidate": "CLINTON, HILLARY"},
            {"year": 2020, "state": "GEORGIA", "candidate": "BIDEN, JOSEPH R. JR"},
        ])
        out = reconcile_mit(frame)
        assert list(out.columns) == list(SHARED_PV_COLUMNS)
        assert len(out) == 3
        # unchanged columns pass through verbatim
        assert list(out["candidate_votes"]) == list(frame["candidate_votes"])

    def test_many_to_one_alt_spelling_supported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fred's Q1: two distinct MIT strings for one person → one canonical name is
        # fine (map values need not be unique). Simulate an alternate spelling for a
        # different election year; both must reconcile to the same canonical name and
        # the grain must hold (distinct year/state keeps them separate rows).
        patched = {**MIT_CANDIDATE_RECONCILIATIONS, "CLINTON, WILLIAM J.": "William J. Clinton"}
        monkeypatch.setattr(
            "usvote.mit.reconcile.MIT_CANDIDATE_RECONCILIATIONS", patched
        )
        out = reconcile_mit(make_frame([
            {"year": 1992, "state": "OHIO", "candidate": "CLINTON, BILL"},
            {"year": 1996, "state": "OHIO", "candidate": "CLINTON, WILLIAM J."},
        ]))
        assert list(out["candidate"]) == ["William J. Clinton", "William J. Clinton"]


class TestGuards:
    def test_unmapped_state_raises(self) -> None:
        with pytest.raises(MITReconcileError, match="PUERTO RICO"):
            reconcile_mit(
                make_frame([{"year": 2020, "state": "PUERTO RICO",
                             "candidate": "BIDEN, JOSEPH R. JR"}])
            )

    def test_unmapped_candidate_raises(self) -> None:
        with pytest.raises(MITReconcileError, match="NADER, RALPH"):
            reconcile_mit(
                make_frame([{"year": 2000, "state": "OHIO", "candidate": "NADER, RALPH"}])
            )

    def test_null_value_raises_reconcile_error_not_typeerror(self) -> None:
        # A malformed upstream frame (a null state among strings) must surface as a
        # clean MITReconcileError, not a TypeError from sorting mixed NaN/str values.
        frame = make_frame([
            {"year": 2020, "state": "OHIO", "candidate": "BIDEN, JOSEPH R. JR"},
            {"year": 2020, "state": "TEXAS", "candidate": "TRUMP, DONALD J."},
        ])
        frame.loc[0, "state"] = None
        with pytest.raises(MITReconcileError):
            reconcile_mit(frame)

    def test_grain_collapse_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two distinct MIT strings mapping to the SAME canonical name within one
        # (year, state) would double-count downstream — must raise, not silently pass.
        patched = {**MIT_CANDIDATE_RECONCILIATIONS, "BILL CLINTON": "William J. Clinton"}
        monkeypatch.setattr(
            "usvote.mit.reconcile.MIT_CANDIDATE_RECONCILIATIONS", patched
        )
        with pytest.raises(MITReconcileError, match="grain violated"):
            reconcile_mit(make_frame([
                {"year": 1992, "state": "OHIO", "candidate": "CLINTON, BILL"},
                {"year": 1992, "state": "OHIO", "candidate": "BILL CLINTON"},
            ]))


class TestSeamOnFixture:
    """Exercise the real transform_mit -> reconcile_mit seam on the MIT sample fixture.

    Ties the map *keys* to what the transform actually emits (a value not in the map
    would trip reconcile's coverage guard), and confirms both maps applied together
    produce canonical names/states on real-shaped data — not just synthetic frames.
    """

    def test_transform_then_reconcile_produces_canonical_names(self) -> None:
        transformed = transform_mit(load_mit_president_csv(MIT_FUSION_SAMPLE_CSV))
        out = reconcile_mit(transformed)
        # The fusion sample covers 2000 FL (Gore/Bush) and 2016 NY (Clinton/Trump).
        assert set(out["candidate"]) == {
            "Albert Gore Jr.", "George W. Bush", "Hillary Clinton", "Donald J. Trump",
        }
        assert set(out["state"]) == {"Florida", "New York"}
        # Grain and shape survive the real two-map rewrite.
        assert not out.duplicated(["year", "state", "candidate"]).any()
        assert list(out.columns) == list(SHARED_PV_COLUMNS)
