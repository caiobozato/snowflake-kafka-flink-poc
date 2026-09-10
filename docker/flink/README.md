# Flink

Consumes the Snowflake CDC topic, transforms it, and publishes the result back
to Kafka.

Web UI: **http://localhost:8081** (`FLINK_UI_PORT`).

```
snowflake.ds_model.                                          ambyio.swo-poc-control-system.
mod_rod_spm_setpoint_  ──▶  snowflake_cdc ─▶ transform ─▶    lufkin.speedRangeRecommendation
recommendation                (Flink SQL job)                Updated
```

## Where to write your transformations

**`sql/20_transform.sql`.** Everything else is plumbing.

The three files in `sql/` are concatenated in lexical order and submitted as one
script — table DDL first, then the `INSERT` statements that become the running
job:

| File | Purpose |
| --- | --- |
| `00_source_snowflake_cdc.sql` | source table over the CDC topic; all 24 Snowflake columns plus the three `METADATA_*` fields |
| `10_sink_speed_range_recommendation.sql` | sink table over the output topic |
| `20_transform.sql` | **the `INSERT ... SELECT` — yours to edit** |

The example transform shapes the CDC stream into the
`speedRangeRecommendationUpdated` event. Two of its mappings are placeholders,
because the source table has no matching columns: the integer `classification`
code, and `status` — which is where validation rules belong.

Replace it with anything: joins, windows,
aggregations, several `INSERT` statements, more tables. Add files with a higher
numeric prefix and they are picked up automatically.

Any new output column has to be added to the sink schema in
`10_sink_speed_range_recommendation.sql` as well — Flink validates the `INSERT` against it.

## Redeploying after an edit

```bash
docker compose up -d --force-recreate flink-sql
```

The submitter cancels running jobs before submitting, so this is a clean
redeploy rather than a second job competing for the same source and sink. This
cluster is assumed to own exactly this pipeline; set `REPLACE_RUNNING_JOBS=false`
to leave existing jobs alone.

`docker logs poc-flink-sql` shows the submitted statements and the new job id.
Failures surface there too — a bad `SELECT` is reported by the SQL client, not
by the cluster.

## Try it

```bash
docker compose exec snowflake python /opt/snowflake/bin/query.py \
  "INSERT INTO PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION
     (TENANT_ID, WELL_ID, CONTROL_SYSTEM_ID, CONTEXT, EFFECTIVE_DATE,
      RECOMMENDED_MIN_SPM_SETPOINT, RECOMMENDED_MAX_SPM_SETPOINT, MODEL_VERSION)
   VALUES ('acme','well-900','cs-1','ROD','2026-09-09 14:00:00', 3.0, 9.5, 'v1.2.3')"

docker compose exec redpanda rpk topic consume \
  ambyio.swo-poc-control-system.lufkin.speedRangeRecommendationUpdated -o -1 -n 1
```

Roughly 10 seconds for NiFi to pick up the row, then Flink is immediate:

```json
{
  "data": {
    "classification": 1,
    "createdOn": "2026-09-09T23:13:17.443Z",
    "max": 5.0,
    "min": 3.6,
    "status": 1,
    "statusName": "Accepted"
  }
}
```

The Kafka message key is the well id, carried outside the value by
`'value.fields-include' = 'EXCEPT_KEY'`, so the payload is exactly the envelope.

Both topics are browsable in kafka-ui at http://localhost:8090.

## Services

| Service | Role |
| --- | --- |
| `flink-jobmanager` | cluster coordinator; serves the Web UI on 8081 |
| `flink-taskmanager` | runs the job; `FLINK_TASK_SLOTS` slots (default 4) |
| `flink-sql` | one-shot: submits the pipeline, then exits. The job keeps running |

Topics are provisioned by `redpanda-topics` (in `docker/redpanda/compose.yaml`)
before submission. Flink's Kafka source resolves partitions through the
AdminClient, which does **not** auto-create topics, so a job submitted before
the producer has published anything dies with
`UnknownTopicOrPartitionException`. `flink-sql` waits for that provisioner via
`service_completed_successfully`.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `FLINK_UI_PORT` | `8081` | Host port for the Web UI. |
| `FLINK_TASK_SLOTS` | `4` | Task slots on the TaskManager. |
| `KAFKA_CDC_TOPIC` | `snowflake.ds_model.mod_rod_spm_setpoint_recommendation` | Source topic — same variable the NiFi flow publishes to. |
| `FLINK_SINK_TOPIC` | `ambyio.swo-poc-control-system.lufkin.speedRangeRecommendationUpdated` | Output topic. |
| `FLINK_CONSUMER_GROUP` | `flink-setpoint-recommendation` | Kafka consumer group. |
| `FLINK_SCAN_STARTUP_MODE` | `earliest-offset` | Where the source starts. |
| `REPLACE_RUNNING_JOBS` | `true` | Cancel running jobs before submitting. |

## Worth knowing

- **The source replays from the beginning on every submit.**
  `scan.startup.mode` is `earliest-offset`, which makes the demo repeatable but
  means a redeploy reprocesses the whole topic. Switch to `latest-offset`, or to
  `group-offsets` for committed-offset behaviour.
- **No checkpointing is configured**, so there is no exactly-once guarantee and
  no state recovery across restarts. Fine for a POC; not a production posture.
- **A fixed-delay restart strategy** (10 attempts, 10s apart) is set on both the
  JobManager and the submitter. The default is no restart at all, which turns any
  transient Kafka hiccup into a permanently FAILED job. It has to be set in both
  places because the job graph is built client-side.
- **Flink SQL has no variable substitution**, so `bin/submit_sql.sh` replaces the
  `${...}` placeholders in the `.sql` files before submitting. Any new
  placeholder must be added to the `SUBSTITUTIONS` list in that script, which
  fails loudly if one is left unresolved.
- **`CONTEXT` is quoted** in the source DDL because it is a reserved word in
  Flink SQL.
- **Timestamps** are read with `'json.timestamp-format.standard' = 'SQL'`,
  matching the `yyyy-MM-dd HH:mm:ss.SSS` the CDC flow emits, and written with
  `ISO-8601` to produce `2026-09-09T23:13:17.443Z`. If the upstream format
  changes, parsing fails here first.
- **`table.local-time-zone` is pinned to UTC** in the source DDL. Snowflake
  already stores these columns as UTC, so without it the cast to
  `TIMESTAMP_LTZ` for `createdOn` would shift by the container's local offset.
- **`min` and `max` are reserved words** in Flink SQL and have to be quoted in
  the sink's `ROW` type.
- **The Kafka connector is versioned against Flink** and ships separately:
  connector `5.0.0-2.2` with Flink `2.2.1`. Flink 2.3 is out but has no matching
  connector release yet, which is why 2.2 is pinned.
- **`flink-sql` runs the submit script as its `command`, not its `entrypoint`.**
  The image's entrypoint applies `FLINK_PROPERTIES` to `config.yaml`; overriding
  it leaves the SQL client with no JobManager address, and the `INSERT` fails
  with `Connection refused` after the DDL has already succeeded.

## Writing to Snowflake from Flink

Not wired up, deliberately. The Snowflake JDBC driver works against the local
service for reads, but two gaps break JDBC writes here — `executeUpdate()` is
rejected by the driver even though the row lands, and `TIMESTAMP` parameter
bindings fail. See the differences section in
[../snowflake/README.md](../snowflake/README.md). Against real Snowflake this is
not a constraint.
