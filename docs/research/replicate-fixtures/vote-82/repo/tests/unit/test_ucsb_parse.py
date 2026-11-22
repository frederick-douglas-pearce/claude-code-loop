"""Unit tests for the UCSB HTML parser (E4-S2, #35).

Structured around the failure modes the corpus survey ranked as most dangerous —
the ones that produce a QUIETLY WRONG number rather than a crash:

    - congressional-district sub-rows double-counting the popular vote (risk 2),
    - the 1976 column-window shift (risk 5),
    - nested summary tables leaking into the body (risk 1),
    - an absence token coerced to 0 (D024 §2),
    - percent-based absence detection (the 1948 0.0% decoy).

Each has a fixture built to expose it and a test that fails if the defence is
removed. Where a defence is load-bearing, there is also a companion test asserting
that DISABLING it breaks an identity — so the defence cannot be quietly dropped later
as redundant.

The eight fixtures are all synthetic (D022): this repo is public and UCSB content is
non-redistributable, so no UCSB bytes are committed. The real 60-page snapshot is the
acceptance corpus, exercised by ``TestRealCorpus`` below, which skips when the
snapshot is absent so CI stays green and never touches UCSB.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

from tests._helpers import FIXTURES_DIR, UCSB_PV_FIXTURES, ucsb_fixture_html
from usvote.ucsb.parse import (
    LEGISLATURE_MARKER,
    NO_POPULAR_VOTE_YEARS,
    STATUS_LEGISLATURE_CHOSEN,
    ParsedUCSBYear,
    UCSBLayout,
    UCSBParseError,
    UCSBStateRow,
    _detect_group_count,
    detect_layout,
    own_rows,
    parse_election_year,
    parse_election_years,
    parse_state_data_row,
    select_results_table,
)

# Shared with test_ucsb_fixtures.py via tests._helpers so the two cannot drift.
FIXTURES = UCSB_PV_FIXTURES
PV_FIXTURES = list(FIXTURES)  # every fixture that has a state table (excludes L0)

_html = ucsb_fixture_html


def _rows(stem: str) -> list[Tag]:
    """The results table's own rows for a fixture, with the None case asserted away."""
    table = select_results_table(BeautifulSoup(_html(stem), "html.parser"))
    assert table is not None, stem
    return own_rows(table)


def _totals(parsed: ParsedUCSBYear) -> UCSBStateRow:
    """The totals row, with the None case asserted away (validate_year requires one)."""
    totals = parsed["totals"]
    assert totals is not None
    return totals


def _parsed(stem: str) -> ParsedUCSBYear:
    year, _ = FIXTURES[stem]
    result = parse_election_year(_html(stem), year)
    assert result is not None
    return result


@pytest.fixture(params=PV_FIXTURES, ids=PV_FIXTURES)
def parsed(request: pytest.FixtureRequest) -> ParsedUCSBYear:
    return _parsed(request.param)


class TestLayoutDetection:
    """All per-era branching lives in ``detect_layout``; these pin every branch."""

    @pytest.mark.parametrize(("stem", "expected"), [(s, FIXTURES[s][1]) for s in FIXTURES])
    def test_each_layout_is_detected(self, stem: str, expected: str) -> None:
        assert _parsed(stem)["layout"] == expected

    def test_1976_is_reachable_and_not_swallowed_by_l3(self) -> None:
        # The regression this guards: 1976's STATE row IS its units row, so the L3
        # test ("contains Votes") matches it too. Without the `len(state_row) ==
        # data_width` discriminator, 1976 classifies as L3, the column window shifts
        # left by one, and every candidate silently gets the previous one's votes.
        rows = _rows("1976")
        layout = detect_layout(rows)
        assert layout.kind == "L1c"
        assert layout.data_width == 8
        # The discriminator itself: the header really is narrower than the data.
        state_ind = layout.name_row_ind + 2
        assert len(rows[state_ind].find_all("td")) == 7 < layout.data_width

    def test_group_count_comes_from_data_rows_not_header_colspans(self) -> None:
        # 1836 (L1b) has NO header colspans at all, so any header-derived g is 0.
        assert _parsed("nocolspan")["group_count"] == 4

    def test_group_count_survives_a_summary_row_tie(self) -> None:
        # The 4group fixture has 4 summary rows (width 9) against 4 data rows (width
        # 14). A bare modal width ties and — because Counter breaks ties by
        # first-seen — picks 9, whose (9-2)//3 floor-divides to a plausible-looking
        # g=2 rather than failing. Filtering to W = 2+3g before taking the mode is
        # what makes this deterministic.
        assert _parsed("4group")["group_count"] == 4

    def test_malformed_width_raises_rather_than_floor_dividing(self) -> None:
        soup = BeautifulSoup("<table><tr>" + "<td>x</td>" * 9 + "</tr></table>", "html.parser")
        table = soup.find("table")
        assert isinstance(table, Tag)
        with pytest.raises(UCSBParseError, match="structurally-valid data width"):
            _detect_group_count(own_rows(table))


