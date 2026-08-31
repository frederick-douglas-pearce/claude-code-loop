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
4. the pipeline's step order, still restated in several artifacts, agrees with
   itself. (#113 removed one of them -- ``commands/init-loop.md``'s
   ``engine step N`` citations, which now name gates instead of numbering them,
   because that file's skeleton ships into repos no release can reach.)

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
            "ALLOWED_NON_BINDINGS if the name is not a config binding. NOTE: "
            "this reads the WHOLE file, so an inference-map row alone satisfies "
            "it while an onboarded repo still gets no binding row -- see #76.",
        )


class PipelineStepOrderTests(unittest.TestCase):
    """The pipeline's step order, restated in several artifacts and checked
    against itself.

    The order lives in ``loop-engine.md``'s ``### N. <name>`` headings, is
    restated with numbers in ``SKILL.md``'s arrow chain, and is spelled out
    again -- unnumbered -- in ``plugin.json``'s ``description``, which is
    published with the plugin. Drift there ships.

    Two more restatements were added by #44, both of which #31's renumber
    breaks: ``SKILL.md``'s **frontmatter** ``description`` chain -- the string
    the model reads when deciding whether to invoke the skill, so a behavior
    surface rather than internal prose -- and the engine's in-prose ``step N``
    / ``Stages N/M`` cross-references: **179 reference sites, 182 numbers** once
    ``/``- and dash-separated runs are expanded. This grep finds 175 of the 179::

        grep -oE '[Ss]teps?[ -][0-9]|[Ss]tages?[ -][0-9]' \\
            skills/dev-loop/loop-engine.md | wc -l

    The ones it misses are line-wrapped -- which is the point: a one-line grep
    cannot see them, ``_STEP_REFERENCE``'s newline branch can, and before review
    caught it neither could. (Deliberately not enumerated, and not counted: this
    sentence carried a literal list and an exact count, and both went stale on
    essentially every structural edit to the engine.)

    **There was a sixth, and #113 removed it.** ``commands/init-loop.md``'s
    ``(engine step 8)`` and ``engine step 6`` skeleton rows -- the first added by
    #10 (as ``engine step 9``, rotated by #31), the second by #39, and both
    guarded from #45 -- were the only restatement that shipped into repos this plugin cannot
    reach, since ``/init-loop`` copies that skeleton verbatim into each
    newly-onboarded repo's ``loop.config.md``. That made them correct only until
    the next renumber, after which they were stranded in every config generated
    in the meantime, uncorrectable by any release. They now cite gates by NAME,
    and ``test_init_loop_md_contains_no_engine_step_number`` pins the file at
    zero engine-anchored step numbers so none returns. (Its own numbering is
    untouched -- those are that file's onboarding steps, not the engine's.) The
    asymmetry that motivated the guard is unchanged and still governs: what
    lands in the skeleton is unreachable, so it carries a higher bar than the
    same wording in the engine.

    The original three are not string-identical and cannot be made so: the engine has
    13 numbered headings, SKILL.md restates all 13 with numbers, and the
    description gives 12 unnumbered labels -- omitting the one internal step
    (load/resume) and saying ``review`` where the engine says ``Code
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
      heading number. It cannot know that ``step 8`` still means *code review*;
      that is semantics, which this module does not do. It fires when a
      reference goes **out of range** -- whether because someone edited it to a
      number no heading defines, or because the heading run shrank or was
      rebased off zero. Stated bluntly, for whoever implements #31: **inserting
      a step mid-pipeline and renumbering everything after it leaves all 182
      numbers (across 179 sites)
      references pointing at the wrong step with the whole suite green.** A
      green run is not evidence the cross-references were correctly renumbered.
    * **Consumer configs.** Every onboarded repo's ``.claude/loop.config.md``
      carries step references of its own, and those files are outside the
      shipped plugin and outside every check here. #113 stops the *generator*
      seeding new ones -- the only end of that pipe this repo owns -- but a
      green run still says nothing about any config already in the field, nor
      about the hand-written references those files acquired on their own. (No
      per-repo tally here: the one this bullet used to carry counted a set that
      changes without any edit to this repo.)
    * **What the frontmatter check is sensitive to.** Order, label count, and
      that each label still word-overlaps some engine heading. A renumber that
      preserves the relative order of the steps the chain names does not
      disturb it. Nor does a same-length RELABEL that stays ordered: swapping
      ``review`` out for ``route`` still binds (to ``2. Triage / route``) and
      still passes, while quietly dropping review from the model-facing
      description. Pinning the label *set* would catch that, at the cost of
      failing every legitimate reword; the count pin is the compromise.
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
    # body-chain parser. Known false-failure, accepted: adding a SECOND,
    # unrelated arrow chain to the description (e.g. a status chain
    # "queued→routed→done") also trips the rule, though nothing has drifted.
    # That is the fail-safe direction -- a loud red run whose message says what
    # to do, rather than a parser guessing which chain is the pipeline one.
    _ARROW_CHAIN = re.compile(r"[\w./+-]+(?:\s*→\s*[\w./+-]+)+")
    # Pinned, not floored: the frontmatter is a behavior surface, so ANY change
    # to the chain's length should be a deliberate, reviewed edit that updates
    # this constant. Without it, a shortening to `plan→merge` is still one valid
    # chain and still an ordered subsequence -- it would pass while quietly
    # dropping three labels from the guarded surface.
    _EXPECTED_FRONTMATTER_LABELS = 5

    # The engine's in-prose cross-references, in every form it actually uses:
    # `step 8`, `Step 11`, `step-1`, `step 0.1`, `step 0/1`, `steps 0–1`,
    # `Stages 4/9`. The trailing run picks up `/`- and dash-separated lists.
    #
    # The newline branch is load-bearing, not defensive: the engine is
    # hard-wrapped, and FOUR references sit astride a wrap today ("(step\n   1)",
    # "(step\n10)", "step\n11" and "step\n9"). A separator of plain `[ -]` silently missed them --
    # found by review, and exactly the invisible-coverage failure this check
    # exists to prevent.
    #
    # Separators inside a run are NOT space-padded, deliberately. Allowing
    # `\s*` there made an ordinary prose aside -- "(step 12 — 40 lines max)" --
    # parse as a run of 12 and 40 and report a dangling "step 40" nobody wrote.
    # All three real runs (`0–1`, `0/1`, `4/9`) are tight, so the padding
    # bought nothing and cost a false failure.
    _STEP_REFERENCE = re.compile(
        r"\b(?:[Ss]teps?|[Ss]tages?)(?:[ -]|[ \t]*\n[ \t]*)"
        r"(\d+(?:\.\d+)?(?:[/–—-]\d+(?:\.\d+)?)*)"
    )
    _REFERENCE_SEPARATORS = re.compile(r"[/–—-]")

    # `commands/init-loop.md`: the matcher behind the zero-step-numbers rule.
    # (This was "restatement #6" until #113 removed it -- the file must now
    # contain no engine step number at all, so this matcher's job changed from
    # finding the references to proving there are none.)
    #
    # Anchored on the literal "engine" because that file is thick with step
    # references that are its OWN onboarding steps (`Step 0` .. `Step 8`), and
    # every number they carry is also a real engine heading -- so pointing
    # _STEP_REFERENCE at it would match all of them and report a large number
    # where the answer must be zero. The anchor is what does the
    # discrimination; note it does so WITHOUT an allow-list, which is the point
    # (cf. _STOPWORDS, ALLOWED_NON_BINDINGS). No tally of either set is given:
    # a figure here strands on the next rewrite of that file, which is what
    # happened to the pair this comment used to carry.
    #
    # Everything after the anchor mirrors _STEP_REFERENCE's NUMBER handling
    # exactly -- same separator class (so `engine step-9` matches), same `.N`
    # sub-item form, same tight `/`- and dash-separated run tail. Both forms are
    # ones the engine itself writes: 8 hyphenated (`step-0`, `step-1`, `step-3`,
    # `step-5`, `step-0.1`) and 8 sub-item (`step 0.1`, `step 0.3`), so an editor
    # of this file is reading them next door. An unmatched form is the worst
    # failure available here: not merely unguarded but invisible to the pin
    # below, which only moves when a MATCHED site appears or disappears.
    #
    # One narrowing remains, deliberately: the noun is `[Ss]teps?` only, not the
    # sibling's `(?:[Ss]teps?|[Ss]tages?)`. This file has no `stage N` form and
    # the engine's two are internal cross-references, not skeleton content.
    #
    # The one addition is the possessive (`the engine's step 9`) -- 4 of the 6
    # engine-anchored references across the three live consumer configs are
    # possessive (including agentfluent's only one), so it is what a future
    # editor of this file is likely to write.
    #
    # Since #113 no branch has a live instance: the file is pinned at ZERO, so
    # nothing in it exercises this pattern. test_the_init_loop_matcher_is_alive
    # is therefore the only proof the matcher is not wholly dead; a narrowing
    # that drops one branch is not caught anywhere and rests on review.
    # The wrap branch tolerates markdown's blockquote continuation marker. It
    # did not until #113's own mutation pass found the hole: init-loop.md is
    # hard-wrapped AND blockquoted -- the shipped skeleton's opening
    # admonitions are `>`-prefixed and wrapped -- so `engine's` / `> step 8`
    # split across two such lines sailed past the matcher while sitting in the
    # exact region copied into every onboarded repo. (Deliberately no count of
    # those lines, per the no-tally rule above: it strands on the next rewrap,
    # and "continuation" has two defensible readings that disagree.) The branch
    # was added speculatively, with no live instance; what it did not
    # anticipate was the prefix this file's own format puts before a continued
    # line. Not an allow-list of phrasings (cf. ALLOWED_NON_BINDINGS) --
    # markdown has one blockquote marker, so this is a closed structural set,
    # and widening it against a pin of ZERO can only turn the suite red.
    #
    # The trade, disclosed: `engine` ending a line and `Step <digit>` opening
    # the next match across it, and since this change across a `>` prefix too.
    # Only the prefixed form is new -- the bare-newline one predates it, so
    # reverting this branch does not close the disclosure. Where the two are
    # merely adjacent prose rather than a citation that is a false positive,
    # reachable by rewrapping this file -- and it fails RED, the safe
    # direction, though the message will prescribe naming the gate when the
    # real fix is the rewrap.
    # Separating "engine ends a clause" from "engine anchors a citation" is
    # semantics, not a coupling, so it is left as is.
    _INIT_LOOP_STEP_REFERENCE = re.compile(
        r"\b[Ee]ngine(?:'s|’s)?(?:[ \t]+|[ \t]*\n[ \t]*(?:>[ \t]*)*)[Ss]teps?"
        r"(?:[ -]|[ \t]*\n[ \t]*(?:>[ \t]*)*)(\d+(?:\.\d+)?(?:[/–—-]\d+(?:\.\d+)?)*)"
    )
    # ZERO, and zero is the whole assertion: init-loop.md must cite gates by
    # NAME, never by step number. #113 took it 2 -> 0 by rewriting the two
    # skeleton rows ("the code-review gate", "the engine's implement step").
    #
    # Why zero rather than a small pin. The skeleton is copied verbatim into
    # each onboarded repo's .claude/loop.config.md -- a file no release, no CI
    # check, no /init-loop re-run and no re-install ever reaches. A number
    # written there is correct only until the next renumber, after which it is
    # stranded in every config generated in the meantime. A gate NAME survives a
    # renumber. The rule covers the surrounding prose too, which does not ship:
    # a rule with an exception is one a later edit migrates into.
    #
    # This counts reference SITES, not numbers, so a run form (`engine steps
    # 9/10`) would be one. An illustrative example must still be written
    # `engine step N`, with a letter -- a digit inflates the pin, which is a
    # mistake #113 made in its own replacement note and caught by running this.
    #
    # It counts across the WHOLE file, which is what let the skeleton-position
    # check go: skeleton is a subset of file, so file == 0 already proves
    # skeleton == 0. That removed the `~~~markdown` span matcher with it -- the
    # instrument CLAUDE.md calls fragile, defeated four times on #39's PR.
    #
    # A pin, not a floor: at zero nothing can drift up unnoticed. Zero cannot
    # detect a dead matcher, though -- a broken regex and a clean file both
    # report 0 -- so liveness is asserted separately in
    # test_the_init_loop_matcher_is_alive, and deleting that makes this vacuous.
    #
    # The `engine` anchor is load-bearing: without it the matcher would find
    # this file's OWN onboarding `Step N` headings, every number also a real
    # engine heading, and report a large number instead of zero. No tally of
    # either set is stated -- a figure here strands on the next rewrite, which
    # is exactly what happened to the one this comment used to carry.
    #
    # If this is EVER raised above zero, restore a resolvability check with it:
    # the one #113 deleted was permanently vacuous only while the count is 0.
    _EXPECTED_INIT_LOOP_STEP_REFERENCES = 0
    # Well below the 182 numbers currently present (179 reference sites,
    # some listing several), so ordinary prose edits never trip it, and well
    # above zero, so a regex broken by a reword fails here instead of passing on
    # an empty list. The headroom is a deliberate choice, not a
    # measurement -- stated without a figure on purpose, since a count here
    # goes stale on any edit that adds a reference: it was 15 when 40 was
    # picked, and 40 has not been revisited since
    # -- and note its cost: a reword that breaks only PART of the
    # matcher (say, `Stages 4/9` -> `Stages 4 and 9`, a form this regex
    # does not match) drops a few numbers and still clears the floor. Raising
    # this as the engine grows is fine; lowering it to make a red run green is
    # working around the check (cf. _STOPWORDS, ALLOWED_NON_BINDINGS).
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
        self,
        labels: list[str],
        engine: list[tuple[int, str]],
        source: str,
        ordered: bool,
        latest_tie: bool = False,
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
            # Ties resolve to the earliest heading (-i maximised) by default;
            # `latest_tie` flips that to the LAST equally-good heading. Which is
            # right depends on whether the chain collapses several headings into
            # one label -- see the two callers.
            tie = (lambda i: i) if latest_tie else (lambda i: -i)
            scored = [
                (len(words & self._words(engine[i][1])), tie(i), i) for i in range(cursor, len(engine))
            ]
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
            "split the parse in two, which would silently shrink what is checked. "
            "If you deliberately added a SECOND, unrelated arrow chain to the "
            "description, this parser needs a way to tell them apart -- widening "
            "_ARROW_CHAIN to just take the first match is not it. If the count "
            "is 0 and the chain looks fine, check whether the description was "
            "reflowed onto several lines: only the first is read.",
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
        # the vacuity guard honest about every restatement it covers.
        self._skill_frontmatter_labels()

    def test_the_init_loop_matcher_is_alive(self) -> None:
        """``_INIT_LOOP_STEP_REFERENCE`` still matches, and still needs its anchor.

        **Its own test, not a clause in the omnibus vacuity check above.** That
        check opens with four ``assertGreaterEqual``s, any of which
        short-circuits the rest -- and the guard this replaces was a clause
        inside it, so it could be skipped without ever running.

        **Why a fixture rather than the live file.** The old guard floored
        ``commands/init-loop.md`` at >=1 real reference. #113 removed them all --
        that file must now contain ZERO -- so a live-file floor is
        unsatisfiable, and the pin it protected became a pin at 0. That is the
        trap: a dead matcher and a clean file both report 0, so without this
        ``test_init_loop_md_contains_no_engine_step_number`` could never fail.
        Nothing else exercises the pattern, which makes the positive
        assertions below the load-bearing ones.

        **What this does NOT do, stated because two review rounds have now
        turned on it.** It does not verify the matcher's individual alternation
        branches. A narrowing that drops one may or may not pass this test, and
        which ones do is **review's to own**, exactly as the bare ``step N``
        gap in ``commands/init-loop.md``'s maintainer note is. **No list of the
        uncovered narrowings is given here, deliberately.** The two fixtures
        pin the forms they literally contain, and which branches that reaches
        is an artifact of the two strings -- change a string and the set moves
        silently. A list would be stale on the next such edit, and this one was
        already: it named the possessive and the second newline position as
        uncovered, and round 5's mutations found the current fixtures catch
        both. Read the fixture strings, not a summary of them. An
        earlier version of this test carried a fixture per branch and claimed to
        cover them all; a fresh checker defeated that claim twice, because
        detecting a narrowing means naming the form narrowed away, and that list
        has no end.

        **Where the boundary now sits, and why it moved once.** Two positive
        fixtures: the canonical same-line form, and one blockquote-continued
        form. The second is here because markdown's blockquote marker is a
        property of the FORMAT this guard scans, not a phrasing choice -- a
        closed set of one, where the phrasing set is open. It is also the only
        branch added in response to a located, demonstrated hole rather than to
        speculation, and #113's own mutation pass showed the suite stayed green
        with that branch reverted. That is the line: a fixture for a structural
        property of the format, never one per phrasing variant. **Do not grow
        this past it** -- a third fixture is the earlier version returning.
        Reaching the dangerous state still takes two edits -- narrow the regex,
        *then* write the variant into a file whose note forbids writing it at
        all.

        It calls the real compiled pattern, so it cannot pass by restating its
        own expected answer.
        """
        self.assertEqual(
            self._INIT_LOOP_STEP_REFERENCE.findall("see engine step 8 for details"),
            ["8"],
            "_INIT_LOOP_STEP_REFERENCE no longer matches `engine step 8`, the "
            "canonical form it exists to find. commands/init-loop.md is pinned at "
            "ZERO references, so a dead matcher reports the expected count and "
            "test_init_loop_md_contains_no_engine_step_number stays green while "
            "guarding nothing.",
        )
        self.assertEqual(
            self._INIT_LOOP_STEP_REFERENCE.findall("see Step 8 of this guide"),
            [],
            "_INIT_LOOP_STEP_REFERENCE matched a bare `Step 8` with no `engine` "
            "anchor. That anchor keeps commands/init-loop.md's OWN onboarding step "
            "headings out of scope -- there are dozens, every number also a real "
            "engine heading. (The live pin catches this one too, and louder: an "
            "unanchored matcher finds all of them and turns it red. This states "
            "the intent.)",
        )
        self.assertEqual(
            self._INIT_LOOP_STEP_REFERENCE.findall("> the engine's\n> step\n> 8 gate"),
            ["8"],
            "_INIT_LOOP_STEP_REFERENCE stopped tolerating markdown's blockquote "
            "continuation marker across a wrap. commands/init-loop.md is "
            "hard-wrapped AND blockquoted, so that is the shape a stranded "
            "citation takes there -- and the pin at ZERO cannot see it: revert "
            "the branch and the whole suite stays green while a citation ships "
            "into every onboarded repo. Wrapped at BOTH positions on purpose: "
            "the marker is tolerated in two places in the pattern, and this is "
            "the one string that exercises both, so neither can rot alone. It "
            "is a worst case, not a claim that citations wrap twice.",
        )

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

        ``latest_tie=True`` is the one difference, and it closes a false pass
        review found: this chain says ``review`` ONCE while the engine has two
        review steps (9 Code review, 10 Security review). Under the default
        earliest-tie rule, ``review`` binds to whichever comes first, so moving
        the OTHER review step after ``Merge`` satisfied the chain and passed --
        a pipeline where code review runs after merge, certified green. Binding
        to the LAST equally-good heading is the correct reading of a label that
        collapses both: every review step must precede merge. ``plugin.json``'s
        chain keeps the default because it lists review and security
        separately, so its labels are not collapsed.
        """
        self._assign(
            self._skill_frontmatter_labels(),
            self._engine_steps(),
            "SKILL.md's frontmatter description",
            ordered=True,
            latest_tie=True,
        )

    def test_every_engine_step_reference_resolves_to_a_real_heading(self) -> None:
        """Restatement #5: 179 in-prose `step N` sites. RESOLVABILITY ONLY.

        This asserts that every referenced N is a real heading number -- not
        that it still points at the step it meant. `step 8` continuing to
        resolve after a renumber says nothing about whether 8 is still *Code
        review*; that is semantics, and CLAUDE.md is explicit that this module
        must not grow into a semantic test of the engine. Sub-item suffixes
        (the `.1` in `step 0.1`) are likewise not resolved -- only the step.

        So: this catches a renumber that leaves references DANGLING (steps
        removed, or the run rebased off zero). It does NOT catch a renumber
        that only adds steps, nor a reference that shifted meaning while
        staying in range -- including the case that matters most, inserting a
        step mid-pipeline, which leaves all 182 references pointing one step off
        and every test green.

        Nor does it see reference FORMS the regex does not match: `steps 3 and
        7`, `steps 3, 7`, and `step #7` are all invisible. None is used in the
        engine today, and each was left out deliberately -- matching `,` or
        `and` as run separators re-introduces the false failure that space-
        padded separators caused ("step 12 — 40 lines max" parsing as a run).
        """
        valid = {number for number, _ in self._engine_steps()}
        # Sorted numerically, not lexically: ['10', '9'] reads as a typo.
        dangling = sorted(
            {literal for literal, number in self._step_references() if number not in valid},
            key=lambda lit: (int(lit.split(".")[0]), lit),
        )
        self.assertEqual(
            dangling,
            [],
            f"loop-engine.md cross-references step(s) {dangling} that no '### N.' "
            f"heading defines (headings are {sorted(valid)}). A renumber must "
            "update the in-prose references in the same change. NOTE: this check "
            "is resolvability-only -- references that stay in range but now point "
            "at the wrong step are NOT caught here.",
        )

    def test_init_loop_md_contains_no_engine_step_number(self) -> None:
        """``commands/init-loop.md`` cites gates by NAME, never by step number.

        The ``~~~markdown`` skeleton in that file is copied verbatim into each
        onboarded repo's ``.claude/loop.config.md`` -- a file **no release, no CI
        check, no /init-loop re-run and no plugin re-install ever reaches**. A
        step number written there is correct only until the next renumber, after
        which it is stranded in every config generated in the meantime, with
        nothing able to correct it. A gate *name* survives a renumber. #113
        removed the last two (``(engine step 8)`` on the ``CODE_REVIEW`` row,
        ``engine step 6`` on ``HERMETIC_TEST_CMD``) and pinned this at zero.

        **Asserted over the whole file, which is what let the old
        skeleton-position check go.** The skeleton is a subset of the file, so
        file == 0 already proves skeleton == 0 -- and the prose is covered too,
        deliberately: a rule with an exception is one a later edit migrates
        into, and a number sitting in prose is a number the next editor copies
        into the skeleton.

        **This test is only as live as its matcher, and at zero it cannot tell
        you so.** A broken ``_INIT_LOOP_STEP_REFERENCE`` reports 0 exactly as a
        clean file does. ``test_the_init_loop_matcher_is_alive`` is what
        keeps this honest -- it checks the matcher against synthetic fixtures in
        both directions. Delete that and this assertion becomes vacuous.

        Counts SITES, so a run form (``engine steps 9/10``) would be one.
        """
        sites = self._INIT_LOOP_STEP_REFERENCE.findall(_INIT_LOOP.read_text(encoding="utf-8"))
        self.assertEqual(
            len(sites),
            self._EXPECTED_INIT_LOOP_STEP_REFERENCES,
            f"commands/init-loop.md cites {len(sites)} engine step(s) by NUMBER "
            f"({sites}); it must cite gates by NAME instead, so the expected count is "
            f"{self._EXPECTED_INIT_LOOP_STEP_REFERENCES}. Write \"the code-review "
            "gate\" or \"the engine's implement step\", never \"engine step 8\". "
            "This is not style: the `~~~markdown` skeleton is copied into every "
            "onboarded repo's .claude/loop.config.md, which no release, no CI check "
            "and no re-install can reach -- so a number here is stranded at the next "
            "renumber, in every config generated in the meantime. If you are writing "
            "an illustrative example, spell it `engine step N` with a letter; a digit "
            "counts. The rule covers this file's surrounding prose too, which does "
            "not ship, because a number there is one the next editor copies inward.",
        )


