"""Parse stage — turn raw Archives HTML into structured per-year records.

Maps to notebook Section 2 (the pure half). These functions take already-fetched
``<table>`` elements (see :mod:`usvote.scrape`) and do no network access, which
makes them the natural first fixture-based unit-test target. The output is
``parsed_election_years``: a list of per-year dicts with keys ``t1``,
``t2.candidate_state`` and ``t2.votes_by_state`` that :mod:`usvote.transform`
(#26) later feeds to ``pd.json_normalize``.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S2 (#25). The parser
family lands here unchanged in behavior — ``parse_election_years``,
``parse_election_year_tables``, ``parse_table1``, ``parse_t1_candidate_party``,
``parse_table2``, ``parse_t2_num_candidates``, ``parse_t2_candidate_state``,
``parse_t2_votes_by_state`` — with two deliberate changes that mirror the
``scrape``/``db`` ports:

- **Typed failures.** Where the notebook printed an error and returned ``None``
  on a malformed table (a bad Table 1 header, a missing ``For President``
  colspan), this raises :class:`ParseError`. Returning ``None`` there silently
  poisoned the downstream ``json_normalize``; a typed, message-carrying
  exception names what was wrong instead.
- **Modern bs4 lookups.** ``find(..., string=)`` replaces the deprecated
  ``text=`` keyword; behavior against the Archives markup is identical (verified
  against saved 2016/2020 fixtures).

Each per-year page has two tables. **Table 1** gives the top-two candidates and
their parties. **Table 2** carries the candidate home states plus a
variable-width votes-by-state matrix — the number of candidate columns is read
from the ``For President`` header's ``colspan`` (:func:`parse_t2_num_candidates`),
which is how anomaly years with faithless/"Other" electors (e.g. 2016) widen the
table.

Note the ``votes_by_state`` records intentionally mix key types: the string keys
``'state'`` and ``'total_electoral_votes'`` alongside integer candidate-column
indices (``1``, ``2``, …). This is the exact shape ``json_normalize`` expects
downstream, so the port preserves it rather than tidying it.
"""

from __future__ import annotations

from collections.abc import Container, Iterable, Sequence
from typing import TypedDict

from bs4.element import Tag

# Table 1 row layout: row 0 is the winning President, row 1 the main opponent.
# Kept as parallel (index, expected-header) pairs exactly as the notebook walked
# them, so a header drift trips the check in parse_t1_candidate_party.
T1_ROW_INDS = (0, 1)
T1_ROW_HEADERS = ("President", "Main Opponent")

# Column-0 labels that mark the electoral-vote totals row rather than a state.
TOTALS_LABELS = frozenset({"Total", "Totals"})


def _is_totals_label(text: str | None) -> bool:
    """True if ``text`` is a ``Total``/``Totals`` label (whitespace-trimmed)."""
    return text is not None and text.strip() in TOTALS_LABELS


def _clean_label(text: str) -> str:
    """Strip footnote asterisks and surrounding whitespace from a cell label.

    Modern Archives pages separate a cell's text from its footnote marker with a
    **non-breaking space** (e.g. ``Oregon\xa0<sup>1</sup>``). Once
    :func:`strip_footnotes` removes the ``<sup>``, a trailing ``\xa0`` remains — and
    a plain ``.strip(" ")`` does not remove it, so the label would fail to match its
    state name and the row would be silently dropped. ``str.strip()`` (no args)
    removes *all* Unicode whitespace, ``\xa0`` included; the ``strip("*")`` between
    the two strips clears footnote asterisks that sit outside the whitespace.
    """
    return text.strip().strip("*").strip()

# Table 2 candidate-column labels for an aggregate "Other(s)" column — minor
# candidates the Archives collapses into one column with no single home state
# (2016's faithless electors print "Other"; pre-1892 years such as 1824 print
# "Others"). transform.apply_other_candidates splits these back into named
# candidates from each year's Notes; here they are just marked (state=None).
OTHER_LABELS = frozenset({"Other", "Others"})


class CandidateParty(TypedDict):
    """One Table 1 candidate: display name (commas stripped) and party code."""

    president_candidate_name: str
    president_candidate_party: str


