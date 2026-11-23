"""Shared PV-absence roster contract + the two-way silent-drop guard (D024).

The sibling of :mod:`usvote.pv.schema`, and source-neutral for the same reason: the
``dwh.pv_state_status`` roster is a **shared** PV structure, not a UCSB one. Three
consumers are already known — #37's DDL (whose ``pv_status`` CHECK is built from
:data:`PV_STATUS_VALUES`), E6's mechanical MIT roster backfill (D024 §6/§Rationale),
and #38's re-run of the two-way assert after it narrows candidates — so the contract
lives here and the dependency runs ``source -> pv``, never ``pv -> ucsb`` or, worse,
``mit -> ucsb``.

**What the roster is (D024 §3/§6).** One row per ``(source, year, state)`` for *every*
state in that year's election, including ordinary ones. It is a **complete roster, not
an exceptions table** — that is precisely what makes absence detectable: an
exceptions-only table cannot distinguish "no exception" from "we never looked."

**What it is for (D024 §7).** :func:`assert_roster_covers_facts` is the project's guard
against the inner-join silent-drop hazard, which no sum validator can see: a state that
vanishes between parse and load takes its votes with it, and every total still
reconciles because the total went missing too. The third of its three checks —
every fact row's ``(year, state)`` is *in* the roster — is the one that catches a
phantom state.

**Scoping is explicit, never inferred.** ``dwh.pv_votes`` holds every source's rows
(D021), so the assert takes ``source``; and a partial-year run must not indict years it
never processed, so it takes the in-scope ``years``. Neither is read off whatever
happens to be in the frame — inferring them would make the guard silently weaker
exactly when it is being misused.
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

#: The ``dwh.pv_state_status`` columns, in load order. ``note`` is nullable.
ROSTER_COLUMNS: tuple[str, ...] = ("source", "year", "state", "pv_status", "note")

#: The roster's natural key (D024 §3). The loader enforces it as a table ``UNIQUE``.
ROSTER_NATURAL_KEY: tuple[str, ...] = ("source", "year", "state")

#: The three ``pv_status`` values, and deliberately only three (D024 §4).
#: ``popular_vote`` — held and recorded in ``pv_votes``; ``legislature_chosen`` — the
#: state's electors were chosen by its legislature, so no popular vote was ever held;
#: ``not_participating`` — the state took no part in the election at all.
#: There is **no** ``unknown``/``unparsed`` value: anything unclassifiable raises,
#: because an ``unknown`` slot is where parse failures go to die quietly. There is
#: likewise no value for "candidate not on the ballot" — that is a candidate-grain
#: fact and produces no ``pv_votes`` row at all (D024 §2, D018).
PV_STATUS_POPULAR_VOTE = "popular_vote"
PV_STATUS_LEGISLATURE_CHOSEN = "legislature_chosen"
PV_STATUS_NOT_PARTICIPATING = "not_participating"
PV_STATUS_VALUES: tuple[str, ...] = (
    PV_STATUS_POPULAR_VOTE,
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
)

#: The two statuses that assert "no popular vote happened here." Every state carrying
#: one must have **exactly zero** ``pv_votes`` rows; every ``popular_vote`` state must
#: have at least one row. That biconditional is the roster's whole point.
PV_ABSENCE_STATUSES: frozenset[str] = frozenset(
    {PV_STATUS_LEGISLATURE_CHOSEN, PV_STATUS_NOT_PARTICIPATING}
)

#: The warehouse schema and roster table. Shares ``dwh`` with the EC star schema and
#: ``pv_votes``; its ``state`` FK targets ``dwh.state`` (see :mod:`usvote.pv.schema`).
ROSTER_SCHEMA = "dwh"
ROSTER_TABLE = "pv_state_status"


class PVRosterError(RuntimeError):
    """Raised when a PV roster is malformed or disagrees with the PV facts.

    The source-neutral analogue of :class:`usvote.pv.schema.PVShapeError`. Every
    function here accepts an ``error_cls`` so a source can raise its own typed error
    (e.g. ``UCSBRosterError``) from this shared implementation, exactly as
    :func:`usvote.mit.transform.assert_unique_grain` already does.
    """


def build_status_column_defs(schema: str = ROSTER_SCHEMA) -> list[tuple[str, ...]]:
    """Return the ``pv_state_status`` column definitions as ``DBC.create_table`` tuples.

    A function rather than a constant for the same reason as
    :func:`usvote.pv.schema.build_pv_column_defs`: the ``state`` FK embeds ``schema``
    in its ``REFERENCES`` clause. ``schema`` must be the shared warehouse schema that
    already holds the EC ``state`` dimension.

    Mirrors the ``pv_votes`` DDL — identity PK, a ``UNIQUE`` on the natural key, the
    ``state`` FK, and a CHECK built from :data:`PV_STATUS_VALUES` so the enum has one
    definition rather than two. Provided here (rather than in #37) so the shared
    contract and its DDL cannot drift apart.

    ``note`` is nullable and, for ``legislature_chosen`` rows, holds **verbatim UCSB
    prose** — ``redistributable=false`` content per D024/D022/D016. It must be excluded
    from any public API surface and must never reach a committed fixture.
    """
    status_check = (
        "CHECK (pv_status IN (" + ", ".join(f"'{v}'" for v in PV_STATUS_VALUES) + "))"
    )
    return [
        ("status_id", "integer", "generated always as identity", "primary key"),
        ("source", "varchar", "not null"),
        ("year", "smallint", "not null"),
        ("state", "varchar", "not null", f"REFERENCES {schema}.state"),
        ("pv_status", "varchar", "not null", status_check),
        ("note", "text"),
        (
            "CONSTRAINT",
            f"{ROSTER_TABLE}_natural_key",
            "UNIQUE",
            "(source, year, state)",
        ),
    ]


def assert_roster_shape(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVRosterError
) -> None:
    """Assert exactly :data:`ROSTER_COLUMNS`, valid statuses, and no null keys.

    ``note`` is exempt from the non-null check — it is null on every ordinary
    ``popular_vote`` row by design.
    """
    if list(df.columns) != list(ROSTER_COLUMNS):
        raise error_cls(
            f"PV roster columns {list(df.columns)} != roster shape "
            f"{list(ROSTER_COLUMNS)}"
        )
    for col in ROSTER_NATURAL_KEY + ("pv_status",):
        if df[col].isna().any():
            raise error_cls(f"PV roster column {col!r} has null value(s)")
    unknown = sorted(set(df["pv_status"].unique()) - set(PV_STATUS_VALUES))
    if unknown:
        raise error_cls(
            f"PV roster has unknown pv_status value(s) {unknown}; the enum is "
            f"{list(PV_STATUS_VALUES)} and D024 §4 admits no others"
        )


def assert_unique_roster_grain(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVRosterError
) -> None:
    """Assert one roster row per ``(source, year, state)``."""
    dupes = df.loc[df.duplicated(list(ROSTER_NATURAL_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "PV roster grain violated — duplicate (source, year, state): "
            f"{dupes[list(ROSTER_NATURAL_KEY)].values.tolist()}"
        )


def assert_roster_covers_facts(
    pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    *,
    source: str,
    years: Collection[int],
    error_cls: type[Exception] = PVRosterError,
    empty_roster_error_cls: type[Exception] | None = None,
) -> None:
    """The two-way roster/fact assert — the guard against silent row loss (D024 §7).

    Three checks, over the rows of ``source`` in the in-scope ``years``:

    1. every ``popular_vote`` roster state has **≥1** ``pv_votes`` row;
    2. every absence-status state (:data:`PV_ABSENCE_STATUSES`) has **exactly 0**;
    3. every ``pv_votes`` ``(year, state)`` is **in** the roster.

    Check 3 is the one no sum validator can replace: a phantom or mis-canonicalized
    state passes every total while being wrong.

    ``source`` and ``years`` are **required and explicit**. ``dwh.pv_votes`` holds
    other sources' rows, and a partial-year run must not report unprocessed years as
    violations — neither is inferred from the frames.

    "The roster is empty for an in-scope year" raises ``empty_roster_error_cls``
    (defaulting to ``error_cls``) rather than being reported as N mismatched states:
    different cause (a mis-sequenced pipeline — the EC spine was never loaded, or was
    loaded for a different year set), different fix. Callers pass a distinct class so
    the two are separable by type, not only by message.
    """
    empty_cls = empty_roster_error_cls or error_cls
    in_scope = frozenset(years)

    roster = roster_df[
        (roster_df["source"] == source) & (roster_df["year"].isin(in_scope))
    ]
    facts = pv_df[(pv_df["source"] == source) & (pv_df["year"].isin(in_scope))]

    missing_years = sorted(in_scope - set(roster["year"].unique()))
    if missing_years:
        raise empty_cls(
            f"{source} roster is empty for in-scope year(s) {missing_years}. This is a "
            f"pipeline-sequencing failure, not a state mismatch: the roster derives "
            f"from the EC spine, so the spine was never loaded for these years (or "
            f"was loaded for a different year set). Run the EC pipeline for them, or "
            f"narrow the PV run's `years` to match."
        )

    fact_keys = set(zip(facts["year"], facts["state"], strict=True))
    roster_keys = set(zip(roster["year"], roster["state"], strict=True))
    is_pv = roster["pv_status"] == PV_STATUS_POPULAR_VOTE

    expected = set(
        zip(roster.loc[is_pv, "year"], roster.loc[is_pv, "state"], strict=True)
    )
    absent = set(
        zip(roster.loc[~is_pv, "year"], roster.loc[~is_pv, "state"], strict=True)
    )

    silent_drops = sorted(expected - fact_keys)
    if silent_drops:
        raise error_cls(
            f"{source}: {len(silent_drops)} roster state(s) marked "
            f"'{PV_STATUS_POPULAR_VOTE}' have no vote rows: {silent_drops[:10]}"
            f"{' ...' if len(silent_drops) > 10 else ''}. Either the rows were dropped "
            f"silently (an unreconciled state label, or a join that lost them), or the "
            f"state genuinely held no popular vote and needs an absence status."
        )

    fabricated = sorted(absent & fact_keys)
    if fabricated:
        raise error_cls(
            f"{source}: {len(fabricated)} state(s) marked as having *no* popular vote "
            f"nevertheless have vote rows: {fabricated[:10]}"
            f"{' ...' if len(fabricated) > 10 else ''}. The roster and the facts "
            f"disagree about whether an election happened."
        )

    phantoms = sorted(fact_keys - roster_keys)
    if phantoms:
        raise error_cls(
            f"{source}: {len(phantoms)} vote-row (year, state) key(s) are absent from "
            f"the roster: {phantoms[:10]}{' ...' if len(phantoms) > 10 else ''}. The "
            f"roster is the complete set of states in each year's election, so these "
            f"are phantom states — most likely an unreconciled or mis-canonicalized "
            f"state label. A sum validator cannot see this."
        )