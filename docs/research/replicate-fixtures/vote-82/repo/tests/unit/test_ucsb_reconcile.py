"""Unit tests for :mod:`usvote.ucsb.reconcile` — UCSB names -> canonical keys + D007 (#38).

Offline. Three layers:

- **Crafted units** over the map, the D007 drop set, and each :class:`UCSBReconcileError`
  guard — including the two guards UCSB has that MIT does not: the reciprocal EC-getter
  completeness check and the re-run two-way roster assert.
- **Authority-backed RHS check**: the map's canonical values are validated against the
  committed EC-getter witness (``ec_getters_by_year.json``, National Archives via the real
  EC transform), not a copy of themselves — see ``TestMapAgainstAuthority``.
- The full ``transform_ucsb -> reconcile_ucsb`` seam over the real 60-page corpus lives in
  ``test_ucsb_transform.py::TestRealCorpus`` (skips without ``USVOTE_UCSB_HTML_DIR``).
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import ec_getters_frame
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.status import PV_STATUS_POPULAR_VOTE, ROSTER_COLUMNS
from usvote.ucsb.reconcile import (
    EC_GETTERS_WITHOUT_POPULAR_VOTE,
    UCSB_CANDIDATE_RECONCILIATIONS,
    UCSB_NON_GETTER_COLUMNS,
    UCSBReconcileError,
    reconcile_ucsb,
)

# --- builders ---------------------------------------------------------------


def make_pv(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Build a valid D018 ``SHARED_PV_COLUMNS`` frame from partial rows.

    Each row needs ``year``/``state``/``candidate`` (UCSB-native); the rest default.
    """
    filled = [
        {
            "source": "UCSB",
            "year": r["year"],
            "state": r["state"],
            "candidate": r["candidate"],
            "party": r.get("party", None),
            "candidate_votes": r.get("candidate_votes", 100),
            "state_total_votes": r.get("state_total_votes", 200),
            "reliability": "exact",
        }
        for r in rows
    ]
    frame = pd.DataFrame(filled)[list(SHARED_PV_COLUMNS)]
    frame["year"] = frame["year"].astype("int64")
    for col in ("candidate_votes", "state_total_votes"):
        frame[col] = frame[col].astype("int64")
    return frame


def make_roster(pairs: list[tuple[int, str]]) -> pd.DataFrame:
    """A ``popular_vote`` roster covering each ``(year, state)`` (source=UCSB)."""
    rows = [
        {"source": "UCSB", "year": y, "state": s,
         "pv_status": PV_STATUS_POPULAR_VOTE, "note": None}
        for y, s in pairs
    ]
    frame = pd.DataFrame(rows, columns=list(ROSTER_COLUMNS))
    frame["year"] = frame["year"].astype("int64")
    return frame


def make_getters(pairs: list[tuple[int, str]], ev: int = 5) -> pd.DataFrame:
    """An ``ec_getters`` frame: each ``(year, canonical_name)`` with president EVs."""
    return pd.DataFrame(
        [{"year": y, "candidate": c, "president_electoral_votes": ev} for y, c in pairs]
    )


# --- the map itself ---------------------------------------------------------


