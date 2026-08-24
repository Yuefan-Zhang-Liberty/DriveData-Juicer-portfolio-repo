-- Flag scene/camera pairs whose max camera/LiDAR keyframe time gap exceeds
-- 75ms (roughly half a 12Hz camera frame period -- a gap bigger than that
-- means the "simultaneous" keyframes are meaningfully desynced).
SELECT
  CONCAT(scene_name, '/', camera_channel) AS scope_key,
  max_abs_diff_ms AS metric_value,
  CASE WHEN max_abs_diff_ms <= 75 THEN 'PASS' ELSE 'WARN' END AS status,
  'max abs camera/LiDAR keyframe timestamp diff (ms)' AS detail
FROM local.silver.sensor_alignment
