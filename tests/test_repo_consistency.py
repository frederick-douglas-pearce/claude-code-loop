#!/usr/bin/env python3
"""Mechanical consistency checks for the markdown/JSON deliverable.

The bulk of this repo is prompt artifacts an agent executes at runtime, so
semantics stay validated by review + dogfooding (CLAUDE.md -> "What this repo
is"). These tests deliberately do **not** attempt that. They cover only the
four couplings that a reader cannot see and a reviewer reliably forgets:

1. the shipped example sidecar still loads through the real ``load_registry``;
2. the ``plugin@marketplace`` identifier hardcoded in prose still matches the
   manifests it is composed from;
3. every ``CAPS`` parameter the engine reads is offered by the ``/init-loop``
   skeleton, so a newly-onboarded repo is never missing a binding;
4. the pipeline's step order, restated in five artifacts, still agrees with
   itself.

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
    """Five restatements of the pipeline's step order, checked against each other.

    The order lives in ``loop-engine.md``'s ``### N. <name>`` headings, is
    restated with numbers in ``SKILL.md``'s arrow chain, and is spelled out
    again -- unnumbered -- in ``plugin.json``'s ``description``, which is
    published with the plugin. Drift there ships.

    Two more restatements were added by #44, both of which #31's renumber
    breaks: ``SKILL.md``'s **frontmatter** ``description`` chain -- the string
    the model reads when deciding whether to invoke the skill, so a behavior
    surface rather than internal prose -- and the engine's ~49 in-prose
    ``step N`` / ``Stages N/M`` cross-references.

    Those three are not string-identical and cannot be made so: the engine has
    13 numbered headings, SKILL.md restates all 13 with numbers, and the
    description gives 11 unnumbered labels -- omitting the two internal steps
    (load/resume, commit/PR) and saying ``review`` where the engine says ``Code
    review``. So correspondence is by normalised word overlap: two labels
    correspond when their content words intersect, and each label binds to its
    *best*-overlapping candidate rather than its first (see ``_assign`` and
    ``test_skill_labels_match_their_engine_headings`` for why first-match
    binding is unsound when two headings share a word).

    **Scope -- what this does NOT guard**, because a green run here is easy to
    over-read as "the renumber is done":

    * The pipeline's *status* vocabulary (the ``queued -> routed -> ...`` chain
      in the ledger format) -- these are ``### N.`` headings only.
    * Whether a step is the *right* thing to do at that point. This is an
      ordering and coupling check, never a semantic one.
    * ``plugin.json`` changing when a step is renumbered or inserted: the
      description carries no numbers and may keep omitting internal steps. Its
      reorderings are caught only *among the labels it lists* -- a swap
      involving a step it omits is invisible here and rests on the SKILL.md
      check.
    * **What a renumber does to the cross-references.** The cross-reference
      check asserts *resolvability only* -- that every referenced N is a real
      heading number. It cannot know that ``step 9`` still means *code review*;
      that is semantics, which this module does not do. Two consequences, both
      aimed at whoever implements #31: a reference that stays in range but now
      points at the wrong step is **not** caught, and a renumber that only
      *adds* steps leaves every existing reference resolvable, so **a green run
      is not evidence the ~49 cross-references were correctly updated.**
    * **What the frontmatter check is sensitive to.** Order and label count
      only. A renumber that preserves the relative order of plan / architect /
      implement / review / merge does not disturb it.
    """

    # `### 9. Code review` -> (9, "Code review"); `### Guardrails` -> not a step.
    _ANY_H3 = re.compile(r"^### (.+)$", re.MULTILINE)
    _NUMBERED_H3 = re.compile(r"^(\d+)\. (.+)$")
    _FENCED_BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
    # The chains in SKILL.md and plugin.json. Only the OPENING is matched by
    # regex; the close is found by counting paren depth, so a parenthesised
    # aside inside a chain ("5 human gate (conditional)") does not silently
    # truncate the parse. The openers require an arrow to be present, so an
    # unrelated earlier paren -- prose in SKILL.md, a different aside in the
    # marketplace copy -- cannot hijack the parse and be reported as drift.
    _SKILL_CHAIN_OPEN = re.compile(r"\(step\s+0\s+[^)]*?→")
    _PLUGIN_CHAIN_OPEN = re.compile(r"\((?=[^()]*->[^()]*->)")

    # Dropped so that "Load or initialize state" and "load/resume" compare on
    # content words. Parenthesised asides are stripped before this applies.
    _STOPWORDS = frozenset({"a", "an", "and", "by", "in", "of", "or", "the", "to"})

    # SKILL.md's YAML frontmatter `description`. Scoped strictly to the
    # frontmatter block: the BODY carries its own numbered chain, and a parser
    # that could reach it would silently check the wrong restatement.
    _FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
    _FM_DESCRIPTION = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
    # An arrow chain of single-token labels. Matching is deliberately narrow so
    # a reword to MULTI-word segments ("plan → architect gate → implement")
    # splits into two matches and trips the exactly-one rule below, rather than
    # silently truncating -- the same failure mode PR #43's review caught in the
    # body-chain parser.
    _ARROW_CHAIN = re.compile(r"[\w./+-]+(?:\s*→\s*[\w./+-]+)+")
    # Pinned, not floored: the frontmatter is a behavior surface, so ANY change
    # to the chain's length should be a deliberate, reviewed edit that updates
    # this constant. Without it, a shortening to `plan→merge` is still one valid
    # chain and still an ordered subsequence -- it would pass while quietly
    # dropping three labels from the guarded surface.
    _EXPECTED_FRONTMATTER_LABELS = 5

    # The engine's in-prose cross-references, in every form it actually uses:
    # `step 9`, `Step 11`, `step-1`, `step 0.1`, `step 0/1`, `steps 0–1`,
    # `Stages 4/7/10`. The trailing run picks up `/`- and dash-separated lists.
    _STEP_REFERENCE = re.compile(
        r"\b(?:[Ss]teps?|[Ss]tages?)[ -](\d+(?:\.\d+)?(?:\s*[/–—-]\s*\d+(?:\.\d+)?)*)"
    )
    _REFERENCE_SEPARATORS = re.compile(r"\s*[/–—-]\s*")
    # Well below the 49 references present when this landed, so ordinary prose
    # edits never trip it, and well above zero, so a regex broken by a reword
    # fails here instead of passing on an empty list. Raising it as the engine
    # grows is fine; lowering it to make a red run green is working around the
    # check (cf. _STOPWORDS, ALLOWED_NON_BINDINGS).
    _MIN_STEP_REFERENCES = 40

    def _balanced_chain(self, text: str, opening, source: str) -> str:
        """Return the contents of the parenthesis `opening` starts, by depth.

        Shared by both chain parsers: the marketplace copy is as entitled to a
        nested aside as SKILL.md is, and hardening only one of them is how the
        plugin-side parser ended up the fragile one.
        """
        self.assertIsNotNone(
            opening,
            f"{source} no longer contains a parenthesised, arrow-separated "
            "pipeline chain; the restatement moved or was reworded, so this "
            "check can no longer verify it against loop-engine.md",
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
        self.assertIsNotNone(end, f"{source}'s pipeline chain has no closing parenthesis")
        return text[opening.start() + 1 : end].replace("\n", " ")

    def _assign(
        self, labels: list[str], engine: list[tuple[int, str]], source: str, ordered: bool
    ) -> None:
        """Bind each label to its BEST-overlapping engine heading, then assert.

        Binding to the *best* match rather than the first non-zero one is what
        makes the word collisions (``Code review``/``Security review``,
        ``Architect gate``/``Human gate``) safe: with first-match binding, a
        label carrying only the shared word latches onto the wrong heading and
        its swapped partner then still fits, so a genuine reversal passes.

        Two failure modes are reported separately, because they call for
        opposite fixes: a label that matches *no* heading anywhere is a wording
        problem, while a label that matches out of position is an ordering
        problem. Collapsing them into one message sends the reader after the
        wrong thing.
        """
        unmatched = [lbl for lbl in labels if not any(self._words(lbl) & self._words(h) for _, h in engine)]
        self.assertEqual(
            unmatched,
            [],
            f"{source} uses step label(s) {unmatched} that share no word with ANY "
            f"loop-engine.md heading. This is a WORDING mismatch, not an ordering "
            f"one -- either reword the label or rename the heading so the two "
            f"artifacts remain mechanically comparable. Engine headings: "
            f"{[h for _, h in engine]}",
        )
        if not ordered:
            return
        cursor = 0
        for label in labels:
            words = self._words(label)
            # Ties resolve to the earliest heading (-i maximised).
            scored = [(len(words & self._words(engine[i][1])), -i, i) for i in range(cursor, len(engine))]
            score, _, index = max(scored, default=(0, 0, len(engine)))
            self.assertGreater(
                score,
                0,
                f"{source} lists {label!r}, but no loop-engine.md heading at or "
                f"after step {cursor} corresponds to it, so the chain is OUT OF "
                f"ORDER. Remaining engine headings: {[h for _, h in engine[cursor:]]}. "
                "NOTE: the walk reports the first label it cannot PLACE, which is "
                "often a downstream casualty rather than the label that actually "
                "moved -- read the whole chain, not just the one named here.",
            )
            cursor = index + 1

    @staticmethod
    def _words(label: str) -> frozenset[str]:
        """Normalise a step label to its content words.

        Parenthesised asides go first -- the engine qualifies headings with
        "(conditional)", "(by route)", "(you, the parent thread)", none of
        which the short restatements carry.
        """
        stripped = re.sub(r"\([^()]*\)", " ", label)
        tokens = re.split(r"[^a-z0-9]+", stripped.lower())
        return frozenset(t for t in tokens if t and t not in PipelineStepOrderTests._STOPWORDS)

    def _engine_steps(self) -> list[tuple[int, str]]:
        """[(number, heading)] in file order, from loop-engine.md.

        Scoped to the pipeline section: fenced blocks are stripped first (the
        engine embeds a ``issue-<N>.plan.md`` template that already carries
        markdown headings), and the scan stops at the first unnumbered ``###``
        after the numbered run -- ``### Escalation rubric`` and the sections
        below it are not pipeline steps.
        """
        text = self._FENCED_BLOCK.sub("", _ENGINE.read_text(encoding="utf-8"))
        steps = []
        for heading in self._ANY_H3.findall(text):
            match = self._NUMBERED_H3.match(heading.strip())
            if match is None:
                if steps:  # the numbered run has ended
                    break
                continue  # not into the pipeline section yet
            steps.append((int(match.group(1)), match.group(2).strip()))
        return steps

    def _skill_steps(self) -> list[tuple[int, str]]:
        """[(number, label)] in file order, from SKILL.md's arrow chain."""
        text = _SKILL.read_text(encoding="utf-8")
        chain = self._balanced_chain(text, self._SKILL_CHAIN_OPEN.search(text), "SKILL.md")
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

    def _skill_frontmatter_labels(self) -> list[str]:
        """[label] in order, from SKILL.md's frontmatter `description`.

        Restatement #4, and the only one that is not internal prose: this
        string is what the model reads when deciding whether to invoke the
        skill, so drift here changes behavior rather than documentation.
        """
        text = _SKILL.read_text(encoding="utf-8")
        frontmatter = self._FRONTMATTER.match(text)
        self.assertIsNotNone(
            frontmatter,
            "SKILL.md no longer opens with a '---' YAML frontmatter block, so the "
            "model-facing description cannot be located or checked.",
        )
        description = self._FM_DESCRIPTION.search(frontmatter.group(1))
        self.assertIsNotNone(
            description,
            "SKILL.md's frontmatter has no 'description:' line. It is the string "
            "the model reads when deciding to invoke the skill; this check cannot "
            "verify its pipeline chain against loop-engine.md without it.",
        )
        chains = self._ARROW_CHAIN.findall(description.group(1))
        self.assertEqual(
            len(chains),
            1,
            f"expected exactly one '→'-separated pipeline chain in SKILL.md's "
            f"frontmatter description, found {len(chains)}: {chains}. The chain "
            "must stay a single run of single-token labels "
            "('plan→architect→implement→review→merge') -- multi-word segments "
            "split the parse in two, which would silently shrink what is checked.",
        )
        return [segment.strip() for segment in chains[0].split("→")]

    def _step_references(self) -> list[tuple[str, int]]:
        """[(literal, step number)] for every in-prose cross-reference.

        Fenced blocks are deliberately NOT stripped here, unlike
        ``_engine_steps``: that one strips them because the embedded
        ``issue-<N>.plan.md`` template contains markdown headings that are not
        pipeline steps, whereas the template's own "see step 3" IS a real
        cross-reference -- it ships into every plan file the loop writes.
        """
        text = _ENGINE.read_text(encoding="utf-8")
        references = []
        for run in self._STEP_REFERENCE.findall(text):
            for token in self._REFERENCE_SEPARATORS.split(run):
                # `0.1` is a sub-item of step 0; only the step resolves here.
                references.append((token, int(token.split(".")[0])))
        return references

    def _plugin_labels(self) -> list[str]:
        """[label] in order, from plugin.json's description. No numbers."""
        description = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))["description"]
        match = self._PLUGIN_CHAIN_OPEN.search(description)
        chain = self._balanced_chain(description, match, "plugin.json's description")
        return [seg.strip() for seg in chain.split("->") if seg.strip()]

    def test_the_extractors_actually_find_steps(self) -> None:
        # Guards against the whole class passing vacuously because a reword
        # broke a regex and a parsed list went empty (cf.
        # test_the_extractor_actually_finds_parameters).
        engine, skill, plugin = self._engine_steps(), self._skill_steps(), self._plugin_labels()
        self.assertGreaterEqual(len(engine), 12, f"suspiciously few engine headings: {engine}")
        self.assertGreaterEqual(len(skill), 12, f"suspiciously few SKILL.md steps: {skill}")
        self.assertGreaterEqual(len(plugin), 10, f"suspiciously few plugin.json labels: {plugin}")
        references = self._step_references()
        self.assertGreaterEqual(
            len(references),
            self._MIN_STEP_REFERENCES,
            f"suspiciously few loop-engine.md step cross-references: "
            f"{len(references)} < {self._MIN_STEP_REFERENCES}. Either the engine "
            "shrank dramatically or _STEP_REFERENCE no longer matches the form the "
            "engine writes -- in which case this check is passing vacuously.",
        )
        # _skill_frontmatter_labels asserts its own shape; calling it here keeps
        # the vacuity guard honest about all five restatements.
        self._skill_frontmatter_labels()

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
        """Positional argmax, checked in BOTH directions.

        Each label must overlap its positional heading at least as well as any
        other heading, *and* each heading must overlap its positional label at
        least as well as any other label. The two-sided form is what allows the
        comparison to be non-strict: requiring a strict win would fail an
        order-preserving reword whose overlap merely ties with a word-colliding
        neighbour ("human gate" -> "approval gate" ties with "Architect gate"
        on ``gate``), reporting an ordering problem that does not exist. The
        reverse pass is what keeps every genuine swap caught anyway.
        """
        engine = self._engine_steps()
        skill = self._skill_steps()
        engine_words = [self._words(h) for _, h in engine]
        label_words = [self._words(lbl) for _, lbl in skill]
        for index, (number, label) in enumerate(skill):
            if index >= len(engine):  # covered by the number-sequence test
                break
            with self.subTest(step=number, label=label):
                fwd = [len(label_words[index] & w) for w in engine_words]
                best_other = max(fwd[:index] + fwd[index + 1 :], default=0)
                self.assertGreaterEqual(
                    fwd[index],
                    best_other,
                    f"SKILL.md step {number} {label!r} matches engine step "
                    f"{fwd.index(best_other)} better than the heading at its own "
                    f"position ('{engine[index][1]}', overlap {fwd[index]} vs "
                    f"{best_other}). The two artifacts disagree about the "
                    "pipeline's order or about what a step is called.",
                )
                rev = [len(engine_words[index] & w) for w in label_words]
                best_other = max(rev[:index] + rev[index + 1 :], default=0)
                self.assertGreaterEqual(
                    rev[index],
                    best_other,
                    f"loop-engine.md step {number} ('{engine[index][1]}') matches "
                    f"SKILL.md's label at position {rev.index(best_other)} better "
                    f"than its own ({label!r}, overlap {rev[index]} vs "
                    f"{best_other}). The two artifacts disagree about the "
                    "pipeline's order.",
                )

    def test_plugin_description_is_an_ordered_subsequence_of_the_engine(self) -> None:
        """The marketplace copy may omit internal steps, never reorder them.

        Each label binds to its *best*-overlapping remaining heading, not the
        first one it overlaps at all. First-match binding is unsound here: with
        ``Code review``/``Security review`` sharing ``review``, a label carrying
        only the shared word latches onto the wrong heading and its swapped
        partner still fits, so a reversed chain passes.
        """
        self._assign(
            self._plugin_labels(),
            self._engine_steps(),
            "plugin.json's published description",
            ordered=True,
        )

    def test_skill_frontmatter_chain_has_its_full_label_count(self) -> None:
        """A chain that SHORTENS is still a valid ordered subsequence.

        Separated from the ordering check because the two fail for opposite
        reasons: `plan→merge` passes _assign happily -- it is a genuine
        subsequence -- while silently dropping architect/implement/review from
        the guarded surface. Only a pinned count catches that.
        """
        labels = self._skill_frontmatter_labels()
        self.assertEqual(
            len(labels),
            self._EXPECTED_FRONTMATTER_LABELS,
            f"SKILL.md's frontmatter chain now lists {len(labels)} labels "
            f"({labels}), not {self._EXPECTED_FRONTMATTER_LABELS}. If the chain "
            "was deliberately reworded, update _EXPECTED_FRONTMATTER_LABELS in "
            "the same change -- the count is pinned because a SHORTER chain is "
            "still an ordered subsequence and would otherwise pass while checking "
            "less.",
        )

    def test_skill_frontmatter_chain_is_an_ordered_subsequence_of_the_engine(self) -> None:
        """Restatement #4, checked by the same rule as plugin.json's.

        The frontmatter omits internal steps exactly as the marketplace
        description does, so the subsequence matcher is the right one: it must
        never REORDER the steps it does list. Same caveat as there -- a swap
        involving a step the chain omits is invisible to this check.
        """
        self._assign(
            self._skill_frontmatter_labels(),
            self._engine_steps(),
            "SKILL.md's frontmatter description",
            ordered=True,
        )

    def test_every_engine_step_reference_resolves_to_a_real_heading(self) -> None:
        """Restatement #5: ~49 in-prose `step N` refs. RESOLVABILITY ONLY.

        This asserts that every referenced N is a real heading number -- not
        that it still points at the step it meant. `step 9` continuing to
        resolve after a renumber says nothing about whether 9 is still *Code
        review*; that is semantics, and CLAUDE.md is explicit that this module
        must not grow into a semantic test of the engine. Sub-item suffixes
        (the `.1` in `step 0.1`) are likewise not resolved -- only the step.

        So: this catches a renumber that leaves references DANGLING (steps
        removed, or the run rebased off zero). It does NOT catch a renumber
        that only adds steps, nor a reference that shifted meaning while
        staying in range.
        """
        valid = {number for number, _ in self._engine_steps()}
        dangling = sorted({literal for literal, number in self._step_references() if number not in valid})
        self.assertEqual(
            dangling,
            [],
            f"loop-engine.md cross-references step(s) {dangling} that no '### N.' "
            f"heading defines (headings are {sorted(valid)}). A renumber must "
            "update the in-prose references in the same change. NOTE: this check "
            "is resolvability-only -- references that stay in range but now point "
            "at the wrong step are NOT caught here.",
        )


if __name__ == "__main__":
    unittest.main()
