-- ============================================================================
-- This is the file to edit. Everything else is plumbing.
-- ============================================================================
--
-- Shapes the CDC stream into the speedRangeRecommendationUpdated event.
--
-- Two mappings below are placeholders, because the source table has no such
-- columns. Replace them with the real code tables:
--
--   classification  -- integer code; OPERATING_CLASSIFICATION is a string
--   status          -- 1 = Accepted; this is where validation rules belong
--
-- After editing:  docker compose up -d --force-recreate flink-sql

CREATE TEMPORARY VIEW recommendation_events AS
SELECT
    WELL_ID,
    -- PLACEHOLDER: substitute the real classification codes.
    CASE OPERATING_CLASSIFICATION
        WHEN 'NORMAL'           THEN 1
        WHEN 'GAS_INTERFERENCE' THEN 2
        WHEN 'PUMPED_OFF'       THEN 3
        ELSE 0
    END AS classification,
    CAST(CREATED_ON AS TIMESTAMP_LTZ(3)) AS createdOn,
    RECOMMENDED_MAX_SPM_SETPOINT AS recommended_max,
    RECOMMENDED_MIN_SPM_SETPOINT AS recommended_min,
    -- PLACEHOLDER validation: a recommendation is Accepted unless it is
    -- incomplete or inverted. Real rules (safe-range checks against
    -- MIN_SAFE_SPM / MAX_SAFE_SPM, etc.) go here.
    CASE
        WHEN RECOMMENDED_MIN_SPM_SETPOINT IS NULL
          OR RECOMMENDED_MAX_SPM_SETPOINT IS NULL              THEN 2
        WHEN RECOMMENDED_MIN_SPM_SETPOINT > RECOMMENDED_MAX_SPM_SETPOINT THEN 2
        ELSE 1
    END AS status
FROM snowflake_cdc
WHERE METADATA_ACTION = 'INSERT';

INSERT INTO speed_range_recommendation_updated
SELECT
    WELL_ID,
    ROW(
        classification,
        createdOn,
        recommended_max,
        recommended_min,
        status,
        CASE status WHEN 1 THEN 'Accepted' ELSE 'Rejected' END
    )
FROM recommendation_events;
