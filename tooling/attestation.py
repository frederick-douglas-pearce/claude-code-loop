"""The value grammar for the version-shaped attestation fields in `posts/` frontmatter.

`claude_code_version_verified` and `humanizer_pass` each record that a manual step was
performed, as the version of the tool that performed it, or `none` where the step was
deliberately declined. `posts/README.md` → *The three attestation fields* states the
contract in prose.

**This module is the one definition of that grammar, and it exists so there is only
one.** Two things read it: `tests/test_posts_frontmatter.py`, the contract checker that
runs under the required `test-suite` check, and `tooling/check-humanizer-pass.py`, the
humanizer guard (#182). Before #182 the grammar lived only in the contract checker; the
guard it was ported from carried a looser grammar of its own. Importing one definition
into both means the guard cannot accept a value the contract rejects.

What this does **not** make identical is how the two callers *extract* a value from a
frontmatter line: the contract checker uses its own parser and the guard uses the
publisher's `read_field`. That is a separate coupling, and this module says nothing
about it.

Stdlib only: the suite loads it by path, and the suite runs on bare `python3`.
"""

from __future__ import annotations

import re

# A step deliberately declined for this post. There is deliberately no `predates`:
# see posts/README.md on why an empty closed set is not created.
DECLINED = "none"

VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")


def is_version_attestation(value: str) -> bool:
    """True iff `value` is a `vX.Y.Z` version or `none`. Matched as given: no stripping."""
    return value == DECLINED or VERSION_RE.match(value) is not None
