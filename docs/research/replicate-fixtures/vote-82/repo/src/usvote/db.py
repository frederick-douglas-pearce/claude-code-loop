"""Database access — the ``DBC`` psycopg2 wrapper.

Thin wrapper around psycopg2 for schema/table create + drop, DataFrame inserts
(``execute_values``), and query-to-DataFrame reads. This is the one importable
module the whole pipeline loads through.

Ported from the top-level ``db_tools.py`` in E1-S3 (#21): type hints added and
SQL-string construction brought under unit test. Behavior matches the original
with one intentional change — a failed connection now raises
:class:`DBConnectionError` instead of calling ``sys.exit(1)``. Raising a typed
exception is both testable and friendlier inside the notebook (a clear
traceback rather than a killed kernel).

Original references:
- https://medium.com/analytics-vidhya/part-4-pandas-dataframe-to-postgresql-using-python-8ffdb0323c09
- https://github.com/Muhd-Shahid/Learn-Python-Data-Access/tree/main/PostgreSQL
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from typing import Any

import numpy as np
import pandas as pd
import psycopg2 as pg
from psycopg2.extras import execute_values


def _df_to_sql_rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    """Convert a DataFrame to native-Python row tuples for :func:`execute_values`.

    ``DataFrame.values`` is unsafe to hand psycopg2 directly: its scalars are numpy
    types (``numpy.int64``, ``numpy.bool_``) that psycopg2 cannot adapt, and its
    missing values are ``NaN`` floats that Postgres receives as a literal ``NaN``
    rather than SQL ``NULL`` — breaking NOT NULL / FK / typed columns. (The frames'
    text columns are pandas ``StringDtype`` whose NA is ``NaN``, so an upstream
    NaN->None pass does not survive into ``.values``.) This normalizes both at the
    write boundary: any null-like value (``None``/``NaN``/``NA``/``NaT``) becomes
    ``None``, and any numpy scalar is unboxed to its Python equivalent.
    """
    return [
        tuple(
            None if pd.isna(v) else v.item() if isinstance(v, np.generic) else v
            for v in row
        )
        for row in df.itertuples(index=False, name=None)
    ]


class DBConnectionError(RuntimeError):
    """Raised when :class:`DBC` cannot connect to the configured database.

    The original ``db_tools.DBC`` printed the error and called ``sys.exit(1)``.
    Raising a typed exception instead lets callers and tests handle the failure
    without terminating the process.
    """


class DBC:
    """Connect to a Postgres database and run schema/table/DML commands.

    ``db_config`` is passed straight through to :func:`psycopg2.connect`
    (e.g. ``host``, ``port``, ``dbname``, ``user``, ``password``). The
    ``connect`` callable can be overridden to substitute the connection factory
    — the unit tests use this to inject a fake connection and avoid a live
    database.
    """

    def __init__(
        self,
        db_config: dict[str, Any],
        *,
        connect: Callable[..., Any] = pg.connect,
    ) -> None:
        self.config = db_config
        # Set to True only for the duration of a ``transaction()`` block, so the write
        # chokepoints (``_execute``) know to skip their own per-statement commit and let
        # the context manager own the single commit/rollback. Single-level by design:
        # ``transaction()`` raises rather than nest (see its docstring).
        self._in_txn = False
        try:
            self.conn = connect(**db_config)
        except pg.DatabaseError as e:
            raise DBConnectionError(f"Unable to connect to database:\n{e}") from e

    def close_connection(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[DBC]:
        """Run the wrapped writes as one all-or-nothing transaction.

        Every DDL/DML method funnels through :meth:`_execute`, which normally wraps each
        statement in ``with self.conn`` so psycopg2 commits it on success (or rolls it
        back on error) — one statement, one commit. Inside this block that per-statement
        commit is suppressed: the writes run on a bare cursor and accumulate, and this
        manager issues a **single** ``commit()`` on clean exit or ``rollback()`` on any
        exception. So a multi-table load (the D024 roster + fact pair in
        :func:`usvote.ucsb.pipeline.run_ucsb_pipeline`, the EC star-schema's three
        tables) can never be left half-written in the database. Postgres DDL is
        transactional, so a wrapped ``CREATE``/``DROP`` rolls back too — an interrupted
        ``replace`` rebuild leaves the previous warehouse intact rather than
        dropped-and-half-built.

        **Ownership rule (why it is not re-entrant).** The owning *pipeline* holds the
        transaction; a caller layered above it — the #84b warehouse orchestrator that
        sequences ``run_ec_pipeline`` / ``run_mit_pipeline`` / ``run_ucsb_pipeline`` —
        must **not** wrap those calls in a second transaction. A nested open is a bug
        (it would make the outer block silently non-atomic, committing the inner half
        early), so this raises rather than reference-count. Keep network/scrape and
        heavy transforms *outside* the block; wrap only the DB-write phase, so a slow
        fetch never holds a transaction (and its locks) open.

        ``close`` is deliberately not handled here — a loader closing the connection
        mid-block would abort the commit; callers close *after* the ``with`` exits.
        """
        if self._in_txn:
            raise RuntimeError(
                "DBC.transaction() is not re-entrant — a transaction is already "
                "open. The owning pipeline holds it; callers above (e.g. the #84b "
                "warehouse orchestrator) must sequence pipelines without nesting one."
            )
        # A transaction is meaningless under autocommit — psycopg2 would commit each
        # statement independently, so the block would not be atomic. Fail loud. This is
        # forward-looking: DBC never enables autocommit and psycopg2 defaults it off, so
        # no current caller can trip it — it guards a future one (e.g. #84b) from wiring
        # an autocommit connection and getting a silently non-atomic block.
        if getattr(self.conn, "autocommit", False):
            raise RuntimeError(
                "DBC.transaction() requires the connection's autocommit to be off; "
                "under autocommit each statement commits on its own and the block "
                "would not be atomic."
            )
        self._in_txn = True
        try:
            yield self
            self.conn.commit()
        except BaseException:
            # Roll back, but never let a rollback failure mask the original error: a
            # broken connection is a plausible cause of the body exception AND makes
            # rollback() raise, so a bare ``self.conn.rollback()`` here would replace
            # the real traceback with an opaque InterfaceError. Suppress the rollback's
            # own exception and re-raise the original (the bare ``raise`` re-raises it).
            with suppress(Exception):
                self.conn.rollback()
            raise
        finally:
            self._in_txn = False

    def _execute(self, run: Callable[[Any], Any]) -> None:
        """Run ``run(cursor)`` inside or outside a transaction.

        The single write chokepoint both :meth:`execute_query` and
        :meth:`insert_df_into_table` funnel through, so :meth:`transaction` can toggle
        the commit behavior in one place. Outside a transaction (the default) it wraps
        the statement in ``with self.conn`` — psycopg2 commits on success, rolls back on
        error, one statement at a time (the original behavior). Inside a
        ``transaction()`` block it runs on a bare cursor and does **not** commit; the
        context manager owns the one commit/rollback for the whole block.
        """
        if self._in_txn:
            with self.conn.cursor() as cur:
                run(cur)
        else:
            with self.conn as conn, conn.cursor() as cur:
                run(cur)

    def execute_query(self, query: str, close: bool = False) -> None:
        self._execute(lambda cur: cur.execute(query))
        if close:
            self.close_connection()

    def delete_schema(
        self, schema: str, option: str = "Restrict", close: bool = False
    ) -> None:
        """Delete schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/16/sql-dropschema.html
        """
        self.execute_query(f"DROP SCHEMA IF EXISTS {schema} {option}", close=close)

    def create_schema(
        self, schema: str, replace: bool = False, close: bool = False
    ) -> None:
        """Create schema.
        https://www.postgresql.org/docs/16/sql-createschema.html
        """
        if replace:
            self.delete_schema(schema, option="Cascade")
        self.execute_query(f"CREATE SCHEMA IF NOT EXISTS {schema}", close=close)

    def delete_table(
        self,
        schema: str,
        table_name: str,
        option: str = "Restrict",
        close: bool = False,
    ) -> None:
        """Delete table in schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/16/sql-droptable.html
        """
        self.execute_query(
            f"DROP TABLE IF EXISTS {schema}.{table_name} {option}", close=close
        )

    def create_table(
        self,
        schema: str,
        table_name: str,
        table_columns: Iterable[tuple[str, ...]],
        replace: bool = False,
        close: bool = False,
    ) -> None:
        """Create table. ``table_columns`` is a list of tuples, each at least two
        strings — the column name and its type — optionally followed by one or more
        constraint strings (e.g. ``("state", "varchar", "primary key")`` or a FK
        ``("candidate_id", "smallint", "not null", "REFERENCES dwh.candidate")``);
        every element is space-joined into the column clause.
        https://www.postgresql.org/docs/16/sql-createtable.html
        """
        column_str = ", ".join(map(" ".join, table_columns))
        if replace:
            self.delete_table(schema, table_name, option="Cascade")
        self.execute_query(
            f"CREATE TABLE IF NOT EXISTS {schema}.{table_name} ({column_str})",
            close=close,
        )

    def create_view(
        self,
        schema: str,
        view_name: str,
        select_sql: str,
        replace: bool = False,
        close: bool = False,
    ) -> None:
        """Create a view named ``schema.view_name`` over ``select_sql``.

        ``replace=True`` emits ``CREATE OR REPLACE VIEW`` — non-destructive (unlike the
        table/schema ``replace`` paths, which ``DROP ... CASCADE``): it swaps the query
        in place without dropping the view, so dependent views (e.g. a later EC<->PV
        join, #69) are left intact. This is why the PV view loader defaults
        ``replace=True`` while the table loaders default ``replace=False``. ``replace``
        does require the new query to generate the same columns (same names, order, and
        types) as the existing view, though it may append columns at the end; a genuine
        column-set change is a migration that drops the view explicitly.
        https://www.postgresql.org/docs/16/sql-createview.html
        """
        verb = "CREATE OR REPLACE VIEW" if replace else "CREATE VIEW"
        self.execute_query(
            f"{verb} {schema}.{view_name} AS {select_sql}", close=close
        )

    def copy_csv_to_table(
        self,
        schema: str,
        table_name: str,
        csv_path: str,
        header: bool = False,
        close: bool = False,
    ) -> None:
        """COPY a CSV file on the server into a table. ``header=True`` when the
        file's first line is a column header row (appends ``CSV HEADER``).

        Note: the original ``db_tools`` version was broken — its header logic was
        inverted and left ``header_str`` unbound when ``header=True`` (NameError).
        This port fixes it (the method was unused, so there was no working
        behavior to preserve); flagged in the #21 PR.
        """
        header_str = " CSV HEADER" if header else ""
        self.execute_query(
            f"COPY {schema}.{table_name} FROM '{csv_path}' DELIMITER ','{header_str}",
            close=close,
        )

    def insert_df_into_table(
        self,
        schema: str,
        table_name: str,
        df: pd.DataFrame,
        close: bool = False,
        **kwargs: Any,
    ) -> None:
        if len(df) > 0:
            columns = ",".join(list(df.columns))
            insert_stmt = f"INSERT INTO {schema}.{table_name} ({columns}) VALUES %s"
            self._execute(
                lambda cur: execute_values(
                    cur, insert_stmt, _df_to_sql_rows(df), **kwargs
                )
            )
        else:
            print("Input dataframe, df, is empty: No data was written to the database!")
        if close:
            self.close_connection()

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        """Execute ``query`` via :func:`pandas.read_sql` and return a DataFrame.

        Note: pandas warns when handed a raw psycopg2 connection rather than a
        SQLAlchemy connectable. Preserved from the original; a fix is out of
        scope for this port (#21).
        """
        df = pd.read_sql(query, self.conn)
        if close:
            self.close_connection()
        return df
