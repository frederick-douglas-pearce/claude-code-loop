"""Parse stage — turn saved UCSB election pages into structured per-year records.

The pure half of the UCSB ingest (E4-S2, #35): it takes HTML already fetched to the
local snapshot by :mod:`usvote.ucsb.scrape` and does no network access, which makes it
fixture-testable offline. Output is a list of :class:`ParsedUCSBYear` records that
E4-S3 (#36) feeds into DataFrames and reconciles against the Electoral College spine.

The whole design rests on one structural finding from the corpus survey
(``docs/ucsb-html-formats.md``): **every data row is ``W = 2 + 3g`` single-colspan
cells** — ``STATE | TOTAL VOTE | (Votes, %, EV) x g``. Only the *header* shape and the
candidate-group count ``g`` vary across eras. So there is exactly one body parser, and
all per-era branching is confined to :func:`detect_layout` and
:func:`parse_candidate_columns`. The invariant worth protecting:
**:func:`parse_state_data_row` never reads ``layout.kind``.**

Six header layouts are modeled — L0 (summary-only, 1789-1820), L1 (stacked 3-row),
L1b (1836: no header colspans at all), L1c (1976: header *narrower* than data rows),
L2 (names-first, nested summary) and L3 (inline 2-row). They are **not chronologically
ordered**: 1936 reverts to L1 mid-L2 block, and 1964/1972/1984/1988 are L2 interleaved
among L3. Branch on detected shape, **never on year** — the one exception being the
year-conditional in :func:`parse_election_year` that decides whether an absent state
table is legitimate (pre-1824) or a regression.

Two conventions this module holds to, both from D024:

- **Absence is never zero.** A candidate not on a state's ballot is ``votes=None``,
  spelled ``--`` (1852+) or a lone U+00A0 (earlier). A literal ``0`` appears nowhere in
  a state-row vote column in the entire corpus, so :func:`validate_year` rejects one.
  Absence is read from the **Votes** cell only — never the percent column, which is
  published pre-rounded and prints ``0.0`` for genuine small counts (1948 California:
  1,228 votes at ``0.0``).
- **Nothing unclassifiable passes silently.** Rows that are not data, totals, a
  legislature status row, or a member of the enumerated benign-skip allowlist raise
  :class:`UCSBParseError`. There is deliberately no ``unknown`` bucket.

Scope note (D024, clarified for #35): the only popular-vote status readable from the
markup is ``legislature_chosen``. ``not_participating`` has **no markup whatsoever** —
the state's row is simply absent — and ``popular_vote`` is the roster's residual, so
both are assigned in #36 against the EC spine. This parser is deliberately
**roster-free**: it emits verbatim cleaned state labels and classifies rows purely
structurally. **State**-label canonicalization is E4-S3's (#36,
:data:`usvote.ucsb.transform.UCSB_STATE_RECONCILIATIONS`); #38 keeps **candidate**-name
reconciliation.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from enum import Enum
from typing import NamedTuple, TypedDict

from bs4 import BeautifulSoup
from bs4.element import Tag


class UCSBParseError(RuntimeError):
    """A UCSB page matched no modeled layout, or violated a parse invariant.

    Deliberately loud. The notebook-era habit of returning ``None`` on a malformed
    table poisoned everything downstream with a shape that looked merely empty; a
    typed, message-carrying exception names what was wrong and where.
    """


# The page wrapper that scopes away UCSB's Highcharts GeoJSON blob, which otherwise
# contributes stray markup to a whole-document search.
MAIN_SECTION_ID = "block-system-main"

# Column-0 labels marking the totals row. SINGULAR "Total" is real: 1864 and 1944 use
# it. A ``== "Totals"`` test drops the totals row on those years and silently no-ops
# the sum validator, which is the whole point of having one.
#
# Every label constant in this module is stored UPPERCASE and compared through
# :func:`_matches_label`. UCSB's casing is not stable across eras (1940 alone switches
# STATE -> STATES), so a case-sensitive comparison here is a latent format-drift bug
# rather than a style choice.
TOTALS_LABELS = frozenset({"TOTAL", "TOTALS"})

# Every one of the 18 legislature-chosen rows in the corpus carries this phrase
# (verified across all 60 pages). The prose is captured VERBATIM and left unparsed —
# elector counts inside it are not extracted, because the Electoral College spine is
# the National Archives, not UCSB (D006).
LEGISLATURE_MARKER = "electors chosen by state legislature"

# The status value this parser can emit. It is the ONLY one readable from markup; see
# the module docstring's scope note.
STATUS_LEGISLATURE_CHOSEN = "legislature_chosen"

# A Votes cell holding one of these means "candidate not on this state's ballot" ->
# ``None``, never 0. "-" (a single hyphen) is a real typo in the 1836 Rhode Island
# row; modeling it as a set rather than a literal is what absorbs that.
ABSENT_VOTE_TOKENS = frozenset({"--", "-", "---"})

# Maine and Nebraska split electoral votes by district, so UCSB emits sub-rows beneath
# the statewide row. They are structurally identical to state rows but their votes are
# a PARTITION of the parent's, so summing them double-counts the national popular vote
# by ~1.5M. They land in their own list for that reason (see ``cd_rows``).
CD_ROW_PATTERN = re.compile(r"^CD-\d+$", re.IGNORECASE)

# Aggregate "all other candidates" columns. Flagged rather than dropped: #36 decides
# whether an aggregate column is in scope, and it cannot decide what it cannot see.
OTHER_LABELS = frozenset({"OTHERS", "OTHER", "VARIOUS", "OTHERS (VARIOUS)"})

# 1789-1820: electors were chosen by legislature nearly everywhere and UCSB publishes
# no state table at all. These are the ONLY years for which a missing table is
# legitimate rather than a scrape/format regression.
#
# Note the cadence: the first inauguration year is 1789 but the quadrennial series
# starts at 1792, so this is NOT ``range(1789, 1824, 4)`` — that yields 1793/1797/...
# and matches no real election. Verified against the snapshot: exactly these nine
# pages carry no state table.
NO_POPULAR_VOTE_YEARS = frozenset({1789, *range(1792, 1824, 4)})

# Header cell texts that identify the STATE column. 1940 uses the plural.
STATE_HEADER_LABELS = frozenset({"STATE", "STATES"})

# The summary block's header cells. On most years the summary sits above the state
# block (and so falls outside the body slice), but on 1928/1932/1940/1944/1948/1952/
# 1956/1972/1988 it is appended as SIBLING ROWS BELOW the totals row of the very same
# table. Those rows are neither data nor benign prose, so the body has to be truncated
# where they begin — otherwise they hit the terminal raise.
SUMMARY_HEADER_LABELS = frozenset({"PARTY", "NOMINEES"})

# The units-row marker used to tell an inline header (L1c/L3, where the STATE row IS
# the units row) from a stacked one (L1/L1b/L2, where units are a separate row).
UNITS_VOTES_LABELS = frozenset({"VOTES"})

# W = 2 + 3g, so the narrowest structurally-possible data row (g=1) is 5 cells.
MIN_DATA_WIDTH = 5

# Rows that carry no data grain and are safe to skip. This is an ENUMERATED ALLOWLIST,
# not a catch-all: anything not matched here and not otherwise classified raises. D024
# rejects an "unknown" bucket by name, and a blanket skip is exactly that bucket.
BENIGN_PROSE_PATTERNS = (
    re.compile(r"last update", re.IGNORECASE),
    re.compile(r"click on (the )?state", re.IGNORECASE),
    re.compile(r"elected by the (House|Senate)", re.IGNORECASE),
    re.compile(r"did not participate", re.IGNORECASE),
    re.compile(r"^source[s]?\b", re.IGNORECASE),
)

# Tolerance for the published-percent cross-check, in percentage points. Generous on
# purpose: UCSB rounds half-up to one decimal (25,000/80,000 -> 31.3, where Python's
# banker's rounding gives 31.2), and some years compute the percent against a slightly
# different denominator. The check exists to catch a COLUMN-WINDOW SHIFT of the 1976
# kind, which moves a cell by whole percentage points, not to audit UCSB's arithmetic.
PERCENT_TOLERANCE = 0.5

# Fraction of a year's cells that may disagree with their published percent before the
# parse is presumed misaligned. A column-window shift misaligns essentially every row,
# so the real signal is a rate near 1.0; isolated source typos sit near zero (the worst
# real year, 1872, is ~2%). Set well clear of both.
PERCENT_MISMATCH_RATE = 0.25


class RowKind(Enum):
    """What a body row is, decided structurally — never from a state-name roster."""

    STATE_DATA = "state_data"
    CD = "cd"
    TOTALS = "totals"
    STATUS = "status"
    SKIP_BENIGN = "skip_benign"


class UCSBLayout(NamedTuple):
    """The shape discovered from a page's header. The only per-era branch point.

    ``kind`` is carried for provenance and error messages. Downstream, only
    ``group_count`` and ``data_width`` reach the body parser.
    """

    kind: str
    group_count: int
    data_width: int
    header_end: int  # first body-row index; rows[:header_end] are header/summary
    name_row_ind: int
    party_row_ind: int | None  # None when the layout has no separate party row


class UCSBCandidateColumn(TypedDict):
    """One candidate column in the state table."""

    col_ind: int  # 1-based; the key vote cells carry over
    name: str
    party: str | None  # NON-AUTHORITATIVE: D018 keeps party truth on the EC spine
    is_other: bool


class UCSBVoteCell(TypedDict):
    """One candidate's numbers for one state."""

    col_ind: int
    votes: int | None  # None == not on the ballot. NEVER 0 (D024 §2).
    percent: float | None  # published and pre-rounded; NEVER an absence signal


