# Snowflake console

Small web SQL client for the local Snowflake service: an object browser, an
editor, and result tables.

Open http://localhost:8086 (`SNOWFLAKE_UI_PORT`).

## Why a purpose-built UI

Off-the-shelf tools (CloudBeaver, DBeaver, SQLPad) reach Snowflake through the
JDBC or Node drivers, which exercise far more of the REST API than fakesnow
implements — see the caveats in [../snowflake/README.md](../snowflake/README.md).
This console drives `snowflake-connector-python`, pinned to the same version the
Snowflake service resolves, so it can only do what application code can also do.
No feature works here and then fails in a Python producer.

## What it does

- **Object browser** — databases, schemas, tables and columns, built from
  `SHOW DATABASES` plus each database's `INFORMATION_SCHEMA.COLUMNS`. Not-null
  columns are marked with `*`. `SELECT *` on a table fills the editor and runs.
- **Editor** — `⌘/Ctrl + Enter` to run. Multiple statements separated by `;`
  run in order, comments included, and each gets its own result block with row
  count and timing.
- **Errors** — a failing statement stops the script but keeps the results of
  everything that already succeeded, and shows the statement that failed
  alongside the Snowflake error text.
- **Session state persists.** The console holds one connection, so `USE SCHEMA
  PROD.DS_MODEL` in one query applies to the next, the way a real SQL client
  behaves.
- Results are capped at `SNOWFLAKE_UI_MAX_ROWS` per statement, and a
  `truncated` badge appears when there was more.

No auth, and arbitrary SQL by design — keep it bound to localhost.

## Environment variables

| Variable                | Default    | Purpose |
| ----------------------- | ---------- | ------- |
| `SNOWFLAKE_UI_PORT`     | `8086`     | Host port for the UI. |
| `SNOWFLAKE_UI_DATABASE` | `PROD`     | Database the console session connects into. |
| `SNOWFLAKE_UI_SCHEMA`   | `DS_MODEL` | Schema the console session connects into. |
| `SNOWFLAKE_UI_MAX_ROWS` | `1000`     | Rows returned per statement. |
| `SNOWFLAKE_UI_LOG_LEVEL`| `info`     | `critical`…`trace`. |

Always connect into a database: fakesnow resolves `DESCRIBE`, `SHOW` and
`information_schema` against the session's current database and fails without
one, even for fully qualified names.

## HTTP endpoints

```bash
curl -s http://localhost:8086/healthz        # ok
curl -s http://localhost:8086/api/objects    # object tree

curl -s -X POST http://localhost:8086/api/query \
  -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT 1"}'
```

## Layout

```
Dockerfile
requirements.txt          pinned to the snowflake service's versions
app/
  main.py                 routes
  db.py                   connection, statement splitting, introspection
  templates/index.html
  static/styles.css
  static/app.js
```

The frontend is plain HTML, CSS and JavaScript — no build step, so editing
`static/` and reloading is the whole development loop. Python changes need
`docker compose up -d --build snowflake-ui`.
