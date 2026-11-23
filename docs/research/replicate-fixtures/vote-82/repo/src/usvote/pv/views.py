"""The three D017 resolution views over the raw PV union, plus pure frame oracles.

The raw PV union already exists physically: both sources load into one
``dwh.pv_votes`` through :func:`usvote.pv.load.load_pv_records`, tagged by ``source``,
with ``source`` in the natural key so the overlap keeps **both** rows (D017 §1). This
story adds no second fact table — it exposes the union as three *thin views* that
resolve the three D017 series at **read time** (never by deduping the fact):

- **``pv_preferred``** (D017 §2) — the default analysis series: exactly one row per
  ``(year, state, candidate)``, MIT winning the 1976–2024 overlap and UCSB supplying
  everything earlier. Resolved by ``DISTINCT ON (key) ORDER BY key, precedence_rank`` —
  precedence comes from :mod:`usvote.pv.source`, **not** a hardcoded ``CASE``, so a
  future grant/new source is a one-row data edit (the forward-compat guarantee).
- **``pv_redistributable``** (D017 §4) — the public API surface: defined
  **independently** as ``WHERE redistributable`` (MIT only), *not* as a filter over
  ``pv_preferred``, so no change to preference resolution can ever leak a
  non-redistributable UCSB row onto the public surface.
- **``pv_ucsb``** (D017 §5) — the whole-span UCSB-only consistency control. Filtered on
  the literal ``source = 'UCSB'`` **by design**: it is specifically the UCSB
  single-source longitudinal lens, not a generic "any non-redistributable source" view.

**Hand-off to #69 (a load-bearing warning):** the EC join must read a *resolved* view
(``pv_preferred`` / ``pv_redistributable``), **never** ``dwh.pv_votes`` — joining the
raw union would fan the 1976–2024 overlap out 2× and double-count every downstream
sum/margin (D017 §Consequence). The views read ``pv_votes`` only (never the roster
``pv_state_status``), so the ``redistributable=false`` roster ``note`` prose cannot leak
through them either.

The SQL builders and the pure frame oracles (``resolve_preferred`` and the assert
helpers) are two testable expressions of the same policy: the builders are unit-tested
as strings and drive the live views; the oracles run on small two-source fixtures and
are re-run against frames read back from the live views (the dual-use precedent of
:func:`usvote.pv.status.assert_roster_covers_facts`).
"""

from __future__ import annotations

import pandas as pd

from usvote.pv.schema import NATURAL_KEY, PV_SCHEMA, PV_TABLE, SHARED_PV_COLUMNS
from usvote.pv.source import PV_SOURCE_TABLE, SOURCE_UCSB

#: The resolved-series view names. Kept deliberately apart from the raw-union table
#: name (:data:`usvote.pv.schema.PV_TABLE`) so the two objects — raw tagged union vs.
#: resolved single-row series — are never confused (D017 names them apart).
PV_PREFERRED_VIEW = "pv_preferred"
PV_REDISTRIBUTABLE_VIEW = "pv_redistributable"
PV_UCSB_VIEW = "pv_ucsb"

#: The ``(year, state, candidate)`` key the resolved series is unique on — the D018
#: natural key minus ``source`` (the union carries both sources per key; the resolved
#: series carries one). ``pv_preferred`` guarantees exactly one row per this key.
RESOLVED_KEY: tuple[str, ...] = ("year", "state", "candidate")


class PVViewError(RuntimeError):
    """Raised when the PV union or a resolved frame violates a view invariant.

    Covers the pure-frame guards in this module — a duplicated union natural key, a
    resolved frame with >1 row per ``(year, state, candidate)``, or a ``pv_votes``
    source with no ``pv_source`` row (the provenance-coverage gap the deliberate absence
    of a DB FK leaves to a test to catch).
    """


def _select(alias: str) -> str:
    """The ``SHARED_PV_COLUMNS`` select list, qualified by ``alias`` (``v.year``)."""
    return ", ".join(f"{alias}.{col}" for col in SHARED_PV_COLUMNS)


def build_pv_preferred_sql(schema: str = PV_SCHEMA) -> str:
    """Return the ``pv_preferred`` SELECT — one row per key, MIT-preferred (D017 §2).

    ``DISTINCT ON (year, state, candidate)`` with ``ORDER BY (year, state, candidate),
    s.precedence_rank`` keeps the lowest-rank (MIT = 1) row per key; where MIT has no
    row only UCSB rank-2 rows exist for that key, so UCSB is kept. Precedence is read
    from the ``pv_source`` join, never hardcoded. An inner join (not outer) means a key
    absent from *both* sources is simply absent — never fabricated (D005).
    """
    key = ", ".join(f"v.{col}" for col in RESOLVED_KEY)
    return (
        f"SELECT DISTINCT ON ({key}) {_select('v')} "
        f"FROM {schema}.{PV_TABLE} v "
        f"JOIN {schema}.{PV_SOURCE_TABLE} s USING (source) "
        f"ORDER BY {key}, s.precedence_rank"
    )


