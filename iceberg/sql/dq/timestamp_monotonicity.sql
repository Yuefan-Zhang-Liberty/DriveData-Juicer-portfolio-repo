-- Per (scene, channel) sample_data timestamp must strictly increase along
-- the prev/next linked-list chain. One row per scene with any violation
-- count (0 rows in the result = no violations anywhere).
WITH linked AS (
  SELECT
    sc.name AS scene_name,
    se.channel,
    sd.timestamp AS ts,
    nxt.timestamp AS next_ts
  FROM local.bronze.sample_data sd
  JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN local.bronze.sensor se ON se.token = cs.sensor_token
  JOIN local.bronze.sample s ON s.token = sd.sample_token
  JOIN local.bronze.scene sc ON sc.token = s.scene_token
  LEFT JOIN local.bronze.sample_data nxt ON nxt.token = sd.next
  WHERE sd.next IS NOT NULL AND sd.next != ''
)
SELECT
  scene_name AS scope_key,
  CAST(SUM(CASE WHEN next_ts <= ts THEN 1 ELSE 0 END) AS DOUBLE) AS metric_value,
  CASE WHEN SUM(CASE WHEN next_ts <= ts THEN 1 ELSE 0 END) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
  'sample_data.next chain links with non-increasing timestamp' AS detail
FROM linked
GROUP BY scene_name
