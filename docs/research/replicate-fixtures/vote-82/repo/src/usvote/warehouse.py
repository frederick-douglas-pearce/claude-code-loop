"""Whole-warehouse composition root — build the entire ``dwh`` from every source.

:func:`run_warehouse` sequences the four source/join steps into one runnable build:
the EC spine (:func:`usvote.pipeline.run_ec_pipeline`), the MIT PV source
(:func:`usvote.mit.pipeline.run_mit_pipeline`), optionally the UCSB PV source
(:func:`usvote.ucsb.pipeline.run_ucsb_pipeline`), then the resolved-PV + EC<->PV join
views (:func:`rebuild_views`). It is the programmatic entry point behind
``python -m usvote all`` (#84b).

**This is a composition root, not part of the EC spine.** It lives at the top level
alongside the source-namespaced ``usvote/`` modules, but unlike them it imports *from*
every source (EC + both PV subpackages) to wire them together. That is allowed for the
same reason :mod:`usvote.__main__` is: a composition root sits **above** both EC and
PV, so it is exempt from the D015 source-to-source prohibition exactly as ``__main__``
is (D027). The invariant that keeps the exemption honest is the reverse one — nothing
under ``usvote/{mit,ucsb,pv}/`` may import :mod:`usvote.warehouse` (a back-import would
invert D015 into a cycle); a unit test enforces it.

**Transactions: per-source atomic, not globally atomic (#84a).** ``run_warehouse`` opens
**no** transaction of its own. Each pipeline it calls already wraps its own DB writes in
``with dbc.transaction():`` (the #84a uniform-ownership rule), and
:meth:`DBC.transaction` raises on a nested open, so wrapping the sequence here would be
a bug. The consequence is deliberate: a mid-build failure leaves the already-committed
sources in place and the later ones absent. Recovery is **not** a bare re-run — the
PV/EC loaders are create-if-absent/append, so a bare re-run raises a unique-constraint
violation on the first already-loaded source before it reaches the missing one. The
honest recovery path is ``run_warehouse(..., replace=True)`` (a clean full rebuild).
Scrape/network stays outside every transaction (each pipeline already keeps it out), so
no build holds a transaction open across HTTP.

**``replace`` maps EC-destructive, PV-additive.** ``replace=True`` forwards to
``run_ec_pipeline(replace=True)``, which drops and recreates the ``dwh`` schema — and
because the PV tables and all views live in ``dwh``, that ``DROP SCHEMA ... CASCADE``
takes them with it. So the PV loads run with ``replace=False`` (append onto the *fresh*
schema, the only sane mapping and exactly the integration-test order), and the join
views are **always rebuilt** as the final step — without that rebuild a
``replace=True`` build would leave a warehouse with the fact tables but no
``ec_pv_preferred`` / ``ec_pv_redistributable`` for E7/E8 to read.

**UCSB is gated explicitly, never by environment magic.** ``ucsb_html_dir=None`` (the
default) **skips** UCSB — this function does not consult ``USVOTE_UCSB_HTML_DIR``
itself; the caller decides and passes a directory to include it. This keeps the
D024/D017 principle — missing data is modeled explicitly, never silent — at the
programmatic seam: the returned :class:`WarehouseResult` names exactly which sources
loaded, so a downstream E7 hybrid step can refuse to compute over a warehouse that
silently lacks the UCSB consistency control, and E8 can assert it only ever built over
redistributable data. The ``python -m usvote all`` CLI may auto-detect the snapshot dir,
but only *loudly* (see :mod:`usvote.__main__`). The alignment worth stating: **EC + MIT
are the redistributable public core; UCSB is the analysis-only control** (the D016
split) — so "a fresh public clone builds EC + MIT, UCSB needs the private snapshot" is
not an arbitrary subset.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from usvote.db import DBC
from usvote.join import create_ec_pv_views
from usvote.mit.pipeline import run_mit_pipeline
from usvote.pipeline import run_ec_pipeline
from usvote.pv.load import build_pv_union
from usvote.scrape import Fetch, fetch_url
from usvote.transform import load_state_geo
from usvote.ucsb.pipeline import run_ucsb_pipeline

#: The source keys a full build loads, in dependency order (EC spine first).
SOURCE_EC = "ec"
SOURCE_MIT = "mit"
SOURCE_UCSB = "ucsb"


@dataclass(frozen=True)
class WarehouseResult:
    """What a :func:`run_warehouse` build loaded — the structured build receipt.

    ``sources_loaded`` names which of ``{"ec", "mit", "ucsb"}`` were ingested (UCSB is
    absent when ``ucsb_html_dir`` was ``None``). The ``*_rows`` counts are the loaded
    frame lengths; the two UCSB counts are ``None`` exactly when UCSB was skipped.
    ``views_built`` records that the resolved-PV + join views were (re)created —
    always ``True`` on a successful build, surfaced so a caller need not re-probe.

    Kept intentionally minimal: E7/E8 read the persistent views, so "is UCSB present?"
    is a query against ``dwh.pv_source`` / the ``pv_ucsb`` view at analysis time, not an
    in-process field to thread. This receipt answers "what did *this* build do", nothing
    speculative.
    """

    ec_rows: int
    mit_rows: int
    ucsb_pv_rows: int | None
    ucsb_roster_rows: int | None
    sources_loaded: frozenset[str]
    views_built: bool


def rebuild_views(dbc: DBC) -> None:
    """(Re)build the resolved-PV views and the EC<->PV join views over current facts.

    :func:`usvote.pv.load.build_pv_union` seeds ``dwh.pv_source`` and creates the three
    resolved series (``pv_preferred`` / ``pv_redistributable`` / ``pv_ucsb``); then
    :func:`usvote.join.create_ec_pv_views` runs its reciprocal anti-join precondition
    and creates ``ec_pv_preferred`` / ``ec_pv_redistributable``. Both are idempotent
    (``CREATE OR REPLACE VIEW``) and open no transaction of their own, so this is safe
    to call after any PV load and never nests over a pipeline's transaction (#84a).

    Factored out of :func:`run_warehouse` so a future ``views`` subcommand — rebuild
    the views without re-scraping the sources — is a thin wrapper over this, not a
    restructuring of the orchestrator (#84 follow-up).
    """
    build_pv_union(dbc)
    create_ec_pv_views(dbc)


def run_warehouse(
    dbc: DBC,
    shapefile_path: str,
    mit_csv_path: str | Path | None = None,
    *,
    ucsb_html_dir: str | Path | None = None,
    years: Collection[int] | None = None,
    replace: bool = False,
    environ: Mapping[str, str] | None = None,
    fetch: Fetch = fetch_url,
    load_geo: Callable[[str], pd.DataFrame] = load_state_geo,
    close: bool = False,
) -> WarehouseResult:
    """Build the whole ``dwh`` warehouse from every source and return a build receipt.

    Sequences EC -> MIT -> (optional) UCSB -> views on a single ``dbc``:

    1. :func:`usvote.pipeline.run_ec_pipeline` — the EC spine. ``replace`` is
       forwarded here (and here only): ``replace=True`` drops and recreates the ``dwh``
       schema, which cascades away the PV tables and views, so everything downstream
       rebuilds onto a fresh schema.
    2. :func:`usvote.mit.pipeline.run_mit_pipeline` — the MIT PV source, always
       ``replace=False`` (append onto the schema EC just built). ``mit_csv_path=None``
       resolves ``USVOTE_MIT_CSV_PATH`` via ``environ`` inside the MIT pipeline.
    3. :func:`usvote.ucsb.pipeline.run_ucsb_pipeline` — the UCSB PV source, only when
       ``ucsb_html_dir`` is not ``None`` (else UCSB is skipped, explicitly — no env
       magic). Also ``replace=False``.
    4. :func:`rebuild_views` — the resolved-PV + EC<->PV join views, always rebuilt.

    ``years`` scopes every source to the same subset of elections (e.g. ``{2016, 2020}``
    to match the fixtures); ``None`` loads each source's full range. ``environ`` is
    threaded to the two PV pipelines' config resolution (EC takes ``shapefile_path``
    directly). ``fetch`` and ``load_geo`` are the EC stage's offline-injection seams,
    forwarded to :func:`~usvote.pipeline.run_ec_pipeline` untouched (defaults are live
    HTTP + the real shapefile); they let the integration test drive *this* shipped path
    over saved fixtures instead of a hand-wired parallel copy. ``close`` closes ``dbc``
    when the build finishes — on success *after* the views are built, and also if a
    pipeline raises mid-build (in a ``finally``), so a caller passing ``close=True``
    never leaks the connection on a partial build. The orchestrator owns the connection
    across the whole build, so the individual pipelines are called with their default
    ``close=False``.

    Opens no transaction itself; see the module docstring for the per-source-atomic
    model and why a failed build is recovered with ``replace=True``, not a bare re-run.
    """
    try:
        candidates_df, state_df, votes_df = run_ec_pipeline(
            dbc,
            shapefile_path,
            replace=replace,
            years=years,
            fetch=fetch,
            load_geo=load_geo,
        )
        ec_rows = len(votes_df)

        mit_loaded = run_mit_pipeline(
            dbc, mit_csv_path, years=years, environ=environ, replace=False
        )
        mit_rows = len(mit_loaded)

        sources = {SOURCE_EC, SOURCE_MIT}
        ucsb_pv_rows: int | None = None
        ucsb_roster_rows: int | None = None
        if ucsb_html_dir is not None:
            pv_votes, roster = run_ucsb_pipeline(
                dbc, ucsb_html_dir, years=years, environ=environ, replace=False
            )
            ucsb_pv_rows = len(pv_votes)
            ucsb_roster_rows = len(roster)
            sources.add(SOURCE_UCSB)

        rebuild_views(dbc)

        return WarehouseResult(
            ec_rows=ec_rows,
            mit_rows=mit_rows,
            ucsb_pv_rows=ucsb_pv_rows,
            ucsb_roster_rows=ucsb_roster_rows,
            sources_loaded=frozenset(sources),
            views_built=True,
        )
    finally:
        # Close on either exit — success after the views, or a mid-build failure — so a
        # ``close=True`` caller never leaks the connection on a partial build. Each
        # source's commit/rollback is already owned by that pipeline's transaction
        # (#84a); closing here only releases the connection, not affecting atomicity.
        if close:
            dbc.close_connection()
