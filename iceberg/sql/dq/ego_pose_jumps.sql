-- Flag physically-implausible ego-motion jumps from silver_ego_motion:
-- implied speed > 40 m/s (144 km/h) between consecutive LIDAR_TOP frames.
SELECT
  scene_name AS scope_key,
  CAST(SUM(CASE WHEN displacement_m / dt_seconds > 40 THEN 1 ELSE 0 END) AS DOUBLE) AS metric_value,
  CASE WHEN SUM(CASE WHEN displacement_m / dt_seconds > 40 THEN 1 ELSE 0 END) = 0
       THEN 'PASS' ELSE 'WARN' END AS status,
  'frames with implied speed > 40 m/s between consecutive ego poses' AS detail
FROM local.silver.ego_motion
WHERE dt_seconds > 0
GROUP BY scene_name
