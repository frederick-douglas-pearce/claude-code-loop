"""Backwards-compatible shim: ``DBC`` now lives in :mod:`usvote.db`.

The implementation moved to ``src/usvote/db.py`` in E1-S3 (#21). This module is
retained only so the step-1 notebook's ``from db_tools import DBC`` keeps working
during the incremental notebook->package migration (D003). Import from
``usvote.db`` in new code. This shim is expected to be removed once the notebook
is ported to the package in E2.
"""

from usvote.db import DBC, DBConnectionError

__all__ = ["DBC", "DBConnectionError"]
