#!/usr/bin/env python3
"""`tooling/publish-to-pages.py` decides which bytes reach a public website.

Ported with the publisher itself (#179) from `us-presidential-vote-analysis`,
whose own suite is pytest; this repo is stdlib `unittest` only, so these are
rewritten rather than copied.

**Two tiers, and the split is the whole point of this module.**

*Tier 1* drives `assert_no_foreign_overwrite` through its `pages_owner` injection
seam. That pins the **refusal logic**: given an owner, does the guard refuse, and
does the message name the right thing? Each of the three refusals carries a
DIFFERENT remedy, and handing a reader the wrong one is its own defect -- telling
someone to rename a slug when the real fault is two publishers disagreeing about
a subject format would move a live permalink and fix nothing.

*Tier 2* drives `git_pages_owner` against **real git histories**, because the
seam bypasses it entirely -- and that function is where the security-critical
work lives (`%an%x00%s` field order, `%an` not `%cn`, the `-- <path>` pathspec,
and the walk that stops on an unattributable sync rather than skipping it).
A seam-only suite would assert the *outcome* (owner=X => refuse naming X) while
leaving the *mechanism* (a real history parsed INTO owner=X) untested. That is
the outcome-shaped hole `tests/CLAUDE.md` is about, and it is not hypothetical:
the source repo MEASURED it. Swapping `%cn` for `%an` left its whole suite green,
and so did dropping the pathspec. Both mutations restore a silent cross-publisher
overwrite. Tier 2 is what notices. (No test count is quoted: the figure carried
over from the source was already stale against the file it named.)

**Tier 2 requires a real `git` binary** and builds throwaway repositories under
`tempfile`. That is a deliberate, conscious precondition rather than an
accident: the alternative -- skipping when git is absent -- would let the
security coverage evaporate silently on exactly the machine where nobody looks.
Still stdlib-only: `subprocess` + `tempfile`, no dependency.

Nothing here touches the real repository or the real Pages site. Tests that
subclass `_FixtureTree` get a throwaway source tree with `REPO_ROOT` repointed at
it, and a Pages tree deliberately made a SIBLING of that root, because `run()`
refuses Pages directories inside the source repo. `ProvenanceGitFixtureTests`
builds its own throwaway git repo and does not patch `REPO_ROOT`; it reads none.
"""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

# Load the publisher by path, as `test_mutate_verify.py` loads the mutation harness.
# Deliberately NOT `sys.path.insert`: `discover` runs every module in one process, so a
# permanent entry would leave `tooling/` on the path for the whole session.
# The filename is HYPHENATED, so it is not importable as a module name at all -- which is
# the reason this loader is mandatory here rather than merely conventional. Do not "fix"
# that by renaming the script: the name is load-bearing twice over, matching the two
# sibling publishers and keeping the ported `REPO_ROOT` comment true.
_PUBLISH_PATH = Path(__file__).resolve().parents[1] / "tooling" / "publish-to-pages.py"
_spec = importlib.util.spec_from_file_location("publish_to_pages", _PUBLISH_PATH)
assert _spec and _spec.loader
publish_to_pages = importlib.util.module_from_spec(_spec)
sys.modules["publish_to_pages"] = publish_to_pages
_spec.loader.exec_module(publish_to_pages)

PublishError = publish_to_pages.PublishError
UNATTRIBUTED_SYNC = publish_to_pages.UNATTRIBUTED_SYNC

OURS = "claude-code-loop"
SIBLING = "claude-code-sessions"

# Deliberately hostile to a formatter: trailing spaces, a tab, and a run of blank
# lines. A "byte-for-byte" assertion against a body with none of these is
# satisfied by any reformat that finds nothing to strip -- which is how the first
# version of this fixture let a whitespace-stripping mutation survive.
_FRAGILE_BODY = (
    "\nBody text with *emphasis* and a trailing line.   \n"
    "\tTab-indented line with trailing tab.\t\n"
    "\n\n\n"
    "Three blank lines above this one.\n"
)