class MutationNaReasonTests(unittest.TestCase):
    """The ``mutation-survivors`` ``n/a`` list is closed, and says so in several places.

    #60's second PR retired one of three reasons (``n/a: apparatus pending``) when the
    mutation apparatus landed. Retiring a member of a closed list is a multi-site edit:
    the engine states the list's size in four separate passages, and a partial
    retraction leaves the engine contradicting itself about how many ways there are to
    skip the gate -- which is the fail-open direction, since a reader who finds "three"
    goes looking for a third reason.

    **Scope, stated narrowly on purpose.** This checks the *stated count* and that the
    retired reason never appears without its retirement. It does NOT check that the
    reasons enumerated are the *right* ones, that the list should be closed at all, or
    anything else semantic -- that stays on review + dogfooding (CLAUDE.md).
    """

    # The number of legal ``n/a`` reasons, pinned rather than derived. Agreement alone
    # cannot catch every site being reverted together, which is exactly what a careless
    # revert of #60's second PR would do.
    _EXPECTED_NA_REASON_COUNT = "two"

    # Every restatement of the list's size.
    #
    # The first draft of this anchored on the literal ``\`n/a\` list is closed at``,
    # which missed a fourth site (`that list is closed at two reasons`) that the very
    # commit adding this class also added -- caught by the acceptance gate, and exactly
    # the multi-site drift the class exists to prevent. Anchoring on ``list is closed
    # at`` instead covers the referring forms too, because what varies between sites is
    # how the slot is named, never the phrase stating the size.
    _STATED_COUNT = re.compile(
        r"list is closed at (?P<count>[a-z]+) reasons?"
        r"|for one of exactly\s+\*\*(?P<count2>[a-z]+)\*\*\s+reasons?",
    )

    # Pinned exactly, not as a floor. A floor cannot catch a restatement reworded out of
    # the matcher's reach when another is added in the same change -- the count stays
    # put while coverage drops. Adding a restatement deliberately means updating this.
    _EXPECTED_RESTATEMENTS = 4

    _RETIRED_REASON = "apparatus pending"

    # Every path reference to the harness, capturing the variable it is rooted at.
    # Capturing the root rather than matching one blessed literal is deliberate: a
    # mutation that repointed the runnable command at ${CLAUDE_PROJECT_DIR} survived an
    # earlier `assertIn` of the correct string, because the correct string still
    # appeared in the prose beside it.
    _HARNESS_REFERENCE = re.compile(r"\$\{([A-Z_]+)\}/tools/mutate_verify\.py")

    # Pinned, for the reason the class pins everything else: a floor of one let the
    # runnable command block be deleted while a prose mention held the test green.
    _EXPECTED_HARNESS_REFERENCES = 2

    # The runnable invocation, as distinct from a mention of the path. Naming the tool
    # is not wiring it in, and only one of the two references is the wiring.
    #
    # Scoped to a single fenced code block, and that scoping is the point: the first
    # draft used `(?:.|\n)*?`, which ran past the closing fence and satisfied
    # `--test-cmd` from the prose below it -- so deleting `--test-cmd` from the command
    # still passed, while the failure message claimed the block had been checked.
    _FENCED_BLOCK = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
    _INVOCATION_PARTS = ("mutate_verify.py", "run", "--spec", "--test-cmd")

    @classmethod
    def _has_runnable_invocation(cls, text: str) -> bool:
        return any(
            all(part in block for part in cls._INVOCATION_PARTS)
            for block in cls._FENCED_BLOCK.findall(text)
        )

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine_text = _ENGINE.read_text(encoding="utf-8")

    def _stated_counts(self) -> list[str]:
        found = []
        for match in self._STATED_COUNT.finditer(self.engine_text):
            found.append(next(g for g in match.groups() if g))
        return found

    def test_the_extractor_actually_finds_the_restatements(self) -> None:
        """Guard the guard: a regex that matches nothing would pass every test below.

        Without this, deleting every statement of the count -- or reflowing one out of
        the matcher's reach -- reads as agreement rather than as the loss it is.
        """
        self.assertEqual(
            len(self._stated_counts()),
            self._EXPECTED_RESTATEMENTS,
            "loop-engine.md states the size of the mutation-survivors n/a list in "
            f"{self._EXPECTED_RESTATEMENTS} passages; the matcher found "
            f"{len(self._stated_counts())}. Either a restatement was deleted, one was "
            "added without updating _EXPECTED_RESTATEMENTS, or one was reworded past "
            "this matcher -- and an unmatched site is invisible to every other "
            "assertion in this class, so it would drift silently.",
        )

    def test_every_restatement_of_the_na_list_size_agrees(self) -> None:
        counts = set(self._stated_counts())
        self.assertEqual(
            len(counts),
            1,
            "loop-engine.md disagrees with itself about how many legal `n/a` reasons "
            f"the mutation-survivors slot has: found {sorted(counts)}. Retiring or "
            "adding a reason is a multi-site edit -- every passage stating the size "
            "must change in the same commit, or a partially-loaded engine reads a "
            "size that licenses a reason the list does not actually contain.",
        )

    def test_the_stated_size_is_the_pinned_one(self) -> None:
        counts = set(self._stated_counts())
        self.assertEqual(
            counts,
            {self._EXPECTED_NA_REASON_COUNT},
            f"the mutation-survivors `n/a` list is pinned at "
            f"'{self._EXPECTED_NA_REASON_COUNT}' reasons and the engine now says "
            f"{sorted(counts)}. If this is a deliberate change, update "
            "_EXPECTED_NA_REASON_COUNT -- but read the engine's own warning first: a "
            "reachable extra reason is an off switch an agent can always reach for, "
            "which is what this slot was designed against.",
        )

    def test_the_retired_reason_never_appears_without_its_retirement(self) -> None:
        """The retired spelling may be *named* -- only in the passage forbidding it.

        Paragraph-scoped rather than line-scoped so that reflowing the passage does not
        fail this spuriously; blank-line delimiting needs no fenced span, which is the
        instrument #76 records as defeated four times.
        """
        offenders = [
            paragraph.strip().splitlines()[0][:90]
            for paragraph in self.engine_text.split("\n\n")
            if self._RETIRED_REASON in paragraph and "RETIRED" not in paragraph
        ]
        self.assertEqual(
            offenders,
            [],
            "loop-engine.md uses the retired `n/a: apparatus pending` reason in a "
            f"passage that does not mark it retired: {offenders}. The apparatus "
            "shipped, so that reason names a gap that no longer exists -- writing it "
            "would report a missing capability as the reason for not using the "
            "capability.",
        )

    def test_the_retired_reason_reaches_no_other_shipped_artifact(self) -> None:
        """A cheap regression guard, and deliberately no more than that.

        Honest about its own strength: the retired spelling has never appeared in any of
        these three files, so this passes identically on `main` and on a full revert. It
        does not guard the retraction -- the tests above do. It guards a *future* edit
        that would carry the dead reason into an artifact with no legitimate use for it,
        init-loop.md most of all, since what that file carries is copied into every
        onboarded repo's config where no later release can correct it.
        """
        for path in (_SKILL, _INIT_LOOP, _README):
            with self.subTest(path=path.name):
                self.assertNotIn(
                    self._RETIRED_REASON,
                    path.read_text(encoding="utf-8"),
                    f"{path.name} names the retired `n/a: apparatus pending` reason. "
                    "It was retired with #60's second PR and has no live use.",
                )

    def test_the_engine_names_the_harness_the_pass_actually_runs(self) -> None:
        """The deferral was lifted *onto* something; this pins that it points at it.

        Lifting the fence without naming the tool would leave the engine authorizing a
        mutation pass while still leaving the procedure to be improvised -- which is
        the one thing every version of this text has forbidden.
        """
        harness = _REPO_ROOT / "tools" / "mutate_verify.py"
        self.assertTrue(
            harness.is_file(),
            "tools/mutate_verify.py is missing, but loop-engine.md tells the "
            "orchestrator to run it.",
        )
        roots = self._HARNESS_REFERENCE.findall(self.engine_text)
        self.assertEqual(
            len(roots),
            self._EXPECTED_HARNESS_REFERENCES,
            "loop-engine.md names the harness "
            f"{self._EXPECTED_HARNESS_REFERENCES} times and the matcher found "
            f"{len(roots)}. Pinned exactly, not as a floor: with a floor of one, "
            "deleting the runnable command block -- reverting the wiring this whole "
            "change is FOR -- stays green off the prose mention beside it.",
        )
        self.assertTrue(
            self._has_runnable_invocation(self.engine_text),
            "loop-engine.md still mentions the harness in prose but no single fenced "
            "code block carries a runnable invocation of it -- one block containing "
            f"all of {self._INVOCATION_PARTS}. Naming a tool is not wiring it in: "
            "without the command, the engine authorizes a mutation pass and leaves the "
            "procedure to be improvised, which every version of this text forbids.",
        )
        self.assertEqual(
            sorted(set(roots)),
            ["CLAUDE_PLUGIN_ROOT"],
            "loop-engine.md reaches the mutation harness through "
            f"{sorted(set(roots))}. **Every** reference must be rooted at "
            "${CLAUDE_PLUGIN_ROOT}: the script ships with the installed plugin, while "
            "${CLAUDE_PROJECT_DIR} is the consumer's repository -- the very tree the "
            "pass is supposed to mutate only through an isolated copy. Asserting one "
            "correct spelling is *present* does not catch this, because the prose "
            "mentions the path beside the runnable command; the property is that no "
            "reference uses any other root.",
        )


