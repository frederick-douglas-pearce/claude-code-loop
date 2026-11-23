"""Transform & validate stage — MIT raw CSV -> the shared PV record shape.

The MIT analogue of the EC :mod:`usvote.transform` stage, and the second half of
the MIT pipeline after :mod:`usvote.mit.read`. It maps the raw MIT
``1976-2024-president.csv`` frame onto the **shared PV record shape** fixed by
decision **D018** — one long-format row per ``(source, year, state, candidate)`` —
so MIT and (later) UCSB rows are interchangeable at load.

The transform is a pure function (:func:`transform_mit`); it does column selection,
typing, the D007 candidate-scope filter, fusion-line aggregation, provenance
tagging, and a set of load-bearing validations. It deliberately does **not**:

- reconcile ``state``/``candidate`` onto the EC canonical keys — that is #67; the
  frame here carries MIT-native names (D018);
- load, assign a surrogate key, or add FKs — that is #66 (D018);
- store a ``redistributable`` column — that is a per-*source* attribute of the
  ``pv_source`` reference table, derived by join (D017/D018);
- convert NaN -> None — that is owned once at the DB write boundary
  (``usvote.db.insert_df_into_table``), never via an upstream ``.map`` (which
  silently no-ops on ``StringDtype``).

**Order is load-bearing.** Two orderings matter and are enforced by tests:

1. **Reconcile totals *before* filtering.** ``sum(candidatevotes) == totalvotes``
   per ``(year, state)`` is a read/parse regression guard that only holds on the
   *complete* candidate set, so it must run before any row is dropped.
2. **Aggregate fusion lines *before* the D007 filter.** In fusion-voting states MIT
   lists a candidate on multiple party lines as separate rows, coding the secondary
   lines under their minor party (``party_simplified == "OTHER"`` — e.g. Clinton's
   2016 NY Working Families / Women's Equality lines). Filtering to
   ``{DEMOCRAT, REPUBLICAN}`` *first* would drop those ``OTHER`` lines and then sum
   only the main line — a silent undercount of a major candidate (the exact
   ``pv_preferred`` ``DISTINCT ON`` hazard D018 warns about). So we aggregate to the
   ``(year, state, candidate)`` grain first, take the plurality line's party, and
   only then apply the party filter.

Ported for #65 (E5-S2); mirrors the EC transform's conventions: a typed
:class:`MITTransformError`, provenance-carrying module constants for the historical
special-cases, named-column ops (no positional ``.iloc``), and dense inline
assertions rewritten as real, tested validation functions.
"""

from __future__ import annotations

import pandas as pd

from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT

# --- provenance literals ----------------------------------------------------
# The D018 shared PV record shape (SHARED_PV_COLUMNS) is the source-neutral SSOT in
# usvote.pv.schema; MIT imports it (direction is always source -> pv) and projects
# onto it in _project_shared_shape.
# ``SOURCE_MIT`` moved to usvote.pv.source in #68 — the SSOT for source-name literals,
# where the pv_source reference table also keys on it (so the tag and the table cannot
# disagree). Re-imported here (still ``source -> pv``) so callers of
# ``usvote.mit.transform.SOURCE_MIT`` are unaffected. ``redistributable`` is likewise a
# per-source attribute of the pv_source table (D017/D018), never a row column here.
#: MIT is a clean modern release, so every row is exact (D005 reliability flag).
#: The shared enum is ``{exact, estimated, unreliable}``; UCSB varies it per row.
RELIABILITY_EXACT = "exact"

# --- D007 candidate scope (D019) -------------------------------------------
#: The MIT D007 candidate-scope proxy (D019): across 1976-2024 *every* electoral
#: vote went to a Democratic or Republican nominee, so ``party_simplified`` in this
#: set is an effectively-exact, zero-maintenance stand-in for "received electoral
#: votes." Libertarian/Green PV candidates (0 EC votes in the window) are knowingly
#: excluded; faithless-elector EC recipients are deferred to #67. Applied to the
#: fusion-*aggregated* plurality party, never a raw secondary ``OTHER`` line.
EC_GETTER_PARTIES: frozenset[str] = frozenset({"DEMOCRAT", "REPUBLICAN"})