class UCSBStateRow(TypedDict):
    """A state's popular-vote row."""

    state_label: str  # verbatim, whitespace- and '*'-cleaned only; NOT canonicalized
    state_total_votes: int
    cells: list[UCSBVoteCell]


class UCSBCDRow(UCSBStateRow):
    """A congressional-district sub-row, kept out of the state grain."""

    # Parent linkage exists only as document order and is destroyed at parse time, so
    # it has to be captured here — it is not recoverable downstream.
    parent_state_label: str


class UCSBStatusRow(TypedDict):
    """A state with no popular vote because its legislature chose the electors."""

    state_label: str
    pv_status: str  # always STATUS_LEGISLATURE_CHOSEN; see the module scope note
    note: str  # verbatim UCSB prose, UNPARSED (D024 §5, D006)


class ParsedUCSBYear(TypedDict):
    """Everything #36 needs from one election page."""

    year: int
    layout: str
    group_count: int
    candidates: list[UCSBCandidateColumn]
    state_rows: list[UCSBStateRow]
    cd_rows: list[UCSBCDRow]
    status_rows: list[UCSBStatusRow]
    totals: UCSBStateRow | None


# --------------------------------------------------------------------------------
# Cell / row primitives
# --------------------------------------------------------------------------------


def own_rows(table: Tag) -> list[Tag]:
    """The table's own ``<tr>`` elements, excluding any nested table's.

    ``find_all`` recurses, so on the years whose summary block is a NESTED table
    (1928 onward) a plain ``table.find_all("tr")`` silently leaks summary rows into
    the body. This is risk 1 in the survey and the single most likely way to get a
    quietly-wrong answer rather than a crash.
    """
    return [row for row in table.find_all("tr") if row.find_parent("table") is table]


