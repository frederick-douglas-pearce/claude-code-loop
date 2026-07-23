#!/usr/bin/env python3
"""Tests for the config-driven append-only guard hook.

Covers ``hooks/guard_append_only.py``: the subset-of-IDs detection (drop,
append, body-edit, count-preserving swap), the anchored ID regex, suffix-based
file matching, the config-driven registry (absent -> silent inert; malformed ->
loud inert; valid -> active, including the ``\\s`` JSON round-trip), the fail
directions, and event-level behaviour.

Stdlib ``unittest`` only -- the plugin repo has no pytest / CI. Run with:

    python3 -m unittest discover -s tests
    # or
    python3 tests/test_guard_append_only.py
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK_PATH = _REPO_ROOT / "hooks" / "guard_append_only.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard_append_only", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_hook()

# The AgentFluent decision-log pattern, used as the representative fixture. The
# regex is written here as Python; the JSON round-trip tests below prove it
# survives being stored as an escaped JSON string in the sidecar.
DECISION_PATTERN = re.compile(r"^##\s+(D\d+(?:-[A-Za-z0-9]+)?)", re.MULTILINE)
SUFFIX = ".claude/specs/decisions.md"
REGISTRY = [(SUFFIX, DECISION_PATTERN)]

# The exact string a sidecar stores for that pattern (note the doubled
# backslashes -- the C5 escaping hazard the round-trip tests guard against).
SIDECAR_ID_PATTERN = "^##\\s+(D\\d+(?:-[A-Za-z0-9]+)?)"


def _entry(num: str, body: str = "Some decision body.") -> str:
    return f"## D{num}: a decision\n\n{body}\n"


def _doc(*nums: str, body: str = "Some decision body.") -> str:
    return "\n".join(_entry(n, body) for n in nums)


def _write_event(path: str, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


class EvaluateTests(unittest.TestCase):
    def test_pure_append_is_allowed(self) -> None:
        blocked, _ = guard.evaluate(_doc("001", "002"), _doc("001", "002", "003"), DECISION_PATTERN)
        self.assertFalse(blocked)

    def test_dropping_an_entry_is_blocked(self) -> None:
        blocked, reason = guard.evaluate(_doc("001", "002"), _doc("001"), DECISION_PATTERN)
        self.assertTrue(blocked)
        self.assertIn("D002", reason)

    def test_editing_body_is_allowed(self) -> None:
        existing = _doc("001", "002", body="Original.")
        proposed = _doc("001", "002", body="Rewritten.")
        blocked, _ = guard.evaluate(existing, proposed, DECISION_PATTERN)
        self.assertFalse(blocked)

    def test_count_preserving_swap_is_blocked(self) -> None:
        blocked, reason = guard.evaluate(_doc("001", "002", "003"), _doc("001", "002", "099"), DECISION_PATTERN)
        self.assertTrue(blocked)
        self.assertIn("D003", reason)

    def test_empty_proposed_is_blocked(self) -> None:
        blocked, reason = guard.evaluate(_doc("001", "002"), "", DECISION_PATTERN)
        self.assertTrue(blocked)
        self.assertIn("D001", reason)
        self.assertIn("D002", reason)

    def test_existing_with_no_ids_is_allowed(self) -> None:
        blocked, _ = guard.evaluate("# Log\n\nNo entries.\n", "anything", DECISION_PATTERN)
        self.assertFalse(blocked)

    def test_suffixed_id_distinct_from_numeric_sibling(self) -> None:
        blocked, reason = guard.evaluate(_doc("038", "038-A"), _doc("038"), DECISION_PATTERN)
        self.assertTrue(blocked)
        self.assertIn("D038-A", reason)

    def test_prose_mentions_not_counted(self) -> None:
        text = "## D001: real\n\nSupersedes D012 and relates to D999 inline.\n"
        self.assertEqual(guard.extract_ids(text, DECISION_PATTERN), {"D001"})


class MatchRegisteredFileTests(unittest.TestCase):
    def test_registered_suffix_matches(self) -> None:
        self.assertIs(guard.match_registered_file(f"/home/u/project/{SUFFIX}", REGISTRY), DECISION_PATTERN)

    def test_unrelated_file_does_not_match(self) -> None:
        self.assertIsNone(guard.match_registered_file("/home/u/notes/decisions.md", REGISTRY))

    def test_empty_path_does_not_match(self) -> None:
        self.assertIsNone(guard.match_registered_file("", REGISTRY))

    def test_relative_registered_path_matches(self) -> None:
        self.assertIs(guard.match_registered_file(SUFFIX, REGISTRY), DECISION_PATTERN)

    def test_suffix_requires_path_boundary(self) -> None:
        self.assertIsNone(guard.match_registered_file(f"/repo/vendor{SUFFIX}", REGISTRY))

    def test_empty_registry_matches_nothing(self) -> None:
        self.assertIsNone(guard.match_registered_file(f"/home/u/{SUFFIX}", []))


class LoadRegistryTests(unittest.TestCase):
    def _sidecar(self, tmp: Path, content: str) -> Path:
        p = tmp / ".claude" / "loop.append-guard.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_no_project_dir_is_silent_inert(self) -> None:
        with mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self.assertEqual(guard.load_registry(None), [])
            self.assertEqual(err.getvalue(), "")

    def test_absent_sidecar_is_silent_inert(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self.assertEqual(guard.load_registry(td), [])  # no sidecar written
            self.assertEqual(err.getvalue(), "")

    def test_valid_sidecar_loads_and_matches_after_json_round_trip(self) -> None:
        # C5: prove the `\s`/`\d` pattern survives JSON escaping and still matches.
        import tempfile

        payload = json.dumps([{"suffix": SUFFIX, "id_pattern": SIDECAR_ID_PATTERN}])
        with tempfile.TemporaryDirectory() as td:
            self._sidecar(Path(td), payload)
            registry = guard.load_registry(td)
        self.assertEqual(len(registry), 1)
        suffix, pattern = registry[0]
        self.assertEqual(suffix, SUFFIX)
        self.assertEqual(guard.extract_ids(_doc("001", "038-A"), pattern), {"D001", "D038-A"})

    def test_malformed_json_is_loud_inert(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), "{not json")
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("invalid JSON", err.getvalue())

    def test_non_list_is_loud_inert(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), json.dumps({"suffix": SUFFIX}))
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("must be a JSON array", err.getvalue())

    def test_uncompilable_regex_entry_is_skipped_loudly(self) -> None:
        import tempfile

        payload = json.dumps([{"suffix": SUFFIX, "id_pattern": "([unclosed"}])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), payload)
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("not a valid regex", err.getvalue())

    def test_entry_missing_fields_is_skipped(self) -> None:
        import tempfile

        payload = json.dumps([{"suffix": SUFFIX}, {"id_pattern": SIDECAR_ID_PATTERN}])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), payload)
            self.assertEqual(guard.load_registry(td), [])
            # The "loud" half of fail-open-but-loud: both bad entries warn.
            self.assertIn("no valid 'id_pattern'", err.getvalue())
            self.assertIn("no valid 'suffix'", err.getvalue())

    def test_non_dict_entry_is_skipped_loudly(self) -> None:
        import tempfile

        payload = json.dumps([123, "not-an-object"])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), payload)
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("is not an object", err.getvalue())

    def test_multi_group_pattern_is_rejected_loudly(self) -> None:
        # Regression: a >=2 capture-group pattern makes re.findall return tuples,
        # which downstream would crash and fail the guard OPEN. It must be
        # skipped at load time with a warning, never reach evaluate().
        import tempfile

        two_groups = "^##\\s+(D\\d+)(?:-([A-Za-z0-9]+))?"
        payload = json.dumps([{"suffix": SUFFIX, "id_pattern": two_groups}])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), payload)
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("exactly one capture group", err.getvalue())

    def test_zero_group_pattern_is_rejected_loudly(self) -> None:
        import tempfile

        no_groups = "^##\\s+D\\d+"  # matches, but captures nothing
        payload = json.dumps([{"suffix": SUFFIX, "id_pattern": no_groups}])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), payload)
            self.assertEqual(guard.load_registry(td), [])
            self.assertIn("exactly one capture group", err.getvalue())

    def test_empty_list_config_loads_as_inert(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td, mock.patch.object(sys, "stderr", io.StringIO()) as err:
            self._sidecar(Path(td), "[]")
            self.assertEqual(guard.load_registry(td), [])
            self.assertEqual(err.getvalue(), "")  # a valid empty config is silent


class CheckTests(unittest.TestCase):
    def _registered(self, tmp: Path) -> Path:
        return tmp / ".claude" / "specs" / "decisions.md"

    def test_ignores_non_write_tools(self) -> None:
        event = {"tool_name": "Edit", "tool_input": {"file_path": f"x/{SUFFIX}"}}
        self.assertEqual(guard.check(event, REGISTRY), (False, ""))

    def test_ignores_unregistered_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "decisions.md"
            target.write_text(_doc("001"), encoding="utf-8")
            blocked, _ = guard.check(_write_event(str(target), ""), REGISTRY)
        self.assertFalse(blocked)

    def test_allows_new_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = self._registered(Path(td))  # does not exist
            blocked, _ = guard.check(_write_event(str(target), _doc("001")), REGISTRY)
        self.assertFalse(blocked)

    def test_blocks_dropping_entries(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = self._registered(Path(td))
            target.parent.mkdir(parents=True)
            target.write_text(_doc("001", "002", "003"), encoding="utf-8")
            blocked, reason = guard.check(_write_event(str(target), _doc("001")), REGISTRY)
        self.assertTrue(blocked)
        self.assertIn("D002", reason)
        self.assertIn("D003", reason)

    def test_allows_valid_append(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = self._registered(Path(td))
            target.parent.mkdir(parents=True)
            target.write_text(_doc("001", "002"), encoding="utf-8")
            blocked, _ = guard.check(_write_event(str(target), _doc("001", "002", "003")), REGISTRY)
        self.assertFalse(blocked)

    def test_fails_closed_on_read_error(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = self._registered(Path(td))
            target.mkdir(parents=True)  # a dir -> IsADirectoryError on read
            blocked, reason = guard.check(_write_event(str(target), _doc("001")), REGISTRY)
        self.assertTrue(blocked)
        self.assertIn("could not read", reason)

    def test_empty_registry_short_circuits(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            target = self._registered(Path(td))
            target.parent.mkdir(parents=True)
            target.write_text(_doc("001", "002"), encoding="utf-8")
            blocked, _ = guard.check(_write_event(str(target), ""), [])
        self.assertFalse(blocked)

    def test_check_loads_registry_from_env_when_not_injected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sidecar = root / ".claude" / "loop.append-guard.json"
            sidecar.parent.mkdir(parents=True)
            sidecar.write_text(
                json.dumps([{"suffix": SUFFIX, "id_pattern": SIDECAR_ID_PATTERN}]),
                encoding="utf-8",
            )
            target = self._registered(root)
            target.parent.mkdir(parents=True)
            target.write_text(_doc("001", "002"), encoding="utf-8")
            with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(root)}):
                blocked, reason = guard.check(_write_event(str(target), _doc("001")))
        self.assertTrue(blocked)
        self.assertIn("D002", reason)


class MainTests(unittest.TestCase):
    def test_fails_closed_on_malformed_event(self) -> None:
        with mock.patch.object(sys, "stdin", io.StringIO("not json")), mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(guard.main(), 2)

    def test_emits_deny_decision(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "loop.append-guard.json").write_text(
                json.dumps([{"suffix": SUFFIX, "id_pattern": SIDECAR_ID_PATTERN}]),
                encoding="utf-8",
            )
            target = root / ".claude" / "specs" / "decisions.md"
            target.parent.mkdir(parents=True)
            target.write_text(_doc("001", "002"), encoding="utf-8")
            event = _write_event(str(target), _doc("001"))
            out = io.StringIO()
            with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(root)}), \
                    mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))), \
                    mock.patch.object(sys, "stdout", out):
                rc = guard.main()
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_fails_closed_on_unexpected_internal_error(self) -> None:
        # Belt-and-suspenders: if check() raises for any reason, main must DENY
        # (emit a decision), never let the write through via a non-blocking crash.
        event = _write_event("/x/.claude/specs/decisions.md", _doc("001"))
        out = io.StringIO()

        def _boom(_event: dict) -> tuple[bool, str]:
            raise RuntimeError("simulated internal failure")

        with mock.patch.object(guard, "check", _boom), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))), \
                mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            rc = guard.main()
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allows_when_unconfigured(self) -> None:
        # No CLAUDE_PROJECT_DIR / no sidecar -> no decision emitted (== allow).
        event = _write_event("/anywhere/.claude/specs/decisions.md", _doc("001"))
        out = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))), \
                mock.patch.object(sys, "stdout", out):
            rc = guard.main()
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