# --- historical corrections (provenance-carrying constants) ----------------
#: Known ``(year, state)`` totals-reconciliation exceptions in the real MIT file,
#: as the *signed* discrepancy ``sum(candidatevotes) - totalvotes`` MIT itself ships.
#: Both are in the 2024 release and stem from MIT itemizing ballot-disposition buckets
#: (``UNDERVOTES``/``OVERVOTES``/``VOID``) as ``OTHER`` pseudo-candidate rows, with
#: ``totalvotes`` defined inconsistently between the two states: DC's ``totalvotes``
#: *excludes* its under/overvote rows (surplus = 2,075 + 460 = +2,535), while NY's is
#: *inclusive* and carries an 874-ballot residual not itemized in any row (-874). Not a
#: disputed/litigated result. Full analysis + MIT outreach questions in
#: ``docs/mit-data-anomalies.md``. The ``{D, R}`` scope drops every ``OTHER`` row, so
#: output is unaffected; encoding the *exact* diff keeps the pre-filter guard firing if
#: a future MIT re-release changes these or adds a new mismatch (EC-correction pattern).
#: Source: MIT Election Lab ``1976-2024-president.csv`` (doi:10.7910/DVN/42MVDX).
TOTALS_RECONCILIATION_EXCEPTIONS: dict[tuple[int, str], int] = {
    (2024, "DISTRICT OF COLUMBIA"): 2535,
    (2024, "NEW YORK"): -874,
}


class MITTransformError(RuntimeError):
    """Raised when a MIT transform validation fails.

    The MIT analogue of the EC :class:`usvote.transform.TransformError` and the
    ingest-stage :class:`usvote.mit.read.MITReadError` — a typed, message-carrying
    failure so a read/parse regression or an upstream MIT data change surfaces
    loudly here rather than flowing silently into the DB load.
    """


def transform_mit(
    df: pd.DataFrame,
    *,
    totals_exceptions: dict[tuple[int, str], int] | None = None,
) -> pd.DataFrame:
    """Transform the raw MIT frame into the D018 shared PV record shape.

    Takes the verbatim frame from :func:`usvote.mit.read.load_mit_president_csv`
    and returns a frame whose columns are exactly :data:`SHARED_PV_COLUMNS`, one row
    per ``(year, state, candidate)`` for the D007 EC-getter scope (D019), with
    ``source``/``reliability`` provenance stamped. ``state``/``candidate`` stay
    MIT-native (reconciliation is #67).

    ``totals_exceptions`` overrides :data:`TOTALS_RECONCILIATION_EXCEPTIONS` (the
    known real-file discrepancies); pass ``{}`` to require exact reconciliation, or a
    custom map in tests. Raises :class:`MITTransformError` on any validation failure.
    """
    if totals_exceptions is None:
        totals_exceptions = TOTALS_RECONCILIATION_EXCEPTIONS

    typed = _coerce_types(df)
    assert_totals_reconcile(typed, totals_exceptions)

    named = _drop_unattributable_rows(typed)
    aggregated = _aggregate_fusion_lines(named)
    scoped = _filter_ec_getters(aggregated)
    shaped = _project_shared_shape(scoped)

    assert_unique_grain(shaped)
    assert_totals_not_exceeded(shaped)
    assert_shape(shaped)
    return shaped


