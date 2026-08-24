-- Q1: 每个 Scene 的持续时间（秒）与 Sample 数
-- name: scene_duration_and_sample_count
SELECT
  sc.name AS scene_name,
  sc.nbr_samples AS declared_sample_count,
  COUNT(s.token) AS actual_sample_count,
  ROUND((MAX(s.timestamp) - MIN(s.timestamp)) / 1e6, 2) AS duration_seconds
FROM scene sc
JOIN sample s ON s.scene_token = sc.token
GROUP BY sc.name, sc.nbr_samples
ORDER BY scene_name;