class TestCandidateMap:
    @pytest.mark.parametrize(
        ("year", "ucsb", "canonical"),
        [
            (1824, "ADAMS", "John Quincy Adams"),        # surname-only early header
            (1856, "JOHN C. FREMONT", "John C. Frémont"),  # accent restored
            (1948, "STROM THURMOND", "J. Strom Thurmond"),  # "J." prefix added
            (1952, "ADLAI E. STEVENSON", "Adlai Stevenson"),  # middle dropped
            (1940, "WENDELL WILLKIE", "Wendell L. Willkie"),  # middle added
            (1992, "BILL CLINTON", "William J. Clinton"),  # given-name substitution
            (2000, "AL GORE", "Albert Gore Jr."),        # given name + suffix
            (2024, "KAMALA HARRIS", "Kamala D. Harris"),  # most recent year
        ],
    )
    def test_representative_reconciliations(
        self, year: int, ucsb: str, canonical: str
    ) -> None:
        assert UCSB_CANDIDATE_RECONCILIATIONS[(year, ucsb)] == canonical

    def test_keys_are_year_and_native_string(self) -> None:
        for year, name in UCSB_CANDIDATE_RECONCILIATIONS:
            assert isinstance(year, int) and 1824 <= year <= 2024
            assert isinstance(name, str) and name == name.strip() and name

    def test_values_are_unique_within_each_year(self) -> None:
        # Per-YEAR uniqueness (not global like MIT): the same person recurs across years
        # (FDR, the two Roosevelts), so a canonical name may repeat across years — but two
        # keys in ONE year mapping to one name would double-count that year.
        by_year: dict[int, list[str]] = {}
        for (year, _), canonical in UCSB_CANDIDATE_RECONCILIATIONS.items():
            by_year.setdefault(year, []).append(canonical)
        for year, values in by_year.items():
            assert len(values) == len(set(values)), f"duplicate canonical name in {year}"

    def test_recurring_surnames_map_to_distinct_people(self) -> None:
        # The same-name-collision hazard across 49 years (docs/canonical-keys.md).
        assert (
            UCSB_CANDIDATE_RECONCILIATIONS[(1904, "THEODORE ROOSEVELT")]
            != UCSB_CANDIDATE_RECONCILIATIONS[(1932, "FRANKLIN D. ROOSEVELT")]
        )
        assert (
            UCSB_CANDIDATE_RECONCILIATIONS[(1988, "GEORGE BUSH")]
            != UCSB_CANDIDATE_RECONCILIATIONS[(2000, "GEORGE W. BUSH")]
        )
        assert (
            UCSB_CANDIDATE_RECONCILIATIONS[(1824, "ADAMS")]  # John Quincy Adams
            == UCSB_CANDIDATE_RECONCILIATIONS[(1828, "JOHN Q. ADAMS")]
        )

    def test_map_and_set_sizes(self) -> None:
        assert len(UCSB_CANDIDATE_RECONCILIATIONS) == 111
        assert len(UCSB_NON_GETTER_COLUMNS) == 8
        assert len(EC_GETTERS_WITHOUT_POPULAR_VOTE) == 13

    def test_map_and_drops_are_disjoint(self) -> None:
        assert not (set(UCSB_CANDIDATE_RECONCILIATIONS) & UCSB_NON_GETTER_COLUMNS)


class TestMapAgainstAuthority:
    """Validate the map RHS against the independent EC-getter witness (not a self-copy)."""

    def test_every_mapped_value_is_an_ec_getter(self) -> None:
        # Every canonical value the map produces must be an actual EC president-EV getter
        # in that year, per the committed Archives-derived witness. A wrong RHS (e.g. a
        # missing accent or middle initial) fails here because it is not among the getters.
        getters = ec_getters_frame()
        getter_keys = set(zip(getters["year"], getters["candidate"], strict=True))
        for (year, ucsb), canonical in UCSB_CANDIDATE_RECONCILIATIONS.items():
            assert (year, canonical) in getter_keys, (
                f"{year} {ucsb!r} -> {canonical!r} is not an EC getter that year"
            )

    def test_exemptions_are_ec_getters_too(self) -> None:
        # An exemption must itself be a real EC-getter (else it is exempting nothing).
        getters = ec_getters_frame()
        getter_keys = set(zip(getters["year"], getters["candidate"], strict=True))
        assert getter_keys >= EC_GETTERS_WITHOUT_POPULAR_VOTE


# --- reconcile behaviour ----------------------------------------------------