def _own_cells(row: Tag) -> list[Tag]:
    """The row's own ``<td>`` elements, excluding any nested table's.

    The mirror of :func:`own_rows`, and needed for the same reason: on a nested-summary
    page the wrapper row's ``find_all("td")`` descends into the inner table.
    """
    return [cell for cell in row.find_all("td") if cell.find_parent("tr") is row]


def _cell_texts(row: Tag) -> list[str]:
    """The row's own cell texts, NBSP-normalized and stripped.

    U+00A0 is how UCSB spells an empty cell — not ``&nbsp;`` and not ``""`` — and
    pre-1852 it is also how it spells "candidate not on this state's ballot".
    """
    return [
        cell.get_text().replace("\xa0", " ").strip() for cell in _own_cells(row)
    ]


def _clean_label(text: str) -> str:
    """Trim whitespace and the footnote asterisks UCSB appends to some state labels.

    Deliberately minimal. Canonicalizing labels (``Dist. of Col.``, the 1852
    ``New jersey`` typo) belongs to E4-S3 (#36) — see
    :data:`usvote.ucsb.transform.UCSB_STATE_RECONCILIATIONS`; doing it here would bury a
    mapping decision inside the parse stage. (D024's 2026-07-18 clarification moved the
    **state**-name half there from #38, because #36's roster is keyed on ``dwh.state``'s
    canonical PK and its two-way assert is meaningless without it. #38 keeps
    **candidate**-name reconciliation.)
    """
    return text.strip().strip("*").strip()


def _colspan(cell: Tag) -> int:
    """A cell's colspan as an int, defaulting to 1."""
    raw = cell.get("colspan")
    if raw is None:
        return 1
    try:
        return int(str(raw))
    except ValueError:
        return 1


def _parse_int(text: str) -> int | None:
    """Parse a comma-grouped integer; ``None`` if the cell is not a plain number."""
    stripped = text.replace(",", "").strip()
    return int(stripped) if re.fullmatch(r"\d+", stripped) else None


def _parse_vote_cell(text: str, *, where: str) -> int | None:
    """Parse a Votes cell: an int, or ``None`` for an off-the-ballot candidate.

    ``None`` means **not on the ballot**, which is categorically different from zero
    votes and must never be conflated with it (D024 §2). Anything that is neither a
    number nor a modeled absence token raises rather than degrading to ``None`` —
    otherwise a format drift would look exactly like a candidate who wasn't running.
    """
    cleaned = text.strip()
    if not cleaned or cleaned in ABSENT_VOTE_TOKENS:
        return None
    value = _parse_int(cleaned)
    if value is None:
        raise UCSBParseError(f"unparseable Votes cell {text!r} in {where}")
    return value


def _parse_percent_cell(text: str) -> float | None:
    """Parse a published percent cell; ``None`` when blank or absent.

    Never consulted for absence — see :data:`PERCENT_TOLERANCE` and the module
    docstring. A malformed percent is tolerated as ``None`` (unlike a malformed Votes
    cell) because percent is a cross-check, not data we load.
    """
    cleaned = text.strip().rstrip("%").strip()
    if not cleaned or cleaned in ABSENT_VOTE_TOKENS:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _matches_label(text: str, labels: frozenset[str]) -> bool:
    """True if ``text`` cleans and upper-cases into ``labels``.

    The single comparison path for every header/label constant in this module. Having
    one keeps casing conventions from diverging between structurally identical lookups
    — which they had, with STATE folded and the summary/totals labels not.
    """
    return _clean_label(text).upper() in labels