def build_pv_redistributable_sql(schema: str = PV_SCHEMA) -> str:
    """Return the ``pv_redistributable`` SELECT — the public surface (D017 §4).

    Defined **independently** as ``WHERE s.redistributable`` (a join to ``pv_source``,
    reading the attribute — not a hardcoded ``source = 'MIT'``, and **not** a filter
    over ``pv_preferred``). Structurally it cannot surface a non-redistributable row
    regardless of any future precedence change.

    It is deduped the same way ``pv_preferred`` is — ``DISTINCT ON (year, state,
    candidate) ORDER BY …, precedence_rank`` — so it stays **exactly one row per key**
    even if a second redistributable source is ever added (the "one-row `pv_source`
    edit" the reference table advertises would otherwise silently double-count the
    public surface where two redistributable sources overlap). Today only MIT is
    redistributable, so the ``DISTINCT ON`` is a no-op and this coincides with
    ``pv_preferred`` across the overlap by construction; it is a forward-compat guard,
    not a behavior change.
    """
    key = ", ".join(f"v.{col}" for col in RESOLVED_KEY)
    return (
        f"SELECT DISTINCT ON ({key}) {_select('v')} "
        f"FROM {schema}.{PV_TABLE} v "
        f"JOIN {schema}.{PV_SOURCE_TABLE} s USING (source) "
        f"WHERE s.redistributable "
        f"ORDER BY {key}, s.precedence_rank"
    )


def build_pv_ucsb_sql(schema: str = PV_SCHEMA) -> str:
    """Return the ``pv_ucsb`` SELECT — the whole-span UCSB-only control (D017 §5).

    Filtered on the literal ``source = 'UCSB'`` **by design**: this is the UCSB
    single-source longitudinal lens specifically, not a generic non-redistributable
    filter (which would silently absorb any future analysis-only source). Reads
    ``pv_votes`` only — no ``pv_source`` join needed.
    """
    return (
        f"SELECT {_select('v')} "
        f"FROM {schema}.{PV_TABLE} v "
        f"WHERE v.source = '{SOURCE_UCSB}'"
    )


def assert_union_grain(
    union_df: pd.DataFrame, *, error_cls: type[Exception] = PVViewError
) -> None:
    """Assert one union row per ``(source, year, state, candidate)`` (the D018 key).

    The table ``UNIQUE`` enforces this in the DB; this is the offline mirror so the
    fixture-level tests catch a malformed union before it reaches Postgres.
    """
    dupes = union_df.loc[union_df.duplicated(list(NATURAL_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "PV union grain violated — duplicate (source, year, state, candidate): "
            f"{dupes[list(NATURAL_KEY)].values.tolist()}"
        )


def assert_single_row_per_key(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVViewError
) -> None:
    """Assert exactly one row per ``(year, state, candidate)`` — the ``pv_preferred``
    guarantee. Run on ``resolve_preferred`` output and on the live view read back."""
    dupes = df.loc[df.duplicated(list(RESOLVED_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "resolved series has >1 row per (year, state, candidate): "
            f"{dupes[list(RESOLVED_KEY)].values.tolist()}"
        )


def assert_provenance_coverage(
    union_df: pd.DataFrame,
    pv_source_df: pd.DataFrame,
    *,
    error_cls: type[Exception] = PVViewError,
) -> None:
    """Assert every ``source`` in the union has a ``pv_source`` row.

    There is deliberately **no** ``pv_votes.source -> pv_source`` FK (adding one would
    reorder the existing load path); this test is what guards the gap instead. A source
    missing from ``pv_source`` would be silently dropped by ``pv_preferred``'s inner
    join to it — this fails loudly instead.
    """
    unknown = sorted(set(union_df["source"]) - set(pv_source_df["source"]))
    if unknown:
        raise error_cls(
            f"PV union has source(s) {unknown} with no pv_source row; the "
            f"pv_preferred/pv_redistributable joins would silently drop them"
        )


def resolve_preferred(
    union_df: pd.DataFrame,
    pv_source_df: pd.DataFrame,
    *,
    error_cls: type[Exception] = PVViewError,
) -> pd.DataFrame:
    """Pure pandas mirror of the ``pv_preferred`` view — the resolver oracle (D017 §2).

    Joins ``precedence_rank`` from ``pv_source`` (via :func:`assert_provenance_coverage`
    first, so an unknown source raises rather than dropping), then keeps the lowest-rank
    row per ``(year, state, candidate)`` with a stable sort + ``drop_duplicates``. Used
    in unit tests to prove MIT wins the overlap, UCSB is kept pre-1976, and a MIT-only
    key stays MIT — the same resolution the live view performs.
    """
    assert_provenance_coverage(union_df, pv_source_df, error_cls=error_cls)
    ranked = union_df.merge(
        pv_source_df[["source", "precedence_rank"]], on="source", how="left"
    )
    ordered = ranked.sort_values(
        [*RESOLVED_KEY, "precedence_rank"], kind="stable"
    )
    resolved = ordered.drop_duplicates(list(RESOLVED_KEY), keep="first")
    return resolved[list(SHARED_PV_COLUMNS)].reset_index(drop=True)
