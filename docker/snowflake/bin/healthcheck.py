#!/usr/bin/env python3
"""Container healthcheck.

Logs in over the Snowflake HTTP protocol and runs a trivial query. The socket
is only bound after the init SQL has been applied, so a passing healthcheck
also means the schema exists.
"""

from __future__ import annotations

import os
import sys

import snowflake.connector


def main() -> int:
    try:
        conn = snowflake.connector.connect(
            user="fake",
            password="snow",
            account="fakesnow",
            host="127.0.0.1",
            port=int(os.environ.get("FAKESNOW_PORT", "8085")),
            protocol="http",
            login_timeout=5,
            network_timeout=5,
            session_parameters={"CLIENT_OUT_OF_BAND_TELEMETRY_ENABLED": False},
        )
    except Exception as e:  # noqa: BLE001
        print(f"unhealthy: cannot connect: {e}", file=sys.stderr)
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            if cur.fetchone() != (1,):
                print("unhealthy: unexpected query result", file=sys.stderr)
                return 1
    except Exception as e:  # noqa: BLE001
        print(f"unhealthy: query failed: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
