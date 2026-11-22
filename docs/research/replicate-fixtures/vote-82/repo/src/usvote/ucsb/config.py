"""UCSB-source configuration — resolve the local snapshot directory from the env.

Per-source inputs live in the relevant subpackage's own config module (the top-level
:mod:`usvote.config` docstring reserves this location). Like the TIGER shapefile and
the MIT CSV, the UCSB HTML snapshot is machine-local data that lives outside the repo,
so its path is externalized to an env var rather than hard-coded — the
``os.path.expanduser(...)`` constant the original snapshot script carried (D023).

The name follows the sibling convention: ``USVOTE_SHAPEFILE_PATH`` and
``USVOTE_MIT_CSV_PATH`` each name **format + role**, so ``USVOTE_UCSB_HTML_DIR`` is
exactly parallel (a ``..._SNAPSHOT_DIR`` variant would name role only).

Here the directory is not merely *where output goes* — it is also **an input**, because
:func:`usvote.ucsb.scrape.snapshot_elections` enumerates the year URLs from an index
page already saved inside it. That is why the unset/missing hints below spell out the
bootstrap command: this getter is exactly where a fresh machine finds out it has no
snapshot directory yet, so it is where the fix belongs.

The unset/empty/nonexistent → typed :class:`~usvote.config.ConfigError` handling is
shared with the shapefile and MIT getters via
:func:`usvote.config.require_path_from_env`; importing *up* from a subpackage into
the source-agnostic top-level config is the
D006-allowed direction.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from usvote.config import require_path_from_env

#: Environment variable holding the path to the local UCSB raw-HTML snapshot directory.
UCSB_HTML_DIR_VAR = "USVOTE_UCSB_HTML_DIR"

# The one manual step in the snapshot flow, and thus the one request not issued by
# usvote.ucsb.scrape.fetch_url -- so it carries the same truthful User-Agent by hand.
# Kept in sync with scrape.USER_AGENT / scrape.INDEX_FILENAME by a test rather than by
# an import (scrape imports this module; the reverse would be a cycle).
_BOOTSTRAP_HINT = (
    "The directory holds one '{year}.html' per election plus the "
    "'_index_elections.html' index that URL enumeration reads. To bootstrap an "
    "empty one, save the index first (identifying truthfully, as the scrape does):\n"
    "  mkdir -p \"$USVOTE_UCSB_HTML_DIR\" && curl -A "
    "'us-presidential-vote-analysis-research/0.1 (personal academic research)' "
    "https://www.presidency.ucsb.edu/statistics/elections "
    '-o "$USVOTE_UCSB_HTML_DIR/_index_elections.html"\n'
    "Then run: python -m usvote.ucsb"
)


def ucsb_html_dir_from_env(environ: Mapping[str, str] = os.environ) -> str:
    """Return the UCSB raw-HTML snapshot directory from ``USVOTE_UCSB_HTML_DIR``.

    Required — there is no sensible default for a machine-local data directory, and
    defaulting would risk silently scraping into the wrong place. Raises
    :class:`~usvote.config.ConfigError` if the variable is unset/empty or points at a
    path that does not exist; both messages carry the bootstrap command, since an
    absent directory is the expected first-run state on a fresh machine rather than an
    exotic failure. UCSB content is non-redistributable (D014/D016), so this directory
    must live **outside** the repository. ``environ`` is injectable for testing.
    """
    return require_path_from_env(
        UCSB_HTML_DIR_VAR,
        environ,
        unset_hint=(
            "Point it at the local UCSB raw-HTML snapshot directory — outside this "
            f"repository, which is public (UCSB content is not redistributable). "
            f"{_BOOTSTRAP_HINT}"
        ),
        missing_hint=_BOOTSTRAP_HINT,
    )