class PlanGateFrozenBlockTests(unittest.TestCase):
    """#28's always-on plan-gate stop hangs on one heading spelled the same everywhere.

    Step 4 WRITES a frozen pre-image of the plan's approach under a fixed heading;
    step 5 LOOKS FOR that heading to diff against; the ``issue-<N>.plan.md`` template
    declares it; Resume names it in the write-once guard. If those spellings drift
    apart the mechanism is **dead while every word of the prose still reads correctly**
    -- step 5 finds no block, and an absent pre-image is exactly the case the engine
    now has to treat as material.

    This is one mechanically-checkable part of an invariant restated across many sites
    (``CLAUDE.md`` enumerates them). The rest is
    prose agreement, which a check would guard only fragilely or vacuously (the #76
    ``~~~markdown`` span problem) -- see ``CLAUDE.md``. What is asserted here is a
    *string* coupling, not a meaning, which is why it is neither.

    **Anchored per region, not counted globally, and the distinction is the whole
    value of the test.** An earlier draft asserted ``count(heading) == 4`` over the
    file. A fresh reviewer broke it twice while the suite stayed green: paraphrase
    Resume's occurrence and add a spare mention in step 4's prose (total still 4), or
    delete the block from the plan template and mention it inside the *progress.md*
    fence instead. Both leave the mechanism dead. A global total cannot tell *which*
    sites carry the heading, which is the only thing worth knowing here.

    Whitespace is normalized deliberately: one occurrence is line-wrapped, the same
    hazard that hid two step references from the naive grep ``CLAUDE.md`` quotes. The
    em dash is normalized too. So this asserts that the heading *appears*, normalized,
    in each of four located regions -- not byte-identity, not equality, and not a
    property of "sites". ``CLAUDE.md`` must not claim more.
    """

    _HEADING = (
        "## Approach as reviewed (frozen before the design gate) "
        "-- write-once, do not edit"
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2014", "--"))

    def _engine(self) -> str:
        return _ENGINE.read_text(encoding="utf-8")

    def _span(self, text: str, start: str, end: str, label: str) -> str:
        i = text.find(start)
        self.assertNotEqual(
            i, -1, f"cannot locate the start of the {label} region ({start!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it."
        )
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it."
        )
        return text[i:j]

    def _plan_template_fence(self, text: str) -> str:
        # The plan template specifically -- NOT just any ```markdown fence. The engine
        # has several; an earlier draft accepted any of them and passed while the
        # heading had been moved into the progress.md one.
        section = self._span(
            text,
            "### `issue-<N>.plan.md`",
            "### Lifecycle & commit policy",
            "issue-<N>.plan.md template section",
        )
        fences = re.findall(r"```markdown(.*?)```", section, flags=re.S)
        self.assertEqual(
            len(fences), 1,
            "expected exactly one ```markdown fence in the issue-<N>.plan.md template "
            f"section; found {len(fences)}. This test anchors on that fence being the "
            "plan template -- re-anchor it rather than loosening the match.",
        )
        fence = fences[0]
        self.assertIn(
            "# Plan: #<N>", fence,
            "the fence found in the issue-<N>.plan.md template section is not the plan "
            "template (no `# Plan: #<N>` line). Re-anchor this test.",
        )
        return fence

    def _regions(self):
        text = self._engine()
        return {
            "step 4 (writes the frozen block)": self._span(
                text, "### 4. Architect gate", "### 5. Human gate", "step 4"
            ),
            "step 5 (diffs against it)": self._span(
                text, "### 5. Human gate", "### 6. Implement", "step 5"
            ),
            "the issue-<N>.plan.md template": self._plan_template_fence(text),
            "Resume (write-once guard)": self._span(
                text, "## Resume after", "## Routing table", "Resume"
            ),
        }

    def test_every_site_that_writes_or_reads_the_frozen_block_spells_it_the_same(
        self,
    ) -> None:
        missing = sorted(
            label
            for label, body in self._regions().items()
            if self._HEADING not in self._normalize(body)
        )
        self.assertEqual(
            missing,
            [],
            "these region(s) of loop-engine.md do not carry the frozen-approach "
            f"heading: {missing}.\n\n"
            f"Expected (normalized): {self._HEADING!r}\n\n"
            "A MISMATCH IS SILENT. Step 5 looks the block up by name, so a heading "
            "that drifts at one site means the diff finds nothing -- and 'no evidence "
            "of a material change' reads as 'not material', so the always-on stop "
            "passes without ever running. That is exactly the self-assessment #28 "
            "removed, failing in the direction that looks like success.\n\n"
            "Each region is checked SEPARATELY on purpose: a global count of the "
            "heading passes when one site loses it and another gains a spare "
            "mention. If you renamed the heading deliberately, rename it in all four "
            "regions and update _HEADING. Never delete a region from _regions() to "
            "make this pass.",
        )

    def test_the_heading_is_a_section_not_a_subsection(self) -> None:
        # `## Foo` is a substring of `### Foo`, so a level change would slip past a
        # plain containment check while producing a different block in the plan file.
        for label, body in self._regions().items():
            with self.subTest(region=label):
                self.assertNotIn(
                    "#" + self._HEADING,
                    self._normalize(body),
                    f"{label} writes the frozen-approach block at a deeper heading "
                    "level (### rather than ##). The orchestrator writes the plan "
                    "file from these strings, so a level change produces a block "
                    "step 5's lookup does not match.",
                )


