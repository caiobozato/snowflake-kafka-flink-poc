# Local Snowflake service

Snowflake ships no official container image, so this service runs
[fakesnow](https://github.com/tekumara/fakesnow): it serves the same HTTP wire
protocol that `snowflake-connector-python` speaks and executes the SQL on
DuckDB, translating Snowflake dialect on the way through.

Everything in `init/*.sql` is applied during ASGI lifespan startup — that is,
*before* the listening socket is bound — so a successful connection implies the
schema already exists. `docker compose ps` reports `healthy` once a login plus
`SELECT 1` round-trips.

## Connecting

Auth is not checked; any credentials work. What matters is `protocol=http` and
the host/port.

| Parameter  | From the host | From another container |
| ---------- | ------------- | ---------------------- |
| `host`     | `localhost`   | `snowflake`            |
| `port`     | `8085` (`SNOWFLAKE_PORT`) | `8085`     |
| `protocol` | `http`        | `http`                 |
| `account`  | anything, e.g. `fakesnow` | same       |
| `user` / `password` | anything | same          |

```python
import snowflake.connector

conn = snowflake.connector.connect(
    user="fake",
    password="snow",
    account="fakesnow",
    host="localhost",
    port=8085,
    protocol="http",
    database="PROD",
    schema="DS_MODEL",
)
```

Always connect *into* a database and schema. `DESCRIBE`, `SHOW` and
`information_schema` queries are resolved against the session's current
database, and fail without one even when the object is fully qualified.

fakesnow implements the endpoints `snowflake-connector-python` uses. The JDBC
and ODBC drivers exercise more of the REST API than that, so treat them as
unverified here — if a Flink or Kafka Connect sink has to talk to this service,
prove the driver handshake works before building on it. A Python-based producer
is the safe path.

## Helper scripts

For anything interactive, the web console at http://localhost:8086 is usually
easier — see [../snowflake-ui/README.md](../snowflake-ui/README.md). These
scripts are for scripting and for debugging the container itself.

```bash
# ad-hoc SQL (also reads from stdin: ... query.py < file.sql)
docker compose exec snowflake python /opt/snowflake/bin/query.py \
  "SELECT * FROM PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION"

# what the healthcheck runs
docker compose exec snowflake python /opt/snowflake/bin/healthcheck.py
```

## Adding or changing tables

Drop a `.sql` file in `init/`, prefixed with a number that orders it after the
databases and schemas it needs, then rebuild:

```bash
docker compose up -d --build snowflake
```

Files run in lexical order on every boot (in-memory mode), so keep the DDL
re-runnable — `create or replace` or `create ... if not exists`.

## Persistence

In-memory by default: each restart replays `init/` against an empty database.
To keep data in the `snowflake-data` volume instead, set `SNOWFLAKE_DB_PATH` in
`.env`:

```
SNOWFLAKE_DB_PATH=/var/lib/snowflake
```

The first boot applies `init/` and writes a `.initialised` marker into the
volume; later boots re-attach the existing DuckDB files and skip `init/`, so a
`create or replace table` cannot wipe persisted rows. To re-apply the scripts,
delete the marker or the whole volume:

```bash
docker compose down -v
```

## Environment variables

Set these on the service (see `.env.example` for the Compose-level names).

| Variable             | Default              | Purpose |
| -------------------- | -------------------- | ------- |
| `FAKESNOW_HOST`      | `0.0.0.0`            | Bind address. Must stay `0.0.0.0` to be reachable from other containers. |
| `FAKESNOW_PORT`      | `8085`               | Bind port inside the container. |
| `FAKESNOW_INIT_DIR`  | `/opt/snowflake/init`| Directory of `*.sql` applied on boot. |
| `FAKESNOW_DB_PATH`   | unset (in-memory)    | Directory for DuckDB files. |
| `FAKESNOW_LOG_LEVEL` | `info`               | `critical`…`trace`. |

## Differences from real Snowflake

Worth knowing before trusting a result here:

- **Primary keys are enforced.** DuckDB rejects a duplicate
  `(TENANT_ID, WELL_ID, EFFECTIVE_DATE, UPDATED_ON)` with a 500; real Snowflake
  treats primary keys as informational and accepts the row. A sink that relies
  on Snowflake's tolerance of duplicates will fail locally.
- No warehouses, roles, grants, resource monitors, time travel or cloning.
- Snowpipe / Snowpipe Streaming is not implemented, so the Kafka Connect
  Snowflake sink cannot ingest through this service. Use a JDBC-style sink, or
  write via `snowflake-connector-python`.
- `VARCHAR(n)` lengths are not enforced, and `FLOAT`/`NUMBER` precision follows
  DuckDB semantics.
- Unsupported statements return HTTP 500. `FAKESNOW_LOG_LEVEL=debug` shows the
  translated SQL, and the container log carries the underlying DuckDB error.

`serve.py` also patches one fakesnow gap: it installs fakesnow's helper macros
for databases created with `CREATE DATABASE` SQL. Without that, a
`TIMESTAMP_NTZ` column default — which fakesnow rewrites to
`_fs_to_timestamp(...)` — fails to create.
