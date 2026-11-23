"""Importable test fixtures.

Most of ``tests/fixtures/`` is saved *data* read by path (``FIXTURES_DIR`` in
``tests/_helpers.py``). This package marker exists so the handful of importable,
code-defined fixtures here (e.g. :mod:`tests.fixtures.api_snapshot`) can be
imported as ``tests.fixtures.<name>`` without loosening the data-only convention
for the rest of the directory.
"""
