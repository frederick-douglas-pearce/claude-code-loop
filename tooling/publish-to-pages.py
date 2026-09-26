#!/usr/bin/env python3
"""Publish posts from this repo's posts/ to the Jekyll Pages site.

Transforms each post's frontmatter to Pages conventions and copies its OG card.

Ported from `us-presidential-vote-analysis` (its `tooling/publish-to-pages.py`),
which in turn ported it from `claude-code-sessions`. Separation of concerns,
preserved from the source: the Action (`.github/workflows/pages-sync.yml`) owns
auth and the reconcile-retry push; this script owns the transform, OG-image
resolution, and the content-compare that makes re-runs idempotent. That split is
what lets this file be tested with no Pages checkout and no token.

Usage:
    publish-to-pages.py <source.md>... --posts-dir DIR --assets-dir DIR
                        --source-repo SLUG [--dry-run]

Example:
    python3 tooling/publish-to-pages.py \\
        posts/2026-10-01-team-you-didnt-hire.md \\
        --posts-dir  /path/to/frederick-douglas-pearce.github.io/_posts/ \\
        --assets-dir /path/to/frederick-douglas-pearce.github.io/assets/img/ \\
        --source-repo claude-code-loop

`--source-repo` is this repo's GitHub slug, and it is REQUIRED: it is the
identity the shared-namespace guard below compares against. It is the HYPHENATED
slug. In the source repo that was a live trap (its working directory is
`us_presidential_vote_analysis`, which is NOT its slug); here the directory and
the slug are both `claude-code-loop`, so the trap does not bite — which makes it
*easier to forget the rule*, not safer. The Action passes
`${{ github.event.repository.name }}`, which is the same value it builds the
sync commit subject from.

What it does, per post:

1. **Transform frontmatter.** Strip this repo's upstream-only fields
   (`og_card_source`, `claude_code_version_verified`, `humanizer_pass`,
   `claims_verified` — see DROP_FIELDS); copy the body and every other field
   byte-for-byte. The strip is line-level, not a YAML round-trip, so the source
   formatting survives unchanged (a round-trip would reflow the frontmatter for
   no benefit).

   Because the body is copied verbatim, THIS SCRIPT NEVER FORMATS ANYTHING —
   what a post says here is what lands on the site, and the site runs
   `prettier . --check` on every push to its main. Keeping the posts in the
   site's dialect is therefore a pre-merge gate's job, not this script's:
   `.github/workflows/prettier.yml`, pinned to the site's exact formatter
   versions. Do not "helpfully" add a format pass here — it would break the
   byte-for-byte contract and make the published post differ from the source of
   record. (That gate was MISSING when the source repo was ported in
   the source repo, and its post 1 duly turned the site red
   on 2026-08-12. This repo landed the gate FIRST, deliberately, in #178.)
2. **Resolve + copy the OG card**: the post's `og_card_source` field
   (repo-root-relative) is the source; the target is `<assets-dir>/<basename of
   the post's og_image URL>`.

Resolution is **fail-closed, never a glob**: a missing field, an absolute or
repo-escaping path, a missing source file, or two posts colliding on one target
all abort the run with zero writes. A wrong image shipped under a green Action
is the exact failure mode this design exists to prevent.

**Cards live at `posts/images/<slug>/og-card.png`, committed** — settled by issue
#180, which also ported `tooling/check-og-cards.py` so the same fail-closed
resolution runs on a PR rather than first on `main`. Nothing here hardcodes a
card directory: `og_card_source` is a per-post frontmatter value resolved against
REPO_ROOT, so that decision changed a frontmatter convention and a file location
and never this file. The publisher is still inert until a dated post exists (the
Action's `detect` step finds none and skips).

Idempotency is **content-compare, not push-diff**: every output is written only
when its bytes differ from what's already in the Pages tree, so a re-run makes
no spurious changes and the Action makes no empty commit.

Atomicity is **validate-all-then-write**: the full plan for ALL posts is built
and validated (Phase 1) before a single byte is written (Phase 2), so one bad
post can't half-publish the batch. Phase 2 is not filesystem-transactional — a
mid-batch failure (e.g. disk full) can leave a partial tree — but the next run's
content-compare plus the Action's reconcile-retry self-heal it, and the
realistic failure (a missing card) is caught in Phase 1 before any write.

**Shared Pages namespace — and this repo makes THREE publishers, not two.** The
site also receives posts from `claude-code-sessions` and from
`us-presidential-vote-analysis`. `build_plan`'s collision check sees only *this*
repo's posts, so a cross-repo collision never enters any publisher's plan. That
gap is closed by `assert_no_foreign_overwrite`, a SECOND Phase-1 validator:
before any write, a target that already exists with different bytes must have
been written last by a sync from THIS repo, or the run aborts. The provenance is
the Pages repo's own history — each sync commits as
`chore(sync): publish posts from <repo>@<sha>`, under the author
`pages-sync[bot]`. **The subject decides ownership; the author is a fallback
read only when the subject does not parse** — `git_pages_owner` is the statement
of record. That history has to be there: the Action's `fetch-depth: 0` predates
this guard (it exists for the
reconcile-retry loop) but the guard now depends on it too, and the workflow
says so at the checkout step. A shallow clone does not merely degrade this — it
**silently fails open**: the grafted tip is parentless, so every path reads as
added there and every target resolves to whoever the tip's sync names. Right
after any of our own publishes that is *us*, so the siblings' cards would be
overwritten with no refusal at all — the exact bug this guard exists to fix.

**The subject and author strings are a CROSS-REPO API, not local constants.**
Both are byte-exact commitments to the other two publishers' guards, permanently.
The source repo records its own half of this as "an assumption, not an
invariant… which no test here can pin", and that limit is inherited: no test in
this repo can cover the siblings' halves, and none pretends to.

One consequence is load-bearing rather than incidental: the check is invisible
to any PR-time guard, which has no Pages checkout. A slug colliding with either
sibling passes CI green and fails at publish time — loudly, but late. (The
PR-time half is `tooling/check-og-cards.py`, ported in issue #180, which runs
`build_plan` but cannot run this check — it has no Pages checkout.) See
posts/README.md.

**Reciprocity is partial, and the asymmetry is worth stating exactly.** Of the
three publishers, `us-presidential-vote-analysis` carries this guard and so does
this repo; `claude-code-sessions` does NOT — its publisher has no
`--source-repo` and no ownership check at all. So this repo will refuse to
overwrite a target either sibling owns, and `us-presidential-vote-analysis` will
refuse ours, but a `claude-code-sessions` sync can still overwrite anyone's. The
operator rule — keep slugs distinct across all three series — is therefore still
load-bearing, not superseded (see posts/README.md).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final, NamedTuple, Union
from urllib.parse import urlparse

# This script lives at <repo-root>/tooling/publish-to-pages.py, so the repo root
# is two parents up. `og_card_source` is resolved against THIS, independent of
# CWD — the Action invokes it from a checkout of the Pages repo.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Upstream-only frontmatter fields, stripped on publish (Pages Jekyll ignores
# them):
#   og_card_source               — the OG-card pointer; consumed by THIS script
#                                  to find the image, never deployed
#   claude_code_version_verified — attestation: which Claude Code version the
#                                  post's behavioural claims were checked against
#   humanizer_pass               — attestation: which humanizer pass was run
#   claims_verified              — attestation: the date the post's receipts list
#                                  was walked
#
# The three attestations are THIS repo's contract (posts/README.md).
# `claude-code-sessions` strips the first two; `claims_verified` exists in
# neither sibling. They record that a manual step was performed, a fact about
# how the post was produced and not content for the published page.
#
# Note the interaction, recorded rather than silently accepted: AI-DISCLOSURE.md
# says the Claude Code version "is recorded per post, in that post's
# frontmatter". Stripping it means that holds inside this repo but NOT on the
# published site. That is the issue's stated intent (#179), not an oversight
# here.
DROP_FIELDS = {
    "og_card_source",
    "claude_code_version_verified",
    "humanizer_pass",
    "claims_verified",
}


class PlanEntry(NamedTuple):
    """One intended write.

    The Phase-1 plan is keyed by resolved destination Path, so collisions are
    detectable and a future "delete targets with no source" diff is a
    set-difference rather than a restructure.
    """

    data: bytes
    kind: str
    post_name: str


class PublishError(Exception):
    """A fail-closed condition. Aborts the whole run with zero writes."""


def split_frontmatter(text: str) -> tuple[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise PublishError("no frontmatter block found")
    return m.group(1), m.group(2)


def _top_level_key(line: str) -> str | None:
    """The key of a top-level frontmatter line, or None for indented/non-key lines.

    Line-level (no YAML parser), so the byte-for-byte formatting guarantee is
    preserved — a line either matches a known key or passes through untouched.
    """
    if line.startswith(" ") or ":" not in line:
        return None
    return line.partition(":")[0].strip()


def _unquote(value: str) -> str:
    """Drop one matching pair of surrounding quotes, YAML-style.

    Added by `us-presidential-vote-analysis` on its port; `claude-code-sessions`
    reads the raw partition. This repo's own
    frontmatter convention quotes `title` and `description`, so quoting
    `og_image` too is a natural habit — and an unstripped quote survives all the
    way into a filename (see `og_target_name`).
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_field(fm_block: str, key: str) -> str | None:
    """Value of a top-level frontmatter key, or None if absent."""
    for line in fm_block.splitlines():
        if _top_level_key(line) == key:
            return _unquote(line.partition(":")[2].strip())
    return None


