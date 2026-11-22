"""Top-level orchestration — scrape -> parse -> transform -> load.

Wires the four stage modules into a single end-to-end Electoral College
ingestion entry point (:func:`run_ec_pipeline`), so the pipeline runs from the
package instead of by executing notebook cells top-to-bottom.

Assembled in E2-S5 (#28). Configuration (DB connection params, the TIGER
shapefile path) is externalized in :mod:`usvote.config` (E2-S6, #31): this module
takes the resolved shapefile path and the ``DBC`` connection by dependency
injection, and :mod:`usvote.__main__` resolves both from the environment when run
as ``python -m usvote``.

The entry point is named for the source (``run_ec_pipeline``, not a bare
``run_pipeline``): under the D006 source-namespacing convention the popular-vote
sources land as sibling ``usvote/ucsb`` and ``usvote/mit`` subpackages, each with
its own pipeline.
"""

from __future__ import annotations

from collections.abc import Callable, Container

import pandas as pd

from usvote import load, parse, scrape, transform
from usvote.db import DBC
from usvote.scrape import Fetch, fetch_url
from usvote.years import (
    EC_SPINE_FLOOR,
    LATEST_ELECTION_YEAR,
    UNSUPPORTED_EC_YEARS,
    ec_ingest_years,
    election_years,
)

# The year-scope domain constants and functions moved to the dependency-free
# :mod:`usvote.years` in #36 and are re-exported here, so existing
# ``from usvote.pipeline import ec_ingest_years`` callers are unaffected. They moved
# because this module imports the DB and network stages, and :mod:`usvote.ucsb.
# transform` — a pure offline transform — must derive its ingest scope from
# :func:`ec_ingest_years` (D024 §6) without inheriting those dependencies.
#
# PATCH POINT: :mod:`usvote.years` is the *authoritative* home. ``ec_ingest_years``
# reads ``usvote.years.UNSUPPORTED_EC_YEARS`` at call time, so a test (e.g. #57
# simulating the Reconstruction-year gate being lifted) must patch it there —
# ``monkeypatch.setattr(usvote.years, "UNSUPPORTED_EC_YEARS", ...)``. The names below
# are by-value re-exports for import compatibility; rebinding
# ``usvote.pipeline.UNSUPPORTED_EC_YEARS`` does **not** change what ``ec_ingest_years``
# sees and would be a silently-passing no-op.
__all__ = [
    "EC_SPINE_FLOOR",
    "LATEST_ELECTION_YEAR",
    "UNSUPPORTED_EC_YEARS",
    "ec_ingest_years",
    "election_years",
    "run_ec_pipeline",
]


def run_ec_pipeline(
    dbc: DBC,
    shapefile_path: str,
    *,
    replace: bool = False,
    years: Container[int] | None = None,
    fetch: Fetch = fetch_url,
    load_geo: Callable[[str], pd.DataFrame] = transform.load_state_geo,
    close: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the end-to-end Electoral College ingestion and return the built frames.

    Reads the TIGER state geography once (via ``load_geo``), derives the valid
    state-name set from it — the same frame :func:`usvote.transform.build_state_dim`
    consumes, keeping the parse filter and the state dimension in lockstep (the SSOT
    is the shapefile) — then scrapes the Archives, parses each year's tables, builds
    the ``(candidates_df, state_df, votes_df)`` warehouse frames, and loads them into
    the ``dwh`` schema on ``dbc``.

    ``years`` is the set of election years to ingest; it defaults to
    :func:`ec_ingest_years` (the supported EC spine — 1824 through
    :data:`LATEST_ELECTION_YEAR`, excluding the Reconstruction-contested
    :data:`UNSUPPORTED_EC_YEARS`). Pass an explicit subset to ingest fewer years (e.g.
    ``{2016, 2020}`` to run only the years captured as fixtures). The scrape reads the
    full results index but fetches only the pages whose year is in ``years``.

    Seams mirror the stage modules' own: ``fetch`` (default live HTTP) lets the whole
    scrape replay from on-disk snapshots via :func:`usvote.scrape.fetch_from_dir`, and
    ``load_geo`` (default :func:`usvote.transform.load_state_geo`) lets a test inject a
    fake geo frame instead of the real shapefile. ``replace`` is forwarded to
    :func:`usvote.load.load_dataframes` — ``True`` for a destructive full rebuild,
    ``False`` (default) to create-if-absent. ``close`` is likewise forwarded; the
    caller owns ``dbc`` so it defaults to ``False``.

    Returns the three frames (candidates, state, votes) for inspection/validation.
    """
    state_geo = load_geo(shapefile_path)
    state_names = set(state_geo["NAME"])

    year_filter = ec_ingest_years() if years is None else years
    links = scrape.scrape_election_links(fetch=fetch)
    raw_tables = scrape.scrape_raw_election_tables(links, year_filter, fetch=fetch)
    parsed_years = parse.parse_election_years(raw_tables, state_names)

    candidates_df, state_df, votes_df = transform.transform_parsed_years(
        parsed_years, state_geo
    )
    # Load the three star-schema tables atomically (#84a): this pipeline OWNS the
    # transaction, so a caller above it (the #84b warehouse orchestrator) sequences
    # pipelines without wrapping them. On the ``replace=True`` path the schema drop +
    # rebuild is inside the transaction too, so an interrupted rebuild rolls back to the
    # previous warehouse rather than a dropped/half-built one. ``close`` fires after the
    # commit — a loader closing the connection mid-block would abort it. Scrape/parse/
    # transform above stay outside the transaction (no network holds it open).
    with dbc.transaction():
        load.load_dataframes(
            dbc,
            state_df=state_df,
            candidates_df=candidates_df,
            votes_df=votes_df,
            replace=replace,
        )
    if close:
        dbc.close_connection()
    return candidates_df, state_df, votes_df
