# NiFi — Openflow simulation

Apache NiFi running the Snowflake → Kafka CDC pipeline locally.

UI: https://localhost:8443/nifi (self-signed certificate, so expect a browser
warning). Log in with `admin` / `openflow-poc-local` (`NIFI_USERNAME`,
`NIFI_PASSWORD`).

> ### In production, use the Openflow connector
>
> This service **simulates** the pipeline. It is not the Snowflake connector.
> In production the source side is the **Openflow Connector for Snowflake to
> Kafka**, imported from the Snowflake connector gallery:
>
> - Setup: <https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/setup>
> - Overview: <https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/about>
>
> Openflow runtimes *are* managed Apache NiFi, so the engine here is the real
> one. What cannot be reproduced locally is the connector itself (a proprietary
> flow definition from the gallery, which needs an Openflow-enabled Snowflake
> account) and the Snowflake **Stream** it consumes. Everything downstream of
> the Kafka topic is unaffected by the swap.

## What it does

```
Snowflake (fakesnow)                  NiFi                         Redpanda
─────────────────────                 ────                         ────────
..._CDC view          ──JDBC──▶  Consume Snowflake CDC
(stream-shaped rows)              QueryDatabaseTableRecord
                                          │
                                          ▼
                                  Publish CDC to Kafka   ──▶  snowflake.ds_model.
                                  PublishKafka                mod_rod_spm_setpoint_
                                                              recommendation
```

The flow is built by `bin/build_flow.py` through the NiFi REST API on every
`docker compose up`, so the pipeline is version-controlled code rather than
clicked-together canvas state, and identical on every machine. The script is
idempotent — if the process group exists it does nothing.

## The message contract

This is the part that is reproducible exactly, and the part downstream code
should be written against. One Kafka message per CDC row, JSON, **no attached
schema** (matching the connector), keyed by the column named in
`Kafka Message Key Field`:

```json
{
  "TENANT_ID": "acme",
  "WELL_ID": "well-100",
  "EFFECTIVE_DATE": "2026-09-08 01:00:00.000",
  "RECOMMENDED_MIN_SPM_SETPOINT": 3.1,
  "OPERATING_CLASSIFICATION": "NORMAL",
  "CREATED_ON": "2026-09-09 01:13:30.133",
  "UPDATED_ON": "2026-09-09 01:13:30.133",
  "METADATA_ROW_ID": "3e9059a43554d92aa25d758c076788cd",
  "METADATA_ISUPDATE": false,
  "METADATA_ACTION": "INSERT"
}
```

All 24 source columns are present (trimmed above), plus the three metadata
columns. The connector renames the stream's `METADATA$ROW_ID`,
`METADATA$ISUPDATE` and `METADATA$ACTION` to these underscore forms in its JSON
payload, which is what the local view emits directly.

One thing to confirm against the real connector before relying on it: the exact
**timestamp rendering**. This flow emits `yyyy-MM-dd HH:mm:ss.SSS`; without an
explicit format NiFi would publish epoch milliseconds instead, so the format is
a local choice rather than something observed from Openflow.

## Try it

```bash
# insert into Snowflake
docker compose exec snowflake python /opt/snowflake/bin/query.py \
  "INSERT INTO PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION
     (TENANT_ID, WELL_ID, CONTROL_SYSTEM_ID, CONTEXT, EFFECTIVE_DATE,
      RECOMMENDED_MIN_SPM_SETPOINT, MODEL_VERSION)
   VALUES ('acme','well-100','cs-1','ROD','2026-09-08 01:00:00', 3.1, 'v1.2.3')"

# within one poll interval (10s by default) it appears in Kafka
docker compose exec redpanda rpk topic consume \
  snowflake.ds_model.mod_rod_spm_setpoint_recommendation -o start -n 1
```

Or watch it land in kafka-ui at http://localhost:8090.

## Parameters

The flow uses three NiFi parameter contexts named after the connector's own
parameter groups — **Kafka Sink Source Parameters**, **Kafka Sink Destination
Parameters** and **Kafka Sink Ingestion Parameters** — inherited into one
context bound to the process group. Opening them in the NiFi UI shows roughly
the same fields you would fill in for the real connector.

Values come from the environment (see `compose.yaml`). A few are local-only,
marked as such in the UI, because Openflow derives or replaces them:

| Parameter | Local value | In Openflow |
| --- | --- | --- |
| `Snowflake FQN Stream Name` | the `..._CDC` view | a real stream FQN |
| `Change Watermark Column` | `UPDATED_ON` | not needed; the stream advances itself |
| `Snowflake JDBC URL` | `jdbc:snowflake://snowflake:8085/?ssl=off` | derived from the account identifier |
| `Authentication Strategy` | password | `KEY_PAIR` or `SNOWFLAKE_MANAGED` |
| `Snowflake Warehouse` / `Snowflake Role` | unused | required |