_FRONTMATTER = """---
layout: post
title: "The team you didn't hire"
date: 2026-10-01 09:00:00-0700
description: "Why the roles on a dev team outlived the people who filled them."
categories: ["claude-code-loop"]
tags: ["claude-code", "dev-loop", "foundation"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/team-you-didnt-hire-og.png
og_card_source: social/images/2026-10-01-linkedin-team-you-didnt-hire/og-card.png
featured: false
claude_code_version_verified: v2.1.243
humanizer_pass: v3.0.0
claims_verified: 2026-10-01
---
"""

_GOOD_POST = _FRONTMATTER + _FRAGILE_BODY

_POST_STEM = "2026-10-01-team-you-didnt-hire"
_CARD_BYTES = b"\x89PNG\r\n\x1a\n-not-really-a-png-but-bytes-are-bytes"


def _git(cwd: Path, *args: str, env_extra: dict | None = None) -> str:
    env = dict(os.environ)
    # Pin identity and disable any user/system config so a developer's global
    # git settings cannot change what these tests observe.
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }
    )
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    ).stdout


class _FixtureTree(unittest.TestCase):
    """A throwaway source repo + a SIBLING Pages tree, with REPO_ROOT repointed.

    `resolve_og_source` resolves `og_card_source` against the module-global
    REPO_ROOT, derived from the script's real path -- so a card dropped in a
    tempdir does not resolve unless REPO_ROOT is patched. Keep REPO_ROOT a
    hardcoded global (it is a deliberate security property: known exactly, never
    git-discovered) and patch it here instead.

    The Pages tree is a sibling, not a child, because `run()` fail-closes on a
    Pages directory inside the source repo.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)

        self.repo = base / "repo"
        self.pages = base / "pages"
        (self.repo / "posts").mkdir(parents=True)
        self.posts_dir = self.pages / "_posts"
        self.assets_dir = self.pages / "assets" / "img"
        self.posts_dir.mkdir(parents=True)
        self.assets_dir.mkdir(parents=True)

        self.post = self.repo / "posts" / (_POST_STEM + ".md")
        self.post.write_text(_GOOD_POST, encoding="utf-8")
        card = self.repo / "social" / "images" / "2026-10-01-linkedin-team-you-didnt-hire"
        card.mkdir(parents=True)
        (card / "og-card.png").write_bytes(_CARD_BYTES)

        patcher = mock.patch.object(publish_to_pages, "REPO_ROOT", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def plan(self):
        return publish_to_pages.build_plan([self.post], self.posts_dir, self.assets_dir)

    def published_post(self) -> Path:
        return self.posts_dir / self.post.name

    def published_card(self) -> Path:
        return self.assets_dir / "team-you-didnt-hire-og.png"


class TransformTests(_FixtureTree):
    """The frontmatter strip and the byte-for-byte body contract (AC2)."""

    def test_the_fixture_plans_cleanly(self) -> None:
        # The control. If this fails every negative case below is meaningless --
        # they would be "detecting" a fixture that was already broken.
        plan = self.plan()
        self.assertEqual(
            sorted(p.name for p in plan),
            ["2026-10-01-team-you-didnt-hire.md", "team-you-didnt-hire-og.png"],
        )

    def test_a_published_post_carries_none_of_the_stripped_fields(self) -> None:
        # AC2. Asserted on the transformed BYTES, not on DROP_FIELDS -- reading the
        # constant back would pass for any implementation that never applies it.
        fm, body = publish_to_pages.split_frontmatter(_GOOD_POST)
        out = publish_to_pages.transform_bytes(fm, body).decode("utf-8")
        for field in (
            "og_card_source",
            "claude_code_version_verified",
            "humanizer_pass",
            "claims_verified",
        ):
            with self.subTest(field=field):
                self.assertNotIn(field, out)

    def test_the_fields_it_must_keep_survive(self) -> None:
        # The other half: a strip that removed everything would pass the test above.
        fm, body = publish_to_pages.split_frontmatter(_GOOD_POST)
        out = publish_to_pages.transform_bytes(fm, body).decode("utf-8")
        for field in ("layout:", "title:", "date:", "categories:", "tags:", "og_image:"):
            with self.subTest(field=field):
                self.assertIn(field, out)

    def test_the_body_is_copied_byte_for_byte(self) -> None:
        # The site runs its own `prettier --check`; a reformat here would publish
        # bytes that differ from the source of record and redden the SITE.
        fm, body = publish_to_pages.split_frontmatter(_GOOD_POST)
        out = publish_to_pages.transform_bytes(fm, body).decode("utf-8")
        # The contract is the bytes, not a substring: asserting one sentence
        # survives would pass for whitespace normalization, CRLF conversion, or
        # a stripped blank line -- every reformat this must not do.
        self.assertTrue(out.endswith(body))
        self.assertIn("Body text with *emphasis* and a trailing line.", out)

    def test_a_missing_card_aborts_the_whole_batch_before_any_write(self) -> None:
        # validate-all-then-write: one bad post must not half-publish the batch.
        # Driven through run() with TWO posts, because build_plan has no write
        # path at all -- asserting an empty output dir against it would hold for
        # every possible implementation, including one that writes eagerly.
        second = self.repo / "posts" / "2026-10-02-second-post.md"
        second.write_text(
            _GOOD_POST.replace("2026-10-01", "2026-10-02")
            .replace("team-you-didnt-hire", "second-post"),
            encoding="utf-8",
        )
        # The FIRST post is fully valid; only the second's card is missing.
        (self.repo / "social" / "images" / "2026-10-02-linkedin-second-post").mkdir(
            parents=True
        )
        with self.assertRaises(PublishError) as cm:
            publish_to_pages.run(
                [self.post, second], self.posts_dir, self.assets_dir,
                dry_run=False, source_repo=OURS, pages_owner=lambda dest: OURS,
            )
        self.assertIn("og card source not found", str(cm.exception))
        self.assertIn("2026-10-02-second-post.md", str(cm.exception))
        # The valid post must NOT have been written despite being planned first.
        self.assertEqual(sorted(p.name for p in self.posts_dir.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.assets_dir.iterdir()), [])


class DryRunTests(_FixtureTree):
    """AC4 -- a plan against a representative post fixture, no Pages checkout.

    AC4 as filed said "a real post"; `posts/` holds none and no card resolves in
    CI, so it was amended at the plan gate to name the fixture and the isolation
    property. The criterion being pinned is that NO Pages checkout and NO token
    are needed, which is what the script/Action split exists to buy.
    """

    def test_dry_run_reports_a_plan_and_writes_nothing(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = publish_to_pages.run(
                [self.post], self.posts_dir, self.assets_dir,
                dry_run=True, source_repo=OURS,
            )
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("[dry-run]", out)
        self.assertIn("CHANGED", out)
        self.assertIn("2 change(s) across 2 target(s).", out)
        # The point of the criterion: nothing was written.
        self.assertFalse(self.published_post().exists())
        self.assertFalse(self.published_card().exists())

    def test_dry_run_still_runs_the_namespace_guard(self) -> None:
        # Deliberately NOT a full no-op: an operator dry-run against a real Pages
        # checkout is exactly the preview that should surface a foreign collision
        # BEFORE the real push does. A dry run that skipped the guard would
        # report "all clear" on the run whose job is to warn.
        self.published_post().write_bytes(b"someone else's bytes\n")
        with self.assertRaises(PublishError) as cm:
            publish_to_pages.run(
                [self.post], self.posts_dir, self.assets_dir,
                dry_run=True, source_repo=OURS,
                pages_owner=lambda dest: SIBLING,
            )
        self.assertIn("refusing to overwrite", str(cm.exception))

    def test_pages_dirs_inside_the_source_repo_are_refused(self) -> None:
        inside = self.repo / "_posts"
        inside.mkdir()
        with self.assertRaises(PublishError):
            publish_to_pages.run(
                [self.post], inside, self.assets_dir, dry_run=True, source_repo=OURS,
            )


class IdempotenceTests(_FixtureTree):
    """Content-compare, not push-diff: a re-run makes no spurious changes."""

    def test_a_second_run_writes_nothing(self) -> None:
        for _ in range(2):
            buf = io.StringIO()
            with redirect_stdout(buf):
                publish_to_pages.run(
                    [self.post], self.posts_dir, self.assets_dir,
                    dry_run=False, source_repo=OURS,
                    pages_owner=lambda dest: OURS,
                )
            last = buf.getvalue()
        self.assertIn("0 change(s) across 2 target(s).", last)
        self.assertEqual(self.published_card().read_bytes(), _CARD_BYTES)


class NamespaceGuardSeamTests(_FixtureTree):
    """Tier 1 -- the refusal logic, through the `pages_owner` seam (AC5).

    Each refusal must name the thing that is actually wrong. Asserting merely
    that *some* PublishError was raised is outcome-shaped: a guard that refused
    everything with one generic message would pass, and an operator handed the
    wrong remedy does real damage -- "rename your slug" on a site-owned file
    moves a permalink and a share-card URL that are already live, and fixes
    nothing.
    """

    def _refusal(self, owner) -> str:
        self.published_post().write_bytes(b"different bytes on the pages side\n")
        with self.assertRaises(PublishError) as cm:
            publish_to_pages.assert_no_foreign_overwrite(
                self.plan(), OURS, pages_owner=lambda dest: owner
            )
        return str(cm.exception)

    def _assert_names(self, message: str, *needles: str) -> None:
        for needle in needles:
            self.assertIn(needle, message)

    def test_a_target_owned_by_a_sibling_is_refused_naming_that_sibling(self) -> None:
        # AC5's required negative: it must fail, and fail FOR THAT REASON.
        # The needle must be the branch's OWN discriminator. "rename this post's
        # slug" is not: it is a substring of all three refusals, two of which say
        # "do NOT rename" -- so asserting it passes whichever branch fired, which
        # is the polarity-blind shape tests/CLAUDE.md warns about.
        msg = self._refusal(SIBLING)
        self._assert_names(
            msg,
            "refusing to overwrite",
            SIBLING,
            OURS,
            "shared with another publisher",
            "targets are unique across both series",
        )
        # Case-INSENSITIVE: a lowercase "do NOT rename" inversion survived the
        # first version of this assertion, which is the same polarity hole one
        # capital letter further down.
        self.assertNotIn("not rename", msg.lower())
        self.assertNotIn("reflexively", msg.lower())

    def test_an_unattributable_sync_is_refused_with_the_subject_format_remedy(self) -> None:
        msg = self._refusal(UNATTRIBUTED_SYNC)
        self._assert_names(
            msg, "cannot parse", "chore(sync): publish posts from <repo>@<sha>"
        )
        # The remedy that would be actively WRONG here.
        self.assertIn("Do NOT rename this post's slug", msg)

    def test_a_site_owned_target_is_refused_with_the_ownership_remedy(self) -> None:
        msg = self._refusal(None)
        self._assert_names(msg, "no Pages sync commit in its history", "site-owned")
        self.assertIn("do NOT reflexively", msg)

    def test_the_three_refusals_do_not_share_a_remedy(self) -> None:
        # The distinction is the point; collapsing any two loses it.
        msgs = [self._refusal(SIBLING), self._refusal(UNATTRIBUTED_SYNC), self._refusal(None)]
        self.assertEqual(len(set(msgs)), 3)

    def test_a_target_we_own_is_allowed(self) -> None:
        self.published_post().write_bytes(b"our own older bytes\n")
        publish_to_pages.assert_no_foreign_overwrite(
            self.plan(), OURS, pages_owner=lambda dest: OURS
        )

    def test_an_unchanged_target_is_never_arbitrated(self) -> None:
        # Phase 2 will not write it, so there is nothing to arbitrate -- and the
        # Action's reconcile-retry re-transforms on every attempt, where the
        # common case is exactly this.
        plan = self.plan()
        for dest, entry in plan.items():
            dest.write_bytes(entry.data)

        def explode(dest):  # pragma: no cover - must never be called
            raise AssertionError("consulted git for an unchanged target")

        publish_to_pages.assert_no_foreign_overwrite(plan, OURS, pages_owner=explode)


class ProvenanceGitFixtureTests(unittest.TestCase):
    """Tier 2 -- `git_pages_owner` against real histories. Requires `git`.

    Every test here pins a property the seam cannot reach. Three of those
    properties were measured in the source repo: swapping `%an` for `%cn` and
    dropping the pathspec each left its whole suite green. No claim is made here
    about the others having been measured.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pages = Path(self._tmp.name) / "pages"
        (self.pages / "_posts").mkdir(parents=True)
        _git(self.pages.parent, "init", "-q", "-b", "main", str(self.pages))
        self.a = self.pages / "_posts" / "a.md"
        self.b = self.pages / "_posts" / "b.md"

    def _commit(self, path: Path, text: str, subject: str, author: str = "a human") -> None:
        path.write_text(text, encoding="utf-8")
        _git(self.pages, "add", str(path))
        _git(
            self.pages, "commit", "-q", "-m", subject,
            env_extra={"GIT_AUTHOR_NAME": author},
        )

    def _sync(self, path: Path, text: str, repo: str) -> None:
        self._commit(
            path, text,
            "chore(sync): publish posts from %s@abc1234" % repo,
            author=publish_to_pages._SYNC_AUTHOR,
        )

    def test_ownership_is_the_repo_named_by_the_most_recent_parseable_sync(self) -> None:
        self._sync(self.a, "v1\n", SIBLING)
        self.assertEqual(publish_to_pages.git_pages_owner(self.a), SIBLING)

    def test_ownership_is_scoped_to_the_path_not_the_repository(self) -> None:
        # Drop the `-- <path>` pathspec and this answers "who wrote the repo
        # last", so whichever publisher synced most recently owns EVERY target.
        self._sync(self.a, "v1\n", SIBLING)
        self._sync(self.b, "v1\n", OURS)
        self.assertEqual(publish_to_pages.git_pages_owner(self.a), SIBLING)
        self.assertEqual(publish_to_pages.git_pages_owner(self.b), OURS)

    def test_the_read_uses_the_author_not_the_committer(self) -> None:
        # A sync commit that was rebased or cherry-picked keeps its AUTHOR and
        # gains a new COMMITTER. Reading %cn re-classifies it, which restores the
        # silent overwrite -- and did so with the source's whole suite green.
        self.a.write_text("v1\n", encoding="utf-8")
        _git(self.pages, "add", str(self.a))
        _git(
            self.pages, "commit", "-q", "-m", "a subject that names no source repo",
            env_extra={
                "GIT_AUTHOR_NAME": publish_to_pages._SYNC_AUTHOR,
                "GIT_COMMITTER_NAME": "someone who rebased it",
            },
        )
        # Author is the sync bot, so this is an unattributable SYNC, not a skip.
        self.assertIs(publish_to_pages.git_pages_owner(self.a), UNATTRIBUTED_SYNC)

    def test_a_drifted_sibling_subject_is_unattributable_not_walked_past(self) -> None:
        # The source repo's #200: the walk used to skip a sync whose subject did
        # not parse and keep going to an older sync of OURS, which then read as
        # ours and the overwrite proceeded silently.
        self._sync(self.a, "v1\n", OURS)
        self._commit(
            self.a, "v2\n", "sync: published some posts",
            author=publish_to_pages._SYNC_AUTHOR,
        )
        self.assertIs(publish_to_pages.git_pages_owner(self.a), UNATTRIBUTED_SYNC)

    def test_a_non_sync_writer_is_skipped_rather_than_read_as_foreign(self) -> None:
        # One `prettier --write` or typo fix on the Pages side must not
        # permanently reclassify our own post as foreign and block all future
        # publishing until someone hand-edits the Pages repo.
        self._sync(self.a, "v1\n", OURS)
        self._commit(self.a, "v2\n", "Fix a typo in the third paragraph")
        self.assertEqual(publish_to_pages.git_pages_owner(self.a), OURS)

    def test_a_target_with_no_sync_in_its_history_is_site_owned(self) -> None:
        self._commit(self.a, "v1\n", "Add a hand-written post")
        self.assertIsNone(publish_to_pages.git_pages_owner(self.a))

    def test_a_split_forging_subject_cannot_forge_our_ownership(self) -> None:
        # `_PROVENANCE_FORMAT` is "%an%x00%s" -- the FREE-TEXT field last. Python's
        # str.splitlines() splits on \x1c, \x1d, \x1e, \x0b, \x0c and \x85, none of
        # which git folds out of a subject. With the author first, every fragment
        # after a split lands in the AUTHOR slot with an EMPTY subject, so it
        # cannot parse as a sync. Reverse the format to "%s%x00%an" and the
        # fragment lands in the SUBJECT slot instead -- where it parses, and an
        # attacker-chosen subject forges ownership.
        self._sync(self.a, "v1\n", SIBLING)
        forged = "x\x1cchore(sync): publish posts from %s@dead1234" % OURS
        self._commit(self.a, "v2\n", forged)
        owner = publish_to_pages.git_pages_owner(self.a)
        self.assertNotEqual(owner, OURS, "a crafted subject forged our ownership")
        self.assertEqual(owner, SIBLING)

    def test_a_path_outside_any_checkout_is_refused_not_guessed(self) -> None:
        outside = Path(self._tmp.name) / "not-a-repo" / "x.md"
        outside.parent.mkdir()
        outside.write_text("x\n", encoding="utf-8")
        with self.assertRaises(PublishError) as cm:
            publish_to_pages.git_pages_owner(outside)
        # Delete the toplevel check and `git log` still raises PublishError here
        # -- under a message blaming an empty repository. Assert the diagnosis,
        # not merely that something was raised.
        self.assertIn("is not inside a git checkout", str(cm.exception))


