#!/usr/bin/env python3
"""Entrypoint for the local Snowflake-compatible service.

Serves the Snowflake HTTP wire protocol via `fakesnow` (backed by DuckDB) and
applies the SQL files in ``FAKESNOW_INIT_DIR`` from the ASGI lifespan startup
hook. Uvicorn runs that hook before it binds the socket, so any client that can
connect is guaranteed to see the initialised schema.

Environment variables:
    FAKESNOW_HOST       bind address (default 0.0.0.0, so other containers can reach it)
    FAKESNOW_PORT       bind port (default 8085)
    FAKESNOW_INIT_DIR   directory of *.sql files applied in lexical order
    FAKESNOW_DB_PATH    directory for DuckDB files; unset means in-memory only
    FAKESNOW_LOG_LEVEL  uvicorn/app log level (default info)
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from starlette.applications import Starlette

import fakesnow.server
from fakesnow import info_schema, macros
from fakesnow.instance import FakeSnow

HOST = os.environ.get("FAKESNOW_HOST", "0.0.0.0")
PORT = int(os.environ.get("FAKESNOW_PORT", "8085"))
INIT_DIR = Path(os.environ.get("FAKESNOW_INIT_DIR", "/opt/snowflake/init"))
DB_PATH = os.environ.get("FAKESNOW_DB_PATH") or None
LOG_LEVEL = os.environ.get("FAKESNOW_LOG_LEVEL", "info")

log = logging.getLogger("snowflake-local")


def patch_create_database_macros() -> None:
    """Create fakesnow's helper macros for databases made with `CREATE DATABASE`.

    fakesnow only installs them when a database is created implicitly by a
    connection, so DDL it rewrites to a macro call -- e.g. a TIMESTAMP_NTZ
    column default becomes `_fs_to_timestamp(...)` -- otherwise fails with
    "Scalar Function with name _fs_to_timestamp does not exist". Hooking the
    per-database DDL fakesnow already runs on CREATE DATABASE covers our init
    scripts and any client that creates a database at runtime.
    """
    original = info_schema.per_db_creation_sql

    def with_macros(catalog: str) -> str:
        return original(catalog) + macros.creation_sql(catalog)

    info_schema.per_db_creation_sql = with_macros


def init_sql_files() -> list[Path]:
    if not INIT_DIR.is_dir():
        log.warning("init dir %s not found, nothing to apply", INIT_DIR)
        return []
    return sorted(INIT_DIR.glob("*.sql"))


def attach_persisted_databases() -> None:
    """ATTACH the DuckDB files already present in DB_PATH.

    fakesnow only attaches a database when something references it by name, so
    without this a restart would hide persisted data from clients that connect
    without a database.
    """
    assert DB_PATH
    for db_file in sorted(Path(DB_PATH).glob("*.db")):
        fakesnow.server.shared_fs.connect(database=db_file.stem).close()
        log.info("attached persisted database %s", db_file.stem)


def apply_init_sql() -> None:
    """Run every init script against the shared in-process database.

    Skipped when persistence is on and the volume was already initialised,
    otherwise a `create or replace table` in an init script would wipe the
    persisted rows on every restart.
    """
    marker = Path(DB_PATH) / ".initialised" if DB_PATH else None
    if marker and marker.exists():
        log.info("reusing persisted databases, init SQL skipped (delete %s to re-apply)", marker)
        attach_persisted_databases()
        return

    files = init_sql_files()
    if not files:
        return

    # Connect in-process rather than over HTTP: this runs during lifespan
    # startup, before uvicorn binds the socket.
    conn = fakesnow.server.shared_fs.connect()
    try:
        for path in files:
            statements = conn.execute_string(path.read_text())
            log.info("applied %s (%d statement(s))", path.name, len(list(statements)))
    finally:
        conn.close()

    if marker:
        marker.touch()
    log.info("applied %d init script(s)", len(files))


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    apply_init_sql()
    yield


def build_server() -> uvicorn.Server:
    patch_create_database_macros()

    if DB_PATH:
        Path(DB_PATH).mkdir(parents=True, exist_ok=True)
        # Replace the server's default in-memory instance so databases are
        # written to disk and survive a container restart.
        fakesnow.server.shared_fs = FakeSnow(db_path=DB_PATH)
        log.info("databases persisted under %s", DB_PATH)
    else:
        log.info("databases are in-memory (set FAKESNOW_DB_PATH to persist)")

    # Rebuild the app off fakesnow's routes so we can attach our own lifespan.
    app = Starlette(debug=True, routes=fakesnow.server.routes, lifespan=lifespan)
    return uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level=LOG_LEVEL))


def main() -> int:
    logging.basicConfig(
        # uvicorn accepts "trace", the stdlib does not
        level={"trace": "DEBUG"}.get(LOG_LEVEL.lower(), LOG_LEVEL.upper()),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    server = build_server()
    server.run()
    return 0 if server.started else 1


if __name__ == "__main__":
    sys.exit(main())
