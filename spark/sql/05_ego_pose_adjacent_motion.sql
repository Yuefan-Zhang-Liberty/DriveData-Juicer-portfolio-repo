-- Q5: Ego Pose 相邻帧位移与旋转变化（以 LIDAR_TOP 20Hz 轨迹为参照，使用窗口函数 LAG）
-- name: ego_pose_adjacent_motion
WITH lidar_pose AS (
  SELECT
    sc.name AS scene_name,
    ep.timestamp,
    ep.translation,
    ep.rotation
  FROM sample_data sd
  JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN sensor se ON se.token = cs.sensor_token
  JOIN ego_pose ep ON ep.token = sd.ego_pose_token
  JOIN sample s ON s.token = sd.sample_token
  JOIN scene sc ON sc.token = s.scene_token
  WHERE se.channel = 'LIDAR_TOP'
),
with_lag AS (
  SELECT
    scene_name,
    timestamp,
    translation,
    rotation,
    LAG(translation) OVER (PARTITION BY scene_name ORDER BY timestamp) AS prev_translation,
    LAG(rotation) OVER (PARTITION BY scene_name ORDER BY timestamp) AS prev_rotation,
    LAG(timestamp) OVER (PARTITION BY scene_name ORDER BY timestamp) AS prev_timestamp
  FROM lidar_pose
),
motion AS (
  SELECT
    scene_name,
    (timestamp - prev_timestamp) / 1e6 AS dt_seconds,
    SQRT(
      POWER(translation[0] - prev_translation[0], 2) +
      POWER(translation[1] - prev_translation[1], 2) +
      POWER(translation[2] - prev_translation[2], 2)
    ) AS displacement_m,
    2 * ACOS(LEAST(1.0, ABS(
      rotation[0] * prev_rotation[0] +
      rotation[1] * prev_rotation[1] +
      rotation[2] * prev_rotation[2] +
      rotation[3] * prev_rotation[3]
    ))) AS rotation_change_rad
  FROM with_lag
  WHERE prev_translation IS NOT NULL
)
SELECT
  scene_name,
  ROUND(AVG(displacement_m), 4) AS avg_displacement_m,
  ROUND(MAX(displacement_m), 4) AS max_displacement_m,
  ROUND(AVG(rotation_change_rad), 4) AS avg_rotation_change_rad,
  ROUND(MAX(rotation_change_rad), 4) AS max_rotation_change_rad,
  ROUND(MAX(displacement_m / dt_seconds), 3) AS max_speed_mps
FROM motion
GROUP BY scene_name
ORDER BY scene_name;
