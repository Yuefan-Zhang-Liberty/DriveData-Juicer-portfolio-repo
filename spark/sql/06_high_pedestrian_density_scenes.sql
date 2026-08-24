-- Q6: 高行人密度场景（按每个 Sample 平均行人标注数排序）
-- name: high_pedestrian_density_scenes
SELECT
  sc.name AS scene_name,
  COUNT(DISTINCT s.token) AS sample_count,
  COUNT(sa.token) AS pedestrian_annotation_count,
  ROUND(COUNT(sa.token) / COUNT(DISTINCT s.token), 3) AS avg_pedestrians_per_sample
FROM scene sc
JOIN sample s ON s.scene_token = sc.token
JOIN sample_annotation sa ON sa.sample_token = s.token
JOIN instance i ON i.token = sa.instance_token
JOIN category c ON c.token = i.category_token
WHERE c.name LIKE 'human.pedestrian%'
GROUP BY sc.name
ORDER BY avg_pedestrians_per_sample DESC;
