-- Annotation enriched with instance/category/scene context. Key: sample_annotation_token.
SELECT
  sa.token AS sample_annotation_token,
  sa.sample_token,
  s.scene_token,
  sc.name AS scene_name,
  sa.instance_token,
  c.token AS category_token,
  c.name AS category_name,
  sa.translation,
  sa.size,
  sa.rotation,
  sa.num_lidar_pts,
  sa.num_radar_pts,
  sa.visibility_token
FROM local.bronze.sample_annotation sa
JOIN local.bronze.sample s ON s.token = sa.sample_token
JOIN local.bronze.scene sc ON sc.token = s.scene_token
JOIN local.bronze.instance i ON i.token = sa.instance_token
JOIN local.bronze.category c ON c.token = i.category_token
