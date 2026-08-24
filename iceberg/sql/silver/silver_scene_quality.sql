-- Per-scene quality aggregates. Key: scene_token. Depends on
-- local.silver.sensor_alignment (build silver_sensor_alignment first).
WITH scene_samples AS (
  SELECT sc.token AS scene_token, sc.name AS scene_name, COUNT(*) AS sample_count
  FROM local.bronze.sample s
  JOIN local.bronze.scene sc ON sc.token = s.scene_token
  GROUP BY sc.token, sc.name
),
sensor_coverage AS (
  -- keyframe channel coverage per sample, then averaged per scene
  SELECT
    s.scene_token,
    AVG(cnt.channel_count) / (SELECT COUNT(*) FROM local.bronze.sensor) AS avg_completeness_rate
  FROM (
    SELECT sd.sample_token, COUNT(DISTINCT se.channel) AS channel_count
    FROM local.bronze.sample_data sd
    JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
    JOIN local.bronze.sensor se ON se.token = cs.sensor_token
    WHERE sd.is_key_frame = true
    GROUP BY sd.sample_token
  ) cnt
  JOIN local.bronze.sample s ON s.token = cnt.sample_token
  GROUP BY s.scene_token
),
alignment AS (
  SELECT scene_token, ROUND(AVG(avg_abs_diff_ms), 3) AS avg_cam_lidar_diff_ms
  FROM local.silver.sensor_alignment
  GROUP BY scene_token
),
pedestrian AS (
  SELECT scene_token, COUNT(*) AS pedestrian_annotation_count
  FROM local.silver.object_annotation
  WHERE category_name LIKE 'human.pedestrian%'
  GROUP BY scene_token
),
long_tail AS (
  SELECT scene_token, COUNT(*) AS long_tail_annotation_count
  FROM local.silver.object_annotation
  WHERE category_name IN (
    'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.truck',
    'vehicle.construction', 'vehicle.trailer', 'vehicle.bicycle',
    'vehicle.motorcycle', 'vehicle.emergency.ambulance', 'vehicle.emergency.police'
  )
  GROUP BY scene_token
)
SELECT
  ss.scene_token,
  ss.scene_name,
  ss.sample_count,
  ROUND(sc.avg_completeness_rate, 4) AS avg_sensor_completeness_rate,
  al.avg_cam_lidar_diff_ms,
  COALESCE(p.pedestrian_annotation_count, 0) AS pedestrian_annotation_count,
  COALESCE(lt.long_tail_annotation_count, 0) AS long_tail_annotation_count
FROM scene_samples ss
LEFT JOIN sensor_coverage sc ON sc.scene_token = ss.scene_token
LEFT JOIN alignment al ON al.scene_token = ss.scene_token
LEFT JOIN pedestrian p ON p.scene_token = ss.scene_token
LEFT JOIN long_tail lt ON lt.scene_token = ss.scene_token
