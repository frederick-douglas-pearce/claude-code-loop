#!/usr/bin/env python3
"""`tooling/check-og-cards.py` checks that every post's OG card resolves (#180).

**Why this module exists at all, stated first because it is the whole argument.**
The guard scans `posts/` for dated posts. While `posts/` holds no dated post it
finds nothing, prints `no posts found to check`, and exits **0** -- so shipped
without this module it would be a check that has never been observed to fail.
That is the defect `tests/CLAUDE.md` names and the one
`tests/test_posts_frontmatter.py` answers with its own `CheckerBatteryTests`;
this is the same answer one file over, for the guard instead of the checker.

**The control comes first and is load-bearing.** `test_the_control_conforms`
asserts a well-formed post passes. Without it every negative case below could be
"detecting" a fixture that was already broken, and the module would certify
nothing while looking thorough.

**Each case asserts the SPECIFIC complaint, never merely that something failed.**
Asserting only a non-zero exit is outcome-shaped: a fixture that happens to trip
an unrelated fail-closed condition would keep the case green while the condition
under test was dead. Borrowed from `_assert_complains` in
`tests/test_posts_frontmatter.py`, for the same reason it exists there.

**What this module does NOT cover.** It does not run `assert_no_foreign_overwrite`
-- the guard structurally cannot, having no Pages checkout. See that guard's own
docstring, and `posts/README.md` -> The shared-namespace guard. It does not
check that a card is a valid image, only that the path resolves to a file. And
it asserts nothing about whether any real post is any good.

**No `git` binary is needed**, unlike `tests/test_publish_to_pages.py`'s Tier 2:
`build_plan` is Phase 1 and this guard never reaches `git_pages_owner`.

Stdlib only, per `CLAUDE.md`. Run with:
    python3 -m unittest tests.test_check_og_cards
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
_GUARD_PATH = _REPO_ROOT / "tooling" / "check-og-cards.py"

# Hyphenated filename, so it is not importable by name. Same idiom as
# tests/test_publish_to_pages.py and as the guard's own loader.
_spec = importlib.util.spec_from_file_location("check_og_cards", _GUARD_PATH)
assert _spec is not None and _spec.loader is not None, f"cannot load {_GUARD_PATH}"
cog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cog)


_CARD_BYTES = b"\x89PNG\r\n\x1a\n-not-really-a-png-but-bytes-are-bytes"

_POST_STEM = "2026-10-01-the-team-you-didnt-hire"
_SLUG = "the-team-you-didnt-hire"
_CARD_REL = f"posts/images/{_SLUG}/og-card.png"

_GOOD = f"""---
layout: post
title: "The team you didn't hire"
date: 2026-10-01 09:00:00-0700
description: "Why the roles on a dev team outlived the people who filled them."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "foundation"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/{_SLUG}-og.png
og_card_source: {_CARD_REL}
featured: false
claude_code_version_verified: v2.1.243
humanizer_pass: v3.0.0
claims_verified: 2026-10-01
---

