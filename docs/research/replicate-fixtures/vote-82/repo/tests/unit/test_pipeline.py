"""Unit tests for ``usvote.pipeline``.

Covers the year-set derivation and the full scrape -> parse -> transform -> load
wiring, run offline: the 2016 + 2020 Archives fixtures replay through
``fetch_from_dir``, a fake state-geo frame is injected via ``load_geo``, and the
load lands on the recording fake connection — so the end-to-end wiring #28 adds is
exercised with no network, no TIGER shapefile, and no live Postgres. The
real-database load is covered by the integration test in
``tests/integration/test_load.py``.
"""

from __future__ import annotations

import pytest

from tests._helpers import (
    FIXTURES_DIR,
    RecordingConnection,
    fake_state_geo,
    make_dbc,
    record_inserts,
)
from usvote.load import SCHEMA
from usvote.parse import ParseError
from usvote.pipeline import (
    EC_SPINE_FLOOR,
    LATEST_ELECTION_YEAR,
    UNSUPPORTED_EC_YEARS,
    ec_ingest_years,
    election_years,
    run_ec_pipeline,
)
from usvote.scrape import fetch_from_dir
from usvote.transform import TransformError

# --- election_years --------------------------------------------------------


def test_election_years_spans_1789_to_latest() -> None:
    years = election_years(2024)
    assert 1789 in years  # the lone off-cycle first election
    assert 1792 in years  # first of the every-four-years cadence
    assert 2024 in years
    assert 2021 not in years  # not an election year
    assert 1790 not in years


def test_election_years_does_not_overshoot_non_election_latest() -> None:
    # A non-election `latest` must not pull in the next cycle: the 4-year cadence
    # from 1792 stops at the last election year <= latest.
    years = election_years(2025)
    assert 2024 in years
    assert 2028 not in years
    assert max(years) == 2024


def test_election_years_defaults_to_module_latest() -> None:
    assert election_years() == election_years(LATEST_ELECTION_YEAR)
    assert max(election_years()) == LATEST_ELECTION_YEAR


def test_ec_ingest_years_applies_floor_and_reconstruction_exclusions() -> None:
    years = ec_ingest_years(2024)
    # The default ingest starts at the 1824 comparison floor (D009) ...
    assert min(years) == EC_SPINE_FLOOR == 1824
    assert 1820 not in years  # post-12A but below the floor (deferred)
    assert 1800 not in years  # pre-12th-Amendment (out of scope, D010)
    # ... 1868 and 1872 are real elections but excluded pending dedicated modeling ...
    assert election_years(2024) >= UNSUPPORTED_EC_YEARS
    assert not (UNSUPPORTED_EC_YEARS & years)
    # ... and the modern spine through the latest year is retained.
    assert {1824, 1864, 1876, 1892, 2024} <= years


# --- full pipeline wiring (offline) ----------------------------------------


def test_run_ec_pipeline_wires_all_stages_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture inserts (insert_df_into_table routes through execute_values, which
    # the recording cursor never sees) so we can assert every table was loaded.
    inserts = record_inserts(monkeypatch)

    candidates_df, state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )

    # The three warehouse frames were built and are non-empty.
    assert list(candidates_df.columns[:2]) == ["candidate_id", "name"]
    assert len(state_df) == 51
    assert {"votes_id", "year", "candidate_id"}.issubset(votes_df.columns)
    assert not votes_df.empty

    # Both fixture years flowed through to the votes fact.
    assert set(votes_df["year"]) == {2016, 2020}

    # All three tables were created and inserted, in FK order.
    assert [sql.split()[2] for sql, _ in inserts] == [
        f"{SCHEMA}.state",
        f"{SCHEMA}.candidate",
        f"{SCHEMA}.votes",
    ]


