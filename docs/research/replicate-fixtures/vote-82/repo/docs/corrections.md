# Historical data corrections catalog

Each ingest patches or tolerates a handful of real historical anomalies in its source
data. The **Electoral College** catalog comes first, then the **UCSB popular-vote**
catalog; each source's constants live in that source's own module, per the
source-namespacing convention (D006/D015).

The Electoral College pipeline patches a handful of real historical anomalies in the
National Archives source data. Each is **hard-won correctness** — a value confirmed
against the Archives' own Notes sections (or, for 2000, a direct email reply from the
Archives) — and must survive the notebook → package migration as an **explicit,
documented, tested** correction rather than a scattered inline edit.

This file is the human-browsable **index**. The authoritative, machine-readable
source of truth is the set of provenance-carrying constants in
[`src/usvote/transform.py`](../src/usvote/transform.py) (the "Corrections" section
near the top of the module); each is locked by a test in
[`tests/test_transform.py`](../tests/test_transform.py). Extending EC coverage below
1892 toward the ~1824 comparison floor (#32) surfaced the 19th-century anomalies in
the table below; adding a new election year follows the same pattern: one constant
entry + a small `apply_*`/reconcile function, one test, and one row in the table.

## Catalog

| Year(s) | Anomaly | Correction applied | `transform.py` constant | Source / provenance |
|---|---|---|---|---|
| 2016 | Table 2 collapses the seven faithless electors' votes into two unnamed "Other" columns | Replace the placeholders with the real recipients — Bernie Sanders, Ron Paul, John Kasich, Colin Powell, Faith Spotted Eagle — and their per-state electoral votes | `OTHER_CANDIDATES_2016`, `OTHER_VOTES_2016` (applied by `apply_other_candidates`, `_votes_matrix`) | Names + electoral-vote counts collected manually from the [Archives 2016 Notes](https://www.archives.gov/electoral-college/2016) |
| 2016 | Colin Powell has no politically-defined home state (he grew up in NY but was not a politician) | Home state left `None` rather than guessing | `OTHER_CANDIDATES_2016` (`state=None`) | Editorial; [Archives 2016](https://www.archives.gov/electoral-college/2016) |
| 2016 | The generic name parser mis-splits the two-word surname "Faith Spotted Eagle" (middle="Spotted", last="Eagle") | Force `name_middle=None`, `name_last="Spotted Eagle"` | `SPOTTED_EAGLE_NAME`, `SPOTTED_EAGLE_LAST` | Editorial (name structure) |
| 2016, 2020 | Trump is printed "Donald Trump" (2016 Table 2, New York) but "Donald J. Trump" (2020 Table 2, Florida), so his two state rows would not collapse to one candidate | Unify the 2016 spelling to the canonical "Donald J. Trump" (+ middle initial "J.") before aggregation, so he becomes one candidate spanning NY/FL | `CANDIDATE_NAME_FIXES` (applied in `_candidate_states`; vote side via `reconcile_vote_candidate_names`) | Archives [2016](https://www.archives.gov/electoral-college/2016) / [2020](https://www.archives.gov/electoral-college/2020) |
| 1972 | Table 2 prints "George McGovern"; Table 1 has "George S. McGovern" | Rewrite the Table-2 name to the canonical form and fill the middle initial "S." | `CANDIDATE_NAME_FIXES` | Archives [1972](https://www.archives.gov/electoral-college/1972) |
| 1996 | Table 1 (party) prints "Bob Dole"; Table 2 prints "Robert Dole", so the two tables' names would not reconcile | Rewrite the Table-1 name to "Robert Dole" | `PARTY_NAME_FIXES` | Archives [1996](https://www.archives.gov/electoral-college/1996) |
| 2000 | DC elector Barbara Lett-Simmons cast a blank ballot, so DC cast only 2 of its 3 allotted electoral votes; the national Totals row is likewise 537 of 538. A naive row-sum check reads this as a broken parse. | Record the confirmed 1-vote shortfall so `assert_row_votes_sum_to_total` adds it back instead of raising; the allotment (`total_electoral_votes=3`) is preserved | `ELECTORAL_VOTE_SHORTFALLS` (used by `_expected_shortfall`) | [Archives 2000 Notes](https://www.archives.gov/electoral-college/2000) **and a direct email reply from the National Archives** confirming total=3 / cast=2 is correct |
| 1824, 1832, 1836, 1860 | Table 2 collapses the minor presidential candidates into a single unnamed "Others" column (parsed with `state=None`, like 2016's "Other") | Split "Others" back into its named candidates with the per-state electoral votes read from each year's Notes: **1824** Crawford (41) / Clay (37); **1832** Floyd (11) / Wirt (7); **1836** White (26) / Webster (14) / Mangum (11); **1860** Breckinridge (72) / Bell (39) | `OTHER_CANDIDATES_1824/1832/1836/1860`, `OTHER_VOTES_*` (applied by `apply_other_candidates`, `_votes_matrix`) | Per-state counts from each year's Archives Notes ("&lt;State&gt; cast N votes for &lt;Name&gt; as President"): [1824](https://www.archives.gov/electoral-college/1824), [1832](https://www.archives.gov/electoral-college/1832), [1836](https://www.archives.gov/electoral-college/1836), [1860](https://www.archives.gov/electoral-college/1860) |
| 1824 (era) | The Archives prints the early Democratic-Republican party inconsistently — "Democratic-Republican" (Jackson) vs. "D-R" (Adams) — for the same party, so one party would read under two labels and the "-" join delimiter would mis-split "D-R" into a spurious `party_2` | Normalize the label to "D-R" before aggregation, and join a candidate's distinct parties on `|` (never present in a party code) instead of "-" | `PARTY_CODE_FIXES`, `PARTY_JOIN` (in `_candidate_parties`) | [Archives 1824](https://www.archives.gov/electoral-college/1824) |
| 1832 | Two of Maryland's electors did not vote, so Maryland cast 8 of its 10 allotted votes (Jackson 3, Clay 5); the national Totals row is likewise 286 of 288 | Record the 2-vote shortfall so `assert_row_votes_sum_to_total` adds it back; the allotment is preserved and the Totals shortfall is derived | `ELECTORAL_VOTE_SHORTFALLS` | [Archives 1832 Notes](https://www.archives.gov/electoral-college/1832) ("two electors from Maryland did not vote, making the total number of votes cast 286") |
| 1824 | No candidate reached an Electoral College majority; Jackson led (99 EC votes) but the House elected John Quincy Adams (84), so the EC leader is *not* who took office | Mark the actual office-holder with `took_office=True` (Adams) while EC-winner stays derived from `president_electoral_rank == 1` (Jackson) — the two are kept distinct, not conflated | `CONTINGENT_OFFICE_HOLDERS` (applied by `_add_took_office`) | [Archives 1824 Notes](https://www.archives.gov/electoral-college/1824) |

## UCSB popular-vote catalog

Source-namespaced per D006/D015, exactly as MIT's reconciliations are: these anomalies
are in the **UCSB** popular-vote source, so their constants live in that subpackage
rather than the EC `transform.py` — parse-stage anomalies in
[`src/usvote/ucsb/parse.py`](../src/usvote/ucsb/parse.py) (locked by
[`tests/unit/test_ucsb_parse.py`](../tests/unit/test_ucsb_parse.py)) and transform-stage
ones in [`src/usvote/ucsb/transform.py`](../src/usvote/ucsb/transform.py) (locked by
[`tests/unit/test_ucsb_transform.py`](../tests/unit/test_ucsb_transform.py)). The
`ucsb/parse.py` constant column below names which module each lives in.

One difference from the EC catalog above is worth stating plainly: the EC corrections
*rewrite* wrong values, whereas most UCSB entries are anomalies the parser must
**tolerate without correcting** — UCSB is not the source of truth for anything the
Electoral College spine already carries (D006), so a wrong percent is recorded and
worked around, never silently "fixed" into a number UCSB never published.

| Year(s) | Anomaly | Handling | `ucsb/` constant (module) | Source / provenance |
|---|---|---|---|---|
| 1836 | Rhode Island's third candidate cell is a single `-` (one hyphen), where every other year spells "not on the ballot" as `--`. A literal `"--"` test reads it as an unparseable vote and raises. | Model the absence token as a **set**, not a literal, so both spellings parse to `None` — never to `0` (D024 §2) | `ABSENT_VOTE_TOKENS` (`parse.py`) | UCSB [1836](https://www.presidency.ucsb.edu/statistics/elections/1836); `-` appears in exactly this one cell corpus-wide |
| 1860 | **Vermont, Virginia and Wisconsin** each publish the Douglas percent as a duplicate of the *next* candidate's (Breckinridge's) — `4.16`, `44.46` and `0.58` respectively, against true values of 19.57%, 9.74% and 42.73%. The columns are provably aligned: each row's four candidates sum to exactly its TOTAL VOTE, and **all 28 other 1860 states agree with their published percent to 0.00pp**, which is what shows these are isolated source typos rather than a column shift. | Tolerated, never rewritten (UCSB is not the source of truth here). The percent cross-check asserts on the **mismatch rate**, not per cell, so isolated typos do not fail the year while a systematic shift still does. At transform these three cells are flagged `reliability='unreliable'` — the page contradicts itself and we cannot know which published number is wrong | `PERCENT_MISMATCH_RATE`, `PERCENT_TOLERANCE` (`parse.py`); `_cell_reliability` (`transform.py`) | UCSB [1860](https://www.presidency.ucsb.edu/statistics/elections/1860); the three-state extent established in #36 (the earlier catalog entry recorded Vermont only) |
| 1968 | Utah publishes `31.1` where 156,665/422,568 is 37.1 — transposed digits. That row's candidates also reconcile against its total. | Tolerated, and flagged `reliability='unreliable'`, as above | `PERCENT_MISMATCH_RATE` (`parse.py`); `_cell_reliability` (`transform.py`) | UCSB [1968](https://www.presidency.ucsb.edu/statistics/elections/1968) |
| 1864, 1868 | **Fourteen states took no part in the election at all** — 1864's eleven Confederate states, and 1868's Mississippi/Texas/Virginia, not yet readmitted. The defining property is that this has **no markup whatsoever**: the state's row is simply absent from the page, so it cannot be parsed, only enumerated (D024 §4 case 2). | Enumerated with its cause, and emitted as a `not_participating` row in `dwh.pv_state_status` — **never** as a null or zero vote in `pv_votes` (D024 §1/§2, D005). Cross-checked against the EC spine, which carries these states with `total_electoral_votes = 0`. All 14 entries are retained but only **in-scope years are consumed** (11 today): 1868 is gated out of the EC spine, so its three are catalogued but not yet ingested, pending #57 | `UCSB_NONPARTICIPATING_STATES` (`transform.py`) | Settled history; the 1868 trio independently corroborated by the EC spine's own `UNSUPPORTED_EC_YEARS` note, and every in-scope entry verified against `dwh.votes` |
| 1852, 1964–2016 | UCSB prints two state labels that differ from the canonical `dwh.state` key: `New jersey` (1852, a lower-case "j" typo) and `Dist. of Col.` (1964–2016; 2020/2024 print `District of Columbia` in full). Unreconciled, DC reads as two different states across the series and the roster assert reports both as phantom states. | Rewritten to the canonical full name before anything roster-related. The map is **exhaustive** over all 53 corpus labels rather than exceptions-only, so an unseen future spelling fails loudly instead of vanishing in a join | `UCSB_STATE_RECONCILIATIONS` (`transform.py`) | UCSB state-column labels, all 60 pages; RHS per the EC state dimension (TIGER2019) |
| 1872 | Kentucky's published percents sum to exactly 100.0 (45.5 / 54.5) while its votes leave a 2,374-vote residual, so UCSB computed them against a different denominator than the printed TOTAL VOTE. | Tolerated, as above | `PERCENT_MISMATCH_RATE` | UCSB [1872](https://www.presidency.ucsb.edu/statistics/elections/1872) |
| 1864, 1944 | The totals row is labelled singular `Total`, not `Totals`. A `== "Totals"` test drops the row, leaves `totals=None`, and silently no-ops the sum validator. | Match against a set of labels, case-insensitively | `TOTALS_LABELS` | UCSB [1864](https://www.presidency.ucsb.edu/statistics/elections/1864), [1944](https://www.presidency.ucsb.edu/statistics/elections/1944) |
| 1940 | The state-column header is plural `STATES`, not `STATE` — and `select_results_table` keys on exactly that cell, so a singular-only test finds no results table and the year reads as having no popular vote. | Match against a set of labels, case-insensitively | `STATE_HEADER_LABELS` | UCSB [1940](https://www.presidency.ucsb.edu/statistics/elections/1940) |

Structural (rather than per-year) UCSB format quirks — the six header layouts, the
trailing summary blocks, 1976's narrower header — are **not** data corrections and are
catalogued instead in [`ucsb-html-formats.md`](ucsb-html-formats.md) §9, with the
reasoning that produced each rule.

## Notes

- **The `ELECTORAL_VOTE_SHORTFALLS` map is keyed on per-state anomalies only.** The
  national "Totals" row's expected shortfall is *derived* (summed over the year's
  states) inside `_expected_shortfall`, so a future multi-state anomaly (e.g. the
  1872 votes for the deceased Horace Greeley, which Congress rejected across several
  states) needs only its per-state entries here — never a hand-maintained Totals
  bump that could silently drift.
- **The name reconciliations** (Trump, Dole, McGovern) are the first instance of the
  canonical-candidate-key problem the popular-vote sources (UCSB/MIT) reconcile
  against; `CANDIDATE_NAME_FIXES` / `PARTY_NAME_FIXES` are the EC-side catalog
  (D006 / #30). The **MIT** realization lives in its own source-namespaced map,
  `MIT_CANDIDATE_RECONCILIATIONS` / `MIT_STATE_RECONCILIATIONS` in
  [`src/usvote/mit/reconcile.py`](../src/usvote/mit/reconcile.py) (#67, D020) — MIT's
  `"LAST, FIRST M."` format shares no keys with the EC fixes, only the canonical RHS
  targets; see [`canonical-keys.md`](canonical-keys.md) for how each source conforms.
- **Format handling vs. data corrections.** Two pre-1892 fixes are parse-level format
  robustness rather than per-year data corrections, so they live in
  [`src/usvote/parse.py`](../src/usvote/parse.py), not the catalog above: superscript
  footnote markers are stripped from state-name and vote cells (`strip_footnotes`), and
  the totals row's `<th>Totals</th>` plural/`<th>` form is recognized (older years use
  it; a singular-only check silently dropped the totals row and emptied the votes fact).
- **Contingent elections — which field is authoritative (#29, D010).** In a contingent
  election the House (or, for the VP, the Senate) chooses the office-holder, so the
  Electoral College leader is not necessarily who took office. The `votes` fact keeps the
  two facts on separate columns, and **downstream flip/margin logic (E6/E7) must read them
  as follows**:
  - **"Who won under the Electoral College"** → `president_electoral_rank == 1` (on a
    year's totals rows). This is the single source of truth for the EC outcome; do **not**
    re-derive it from `took_office`.
  - **"Who assumed office"** → `took_office == True`. Defaults to the EC winner and is
    overridden only for the contingent years in `CONTINGENT_OFFICE_HOLDERS`; it is
    broadcast to every one of a candidate's rows (like the rank). A flip where the EC
    leader did not become president is the year whose `rank == 1` candidate has
    `took_office == False`.

  Scope: `took_office` models **president** office-holding only, and only **1824** (Jackson
  EC rank 1, Adams `took_office`) is within the loaded coverage and exercised in tests.
  **1836** (a VP-only contingency — the Senate chose the VP while President Van Buren won
  normally, so there is no president-level divergence) and **1800** (pre-12th-Amendment,
  two undifferentiated presidential votes, below the 1804 load floor) are representable by
  the same boolean but are not loaded or tested here; their office outcomes become markable
  when those eras are ingested under the deferred pre-12th-Amendment epic (D010).
- **UCSB candidate reconciliation onto the canonical key (#38, D025).**
  `UCSB_STATE_RECONCILIATIONS` (above) canonicalizes **state** names in #36; UCSB
  **candidate** names are reconciled onto the canonical EC `name` in
  [`src/usvote/ucsb/reconcile.py`](../src/usvote/ucsb/reconcile.py) via
  `UCSB_CANDIDATE_RECONCILIATIONS` — a curated map keyed by `(year, ucsb_native_name)`
  (111 EC-getter columns). The spellings are non-mechanical, mirroring the EC/MIT
  catalogs: `STROM THURMOND` → `J. Strom Thurmond`, `ADLAI E. STEVENSON` → `Adlai
  Stevenson`, `WENDELL WILLKIE` → `Wendell L. Willkie`, `AL GORE` → `Albert Gore Jr.`,
  and the accent restored in `JOHN C. FREMONT` → `John C. Frémont`. (The 1872 `HORACE
  GREEFLEY` typo lives in a Reconstruction year gated out of the EC spine, so it is
  catalogued but not ingested until #57 — see below.) The **D007 candidate scope** is
  applied in the same stage: the 8 popular-vote-only minors UCSB prints are dropped
  (`UCSB_NON_GETTER_COLUMNS` — Van Buren '48, Hale '52, Debs '12, Anderson '80, Perot
  '92/'96, Nader '00, G. Johnson '16), and a reciprocal completeness guard against an
  injected EC-getter frame proves no major was silently lost.
  `EC_GETTERS_WITHOUT_POPULAR_VOTE` (13 entries) exempts the getters that held no popular
  vote — faithless/unpledged electors (1960 Byrd, 2016's five, 2004 Edwards, …) and the
  1832/1836 South Carolina legislature-chosen awards. With #38 landed, MIT and UCSB rows
  now share the EC-getter candidate grain in `dwh.pv_votes` (totals/margins were never
  affected — `state_total_votes` is carried verbatim).
- **1944 Franklin D. Roosevelt footnote asterisk (EC-side, D025).** Table 2 of the
  National Archives [1944 page](https://www.archives.gov/electoral-college/1944) prints
  `Franklin D. Roosevelt*` — a footnote marker (he died in office the following April) —
  while every other year prints him unmarked. Left in, the `*` splits one person across
  two canonical keys (`Franklin D. Roosevelt` in 1932–1940 vs. `…Roosevelt*` in 1944),
  giving FDR a second, party-less candidate row and breaking the D006 canonical key.
  `usvote.transform.strip_name_footnote_markers` strips a trailing `*` from both tables'
  names at normalize time, so the marker never reaches the canonical `name`; it is a
  no-op for every unmarked candidate and 1944 FDR is the only one affected in current
  coverage. Discovered while authoring the #38 UCSB candidate map (the RHS must equal the
  clean EC name for the E6 join to key on it). Source: the 1944 Table 2 + Notes.
- **Deferred Reconstruction years (1868, 1872).** These are **excluded** from the
  default ingest (`UNSUPPORTED_EC_YEARS` in [`years.py`](../src/usvote/years.py),
  re-exported from [`pipeline.py`](../src/usvote/pipeline.py)),
  not corrected here, because their tables encode contested/uncounted electoral votes
  that need dedicated modeling: 1868's Georgia votes were contested (dual
  "excluding/including Georgia" totals rows; MS/TX/VA had not been readmitted), and
  1872's Horace Greeley died after the popular vote, scattering his electoral votes with
  Georgia's rejected by Congress. Ingesting them is tracked as follow-up work (#57).
  **UCSB ingestion inherits this gate by derivation** (D024 §6): `ucsb_ingest_years()` is
  `ec_ingest_years()` minus the pre-1824 no-popular-vote years, so #57 admits both years
  to E4 with no change under `usvote/ucsb/`. Until then UCSB's 1868 rows — three
  non-participating states and the Florida legislature-chosen row — are catalogued but
  not ingested.