class VerdictFirstInvariantTests(unittest.TestCase):
    """#119's Verdict-first invariant reaches its gates by NAME, at located sites.

    The invariant is defined once, under Gates, and every gate that spawns an agent
    to produce a verdict is supposed to pass it on. Two kinds of site carry it and
    they fail differently, which is why both are checked:

    * **Orchestrator-facing recipes** name the invariant; the orchestrator resolves
      the name when it composes the prompt. If a site loses the reference the
      orchestrator stops passing it on -- silently, because the surrounding prose
      still reads correctly and the gate still returns *something*.
    * **Text handed to the agent verbatim** -- the AC-verifier's Part 1 ``Prompt:``
      block -- is different in kind: that text reaches an agent which reads neither
      the Gates section nor anything else in the engine, so a bare NAME there is
      inert. That site has to carry the operative clause itself, which is what
      ``test_the_verbatim_prompt_carries_the_clause_not_only_the_name`` pins.

    The second case is the failure the design was changed to avoid: satisfy the
    invariant by writing "per the Verdict-first invariant" into the ``Prompt:`` block
    and the instruction never reaches the verifier at all -- the gate keeps running,
    the prose keeps reading correctly, and the one agent the invariant was written
    for is the one agent that never hears it.

    **What this asserts is a string coupling, never a meaning** -- the ceiling
    ``CLAUDE.md`` sets for a prose guard. It cannot tell whether the sentence is
    *right*, whether an orchestrator actually pastes it, or whether the reference
    sits in the recipe rather than merely somewhere in the same region.

    **Two limits worth stating, because an earlier draft of this docstring got the
    first one wrong.** (1) A *synchronized* reword of both clause copies does NOT
    pass -- ``_OPERATIVE`` is a literal, so it fails until the constant is edited
    too. That is deliberate (the reword should be reviewed), but it is a maintenance
    cost, not a free pass. (2) ``_REFERENCE_REGIONS`` is hand-maintained and has no
    coupling to the engine's actual gate set, so a gate added later is uncovered
    until someone adds it here. The method name says "located reference site" rather
    than "every gate" for exactly that reason.

    **Anchored per region, never counted globally** -- the lesson
    ``PlanGateFrozenBlockTests`` records. A total passes when one site drops the name
    and another gains a spare mention, and a total cannot say *which* site went dark.

    Regions are scoped to the run of paragraphs carrying the reference rather than to
    the whole pipeline step, which narrows how far the name can drift and still
    satisfy the check. **It does not close that gap and this docstring must not say
    it does.** An earlier draft claimed relocating the reference into an unrelated
    aside in the same step was "caught rather than tolerated"; the acceptance gate's
    mutation pass falsified it -- deleting the instruction and leaving a plausible
    in-place exemption that still names the invariant passes green at every one of
    the recipe sites. ``assertIn(name, region)`` cannot distinguish "the recipe
    instructs X" from "the recipe says X does not apply here", and no amount of
    tightening changes that.

    No region's START anchor may contain the invariant's name, or that region's
    subtest would be unfalsifiable; ``test_no_region_is_satisfied_by_its_own_anchor``
    enforces that over ``_REFERENCE_REGIONS`` **and** the verbatim region, which is
    every region ``_regions()`` returns.

    **What review owns, because this test provably cannot.** Per ``CLAUDE.md``'s
    ruling on prose guards, polarity is not reachable here and trying to reach it is
    the displacement loop, not a gap someone forgot:

    * whether a site's instruction *says* verdict-first or its opposite;
    * whether a site exempts itself while still naming the invariant;
    * whether the canonical definition still asserts the rule, or has demoted the
      pinned clause to a historical aside.

    All three were demonstrated as surviving mutations at this change's own
    acceptance gate and are recorded here rather than chased with a broader literal.
    """

    _NAME = "Verdict-first invariant"

    # The clause the verbatim site must carry in full, pinned in both the canonical
    # definition and the verbatim copy so deleting it from either end fails.
    #
    # It includes the ordering token ("first, then"), which raised the bar and did
    # NOT close it -- do not read the token as a polarity guard. The acceptance
    # gate's mutation pass demonstrated the boundary with a paired probe:
    #   "start with the riskiest criterion AND THEN deepen ..."  -> killed
    #   "start with the riskiest criterion FIRST, THEN deepen ..." -> SURVIVED
    # Same inversion, one word apart. The pin covers everything after "first,"; what
    # must be complete first is the whole content of the invariant, and it sits
    # before the pin. Extending this literal to swallow that variant would enumerate
    # the phrasings an author happened to think of, which is the ALLOWED_NON_BINDINGS
    # shape CLAUDE.md forbids. Polarity is review's; see the class docstring.
    _OPERATIVE = "first, then deepen with whatever budget remains"

    # (start, end) anchors. Each span must be the paragraph carrying the reference.
    _REFERENCE_REGIONS = {
        "step 4 (architect invoke site)": (
            "### 4. Architect gate",
            "**Do these three things in this order.**",
        ),
        "step 5 (the DESIGN_AGENT consult)": (
            '"auto-approved" is never a legitimate journal entry for this gate.',
            "**One stop condition is ALWAYS-ON.**",
        ),
        "step 6 (hermetic fresh read)": (
            "Whether the fix **preserved what the test asserts**",
            "**A test added later re-arms the trigger.**",
        ),
        "step 8 (the finder fan-out)": (
            "**Give every finder the issue's acceptance criteria alongside the diff.**",
            "**Pick finder angles from the diff's risk surface",
        ),
        "the Class B limit-case checker": (
            "- **Acceptance gate, Class B \u2014 the limit case needs its own recipe.**",
            "- **Code review (step 8) \u2014 the previous round's findings",
        ),
        "step 8's fresh re-check recipe": (
            "- **Code review (step 8) \u2014 the previous round's findings",
            "**The bound \u2014 one fresh re-check",
        ),
        "AC-verifier Part 2 (the mutating agent)": (
            "**Who writes the spec \u2014 and what it may never be built from.**",
            "**The applied-check",
        ),
    }

    _VERBATIM = (
        '   Prompt: *"Run the commands above yourself against base',
        "2. For behavior that needs runtime proof, also run",
    )
    _CANONICAL = (
        "**Verdict-first invariant (a verdict before depth).**",
        "**Convergence & the resting states.**",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2014", "--"))

    def _engine(self) -> str:
        return _ENGINE.read_text(encoding="utf-8")

    def _span(self, text: str, start: str, end: str, label: str) -> str:
        # A duplicated START anchor is the one drift that fails OPEN: `find` takes
        # the first occurrence, so the span can silently widen to swallow neighbouring
        # regions and then satisfy the containment check on someone else's text.
        # Assert the property the anchor actually relies on rather than bounding the
        # resulting width, which cannot distinguish a legitimately long region from a
        # runaway one.
        self.assertEqual(
            text.count(start), 1,
            f"the start anchor for the {label} region occurs {text.count(start)} "
            f"times in loop-engine.md ({start!r}); it must occur exactly once. More "
            "than one lets the span silently widen past this region and find the "
            "name in a neighbour's text.",
        )
        i = text.find(start)
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it."
        )
        return text[i:j]

    def _regions(self):
        text = self._engine()
        out = {
            label: self._span(text, a, b, label)
            for label, (a, b) in self._REFERENCE_REGIONS.items()
        }
        out["the AC-verifier Part 1 verbatim prompt"] = self._span(
            text, *self._VERBATIM, "the AC-verifier Part 1 verbatim prompt"
        )
        return out

    def _canonical(self, text: str) -> str:
        return self._span(text, *self._CANONICAL, "the canonical definition")

    def test_no_region_is_satisfied_by_its_own_anchor(self) -> None:
        # A start anchor containing _NAME makes that region's subtest unfalsifiable:
        # the span always begins with the string being asserted. An earlier draft
        # shipped exactly that for the canonical definition.
        pairs = dict(self._REFERENCE_REGIONS)
        pairs["the AC-verifier Part 1 verbatim prompt"] = self._VERBATIM
        for label, (start, end) in pairs.items():
            with self.subTest(region=label):
                for which, anchor in (("start", start), ("end", end)):
                    self.assertNotIn(
                        self._NAME, anchor,
                        f"the {which} anchor for {label} contains {self._NAME!r}, so "
                        "that region's containment check can never fail. Re-anchor it "
                        "on text that does not name the invariant.",
                    )

    def test_the_span_anchors_actually_resolve(self) -> None:
        # Liveness: a span that silently collapsed would satisfy nothing and fail
        # loudly, but the anchors themselves could rot into a region that is not the
        # paragraph intended. Bound the low end; the high end is covered by the
        # unique-start-anchor assertion in _span, which is the real drift vector.
        for label, body in self._regions().items():
            with self.subTest(region=label):
                self.assertGreater(
                    len(body), 80,
                    f"the {label} region resolved to {len(body)} characters, which is "
                    "too short to be that region -- the anchors have drifted.",
                )

    def test_each_located_reference_site_names_the_invariant(self) -> None:
        name = self._normalize(self._NAME)
        missing = sorted(
            label
            for label, body in self._regions().items()
            if name not in self._normalize(body)
        )
        self.assertEqual(
            missing,
            [],
            f"these region(s) of loop-engine.md no longer name the {self._NAME}: "
            f"{missing}.\n\n"
            "A MISMATCH IS SILENT. Each region is the recipe telling the orchestrator "
            "what to put in a prompt it composes; a region that drops the reference "
            "stops passing the instruction on, and the agent it spawns runs without "
            "it. Nothing downstream can tell that apart from an agent that had the "
            "instruction and chose depth anyway.\n\n"
            "Each region is checked SEPARATELY on purpose: a global count of the name "
            "passes when one site loses it and another gains a spare mention. If you "
            "renamed the invariant deliberately, rename it in EVERY region and update "
            "_NAME. Never delete a region from _REFERENCE_REGIONS to make this pass -- "
            "that is the check agreeing to cover less.",
        )

    def test_the_verbatim_prompt_carries_the_clause_not_only_the_name(self) -> None:
        # The name alone is INERT here, which is why this site is distinguished from
        # the orchestrator-facing recipes above.
        text = self._engine()
        clause = self._normalize(self._OPERATIVE)
        for label, body in (
            ("the canonical definition (Gates)", self._canonical(text)),
            (
                "the AC-verifier Part 1 verbatim prompt",
                self._span(text, *self._VERBATIM, "the verbatim prompt"),
            ),
        ):
            with self.subTest(region=label):
                self.assertIn(
                    clause,
                    self._normalize(body),
                    f"{label} no longer carries the operative clause "
                    f"{self._OPERATIVE!r}.\n\n"
                    "The AC-verifier's Part 1 prompt is handed to a subagent VERBATIM. "
                    "That agent reads neither the Gates section nor anything else in "
                    "this engine, so a bare reference to the invariant by name does "
                    "not reach it: the instruction silently does not exist for the "
                    "one agent it was written for, while every word of the engine "
                    "still reads correctly.\n\n"
                    "The clause deliberately includes the ordering token ('first, "
                    "then deepen'). A fragment starting at 'then deepen' would be "
                    "satisfied by an instruction that INVERTED the rule into "
                    "depth-first while keeping the invariant's words.\n\n"
                    "Both copies are checked against this constant, so deleting the "
                    "clause from either end fails. A deliberate reword must change "
                    "both copies AND _OPERATIVE.",
                )


