#!/usr/bin/env python3
"""`tooling/check-humanizer-pass.py` checks that every post records a humanizer pass (#182).

**Why this module exists.** The guard scans `posts/` for dated posts. While `posts/`
holds none it prints `no posts found to check` and exits **0**, so without this
module it would be a check that has never been observed to fail -- the answer
`tests/test_check_og_cards.py` gives for `check-og-cards.py`, one file over.

**The control comes first.** `test_the_control_passes` asserts a well-formed post
passes; without it every negative case could be detecting a fixture that was already
broken. **Each negative case asserts the specific complaint**, never merely a
non-zero exit, for the reason `_assert_complains` gives in
`tests/test_posts_frontmatter.py`.

**What it pins about the two couplings the guard has, and only that.**
`GrammarSourceTests` pins that the guard and `tests/test_posts_frontmatter.py` both
take their verdict from `tooling/attestation.py` (AC5). `ParserReuseTests` pins that
the guard reads the value through the publisher's `read_field` (AC1). Each is a
coupling's identity, not a proposition's truth (`tests/CLAUDE.md`): neither says the
grammar is right.

Stdlib only, per `CLAUDE.md`. Run with:
    python3 -m unittest tests.test_check_humanizer_pass
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chp = _load("check_humanizer_pass", _REPO_ROOT / "tooling" / "check-humanizer-pass.py")
contract = _load("posts_contract", _REPO_ROOT / "tests" / "test_posts_frontmatter.py")

_POST_STEM = "2026-10-01-the-team-you-didnt-hire"

_GOOD = """---
layout: post
title: "The team you didn't hire"
date: 2026-10-01 09:00:00-0700
description: "Why the roles on a dev team outlived the people who filled them."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "foundation"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/the-team-you-didnt-hire-og.png
og_card_source: posts/images/the-team-you-didnt-hire/og-card.png
featured: false
claude_code_version_verified: v2.1.243
humanizer_pass: v3.0.0
claims_verified: 2026-10-01
---

