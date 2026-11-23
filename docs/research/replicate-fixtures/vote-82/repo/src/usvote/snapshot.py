"""Materialize ``ec_pv_redistributable`` into a read-only SQLite snapshot (E8-S1, #95).

The API's **only** data source (D028): the snapshot is built here from the local
warehouse, and the running API (``usvote/api/``, E8-S2) reads the artifact with **no
live DB at serve time**. Keeping the build here — a new top-level EC-domain consumer of
``ec_pv_redistributable`` in the :mod:`usvote.spine` / :mod:`usvote.join` /
:mod:`usvote.warehouse` family (composition-root-exempt from D015 per D027) — is what
makes the DB-free property *structural*: ``usvote/api/`` imports the artifact + a thin
repository, never :mod:`usvote.db`. This module names ``ec_pv_redistributable`` (EC
star-schema knowledge), so like :mod:`usvote.join` it stays out of ``usvote/pv/``.

**The serving contract (what E8-S2/S3 consume).** A SQLite file with three tables:

``ec_pv`` — the joined fact, one row per ``(year, state, candidate_slug)`` over the
    **redistributable window** (the years MIT covers, 1976–2024). Every EC state row in
    those years is kept (winners *and* 0-EV losers — the dense-fact rows the thesis
    needs, D026); PV columns are NULL for a getter MIT does not cover (a faithless
    elector, an unpledged slate), an honest D005 gap. Indexed on ``year`` / ``state`` /
    ``candidate_slug`` for the by-year/by-state/by-candidate endpoints (#97). The
    internal surrogate ``candidate_id`` is **dropped** (D006 /
    ``docs/canonical-keys.md``) and replaced by ``candidate_slug`` — the durable public
    candidate id minted here. ``state_usps`` is carried alongside the full
    ``state`` name as a clean URL/path key for ``/v1/states/{...}`` (#97).

``national_rollup`` — one row per ``(year, candidate_slug)`` with the per-candidate
    national EC total (the view's window sum) and national PV total (+ denominator), so
    ``/v1/elections/{year}/summary`` (#97) **reads** the roll-up instead of computing it
    in a route handler. Safe to precompute because the redistributable window is
    **single-source (MIT)**, so the D017 cross-source-denominator caveat does not bite.

``snapshot_meta`` — one row of provenance for the API ``meta`` block: the content-hash
    ``snapshot_version``, the schema version, row/candidate counts, the coverage window
    (``year_min`` / ``year_max``), ``source`` = MIT and its ``license`` (CC0-1.0, read
    from the ``pv_source`` reference data, not hardcoded), and an **informational-only**
    build timestamp.

**Version = content hash, not timestamp (D028).** ``snapshot_version`` is a SHA-256
over the ``ec_pv`` rows in a deterministic ``ORDER BY (year, state, candidate_slug)``
plus the schema version; the build timestamp is excluded from it. This reconciles the
two requirements that would otherwise conflict — byte-reproducibility ("same warehouse,
same version") and the ETag freshness contract ("identical data, identical version") —
and is why the timestamp is metadata only.

**Redistributable-only guaranteed at the source (D030).** The build reads
``ec_pv_redistributable`` (which wraps ``pv_redistributable``, defined independently as
``WHERE redistributable``, D017), and :func:`assert_redistributable_only` re-asserts
that no ``redistributable = false`` / non-MIT row entered the snapshot — the first of
the three defense-in-depth guards (source here, endpoints in #97, regression in #99).

Build it with ``python -m usvote.snapshot`` (needs the local warehouse; writes to
``USVOTE_API_SNAPSHOT_PATH``). The pure builder :func:`build_snapshot` takes an
in-memory ``ec_pv_redistributable``-shaped frame, so the whole contract is unit-tested
offline from a small synthetic frame — no live DB.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from usvote import config
from usvote.config import ConfigError
from usvote.db import DBC, DBConnectionError
from usvote.join import EC_PV_REDISTRIBUTABLE_VIEW
from usvote.load import SCHEMA
from usvote.pv.source import SOURCE_MIT, build_pv_source_frame
from usvote.slug import candidate_slug
from usvote.snapshot_schema import (
    DATA_COLUMNS,
    DATA_TABLE,
    META_TABLE,
    ROLLUP_COLUMNS,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotMeta,
)

#: The name of the EC state dimension the build reads ``state_usps`` from. Reading a
#: second *relation* (not a second path to the join view) is fine — the AC's "reuse the
#: view, no second hand-rolled SQL path" is about the view, and ``state_usps`` is a
#: clean URL/path key for ``/v1/states/{...}`` (#97) the view itself does not carry.
STATE_DIM = "state"

#: Integer-valued columns that the EC-left join returns as float64 (LEFT-JOIN NULLs make
#: NaN). Cast to nullable ``Int64`` before hashing/writing so ``150`` never becomes
#: ``150.0`` (which would make the content hash depend on pandas' float formatting) and
#: so NULLs land as SQL NULL, not the float ``NaN``.
_INTEGER_COLUMNS: tuple[str, ...] = (
    "total_electoral_votes",
    "president_electoral_votes",
    "national_electoral_votes",
    "president_electoral_rank",
    "candidate_votes",
    "state_total_votes",
)

#: The deterministic order the content hash and the ``ec_pv`` rows are written in.
_ORDER_BY: tuple[str, ...] = ("year", "state", "candidate_slug")


class SnapshotError(RuntimeError):
    """Raised when the snapshot build violates an E8-S1 invariant.

    Covers a non-redistributable row reaching the build (D030), a slug collision
    (``docs/canonical-keys.md`` same-name residual), or a missing source view — each a
    fail-loud condition rather than a silently degraded snapshot.
    """


def _mit_license() -> str:
    """Return MIT's license from the ``pv_source`` reference data (D017: data not code).

    The redistributable surface is MIT-only, so the snapshot's license is MIT's — read
    from :func:`usvote.pv.source.build_pv_source_frame` rather than duplicating the
    literal, so a license edit stays a one-row change in the reference table.
    """
    src = build_pv_source_frame()
    return str(src.loc[src["source"] == SOURCE_MIT, "license"].iloc[0])


def assert_redistributable_only(ec_pv_df: pd.DataFrame) -> None:
    """Assert no ``redistributable = false`` / non-MIT row is present (D030, guard 1/3).

    The source view ``ec_pv_redistributable`` already wraps ``pv_redistributable``
    (``WHERE redistributable``, D017), so this can only fail on a regression — which is
    exactly when a licensing guard must fail loud rather than trust the upstream. A
    getter MIT does not cover has NULL PV (``source``/``redistributable`` NULL), which
    is fine — an honest D005 gap, not a non-redistributable row; only an explicit
    ``False`` or a non-MIT ``source`` is a violation.
    """
    if "redistributable" in ec_pv_df.columns:
        bad = ec_pv_df["redistributable"] == False  # noqa: E712 — NULL must NOT match
        if bool(bad.any()):
            # ``candidate_slug`` is not minted until after this guard, so report the
            # raw canonical key columns that exist on the source frame here.
            cols = ["year", "state", "candidate"]
            raise SnapshotError(
                "redistributable=false row(s) reached the snapshot build — the "
                "redistributable-only surface (D030) was violated upstream: "
                f"{ec_pv_df.loc[bad, cols].head().values.tolist()}"
            )
    non_mit = ec_pv_df["source"].dropna().ne(SOURCE_MIT)
    if bool(non_mit.any()):
        offenders = sorted(ec_pv_df["source"].dropna()[non_mit].unique())
        raise SnapshotError(
            f"non-MIT source(s) {offenders} reached the redistributable snapshot "
            "(D016/D030) — only MIT is redistributable."
        )


def add_candidate_slug(ec_pv_df: pd.DataFrame) -> pd.DataFrame:
    """Return ``ec_pv_df`` with a ``candidate_slug`` column, failing on a collision.

    The slug is the durable **public** candidate id (D006 / ``docs/canonical-keys.md`` —
    ``candidate_id`` is an internal surrogate that must never leave the warehouse). It
    is derived deterministically from the canonical ``candidate`` name via
    :func:`usvote.slug.candidate_slug`. A **same-name collision** (two distinct
    canonical names mapping to one slug) is the known residual documented in
    ``docs/canonical-keys.md``; it would silently merge two people on the API surface,
    so it raises here rather than being written.
    """
    out = ec_pv_df.copy()
    out["candidate_slug"] = out["candidate"].map(candidate_slug)
    name_to_slug = out[["candidate", "candidate_slug"]].drop_duplicates()
    collisions = name_to_slug[name_to_slug["candidate_slug"].duplicated(keep=False)]
    if not collisions.empty:
        grouped = (
            collisions.groupby("candidate_slug")["candidate"].apply(list).to_dict()
        )
        raise SnapshotError(
            "candidate slug collision — two canonical names share one slug (the "
            f"docs/canonical-keys.md same-name residual): {grouped}"
        )
    empty = out.loc[out["candidate_slug"] == "", "candidate"].unique().tolist()
    if empty:
        raise SnapshotError(f"candidate name(s) produced an empty slug: {empty}")
    return out


def _covered_years(ec_pv_df: pd.DataFrame) -> list[int]:
    """The years with any redistributable PV — the snapshot's coverage window.

    ``ec_pv_redistributable`` is EC-**left**, so it carries every EC state row from 1824
    on with PV attached only where MIT covers it. The public surface is the
    redistributable window (D005/D016): the years that actually have PV. Pre-1976 years
    (all-NULL PV) are honestly absent — the point of the surface, not a bug.
    """
    with_pv = ec_pv_df.loc[ec_pv_df["candidate_votes"].notna(), "year"]
    return sorted(int(y) for y in with_pv.unique())


def build_national_rollup(data_df: pd.DataFrame) -> pd.DataFrame:
    """Precompute the per-``(year, candidate_slug)`` national roll-up (#97's summary).

    - ``national_electoral_votes`` — the view's window sum, constant per candidate-year,
      so ``first`` is exact.
    - ``national_pv_votes`` — ``sum(candidate_votes)`` over the candidate's state rows,
      with ``min_count=1`` so a getter with **no** PV stays NULL (honest), not a fake 0.
    - ``national_pv_denominator`` — the year's total votes cast: each state's
      ``state_total_votes`` counted **once** then summed. This pins to MIT's *provided*
      per-state denominator, never a re-sum of candidate rows (D017). Single-source
      (MIT) window, so there is no cross-source denominator ambiguity to reconcile.

    The per-state total is taken as the **non-null** ``state_total_votes`` for each
    ``(year, state)`` (``max`` skips NA), *not* an arbitrary deduped row: MIT broadcasts
    the same per-state denominator onto every candidate row in the state, but a no-PV
    getter (a faithless elector) carries a NULL ``state_total_votes``. A plain
    ``drop_duplicates(["year", "state"])`` keeps the first row in ``(year, state,
    candidate_slug)`` order, which is that NULL row whenever the getter's slug sorts
    first — silently dropping the whole state from the national denominator.
    """
    per_candidate = (
        data_df.groupby(["year", "candidate_slug"], as_index=False)
        .agg(
            candidate=("candidate", "first"),
            party=("party", "first"),
            national_electoral_votes=("national_electoral_votes", "first"),
            president_electoral_rank=("president_electoral_rank", "first"),
            took_office=("took_office", "first"),
            national_pv_votes=("candidate_votes", lambda s: s.sum(min_count=1)),
        )
    )
    per_state = data_df.groupby(["year", "state"], as_index=False)[
        "state_total_votes"
    ].max()
    denom = (
        per_state.groupby("year", as_index=False)["state_total_votes"]
        .sum(min_count=1)
        .rename(columns={"state_total_votes": "national_pv_denominator"})
    )
    rollup = per_candidate.merge(denom, on="year", how="left")
    return rollup[list(ROLLUP_COLUMNS)]


def _to_int64(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Cast ``columns`` to nullable ``Int64`` (LEFT-JOIN floats/NaN → clean ints/NA)."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = out[col].astype("Int64")
    return out


def _rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    """DataFrame → native-Python row tuples for :meth:`sqlite3.executemany`.

    Mirrors the NaN/NA → ``None`` + numpy-unbox normalization the DB write boundary does
    (:func:`usvote.db._df_to_sql_rows`); sqlite3 rejects pandas ``NA`` / numpy scalars
    just as psycopg2 does. Kept local (a few lines) rather than importing that module's
    private helper.
    """
    return [
        tuple(
            None if pd.isna(v) else v.item() if isinstance(v, np.generic) else v
            for v in row
        )
        for row in df.itertuples(index=False, name=None)
    ]


def _content_hash(data_df: pd.DataFrame) -> str:
    """SHA-256 of the ``ec_pv`` rows (deterministic order) + the schema version (D028).

    The build timestamp is *not* mixed in — identical warehouse data must yield an
    identical version so the ETag (E8-S2) is content-addressed and the build is
    reproducible. Rows are serialized field-by-field with control-char separators that
    cannot occur in the data, after the integer cast so numeric formatting is stable.
    """
    ordered = data_df.sort_values(list(_ORDER_BY), kind="stable")
    h = hashlib.sha256()
    h.update(f"schema={SNAPSHOT_SCHEMA_VERSION}\x1e".encode())
    for row in _rows(ordered[list(DATA_COLUMNS)]):
        h.update("\x1f".join("" if v is None else str(v) for v in row).encode())
        h.update(b"\x1e")
    return h.hexdigest()


def build_snapshot(
    ec_pv_df: pd.DataFrame,
    out_path: str,
    *,
    build_timestamp: datetime | None = None,
) -> SnapshotMeta:
    """Build the SQLite snapshot from an ``ec_pv_redistributable``-shaped frame.

    ``ec_pv_df`` is the view frame (:data:`usvote.join.EC_PV_COLUMNS`) enriched with
    ``state_usps`` — exactly what :func:`read_redistributable` produces. The pure core,
    unit-tested offline from a synthetic frame (no DB). Steps: assert
    redistributable-only
    (D030); **restrict to the redistributable window first** (:func:`_covered_years`),
    *then* mint the candidate slug + drop ``candidate_id`` (D006) — so a slug collision
    between candidates that never ship (e.g. two pre-1976 names) can't fail a build over
    data the snapshot won't even contain; precompute the national roll-up; content-hash
    the fact rows (D028); and write the three tables to ``out_path`` atomically
    (temp file + ``os.replace``) so a partial write never leaves a corrupt snapshot.

    ``build_timestamp`` is injectable for deterministic tests; it is informational
    metadata only, never part of the version.
    """
    assert_redistributable_only(ec_pv_df)

    covered = _covered_years(ec_pv_df)
    if not covered:
        raise SnapshotError(
            "no redistributable PV rows in the source view — the snapshot would be "
            "empty; build the warehouse (run_warehouse) with MIT loaded first."
        )
    # Filter to the served window BEFORE minting/validating slugs, so slug uniqueness is
    # only enforced over candidates that actually ship (the architect-review fix).
    in_window = add_candidate_slug(ec_pv_df[ec_pv_df["year"].isin(covered)].copy())

    data_df = _to_int64(in_window, _INTEGER_COLUMNS)[list(DATA_COLUMNS)]
    data_df = data_df.sort_values(list(_ORDER_BY), kind="stable").reset_index(drop=True)
    rollup_df = _to_int64(
        build_national_rollup(data_df),
        ("national_electoral_votes", "president_electoral_rank"),
    )

    ts = build_timestamp if build_timestamp is not None else datetime.now(UTC)
    meta = SnapshotMeta(
        snapshot_version=_content_hash(data_df),
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        row_count=len(data_df),
        candidate_count=int(data_df["candidate_slug"].nunique()),
        year_min=covered[0],
        year_max=covered[-1],
        source=SOURCE_MIT,
        license=_mit_license(),
        build_timestamp=ts.isoformat(),
    )
    _write_sqlite(out_path, data_df, rollup_df, meta)
    return meta


def _write_sqlite(
    out_path: str,
    data_df: pd.DataFrame,
    rollup_df: pd.DataFrame,
    meta: SnapshotMeta,
) -> None:
    """Write the three tables to a fresh SQLite file at ``out_path``, atomically.

    Built into a temp file in the same directory then ``os.replace``-d over ``out_path``
    so a reader (or a re-run) never sees a half-written snapshot. The file is opened
    fresh each build (idempotent overwrite); the snapshot is immutable once served.
    """
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".sqlite", dir=out_dir)
    os.close(fd)
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            _create_tables(conn)
            conn.executemany(
                f"INSERT INTO {DATA_TABLE} ({','.join(DATA_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(DATA_COLUMNS))})",
                _rows(data_df),
            )
            conn.executemany(
                f"INSERT INTO {ROLLUP_TABLE} ({','.join(ROLLUP_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(ROLLUP_COLUMNS))})",
                _rows(rollup_df),
            )
            meta_cols = tuple(asdict(meta))
            conn.execute(
                f"INSERT INTO {META_TABLE} ({','.join(meta_cols)}) "
                f"VALUES ({','.join('?' * len(meta_cols))})",
                tuple(asdict(meta).values()),
            )
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp_path, out_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create the ``ec_pv`` / ``national_rollup`` / ``snapshot_meta`` tables+indexes."""
    conn.execute(
        f"CREATE TABLE {DATA_TABLE} ("
        " year INTEGER NOT NULL,"
        " state TEXT NOT NULL,"
        " state_usps TEXT NOT NULL,"
        " candidate TEXT NOT NULL,"
        " candidate_slug TEXT NOT NULL,"
        " total_electoral_votes INTEGER,"
        " president_electoral_votes INTEGER,"
        " national_electoral_votes INTEGER,"
        " president_electoral_rank INTEGER,"
        " took_office INTEGER,"
        " source TEXT,"
        " party TEXT,"
        " candidate_votes INTEGER,"
        " state_total_votes INTEGER,"
        " reliability TEXT,"
        # Canonical grain (D026): one row per (year, state, candidate_slug). A PRIMARY
        # KEY makes a join-view / slug-mapping fan-out fail loud at INSERT (matching
        # national_rollup's own PK guard and the "validation is load-bearing" rule)
        # rather than silently shipping duplicates the content hash would bless.
        " PRIMARY KEY (year, state, candidate_slug))"
    )
    # No separate year index: the (year, ...) PRIMARY KEY already serves year lookups
    # via its leftmost-prefix. state / state_usps / slug each need their own.
    conn.execute(f"CREATE INDEX idx_{DATA_TABLE}_state ON {DATA_TABLE}(state)")
    conn.execute(f"CREATE INDEX idx_{DATA_TABLE}_usps ON {DATA_TABLE}(state_usps)")
    conn.execute(
        f"CREATE INDEX idx_{DATA_TABLE}_slug ON {DATA_TABLE}(candidate_slug)"
    )
    conn.execute(
        f"CREATE TABLE {ROLLUP_TABLE} ("
        " year INTEGER NOT NULL,"
        " candidate TEXT NOT NULL,"
        " candidate_slug TEXT NOT NULL,"
        " party TEXT,"
        " national_electoral_votes INTEGER,"
        " president_electoral_rank INTEGER,"
        " took_office INTEGER,"
        " national_pv_votes INTEGER,"
        " national_pv_denominator INTEGER,"
        " PRIMARY KEY (year, candidate_slug))"
    )
    conn.execute(
        f"CREATE TABLE {META_TABLE} ("
        " snapshot_version TEXT NOT NULL,"
        " schema_version INTEGER NOT NULL,"
        " row_count INTEGER NOT NULL,"
        " candidate_count INTEGER NOT NULL,"
        " year_min INTEGER NOT NULL,"
        " year_max INTEGER NOT NULL,"
        " source TEXT NOT NULL,"
        " license TEXT NOT NULL,"
        " build_timestamp TEXT NOT NULL)"
    )


# --- live-DB read + CLI -----------------------------------------------------


def _relation_exists(dbc: DBC, schema: str, name: str) -> bool:
    """Return whether ``schema.name`` exists, via ``to_regclass`` (NULL when absent).

    The cheap, non-raising existence probe :func:`read_redistributable` uses to turn a
    missing view into a clear precondition. Kept local — the same idiom as
    :func:`usvote.join._relation_exists` and :func:`usvote.pv.load._relation_exists`, so
    ``usvote.snapshot`` does not reach into another module's private helper (the
    project's established layering convention).
    """
    got = dbc.select_query_to_df(f"SELECT to_regclass('{schema}.{name}') AS relation")
    return got["relation"].iloc[0] is not None


def read_redistributable(dbc: DBC, *, schema: str = SCHEMA) -> pd.DataFrame:
    """Read ``ec_pv_redistributable`` (+ ``state_usps``), failing loud if absent.

    Reuses the ``join.py`` view-name **constant** (no second hand-rolled SQL path to the
    view) and the shared existence probe, turning a missing view into a clear
    precondition pointing the operator at ``run_warehouse`` — not an opaque
    ``OperationalError`` deep in the read. Then left-joins ``state_usps`` from the
    ``dwh.state`` dimension (a different relation, not a second path to the view) so the
    snapshot carries a clean URL/path key for ``/v1/states/{...}`` (#97) that the view
    itself does not expose. Local Postgres is required here, at build time **only**; the
    served API never opens this connection (D028).
    """
    if not _relation_exists(dbc, schema, EC_PV_REDISTRIBUTABLE_VIEW):
        raise SnapshotError(
            f"{schema}.{EC_PV_REDISTRIBUTABLE_VIEW} does not exist — build the "
            "warehouse first (`python -m usvote all`, i.e. usvote.warehouse."
            "run_warehouse, which creates the EC<->PV join views)."
        )
    ec_pv = dbc.select_query_to_df(
        f"SELECT * FROM {schema}.{EC_PV_REDISTRIBUTABLE_VIEW}"
    )
    state_usps = dbc.select_query_to_df(
        f"SELECT state, state_usps FROM {schema}.{STATE_DIM}"
    )
    return ec_pv.merge(state_usps, on="state", how="left")


def build_snapshot_from_db(
    dbc: DBC,
    out_path: str,
    *,
    schema: str = SCHEMA,
    build_timestamp: datetime | None = None,
    close: bool = False,
) -> SnapshotMeta:
    """Read the live view and build the snapshot — the glue behind the CLI."""
    try:
        ec_pv_df = read_redistributable(dbc, schema=schema)
        return build_snapshot(ec_pv_df, out_path, build_timestamp=build_timestamp)
    finally:
        if close:
            dbc.close_connection()


def _run_build(environ: Mapping[str, str], out_override: str | None) -> int:
    import getpass

    try:
        out_path = out_override or config.snapshot_path_from_env(environ)
        db_config: dict[str, Any] = config.db_config_from_env(environ)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        dbc = DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return 1

    try:
        meta = build_snapshot_from_db(dbc, out_path, close=True)
    except SnapshotError as e:
        print(f"Snapshot build failed: {e}", file=sys.stderr)
        return 3
    print(
        f"Wrote snapshot to {out_path} "
        f"(version {meta.snapshot_version[:12]}…, {meta.row_count} rows, "
        f"{meta.candidate_count} candidates, {meta.year_min}–{meta.year_max})."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.snapshot",
        description=(
            "Build the read-only SQLite API snapshot from dwh.ec_pv_redistributable "
            "(E8-S1, D028). Requires the local warehouse at build time only."
        ),
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output snapshot path (overrides USVOTE_API_SNAPSHOT_PATH).",
    )
    args = parser.parse_args(argv)
    return _run_build(os.environ, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
