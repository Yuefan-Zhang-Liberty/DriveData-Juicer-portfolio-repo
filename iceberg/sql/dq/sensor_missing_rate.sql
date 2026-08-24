-- Sensor keyframe-coverage rate per scene, from silver_scene_quality.
-- WARN if a scene's average completeness falls below 0.98 (nuScenes
-- guarantees synced keyframes across all 12 sensors, so <98% is unexpected).
SELECT
  scene_name AS scope_key,
  avg_sensor_completeness_rate AS metric_value,
  CASE WHEN avg_sensor_completeness_rate >= 0.98 THEN 'PASS' ELSE 'WARN' END AS status,
  'avg keyframe channel coverage vs 12 expected sensors' AS detail
FROM local.silver.scene_quality
