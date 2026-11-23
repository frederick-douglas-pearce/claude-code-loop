"""Unit tests for :mod:`usvote.mit.transform` — MIT raw CSV -> shared PV shape (#65).

Offline, driven by the self-consistent ``mit_fusion_sample.csv`` fixture (see
``tests._helpers.MIT_FUSION_SAMPLE_CSV``). They lock the D018 shape, the D019
``{DEMOCRAT, REPUBLICAN}`` candidate scope, and — critically — that fusion lines are
aggregated *before* the party filter so a major candidate's ``OTHER``-coded
secondary lines are not silently dropped.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import MIT_FUSION_SAMPLE_CSV
from usvote.mit.read import load_mit_president_csv
from usvote.mit.transform import (
    EC_GETTER_PARTIES,
    RELIABILITY_EXACT,
    SOURCE_MIT,
    MITTransformError,
    assert_totals_reconcile,
    transform_mit,
)
from usvote.pv.schema import SHARED_PV_COLUMNS


@pytest.fixture
def raw() -> pd.DataFrame:
    return load_mit_president_csv(MIT_FUSION_SAMPLE_CSV)


@pytest.fixture
def out(raw: pd.DataFrame) -> pd.DataFrame:
    return transform_mit(raw)


def _row(df: pd.DataFrame, year: int, state: str, candidate: str) -> pd.Series:
    hit = df[(df["year"] == year) & (df["state"] == state) & (df["candidate"] == candidate)]
    assert len(hit) == 1, f"expected exactly one {candidate} row in {year} {state}"
    return hit.iloc[0]


class TestShape:
    def test_columns_are_exactly_the_shared_shape_in_order(self, out: pd.DataFrame) -> None:
        assert list(out.columns) == list(SHARED_PV_COLUMNS)

    def test_provenance_stamped_on_every_row(self, out: pd.DataFrame) -> None:
        assert (out["source"] == SOURCE_MIT).all()
        assert (out["reliability"] == RELIABILITY_EXACT).all()

    def test_vote_columns_are_integer(self, out: pd.DataFrame) -> None:
        assert pd.api.types.is_integer_dtype(out["candidate_votes"])
        assert pd.api.types.is_integer_dtype(out["state_total_votes"])

    def test_state_and_candidate_stay_mit_native(self, out: pd.DataFrame) -> None:
        # Reconciliation onto canonical keys is #67; names are MIT-native here.
        assert _row(out, 2000, "FLORIDA", "GORE, AL")["state"] == "FLORIDA"

    def test_no_redistributable_column(self, out: pd.DataFrame) -> None:
        # redistributable is a per-source pv_source attribute (D017/D018), not a fact column.
        assert "redistributable" not in out.columns


class TestFusionAggregation:
    def test_clinton_fusion_lines_collapse_and_sum(self, out: pd.DataFrame) -> None:
        # 3 NY lines (DEMOCRAT + two OTHER) -> one row summed; party is the plurality line.
        clinton = _row(out, 2016, "NEW YORK", "CLINTON, HILLARY")
        assert clinton["candidate_votes"] == 4379789 + 140041 + 36294
        assert clinton["party"] == "DEMOCRAT"

    def test_trump_fusion_lines_collapse_and_sum(self, out: pd.DataFrame) -> None:
        trump = _row(out, 2016, "NEW YORK", "TRUMP, DONALD J.")
        assert trump["candidate_votes"] == 2814589 + 292392
        assert trump["party"] == "REPUBLICAN"

    def test_one_row_per_candidate_after_aggregation(self, out: pd.DataFrame) -> None:
        ny = out[(out["year"] == 2016) & (out["state"] == "NEW YORK")]
        # Only Clinton + Trump survive the D019 scope, one row each.
        assert sorted(ny["candidate"]) == ["CLINTON, HILLARY", "TRUMP, DONALD J."]

    def test_state_total_preserved_through_aggregation(self, out: pd.DataFrame) -> None:
        clinton = _row(out, 2016, "NEW YORK", "CLINTON, HILLARY")
        assert clinton["state_total_votes"] == 7889703


class TestCandidateScope:
    def test_libertarian_dropped(self, out: pd.DataFrame) -> None:
        assert "JOHNSON, GARY" not in set(out["candidate"])

    def test_other_minor_candidate_dropped(self, out: pd.DataFrame) -> None:
        # Nader 2000 FL is party_simplified=OTHER -> not an EC-getter (D019).
        assert "NADER, RALPH" not in set(out["candidate"])

    def test_unnamed_row_dropped(self, out: pd.DataFrame) -> None:
        # The fixture's write-in row has a NaN candidate (unattributable) -> dropped.
        assert out["candidate"].notna().all()
        assert len(out) == 4  # Bush, Gore (2000 FL) + Clinton, Trump (2016 NY)

    def test_named_writein_major_candidate_is_retained(self, raw: pd.DataFrame) -> None:
        # A named major-party line mis-flagged writein=True (MIT's 2020 DC quirk, where
        # Biden/Trump are both flagged write-in) must NOT be dropped: scoping is by
        # party, not the write-in flag. Flip Clinton's main NY line and assert her full
        # (fusion-summed) total still lands.
        quirked = raw.copy()
        main = (quirked["candidate"] == "CLINTON, HILLARY") & (
            quirked["party_detailed"] == "DEMOCRAT"
        )
        quirked.loc[main, "writein"] = True
        out = transform_mit(quirked)
        clinton = _row(out, 2016, "NEW YORK", "CLINTON, HILLARY")
        assert clinton["candidate_votes"] == 4379789 + 140041 + 36294

    def test_only_dem_and_rep_survive(self, out: pd.DataFrame) -> None:
        assert set(out["party"]) <= EC_GETTER_PARTIES


class TestGrain:
    def test_transformed_frame_has_unique_grain(self, out: pd.DataFrame) -> None:
        assert not out.duplicated(["year", "state", "candidate"]).any()

    def test_2000_and_2016_both_covered(self, out: pd.DataFrame) -> None:
        assert set(out["year"]) == {2000, 2016}


class TestTotalsReconciliation:
    def test_prefilter_reconciliation_passes_on_self_consistent_fixture(
        self, raw: pd.DataFrame
    ) -> None:
        # No exceptions needed — the fixture reconciles exactly.
        transform_mit(raw, totals_exceptions={})

    def test_prefilter_mismatch_raises(self, raw: pd.DataFrame) -> None:
        # Corrupt one candidate's votes so its (year, state) no longer reconciles.
        bad = raw.copy()
        bad.loc[bad["candidate"] == "GORE, AL", "candidatevotes"] = 999999
        with pytest.raises(MITTransformError, match="do not reconcile"):
            transform_mit(bad)

    def test_documented_exception_allows_a_known_discrepancy(self, raw: pd.DataFrame) -> None:
        bad = raw.copy()
        # Introduce a +100 discrepancy in 2000 FL, then whitelist exactly it.
        bad.loc[bad["candidate"] == "GORE, AL", "candidatevotes"] += 100
        transform_mit(bad, totals_exceptions={(2000, "FLORIDA"): 100})

    def test_inconsistent_totalvotes_within_a_state_raises(self, raw: pd.DataFrame) -> None:
        bad = raw.copy()
        bad.loc[bad["candidate"] == "GORE, AL", "totalvotes"] = 1
        with pytest.raises(MITTransformError, match="disagree on totalvotes"):
            transform_mit(bad, totals_exceptions={})

    def test_postfilter_totals_not_exceeded_holds(self, out: pd.DataFrame) -> None:
        grouped = out.groupby(["year", "state"]).agg(
            csum=("candidate_votes", "sum"), total=("state_total_votes", "first")
        )
        assert (grouped["csum"] <= grouped["total"]).all()


class TestTyping:
    def test_non_numeric_votes_raise(self, raw: pd.DataFrame) -> None:
        bad = raw.copy()
        bad["candidatevotes"] = bad["candidatevotes"].astype(object)
        bad.loc[bad["candidate"] == "GORE, AL", "candidatevotes"] = "not-a-number"
        with pytest.raises(MITTransformError, match="non-numeric"):
            transform_mit(bad)

    def test_unnamed_minor_row_is_dropped_not_errored(self, raw: pd.DataFrame) -> None:
        # Turn the fixture's write-in row into a non-write-in unnamed OTHER line —
        # exactly MIT's ~66 real unnamed minor rows. It must be dropped, not raise,
        # and must not change the D/R output (still Bush, Gore, Clinton, Trump).
        bad = raw.copy()
        bad.loc[bad["writein"], "writein"] = False
        out = transform_mit(bad)
        assert len(out) == 4
        assert out["candidate"].notna().all()

    def test_unnamed_ec_getter_row_raises(self, raw: pd.DataFrame) -> None:
        # A *major-party* row with no candidate name is a genuine anomaly (silent
        # undercount risk), so it must fail loud rather than be dropped.
        bad = raw.copy()
        mask = bad["writein"]
        bad.loc[mask, ["writein", "party_simplified"]] = [False, "DEMOCRAT"]
        with pytest.raises(MITTransformError, match="null candidate name"):
            transform_mit(bad)


def test_assert_totals_reconcile_is_directly_callable(raw: pd.DataFrame) -> None:
    # The validation is a real function, callable in isolation (EC transform style).
    typed = raw.copy()
    typed["candidatevotes"] = typed["candidatevotes"].astype("int64")
    typed["totalvotes"] = typed["totalvotes"].astype("int64")
    typed["state"] = typed["state"].astype("string")
    assert_totals_reconcile(typed, {})
