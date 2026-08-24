-- Q2: 各类别 3D 标注数量
-- name: annotation_count_by_category
SELECT
  c.name AS category_name,
  COUNT(sa.token) AS annotation_count
FROM sample_annotation sa
JOIN instance i ON i.token = sa.instance_token
JOIN category c ON c.token = i.category_token
GROUP BY c.name
ORDER BY annotation_count DESC;