def strip_dropped_fields(fm_block: str) -> str:
    """Drop the top-level frontmatter lines whose key is in DROP_FIELDS."""
    return "\n".join(
        line
        for line in fm_block.splitlines()
        if _top_level_key(line) not in DROP_FIELDS
    )


def transform_bytes(fm_block: str, body: str) -> bytes:
    """The published markdown: stripped frontmatter + verbatim body, trailing \\n."""
    out = f"---\n{strip_dropped_fields(fm_block)}\n---\n{body}"
    if not out.endswith("\n"):
        out += "\n"
    return out.encode()


def resolve_og_source(og_card_source: str | None) -> Path:
    """Resolve `og_card_source` to an existing file inside the repo. Fail closed.

    Rejects shape (absent / absolute / repo-escaping) before touching the FS.
    """
    if not og_card_source:
        raise PublishError("missing `og_card_source` frontmatter field")
    p = Path(og_card_source)
    if p.is_absolute():
        raise PublishError(
            "`og_card_source` must be repo-root-relative, "
            f"got absolute {og_card_source!r}"
        )
    resolved = (REPO_ROOT / p).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise PublishError(
            f"`og_card_source` escapes the repo root: {og_card_source!r}"
        ) from None
    if not resolved.is_file():
        raise PublishError(f"og card source not found: {og_card_source!r}")
    return resolved


