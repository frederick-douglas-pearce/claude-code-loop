"""MIT-source configuration — resolve the local CSV path from the environment.

Per-source inputs live in the relevant subpackage's own config module (the
top-level :mod:`usvote.config` docstring reserves this location and the
``USVOTE_MIT_CSV_PATH`` name). Like the TIGER shapefile, the MIT
``1976-2024-president.csv`` is a machine-local download that lives outside the repo
(under the shared external data directory), so its path is externalized to an env
var rather than hard-coded — consistent with the DB/shapefile config pattern from
E2-S6 (#31).

The heavy lifting (unset/empty/nonexistent → typed :class:`~usvote.config.ConfigError`)
is shared with the shapefile getter via :func:`usvote.config.require_path_from_env`;
importing *up* from a subpackage into the source-agnostic top-level config is the
D006-allowed direction.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from usvote.config import require_path_from_env

#: Environment variable holding the path to the MIT ``1976-2024-president.csv``.
MIT_CSV_PATH_VAR = "USVOTE_MIT_CSV_PATH"


def mit_csv_path_from_env(environ: Mapping[str, str] = os.environ) -> str:
    """Return the MIT president-CSV path from ``USVOTE_MIT_CSV_PATH``.

    Required — there is no sensible default for a machine-local download. Raises
    :class:`~usvote.config.ConfigError` if the variable is unset/empty or points at a
    path that does not exist. The MIT Election Lab president dataset is a free CC0
    download from Harvard Dataverse (``doi:10.7910/DVN/42MVDX``). ``environ`` is
    injectable for testing.
    """
    return require_path_from_env(
        MIT_CSV_PATH_VAR,
        environ,
        unset_hint=(
            "Point it at the MIT Election Lab '1976-2024-president.csv', a free CC0 "
            "download from Harvard Dataverse: https://doi.org/10.7910/DVN/42MVDX"
        ),
        missing_hint=(
            "Check the path points at the MIT '1976-2024-president.csv' file."
        ),
    )
