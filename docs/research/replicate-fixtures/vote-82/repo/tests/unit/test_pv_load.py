"""Unit tests for the shared PV schema + loader (``usvote.pv``).

Crafted units over the DDL the loader emits, the ``pv_id`` assignment, the boundary
shape guard, and — most load-bearing — the guard that a PV ``replace`` drops only the
``pv_votes`` table and **never** the ``dwh`` schema (which would wipe the EC spine
sharing it). All against the recording fake connection, no live Postgres; the
full-pipeline load into a real database lives in ``tests/integration/test_pv_load.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote.pv.load import (
    assert_db_provenance_coverage,
    build_pv_union,
    create_pv_views,
    load_pv_records,
    load_pv_source,
    load_pv_status,
)
from usvote.pv.schema import (
    PV_SCHEMA,
    PV_TABLE,
    RELIABILITY_VALUES,
    SHARED_PV_COLUMNS,
    PVShapeError,
    assert_pv_shape,
    build_pv_column_defs,
)
from usvote.pv.source import PV_SOURCE_SCHEMA, PV_SOURCE_TABLE, SOURCE_MIT, SOURCE_UCSB
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
    PVRosterError,
)
from usvote.pv.views import (
    PV_PREFERRED_VIEW,
    PV_REDISTRIBUTABLE_VIEW,
    PV_UCSB_VIEW,
    PVViewError,
)

# --- column definitions ----------------------------------------------------


def test_column_defs_embed_schema_in_state_fk() -> None:
    defs = {col[0]: col for col in build_pv_column_defs("mart")}
    # The only FK is state -> <schema>.state (no candidate FK — the EC candidate PK
    # is candidate_id, not the name string this shape carries).
    assert "REFERENCES mart.state" in defs["state"]
    fk_cols = [name for name, col in defs.items() if any("REFERENCES" in c for c in col)]
    assert fk_cols == ["state"]


def test_column_defs_default_to_dwh_schema() -> None:
    defs = {col[0]: col for col in build_pv_column_defs()}
    assert f"REFERENCES {PV_SCHEMA}.state" in defs["state"]


def test_column_defs_pv_id_is_db_generated_identity_pk() -> None:
    # pv_id must be a DB-assigned IDENTITY PK, not a value the loader supplies — so
    # ids stay unique across separate loads (MIT then UCSB) instead of restarting at 1.
    first = build_pv_column_defs()[0]
    assert first[0] == "pv_id"
    assert "primary key" in first
    assert "generated always as identity" in first


def test_column_defs_reliability_check_lists_the_enum() -> None:
    check = next(c for col in build_pv_column_defs() for c in col if "CHECK" in c)
    for value in RELIABILITY_VALUES:
        assert f"'{value}'" in check


def test_column_defs_carry_natural_key_unique_constraint() -> None:
    constraint = build_pv_column_defs()[-1]
    assert constraint[0] == "CONSTRAINT"
    assert f"{PV_TABLE}_natural_key" in constraint
    assert "UNIQUE" in constraint
    assert "(source, year, state, candidate)" in constraint


def test_column_defs_define_pv_id_then_shared_shape() -> None:
    # The DDL defines pv_id (DB-generated) first, then every SHARED_PV_COLUMNS column,
    # before the trailing table constraint. The loader inserts only SHARED_PV_COLUMNS —
    # pv_id is filled by the identity sequence (see the INSERT-columns test below).
    names = [col[0] for col in build_pv_column_defs()[:-1]]
    assert names == ["pv_id", *SHARED_PV_COLUMNS]


# --- assert_pv_shape (boundary guard) --------------------------------------


def _valid_frame() -> pd.DataFrame:
    """A minimal valid shared-shape frame, rows deliberately out of key order."""
    rows = [
        {
            "source": "MIT", "year": 2016, "state": "New York",
            "candidate": "Donald J. Trump", "party": "REPUBLICAN",
            "candidate_votes": 2814589, "state_total_votes": 7889703,
            "reliability": "exact",
        },
        {
            "source": "MIT", "year": 2016, "state": "New York",
            "candidate": "Hillary Clinton", "party": "DEMOCRAT",
            "candidate_votes": 4556124, "state_total_votes": 7889703,
            "reliability": "exact",
        },
        {
            "source": "MIT", "year": 2016, "state": "California",
            "candidate": "Hillary Clinton", "party": "DEMOCRAT",
            "candidate_votes": 8753788, "state_total_votes": 14181595,
            "reliability": "exact",
        },
    ]
    return pd.DataFrame(rows)[list(SHARED_PV_COLUMNS)]


def test_assert_pv_shape_accepts_valid_frame() -> None:
    assert_pv_shape(_valid_frame())  # does not raise


def test_assert_pv_shape_rejects_wrong_columns() -> None:
    bad = _valid_frame().drop(columns=["reliability"])
    with pytest.raises(PVShapeError, match="shared PV shape"):
        assert_pv_shape(bad)


def test_assert_pv_shape_rejects_reordered_columns() -> None:
    cols = list(SHARED_PV_COLUMNS)
    cols[0], cols[1] = cols[1], cols[0]
    with pytest.raises(PVShapeError, match="shared PV shape"):
        assert_pv_shape(_valid_frame()[cols])


def test_assert_pv_shape_rejects_null_natural_key() -> None:
    bad = _valid_frame()
    bad.loc[0, "candidate"] = None
    with pytest.raises(PVShapeError, match="candidate"):
        assert_pv_shape(bad)


def test_assert_pv_shape_allows_null_party() -> None:
    # party is nullable (UCSB forward-compat) — not in REQUIRED_NON_NULL.
    ok = _valid_frame()
    ok.loc[0, "party"] = None
    assert_pv_shape(ok)  # does not raise


def test_assert_pv_shape_rejects_float_vote_counts() -> None:
    # A source whose transform left candidate_votes as float64 would otherwise be
    # inserted into the integer DDL column (silent rounding / opaque psycopg2 error).
    # The shared guard must reject it — mirroring MIT's own transform.assert_shape.
    bad = _valid_frame()
    bad["candidate_votes"] = bad["candidate_votes"].astype("float64")
    with pytest.raises(PVShapeError, match="must be integer"):
        assert_pv_shape(bad)


# --- load_pv_records: ordering + insert ------------------------------------


def test_load_inserts_rows_in_natural_key_order(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    loaded = load_pv_records(make_dbc(recording_conn), _valid_frame())

    # Rows sorted by (source, year, state, candidate): California sorts before New
    # York, and within New York "Donald..." before "Hillary...". pv_id is NOT in the
    # returned frame — the database assigns it (identity), so nothing here can depend
    # on a per-call 1..n numbering.
    assert "pv_id" not in loaded.columns
    assert loaded[["state", "candidate"]].values.tolist() == [
        ["California", "Hillary Clinton"],
        ["New York", "Donald J. Trump"],
        ["New York", "Hillary Clinton"],
    ]


def test_load_insert_omits_pv_id_so_the_db_generates_it(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())

    # The INSERT column list is exactly SHARED_PV_COLUMNS — pv_id is absent, so the
    # GENERATED ALWAYS AS IDENTITY sequence fills it (a supplied pv_id would both
    # collide across loads and be rejected by the ALWAYS identity).
    (sql, _argslist) = inserts[0]
    expected_cols = ",".join(SHARED_PV_COLUMNS)
    assert sql == f"INSERT INTO {PV_SCHEMA}.{PV_TABLE} ({expected_cols}) VALUES %s"
    assert "pv_id" not in sql


# --- load_pv_records: the replace footgun ----------------------------------


def test_load_non_destructive_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())

    assert not any("DROP" in q for q in recording_conn.executed)
    assert any(
        q.startswith("CREATE SCHEMA IF NOT EXISTS") for q in recording_conn.executed
    )
    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {PV_SCHEMA}.{PV_TABLE}")
        for q in recording_conn.executed
    )


def test_load_replace_drops_only_the_table_never_the_schema(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # THE guard: a PV replace must not cascade-drop the dwh schema (which would wipe
    # the EC spine sharing it). Exactly one drop, and it is the pv_votes table.
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame(), replace=True)

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    assert drops == [f"DROP TABLE IF EXISTS {PV_SCHEMA}.{PV_TABLE} Cascade"]
    assert not any("DROP SCHEMA" in q for q in recording_conn.executed)


# --- load_pv_records: connection ownership ---------------------------------


def test_load_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame(), close=True)
    assert recording_conn.closed is True


def test_load_defaults_to_leaving_connection_open(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_records(make_dbc(recording_conn), _valid_frame())
    assert recording_conn.closed is False


# --- load_pv_status: the D024 roster loader --------------------------------


def _valid_roster() -> pd.DataFrame:
    """A minimal valid roster frame, rows deliberately out of natural-key order."""
    rows = [
        {
            "source": "UCSB", "year": 1876, "state": "South Carolina",
            "pv_status": PV_STATUS_LEGISLATURE_CHOSEN, "note": "chosen by legislature",
        },
        {
            "source": "UCSB", "year": 1876, "state": "Colorado",
            "pv_status": PV_STATUS_NOT_PARTICIPATING, "note": None,
        },
        {
            "source": "UCSB", "year": 1876, "state": "Alabama",
            "pv_status": PV_STATUS_POPULAR_VOTE, "note": None,
        },
    ]
    return pd.DataFrame(rows)[list(ROSTER_COLUMNS)]


def test_load_status_inserts_rows_in_natural_key_order(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    loaded = load_pv_status(make_dbc(recording_conn), _valid_roster())

    # Sorted by (source, year, state): Alabama, Colorado, South Carolina. status_id is
    # DB-assigned (identity), so it is absent from the returned frame.
    assert "status_id" not in loaded.columns
    assert loaded["state"].tolist() == ["Alabama", "Colorado", "South Carolina"]


def test_load_status_insert_omits_status_id_so_the_db_generates_it(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    load_pv_status(make_dbc(recording_conn), _valid_roster())

    (sql, _argslist) = inserts[0]
    expected_cols = ",".join(ROSTER_COLUMNS)
    assert sql == (
        f"INSERT INTO {ROSTER_SCHEMA}.{ROSTER_TABLE} ({expected_cols}) VALUES %s"
    )
    assert "status_id" not in sql


def test_load_status_creates_table_and_is_non_destructive_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_status(make_dbc(recording_conn), _valid_roster())

    assert not any("DROP" in q for q in recording_conn.executed)
    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {ROSTER_SCHEMA}.{ROSTER_TABLE}")
        for q in recording_conn.executed
    )


def test_load_status_does_not_create_the_schema(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Unlike load_pv_records, the roster loader does NOT re-issue CREATE SCHEMA: dwh
    # always pre-exists a roster load (the EC spine created it and the pipeline read
    # from it first), so a second CREATE SCHEMA would be a redundant round-trip.
    record_inserts(monkeypatch)
    load_pv_status(make_dbc(recording_conn), _valid_roster())
    assert not any(q.startswith("CREATE SCHEMA") for q in recording_conn.executed)


def test_load_status_replace_drops_only_the_table_never_the_schema(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same guard as the fact loader: a roster replace must not cascade-drop the dwh
    # schema (wiping the EC spine). Exactly one drop, and it is the roster table.
    record_inserts(monkeypatch)
    load_pv_status(make_dbc(recording_conn), _valid_roster(), replace=True)

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    assert drops == [f"DROP TABLE IF EXISTS {ROSTER_SCHEMA}.{ROSTER_TABLE} Cascade"]
    assert not any("DROP SCHEMA" in q for q in recording_conn.executed)


def test_load_status_guards_shape_before_any_ddl(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A malformed roster must fail loudly at the boundary, not mid-insert. A null state
    # in the natural key trips assert_roster_shape before any CREATE/INSERT is issued.
    record_inserts(monkeypatch)
    bad = _valid_roster()
    bad.loc[0, "state"] = None
    with pytest.raises(PVRosterError):
        load_pv_status(make_dbc(recording_conn), bad)
    assert not any(q.startswith("CREATE TABLE") for q in recording_conn.executed)


def test_load_status_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_status(make_dbc(recording_conn), _valid_roster(), close=True)
    assert recording_conn.closed is True


# --- load_pv_source: the D017 reference-table seed (#68) --------------------


def test_load_source_creates_and_seeds_the_reference_table(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    seeded = load_pv_source(make_dbc(recording_conn))

    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {PV_SOURCE_SCHEMA}.{PV_SOURCE_TABLE}")
        for q in recording_conn.executed
    )
    # The two D017 rows are inserted; the seed IS the contract (no frame is passed in).
    (sql, argslist) = inserts[0]
    assert f"INSERT INTO {PV_SOURCE_SCHEMA}.{PV_SOURCE_TABLE}" in sql
    assert set(seeded["source"]) == {SOURCE_MIT, SOURCE_UCSB}
    assert len(argslist) == 2


def test_load_source_non_destructive_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    load_pv_source(make_dbc(recording_conn))
    assert not any("DROP" in q for q in recording_conn.executed)


def test_load_source_replace_drops_only_the_table_never_the_schema(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same footgun guard as the fact/roster loaders: a reference-table replace must not
    # cascade-drop the dwh schema (wiping the EC spine). Exactly one drop, the table.
    record_inserts(monkeypatch)
    load_pv_source(make_dbc(recording_conn), replace=True)

    drops = [q for q in recording_conn.executed if q.startswith("DROP")]
    assert drops == [
        f"DROP TABLE IF EXISTS {PV_SOURCE_SCHEMA}.{PV_SOURCE_TABLE} Cascade"
    ]
    assert not any("DROP SCHEMA" in q for q in recording_conn.executed)


# --- create_pv_views: the three resolution views (#68) ---------------------


def test_create_views_issues_three_create_or_replace_views(
    recording_conn: RecordingConnection,
) -> None:
    create_pv_views(make_dbc(recording_conn))
    views = [q for q in recording_conn.executed if "VIEW" in q]
    assert len(views) == 3
    # Default replace=True → non-destructive CREATE OR REPLACE, and never a schema drop.
    assert all(q.startswith("CREATE OR REPLACE VIEW") for q in views)
    for name in (PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW, PV_UCSB_VIEW):
        assert any(f"{PV_SCHEMA}.{name} AS" in q for q in views)
    assert not any("DROP" in q for q in recording_conn.executed)


def test_create_views_plain_create_when_not_replacing(
    recording_conn: RecordingConnection,
) -> None:
    create_pv_views(make_dbc(recording_conn), replace=False)
    views = [q for q in recording_conn.executed if "VIEW" in q]
    assert len(views) == 3
    assert all(q.startswith("CREATE VIEW") for q in views)


# --- build_pv_union: the #68 orchestrator ----------------------------------
#
# build_pv_union runs two live DB-side guards (pv_votes exists; every source covered by
# pv_source) via select_query_to_df, which the recording fake cannot serve — so these
# tests stub it. `_covered_db_reads` is the happy path: pv_votes exists and its sources
# {MIT, UCSB} are all in pv_source.


def _covered_db_reads(query: str, close: bool = False) -> pd.DataFrame:
    if "to_regclass" in query:
        return pd.DataFrame({"relation": [f"{PV_SCHEMA}.{PV_TABLE}"]})
    if PV_SOURCE_TABLE in query:  # SELECT source FROM dwh.pv_source
        return pd.DataFrame({"source": [SOURCE_MIT, SOURCE_UCSB]})
    return pd.DataFrame({"source": [SOURCE_MIT, SOURCE_UCSB]})  # DISTINCT pv_votes.source


def test_build_union_seeds_source_then_creates_views(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The single #68 entry point: seed pv_source, then CREATE OR REPLACE the three
    # views. It writes NO new fact table — the raw union is the already-loaded pv_votes.
    record_inserts(monkeypatch)
    dbc = make_dbc(recording_conn)
    monkeypatch.setattr(dbc, "select_query_to_df", _covered_db_reads)
    build_pv_union(dbc)

    executed = recording_conn.executed
    assert any(
        f"{PV_SOURCE_TABLE}" in q and q.startswith("CREATE TABLE") for q in executed
    )
    view_stmts = [q for q in executed if "VIEW" in q]
    assert len(view_stmts) == 3
    # pv_source is created before the views that join it.
    src_idx = next(
        i for i, q in enumerate(executed) if PV_SOURCE_TABLE in q and "CREATE TABLE" in q
    )
    first_view_idx = next(i for i, q in enumerate(executed) if "VIEW" in q)
    assert src_idx < first_view_idx
    # No new pv_votes fact write, and never a schema drop (EC spine survives).
    assert not any(
        f"CREATE TABLE IF NOT EXISTS {PV_SCHEMA}.{PV_TABLE}" in q for q in executed
    )
    assert not any("DROP SCHEMA" in q for q in executed)


def test_build_union_close_flag_closes_connection(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    dbc = make_dbc(recording_conn)
    monkeypatch.setattr(dbc, "select_query_to_df", _covered_db_reads)
    build_pv_union(dbc, close=True)
    assert recording_conn.closed is True


def test_build_union_raises_when_pv_votes_absent(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #3: a union built before any PV source load must raise a clear precondition error
    # (not an opaque UndefinedTable inside CREATE VIEW), and create nothing.
    record_inserts(monkeypatch)
    dbc = make_dbc(recording_conn)

    def _missing_pv_votes(query: str, close: bool = False) -> pd.DataFrame:
        if "to_regclass" in query:
            return pd.DataFrame({"relation": [None]})
        return pd.DataFrame({"source": []})

    monkeypatch.setattr(dbc, "select_query_to_df", _missing_pv_votes)
    with pytest.raises(PVViewError, match="does not exist"):
        build_pv_union(dbc)
    # Bailed before seeding pv_source or creating any view.
    assert not any("CREATE" in q for q in recording_conn.executed)


def test_build_union_raises_on_uncovered_source(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #1: a pv_votes source with no pv_source row would be silently dropped by the
    # inner-join views — build_pv_union must fail loudly, after seeding pv_source but
    # before creating the views.
    record_inserts(monkeypatch)
    dbc = make_dbc(recording_conn)

    def _uncovered(query: str, close: bool = False) -> pd.DataFrame:
        if "to_regclass" in query:
            return pd.DataFrame({"relation": [f"{PV_SCHEMA}.{PV_TABLE}"]})
        if PV_SOURCE_TABLE in query:
            return pd.DataFrame({"source": [SOURCE_MIT, SOURCE_UCSB]})
        return pd.DataFrame({"source": [SOURCE_MIT, "ICPSR"]})  # ICPSR uncovered

    monkeypatch.setattr(dbc, "select_query_to_df", _uncovered)
    with pytest.raises(PVViewError, match="no pv_source row"):
        build_pv_union(dbc)
    assert not any("VIEW" in q for q in recording_conn.executed)


def test_assert_db_provenance_coverage_passes_when_covered(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    dbc = make_dbc(recording_conn)
    monkeypatch.setattr(dbc, "select_query_to_df", _covered_db_reads)
    assert_db_provenance_coverage(dbc)  # does not raise