#: A derived Pages filename must look like one. Anything else means the
#: `og_image` value carried something this line-level reader did not expect.
_SAFE_BASENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def og_target_name(og_image: str | None) -> str:
    """Pages target basename, from the post's og_image URL. Fail closed."""
    if not og_image:
        raise PublishError("missing `og_image` frontmatter field")
    name = Path(urlparse(og_image).path).name
    if not name:
        raise PublishError(
            f"could not derive an OG target basename from og_image {og_image!r}"
        )
    # Added by `us-presidential-vote-analysis` on its port. Without it, a stray
    # character in the frontmatter value rides through into the filename and the
    # card is written one byte away from
    # where `og_image` points — a broken share image on a green Action, which is
    # the precise failure this module's fail-closed design exists to prevent. A
    # trailing inline comment does it (urlparse reads `# …` as a fragment,
    # leaving trailing spaces), as does a quote style `_unquote` cannot pair up.
    if not _SAFE_BASENAME.match(name):
        raise PublishError(
            f"derived OG target basename {name!r} is not a plain filename "
            f"(from og_image {og_image!r}) — check the frontmatter value"
        )
    return name


def _add(
    plan: dict[Path, PlanEntry], dest: Path, data: bytes, kind: str, post_name: str
) -> None:
    """Record an intended write, failing closed on a target collision."""
    dest = dest.resolve()
    if dest in plan:
        prior = plan[dest]
        raise PublishError(
            f"target collision ({kind}) with {prior.post_name} ({prior.kind}) at {dest}"
        )
    plan[dest] = PlanEntry(data, kind, post_name)


