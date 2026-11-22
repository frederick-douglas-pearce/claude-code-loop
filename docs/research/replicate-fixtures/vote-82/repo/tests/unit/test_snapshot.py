"""Unit tests for the read-only SQLite snapshot build (``usvote.snapshot``, E8-S1 #95).

All offline (no live DB): the pure builder :func:`usvote.snapshot.build_snapshot` takes an
``ec_pv_redistributable``-shaped frame, so the whole serving contract — table shape,
content-hash version, candidate slug, ``candidate_id`` drop, national roll-up, coverage
window, and the redistributable-only guard — is exercised from a small **synthetic** frame
(D022 posture; this data is EC/MIT/CC0 and carries no UCSB restriction). Any build from
real Postgres is ``@pytest.mark.integration`` and lives elsewhere.

The synthetic scenario (``_ec_pv_frame``) deliberately mixes:
- **1972** — a pre-window year with all-NULL PV, to prove it is filtered out (D005/D016).
- **2016** — an "EC winner ≠ PV winner"-shaped year with a **faithless getter** (EC vote,
  no MIT PV), to prove an in-window NULL-PV getter survives with NULL national PV.
- **2020** — an ordinary two-candidate year.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from usvote.join import EC_PV_COLUMNS
from usvote.slug import candidate_slug
from usvote.snapshot import (
    DATA_COLUMNS,
    DATA_TABLE,
    META_TABLE,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotError,
    SnapshotMeta,
    add_candidate_slug,
    build_snapshot,
    read_redistributable,
)

_TS = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

#: The state->USPS enrichment read_redistributable adds from dwh.state; the synthetic
#: frame carries it directly (it is the shape build_snapshot consumes).
_USPS = {"Texas": "TX", "California": "CA", "Washington": "WA"}


def _row(
    year: int,
    state: str,
    candidate_id: int,
    candidate: str,
    president_ev: int,
    national_ev: int,
    rank: int,
    took_office: bool,
    *,
    candidate_votes: int | None,
    state_total: int | None,
    party: str | None = "DEMOCRAT",
    source: str | None = "MIT",
    reliability: str | None = "exact",
    total_ev: int = 38,
    redistributable: bool | None = True,
) -> dict:
    """One ``ec_pv_redistributable`` row. NULL PV (no MIT coverage) ⇒ NULL PV columns."""
    return {
        "year": year,
        "state": state,
        "state_usps": _USPS[state],
        "candidate_id": candidate_id,
        "candidate": candidate,
        "total_electoral_votes": total_ev,
        "president_electoral_votes": president_ev,
        "national_electoral_votes": national_ev,
        "president_electoral_rank": rank,
        "took_office": took_office,
        "source": source,
        "party": party,
        "candidate_votes": candidate_votes,
        "state_total_votes": state_total,
        "reliability": reliability,
        "redistributable": redistributable,
    }


def _ec_pv_frame() -> pd.DataFrame:
    rows = [
        # --- 1972: pre-window, all PV NULL (must be filtered out of the snapshot) ---
        _row(1972, "Texas", 6, "Richard Nixon", 26, 26, 1, True,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None),
        _row(1972, "Texas", 7, "George McGovern", 0, 0, 2, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None),
        # --- 2016: C (49 EV), D wins (55, took office), F faithless (1 EV, no PV) ---
        _row(2016, "Texas", 3, "Cand C", 38, 49, 2, False,
             candidate_votes=4000000, state_total=9000000),
        _row(2016, "Texas", 4, "Cand D", 0, 55, 1, True,
             candidate_votes=3800000, state_total=9000000),
        _row(2016, "Texas", 5, "Faithless F", 0, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None),
        _row(2016, "California", 3, "Cand C", 0, 49, 2, False,
             candidate_votes=3000000, state_total=12000000, total_ev=55),
        _row(2016, "California", 4, "Cand D", 55, 55, 1, True,
             candidate_votes=7000000, state_total=12000000, total_ev=55),
        _row(2016, "California", 5, "Faithless F", 0, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=55),
        _row(2016, "Washington", 3, "Cand C", 11, 49, 2, False,
             candidate_votes=1400000, state_total=3000000, total_ev=12),
        _row(2016, "Washington", 4, "Cand D", 0, 55, 1, True,
             candidate_votes=1300000, state_total=3000000, total_ev=12),
        _row(2016, "Washington", 5, "Faithless F", 1, 1, 3, False,
             candidate_votes=None, state_total=None, source=None, party=None,
             reliability=None, redistributable=None, total_ev=12),
        # --- 2020: A (38 EV), B wins (55, took office) ---
        _row(2020, "Texas", 1, "Cand A", 38, 38, 2, False,
             candidate_votes=5000000, state_total=11000000),
        _row(2020, "Texas", 2, "Cand B", 0, 55, 1, True,
             candidate_votes=5500000, state_total=11000000),
        _row(2020, "California", 1, "Cand A", 0, 38, 2, False,
             candidate_votes=6000000, state_total=17000000, total_ev=55),
        _row(2020, "California", 2, "Cand B", 55, 55, 1, True,
             candidate_votes=11000000, state_total=17000000, total_ev=55),
    ]
    # The enriched shape build_snapshot consumes: the view columns + state_usps.
    return pd.DataFrame(rows)[[*EC_PV_COLUMNS, "state_usps"]]


def _build(
    tmp_path: Path, frame: pd.DataFrame | None = None
) -> tuple[Path, SnapshotMeta]:
    out = tmp_path / "snapshot.sqlite"
    meta = build_snapshot(
        _ec_pv_frame() if frame is None else frame, str(out), build_timestamp=_TS
    )
    return out, meta


def _read(out: Path, table: str) -> pd.DataFrame:
    con = sqlite3.connect(str(out))
    try:
        return pd.read_sql(f"SELECT * FROM {table}", con)
    finally:
        con.close()


# --- slug ------------------------------------------------------------------


def test_candidate_slug_is_deterministic_and_ascii_folded() -> None:
    assert candidate_slug("Donald J. Trump") == "donald-j-trump"
    assert candidate_slug("John C. Frémont") == "john-c-fremont"
    assert candidate_slug("  Adlai   Stevenson ") == "adlai-stevenson"
    # Stable regardless of surrounding punctuation.
    assert candidate_slug("J. Strom Thurmond") == "j-strom-thurmond"


def test_empty_slug_fails_loud() -> None:
    # A candidate name with no alphanumeric content slugs to "" — unusable as a public
    # id, so it must fail loud rather than be written.
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "candidate"] = "…"
    with pytest.raises(SnapshotError, match="empty slug"):
        build_snapshot(frame, "/dev/null")


def test_slug_collision_fails_loud() -> None:
    # Two DISTINCT canonical names that fold to one slug — the docs/canonical-keys.md
    # same-name residual — must raise, not silently merge two people (in-window).
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "candidate"] = "José Foo"
    frame.loc[frame["candidate"] == "Cand B", "candidate"] = "Jose Foo"
    with pytest.raises(SnapshotError, match="slug collision"):
        build_snapshot(frame, "/dev/null")


def test_pre_window_slug_collision_is_tolerated(tmp_path: Path) -> None:
    # A slug collision among candidates that never ship (pre-1976, filtered out) must
    # NOT fail the build — slug uniqueness is enforced only over the served window.
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Richard Nixon", "candidate"] = "José Foo"
    frame.loc[frame["candidate"] == "George McGovern", "candidate"] = "Jose Foo"
    out, meta = _build(tmp_path, frame)  # does not raise
    assert set(_read(out, DATA_TABLE)["year"]) == {2016, 2020}


# --- shape / candidate_id drop ---------------------------------------------


def test_data_columns_drop_candidate_id_and_add_slug() -> None:
    assert "candidate_id" not in DATA_COLUMNS
    assert "candidate_slug" in DATA_COLUMNS
    assert "redistributable" not in DATA_COLUMNS  # constant-true → recorded in meta


def test_snapshot_tables_have_expected_shape(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    assert list(data.columns) == list(DATA_COLUMNS)
    assert "candidate_id" not in data.columns
    # Slug is minted for every row.
    assert (data["candidate_slug"] == data["candidate"].map(candidate_slug)).all()
    # state_usps is carried for the /v1/states/{...} path key (#97).
    assert set(data.loc[data["state"] == "California", "state_usps"]) == {"CA"}


def test_add_candidate_slug_is_pure() -> None:
    frame = _ec_pv_frame()
    slugged = add_candidate_slug(frame)
    assert "candidate_slug" in slugged.columns
    assert "candidate_slug" not in frame.columns  # did not mutate the input


# --- coverage window (pre-1976 excluded) -----------------------------------


def test_pre_window_years_are_filtered_out(tmp_path: Path) -> None:
    out, meta = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    assert set(data["year"]) == {2016, 2020}  # 1972 (all-NULL PV) dropped
    assert meta.year_min == 2016
    assert meta.year_max == 2020


def test_in_window_null_pv_getter_survives(tmp_path: Path) -> None:
    # A faithless getter (EC vote, no MIT PV) in a covered year stays — with NULL PV.
    out, _ = _build(tmp_path)
    data = _read(out, DATA_TABLE)
    faithless = data[data["candidate"] == "Faithless F"]
    assert len(faithless) == 3  # present in all three 2016 states
    assert faithless["candidate_votes"].isna().all()
    assert faithless["president_electoral_votes"].sum() == 1  # its one real EV


def test_empty_window_fails_loud() -> None:
    # A frame with no redistributable PV at all would build an empty surface.
    frame = _ec_pv_frame()
    frame["candidate_votes"] = None
    with pytest.raises(SnapshotError, match="no redistributable PV"):
        build_snapshot(frame, "/dev/null")


# --- national roll-up -------------------------------------------------------


def test_national_rollup_ec_and_pv_totals(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    c = rollup.loc[(2016, "cand-c")]
    assert c["national_electoral_votes"] == 49
    assert c["national_pv_votes"] == 4000000 + 3000000 + 1400000
    # Denominator = each state's total counted once: 9M + 12M + 3M = 24M.
    assert c["national_pv_denominator"] == 24000000


def test_denominator_survives_no_pv_getter_sorting_first(tmp_path: Path) -> None:
    # Regression (code-review): national_pv_denominator must count every state once even
    # when the alphabetically-first candidate_slug in a state is a no-PV getter (NULL
    # state_total_votes). Rename the faithless getter so its slug sorts BEFORE the real
    # candidates in every 2016 state; the denominator must stay 9M + 12M + 3M = 24M. With
    # the old drop_duplicates(["year","state"]) this would keep the NULL row per state
    # and understate the denominator (here, drop to 0).
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Faithless F", "candidate"] = "Aardvark Faithless"
    out, _ = _build(tmp_path, frame)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    assert rollup.loc[(2016, "cand-c"), "national_pv_denominator"] == 24000000


def test_rollup_null_pv_getter_has_null_pv_total(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE).set_index(["year", "candidate_slug"])
    f = rollup.loc[(2016, "faithless-f")]
    assert f["national_electoral_votes"] == 1
    assert pd.isna(f["national_pv_votes"])  # honest NULL, not a fabricated 0


def test_rollup_one_row_per_year_candidate(tmp_path: Path) -> None:
    out, _ = _build(tmp_path)
    rollup = _read(out, ROLLUP_TABLE)
    assert not rollup.duplicated(["year", "candidate_slug"]).any()
    assert set(rollup["year"]) == {2016, 2020}


# --- metadata / content-hash version ---------------------------------------


def test_meta_records_provenance(tmp_path: Path) -> None:
    out, meta = _build(tmp_path)
    assert meta.schema_version == SNAPSHOT_SCHEMA_VERSION
    assert meta.source == "MIT"
    assert meta.license == "CC0-1.0"
    assert meta.build_timestamp == _TS.isoformat()
    data = _read(out, DATA_TABLE)
    assert meta.row_count == len(data)
    assert meta.candidate_count == data["candidate_slug"].nunique()
    meta_tbl = _read(out, META_TABLE)
    assert len(meta_tbl) == 1
    assert meta_tbl["snapshot_version"].iloc[0] == meta.snapshot_version


def test_version_is_content_hash_independent_of_timestamp(tmp_path: Path) -> None:
    # Two builds of the same data with DIFFERENT timestamps ⇒ identical version (D028).
    out_a = tmp_path / "a.sqlite"
    out_b = tmp_path / "b.sqlite"
    meta_a = build_snapshot(_ec_pv_frame(), str(out_a), build_timestamp=_TS)
    meta_b = build_snapshot(
        _ec_pv_frame(), str(out_b), build_timestamp=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert meta_a.snapshot_version == meta_b.snapshot_version
    assert meta_a.build_timestamp != meta_b.build_timestamp


def test_version_changes_when_data_changes(tmp_path: Path) -> None:
    base = build_snapshot(_ec_pv_frame(), str(tmp_path / "a.sqlite"), build_timestamp=_TS)
    changed = _ec_pv_frame()
    changed.loc[changed["candidate"] == "Cand A", "candidate_votes"] = 42
    other = build_snapshot(changed, str(tmp_path / "b.sqlite"), build_timestamp=_TS)
    assert base.snapshot_version != other.snapshot_version


# --- redistributable-only guard (D030) -------------------------------------


def test_redistributable_false_row_fails_loud() -> None:
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "redistributable"] = False
    with pytest.raises(SnapshotError, match="redistributable=false"):
        build_snapshot(frame, "/dev/null")


def test_non_mit_source_fails_loud() -> None:
    frame = _ec_pv_frame()
    frame.loc[frame["candidate"] == "Cand A", "source"] = "UCSB"
    with pytest.raises(SnapshotError, match="non-MIT source"):
        build_snapshot(frame, "/dev/null")


# --- atomic write -----------------------------------------------------------


def test_duplicate_grain_row_fails_loud(tmp_path: Path) -> None:
    # The ec_pv PRIMARY KEY (year, state, candidate_slug) makes a grain fan-out fail loud
    # at INSERT rather than silently shipping duplicates the content hash would bless.
    frame = _ec_pv_frame()
    dup = frame[
        (frame["year"] == 2020)
        & (frame["state"] == "Texas")
        & (frame["candidate"] == "Cand A")
    ]
    frame = pd.concat([frame, dup], ignore_index=True)
    with pytest.raises(sqlite3.IntegrityError):
        build_snapshot(frame, str(tmp_path / "snapshot.sqlite"), build_timestamp=_TS)


def test_build_is_idempotent_overwrite(tmp_path: Path) -> None:
    out = tmp_path / "snapshot.sqlite"
    first = build_snapshot(_ec_pv_frame(), str(out), build_timestamp=_TS)
    second = build_snapshot(_ec_pv_frame(), str(out), build_timestamp=_TS)
    assert first.snapshot_version == second.snapshot_version
    assert out.exists()


# --- live-DB read probe (offline, via a stub dbc) --------------------------


class _StubDBC:
    """Minimal stand-in exposing the one method ``read_redistributable`` calls."""

    def __init__(self, exists: bool) -> None:
        self._exists = exists
        self.closed = False

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        if "to_regclass" in query:
            rel = "dwh.ec_pv_redistributable" if self._exists else None
            return pd.DataFrame({"relation": [rel]})
        if "state_usps" in query:  # SELECT state, state_usps FROM dwh.state
            return pd.DataFrame(
                {"state": list(_USPS), "state_usps": list(_USPS.values())}
            )
        # The view read: return the frame WITHOUT the enrichment column (the view
        # itself does not carry state_usps — read_redistributable merges it in).
        return _ec_pv_frame().drop(columns=["state_usps"])

    def close_connection(self) -> None:
        self.closed = True


def test_read_missing_view_fails_loud() -> None:
    with pytest.raises(SnapshotError, match="does not exist"):
        read_redistributable(_StubDBC(exists=False))  # type: ignore[arg-type]


def test_read_present_view_enriches_with_state_usps() -> None:
    df = read_redistributable(_StubDBC(exists=True))  # type: ignore[arg-type]
    assert list(df.columns) == [*EC_PV_COLUMNS, "state_usps"]
    assert set(df["state_usps"]) == {"TX", "CA", "WA"}


def test_build_from_db_reads_then_builds(tmp_path: Path) -> None:
    # The glue: read the (stubbed) live view, build the snapshot, close the connection.
    from usvote.snapshot import build_snapshot_from_db

    stub = _StubDBC(exists=True)
    out = tmp_path / "snapshot.sqlite"
    meta = build_snapshot_from_db(
        stub,  # type: ignore[arg-type]
        str(out),
        build_timestamp=_TS,
        close=True,
    )
    assert out.exists()
    assert meta.year_min == 2016
    assert stub.closed
