-- Q8: 不同时间段（白天/夜晚，由 Scene 描述中的 "Night" 关键字判定）的目标类别分布
-- name: object_distribution_by_time_of_day
WITH scene_period AS (
  SELECT
    token AS scene_token,
    name AS scene_name,
    CASE WHEN LOWER(description) LIKE '%night%' THEN 'night' ELSE 'day' END AS time_period
  FROM scene
)
SELECT
  sp.time_period,
  c.name AS category_name,
  COUNT(sa.token) AS annotation_count
FROM sample_annotation sa
JOIN instance i ON i.token = sa.instance_token
JOIN category c ON c.token = i.category_token
JOIN sample s ON s.token = sa.sample_token
JOIN scene_period sp ON sp.scene_token = s.scene_token
GROUP BY sp.time_period, c.name
ORDER BY time_period, annotation_count DESC;
