-- Per-frame ego motion referenced against the LIDAR_TOP 20Hz trajectory
-- (same logic as spark/sql/05_ego_pose_adjacent_motion.sql, kept at frame
-- grain instead of aggregated per scene). Key: ego_pose_token.
WITH lidar_pose AS (
  SELECT
    ep.token AS ego_pose_token,
    sc.token AS scene_token,
    sc.name AS scene_name,
    ep.timestamp,
    ep.translation,
    ep.rotation
  FROM local.bronze.sample_data sd
  JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
  JOIN local.bronze.sensor se ON se.token = cs.sensor_token
  JOIN local.bronze.ego_pose ep ON ep.token = sd.ego_pose_token
  JOIN local.bronze.sample s ON s.token = sd.sample_token
  JOIN local.bronze.scene sc ON sc.token = s.scene_token
  WHERE se.channel = 'LIDAR_TOP'
),
with_lag AS (
  SELECT
    ego_pose_token,
    scene_token,
    scene_name,
    timestamp,
    translation,
    rotation,
    LAG(translation) OVER (PARTITION BY scene_token ORDER BY timestamp) AS prev_translation,
    LAG(rotation) OVER (PARTITION BY scene_token ORDER BY timestamp) AS prev_rotation,
    LAG(timestamp) OVER (PARTITION BY scene_token ORDER BY timestamp) AS prev_timestamp
  FROM lidar_pose
)
SELECT
  ego_pose_token,
  scene_token,
  scene_name,
  timestamp,
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