class TestReconcile:
    def test_maps_and_scopes_on_happy_path(self) -> None:
        pv = make_pv([
            {"year": 2000, "state": "Ohio", "candidate": "GEORGE W. BUSH"},
            {"year": 2000, "state": "Ohio", "candidate": "AL GORE"},
            {"year": 2000, "state": "Ohio", "candidate": "RALPH NADER"},  # D007 drop
        ])
        roster = make_roster([(2000, "Ohio")])
        getters = make_getters([(2000, "George W. Bush"), (2000, "Albert Gore Jr.")])
        out = reconcile_ucsb(pv, roster, getters, years={2000})
        assert set(out["candidate"]) == {"George W. Bush", "Albert Gore Jr."}  # Nader gone
        assert list(out.columns) == list(SHARED_PV_COLUMNS)

    def test_non_getter_columns_are_dropped(self) -> None:
        # A state whose only surviving column is the winner still reconciles; the minor
        # column (Perot) is dropped and its votes simply leave the fact.
        pv = make_pv([
            {"year": 1992, "state": "Texas", "candidate": "GEORGE BUSH"},
            {"year": 1992, "state": "Texas", "candidate": "H. ROSS PEROT"},  # drop
        ])
        roster = make_roster([(1992, "Texas")])
        getters = make_getters([(1992, "George Bush")])
        out = reconcile_ucsb(pv, roster, getters, years={1992})
        assert list(out["candidate"]) == ["George Bush"]

    def test_row_count_and_passthrough_columns_preserved(self) -> None:
        pv = make_pv([
            {"year": 2012, "state": "Ohio", "candidate": "BARACK OBAMA",
             "candidate_votes": 111},
            {"year": 2012, "state": "Ohio", "candidate": "MITT ROMNEY",
             "candidate_votes": 222},
        ])
        roster = make_roster([(2012, "Ohio")])
        getters = make_getters([(2012, "Barack Obama"), (2012, "Mitt Romney")])
        out = reconcile_ucsb(pv, roster, getters, years={2012})
        assert len(out) == 2
        assert sorted(out["candidate_votes"]) == [111, 222]


