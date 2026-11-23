# UCSB Election-Page HTML Formats

Research findings from a survey of the complete UCSB / American Presidency Project
snapshot corpus, conducted 2026-07-17 as the design input for **E4-S2 (#35)**, the UCSB
parser. This is the reference companion to [`corrections.md`](corrections.md) (the
per-anomaly catalog) and [`mit-data-anomalies.md`](mit-data-anomalies.md) (the MIT-source
equivalent).

The corpus itself lives **outside this repository** at the path named by
`USVOTE_UCSB_HTML_DIR` — UCSB content is non-redistributable (D014/D016), and D022
established that committing UCSB bytes to this public repo would itself constitute
redistribution. **Every markup snippet quoted below is structural** — tag shapes,
attribute names, and sentinel tokens. Vote numbers appear only where a specific numeric
value *is* the finding (the `0.0`-percent decoy in §4).

---

## 1. Corpus inventory

- **60 year pages**, `1789.html` … `2024.html`, every four years, no gaps. Includes 1868
  and 1872, which the EC spine excludes via `UNSUPPORTED_EC_YEARS`.
- `_index_elections.html` is present, plus `manifest.json` and the original snapshot
  script.
- Every page decodes as UTF-8 and contains **literal U+00A0 bytes**. The entity
  `&nbsp;` never appears, and a truly empty `<td></td>` **never occurs anywhere in the
  corpus** — apparently-blank cells always hold a non-breaking space.
- **Zero `<th>` elements in any of the 60 pages.** Column identity is entirely
  positional.
- Pages embed a large Highcharts GeoJSON blob containing every state name. **Any
  regex or text search over raw HTML will hit that blob first.** Always scope to
  `<section id="block-system-main">` and work from parsed `<table>` elements.

---

## 2. The central structural finding

**The data-row grammar is identical across every era.** Each state row is

```
W = 2 + 3g   single-colspan <td> cells
STATE | TOTAL VOTE | (Votes, %, EV) × g
```

where `g` is the candidate-group count for that year. What varies across eras is **only
the header shape above the data rows** and the value of `g`.

This is why the parser needs **one** body parser rather than six. Per-era branching
belongs exclusively in layout detection and name extraction; any year-keyed conditional
below that line is a design smell.

**`g` must be derived from the data, not the header** — as the modal width of
single-colspan data rows, `g = (W - 2) // 3`. Header-derived approaches fail on 1836
(no colspans) and 1976 (header row narrower than data rows).

| `g` | Years |
|---|---|
| 2 | 1828, 1840, 1844, 1864, 1868, 1872, 1876, 1880, 1884, 1888, 1896, 1900, 1904, 1908, 1916, 1920, 1928, 1932, 1936, 1940, 1944, 1952, 1956, 1960, 1964, 1972, 1976, 1984, 1988, 2004, 2008, 2012 |
| 3 | 1832, 1848, 1852, 1856, 1892, 1924, 1948, 1968, 1980, 1992, 1996, 2000, 2016, 2020, 2024 |
| 4 | 1824, 1836, 1860, 1912 |

---

## 3. Layout taxonomy

| Layout | Years | Header structure | Detection signal |
|---|---|---|---|
| **L0 — summary-only** | 1789, 1792, 1796, 1800, 1804, 1808, 1812, 1816, 1820 | No state table at all. One `<table>`, 2–6 rows. 1789–1800: 6 cols (`Party`×2, swatch, `Nominee`, `Electoral Vote`×2). 1804–1820: 7 cols. **No `Popular Vote` column pair exists.** | No row whose col-0 text is `STATE`; max table width ≤ 7 |
| **L1 — stacked 3-row** | 1824–1924 (all), 1936, 1976 (variant) | `[STATE, TOTAL VOTE, party×colspan=3 …]` → `[NAME ×colspan=3 …]` → `[Votes, %, EV ×g]` | Row starting `STATE` also contains `colspan="3"` cells; a separate units row follows |
| **L1b — L1 without colspans** | **1836 only** | Same three rows, but party and NAME rows use `colspan=1` cells while `STATE`/`TOTAL VOTES` carry `rowspan="3"` | `STATE` row is width 6, not 14; NAME row is width 4; only the units row is 12 wide |
| **L1c — 1976 only** | **1976** | `[NAME ×colspan=3]` → `[ , TOTAL VOTES(rowspan=2), party×colspan=3 …]` → `[STATE, Votes, %, EV, …]` | `STATE` appears in the **units** row, and that row is **7 wide while data rows are 8** — the only page whose header row is narrower than its data rows |
| **L2 — names-first 3-row** | 1928, 1932, 1940, 1944, 1948, 1952, 1956, 1964, 1972, 1984, 1988 | `[NAME ×colspan=3 …]` → `[STATE, TOTAL VOTE, party×colspan=3 …]` → `[Votes, %, EV ×g]` — names row **precedes** the STATE row | Summary table is **nested inside the main table's first `<td>`**; a second nested table trails at the bottom |
| **L3 — inline 2-row** | 1960, 1968, 1980, 1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020, 2024 | `[<strong>NAME</strong><br /><em>Party</em> ×colspan=3 …]` → one flat row `[STATE, TOTAL VOTES, Votes, %, EV, …]` | The `STATE` row itself contains the literal cell `Votes`; no separate units row |

### Layouts are NOT chronologically ordered

This is the single most important consequence for implementation. **1936 reverts to L1
in the middle of the L2 block; 1964, 1972, 1984, and 1988 are L2 interleaved among the
L3 years; 1976 is its own layout entirely.** A year-range dispatch is wrong for at least
six pages.

**Branch on detected header shape, never on year.**

---

## 4. Popular-vote absence — the four cases

### A literal `0` never appears in a state-row vote column

Across all 51 popular-vote-bearing years, the complete set of distinct non-numeric
tokens in state-row `Votes` cells is:

| Token | Cells | Years |
|---|---|---|
| lone U+00A0 | 98 | 1824, 1832, 1836, 1848 |
| `--` | 87 | 1852, 1856, 1860, 1892, 1912, 1924, 1948, 1964, 1968, 2000 |
| `-` | 1 | 1836 (Rhode Island) — an apparent typo |

The only `0` cells anywhere are electoral-vote columns and summary-table cells.
**"Zero popular votes" is never encoded**, so absence must never be modeled as zero.

The four absence cases are cleanly distinguishable:

#### Case 1 — state chose electors by legislature *(state-level)*

A 2-cell row whose second cell spans the remaining width:

```html
<tr bgcolor="#F7FAFD">
<td bgcolor="#FFFFFF">Colorado</td>
<td bgcolor="#FFFFFF" colspan="7">3 electors chosen by state legislature and awarded to Rutherford B. Hayes</td>
</tr>
```

**Detection rule:** `len(cells) == 2 and colspan(cells[1]) >= W - 1`. The colspan is
`W - 1` in all 18 occurrences (7, 10, or 13 depending on `g`).

The prose always contains the exact substring **`electors chosen by state legislature`**
— verified in all 18 rows. Do **not** depend on phrasing beyond that: it forks into
`… and awarded to <Name>` versus a split allocation of the form `…: 2 for Crawford;
1 for Adams`, and 1824's New York cell carries a `<br />` mid-sentence.

**Complete set — 18 rows, 12 years, nothing after 1876:**

| Year | States |
|---|---|
| 1824 | Delaware, Georgia, Louisiana, New York, South Carolina, Vermont |
| 1828 | Delaware, South Carolina |
| 1832, 1836, 1840, 1844, 1848, 1852, 1856, 1860 | South Carolina (each cycle) |
| 1868 | Florida |
| 1876 | Colorado |

**18 at the parser, 17 at the roster — not a regression.** 1868 Florida is the only one of
the 18 outside the EC spine (`UNSUPPORTED_EC_YEARS` gates 1868/1872; see D024 §6 as clarified
2026-07-18). The parser finds all 18 — `TestRealCorpus` runs the full 60-page snapshot — but
the `pv_state_status` roster contains 17 until #57 ingests the Reconstruction years. Any test
asserting a count must state which layer it measures.

#### Case 2 — state did not participate *(state-level, no markup at all)*

The row is simply **absent**. No placeholder, no blank row. Only a prose footnote
elsewhere on the page attests to it:

```html
<td colspan="8">Eleven Confederate states did not participate in the election because of the Civil War.</td>
```

- **1864** omits 11 states: Alabama, Arkansas, Florida, Georgia, Louisiana, Mississippi,
  North Carolina, South Carolina, Tennessee, Texas, Virginia.
- **1868** still omits Mississippi, Texas, Virginia.

**This absence is invisible to any row-level check.** A parser that merely iterates rows
silently yields 26 states for 1864 and never notices — exactly the inner-join
silent-drop failure mode this repo has hit before. It is catchable **only** by comparing
the parsed state set against an expected roster.

#### Case 3 — candidate not on ballot, pre-1852 *(candidate-level)*

Both the `Votes` cell and its paired `%` cell hold a lone U+00A0. Structural shape, from
an 1824 row with one real candidate and three absent:

```html
<td>Connecticut</td>
<td>[total]</td>
<td>[votes]</td><td>[pct]</td><td>[ev]</td>
<td> </td><td> </td><td> </td>
<td> </td><td> </td><td> </td>
<td>[votes]</td><td>[pct]</td><td> </td>
```

Occurs in 1824, 1832, 1836, 1848 only.

#### Case 4 — candidate not on ballot, 1852+ *(candidate-level)*

The `Votes` cell holds `--`, paired with a percent cell:

```html
<td>Alabama</td>
<td>214,980</td>
<td>--</td>
<td>0.0</td>
<td> </td>
…
```

**⚠️ The `0.0` percent is a decoy.** In the 1948 page, two rows below the snippet above,
California's corresponding column reads `1,228` votes at `0.0` percent — a real,
non-zero count. **Percent `0.0` means "rounds to zero", not "zero".** Only the `--` in
the *Votes* cell carries absence meaning. Three paired-percent variants exist: `0.0`
(most years), `--` (1860, 16 cells), and bare `0` (1924 Louisiana).

### Summary

| Case | Grain | Signal |
|---|---|---|
| Legislature chose electors | (year, state) | 2-cell row, `colspan = W-1`, prose `electors chosen by state legislature` |
| State did not participate | (year, state) | Row absent entirely — roster comparison only |
| Candidate not on ballot, pre-1852 | (year, state, candidate) | `Votes` cell is a lone U+00A0 |
| Candidate not on ballot, 1852+ | (year, state, candidate) | `Votes` cell is `--` |
| **Popular vote genuinely zero** | — | **Does not occur** |

---

## 5. Era breakpoints

| Breakpoint | What changes |
|---|---|
| 1820 → **1824** | Popular vote appears for the first time. Earlier pages have no state table and no PV columns at all. This is the corpus's hard floor for PV extraction (cf. D009). |
| 1824 → 1828 | Legislature-chosen states drop from 6 to 2, then to 1 (South Carolina) from 1832. |
| 1848 → **1852** | The candidate-absence marker switches from NBSP-blank to `--`. The two **never coexist** in one year (1836's lone `-` is a separate typo). |
| 1860 → **1864** | Civil War: 11 Confederate states vanish as rows entirely. 1868 still omits three; all are back by 1872. |
| 1876 → **1880** | Last legislature-chosen state (Colorado, 1876). **From 1880 onward no PV-absent state exists anywhere in the corpus.** |
| 1924 → **1928** | The summary table becomes nested inside the main table (L2), persisting through 2024 with the 1936 and 1976 exceptions. |
| 1956 → 1960 | Header collapses to the flat L3 two-row form — though L2 recurs at 1964, 1972, 1984, 1988. |
| 2004 → **2008** | Percent cells gain a `%` suffix. Sole earlier exception: the 1860 totals row. |
| 2012 → **2016** | Congressional-district sub-rows appear — 2016 Nebraska only; 2020 and 2024 both Maine and Nebraska. Also `Dist. of Col.` → `District of Columbia` in 2020. |

---

## 6. Ranked parsing risks

1. **Nested tables leak rows into `find_all("tr")`.** 23 of 60 pages (1928 onward, L2/L3)
   nest the summary table inside the main table's first `<td>`; 1928–1972 also carry a
   second nested table at the bottom. The EC parser's `year_tables[1].find_all("tr")`
   idiom is **unsafe here**. Fix:
   `[r for r in t.find_all("tr") if r.find_parent("table") is t]`.
2. **CD sub-rows double-count popular votes.** 2016 (NE), 2020 and 2024 (ME + NE). A
   state's CD rows sum to exactly its own total, so summing every row overcounts by
   roughly 1.5 M. Detect via `^CD-\d` on column 0. **Verified: with CD rows excluded,
   all 51 years reconcile exactly** — each candidate's `Votes` column sums to its totals
   cell with zero residual, making an exact-equality sum validator viable corpus-wide.
3. **Missing state rows** (1864, 1868) — risk 2's silent twin, needing a per-year
   expected-roster assertion.
4. **1836 has no header colspans**, breaking any group-count-from-header logic.
5. **1976's header row is narrower than its data rows** (7 vs 8) and puts `STATE` in the
   units row, mis-windowing any "find the STATE row and slice" approach by one column.
6. **Header shape is non-monotonic in year** — see §3.
7. **Name and label anomalies.** Typos `New jersey` (1852) and `HORACE GREEFLEY` (1872
   header). Trailing `*` footnote markers appear **in plain text, not in `<sup>`**:
   `Alabama*` (1956, 1960), `Mississippi*`/`Oklahoma*` (1960), `Virginia*` (1972),
   `Washington*` (1976), `West Virginia*` (1988), `Dist. of Col.*` (2000), `Minnesota*`
   (2004). DC label drifts `Dist. of Col.` → `District of Columbia` at 2020.
8. **Totals-row label drift** — `Totals` everywhere except singular `Total` in 1864 and
   1944. The EC parser's `TOTALS_LABELS = {"Total", "Totals"}` already covers both.
9. **The second-column header label is wildly unstable** — `TOTAL VOTE`, `TOTAL VOTES`,
   `T. VOTES`, `Votes` (1976). **Never match on it.** Column 0's header is `STATES`
   (plural) in 1940.
10. **Percent format split** — bare `48.0` through 2004, `%`-suffixed from 2008. Strip a
    trailing `%` unconditionally.
11. **Thousands separators are always ASCII commas.** No spaces, periods, or Unicode
    separators anywhere. `int(v.replace(",", ""))` is safe.
12. **EV cells carry asterisks** (`5*`, and 10 bare `*` cells in 1872/1960) and sometimes
    wrap in `<span>`. Per D006 the EV columns are **not parsed** — but a naive
    "int every numeric column" pass would crash. Skip positions `4 + 3i` explicitly.
13. **Separator and note rows inside the body.** A `bgcolor="#AACAEA"` full-width bar sits
    between header and body and again before totals. 1824 has an all-NBSP 14-cell row and
    1836 a 9-cell blank — **neither is a full-width colspan**, so a "skip colspan rows"
    rule alone won't catch them. Trailing prose rows include footnotes,
    `Click on state name for access to source…`, and `Last update: …`.
14. **Name and party are fused in one cell in L3** —
    `<strong>NAME</strong><br /><em>Democratic</em>`, preceded by an `<img>` in the same
    cell for 1960–1976. Requires `<br>`-aware splitting, exactly like the EC parser's
    `parse_t2_candidate_state` handling.
15. **`OTHERS` / `Various` aggregate column** in 2020 and 2024 (group 3) — analogous to the
    EC parser's `OTHER_LABELS`; no single candidate or home state, and must not be treated
    as a named candidate.
16. **Summary-table candidate count ≠ state-table group count.** 1836's summary lists five
    candidates but the state table has four groups; 1832, 1848, 1852, 1872, and 1912 are
    similar. **Never cross-key candidates by summary position** — 1824's state-block order
    (Adams, Jackson, Clay, Crawford) differs from its summary order (Jackson, Adams,
    Crawford, Clay).

---

## 7. Fixture representatives

Per D022, committed fixtures are **synthetic** — structure faithful, numbers fabricated,
hand-written rather than copied bytes. Each fixture below is the minimal page that pins
one structural feature nothing else covers.

| Fixture | Modeled on | Why |
|---|---|---|
| `ucsb_synthetic_4group.html` *(exists)* | 1824 | L1, `g=4`, all six legislature rows, NBSP absences, contingent-election footnote |
| `ucsb_synthetic_2group.html` *(exists)* | 1876 | L1, `g=2`, the last legislature row, separator bars, totals |
| `ucsb_synthetic_nocolspan.html` *(proposed)* | 1836 | The only page whose header cells lack `colspan`, plus `rowspan="3"`, the lone `-` cell, and a summary candidate missing from the state table |
| `ucsb_synthetic_dashdash.html` *(proposed)* | 1948 | L2 (names-first + nested summary), `g=3`, and the `--`/`0.0` vs. real-votes/`0.0` decoy pair — the single best pin for case 4 |
| `ucsb_synthetic_missing_states.html` *(proposed)* | 1864 | The only shape for case 2: absent rows, singular `Total`, prose footnote |
| `ucsb_synthetic_inline_cd.html` *(proposed)* | 2020 | L3, `g=3` with `OTHERS`, CD rows under both ME and NE, `%`-suffixed percents, `<strong>/<br>/<em>` name cell |
| `ucsb_synthetic_1976.html` *(proposed)* | 1976 | Sole L1c page: narrow header row, `STATE` in the units row, `rowspan="2"` |
| `ucsb_synthetic_summary_only.html` *(proposed)* | 1820 | L0: no state table, no PV columns — pins the "this year publishes no PV" path for all nine 1789–1820 pages |

---

## 8. Recommended parser decomposition

Mirrors `usvote/parse.py`'s shape — provenance-carrying module constants, a typed error,
small pure functions, `TypedDict` records — in a new `src/usvote/ucsb/parse.py`.

```
UCSBParseError(RuntimeError)

# constants
LEGISLATURE_MARKER    = "electors chosen by state legislature"
ABSENT_VOTE_TOKENS    = frozenset({"--", "-"})   # + lone NBSP, handled by _clean_cell
TOTALS_LABELS         = frozenset({"Total", "Totals"})
CD_ROW_PATTERN        = re.compile(r"^CD-\d+$")
OTHER_LABELS          = frozenset({"OTHERS", "OTHER"})
NO_POPULAR_VOTE_YEARS = frozenset(range(1789, 1824, 4))

# entry points
parse_election_years(html_by_year) -> list[ParsedUCSBYear]
parse_election_year(html, year)    -> ParsedUCSBYear | None    # None for L0

# table location — owns the nesting trap
select_results_table(soup) -> Tag      # scope to #block-system-main
own_rows(table)            -> list[Tag]

# shape discovery — ALL layout branching lives here, and only here
detect_layout(rows) -> UCSBLayout      # (kind, group_count, header_span, data_width)
    _detect_group_count(rows)          # modal single-colspan width -> (W-2)//3
    _detect_header_span(rows, g)

# header
parse_candidate_columns(rows, layout) -> list[UCSBCandidateColumn]
    _names_from_stacked_header(...)    # L1/L1b/L2
    _names_from_inline_header(...)     # L3/L1c
    _split_name_and_party(cell)        # <br>-aware

# body — layout-agnostic
parse_state_rows(rows, layout, state_names) -> list[UCSBStateRow]
    classify_row(row, layout)          # STATE_DATA | PV_ABSENT | TOTALS
                                       #   | CD_BREAKDOWN | SEPARATOR | NOTE
    parse_pv_absent_row(row)           # verbatim prose preserved
    parse_state_data_row(row, g)
        _parse_vote_cell(text)         # None for NBSP/'--'/'-'; NEVER 0
        _parse_percent_cell(text)      # strips trailing '%'
    _clean_label(text)                 # .strip().strip("*").strip()

# validation
validate_year(parsed) -> None
    _assert_column_widths_consistent   # every data row exactly 2+3g wide
    _assert_sums_reconcile             # exact equality, CD rows excluded
    _assert_states_recognized          # guards the inner-join silent drop
    _assert_expected_state_count       # catches 1864/1868 missing rows
```

**Where per-era branching belongs:** exclusively in `detect_layout` and the two
`_names_from_*` helpers. Everything from `parse_state_rows` down must be
layout-agnostic.

**Two EC-parser carry-overs worth keeping:** the `col_ind`-keyed record shape (so the
downstream normalize/melt works identically), and the "resolve column 0 to decide row
kind" discipline — though here it returns a **five-way** classification, since PV-absent
and CD-breakdown rows have no EC analogue.

**One carry-over to deliberately reject: `strip_footnotes`.** UCSB uses **no `<sup>`
elements at all** — footnote markers are bare `*` characters inside the text. A
`strip_footnotes` port would be a silent no-op giving false confidence; `_clean_label`'s
`.strip("*")` is what actually handles them.

---

## 9. Corrections and additions from the #35 implementation

The survey above was written from reading the corpus; this section records what
actually running a parser against all 60 pages changed. Everything here is verified
against the real snapshot, and each item is pinned by a test in
`tests/unit/test_ucsb_parse.py`.

**§3's nesting claim was too narrow.** The taxonomy implies table nesting begins at
L2/1928. In fact **1836's summary block is sibling rows of the same table as its state
block** (widths 9 and 14 interleaved in one `<table>`). `own_rows` does not separate
them — the modal-width rule does — so that rule is load-bearing for considerably more
years than §3 suggests. Two independent defences are needed and neither covers the
other: `own_rows`/`_own_cells` for genuinely nested tables, and the modal-width rule for
same-table interleaving.

**The summary block also appears BELOW the state block, in the same table.** On
1928, 1932, 1940, 1944, 1948, 1952, 1956, 1972 and 1988 the summary rows are appended
after the totals row. They are neither data nor benign prose, so the body has to be
truncated where they begin (`_find_body_end`, keying on the `Party`/`Nominees` header
cells). Without that truncation those nine years hit the terminal raise.

**§2's `g` rule needs one addition: filter before taking the mode.** Taking the modal
width of all-single-colspan rows is right, but it must be restricted to structurally
possible widths (`W = 2 + 3g`) *first*. On a page whose summary rows tie with or
outnumber its data rows, a bare mode picks the summary width — and `(9-2)//3`
floor-divides to a plausible-looking `g=2` instead of failing. Filtered, the rule
reproduces the §5 `g` table for all 51 popular-vote years with zero mismatches.

**1976's header is three rows, not two, and the missing header cell is TOTAL VOTE.**
§3 records that the header is narrower than the data rows but not why. The real shape
is names / parties+`TOTAL VOTES` / `STATE`+units, and the `STATE` row carries no
TOTAL VOTE header at all — hence `1 + 3g = 7` against data rows of `2 + 3g = 8`. Its
name and party rows are at `STATE_row - 2` and `STATE_row - 1`, unlike every other
layout's single adjacent name row.

**`select_results_table` cannot be "the widest table in the section."** On 1976 the
summary rows are 9 wide and the data rows 8, so widest-table selects the summary block.
The rule that works — *the table containing an own-row with a `STATE`/`STATES` cell* —
selects exactly one table on each of the 51 popular-vote years and zero on all nine
1789–1820 pages, so it doubles as the L0 detector.

**The percent cross-check must be aggregate, not per cell.** Three years carry percents
that disagree with their own vote counts, and in all three the columns are provably
aligned (the row's candidates sum exactly to its TOTAL VOTE):

| Year | State | Published | Actual | What happened |
|------|-------|-----------|--------|---------------|
| 1860 | Vermont | `4.16` twice | 19.6 / 4.16 | the same percent duplicated into two cells |
| 1968 | Utah | `31.1` | 37.1 | transposed digits |
| 1872 | Kentucky | percents sum to exactly 100.0 | 46.4 / 52.3 | computed on a different denominator |

These are source defects, not parse errors. Since a genuine column-window shift
misaligns essentially *every* row while a source typo hits one cell, the check asserts
on the mismatch **rate** (>25%), not on any individual cell.

**The pre-1824 year set is not `range(1789, 1824, 4)`.** That yields 1793, 1797, 1801…
and matches no real election. The series starts at 1789 but goes quadrennial from 1792:
`{1789, *range(1792, 1824, 4)}` — exactly the nine pages that carry no state table.

**Counts confirmed against the snapshot.** 18 legislature-chosen rows (six 1824 states;
South Carolina every year through 1860; 1868 Florida; 1876 Colorado); CD sub-rows only
in 2016 (Nebraska, 3) and 2020/2024 (Maine + Nebraska, 5 each); 186 not-on-ballot cells;
and **zero literal `0` values in any state-row vote column**, which is what licenses
treating a parsed `0` as proof of a bug.
