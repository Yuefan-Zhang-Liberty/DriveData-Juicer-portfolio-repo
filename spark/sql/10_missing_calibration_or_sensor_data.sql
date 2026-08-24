-- Q10: 缺失标定或 Sensor Data 检查
-- 10a: 每个 Sample 应有 12 个传感器（6 相机+1 LiDAR+5 雷达）的关键帧数据，缺失即为异常
-- 10b: 相机标定项 camera_intrinsic 为空，视为标定缺失
-- name: missing_calibration_or_sensor_data
WITH expected_channels AS (
  SELECT COUNT(*) AS n FROM sensor
),
sample_channel_coverage AS (
  SELECT
    s.token AS sample_token,
    sc.name AS scene_name,
    COUNT(DISTINCT se.channel) AS channel_count
  FROM sample s
  JOIN scene sc ON sc.token = s.scene_token
  LEFT JOIN sample_data sd ON sd.sample_token = s.token AND sd.is_key_frame = true
  LEFT JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  LEFT JOIN sensor se ON se.token = cs.sensor_token
  GROUP BY s.token, sc.name
)
SELECT
  'missing_sensor_data' AS issue_type,
  scc.scene_name,
  scc.sample_token,
  scc.channel_count AS actual_channel_count,
  (SELECT n FROM expected_channels) AS expected_channel_count
FROM sample_channel_coverage scc
WHERE scc.channel_count < (SELECT n FROM expected_channels)

UNION ALL

SELECT
  'missing_camera_intrinsic' AS issue_type,
  NULL AS scene_name,
  cs.token AS sample_token,
  0 AS actual_channel_count,
  0 AS expected_channel_count
FROM calibrated_sensor cs
JOIN sensor se ON se.token = cs.sensor_token
WHERE se.modality = 'camera' AND SIZE(cs.camera_intrinsic) = 0;