class TestAbsenceIsNeverZero:
    """D024 §2: a candidate not on the ballot is None, never 0."""

    def test_no_vote_value_is_ever_zero(self, parsed: ParsedUCSBYear) -> None:
        for row in [*parsed["state_rows"], *parsed["cd_rows"]]:
            for cell in row["cells"]:
                assert cell["votes"] != 0, (row["state_label"], cell)

    def test_dash_dash_parses_to_none(self) -> None:
        rows = {r["state_label"]: r for r in _parsed("dashdash")["state_rows"]}
        # Delaware's third and fourth candidates are both "--".
        assert [c["votes"] for c in rows["Delaware"]["cells"]] == [24000, 25000, None, None]

    def test_single_hyphen_typo_is_also_absence(self) -> None:
        # 1836 Rhode Island spells absence with ONE hyphen. Modeling the token as a
        # set rather than a literal "--" is the whole reason this parses.
        rows = {r["state_label"]: r for r in _parsed("nocolspan")["state_rows"]}
        assert rows["Rhode Island"]["cells"][3]["votes"] is None

    def test_absent_cells_contribute_nothing_to_the_column_total(self) -> None:
        # The proof that None is not 0: the fourth candidate's national total is
        # 4,228 from just two states, and the year's sums still reconcile exactly.
        parsed = _parsed("dashdash")
        assert _totals(parsed)["cells"][3]["votes"] == 4228


class TestPercentIsNeverAnAbsenceSignal:
    """The 1948 decoy — the single easiest way to get absence wrong."""

    def test_zero_percent_with_real_votes_is_not_absence(self) -> None:
        rows = {r["state_label"]: r for r in _parsed("dashdash")["state_rows"]}
        california = rows["California"]["cells"][3]
        alabama = rows["Alabama"]["cells"][3]

        # Same published percent story, opposite meanings. Any absence rule that
        # consults the percent column collapses these two into one.
        assert california["votes"] == 1228, "0.0% means 'rounds to zero', not 'zero'"
        assert california["percent"] == 0.0
        assert alabama["votes"] is None, "'--' is the only absence signal"

    def test_percent_is_retained_for_the_column_shift_check(self) -> None:
        for row in _parsed("1976")["state_rows"]:
            assert all(cell["percent"] is not None for cell in row["cells"])


class TestCongressionalDistrictRows:
    """Risk 2: CD sub-rows partition the parent state's votes, they do not add to it."""

    def test_cd_rows_are_kept_out_of_the_state_grain(self) -> None:
        parsed = _parsed("inline_cd")
        assert [r["state_label"] for r in parsed["state_rows"]] == [
            "Maine", "Nebraska", "Vermont",
        ]
        assert len(parsed["cd_rows"]) == 5

    def test_cd_rows_carry_their_parent_state(self) -> None:
        # Parent linkage exists only as document order and is destroyed at parse
        # time, so if it is not captured here it is not recoverable at all.
        parsed = _parsed("inline_cd")
        assert [(r["parent_state_label"], r["state_label"]) for r in parsed["cd_rows"]] == [
            ("Maine", "CD-1"), ("Maine", "CD-2"),
            ("Nebraska", "CD-1"), ("Nebraska", "CD-2"), ("Nebraska", "CD-3"),
        ]

    def test_including_cd_rows_would_break_the_totals_identity(self) -> None:
        # The companion test that pins the exclusion as LOAD-BEARING. Without it,
        # a future reader could merge the two lists and every existing test would
        # still pass while the national popular vote inflated by ~1.5M.
        parsed = _parsed("inline_cd")
        states_only = sum(r["state_total_votes"] for r in parsed["state_rows"])
        with_cds = states_only + sum(r["state_total_votes"] for r in parsed["cd_rows"])

        assert states_only == _totals(parsed)["state_total_votes"]
        assert with_cds != _totals(parsed)["state_total_votes"]

    def test_a_cd_row_without_a_parent_raises(self) -> None:
        html = _html("inline_cd").replace(
            '<td bgcolor="#F7FAFD">Maine</td>', '<td bgcolor="#F7FAFD">CD-9</td>', 1
        )
        with pytest.raises(UCSBParseError, match="precedes any state row"):
            parse_election_year(html, 2020)