def _has_state_header(row: Tag) -> bool:
    """True if the row carries a ``STATE``/``STATES`` header cell."""
    return any(_matches_label(text, STATE_HEADER_LABELS) for text in _cell_texts(row))


# --------------------------------------------------------------------------------
# Table location
# --------------------------------------------------------------------------------


def select_results_table(soup: BeautifulSoup) -> Tag | None:
    """Find the state-results table, or ``None`` when the page has none (L0).

    The rule is **"the table containing an own-row with a ``STATE``/``STATES`` cell"**.
    The obvious alternative — widest table in the section — is WRONG: on the 1976 page
    the summary rows are 9 cells wide and the data rows only 8, so widest-table picks
    the summary block and every downstream column is read from the wrong table.

    Verified across all 60 saved pages: this selects exactly one table on each of the
    51 popular-vote years and zero on all nine 1789-1820 pages, so it doubles as the
    L0 detector.
    """
    section = soup.find(id=MAIN_SECTION_ID) or soup
    hits = [
        table
        for table in section.find_all("table")
        if any(_has_state_header(row) for row in own_rows(table))
    ]
    if not hits:
        return None
    if len(hits) > 1:
        raise UCSBParseError(
            f"expected one results table, found {len(hits)}; the page layout changed"
        )
    return hits[0]


# --------------------------------------------------------------------------------
# Shape discovery — ALL per-era branching lives below, and nowhere else
# --------------------------------------------------------------------------------


def _detect_group_count(rows: list[Tag]) -> tuple[int, int]:
    """Discover ``(group_count, data_width)`` from the data rows, never the header.

    Takes the modal width of rows whose cells are all single-colspan, **restricted
    first to structurally-possible data widths** (``W = 2 + 3g``). Both halves matter:

    - Deriving ``g`` from header colspans breaks on 1836, which has none; deriving it
      from header *width* breaks on 1976, whose header is narrower than its data.
    - Filtering to valid widths before taking the mode is what keeps a page whose
      summary rows tie with (or outnumber) its data rows from picking the summary
      width. A bare mode picks 9 on such a page, and ``(9-2)//3`` floor-divides to a
      plausible-looking ``g=2`` instead of failing — the worst outcome available.

    Verified against all 51 real popular-vote years with zero mismatches.
    """
    all_cells = [_own_cells(row) for row in rows]
    widths = Counter(
        len(cells)
        for cells in all_cells
        if cells and all(_colspan(cell) == 1 for cell in cells)
    )
    valid = {
        width: count
        for width, count in widths.items()
        if width >= MIN_DATA_WIDTH and (width - 2) % 3 == 0
    }
    if not valid:
        raise UCSBParseError(
            f"no structurally-valid data width (W = 2 + 3g) among {dict(widths)}"
        )
    data_width = max(valid, key=lambda width: (valid[width], width))
    return (data_width - 2) // 3, data_width


def _is_name_row(row: Tag, group_count: int) -> bool:
    """True if the row looks like the candidate-name row for ``group_count`` columns.

    Counts non-empty own cells, which absorbs the leading blank spacer cell that the
    names-first layouts (L1c/L2/L3) put in front of the names.
    """
    return sum(1 for text in _cell_texts(row) if text) == group_count