class CandidateState(TypedDict):
    """One Table 2 candidate column: name, 1-based column index, home state.

    ``president_candidate_state`` is ``None`` for the "Other" aggregate column
    (faithless / minor electors), which has no single home state.
    """

    president_candidate_name: str
    col_ind: int
    president_candidate_state: str | None


# A votes-by-state record: 'state' -> name, 'total_electoral_votes' -> int, and
# integer candidate-column indices -> that candidate's electoral votes. The mixed
# key/value types are load-bearing for the downstream json_normalize (see module
# docstring); this alias documents the shape without narrowing it.
StateVotes = dict[str | int, str | int]


class ParsedTable2(TypedDict):
    """Table 2 parsed into its two parts: candidate home states + vote matrix."""

    candidate_state: list[CandidateState]
    votes_by_state: list[StateVotes]


class ParsedYear(TypedDict):
    """One election year: Table 1 candidates/parties, Table 2, and the year."""

    t1: list[CandidateParty]
    t2: ParsedTable2
    year: int


class ParseError(RuntimeError):
    """Raised when an Archives table does not match the expected structure.

    The notebook printed a message and returned ``None`` on a malformed Table 1
    header or a missing ``For President`` colspan, letting the bad value flow into
    ``json_normalize``. Raising a typed, message-carrying exception instead
    surfaces the problem at the row that caused it.
    """


def parse_election_years(
    data_tables: dict[int, list[Tag]], state_names: Container[str]
) -> list[ParsedYear]:
    """Parse every scraped election year into a :class:`ParsedYear` record.

    ``data_tables`` maps a year to its two raw ``<table>`` elements (the output
    of :func:`usvote.scrape.scrape_raw_election_tables`); ``state_names`` is the
    set of valid US state names used to tell state rows from the totals/notes
    rows at the foot of Table 2.
    """
    parsed_years: list[ParsedYear] = []
    for ind, year in enumerate(data_tables):
        print(f"Working on Election Year = {year} ({ind})")
        parsed = parse_election_year_tables(data_tables[year], state_names)
        parsed_years.append({"t1": parsed["t1"], "t2": parsed["t2"], "year": year})
    return parsed_years


class _YearTables(TypedDict):
    t1: list[CandidateParty]
    t2: ParsedTable2


def parse_election_year_tables(
    year_tables: Sequence[Tag], state_names: Container[str]
) -> _YearTables:
    """Dispatch a single year's two tables to the Table 1 / Table 2 parsers.

    Each table parser strips its own footnote markers (see :func:`strip_footnotes`),
    so this dispatch carries no hidden precondition — a direct caller of
    :func:`parse_table1` / :func:`parse_table2` is handled identically.
    """
    return {
        "t1": parse_table1(year_tables[0].find_all("tr")),
        "t2": parse_table2(year_tables[1].find_all("tr"), state_names),
    }


def strip_footnotes(subtree: Tag) -> None:
    """Remove ``<sup>`` footnote markers (and their contents) from ``subtree`` in place.

    Accepts any ``<table>`` or ``<tr>`` element (each table parser calls it on its own
    rows, so no caller depends on a prior table-wide pass). Older Archives pages
    annotate state names and vote counts with superscript footnote numbers —
    ``<td>Connecticut<sup>3</sup></td>``, a Totals cell ``261<sup>13</sup>``, the
    aggregate column ``Others<sup>1</sup>``. Left in, they break state-name matching
    (``"Connecticut3"`` is not a state) and integer parsing (``int("26113")``).
    Decomposing the element removes the marker *and its digits* cleanly, where a regex
    on the rendered text could eat a real trailing digit. (A non-breaking space left
    between a label and its removed marker is handled separately by
    :func:`_clean_label`.)

    Nothing load-bearing is lost: the footnote *text* lives in Table 2's trailing
    Notes row, which :func:`parse_t2_votes_by_state` already skips, and any real vote
    anomaly a footnote points to (e.g. an elector shortfall) is curated separately as
    a provenance-carrying constant in :mod:`usvote.transform`, not read from the
    marker. Modern pages (2016/2020) carry no ``<sup>``, so this is a no-op there.
    """
    for sup in subtree.find_all("sup"):
        sup.decompose()