class TestLegislatureStatusRows:
    """D024 §4 case 1 — the only PV-absence case with any markup to read."""

    def test_status_row_shape(self) -> None:
        parsed = _parsed("2group")
        assert len(parsed["status_rows"]) == 1
        status = parsed["status_rows"][0]
        assert status["state_label"] == "Colorado"
        assert status["pv_status"] == STATUS_LEGISLATURE_CHOSEN
        assert LEGISLATURE_MARKER in status["note"].lower()

    def test_note_is_verbatim_and_electors_are_not_extracted(self) -> None:
        # D006: the Electoral College is sourced from the National Archives spine. A
        # second, weaker EC number parsed out of UCSB prose becomes a liability the
        # moment the two disagree — so the prose is carried whole and untouched.
        status = _parsed("4group")["status_rows"][3]
        assert status["note"].startswith("36 electors chosen by state legislature")
        assert set(status) == {"state_label", "pv_status", "note"}

    def test_legislature_states_never_appear_as_zero_vote_data_rows(self) -> None:
        parsed = _parsed("4group")
        legislature = {s["state_label"] for s in parsed["status_rows"]}
        data = {r["state_label"] for r in parsed["state_rows"]}
        assert legislature and legislature.isdisjoint(data)

    def test_an_unmarked_full_width_row_raises(self) -> None:
        # A 2-cell wide-colspan row that is NOT a legislature row is unmodeled. It
        # must raise rather than be skipped: silently dropping it would delete a
        # state from the year with no trace. (Verified corpus-wide: every real such
        # row carries the marker, so this can only fire on genuinely new markup.)
        html = _html("2group").replace(
            "3 electors chosen by state legislature and awarded to Alexandra Placeholder",
            "Something entirely new happened here",
        )
        with pytest.raises(UCSBParseError, match="unmodeled full-width 2-cell row"):
            parse_election_year(html, 1876)


class TestNestedAndTrailingSummaryBlocks:
    """Risk 1 — the survey's top-ranked quiet-wrongness risk."""

    def test_nested_summary_rows_do_not_leak_into_the_body(self) -> None:
        # The dashdash fixture's summary is a <table> inside a cell of the outer
        # table, so a plain find_all("tr") walks into it. The tell would be summary
        # candidate names showing up as states.
        labels = {r["state_label"] for r in _parsed("dashdash")["state_rows"]}
        assert labels == {"Alabama", "California", "Connecticut", "Delaware"}

    def test_nested_cells_do_not_leak_into_a_row(self) -> None:
        # The mirror of the above and a distinct bug: find_all("td") on the wrapper
        # row descends into the nested table too, so cell counting needs the same
        # own-element discipline that row collection does.
        wrapper = _rows("dashdash")[0]
        assert len(wrapper.find_all("td")) > 1  # recursive count sees the inner table
        assert _parsed("dashdash")["group_count"] == 4


class TestOneBodyParser:
    """The structural claim the whole design rests on."""

    def test_parse_state_data_row_never_reads_the_layout_kind(self) -> None:
        # The survey's central finding is that every data row is 2 + 3g cells
        # regardless of era, so per-era branching can be confined to the header. This
        # asserts that directly: identical markup must parse identically under
        # layouts that differ ONLY in `kind`.
        html = (
            "<table><tr>"
            "<td>Alabama</td><td>100,000</td>"
            "<td>60,000</td><td>60.0</td><td>9</td>"
            "<td>39,000</td><td>39.0</td><td> </td>"
            "</tr></table>"
        )
        table = BeautifulSoup(html, "html.parser").find("table")
        assert isinstance(table, Tag)
        row = own_rows(table)[0]
        geometry = {
            "group_count": 2, "data_width": 8, "header_end": 0, "name_row_ind": 0,
        }

        results = [
            parse_state_data_row(row, UCSBLayout(kind=kind, party_row_ind=None, **geometry))
            for kind in ("L1", "L1b", "L1c", "L2", "L3")
        ]
        assert all(result == results[0] for result in results)


