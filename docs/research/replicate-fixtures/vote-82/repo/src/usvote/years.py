"""Election-year domain constants and the default EC ingest scope.

Extracted from :mod:`usvote.pipeline` (#36) so that a **pure, offline** module can
name the year scope without importing the orchestrator. ``usvote.pipeline`` imports
:mod:`usvote.load`, :mod:`usvote.scrape` and :class:`usvote.db.DBC`, so it pulls in
psycopg2 and the network stack; :mod:`usvote.ucsb.transform` needs only
:func:`ec_ingest_years`, and a leaf transform depending on the top-level orchestrator
is the shape that becomes a real import cycle the moment PV is wired into
``usvote.pipeline``.

Everything here is data and pure functions — **this module must stay dependency-free**
(no stage modules, no DB, no network), which is the property that makes it importable
from any source subpackage.

``usvote.pipeline`` re-exports all five names, so existing
``from usvote.pipeline import ec_ingest_years`` callers are unaffected.

**Why UCSB imports this (D006).** The EC spine is authoritative on participation, and
UCSB's ingest scope is *derived* from it — ``ec_ingest_years()`` minus the years UCSB
publishes no popular vote for (D024 §6, clarified 2026-07-18). The dependency direction
``ucsb -> years`` is acyclic and D006-correct; the literals ``1868``/``1872`` must never
be duplicated into ``usvote/ucsb/``, so that #57 lifting :data:`UNSUPPORTED_EC_YEARS`
admits both years to UCSB ingestion with no change there.
"""

from __future__ import annotations

# The most recent election year the pipeline ingests. A domain constant bumped
# each cycle (the notebook, cell 7, hardcoded 2020; this is the actual latest).
# Not deployment config: callers override per-run via ``election_years(latest=...)``
# or the ``years`` argument to :func:`usvote.pipeline.run_ec_pipeline`.
LATEST_ELECTION_YEAR = 2024

# The default EC ingestion floor (#32). The structurally-uniform post-12th-Amendment
# era begins in 1804, but the default spine starts at 1824 — the MVP popular-vote
# comparison floor (D009). 1804-1820 are post-12A yet below that floor and carry their
# own elector-shortfall notation in the totals cell ("176 (175)*" = appointed (cast));
# they are deferred, not required. 1789-1800 are pre-12th-Amendment (each elector cast
# two presidential votes) and out of scope entirely — a dedicated later epic (D010).
EC_SPINE_FLOOR = 1824

# Years the default ingest deliberately excludes because their Archives tables encode
# contested/uncounted electoral votes that need dedicated modeling, not the standard
# per-state candidate grain (#32; tracked for follow-up in #57):
#   - 1868: Georgia's 9 votes were contested (Congress could not agree whether to count
#     them), so the page carries dual "excluding/including Georgia" totals rows, and
#     Mississippi, Texas and Virginia did not participate (not yet readmitted).
#   - 1872: Horace Greeley died after the popular vote; his electoral votes scattered
#     across several candidates and Georgia's 3 Greeley votes were rejected by Congress.
# These are a default-scoping choice, not a hard block: an explicit ``years={1868}``
# still attempts them and fails loudly rather than being silently dropped.
#
# This constant is the **single gate** on both sources: UCSB derives its own scope from
# ``ec_ingest_years()`` (D024 §6), so removing a year here admits it to E4 as well.
UNSUPPORTED_EC_YEARS = frozenset({1868, 1872})


def election_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """Return the set of US presidential election years, 1789 through ``latest``.

    1789 is the lone off-cycle year (the first election); every election since has
    been held every four years from 1792. Ported from notebook cells 10/11; the
    full election calendar. :func:`ec_ingest_years` narrows this to the years the EC
    pipeline actually ingests by default. ``latest + 1`` as the range bound includes
    ``latest`` when it is an election year without overshooting to the next cycle when
    it is not (e.g. ``election_years(2025)`` stops at 2024, not 2028).
    """
    return {1789} | set(range(1792, latest + 1, 4))


def ec_ingest_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """The default set of years the EC pipeline ingests.

    The full election calendar (:func:`election_years`) narrowed to the supported EC
    spine: from :data:`EC_SPINE_FLOOR` (1824, the D009 comparison floor) through
    ``latest``, excluding :data:`UNSUPPORTED_EC_YEARS` (the Reconstruction years whose
    contested/uncounted votes need dedicated modeling). See those constants for why the
    pre-1824 and 1868/1872 years are out of the default. This is the default ``years``
    filter for :func:`usvote.pipeline.run_ec_pipeline`; pass an explicit ``years`` to
    override it.

    Also the base of the **UCSB** ingest scope — :func:`usvote.ucsb.transform.
    ucsb_ingest_years` subtracts the no-popular-vote years from this set (D024 §6).
    """
    return {
        y
        for y in election_years(latest)
        if y >= EC_SPINE_FLOOR and y not in UNSUPPORTED_EC_YEARS
    }
