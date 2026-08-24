-- Metadata-level duplicate-frame proxy: duplicate (channel, timestamp) or
-- duplicate filename within sample_data. This is NOT pixel-content dedup --
-- Phase 2 has no pixel access, so this only catches duplicate *records*.
-- True perceptual/content duplicate detection is deferred to Data-Juicer's
-- video dedup operators in Phase 3.
WITH by_channel_ts AS (
  SELECT se.channel, sd.timestamp, COUNT(*) AS n
  FROM local.bronze.sample_data sd
  JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN local.bronze.sensor se ON se.token = cs.sensor_token
  GROUP BY se.channel, sd.timestamp
  HAVING COUNT(*) > 1
),
by_filename AS (
  SELECT filename, COUNT(*) AS n
  FROM local.bronze.sample_data
  GROUP BY filename
  HAVING COUNT(*) > 1
)
SELECT 'duplicate_channel_timestamp' AS scope_key,
       CAST(COALESCE(SUM(n), 0) AS DOUBLE) AS metric_value,
       CASE WHEN COALESCE(SUM(n), 0) = 0 THEN 'PASS' ELSE 'WARN' END AS status,
       '[metadata-level proxy, not pixel dedup] duplicate (channel, timestamp) sample_data rows' AS detail
FROM by_channel_ts

UNION ALL

SELECT 'duplicate_filename',
       CAST(COALESCE((SELECT SUM(n) FROM by_filename), 0) AS DOUBLE),
       CASE WHEN COALESCE((SELECT SUM(n) FROM by_filename), 0) = 0 THEN 'PASS' ELSE 'WARN' END,
       '[metadata-level proxy, not pixel dedup] duplicate filename sample_data rows'