To change a parameter, edit `compose.yaml` and rebuild the flow:

```bash
docker compose up -d --force-recreate nifi   # conf is restored from the image
docker compose up -d nifi-flow               # rebuilds the flow
```

## What differs from Openflow

Say this part out loud in any demo — it is where the local model and production
genuinely diverge.

| | Local | Openflow |
| --- | --- | --- |
| Capture | polls `WHERE UPDATED_ON > watermark` | consumes a Snowflake Stream |
| Deletes | never observed — every row reads as `INSERT` | stream emits `DELETE` too |
| `METADATA_ISUPDATE` | derived from `UPDATED_ON <> CREATED_ON` | set by the stream |
| `METADATA_ROW_ID` | `MD5(TENANT_ID, WELL_ID, EFFECTIVE_DATE)` | stream-internal row identity |
| Offset | NiFi processor state; lost when the flow is rebuilt, so rows replay | consuming the stream advances it, and it cannot be shared by two readers |
| Auth | username/password over plain HTTP | key-pair JWT, secrets manager |
| Operations | this container | Openflow runtime, parameter providers, RBAC, Snowsight |

Also worth raising with Snowflake, straight from the connector docs:

- **BYOC deployments are limited to AWS commercial regions.** Confirm your
  account's cloud and region before committing to the architecture.
- **One connector handles one stream to one topic.** N tables means N connector
  instances to operate.
- **No schema is attached and schema evolution is unsupported**, so the Schema
  Registry in this stack goes unused by the connector and consumers must absorb
  drift themselves.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `NIFI_PORT` | `8443` | Host port for the NiFi UI. |
| `NIFI_USERNAME` / `NIFI_PASSWORD` | `admin` / `openflow-poc-local` | Single-user login. NiFi requires ≥12 characters. |
| `NIFI_HEAP_INIT` / `NIFI_HEAP_MAX` | `512m` / `2g` | JVM heap. |
| `SNOWFLAKE_STREAM_FQN` | the `..._CDC` view | Source object the flow reads. |
| `CHANGE_WATERMARK_COLUMN` | `UPDATED_ON` | Incrementing column used as the local offset. |
| `KAFKA_CDC_TOPIC` | `snowflake.ds_model.mod_rod_spm_setpoint_recommendation` | Destination topic. |
| `KAFKA_MESSAGE_KEY_FIELD` | `WELL_ID` | Column used as the Kafka message key. |
| `NIFI_POLL_INTERVAL` | `10 sec` | How often the source is polled. |

## Things that bite, and why they are configured this way

Each of these was hit while building the flow; they are all encoded in the
Dockerfile or `build_flow.py`.

- **`--add-opens=java.base/java.nio=ALL-UNNAMED`** is appended to
  `bootstrap.conf`. The Snowflake driver parses Arrow result sets, which fails
  on JDK 17+ with `ExceptionInInitializerError` in Arrow's
  `UnsafeAllocationManager` without it.
- **The DBCP pool sets `Validation Query` to `SELECT 1`.** By default DBCP
  validates connections with `Connection.isValid()`, which the Snowflake driver
  answers from a `/session/heartbeat` call that fakesnow does not implement. The
  pool then fails with `Cannot create PoolableConnectionFactory (isValid()
  returned false)`.
- **`hostname: nifi`** is set on the container. NiFi generates a self-signed
  certificate containing the container hostname; without this, TLS from other
  containers fails Jetty's SNI check with `Invalid SNI` before the request is
  seen.
- **`NIFI_WEB_PROXY_HOST` lists `nifi:8443` as well as `localhost:8443`.** NiFi
  rejects unrecognised `Host` headers with a bare `400`.
- **`NIFI_WEB_HTTPS_HOST` is `0.0.0.0`.** It otherwise binds only the container
  hostname, leaving the healthcheck's `localhost` unreachable.
- **`conf/` is restored from the image on every boot** by `bin/entrypoint.sh`.
  The base image declares it a `VOLUME`, and Compose preserves anonymous volumes
  across container recreation — so a stale `conf` would silently outlive an
  image rebuild, keeping old JVM arguments and an old certificate.
- **Two JSON writers.** The query side writes an array per FlowFile; each Kafka
  message must be a single object. Sharing one writer leaves the array separator
  at the start of every message after the first.
- **`Use Avro Logical Types` is `true`.** Otherwise `TIMESTAMP` columns arrive as
  plain longs, the writer's timestamp format never applies, and every timestamp
  is published as epoch milliseconds.
