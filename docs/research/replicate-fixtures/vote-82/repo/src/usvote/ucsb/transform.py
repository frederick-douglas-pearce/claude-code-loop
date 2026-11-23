"""Transform & validate stage — parsed UCSB pages -> PV facts + the absence roster.

The UCSB analogue of :mod:`usvote.mit.transform`, and E4-S3 (#36). It takes the
:class:`~usvote.ucsb.parse.ParsedUCSBYear` records :mod:`usvote.ucsb.parse` emits and
produces **two** frames:

- **PV facts** on the D018 shared shape (:data:`~usvote.pv.schema.SHARED_PV_COLUMNS`),
  interchangeable with MIT's at load; and
- the **`pv_state_status` roster** (:data:`~usvote.pv.status.ROSTER_COLUMNS`) — one row
  per ``(source, year, state)`` for *every* state in that year's election, which is
  what makes popular-vote absence representable at all (D024 §3).

Everything here is pure and offline. The roster's only legitimate inputs are the **EC
spine** and :data:`UCSB_NONPARTICIPATING_STATES` (D024 §6) — never UCSB markup — and
the spine arrives by **dependency injection** as a frame, never a query, so the whole
roster including its two-way assert stays in the offline unit suite.

**Three things this stage owns that nothing upstream can.**

1. **All three ``pv_status`` values.** The parser emits only ``legislature_chosen``, the
   sole status readable from markup. ``not_participating`` has no markup whatsoever (the
   row is simply absent), and ``popular_vote`` is the **residual** — a roster state the
   parser did not flag and the constant does not list. All three are therefore assigned
   here, in one place, against the complete roster.
2. **State-label canonicalization**, via :data:`UCSB_STATE_RECONCILIATIONS`. #35 emits
   verbatim labels by design; the roster is keyed on ``dwh.state``'s canonical PK, so
   this must precede anything roster-related or the assert reports every label variant
   as a phantom state. (#38 keeps **candidate**-name reconciliation.)
3. **The cross-page two-way assert**
   (:func:`usvote.pv.status.assert_roster_covers_facts`), which needs the EC spine
   the parser deliberately cannot see.

**Ordering is load-bearing**, and each step is enforced by a test:

1. **Scope years first**, and raise if an in-scope year has no parsed page — otherwise
   the roster builds ~40 ``popular_vote`` states for it with zero facts, and the assert
   reports one missing page as forty mismatched states.
2. **Canonicalize before everything roster-related** (above). Canonicalization is a
   many-to-one rewrite, so it also *reopens* the state-vs-status overlap hole
   :func:`usvote.ucsb.parse._assert_one_status_per_state` closed on **verbatim** labels
   (``New jersey`` as a vote row beside ``New Jersey`` as a status row would collapse
   onto one state). It is therefore re-asserted here on canonical labels — the same
   reason :mod:`usvote.mit.reconcile` re-runs its grain check after its rewrite.
3. **Detect status contradictions on the *input sets*, before assembling the roster.**
   The builder's precedence chain resolves a contradictory state to one row with one
   status, destroying the evidence; a check that ran afterwards would pass on a frame
   built by silently resolving exactly what D024 says must raise.

**What is deliberately not here:** candidate-name reconciliation and the D007
candidate-scope filter (both #38 — see :func:`_build_pv_votes`); the DDL and load (#37);
NaN -> None (owned once at the DB write boundary, never an upstream ``.map``).
"""

from __future__ import annotations

from collections.abc import Collection

import numpy as np
import pandas as pd

from usvote.pv.schema import SHARED_PV_COLUMNS, assert_pv_shape
from usvote.pv.source import SOURCE_UCSB
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
    assert_roster_covers_facts,
    assert_roster_shape,
    assert_unique_roster_grain,
)
from usvote.ucsb.parse import (
    NO_POPULAR_VOTE_YEARS,
    PERCENT_TOLERANCE,
    ParsedUCSBYear,
)
from usvote.years import LATEST_ELECTION_YEAR, ec_ingest_years

# --- provenance literals ----------------------------------------------------
# ``SOURCE_UCSB`` moved to usvote.pv.source in #68 — the SSOT for source-name literals,
# where the pv_source reference table also keys on it. Re-imported above (still
# ``source -> pv``) so callers of ``usvote.ucsb.transform.SOURCE_UCSB`` (including
# ``usvote.ucsb.reconcile``) are unaffected. ``redistributable`` is *not* a column — it
# is a per-source attribute of the pv_source reference table (D017/D018), and for UCSB
# it is ``false`` pending a license answer (D022).

#: The D018 reliability values UCSB emits. UCSB publishes exact integer counts and no
#: reliability signal of its own, so rows are ``exact`` unless the page contradicts
#: itself — see :func:`_cell_reliability`. ``estimated`` is unused by this source.
RELIABILITY_EXACT = "exact"
RELIABILITY_UNRELIABLE = "unreliable"