class ProvenanceFormatTests(unittest.TestCase):
    """The field order in `_PROVENANCE_FORMAT` is a security property.

    Pinned on the constant as well as behaviourally (see
    `test_a_split_forging_subject_cannot_forge_our_ownership`): the free-text
    field must come LAST, so that every fragment a `splitlines()` split produces
    lands in the author slot with an empty subject. Reversed, a crafted subject
    lands in the slot that gets parsed, and forges ownership.
    """

    def test_the_provenance_format_puts_the_free_text_field_last(self) -> None:
        fmt = publish_to_pages._PROVENANCE_FORMAT
        self.assertTrue(fmt.endswith("%s"), "the free-text subject must come last")
        self.assertEqual(fmt.index("%an"), 0, "the author must come first")
        self.assertIn("%x00", fmt, "the separator must be NUL")
        self.assertNotIn("%cn", fmt, "the committer does not survive a rebase")


class SubjectParsingTests(unittest.TestCase):
    """`sync_source_repo` -- the cross-repo subject contract, in isolation."""

    def test_it_reads_the_repo_out_of_a_well_formed_subject(self) -> None:
        self.assertEqual(
            publish_to_pages.sync_source_repo(
                "chore(sync): publish posts from claude-code-loop@abc1234"
            ),
            OURS,
        )

    def test_a_non_sync_subject_names_no_repo(self) -> None:
        for subject in ("Fix a typo", "sync: publish posts from x@1", "", "chore(sync): nope"):
            with self.subTest(subject=subject):
                self.assertIsNone(publish_to_pages.sync_source_repo(subject))

    def test_an_empty_slug_does_not_parse(self) -> None:
        # The trap an empty --source-repo creates: the subject it commits can
        # never be parsed, so every LATER update of that post is refused.
        self.assertIsNone(
            publish_to_pages.sync_source_repo("chore(sync): publish posts from @abc1234")
        )


class CliContractTests(_FixtureTree):
    """`--source-repo` is required and must not be empty."""

    def test_an_empty_source_repo_is_rejected(self) -> None:
        with self.assertRaises(PublishError) as cm:
            publish_to_pages.main(
                [
                    str(self.post),
                    "--posts-dir", str(self.posts_dir),
                    "--assets-dir", str(self.assets_dir),
                    "--source-repo", "   ",
                    "--dry-run",
                ]
            )
        self.assertIn("--source-repo must not be empty", str(cm.exception))

    def test_source_repo_is_required(self) -> None:
        # argparse writes its usage block to stderr on a missing required arg.
        # Swallow it: otherwise a fully green run prints what reads at a glance
        # like a failure, and a suite whose clean output looks broken trains the
        # reader to skim past real output.
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit):
            publish_to_pages.main(
                [
                    str(self.post),
                    "--posts-dir", str(self.posts_dir),
                    "--assets-dir", str(self.assets_dir),
                ]
            )
        # Assert the diagnosis, not merely the exit: argparse exits non-zero for
        # any bad invocation, so a bare SystemExit would pass if the flag were
        # renamed rather than made required.
        self.assertIn("--source-repo", err.getvalue())


if __name__ == "__main__":
    unittest.main()
