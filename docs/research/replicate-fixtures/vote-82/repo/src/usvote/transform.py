"""Transform & validate stage — build the three warehouse DataFrames.

Maps to notebook Section 3. :func:`transform_parsed_years` flattens
``parsed_election_years`` (see :mod:`usvote.parse`) into three DataFrames, each
transformed and validated independently before a final join:

- ``candidates_df`` (candidate dimension) — Table 2 states + Table 1 parties,
  joined on candidate name; multi-state/multi-party candidates are aggregated to
  one row with ``_2`` columns (e.g. Bryan D/P, T. Roosevelt R->P, Trump NY/FL).
- ``state_df`` (state dimension) — US state names joined to the geopandas
  shapefile data (region, division, area, lat/lon).
- ``votes_df`` (votes fact) — the melted votes-by-state matrix joined to both
  dimensions, with ``is_total`` / electoral-rank shaping.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S3 (#26), mirroring the
scrape/parse ports' conventions:

- **Typed failures.** The notebook's dense inline assertions (``Q: ... A: {...}``
  grain checks, ``value_counts`` sanity checks) become explicit validation
  functions that raise :class:`TransformError`. They are load-bearing: a
  scrape/parse regression must surface loudly, not flow silently into the DB load.
- **Injected geo seam.** ``build_state_dim`` takes a plain-pandas state-geo frame;
  the geopandas file read lives in the untested :func:`load_state_geo` wrapper,
  mirroring the ``fetch`` seam so the transform core tests offline with a fake
  frame (no TIGER shapefile needed). The shapefile path is externalized in
  :mod:`usvote.config` (E2-S6, #31).
- **Name-based column ops.** Every notebook ``value_vars=[1..7]`` / positional
  ``.iloc[:, [...]]`` reorder becomes an explicit named-column selection. This
  preserves the notebook's exact final column order (the load contract, #28) while
  making the transform runnable on any *subset* of years, not just the full
  dataset the notebook's absolute positions assumed.

**Corrections.** Every hardcoded historical correction lives here as a named,
provenance-carrying module-level constant paired with a small ``apply_*``/reconcile
function (never a scattered ``df.loc[...] =`` edit). These constants are the
authoritative catalog; ``docs/corrections.md`` is a human-browsable index that points
back to them, and each is locked by a test in ``tests/test_transform.py`` (E2-S4 /
#27). A new election year's anomaly slots in by adding one constant entry + its test
and one catalog row. The name reconciliations (Trump, Dole, McGovern, Faith Spotted
Eagle) are also the first instance of the canonical-candidate-key problem the PV
sources reconcile against (D006 / #30).
"""

from __future__ import annotations

import re
from collections.abc import Container, Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

# --- historical corrections (provenance-carrying constants) ----------------
# 2016 faithless/"Other" electors. The Archives Table 2 for 2016 collapses the
# faithless votes into two unnamed "Other" columns (parsed col_ind 2 & 4); the
# real recipients + their electoral votes come from the Notes section:
# https://www.archives.gov/electoral-college/2016
#
# Colin Powell is given no home state: while he grew up in New York he was not a
# politician, so there is no politically-defined home state to assign (None).
# col_ind 2 & 4 reuse the two parsed "Other" columns; 5/6/7 are new columns. The
# indices are never a schema key — they only join votes to candidates in
# build_votes_fact and are then discarded in favour of the electoral-vote rank.
OTHER_CANDIDATES_2016: tuple[dict[str, Any], ...] = (
    {"name": "Bernie Sanders", "col_ind": 2, "state": "Vermont"},
    {"name": "Ron Paul", "col_ind": 4, "state": "Texas"},
    {"name": "John Kasich", "col_ind": 5, "state": "Ohio"},
    {"name": "Colin Powell", "col_ind": 6, "state": None},
    {"name": "Faith Spotted Eagle", "col_ind": 7, "state": "South Dakota"},
)

# Per-state electoral votes for the 2016 "Other" candidates (same Archives Notes).
# Every other (2016 state, Other col_ind) cell is zero.
OTHER_VOTES_2016: tuple[dict[str, Any], ...] = (
    {"state": "Hawaii", "col_ind": 2, "votes": 1},  # Sanders (1, Clinton elector)
    {"state": "Texas", "col_ind": 4, "votes": 1},  # Paul (1, Trump elector)
    {"state": "Texas", "col_ind": 5, "votes": 1},  # Kasich (1, Trump elector)
    {"state": "Washington", "col_ind": 6, "votes": 3},  # Powell (3, Clinton electors)
    {"state": "Washington", "col_ind": 7, "votes": 1},  # Faith Spotted Eagle (1)
)

# --- pre-1892 "Others" aggregate columns (EC coverage extension, #32) ----------
# Several 19th-century Table 2 pages collapse the minor presidential candidates into
# a single "Others" column (parsed with state=None, like 2016's "Other"). Each is
# split back here into its named candidates with the per-state electoral votes read
# from that year's Archives Notes ("<State> cast N votes for <Name> as President").
# Following the 2016 pattern, the first named candidate reuses the parsed "Others"
# col_ind; the rest take fresh indices. col_ind is only a votes<->candidate join key
# (build_votes_fact), never a schema key. The ``state`` is each candidate's HOME
# state (not a state they won). Every split below is verified to reproduce the parsed
# Others column per state and to match the candidate's known national EC total.

# 1824 — Crawford (41) + Clay (37) collapsed into "Others". Their per-state votes and
# home states come from the Archives Notes ("William H. Crawford, of Georgia; and
# Henry Clay, of Kentucky"). https://www.archives.gov/electoral-college/1824
OTHER_CANDIDATES_1824: tuple[dict[str, Any], ...] = (
    {"name": "William H. Crawford", "col_ind": 3, "state": "Georgia"},
    {"name": "Henry Clay", "col_ind": 4, "state": "Kentucky"},
)
OTHER_VOTES_1824: tuple[dict[str, Any], ...] = (
    {"state": "Delaware", "col_ind": 3, "votes": 2},  # Crawford
    {"state": "Georgia", "col_ind": 3, "votes": 9},
    {"state": "Maryland", "col_ind": 3, "votes": 1},
    {"state": "New York", "col_ind": 3, "votes": 5},
    {"state": "Virginia", "col_ind": 3, "votes": 24},
    {"state": "Kentucky", "col_ind": 4, "votes": 14},  # Clay
    {"state": "Missouri", "col_ind": 4, "votes": 3},
    {"state": "New York", "col_ind": 4, "votes": 4},
    {"state": "Ohio", "col_ind": 4, "votes": 16},
)

