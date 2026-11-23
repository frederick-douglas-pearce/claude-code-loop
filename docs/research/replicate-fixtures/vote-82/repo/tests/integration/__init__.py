"""Integration tests — require a live Postgres (excluded by default).

Home for tests that exercise the real load path against a database:
``test_db.py`` (the ``DBC`` round-trip) and ``test_load.py`` (the full EC
pipeline into Postgres). Every test here must carry ``@pytest.mark.integration``
so the default ``-m 'not integration'`` selection (see
``[tool.pytest.ini_options]``) skips it; CI runs them in a dedicated job with a
Postgres service container (``uv run pytest -m integration``).

The live-DB config comes from the ``integration_db_config`` fixture in
``tests/conftest.py`` (``USVOTE_TEST_DB_*`` env vars); import plain helpers with
``from tests._helpers import ...``.
"""
