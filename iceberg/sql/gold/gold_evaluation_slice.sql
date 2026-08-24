-- Train/val split assignment, one row per scene. nuScenes mini has no
-- official split, so this assigns deterministically PER LOG (not per scene) —
-- crc32(log_token) % 5: buckets 0-3 -> train (80%), bucket 4 -> val (20%).
-- Assigning per log rather than per scene is exactly the fix for the leakage
-- risk Phase 1 query 9 flagged (a log with multiple scenes could otherwise
-- straddle both splits). crc32 is deterministic, so this MERGE is idempotent
-- and the split never drifts between reruns.
SELECT
  sc.token AS scene_token,
  sc.name AS scene_name,
  l.token AS log_token,
  l.logfile,
  CASE WHEN crc32(l.token) % 5 = 4 THEN 'val' ELSE 'train' END AS split
FROM local.bronze.scene sc
JOIN local.bronze.log l ON l.token = sc.log_token
