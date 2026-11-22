"""Load stage — write the three DataFrames into the Postgres ``dwh`` schema.

Maps to notebook Section 4. Orchestrates DataFrame -> Postgres via the ``DBC``
wrapper in :mod:`usvote.db`, creating the loose star schema (``state`` and
``candidate`` dimensions, ``votes`` fact) in FK-dependency order
(state -> candidate -> votes) and inserting the rows.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S5 (#28). Two changes
from the notebook's ``create_tables_from_dfs``:

- **Named frames, not a positional list.** The notebook relied on
  ``dfs = [state_df, candidates_df, votes_df]`` lining up by position with
  ``table_names``; :func:`load_dataframes` takes the three frames by keyword and
  orders them internally, so a caller cannot silently transpose the candidate and
  state loads (``transform_parsed_years`` returns them candidates-first).
- **Guarded destructive write.** The notebook defaulted ``replace=True``, which
  cascades a drop/recreate of the whole ``dwh`` schema on every run. Here
  ``replace`` defaults to ``False``; the drop happens only when a caller passes
  ``replace=True`` explicitly (CLAUDE.md: "be deliberate about executing the write
  cells").

This is the **EC star-schema** loader. The popular-vote sources do not reuse it —
they share their own source-neutral seam, :func:`usvote.pv.load.load_pv_records`
over the ``dwh.pv_votes`` table (D018), which loads *alongside* this EC spine in the
same schema. Both loaders share only the lower-level :class:`usvote.db.DBC` wrapper.
Connection params and the shapefile path are externalized in :mod:`usvote.config`
(E2-S6, #31).
"""

from __future__ import annotations

import pandas as pd

from usvote.db import DBC

# The data-warehouse schema and its tables, listed in FK-dependency order: a table
# with a FK REFERENCES must be created after the table it points at (candidate ->
# state, votes -> state + candidate). load_dataframes creates and inserts in this
# order.
SCHEMA = "dwh"
TABLE_NAMES: tuple[str, str, str] = ("state", "candidate", "votes")


def build_table_column_defs(schema: str = SCHEMA) -> list[list[tuple[str, ...]]]:
    """Return the per-table column definitions, ported from notebook cell 200.

    A function (not a module constant) because the ``candidate`` and ``votes`` FK
    definitions embed ``schema`` in their ``REFERENCES`` clause; keeping it
    parameterized lets a caller load into a schema other than ``dwh`` without the
    FKs drifting. Each inner list is one table's columns as ``DBC.create_table``
    tuples (name, type, *constraints), ordered to match :data:`TABLE_NAMES`.
    """
    state, candidate, _votes = TABLE_NAMES
    return [
        [  # state dimension
            ("state", "varchar", "primary key"),
            ("state_usps", "varchar(2)", "not null"),
            ("region", "smallint", "not null"),
            ("division", "smallint", "not null"),
            ("statens", "varchar", "not null"),
            ("geoid", "varchar", "not null"),
            ("area_land", "bigint", "not null"),
            ("area_water", "bigint", "not null"),
            ("latitude", "numeric", "not null"),
            ("longitude", "numeric", "not null"),
        ],
        [  # candidate dimension
            ("candidate_id", "smallint", "primary key"),
            # UNIQUE so the EC<->PV join (usvote.join, #69) can resolve a PV loser
            # row's candidate_id by canonical ``name`` unambiguously — the surrogate
            # candidate_id is not carried on PV rows, so the name is the join key, and
            # the one-row-per-name grain (only a transform-time assert until now) must
            # hold at the DB level too. See docs/canonical-keys.md (name is the
            # canonical candidate key) and transform.assert_unique_grain.
            ("name", "varchar", "not null", "unique"),
            ("name_first", "varchar", "not null"),
            ("name_middle", "varchar"),
            ("name_last", "varchar"),
            ("name_suffix", "varchar"),
            ("state", "varchar", f"REFERENCES {schema}.{state}"),
            ("state_2", "varchar", f"REFERENCES {schema}.{state}"),
            ("party", "varchar"),
            ("party_2", "varchar"),
        ],
        [  # votes fact
            ("votes_id", "integer", "primary key"),
            ("year", "smallint", "not null"),
            ("state", "varchar", f"REFERENCES {schema}.{state}"),
            ("is_total", "boolean", "not null"),
            (
                "candidate_id", "smallint", "not null",
                f"REFERENCES {schema}.{candidate}",
            ),
            ("total_electoral_votes", "smallint", "not null"),
            ("president_electoral_votes", "smallint", "not null"),
            ("president_electoral_rank", "smallint", "not null"),
            ("took_office", "boolean", "not null"),
        ],
    ]


def load_dataframes(
    dbc: DBC,
    *,
    state_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    votes_df: pd.DataFrame,
    schema: str = SCHEMA,
    replace: bool = False,
    close: bool = False,
) -> None:
    """Create the ``dwh`` schema + tables and insert the three warehouse frames.

    Creates ``schema`` then each table in FK-dependency order (state -> candidate
    -> votes) using :func:`build_table_column_defs`, inserting each frame right
    after its table is created.

    ``replace`` gates the **destructive** rebuild: when ``True`` the schema is
    dropped with ``CASCADE`` and recreated empty, discarding all existing ``dwh``
    data — this is the notebook's full-refresh behavior, now opt-in. When ``False``
    (the default) nothing is dropped; the schema/tables are created only if absent,
    so re-running against a populated warehouse will raise a primary-key violation
    on insert. Pass ``replace=True`` for a clean rebuild.

    The per-table ``create_table`` call is always non-destructive: on the
    ``replace=True`` path the schema drop has already removed the tables, so a
    second per-table drop would be redundant.

    ``close`` closes the connection when done; it defaults to ``False`` because the
    caller owns the ``dbc`` it passed in.
    """
    frames = {"state": state_df, "candidate": candidates_df, "votes": votes_df}
    column_defs = dict(zip(TABLE_NAMES, build_table_column_defs(schema), strict=True))

    dbc.create_schema(schema, replace=replace)
    for table_name in TABLE_NAMES:
        dbc.create_table(schema, table_name, column_defs[table_name], replace=False)
        dbc.insert_df_into_table(schema, table_name, frames[table_name])
    if close:
        dbc.close_connection()
