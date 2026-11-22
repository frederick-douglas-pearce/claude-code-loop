"""Shared PV record shape + target-table DDL + boundary shape guard (D018).

The source-neutral SSOT for the popular-vote contract. :data:`SHARED_PV_COLUMNS`
fixes the D018 long-format record shape — one row per ``(source, year, state,
candidate)`` — that *every* PV source's transform emits and the shared PV target
table stores; it lives here (not in any one source module) so the dependency runs
``source -> pv`` and adding UCSB never reaches back into MIT.

:func:`build_pv_column_defs` is the ``dwh.pv_votes`` DDL, mirroring the EC loader's
:func:`usvote.load.build_table_column_defs` pattern (a function, not a constant,
because the ``state`` FK embeds the schema name). :func:`assert_pv_shape` is the
defensive guard the shared loader runs before every insert, so a malformed source
frame fails loudly at the one write boundary rather than loading silently-wrong rows.

**Scope boundary (D017/D018).** This table stores only ``source`` as provenance;
``redistributable``/``precedence_rank``/license are per-*source* attributes of the
``pv_source`` reference table (#68), never per-row columns here. ``state``/
``candidate``/``party``/``reliability`` are left nullable in the DDL for UCSB
forward-compat (UCSB may lack ``party`` and varies ``reliability``); the shared
:func:`assert_pv_shape` enforces non-null on the natural-key + vote columns for the
frame actually being loaded. FKs: ``state -> dwh.state`` (the canonical full name is
that dim's PK). There is deliberately **no** ``candidate`` FK — the EC ``candidate``
PK is ``candidate_id``, not the ``name`` string this shape carries, and re-constraining
the EC dim from a PV load would invert the D006 spine dependency; candidate referential
integrity is guarded offline at reconcile (#67) and at the EC<->PV join seam (#69).
"""

from __future__ import annotations

import pandas as pd

#: The D018 shared PV record-shape columns, in load order. Both PV sources emit
#: exactly these; the shared PV target table stores exactly these (plus the surrogate
#: ``pv_id`` the loader prepends). This is the SSOT — ``usvote.mit`` (and later
#: ``usvote.ucsb``) import it from here rather than redefining it.
SHARED_PV_COLUMNS: tuple[str, ...] = (
    "source",
    "year",
    "state",
    "candidate",
    "party",
    "candidate_votes",
    "state_total_votes",
    "reliability",
)

#: The natural key of the shared shape (D018). ``source`` is part of the key because
#: the union keeps both sources' rows (D017 — precedence is a read-time view concern,
#: never a load-time dedup). The loader sorts on this to assign a reproducible
#: ``pv_id`` and enforces it as a table ``UNIQUE`` constraint.
NATURAL_KEY: tuple[str, ...] = ("source", "year", "state", "candidate")

#: Columns the shared loader requires non-null in the frame being loaded. ``party``
#: and ``reliability`` are intentionally omitted — they are nullable for UCSB
#: forward-compat — while the natural-key and vote columns must be present for any
#: source (a null key would break the grain; a null vote count is a load bug).
REQUIRED_NON_NULL: tuple[str, ...] = (
    "source",
    "year",
    "state",
    "candidate",
    "candidate_votes",
    "state_total_votes",
)

#: Vote-count columns the shared guard requires to be an integer dtype. A float-typed
#: count (e.g. a source whose transform let an NA coerce the column to float64) would
#: otherwise be inserted into the ``integer`` DDL columns — whole floats round
#: silently, a residual fraction/NaN errors deep in psycopg2. Mirrors the per-source
#: check in :func:`usvote.mit.transform.assert_shape`, generalized to the shared
#: boundary so every source (not just MIT) is covered.
INTEGER_COLUMNS: tuple[str, ...] = ("candidate_votes", "state_total_votes")

#: The D018 ``reliability`` enum, enforced as a table CHECK. MIT pins ``"exact"``;
#: UCSB varies it per row. NULL is permitted (the CHECK only constrains present
#: values) for forward-compat.
RELIABILITY_VALUES: tuple[str, ...] = ("exact", "estimated", "unreliable")

#: The warehouse schema and shared PV fact table. The table shares the ``dwh`` schema
#: with the EC star schema (its ``state`` FK points at ``dwh.state``). Named
#: ``pv_votes`` — parallel to the EC ``votes`` fact — and deliberately kept distinct
#: from the D017 resolved-series names (``pv_preferred``/``pv_redistributable``/
#: ``pv_ucsb``/``pv_source``) so the raw per-source union is never confused with a
#: resolved view (the double-count hazard D017 warns about).
PV_SCHEMA = "dwh"
PV_TABLE = "pv_votes"


