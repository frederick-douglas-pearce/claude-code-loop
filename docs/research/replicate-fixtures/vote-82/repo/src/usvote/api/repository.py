"""The ``SnapshotRepository`` seam — the API's only data-access path (E8-S2, #96).

A deliberately thin wrapper over the read-only SQLite snapshot. It isolates the SQLite
specifics (D028's chosen store) from the route handlers so that (a) E8-S3 endpoints read
through this interface, never raw SQL, and (b) a future mart/live backend (E9) could
satisfy the same shape without rewriting routes.

**No live DB, structurally.** This module imports only :mod:`usvote.snapshot_schema`
(stdlib-only: table/column names + the :class:`~usvote.snapshot_schema.SnapshotMeta`
shape) and stdlib :mod:`sqlite3`. It must **never** import :mod:`usvote.db`, psycopg2,
:mod:`usvote.snapshot` (which drags pandas + the DB stack), or pandas — the D028
import-graph invariant, enforced by ``tests/unit/test_api_import_graph.py``.

**Connection model.** The file is opened **read-only + immutable**
(``file:…?mode=ro&immutable=1``), a fresh connection per read: independent connections
over an immutable file are safe across uvicorn's threadpool (a single shared connection
is not merely by setting ``check_same_thread=False``), microsecond-cheap, and pick up a
dev-time ``os.replace`` rebuild without a pinned stale handle. The immutable
``snapshot_meta`` row is read **once at open** and cached in memory, so ``meta()`` /
``/health`` need no connection at all.
"""

from __future__ import annotations

import sqlite3
from dataclasses import fields
from pathlib import Path

from usvote.snapshot_schema import (
    DATA_COLUMNS,
    DATA_TABLE,
    META_TABLE,
    ROLLUP_COLUMNS,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotMeta,
)

#: Server-side row cap (D031 / #97). No legitimate scoped query approaches it: the whole
#: redistributable window is ~a few thousand ``ec_pv`` rows and the widest endpoint
#: (one candidate across the window) is ≈13 years × 51 states ≈ 660 rows — so hitting it
#: means a grain/fan-out regression, not a large-but-valid result. We therefore fetch
#: ``LIMIT MAX_ROWS + 1`` and **fail loud** on overflow (:class:`SnapshotError`) rather
#: than silently truncate: silent truncation is exactly the drop this codebase forbids.
MAX_ROWS = 5000


class SnapshotError(RuntimeError):
    """Raised when the snapshot cannot be opened or is incompatible at startup.

    A startup-time failure (missing file, empty/corrupt ``snapshot_meta``, a
    ``schema_version`` the server was not built for) — fail loud at boot rather than
    mis-serve a stale-shape snapshot or 500 per request (D028).
    """


