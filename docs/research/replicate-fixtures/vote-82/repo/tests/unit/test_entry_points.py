"""Unit tests for the three CLI entry points (#84b).

Drives ``main(argv)`` for ``usvote.__main__``, ``usvote.mit.__main__`` and
``usvote.ucsb.__main__`` with the pipelines/orchestrator and config resolvers
monkeypatched, asserting subcommand dispatch, the bare-default paths (``usvote`` -> EC,
``usvote.ucsb`` -> snapshot, ``usvote.mit`` -> load), the ``--replace`` mapping, and the
loud/explicit UCSB gating for ``usvote all``. No DB, no network.
"""

from __future__ import annotations

from typing import Any

import pytest

import usvote.__main__ as top
import usvote.mit.__main__ as mit_main
import usvote.ucsb.__main__ as ucsb_main
from usvote.config import ConfigError
from usvote.warehouse import (
    SOURCE_EC,
    SOURCE_MIT,
    SOURCE_UCSB,
    WarehouseResult,
)

_DB = {"user": "u", "host": "h", "password": "p"}  # password present -> no getpass


@pytest.fixture
def top_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Patch the top-level entry point's config + steps; record what dispatched."""
    calls: dict[str, list] = {"ec": [], "warehouse": []}
    monkeypatch.setattr(top.config, "shapefile_path_from_env", lambda *a, **k: "s.shp")
    monkeypatch.setattr(top.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(top, "mit_csv_path_from_env", lambda *a, **k: "mit.csv")
    monkeypatch.setattr(top, "DBC", lambda cfg: "DBC")

    def ec(
        dbc: object, shapefile_path: str, *, replace: bool = False, close: bool = False
    ) -> None:
        calls["ec"].append({"replace": replace})

    def wh(
        dbc: object,
        shapefile_path: str,
        mit_csv_path: Any,
        *,
        ucsb_html_dir: Any,
        replace: bool,
        environ: Any,
        close: bool,
    ) -> WarehouseResult:
        calls["warehouse"].append({"ucsb_html_dir": ucsb_html_dir, "replace": replace})
        loaded = {SOURCE_EC, SOURCE_MIT} | (
            {SOURCE_UCSB} if ucsb_html_dir is not None else set()
        )
        return WarehouseResult(5, 3, None, None, frozenset(loaded), True)

    monkeypatch.setattr(top, "run_ec_pipeline", ec)
    monkeypatch.setattr(top, "run_warehouse", wh)
    return calls


@pytest.mark.parametrize(
    "argv,replace",
    [([], False), (["--replace"], True), (["ec"], False), (["ec", "--replace"], True)],
)
def test_bare_and_ec_run_the_ec_pipeline(
    top_env: dict[str, list], argv: list[str], replace: bool
) -> None:
    # Bare ``python -m usvote`` stays EC (backward compat), and ``--replace`` still works
    # bare (top-level) as well as on the explicit ``ec`` subcommand.
    assert top.main(argv) == 0
    assert top_env["ec"] == [{"replace": replace}]
    assert top_env["warehouse"] == []


def test_all_autodetects_ucsb_when_snapshot_present(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    assert top.main(["all", "--replace"]) == 0
    assert top_env["warehouse"] == [{"ucsb_html_dir": "snap/", "replace": True}]


def test_all_skips_ucsb_loudly_when_snapshot_absent(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_UCSB_HTML_DIR unset")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", absent)
    assert top.main(["all"]) == 0
    assert top_env["warehouse"] == [{"ucsb_html_dir": None, "replace": False}]
    # The skip must be loud (D024): a prominent notice on stderr.
    assert "WITHOUT UCSB" in capsys.readouterr().err


def test_all_no_ucsb_skips_without_probing_env(
    top_env: dict[str, list],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    # ``--no-ucsb`` must skip even if a snapshot exists, and must not consult the env.
    def boom(*a: Any, **k: Any) -> str:
        raise AssertionError("ucsb_html_dir_from_env must not be called for --no-ucsb")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", boom)
    assert top.main(["all", "--no-ucsb"]) == 0
    assert top_env["warehouse"] == [{"ucsb_html_dir": None, "replace": False}]
    # Still loud (D024), but the remedy acknowledges the deliberate choice rather than
    # suggesting --require-ucsb / USVOTE_UCSB_HTML_DIR as if UCSB were missing by accident.
    err = capsys.readouterr().err
    assert "WITHOUT UCSB" in err
    assert "--no-ucsb" in err
    assert "--require-ucsb" not in err


def test_all_require_ucsb_fails_when_snapshot_absent(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_UCSB_HTML_DIR unset")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", absent)
    # --require-ucsb turns an absent snapshot into a hard config failure (exit 2), never
    # a silent EC+MIT build.
    assert top.main(["all", "--require-ucsb"]) == 2
    assert top_env["warehouse"] == []


def test_config_error_returns_2(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_SHAPEFILE_PATH unset")

    monkeypatch.setattr(top.config, "shapefile_path_from_env", absent)
    assert top.main(["ec"]) == 2
    assert top_env["ec"] == []


# --- usvote.ucsb -----------------------------------------------------------------


@pytest.fixture
def ucsb_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"snapshot": [], "load": []}
    monkeypatch.setattr(ucsb_main, "snapshot_elections", lambda: calls["snapshot"].append({}))
    monkeypatch.setattr(ucsb_main.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(ucsb_main, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setattr(ucsb_main, "DBC", lambda cfg: "DBC")
    monkeypatch.setattr(
        ucsb_main,
        "run_ucsb_pipeline",
        lambda dbc, html_dir, *, replace=False, close=False: calls["load"].append(
            {"html_dir": html_dir, "replace": replace}
        ),
    )
    return calls


@pytest.mark.parametrize("argv", [[], ["snapshot"]])
def test_ucsb_bare_and_snapshot_snapshot(
    ucsb_env: dict[str, list], argv: list[str]
) -> None:
    # Bare ``python -m usvote.ucsb`` keeps its D023 meaning: snapshot, not load.
    assert ucsb_main.main(argv) == 0
    assert ucsb_env["snapshot"] == [{}]
    assert ucsb_env["load"] == []


@pytest.mark.parametrize("argv,replace", [(["load"], False), (["load", "--replace"], True)])
def test_ucsb_load_runs_pipeline(
    ucsb_env: dict[str, list], argv: list[str], replace: bool
) -> None:
    assert ucsb_main.main(argv) == 0
    assert ucsb_env["load"] == [{"html_dir": "snap/", "replace": replace}]
    assert ucsb_env["snapshot"] == []


# --- usvote.mit ------------------------------------------------------------------


@pytest.fixture
def mit_env(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(mit_main.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(mit_main, "mit_csv_path_from_env", lambda *a, **k: "mit.csv")
    monkeypatch.setattr(mit_main, "DBC", lambda cfg: "DBC")
    monkeypatch.setattr(
        mit_main,
        "run_mit_pipeline",
        lambda dbc, path, *, replace=False, close=False: calls.append(
            {"path": path, "replace": replace}
        ),
    )
    return calls


@pytest.mark.parametrize(
    "argv,replace", [([], False), (["load"], False), (["load", "--replace"], True)]
)
def test_mit_bare_and_load_run_pipeline(
    mit_env: list[dict], argv: list[str], replace: bool
) -> None:
    # Bare ``python -m usvote.mit`` loads (the single subcommand's default).
    assert mit_main.main(argv) == 0
    assert mit_env == [{"path": "mit.csv", "replace": replace}]