class PVShapeError(RuntimeError):
    """Raised when a frame handed to the shared PV loader is off the D018 shape.

    The source-neutral analogue of the per-source transform errors
    (:class:`usvote.mit.transform.MITTransformError`). It fires at the one shared
    write boundary (:func:`usvote.pv.load.load_pv_records`), so a malformed frame from
    *any* PV source — wrong column set/order, or a null natural-key/vote value — fails
    loudly here rather than as an opaque psycopg2 error mid-insert.
    """


def build_pv_column_defs(schema: str = PV_SCHEMA) -> list[tuple[str, ...]]:
    """Return the ``pv_votes`` column definitions as :meth:`DBC.create_table` tuples.

    A function (not a module constant) because the ``state`` FK embeds ``schema`` in
    its ``REFERENCES`` clause, exactly as :func:`usvote.load.build_table_column_defs`
    does for the EC tables. **``schema`` is the shared warehouse schema that already
    holds the EC dimensions** (D021: PV co-locates with the EC spine in one schema) —
    the ``state`` FK targets ``{schema}.state``, so it is *not* an independent
    PV-only location: passing a schema whose ``state`` dim does not exist yields a
    dangling FK at ``CREATE TABLE``. Both the EC load (:data:`usvote.load.SCHEMA`) and
    this must use the same schema; the default ``dwh`` keeps them aligned.

    ``pv_id`` is ``GENERATED ALWAYS AS IDENTITY``: the database owns a persistent
    sequence and assigns each row's id on insert, so ids stay globally unique **across
    separate loads** (MIT then UCSB, or incremental year batches) — the loader never
    supplies ``pv_id``. ``ALWAYS`` also rejects any hand-supplied id, so a per-call
    ``1..n`` scheme (which would collide on the second load) cannot be reintroduced.

    The remaining columns are :data:`SHARED_PV_COLUMNS`; the final tuple is a
    table-level ``UNIQUE`` constraint on the D018 natural key.
    """
    reliability_check = (
        "CHECK (reliability IN ("
        + ", ".join(f"'{v}'" for v in RELIABILITY_VALUES)
        + "))"
    )
    return [
        ("pv_id", "integer", "generated always as identity", "primary key"),
        ("source", "varchar", "not null"),
        ("year", "smallint", "not null"),
        ("state", "varchar", f"REFERENCES {schema}.state"),
        ("candidate", "varchar"),
        ("party", "varchar"),
        ("candidate_votes", "integer", "not null"),
        ("state_total_votes", "integer", "not null"),
        ("reliability", "varchar", reliability_check),
        (
            "CONSTRAINT",
            f"{PV_TABLE}_natural_key",
            "UNIQUE",
            "(source, year, state, candidate)",
        ),
    ]


def assert_pv_shape(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVShapeError
) -> None:
    """Assert ``df`` is on the D018 shared shape before the shared loader inserts it.

    Checks the columns are exactly :data:`SHARED_PV_COLUMNS` in order, that every
    :data:`REQUIRED_NON_NULL` column has no null values, and that every
    :data:`INTEGER_COLUMNS` count is an integer dtype (not float, which the
    ``integer`` DDL columns would silently round or error on). Raises
    :class:`PVShapeError` on any. This is the boundary guard that makes the loader
    safely reusable by every PV source — it does not re-validate source-specific
    invariants (grain, totals) that each source's own transform already enforced.

    ``error_cls`` lets a source raise its own typed error from this shared
    implementation (as :func:`usvote.mit.transform.assert_unique_grain` does), so a
    source's transform can use this as its own D018-shape guard instead of
    re-implementing it — and drift like a dropped non-null column (``candidate``) cannot
    reappear per source.
    """
    if list(df.columns) != list(SHARED_PV_COLUMNS):
        raise error_cls(
            f"PV frame columns {list(df.columns)} != shared PV shape "
            f"{list(SHARED_PV_COLUMNS)}"
        )
    for col in REQUIRED_NON_NULL:
        if df[col].isna().any():
            raise error_cls(
                f"PV frame column {col!r} has null value(s) (required non-null)"
            )
    for col in INTEGER_COLUMNS:
        if not pd.api.types.is_integer_dtype(df[col]):
            raise error_cls(
                f"PV frame column {col!r} must be integer, got {df[col].dtype}"
            )
