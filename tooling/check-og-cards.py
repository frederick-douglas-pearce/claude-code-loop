#!/usr/bin/env python3
"""Pre-merge guard: every post under posts/ has a resolvable OG card.

The Pages-sync Action (`.github/workflows/pages-sync.yml` →
`tooling/publish-to-pages.py`) resolves each post's `og_card_source`, copies the
rendered card into the Pages repo, and **fails closed** if it can't. But that
only runs at publish time — on a push to `main` — so a post merged without its
OG card turns the sync red on `main`, after the fact. That is not hypothetical:
it happened in the `claude-code-sessions` repo for its Part 3 post, which is why
this guard is ported alongside the publisher.

This guard runs the publisher's OWN Phase-1 validator (`build_plan`) on PRs, so
the same fail-closed conditions — missing/empty `og_card_source`, an absolute or
repo-escaping path, a missing source file, a missing `og_image`, and cross-post
image-target collisions — surface on the PR instead of on `main`. By reusing
`build_plan` rather than re-deriving the rules, the guard cannot drift from what
`build_plan` enforces; a future fail-closed condition added THERE is inherited
here for free.

**It does not cover everything publish enforces, and the gap is deliberate.**
`publish-to-pages.py` runs a second Phase-1 validator outside `build_plan` —
`assert_no_foreign_overwrite`, the shared-namespace guard — which needs the Pages
repo's commit history to decide whether a target belongs to this repo or to a
sibling publisher. This guard has no Pages checkout by design (see below), so it
structurally cannot run that check: a slug that collides with a sibling passes
here green and stops at the sync. See posts/README.md → The shared-namespace
guard.

This repo is PR-per-feature-branch (CLAUDE.md → Branching & PR flow; `posts/` is
on the PR side), so this runs on every `posts/` PR — unlike `claude-code-sessions`,
where `posts/` is direct-commit-allowed. It does not BLOCK a merge: branch
protection requires the aggregate `test-suite` job only, and whether this becomes
a required check is issue #195's question.

It guards card *presence*, not *generation*. **There is no renderer in this repo
yet** — producing the card is a manual step, and automating it is issue #181. So
the remedy this guard prints tells you to commit a card at the path
`og_card_source` names; it deliberately describes no rendering procedure, because
none exists here to describe.

Stdlib only; needs no Pages repo, checkout, or PAT — `build_plan` is Phase 1 (no
writes), so the Pages target dirs are passed as inert placeholders used only as
plan keys.

Usage:
    python3 tooling/check-og-cards.py [posts/NNNN-*.md ...]

Defaults to every dated post (`posts/[0-9][0-9][0-9][0-9]-*.md`), matching the
publisher's own selection so the two see the same file set (and the guard skips
`posts/README.md`). Exit 0 if all resolve, 1 with a per-post report otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

# Reuse publish-to-pages.py verbatim so the guard can't drift from the publisher.
# The script's filename is hyphenated (not importable by name), so we load it the
# same way the test suite does. This is also why the guard must live in tooling/
# beside the publisher rather than anywhere else.
_SCRIPT = Path(__file__).resolve().parent / "publish-to-pages.py"


def _load_publisher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publish_to_pages", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ptp = _load_publisher()

# Inert stand-ins for the Pages target dirs. `build_plan` is Phase 1 (no writes)
# and uses these only as resolved dict keys, so they need not exist. Two posts
# whose `og_image` basenames collide map to the same key under _PAGES_ASSETS —
# which is exactly how `build_plan` detects a real cross-post collision.
_PAGES_POSTS = Path("/__pages__/_posts")
_PAGES_ASSETS = Path("/__pages__/assets/img")

_REMEDY = (
    "This is the same fail-closed resolution the Pages-sync Action runs at\n"
    "publish time — fixing it here keeps it off `main`. Commit an OG card at the\n"
    "path the post's `og_card_source` names (under `posts/images/<slug>/`, per\n"
    "posts/README.md), or correct the pointer. Producing the card is a manual\n"
    "step today; automating it is issue #181."
)


def _bare(err: Exception, name: str) -> str:
    """`build_plan` tags errors as '<post>: <msg>'; drop the prefix for the report."""
    msg = str(err)
    prefix = f"{name}: "
    return msg[len(prefix) :] if msg.startswith(prefix) else msg


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Guard: every post under posts/ has a resolvable OG card "
            "(runs publish-to-pages.py's own fail-closed validator)."
        ),
    )
    ap.add_argument(
        "posts",
        nargs="*",
        type=Path,
        help="posts to check (default: every posts/[0-9][0-9][0-9][0-9]-*.md)",
    )
    args = ap.parse_args(argv)

    posts: list[Path] = list(args.posts) or sorted(
        (ptp.REPO_ROOT / "posts").glob("[0-9][0-9][0-9][0-9]-*.md")
    )
    if not posts:
        print("no posts found to check", file=sys.stderr)
        return 0

    # Per-post: run the real validator on each post alone, so we collect EVERY
    # failing post. (`build_plan` raises on the first failure, so a single
    # whole-batch call would stop at one and hide the rest.)
    results: list[tuple[str, str | None]] = []
    ok_sources: list[Path] = []
    for src in posts:
        try:
            ptp.build_plan([src], _PAGES_POSTS, _PAGES_ASSETS)
            results.append((src.name, None))
            ok_sources.append(src)
        except ptp.PublishError as e:
            results.append((src.name, _bare(e, src.name)))

    # Whole-batch over the individually-valid posts: the one condition a per-post
    # pass can't see is two posts colliding on the same Pages image target.
    collision: str | None = None
    if len(ok_sources) > 1:
        try:
            ptp.build_plan(ok_sources, _PAGES_POSTS, _PAGES_ASSETS)
        except ptp.PublishError as e:
            collision = str(e)

    for name, err in results:
        print(f"  [{'FAIL' if err else 'ok'}] {name}" + (f" — {err}" if err else ""))
    if collision:
        print(f"  [FAIL] cross-post image collision — {collision}")

    n_fail = sum(1 for _, e in results if e) + (1 if collision else 0)
    if n_fail:
        # Ensure the per-post report precedes the stderr summary in CI logs.
        sys.stdout.flush()
        print(f"\n{n_fail} OG-card problem(s). {_REMEDY}", file=sys.stderr)
        return 1

    print(f"\nAll {len(posts)} post(s) have a resolvable OG card.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
