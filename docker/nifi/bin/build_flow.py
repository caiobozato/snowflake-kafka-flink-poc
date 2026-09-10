#!/usr/bin/env python3
"""Build the Snowflake -> Kafka CDC flow in NiFi through the REST API.

Runs once, after NiFi reports healthy, and is idempotent: if the process group
already exists it does nothing. Keeping the flow as code rather than canvas
state means the pipeline is reviewable in git and identical on every machine.

The shape deliberately mirrors the Openflow "Snowflake to Kafka" connector:
three parameter contexts matching its Source / Destination / Ingestion groups,
a single source object, a single Kafka topic, JSON messages with no attached
schema, and an optional message key column.

    https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/setup

Environment variables:
    NIFI_API_URL, NIFI_USERNAME, NIFI_PASSWORD
    SNOWFLAKE_JDBC_URL, SNOWFLAKE_USERNAME, SNOWFLAKE_PASSWORD
    SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE
    SNOWFLAKE_ACCOUNT_IDENTIFIER, SNOWFLAKE_STREAM_FQN, CHANGE_WATERMARK_COLUMN
    KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC, KAFKA_MESSAGE_KEY_FIELD
    POLL_INTERVAL
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("NIFI_API_URL", "https://nifi:8443/nifi-api")
USERNAME = os.environ.get("NIFI_USERNAME", "admin")
PASSWORD = os.environ.get("NIFI_PASSWORD", "openflow-poc-local")

GROUP_NAME = "Snowflake to Kafka (Openflow simulation)"
DRIVER_JAR = "/opt/nifi/drivers/snowflake-jdbc.jar"
DRIVER_CLASS = "net.snowflake.client.jdbc.SnowflakeDriver"

# Mirrors of the connector's parameters, plus a few marked local-only where the
# simulation needs something Openflow derives or replaces.
PARAMETERS = {
    "Kafka Sink Source Parameters": [
        ("Snowflake Account Identifier", os.environ.get("SNOWFLAKE_ACCOUNT_IDENTIFIER", "fakesnow"), False),
        ("Authentication Strategy", "PASSWORD (local only; KEY_PAIR in Openflow)", False),
        ("Snowflake Database", os.environ.get("SNOWFLAKE_DATABASE", "PROD"), False),
        ("Snowflake Schema", os.environ.get("SNOWFLAKE_SCHEMA", "DS_MODEL"), False),
        ("Snowflake Warehouse", os.environ.get("SNOWFLAKE_WAREHOUSE", "not used locally"), False),
        ("Snowflake Role", os.environ.get("SNOWFLAKE_ROLE", "not used locally"), False),
        ("Snowflake Username", os.environ.get("SNOWFLAKE_USERNAME", "fake"), False),
        ("Snowflake Password", os.environ.get("SNOWFLAKE_PASSWORD", "snow"), True),
        ("Snowflake JDBC URL", os.environ.get("SNOWFLAKE_JDBC_URL", ""), False),
    ],
    "Kafka Sink Destination Parameters": [
        ("Kafka Bootstrap Servers", os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092"), False),
        ("Kafka Security Protocol", os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"), False),
        ("Kafka Topic", os.environ.get("KAFKA_TOPIC", "snowflake.ds_model.mod_rod_spm_setpoint_recommendation"), False),
        ("Kafka Message Key Field", os.environ.get("KAFKA_MESSAGE_KEY_FIELD", "WELL_ID"), False),
    ],
    "Kafka Sink Ingestion Parameters": [
        ("Snowflake FQN Stream Name", os.environ.get("SNOWFLAKE_STREAM_FQN", ""), False),
        ("Change Watermark Column", os.environ.get("CHANGE_WATERMARK_COLUMN", "UPDATED_ON"), False),
    ],
}

CTX = ssl._create_unverified_context()
_token: str | None = None


def log(message: str) -> None:
    print(message, flush=True)


def token() -> str:
    global _token
    if _token is None:
        body = urllib.parse.urlencode({"username": USERNAME, "password": PASSWORD}).encode()
        req = urllib.request.Request(
            f"{API}/access/token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _token = urllib.request.urlopen(req, context=CTX).read().decode()
    return _token


def api(method: str, path: str, body: dict | None = None) -> dict | None:
    req = urllib.request.Request(
        f"{API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(req, context=CTX)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} failed: HTTP {e.code} {e.read().decode()[:800]}") from None
    raw = response.read().decode()
    return json.loads(raw) if raw else None


def wait_for_nifi(timeout: int = 300) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        try:
            api("GET", "/flow/process-groups/root")
            log("NiFi API is up")
            return
        except Exception as e:  # noqa: BLE001 - includes auth and TLS failures
            # Report the reason: a rejected Host header or bad credentials would
            # otherwise look identical to NiFi still booting.
            reason = f"{type(e).__name__}: {e}"[:300]
            if reason != last:
                log(f"waiting for NiFi API ({reason})")
                last = reason
            time.sleep(5)
    raise SystemExit(f"NiFi API did not become available in time; last error: {last}")


def revision(path: str) -> dict:
    return api("GET", path)["revision"]


def create_parameter_contexts() -> str:
    """Create the three mirrored contexts, plus one that inherits all of them.

    NiFi binds a single context to a process group, so the connector's three
    parameter groups are modelled as inherited contexts to keep the same names.
    """
    inherited = []
    for name, params in PARAMETERS.items():
        entity = api("POST", "/parameter-contexts", {
            "revision": {"version": 0},
            "component": {
                "name": name,
                "description": "Mirrors the Openflow connector's parameter group of the same name",
                "parameters": [
                    {"parameter": {"name": p, "value": v, "sensitive": s, "description": ""}}
                    for p, v, s in params
                ],
            },
        })
        log(f"  parameter context: {name} ({len(params)} parameters)")
        inherited.append({"id": entity["id"], "component": {"id": entity["id"], "name": name}})

    combined = api("POST", "/parameter-contexts", {
        "revision": {"version": 0},
        "component": {
            "name": "Snowflake to Kafka",
            "description": "Inherits the connector's Source, Destination and Ingestion parameter groups",
            "parameters": [],
            "inheritedParameterContexts": inherited,
        },
    })
    return combined["id"]


def create_process_group(parameter_context_id: str) -> str:
    root = api("GET", "/flow/process-groups/root")["processGroupFlow"]["id"]
    entity = api("POST", f"/process-groups/{root}/process-groups", {
        "revision": {"version": 0},
        "component": {
            "name": GROUP_NAME,
            "comments": (
                "Simulates the Openflow Connector for Snowflake to Kafka. In production this "
                "process group is replaced by the connector imported from the Snowflake "
                "connector gallery: https://docs.snowflake.com/en/user-guide/data-integration/"
                "openflow/connectors/snowflake-to-kafka/setup"
            ),
            "position": {"x": 0, "y": 0},
            "parameterContext": {"id": parameter_context_id},
        },
    })
    return entity["id"]


def create_service(group: str, name: str, type_name: str, properties: dict) -> str:
    entity = api("POST", f"/process-groups/{group}/controller-services", {
        "revision": {"version": 0},
        "component": {"name": name, "type": type_name, "properties": properties},
    })
    log(f"  controller service: {name}")
    return entity["id"]


def enable_service(service_id: str, timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entity = api("GET", f"/controller-services/{service_id}")
        status = entity["component"]["validationStatus"]
        if status == "VALID":
            break
        if status == "INVALID":
            errors = entity["component"].get("validationErrors", [])
            raise SystemExit(f"controller service invalid: {errors}")
        time.sleep(2)

    api("PUT", f"/controller-services/{service_id}/run-status", {
        "revision": revision(f"/controller-services/{service_id}"),
        "state": "ENABLED",
    })
    while time.monotonic() < deadline:
        if api("GET", f"/controller-services/{service_id}")["component"]["state"] == "ENABLED":
            return
        time.sleep(2)
    raise SystemExit("controller service did not enable in time")


def create_processor(group: str, name: str, type_name: str, properties: dict,
                     scheduling: str | None = None, auto_terminate: list[str] | None = None) -> str:
    config: dict = {"properties": properties}
    if scheduling:
        config["schedulingPeriod"] = scheduling
    if auto_terminate:
        config["autoTerminatedRelationships"] = auto_terminate
    entity = api("POST", f"/process-groups/{group}/processors", {
        "revision": {"version": 0},
        "component": {"name": name, "type": type_name, "position": {"x": 0, "y": 0}, "config": config},
    })
    log(f"  processor: {name}")
    return entity["id"]


def connect(group: str, source: str, destination: str, relationships: list[str]) -> None:
    api("POST", f"/process-groups/{group}/connections", {
        "revision": {"version": 0},
        "component": {
            "source": {"id": source, "groupId": group, "type": "PROCESSOR"},
            "destination": {"id": destination, "groupId": group, "type": "PROCESSOR"},
            "selectedRelationships": relationships,
        },
    })


def build() -> None:
    root = api("GET", "/flow/process-groups/root")["processGroupFlow"]["id"]
    existing = api("GET", f"/flow/process-groups/{root}")["processGroupFlow"]["flow"]["processGroups"]
    for group in existing:
        if group["component"]["name"] == GROUP_NAME:
            log(f"process group '{GROUP_NAME}' already exists, nothing to do")
            return

    log("building flow")
    parameter_context = create_parameter_contexts()
    group = create_process_group(parameter_context)

    # Snowflake timestamps would otherwise serialise as epoch milliseconds.
    timestamp_formats = {
        "Timestamp Format": "yyyy-MM-dd HH:mm:ss.SSS",
        "Date Format": "yyyy-MM-dd",
        "Time Format": "HH:mm:ss.SSS",
    }
    # The query side writes a JSON array per FlowFile...
    writer = create_service(group, "CDC JSON Writer", "org.apache.nifi.json.JsonRecordSetWriter", {
        # The connector publishes messages with no attached schema.
        "Schema Write Strategy": "no-schema",
        "Output Grouping": "output-array",
        "Suppress Null Values": "never-suppress",
        **timestamp_formats,
    })
    # ...while each Kafka message must be a single JSON object. Sharing one
    # writer leaves the array separator at the start of every message after the
    # first.
    message_writer = create_service(group, "CDC Message Writer", "org.apache.nifi.json.JsonRecordSetWriter", {
        "Schema Write Strategy": "no-schema",
        "Output Grouping": "output-oneline",
        "Suppress Null Values": "never-suppress",
        **timestamp_formats,
    })
    reader = create_service(group, "CDC JSON Reader", "org.apache.nifi.json.JsonTreeReader", {})
    pool = create_service(group, "Snowflake Connection Pool", "org.apache.nifi.dbcp.DBCPConnectionPool", {
        "Database Connection URL": "#{Snowflake JDBC URL}",
        "Database Driver Class Name": DRIVER_CLASS,
        "Database Driver Locations": DRIVER_JAR,
        "Database User": "#{Snowflake Username}",
        "Password Source": "PASSWORD",
        "Password": "#{Snowflake Password}",
        # Without this, DBCP validates borrowed connections with
        # Connection.isValid(), which the Snowflake driver answers from a
        # /session/heartbeat call that fakesnow does not implement. The pool then
        # fails with "Cannot create PoolableConnectionFactory (isValid() returned
        # false)". A validation query bypasses that path.
        "Validation Query": "SELECT 1",
    })
    kafka = create_service(group, "Kafka Connection", "org.apache.nifi.kafka.service.Kafka3ConnectionService", {
        "bootstrap.servers": "#{Kafka Bootstrap Servers}",
        "security.protocol": "#{Kafka Security Protocol}",
    })

    for service in (writer, message_writer, reader, pool, kafka):
        enable_service(service)
    log("  controller services enabled")

    query = create_processor(
        group,
        "Consume Snowflake CDC",
        "org.apache.nifi.processors.standard.QueryDatabaseTableRecord",
        {
            "Database Connection Pooling Service": pool,
            "Database Type": "Generic",
            "Table Name": "#{Snowflake FQN Stream Name}",
            # Openflow consumes a stream, which advances as it is read. Without
            # change tracking, an incrementing column is the local equivalent.
            "Maximum-value Columns": "#{Change Watermark Column}",
            "Initial Load Strategy": "Start at Beginning",
            "Record Writer": writer,
            "Normalize Table/Column Names": "false",
            # Without logical types, TIMESTAMP columns arrive as plain longs and
            # the writer's Timestamp Format never applies, so every timestamp
            # would be published as epoch milliseconds.
            "Use Avro Logical Types": "true",
            "Max Rows Per FlowFile": "500",
        },
        scheduling=os.environ.get("POLL_INTERVAL", "10 sec"),
    )

    publish = create_processor(
        group,
        "Publish CDC to Kafka",
        "org.apache.nifi.kafka.processors.PublishKafka",
        {
            "Kafka Connection Service": kafka,
            "Topic Name": "#{Kafka Topic}",
            # Record mode: one Kafka message per CDC row, as the connector does.
            "Record Reader": reader,
            "Record Writer": message_writer,
            "Publish Strategy": "USE_VALUE",
            "Message Key Field": "#{Kafka Message Key Field}",
            "Transactions Enabled": "false",
            "acks": "all",
        },
        auto_terminate=["success", "failure"],
    )

    connect(group, query, publish, ["success"])
    log("  connected: Consume Snowflake CDC -> Publish CDC to Kafka")

    api("PUT", f"/flow/process-groups/{group}", {"id": group, "state": "RUNNING"})
    log(f"flow '{GROUP_NAME}' is running")


def main() -> int:
    wait_for_nifi()
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
