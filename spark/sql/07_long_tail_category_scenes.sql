-- Q7: 长尾类别（大车、骑行者、施工车辆等）出现的场景
-- name: long_tail_category_scenes
SELECT
  c.name AS category_name,
  sc.name AS scene_name,
  COUNT(sa.token) AS annotation_count
FROM sample_annotation sa
JOIN instance i ON i.token = sa.instance_token
JOIN category c ON c.token = i.category_token
JOIN sample s ON s.token = sa.sample_token
JOIN scene sc ON sc.token = s.scene_token
WHERE c.name IN (
  'vehicle.bus.bendy', 'vehicle.bus.rigid', 'vehicle.truck',
  'vehicle.construction', 'vehicle.trailer', 'vehicle.bicycle',
  'vehicle.motorcycle', 'vehicle.emergency.ambulance', 'vehicle.emergency.police'
)
GROUP BY c.name, sc.name
ORDER BY category_name, annotation_count DESC;