def detect_layout(rows: list[Tag]) -> UCSBLayout:
    """Identify the header layout and the column geometry.

    Test order matters and each test is chosen to be unambiguous given the survey.
    The subtle one is L3 vs L1c: 1976's STATE row *is* its units row, so the "contains
    ``Votes``" test is true for both. The discriminator is ``len(state_row) ==
    data_width`` — 7 against 8 for 1976 — without which L1c is unreachable and every
    1976 candidate column is read one position to the left.
    """
    group_count, data_width = _detect_group_count(rows)

    state_inds = [ind for ind, row in enumerate(rows) if _has_state_header(row)]
    if not state_inds:
        raise UCSBParseError("no STATE/STATES header row in the selected table")
    ind = state_inds[0]

    def above(offset: int, kind: str) -> int:
        """Index ``offset`` rows above the STATE row, refusing to run off the top.

        Without this, ``ind - 1`` / ``ind - 2`` index NEGATIVELY on a table whose
        STATE row sits near the top, and Python silently wraps to rows at the END of
        the table. That does not crash — it reads a trailing data or footnote row as
        the candidate-name row, so a whole year's candidates come out mislabelled
        with no error. Refuse loudly instead.
        """
        if ind - offset < 0:
            raise UCSBParseError(
                f"{kind}: STATE row at index {ind} has no header row {offset} above "
                f"it; the page is missing the expected candidate header"
            )
        return ind - offset

    cells = _own_cells(rows[ind])
    width = len(cells)
    has_units = any(
        _matches_label(text, UNITS_VOTES_LABELS) for text in _cell_texts(rows[ind])
    )
    has_colspan = any(_colspan(cell) > 1 for cell in cells)

    if has_units and width == data_width:
        # L3 — inline 2-row header; name and party fused in one cell above.
        return UCSBLayout("L3", group_count, data_width, ind + 1, above(1, "L3"), None)
    if has_units and width < data_width:
        # L1c — 1976 only. Three stacked rows (names / parties+TOTAL VOTES / STATE+
        # units), and the STATE row carries no TOTAL VOTE header at all, which is why
        # it is 1 + 3g wide against data rows of 2 + 3g.
        return UCSBLayout(
            "L1c", group_count, data_width, ind + 1, above(2, "L1c"), above(1, "L1c")
        )
    if not has_colspan:
        # L1b — 1836 only; stacked header carrying no colspans at all.
        return UCSBLayout("L1b", group_count, data_width, ind + 3, ind + 1, ind)
    if ind > 0 and _is_name_row(rows[ind - 1], group_count):
        # L2 — names-first; the name row precedes the STATE row.
        return UCSBLayout("L2", group_count, data_width, ind + 2, ind - 1, ind)
    if ind + 1 < len(rows) and _is_name_row(rows[ind + 1], group_count):
        # L1 — the common stacked 3-row header: STATE / names / units.
        return UCSBLayout("L1", group_count, data_width, ind + 3, ind + 1, ind)

    raise UCSBParseError(
        f"unrecognized header layout: STATE row at index {ind} is {width} cells "
        f"(data width {data_width}, g={group_count}), colspans={has_colspan}, "
        f"units_inline={has_units}"
    )


# --------------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------------


def _split_name_and_party(cell: Tag) -> tuple[str, str | None]:
    """Split a header cell into ``(name, party)``.

    L3 fuses the two into one cell separated by a ``<br>``; the stacked layouts put
    the party on its own row. Walking ``stripped_strings`` handles both, and ignores
    the ``<img>`` winner markers that appear inside some header cells.
    """
    parts = [part for part in cell.stripped_strings if part.strip()]
    if not parts:
        raise UCSBParseError("empty candidate header cell")
    return parts[0], (parts[1] if len(parts) > 1 else None)


def parse_candidate_columns(
    rows: list[Tag], layout: UCSBLayout
) -> list[UCSBCandidateColumn]:
    """Read the candidate columns, left to right, from the header.

    ``col_ind`` is 1-based and is the key every :class:`UCSBVoteCell` carries, so a
    column's identity survives the melt into long form downstream.
    """
    name_cells = [
        cell
        for cell in _own_cells(rows[layout.name_row_ind])
        if cell.get_text().replace("\xa0", " ").strip()
    ]
    if len(name_cells) != layout.group_count:
        raise UCSBParseError(
            f"{layout.kind}: found {len(name_cells)} candidate name cells, "
            f"expected {layout.group_count} from the data width"
        )

    parties: list[str | None] | None = None
    if layout.party_row_ind is not None:
        # The party row is the STATE row itself: STATE | TOTAL VOTE | party x g.
        party_cells = _own_cells(rows[layout.party_row_ind])[2:]
        if len(party_cells) != layout.group_count:
            raise UCSBParseError(
                f"{layout.kind}: found {len(party_cells)} party cells, "
                f"expected {layout.group_count}"
            )
        parties = [_clean_label(cell.get_text()) or None for cell in party_cells]

    columns: list[UCSBCandidateColumn] = []
    for ind, cell in enumerate(name_cells):
        name, fused_party = _split_name_and_party(cell)
        name = _clean_label(name)
        columns.append(
            UCSBCandidateColumn(
                col_ind=ind + 1,
                name=name,
                party=parties[ind] if parties is not None else fused_party,
                is_other=name.upper() in OTHER_LABELS,
            )
        )
    return columns


# --------------------------------------------------------------------------------
# Body — layout-agnostic below this line
# --------------------------------------------------------------------------------


def _find_body_end(rows: list[Tag], header_end: int) -> int:
    """Index where the body stops — the start of a trailing summary block, or the end.

    Nine years append their summary block as sibling rows beneath the totals row of
    the same table, so ``own_rows`` cannot separate them and the modal-width rule does
    not reach them (they sit after the data). Truncating at the summary header is what
    keeps them from reaching :func:`classify_row`'s terminal raise.
    """
    for ind in range(header_end, len(rows)):
        labels = {_clean_label(text).upper() for text in _cell_texts(rows[ind])}
        if labels.issuperset(SUMMARY_HEADER_LABELS):
            return ind
    return len(rows)


