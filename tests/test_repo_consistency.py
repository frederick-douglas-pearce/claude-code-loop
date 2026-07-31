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
   skeleton, so a newly-onboarded repo is never missing a binding;
4. the pipeline's step order, restated in three parseable artifacts, still
   agrees with itself.

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


class PipelineStepOrderTests(unittest.TestCase):
    """The pipeline's step order is written down three times; nothing else catches drift.

    The order lives in ``loop-engine.md``'s ``### N. <name>`` headings, is
    restated with numbers in ``SKILL.md``'s arrow chain, and is spelled out
    again -- unnumbered -- in ``plugin.json``'s ``description``, which is the
    **published marketplace copy** a prospective user reads before installing.
    Drift there ships.

    **Scope -- what this does and does not guard.** It guards step *heading
    numbering* and the engine<->SKILL label/number coupling. It does **not**
    cover the pipeline's *status* vocabulary (``in-acceptance`` and friends
    live in the ledger format, not in ``### N.`` headings), and it does **not**
    force ``plugin.json`` to change when a step is renumbered or inserted --
    the description carries no numbers and is matched loosely (below). This is
    an ordering/coupling check, never a check on whether a step is *right*.

    The three sources are not string-identical and cannot be made so: the
    engine has 13 numbered headings, SKILL.md restates all 13 with numbers, and
    the marketplace description gives 11 unnumbered labels -- omitting the two
    internal steps (load/resume, commit/PR) and saying ``review`` where the
    engine says ``Code review``. So correspondence is by normalised word
    overlap, at two different strictnesses:

    * **SKILL.md gets positional-argmax uniqueness.** A label's overlap with
      its positional counterpart must be strictly greater than its overlap
      with every other heading. Mere intersection is too weak: ``Code review``
      / ``Security review`` share ``review`` and ``Architect gate`` / ``Human
      gate`` share ``gate``, so a swap of the pair would be caught only by the
      accident that SKILL.md currently abbreviates step 10 to bare
      ``security``. Harmonising that to ``security review`` -- a plausible
      copy-edit -- would silently blind the check for exactly the swaps it
      exists to catch. Argmax catches them regardless of wording.
    * **plugin.json gets an order-preserving subsequence.** Deliberately
      loose: it is marketing copy, and requiring it to enumerate
      ``load/resume`` for the test's convenience would invert the dependency.
      Reorderings are still caught, because relocating a label leaves a
      distinctive one unmatchable.

    Failure messages name the source, the step index, and both labels. That
    matters more here than elsewhere: an engine 9/10 swap surfaces at position
    **10**, not at the 9 the human edited.
    """

    # `### 9. Code review` -> (9, "Code review")
    _ENGINE_HEADING = re.compile(r"^### (\d+)\. (.+)$", re.MULTILINE)
    # SKILL.md's parenthesised chain: "(step 0 load/resume -> 1 select -> ...)".
    # Only the opening is matched by regex; the close is found by counting
    # depth, so a parenthesised aside inside the chain ("5 human gate
    # (conditional)") does not silently truncate the parse to six steps.
    _SKILL_CHAIN_OPEN = re.compile(r"\(step\s+0\b", re.DOTALL)
    # plugin.json's parenthesised chain, the only parenthesis holding arrows.
    _PLUGIN_CHAIN = re.compile(r"\(([^()]*->[^()]*)\)")

    # Dropped so that "Load or initialize state" and "load/resume" compare on
    # content words. Parenthesised asides are stripped before this applies.
    _STOPWORDS = frozenset({"a", "an", "and", "by", "in", "of", "or", "the", "to"})

    @staticmethod
    def _words(label: str) -> frozenset:
        """Normalise a step label to its content words.

        Parenthesised asides go first -- the engine qualifies headings with
        "(conditional)", "(by route)", "(you, the parent thread)", none of
        which the short restatements carry.
        """
        stripped = re.sub(r"\([^()]*\)", " ", label)
        tokens = re.split(r"[^a-z0-9]+", stripped.lower())
        return frozenset(t for t in tokens if t and t not in PipelineStepOrderTests._STOPWORDS)

    def _engine_steps(self) -> list:
        """[(number, heading)] in file order, from loop-engine.md."""
        text = _ENGINE.read_text(encoding="utf-8")
        return [(int(n), h.strip()) for n, h in self._ENGINE_HEADING.findall(text)]

    def _skill_steps(self) -> list:
        """[(number, label)] in file order, from SKILL.md's arrow chain."""
        text = _SKILL.read_text(encoding="utf-8")
        opening = self._SKILL_CHAIN_OPEN.search(text)
        self.assertIsNotNone(
            opening,
            "SKILL.md no longer contains a parenthesised pipeline chain starting "
            "'(step 0 ...'; the restatement moved or was reworded, so this check "
            "can no longer verify it against loop-engine.md",
        )
        depth, end = 0, None
        for i in range(opening.start(), len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        self.assertIsNotNone(
            end, "SKILL.md's '(step 0 ...' chain has no matching closing parenthesis"
        )
        chain = text[opening.start() + 1 : end].replace("\n", " ")
        steps = []
        for segment in chain.split("→"):
            segment = segment.strip()
            # The first segment carries a leading "step " ordinal marker.
            segment = re.sub(r"^step\s+", "", segment)
            m = re.match(r"(\d+)\s+(.+)$", segment)
            self.assertIsNotNone(
                m,
                f"SKILL.md chain segment {segment!r} is not '<number> <label>'. The "
                "chain must stay a '→'-separated list of '<number> <label>' steps.",
            )
            steps.append((int(m.group(1)), m.group(2).strip()))
        return steps

    def _plugin_labels(self) -> list:
        """[label] in order, from plugin.json's description. No numbers."""
        description = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))["description"]
        match = self._PLUGIN_CHAIN.search(description)
        self.assertIsNotNone(
            match,
            "plugin.json's description no longer contains a parenthesised "
            "'->'-separated step chain; the published marketplace copy changed "
            "shape and is no longer pinned to the engine's step order",
        )
        return [seg.strip() for seg in match.group(1).split("->") if seg.strip()]

    def test_the_extractors_actually_find_steps(self) -> None:
        # Guards against the whole class passing vacuously because a reword
        # broke a regex and a parsed list went empty (cf.
        # test_the_extractor_actually_finds_parameters).
        engine, skill, plugin = self._engine_steps(), self._skill_steps(), self._plugin_labels()
        self.assertGreaterEqual(len(engine), 12, f"suspiciously few engine headings: {engine}")
        self.assertGreaterEqual(len(skill), 12, f"suspiciously few SKILL.md steps: {skill}")
        self.assertGreaterEqual(len(plugin), 10, f"suspiciously few plugin.json labels: {plugin}")

    def test_engine_headings_are_numbered_contiguously_from_zero(self) -> None:
        numbers = [n for n, _ in self._engine_steps()]
        expected = list(range(len(numbers)))
        self.assertEqual(
            numbers,
            expected,
            "loop-engine.md's '### N.' headings must run 0, 1, 2, ... with no gaps, "
            "duplicates, or reordering. Starting at 0 is intentional: step 0 is "
            f"load/resume. Found {numbers}.",
        )

    def test_skill_restates_the_engine_step_numbers_exactly(self) -> None:
        engine = [n for n, _ in self._engine_steps()]
        skill = [n for n, _ in self._skill_steps()]
        self.assertEqual(
            skill,
            engine,
            "SKILL.md's pipeline chain does not restate loop-engine.md's step "
            f"numbers. SKILL.md has {skill}, the engine has {engine}. Renumbering "
            "the pipeline must update both artifacts in the same change.",
        )

    def test_skill_labels_match_their_engine_headings(self) -> None:
        """Positional-argmax uniqueness -- see the class docstring.

        Asserting the *best-overlapping* heading is the positional one (not
        merely that they overlap) is what makes a Code-review/Security-review
        or Architect-gate/Human-gate swap detectable no matter how either side
        abbreviates.
        """
        engine = self._engine_steps()
        engine_words = [(n, h, self._words(h)) for n, h in engine]
        for index, (number, label) in enumerate(self._skill_steps()):
            if index >= len(engine_words):  # covered by the number-sequence test
                break
            with self.subTest(step=number, label=label):
                scores = [(len(self._words(label) & w), n, h) for n, h, w in engine_words]
                own = scores[index]
                best_other = max(scores[:index] + scores[index + 1 :], default=(0, -1, ""))
                self.assertGreater(
                    own[0],
                    best_other[0],
                    f"SKILL.md step {number} {label!r} does not best-match the engine "
                    f"heading at that position ('{engine[index][1]}', overlap "
                    f"{own[0]}); it matches engine step {best_other[1]} "
                    f"('{best_other[2]}') at least as well (overlap {best_other[0]}). "
                    "The two artifacts disagree about the pipeline's order or "
                    "about what a step is called.",
                )

    def test_plugin_description_is_an_ordered_subsequence_of_the_engine(self) -> None:
        """The marketplace copy may omit internal steps, never reorder them.

        Greedy earliest-match is exact for the subsequence-exists predicate,
        so a failure here is a genuine order violation, not an artifact of the
        matching strategy.
        """
        engine = self._engine_steps()
        labels = self._plugin_labels()
        cursor = 0
        for label in labels:
            words = self._words(label)
            start = cursor
            while cursor < len(engine) and not (words & self._words(engine[cursor][1])):
                cursor += 1
            self.assertLess(
                cursor,
                len(engine),
                f"plugin.json's published description lists {label!r}, but no "
                f"loop-engine.md step heading at or after step {start} corresponds "
                f"to it. Remaining engine headings: "
                f"{[h for _, h in engine[start:]]}. The marketplace copy and the "
                "engine disagree about the pipeline's order. NOTE: a subsequence "
                "walk reports the first label it cannot PLACE, which is often a "
                "downstream casualty rather than the label that actually moved — "
                "read the whole chain, not just the one named here.",
            )
            cursor += 1


if __name__ == "__main__":
    unittest.main()
