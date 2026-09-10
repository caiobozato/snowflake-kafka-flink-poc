-- Stand-in for the Snowflake Stream that the Openflow "Snowflake to Kafka"
-- connector consumes in production:
--   https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/snowflake-to-kafka/about
--
-- fakesnow implements neither CREATE STREAM nor ALTER TABLE ... SET
-- CHANGE_TRACKING, so this view reproduces the stream's *output shape* instead:
-- every source column, plus the three metadata columns the connector publishes
-- (it renames METADATA$ROW_ID, METADATA$ISUPDATE and METADATA$ACTION to
-- METADATA_ROW_ID, METADATA_ISUPDATE and METADATA_ACTION in the JSON payload).
--
-- In production this view is replaced by a real stream and the column names
-- revert to METADATA$*. Nothing downstream of the Kafka topic changes.

CREATE OR REPLACE VIEW PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION_CDC AS
SELECT
	TENANT_ID,
	WELL_ID,
	CONTROL_SYSTEM_ID,
	CONTEXT,
	EFFECTIVE_DATE,
	EFFECTIVE_ASPM_CLASSIFICATION,
	GAS_INTERFERENCE_SPEEDUP,
	CURRENT_MIN_SPM_SETPOINT,
	CURRENT_MAX_SPM_SETPOINT,
	MIN_SAFE_SPM,
	MAX_SAFE_SPM,
	RECOMMENDED_MIN_SPM_SETPOINT,
	RECOMMENDED_MAX_SPM_SETPOINT,
	MIN_SPM_SETPOINT_CHANGED,
	MAX_SPM_SETPOINT_CHANGED,
	OPERATING_CLASSIFICATION,
	CREATED_ON,
	UPDATED_ON,
	MODEL_VERSION,
	MESSAGES,
	MINSOP_LOWER,
	MINSOP_UPPER,
	MAXSOP_LOWER,
	MAXSOP_UPPER,
	-- Stable row identity, from the columns that identify a recommendation.
	-- A real stream derives this internally.
	MD5(TENANT_ID || '|' || WELL_ID || '|' || TO_VARCHAR(EFFECTIVE_DATE)) AS METADATA_ROW_ID,
	-- A stream sets this when an INSERT/DELETE pair represents an UPDATE. With
	-- no change tracking available, the table's own audit columns are the best
	-- available signal.
	(UPDATED_ON <> CREATED_ON) AS METADATA_ISUPDATE,
	-- Without change tracking there are no DELETEs to observe, so every row
	-- reads as an INSERT. A real stream also emits 'DELETE'.
	'INSERT' AS METADATA_ACTION
FROM PROD.DS_MODEL.MOD_ROD_SPM_SETPOINT_RECOMMENDATION
;
