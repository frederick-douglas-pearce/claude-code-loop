"""Integrity tests for the synthetic UCSB parser fixtures (#34, D022).

These do **not** exercise the #35 parser — that does not exist yet. They guard the
*fixtures themselves*: the synthetic HTML is a deliverable of this story, and its whole
value is that it reproduces the real UCSB table's structure **and its aggregation
identities** so #35's sum-validation has something true to check. Fabricated numbers
that silently stop adding up would make the fixtures a trap — a parser bug and a fixture
typo would look identical. So this locks the four identities read off the real data:

    (1) each candidate's Votes column sums exactly to the Totals row,
    (2) the TOTAL VOTE column sums exactly to the Totals row,
    (3) per state, TOTAL VOTE strictly exceeds the shown candidates (a residual "other"),
    (4) the Totals EV per candidate equals data-row EV PLUS the legislature-state
        electors apportioned in each cell's prose (D005: flagged and counted, never
        zeroed).

The small extractor below is deliberately ad hoc — just enough to read the grid, not a
preview of the real parser. It reads the state-block header to discover the candidate
count and names (never assuming a fixed width), which is also why the same test covers
both the 2- and 4-candidate-group eras.

**It stays frozen against the two fixtures it was written for.** #35 added six more
(L1b/L1c/L2/L3/L0), and the extractor cannot read them: its ``find_next_sibling``
name-row lookup assumes L1's stacked header, and the legislature assertion below
assumes every fixture has a legislature-chosen state — true of these two, false of
five of the six new ones. Growing it to cope would turn a throwaway grid reader into a
second, untested parser shadowing the real one.

So the new fixtures are held to the same identities by :mod:`tests.unit.test_ucsb_parse`
using the **real** parser instead. Identities (1) and (2) are enforced there by
``validate_year`` on every parse; identity (3) is checked for all seven popular-vote
fixtures by ``TestFixtureRealism`` at the bottom of this file, which is the one
fixture-realism property the parser has no reason to assert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

from tests._helpers import FIXTURES_DIR, UCSB_PV_FIXTURES, ucsb_fixture_html
from usvote.ucsb.parse import parse_election_year

# The two #34 fixtures the ad-hoc extractor was written for; see the module docstring
# on why it is not extended to the rest.
FIXTURES = {
    "2group": FIXTURES_DIR / "ucsb_synthetic_2group.html",
    "4group": FIXTURES_DIR / "ucsb_synthetic_4group.html",
}

# Shared with test_ucsb_parse.py via tests._helpers so the two cannot drift.
PV_FIXTURES = UCSB_PV_FIXTURES


def _cells(row: Tag) -> list[str]:
    """A row's cell texts, NBSP and surrounding whitespace normalized to ''."""
    return [td.get_text().replace("\xa0", " ").strip() for td in row.find_all("td")]


def _int(text: str) -> int | None:
    """Parse a comma-grouped integer, or None for a blank/non-numeric cell."""
    stripped = text.replace(",", "").strip()
    return int(stripped) if re.fullmatch(r"\d+", stripped) else None


@dataclass
class Grid:
    candidates: list[str]  # last-name key per candidate column, in state-block order
    totals: dict[str, int]  # candidate key / "TOTAL" -> Totals-row votes
    totals_ev: dict[str, int]  # candidate key -> Totals-row EV
    data_votes: dict[str, list[int]] = field(default_factory=dict)
    data_ev: dict[str, list[int]] = field(default_factory=dict)
    state_totals: list[int] = field(default_factory=list)
    state_shown_sums: list[int] = field(default_factory=list)
    pv_states: list[str] = field(default_factory=list)  # states with a popular vote
    legislature_states: list[str] = field(default_factory=list)  # no-PV, flagged rows
    legislature_awards: list[list[tuple[int, str]]] = field(default_factory=list)


def _key(name: str) -> str:
    """Reduce a candidate name to its uppercase last word (the match key)."""
    return name.upper().split()[-1]


