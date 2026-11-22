"""Unit tests for the UCSB pipeline wiring (``usvote.ucsb.pipeline``).

Offline. The individual stages are tested against real markup elsewhere
(``test_ucsb_parse``/``test_ucsb_transform``/``test_ucsb_reconcile``, plus the real
corpus and the ``#37`` live-DB integration test). What is *only* observable here is the
orchestration this module owns: that the six seams are wired in order, that ``years`` is
resolved once and threaded to every stage, and — the two-table load's whole risk — that
both PV tables are created and the roster is loaded **before** the facts, under one
``replace`` flag.

The upstream stages (snapshot read, parse, the two spine reads, transform, reconcile)
are stubbed so no network/DB/markup is needed; the two real loaders
(:func:`usvote.pv.load.load_pv_status` / :func:`~usvote.pv.load.load_pv_records`) run
against the recording fake connection, so the CREATE/INSERT SQL they emit is genuine.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, make_dbc, record_inserts
from usvote.pv.schema import PV_SCHEMA, PV_TABLE, SHARED_PV_COLUMNS
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
)
from usvote.ucsb import pipeline as pipeline_mod
from usvote.ucsb.pipeline import run_ucsb_pipeline
from usvote.ucsb.transform import ucsb_ingest_years


def _pv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "source": "UCSB", "year": 2016, "state": "Ohio",
            "candidate": "Donald J. Trump", "party": None,
            "candidate_votes": 100, "state_total_votes": 200, "reliability": "exact",
        }]
    )[list(SHARED_PV_COLUMNS)]


def _roster_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "source": "UCSB", "year": 2016, "state": "Ohio",
            "pv_status": PV_STATUS_POPULAR_VOTE, "note": None,
        }]
    )[list(ROSTER_COLUMNS)]


class SeamSpy:
    """Stubs the six upstream seams on ``usvote.ucsb.pipeline`` and records their args.

    Each stub returns a canned value and records the ``years`` (or positional args) it
    was called with, so a test can assert the pipeline resolved ``years`` once and
    threaded the same value everywhere.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.years_seen: dict[str, Any] = {}
        pv, roster = _pv_frame(), _roster_frame()

        def snapshot(html_dir: Any, *, years: Any, environ: Any = None) -> dict[int, str]:
            self.years_seen["snapshot"] = years
            return {2016: "<html/>"}

        def parse(html_by_year: Any) -> list[Any]:
            return []

        def participation(dbc: Any, *, years: Any = None) -> pd.DataFrame:
            self.years_seen["participation"] = years
            return pd.DataFrame()

        def transform(parsed: Any, ec_part: Any, *, years: Any = None) -> Any:
            self.years_seen["transform"] = years
            return pv.copy(), roster.copy()

        def getters(dbc: Any, *, years: Any = None) -> pd.DataFrame:
            self.years_seen["getters"] = years
            return pd.DataFrame()

        def reconcile(pv_df: Any, roster_df: Any, ec_g: Any, *, years: Any = None) -> Any:
            self.years_seen["reconcile"] = years
            return pv.copy()

        monkeypatch.setattr(pipeline_mod, "read_snapshot_html", snapshot)
        monkeypatch.setattr(pipeline_mod, "parse_election_years", parse)
        monkeypatch.setattr(pipeline_mod, "read_ec_participation", participation)
        monkeypatch.setattr(pipeline_mod, "transform_ucsb", transform)
        monkeypatch.setattr(pipeline_mod, "read_ec_getters", getters)
        monkeypatch.setattr(pipeline_mod, "reconcile_ucsb", reconcile)


def test_pipeline_creates_both_pv_tables(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016})

    creates = [q for q in recording_conn.executed if q.startswith("CREATE TABLE")]
    assert any(f"{ROSTER_SCHEMA}.{ROSTER_TABLE}" in q for q in creates)
    assert any(f"{PV_SCHEMA}.{PV_TABLE}" in q for q in creates)


def test_pipeline_loads_roster_before_facts(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The load order that minimizes the blast radius of the non-atomic two-table write:
    # the roster (FK-safe, obviously-incomplete-if-interrupted) lands first.
    SeamSpy(monkeypatch)
    inserts = record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016})

    targets = [sql.split()[2] for sql, _ in inserts]
    assert targets == [
        f"{ROSTER_SCHEMA}.{ROSTER_TABLE}",
        f"{PV_SCHEMA}.{PV_TABLE}",
    ]


def test_pipeline_loads_both_tables_in_one_transaction(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The #84a headline guard: the roster + fact writes are ONE transaction, so the D024
    # two-way invariant can never be left half-written. The recording connection commits
    # once per ``with self.conn`` block (per statement) and once per explicit
    # ``transaction()`` commit, so a wrapped load is exactly ONE commit; drop the
    # ``with dbc.transaction():`` and the create/insert statements would each commit,
    # pushing this well above 1. That is the regression this test exists to catch.
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016})

    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0


def test_pipeline_returns_facts_then_roster(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    pv, roster = run_ucsb_pipeline(make_dbc(recording_conn), years={2016})

    assert list(pv.columns) == list(SHARED_PV_COLUMNS)
    assert list(roster.columns) == list(ROSTER_COLUMNS)


def test_pipeline_resolves_years_once_and_threads_it(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016})

    # Every stage saw the same frozenset — not None, not a re-resolved default.
    assert set(spy.years_seen.values()) == {frozenset({2016})}


def test_pipeline_default_years_is_the_ucsb_ingest_scope(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn))

    assert spy.years_seen["snapshot"] == frozenset(ucsb_ingest_years())


def test_pipeline_forwards_replace_to_both_tables(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016}, replace=True)

    drops = [q for q in recording_conn.executed if q.startswith("DROP TABLE")]
    assert any(ROSTER_TABLE in q for q in drops)
    assert any(PV_TABLE in q for q in drops)
    # Never a schema-level drop — that would wipe the EC spine sharing dwh.
    assert not any("DROP SCHEMA" in q for q in recording_conn.executed)


def test_pipeline_close_closes_connection_after_the_last_load(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016}, close=True)
    assert recording_conn.closed is True


def test_pipeline_default_leaves_connection_open(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    SeamSpy(monkeypatch)
    record_inserts(monkeypatch)
    run_ucsb_pipeline(make_dbc(recording_conn), years={2016})
    assert recording_conn.closed is False
