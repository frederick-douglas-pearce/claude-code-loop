"""Unit tests for ``usvote.db.DBC``.

These cover SQL-string construction and control flow (close/replace flags, the
empty-DataFrame guard, connect-failure) without a live Postgres — the recording
fake connection from ``tests._helpers`` captures executed SQL. The live-database
round-trip lives in ``tests/integration/test_db.py``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import psycopg2 as pg
import pytest

import usvote.db as db_module
from tests._helpers import RecordingConnection, make_dbc
from usvote.db import DBC, DBConnectionError

# --- connection handling ---------------------------------------------------


def test_init_passes_config_to_connect() -> None:
    captured: dict[str, object] = {}

    def fake_connect(**kwargs: object) -> RecordingConnection:
        captured.update(kwargs)
        return RecordingConnection()

    config = {"host": "localhost", "port": 5432, "dbname": "elections"}
    dbc = DBC(config, connect=fake_connect)

    assert captured == config
    assert dbc.config == config


def test_connect_failure_raises_typed_exception() -> None:
    def boom(**_: object) -> RecordingConnection:
        raise pg.DatabaseError("no server")

    with pytest.raises(DBConnectionError):
        DBC({"dbname": "x"}, connect=boom)


def test_close_connection(recording_conn: RecordingConnection) -> None:
    dbc = make_dbc(recording_conn)
    dbc.close_connection()
    assert recording_conn.closed is True


def test_close_flag_closes_after_query(recording_conn: RecordingConnection) -> None:
    dbc = make_dbc(recording_conn)
    dbc.execute_query("SELECT 1", close=True)
    assert recording_conn.closed is True


def test_no_close_flag_leaves_connection_open(
    recording_conn: RecordingConnection,
) -> None:
    dbc = make_dbc(recording_conn)
    dbc.execute_query("SELECT 1")
    assert recording_conn.closed is False


# --- schema DDL ------------------------------------------------------------


def test_create_schema_sql(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).create_schema("dwh")
    assert recording_conn.executed == ["CREATE SCHEMA IF NOT EXISTS dwh"]


def test_create_schema_replace_drops_then_creates(
    recording_conn: RecordingConnection,
) -> None:
    make_dbc(recording_conn).create_schema("dwh", replace=True)
    assert recording_conn.executed == [
        "DROP SCHEMA IF EXISTS dwh Cascade",
        "CREATE SCHEMA IF NOT EXISTS dwh",
    ]


def test_delete_schema_default_option(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).delete_schema("dwh")
    assert recording_conn.executed == ["DROP SCHEMA IF EXISTS dwh Restrict"]


# --- table DDL -------------------------------------------------------------


def test_create_table_joins_column_defs(recording_conn: RecordingConnection) -> None:
    columns = [("state", "text"), ("geoid", "integer"), ("area", "double precision")]
    make_dbc(recording_conn).create_table("dwh", "state", columns)
    assert recording_conn.executed == [
        "CREATE TABLE IF NOT EXISTS dwh.state "
        "(state text, geoid integer, area double precision)"
    ]


def test_create_table_replace_drops_then_creates(
    recording_conn: RecordingConnection,
) -> None:
    make_dbc(recording_conn).create_table(
        "dwh", "state", [("state", "text")], replace=True
    )
    assert recording_conn.executed == [
        "DROP TABLE IF EXISTS dwh.state Cascade",
        "CREATE TABLE IF NOT EXISTS dwh.state (state text)",
    ]


def test_delete_table_default_option(recording_conn: RecordingConnection) -> None:
    make_dbc(recording_conn).delete_table("dwh", "state")
    assert recording_conn.executed == ["DROP TABLE IF EXISTS dwh.state Restrict"]


def test_create_view_default_is_plain_create(
    recording_conn: RecordingConnection,
) -> None:
    make_dbc(recording_conn).create_view("dwh", "pv_ucsb", "SELECT 1")
    assert recording_conn.executed == ["CREATE VIEW dwh.pv_ucsb AS SELECT 1"]


def test_create_view_replace_is_create_or_replace_not_a_drop(
    recording_conn: RecordingConnection,
) -> None:
    # replace=True must be non-destructive (CREATE OR REPLACE VIEW) — no DROP, so
    # dependent views survive. This is why the PV view loader can default replace=True.
    make_dbc(recording_conn).create_view("dwh", "pv_ucsb", "SELECT 1", replace=True)
    assert recording_conn.executed == [
        "CREATE OR REPLACE VIEW dwh.pv_ucsb AS SELECT 1"
    ]
    assert not any("DROP" in q for q in recording_conn.executed)


def test_copy_csv_with_and_without_header(
    recording_conn: RecordingConnection,
) -> None:
    dbc = make_dbc(recording_conn)
    dbc.copy_csv_to_table("dwh", "state", "/tmp/s.csv", header=True)
    dbc.copy_csv_to_table("dwh", "state", "/tmp/s.csv", header=False)
    assert recording_conn.executed == [
        "COPY dwh.state FROM '/tmp/s.csv' DELIMITER ',' CSV HEADER",
        "COPY dwh.state FROM '/tmp/s.csv' DELIMITER ','",
    ]


# --- insert_df_into_table --------------------------------------------------


def test_insert_df_builds_columns_and_stmt(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, str, Any]] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        calls.append((cur, sql, argslist))

    # Patch at the lookup site (usvote.db), not psycopg2.extras.
    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)

    df = pd.DataFrame({"year": [2020], "candidate_id": [1]})
    make_dbc(recording_conn).insert_df_into_table("dwh", "votes", df)

    assert len(calls) == 1
    _, sql, argslist = calls[0]
    assert sql == "INSERT INTO dwh.votes (year,candidate_id) VALUES %s"
    # Rows are native-Python tuples (not numpy) handed to execute_values.
    assert list(argslist[0]) == [2020, 1]
    assert all(type(v) is int for v in argslist[0])


def test_insert_normalizes_nan_and_numpy_scalars() -> None:
    # The DataFrame->SQL conversion must unbox numpy scalars (psycopg2 can't adapt
    # numpy.int64) and turn every null-like value into None (NOT a literal NaN,
    # which Postgres rejects on NOT NULL / FK columns). Regression for the two
    # failures the live-Postgres integration test surfaced.
    df = pd.DataFrame(
        {
            "n": [1, 2],  # int64 -> python int
            "flag": [True, False],  # bool -> python bool
            "name": pd.array(["Trump", None], dtype="string"),  # StringDtype NA
            "state_2": [float("nan"), "Ohio"],  # float NaN -> None
        }
    )
    rows = db_module._df_to_sql_rows(df)

    assert rows == [(1, True, "Trump", None), (2, False, None, "Ohio")]
    # Every non-None scalar is a builtin Python type, not a numpy scalar.
    for row in rows:
        for v in row:
            assert v is None or type(v).__module__ == "builtins"


def test_insert_empty_df_is_guarded(
    recording_conn: RecordingConnection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def fake_execute_values(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)

    make_dbc(recording_conn).insert_df_into_table("dwh", "votes", pd.DataFrame())

    assert called is False
    assert recording_conn.executed == []  # no SQL built for an empty frame
    assert "empty" in capsys.readouterr().out.lower()


# --- select_query_to_df ----------------------------------------------------


def test_select_query_to_df_delegates_to_read_sql(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = pd.DataFrame({"n": [1]})
    seen: dict[str, object] = {}

    def fake_read_sql(query: str, conn: object) -> pd.DataFrame:
        seen["query"] = query
        seen["conn"] = conn
        return sentinel

    monkeypatch.setattr(db_module.pd, "read_sql", fake_read_sql)

    dbc = make_dbc(recording_conn)
    result = dbc.select_query_to_df("SELECT n FROM t")

    assert result is sentinel
    assert seen["query"] == "SELECT n FROM t"
    assert seen["conn"] is recording_conn


# --- transaction() (#84a) --------------------------------------------------


def test_statements_commit_per_statement_outside_a_transaction(
    recording_conn: RecordingConnection,
) -> None:
    # Baseline the transaction tests contrast against: with no open transaction each
    # statement commits on its own (psycopg2's ``with self.conn`` semantics), so three
    # statements are three commits. The refactor must preserve this.
    dbc = make_dbc(recording_conn)
    dbc.execute_query("INSERT 1")
    dbc.execute_query("INSERT 2")
    dbc.execute_query("INSERT 3")
    assert recording_conn.commits == 3
    assert recording_conn.rollbacks == 0


def test_transaction_commits_once_spanning_every_statement(
    recording_conn: RecordingConnection,
) -> None:
    # The core guarantee: N statements inside the block yield exactly ONE commit (not N),
    # so the writes land all-or-nothing. This is what makes the UCSB roster+fact pair
    # atomic.
    dbc = make_dbc(recording_conn)
    with dbc.transaction():
        dbc.execute_query("INSERT roster")
        dbc.execute_query("INSERT facts")
    assert recording_conn.executed == ["INSERT roster", "INSERT facts"]
    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0
    assert dbc._in_txn is False  # flag cleared on the way out


def test_transaction_rolls_back_and_re_raises_on_exception(
    recording_conn: RecordingConnection,
) -> None:
    # An exception mid-block rolls the whole thing back (one rollback, zero commits) and
    # propagates — the first statement's write does not survive the second's failure.
    dbc = make_dbc(recording_conn)
    with pytest.raises(ValueError, match="boom"), dbc.transaction():
        dbc.execute_query("INSERT roster")
        raise ValueError("boom")
    assert recording_conn.executed == ["INSERT roster"]
    assert recording_conn.commits == 0
    assert recording_conn.rollbacks == 1
    assert dbc._in_txn is False


def test_insert_df_participates_in_the_open_transaction(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # insert_df_into_table routes through the same chokepoint as execute_query, so it too
    # is suppressed inside a transaction: two inserts, one commit.
    monkeypatch.setattr(db_module, "execute_values", lambda *_, **__: None)
    dbc = make_dbc(recording_conn)
    df = pd.DataFrame({"a": [1]})
    with dbc.transaction():
        dbc.insert_df_into_table("dwh", "pv_state_status", df)
        dbc.insert_df_into_table("dwh", "pv_votes", df)
    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0


def test_transaction_is_not_re_entrant(
    recording_conn: RecordingConnection,
) -> None:
    # Single-level by design: a nested open is a bug (it would commit the inner half
    # early and make the outer block non-atomic), so it raises. The RuntimeError
    # propagating through the outer block rolls the outer transaction back.
    dbc = make_dbc(recording_conn)
    with (
        pytest.raises(RuntimeError, match="not re-entrant"),
        dbc.transaction(),
        dbc.transaction(),
    ):
        pass
    assert recording_conn.commits == 0
    assert recording_conn.rollbacks == 1
    assert dbc._in_txn is False


def test_transaction_rollback_failure_does_not_mask_the_original_error(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If rollback() itself fails — a broken connection is a plausible cause of BOTH the
    # body error and the rollback failure — the original exception must still propagate,
    # not the rollback's. Otherwise the traceback blames rollback and hides the root
    # cause.
    def boom_rollback() -> None:
        raise RuntimeError("connection is broken")

    monkeypatch.setattr(recording_conn, "rollback", boom_rollback)
    dbc = make_dbc(recording_conn)
    with pytest.raises(ValueError, match="original"), dbc.transaction():
        raise ValueError("original")
    assert dbc._in_txn is False  # flag still cleared despite the rollback failure


def test_transaction_requires_autocommit_off(
    recording_conn: RecordingConnection,
) -> None:
    # A transaction is meaningless under autocommit (each statement commits on its own),
    # so the block refuses to run rather than give a false atomicity guarantee. It fails
    # before opening anything: no commit, no rollback, flag untouched.
    recording_conn.autocommit = True
    dbc = make_dbc(recording_conn)
    with pytest.raises(RuntimeError, match="autocommit"), dbc.transaction():
        dbc.execute_query("INSERT roster")
    assert recording_conn.executed == []
    assert recording_conn.commits == 0
    assert recording_conn.rollbacks == 0
    assert dbc._in_txn is False


def test_transaction_flag_resets_so_the_dbc_is_reusable_after_a_failure(
    recording_conn: RecordingConnection,
) -> None:
    # The ``finally`` clears ``_in_txn`` even when the block raised, so a later
    # transaction on the same DBC is not wedged shut.
    dbc = make_dbc(recording_conn)
    with pytest.raises(ValueError), dbc.transaction():
        raise ValueError("first")
    assert dbc._in_txn is False

    with dbc.transaction():
        dbc.execute_query("SELECT 1")
    assert recording_conn.executed == ["SELECT 1"]
    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 1  # the first block's rollback