def _is_benign_skip(row: Tag) -> bool:
    """True for rows that provably carry no data grain.

    An enumerated allowlist, not a fallback. Three shapes qualify:

    1. every cell blank — the separator bars, and the all-NBSP row on the 1824 and
       1836 pages;
    2. a single full-width cell — separators and footnote prose, which cannot be a
       data row because a data row needs ``W >= 5`` cells;
    3. text matching a known prose pattern (``Last update:``, the House-election
       footnote, and friends).

    Anything else reaching :func:`classify_row`'s fallthrough raises.
    """
    texts = _cell_texts(row)
    if not any(texts):
        return True
    if len(_own_cells(row)) <= 1:
        return True
    return any(
        pattern.search(text) for text in texts for pattern in BENIGN_PROSE_PATTERNS
    )


def classify_row(row: Tag, layout: UCSBLayout) -> RowKind:
    """Decide what a body row is. Structural only — no state-name roster involved.

    Order is load-bearing in two places:

    - **STATUS first.** A legislature row is two cells (label + wide-colspan prose)
      and would otherwise fall through to the benign allowlist and vanish.
    - **TOTALS before the width and integer gates.** Classifying totals last means a
      malformed totals row is skipped, ``totals`` stays ``None``, and the sum
      validator silently no-ops — losing exactly the check most likely to catch the
      bug that malformed the row.
    """
    cells = _own_cells(row)
    texts = _cell_texts(row)

    if len(cells) == 2 and _colspan(cells[1]) >= layout.data_width - 1:
        if LEGISLATURE_MARKER not in texts[1].lower():
            raise UCSBParseError(
                f"unmodeled full-width 2-cell row: {texts[0]!r} / {texts[1]!r:.80}"
            )
        return RowKind.STATUS

    label = _clean_label(texts[0]) if texts else ""
    if label.upper() in TOTALS_LABELS:
        return RowKind.TOTALS

    if len(texts) == layout.data_width and _parse_int(texts[1]) is not None:
        return RowKind.CD if CD_ROW_PATTERN.match(label) else RowKind.STATE_DATA

    if _is_benign_skip(row):
        return RowKind.SKIP_BENIGN

    raise UCSBParseError(
        f"unclassifiable row ({len(texts)} cells, data width {layout.data_width}): "
        f"{texts[:4]}"
    )


def parse_status_row(row: Tag) -> UCSBStatusRow:
    """Parse a legislature-chosen row, keeping its prose verbatim and unparsed.

    The prose often names elector splits ("15 to Fictitious; 14 to Notional"). Those
    are NOT extracted: the Electoral College is sourced from the National Archives
    spine (D006), and a second, weaker EC number parsed out of UCSB prose would be a
    liability the moment the two disagreed.
    """
    texts = _cell_texts(row)
    return UCSBStatusRow(
        state_label=_clean_label(texts[0]),
        pv_status=STATUS_LEGISLATURE_CHOSEN,
        note=texts[1].strip(),
    )


def parse_state_data_row(row: Tag, layout: UCSBLayout) -> UCSBStateRow:
    """Parse one data row into a state record.

    The single body parser the survey's ``W = 2 + 3g`` finding buys us. It reads only
    ``layout.group_count`` and ``layout.data_width`` — **never ``layout.kind``** — so
    identical cell text produces identical output regardless of the era the row came
    from. The EV cell at offset ``4 + 3i`` is skipped by design (D006).
    """
    texts = _cell_texts(row)
    label = _clean_label(texts[0]) if texts else "?"
    if len(texts) != layout.data_width:
        raise UCSBParseError(
            f"row {label!r} has {len(texts)} cells, expected {layout.data_width}"
        )
    total = _parse_int(texts[1])
    if total is None:
        raise UCSBParseError(f"row {label!r} has unparseable TOTAL VOTE {texts[1]!r}")

    cells = [
        UCSBVoteCell(
            col_ind=ind + 1,
            votes=_parse_vote_cell(texts[2 + 3 * ind], where=f"row {label!r}"),
            percent=_parse_percent_cell(texts[3 + 3 * ind]),
        )
        for ind in range(layout.group_count)
    ]
    return UCSBStateRow(state_label=label, state_total_votes=total, cells=cells)


# --------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------


def _assert_never_zero(parsed: ParsedUCSBYear) -> None:
    """No vote cell may be a literal 0 (D024 §2), corpus-verified.

    Absence is ``None``. A ``0`` in the output therefore means something coerced an
    absence token into a number — the exact bug that would quietly deflate a
    candidate's national total while every sum still reconciled.
    """
    for row in [*parsed["state_rows"], *parsed["cd_rows"]]:
        for cell in row["cells"]:
            if cell["votes"] == 0:
                raise UCSBParseError(
                    f"{parsed['year']}: literal 0 votes for column {cell['col_ind']} "
                    f"in {row['state_label']!r}; absence must be None, never 0"
                )