# 1832 — Floyd (11, South Carolina's Nullifier slate) + Wirt (7, Anti-Masonic).
# https://www.archives.gov/electoral-college/1832
OTHER_CANDIDATES_1832: tuple[dict[str, Any], ...] = (
    {"name": "John Floyd", "col_ind": 3, "state": "Virginia"},
    {"name": "William Wirt", "col_ind": 4, "state": "Maryland"},
)
OTHER_VOTES_1832: tuple[dict[str, Any], ...] = (
    {"state": "South Carolina", "col_ind": 3, "votes": 11},  # Floyd
    {"state": "Vermont", "col_ind": 4, "votes": 7},  # Wirt
)

# 1836 — the three anti-Van-Buren Whig candidates: White (26), Webster (14),
# Mangum (11). https://www.archives.gov/electoral-college/1836
OTHER_CANDIDATES_1836: tuple[dict[str, Any], ...] = (
    {"name": "Hugh L. White", "col_ind": 3, "state": "Tennessee"},
    {"name": "Daniel Webster", "col_ind": 4, "state": "Massachusetts"},
    {"name": "Willie P. Mangum", "col_ind": 5, "state": "North Carolina"},
)
OTHER_VOTES_1836: tuple[dict[str, Any], ...] = (
    {"state": "Georgia", "col_ind": 3, "votes": 11},  # White
    {"state": "Tennessee", "col_ind": 3, "votes": 15},
    {"state": "Massachusetts", "col_ind": 4, "votes": 14},  # Webster
    {"state": "South Carolina", "col_ind": 5, "votes": 11},  # Mangum
)

# 1860 — Breckinridge (72, Southern Democrat) + Bell (39, Constitutional Union).
# https://www.archives.gov/electoral-college/1860
OTHER_CANDIDATES_1860: tuple[dict[str, Any], ...] = (
    {"name": "John C. Breckinridge", "col_ind": 3, "state": "Kentucky"},
    {"name": "John Bell", "col_ind": 4, "state": "Tennessee"},
)
OTHER_VOTES_1860: tuple[dict[str, Any], ...] = (
    {"state": "Alabama", "col_ind": 3, "votes": 9},  # Breckinridge
    {"state": "Arkansas", "col_ind": 3, "votes": 4},
    {"state": "Delaware", "col_ind": 3, "votes": 3},
    {"state": "Florida", "col_ind": 3, "votes": 3},
    {"state": "Georgia", "col_ind": 3, "votes": 10},
    {"state": "Louisiana", "col_ind": 3, "votes": 6},
    {"state": "Maryland", "col_ind": 3, "votes": 8},
    {"state": "Mississippi", "col_ind": 3, "votes": 7},
    {"state": "North Carolina", "col_ind": 3, "votes": 10},
    {"state": "South Carolina", "col_ind": 3, "votes": 8},
    {"state": "Texas", "col_ind": 3, "votes": 4},
    {"state": "Kentucky", "col_ind": 4, "votes": 12},  # Bell
    {"state": "Tennessee", "col_ind": 4, "votes": 12},
    {"state": "Virginia", "col_ind": 4, "votes": 15},
)

# Year-keyed registries dispatching the faithless/"Other" aggregate-column split.
# 2016 was the first such correction; extending EC coverage below 1892 (#32) adds
# the 19th-century years above whose Table 2 collapses minor candidates into an
# "Other(s)" column. apply_other_candidates and _votes_matrix iterate these maps and
# apply each correction only to the years actually being ingested, so a subset run
# (e.g. {2020}) never injects another year's Other candidates. Add a new year by
# registering its two entries here (plus a test + docs/corrections.md row).
OTHER_CANDIDATES: Mapping[int, tuple[dict[str, Any], ...]] = {
    1824: OTHER_CANDIDATES_1824,
    1832: OTHER_CANDIDATES_1832,
    1836: OTHER_CANDIDATES_1836,
    1860: OTHER_CANDIDATES_1860,
    2016: OTHER_CANDIDATES_2016,
}
OTHER_VOTES: Mapping[int, tuple[dict[str, Any], ...]] = {
    1824: OTHER_VOTES_1824,
    1832: OTHER_VOTES_1832,
    1836: OTHER_VOTES_1836,
    1860: OTHER_VOTES_1860,
    2016: OTHER_VOTES_2016,
}

# Table-2 candidate spellings unified to their canonical (Table-1 / later-year)
# form. Each maps a raw parsed ``name`` to its canonical full name + middle
# initial. Applied to ``candidates_df`` *before* the multi-state aggregation (so
# Trump's two state rows collapse into one) and, via reconcile_vote_candidate_names,
# to the votes-side names *before* the votes<->candidate join.
#   - Trump:    2016 Table 2 prints "Donald Trump"; 2020 prints "Donald J. Trump".
#   - McGovern: 1972 Table 2 prints "George McGovern"; Table 1 has "George S. McGovern".
CANDIDATE_NAME_FIXES: Mapping[str, dict[str, str]] = {
    "Donald Trump": {"name": "Donald J. Trump", "name_middle": "J."},
    "George McGovern": {"name": "George S. McGovern", "name_middle": "S."},
}

# Table-1 (party) candidate spellings unified to their Table-2 form so the two
# tables' names reconcile. "Bob Dole" (Table 1) -> "Robert Dole" (Table 2, 1996).
PARTY_NAME_FIXES: Mapping[str, str] = {"Bob Dole": "Robert Dole"}

# Trailing footnote marker the Archives appends to a candidate's name in a single
# year's table when a note applies to them. Table 2 for 1944 prints
# "Franklin D. Roosevelt*" (the page footnotes that he died in office the following
# April); every other year prints him unmarked. The "*" is not part of the name, and
# left in it splits one person across two canonical keys — "Franklin D. Roosevelt"
# (1932-1940) vs. "Franklin D. Roosevelt*" (1944) — which would give FDR a second,
# party-less candidate row and break the D006 canonical candidate key that both PV
# sources reconcile onto (#38 UCSB, #67 MIT). Stripped from both tables' names at
# normalize time so the marker never reaches the canonical `name`. A no-op for every
# unmarked name; 1944 FDR is the only affected candidate in current coverage.
# Source: https://www.archives.gov/electoral-college/1944 (Table 2 + Notes); see
# docs/corrections.md.
_NAME_FOOTNOTE_MARKER_RE = re.compile(r"\s*\*+$")


