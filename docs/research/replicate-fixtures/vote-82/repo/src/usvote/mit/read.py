"""Read stage — load the MIT Election Lab president CSV into a DataFrame.

The ingest seam of the MIT pipeline, and the MIT analogue of the EC
:mod:`usvote.scrape` stage. It is deliberately **not** named ``scrape.py``: MIT
ships a single clean local CSV already at the (year, state, candidate) fact grain
(4,822 rows, 13 elections 1976–2024, 51 jurisdictions; CC0 — see D016 and
``.claude/specs/research-pv-source.md`` §4), so there is no network access and no
snapshot/replay story. Naming it ``read.py`` keeps the EC ``scrape.py`` "only place
network belongs" contract intact while marking this as its own kind of ingest.

The load is a pure local-file read: point it at a path (or let it resolve
``USVOTE_MIT_CSV_PATH`` via :mod:`usvote.mit.config`) and it returns the raw frame.
It intentionally does **no** transform work — no filtering to EC-getting candidates,
no melting, no name reconciliation, no NaN handling; those belong to the later MIT
transform stage. The one guard it does apply is a **schema check**: the CSV's
columns must contain every name in :data:`EXPECTED_COLUMNS`, so an upstream MIT
re-release that renames or drops a column fails loudly here rather than surfacing as
a confusing ``KeyError`` deep in transform. The check is a *subset* test — MIT
versions the file and may add columns; additive changes are non-breaking.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from usvote.mit.config import mit_csv_path_from_env

#: The MIT president CSV columns this pipeline reads from, in file order. This is
#: the full 15-column snapshot of the ``1976-2024-president.csv`` schema (not just
#: the subset transform consumes), so any renamed/dropped column is caught at the
#: ingest boundary. See ``.claude/specs/research-pv-source.md`` §4 for the field
#: catalog.
EXPECTED_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "state_po",
    "state_fips",
    "state_cen",
    "state_ic",
    "office",
    "candidate",
    "party_detailed",
    "writein",
    "candidatevotes",
    "totalvotes",
    "version",
    "notes",
    "party_simplified",
)


class MITReadError(RuntimeError):
    """Raised when the MIT CSV cannot be read or is missing an expected column.

    Mirrors the EC :class:`usvote.scrape.ScrapeError` — a typed, message-carrying
    failure at the ingest boundary rather than a bare ``KeyError`` /
    ``FileNotFoundError`` / pandas error surfacing later. Covers a missing file, an
    empty/unparseable file, and a renamed/dropped column, so every ingest failure is
    diagnosable at this seam regardless of whether the path was passed explicitly or
    resolved from the env.
    """


def load_mit_president_csv(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Load the MIT ``1976-2024-president.csv`` into a DataFrame.

    When ``path`` is ``None`` the CSV location is resolved from
    ``USVOTE_MIT_CSV_PATH`` via :func:`usvote.mit.config.mit_csv_path_from_env`
    (pass ``environ`` to drive that resolution in tests; it defaults to the live
    process environment); an explicit ``path`` is used as-is. The returned frame is
    the CSV verbatim — no dtype coercion, so the transform stage owns typing — after
    asserting every name in :data:`EXPECTED_COLUMNS` is present.

    Raises :class:`MITReadError` if the file is missing, empty/unparseable, or missing
    an expected column — so an explicitly-passed path fails the same typed way an
    env-resolved one does (the latter's *unset* var still surfaces as
    :class:`~usvote.config.ConfigError` from the getter).
    """
    if path is None:
        path = (
            mit_csv_path_from_env(environ)
            if environ is not None
            else mit_csv_path_from_env()
        )
    try:
        df = pd.read_csv(path)
    except FileNotFoundError as exc:
        raise MITReadError(f"MIT CSV not found at {path!r}.") from exc
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise MITReadError(
            f"MIT CSV at {path!r} is empty or unparseable: {exc}"
        ) from exc
    _assert_expected_columns(df)
    return df


def _assert_expected_columns(df: pd.DataFrame) -> None:
    """Raise :class:`MITReadError` if ``df`` lacks any :data:`EXPECTED_COLUMNS`."""
    missing = [col for col in EXPECTED_COLUMNS if col not in df.columns]
    if missing:
        raise MITReadError(
            f"MIT CSV is missing expected column(s): {missing}. "
            f"Present columns: {list(df.columns)}"
        )