def build_plan(
    sources: Sequence[Path], posts_dir: Path, assets_dir: Path
) -> dict[Path, PlanEntry]:
    """Phase 1: resolve+validate every post into a dest-keyed plan. No writes.

    Raises PublishError on the first fail-closed condition, before any output is
    written, so a bad post never half-publishes the batch. Each source's failures
    are tagged with its filename in one place, so leaf validators raise bare.
    """
    plan: dict[Path, PlanEntry] = {}
    for src in sources:
        if not src.is_file():
            raise PublishError(f"source not found: {src}")
        try:
            # Explicit encoding, matching the rest of the codebase: the output
            # side is unconditionally UTF-8 (`transform_bytes` calls `.encode()`),
            # and posts are full of em dashes. Left to the runner's locale this
            # either raises mid-publish or round-trips mojibake to a public site.
            fm_block, body = split_frontmatter(src.read_text(encoding="utf-8"))
            _add(
                plan,
                posts_dir / src.name,
                transform_bytes(fm_block, body),
                "post",
                src.name,
            )
            og_src = resolve_og_source(read_field(fm_block, "og_card_source"))
            target = assets_dir / og_target_name(read_field(fm_block, "og_image"))
            _add(plan, target, og_src.read_bytes(), "image", src.name)
        except PublishError as e:
            raise PublishError(f"{src.name}: {e}") from e
    return plan


#: Every sync into the shared Pages repo commits under this subject, naming its
#: source repo — the provenance the guard needs, recorded by the very mechanism
#: that would be racing. Our Action builds it from the same value it passes to
#: `--source-repo` (see .github/workflows/pages-sync.yml), so OUR half cannot
#: drift -- pinned by `SyncCouplingTests` (tests/test_publish_to_pages.py), which
#: renders the workflow's subject through `sync_source_repo`.
#:
#: Each sibling's half is an assumption, not an invariant: it must match what
#: that repo's own Action writes, and no test here can pin another repo.
#:
#: A drifted sibling subject is not walked past. `_SYNC_AUTHOR` below is a second
#: signal, read when this pattern does not match: the commit is still authored by
#: the sync bot, so it is read as an unattributable sync and refused rather than
#: resolving to an older sync of ours.
_SYNC_SUBJECT = re.compile(
    r"^chore\(sync\): publish posts from (?P<repo>[A-Za-z0-9._-]+)@"
)

#: The identity a publisher's sync commits under — the second signal, read when a
#: subject does not parse. Our own Action sets it with `git config user.name` in
#: .github/workflows/pages-sync.yml, and
#: `test_the_workflow_commits_under_the_identity_the_guard_reads`
#: (tests/test_publish_to_pages.py) fails if the two differ.
#:
#: Deliberately the sync identity and NOT "any bot": the Pages repo's other
#: automated writer is `dependabot[bot]`, and a rule keyed on the `[bot]` suffix
#: would refuse the day it — or any future image optimizer — touched a guarded
#: dir. Narrow makes that safety structural rather than contingent on what
#: dependabot happens to write today.
_SYNC_AUTHOR = "pages-sync[bot]"

#: The `git log` format the provenance walk reads — and the one place its field
#: order is decided.
#:
#: **The free-text field goes LAST, and that is a security property, not a style
#: choice.** Python's `str.splitlines()` splits on boundaries git's `%s` does not
#: fold — `\v`, `\f`, `\r`, `\x1c`-`\x1e`, `\x85`, U+2028, U+2029 — so one commit
#: subject can arrive as several Python "lines". Because `%an` is emitted first,
#: every fragment after such a boundary IN THE SUBJECT — the attacker-controlled
#: field, and the case this guards — lands on a line carrying no NUL:
#: `partition("\x00")` puts it in the AUTHOR slot and leaves `subject == ""`,
#: which can never parse as a sync. (The fragment BEFORE the first boundary
#: keeps the NUL-bearing line and so keeps a real subject slot — harmless, since
#: an attacker who can put a valid sync at the HEAD of a subject has no need of
#: a separator at all.) Reorder this to `%s%x00%an` and a subject
#: crafted as `typo fix<U+2028>chore(sync): publish posts from <us>@<sha>` splits
#: into a fragment that parses as OURS — granting an overwrite of the sibling's
#: file, silently, under a green Action.
#:
#: **The separator is NUL** because an author name cannot contain one, so the
#: first `\x00` on a line is unambiguously the field boundary; and `%s` is
#: single-line as far as git is concerned, so one commit stays one git line.
#:
#: Both halves are pinned by `test_the_provenance_format_puts_the_free_text_field_last`,
#: and the security consequence by
#: `test_a_split_forging_subject_cannot_forge_our_ownership`
#: (tests/test_publish_to_pages.py).
_PROVENANCE_FORMAT: Final = "%an%x00%s"


class _UnattributedSync:
    """A sync commit whose subject this guard cannot parse. See `UNATTRIBUTED_SYNC`."""

    __slots__ = ()