# --- historical corrections (provenance-carrying constants) ------------------
#: States that took no part in an election at all — D024 §4 case 2, whose defining
#: property is that it has **no markup whatsoever**: the state's row is simply absent
#: from the UCSB page, and only a prose footnote elsewhere attests to it. Absence with
#: no markup cannot be parsed, so it is enumerated here, with its cause.
#:
#: All 14 entries are retained, but **only in-scope years produce roster rows**: 1868 is
#: gated out of the EC spine by ``UNSUPPORTED_EC_YEARS``, so its three are catalogued
#: but not yet ingested, pending #57 (D024 §6, clarified 2026-07-18). The consumed count
#: is 11 today and becomes 14 with no change here when #57 lands.
#:
#: The note text is **ours**, not UCSB's — unlike the verbatim legislature prose the
#: parser captures, it carries no redistributability restriction (D024/D022).
#:
#: Source: the 11 Confederate states of 1864 and the three states not yet readmitted in
#: 1868 are settled history; the 1868 trio is independently corroborated by the EC
#: spine's own note (``usvote.years.UNSUPPORTED_EC_YEARS``, "Mississippi, Texas and
#: Virginia did not participate"). Verified against the spine: every in-scope entry has
#: ``total_electoral_votes == 0`` in ``dwh.votes``
#: (:func:`assert_absence_matches_zero_ev`).
_SECEDED = "Seceded; took no part in the 1864 election during the Civil War."
_UNREADMITTED = "Not yet readmitted to the Union; took no part in the 1868 election."
UCSB_NONPARTICIPATING_STATES: dict[tuple[int, str], str] = {
    (1864, "Alabama"): _SECEDED,
    (1864, "Arkansas"): _SECEDED,
    (1864, "Florida"): _SECEDED,
    (1864, "Georgia"): _SECEDED,
    (1864, "Louisiana"): _SECEDED,
    (1864, "Mississippi"): _SECEDED,
    (1864, "North Carolina"): _SECEDED,
    (1864, "South Carolina"): _SECEDED,
    (1864, "Tennessee"): _SECEDED,
    (1864, "Texas"): _SECEDED,
    (1864, "Virginia"): _SECEDED,
    # Out of scope until #57 lifts 1868 from UNSUPPORTED_EC_YEARS. Retained, not
    # deleted: the fact is catalogued, and deferring the *ingest* is not hiding it.
    (1868, "Mississippi"): _UNREADMITTED,
    (1868, "Texas"): _UNREADMITTED,
    (1868, "Virginia"): _UNREADMITTED,
}

#: UCSB state label -> the canonical ``dwh.state`` PK (the TIGER full name). Mirrors
#: :data:`usvote.mit.reconcile.MIT_STATE_RECONCILIATIONS` in being **exhaustive** rather
#: than exceptions-only: a map that lists only the odd ones cannot tell "already
#: canonical" from "never seen", and it is the coverage guard
#: (:func:`_assert_label_coverage`) — not the map's size — that makes a new UCSB
#: spelling fail loudly instead of vanishing in a downstream join.
#:
#: Only **two** of the 53 corpus labels are non-identity, both marked below. Verified
#: across all 60 saved pages: these 53 are every distinct state label UCSB prints.
#: Source: UCSB state-column labels (https://www.presidency.ucsb.edu/statistics/
#: elections/<year>); RHS per the EC state dimension (TIGER2019,
#: ``usvote.transform.load_state_geo``).
UCSB_STATE_RECONCILIATIONS: dict[str, str] = {
    "Alabama": "Alabama",
    "Alaska": "Alaska",
    "Arizona": "Arizona",
    "Arkansas": "Arkansas",
    "California": "California",
    "Colorado": "Colorado",
    "Connecticut": "Connecticut",
    "Delaware": "Delaware",
    # 1964-2016 abbreviate DC; 2020/2024 print it in full. Both must land on the one
    # canonical spelling or DC reads as two different states across the series.
    "Dist. of Col.": "District of Columbia",
    "District of Columbia": "District of Columbia",
    "Florida": "Florida",
    "Georgia": "Georgia",
    "Hawaii": "Hawaii",
    "Idaho": "Idaho",
    "Illinois": "Illinois",
    "Indiana": "Indiana",
    "Iowa": "Iowa",
    "Kansas": "Kansas",
    "Kentucky": "Kentucky",
    "Louisiana": "Louisiana",
    "Maine": "Maine",
    "Maryland": "Maryland",
    "Massachusetts": "Massachusetts",
    "Michigan": "Michigan",
    "Minnesota": "Minnesota",
    "Mississippi": "Mississippi",
    "Missouri": "Missouri",
    "Montana": "Montana",
    "Nebraska": "Nebraska",
    "Nevada": "Nevada",
    "New Hampshire": "New Hampshire",
    "New Jersey": "New Jersey",
    "New Mexico": "New Mexico",
    "New York": "New York",
    "New jersey": "New Jersey",  # 1852 only — a lower-case "j" typo in the source
    "North Carolina": "North Carolina",
    "North Dakota": "North Dakota",
    "Ohio": "Ohio",
    "Oklahoma": "Oklahoma",
    "Oregon": "Oregon",
    "Pennsylvania": "Pennsylvania",
    "Rhode Island": "Rhode Island",
    "South Carolina": "South Carolina",
    "South Dakota": "South Dakota",
    "Tennessee": "Tennessee",
    "Texas": "Texas",
    "Utah": "Utah",
    "Vermont": "Vermont",
    "Virginia": "Virginia",
    "Washington": "Washington",
    "West Virginia": "West Virginia",
    "Wisconsin": "Wisconsin",
    "Wyoming": "Wyoming",
}