class TestNoPopularVoteYears:
    """Design call (B): None is reserved for years that legitimately have no PV."""

    def test_l0_page_returns_none_for_a_pre_1824_year(self) -> None:
        assert parse_election_year(_html("summary_only"), 1820) is None

    def test_l0_page_raises_for_a_year_that_should_have_a_popular_vote(self) -> None:
        # A bare "no STATE row -> None" is the silent-failure shape D024 §4 rules
        # out: a scrape regression would present as a year with no popular vote.
        with pytest.raises(UCSBParseError, match="should have a popular vote"):
            parse_election_year(_html("summary_only"), 1900)

    def test_a_state_table_in_a_pre_1824_year_raises(self) -> None:
        with pytest.raises(UCSBParseError, match="predates any recorded popular vote"):
            parse_election_year(_html("2group"), 1816)

    def test_the_no_pv_year_set_matches_the_real_election_cadence(self) -> None:
        # Guards a cadence bug that range(1789, 1824, 4) makes easy: it yields
        # 1793/1797/1801/... and matches no actual election. The series starts at
        # 1789 but goes quadrennial from 1792.
        assert sorted(NO_POPULAR_VOTE_YEARS) == [
            1789, 1792, 1796, 1800, 1804, 1808, 1812, 1816, 1820,
        ]


class TestWithinPageInvariants:
    """``validate_year``: everything checkable without the state roster."""

    def test_every_row_accounts_for_every_candidate_column(
        self, parsed: ParsedUCSBYear
    ) -> None:
        # D024 §7's within-page half. The cross-page roster assert is #36's, because
        # an absent row is invisible from here by construction.
        for row in [*parsed["state_rows"], *parsed["cd_rows"]]:
            assert len(row["cells"]) == parsed["group_count"]
        assert len(parsed["candidates"]) == parsed["group_count"]

    def test_sums_reconcile_exactly(self, parsed: ParsedUCSBYear) -> None:
        totals = _totals(parsed)
        assert sum(r["state_total_votes"] for r in parsed["state_rows"]) == (
            totals["state_total_votes"]
        )
        for column in totals["cells"]:
            if column["votes"] is None:
                continue
            assert column["votes"] == sum(
                cell["votes"] or 0
                for row in parsed["state_rows"]
                for cell in row["cells"]
                if cell["col_ind"] == column["col_ind"]
            )

    def test_a_broken_sum_is_caught(self) -> None:
        html = _html("2group").replace(
            '<td bgcolor="#F7FAFD">60,000</td>', '<td bgcolor="#F7FAFD">61,000</td>', 1
        )
        with pytest.raises(UCSBParseError, match="sums to"):
            parse_election_year(html, 1876)

    def test_a_singular_total_label_is_still_a_totals_row(self) -> None:
        # 1864 and 1944 use "Total". A `== "Totals"` test drops the row, leaves
        # totals=None, and silently no-ops the sum validator above.
        assert _parsed("missing_states")["totals"] is not None

    def test_a_systematic_percent_shift_is_caught(self) -> None:
        # Simulates the 1976 column-window failure: every row's candidates swapped
        # against their percents. Isolated source typos must NOT trip this (three
        # real years have them), so the check is on the mismatch RATE.
        parsed = _parsed("1976")
        shifted = ParsedUCSBYear(
            **{**parsed, "state_rows": [
                {**row, "cells": [
                    {**cell, "votes": row["cells"][1 - ind]["votes"]}
                    for ind, cell in enumerate(row["cells"])
                ]}
                for row in parsed["state_rows"]
            ]},
        )
        from usvote.ucsb.parse import _assert_percent_consistent

        with pytest.raises(UCSBParseError, match="column window is probably misaligned"):
            _assert_percent_consistent(shifted)


