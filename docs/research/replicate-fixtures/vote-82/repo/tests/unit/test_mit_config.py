"""Unit tests for :mod:`usvote.mit.config` — the MIT CSV-path getter (#64).

Mirrors ``test_config.py``'s shapefile cases: every case injects an explicit
``environ`` mapping rather than mutating the process environment, so the tests are
hermetic and order-independent. The unset/empty/nonexistent branching is shared
with the shapefile getter via ``config.require_path_from_env``; these cases pin the
MIT-specific variable name and messages.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from usvote import config
from usvote.mit import config as mit_config


class TestMitCsvPathFromEnv:
    def test_unset_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=mit_config.MIT_CSV_PATH_VAR):
            mit_config.mit_csv_path_from_env({})

    def test_empty_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=mit_config.MIT_CSV_PATH_VAR):
            mit_config.mit_csv_path_from_env({mit_config.MIT_CSV_PATH_VAR: ""})

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(config.ConfigError, match="does not exist"):
            mit_config.mit_csv_path_from_env(
                {mit_config.MIT_CSV_PATH_VAR: "/no/such/1976-2024-president.csv"}
            )

    def test_existing_path_returned(self, tmp_path: Path) -> None:
        csv = tmp_path / "1976-2024-president.csv"
        csv.write_text("")  # existence is all the getter checks
        result = mit_config.mit_csv_path_from_env(
            {mit_config.MIT_CSV_PATH_VAR: str(csv)}
        )
        assert result == str(csv)