def test_run_ec_pipeline_loads_the_star_schema_in_one_transaction(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The three-table star-schema load is atomic (#84a): drop/create-schema, three
    # create-tables and three inserts all land in ONE transaction, so an interrupted
    # ``replace`` rebuild rolls back to the previous warehouse rather than a
    # dropped/half-built one. The recording connection commits once per statement's
    # ``with self.conn`` block and once per explicit ``transaction()`` commit, so a
    # wrapped load is exactly ONE commit; removing the wrapper would push it well above 1.
    record_inserts(monkeypatch)
    run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )

    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0


def test_run_ec_pipeline_pre1892_spine_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # End-to-end over the corrected pre-1892 spine years, exercising every #32 drift
    # together: <sup> footnotes, the plural <th>Totals> row, and each "Others" split
    # into named minor candidates — plus 1856 as a clean 3-way baseline.
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={1824, 1832, 1836, 1856, 1860},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    tot = votes_df[votes_df["is_total"]].merge(
        candidates_df[["candidate_id", "name"]], on="candidate_id"
    )
    ev = {
        (int(r["year"]), r["name"]): int(r["president_electoral_votes"])
        for _, r in tot.iterrows()
    }
    # Winner electoral totals per year match the historical record.
    assert ev[(1824, "Andrew Jackson")] == 99
    assert ev[(1832, "Andrew Jackson")] == 219
    assert ev[(1836, "Martin Van Buren")] == 170
    assert ev[(1856, "James Buchanan")] == 174
    assert ev[(1860, "Abraham Lincoln")] == 180
    # Every "Others" split candidate loaded with its correct total (both sides of the
    # split reconciled — a silent inner-join drop would fail assert_totals_equal_state_sum).
    assert (ev[(1824, "William H. Crawford")], ev[(1824, "Henry Clay")]) == (41, 37)
    assert (ev[(1832, "John Floyd")], ev[(1832, "William Wirt")]) == (11, 7)
    assert ev[(1836, "Hugh L. White")] == 26
    assert ev[(1836, "Willie P. Mangum")] == 11
    assert (ev[(1860, "John C. Breckinridge")], ev[(1860, "John Bell")]) == (72, 39)
    # Party label drift normalized: Jackson reads "D-R" (1824 D-R + 1832 D -> party_2),
    # not the verbose "Democratic-Republican" the 1824 page prints.
    jackson = candidates_df.set_index("name").loc["Andrew Jackson"]
    assert (jackson["party"], jackson["party_2"]) == ("D-R", "D")


@pytest.mark.parametrize(
    ("year", "exc", "match"),
    [
        # 1872: Greeley's scattered votes parse as an "Others" column with no
        # registered correction -> TransformError.
        (1872, TransformError, "no registered correction"),
        # 1868: Georgia's contested "(9)" is a non-numeric vote cell -> ParseError.
        (1868, ParseError, "un-modelled vote notation"),
    ],
)
def test_run_ec_pipeline_rejects_gated_reconstruction_year(
    recording_conn: RecordingConnection,
    monkeypatch: pytest.MonkeyPatch,
    year: int,
    exc: type[Exception],
    match: str,
) -> None:
    # Both years are excluded from the default ingest (UNSUPPORTED_EC_YEARS); an
    # explicit years={year} must fail loudly with a typed, located error rather than
    # silently loading wrong data or crashing with a bare ValueError.
    record_inserts(monkeypatch)
    with pytest.raises(exc, match=match):
        run_ec_pipeline(
            make_dbc(recording_conn),
            "unused.shp",
            replace=True,
            years={year},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )


def test_run_ec_pipeline_2024_footnoted_state_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2024 exercises the modern footnote format (a non-breaking space between a state
    # label and its <sup> marker, e.g. Oregon) plus Maine/Nebraska district splits.
    # All 538 electoral votes must reconcile: Trump 312, Harris 226 (Oregon's 8 for
    # Harris are only present if the footnoted label was not dropped).
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2024},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    tot = votes_df[votes_df["is_total"]].merge(
        candidates_df[["candidate_id", "name"]], on="candidate_id"
    )
    ev = {r["name"]: int(r["president_electoral_votes"]) for _, r in tot.iterrows()}
    assert ev == {"Donald J. Trump": 312, "Kamala D. Harris": 226}


def test_run_ec_pipeline_leaves_connection_open_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    # The caller owns the dbc; the pipeline must not close it by default.
    assert recording_conn.closed is False
