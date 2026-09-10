#!/usr/bin/env python3
"""Web SQL console for the local Snowflake service.

A deliberately small UI: an object browser, an editor, and result tables. It
uses snowflake-connector-python, the one client fakesnow implements the protocol
for, so anything that works here works the same way from application code.

Environment variables:
    SNOWFLAKE_HOST          host of the Snowflake service (default snowflake)
    SNOWFLAKE_PORT          port of the Snowflake service (default 8085)
    SNOWFLAKE_DATABASE      database the console session connects into
    SNOWFLAKE_SCHEMA        schema the console session connects into
    SNOWFLAKE_UI_HOST       bind address (default 0.0.0.0)
    SNOWFLAKE_UI_PORT       bind port (default 8086)
    SNOWFLAKE_UI_MAX_ROWS   rows returned per statement (default 1000)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

import db

APP_DIR = Path(__file__).parent
HOST = os.environ.get("SNOWFLAKE_UI_HOST", "0.0.0.0")
PORT = int(os.environ.get("SNOWFLAKE_UI_PORT", "8086"))
LOG_LEVEL = os.environ.get("SNOWFLAKE_UI_LOG_LEVEL", "info")

templates = Jinja2Templates(directory=APP_DIR / "templates")
log = logging.getLogger("snowflake-ui")


async def index(request: Request) -> object:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "endpoint": f"{db.HOST}:{db.PORT}",
            "database": db.DATABASE,
            "schema": db.SCHEMA,
            "max_rows": db.MAX_ROWS,
        },
    )


async def query(request: Request) -> JSONResponse:
    body = await request.json()
    sql = (body.get("sql") or "").strip()
    if not sql:
        return JSONResponse({"results": [], "error": "nothing to run"}, status_code=400)

    return JSONResponse(await run_in_threadpool(db.run, sql))


async def objects(request: Request) -> JSONResponse:
    try:
        return JSONResponse({"databases": await run_in_threadpool(db.objects)})
    except Exception as e:  # noqa: BLE001
        log.warning("object browser failed: %s", e)
        return JSONResponse({"databases": [], "error": str(e)})


async def healthz(request: Request) -> PlainTextResponse:
    ok = await run_in_threadpool(db.ping)
    return PlainTextResponse("ok" if ok else "unhealthy", status_code=200 if ok else 503)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/query", query, methods=["POST"]),
        Route("/api/objects", objects),
        Route("/healthz", healthz),
        Mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static"),
    ]
)


def main() -> int:
    logging.basicConfig(
        level={"trace": "DEBUG"}.get(LOG_LEVEL.lower(), LOG_LEVEL.upper()),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
