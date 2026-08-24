-- Per-scene long-tail-category summary (materializes Phase 1 query 7 at
-- scene grain). Key: scene_token.
WITH long_tail AS (
  SELECT
    scene_token,
    category_name,
    COUNT(*) AS annotation_count
  FROM local.silver.object_annotation
  WHERE category_name IN (
    'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.truck',
    'vehicle.construction', 'vehicle.trailer', 'vehicle.bicycle',
    'vehicle.motorcycle', 'vehicle.emergency.ambulance', 'vehicle.emergency.police'
  )
  GROUP BY scene_token, category_name
)
SELECT
  sq.scene_token,
  sq.scene_name,
  COALESCE(SUM(lt.annotation_count), 0) AS long_tail_annotation_count,
  COLLECT_LIST(lt.category_name) AS long_tail_categories,
  COALESCE(SUM(lt.annotation_count), 0) > 0 AS is_long_tail_scene
FROM local.silver.scene_quality sq
LEFT JOIN long_tail lt ON lt.scene_token = sq.scene_token
GROUP BY sq.scene_token, sq.scene_name