def strip_name_footnote_markers(name: str) -> str:
    """Strip a trailing Archives footnote marker (``*``) from a candidate name."""
    return _NAME_FOOTNOTE_MARKER_RE.sub("", name)


def strip_footnote_markers_column(df: pd.DataFrame) -> pd.DataFrame:
    """Strip footnote markers from ``president_candidate_name`` in ``df``, in place.

    The frame-level form used by the Table-1/Table-2 normalizers. Vectorized via
    ``.str.replace`` rather than ``.map(strip_name_footnote_markers)`` so it is
    null-safe (a NaN name passes through as NaN, not a ``TypeError``) and a no-op when
    the frame is empty and the column is absent — keeping the normalizers total, as they
    were before the strip was introduced. Returns ``df`` for chaining.
    """
    col = "president_candidate_name"
    if col in df.columns:
        df[col] = df[col].str.replace(_NAME_FOOTNOTE_MARKER_RE, "", regex=True)
    return df

# Table-1 party *labels* normalized to one canonical code before aggregation, so the
# same party reads identically across candidates and years and label drift does not
# spuriously populate party_2. The Archives prints the early-era Democratic-Republican
# party inconsistently — "Democratic-Republican" (1824 winner Jackson, and 1804-1820)
# vs. "D-R" (1824 opponent Adams) — for the same party. Left unnormalized, Jackson's
# and Adams's 1824 party would read differently. https://www.archives.gov/electoral-college/1824
PARTY_CODE_FIXES: Mapping[str, str] = {"Democratic-Republican": "D-R"}

# Delimiter joining a candidate's distinct parties into party/party_2. Must not occur
# in any party label: "-" cannot be used because era party codes contain it ("D-R"),
# which would mis-split a single hyphenated party into a spurious party_2. "|" never
# appears in an Archives party string.
PARTY_JOIN = "|"

# Faith Spotted Eagle's two-word last name is mis-split by the generic name parser
# (middle="Spotted", last="Eagle"); the whole surname is "Spotted Eagle".
SPOTTED_EAGLE_NAME = "Faith Spotted Eagle"
SPOTTED_EAGLE_LAST = "Spotted Eagle"

# Confirmed electoral votes that were allotted to a state but never cast or counted
# — the state's electors cast FEWER votes than its allotment, so that row's
# per-candidate votes intentionally sum to ``total_electoral_votes - shortfall``.
# These are NOT scrape errors: assert_row_votes_sum_to_total adds each state's
# shortfall back before comparing, so the confirmed anomaly does not read as a
# broken parse. Keyed by *per-state* (year, state) only; the national "Totals" row's
# shortfall is derived (summed over the year's states) inside the validator, so a
# new anomaly needs one per-state entry here and never a hand-entered Totals bump.
#
# 1832 Maryland: two of Maryland's electors did not vote, so Maryland cast 8 of its
# 10 allotted votes (Jackson 3, Clay 5). The Archives Notes: "two electors from
# Maryland did not vote, making the total number of votes cast 286" (of 288 appointed)
# — so the 1832 national Totals row inherits the same 2-vote shortfall.
# Source: https://www.archives.gov/electoral-college/1832 (Notes section).
#
# 2000 District of Columbia: DC elector Barbara Lett-Simmons cast a blank ballot in
# protest of DC's lack of Congressional representation, so DC cast 2 of its 3 votes
# (Gore 2, Bush 0) — the first (and to date only) modern abstention. The National
# Archives confirmed by email that the published total=3 / cast=2 is correct; the
# 2000 national Totals row inherits the same 1-vote shortfall (538 allotted, 537
# cast). Source: https://www.archives.gov/electoral-college/2000 (Notes section) and
# the Archives' email reply; see docs/corrections.md.
ELECTORAL_VOTE_SHORTFALLS: Mapping[tuple[int, str], int] = {
    (1832, "Maryland"): 2,
    (2000, "District of Columbia"): 1,
}

# Contingent elections: the candidate who *assumed office* is NOT the Electoral
# College leader. Keyed by year -> the full name of the candidate the House elected.
# For every other year the office-holder is the EC rank-1 candidate, so ``took_office``
# is derived from ``president_electoral_rank == 1`` and only these years override it
# (see _add_took_office). Keeping EC-winner derivable from the rank means the two facts
# never duplicate, so E6/E7 flip logic has one unambiguous "who won under EC"
# (#29, D010).
#
# 1824: no candidate reached an Electoral College majority (131 of 261 needed). Jackson
# led with 99 electoral votes (rank 1), but under the 12th Amendment the House elected
# John Quincy Adams (84 EC votes, rank 2), who took office.
# Source: https://www.archives.gov/electoral-college/1824 (Notes section).
#
# Scope: 1824 is the only contingent election inside the loaded EC coverage (post-1804
# spine, #32) and is therefore the one case exercised/tested. 1800 (pre-12th-Amendment:
# electors cast two undifferentiated presidential votes, Jefferson/Burr tied 73-73 — a
# vote structure the president_electoral_votes model does not represent, and below the
# 1804 load floor) and 1836 (a *VP-only* contingency: the Senate chose the VP, while
# president Van Buren won normally, so there is no president-level divergence to mark)
# are out of the loaded/tested scope here. A president-level ``took_office`` neither
# covers nor precludes them; their office outcomes become markable when those eras are
# ingested under the deferred pre-12th-Amendment epic (D010). See docs/corrections.md.
CONTINGENT_OFFICE_HOLDERS: Mapping[int, str] = {
    1824: "John Quincy Adams",
}

# The literal state label the parser gives the per-year national totals row (Table 2's
# final row). The votes matrix carries it verbatim until build_votes_fact NULLs it out.
TOTALS_ROW_LABEL = "Totals"

# The TIGER state shapefile carries these five US territories in its NAME column;
# they are not states and are dropped so the state dimension is the 50 states + DC.
TERRITORY_NAMES: frozenset[str] = frozenset({
    "American Samoa",
    "Commonwealth of the Northern Mariana Islands",
    "Guam",
    "Puerto Rico",
    "United States Virgin Islands",
})