class TestGuardsFailLoudly:
    """Regressions for four guards that used to degrade quietly instead of raising.

    All four shared one defect: a check that could not run silently reported success.
    That is the same failure the module docstring rules out for *input data* ("nothing
    unclassifiable passes silently"), applied inconsistently to the parser's own
    control flow — so each is pinned here rather than left to the corpus to re-find.
    """

    def test_a_state_row_at_the_top_does_not_wrap_to_the_last_row(self) -> None:
        # `ind - 1` on an L3 table whose STATE row is row 0 used to index NEGATIVELY.
        # Python wraps silently, so the table's LAST row was read as the candidate
        # name row: parsing succeeded and returned names lifted from a trailing data
        # row. A whole year's candidates would be mislabelled with no error at all.
        html = (
            "<table>"
            "<tr><td>STATE</td><td>TOTAL VOTE</td><td>Votes</td><td>%</td><td>EV</td>"
            "<td>Votes</td><td>%</td><td>EV</td></tr>"
            "<tr><td>Alabama</td><td>100,000</td><td>60,000</td><td>60.0</td><td>9</td>"
            "<td>39,000</td><td>39.0</td><td> </td></tr>"
            "<tr><td>Maine</td><td>50,000</td><td>30,000</td><td>60.0</td><td>4</td>"
            "<td>19,000</td><td>38.0</td><td> </td></tr>"
            "<tr><td>DECOY-A</td><td>DECOY-B</td></tr>"
            "</table>"
        )
        table = BeautifulSoup(html, "html.parser").find("table")
        assert isinstance(table, Tag)
        with pytest.raises(UCSBParseError, match="no header row 1 above it"):
            detect_layout(own_rows(table))

    def test_an_absent_totals_cell_does_not_exempt_a_column_from_the_sum_check(
        self,
    ) -> None:
        # `if total_cell["votes"] is None: continue` conflated "nothing to check" with
        # "checked and fine", so blanking a totals cell disabled that candidate's sum
        # validation entirely and let arbitrary corruption through.
        html = _html("dashdash").replace(
            '<td bgcolor="#F7FAFD">100,000</td>', '<td bgcolor="#F7FAFD">999,000</td>', 1
        ).replace(
            '<td bgcolor="#F7FAFD">2,194,000</td>', '<td bgcolor="#F7FAFD">--</td>', 1
        )
        with pytest.raises(UCSBParseError, match="has no totals value"):
            parse_election_year(html, 1948)

    def test_unreadable_percents_raise_rather_than_silently_skipping_the_check(
        self,
    ) -> None:
        # The percent cross-check is the only cheap detector for a column-window
        # shift. Guarding on `if compared and ...` meant a year whose percent format
        # drifted compared ZERO cells and passed — quietly dropping the guarantee.
        html = re.sub(
            r'(<td bgcolor="#(?:F7FAFD|FFFFFF)">)(\d+\.\d)(</td>)',
            r"\1n/a\3",
            _html("1976"),
        )
        with pytest.raises(UCSBParseError, match="no percent cell could be read"):
            parse_election_year(html, 1976)

    def test_a_state_cannot_be_both_a_vote_row_and_a_legislature_row(self) -> None:
        # `pv_state_status` is keyed (source, year, state), so this hands #36 two
        # irreconcilable facts for one key. Cheap to reject at the source.
        html = _html("2group").replace(
            '<td bgcolor="#F7FAFD">Alabama</td>', '<td bgcolor="#F7FAFD">Colorado</td>', 1
        )
        with pytest.raises(UCSBParseError, match="both popular-vote rows and"):
            parse_election_year(html, 1876)

    def test_duplicate_state_rows_raise(self) -> None:
        html = _html("2group").replace(
            '<td bgcolor="#FFFFFF">California</td>',
            '<td bgcolor="#FFFFFF">Alabama</td>',
            1,
        )
        with pytest.raises(UCSBParseError, match="duplicate state rows"):
            parse_election_year(html, 1876)

    @pytest.mark.parametrize(
        ("original", "shouted"),
        [("Totals", "TOTALS"), ("STATE", "State"), ("Party", "PARTY")],
    )
    def test_header_labels_are_matched_case_insensitively(
        self, original: str, shouted: str
    ) -> None:
        # UCSB's casing is not stable across eras (1940 alone switches STATE ->
        # STATES), and the label lookups had diverged: STATE folded case, the totals
        # and summary-block labels did not.
        parsed = parse_election_year(
            _html("2group").replace(f">{original}<", f">{shouted}<"), 1876
        )
        assert parsed is not None
        assert parsed["totals"] is not None