# --- transform steps -------------------------------------------------------
def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Type the raw frame (read returns it verbatim, so transform owns typing).

    Vote counts become nullable ``Int64`` first so a stray non-numeric/blank cell
    fails loud as :class:`MITTransformError` rather than an opaque pandas cast; text
    columns become ``StringDtype``. No NaN -> None pass — that is the DB boundary's job.
    """
    out = df.copy()
    out["year"] = out["year"].astype("int64")
    for col in ("candidatevotes", "totalvotes"):
        numeric = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        if numeric.isna().any():
            bad = out.loc[numeric.isna(), col].tolist()
            raise MITTransformError(
                f"MIT column {col!r} has non-numeric/null value(s): {bad}"
            )
        out[col] = numeric.astype("int64")
    out["writein"] = out["writein"].astype(bool)
    for col in ("state", "candidate", "party_simplified"):
        out[col] = out[col].astype("string")
    return out


def _drop_unattributable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with no candidate name — they cannot be attributed or aggregated.

    MIT records ~66 minor/independent lines across 1976-2016 with a null ``candidate``
    (all coded ``party_simplified`` ``OTHER``/``LIBERTARIAN``); a null value is also a
    groupby key the fusion aggregation would drop silently, so we drop it explicitly.

    We deliberately do **not** filter on the ``writein`` flag. The D007 scope is
    enforced by the ``{DEMOCRAT, REPUBLICAN}`` party filter (D019), which already
    subsumes the write-in long tail (it is all ``OTHER``); filtering on ``writein``
    as well would *silently drop a major candidate wherever MIT mis-flags one* — most
    egregiously **2020 DC, where every row (Biden 317,323; Trump 18,586) is flagged
    ``writein=True``** (DC does not run its presidential election by write-in). See
    ``docs/mit-data-anomalies.md``. Retaining named write-in lines and scoping by
    party keeps those real votes; empirically it yields exactly one D and one R row
    per (year, state) with no duplicates.

    Guard: a *non-write-in* unnamed row in the EC-getter party set would be a genuine
    anomaly (a major-party nominee with no name — a silent-undercount risk), so it
    fails loud rather than being dropped. (An unnamed *write-in* D/R line is a real,
    unattributable residual — e.g. 2016 AZ's 42-vote write-in coded DEMOCRAT — and is
    dropped with the other unnamed rows.)
    """
    unnamed = df["candidate"].isna()
    unnamed_major = df.loc[
        unnamed & ~df["writein"] & df["party_simplified"].isin(EC_GETTER_PARTIES)
    ]
    if not unnamed_major.empty:
        raise MITTransformError(
            "MIT rows in the EC-getter party scope with a null candidate name "
            f"(year, state): {unnamed_major[['year', 'state']].values.tolist()}"
        )
    return df.loc[~unnamed].copy()