# Raw TIGER columns kept, and their warehouse names. NAME is the join key (dropped
# after). The final state_df column order is spelled out in STATE_COLUMN_ORDER.
STATE_COLUMN_RENAMES: Mapping[str, str] = {
    "REGION": "region",
    "DIVISION": "division",
    "STATENS": "statens",
    "GEOID": "geoid",
    "STUSPS": "state_usps",
    "ALAND": "area_land",
    "AWATER": "area_water",
    "INTPTLAT": "latitude",
    "INTPTLON": "longitude",
}
STATE_COLUMN_ORDER: tuple[str, ...] = (
    "state",
    "state_usps",
    "region",
    "division",
    "statens",
    "geoid",
    "area_land",
    "area_water",
    "latitude",
    "longitude",
)

# Final votes_df column order (the load contract for #28); votes_id is prepended
# after the deterministic sort assigns it.
VOTES_COLUMN_ORDER: tuple[str, ...] = (
    "year",
    "state",
    "is_total",
    "candidate_id",
    "total_electoral_votes",
    "president_electoral_votes",
    "president_electoral_rank",
    "took_office",
)

# --- canonical keys (the cross-source reconciliation spine, D006 / #30) ----
# EC (National Archives) data is the source of truth every popular-vote source
# (E4 UCSB, E5 MIT) reconciles onto (D006). Two canonical keys form that spine;
# docs/canonical-keys.md is the browsable catalog. This story only *fixes and
# documents* the keys — the reconciliation itself is deferred to #38 / the E6 join.
#
# The spine is two-tier by design:
#   - Human/display PK — what the warehouse stores and people read:
#       candidate -> the reconciled full ``name``  (CANDIDATE_KEY)
#       state     -> the full ``state`` name        (STATE_KEY)
#   - Machine match target — the stable, format-normalized columns a PV source
#     maps onto, because its display strings never match the Archives' verbatim
#     (UCSB prints "BIDEN, JOSEPH R. JR"; MIT carries state_po/state_fips):
#       candidate -> the parsed name parts (CANDIDATE_MATCH_COLUMNS)
#       state     -> the USPS code          (STATE_MATCH_COLUMN)
#
# candidate_id is deliberately NOT canonical: build_candidate_dim assigns it as a
# 1-based, row-order surrogate, so it shifts whenever the candidate set or its
# order changes (e.g. extending coverage below 1892, #32). It is an internal join
# key only — never a cross-source reconciliation key, never an externally-exposed
# identifier. A durable public id (e.g. a name slug) is out of scope until one is
# actually needed (see docs/canonical-keys.md).
CANDIDATE_KEY = "name"
STATE_KEY = "state"
CANDIDATE_MATCH_COLUMNS: tuple[str, ...] = (
    "name_first",
    "name_middle",
    "name_last",
    "name_suffix",
)
STATE_MATCH_COLUMN = "state_usps"

# At most two home states are representable per candidate (state + state_2); more
# than two distinct states in one candidate group is either a genuinely 3-state
# candidate (extend the schema deliberately) or two different people colliding on
# one full name — the canonical-candidate-key failure mode _candidate_states guards.
MAX_HOME_STATES = 2

_JR_SUFFIX_RE = re.compile(r",? Jr\.?$")


class TransformError(RuntimeError):
    """Raised when a transform invariant the notebook asserted inline is violated.

    The notebook printed ``Q: ... A: {check}`` lines and read the boolean by eye.
    Raising a typed, message-carrying exception instead surfaces a scrape/parse
    regression (a broken grain, a dropped candidate, a totals mismatch) loudly at
    the step that detected it rather than letting a bad frame reach the DB load.
    """


# --- name-part parsing -----------------------------------------------------


def get_name_middle_last(middle_last: str | None) -> tuple[str | None, str | None]:
    """Split the post-first-name remainder into (middle, last).

    One token is the last name (no middle); two or more tokens take the first as
    the middle and the rest as the last name (any internal space is part of the
    last name). ``None``/empty yields ``(None, None)``. Ported verbatim from the
    notebook's ``get_name_middle_last``.
    """
    try:
        parts = middle_last.split()  # type: ignore[union-attr]
    except AttributeError:
        parts = []
    if len(parts) == 1:
        return (None, parts[0])
    if len(parts) > 1:
        return (parts[0], " ".join(parts[1:]))
    return (None, None)


def split_name(full_name: str) -> dict[str, str | None]:
    """Parse a full name into first / middle / last / suffix parts.

    The first whitespace-delimited token is the first name; a trailing ``Jr.``
    (with or without a comma) is stripped from the remainder before the
    middle/last split and re-surfaced as ``name_suffix``.
    """
    first, _, remainder = full_name.partition(" ")
    stripped = _JR_SUFFIX_RE.sub("", remainder) if remainder else None
    name_middle, name_last = get_name_middle_last(stripped)
    return {
        "name_first": first,
        "name_middle": name_middle,
        "name_last": name_last,
        "name_suffix": "Jr." if full_name.endswith("Jr.") else None,
    }


# --- Table 2: candidate-state records --------------------------------------


