-- Camera/LiDAR keyframe time-sync stats per scene per camera (same logic as
-- spark/sql/04_camera_lidar_time_diff.sql, materialized per scene instead of
-- globally). Key: (scene_token, camera_channel).
WITH cam AS (
  SELECT sd.sample_token, sd.timestamp AS cam_ts, se.channel
  FROM local.bronze.sample_data sd
  JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN local.bronze.sensor se ON se.token = cs.sensor_token
  WHERE se.modality = 'camera' AND sd.is_key_frame = true
),
lidar AS (
  SELECT sd.sample_token, sd.timestamp AS lidar_ts
  FROM local.bronze.sample_data sd
  JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN local.bronze.sensor se ON se.token = cs.sensor_token
  WHERE se.modality = 'lidar' AND sd.is_key_frame = true
),
pairs AS (
  SELECT
    s.scene_token,
    sc.name AS scene_name,
    cam.channel AS camera_channel,
    ABS(cam.cam_ts - lidar.lidar_ts) AS abs_diff_us
  FROM cam
  JOIN lidar ON lidar.sample_token = cam.sample_token
  JOIN local.bronze.sample s ON s.token = cam.sample_token
  JOIN local.bronze.scene sc ON sc.token = s.scene_token
)
SELECT
  scene_token,
  scene_name,
  camera_channel,
  ROUND(AVG(abs_diff_us) / 1000, 3) AS avg_abs_diff_ms,
  ROUND(MIN(abs_diff_us) / 1000, 3) AS min_abs_diff_ms,
  ROUND(MAX(abs_diff_us) / 1000, 3) AS max_abs_diff_ms,
  COUNT(*) AS pair_count
FROM pairs
GROUP BY scene_token, scene_name, camera_channel
