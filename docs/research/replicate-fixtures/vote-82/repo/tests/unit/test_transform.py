"""Unit tests for ``usvote.transform`` (all offline).

Two coverage layers, mirroring ``test_parse``:

- **Crafted units** over the pure pieces — name parsing, the candidate/party
  aggregation into ``_2`` columns, the historical name reconciliations, and each
  raising validator. These carry the cases the fixture slice cannot: ``party_2``
  (Bryan D-P, T. Roosevelt R-P are pre-1920) and the Bob Dole / McGovern
  reconciliations have **zero** fixture coverage, so they are exercised here.
- **One full-transform fixture-replay test** (offline — this is *not* a live-DB
  ``@pytest.mark.integration`` test; those live in ``tests/integration/``)
  replaying the 2016 + 2020 Archives fixtures through the full
  ``transform_parsed_years`` with an injected fake state-geo frame (no TIGER
  shapefile). It exercises the 2016 "Other" expansion, the Trump multi-state +
  name reconciliation, Biden's ``Jr.`` suffix, ``is_total`` shaping and the
  per-year electoral rank.

Note on scope: ``assert_unique_grain`` ("unique candidate names across ALL years")
is only *meaningful* at full-dataset scale — a 2-year slice can pass it while the
full set fails. #26 claims validator *correctness* (the unit tests below) plus
slice-level end-to-end coverage; running the validators against the whole 1789-2020 corpus
is deferred to the pipeline run (#28) / a dedicated data-validation story.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from bs4.element import Tag

from tests._helpers import FIXTURES_DIR, STATE_NAMES, fake_state_geo
from usvote import transform as T
from usvote.parse import ParsedYear, parse_election_years
from usvote.scrape import fetch_from_dir, get_html_tables
from usvote.transform import (
    TransformError,
    apply_other_candidates,
    build_candidate_dim,
    build_state_dim,
    get_name_middle_last,
    normalize_candidate_parties,
    normalize_candidate_states,
    split_name,
    strip_footnote_markers_column,
    strip_name_footnote_markers,
    transform_parsed_years,
)

# --- name-part parsing -----------------------------------------------------


def test_split_name_jr_suffix() -> None:
    assert split_name("Joseph R. Biden Jr.") == {
        "name_first": "Joseph",
        "name_middle": "R.",
        "name_last": "Biden",
        "name_suffix": "Jr.",
    }


def test_split_name_middle_initial() -> None:
    assert split_name("Donald J. Trump") == {
        "name_first": "Donald",
        "name_middle": "J.",
        "name_last": "Trump",
        "name_suffix": None,
    }


def test_split_name_no_middle() -> None:
    assert split_name("Hillary Clinton") == {
        "name_first": "Hillary",
        "name_middle": None,
        "name_last": "Clinton",
        "name_suffix": None,
    }


def test_split_name_two_word_last_is_mis_split() -> None:
    # The generic parser mis-splits "Faith Spotted Eagle" (middle="Spotted"); the
    # dedicated correction in build_candidate_dim fixes it — asserted below.
    assert split_name("Faith Spotted Eagle") == {
        "name_first": "Faith",
        "name_middle": "Spotted",
        "name_last": "Eagle",
        "name_suffix": None,
    }


def test_get_name_middle_last_variants() -> None:
    assert get_name_middle_last("Clinton") == (None, "Clinton")
    assert get_name_middle_last("R. Biden") == ("R.", "Biden")
    assert get_name_middle_last("S. Grant Jr") == ("S.", "Grant Jr")
    assert get_name_middle_last(None) == (None, None)
    assert get_name_middle_last("") == (None, None)


# --- candidate dimension: crafted (party_2 + reconciliations) ---------------


def _t2_states(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """A Table-2 candidate-state frame (post-normalize shape)."""
    return pd.DataFrame(rows)


def _t1(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """A Table-1 candidate-party frame (post-normalize shape)."""
    columns = ["president_candidate_name", "president_candidate_party", "year"]
    return pd.DataFrame(rows, columns=columns)


def test_multi_party_aggregates_into_party_2() -> None:
    # Bryan (D then P) and T. Roosevelt (R then P) are THE canonical multi-party
    # cases (CLAUDE.md) and have no fixture coverage — they are pre-1920.
    t2 = _t2_states([
        {"president_candidate_name": "William J. Bryan", "col_ind": 1,
         "president_candidate_state": "Nebraska", "year": 1900},
        {"president_candidate_name": "Theodore Roosevelt", "col_ind": 1,
         "president_candidate_state": "New York", "year": 1904},
    ])
    t1 = _t1([
        {"president_candidate_name": "William J. Bryan", "president_candidate_party": "D", "year": 1900},
        {"president_candidate_name": "William J. Bryan", "president_candidate_party": "P", "year": 1900},
        {"president_candidate_name": "Theodore Roosevelt", "president_candidate_party": "R", "year": 1904},
        {"president_candidate_name": "Theodore Roosevelt", "president_candidate_party": "P", "year": 1912},
    ])
    candidates = build_candidate_dim(t2, t1).set_index("name")
    assert (candidates.loc["William J. Bryan", "party"],
            candidates.loc["William J. Bryan", "party_2"]) == ("D", "P")
    assert (candidates.loc["Theodore Roosevelt", "party"],
            candidates.loc["Theodore Roosevelt", "party_2"]) == ("R", "P")


def test_single_party_has_null_party_2() -> None:
    t2 = _t2_states([
        {"president_candidate_name": "Hillary Clinton", "col_ind": 1,
         "president_candidate_state": "New York", "year": 2016},
    ])
    t1 = _t1([
        {"president_candidate_name": "Hillary Clinton", "president_candidate_party": "D", "year": 2016},
    ])
    row = build_candidate_dim(t2, t1).iloc[0]
    assert row["party"] == "D"
    assert row["party_2"] is None


def test_hyphenated_party_label_not_mis_split_and_normalized() -> None:
    # The Archives prints the Democratic-Republican party as "Democratic-Republican"
    # (Jackson 1824) and "D-R" (Adams 1824) — one party, two labels. Normalizing both
    # to "D-R" makes them read identically, and the non-"-" join delimiter keeps the
    # hyphenated code from mis-splitting into a spurious party_2.
    t2 = _t2_states([
        {"president_candidate_name": "Andrew Jackson", "col_ind": 1,
         "president_candidate_state": "Tennessee", "year": 1824},
        {"president_candidate_name": "John Quincy Adams", "col_ind": 2,
         "president_candidate_state": "Massachusetts", "year": 1824},
    ])
    t1 = _t1([
        {"president_candidate_name": "Andrew Jackson",
         "president_candidate_party": "Democratic-Republican", "year": 1824},
        {"president_candidate_name": "John Quincy Adams",
         "president_candidate_party": "D-R", "year": 1824},
    ])
    candidates = build_candidate_dim(t2, t1).set_index("name")
    for name in ("Andrew Jackson", "John Quincy Adams"):
        assert candidates.loc[name, "party"] == "D-R"
        assert candidates.loc[name, "party_2"] is None


def test_party_2_keeps_full_multi_word_label() -> None:
    # Henry Clay ran National Republican (1832) then Whig (1844). party_2 (a varchar)
    # must keep the full "Whig", not truncate to a meaningless single char "W".
    t2 = _t2_states([
        {"president_candidate_name": "Henry Clay", "col_ind": 1,
         "president_candidate_state": "Kentucky", "year": 1832},
    ])
    t1 = _t1([
        {"president_candidate_name": "Henry Clay",
         "president_candidate_party": "National Republican", "year": 1832},
        {"president_candidate_name": "Henry Clay",
         "president_candidate_party": "Whig", "year": 1844},
    ])
    row = build_candidate_dim(t2, t1).iloc[0]
    assert (row["party"], row["party_2"]) == ("National Republican", "Whig")


def test_cross_year_party_change_populates_party_2_after_normalization() -> None:
    # Jackson runs Democratic-Republican (1824) then Democrat (1832) — a genuine
    # cross-year party change, so party/party_2 = D-R/D, not a hyphen mis-split.
    t2 = _t2_states([
        {"president_candidate_name": "Andrew Jackson", "col_ind": 1,
         "president_candidate_state": "Tennessee", "year": 1824},
    ])
    t1 = _t1([
        {"president_candidate_name": "Andrew Jackson",
         "president_candidate_party": "Democratic-Republican", "year": 1824},
        {"president_candidate_name": "Andrew Jackson",
         "president_candidate_party": "D", "year": 1832},
    ])
    row = build_candidate_dim(t2, t1).iloc[0]
    assert (row["party"], row["party_2"]) == ("D-R", "D")


def test_bob_dole_name_reconciled_to_table_2() -> None:
    # Table 1 prints "Bob Dole"; Table 2 (and the canonical key) is "Robert Dole".
    t2 = _t2_states([
        {"president_candidate_name": "Robert Dole", "col_ind": 1,
         "president_candidate_state": "Kansas", "year": 1996},
    ])
    t1 = _t1([
        {"president_candidate_name": "Bob Dole", "president_candidate_party": "R", "year": 1996},
    ])
    candidates = build_candidate_dim(t2, t1)
    assert candidates["name"].tolist() == ["Robert Dole"]
    assert candidates.iloc[0]["party"] == "R"


def test_mcgovern_name_reconciled_to_table_1() -> None:
    # Table 2 prints "George McGovern"; Table 1 has the middle initial. The fix
    # rewrites the Table-2 name AND fills the middle initial before aggregation.
    t2 = _t2_states([
        {"president_candidate_name": "George McGovern", "col_ind": 1,
         "president_candidate_state": "South Dakota", "year": 1972},
    ])
    t1 = _t1([
        {"president_candidate_name": "George S. McGovern", "president_candidate_party": "D", "year": 1972},
    ])
    row = build_candidate_dim(t2, t1).iloc[0]
    assert row["name"] == "George S. McGovern"
    assert row["name_middle"] == "S."
    assert row["party"] == "D"


def test_multi_state_aggregates_into_state_2() -> None:
    # A candidate appearing under two home states collapses to one row with a
    # primary state + state_2 (first-appearance order preserved).
    t2 = _t2_states([
        {"president_candidate_name": "Andrew Jackson", "col_ind": 1,
         "president_candidate_state": "Tennessee", "year": 1828},
        {"president_candidate_name": "Andrew Jackson", "col_ind": 1,
         "president_candidate_state": "Louisiana", "year": 1832},
    ])
    t1 = _t1([
        {"president_candidate_name": "Andrew Jackson", "president_candidate_party": "D", "year": 1828},
    ])
    candidates = build_candidate_dim(t2, t1)
    assert len(candidates) == 1
    row = candidates.iloc[0]
    assert (row["state"], row["state_2"]) == ("Tennessee", "Louisiana")


def test_spotted_eagle_surname_corrected() -> None:
    t2 = _t2_states([
        {"president_candidate_name": "Faith Spotted Eagle", "col_ind": 1,
         "president_candidate_state": "South Dakota", "year": 2016},
    ])
    t1 = _t1([])  # no Table-1 party row for a faithless-only candidate
    row = build_candidate_dim(t2, t1).iloc[0]
    assert pd.isna(row["name_middle"])  # mis-split middle cleared (NA -> NULL at load)
    assert row["name_last"] == "Spotted Eagle"


def test_strip_name_footnote_markers() -> None:
    # Trailing "*" (with or without a leading space) is stripped; clean names untouched.
    assert strip_name_footnote_markers("Franklin D. Roosevelt*") == "Franklin D. Roosevelt"
    assert strip_name_footnote_markers("Franklin D. Roosevelt *") == "Franklin D. Roosevelt"
    assert strip_name_footnote_markers("Franklin D. Roosevelt") == "Franklin D. Roosevelt"
    assert strip_name_footnote_markers("Harry S. Truman") == "Harry S. Truman"


def test_strip_footnote_markers_column_is_null_safe_and_total() -> None:
    # The frame-level strip must pass a NaN name through unchanged (not TypeError) and
    # no-op when the frame is empty and the column is absent (not KeyError).
    df = pd.DataFrame({"president_candidate_name": ["Franklin D. Roosevelt*", None]})
    out = strip_footnote_markers_column(df)["president_candidate_name"]
    assert out.iloc[0] == "Franklin D. Roosevelt"
    assert pd.isna(out.iloc[1])  # null passes through, not a TypeError
    empty = pd.DataFrame()  # no such column
    assert strip_footnote_markers_column(empty).empty


def _parsed_year(year: int, t2_name: str, t1_name: str) -> dict[str, Any]:
    return {
        "year": year,
        "t1": [
            {"president_candidate_name": t1_name, "president_candidate_party": "D"},
        ],
        "t2": {
            "candidate_state": [
                {
                    "president_candidate_name": t2_name,
                    "col_ind": 1,
                    "president_candidate_state": "New York",
                }
            ]
        },
    }


def test_fdr_1944_asterisk_merges_into_single_candidate() -> None:
    # Table 2 prints "Franklin D. Roosevelt*" in 1944 (a footnote marker) but the
    # unmarked name in 1940. Left in, the "*" would give FDR a second, party-less
    # candidate row keyed "...Roosevelt*"; the normalize-time strip collapses both
    # years onto the one canonical "Franklin D. Roosevelt" with its Table-1 party.
    parsed = [
        _parsed_year(1940, "Franklin D. Roosevelt", "Franklin D. Roosevelt"),
        _parsed_year(1944, "Franklin D. Roosevelt*", "Franklin D. Roosevelt"),
    ]
    t2 = normalize_candidate_states(parsed)
    t1 = normalize_candidate_parties(parsed)
    assert "Franklin D. Roosevelt*" not in set(t2["president_candidate_name"])
    candidates = build_candidate_dim(t2, t1)
    fdr = candidates[candidates["name"].str.startswith("Franklin")]
    assert fdr["name"].tolist() == ["Franklin D. Roosevelt"]  # one row, no "*" twin
    assert fdr.iloc[0]["party"] == "D"


def test_candidate_id_is_one_based_and_missing_values_are_na() -> None:
    t2 = _t2_states([
        {"president_candidate_name": "Colin Powell", "col_ind": 1,
         "president_candidate_state": None, "year": 2016},
    ])
    row = build_candidate_dim(t2, _t1([])).iloc[0]
    assert row["candidate_id"] == 1
    # No Table-1 party and no home state -> pandas NA; usvote.db.insert_df_into_table
    # maps NA to SQL NULL at the write boundary.
    assert pd.isna(row["state"])
    assert pd.isna(row["party"])


# --- canonical keys: the cross-source reconciliation spine (D006 / #30) -----


def test_canonical_keys_are_the_documented_columns() -> None:
    # #30 freezes the canonical keys as data; lock the constants against the dims
    # so a rename can't silently break the spine the PV sources reconcile onto.
    candidates = build_candidate_dim(
        _t2_states([{"president_candidate_name": "Robert Dole", "col_ind": 1,
                     "president_candidate_state": "Kansas", "year": 1996}]),
        _t1([]),
    )
    state_df = build_state_dim(fake_state_geo())
    # Lock the exact key identity, not just membership — the canonical candidate key
    # must be the reconciled name (never the candidate_id surrogate the module
    # forbids) and the state key the full state name.
    assert T.CANDIDATE_KEY == "name"
    assert T.STATE_KEY == "state"
    assert T.CANDIDATE_MATCH_COLUMNS == ("name_first", "name_middle", "name_last", "name_suffix")
    assert T.STATE_MATCH_COLUMN == "state_usps"
    # ...and each names a real column on the dimension it keys.
    assert T.CANDIDATE_KEY in candidates.columns
    assert T.STATE_KEY in state_df.columns
    assert set(T.CANDIDATE_MATCH_COLUMNS) <= set(candidates.columns)
    assert T.STATE_MATCH_COLUMN in state_df.columns


def test_candidate_key_is_stable_but_candidate_id_is_not() -> None:
    # The canonical candidate key is the reconciled name — invariant to input row
    # order, which is what the future join relies on. candidate_id is a row-order
    # surrogate (D006 / #30) and is deliberately NOT stable: it must never be the
    # reconciliation key.
    rows = [
        {"president_candidate_name": "John Adams", "col_ind": 1,
         "president_candidate_state": "Massachusetts", "year": 1796},
        {"president_candidate_name": "Thomas Jefferson", "col_ind": 1,
         "president_candidate_state": "Virginia", "year": 1796},
    ]
    forward = build_candidate_dim(_t2_states(rows), _t1([]))
    reverse = build_candidate_dim(_t2_states(list(reversed(rows))), _t1([]))
    assert set(forward["name"]) == set(reverse["name"])  # the spine is invariant
    # candidate_id, by contrast, tracks first-appearance order and flips.
    assert dict(zip(forward["candidate_id"], forward["name"], strict=True)) != dict(
        zip(reverse["candidate_id"], reverse["name"], strict=True)
    )


def test_state_key_is_unique_and_stable_under_input_order() -> None:
    geo = fake_state_geo()
    forward = build_state_dim(geo)
    shuffled = build_state_dim(geo.iloc[::-1].reset_index(drop=True))
    T.assert_unique_grain(forward, "state", "state")  # one row per state
    assert list(forward["state"]) == list(shuffled["state"])  # order-independent
    assert set(forward["state"]) == STATE_NAMES  # 50 states + DC, territories dropped


def test_more_than_two_home_states_fails_loud() -> None:
    # Three distinct home states is unrepresentable in the state/state_2 model and
    # is the same-name-collision tripwire — it must raise, not silently drop the
    # third state in the split.
    t2 = _t2_states([
        {"president_candidate_name": "Ambiguous Name", "col_ind": 1,
         "president_candidate_state": state, "year": year}
        for state, year in (("Ohio", 1900), ("Texas", 1904), ("Iowa", 1908))
    ])
    with pytest.raises(TransformError, match="more than 2 home states"):
        build_candidate_dim(t2, _t1([]))


def test_null_home_state_does_not_occupy_primary_slot() -> None:
    # A candidate whose first-appearing row has no home state must not be demoted to
    # a NULL primary with the real state pushed into state_2 (#30 review): nulls are
    # dropped before the primary/secondary split.
    t2 = _t2_states([
        {"president_candidate_name": "John Roe", "col_ind": 1,
         "president_candidate_state": None, "year": 1900},
        {"president_candidate_name": "John Roe", "col_ind": 1,
         "president_candidate_state": "Ohio", "year": 1904},
    ])
    row = build_candidate_dim(t2, _t1([])).iloc[0]
    assert row["state"] == "Ohio"
    assert row["state_2"] is None


def test_duplicate_home_state_does_not_mangle_state_2() -> None:
    # Two raw spellings that reconcile to one canonical name in the SAME state must
    # collapse to a single home state, not a "New York-New York" composite (#30
    # review). drop_duplicates upstream keys on the RAW name, so both rows survive
    # into one group once CANDIDATE_NAME_FIXES rewrites the name.
    t2 = _t2_states([
        {"president_candidate_name": "Donald Trump", "col_ind": 1,
         "president_candidate_state": "New York", "year": 2016},
        {"president_candidate_name": "Donald J. Trump", "col_ind": 1,
         "president_candidate_state": "New York", "year": 2020},
    ])
    row = build_candidate_dim(t2, _t1([])).iloc[0]
    assert row["state"] == "New York"
    assert row["state_2"] is None


# --- validators: pass + raise ----------------------------------------------


def test_assert_unique_grain_raises_on_duplicate() -> None:
    df = pd.DataFrame({"name": ["A", "A", "B"]})
    with pytest.raises(TransformError, match="grain broken"):
        T.assert_unique_grain(df, "name", "candidate")


def test_assert_names_reconciled_raises_on_unmatched() -> None:
    with pytest.raises(TransformError, match="Bob Dole"):
        T.assert_names_reconciled({"Bob Dole"}, {"Robert Dole"}, "names differ")


def test_assert_names_reconciled_passes_when_subset() -> None:
    T.assert_names_reconciled({"Robert Dole"}, {"Robert Dole", "Bill Clinton"}, "ok")


def test_build_candidate_dim_raises_when_party_name_unreconciled() -> None:
    # A Table-1 name with no Table-2 counterpart trips the reconciliation check.
    t2 = _t2_states([
        {"president_candidate_name": "Robert Dole", "col_ind": 1,
         "president_candidate_state": "Kansas", "year": 1996},
    ])
    t1 = _t1([
        {"president_candidate_name": "Unknown Person", "president_candidate_party": "X", "year": 1996},
    ])
    with pytest.raises(TransformError, match="not all present"):
        build_candidate_dim(t2, t1)


def test_assert_count_equals_raises_on_mismatch() -> None:
    with pytest.raises(TransformError, match="expected 3, got 2"):
        T.assert_count_equals(2, 3, "candidate count")


def test_assert_row_votes_sum_to_total_raises() -> None:
    # An *undocumented* shortfall (Ohio 2004: 10 + 7 = 17 != 18) is a scrape error.
    matrix = pd.DataFrame({
        "state": ["Ohio"], "total_electoral_votes": [18], "year": [2004], 1: [10], 2: [7],
    })
    with pytest.raises(TransformError, match="do not sum"):
        T.assert_row_votes_sum_to_total(matrix, [1, 2])


def test_assert_row_votes_sum_to_total_allows_2000_dc_abstention() -> None:
    # The 2000 DC abstention (cast 2 of 3) and the Totals row that inherits its
    # 1-vote shortfall are documented in ELECTORAL_VOTE_SHORTFALLS and must NOT raise.
    matrix = pd.DataFrame({
        "state": ["District of Columbia", "Totals"],
        "total_electoral_votes": [3, 3],
        "year": [2000, 2000],
        1: [0, 0],  # Bush
        2: [2, 2],  # Gore (DC cast 2; the year's only counted votes here)
    })
    T.assert_row_votes_sum_to_total(matrix, [1, 2])  # does not raise


def test_assert_row_votes_sum_to_total_allows_1832_maryland_undervote() -> None:
    # 1832 Maryland: 10 allotted, two electors did not vote (cast 8). The documented
    # shortfall lets the row-sum pass; the Totals row inherits the same 2-vote gap.
    matrix = pd.DataFrame({
        "state": ["Maryland", "Totals"],
        "total_electoral_votes": [10, 288],
        "year": [1832, 1832],
        1: [3, 219],  # Jackson
        2: [5, 49],   # Clay (Maryland cast 3 + 5 = 8 of 10)
        3: [0, 18],   # Others (Floyd + Wirt)
    })
    T.assert_row_votes_sum_to_total(matrix, [1, 2, 3])  # does not raise


def test_assert_row_votes_sum_to_total_shortfall_is_year_scoped() -> None:
    # The documented (2000, DC) shortfall must not excuse the SAME 3-vs-2 gap in a
    # different year — that would still be an unexplained scrape error.
    matrix = pd.DataFrame({
        "state": ["District of Columbia"], "total_electoral_votes": [3],
        "year": [2004], 1: [0], 2: [2],
    })
    with pytest.raises(TransformError, match="do not sum"):
        T.assert_row_votes_sum_to_total(matrix, [1, 2])


def test_assert_totals_equal_state_sum_raises() -> None:
    votes = pd.DataFrame({
        "year": [2004, 2004, 2004],
        "state": ["Ohio", "Texas", None],  # None row is the scraped total
        "candidate_id": [1, 1, 1],
        "president_electoral_votes": [10, 5, 99],  # 99 != 10 + 5
    })
    with pytest.raises(TransformError, match="!= sum across states"):
        T.assert_totals_equal_state_sum(votes)


def test_assert_rectangular_state_grain_passes_on_dense_fact() -> None:
    # Two states x two candidates = 4 rows, every (state, candidate) present incl. a 0-EV
    # loser — the dense shape the real fact always has (D026). is_total rows are ignored.
    votes = pd.DataFrame({
        "year": [2020, 2020, 2020, 2020, 2020],
        "state": ["Ohio", "Ohio", "Texas", "Texas", None],
        "candidate_id": [1, 2, 1, 2, 1],
        "president_electoral_votes": [18, 0, 0, 40, 18],  # 0-EV losers present
    })
    T.assert_rectangular_state_grain(votes)  # does not raise


def test_assert_rectangular_state_grain_raises_on_a_missing_loser_row() -> None:
    # Ohio has both candidates but Texas has only the winner — a getter's 0-EV row was
    # dropped, breaking the dense-fact invariant the EC-left join relies on.
    votes = pd.DataFrame({
        "year": [2020, 2020, 2020],
        "state": ["Ohio", "Ohio", "Texas"],
        "candidate_id": [1, 2, 2],
        "president_electoral_votes": [18, 0, 40],
    })
    with pytest.raises(TransformError, match="not rectangular"):
        T.assert_rectangular_state_grain(votes)


def test_assert_rectangular_state_grain_catches_a_duplicate_masking_a_drop() -> None:
    # The blind spot a pure count check would miss: Ohio duplicates candidate 1 and Texas
    # drops it, so rows (4) == states (2) x getters (2) — yet Texas/candidate-1 is absent.
    # The duplicate-grain check must catch it before the count test passes vacuously.
    votes = pd.DataFrame({
        "year": [2020, 2020, 2020, 2020],
        "state": ["Ohio", "Ohio", "Ohio", "Texas"],
        "candidate_id": [1, 1, 2, 2],  # Ohio/1 duplicated; Texas/1 missing
        "president_electoral_votes": [18, 18, 0, 40],
    })
    with pytest.raises(TransformError, match="duplicate"):
        T.assert_rectangular_state_grain(votes)


def test_build_votes_fact_raises_on_a_ragged_non_rectangular_year() -> None:
    # Drive a ragged parsed year (Texas lists only the winner, so the loser's 0-EV row is
    # never created) through the FULL transform, proving assert_rectangular_state_grain is
    # actually wired into build_votes_fact — not merely unit-tested in isolation.
    ragged = {
        "year": 2012,
        "t1": [
            {"president_candidate_name": "Alice Winner", "president_candidate_party": "D"},
            {"president_candidate_name": "Bob Loser", "president_candidate_party": "R"},
        ],
        "t2": {
            "candidate_state": [
                {"president_candidate_name": "Alice Winner", "col_ind": 1,
                 "president_candidate_state": "Ohio"},
                {"president_candidate_name": "Bob Loser", "col_ind": 2,
                 "president_candidate_state": "Texas"},
            ],
            "votes_by_state": [
                {"state": "Ohio", "total_electoral_votes": 5, 1: 3, 2: 2},
                {"state": "Texas", "total_electoral_votes": 5, 1: 5},  # no candidate 2 cell
                {"state": "Totals", "total_electoral_votes": 10, 1: 8, 2: 2},
            ],
        },
    }
    with pytest.raises(TransformError, match="not rectangular"):
        transform_parsed_years([ragged], fake_state_geo())


def test_assert_state_count_by_year_raises_on_dropped_state() -> None:
    # Parsed says 2 states (Ohio + Totals); votes has only Ohio -> a row was lost.
    parsed = [{"year": 2020, "t2": {"votes_by_state": [{"state": "Ohio"}, {"state": "Totals"}]}}]
    votes = pd.DataFrame(
        {"year": [2020], "state": ["Ohio"], "president_electoral_rank": [1]}
    )
    with pytest.raises(TransformError, match="Per-year state count"):
        T.assert_state_count_by_year(parsed, votes)


def test_apply_other_candidates_raises_on_unregistered_placeholder() -> None:
    # An unnamed "Other" column in a year with no registered correction must raise.
    t2 = _t2_states([
        {"president_candidate_name": "Other", "col_ind": 2,
         "president_candidate_state": None, "year": 2004},
    ])
    with pytest.raises(TransformError, match="no registered correction"):
        apply_other_candidates(t2)


# --- state dimension -------------------------------------------------------


def test_build_state_dim_drops_territories_and_orders_columns() -> None:
    state_df = build_state_dim(fake_state_geo())
    assert len(state_df) == 51
    assert "Puerto Rico" not in state_df["state"].tolist()
    assert list(state_df.columns) == list(T.STATE_COLUMN_ORDER)
    # REGION/DIVISION arrive as strings and must be coerced to int.
    assert state_df["region"].dtype == "int64"
    assert state_df["latitude"].dtype == "float64"


# --- 2000 DC abstainer: full-transform integration -------------------------

# A crafted mini-2000 driven through the whole transform (cheaper + more targeted
# than a real 2000 Archives fixture, which would drag in every 2000 candidate/state).
# Bush wins Texas 3-0; DC's 3rd elector abstained so DC casts only 2 (Gore 2, Bush 0);
# the national Totals inherit that 1-vote shortfall (6 allotted, 5 cast).
_SYNTHETIC_2000: dict[str, Any] = {
    "year": 2000,
    "t1": [
        {"president_candidate_name": "George W. Bush", "president_candidate_party": "R"},
        {"president_candidate_name": "Al Gore", "president_candidate_party": "D"},
    ],
    "t2": {
        "candidate_state": [
            {"president_candidate_name": "George W. Bush", "col_ind": 1,
             "president_candidate_state": "Texas"},
            {"president_candidate_name": "Al Gore", "col_ind": 2,
             "president_candidate_state": "Tennessee"},
        ],
        "votes_by_state": [
            {"state": "Texas", "total_electoral_votes": 3, 1: 3, 2: 0},
            {"state": "District of Columbia", "total_electoral_votes": 3, 1: 0, 2: 2},
            {"state": "Totals", "total_electoral_votes": 6, 1: 3, 2: 2},
        ],
    },
}


def test_2000_dc_abstention_survives_transform() -> None:
    # The confirmed abstention must flow through transform_parsed_years without
    # tripping assert_row_votes_sum_to_total, preserving the allotment/cast gap.
    candidates, _, votes = transform_parsed_years([_SYNTHETIC_2000], fake_state_geo())
    ids = candidates.set_index("name")["candidate_id"]

    dc = votes[(votes["state"] == "District of Columbia")].set_index("candidate_id")
    # DC keeps its 3-vote allotment, but only 2 were cast (Gore 2, Bush 0).
    assert (dc["total_electoral_votes"] == 3).all()
    assert dc.loc[ids["Al Gore"], "president_electoral_votes"] == 2
    assert dc.loc[ids["George W. Bush"], "president_electoral_votes"] == 0

    # The national totals row: Gore's cast total is 2 (the DC abstention is not
    # counted for anyone), against a 6-vote allotment that still records the gap.
    totals = votes[votes["is_total"]].set_index("candidate_id")
    assert totals.loc[ids["Al Gore"], "president_electoral_votes"] == 2
    assert totals.loc[ids["George W. Bush"], "president_electoral_votes"] == 3
    assert (totals["total_electoral_votes"] == 6).all()


# --- 1824 contingent election: office-holder vs. EC winner (#29) -----------

# A crafted mini-1824 driven through the whole transform (same targeted approach as
# the 2000 case above). 1824 is the one contingent election inside the loaded EC
# coverage (post-1804 spine, #32): no candidate reached an EC majority, Jackson led
# the Electoral College but the House elected John Quincy Adams, who took office. The
# per-state splits are illustrative (Jackson's home Tennessee outweighs Adams's
# Massachusetts, so Jackson is EC rank 1); the fact under test is the took_office vs.
# president_electoral_rank distinction, not the real 1824 counts.
_SYNTHETIC_1824: dict[str, Any] = {
    "year": 1824,
    "t1": [
        {"president_candidate_name": "Andrew Jackson",
         "president_candidate_party": "Democratic-Republican"},
        {"president_candidate_name": "John Quincy Adams",
         "president_candidate_party": "D-R"},
    ],
    "t2": {
        "candidate_state": [
            {"president_candidate_name": "Andrew Jackson", "col_ind": 1,
             "president_candidate_state": "Tennessee"},
            {"president_candidate_name": "John Quincy Adams", "col_ind": 2,
             "president_candidate_state": "Massachusetts"},
        ],
        "votes_by_state": [
            {"state": "Tennessee", "total_electoral_votes": 11, 1: 11, 2: 0},
            {"state": "Massachusetts", "total_electoral_votes": 10, 1: 0, 2: 10},
            {"state": "Totals", "total_electoral_votes": 21, 1: 11, 2: 10},
        ],
    },
}


def test_1824_office_holder_differs_from_ec_winner() -> None:
    # The contingent-election distinction (#29): Jackson leads the Electoral College
    # (rank 1) but Adams took office via the House. took_office marks the office-holder;
    # the EC winner stays derivable from president_electoral_rank == 1, so the two facts
    # never duplicate.
    candidates, _, votes = transform_parsed_years([_SYNTHETIC_1824], fake_state_geo())
    ids = candidates.set_index("name")["candidate_id"]

    totals = votes[votes["is_total"]].set_index("candidate_id")
    # Jackson leads the Electoral College...
    assert totals.loc[ids["Andrew Jackson"], "president_electoral_rank"] == 1
    assert totals.loc[ids["John Quincy Adams"], "president_electoral_rank"] == 2
    # ...but Adams took office, not Jackson.
    assert not bool(totals.loc[ids["Andrew Jackson"], "took_office"])
    assert bool(totals.loc[ids["John Quincy Adams"], "took_office"])

    # took_office is broadcast to every one of a candidate's rows (like the rank), so a
    # state-row query is not a "only meaningful when is_total" trap.
    assert votes[votes["candidate_id"] == ids["John Quincy Adams"]]["took_office"].all()
    assert not votes[votes["candidate_id"] == ids["Andrew Jackson"]]["took_office"].any()


def test_1824_real_fixture_office_holder_reconciles() -> None:
    # Regression guard the synthetic case above cannot provide: _SYNTHETIC_1824
    # hardcodes "John Quincy Adams" on both the input and CONTINGENT_OFFICE_HOLDERS
    # sides, so it is self-consistent by construction and would still pass if the
    # candidate dimension started spelling the name differently. Drive the *real*
    # 1824 Archives fixture end-to-end so the office-holder name actually matches the
    # parsed-and-reconciled candidate dim — otherwise _add_took_office raises and the
    # default `python -m usvote` run over 1824 (in loaded coverage, #32) would break.
    parsed = parse_election_years({1824: _year_tables(1824)}, STATE_NAMES)
    candidates, _, votes = transform_parsed_years(parsed, fake_state_geo())

    assert "John Quincy Adams" in set(candidates["name"])
    ids = candidates.set_index("name")["candidate_id"]
    totals = votes[votes["is_total"]].set_index("candidate_id")
    # Jackson led the Electoral College (rank 1) but Adams took office via the House.
    assert totals.loc[ids["Andrew Jackson"], "president_electoral_rank"] == 1
    assert not bool(totals.loc[ids["Andrew Jackson"], "took_office"])
    assert bool(totals.loc[ids["John Quincy Adams"], "took_office"])
    # Exactly one office-holder for the year.
    assert int(totals["took_office"].sum()) == 1


def test_contingent_office_holder_must_reconcile() -> None:
    # A contingent office-holder whose name is not in the candidate dimension (e.g. a
    # reconciliation miss) must fail loudly, not silently leave the EC leader marked as
    # having taken office.
    candidates = pd.DataFrame({"candidate_id": [1], "name": ["Andrew Jackson"]})
    votes = pd.DataFrame(
        {"year": [1824], "candidate_id": [1], "president_electoral_rank": [1]}
    )
    with pytest.raises(TransformError, match="contingent office-holder"):
        T._add_took_office(votes, candidates)


# --- integration: 2016 + 2020 fixture slice --------------------------------


def _year_tables(year: int) -> list[Tag]:
    return get_html_tables(
        f"https://www.archives.gov/electoral-college/{year}",
        find_all=True,
        fetch=fetch_from_dir(FIXTURES_DIR),
    )


@pytest.fixture(scope="module")
def parsed_slice() -> list[ParsedYear]:
    data_tables = {year: _year_tables(year) for year in (2016, 2020)}
    return parse_election_years(data_tables, STATE_NAMES)


@pytest.fixture(scope="module")
def frames(
    parsed_slice: list[ParsedYear],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return transform_parsed_years(parsed_slice, fake_state_geo())


def test_frames_schema_and_grain(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    candidates, state_df, votes = frames
    # 8 distinct candidates across 2016 + 2020: Trump, Biden, Clinton + the five
    # 2016 faithless recipients (Sanders, Paul, Kasich, Powell, Spotted Eagle).
    assert len(candidates) == 8
    assert candidates["candidate_id"].tolist() == list(range(1, 9))
    assert len(candidates) == candidates["name"].nunique()
    assert list(votes.columns) == ["votes_id", *T.VOTES_COLUMN_ORDER]
    assert votes["votes_id"].tolist() == list(range(1, len(votes) + 1))


def test_trump_is_one_candidate_across_both_years(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    candidates, _, votes = frames
    trump = candidates[candidates["name"] == "Donald J. Trump"]
    # 2016 "Donald Trump"/NY reconciled to the 2020 "Donald J. Trump"/FL spelling,
    # collapsed to one row spanning both states.
    assert len(trump) == 1
    assert {trump.iloc[0]["state"], trump.iloc[0]["state_2"]} == {"New York", "Florida"}
    trump_id = trump.iloc[0]["candidate_id"]
    # Same candidate_id carries Trump's votes in both years.
    assert set(votes.loc[votes["candidate_id"] == trump_id, "year"]) == {2016, 2020}


def test_biden_jr_suffix(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    candidates, _, _ = frames
    biden = candidates[candidates["name"] == "Joseph R. Biden Jr."].iloc[0]
    assert biden["name_suffix"] == "Jr."
    assert biden["name_last"] == "Biden"


def test_2016_totals_and_faithless_placement(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    candidates, _, votes = frames
    ids = candidates.set_index("name")["candidate_id"]
    totals = votes[(votes["year"] == 2016) & votes["is_total"]].set_index("candidate_id")
    # The manually-entered Archives Notes totals: 304/227/3/1/1/1/1 summing to 538.
    assert totals.loc[ids["Donald J. Trump"], "president_electoral_votes"] == 304
    assert totals.loc[ids["Hillary Clinton"], "president_electoral_votes"] == 227
    assert totals.loc[ids["Colin Powell"], "president_electoral_votes"] == 3
    assert totals["president_electoral_votes"].sum() == 538
    # Faithless votes land in the right states (state row, is_total False).
    powell_wa = votes[
        (votes["candidate_id"] == ids["Colin Powell"]) & (votes["state"] == "Washington")
    ]
    assert powell_wa.iloc[0]["president_electoral_votes"] == 3
    sanders_hi = votes[
        (votes["candidate_id"] == ids["Bernie Sanders"]) & (votes["state"] == "Hawaii")
    ]
    assert sanders_hi.iloc[0]["president_electoral_votes"] == 1


def test_totals_rows_have_null_state_and_is_total(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    _, _, votes = frames
    # Every is_total row has a NULL state and vice-versa; 7 (2016) + 2 (2020) = 9.
    assert votes["is_total"].sum() == votes["state"].isna().sum() == 9
    assert (votes.loc[votes["is_total"], "state"].isna()).all()


def test_build_votes_fact_raises_on_unreconciled_names(
    parsed_slice: list[ParsedYear],
) -> None:
    # A caller (e.g. the future pipeline) that forgets reconcile_vote_candidate_names
    # must fail loudly, not silently drop Trump's 2016 votes: the raw Table-2 name
    # "Donald Trump" no longer matches the candidate dim's "Donald J. Trump".
    t2_raw = T.normalize_candidate_states(parsed_slice)
    t1 = T.normalize_candidate_parties(parsed_slice)
    candidates = T.build_candidate_dim(t2_raw, t1)
    state_df = build_state_dim(fake_state_geo())
    with pytest.raises(TransformError, match="not present in the candidate dimension"):
        T.build_votes_fact(parsed_slice, t2_raw, candidates, state_df)


def test_electoral_rank_matches_vote_order(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    candidates, _, votes = frames
    ids = candidates.set_index("name")["candidate_id"]
    ranks = votes[(votes["year"] == 2020) & votes["is_total"]].set_index("candidate_id")
    # Biden (306) outranks Trump (232) in 2020.
    assert ranks.loc[ids["Joseph R. Biden Jr."], "president_electoral_rank"] == 1
    assert ranks.loc[ids["Donald J. Trump"], "president_electoral_rank"] == 2


def test_non_contingent_office_holder_is_ec_winner(
    frames: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    # For an ordinary (non-contingent) election the office-holder IS the EC rank-1
    # candidate: Biden (2020) is both rank 1 and took_office; Trump is neither.
    candidates, _, votes = frames
    ids = candidates.set_index("name")["candidate_id"]
    totals = votes[(votes["year"] == 2020) & votes["is_total"]].set_index("candidate_id")
    assert bool(totals.loc[ids["Joseph R. Biden Jr."], "took_office"])
    assert not bool(totals.loc[ids["Donald J. Trump"], "took_office"])