class TestUnclassifiableRowsRaise:
    """D024 §4 rejects an 'unknown' bucket by name; there is no blanket skip."""

    def test_an_unmodeled_row_raises(self) -> None:
        html = _html("2group").replace(
            "<td>Connecticut</td>", "<td>Connecticut</td><td>surprise</td>", 1
        )
        with pytest.raises(UCSBParseError, match="unclassifiable row"):
            parse_election_year(html, 1876)

    def test_benign_prose_and_separators_are_skipped(self) -> None:
        # The allowlist is enumerated, not a fallback: separator bars, all-blank
        # rows, and the House-election footnote are known shapes.
        assert len(_parsed("4group")["state_rows"]) == 3
        assert len(_parsed("missing_states")["state_rows"]) == 4


class TestEntryPoint:
    def test_parse_election_years_drops_l0_and_sorts(self) -> None:
        result = parse_election_years({
            1876: _html("2group"),
            1820: _html("summary_only"),
            1864: _html("missing_states"),
        })
        assert [p["year"] for p in result] == [1864, 1876]


class TestCorrectionsCatalog:
    """Every UCSB anomaly constant must appear in ``docs/corrections.md``.

    CLAUDE.md: "add a new anomaly the same way (constant + test + catalog row),
    documenting its source as existing entries do." The catalog is only useful if it
    is complete, and completeness is exactly the property that rots silently — so it
    is asserted rather than trusted.
    """

    @pytest.mark.parametrize(
        "constant",
        ["ABSENT_VOTE_TOKENS", "PERCENT_MISMATCH_RATE", "TOTALS_LABELS",
         "STATE_HEADER_LABELS"],
    )
    def test_anomaly_constant_has_a_catalog_row(self, constant: str) -> None:
        catalog = (
            Path(__file__).resolve().parents[2] / "docs" / "corrections.md"
        ).read_text(encoding="utf-8")
        assert constant in catalog, (
            f"{constant} handles a real UCSB data anomaly but has no row in "
            f"docs/corrections.md"
        )


class TestFixtureHygiene:
    def test_no_fixture_ships_real_ucsb_bytes(self) -> None:
        # D022: the tell would be real presidency.ucsb.edu asset URLs; the
        # synthetics use example.invalid.
        for path in FIXTURES_DIR.glob("ucsb_synthetic_*.html"):
            assert "presidency.ucsb.edu" not in path.read_text(encoding="utf-8")

    def test_every_modeled_layout_has_a_fixture(self) -> None:
        assert {layout for _, layout in FIXTURES.values()} == {
            "L1", "L1b", "L1c", "L2", "L3",
        }


_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


@pytest.mark.skipif(
    not _CORPUS, reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo"
)
class TestRealCorpus:
    """The acceptance check fixtures cannot deliver: every real page must parse.

    Skipped whenever the snapshot is absent, so CI stays green and never touches
    UCSB (D014/D016/D022). This is the test that caught the trailing-summary-block
    years, the real 1976 header shape, and the pre-1824 year cadence — none of which
    the synthetic fixtures could have surfaced on their own.
    """

    def test_every_page_parses(self) -> None:
        pages = sorted(p for p in Path(_CORPUS).glob("*.html") if p.stem.isdigit())
        assert len(pages) >= 60

        parsed: list[int] = []
        skipped: list[int] = []
        for path in pages:
            year = int(path.stem)
            result = parse_election_year(
                path.read_text(encoding="utf-8", errors="replace"), year
            )
            (skipped if result is None else parsed).append(year)

        assert skipped == sorted(NO_POPULAR_VOTE_YEARS)
        assert len(parsed) == len(pages) - len(skipped)

    def test_no_literal_zero_anywhere_in_the_corpus(self) -> None:
        # The corpus-wide claim that licenses treating a 0 as proof of a bug.
        for path in sorted(Path(_CORPUS).glob("*.html")):
            if not path.stem.isdigit():
                continue
            result = parse_election_year(
                path.read_text(encoding="utf-8", errors="replace"), int(path.stem)
            )
            if result is None:
                continue
            for row in [*result["state_rows"], *result["cd_rows"]]:
                for cell in row["cells"]:
                    assert cell["votes"] != 0, (result["year"], row["state_label"])