class UCSBTransformError(RuntimeError):
    """Raised when a UCSB transform validation fails.

    The UCSB analogue of :class:`usvote.mit.transform.MITTransformError` and the
    sibling of :class:`usvote.ucsb.parse.UCSBParseError` — a typed, message-carrying
    failure so a parse regression or a source change surfaces loudly here rather than
    flowing silently into the DB load.
    """


class UCSBRosterError(UCSBTransformError):
    """Raised when the roster itself cannot be built, or disagrees with the facts.

    Deliberately a **distinct type**, not just a distinct message: "the roster is empty
    for an in-scope year" and "a state mismatched" have different causes (a
    mis-sequenced pipeline vs. data drift) and different fixes, and the ACs require them
    to be separable.
    """


class UCSBMissingYearError(UCSBRosterError):
    """Raised when an in-scope year has no parsed UCSB page.

    Its own type for the same reason: one absent snapshot page would otherwise surface
    as ~40 individually mismatched states, sending the reader hunting for a state-name
    bug instead of a missing file.
    """


def ucsb_ingest_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """The default set of years the UCSB pipeline ingests.

    **Derived, never duplicated** (D024 §6, clarified 2026-07-18): the EC spine
    (:func:`usvote.years.ec_ingest_years`) minus the years UCSB publishes no popular
    vote for (:data:`usvote.ucsb.parse.NO_POPULAR_VOTE_YEARS`, 1789-1820).

    UCSB *does* publish popular vote for 1868 and 1872, but the EC spine gates them
    (``UNSUPPORTED_EC_YEARS``), and ``pv_coverage`` (D024 §8) is electoral-vote-weighted
    and so uncomputable for a year with no EC spine — ingesting them would create
    exactly the partial-coverage years D009 mandates a caveat for, with no means to
    quantify one. Because the exclusion is *derived*, #57 lifting the gate admits both
    years here with **no change in this package**; the literals ``1868``/``1872``
    deliberately appear nowhere under ``usvote/ucsb/`` (a test enforces this).
    """
    return ec_ingest_years(latest) - NO_POPULAR_VOTE_YEARS