def parse_table1(t1_rows: Sequence[Tag]) -> list[CandidateParty]:
    """Parse Table 1's President and Main-Opponent rows into name/party dicts.

    Strips its rows' footnote markers first, so it is self-contained (no reliance on
    a prior table-wide :func:`strip_footnotes` pass).
    """
    for row in t1_rows:
        strip_footnotes(row)
    return [
        parse_t1_candidate_party(t1_rows, ri, rh)
        for ri, rh in zip(T1_ROW_INDS, T1_ROW_HEADERS, strict=True)
    ]


def parse_t1_candidate_party(
    t1_rows: Sequence[Tag], row_ind: int, row_header: str
) -> CandidateParty:
    """Parse one Table 1 row into its candidate name and party code.

    The candidate cell reads ``Name [Party]``; the name has commas and leading/
    trailing ``*`` (footnote markers) stripped. Raises :class:`ParseError` if the
    row's header is not ``row_header`` (the notebook printed and returned
    ``None``).
    """
    header = t1_rows[row_ind].find("th")
    if header is None:
        raise ParseError(
            f"Table 1 row {row_ind} has no <th> header (expected {row_header!r})"
        )
    if header.get_text() != row_header:
        raise ParseError(
            f"Table 1 row {row_ind} header is {header.get_text()!r}, "
            f"expected {row_header!r}"
        )
    cell = t1_rows[row_ind].find("td")
    if cell is None:
        raise ParseError(f"Table 1 row {row_ind} ({row_header}) has no <td> data cell")
    candidate, party = cell.get_text().split(" [")
    return {
        "president_candidate_name": _clean_label(candidate).replace(",", ""),
        # party is "Code]" possibly trailed by a footnote (" *"); drop the bracket
        # then clean, so "[None] *" -> "None" regardless of marker order.
        "president_candidate_party": _clean_label(party.replace("]", "")),
    }


def parse_table2(t2_rows: Sequence[Tag], state_names: Container[str]) -> ParsedTable2:
    """Parse Table 2 into candidate home states and the votes-by-state matrix.

    Row 0 is the header (its ``For President`` colspan sets the candidate count),
    row 1 the candidate/home-state row, and rows 2+ the per-state vote rows. Strips
    its rows' footnote markers first, so it is self-contained (no reliance on a prior
    table-wide :func:`strip_footnotes` pass).
    """
    for row in t2_rows:
        strip_footnotes(row)
    num_candidates = parse_t2_num_candidates(t2_rows[0])
    candidate_state = parse_t2_candidate_state(t2_rows[1], num_candidates)
    votes_by_state = parse_t2_votes_by_state(t2_rows[2:], num_candidates, state_names)
    _assert_candidate_columns_consistent(
        num_candidates, candidate_state, votes_by_state
    )
    return {"candidate_state": candidate_state, "votes_by_state": votes_by_state}


def _assert_candidate_columns_consistent(
    num_candidates: int,
    candidate_state: list[CandidateState],
    votes_by_state: list[StateVotes],
) -> None:
    """Raise unless every parsed row exposes exactly ``num_candidates`` columns.

    The ``For President`` colspan (:func:`parse_t2_num_candidates`) is the single
    hinge every downstream slice keys off. This cross-checks that the candidate/
    home-state row yielded that many candidates and that each votes-by-state record
    carries exactly that many per-candidate vote columns — catching a silent
    window misalignment on an older page (an extra leading cell, a merged header)
    before the melt in :mod:`usvote.transform` maps votes to the wrong candidate.
    """
    if len(candidate_state) != num_candidates:
        raise ParseError(
            f"Table 2 candidate row has {len(candidate_state)} candidates, "
            f"expected {num_candidates} (the 'For President' colspan)"
        )
    for record in votes_by_state:
        vote_cols = sum(1 for key in record if isinstance(key, int))
        if vote_cols != num_candidates:
            raise ParseError(
                f"Table 2 row {record.get('state')!r} has {vote_cols} candidate "
                f"vote columns, expected {num_candidates} (the 'For President' "
                "colspan)"
            )


def parse_t2_num_candidates(header_row: Tag) -> int:
    """Return the candidate-column count from the ``For President`` colspan.

    This is the variable-width hinge: anomaly years with faithless or "Other"
    electors publish extra columns, and every downstream slice keys off this
    count. Raises :class:`ParseError` if the header or its colspan is absent.
    """
    header = header_row.find("th", string="For President")
    if header is None:
        raise ParseError("Table 2 header row has no 'For President' <th>")
    colspan = header.get("colspan")
    if colspan is None:
        raise ParseError("Table 2 'For President' <th> has no colspan")
    # bs4 may hand back a multi-valued attribute as a list; take the first, as
    # scrape._href does for hrefs.
    return int(colspan if isinstance(colspan, str) else colspan[0])


