"""Connection handling for the Snowflake SQL console.

One long-lived connection, serialised with a lock, so session state set from the
console (`USE DATABASE`, session parameters) survives between requests the way
it would in a real SQL client. The connection is re-established on failure.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any

import snowflake.connector
from snowflake.connector.util_text import split_statements

HOST = os.environ.get("SNOWFLAKE_HOST", "snowflake")
PORT = int(os.environ.get("SNOWFLAKE_PORT", "8085"))
DATABASE = os.environ.get("SNOWFLAKE_DATABASE", "PROD")
SCHEMA = os.environ.get("SNOWFLAKE_SCHEMA", "DS_MODEL")
MAX_ROWS = int(os.environ.get("SNOWFLAKE_UI_MAX_ROWS", "1000"))

log = logging.getLogger("snowflake-ui")

_lock = threading.Lock()
_conn: snowflake.connector.SnowflakeConnection | None = None


def _connect() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        user="fake",
        password="snow",
        account="fakesnow",
        host=HOST,
        port=PORT,
        protocol="http",
        # fakesnow resolves DESCRIBE/SHOW and information_schema against the
        # session's current database, so always connect into one.
        database=DATABASE,
        schema=SCHEMA,
        login_timeout=10,
        network_timeout=60,
        session_parameters={"CLIENT_OUT_OF_BAND_TELEMETRY_ENABLED": False},
    )


def _connection() -> snowflake.connector.SnowflakeConnection:
    global _conn
    if _conn is None or _conn.is_closed():
        _conn = _connect()
    return _conn


def _reset() -> None:
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:  # noqa: BLE001 - already broken, nothing to salvage
            pass
    _conn = None


def encode(value: Any) -> Any:
    """Make a cell JSON-safe without losing how it would read in SQL output."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)


def statements(sql: str) -> list[str]:
    """Split a script the way the Snowflake client does, comments included."""
    parsed = split_statements(io.StringIO(sql), remove_comments=False)
    return [s.strip() for s, _ in parsed if s and s.strip()]


def run(sql: str) -> dict[str, Any]:
    """Execute every statement in `sql`, stopping at the first failure.

    Returns the results collected so far alongside the error, so a script that
    fails halfway still shows what succeeded.
    """
    results: list[dict[str, Any]] = []

    with _lock:
        for statement in statements(sql):
            try:
                conn = _connection()
                cur = conn.cursor()
            except Exception as e:  # noqa: BLE001
                _reset()
                return {"results": results, "error": f"cannot reach the Snowflake service: {e}"}

            started = time.monotonic()
            try:
                cur.execute(statement)
                columns = [c[0] for c in cur.description] if cur.description else []
                rows = [[encode(v) for v in row] for row in cur.fetchmany(MAX_ROWS)] if columns else []
                truncated = bool(columns) and cur.fetchone() is not None
                results.append(
                    {
                        "sql": statement,
                        "columns": columns,
                        "rows": rows,
                        "rowCount": cur.rowcount if cur.rowcount is not None else len(rows),
                        "truncated": truncated,
                        "elapsedMs": round((time.monotonic() - started) * 1000, 1),
                    }
                )
            except snowflake.connector.errors.ProgrammingError as e:
                return {"results": results, "error": f"{e.msg}", "failedSql": statement}
            except Exception as e:  # noqa: BLE001 - unsupported SQL surfaces as a 500 from fakesnow
                _reset()
                return {"results": results, "error": str(e), "failedSql": statement}
            finally:
                cur.close()

    return {"results": results, "error": None}


def _query(sql: str) -> list[tuple]:
    with _lock:
        cur = _connection().cursor()
        try:
            cur.execute(sql)
            return cur.fetchall()
        finally:
            cur.close()


def objects() -> list[dict[str, Any]]:
    """Database -> schema -> table -> column tree for the sidebar.

    Built from SHOW DATABASES plus each database's INFORMATION_SCHEMA, because
    fakesnow does not implement the cross-database INFORMATION_SCHEMA.SCHEMATA.
    """
    tree: list[dict[str, Any]] = []

    for row in _query("SHOW DATABASES"):
        database = row[1]
        columns: dict[tuple[str, str], list[dict[str, str]]] = {}
        try:
            for schema, table, column, data_type, nullable in _query(
                f"""SELECT table_schema, table_name, column_name, data_type, is_nullable
                    FROM {database}.INFORMATION_SCHEMA.COLUMNS
                    ORDER BY table_schema, table_name, ordinal_position"""
            ):
                columns.setdefault((schema, table), []).append(
                    {"name": column, "type": data_type, "nullable": nullable == "YES"}
                )
        except Exception as e:  # noqa: BLE001 - keep the rest of the tree usable
            log.warning("cannot introspect %s: %s", database, e)

        schemas: dict[str, list[dict[str, Any]]] = {}
        for (schema, table), cols in columns.items():
            schemas.setdefault(schema, []).append({"name": table, "columns": cols})

        tree.append(
            {
                "name": database,
                "schemas": [
                    {"name": name, "tables": sorted(tables, key=lambda t: t["name"])}
                    for name, tables in sorted(schemas.items())
                ],
            }
        )

    return tree


def ping() -> bool:
    try:
        return _query("SELECT 1") == [(1,)]
    except Exception:  # noqa: BLE001
        _reset()
        return False
