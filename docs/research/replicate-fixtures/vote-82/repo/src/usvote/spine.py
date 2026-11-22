"""EC-spine readers — the DB seam a PV source uses to derive facts from the spine.

Two ``SELECT``s of the loaded EC star schema (``dwh.votes``/``dwh.candidate``), each
returning the exact frame a UCSB stage expects across its dependency-injection seam:

- :func:`read_ec_participation` — the ``dwh.votes`` participation frame
  :func:`usvote.ucsb.transform.transform_ucsb` builds the D024 roster from.
- :func:`read_ec_getters` — the president-EV getter frame
  :func:`usvote.ucsb.reconcile.reconcile_ucsb` runs its reciprocal completeness guard
  against.

**Why this lives at the top level, not under ``usvote/pv/``.** These readers embed
knowledge of the EC star schema (they name ``dwh.votes``/``dwh.candidate`` and the
``is_total`` shaping) — they are *EC-spine* readers that happen to feed a PV stage, not
part of the source-neutral PV contract. ``usvote/pv/`` holds only what every PV source
conforms to (the shared shape + loader); a greppable invariant follows — nothing under
``src/usvote/pv/`` mentions ``dwh.votes``. The precedent is :mod:`usvote.years`: a
dependency-free EC-domain module a PV transform reads *from* (D006 makes EC
authoritative), never the reverse.

Both are passed to the UCSB stages rather than queried inside them, so every UCSB
transform/reconcile test stays offline (the frames come from committed fixtures); this
module is the one place the real DB read happens, exercised by the ``#37`` integration
test.
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from usvote.db import DBC
from usvote.load import SCHEMA

#: Columns :func:`read_ec_participation` returns — the subset of ``dwh.votes`` the D024
#: roster derivation needs (``usvote.ucsb.transform._assert_participation_shape``).
EC_PARTICIPATION_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "is_total",
    "total_electoral_votes",
)

#: Columns :func:`read_ec_getters` returns — one row per ``(year, candidate)`` getter
#: (``usvote.ucsb.reconcile.EC_GETTERS_COLUMNS``).
EC_GETTERS_COLUMNS: tuple[str, ...] = (
    "year",
    "candidate",
    "president_electoral_votes",
)


def _year_predicate(years: Collection[int] | None, *, column: str) -> str | None:
    """Return a ``column IN (...)`` predicate narrowing to ``years``, or ``None``.

    The caller composes it into ``WHERE``/``AND`` as its query needs. The year values
    are the pipeline's own in-scope set (ints from
    :func:`usvote.years.ec_ingest_years`), never user input, so an inline literal list
    is safe here; ``None`` years reads every year.

    An **empty but non-``None``** ``years`` (e.g. a caller passing ``set()``) means "no
    in-scope years", so it returns the always-false predicate ``"FALSE"`` — a valid
    query yielding zero rows — rather than the invalid SQL ``column IN ()`` that an
    empty join would produce.
    """
    if years is None:
        return None
    ints = ", ".join(str(int(y)) for y in sorted(years))
    if not ints:
        return "FALSE"
    return f"{column} IN ({ints})"


def read_ec_participation(
    dbc: DBC,
    *,
    schema: str = SCHEMA,
    years: Collection[int] | None = None,
) -> pd.DataFrame:
    """Read the ``dwh.votes`` participation frame the UCSB roster derives from.

    Returns :data:`EC_PARTICIPATION_COLUMNS` — every ``dwh.votes`` row (including the
    per-year totals rows, ``state`` NULL / ``is_total`` true, which the roster
    derivation excludes itself). ``years`` narrows to a subset of elections; ``None``
    reads all.

    A 0/1-int ``is_total`` is coerced to ``bool`` here; **any other representation is
    passed through untouched** so
    :func:`usvote.ucsb.transform._assert_participation_shape` can validate it. A blanket
    ``.astype(bool)`` would silently map every non-empty ``'t'``/``'f'`` string to
    ``True`` — treating every row as a totals row — and, because it runs *before* that
    guard, would defeat the guard's whole reason to reject strings. Real Postgres
    booleans already arrive as ``bool`` (via psycopg2), so this coercion is a no-op on
    the live path and only rescues the 0/1-int case.
    """
    predicate = _year_predicate(years, column="year")
    where = f" WHERE {predicate}" if predicate else ""
    df = dbc.select_query_to_df(
        f"SELECT year, state, is_total, total_electoral_votes "
        f"FROM {schema}.votes{where}"
    )
    if pd.api.types.is_integer_dtype(df["is_total"]):
        df["is_total"] = df["is_total"].astype(bool)
    return df[list(EC_PARTICIPATION_COLUMNS)]


def read_ec_getters(
    dbc: DBC,
    *,
    schema: str = SCHEMA,
    years: Collection[int] | None = None,
) -> pd.DataFrame:
    """Read the president-EV getter frame the UCSB reconcile completeness guard needs.

    Returns :data:`EC_GETTERS_COLUMNS` — one row per ``(year, candidate)``, the
    canonical candidate ``name`` joined from ``dwh.candidate`` and the **national**
    ``president_electoral_votes`` total. The national total sits on each candidate's
    ``is_total`` row (state NULL), so filtering to ``is_total`` yields exactly one row
    per getter and avoids the per-state duplicates a whole-fact read would produce.
    (The ``> 0`` getter filter is applied downstream in
    :func:`usvote.ucsb.reconcile._assert_getter_completeness`, which also owns the
    empty-frame guard.)

    ``years`` narrows to a subset of elections; ``None`` reads all.
    """
    predicate = _year_predicate(years, column="v.year")
    year_and = f" AND {predicate}" if predicate else ""
    df = dbc.select_query_to_df(
        f"SELECT v.year, c.name AS candidate, v.president_electoral_votes "
        f"FROM {schema}.votes v "
        f"JOIN {schema}.candidate c ON v.candidate_id = c.candidate_id "
        f"WHERE v.is_total{year_and}"
    )
    return df[list(EC_GETTERS_COLUMNS)]
