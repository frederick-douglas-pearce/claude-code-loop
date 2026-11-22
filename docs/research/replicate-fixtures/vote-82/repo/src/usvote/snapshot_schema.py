"""The API snapshot's serving contract — table names, columns, version, meta shape.

Deliberately **dependency-free** (stdlib only, like :mod:`usvote.slug`): it imports
neither :mod:`usvote.db` nor pandas. That is the point. The snapshot *build*
(:mod:`usvote.snapshot`) needs Postgres and pandas, but the *serving* layer
(``usvote/api/``, E8-S2) must not — D028 makes "no live DB at serve time" a **structural
import-graph invariant** (a test there asserts nothing under ``usvote/api/`` imports
``usvote.db``/psycopg2). Both sides need the same column names, table names, schema
version, and ``meta`` shape, so those live here where either can import them without
dragging the DB stack across the API's import boundary.

Only the *contract* lives here — the names and shapes E8-S2/S3 must agree on. Build-time
mechanics (the content-hash order, the integer-cast set, the SQL/SQLite writers) stay in
:mod:`usvote.snapshot`, which imports these.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bump when the snapshot's table shape or the roll-up's derivation logic changes. A
#: consumer keys compatibility off it, and :mod:`usvote.snapshot` folds it into the
#: content hash so a shape change forces a new ``snapshot_version``. **Because the hash
#: covers only the ``ec_pv`` data rows (not the derived roll-up), a change to how the
#: roll-up is computed with identical underlying data would NOT move the hash on
#: its own — so a roll-up-logic change MUST bump this version.**
SNAPSHOT_SCHEMA_VERSION = 1

#: The three snapshot tables (the serving contract E8-S2/S3 read).
DATA_TABLE = "ec_pv"
ROLLUP_TABLE = "national_rollup"
META_TABLE = "snapshot_meta"

#: The ``ec_pv`` fact columns, in order. This is ``usvote.join.EC_PV_COLUMNS`` with the
#: internal ``candidate_id`` **dropped** (D006), ``candidate_slug`` inserted after the
#: canonical ``candidate`` name, ``state_usps`` carried alongside the full ``state``
#: name (a clean URL/path key for ``/v1/states/{...}``, #97), and ``redistributable``
#: dropped (constant-true here — recorded once in ``snapshot_meta.source``).
DATA_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "state_usps",
    "candidate",
    "candidate_slug",
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "source",
    "party",
    "candidate_votes",
    "state_total_votes",
    "reliability",
)

#: The precomputed national roll-up columns, one row per ``(year, candidate_slug)``.
ROLLUP_COLUMNS: tuple[str, ...] = (
    "year",
    "candidate",
    "candidate_slug",
    "party",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "national_pv_votes",
    "national_pv_denominator",
)


@dataclass(frozen=True)
class SnapshotMeta:
    """The provenance row written to ``snapshot_meta`` and returned by the build.

    ``snapshot_version`` is the content hash (D028); ``build_timestamp`` is
    informational only and **excluded** from that hash, so two builds of the same
    warehouse data share a version even though their timestamps differ.
    ``year_min`` / ``year_max`` are **descriptive of the snapshot's actual content**
    (the redistributable years it contains), not a promise of completeness — a
    warehouse built over a scoped subset of years yields a narrower window.
    """

    snapshot_version: str
    schema_version: int
    row_count: int
    candidate_count: int
    year_min: int
    year_max: int
    source: str
    license: str
    build_timestamp: str