class ResumeHandoffPointerTests(unittest.TestCase):
    """#32's Resume hands its recovery procedure off to Part 2 by NAME.

    Resume's working-tree reconciliation deliberately does not restate the
    interrupted-pass recovery apparatus -- an earlier draft of #32 did, and every
    blocking defect that review round found lived in the restatement. The architect's
    scope ruling replaced it with a pointer: *"hand off to AC-verifier -> Part 2,
    Interrupted-pass recovery, which owns the diagnosis, the repair, and when to
    escalate -- do not re-derive it here."*

    That makes the label a **load-bearing string**. Rename Part 2's block and the
    pointer dangles: Resume tells the orchestrator to go somewhere that no longer
    exists, so AC2's prune and the whole mutation-recovery path have no owner --
    **while every word of the prose still reads correctly.** That is the same failure
    mode ``PlanGateFrozenBlockTests`` exists for, and it was confirmed by execution
    rather than argued: the acceptance gate for #32 renamed Part 2's heading to
    "Recovery from an interrupted pass" and the suite stayed green (137 tests, OK).

    What is asserted is a *string* coupling in two located regions, not a meaning and
    not a global count -- for the reasons that test's docstring gives at length. It
    says nothing about whether the delegation is a good idea, only that its two ends
    still name the same thing.

    Whitespace is normalized because Resume's occurrence is **line-wrapped**, which is
    exactly how the coupling would otherwise evade a naive grep.
    """

    _LABEL = "Interrupted-pass recovery"

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2014", "--"))

    def _span(self, start: str, end: str, label: str) -> str:
        text = _ENGINE.read_text(encoding="utf-8")
        i = text.find(start)
        self.assertNotEqual(
            i, -1, f"cannot locate the start of the {label} region ({start!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        return text[i:j]

    def _regions(self):
        return {
            "Part 2 (defines the block)": self._span(
                "**Part 2 ", "## Initialization procedure", "Part 2",
            ),
            "Resume (points at it)": self._span(
                "## Resume after", "## Routing table", "Resume",
            ),
        }

    def test_both_ends_of_the_handoff_name_the_same_block(self) -> None:
        for label, body in self._regions().items():
            with self.subTest(region=label):
                self.assertIn(
                    self._LABEL,
                    self._normalize(body),
                    f"{label} no longer carries the string {self._LABEL!r}. Resume "
                    "delegates its recovery procedure to Part 2 by this name instead "
                    "of restating it, so if the two ends stop agreeing the pointer "
                    "dangles and the procedure has no owner -- with the prose still "
                    "reading correctly. Re-point both ends together; do not drop a "
                    "region to make this pass.",
                )


class DeltaScopedRoundNotationTests(unittest.TestCase):
    """#120's delta-scoped rounds name the SAME range at every site that fixes it.

    Three sites specify what a code-review round after the first reads, and a fourth
    is where the range it read is written down:

    * **step 8's scoping rule** -- the pipeline text an orchestrator executes;
    * **the Fresh-re-check invariant's code-review bullet** (under Gates) -- the
      input recipe step 8 explicitly delegates to rather than restating;
    * **step 8's three-bases aside** -- the opener's parenthetical, which names
      round 1's base, a later round's, and step 10's, and forbids "fixing" one to
      match another;
    * **the Ledger format's ``- Code-review:`` paragraph** -- the human-readable
      record of what each round covered, which is what the currency argument is
      checked against at the merge gate. It is deliberately NOT parsed by any step:
      an earlier draft made it a state store, and most of what round 3 returned
      descended from that. (Say which round's findings you mean: an earlier draft
      claimed "every finding" across two rounds and was falsified by the commit
      log, and its replacement read either 3-of-4 or 1-of-3 depending on whether
      you counted round 3's findings or the round-2 findings that caused it.)

    **The failure this catches is a silent disagreement, not a missing sentence.**
    Revert one site to ``main...HEAD`` while the others still say
    ``<reviewed>..HEAD`` and every word of each still reads correctly -- the
    orchestrator follows one of them, the gate returns a verdict either way, and
    nothing downstream can tell which range was actually read. The same holds if the
    ledger paragraph drops the notation: the anchor stops being written, every
    resumed round quietly falls back to full, and the only evidence is a saving that
    stopped happening.

    **Both region sets were narrowed after review defeated an earlier draft**, and the
    reason generalises. The step-8 span originally ran to the end of the scoping
    passage, which swept in an illustrative ``git diff --numstat`` line carrying the
    same token -- so the normative bullet could go dark with the suite green. The
    ledger check originally asserted the anchor NAME, which that paragraph's rationale
    carries as well as its spec -- so deleting the entire format spec passed. **An
    example is not a specification, and a rationale is not one either:** when a region
    must contain a rule, anchor it on text that exists only in the rule.

    **This asserts a coupling's identity, never a proposition's truth** -- the
    ceiling ``CLAUDE.md`` sets for a prose guard, and the reason no attempt is made
    here to pin the POLARITY of "round 1 is unscoped". That class is ruled
    unreachable -- every attempt so far has been defeated by a one-word edit -- and
    re-attempting it is the displacement loop rather than a gap someone forgot. No
    count of those attempts is given here on purpose: the figure lives in the ledger,
    which is gitignored, so a reader of this repo cannot check it.

    So what review owns, because this test provably cannot:

    * whether round 1 is still specified as unscoped, or has been quietly narrowed;
    * **whether the ledger paragraph still fixes a WRITE-TIME for each element** --
      an append-only journal is only a record of what happened if it is written when
      it happens, and a line reconstructed at step 12 is written from memory about
      rounds that may predate a ``/clear``. It is a proposition, not a coupling, so
      nothing here reaches it; a reword defeats any literal that could;
    * whether a site names the range while exempting itself from using it;
    * whether the fallback conditions still fall back, or have been inverted;
    * whether the known-vs-unknown boundary on a project's sensitive-path
      declaration is drawn where the prose says it is.

    **Anchored per region, never counted globally** -- the lesson
    ``PlanGateFrozenBlockTests`` records. A global count of the notation passes when
    one site drops it and another gains a spare mention, and cannot say which site
    went dark.
    """

    # The range notation every site must name. Deliberately the literal token rather
    # than a pattern over "some range": a pattern matching `<anything>..HEAD` would
    # be satisfied by `main..HEAD`, which is the mutation this exists to catch.
    _NOTATION = "<reviewed>..HEAD"

    # The ledger's own spelling of a scoped round, pinned SEPARATELY and deliberately
    # NOT on the anchor name. The anchor name appears in that paragraph's rationale
    # as well as its spec, so asserting it there passed when the entire format spec --
    # the only text discharging "the journal line records the range" -- was deleted and
    # the rationale sentence left behind. This constant occurs only in the spec.
    _LEDGER_SPELLING = "<sha>..<head>"

    # Used only by the anchor-contamination meta-test, which needs a token shorter
    # than either of the above.
    _ANCHOR = "<reviewed>"

    # (start, end) anchors. Each span must be the passage that FIXES the range, not
    # merely a paragraph that mentions rounds.
    _REGIONS = {
        # Narrowed to the BULLET RUN, not the whole scoping passage, so the span
        # holds the sentence that FIXES the range and nothing that merely mentions
        # it. The boundary is what matters, not the direction: extend the end anchor
        # PAST the currency paragraph and its own `<reviewed>..HEAD` comes inside,
        # after which the normative bullet can be reverted to `main...HEAD` with the
        # containment check still green -- the within-region form of the spare-mention
        # defeat PlanGateFrozenBlockTests records. (The original offender was a
        # `git diff --numstat` example since deleted; a later verification round
        # confirmed the currency paragraph now supplies the same hazard, which is why
        # this names a boundary rather than one deleted line.)
        "step 8's scoping rule": (
            "- **Round 1 is unscoped.**",
            "**The anchor is owed by every round after the first",
        ),
        "the Fresh-re-check code-review recipe (Gates)": (
            "- **Code review (step 8) \u2014 the previous round's findings",
            "**The bound \u2014 one fresh re-check",
        ),
        # The step-8 opener's parenthetical enumerates all three bases this engine
        # uses and forbids "fixing" one to match another. It names the range, so it
        # drifts the same way the other two do -- review found it reverted cleanly
        # while the rest of the change stood.
        "step 8's three-bases aside": (
            "**These bases",
            "Running those finders at once is permitted",
        ),
    }

    _LEDGER_REGION = (
        "The **`- Code-review:`** line names",
        "The **`- Restore:`** line records",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2014", "--"))

    def _engine(self) -> str:
        return _ENGINE.read_text(encoding="utf-8")

    def _span(self, text: str, start: str, end: str, label: str) -> str:
        # A duplicated START anchor fails OPEN: `find` takes the first occurrence, so
        # the span can widen past this region and satisfy the containment check on a
        # neighbour's text. Assert uniqueness rather than bounding the width, which
        # cannot tell a long region from a runaway one.
        self.assertEqual(
            text.count(start), 1,
            f"the start anchor for the {label} region occurs {text.count(start)} "
            f"times in loop-engine.md ({start!r}); it must occur exactly once.",
        )
        i = text.find(start)
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        return text[i:j]

    def _regions(self):
        text = self._engine()
        return {
            label: self._span(text, a, b, label)
            for label, (a, b) in self._REGIONS.items()
        }

    def test_no_region_is_satisfied_by_its_own_anchor(self) -> None:
        # An anchor containing the notation makes that region's check unfalsifiable.
        pairs = dict(self._REGIONS)
        pairs["the ledger's - Code-review: paragraph"] = self._LEDGER_REGION
        for label, (start, end) in pairs.items():
            with self.subTest(region=label):
                for which, anchor in (("start", start), ("end", end)):
                    self.assertNotIn(
                        self._ANCHOR, anchor,
                        f"the {which} anchor for {label} contains {self._ANCHOR!r}, so "
                        "that region's containment check can never fail. Re-anchor it "
                        "on text that does not carry the notation.",
                    )

    def test_the_span_anchors_actually_resolve(self) -> None:
        regions = dict(self._regions())
        regions["the ledger's - Code-review: paragraph"] = self._span(
            self._engine(), *self._LEDGER_REGION,
            "the ledger's - Code-review: paragraph",
        )
        for label, body in regions.items():
            with self.subTest(region=label):
                self.assertGreater(
                    len(body), 80,
                    f"the {label} region resolved to {len(body)} characters, which is "
                    "too short to be that region -- the anchors have drifted.",
                )

    def test_each_site_that_fixes_the_range_names_the_same_one(self) -> None:
        notation = self._normalize(self._NOTATION)
        missing = sorted(
            label
            for label, body in self._regions().items()
            if notation not in self._normalize(body)
        )
        self.assertEqual(
            missing,
            [],
            f"these region(s) of loop-engine.md no longer name {self._NOTATION!r}: "
            f"{missing}.\n\n"
            "A MISMATCH IS SILENT. Step 8 and the Gates recipe both fix what a round "
            "after the first reads; if one reverts to the full `main...HEAD` while "
            "the other stays scoped, both still read correctly, the gate still "
            "returns a verdict, and nothing downstream records which range was "
            "actually read.\n\n"
            "Each region is checked SEPARATELY: a global count passes when one site "
            "drops the notation and another gains a spare mention. If you changed the "
            "notation deliberately, change it in EVERY region and update _NOTATION. "
            "Never delete a region from _REGIONS to make this pass -- that is the "
            "check agreeing to cover less.",
        )

    def test_the_ledger_paragraph_still_specifies_a_scoped_round(self) -> None:
        # Distinct failure from the one above, which is why it is its own test. The
        # two engine sites can agree perfectly while the ledger paragraph stops
        # specifying the range -- and then nothing writes the anchor down, every
        # resumed round takes step 8's full fallback, and the only symptom is a
        # saving that silently stopped.
        #
        # Pinned on the SPEC's spelling, not on the anchor name: an earlier draft
        # asserted the anchor name, which also appears in the paragraph's rationale,
        # so deleting the whole format spec and leaving the rationale passed green.
        body = self._span(
            self._engine(), *self._LEDGER_REGION,
            "the ledger's - Code-review: paragraph",
        )
        self.assertIn(
            self._normalize(self._LEDGER_SPELLING),
            self._normalize(body),
            "the Ledger format's `- Code-review:` paragraph no longer specifies the "
            f"scoped-round spelling {self._LEDGER_SPELLING!r}.\n\n"
            "That spelling is what discharges 'the round's journal line records the "
            "commit range it was scoped to', and each element is where that round's "
            "anchor PERSISTS across /clear -- state lives in the ledger, not in "
            "context. Without it nothing writes the anchor down, so step 8's full "
            "fallback becomes the only path a resumed round can take.\n\n"
            "Do NOT satisfy this by mentioning the anchor in the surrounding prose: "
            "this constant is pinned on the format spec precisely because a rationale "
            "sentence once kept the check green while the spec was deleted.",
        )


class CurrencyExemptionAgreementTests(unittest.TestCase):
    """#33's currency clause claims step 10 already draws the same exemption line.

    The Gate-outcome invariant's currency clause says a change touching neither
    source nor tests re-arms nothing, **"the same line step 10 already draws for
    its own fixes."** That phrase is a claim about another passage, so the two
    exemption lists are a coupling: edit one and the claim silently becomes false.

    **This is not hypothetical -- it is the defect this test was written for.**
    #33's own code review caught it at the round cap. The fix round dropped
    ``a test name`` from the clause's list and left step 10's copy carrying it,
    so the clause asserted an agreement that no longer held **and** step 10 kept
    telling the orchestrator that a test-only fix re-arms nothing. That is a live
    fail-open at the acceptance gate: step 6's hermetic trigger fires on *any*
    added or modified test ("over-running costs one command, under-running is the
    entire defect"), so the exemption skipped a gate that was due. The whole suite
    was green across that desync.

    What is asserted is a **string** coupling in two located regions -- the same
    shape, and for the same reasons, as ``ResumeHandoffPointerTests`` and
    ``PlanGateFrozenBlockTests``. The lists are *extracted from the prose and
    compared to each other*, never compared to a copy pinned here: a pinned copy
    would pass for any edit that changed both regions in the same wrong direction
    only by accident, and would need updating on every legitimate reword.

    It says nothing about whether the exemption is a good idea -- only that its
    two statements still say the same thing, and that neither has re-acquired the
    test-shaped item that made it fail open.

    **What this class deliberately does NOT guard, and why you should not add it.**
    Neither the *polarity* nor the *predicate* of the test-only carve-out is
    pinned. Both passages must also say a test-only change is **not** exempt (step
    6's hermetic trigger fires on any added or modified test), and nothing here
    checks that. Three successive attempts were made and each was judged
    outcome-shaped by a fresh checker, every one defeated by a one-word edit:
    asserting the token ``test-only`` appears (delete the ``not``); then matching
    ``test-only change is not`` (reword to ``is not excluded from that set``);
    then a closed alternation of accepted phrasings -- rejected before it was
    written, because an enumerated list of blessed wordings is the
    ``ALLOWED_NON_BINDINGS``/``_STOPWORDS`` shape this file's own header warns
    about, where the easy way to fix a failing test is to append the new phrasing.

    The ruling that ended it (architect, #33 pass 3) generalizes past this class:
    **a mechanical guard can pin a coupling's identity and existence, never a
    proposition's truth.** The other prose guards here pin *labels* -- arbitrary
    strings where any change is a real change. Polarity is not that, and chasing
    it displaces the defect one token at a time forever. The real fix is a product
    fix -- word the engine so the dangerous reading requires *adding* a claim
    rather than deleting a word -- which is filed separately, not bolted on here.
    Polarity is review's to own. Do not "complete" this class by adding it back.
    """

    # The lead-in differs by design (step 10 speaks of "its own fixes", the clause
    # of any change), so the anchor is the shared consequent, not the whole sentence.
    _LIST_RE = re.compile(r"--\s*(a [^-]+?)\s*--\s*re-arms nothing")

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("—", "--").replace("*", ""))

    def _span(self, start: str, end: str, label: str) -> str:
        text = _ENGINE.read_text(encoding="utf-8")
        i = text.find(start)
        self.assertNotEqual(
            i, -1, f"cannot locate the start of the {label} region ({start!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        return text[i:j]

    def _exemptions(self) -> tuple:
        regions = {
            "step 10 (draws the line)": self._span(
                "### 10. Verify done", "### 11. Merge", "step 10",
            ),
            "currency clause (claims to match it)": self._span(
                "**Currency — a verdict is bound to the commit it ran on.**",
                "**Fresh-re-check invariant",
                "currency clause",
            ),
        }
        found = {}
        for label, body in regions.items():
            match = self._LIST_RE.search(self._normalize(body))
            if match is not None:
                found[label] = match.group(1).strip()
        return regions, found

    def test_the_extractor_actually_finds_both_exemption_lists(self) -> None:
        """Guards the guard: an unmatched region would silently assert nothing."""
        regions, found = self._exemptions()
        missing = sorted(set(regions) - set(found))
        self.assertEqual(
            missing, [],
            f"the exemption list could not be extracted from: {missing}. This test "
            "compares the two lists against each other, so a region that stops "
            "matching makes it vacuous rather than failing loudly. Re-anchor "
            "_LIST_RE against the current wording; do not delete a region to make "
            "this pass.",
        )

    def test_both_statements_of_the_exemption_agree(self) -> None:
        _, found = self._exemptions()
        lists = set(found.values())
        self.assertEqual(
            len(lists), 1,
            "step 10 and the currency clause state DIFFERENT exemption lists: "
            f"{found!r}. The clause claims 'the same line step 10 already draws', "
            "so the two must agree or that claim is false while both passages "
            "still read correctly. Edit them together.",
        )

    def test_neither_statement_exempts_a_test_only_change(self) -> None:
        _, found = self._exemptions()
        for label, items in found.items():
            with self.subTest(region=label):
                self.assertNotIn(
                    "test", items.lower(),
                    f"{label} lists {items!r} as re-arming nothing, and it names a "
                    "test. A test-only change is NOT sourceless: step 6's hermetic "
                    "trigger fires on any added or modified test, so exempting one "
                    "skips a gate that is due -- the fail-open #33's review caught. "
                    "If the exemption genuinely needs to cover a test, change step "
                    "6's trigger first and say so there.",
                )


class FindingClassAgreementTests(unittest.TestCase):
    """#121's finding classes are restated in pairs; each pair must agree.

    Two couplings, both the same shape as ``CurrencyExemptionAgreementTests``:
    the lists are **extracted from the prose and compared to each other**, never
    to a copy pinned here. A pinned copy passes for any edit that changes both
    regions in the same wrong direction, and needs updating on every legitimate
    reword.

    **Coupling 1 -- the round bound is written twice.** Step 8 states it
    mid-step ("Bounded to 2 rounds ... escalate to the human, do not loop", with
    ~90 further lines of step 8 after it); the Fresh-re-check invariant restates
    the same bound under "there is no ladder".
    #121 changed the *semantics* of both -- only BLOCKING re-arms. Drop a class
    from one and the engine names different classes in its two statements of the
    bound, with every word of both passages still reading correctly.

    **Coupling 2 -- the merge gate's always-escalate list is written twice.**
    Step 11 enumerates it, and the ``escalation-only`` bullet in Ledger format
    enumerates it again for the mode that can auto-merge. The second is the one
    that matters most: it governs the path with **no human in it**, so a
    condition present in step 11 and missing there is a row that auto-merges past
    a finding step 11 would have stopped for. The first draft of #121's own plan
    named only step 11 and the architect caught it -- this test is that
    near-miss made mechanical.

    **What coupling 1 does NOT guard, stated because an earlier draft claimed it
    did.** It compares the *set of class tokens* named in each region, and says
    nothing about the round **bound** itself -- the numeral -- so a mutation
    changing the cap on one side only survives it. That earlier draft cited
    #114/AC7, which is exactly about the bound moving in lockstep; the claim is
    **withdrawn**, and the bound-number comparison belongs with #114, where the
    bound actually moves.

    **The span anchor is deliberately free of the CAP numeral** -- it still
    contains ``round 1``, so "numeral-free" would overstate it. An earlier draft
    anchored on the literal ``"Bounded to 2 rounds"``, which pinned the cap by
    accident: the one-sided cap mutation the paragraph above says survives was in
    fact killed, and -- worse -- a *legitimate* both-sides cap change went red
    with a message inviting the maintainer to bump the literal. #114 is queued to
    make exactly that change. Do not reintroduce the cap numeral into either
    anchor.

    **A residual coupling to #114 remains, and is recorded rather than implied.**
    The anchor spans the round *enumeration* (``round 1 being the review``), so a
    cap change that also rewords that parenthetical -- the likely shape of #114's
    edit -- still goes red. It fails **safely**: the message is ``cannot locate
    the start of the step 8 bound region ... re-anchor this test before trusting
    it``, which is correct guidance rather than an invitation to bump a literal.
    Improved, not eliminated.

    **What coupling 2 does not reach.** It guards 2 of the 3+ statements of the
    always-escalate conditions: ``README.md`` states them a third time and the
    Escalation rubric carries a differently-worded mention. Neither is compared
    here -- their agreement is review's to own. Three further gaps, all measured
    by mutation rather than reasoned about:

    * **Step 11's peer bullets are outside the span.** It starts at "none of the
      always-escalate conditions apply:", so a condition added as its own
      ``- ... , AND`` bullet -- which is how ``hold`` and the release-bump
      condition are already written -- is invisible here.
    * **``_HOLD_ROW`` is subtracted from both sides unconditionally**, so the
      escalation-only bullet dropping ``a hold row`` altogether is not caught.
    * **A condition inserted before the introducing ``:``** is not parsed.

    **Extractor assumptions, and how each fails.** The first ``:`` in a region
    introduces the list, and no item contains a non-parenthetical comma. An
    **asymmetric** violation of either fails loud -- but via
    ``test_both_statements_of_the_always_escalate_list_agree``, *not* via the
    guard-on-guard tests, which stay green because both regions still parse to
    three or more items. A violation applied **identically to both regions** --
    the likely shape, since this project's convention is to edit them together --
    is absorbed **silently**: both lists mis-split the same way and still agree.
    That is the one blind spot worth knowing before trusting a green run.

    **And what neither guards, deliberately.** Not the polarity or the
    correctness of any rule: nothing here knows that EDITORIAL *should* be the
    non-re-arming class, or that the promotion is one-directional. That is the
    #33 ceiling ruling -- a mechanical guard pins a coupling's identity and
    existence, never a proposition's truth -- and three attempts at the polarity
    form were each defeated by a one-word edit. Do not "complete" this class by
    adding it. Polarity is review's to own.
    """

    _CLASS_TOKENS = ("BLOCKING", "EDITORIAL")
    _HOLD_ROW = "a hold row"

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"\([^()]*\)", " ", text)      # drop parentheticals
        text = text.replace("**", "").replace("`", "").replace("*", "")
        return re.sub(r"\s+", " ", text).strip()

    def _span(self, start: str, end: str, label: str) -> str:
        text = _ENGINE.read_text(encoding="utf-8")
        i = text.find(start)
        self.assertNotEqual(
            i, -1, f"cannot locate the start of the {label} region ({start!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it.",
        )
        return text[i:j]

    # ---- coupling 1: the two statements of the round bound ----

    def _bound_regions(self) -> dict:
        return {
            "step 8 (the gate's own bound)": self._span(
                " rounds (round 1 being the review",
                "**Round 1 reads the whole change",
                "step 8 bound",
            ),
            "Fresh-re-check invariant (restates it)": self._span(
                "**The bound \u2014 one fresh re-check",
                "**Reaching a cap is a handoff", "invariant bound",
            ),
        }

    def _classes_named(self, body: str) -> frozenset:
        return frozenset(t for t in self._CLASS_TOKENS if t in body)

    def test_the_extractor_actually_finds_a_class_in_both_bound_regions(self) -> None:
        """Guards the guard: two empty sets compare equal and assert nothing."""
        for label, body in self._bound_regions().items():
            with self.subTest(region=label):
                self.assertNotEqual(
                    self._classes_named(body), frozenset(),
                    f"{label} names neither BLOCKING nor EDITORIAL. The agreement "
                    "check below compares the two regions to each other, so a "
                    "region that names no class makes it vacuous rather than "
                    "failing. Re-anchor the span, or restore the class the bound "
                    "depends on -- do not delete a region to make this pass.",
                )

    def test_both_statements_of_the_round_bound_name_the_same_classes(self) -> None:
        found = {k: self._classes_named(v) for k, v in self._bound_regions().items()}
        shown = {k: sorted(v) for k, v in found.items()}
        self.assertEqual(
            len(set(found.values())), 1,
            "step 8 and the Fresh-re-check invariant state the round bound in "
            f"terms of DIFFERENT finding classes: {shown}. They are two "
            "restatements of one bound, so they must move together or the engine "
            "says two different things about when a round escalates while both "
            "passages still read correctly.",
        )

    # ---- coupling 2: the two statements of the always-escalate list ----

    def _escalate_regions(self) -> dict:
        return {
            "step 11 (the human merge gate)": self._span(
                "none of the always-escalate conditions apply:", "**Default-deny:**",
                "step 11 escalate list",
            ),
            "escalation-only bullet (the auto-merge path)": self._span(
                "The human merge gate is **retained**", "\u2014 **and, by default-deny",
                "escalation-only escalate list",
            ),
        }

    def _conditions(self, body: str) -> frozenset:
        body = self._normalize(body)
        i = body.find(":")
        self.assertNotEqual(i, -1, "no ':' introducing the condition list")
        items = set()
        for raw in body[i + 1:].split(","):
            item = re.sub(r"^(or|and)\s+", "", raw.strip().rstrip(".")).strip()
            if not item:
                continue
            items.add(item.lower())
        # step 11 carries `hold` as its own bullet above the list; the
        # escalation-only bullet folds it in. That divergence is structural, so
        # it is excluded explicitly rather than by a fuzzy comparison.
        # DO NOT GROW THIS EXCLUSION. It has the shape CLAUDE.md flags for
        # ALLOWED_NON_BINDINGS and _STOPWORDS: appending a term is the cheap way
        # to green a failing comparison, and each one is a condition this guard
        # stops comparing. A new divergence is a finding about the engine, not a
        # constant to add here.
        return frozenset(x for x in items if x != self._HOLD_ROW)

    def test_the_extractor_actually_finds_both_escalate_lists(self) -> None:
        """Guards the guard: a region that matches but stops parsing asserts nothing.

        An *unmatched* region is not the risk here -- ``_span`` asserts, so both
        tests go red loudly. The silent case is a region that matches and then
        parses to almost nothing, which would make the comparison below vacuous.
        """
        for label, body in self._escalate_regions().items():
            with self.subTest(region=label):
                self.assertGreaterEqual(
                    len(self._conditions(body)), 3,
                    "fewer than three always-escalate conditions extracted from "
                    f"{label}. This test compares the two lists to each other, so "
                    "a region that stops parsing makes it vacuous. Re-anchor the "
                    "span or the splitter; do not drop a region to make this pass.",
                )

    def test_both_statements_of_the_always_escalate_list_agree(self) -> None:
        found = {k: self._conditions(v) for k, v in self._escalate_regions().items()}
        (a_label, a), (b_label, b) = found.items()
        self.assertEqual(
            a, b,
            "the merge gate's always-escalate conditions are enumerated twice and "
            f"the two lists DIFFER.\n  only in {a_label}: {sorted(a - b)}\n  only "
            f"in {b_label}: {sorted(b - a)}\nThe escalation-only bullet governs "
            "the path with no human in it, so a condition present in step 11 and "
            "missing there auto-merges past something step 11 would have stopped "
            "for. Edit them together.",
        )


class GuardEfficacyLensLabelTests(unittest.TestCase):
    """#122's mandatory review lens hangs on one label spelled the same everywhere.

    Step 8 declares a **floor**: on a round it is due on, the finder roster must carry a
    lens with a fixed label. Several other passages depend on that exact string -- the
    distinction from the acceptance gate's Class B pass, the journal-slot separation,
    the roster's naming duty, Tool surface's bound on the fan-out, the
    ``mutation-survivors`` slot's exclusion, Part 2's pointer, and the recipe's
    second-caller note. Rename it at one site and the others go dark while every word
    still reads correctly: a roster then satisfies a floor that mandates something
    else, and nothing else in this suite notices.

    **No count of those sites appears here, deliberately.** An earlier draft said "two
    other passages" and was wrong within one commit -- the set grew as the change did,
    and a stated tally is the enumerable assertion this repo has retracted repeatedly.
    ``_REGIONS`` is the list; read it rather than a sentence about it.

    What is asserted is a **string** coupling, not a meaning. This does NOT assert that
    the lens reads rather than mutates, that its due-when clause is correctly scoped,
    or that the Class B distinction is true -- those are propositions about prose,
    which ``CLAUDE.md`` records as beyond what a guard over prose can pin. They stay
    with review. Do not "complete" this test by adding them.

    **Regions are located by SECTION HEADING first, then narrowed**, the nesting
    ``PlanGateFrozenBlockTests._plan_template_fence`` uses.
    An earlier draft anchored the step-8 regions on the paragraphs' own opening words,
    so a region was defined by the text under test: moving the floor out of step 8 --
    into an aside, or past a renumber -- left every assertion green with the floor no
    longer at the gate.

    **Anchored per region, never counted globally.** A total passes when one site loses
    the label and another gains a spare mention, and cannot say *which* site went dark.

    **What this does not pin, stated because the engine's own authoring rule makes an
    overclaiming test message a defect.** A region check is satisfied by *any*
    occurrence, so within a region that mentions the label more than once, drift of one
    mention beside a surviving sibling passes. The mandate is therefore pinned
    separately -- including its modality, since a ``must`` softened to ``should`` turns
    the floor into a suggestion -- but that pin is a *literal*, so a scope condition
    appended after it ("...when the reviewer judges it warranted") would still pass.
    Polarity and scope of the mandate stay with review; ``CLAUDE.md`` records why a
    prose guard cannot reach them, and adding the assertion back is the displacement
    loop, not a gap.
    """

    _LABEL = "`guard-efficacy`"
    _MANDATE = "must carry a lens labelled `guard-efficacy`"
    # The label+separator a SKIP must be written with. Pinned as a literal for the same
    # reason the mandate is: the region check passes on any sibling mention, and this is
    # the spelling that makes a not-due floor auditable rather than silent.
    #
    # NO leading backtick: an earlier draft carried one, which matched ONLY the prose
    # restatement and left the enumerated bullet -- the rendering the message names --
    # unpinned, so renaming the bullet alone passed.
    _NOT_DUE = "guard-efficacy -- not due:"
    # The enumerated bullet must carry the rendering WHOLE and CONTIGUOUS -- marker,
    # label, separator and the one legal reason, as one literal.
    #
    # Two weaker versions shipped and were each defeated by a mutation. A containment
    # check over the region fell to renaming the bullet plus a spare mention anywhere in
    # the region. Splitting it into a bullet-opener pin plus a separate reason pin fell
    # to the same trick one level down: the sub-region below is anchored on bullet 1's
    # TAIL and on bullet 3, so all of bullet 2's gloss is inside it, and a decoy planted
    # there satisfies a reason pin while the rendering itself reads
    # "not due: the reviewer judged the delta inert".
    #
    # A LONGER literal was the third attempt and failed the same way: `assertIn` over a
    # span is a presence check whatever its literal, so a longer decoy defeats it. What
    # closes the hole is asserting POSITION -- the rendering must be the FIRST thing in
    # its span -- which is why the start anchor runs to the end of bullet 1's sentence.
    # This constant REPLACES `_SKIP_BULLET` and `_NOT_DUE_REASON` rather than joining
    # them: both were strict substrings read over the same span, so `assertIn` of this
    # one strictly implied both, and keeping them adds knobs, not coverage.
    _SKIP_RENDERING = ("- **`… ; guard-efficacy -- not due: "
                       "every path in the delta is declared docs or research`**")

    # The two places inside the roster region that must spell the rendering, located
    # SEPARATELY rather than counted. A total over the region is satisfied by one real
    # rendering plus a spare mention and cannot say which site went dark -- the failure
    # this class's own docstring names, and which an earlier draft of this test walked
    # straight into with ``count(...) >= 2``.
    _SKIP_SITES = {
        "the prose restatement": (
            "**Every round-1 roster names",
            "The renderings, enumerated for the reason"),
        "the enumerated bullet": (
            "and `nothing to read` where a lens found nothing to apply its "
            "question to (above).",
            "- **`roster: none (recheck)`**"),
    }

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("\u2014", "--"))

    def _engine(self) -> str:
        return _ENGINE.read_text(encoding="utf-8")

    def _span(self, text: str, start: str, end: str, label: str) -> str:
        # Same slicing as the six sibling helpers in this file: the body INCLUDES the
        # start anchor. Do not diverge -- an earlier draft returned
        # text[i + len(start):j], which silently made an anchor-exclusion test vacuous.
        # Because the anchor IS in the body, no inner start anchor may contain the
        # label; test_no_inner_anchor_contains_the_label enforces that.
        i = text.find(start)
        self.assertNotEqual(
            i, -1, f"cannot locate the start of the {label} region ({start!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it."
        )
        j = text.find(end, i + len(start))
        self.assertNotEqual(
            j, -1, f"cannot locate the end of the {label} region ({end!r}) in "
            "loop-engine.md -- re-anchor this test before trusting it."
        )
        return text[i:j]

    _OUTER = {
        "step 8": ("### 8. Code review", "### 9. Security review"),
        "Tool surface": ("### Tool surface —", "## Ledger format"),
        "Ledger format": ("## Ledger format", "## Router — classification"),
        "AC-verifier": ("## AC-verifier", "## Initialization procedure"),
        "Gates": ("## Gates, convergence & resting states", "**Convergence & the resting"),
    }
    # (outer, inner-start, inner-end) -- every inner start anchor excludes the label.
    _REGIONS = {
        "step 8's floor (mandates the lens)": (
            "step 8", "**One lens is a floor, not a choice:", "**What it asks.**"),
        "step 8's Class B distinction table": (
            "step 8", "**This lens is NOT the acceptance gate's Class B pass",
            "**A surviving mutant is step 10's"),
        "step 8's journal-slot separation": (
            "step 8", "**A surviving mutant is step 10's",
            "**Record the round's lens roster"),
        "step 8's roster naming duty": (
            "step 8", "**Every round-1 roster names",
            "**Keep the floor lens out of any later tier"),
        "Tool surface's bound on the fan-out": (
            "Tool surface", "Other bounds are unaffected:", "- **Isolated.**"),
        "the mutation-survivors slot's exclusion": (
            "Ledger format", "**This slot is not where a step-8",
            "The three readings exist because"),
        "AC-verifier Part 2 (the pointer back)": (
            "AC-verifier", "**Part 2 \u2014 Class B: mutation survivors.**",
            "*Why a checklist cannot find these*"),
        "the recipe's second-caller note": (
            "Gates", "(**This recipe has a second caller.**",
            "**Why a read is a legitimate check here"),
    }

    def _outer(self):
        text = self._engine()
        return {n: self._span(text, s, e, f"{n} section")
                for n, (s, e) in self._OUTER.items()}

    def _regions(self):
        outer = self._outer()
        return {label: self._span(outer[o], s, e, label)
                for label, (o, s, e) in self._REGIONS.items()}

    def test_every_anchor_is_unique_within_its_scope(self) -> None:
        """``str.find`` takes the FIRST match, so a duplicated anchor silently
        relocates a region to a span that can sweep up unrelated mentions -- green
        while the passage it was meant to pin has gone."""
        text = self._engine()
        for name, (s, e) in self._OUTER.items():
            with self.subTest(section=name):
                self.assertEqual(text.count(s), 1, f"section anchor {s!r} is not unique")
                self.assertEqual(text.count(e), 1, f"section anchor {e!r} is not unique")
        outer = self._outer()
        for label, (o, s, e) in self._REGIONS.items():
            with self.subTest(region=label):
                self.assertEqual(
                    outer[o].count(s), 1,
                    f"the start anchor for {label} occurs {outer[o].count(s)} times "
                    f"in {o}; a region located by a non-unique anchor is not the "
                    "region this test names. Re-anchor it.")
                self.assertEqual(
                    outer[o].count(e), 1,
                    f"the end anchor for {label} occurs {outer[o].count(e)} times "
                    f"in {o}. Re-anchor it.")
        roster = self._normalize(self._regions()["step 8's roster naming duty"])
        for site, (s, e) in self._SKIP_SITES.items():
            with self.subTest(skip_site=site):
                ns, ne = self._normalize(s), self._normalize(e)
                self.assertEqual(
                    roster.count(ns), 1,
                    f"the start anchor for {site} occurs {roster.count(ns)} times in "
                    "the roster region; str.find takes the FIRST, so a duplicate "
                    "relocates the sub-region and the pin can pass on a decoy while "
                    "the real rendering is renamed. Re-anchor it.")
                self.assertEqual(
                    roster.count(ne), 1,
                    f"the end anchor for {site} occurs {roster.count(ne)} times in "
                    "the roster region. Re-anchor it.")

    def test_no_inner_anchor_contains_the_label(self) -> None:
        """``_span`` includes the start anchor in the body, so an anchor carrying the
        label would satisfy its own region's containment check. This is the assertion
        that keeps that from going unnoticed -- and unlike the version it replaces, it
        can actually fail: the earlier draft excluded both anchors by construction, so
        it certified a property the slicing made unconditional."""
        for label, (_o, s, e) in self._REGIONS.items():
            with self.subTest(region=label):
                self.assertNotIn(
                    self._LABEL, self._normalize(s + " " + e),
                    f"the {label} anchors contain the lens label, so its containment "
                    "check would pass on the boundary rather than the body. "
                    "Re-anchor on text that excludes the label.")

    def test_the_floor_mandates_the_label_with_its_modality(self) -> None:
        floor = self._normalize(self._regions()["step 8's floor (mandates the lens)"])
        self.assertIn(
            self._MANDATE, floor,
            "step 8's floor no longer carries the mandate clause verbatim.\n\n"
            f"Expected (normalized): {self._MANDATE!r}\n\n"
            "The region check passes on any mention of the label, so this is what "
            "pins the one occurrence that does the mandating -- and it includes "
            "`must` deliberately, because softening the modality turns the floor "
            "into a suggestion while the paragraph still reads as a floor. NOTE what "
            "this does not catch: a scope condition appended after the clause leaves "
            "it intact. That is review's, not this test's. If you reworded the "
            "mandate deliberately, update _MANDATE and _LABEL together.")

    def test_each_skip_site_spells_the_rendering(self) -> None:
        """Both places the roster region carries the not-due rendering -- the prose
        restatement and the enumerated bullet -- are located and checked SEPARATELY.
        Counting occurrences over the region instead is satisfied by one surviving
        rendering plus a spare mention, which is the anti-pattern this class's
        docstring forbids and which a previous draft of this test shipped."""
        roster = self._normalize(self._regions()["step 8's roster naming duty"])
        for site, (start, end) in self._SKIP_SITES.items():
            with self.subTest(site=site):
                ns, ne = self._normalize(start), self._normalize(end)
                self.assertNotIn(
                    self._NOT_DUE, ns,
                    f"the start anchor for {site} contains the rendering, so its "
                    "containment check would pass on the boundary. Re-anchor it.")
                span = self._span(roster, ns, ne, f"the roster region's {site}")
                self.assertIn(
                    self._NOT_DUE, span,
                    f"{site} no longer spells the not-due rendering with the lens "
                    f"label.\n\nExpected (normalized): {self._NOT_DUE!r}\n\n"
                    "This is the rendering a SKIPPED floor must be written as, so it "
                    "is what makes a not-due round auditable instead of silent. If "
                    "you reworded it deliberately, update _NOT_DUE.\n\n"
                    "Never drop a site from _SKIP_SITES to make this pass -- the two "
                    "sites are located separately because a total over the region "
                    "cannot say which one went dark.")

    def test_the_skip_bullet_carries_the_whole_rendering(self) -> None:
        """The rendering must be the FIRST thing in the enumerated bullet's span.

        Position is the assertion. Presence is not enough at any literal length: the
        span runs from bullet 1's tail to bullet 3, so a decoy planted anywhere in
        bullet 2's gloss -- a parenthetical, a nested sub-bullet, a "superseded
        spelling" note -- satisfies a containment check while the rendering itself
        reads "not due: the reviewer judged the delta inert". Three pins were defeated
        that way on this branch (a region-wide check, a split opener/reason pair, and a
        single longer literal) before the assertion's SHAPE was changed rather than its
        text.

        What this does NOT pin: that the reason list is closed, or that this is the
        only legal reason. Those are propositions about the prose, which ``CLAUDE.md``
        puts beyond a guard's reach; a second rendering added elsewhere passes.
        """
        start, end = self._SKIP_SITES["the enumerated bullet"]
        roster = self._normalize(self._regions()["step 8's roster naming duty"])
        ns = self._normalize(start)
        span = self._span(roster, ns, self._normalize(end),
                          "the roster region's enumerated bullet")
        expected = ns + " " + self._SKIP_RENDERING
        self.assertTrue(
            span.startswith(expected),
            "the enumerated skip rendering is not the first thing in its bullet.\n\n"
            f"Expected the span to start: {expected!r}\n\n"
            f"Span starts:                {span[:len(expected)]!r}\n\n"
            "Either the label, the separator, or the one legal reason changed. The "
            "reason is the due-when's only conjunct negated, so if the due-when "
            "gained or lost a conjunct the rendering changed with it and BOTH the "
            "engine and _SKIP_RENDERING need updating -- deliberately, not to make "
            "this pass. A mention of the old text elsewhere in the bullet does NOT "
            "satisfy this -- the rendering must come first, which is the whole point "
            "of pinning position rather than presence.")

    def test_every_region_that_depends_on_the_lens_label_spells_it_the_same(
        self,
    ) -> None:
        missing = sorted(
            label for label, body in self._regions().items()
            if self._LABEL not in self._normalize(body))
        self.assertEqual(
            missing, [],
            "these region(s) of loop-engine.md do not carry the mandatory review "
            f"lens label: {missing}.\n\n"
            f"Expected (normalized): {self._LABEL!r}\n\n"
            "A MISMATCH IS SILENT AND FAILS OPEN. The floor is satisfied by a roster "
            "naming this exact label, so if one region renames it and the others do "
            "not, a roster can satisfy a floor nothing now mandates while all the "
            "passages still read correctly.\n\n"
            "Each region is checked SEPARATELY on purpose: a global count passes "
            "when one region loses the label and another gains a spare mention. If "
            "you renamed the lens deliberately, rename it in every region and update "
            "_LABEL. Never drop a region from _REGIONS to make this pass.")


if __name__ == "__main__":
    unittest.main()