Body text.
"""


class _PostTree(unittest.TestCase):
    """A throwaway repo with `posts/`, and the guard's publisher REPO_ROOT repointed.

    The default glob reads `REPO_ROOT` off the publisher instance the GUARD loaded --
    `chp.ptp` -- so that is the object patched.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "posts").mkdir(parents=True)
        patcher = mock.patch.object(chp.ptp, "REPO_ROOT", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_post(self, text: str = _GOOD, stem: str = _POST_STEM) -> Path:
        path = self.repo / "posts" / f"{stem}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def mutated(self, old: str, new: str) -> str:
        self.assertEqual(_GOOD.count(old), 1, "fixture drifted; %r is not unique" % old)
        self.assertNotEqual(old, new, "a no-op substitution asserts nothing")
        return _GOOD.replace(old, new, 1)

    def with_pass(self, value: str) -> str:
        return self.mutated("humanizer_pass: v3.0.0\n", f"humanizer_pass: {value}\n")

    def run_guard(self, *paths: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = chp.main([str(p) for p in paths])
        return code, out.getvalue(), err.getvalue()

    def assert_complains(self, result: tuple[int, str, str], *needles: str) -> None:
        code, out, err = result
        self.assertEqual(code, 1, "guard passed; expected a failure.\nout=%r" % out)
        for needle in needles:
            self.assertIn(needle, out + err, "no complaint mentioning %r" % needle)


class ControlTests(_PostTree):
    def test_the_control_passes(self) -> None:
        code, out, err = self.run_guard(self.write_post())
        self.assertEqual(code, 0, out + err)
        self.assertIn("1 versioned, 0 declined", out)

    def test_the_control_also_satisfies_the_contract(self) -> None:
        # The fixture is a real post, not a guard-shaped fragment, so a case below
        # that the guard rejects is rejected for the humanizer_pass line alone.
        self.assertEqual(contract.check_post(_POST_STEM, _GOOD), [])


class ValueTests(_PostTree):
    def test_missing_field_fails(self) -> None:
        post = self.write_post(self.mutated("humanizer_pass: v3.0.0\n", ""))
        self.assert_complains(self.run_guard(post), "no `humanizer_pass` in frontmatter")

    def test_empty_field_fails(self) -> None:
        post = self.write_post(self.mutated("humanizer_pass: v3.0.0", "humanizer_pass:"))
        self.assert_complains(self.run_guard(post), "`humanizer_pass` is empty")

    def test_predates_is_not_accepted(self) -> None:
        # AC2. The source guard accepts it; this series has no pre-convention archive.
        post = self.write_post(self.with_pass("predates"))
        self.assert_complains(self.run_guard(post), "`humanizer_pass: predates` is not")

    def test_malformed_values_are_rejected(self) -> None:
        # The source guard accepts the first three; the contract rejects all five, and
        # the guard must not be the weaker of the two checks on the grammar (AC5).
        for value in ("3.0.0", "v3.0", "v3.0.0 # 2026-10-01", "yes", "true"):
            with self.subTest(value=value):
                post = self.write_post(self.with_pass(value))
                self.assert_complains(self.run_guard(post), f"`humanizer_pass: {value}`")

    def test_a_declined_value_with_a_stray_space_is_rejected(self) -> None:
        # The source strips the space inside the quotes and counts this as declined;
        # the contract rejects it, so the guard does too.
        post = self.write_post(self.with_pass('"none "'))
        self.assert_complains(self.run_guard(post), "`humanizer_pass: none ` is not")

    def test_a_quoted_version_passes(self) -> None:
        code, out, err = self.run_guard(self.write_post(self.with_pass('"v3.0.0"')))
        self.assertEqual(code, 0, out + err)

    def test_none_passes_and_is_counted_as_declined(self) -> None:
        # AC3: declined is its own number, not folded into the pass count.
        code, out, err = self.run_guard(self.write_post(self.with_pass("none")))
        self.assertEqual(code, 0, out + err)
        self.assertIn("0 versioned, 1 declined", out)
        self.assertIn("pass deliberately declined", out)

    def test_versioned_and_declined_are_counted_separately(self) -> None:
        a = self.write_post(stem="2026-10-01-a")
        b = self.write_post(self.with_pass("none"), stem="2026-10-02-b")
        c = self.write_post(self.with_pass("none"), stem="2026-10-03-c")
        code, out, err = self.run_guard(a, b, c)
        self.assertEqual(code, 0, out + err)
        self.assertIn("1 versioned, 2 declined", out)

    def test_every_failing_post_is_reported_not_just_the_first(self) -> None:
        a = self.write_post(self.with_pass("yes"), stem="2026-10-01-a")
        b = self.write_post(self.with_pass("predates"), stem="2026-10-02-b")
        self.assert_complains(
            self.run_guard(a, b), "2026-10-01-a.md", "2026-10-02-b.md", "2 post(s)"
        )

    def test_the_declined_count_is_reported_on_a_failing_run_too(self) -> None:
        # AC3: the debt stays visible when some other post fails.
        bad = self.write_post(self.with_pass("yes"), stem="2026-10-01-bad")
        declined = self.write_post(self.with_pass("none"), stem="2026-10-02-declined")
        self.assert_complains(
            self.run_guard(bad, declined), "1 post(s) without", "1 other post(s) declined"
        )


class UnreadableInputTests(_PostTree):
    """Each lands in the per-post report; none escapes as a traceback."""

    def test_missing_frontmatter_is_reported(self) -> None:
        post = self.write_post("No frontmatter here.\n")
        self.assert_complains(self.run_guard(post), "no frontmatter block found")

    def test_a_non_utf8_file_is_reported(self) -> None:
        post = self.repo / "posts" / f"{_POST_STEM}.md"
        post.write_bytes(b"---\nhumanizer_pass: v3.0.0\n---\n\xff\xfe\n")
        self.assert_complains(self.run_guard(post), f"cannot read {post.name}")

    def test_a_missing_explicit_path_is_reported(self) -> None:
        post = self.repo / "posts" / "2026-10-01-absent.md"
        self.assert_complains(self.run_guard(post), "cannot read 2026-10-01-absent.md")


class SelectionTests(_PostTree):
    def test_the_default_glob_finds_dated_posts(self) -> None:
        self.write_post()
        code, out, _ = self.run_guard()
        self.assertEqual(code, 0, out)
        self.assertIn(_POST_STEM, out)

    def test_the_default_glob_skips_the_readme(self) -> None:
        self.write_post()
        (self.repo / "posts" / "README.md").write_text("# not a post\n", encoding="utf-8")
        code, out, _ = self.run_guard()
        self.assertEqual(code, 0, out)
        self.assertNotIn("README.md", out)

    def test_explicit_paths_override_the_glob(self) -> None:
        self.write_post(self.with_pass("yes"), stem="2026-10-01-bad")
        good = self.write_post(stem="2026-10-02-good")
        code, out, _ = self.run_guard(good)
        self.assertEqual(code, 0, out)
        self.assertNotIn("2026-10-01-bad", out)

    def test_an_empty_posts_dir_exits_zero_and_says_so(self) -> None:
        """Pinned deliberately: this is the repo's state today, and the source exits 1.

        A green run on an empty `posts/` means there was nothing to check, never that
        the guard works; the cases above are what show it can fail.
        """
        code, _, err = self.run_guard()
        self.assertEqual(code, 0)
        self.assertIn("no posts found to check", err)


class GrammarSourceTests(unittest.TestCase):
    """AC5: the guard and the contract checker take their verdict from one definition.

    Asserting only that both load `tooling/attestation.py` would pass a checker that
    loaded it and then decided with a grammar of its own. So each direction is
    observed through the verdict: a stubbed-permissive grammar must make `yes` pass,
    and a stubbed-strict one must make `v3.0.0` fail -- in the guard AND in the
    contract checker.
    """

    _ATTESTATION = _REPO_ROOT / "tooling" / "attestation.py"

    def test_both_load_the_real_shared_module(self) -> None:
        self.assertEqual(Path(chp.attestation.__file__).resolve(), self._ATTESTATION.resolve())
        self.assertEqual(
            Path(contract._attestation.__file__).resolve(), self._ATTESTATION.resolve()
        )

    def test_the_guard_takes_its_verdict_from_the_shared_grammar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yes = Path(tmp) / "2026-10-01-yes.md"
            yes.write_text(_GOOD.replace("humanizer_pass: v3.0.0", "humanizer_pass: yes", 1), encoding="utf-8")
            good = Path(tmp) / f"{_POST_STEM}.md"
            good.write_text(_GOOD, encoding="utf-8")
            with mock.patch.object(chp.attestation, "is_version_attestation", return_value=True):
                self.assertEqual(self._run(yes)[0], 0)
            with mock.patch.object(chp.attestation, "is_version_attestation", return_value=False):
                code, report = self._run(good)
            self.assertEqual(code, 1, report)
            self.assertIn("`humanizer_pass: v3.0.0` is not", report)

    @staticmethod
    def _run(post: Path) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = chp.main([str(post)])
        return code, out.getvalue() + err.getvalue()

    def test_the_contract_takes_its_verdict_from_the_shared_grammar(self) -> None:
        yes = _GOOD.replace("humanizer_pass: v3.0.0", "humanizer_pass: yes", 1)
        with mock.patch.object(contract._attestation, "is_version_attestation", return_value=True):
            self.assertEqual(contract.check_post(_POST_STEM, yes), [])
        with mock.patch.object(contract._attestation, "is_version_attestation", return_value=False):
            problems = contract.check_post(_POST_STEM, _GOOD)
        # Named, because the strict stub also fails claude_code_version_verified, which
        # would satisfy a bare non-empty check on its own.
        self.assertTrue(
            any(p.startswith("humanizer_pass must be") for p in problems), problems
        )

    def test_the_grammar_does_not_accept_a_trailing_newline_or_non_ascii_digits(self) -> None:
        for value in ("v3.0.0\n", "v\u0663.0.0"):
            with self.subTest(value=value):
                self.assertFalse(chp.attestation.is_version_attestation(value))


class ParserReuseTests(_PostTree):
    """AC1: the value the guard judges is the one the publisher's `read_field` returns."""

    def test_the_guard_loads_the_real_publisher(self) -> None:
        self.assertEqual(
            Path(chp.ptp.__file__).resolve(),
            (_REPO_ROOT / "tooling" / "publish-to-pages.py").resolve(),
        )

    def test_read_fields_answer_is_what_the_guard_judges(self) -> None:
        # The file on disk says v3.0.0; only a guard that asks read_field sees the
        # sentinel.
        post = self.write_post()
        with mock.patch.object(chp.ptp, "read_field", return_value="sentinel-from-read-field"):
            self.assert_complains(self.run_guard(post), "sentinel-from-read-field")


if __name__ == "__main__":
    unittest.main()
