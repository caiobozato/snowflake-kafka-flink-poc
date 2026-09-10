#!/usr/bin/env python3
"""Ad-hoc SQL client for the local Snowflake service.

There is no snowsql for fakesnow, so this is the quickest way to poke at the
data:

    docker compose exec snowflake python /opt/snowflake/bin/query.py \
        "SELECT * FROM PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION"

Reads the statement(s) from argv, or from stdin when no argument is given.
"""

from __future__ import annotations

import os
import sys

import snowflake.connector


def main(argv: list[str]) -> int:
    sql = " ".join(argv[1:]).strip() or sys.stdin.read().strip()
    if not sql:
        print("usage: query.py <sql> | query.py < file.sql", file=sys.stderr)
        return 2

    conn = snowflake.connector.connect(
        user="fake",
        password="snow",
        account="fakesnow",
        host=os.environ.get("SNOWFLAKE_HOST", "127.0.0.1"),
        port=int(os.environ.get("FAKESNOW_PORT", "8085")),
        protocol="http",
        # fakesnow resolves DESCRIBE/SHOW and information_schema against the
        # session's current database, so always connect into one.
        database=os.environ.get("SNOWFLAKE_DATABASE", "PROD"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "DS_MODEL"),
        # fail fast instead of retrying for the default five minutes
        login_timeout=10,
        network_timeout=60,
        session_parameters={"CLIENT_OUT_OF_BAND_TELEMETRY_ENABLED": False},
    )
    try:
        for cur in conn.execute_string(sql):
            if cur.description:
                print(" | ".join(c[0] for c in cur.description))
                for row in cur:
                    print(" | ".join("NULL" if v is None else str(v) for v in row))
            print(f"-- {cur.rowcount if cur.rowcount is not None else 0} row(s)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
