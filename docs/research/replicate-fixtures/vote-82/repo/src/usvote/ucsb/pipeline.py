"""Top-level UCSB orchestration — snapshot -> parse -> transform -> reconcile -> load.

The UCSB analogue of :func:`usvote.mit.pipeline.run_mit_pipeline`, wiring the merged
stage stories (#35 parse, #36 transform, #38 reconcile) into one runnable path and
loading through the shared, source-neutral :mod:`usvote.pv.load` seam. Each PV source
owns its own pipeline (the EC ``pipeline.py`` docstring's design), so this lives under
``usvote/ucsb/``.

**``python -m usvote.ucsb`` defaults to *snapshot*, not *run this pipeline*.** The UCSB
``__main__`` is subcommand-based (#84b): ``load`` runs this pipeline, while the **bare**
``python -m usvote.ucsb`` (the ``snapshot`` default) runs
:func:`usvote.ucsb.scrape.snapshot_elections` — the D023 reproducible network refresh.
So bare UCSB snapshots while bare ``python -m usvote`` loads; the asymmetry is
principled (MIT reads a local CSV and has no network stage to snapshot, so only UCSB
carries a snapshot command) and is now a *documented default subcommand* rather than a
surprise (D027). This pipeline is also invoked by the whole-warehouse build
(:func:`usvote.warehouse.run_warehouse`).

**Two tables, one ``replace``, loaded atomically.** A UCSB run loads *both* shared PV
tables — the ``dwh.pv_votes`` fact and the ``dwh.pv_state_status`` roster — the two
frames :func:`usvote.ucsb.transform.transform_ucsb` emits. One ``replace`` flag drives
both loads (never two knobs), and both writes run inside a single
:meth:`usvote.db.DBC.transaction` (#84a), so the D024 two-way roster/fact invariant can
never be left half-written in the database: a crash rolls the pair back together. The
roster still loads **first** — its ``state`` FK targets ``dwh.state`` (safe once the
EC spine is loaded) — but that ordering is now a readability choice, not the
blast-radius guard it had to be when the two writes committed separately. A re-run over
already-loaded data still raises a unique-constraint violation (the intended
non-destructive guard); the transaction now also rolls back the first table's write when
the second fails, rather than leaving it committed.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.pv.load import load_pv_records, load_pv_status
from usvote.spine import read_ec_getters, read_ec_participation
from usvote.ucsb.parse import parse_election_years
from usvote.ucsb.reconcile import reconcile_ucsb
from usvote.ucsb.scrape import read_snapshot_html
from usvote.ucsb.transform import transform_ucsb, ucsb_ingest_years


def run_ucsb_pipeline(
    dbc: DBC,
    html_dir: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the end-to-end UCSB PV ingestion and return the loaded frames.

    Reads the saved snapshot (``html_dir`` explicit, or resolved from
    ``USVOTE_UCSB_HTML_DIR`` via ``environ`` when ``None``), parses each page, derives
    the roster from the EC ``votes`` participation frame, transforms onto the D018
    shared shape + D024 roster, reconciles ``candidate`` onto the canonical keys against
    the EC president-EV getters, and loads both into ``dwh`` alongside (never
    overwriting) the EC spine and MIT data.

    ``years`` scopes every stage to a subset of elections (e.g. ``{2016, 2020}`` to
    match the EC fixture years); it is resolved **once** here — defaulting to
    :func:`~usvote.ucsb.transform.ucsb_ingest_years` — and threaded to the snapshot
    read, transform, reconcile, and both spine reads, so a partial run never reports
    unprocessed years as violations and the roster/getter guards see the same year set.

    ``replace`` gates the table-level rebuild of **both** PV tables (never the schema;
    the EC spine survives); it drives one flag to both loads. ``close`` closes the
    connection after the last load — the pipeline owns it, so it is not threaded into
    the individual loaders.

    Returns ``(pv_votes, roster)`` — the reconciled fact frame (as inserted, without
    ``pv_id``) and the roster frame (as inserted, without ``status_id``). Raises the
    UCSB stage errors (:class:`~usvote.ucsb.transform.UCSBTransformError` and
    subclasses) on any validation failure, or
    :class:`~usvote.ucsb.scrape.UCSBScrapeError` on a structurally broken snapshot.
    """
    in_scope = frozenset(ucsb_ingest_years() if years is None else years)

    html_by_year = read_snapshot_html(html_dir, years=in_scope, environ=environ)
    parsed_years = parse_election_years(html_by_year)

    ec_participation = read_ec_participation(dbc, years=in_scope)
    pv_votes, roster = transform_ucsb(parsed_years, ec_participation, years=in_scope)

    ec_getters = read_ec_getters(dbc, years=in_scope)
    reconciled = reconcile_ucsb(pv_votes, roster, ec_getters, years=in_scope)

    # Both writes in ONE transaction (#84a), so the D024 two-way roster/fact invariant
    # can never be left half-written in the DB. This pipeline OWNS the transaction; the
    # #84b orchestrator sequences pipelines and must not wrap them again
    # (DBC.transaction() is single-level and raises on a nested open). Roster still
    # loads first — its state FK is safe once the EC spine is loaded — but the ordering
    # is now a readability choice, not the corruption guard it had to be when the two
    # writes committed separately. Scrape/parse/transform/reconcile above (including the
    # spine reads) stay OUTSIDE the transaction; ``close`` fires after the commit, since
    # a loader closing the connection mid-block would abort it.
    with dbc.transaction():
        loaded_roster = load_pv_status(dbc, roster, replace=replace)
        loaded_pv = load_pv_records(dbc, reconciled, replace=replace)
    if close:
        dbc.close_connection()
    return loaded_pv, loaded_roster