#: The third outcome of `git_pages_owner`, distinct from both a repo slug and
#: `None`: a commit authored by `_SYNC_AUTHOR` whose subject `_SYNC_SUBJECT`
#: does not recognize. Some publisher's sync wrote this target, and we cannot
#: tell whose — so it is refused.
#:
#: A distinct TYPE, not a bare `object()` and not a reserved string. A bare
#: sentinel types as `object`, which collapses the union back to `object` and
#: silently switches mypy off on this reader's return — losing exactly the
#: checking that makes a sentinel better than a string here. A reserved string
#: is worse still: it shares a domain with legitimate returns, so a
#: `--source-repo` equal to it would compare equal and fail OPEN.
UNATTRIBUTED_SYNC: Final = _UnattributedSync()

#: What `git_pages_owner` answers, and what the `pages_owner` seam accepts:
#: a source-repo slug, `None` (no sync commit touches the target at all), or
#: `UNATTRIBUTED_SYNC`.
#:
#: **Discriminate with `isinstance(owner, _UnattributedSync)` and `owner is
#: None`, NOT with `owner is UNATTRIBUTED_SYNC`.** Both are correct at runtime,
#: since it is a singleton — but mypy narrows a union on `isinstance` and does
#: **not** narrow on identity against a `Final` instance of a non-enum type, so
#: the `is` form leaves `_UnattributedSync` in the union and any later `str`
#: operation on the remainder fails `union-attr` under this repo's gate. See
#: the branch in `assert_no_foreign_overwrite`, which is the worked example.
PagesOwner = Union[str, None, _UnattributedSync]


def sync_source_repo(subject: str) -> str | None:
    """The source repo a Pages sync commit names, or None if it is not one.

    None covers every non-sync writer — a hand commit, the site's own history
    (`assets/img/og_banner.png` is one), the daily ESG cron. The caller treats
    that as foreign, because "someone else wrote this" is the question, not
    "which sync wrote this".
    """
    m = _SYNC_SUBJECT.match(subject)
    return m.group("repo") if m else None


