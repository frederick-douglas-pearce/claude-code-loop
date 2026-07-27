#!/usr/bin/env python3
"""Mechanical consistency checks for the markdown/JSON deliverable.

The bulk of this repo is prompt artifacts an agent executes at runtime, so
semantics stay validated by review + dogfooding (CLAUDE.md -> "What this repo
is"). These tests deliberately do **not** attempt that. They cover only the
three couplings that a reader cannot see and a reviewer reliably forgets:

1. the shipped example sidecar still loads through the real ``load_registry``;
2. the ``plugin@marketplace`` identifier hardcoded in prose still matches the
   manifests it is composed from;
3. every ``CAPS`` parameter the engine reads is offered by the ``/init-loop``
   skeleton, so a newly-onboarded repo is never missing a binding.

Each failure here is silent rot in the shipped product, not a style nit.

Stdlib ``unittest`` only -- the guard hook and its tests are stdlib-only by
design (CLAUDE.md -> the append-only guard hook). Run with:

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK_PATH = _REPO_ROOT / "hooks" / "guard_append_only.py"

_EXAMPLE_SIDECAR = _REPO_ROOT / "hooks" / "loop.append-guard.example.json"
_PLUGIN_MANIFEST = _REPO_ROOT / ".claude-plugin" / "plugin.json"
_MARKETPLACE_MANIFEST = _REPO_ROOT / ".claude-plugin" / "marketplace.json"
_HOOKS_MANIFEST = _REPO_ROOT / "hooks" / "hooks.json"

_ENGINE = _REPO_ROOT / "skills" / "dev-loop" / "loop-engine.md"
_SKILL = _REPO_ROOT / "skills" / "dev-loop" / "SKILL.md"
_INIT_LOOP = _REPO_ROOT / "commands" / "init-loop.md"
_README = _REPO_ROOT / "README.md"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard_append_only", _HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_hook()


class ExampleSidecarTests(unittest.TestCase):
    """``hooks/loop.append-guard.example.json`` is documentation-as-code.

    It is the copy-paste template every consuming project starts from, so it
    must stay loadable by the *real* loader -- not by a re-implementation of
    it here. A tightening of ``load_registry``'s validation (as in the
    capture-group check) could otherwise invalidate the shipped example
    silently: the loader fails open, so the only symptom would be a consuming
    project whose guard quietly protects nothing.
    """

    def _load_example(self) -> tuple[list, str]:
        """Load the shipped example through load_registry; return (registry, stderr).

        The loader reads ``<project_dir>/.claude/loop.append-guard.json``, so
        the example is staged at that exact path -- this exercises the real
        code path a consuming repo hits, not a private parsing shortcut.
        """
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / guard.SIDECAR_RELPATH
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(_EXAMPLE_SIDECAR, dest)
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                registry = guard.load_registry(td)
            return registry, stderr.getvalue()

    def test_example_sidecar_loads_as_exactly_one_active_entry(self) -> None:
        registry, stderr = self._load_example()
        self.assertEqual(
            len(registry),
            1,
            f"shipped example sidecar did not yield exactly one active entry; "
            f"loader stderr: {stderr!r}",
        )

    def test_example_sidecar_loads_without_warnings(self) -> None:
        # load_registry fails OPEN on a malformed entry -- it warns and skips.
        # A silent-but-empty registry is the failure mode this catches.
        _, stderr = self._load_example()
        self.assertEqual(stderr, "", f"loader warned on the shipped example: {stderr!r}")

    def test_example_pattern_extracts_a_known_id(self) -> None:
        registry, _ = self._load_example()
        suffix, pattern = registry[0]
        self.assertEqual(suffix, ".claude/specs/decisions.md")
        fixture = "## D001: first decision\n\nbody\n\n## D002-alt: second\n\nbody\n"
        self.assertEqual(pattern.findall(fixture), ["D001", "D002-alt"])

    def test_example_pattern_has_exactly_one_capture_group(self) -> None:
        # The contract load_registry enforces. Asserted directly so a failure
        # names the actual problem instead of surfacing as "zero entries".
        registry, _ = self._load_example()
        self.assertEqual(registry[0][1].groups, 1)


class PluginIdentifierTests(unittest.TestCase):
    """``dev-loop@claude-code-loop`` is composed, then hand-written elsewhere.

    The identifier is derived from two manifests but typed by hand into the
    ``/init-loop`` settings wiring and the README install snippet. A rename
    that misses a call site breaks onboarding silently -- the plugin installs
    and then never activates.
    """

    def _read_json(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:  # pragma: no cover - failure path
            self.fail(f"{path.relative_to(_REPO_ROOT)} is not valid JSON: {e}")

    def test_manifests_parse(self) -> None:
        for path in (_PLUGIN_MANIFEST, _MARKETPLACE_MANIFEST, _HOOKS_MANIFEST):
            with self.subTest(manifest=path.name):
                self.assertIsInstance(self._read_json(path), dict)

    def test_marketplace_entry_matches_the_plugin_manifest(self) -> None:
        plugin_name = self._read_json(_PLUGIN_MANIFEST)["name"]
        listed = [p["name"] for p in self._read_json(_MARKETPLACE_MANIFEST)["plugins"]]
        self.assertIn(
            plugin_name,
            listed,
            "plugin.json 'name' is not listed in marketplace.json 'plugins'",
        )

    def test_composed_identifier_appears_at_every_call_site(self) -> None:
        identifier = "{}@{}".format(
            self._read_json(_PLUGIN_MANIFEST)["name"],
            self._read_json(_MARKETPLACE_MANIFEST)["name"],
        )
        # Both files are user-facing entry points: init-loop.md writes the key
        # into settings.json, README.md is the documented install command.
        for path in (_INIT_LOOP, _README):
            with self.subTest(call_site=path.name):
                self.assertIn(
                    identifier,
                    path.read_text(encoding="utf-8"),
                    f"identifier {identifier!r} derived from the manifests does not "
                    f"appear in {path.relative_to(_REPO_ROOT)}",
                )

    def test_hooks_manifest_points_at_a_script_that_exists(self) -> None:
        raw = _HOOKS_MANIFEST.read_text(encoding="utf-8")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", raw, "hook command must be plugin-root relative")
        for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)", raw):
            with self.subTest(script=rel):
                self.assertTrue(
                    (_REPO_ROOT / rel).is_file(),
                    f"hooks.json references {rel}, which does not exist in the repo",
                )


class CapsVocabularyTests(unittest.TestCase):
    """The engine <-> skeleton binding contract (CLAUDE.md -> three-layer split).

    The engine references config values by ``CAPS`` name only. If it reads a
    name the ``/init-loop`` skeleton does not offer, every newly-onboarded repo
    is missing a binding the engine will look for -- and nothing fails loudly;
    the loop just resolves it to nothing at runtime.

    The check is one-directional on purpose: skeleton-only parameters are fine
    (the skeleton may offer bindings the engine reads indirectly, or ahead of
    an engine change), engine-only parameters are the bug.
    """

    # Names that look like bindings but are not config parameters. Keep this
    # SHORT -- a growing allow-list means the test is being worked around
    # rather than the vocabulary being kept in sync.
    ALLOWED_NON_BINDINGS = frozenset(
        {
            "CLAUDE_PLUGIN_ROOT",  # env var: the installed plugin's root
            "CLAUDE_PROJECT_DIR",  # env var: the consuming repo's root
            "CAPS",  # the meta-term for this convention itself
        }
    )

    # Two shapes, matching how the engine actually writes bindings:
    #   underscore-joined ALLCAPS anywhere (BACKLOG_SOURCE, TEST_CMD, ...)
    #   backticked single-word ALLCAPS of 4+ chars (`VERIFY`)
    # The length floor keeps prose abbreviations (`AC`, `PR`, `CI`) out.
    _UNDERSCORED = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
    _SINGLE_WORD = re.compile(r"`([A-Z]{4,})`")

    def _engine_parameters(self) -> set[str]:
        names: set[str] = set()
        # SKILL.md is scanned alongside loop-engine.md: it restates a subset of
        # the bindings, and a name introduced only there needs the skeleton too.
        for path in (_ENGINE, _SKILL):
            text = path.read_text(encoding="utf-8")
            names.update(self._UNDERSCORED.findall(text))
            names.update(self._SINGLE_WORD.findall(text))
        return names - self.ALLOWED_NON_BINDINGS

    def test_the_extractor_actually_finds_parameters(self) -> None:
        # Guards against the check silently passing because a refactor broke
        # the regexes and the extracted set went empty.
        found = self._engine_parameters()
        self.assertGreater(len(found), 10, f"suspiciously few parameters extracted: {found}")
        self.assertIn("BACKLOG_SOURCE", found)

    def test_every_engine_parameter_is_offered_by_the_init_loop_skeleton(self) -> None:
        skeleton = _INIT_LOOP.read_text(encoding="utf-8")
        missing = sorted(n for n in self._engine_parameters() if n not in skeleton)
        self.assertEqual(
            missing,
            [],
            "the engine reads parameters that /init-loop does not offer: "
            f"{missing}. Add them to the §1 binding table (and the inference "
            "map) in commands/init-loop.md, or add a commented entry to "
            "ALLOWED_NON_BINDINGS if the name is not a config binding.",
        )


if __name__ == "__main__":
    unittest.main()