def parse_t2_candidate_state(
    cs_row: Tag, num_candidates: int
) -> list[CandidateState]:
    """Parse the candidate/home-state row into ``num_candidates`` records.

    Each cell reads ``Name, of State``; the "Other" aggregate column has no home
    state and yields ``president_candidate_state=None``. Cells that split a name
    across a ``<br>`` are joined on whitespace before parsing.
    """
    cs_cols = cs_row.find_all("td")
    candidate_state: list[CandidateState] = []
    for ci, cs in enumerate(cs_cols[:num_candidates]):
        text = " ".join(cs.stripped_strings) if cs.find("br") else cs.get_text()
        text = _clean_label(text)
        if text in OTHER_LABELS:
            candidate, state = text, None
        else:
            candidate, state = text.split(" of ")
            candidate = _clean_label(candidate).replace(",", "")
            state = _clean_label(state).replace(",", "")
        candidate_state.append(
            {
                "president_candidate_name": candidate,
                "col_ind": ci + 1,
                "president_candidate_state": state,
            }
        )
    return candidate_state


def parse_t2_votes_by_state(
    states_rows: Iterable[Tag],
    num_candidates: int,
    state_names: Container[str],
) -> list[StateVotes]:
    """Parse the per-state vote rows into ``{state, votes...}`` records.

    Resolving column 0 tells three row kinds apart: a state name (present in
    ``state_names``), a ``Total``/``Totals`` label in column 0, or a
    ``<th>Total(s)</th>`` header row — the last shifts the column window left by
    one since it has no state ``<td>``. Any other row (e.g. the trailing Notes row)
    has no valid state and is skipped, which is the notebook's parse-time check.

    Within a kept row, column 0 of the vote window is the state's electoral-vote
    total (stored under ``'total_electoral_votes'``); the remaining columns are
    per-candidate electoral votes keyed by integer column index, with ``'-'``
    read as ``0``.
    """
    votes_by_state: list[StateVotes] = []
    for sr in states_rows:
        state_cols = sr.find_all("td")
        # An empty `if state_cols` yields col-0 "" which resolves to no state and
        # is skipped — a deliberate softening of the notebook's IndexError on a
        # cell-less row, so a stray blank/separator row can't crash a full run.
        col_0_text = _clean_label(state_cols[0].get_text()) if state_cols else ""
        state: str | None
        if col_0_text in state_names:
            state = col_0_text
            start_ind, end_ind = 1, num_candidates + 2
        elif col_0_text in TOTALS_LABELS:
            state = "Totals"
            start_ind, end_ind = 1, num_candidates + 2
        elif sr.find("th", string=_is_totals_label):
            # A ``<th>`` totals header (no state ``<td>``): the window starts at 0.
            # Older pages use the plural ``<th>Totals</th>`` (e.g. 1824), so match
            # both labels — a singular-only check silently drops the totals row,
            # which empties the whole votes fact downstream (rank derives from it).
            state = "Totals"
            start_ind, end_ind = 0, num_candidates + 1
        else:
            state = None
        # Only keep the row if column 0 resolved to a valid state (or the totals
        # row): this validates the parse and skips the trailing Notes row.
        if state is not None:
            state_votes: StateVotes = {"state": state}
            for si, sv in enumerate(state_cols[start_ind:end_ind]):
                votes = sv.get_text().strip()  # strip() also clears a footnote nbsp
                key: str | int = "total_electoral_votes" if si == 0 else si
                if votes == "-":
                    state_votes[key] = 0
                    continue
                try:
                    state_votes[key] = int(votes)
                except ValueError as exc:
                    # A non-numeric electoral-vote cell is an un-modelled vote
                    # notation, e.g. 1868's contested "(9)" for Georgia. Fail with a
                    # typed, located error instead of a bare int() ValueError.
                    raise ParseError(
                        f"Table 2 row {state!r}: non-numeric electoral-vote cell "
                        f"{votes!r} (column {key}) — an un-modelled vote notation"
                    ) from exc
            votes_by_state.append(state_votes)
    return votes_by_state