def git_pages_owner(dest: Path) -> PagesOwner:
    """Source repo of the most recent Pages SYNC commit touching `dest`.

    None means no sync commit touches it at all — a site-owned asset
    (`assets/img/og_banner.png` is one), or a file only ever written by hand.

    `UNATTRIBUTED_SYNC` means the most recent commit this reader could attribute
    to a publisher at all was one it could not attribute to WHICH publisher: a
    commit authored by `_SYNC_AUTHOR` whose subject `_SYNC_SUBJECT` does not
    parse. That is the sibling-drift case, and reading it required a second
    signal because the subject alone cannot: a drifted subject is
    indistinguishable from prose, so it was previously skipped and the scan
    resolved ownership to whatever it found NEXT — an older sync of ours,
    typically, which meant the overwrite proceeded. The author survives the walk
    where the subject does not.

    **Author (%an), not committer.** They are equal for a direct-push sync in
    both repos today, but the author is what survives a rebase or cherry-pick of
    a sync commit, where the committer flips to whoever rewrote it — and "who
    originally published this target" is the provenance question being asked.
    Guarded by `test_the_read_uses_the_author_not_the_committer`
    (tests/test_publish_to_pages.py), which builds a history where the two
    differ. It is worth a test rather than a paragraph: in the source repo,
    swapping `_PROVENANCE_FORMAT` to `%cn` left the whole suite green while
    restoring a silent overwrite.

    **Scoped to `dest`, by the `-- <path>` pathspec on the log call.** The
    summary line above says *touching `dest`*; this is the mechanism that makes
    it true, and it is load-bearing rather than incidental. Drop the pathspec and
    the walk answers "who wrote the repo last" instead of "who wrote this target
    last": whichever publisher synced most recently then owns EVERY target, and
    right after one of our own publishes that is us, so the overwrite proceeds.
    Guarded by `test_ownership_is_scoped_to_the_path_not_the_repository`
    (tests/test_publish_to_pages.py), whose fixture holds two targets owned by
    two publishers.

    **A RENAME is not covered by that, and is not fail-closed in general.** A
    path-scoped walk loses everything BEFORE a rename but keeps the renaming
    commit. A rename made by hand is a non-sync writer, so
    this returns None and the caller refuses; a rename made INSIDE a sync commit
    is attributed to that sync — ours included, which permits the write.
    `--follow` is not used, and would not rescue the second case anyway: the loop
    below returns on the newest parseable sync subject, which IS the renaming
    commit, so nothing `--follow` adds behind it is ever reached.

    **The most recent SYNC commit, not the most recent commit.** Reading the
    latest commit of any kind would let one ordinary edit on the Pages side —
    a typo fixed in place, or a bulk `prettier --write` of the kind that follows
    the site going red (twice so far — see .github/workflows/prettier.yml) —
    permanently reclassify our own post as foreign. Since the Action re-publishes every
    dated post on every run and aborts the whole batch on the first refusal,
    that would block *all* future publishing, on every retry, until someone
    hand-edited the Pages repo. Skipping non-sync commits keeps the question
    the one that matters: which publisher put this target here?

    Overwriting a later hand edit to one of OUR posts is correct, and is the
    contract that already held: this repo's `posts/` is the source of record,
    and every run rewrites its own targets from it.

    Runs `git -C <dest's own dir>`, letting git find the repo by its own upward
    walk. **That walk is not bounded here.** An earlier attempt compared the
    discovered toplevel against `dest`, which is a tautology: git found that
    repo BY walking up from `dest`, so it is always an ancestor. A bound from
    one target alone would need a different question entirely (`git ls-files
    --error-unmatch`, say); it is not attempted, rather than impossible.
    What `run()` rules out instead is narrower and decidable without git — the
    Pages dirs may not sit inside `REPO_ROOT`.

    So a Pages tree that is not a checkout, sitting under some unrelated third
    repository, consults that repository's history. That *usually* refuses, for
    want of any `chore(sync)` commit — but not always: a history that happens to
    carry our own sync subject at that path grants ownership instead, which is
    what the probe behind this rewrite actually observed. It is out of reach of
    CI, where the Action checks source and Pages out as siblings.
    """
    toplevel = _git_toplevel(dest)
    if toplevel is None:
        raise PublishError(
            f"{dest.parent} is not inside a git checkout — the shared-namespace "
            f"guard reads the Pages repo's history, so --posts-dir and "
            f"--assets-dir must point into a real clone of it."
        )
    # Field order is a security property; `_PROVENANCE_FORMAT` carries the why.
    log = _git_out(dest, "log", f"--format={_PROVENANCE_FORMAT}", "--", str(dest))
    for line in log.splitlines():
        author, _, subject = line.partition("\x00")
        owner = sync_source_repo(subject)
        if owner is not None:
            return owner
        # A sync we cannot attribute stops the walk rather than being skipped.
        # Walking past it would reach the next recognizable sync, usually an
        # older one of ours, which reads as ownership we do not have.
        if author == _SYNC_AUTHOR:
            return UNATTRIBUTED_SYNC
        # Anything else is a non-sync writer — a hand edit, a web merge, the
        # site's daily ESG cron — and is skipped: reading it as foreign would
        # let one typo fix on the Pages side brick every future publish.
    return None


def _contains(root: Path, dest: Path) -> bool:
    """Whether `dest` lies inside `root`.

    Used against `REPO_ROOT`, which is derived from `__file__` and so is a value
    this module knows exactly — never against a root git discovered by walking
    up from `dest`, which it necessarily contains.
    """
    try:
        dest.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _git_toplevel(dest: Path) -> Path | None:
    """Root of the git repo containing `dest`'s directory, or None if there is none.

    A non-zero exit here is not an anomaly — it is the ordinary answer for "that
    is not a checkout" — so it returns None rather than raising, and the caller
    raises instead.
    """
    proc = _git_run(dest, "rev-parse", "--show-toplevel")
    out = (proc.stdout or "").strip()
    return Path(out) if proc.returncode == 0 and out else None


def _git_out(dest: Path, *args: str) -> str:
    """Stdout of a git command run in `dest`'s directory. Fail closed, loudly.

    **Empty output and a non-zero exit are different conditions and are not
    collapsed.** `git log` exits 0 with empty stdout for a path it has no
    history for, which is an ordinary answer and not an error.
    """
    proc = _git_run(dest, *args)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        raise PublishError(
            f"could not read Pages history for {dest} (git {args[0]} exited "
            f"{proc.returncode}) — the repository was found, so the likely "
            f"cause is that it has no commits yet. "
            f"{stderr[0] if stderr else 'no-stderr'}"
        )
    return (proc.stdout or "").strip()