class TestGuards:
    def _ohio_2016(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        pv = make_pv([
            {"year": 2016, "state": "Ohio", "candidate": "DONALD TRUMP"},
            {"year": 2016, "state": "Ohio", "candidate": "HILLARY CLINTON"},
        ])
        roster = make_roster([(2016, "Ohio")])
        getters = make_getters([(2016, "Donald J. Trump"), (2016, "Hillary Clinton")])
        return pv, roster, getters

    def test_unclassified_column_raises(self) -> None:
        # A UCSB column neither mapped nor listed out-of-scope must fail loudly, not be
        # silently dropped and lose its votes.
        pv = make_pv([{"year": 2016, "state": "Ohio", "candidate": "SOME NEW NAME"}])
        roster = make_roster([(2016, "Ohio")])
        getters = make_getters([(2016, "Donald J. Trump")])
        with pytest.raises(UCSBReconcileError, match="no canonical-key reconciliation"):
            reconcile_ucsb(pv, roster, getters, years={2016})

    def test_forgotten_major_raises(self) -> None:
        # Clinton is an EC-getter in ec_getters but her row is absent from the facts
        # (the reciprocal silent-drop the two-way roster assert cannot see: Ohio still has
        # Trump, so the state is non-empty and in-roster).
        pv = make_pv([{"year": 2016, "state": "Ohio", "candidate": "DONALD TRUMP"}])
        roster = make_roster([(2016, "Ohio")])
        getters = make_getters([(2016, "Donald J. Trump"), (2016, "Hillary Clinton")])
        with pytest.raises(UCSBReconcileError, match="no reconciled UCSB popular-vote row"):
            reconcile_ucsb(pv, roster, getters, years={2016})

    def test_exempt_getter_not_required(self) -> None:
        # A faithless-elector getter (2016 Colin Powell, 3 EV) has no UCSB column by design;
        # the completeness guard must not demand one.
        pv, roster, getters = self._ohio_2016()
        getters = pd.concat(
            [getters, make_getters([(2016, "Colin Powell")], ev=3)], ignore_index=True
        )
        out = reconcile_ucsb(pv, roster, getters, years={2016})
        assert "Colin Powell" not in set(out["candidate"])  # not fabricated either

    def test_stale_exemption_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # If an exemption entry actually appears in the facts, it held a popular vote and
        # must not be exempt.
        monkeypatch.setattr(
            "usvote.ucsb.reconcile.EC_GETTERS_WITHOUT_POPULAR_VOTE",
            frozenset({(2016, "Hillary Clinton")}),
        )
        pv, roster, getters = self._ohio_2016()
        with pytest.raises(UCSBReconcileError, match="exemption"):
            reconcile_ucsb(pv, roster, getters, years={2016})

    def test_ec_getters_missing_column_raises(self) -> None:
        pv, roster, _ = self._ohio_2016()
        bad = pd.DataFrame([{"year": 2016, "candidate": "Donald J. Trump"}])  # no EV col
        with pytest.raises(UCSBReconcileError, match="missing column"):
            reconcile_ucsb(pv, roster, bad, years={2016})

    def test_grain_collapse_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two UCSB columns in one (year, state) mapping to the SAME canonical name would
        # double-count — must raise on the re-run grain check.
        patched = {
            **UCSB_CANDIDATE_RECONCILIATIONS,
            (2016, "DONALD J TRUMP ALT"): "Donald J. Trump",
        }
        monkeypatch.setattr(
            "usvote.ucsb.reconcile.UCSB_CANDIDATE_RECONCILIATIONS", patched
        )
        pv = make_pv([
            {"year": 2016, "state": "Ohio", "candidate": "DONALD TRUMP"},
            {"year": 2016, "state": "Ohio", "candidate": "DONALD J TRUMP ALT"},
        ])
        roster = make_roster([(2016, "Ohio")])
        getters = make_getters([(2016, "Donald J. Trump")])
        with pytest.raises(UCSBReconcileError, match="grain violated"):
            reconcile_ucsb(pv, roster, getters, years={2016})

    def test_scoping_that_empties_a_popular_vote_state_raises(self) -> None:
        # If a state's ONLY column is a D007 drop, scoping empties it while the roster still
        # marks it popular_vote. Completeness passes (both getters survive in Ohio), so the
        # two-way roster assert is what must catch the resulting zero-fact Wyoming.
        pv = make_pv([
            {"year": 2000, "state": "Ohio", "candidate": "GEORGE W. BUSH"},
            {"year": 2000, "state": "Ohio", "candidate": "AL GORE"},
            {"year": 2000, "state": "Wyoming", "candidate": "RALPH NADER"},  # only minor
        ])
        roster = make_roster([(2000, "Ohio"), (2000, "Wyoming")])
        getters = make_getters([(2000, "George W. Bush"), (2000, "Albert Gore Jr.")])
        with pytest.raises(UCSBReconcileError, match="no vote rows"):
            reconcile_ucsb(pv, roster, getters, years={2000})

    def test_empty_or_wrong_year_ec_getters_raises_not_vacuous(self) -> None:
        # The completeness guard must not pass vacuously when ec_getters has no rows for
        # an in-scope year (e.g. #37's query returned nothing, or year came back as str
        # so .isin of ints matched nothing) — that would silently disable it.
        pv, roster, _ = self._ohio_2016()
        wrong_year = make_getters([(2020, "Donald J. Trump")])  # nothing for 2016
        with pytest.raises(UCSBReconcileError, match="no president-EV getter"):
            reconcile_ucsb(pv, roster, wrong_year, years={2016})

    def test_zero_ev_getter_is_not_required(self) -> None:
        # The `president_electoral_votes > 0` filter: a 0-EV row is not a getter, so the
        # completeness guard must not demand a popular-vote row for it.
        pv, roster, getters = self._ohio_2016()
        getters = pd.concat(
            [getters, make_getters([(2016, "Not A Getter")], ev=0)], ignore_index=True
        )
        out = reconcile_ucsb(pv, roster, getters, years={2016})
        assert "Not A Getter" not in set(out["candidate"])

    def test_out_of_scope_year_rows_are_scoped_out_not_leaked(self) -> None:
        # A pv_votes row for a year outside `years` must not leak into the output (nor
        # bypass the coverage guard by being dropped unchecked): reconcile scopes first.
        pv = make_pv([
            {"year": 2016, "state": "Ohio", "candidate": "DONALD TRUMP"},
            {"year": 2016, "state": "Ohio", "candidate": "HILLARY CLINTON"},
            {"year": 2020, "state": "Ohio", "candidate": "DONALD TRUMP"},  # out of scope
        ])
        roster = make_roster([(2016, "Ohio")])
        getters = make_getters([(2016, "Donald J. Trump"), (2016, "Hillary Clinton")])
        out = reconcile_ucsb(pv, roster, getters, years={2016})
        assert set(out["year"]) == {2016}
        assert len(out) == 2