def transform_ucsb(
    parsed_years: list[ParsedUCSBYear],
    ec_participation: pd.DataFrame,
    *,
    years: Collection[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Transform parsed UCSB pages into ``(pv_votes, pv_state_status)`` frames.

    ``ec_participation`` is the EC ``votes`` fact — the frame
    :func:`usvote.transform.transform_parsed_years` returns, or an equivalent
    ``SELECT`` of ``dwh.votes``. It must carry ``year``, ``state``, ``is_total`` and
    ``total_electoral_votes``. It is **passed in rather than queried** so every roster
    test stays offline; the caller (#37) resolves it from the in-memory frame or the DB.

    ``years`` defaults to :func:`ucsb_ingest_years`. Pass an explicit subset to process
    fewer years — the roster and the two-way assert are scoped to it, so a partial run
    never reports unprocessed years as violations.

    Returns ``(pv_votes_df, roster_df)`` — ``pv_votes_df`` on
    :data:`~usvote.pv.schema.SHARED_PV_COLUMNS`, ``roster_df`` on
    :data:`~usvote.pv.status.ROSTER_COLUMNS`. Raises :class:`UCSBTransformError` (or a
    subclass) on any validation failure.
    """
    in_scope = frozenset(ucsb_ingest_years() if years is None else years)

    scoped = _scope_years(parsed_years, in_scope)
    canonical = [_canonicalize_state_labels(parsed) for parsed in scoped]

    roster_states = _build_ec_roster(ec_participation, in_scope)
    _assert_roster_built_for_every_year(roster_states, in_scope)
    assert_no_status_contradictions(canonical, roster_states)

    pv_votes = _build_pv_votes(canonical)
    roster = _build_state_status(canonical, roster_states, in_scope)

    assert_absence_matches_zero_ev(roster, roster_states)
    assert_pv_grain(pv_votes)
    assert_no_zero_votes(pv_votes)
    assert_totals_not_exceeded(pv_votes)
    assert_pv_columns(pv_votes)
    assert_roster_shape(roster, error_cls=UCSBRosterError)
    assert_unique_roster_grain(roster, error_cls=UCSBRosterError)
    assert_note_only_on_absence(roster)
    assert_roster_covers_facts(
        pv_votes,
        roster,
        source=SOURCE_UCSB,
        years=in_scope,
        error_cls=UCSBRosterError,
        empty_roster_error_cls=UCSBRosterError,
    )
    return pv_votes, roster


# --- transform steps ---------------------------------------------------------
def _scope_years(
    parsed_years: list[ParsedUCSBYear], in_scope: frozenset[int]
) -> list[ParsedUCSBYear]:
    """Keep the in-scope years, and raise if any in-scope year has no parsed page.

    The converse check is the point. Without it a missing snapshot page yields a full
    roster of ``popular_vote`` states with zero facts, which the two-way assert reports
    as ~40 mismatched states — the right failure for the wrong reason.
    """
    seen = [parsed["year"] for parsed in parsed_years]
    duplicates = sorted({year for year in seen if seen.count(year) > 1})
    if duplicates:
        # A dict keyed on year would silently keep the last record per year, dropping
        # the first year's states — a silent drop in the stage built to prevent them.
        # The two-way assert catches the *consequence* but reports it as an unreconciled
        # label, pointing at the wrong cause. Name it here instead.
        raise UCSBTransformError(
            f"more than one parsed UCSB page for year(s) {duplicates}; the grain is "
            f"one page per election year. A batched caller passed duplicates, or two "
            f"pages parsed to the same `year`."
        )
    by_year = {parsed["year"]: parsed for parsed in parsed_years}
    missing = sorted(in_scope - set(by_year))
    if missing:
        raise UCSBMissingYearError(
            f"no parsed UCSB page for in-scope year(s) {missing}. The snapshot is "
            f"incomplete (re-run `python -m usvote.ucsb`), or narrow `years` to the "
            f"set actually being processed — do not let a missing page be read as a "
            f"year in which no state held a popular vote."
        )
    return [by_year[year] for year in sorted(in_scope)]


def _canonicalize_state_labels(parsed: ParsedUCSBYear) -> ParsedUCSBYear:
    """Rewrite every verbatim UCSB state label onto the canonical ``dwh.state`` PK.

    Applies to state rows and status rows — a status row keyed on a verbatim label
    would miss its roster state just as surely as a vote row would. Raises if any label
    is unmapped: an unmapped label would become a phantom state in the two-way assert,
    and (via ``pv_votes.state``'s FK) could not load at all.

    CD rows are **not** rewritten: :func:`_build_pv_votes` drops them wholesale (their
    votes partition the parent state's), so nothing downstream reads their labels.
    Their parent labels are still validated for coverage —
    :func:`_assert_label_coverage` checks them, catching label drift on a split-EV
    state — they are just not carried canonicalized into output nothing consumes.
    """
    _assert_label_coverage(parsed)
    fix = UCSB_STATE_RECONCILIATIONS.__getitem__
    out = dict(parsed)
    out["state_rows"] = [
        {**row, "state_label": fix(row["state_label"])} for row in parsed["state_rows"]
    ]
    out["status_rows"] = [
        {**row, "state_label": fix(row["state_label"])} for row in parsed["status_rows"]
    ]
    return out  # type: ignore[return-value]


def _build_ec_roster(
    ec_participation: pd.DataFrame, in_scope: frozenset[int]
) -> dict[int, dict[str, int]]:
    """Derive ``{year: {state: max total_electoral_votes}}`` from the EC spine.

    **Totals rows are excluded explicitly** — ``votes.state`` is NULL on them, so a
    naive ``DISTINCT year, state`` yields a NULL roster entry per year, which becomes
    either a garbage roster row or a NOT NULL violation at load (D024 §6).

    The roster is **every** distinct state, not just those with electoral votes. The
    Archives carries rows for non-participating states with ``total_electoral_votes =
    0`` (1864's 11 Confederate states), so the spine already *is* the complete roster —
    filtering to ``> 0`` would drop exactly the states the absence design exists to
    represent. The EV figure is carried only for
    :func:`assert_absence_matches_zero_ev`; it is never loaded (D024 §5 — the EC fact
    is the single source of electoral-vote truth).
    """
    _assert_participation_shape(ec_participation)
    frame = ec_participation
    rows = frame[
        (~frame["is_total"].astype(bool))
        & frame["state"].notna()
        & frame["year"].isin(in_scope)
    ]
    # `total_electoral_votes` feeds ``int(max_ev)`` below and the EV cross-check. A
    # NULL there (a nullable column in a DB read) would otherwise surface as a bare
    # ``ValueError: cannot convert float NaN to integer`` with no year/state — so name
    # it here as a typed roster error. Checked on the participating rows only, so a NaN
    # in a dropped totals row is not a false positive.
    null_ev = rows[rows["total_electoral_votes"].isna()]
    if not null_ev.empty:
        raise UCSBRosterError(
            "EC participation frame has null `total_electoral_votes` for "
            f"{null_ev[['year', 'state']].values.tolist()[:10]}; every participating "
            f"state carries an electoral-vote count in the EC fact (0 for a "
            f"non-participating state), so a null here is an upstream EC-load defect."
        )
    grouped = rows.groupby(["year", "state"])["total_electoral_votes"].max()
    roster: dict[int, dict[str, int]] = {}
    for (year, state), max_ev in grouped.items():
        roster.setdefault(int(year), {})[str(state)] = int(max_ev)
    return roster


def _assert_roster_built_for_every_year(
    roster_states: dict[int, dict[str, int]], in_scope: frozenset[int]
) -> None:
    """Raise if the EC spine yielded no roster for an in-scope year, before all else.

    This must run **before** :func:`assert_no_status_contradictions` and the two-way
    assert. Otherwise a year with legislature rows but no spine (the EC pipeline was
    run for a different year set) trips the contradiction check first — "UCSB says the
    state took part; the EC spine does not carry it" — misdiagnosing a
    pipeline-sequencing problem as a source disagreement about participation. The ACs
    require these two to stay distinct: different cause, different fix.
    """
    missing = sorted(in_scope - set(roster_states))
    if missing:
        raise UCSBRosterError(
            f"the EC spine yielded no roster for in-scope year(s) {missing}. This is a "
            f"pipeline-sequencing failure, not a state mismatch: the roster derives "
            f"from `dwh.votes`, so the EC pipeline was never run for these years (or "
            f"was run for a different year set). Load the EC spine for them, or narrow "
            f"the UCSB run's `years` to match."
        )


def _build_pv_votes(parsed_years: list[ParsedUCSBYear]) -> pd.DataFrame:
    """Melt the parsed state rows into the D018 long shape, one row per candidate.

    Four exclusions, each deliberate:

    - **absent cells produce no row** (``votes is None`` — "not on this state's
      ballot"). Never a zero: D024 §2's corpus finding is that a literal ``0`` appears
      nowhere in a state-row vote column, so absence has no numeric encoding to fall
      back to, and D018 already settled absent-row-not-zero-fill;
    - **CD rows are dropped.** Maine's and Nebraska's district sub-rows *partition* the
      statewide row rather than adding to it, so keeping them double-counts (~1.5M
      votes across the split-EV years). The statewide row already carries the total;
    - **``is_other`` aggregate columns are dropped** ("OTHERS", 2020/2024 only). An
      aggregate bucket is not a candidate: it cannot be reconciled to a canonical name
      (#38) and is outside the D007 EC-getter scope. Its votes remain represented in
      ``state_total_votes``, exactly as MIT's dropped minor candidates are;
    - the **totals row** is not a state and never enters the fact.

    ``candidate`` stays **UCSB-native** — reconciliation onto the canonical EC name is
    #38's. So is the D007 candidate-scope filter: unlike MIT, UCSB has no
    ``party_simplified`` proxy (D019), and scoping to EC-getters requires the very name
    match #38 owns. **Consequence to carry forward:** until #38 lands, ``dwh.pv_votes``
    holds MIT rows scoped to EC-getters and UCSB rows scoped to every named column UCSB
    prints. Totals and margins are unaffected (``state_total_votes`` is carried
    verbatim, never re-summed), but the *candidate* grain differs by source — and #38
    must **re-run** the two-way assert after narrowing, since dropping candidates can
    empty a ``(year, state)`` and turn a ``popular_vote`` state into a zero-fact one.

    ``party`` is carried as UCSB prints it: nullable and **non-authoritative** (D018 —
    it must not become a second source of party truth).
    """
    records = []
    for parsed in parsed_years:
        columns = {col["col_ind"]: col for col in parsed["candidates"]}
        for row in parsed["state_rows"]:
            for cell in row["cells"]:
                column = columns[cell["col_ind"]]
                if column["is_other"] or cell["votes"] is None:
                    continue
                records.append(
                    {
                        "source": SOURCE_UCSB,
                        "year": parsed["year"],
                        "state": row["state_label"],
                        "candidate": column["name"],
                        "party": column["party"],
                        "candidate_votes": cell["votes"],
                        "state_total_votes": row["state_total_votes"],
                        "reliability": _cell_reliability(
                            cell["votes"], cell["percent"], row["state_total_votes"]
                        ),
                    }
                )
    frame = pd.DataFrame.from_records(records, columns=list(SHARED_PV_COLUMNS))
    for col in ("year", "candidate_votes", "state_total_votes"):
        frame[col] = frame[col].astype("int64")
    return frame.reset_index(drop=True)


def _cell_reliability(votes: int, percent: float | None, total: int) -> str:
    """Flag a cell ``unreliable`` when UCSB's own published values contradict.

    UCSB publishes no reliability signal, and inventing an era-based judgment ("pre-1880
    is estimated") would be fabrication under D005. But a cell whose published *percent*
    disagrees with its published *votes over total* beyond
    :data:`~usvote.ucsb.parse.PERCENT_TOLERANCE` is internally inconsistent on the
    source's own terms — and since we cannot know **which** of the two published numbers
    is wrong, that is a fact about the record, which is what ``reliability`` describes.
    Pinning every row ``exact`` would assert something demonstrably false for the four
    in-scope cells this catches (1860 Vermont/Virginia/Wisconsin, 1968 Utah).

    The tolerance is **imported** from the parser rather than restated, and the known
    cells are deliberately *not* hardcoded as a list — the rule is derived, so a new
    contradiction in a future UCSB revision is flagged rather than missed.

    Attaches per **cell**, a conservative approximation: when many cells in one state
    disagree, the state's *total* is the likelier culprit and the counts may be fine.
    A systematic, whole-year misalignment is a different failure and is
    already caught upstream by ``_assert_percent_consistent``.
    """
    if percent is None or total <= 0:
        return RELIABILITY_EXACT
    computed = votes / total * 100
    return (
        RELIABILITY_UNRELIABLE
        if abs(computed - percent) > PERCENT_TOLERANCE
        else RELIABILITY_EXACT
    )


def _build_state_status(
    parsed_years: list[ParsedUCSBYear],
    roster_states: dict[int, dict[str, int]],
    in_scope: frozenset[int],
) -> pd.DataFrame:
    """Assemble the complete roster, assigning all three statuses in one place.

    Starts from every roster state in every in-scope year, then layers the two
    *attested* absences over it — ``legislature_chosen`` with the parser's verbatim
    prose, ``not_participating`` with our own cause note — leaving ``popular_vote`` as
    the **residual**. Doing all three here, against the complete roster, is what makes
    the residual meaningful: a state is "ordinary" precisely because nothing said
    otherwise, which can only be known once the roster is complete.
    """
    legislature = {
        (parsed["year"], row["state_label"]): row["note"]
        for parsed in parsed_years
        for row in parsed["status_rows"]
    }
    nonparticipating = {
        key: note
        for key, note in UCSB_NONPARTICIPATING_STATES.items()
        if key[0] in in_scope
    }

    records = []
    for year in sorted(in_scope):
        for state in sorted(roster_states.get(year, {})):
            key = (year, state)
            if key in nonparticipating:
                status, note = PV_STATUS_NOT_PARTICIPATING, nonparticipating[key]
            elif key in legislature:
                status, note = PV_STATUS_LEGISLATURE_CHOSEN, legislature[key]
            else:
                status, note = PV_STATUS_POPULAR_VOTE, None
            records.append(
                {
                    "source": SOURCE_UCSB,
                    "year": year,
                    "state": state,
                    "pv_status": status,
                    "note": note,
                }
            )
    frame = pd.DataFrame.from_records(records, columns=list(ROSTER_COLUMNS))
    frame["year"] = frame["year"].astype("int64")
    return frame.reset_index(drop=True)


# --- validations (load-bearing; each raises UCSBTransformError or a subclass) --
def _assert_label_coverage(parsed: ParsedUCSBYear) -> None:
    """Assert every verbatim state label has a canonical reconciliation."""
    labels = {row["state_label"] for row in parsed["state_rows"]}
    labels |= {row["state_label"] for row in parsed["status_rows"]}
    labels |= {row["parent_state_label"] for row in parsed["cd_rows"]}
    unmapped = sorted(labels - set(UCSB_STATE_RECONCILIATIONS), key=str)
    if unmapped:
        raise UCSBTransformError(
            f"{parsed['year']}: UCSB state label(s) with no canonical reconciliation: "
            f"{unmapped}. Add a provenance-carrying UCSB_STATE_RECONCILIATIONS "
            f"entry — an unmapped label becomes a phantom state in the roster assert "
            f"and cannot satisfy pv_votes.state's foreign key."
        )


def _assert_participation_shape(df: pd.DataFrame) -> None:
    """Assert the injected EC frame carries the columns the roster derivation needs.

    The whole roster rests on this frame, and it arrives across a DI seam from a caller
    we do not control — #37 will hand it a DB result, where ``state`` may be ``None``
    rather than ``NaN``. The roster excludes totals rows via ``is_total``, so a mistyped
    ``is_total`` silently admits them (a totals row's NULL state then becomes a phantom
    roster entry). The subtle case: a driver returning ``is_total`` as ``'t'``/``'f'``
    **strings** makes ``.astype(bool)`` truthy for *every* row (a non-empty string is
    ``True``), so no row is treated as data and the roster comes back empty — which the
    downstream check then blames on the spine "never being loaded." So require genuine
    booleans, accepting an ``object`` column of real ``bool`` values (what psycopg2
    yields for a Postgres boolean) but rejecting strings and 0/1 ints.
    """
    required = ("year", "state", "is_total", "total_electoral_votes")
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise UCSBRosterError(
            f"EC participation frame is missing column(s) {missing}; the roster "
            f"derives from {list(required)} (totals rows excluded via `is_total`)."
        )
    is_total = df["is_total"]
    if is_total.isna().any():
        raise UCSBRosterError(
            "EC participation frame has null `is_total` value(s); totals rows could "
            "not be excluded, and a totals row's NULL state becomes a phantom entry."
        )
    non_bool = is_total.map(lambda v: not isinstance(v, bool | np.bool_))
    if non_bool.any():
        bad = sorted({repr(v) for v in is_total[non_bool]})[:5]
        raise UCSBRosterError(
            f"EC participation frame `is_total` is not boolean (dtype "
            f"{is_total.dtype}, e.g. {bad}); casting it to bool would silently "
            f"misclassify totals rows (a 't'/'f' string is truthy). Cast it to bool on "
            f"read (#37's DB seam)."
        )


def assert_no_status_contradictions(
    parsed_years: list[ParsedUCSBYear], roster_states: dict[int, dict[str, int]]
) -> None:
    """Raise on any state whose absence facts disagree — **before** the roster is built.

    Consumes the **input sets**, not the assembled roster, and that is the whole point:
    ``_build_state_status``'s precedence chain resolves a contradictory state to a
    single row with a single status, so a check that ran afterwards would pass on a
    frame built by silently resolving exactly what D024 requires to raise.

    Three contradictions, plus the canonicalization-reopened overlap:

    1. a ``legislature_chosen`` state absent from that year's EC roster;
    2. a state both flagged ``legislature_chosen`` and listed non-participating;
    3. a state listed non-participating that nonetheless has UCSB vote rows;
    4. a state appearing as both a vote row and a status row **on canonical labels** —
       :func:`usvote.ucsb.parse._assert_one_status_per_state` already rejects this, but
       it compares *verbatim* labels, and canonicalization is many-to-one, so two
       distinct labels can collapse onto one state after that guard has run.
    """
    for parsed in parsed_years:
        year = parsed["year"]
        roster = set(roster_states.get(year, {}))
        voting = [row["state_label"] for row in parsed["state_rows"]]
        flagged = {row["state_label"] for row in parsed["status_rows"]}
        nonparticipating = {
            state for (y, state) in UCSB_NONPARTICIPATING_STATES if y == year
        }

        orphans = sorted(flagged - roster)
        if orphans:
            raise UCSBRosterError(
                f"{year}: legislature-chosen state(s) {orphans} are absent from the EC "
                f"roster for that year. UCSB says the state took part; the EC spine "
                f"does not carry it. One of the two sources is wrong about "
                f"participation — this is not resolvable here."
            )

        both = sorted(flagged & nonparticipating)
        if both:
            raise UCSBTransformError(
                f"{year}: state(s) {both} are flagged legislature-chosen by the parser "
                f"*and* listed in UCSB_NONPARTICIPATING_STATES. A state cannot both "
                f"choose electors by legislature and take no part in the election."
            )

        voted_but_absent = sorted(nonparticipating.intersection(voting))
        if voted_but_absent:
            raise UCSBTransformError(
                f"{year}: state(s) {voted_but_absent} are listed in "
                f"UCSB_NONPARTICIPATING_STATES but have UCSB popular-vote rows. Either "
                f"the constant is wrong or the page changed."
            )

        overlap = sorted(flagged.intersection(voting))
        if overlap:
            raise UCSBTransformError(
                f"{year}: state(s) {overlap} appear as both popular-vote rows and "
                f"legislature-chosen rows once labels are canonicalized. The parser "
                f"checks this on verbatim labels, so two distinct UCSB spellings have "
                f"collapsed onto one canonical state."
            )

        duplicates = sorted({s for s in voting if voting.count(s) > 1})
        if duplicates:
            raise UCSBTransformError(
                f"{year}: duplicate canonical state(s) {duplicates} among the "
                f"popular-vote rows; two UCSB spellings map to one state and would be "
                f"double-counted."
            )


def assert_absence_matches_zero_ev(
    roster: pd.DataFrame, roster_states: dict[int, dict[str, int]]
) -> None:
    """Cross-check the absence roster against the EC spine's electoral votes (D024 §5).

    A state that took no part in an election cast no electoral votes, so the spine's
    ``total_electoral_votes`` is an **independent witness** for
    :data:`UCSB_NONPARTICIPATING_STATES`. Verified exact corpus-wide: the roster states
    with zero electoral votes are precisely 1864's 11 Confederate states, in every
    in-scope year. Both directions are checked:

    (a) every ``not_participating`` state has zero electoral votes in the spine — this
    validates our constant against the authority; and (b) no zero-EV state is classified
    ``popular_vote`` — this deliberately couples us to the Archives' rendering, because
    a silent change in how it renders non-participating states would corrupt the roster
    invisibly, and making that visible is the roster's entire purpose.

    ``legislature_chosen`` is exempt from (a) by construction: those states *did*
    participate and cast electoral votes (1876 Colorado cast 3) — they simply held no
    popular vote, which is why the two absence statuses are distinct values.
    """
    for row in roster.itertuples(index=False):
        max_ev = roster_states.get(row.year, {}).get(row.state)
        if max_ev is None:
            continue
        if row.pv_status == PV_STATUS_NOT_PARTICIPATING and max_ev != 0:
            raise UCSBRosterError(
                f"{row.year} {row.state} is listed in UCSB_NONPARTICIPATING_STATES but "
                f"the EC spine records {max_ev} electoral vote(s) for it. A state that "
                f"took no part in the election cast none — the constant and the "
                f"Archives disagree."
            )
        if row.pv_status == PV_STATUS_POPULAR_VOTE and max_ev == 0:
            raise UCSBRosterError(
                f"{row.year} {row.state} has zero electoral votes in the EC spine but "
                f"is classified '{PV_STATUS_POPULAR_VOTE}'. **This indicates a change "
                f"in the EC spine, not in UCSB**: the Archives carries "
                f"non-participating states as zero-electoral-vote rows, so a new "
                f"zero-EV state means either a new non-participation case (add it to "
                f"UCSB_NONPARTICIPATING_STATES) or a change in how the Archives "
                f"renders these rows. Start in usvote/parse.py, not usvote/ucsb/."
            )


def assert_pv_grain(
    df: pd.DataFrame, *, error_cls: type[Exception] = UCSBTransformError
) -> None:
    """Assert one PV row per ``(year, state, candidate)`` (``source`` is constant).

    ``error_cls`` lets the reconcile stage (#38) re-run this after its candidate rewrite
    and raise its own :class:`~usvote.ucsb.reconcile.UCSBReconcileError`, mirroring how
    :func:`usvote.mit.transform.assert_unique_grain` is reused across MIT's stages.
    """
    dupes = df.loc[df.duplicated(["year", "state", "candidate"], keep=False)]
    if not dupes.empty:
        raise error_cls(
            "UCSB transform grain violated — duplicate (year, state, candidate): "
            f"{dupes[['year', 'state', 'candidate']].values.tolist()}"
        )


def assert_no_zero_votes(df: pd.DataFrame) -> None:
    """Assert no emitted row carries zero votes (D024 §2).

    A literal ``0`` appears nowhere in a state-row vote column in the entire corpus:
    "zero popular votes" is never encoded, so absence must never be modeled as it. The
    parser enforces this upstream, but the melt is exactly where a later ``fillna(0)``
    would creep in, and this frame is what reaches the DB.
    """
    zeros = df.loc[df["candidate_votes"] == 0]
    if not zeros.empty:
        raise UCSBTransformError(
            f"UCSB transform emitted {len(zeros)} row(s) with 0 votes: "
            f"{zeros[['year', 'state', 'candidate']].values.tolist()[:10]}. Absence is "
            f"an omitted row, never a zero (D024 §2)."
        )


def assert_totals_not_exceeded(df: pd.DataFrame) -> None:
    """Assert ``sum(candidate_votes) <= state_total_votes`` per ``(year, state)``.

    Not equality: the dropped "OTHERS" aggregate columns are a legitimate residual, so
    only an *excess* over the state's published total signals a bug. (The exact
    reconciliation of every column against the totals row is the parser's, and runs on
    the complete pre-drop candidate set.)
    """
    grouped = df.groupby(["year", "state"], as_index=False).agg(
        csum=("candidate_votes", "sum"),
        total=("state_total_votes", "first"),
    )
    over = grouped.loc[grouped["csum"] > grouped["total"]]
    if not over.empty:
        raise UCSBTransformError(
            "UCSB candidate votes exceed the state total for "
            f"{len(over)} (year, state) cell(s): {over.values.tolist()}"
        )


def assert_pv_columns(
    df: pd.DataFrame, *, error_cls: type[Exception] = UCSBTransformError
) -> None:
    """Assert the D018 shape: column order, key non-nullity, and integer counts.

    Delegates to the shared :func:`usvote.pv.schema.assert_pv_shape` rather than
    re-implementing it, so the non-null key set (which must include ``candidate``) and
    the integer-column set have one definition, not one per source that can silently
    drift. ``error_cls`` keeps the failure typed to the caller's stage (UCSB transform
    by default; :class:`~usvote.ucsb.reconcile.UCSBReconcileError` when #38 re-runs it).
    """
    assert_pv_shape(df, error_cls=error_cls)


def assert_note_only_on_absence(roster: pd.DataFrame) -> None:
    """Assert ``note`` is null on every ordinary ``popular_vote`` row.

    ``note`` holds verbatim UCSB prose on ``legislature_chosen`` rows and is therefore
    ``redistributable=false`` content (D024, extending D022/D016). Confining it to rows
    that structurally need it makes "exclude ``note`` from any public API surface" a
    filter on ``pv_status`` for #37/E6, rather than a per-row audit.
    """
    leaked = roster.loc[
        (roster["pv_status"] == PV_STATUS_POPULAR_VOTE) & roster["note"].notna()
    ]
    if not leaked.empty:
        raise UCSBTransformError(
            f"{len(leaked)} '{PV_STATUS_POPULAR_VOTE}' roster row(s) carry a note: "
            f"{leaked[['year', 'state']].values.tolist()[:10]}. A note is only "
            f"meaningful on an absence row, and it may carry non-redistributable "
            f"verbatim UCSB text."
        )