def _aggregate_fusion_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse fusion party lines to one row per ``(year, state, candidate)``.

    Sums ``candidatevotes`` across lines and takes ``party`` from the **plurality**
    line (the constituent row with the most votes); ``state_total_votes`` is the
    per-state total (identical across the group). Sorting by votes descending — with
    ``party_simplified`` as a deterministic tie-break — before a grouped ``first``
    makes the plurality-party pick reproducible. Must run *before* the D007 filter.
    """
    ordered = df.sort_values(
        ["candidatevotes", "party_simplified"],
        ascending=[False, True],
        kind="stable",
    )
    return ordered.groupby(
        ["year", "state", "candidate"], sort=False, as_index=False
    ).agg(
        candidate_votes=("candidatevotes", "sum"),
        party=("party_simplified", "first"),
        state_total_votes=("totalvotes", "first"),
    )


def _filter_ec_getters(df: pd.DataFrame) -> pd.DataFrame:
    """Keep D007 EC-getters — aggregated plurality party in the D019 scope set."""
    return df.loc[df["party"].isin(EC_GETTER_PARTIES)].copy()


def _project_shared_shape(df: pd.DataFrame) -> pd.DataFrame:
    """Stamp provenance and project onto :data:`SHARED_PV_COLUMNS` in load order."""
    out = df.assign(source=SOURCE_MIT, reliability=RELIABILITY_EXACT)
    return out[list(SHARED_PV_COLUMNS)].reset_index(drop=True)


# --- validations (load-bearing; each raises MITTransformError) --------------
def assert_totals_reconcile(
    df: pd.DataFrame, exceptions: dict[tuple[int, str], int]
) -> None:
    """Assert ``sum(candidatevotes) == totalvotes`` per ``(year, state)``, pre-filter.

    Runs on the full candidate set (the property only holds before any row is
    dropped). ``exceptions`` maps a ``(year, state)`` to its known signed discrepancy
    (``sum - total``); a group reconciles when its actual diff equals the allowed one
    (0 when absent). Also asserts ``totalvotes`` is constant within a ``(year, state)``.
    """
    grouped = df.groupby(["year", "state"], as_index=False, sort=True).agg(
        csum=("candidatevotes", "sum"),
        total=("totalvotes", "first"),
        n_total=("totalvotes", "nunique"),
    )
    inconsistent = grouped.loc[grouped["n_total"] > 1, ["year", "state"]]
    if not inconsistent.empty:
        raise MITTransformError(
            "MIT rows disagree on totalvotes within a (year, state): "
            f"{inconsistent.values.tolist()}"
        )
    allowed = [
        exceptions.get((int(y), str(s)), 0)
        for y, s in zip(grouped["year"], grouped["state"], strict=True)
    ]
    diff = (grouped["csum"] - grouped["total"]).to_numpy()
    mism = grouped.loc[diff != allowed, ["year", "state", "csum", "total"]]
    if not mism.empty:
        raise MITTransformError(
            "MIT candidate votes do not reconcile to totalvotes for "
            f"{len(mism)} (year, state) cell(s): {mism.values.tolist()}. "
            "Add a provenance-carrying TOTALS_RECONCILIATION_EXCEPTIONS entry if "
            "this is a known upstream discrepancy."
        )


def assert_unique_grain(
    df: pd.DataFrame,
    *,
    error_cls: type[Exception] = MITTransformError,
    context: str = "transform",
) -> None:
    """Assert one row per ``(year, state, candidate)`` (``source`` is constant here).

    Shared by the transform (default `MITTransformError`) and the reconcile stage,
    which passes ``error_cls=MITReconcileError`` / ``context="reconcile"`` so the same
    grain check reports under its own error type and stage name.
    """
    dupes = df.loc[df.duplicated(["year", "state", "candidate"], keep=False)]
    if not dupes.empty:
        raise error_cls(
            f"MIT {context} grain violated — duplicate (year, state, candidate): "
            f"{dupes[['year', 'state', 'candidate']].values.tolist()}"
        )


def assert_totals_not_exceeded(df: pd.DataFrame) -> None:
    """Assert ``sum(candidate_votes) <= state_total_votes`` per ``(year, state)``.

    Post-filter, the dropped minor candidates are the residual, so equality is *not*
    expected; only an *excess* over the state total signals a bug.
    """
    grouped = df.groupby(["year", "state"], as_index=False).agg(
        csum=("candidate_votes", "sum"),
        total=("state_total_votes", "first"),
    )
    over = grouped.loc[grouped["csum"] > grouped["total"]]
    if not over.empty:
        raise MITTransformError(
            "MIT scoped candidate votes exceed the state total for "
            f"{len(over)} (year, state) cell(s): {over.values.tolist()}"
        )


def assert_shape(df: pd.DataFrame) -> None:
    """Assert the exact D018 shape: columns, key non-nullity, and vote dtypes."""
    if list(df.columns) != list(SHARED_PV_COLUMNS):
        raise MITTransformError(
            f"MIT transform columns {list(df.columns)} != shared PV shape "
            f"{list(SHARED_PV_COLUMNS)}"
        )
    for col in SHARED_PV_COLUMNS:
        if df[col].isna().any():
            raise MITTransformError(f"MIT transform column {col!r} has null values")
    for col in ("candidate_votes", "state_total_votes"):
        if not pd.api.types.is_integer_dtype(df[col]):
            raise MITTransformError(
                f"MIT transform column {col!r} must be integer, got {df[col].dtype}"
            )