Body text. The guard never reads past the frontmatter, but a post has one.
"""


class _PostTree(unittest.TestCase):
    """A throwaway repo with `posts/`, and the guard's REPO_ROOT repointed at it.

    `resolve_og_source` resolves `og_card_source` against the module-global
    `REPO_ROOT` of the publisher instance the GUARD loaded -- `cog.ptp` -- so
    that is the object to patch. Patching a separately-imported
    `publish_to_pages` would leave the guard reading the real repository and the
    fixtures would silently not apply.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "posts").mkdir(parents=True)
        patcher = mock.patch.object(cog.ptp, "REPO_ROOT", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- fixture helpers -------------------------------------------------

    def write_card(self, rel: str = _CARD_REL) -> Path:
        card = self.repo / rel
        card.parent.mkdir(parents=True, exist_ok=True)
        card.write_bytes(_CARD_BYTES)
        return card

    def write_post(self, text: str = _GOOD, stem: str = _POST_STEM) -> Path:
        path = self.repo / "posts" / f"{stem}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def mutated(self, old: str, new: str) -> str:
        """`_GOOD` with exactly one substitution, asserting the target is present.

        The assertion is what stops a drifted fixture turning a negative case
        into a vacuous pass -- the same guard `_mutated` applies in
        tests/test_posts_frontmatter.py.
        """
        self.assertEqual(
            _GOOD.count(old), 1, "fixture drifted; %r is not unique in _GOOD" % old
        )
        self.assertNotEqual(old, new, "a no-op substitution asserts nothing")
        return _GOOD.replace(old, new, 1)

    # -- running the guard -----------------------------------------------

    def run_guard(self, *paths: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [str(p) for p in paths]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cog.main(argv)
        return code, out.getvalue(), err.getvalue()

    def assert_complains(self, result: tuple[int, str, str], *needles: str) -> None:
        """The guard must fail AND name the thing that is broken."""
        code, out, err = result
        self.assertEqual(code, 1, "guard passed; expected a failure.\nout=%r" % out)
        report = out + err
        for needle in needles:
            self.assertIn(
                needle,
                report,
                "no complaint mentioning %r; got %r" % (needle, report),
            )


class ControlTests(_PostTree):
    def test_the_control_conforms(self) -> None:
        # If this fails, every negative case below is meaningless -- they would
        # be "detecting" a fixture that was already broken.
        self.write_card()
        post = self.write_post()
        code, out, err = self.run_guard(post)
        self.assertEqual(code, 0, "control post failed: %r %r" % (out, err))
        self.assertIn("[ok]", out)
        self.assertIn("resolvable OG card", out)


class FailClosedTests(_PostTree):
    """Cases over the fail-closed conditions `build_plan` enforces.

    Not one per condition, and deliberately not claimed as one: `build_plan`
    reaches about ten, and these cover six. `og_target_name`'s `_SAFE_BASENAME`
    branch in particular is unguarded by the whole suite -- confirmed by
    mutation, and filed on #1 rather than fixed here, because it is #179's
    surface.
    """

    def test_missing_og_card_source_is_caught(self) -> None:
        self.write_card()
        post = self.write_post(self.mutated(f"og_card_source: {_CARD_REL}\n", ""))
        self.assert_complains(self.run_guard(post), "missing `og_card_source`")

    def test_absolute_og_card_source_is_caught(self) -> None:
        self.write_card()
        post = self.write_post(self.mutated(_CARD_REL, "/etc/passwd"))
        self.assert_complains(self.run_guard(post), "repo-root-relative")

    def test_og_card_source_escaping_the_repo_is_caught(self) -> None:
        self.write_card()
        post = self.write_post(self.mutated(_CARD_REL, "../../" + _CARD_REL))
        self.assert_complains(self.run_guard(post), "escapes the repo root")

    def test_a_card_that_does_not_exist_is_caught(self) -> None:
        # The whole point of #180: shape alone would pass this post.
        post = self.write_post()  # note: no write_card()
        self.assert_complains(self.run_guard(post), "og card source not found")

    def test_missing_og_image_is_caught(self) -> None:
        self.write_card()
        post = self.write_post(
            self.mutated(
                f"og_image: https://frederick-douglas-pearce.github.io/assets/img/{_SLUG}-og.png\n",
                "",
            )
        )
        self.assert_complains(self.run_guard(post), "missing `og_image`")

    def test_two_posts_colliding_on_one_image_target_is_caught(self) -> None:
        """The one condition a per-post pass structurally cannot see."""
        self.write_card()
        first = self.write_post()

        other_rel = "posts/images/a-different-post/og-card.png"
        self.write_card(other_rel)
        # Different slug and different card, but the SAME og_image basename --
        # so both resolve individually and collide on one Pages target.
        second = self.write_post(
            self.mutated(_CARD_REL, other_rel), stem="2026-10-02-a-different-post"
        )

        # Two needles: the guard's own label for the batch branch, AND
        # `build_plan`'s own wording, so deleting either side is caught.
        self.assert_complains(
            self.run_guard(first, second),
            "cross-post image collision",
            "target collision (image)",
        )

    def test_two_valid_posts_pass_together(self) -> None:
        """The batch pass's PASSING direction, which nothing else exercises.

        Every other multi-post case here expects the batch call to raise, and the
        single-post cases never reach it (it is gated on `len(ok_sources) > 1`).
        Without this, a mutation making that second `build_plan` call always raise
        leaves the whole suite green while every multi-post PR is falsely blocked.
        """
        self.write_card()
        first = self.write_post()

        other_rel = "posts/images/a-different-post/og-card.png"
        self.write_card(other_rel)
        second_text = self.mutated(_CARD_REL, other_rel).replace(
            f"{_SLUG}-og.png", "a-different-post-og.png", 1
        )
        second = self.write_post(second_text, stem="2026-10-02-a-different-post")

        code, out, err = self.run_guard(first, second)
        self.assertEqual(code, 0, "two valid posts failed: %r %r" % (out, err))
        self.assertEqual(out.count("[ok]"), 2, out)

    def test_every_failing_post_is_reported_not_just_the_first(self) -> None:
        """`build_plan` raises on the first failure; the guard runs it per post.

        Without the per-post loop a two-bad-post PR would report one and the
        author would fix it, push, and meet the second -- which is the drip-feed
        this guard exists to avoid.
        """
        first = self.write_post()  # no card
        second = self.write_post(
            self.mutated(_CARD_REL, "/etc/passwd"), stem="2026-10-02-a-different-post"
        )
        code, out, err = self.run_guard(first, second)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[FAIL]"), 2, out)
        self.assertIn("2 OG-card problem(s)", err)


class SelectionTests(_PostTree):
    def test_the_default_glob_finds_dated_posts(self) -> None:
        self.write_card()
        self.write_post()
        code, out, _ = self.run_guard()  # no explicit paths
        self.assertEqual(code, 0, out)
        self.assertIn(_POST_STEM, out)

    def test_the_default_glob_skips_the_readme(self) -> None:
        """`posts/README.md` is not a dated post and has no frontmatter."""
        self.write_card()
        self.write_post()
        (self.repo / "posts" / "README.md").write_text("# not a post\n", encoding="utf-8")
        code, out, _ = self.run_guard()
        self.assertEqual(code, 0, out)
        self.assertNotIn("README.md", out)

    def test_an_empty_posts_dir_exits_zero_and_says_so(self) -> None:
        """Pinned deliberately: this is the repo's state today.

        Recording it as a test rather than leaving it implicit is what stops a
        green CI run on an empty `posts/` being read as evidence the card
        pipeline works. It does not; it means there was nothing to check.
        """
        code, out, err = self.run_guard()
        self.assertEqual(code, 0)
        self.assertIn("no posts found to check", err)


class RemedyTests(unittest.TestCase):
    """The remedy string may only describe things that exist in THIS repo.

    The guard is ported from `us-presidential-vote-analysis`, whose remedy tells
    the author to run `uv run python tooling/render-og-card.py <brief>.toml`
    (which needs Inkscape). **None of that exists here** -- the renderer is #181
    -- so the port deletes that procedure rather than substituting one. This
    pins the deletion, because a later editor restoring the source's wording is
    exactly how a citation to a nonexistent tool gets back in.
    """

    def test_the_remedy_keeps_the_source_repos_renderer_wording_deleted(self) -> None:
        for absent in ("render-og-card", "uv run", "Inkscape", ".toml"):
            self.assertNotIn(
                absent,
                cog._REMEDY,
                "remedy carries %r, which the port deleted deliberately" % absent,
            )

    def test_the_remedy_points_at_the_issue_that_automates_rendering(self) -> None:
        self.assertIn("#181", cog._REMEDY)

    def test_the_remedy_names_the_settled_card_directory(self) -> None:
        self.assertIn("posts/images/", cog._REMEDY)


class ReuseTests(unittest.TestCase):
    """The guard's VERDICT comes from `build_plan`; it does not re-derive the rules.

    AC1 says "Do not reimplement the checks. Call `build_plan`." Asserting only
    that `build_plan` was *called* does not pin that: a guard that called it once
    decoratively, discarded the result and re-derived everything would pass such a
    test. So these observe which code *decided* -- a sentinel error injected into
    `build_plan` must reach the report, and a stubbed-clean `build_plan` must make
    a guaranteed-bad post pass. Both directions, because either alone is
    satisfiable by an implementation that only half-delegates.

    A coupling's identity, not a proposition's truth (`tests/CLAUDE.md`).
    """

    def _tree(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name) / "repo"
        (repo / "posts").mkdir(parents=True)
        card = repo / _CARD_REL
        card.parent.mkdir(parents=True)
        card.write_bytes(_CARD_BYTES)
        post = repo / "posts" / f"{_POST_STEM}.md"
        post.write_text(_GOOD, encoding="utf-8")
        return repo, post

    def _run(self, repo: Path, post: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cog.ptp, "REPO_ROOT", repo):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cog.main([str(post)])
        return code, out.getvalue(), err.getvalue()

    def test_the_guard_loads_the_real_publisher(self) -> None:
        self.assertEqual(
            Path(cog.ptp.__file__).resolve(),
            (_REPO_ROOT / "tooling" / "publish-to-pages.py").resolve(),
        )

    def test_build_plans_refusal_is_what_the_guard_reports(self) -> None:
        """Inject a sentinel refusal; it must surface as the guard's verdict."""
        repo, post = self._tree()
        sentinel = "sentinel-only-build-plan-can-say-this"
        with mock.patch.object(
            cog.ptp, "build_plan", side_effect=cog.ptp.PublishError(sentinel)
        ):
            code, out, err = self._run(repo, post)
        self.assertEqual(code, 1, "a refusing build_plan did not fail the guard")
        self.assertIn(sentinel, out + err)

    def test_build_plans_acceptance_is_what_the_guard_reports(self) -> None:
        """The other direction: a post that MUST fail passes if build_plan says so.

        The card is deleted, so any re-derived existence check inside the guard
        would still refuse. Only a guard that takes `build_plan`'s word passes.
        """
        repo, post = self._tree()
        (repo / _CARD_REL).unlink()
        with mock.patch.object(cog.ptp, "build_plan", return_value={}):
            code, out, err = self._run(repo, post)
        self.assertEqual(
            code, 0, "the guard refused a post build_plan accepted: %r %r" % (out, err)
        )


if __name__ == "__main__":
    unittest.main()
