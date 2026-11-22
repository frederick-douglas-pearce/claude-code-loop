"""Unit tests for :mod:`usvote.config` — the env-driven configuration seam (#31).

Every case injects an explicit ``environ`` mapping rather than mutating the real
process environment, so the tests are hermetic and order-independent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from usvote import config


class TestDbConfigFromEnv:
    def test_defaults_when_unset(self) -> None:
        cfg = config.db_config_from_env({})
        assert cfg == {
            "host": "localhost",
            "port": "5432",
            "dbname": "elections",
            "user": "postgres",
        }
        # Password is omitted entirely when unset so the caller can prompt.
        assert "password" not in cfg

    def test_overrides_honored(self) -> None:
        cfg = config.db_config_from_env(
            {
                "PGHOST": "db.internal",
                "PGPORT": "6543",
                "PGDATABASE": "votes",
                "PGUSER": "analyst",
            }
        )
        assert cfg == {
            "host": "db.internal",
            "port": "6543",
            "dbname": "votes",
            "user": "analyst",
        }

    def test_password_included_when_set(self) -> None:
        cfg = config.db_config_from_env({"PGPASSWORD": "s3cret"})
        assert cfg["password"] == "s3cret"

    def test_empty_password_is_kept_not_dropped(self) -> None:
        # An explicitly-set empty password is a real (if unusual) choice; only an
        # *unset* variable triggers the prompt path, so "" must survive.
        cfg = config.db_config_from_env({"PGPASSWORD": ""})
        assert cfg["password"] == ""


class TestShapefilePathFromEnv:
    def test_unset_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=config.SHAPEFILE_PATH_VAR):
            config.shapefile_path_from_env({})

    def test_empty_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=config.SHAPEFILE_PATH_VAR):
            config.shapefile_path_from_env({config.SHAPEFILE_PATH_VAR: ""})

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(config.ConfigError, match="does not exist"):
            config.shapefile_path_from_env(
                {config.SHAPEFILE_PATH_VAR: "/no/such/tl_2019_us_state.shp"}
            )

    def test_existing_path_returned(self, tmp_path: Path) -> None:
        shp = tmp_path / "tl_2019_us_state.shp"
        shp.write_text("")  # existence is all the getter checks
        result = config.shapefile_path_from_env(
            {config.SHAPEFILE_PATH_VAR: str(shp)}
        )
        assert result == str(shp)
