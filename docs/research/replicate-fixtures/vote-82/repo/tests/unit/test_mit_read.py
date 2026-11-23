"""Unit tests for :mod:`usvote.mit.read` — the MIT CSV ingest seam (#64).

These run fully offline against a small sample of real MIT rows saved under
``tests/fixtures/`` (see ``tests._helpers.MIT_SAMPLE_CSV``). They exercise the
happy-path load, the env-var path resolution, and the schema-drift guard.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests._helpers import MIT_SAMPLE_CSV
from usvote.mit.config import MIT_CSV_PATH_VAR
from usvote.mit.read import (
    EXPECTED_COLUMNS,
    MITReadError,
    load_mit_president_csv,
)


class TestLoadMitPresidentCsv:
    def test_explicit_path_loads_all_columns_and_rows(self) -> None:
        df = load_mit_president_csv(MIT_SAMPLE_CSV)
        # Every expected column is present (the fixture is the real 15-col schema).
        assert set(EXPECTED_COLUMNS) <= set(df.columns)
        # The sample fixture is 13 real rows across four representative years.
        assert len(df) == 13
        assert sorted(df["year"].unique()) == [1976, 2000, 2016, 2024]

    def test_accepts_str_path(self) -> None:
        df = load_mit_president_csv(str(MIT_SAMPLE_CSV))
        assert not df.empty

    def test_no_dtype_coercion_transform_owns_typing(self) -> None:
        # The read stage returns the CSV verbatim; the writein=True / NaN-candidate
        # row survives untouched (NaN handling is a later transform concern).
        df = load_mit_president_csv(MIT_SAMPLE_CSV)
        writeins = df[df["writein"]]
        assert len(writeins) == 1
        assert writeins["candidate"].isna().all()

    def test_path_resolved_from_env_when_omitted(self) -> None:
        # With path=None, the location comes from USVOTE_MIT_CSV_PATH via the
        # injected environ — no reliance on the real process environment.
        df = load_mit_president_csv(
            environ={MIT_CSV_PATH_VAR: str(MIT_SAMPLE_CSV)}
        )
        assert len(df) == 13

    def test_missing_column_raises_mit_read_error(self, tmp_path: Path) -> None:
        # Drop a column to simulate an upstream MIT schema change; the ingest guard
        # must fail loudly and name the missing column, not surface a later KeyError.
        df = load_mit_president_csv(MIT_SAMPLE_CSV).drop(columns=["candidatevotes"])
        drifted = tmp_path / "drifted.csv"
        df.to_csv(drifted, index=False)
        with pytest.raises(MITReadError, match="candidatevotes"):
            load_mit_president_csv(drifted)

    def test_additive_column_is_non_breaking(self, tmp_path: Path) -> None:
        # The schema check is a subset test: MIT versions the file and may add
        # columns, so an extra column must not trip the guard.
        df = load_mit_president_csv(MIT_SAMPLE_CSV)
        df["new_upstream_field"] = 1
        augmented = tmp_path / "augmented.csv"
        df.to_csv(augmented, index=False)
        loaded = load_mit_president_csv(augmented)
        assert "new_upstream_field" in loaded.columns

    def test_missing_file_raises_mit_read_error(self, tmp_path: Path) -> None:
        # An explicitly-passed nonexistent path fails the same typed way an
        # env-resolved missing path does — not a raw FileNotFoundError.
        with pytest.raises(MITReadError, match="not found"):
            load_mit_president_csv(tmp_path / "no_such_president.csv")

    def test_empty_file_raises_mit_read_error(self, tmp_path: Path) -> None:
        # A zero-byte file trips pandas' EmptyDataError; the ingest boundary
        # translates it to a typed MITReadError instead of leaking the pandas error.
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        with pytest.raises(MITReadError, match="empty or unparseable"):
            load_mit_president_csv(empty)

    def test_returns_dataframe(self) -> None:
        assert isinstance(load_mit_president_csv(MIT_SAMPLE_CSV), pd.DataFrame)
