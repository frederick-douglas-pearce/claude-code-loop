#!/usr/bin/env python3
"""Pre-merge guard: every post under posts/ records a humanizer pass.

The humanizer skill (https://github.com/blader/humanizer) strips structural
AI-writing tells from a draft: not-X-but-Y staging, one-line closers, staged
run-ups, forced triads, dashes used as a universal connector, inflated
significance. It is a manual, judgment-heavy step, and nothing about a finished
draft reveals whether it ran.

**It checks that the pass was recorded, not that the prose is clean.** The skill
needs judgment a pattern-matching lint cannot supply, and a lint that fires on
load-bearing uses trains the writer to write around it, which is worse than no
lint. So `humanizer_pass` is an attestation, and this guard only enforces that
one was made. Ported from `claude-code-sessions`' `tooling/check-humanizer-pass.py`
(#182), which records the worked case behind that argument.

**This is not the enforcing check.** `tests/test_posts_frontmatter.py` already
requires `humanizer_pass` on every post and rejects a malformed value, under the
required `test-suite` check. What this guard adds is a per-post report, a remedy
message, and the **count of declined passes**: `none` keeps a post green without
claiming work that never happened, and the number of them is debt someone can act
on. Both read the value grammar from `tooling/attestation.py`, so this guard
cannot accept a value the contract checker rejects.

Two deltas from the source, both deliberate:
  - it accepts only `vX.Y.Z` or `none`. The source also accepts `predates`, a
    version without its `v`, a two-part version, and a trailing `# comment`; this
    series' contract rejects all four (posts/README.md).
  - with no dated post on disk it exits 0 and says so. The source exits 1. Here
    `tests/test_check_humanizer_pass.py` is what shows the guard can fail, as
    `tests/test_check_og_cards.py` does for `check-og-cards.py`.

Frontmatter is read with publish-to-pages.py's own parser, so the guard sees each
field exactly as the publisher does.

Stdlib only. Usage:
    python3 tooling/check-humanizer-pass.py [posts/NNNN-*.md ...]

Defaults to every dated post (`posts/[0-9][0-9][0-9][0-9]-*.md`), matching the
publisher's own selection, so `posts/README.md` is skipped. Exit 0 if every post
records a pass, 1 with a per-post report otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str) -> ModuleType:
    # publish-to-pages.py is hyphenated, so neither sibling is imported by name.
    path = _HERE / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ptp = _load("publish_to_pages", "publish-to-pages.py")
attestation = _load("attestation", "attestation.py")

FIELD = "humanizer_pass"


def check_value(value: str | None) -> str | None:
    """None if the recorded value is acceptable, else the reason it isn't."""
    if value is None:
        return f"no `{FIELD}` in frontmatter"
    if not value:
        return f"`{FIELD}` is empty"
    if not attestation.is_version_attestation(value):
        return (
            f"`{FIELD}: {value}` is not a skill version "
            f"(expected e.g. `v3.0.0`, or `{attestation.DECLINED}`)"
        )
    return None


def read_pass(src: Path) -> str | None:
    """The post's recorded `humanizer_pass`, or None if absent.

    Raises PublishError for an unreadable file, so a bad explicit path lands in
    the per-post report instead of as a traceback."""
    try:
        # Posts are UTF-8 and full of em dashes; a runner with a non-UTF-8 locale
        # would otherwise decode as ASCII. UnicodeDecodeError is a ValueError, not
        # an OSError, so it is named separately.
        text = src.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        reason = getattr(e, "strerror", None) or e
        raise ptp.PublishError(f"cannot read {src.name}: {reason}") from e
    fm_block, _ = ptp.split_frontmatter(text)
    return ptp.read_field(fm_block, FIELD)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Guard: every post under posts/ records a humanizer pass "
        "(the pass itself is manual; this checks it was recorded).",
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

    # Collect every failure rather than stopping at the first, so one run reports
    # the whole backlog.
    results: list[tuple[str, str | None, str | None]] = []
    for src in posts:
        try:
            value = read_pass(src)
        except ptp.PublishError as e:
            results.append((src.name, str(e), None))
            continue
        results.append((src.name, check_value(value), value))

    for name, err, value in results:
        if err:
            print(f"  [FAIL] {name}: {err}")
        elif value == attestation.DECLINED:
            print(f"  [ok]   {name}: {value} (pass deliberately declined)")
        else:
            print(f"  [ok]   {name}: {value}")

    n_fail = sum(1 for _, err, _ in results if err)
    n_declined = sum(
        1 for _, err, value in results if not err and value == attestation.DECLINED
    )

    if n_fail:
        sys.stdout.flush()  # keep the per-post report ahead of the stderr summary
        print(
            f"\n{n_fail} post(s) with no recorded humanizer pass. Run the humanizer skill over the\n"
            f"draft, then set `{FIELD}: v<version>` in its frontmatter. If the pass was\n"
            f"deliberately skipped, set `{FIELD}: {attestation.DECLINED}` to record that instead.",
            file=sys.stderr,
        )
        return 1

    # Versioned and declined are reported as two numbers, never one: the declined
    # count is the actionable one, and a combined total would bury it.
    print(
        f"\nAll {len(posts)} post(s) record a humanizer pass: "
        f"{len(posts) - n_declined} versioned, {n_declined} declined."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