def normalize_candidate_states(
    parsed_years: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Flatten every year's Table 2 candidate/home-state records + apply 2016 Other.

    ``pd.json_normalize`` on the ``t2.candidate_state`` path yields one row per
    (year, candidate column) with ``president_candidate_name``, ``col_ind`` and
    ``president_candidate_state``. The 2016 "Other" placeholder columns are then
    replaced with the named faithless candidates (see :func:`apply_other_candidates`).
    """
    t2_states = pd.json_normalize(
        list(parsed_years), ["t2", "candidate_state"], ["year"]
    )
    t2_states = strip_footnote_markers_column(t2_states)
    return apply_other_candidates(t2_states)


def apply_other_candidates(t2_states: pd.DataFrame) -> pd.DataFrame:
    """Replace parsed "Other(s)" placeholder columns with named candidates.

    The parser leaves an aggregate-column candidate as ``name="Other"`` /
    ``"Others"`` with ``state=None`` (e.g. 2016's faithless electors, 1824's
    Crawford+Clay). Here those placeholder rows are dropped and each affected
    year's registered recipients (:data:`OTHER_CANDIDATES`) appended. Only years
    actually present in ``t2_states`` are injected, so a subset run never pulls in
    another year's Other candidates. Keyed by year (not the notebook's absolute row
    indices) so it holds on any subset of years. Raises :class:`TransformError` if a
    placeholder appears in a year with no registered correction.
    """
    placeholder = t2_states["president_candidate_state"].isna()
    present_other_years = set(t2_states.loc[placeholder, "year"])
    bad_years = present_other_years - set(OTHER_CANDIDATES)
    if bad_years:
        raise TransformError(
            f"Unnamed 'Other(s)' candidate column(s) in year(s) {sorted(bad_years)} "
            "with no registered correction; add an OTHER_CANDIDATES[year] entry "
            "(see OTHER_CANDIDATES_2016)"
        )
    added = pd.DataFrame(
        [
            {
                "president_candidate_name": c["name"],
                "col_ind": c["col_ind"],
                "president_candidate_state": c["state"],
                "year": year,
            }
            for year in present_other_years
            for c in OTHER_CANDIDATES[year]
        ]
    )
    kept = t2_states.loc[~placeholder]
    if added.empty:
        return kept.sort_values(["year", "col_ind"]).reset_index(drop=True)
    return (
        pd.concat([kept, added], axis=0)
        .sort_values(["year", "col_ind"])
        .reset_index(drop=True)
    )


def reconcile_vote_candidate_names(t2_states: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``t2_states`` with vote-side names reconciled to canonical.

    The votes fact joins to ``candidates_df`` on candidate *name*, so the Table-2
    names carried on the vote rows must first be rewritten to the canonical
    spellings (:data:`CANDIDATE_NAME_FIXES`) that ``build_candidate_dim`` produced.
    Returns a new frame — ``t2_states`` has two consumers (the candidate dim and
    the votes fact) and must not be mutated across that boundary.
    """
    reconciled = t2_states.copy()
    for raw, fix in CANDIDATE_NAME_FIXES.items():
        reconciled.loc[
            reconciled["president_candidate_name"] == raw, "president_candidate_name"
        ] = fix["name"]
    return reconciled


# --- Table 1: candidate-party records --------------------------------------