def _parse_legislature_prose(text: str) -> list[tuple[int, str]]:
    """Return ``(electors, candidate_key)`` awards from a legislature cell's prose.

    Handles both real 1824/1876 phrasings the fixtures mimic: split awards
    ("2 for Hypothetical; 1 for Notional", "15 to Fictitious; ...") and whole-state
    awards ("N electors ... awarded to <Full Name>").
    """
    splits = re.findall(r"(\d+)\s+(?:for|to)\s+([A-Za-z]+)", text)
    if splits:
        return [(int(count), _key(name)) for count, name in splits]
    lead_match = re.match(r"\s*(\d+)", text)
    assert lead_match is not None  # caller only passes cells that open with a digit
    last_name = re.findall(r"[A-Z][a-z]+", text)[-1]
    return [(int(lead_match.group(1)), _key(last_name))]


def _parse_grid(html: str) -> Grid:
    table = BeautifulSoup(html, "html.parser").find("table")
    assert isinstance(table, Tag)
    rows = table.find_all("tr")

    # The candidate names live in the row after the STATE/TOTAL VOTE header row: one
    # bold colspan=3 cell per candidate, in state-block column order.
    header_row = next(r for r in rows if any(c == "STATE" for c in _cells(r)))
    name_row = header_row.find_next_sibling("tr")
    assert isinstance(name_row, Tag)
    candidates = [_key(td.get_text()) for td in name_row.find_all("td")]
    width = 2 + 3 * len(candidates)  # STATE, TOTAL VOTE, then (Votes,%,EV) per candidate

    grid = Grid(
        candidates=candidates,
        totals={},
        totals_ev={},
        data_votes={c: [] for c in candidates},
        data_ev={c: [] for c in candidates},
    )

    for row in rows:
        cells = _cells(row)
        if not cells or cells[0] in ("", "STATE", "Votes"):
            continue
        tds = row.find_all("td")

        # Legislature row: state name + one cell spanning the rest of the width, whose
        # prose opens with the elector count. The leading-digit test distinguishes it
        # from the candidate-name header row, also two cells with a colspan.
        if len(tds) == 2 and tds[1].get("colspan") and re.match(r"\s*\d", cells[1]):
            grid.legislature_states.append(cells[0])
            grid.legislature_awards.append(_parse_legislature_prose(cells[1]))
            continue

        if len(cells) != width:
            continue  # separator / footnote / summary rows

        total = _int(cells[1])
        if total is None:
            continue
        votes = {c: (_int(cells[2 + 3 * i]) or 0) for i, c in enumerate(candidates)}
        evs = {c: (_int(cells[4 + 3 * i]) or 0) for i, c in enumerate(candidates)}

        if cells[0] == "Totals":
            grid.totals = {"TOTAL": total, **votes}
            grid.totals_ev = evs
        else:
            grid.pv_states.append(cells[0])
            grid.state_totals.append(total)
            grid.state_shown_sums.append(sum(votes.values()))
            for c in candidates:
                grid.data_votes[c].append(votes[c])
                grid.data_ev[c].append(evs[c])
    return grid


@pytest.fixture(params=list(FIXTURES), ids=list(FIXTURES))
def grid(request: pytest.FixtureRequest) -> Grid:
    return _parse_grid(FIXTURES[request.param].read_text(encoding="utf-8"))