class SnapshotRepository:
    """Read-only access to the SQLite snapshot behind a thin, swappable interface.

    Construct via :meth:`open`, which validates the snapshot at startup (meta row
    present, ``schema_version`` compatible) and caches the immutable provenance row. The
    data-read methods (by year / state / candidate) arrive in E8-S3; E8-S2 needs only
    :meth:`meta`.
    """

    def __init__(self, path: str, meta: SnapshotMeta) -> None:
        self._path = path
        self._meta = meta

    @classmethod
    def open(cls, snapshot_path: str) -> SnapshotRepository:
        """Open the snapshot read-only, validate it, and cache its ``snapshot_meta``.

        Fails loud (:class:`SnapshotError`) when the file has no ``snapshot_meta`` row
        or its ``schema_version`` differs from the :data:`SNAPSHOT_SCHEMA_VERSION` this
        server was built for — a mismatched snapshot would silently mis-serve.
        """
        if not Path(snapshot_path).exists():
            # The config layer already guards this (must_exist=True); belt-and-braces so
            # a repository opened directly (tests, a future caller) also fails clearly.
            raise SnapshotError(
                f"snapshot file {snapshot_path!r} does not exist — build it with "
                "`python -m usvote.snapshot` (needs the local warehouse)."
            )
        meta = cls._read_meta(snapshot_path)
        if meta.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotError(
                f"snapshot schema_version {meta.schema_version} != this server's "
                f"{SNAPSHOT_SCHEMA_VERSION}; rebuild the snapshot against the current "
                "code (`python -m usvote.snapshot`) or deploy a matching server."
            )
        return cls(snapshot_path, meta)

    @staticmethod
    def _connect(snapshot_path: str) -> sqlite3.Connection:
        """Open a fresh read-only, immutable connection to the snapshot file."""
        # ``as_uri`` percent-encodes the path (spaces, ``?``, ``#``, ``%``); a raw
        # f-string would let a ``?`` in the path start the query component early and
        # drop ``mode=ro``/``immutable=1``. Append our params to the encoded base.
        base = Path(snapshot_path).resolve().as_uri()
        conn = sqlite3.connect(
            f"{base}?mode=ro&immutable=1", uri=True, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def _read_meta(cls, snapshot_path: str) -> SnapshotMeta:
        """Read the single ``snapshot_meta`` row into a :class:`SnapshotMeta`."""
        cols = [f.name for f in fields(SnapshotMeta)]
        conn = cls._connect(snapshot_path)
        try:
            try:
                row = conn.execute(
                    f"SELECT {','.join(cols)} FROM {META_TABLE}"  # noqa: S608 — names are constants
                ).fetchone()
            except sqlite3.OperationalError as e:  # missing table / malformed file
                raise SnapshotError(
                    f"snapshot {snapshot_path!r} is missing the {META_TABLE} table — "
                    f"it is not a valid usvote snapshot ({e})."
                ) from e
        finally:
            conn.close()
        if row is None:
            raise SnapshotError(
                f"snapshot {snapshot_path!r} has an empty {META_TABLE} table."
            )
        return SnapshotMeta(**{c: row[c] for c in cols})

    def meta(self) -> SnapshotMeta:
        """Return the cached snapshot provenance (version, coverage, source/license)."""
        return self._meta

    @property
    def snapshot_version(self) -> str:
        """The content-hash version — the ETag value and the freshness key (D028)."""
        return self._meta.snapshot_version

    # --- data reads (E8-S3, #97) --------------------------------------------
    #
    # Each returns plain ``dict`` rows keyed by snapshot column (the route layer maps
    # them to public Pydantic models). Column lists are module constants, never user
    # input, so the f-string interpolation is safe (the S608 noqa).

    def _select(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        """Run a capped SELECT; fail loud if it would exceed :data:`MAX_ROWS`.

        Fetches ``LIMIT MAX_ROWS + 1`` and raises :class:`SnapshotError` on overflow — a
        grain/fan-out regression, never a silent truncation (see :data:`MAX_ROWS`).
        """
        conn = self._connect(self._path)
        try:
            rows = conn.execute(f"{sql} LIMIT ?", (*params, MAX_ROWS + 1)).fetchall()
        finally:
            conn.close()
        if len(rows) > MAX_ROWS:
            raise SnapshotError(
                f"query returned more than the {MAX_ROWS}-row cap "
                f"({sql!r}, params={params!r}) — a grain/fan-out regression; "
                "no legitimate scoped query is this large."
            )
        return [dict(r) for r in rows]

    def _exists(self, column: str, value: object) -> bool:
        """Whether any ``ec_pv`` row has ``column == value`` (for clean 404s)."""
        conn = self._connect(self._path)
        try:
            row = conn.execute(
                f"SELECT 1 FROM {DATA_TABLE} WHERE {column} = ? LIMIT 1",  # noqa: S608
                (value,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def list_years(
        self, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """Covered years with a distinct-candidate count, from the roll-up table."""
        clauses, params = _year_range_clauses(year_from, year_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._select(
            f"SELECT year, COUNT(*) AS candidate_count FROM {ROLLUP_TABLE}"  # noqa: S608
            f"{where} GROUP BY year ORDER BY year",
            tuple(params),
        )

    def year_exists(self, year: int) -> bool:
        """Whether the snapshot contains this year (pre-1976 / unknown → 404)."""
        return self._exists("year", year)

    def _data_rows(
        self, clauses: list[str], params: list[object], order_by: str
    ) -> list[dict[str, object]]:
        """Capped SELECT of the full ``ec_pv`` projection under a WHERE + ORDER BY.

        The one shared seam for the by-year / by-state / by-candidate fact reads, so the
        column projection and the cap live in one place. ``clauses`` and ``order_by``
        come only from module constants, never user input (the S608 noqa).
        """
        cols = ", ".join(DATA_COLUMNS)
        return self._select(
            f"SELECT {cols} FROM {DATA_TABLE} "  # noqa: S608
            f"WHERE {' AND '.join(clauses)} ORDER BY {order_by}",
            tuple(params),
        )

    def rows_by_year(
        self, year: int, state: str | None = None, candidate: str | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` state rows for a year, optionally narrowed by state/cand."""
        clauses = ["year = ?"]
        params: list[object] = [year]
        if state is not None:
            clauses.append("state_usps = ?")
            params.append(state.upper())
        if candidate is not None:
            clauses.append("candidate_slug = ?")
            params.append(candidate.lower())
        return self._data_rows(clauses, params, "state, candidate_slug")

    def rollup_by_year(self, year: int) -> list[dict[str, object]]:
        """The precomputed national roll-up rows for a year (no handler computation)."""
        cols = ", ".join(ROLLUP_COLUMNS)
        return self._select(
            f"SELECT {cols} FROM {ROLLUP_TABLE} WHERE year = ? "  # noqa: S608
            "ORDER BY president_electoral_rank",
            (year,),
        )

    def state_exists(self, usps: str) -> bool:
        """Whether the snapshot contains this USPS state code (else 404)."""
        return self._exists("state_usps", usps.upper())

    def rows_by_state(
        self, usps: str, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` rows for one state across years (optional year window)."""
        clauses = ["state_usps = ?"]
        params: list[object] = [usps.upper()]
        extra, extra_params = _year_range_clauses(year_from, year_to)
        clauses += extra
        params += extra_params
        return self._data_rows(clauses, params, "year, candidate_slug")

    def candidate_exists(self, slug: str) -> bool:
        """Whether the snapshot contains this candidate slug (else 404)."""
        return self._exists("candidate_slug", slug.lower())

    def rows_by_candidate(
        self, slug: str, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` rows for one candidate across years (optional year window)."""
        clauses = ["candidate_slug = ?"]
        params: list[object] = [slug.lower()]
        extra, extra_params = _year_range_clauses(year_from, year_to)
        clauses += extra
        params += extra_params
        return self._data_rows(clauses, params, "year, state")


def _year_range_clauses(
    year_from: int | None, year_to: int | None
) -> tuple[list[str], list[object]]:
    """Build ``year >= ?`` / ``year <= ?`` SQL fragments for an optional window."""
    clauses: list[str] = []
    params: list[object] = []
    if year_from is not None:
        clauses.append("year >= ?")
        params.append(year_from)
    if year_to is not None:
        clauses.append("year <= ?")
        params.append(year_to)
    return clauses, params