def _assert_no_residual_cells(parsed: ParsedUCSBYear) -> None:
    """Every row must account for exactly ``group_count`` columns (D024 §7).

    The within-page half of the residual guard. The cross-page two-way roster assert
    is #36's, because it needs the EC spine this stage deliberately cannot see.
    """
    expected = parsed["group_count"]
    if len(parsed["candidates"]) != expected:
        raise UCSBParseError(
            f"{parsed['year']}: {len(parsed['candidates'])} candidate columns from the "
            f"header, {expected} from the data width"
        )
    for row in [*parsed["state_rows"], *parsed["cd_rows"]]:
        if len(row["cells"]) != expected:
            raise UCSBParseError(
                f"{parsed['year']}: {row['state_label']!r} has {len(row['cells'])} "
                f"cells, expected {expected}"
            )


def _assert_sums_reconcile(parsed: ParsedUCSBYear) -> None:
    """State rows must sum exactly to the totals row — with CD rows EXCLUDED.

    Exact equality, not a tolerance: UCSB's own totals are internally consistent, so
    any drift is our bug. CD rows are excluded because their votes partition the
    parent state's rather than adding to it; including them inflates the national
    popular vote by ~1.5M across the split-EV years.
    """
    totals = parsed["totals"]
    if totals is None:
        raise UCSBParseError(f"{parsed['year']}: no totals row found")

    summed = sum(row["state_total_votes"] for row in parsed["state_rows"])
    if summed != totals["state_total_votes"]:
        raise UCSBParseError(
            f"{parsed['year']}: TOTAL VOTE sums to {summed:,}, totals row says "
            f"{totals['state_total_votes']:,}"
        )

    for ind, total_cell in enumerate(totals["cells"]):
        name = parsed["candidates"][ind]["name"]
        column = sum(
            cell["votes"] or 0
            for row in parsed["state_rows"]
            for cell in row["cells"]
            if cell["col_ind"] == total_cell["col_ind"]
        )
        if total_cell["votes"] is None:
            # An absent totals cell is only consistent with a candidate who polled
            # nowhere. Skipping the column outright — as this used to — conflates
            # "nothing to check" with "checked and fine", and silently exempts an
            # entire candidate from the sum validator. Verified: no year in the
            # corpus has an absent totals cell, so this can only fire on new markup.
            if column:
                raise UCSBParseError(
                    f"{parsed['year']}: column {total_cell['col_ind']} ({name}) has no "
                    f"totals value, but its state rows sum to {column:,} — the totals "
                    f"row and the data disagree about whether this candidate ran"
                )
            continue
        if column != total_cell["votes"]:
            raise UCSBParseError(
                f"{parsed['year']}: column {total_cell['col_ind']} ({name}) sums to "
                f"{column:,}, totals row says {total_cell['votes']:,}"
            )


def _assert_percent_consistent(parsed: ParsedUCSBYear) -> None:
    """Cross-check the published percents in AGGREGATE, not cell by cell.

    The cheapest independent detector for a column-window shift of the 1976 kind: a
    shifted window puts one candidate's votes beside another's percent. The key
    property is that a shift is *systematic* — it misaligns essentially every row in
    the year — whereas UCSB's own occasional typos hit a single cell.

    So this asserts on the mismatch RATE. Raising per cell instead would fail three
    years on defects that are demonstrably in the source, not in the parse:

    - **1860 Vermont** publishes ``4.16`` twice, against 8,748 and 1,859 votes. The
      row's four candidates sum to exactly its 44,712 TOTAL VOTE, so the columns are
      provably aligned and the duplicated percent is UCSB's slip.
    - **1968 Utah** publishes ``31.1`` where 156,665/422,568 is 37.1 — a transposed
      digit; that row's candidates also reconcile against its total.
    - **1872 Kentucky** publishes percents that sum to exactly 100.0 while the votes
      leave a 2,374-vote residual, so UCSB computed them on a different denominator.

    This is the only job the percent column has; it is never consulted for absence.
    """
    mismatched = 0
    compared = 0
    worst: str | None = None
    for row in parsed["state_rows"]:
        total = row["state_total_votes"]
        if total <= 0:
            continue
        for cell in row["cells"]:
            if cell["votes"] is None or cell["percent"] is None:
                continue
            compared += 1
            computed = cell["votes"] / total * 100
            if abs(computed - cell["percent"]) > PERCENT_TOLERANCE:
                mismatched += 1
                if worst is None:
                    worst = (
                        f"{row['state_label']!r} column {cell['col_ind']}: "
                        f"{cell['votes']:,}/{total:,} = {computed:.1f}%, "
                        f"page publishes {cell['percent']}%"
                    )
    if not compared:
        # No comparable cell means this detector did not run at all. Since it is the
        # only cheap check for a column-window shift, passing silently here would
        # quietly downgrade the guarantee the docstring above advertises — so a year
        # with votes but no readable percents is itself the error. (All 51 corpus
        # years compare every populated cell, so this fires only on format drift.)
        if any(
            cell["votes"] is not None
            for row in parsed["state_rows"]
            for cell in row["cells"]
        ):
            raise UCSBParseError(
                f"{parsed['year']}: no percent cell could be read, so the "
                f"column-alignment cross-check could not run; the percent column's "
                f"format has probably changed"
            )
        return

    if mismatched / compared > PERCENT_MISMATCH_RATE:
        raise UCSBParseError(
            f"{parsed['year']}: {mismatched}/{compared} cells disagree with their "
            f"published percent — the column window is probably misaligned "
            f"(first: {worst})"
        )