class TestAggregationIdentities:
    def test_candidate_vote_columns_sum_to_totals(self, grid: Grid) -> None:
        # Identity (1): the reconciliation #35 will run.
        for candidate in grid.candidates:
            assert sum(grid.data_votes[candidate]) == grid.totals[candidate], candidate

    def test_total_vote_column_sums_to_totals(self, grid: Grid) -> None:
        # Identity (2).
        assert sum(grid.state_totals) == grid.totals["TOTAL"]

    def test_each_state_total_exceeds_the_shown_candidates(self, grid: Grid) -> None:
        # Identity (3): a residual "other" exists, so within-row votes must NOT be
        # assumed to sum to TOTAL VOTE. Strict — a fixture where they summed exactly
        # would quietly misrepresent the real data and let a wrong assumption pass #35.
        for total, shown in zip(grid.state_totals, grid.state_shown_sums, strict=True):
            assert total > shown

    def test_ev_totals_include_the_legislature_states(self, grid: Grid) -> None:
        # Identity (4), the D005 case: Totals EV = data-row EV + legislature electors.
        legislature_ev = dict.fromkeys(grid.candidates, 0)
        for awards in grid.legislature_awards:
            for count, key in awards:
                assert key in legislature_ev, f"unknown candidate in prose: {key}"
                legislature_ev[key] += count

        for candidate in grid.candidates:
            expected = sum(grid.data_ev[candidate]) + legislature_ev[candidate]
            assert expected == grid.totals_ev[candidate], candidate

    def test_legislature_states_are_flagged_and_never_zeroed(self, grid: Grid) -> None:
        # The D005 property, and the flip side of identity (4). Two things must hold,
        # and the earlier tautological version checked neither:
        assert grid.legislature_states  # both fixtures must exercise the case

        # (a) NEVER ZEROED: every legislature state carries a positive elector count in
        #     its prose. A state coerced to zero -- or dropped -- would show up as an
        #     award summing to 0 here.
        for state, awards in zip(
            grid.legislature_states, grid.legislature_awards, strict=True
        ):
            assert sum(count for count, _ in awards) > 0, state

        # (b) NOT IN THE PV GRAIN: legislature states are absent from the popular-vote
        #     rows entirely (identity 1 reconciles without them), not entered as
        #     zero-vote data rows. If one had leaked into the data rows it would appear
        #     in both lists.
        assert set(grid.legislature_states).isdisjoint(grid.pv_states)


class TestStructuralCoverage:
    """The fixtures must, between them, pin the structural cases D022 enumerates."""

    def test_group_counts_drift_across_the_two_fixtures(self) -> None:
        two = _parse_grid(FIXTURES["2group"].read_text(encoding="utf-8"))
        four = _parse_grid(FIXTURES["4group"].read_text(encoding="utf-8"))
        assert len(two.candidates) == 2
        assert len(four.candidates) == 4

    def test_four_group_has_the_full_1824_legislature_set(self) -> None:
        html = FIXTURES["4group"].read_text(encoding="utf-8")
        # The six real-1824 legislature states, flagged not zeroed (D005).
        for state in ("Delaware", "Georgia", "Louisiana", "New York",
                      "South Carolina", "Vermont"):
            assert f">{state}<" in html
        grid = _parse_grid(html)
        assert len(grid.legislature_awards) == 6

    def test_four_group_carries_a_house_footnote(self) -> None:
        html = FIXTURES["4group"].read_text(encoding="utf-8")
        assert "elected by the House of Representatives" in html

    def test_no_fixture_ships_real_ucsb_bytes(self) -> None:
        # D022: the tell would be real presidency.ucsb.edu asset URLs; the synthetics
        # use example.invalid. A cheap guard against a real page being pasted in later.
        # Globs rather than iterating FIXTURES so fixtures added later are covered
        # automatically — a hygiene check that can be outgrown is worse than none.
        for path in FIXTURES_DIR.glob("ucsb_synthetic_*.html"):
            assert "presidency.ucsb.edu" not in path.read_text(encoding="utf-8")


class TestFixtureRealism:
    """Identity (3) across all seven popular-vote fixtures, via the real parser.

    The columned candidates are never the whole ballot — real UCSB pages carry a
    residual "other" vote — so per state, TOTAL VOTE must strictly exceed the sum of
    the shown candidates. This is the one identity the parser has no business
    asserting (a year where they summed exactly would be legitimate data, not a parse
    error), yet a fixture that got it wrong would quietly license a wrong assumption
    downstream: that within-row votes can be used as the state total.
    """

    @pytest.mark.parametrize("stem", list(PV_FIXTURES))
    def test_total_vote_exceeds_the_shown_candidates(self, stem: str) -> None:
        year, _ = PV_FIXTURES[stem]
        parsed = parse_election_year(ucsb_fixture_html(stem), year)
        assert parsed is not None
        for row in parsed["state_rows"]:
            shown = sum(cell["votes"] or 0 for cell in row["cells"])
            assert row["state_total_votes"] > shown, (stem, row["state_label"])
