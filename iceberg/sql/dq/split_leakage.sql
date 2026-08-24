-- Verifies gold_evaluation_slice's log-based split assignment produced zero
-- logs spanning more than one split (the leakage pattern Phase 1 query 9 flagged).
SELECT
  'logs_spanning_multiple_splits' AS scope_key,
  CAST(COUNT(*) AS DOUBLE) AS metric_value,
  CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
  'log_token values whose scenes were assigned to more than one split' AS detail
FROM (
  SELECT log_token
  FROM local.gold.evaluation_slice
  GROUP BY log_token
  HAVING COUNT(DISTINCT split) > 1
)
