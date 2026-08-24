-- Q4: 同一 Sample 内 Camera 与 LiDAR 关键帧的时间差分布（毫秒）
-- name: camera_lidar_time_diff
WITH cam AS (
  SELECT sd.sample_token, sd.timestamp AS cam_ts, se.channel
  FROM sample_data sd
  JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN sensor se ON se.token = cs.sensor_token
  WHERE se.modality = 'camera' AND sd.is_key_frame = true
),
lidar AS (
  SELECT sd.sample_token, sd.timestamp AS lidar_ts
  FROM sample_data sd
  JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN sensor se ON se.token = cs.sensor_token
  WHERE se.modality = 'lidar' AND sd.is_key_frame = true
)
SELECT
  cam.channel AS camera_channel,
  ROUND(AVG(ABS(cam.cam_ts - lidar.lidar_ts)) / 1000, 3) AS avg_abs_diff_ms,
  ROUND(MIN(ABS(cam.cam_ts - lidar.lidar_ts)) / 1000, 3) AS min_abs_diff_ms,
  ROUND(MAX(ABS(cam.cam_ts - lidar.lidar_ts)) / 1000, 3) AS max_abs_diff_ms,
  COUNT(*) AS pair_count
FROM cam
JOIN lidar ON lidar.sample_token = cam.sample_token
GROUP BY cam.channel
ORDER BY camera_channel;
