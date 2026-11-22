"""Top-level MIT orchestration — read -> transform -> reconcile -> load.

The MIT analogue of :mod:`usvote.pipeline`'s :func:`run_ec_pipeline`, wiring the four
MIT stages into one runnable path. Each PV source owns its own pipeline (the EC
``pipeline.py`` docstring's design), so this lives under ``usvote/mit/`` and loads
through the shared, source-neutral :func:`usvote.pv.load.load_pv_records` seam.

Kept thin and injectable: ``path``/``environ`` drive the read the same way
:func:`usvote.mit.read.load_mit_president_csv` does (so a test replays a fixture CSV
offline), and ``years`` scopes the load to a subset of elections — the MIT analogue
of ``run_ec_pipeline``'s ``years`` — which the integration test uses to load only the
years the EC fixtures also cover (so the ``state`` FK resolves). Year filtering runs
on the raw frame *before* transform, keeping every ``(year, state)`` group whole, so
transform's pre-filter totals reconciliation still holds.

``python -m usvote.mit load`` (bare ``python -m usvote.mit`` — ``load`` is the default
subcommand) runs this via :mod:`usvote.mit.__main__` (#84b); the whole-warehouse build
(:func:`usvote.warehouse.run_warehouse`) also calls it. There is no ``snapshot``
subcommand — MIT reads a local CSV, so unlike UCSB it has no network stage to reproduce.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.mit.read import load_mit_president_csv
from usvote.mit.reconcile import reconcile_mit
from usvote.mit.transform import transform_mit
from usvote.pv.load import load_pv_records


def run_mit_pipeline(
    dbc: DBC,
    path: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Run the end-to-end MIT PV ingestion and return the loaded frame.

    Reads the MIT ``1976-2024-president.csv`` (``path`` explicit, or resolved from
    ``USVOTE_MIT_CSV_PATH`` via ``environ`` when ``path`` is ``None``), optionally
    filters to ``years``, then transforms onto the D018 shared shape, reconciles
    ``state``/``candidate`` onto the canonical keys, and loads into ``dwh.pv_votes``
    via :func:`usvote.pv.load.load_pv_records`.

    ``years`` scopes the ingest to a subset of elections (e.g. ``{2016, 2020}`` to
    match the EC fixture years); ``None`` loads every year in the file. ``replace`` and
    ``close`` are forwarded to the loader — ``replace=True`` rebuilds ``dwh.pv_votes``
    only (never the schema; the EC spine survives). Returns the loaded frame (with
    ``pv_id``) for inspection/validation.
    """
    raw = load_mit_president_csv(path, environ=environ)
    if years is not None:
        matched = raw["year"].isin(years)
        if not matched.any():
            # Only materialize the diagnostic on the error path. .tolist() converts the
            # numpy scalars to native ints so the message renders as [2000, 2016].
            available = sorted(raw["year"].unique().tolist())
            raise ValueError(
                f"run_mit_pipeline: no MIT rows for requested years {sorted(years)}; "
                f"the file covers {available}."
            )
        raw = raw.loc[matched].copy()

    shaped = transform_mit(raw)
    reconciled = reconcile_mit(shaped)
    # One write, but wrapped for the uniform ownership rule (#84a): every pipeline owns
    # its DB-write transaction so the #84b orchestrator can sequence them without ever
    # nesting one. The load still does create-schema + create-table + insert, so the
    # transaction also makes those three all-or-nothing. ``close`` after the commit.
    with dbc.transaction():
        loaded = load_pv_records(dbc, reconciled, replace=replace)
    if close:
        dbc.close_connection()
    return loaded
