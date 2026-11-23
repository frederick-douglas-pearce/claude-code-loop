"""D028 structural invariant: ``usvote/api/`` never imports the DB / build stack.

The API serves a read-only snapshot with **no live DB at serve time**. The plan makes
that structural, not incidental: nothing under ``usvote/api/`` may import
:mod:`usvote.db`, psycopg2, :mod:`usvote.snapshot` (the build module, which drags pandas
+ the DB stack), or pandas itself. This mirrors the project's other greppable layering
guards (the ``dwh.votes`` guard; ``test_warehouse.test_no_pv_source_imports_the_warehouse
_composition_root``) — a violation fails this test, not review.
"""

from __future__ import annotations

import re
from pathlib import Path

import usvote.api as api

#: The forbidden imports under ``usvote/api/``. ``usvote.snapshot`` (build) and pandas are
#: forbidden alongside the obvious DB modules because importing either would transitively
#: pull the whole build/DB stack across the serve-time boundary D028 draws.
_FORBIDDEN = ("usvote.db", "psycopg2", "usvote.snapshot", "pandas")


def test_api_imports_no_db_or_build_stack() -> None:
    pkg_root = Path(api.__file__).parent
    # Match `import <mod>` / `from <mod> import ...` for each forbidden module, being
    # careful that `usvote.snapshot` does NOT match the allowed `usvote.snapshot_schema`
    # (word boundary after the module name).
    patterns = [
        re.compile(rf"(^|\W)(import\s+{re.escape(m)}|from\s+{re.escape(m)})\b")
        for m in _FORBIDDEN
    ]
    offenders: list[str] = []
    for py in pkg_root.rglob("*.py"):
        text = py.read_text()
        for mod, pattern in zip(_FORBIDDEN, patterns, strict=True):
            if pattern.search(text):
                offenders.append(f"{py.relative_to(pkg_root).as_posix()} -> {mod}")
    assert not offenders, f"usvote/api must not import the DB/build stack: {offenders}"