def normalize_candidate_parties(
    parsed_years: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Flatten every year's Table 1 candidate/party records.

    One row per year/candidate.
    """
    t1 = pd.json_normalize(list(parsed_years), "t1", ["year"])
    return strip_footnote_markers_column(t1)


# --- candidate dimension ---------------------------------------------------


def build_candidate_dim(t2_states: pd.DataFrame, t1: pd.DataFrame) -> pd.DataFrame:
    """Build the candidate dimension from Table 2 states and Table 1 parties.

    Unique (name, state) combos are name-parsed, corrected, then aggregated so a
    candidate spanning multiple states becomes one row with primary ``state`` +
    secondary ``state_2``. Parties are aggregated the same way into
    ``party``/``party_2`` and left-joined on the reconciled name. A 1-based
    ``candidate_id`` PK is assigned. Missing home states / parties are left as
    pandas NA; the DB write boundary (:func:`usvote.db.insert_df_into_table`) maps
    NA to SQL ``NULL``. Raises :class:`TransformError` if the grain (one row per
    candidate) or the Table-1/Table-2 name reconciliation is violated.
    """
    states = _candidate_states(t2_states)
    parties = _candidate_parties(t1)

    assert_names_reconciled(
        set(parties["name"]),
        set(states["name"]),
        "Table 1 party names not all present among Table 2 candidate names",
    )

    candidates = states.merge(parties, how="left", on="name", validate="1:1")
    # The party left-join must neither drop nor duplicate a Table-2 candidate.
    assert_count_equals(
        len(candidates), len(states), "candidate count changed in party join"
    )
    candidates.insert(0, "candidate_id", range(1, len(candidates) + 1))

    assert_unique_grain(candidates, "name", "candidate")
    return candidates


def _candidate_states(t2_states: pd.DataFrame) -> pd.DataFrame:
    """Table 2 -> per-candidate name parts + primary/secondary home state."""
    states = (
        t2_states[["president_candidate_name", "president_candidate_state"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .rename(
            columns={
                "president_candidate_name": "name",
                "president_candidate_state": "state",
            }
        )
    )
    name_parts = pd.DataFrame(
        list(states["name"].map(split_name)), index=states.index
    )
    states = pd.concat([states, name_parts], axis=1)

    # Correct the mis-split "Faith Spotted Eagle" surname, then unify the Table-2
    # name spellings that differ from their canonical form (Trump NY vs FL,
    # McGovern) *before* aggregating, so multi-state rows collapse together.
    fse = states["name"] == SPOTTED_EAGLE_NAME
    states.loc[fse, "name_middle"] = None
    states.loc[fse, "name_last"] = SPOTTED_EAGLE_LAST
    for raw, fix in CANDIDATE_NAME_FIXES.items():
        match = states["name"] == raw
        for col, value in fix.items():
            states.loc[match, col] = value

    # Aggregate multi-state candidates: join their distinct, non-null home states
    # with "-" in first-appearance order (sort=False), then split into state/state_2.
    key_cols = ["name", "name_first", "name_middle", "name_last", "name_suffix"]
    by_candidate = states.groupby(key_cols, sort=False, dropna=False)["state"]

    # Canary (D006 / #30): the split below keeps only the first two states, so a
    # third would vanish silently. Because a groupby always yields unique keys, the
    # downstream one-row-per-name grain check cannot see a same-name collision either
    # — it surfaces here as an over-count. Fail loud instead of dropping data.
    over_key = by_candidate.agg(lambda col: col.dropna().nunique()) > MAX_HOME_STATES
    if over_key.any():
        collided = sorted({key[0] for key in over_key.index[over_key]})
        raise TransformError(
            f"canonical candidate key: {collided} aggregate to more than "
            f"{MAX_HOME_STATES} home states, unrepresentable in the state/state_2 "
            "model (a new multi-state candidate, or two people sharing one full "
            "name — see docs/canonical-keys.md)"
        )

    # Join the DISTINCT, non-null states (dict.fromkeys preserves first-appearance
    # order): dropping nulls keeps a candidate's real state out of a NULL-primary
    # slot when an earlier appearance had no home state, and de-duplicating keeps the
    # token count equal to the canary's distinct-state count above — so the split
    # below can never mangle state_2 into a hyphen composite or an empty string.
    grouped = by_candidate.agg(
        lambda col: "-".join(dict.fromkeys(s for s in col if not pd.isna(s)))
    ).reset_index()
    split = grouped["state"].str.split("-", n=1, expand=True)
    grouped["state"] = split[0]
    grouped["state_2"] = split[1] if split.shape[1] > 1 else None
    grouped.loc[grouped["state"] == "", "state"] = None

    assert_unique_grain(grouped, "name", "candidate (Table 2 states)")
    return grouped


def _candidate_parties(t1: pd.DataFrame) -> pd.DataFrame:
    """Table 1 -> per-candidate primary/secondary party."""
    parties = (
        t1[["president_candidate_name", "president_candidate_party"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .rename(
            columns={
                "president_candidate_name": "name",
                "president_candidate_party": "party",
            }
        )
    )
    parties["name"] = parties["name"].replace(dict(PARTY_NAME_FIXES))
    # Normalize label drift (e.g. "Democratic-Republican" -> "D-R") *before*
    # aggregation, then re-dedupe so a candidate whose two labels were the same party
    # collapses to one row instead of a spurious two-party aggregation.
    parties["party"] = parties["party"].replace(dict(PARTY_CODE_FIXES))
    parties = parties.drop_duplicates()

    if parties.empty:
        # No Table-1 rows (e.g. a fixture of faithless-only candidates); every
        # candidate left-joins to a null party.
        return pd.DataFrame(columns=["name", "party", "party_2"])

    parties = parties.groupby("name")["party"].agg(PARTY_JOIN.join).reset_index()
    split = parties["party"].str.split(PARTY_JOIN, expand=True)
    parties["party"] = split[0]
    # Secondary party is the full second label (any tertiary is dropped) — keep it
    # intact rather than truncating to one char, so historical multi-word labels
    # like "Whig" / "National Republican" survive in party_2 (a varchar) instead of
    # collapsing to a meaningless "W" / "N".
    parties["party_2"] = split[1] if split.shape[1] > 1 else None

    assert_unique_grain(parties, "name", "candidate (Table 1 parties)")
    return parties


# --- state dimension -------------------------------------------------------


def load_state_geo(shapefile_path: str) -> pd.DataFrame:
    """Read the TIGER state shapefile into a plain-pandas geo frame (untested seam).

    Drops the geometry and the columns the warehouse does not use, returning a
    non-geopandas ``DataFrame`` so every downstream transform (rename, astype,
    reorder, the ``build_state_dim`` join) is exercised on ordinary pandas and
    tests can inject a small fake frame. This is the package's only geopandas read;
    the hardcoded path becomes config in E2-S6 (#31).
    """
    import geopandas as gpd  # local import: keep geopandas out of the tested core

    usa = gpd.read_file(shapefile_path)
    drop_cols = ["STATEFP", "LSAD", "MTFCC", "FUNCSTAT", "geometry"]
    return pd.DataFrame(usa.drop(columns=drop_cols))


def build_state_dim(state_geo: pd.DataFrame) -> pd.DataFrame:
    """Build the state dimension: 50 states + DC joined to their geo attributes.

    ``state_geo`` is the plain-pandas TIGER frame (see :func:`load_state_geo`) with
    a ``NAME`` column; territories are dropped, the survivors inner-joined by name,
    columns renamed/typed, and ordered to :data:`STATE_COLUMN_ORDER`. Raises
    :class:`TransformError` if the state grain is not one row per state.
    """
    states = state_geo[~state_geo["NAME"].isin(TERRITORY_NAMES)]
    state_df = pd.DataFrame({"state": sorted(states["NAME"])})
    state_df = state_df.merge(
        states, how="inner", left_on="state", right_on="NAME", validate="1:1"
    )
    state_df = state_df.drop(columns=["NAME"]).rename(
        columns=dict(STATE_COLUMN_RENAMES)
    )
    state_df = state_df.astype(
        {"region": "int", "division": "int", "latitude": "float", "longitude": "float"}
    )
    state_df = state_df[list(STATE_COLUMN_ORDER)]

    assert_unique_grain(state_df, "state", "state")
    return state_df


# --- votes fact ------------------------------------------------------------


def build_votes_fact(
    parsed_years: Sequence[Mapping[str, Any]],
    t2_states: pd.DataFrame,
    candidates: pd.DataFrame,
    state_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the votes fact by melting the votes matrix and joining both dims.

    ``t2_states`` must already be name-reconciled (see
    :func:`reconcile_vote_candidate_names`) and ``candidates`` already corrected,
    so the (year, col_ind) and name joins resolve. The per-state matrix is melted
    long, joined to the candidate + state dims, shaped with ``is_total`` (state is
    NULL for a year's totals row) and a per-year electoral-vote rank, then given a
    ``votes_id`` PK after a deterministic sort. Raises :class:`TransformError` if a
    per-year/candidate totals value disagrees with the sum over its states.
    """
    votes_matrix = _votes_matrix(parsed_years)
    candidate_cols = [c for c in votes_matrix.columns if isinstance(c, int)]
    assert_row_votes_sum_to_total(votes_matrix, candidate_cols)

    votes = pd.melt(
        votes_matrix,
        id_vars=["year", "state", "total_electoral_votes"],
        value_vars=candidate_cols,
        var_name="col_ind",
        value_name="president_electoral_votes",
    ).dropna(subset=["president_electoral_votes"])
    votes = votes.astype({"president_electoral_votes": "int"})

    # Attach candidate metadata (name via year/col_ind, then candidate_id via name)
    # and mark totals rows (state not in the state dim -> NULL state, is_total).
    votes = votes.merge(
        t2_states[["year", "col_ind", "president_candidate_name"]],
        how="inner",
        on=["year", "col_ind"],
        validate="m:1",
    )
    # Guard the inner join: an unreconciled vote-side name would otherwise drop
    # that candidate's whole record (state rows AND totals row together), which
    # assert_totals_equal_state_sum cannot detect since both sides of the sum
    # vanish. Ported from the notebook's cell-167 name-diff check.
    assert_names_reconciled(
        set(votes["president_candidate_name"]),
        candidates["name"],
        "vote candidate names not present in the candidate dimension",
    )
    votes = votes.merge(
        candidates[["candidate_id", "name"]],
        how="inner",
        left_on="president_candidate_name",
        right_on="name",
        validate="m:1",
    )
    votes = votes.merge(
        state_df[["state"]], how="left", on="state", indicator=True, validate="m:1"
    )
    votes["is_total"] = votes["_merge"].eq("left_only")
    votes.loc[votes["is_total"], "state"] = None
    votes = votes.drop(columns=["president_candidate_name", "name", "_merge"])

    votes = _add_electoral_rank(votes)
    # took_office is already boolean (from the `== 1` comparison + boolean overrides
    # in _add_took_office), so it needs no cast here.
    votes = _add_took_office(votes, candidates)
    votes = votes.astype({"year": "int", "is_total": "bool"})[list(VOTES_COLUMN_ORDER)]
    votes = votes.sort_values(
        ["year", "state", "is_total", "candidate_id", "president_electoral_rank"],
        ignore_index=True,
    )
    votes.insert(0, "votes_id", range(1, len(votes) + 1))

    assert_totals_equal_state_sum(votes)
    assert_state_count_by_year(parsed_years, votes)
    assert_rectangular_state_grain(votes)
    return votes


def _votes_matrix(parsed_years: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Flatten votes-by-state records and fold in the 2016 "Other" vote data.

    ``pd.json_normalize`` widens the per-candidate electoral votes into integer
    columns (1..N). The 2016 correction zeroes the reused "Other" columns, writes
    the per-state Other votes, and sums them into the 2016 totals row.
    """
    matrix = pd.json_normalize(
        list(parsed_years), ["t2", "votes_by_state"], ["year"]
    )
    for year, candidates in OTHER_CANDIDATES.items():
        year_mask = matrix["year"] == year
        if not year_mask.any():
            continue
        # Zero every Other column for this year (creating any new column indices),
        # set the per-state Other votes, then recompute this year's totals row for
        # those columns so the derived totals can never drift from the per-state data.
        other_cols = [c["col_ind"] for c in candidates]
        matrix.loc[year_mask, other_cols] = 0
        for ov in OTHER_VOTES[year]:
            row = year_mask & (matrix["state"] == ov["state"])
            matrix.loc[row, ov["col_ind"]] = ov["votes"]
        totals_row = year_mask & (matrix["state"] == TOTALS_ROW_LABEL)
        state_rows = year_mask & (matrix["state"] != TOTALS_ROW_LABEL)
        matrix.loc[totals_row, other_cols] = (
            matrix.loc[state_rows, other_cols].sum(axis=0).values
        )
    return matrix


def _add_electoral_rank(votes: pd.DataFrame) -> pd.DataFrame:
    """Attach each candidate's per-year electoral-vote rank (from the totals rows)."""
    totals = votes.loc[
        votes["state"].isna(),
        ["year", "candidate_id", "col_ind", "president_electoral_votes"],
    ].copy()
    totals["president_electoral_rank"] = (
        totals.groupby("year")["president_electoral_votes"]
        .rank("dense", ascending=False)
        .astype("int")
    )
    totals = totals.drop(columns=["president_electoral_votes"])
    ranked = votes.merge(
        totals, how="inner", on=["year", "candidate_id", "col_ind"], validate="m:1"
    )
    return ranked.drop(columns=["col_ind"])


def _add_took_office(votes: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Mark the candidate who assumed the presidency (broadcast to all their rows).

    Defaults to the Electoral College winner (``president_electoral_rank == 1``); for
    the contingent elections in :data:`CONTINGENT_OFFICE_HOLDERS` — where the House
    elected a president other than the EC leader — the office-holder is overridden by
    name. EC-winner stays derivable from the rank so the two facts never duplicate
    (#29, D010). Like the rank, ``took_office`` is broadcast to every one of a
    candidate's rows, so a state-row query is not a "only meaningful when is_total"
    trap. Raises :class:`TransformError` if a contingent office-holder for a loaded
    year is absent from the candidate dimension (a name that failed to reconcile).
    """
    votes = votes.copy()
    votes["took_office"] = votes["president_electoral_rank"] == 1
    name_to_id = candidates.set_index("name")["candidate_id"]
    for year, holder in CONTINGENT_OFFICE_HOLDERS.items():
        year_mask = votes["year"] == year
        if not year_mask.any():
            continue  # this year not in the current (possibly subset) run
        if holder not in name_to_id.index:
            raise TransformError(
                f"contingent office-holder {holder!r} for {year} not present in the "
                "candidate dimension"
            )
        votes.loc[year_mask, "took_office"] = (
            votes.loc[year_mask, "candidate_id"] == name_to_id[holder]
        )
    return votes


# --- validators (load-bearing; each raises TransformError) ------------------


def assert_unique_grain(df: pd.DataFrame, subset: str, label: str) -> None:
    """Raise unless every value of ``subset`` is unique (one row per ``label``)."""
    duplicated = df[subset][df[subset].duplicated()].tolist()
    if duplicated:
        raise TransformError(
            f"{label} grain broken: {subset} not unique (duplicates: {duplicated})"
        )


def assert_names_reconciled(
    source: Container[str], target: Iterable[str], message: str
) -> None:
    """Raise unless every name in ``source`` also appears in ``target``."""
    target_set = set(target)
    missing = {name for name in source if name not in target_set}  # type: ignore[attr-defined]
    if missing:
        raise TransformError(f"{message}: {sorted(missing)}")


def assert_count_equals(actual: int, expected: int, label: str) -> None:
    """Raise unless ``actual == expected`` (a count-preserved regression guard)."""
    if actual != expected:
        raise TransformError(f"{label}: expected {expected}, got {actual}")


def assert_row_votes_sum_to_total(
    matrix: pd.DataFrame, candidate_cols: list[int]
) -> None:
    """Raise if any votes-matrix row's candidate votes != its total_electoral_votes.

    Documented electoral-vote shortfalls (:data:`ELECTORAL_VOTE_SHORTFALLS`, e.g. the
    2000 DC abstention) are added back before the comparison, so a confirmed anomaly
    — electors who cast fewer votes than their allotment — is not flagged as a broken
    parse. A per-state row uses its own shortfall; a year's national totals row uses
    the sum of that year's per-state shortfalls (derived, never hand-entered).
    """
    row_sum = matrix[candidate_cols].sum(axis=1)
    expected = matrix["total_electoral_votes"] - _expected_shortfall(matrix)
    mismatched = matrix.loc[row_sum != expected]
    if len(mismatched):
        offenders = list(zip(mismatched["year"], mismatched["state"], strict=True))
        raise TransformError(
            f"Row electoral votes do not sum to total_electoral_votes for: {offenders}"
        )


def _expected_shortfall(matrix: pd.DataFrame) -> pd.Series:
    """Per-row documented shortfall aligned to ``matrix.index`` (0 where none).

    A per-state row maps to :data:`ELECTORAL_VOTE_SHORTFALLS`; a national totals row
    (state == :data:`TOTALS_ROW_LABEL`) maps to the sum of its year's per-state
    shortfalls, so the derived totals expectation can never drift from the per-state
    truth.
    """
    shortfall_by_year: dict[int, int] = {}
    for (year, _state), n in ELECTORAL_VOTE_SHORTFALLS.items():
        shortfall_by_year[year] = shortfall_by_year.get(year, 0) + n

    def row_shortfall(row: pd.Series) -> int:
        if row["state"] == TOTALS_ROW_LABEL:
            return shortfall_by_year.get(row["year"], 0)
        return ELECTORAL_VOTE_SHORTFALLS.get((row["year"], row["state"]), 0)

    return matrix.apply(row_shortfall, axis=1)


def assert_state_count_by_year(
    parsed_years: Sequence[Mapping[str, Any]], votes: pd.DataFrame
) -> None:
    """Raise if any year lost (or gained) a state row between parse and votes.

    Ported from notebook cell 196: each year's parsed votes-by-state count (states
    + the totals row) must equal the distinct states the winning candidate ends up
    with in ``votes``. Catches a per-state row silently dropped by the inner joins
    that :func:`assert_names_reconciled` (whole-candidate drop) would miss.
    Deduplicating on (year, state) makes it robust to a rank-1 tie.
    """
    initial = {py["year"]: len(py["t2"]["votes_by_state"]) for py in parsed_years}
    final = (
        votes.loc[votes["president_electoral_rank"] == 1]
        .drop_duplicates(["year", "state"])
        .groupby("year")
        .size()
        .to_dict()
    )
    mismatched = {
        year: (count, final.get(year))
        for year, count in initial.items()
        if count != final.get(year)
    }
    if mismatched:
        raise TransformError(
            f"Per-year state count changed (year: parsed -> votes): {mismatched}"
        )


def assert_rectangular_state_grain(votes: pd.DataFrame) -> None:
    """Raise unless each year's state-level fact is rectangular: one row per
    ``(state, candidate)`` — i.e. every getter has a row in every participating state.

    The EC votes fact is **dense**: the Archives Table 2 prints ``-`` for "won no
    electoral votes here", which :func:`usvote.parse.parse_t2_votes_by_state` reads as
    ``0``, so a losing candidate is an explicit ``president_electoral_votes = 0`` row —
    never a dropped one. The EC<->PV join (:mod:`usvote.join`, D026) rests on this: an
    EC-left join preserves every loser only because their 0-EV rows exist. This asserts
    the premise (per year, ``rows == states x getters``) rather than leaving it
    emergent, so a future coverage extension below 1892 (#32) with a ragged early table
    fails loud here instead of silently dropping a loser row into a downstream gap.
    :func:`assert_state_count_by_year` only checks the rank-1 winner per state, and
    :func:`assert_totals_equal_state_sum` is blind to a dropped 0-row — this closes that
    seam. Verified to hold across all 49 currently-loaded years.

    Both a duplicate ``(state, candidate)`` row **and** full ``rows == states x
    getters`` coverage are checked: a pure count test alone has a blind spot — a
    duplicated pair
    masking a dropped one satisfies the product — so the duplicate check runs first, and
    together they prove every ``(state, candidate)`` pair is present exactly once.
    """
    state_rows = votes.loc[votes["state"].notna()]

    grain = ["year", "state", "candidate_id"]
    dupes = state_rows.loc[state_rows.duplicated(grain, keep=False)]
    if not dupes.empty:
        raise TransformError(
            "EC votes fact has duplicate (year, state, candidate_id) row(s) — grain "
            f"broken (D026): {dupes[grain].drop_duplicates().values.tolist()}"
        )

    offenders: dict[int, tuple[int, int, int]] = {}
    for year, grp in state_rows.groupby("year"):
        n_states = grp["state"].nunique()
        n_getters = grp["candidate_id"].nunique()
        if len(grp) != n_states * n_getters:
            offenders[int(year)] = (len(grp), n_states, n_getters)
    if offenders:
        raise TransformError(
            "EC votes fact not rectangular — a getter is missing a state row "
            f"(dense-fact invariant, D026). year: (rows, states, getters) = {offenders}"
        )


def assert_totals_equal_state_sum(votes: pd.DataFrame) -> None:
    """Raise if a year/candidate's scraped totals row != the sum over its states.

    The strongest end-to-end check (notebook cell 197): the electoral-vote total
    the Archives published for each candidate must equal the sum of that
    candidate's per-state electoral votes.
    """
    keys = ["year", "candidate_id"]
    state_sum = (
        votes.loc[votes["state"].notna()]
        .groupby(keys)["president_electoral_votes"]
        .sum()
    )
    scraped = (
        votes.loc[votes["state"].isna()].set_index(keys)["president_electoral_votes"]
    )
    joined = pd.concat([state_sum, scraped], axis=1, keys=["state_sum", "scraped"])
    bad = joined[joined["state_sum"] != joined["scraped"]]
    if len(bad):
        raise TransformError(
            f"Scraped vote totals != sum across states for (year, candidate_id): "
            f"{bad.index.tolist()}"
        )


# --- public entry point ----------------------------------------------------


def transform_parsed_years(
    parsed_years: Sequence[Mapping[str, Any]], state_geo: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the (candidates_df, state_df, votes_df) warehouse frames.

    ``parsed_years`` is :func:`usvote.parse.parse_election_years` output;
    ``state_geo`` is the plain-pandas TIGER frame (see :func:`load_state_geo`).
    Ordering is load-bearing: the candidate dim is built (and corrected) first, the
    Table-2 vote names are reconciled against it, and only then is the votes fact
    joined to both dims.
    """
    t2_states = normalize_candidate_states(parsed_years)
    t1 = normalize_candidate_parties(parsed_years)

    candidates_df = build_candidate_dim(t2_states, t1)
    state_df = build_state_dim(state_geo)
    votes_df = build_votes_fact(
        parsed_years, reconcile_vote_candidate_names(t2_states), candidates_df, state_df
    )
    return candidates_df, state_df, votes_df