def _git_run(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in `dest`'s directory, capturing output. Never raises on exit code.

    Decoding is explicit UTF-8 rather than the runner's locale, for the reason
    `build_plan` gives about reading posts — and `errors="replace"` because a
    commit subject is not ours to control: an undecodable byte should degrade to
    a replacement character, which then simply fails to parse as a sync subject,
    rather than raise.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(dest.parent), *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as e:
        raise PublishError(f"could not run git to read Pages history: {e}") from e


def assert_no_foreign_overwrite(
    plan: dict[Path, PlanEntry],
    source_repo: str,
    pages_owner: Callable[[Path], PagesOwner] = git_pages_owner,
) -> None:
    """Phase 1: refuse to overwrite a target another publisher owns. No writes.

    The shared-namespace guard. `build_plan` catches two of THIS repo's posts
    colliding; this catches a collision with the OTHER publisher, which never
    enters either repo's plan (see the module docstring).

    Deliberately checks BOTH target kinds. The card is the likelier collision —
    a shared slug like `token-accounting-og.png` is plausible across two
    technical series, where a post collision needs the same filename on the same
    date — but a silently clobbered post is the worse outcome, and one uniform
    loop is less code than a kind-based exception.

    An **unchanged** target is waved through without consulting git: Phase 2
    will not write it, so there is nothing to arbitrate. That matters
    operationally as well as for cost — the Action's reconcile-retry loop
    re-transforms against a moved tip on every attempt, and the common case
    there is a target whose bytes already match.

    **Each refusal carries the remedy that fits it, and they are not the same
    remedy.** "Rename your slug" is right for a live collision with the sibling
    series and actively wrong for a site-owned file, where renaming an
    already-published post would break a permalink and a share-card URL that
    are already in the wild. It is wrong again for the third case
    (`UNATTRIBUTED_SYNC`) and for a third reason: the target is not a
    slug collision at all, so renaming would move a live URL and leave the
    actual defect — two publishers disagreeing about the subject format —
    exactly where it was.
    """
    for dest in sorted(plan):
        entry = plan[dest]
        if not dest.exists() or _unchanged(dest, entry.data):
            continue
        owner = pages_owner(dest)
        if owner == source_repo:
            continue
        where = f"{dest} ({entry.kind} for {entry.post_name})"
        # `isinstance`, not `is UNATTRIBUTED_SYNC`: both are correct at runtime
        # (it is a singleton), but mypy narrows a union on isinstance and does
        # not narrow on identity against a Final instance of a non-enum type —
        # and narrowing is what leaves `owner` a plain `str` by the last branch.
        if isinstance(owner, _UnattributedSync):
            raise PublishError(
                f"refusing to overwrite {where}: the most recent commit "
                f"touching it that was authored by {_SYNC_AUTHOR!r} carries a "
                f"subject this guard cannot parse, so it names no source repo. "
                f"Some publisher synced this target and there is no way to tell "
                f"which. Do NOT rename this post's slug — it would move a live "
                f"permalink and share-card URL and would not fix this. The fix "
                f"is to realign the subject format across both publishers, which "
                f"is expected to read "
                f"'chore(sync): publish posts from <repo>@<sha>'."
            )
        if owner is None:
            raise PublishError(
                f"refusing to overwrite {where}: no Pages sync commit in its "
                f"history, so no publisher this guard recognizes owns it. It is "
                f"site-owned, hand-written, or published by a writer that commits "
                f"neither under the sync identity nor under a subject this guard "
                f"parses. Check who owns it on the Pages side; do NOT reflexively "
                f"rename this post's slug, which would move a permalink and a "
                f"share-card URL that are already live."
            )
        raise PublishError(
            f"refusing to overwrite {where}: it was last published by "
            f"{owner!r}, not by {source_repo!r}. The Pages site is a namespace "
            f"shared with another publisher — rename this post's slug so its "
            f"targets are unique across both series."
        )


def _unchanged(dest: Path, data: bytes) -> bool:
    """Whether `dest` already holds exactly `data` — the content-compare predicate.

    Shared by `assert_no_foreign_overwrite` and `write_if_changed` so the two
    cannot drift: a target the guard waves through as unchanged is exactly the
    target Phase 2 declines to write.
    """
    return dest.exists() and dest.read_bytes() == data


def write_if_changed(dest: Path, data: bytes, dry_run: bool) -> bool:
    """Write `data` to `dest` only if the bytes differ. Returns whether changed.

    The parent dir is a precondition (checked up front), never created here — a
    missing Pages dir means the worktree isn't set up, which should fail loud.
    """
    if _unchanged(dest, data):
        return False
    if not dry_run:
        dest.write_bytes(data)
    return True


def run(
    sources: Sequence[Path],
    posts_dir: Path,
    assets_dir: Path,
    dry_run: bool,
    source_repo: str,
    pages_owner: Callable[[Path], PagesOwner] = git_pages_owner,
) -> int:
    # Phase-1 preconditions: the Pages dirs must already exist. Do NOT mkdir —
    # absence means the worktree isn't checked out, an operator error.
    for label, d in (("posts dir", posts_dir), ("assets dir", assets_dir)):
        if not d.is_dir():
            raise PublishError(
                f"{label} not found: {d} — is the Pages worktree checked out?"
            )
        # A dir-sanity precondition, deliberately EAGER and deliberately here
        # rather than in the guard: a brand-new post's targets are all absent,
        # so nothing is arbitrated, and yet writing them into this repo's own
        # tree is exactly the slip worth catching. `REPO_ROOT` is derived from
        # __file__, so this asks git nothing and cannot be a tautology — unlike
        # the toplevel-vs-target comparison this replaced (see
        # `git_pages_owner`).
        if _contains(REPO_ROOT, d):
            raise PublishError(
                f"{label} is inside this repo ({d}) — --posts-dir and "
                f"--assets-dir must point at a checkout of the Pages repo, "
                f"not at the source repo publishing into it."
            )

    plan = build_plan(sources, posts_dir, assets_dir)
    # The second Phase-1 validator. Not gated on `dry_run` — the operator
    # dry-run runs against a real Pages checkout and is exactly the preview that
    # should surface a foreign collision before the real push does.
    assert_no_foreign_overwrite(plan, source_repo, pages_owner)

    # Phase 2: apply. Content-compare means unchanged outputs write nothing.
    prefix = "[dry-run] " if dry_run else ""
    changed = 0
    for dest in sorted(plan):
        entry = plan[dest]
        if write_if_changed(dest, entry.data, dry_run):
            changed += 1
            print(f"{prefix}{entry.kind:5} CHANGED   {dest}")
        else:
            print(f"{prefix}{entry.kind:5} unchanged {dest}")
    print(f"{prefix}{changed} change(s) across {len(plan)} target(s).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Transform + publish posts (and their OG cards) to the Jekyll Pages tree."
        ),
    )
    ap.add_argument(
        "sources", nargs="+", type=Path, metavar="source.md", help="post(s) to publish"
    )
    ap.add_argument(
        "--posts-dir", required=True, type=Path, help="Pages _posts/ directory"
    )
    ap.add_argument(
        "--assets-dir", required=True, type=Path, help="Pages assets/img/ directory"
    )
    ap.add_argument(
        "--source-repo",
        required=True,
        metavar="SLUG",
        help=(
            "this repo's GitHub slug (hyphenated), used to tell our own Pages "
            "targets from another publisher's"
        ),
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="resolve + compare, but write nothing"
    )
    args = ap.parse_args(argv)
    # `required=True` accepts an empty string, and an empty slug commits a
    # subject `_SYNC_SUBJECT` can never parse: `... posts from @<sha>`. Nothing
    # goes wrong at the time — every target of a brand-new post is absent, so
    # the guard waves the run through — and the cost lands on a LATER run.
    # That commit is also authored by `_SYNC_AUTHOR`, so every later
    # update of that post reads as `UNATTRIBUTED_SYNC`: a loud refusal by then,
    # but under a remedy ("realign the subject format across both publishers")
    # that names the wrong cause entirely.
    #
    # The check below closes the EMPTY case only. A non-empty slug carrying a
    # character outside `_SYNC_SUBJECT`'s `[A-Za-z0-9._-]` — `my repo`, say —
    # reaches the identical trap, and nothing here rejects it: the pattern is
    # never applied to the incoming slug. Unreached in practice for the reason
    # below rather than by validation.
    #
    # The workflow feeds this from `github.event.repository.name`; check it
    # rather than trust it.
    source_repo = args.source_repo.strip()
    if not source_repo:
        raise PublishError("--source-repo must not be empty")
    return run(
        args.sources,
        args.posts_dir,
        args.assets_dir,
        args.dry_run,
        source_repo,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PublishError as e:
        sys.exit(f"error: {e}")
