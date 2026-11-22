"""Unit tests for :mod:`usvote.ucsb.config` — the UCSB snapshot-dir getter (#34).

Mirrors ``test_mit_config.py`` / ``test_config.py``: every case injects an explicit
``environ`` mapping rather than mutating the process environment, so the tests are
hermetic and order-independent. The unset/empty/nonexistent branching is shared with
the sibling getters via ``config.require_path_from_env``; these cases pin the
UCSB-specific variable name, and the bootstrap hint that a fresh machine depends on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from usvote import config
from usvote.ucsb import config as ucsb_config
from usvote.ucsb import scrape

VAR = ucsb_config.UCSB_HTML_DIR_VAR


class TestUcsbHtmlDirFromEnv:
    def test_unset_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=VAR):
            ucsb_config.ucsb_html_dir_from_env({})

    def test_empty_raises(self) -> None:
        with pytest.raises(config.ConfigError, match=VAR):
            ucsb_config.ucsb_html_dir_from_env({VAR: ""})

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(config.ConfigError, match="does not exist"):
            ucsb_config.ucsb_html_dir_from_env({VAR: "/no/such/ucsb_raw"})

    def test_existing_dir_returned(self, tmp_path: Path) -> None:
        result = ucsb_config.ucsb_html_dir_from_env({VAR: str(tmp_path)})
        assert result == str(tmp_path)


class TestBootstrapHint:
    """The hints carry the one manual step in the flow, so they must stay correct.

    An absent snapshot directory is the *expected* first-run state, and this getter is
    where a fresh machine meets it — so both messages have to explain the bootstrap,
    and the command they print has to be the polite one.
    """

    @pytest.mark.parametrize(
        "environ, expected_error",
        [({}, "not set"), ({VAR: "/no/such/ucsb_raw"}, "does not exist")],
    )
    def test_both_failure_modes_explain_the_bootstrap(
        self, environ: dict[str, str], expected_error: str
    ) -> None:
        with pytest.raises(config.ConfigError) as excinfo:
            ucsb_config.ucsb_html_dir_from_env(environ)
        message = str(excinfo.value)
        assert expected_error in message
        assert scrape.INDEX_FILENAME in message
        assert "python -m usvote.ucsb" in message

    def test_documented_command_carries_the_truthful_user_agent(self) -> None:
        # The bootstrap curl is the only request in the flow that scrape.fetch_url does
        # not make, so it is the only one that can go out unidentified. It is also the
        # one place the UA is duplicated (scrape imports this module, so config cannot
        # import the constant back without a cycle) -- this pins the two together.
        assert f"-A '{scrape.USER_AGENT}'" in ucsb_config._BOOTSTRAP_HINT

    def test_hint_warns_the_snapshot_stays_out_of_the_repo(self) -> None:
        # D022/D023: this repo is public and UCSB is non-redistributable, so a user
        # pointing the var inside the tree is the mistake worth pre-empting.
        with pytest.raises(config.ConfigError, match="outside this repository"):
            ucsb_config.ucsb_html_dir_from_env({})
