"""Unit tests — no network, no database.

Home for the offline suite (and new unit tests as the package grows: the E4/E5
``usvote/ucsb`` and ``usvote/mit`` ports).

Selection is by **marker**, not directory: the default ``-m 'not integration'``
(see ``[tool.pytest.ini_options]``) is the single source of truth for what runs
where. A test placed here must stay offline; one needing a live Postgres belongs
in ``tests/integration/`` and must carry ``@pytest.mark.integration``.

Fixtures live in ``tests/conftest.py`` (auto-discovered up the tree); import
plain helpers with ``from tests._helpers import ...``.
"""
