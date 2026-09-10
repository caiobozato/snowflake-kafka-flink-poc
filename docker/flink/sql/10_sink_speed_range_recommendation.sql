-- Sink: the event contract published to
-- ambyio.swo-poc-control-system.lufkin.speedRangeRecommendationUpdated
--
-- The payload is a `data` envelope:
--
--   {"data": {"classification": 1, "createdOn": "2026-09-09T01:30:16.219Z",
--             "max": 5, "min": 3.6, "status": 1, "statusName": "Accepted"}}
--
-- WELL_ID is declared so it can be used as the Kafka message key, and excluded
-- from the value by 'value.fields-include' = 'EXCEPT_KEY'.
--
-- `min` and `max` are reserved words in Flink SQL, hence the quoting.
CREATE TABLE speed_range_recommendation_updated (
    WELL_ID STRING,
    `data` ROW<
        classification INT,
        createdOn      TIMESTAMP_LTZ(3),
        `max`          DOUBLE,
        `min`          DOUBLE,
        status         INT,
        statusName     STRING
    >
) WITH (
    'connector'                    = 'kafka',
    'topic'                        = '${SINK_TOPIC}',
    'properties.bootstrap.servers' = '${KAFKA_BOOTSTRAP_SERVERS}',
    'key.format'                   = 'raw',
    'key.fields'                   = 'WELL_ID',
    -- Keep the key out of the value, so the payload is exactly the envelope.
    'value.fields-include'         = 'EXCEPT_KEY',
    'value.format'                 = 'json',
    -- Produces 2026-09-09T01:30:16.219Z rather than a space-separated stamp.
    'value.json.timestamp-format.standard' = 'ISO-8601'
);
