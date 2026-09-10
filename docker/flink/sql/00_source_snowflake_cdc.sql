-- Snowflake stores these columns already converted to UTC, so pin Flink's
-- session zone to UTC. Otherwise casting to TIMESTAMP_LTZ for the ISO-8601
-- output would shift the value by the container's local offset.
SET 'table.local-time-zone' = 'UTC';

-- Source: the CDC topic produced by the NiFi flow (the Openflow connector's
-- output contract in production). Column names must match the JSON field names
-- exactly, so they are upper case.
--
-- `CONTEXT` is quoted because it is a reserved word in Flink SQL.
CREATE TABLE snowflake_cdc (
    TENANT_ID                     STRING,
    WELL_ID                       STRING,
    CONTROL_SYSTEM_ID             STRING,
    `CONTEXT`                     STRING,
    EFFECTIVE_DATE                TIMESTAMP(3),
    EFFECTIVE_ASPM_CLASSIFICATION STRING,
    GAS_INTERFERENCE_SPEEDUP      BOOLEAN,
    CURRENT_MIN_SPM_SETPOINT      DOUBLE,
    CURRENT_MAX_SPM_SETPOINT      DOUBLE,
    MIN_SAFE_SPM                  DOUBLE,
    MAX_SAFE_SPM                  DOUBLE,
    RECOMMENDED_MIN_SPM_SETPOINT  DOUBLE,
    RECOMMENDED_MAX_SPM_SETPOINT  DOUBLE,
    MIN_SPM_SETPOINT_CHANGED      BOOLEAN,
    MAX_SPM_SETPOINT_CHANGED      BOOLEAN,
    OPERATING_CLASSIFICATION      STRING,
    CREATED_ON                    TIMESTAMP(3),
    UPDATED_ON                    TIMESTAMP(3),
    MODEL_VERSION                 STRING,
    MESSAGES                      STRING,
    MINSOP_LOWER                  DOUBLE,
    MINSOP_UPPER                  DOUBLE,
    MAXSOP_LOWER                  DOUBLE,
    MAXSOP_UPPER                  DOUBLE,
    METADATA_ROW_ID               STRING,
    METADATA_ISUPDATE             BOOLEAN,
    METADATA_ACTION               STRING,
    -- Kafka's own record timestamp, available for windowing.
    KAFKA_TIMESTAMP               TIMESTAMP_LTZ(3) METADATA FROM 'timestamp' VIRTUAL
) WITH (
    'connector'                       = 'kafka',
    'topic'                           = '${SOURCE_TOPIC}',
    'properties.bootstrap.servers'    = '${KAFKA_BOOTSTRAP_SERVERS}',
    'properties.group.id'             = '${CONSUMER_GROUP}',
    -- Replays the topic from the start on every submit, which keeps the demo
    -- repeatable. Use 'group-offsets' or 'latest-offset' to change that.
    'scan.startup.mode'               = '${SCAN_STARTUP_MODE}',
    'format'                          = 'json',
    -- Matches the 'yyyy-MM-dd HH:mm:ss.SSS' timestamps the CDC flow emits.
    'json.timestamp-format.standard'  = 'SQL',
    'json.ignore-parse-errors'        = 'false'
);