def _assert_one_status_per_state(parsed: ParsedUCSBYear) -> None:
    """A state may be a popular-vote row or a legislature row, never both.

    ``pv_state_status`` is keyed ``(source, year, state)``, so a state carrying both a
    vote total and a ``legislature_chosen`` status hands #36 two irreconcilable facts
    for one key. The contradiction originates here and is cheap to reject here, rather
    than surfacing downstream as a merge conflict with no way back to the markup.
    """
    voting = [row["state_label"] for row in parsed["state_rows"]]
    overlap = {row["state_label"] for row in parsed["status_rows"]}.intersection(voting)
    if overlap:
        raise UCSBParseError(
            f"{parsed['year']}: {sorted(overlap)} appear as both popular-vote rows and "
            f"legislature-chosen rows; a state cannot be in two statuses at once"
        )

    duplicates = {label for label in voting if voting.count(label) > 1}
    if duplicates:
        raise UCSBParseError(
            f"{parsed['year']}: duplicate state rows for {sorted(duplicates)}; the "
            f"state grain is one row per state"
        )


def validate_year(parsed: ParsedUCSBYear) -> None:
    """Run every within-page invariant, raising on the first violation.

    Deliberately all within-page. Anything needing the state roster — missing-state
    detection, the two-way roster assert, ``popular_vote``/``not_participating``
    assignment — is E4-S3's (#36) by construction: an absent row is invisible here.
    """
    _assert_no_residual_cells(parsed)
    _assert_never_zero(parsed)
    _assert_one_status_per_state(parsed)
    _assert_sums_reconcile(parsed)
    _assert_percent_consistent(parsed)


# --------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------


def parse_election_year(html: str, year: int) -> ParsedUCSBYear | None:
    """Parse one saved UCSB election page.

    Returns ``None`` **only** for the 1789-1820 years that legitimately have no
    popular vote. The year-conditional lives here rather than in
    :func:`detect_layout` so that shape discovery stays year-blind:

    - no state table, year in :data:`NO_POPULAR_VOTE_YEARS` -> ``None``
    - no state table, year >= 1824 -> raise (a scrape or format regression)
    - state table present, year in :data:`NO_POPULAR_VOTE_YEARS` -> raise (UCSB
      restructured something; guessing here is exactly the silent failure D024 §4
      rules out)
    """
    table = select_results_table(BeautifulSoup(html, "html.parser"))

    if table is None:
        if year in NO_POPULAR_VOTE_YEARS:
            return None
        raise UCSBParseError(
            f"{year}: no state-results table, but {year} should have a popular vote"
        )
    if year in NO_POPULAR_VOTE_YEARS:
        raise UCSBParseError(
            f"{year}: a state-results table is present, but {year} predates any "
            f"recorded popular vote; the page layout changed"
        )

    rows = own_rows(table)
    layout = detect_layout(rows)

    state_rows: list[UCSBStateRow] = []
    cd_rows: list[UCSBCDRow] = []
    status_rows: list[UCSBStatusRow] = []
    totals: UCSBStateRow | None = None
    parent_label: str | None = None

    for row in rows[layout.header_end : _find_body_end(rows, layout.header_end)]:
        kind = classify_row(row, layout)
        if kind is RowKind.SKIP_BENIGN:
            continue
        if kind is RowKind.STATUS:
            status_rows.append(parse_status_row(row))
            continue

        record = parse_state_data_row(row, layout)
        if kind is RowKind.TOTALS:
            if totals is not None:
                raise UCSBParseError(f"{year}: more than one totals row")
            totals = record
        elif kind is RowKind.CD:
            if parent_label is None:
                raise UCSBParseError(
                    f"{year}: CD row {record['state_label']!r} precedes any state row"
                )
            cd_rows.append(UCSBCDRow(**record, parent_state_label=parent_label))
        else:
            state_rows.append(record)
            parent_label = record["state_label"]

    parsed = ParsedUCSBYear(
        year=year,
        layout=layout.kind,
        group_count=layout.group_count,
        candidates=parse_candidate_columns(rows, layout),
        state_rows=state_rows,
        cd_rows=cd_rows,
        status_rows=status_rows,
        totals=totals,
    )
    validate_year(parsed)
    return parsed


def parse_election_years(html_by_year: Mapping[int, str]) -> list[ParsedUCSBYear]:
    """Parse every saved page, dropping the pre-1824 years that have no popular vote.

    Ordered by year so downstream frames are deterministic.
    """
    parsed = (
        parse_election_year(html_by_year[year], year)
        for year in sorted(html_by_year)
    )
    return [record for record in parsed if record is not None]
