-- Q9: 训练集/验证集 Scene 泄漏检查
-- nuScenes mini 没有自带 train/val 官方 split，此查询检测"若按 Scene 随机划分 train/val，
-- 是否会把同一 Log（同一车辆、同一天、同一路线）的多个 Scene 分到不同集合"——
-- 这是真实 nuScenes 全量数据集分 split 时必须避免的泄漏模式（同一 Log 的场景在时间和路线上高度相关）。
-- name: train_val_scene_leakage_by_log
WITH log_scene_count AS (
  SELECT
    l.token AS log_token,
    l.logfile,
    l.vehicle,
    l.date_captured,
    COUNT(DISTINCT sc.token) AS scene_count,
    COLLECT_LIST(sc.name) AS scene_names
  FROM log l
  JOIN scene sc ON sc.log_token = l.token
  GROUP BY l.token, l.logfile, l.vehicle, l.date_captured
)
SELECT
  logfile,
  vehicle,
  date_captured,
  scene_count,
  scene_names,
  CASE WHEN scene_count > 1 THEN 'LEAKAGE_RISK' ELSE 'SAFE' END AS split_risk
FROM log_scene_count
ORDER BY scene_count DESC, logfile;
