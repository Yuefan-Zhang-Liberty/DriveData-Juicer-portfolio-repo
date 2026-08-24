-- Q3: 每个相机的数据完整率（关键帧覆盖率 = 该相机关键帧数 / 总 Sample 数）
-- name: camera_completeness_rate
WITH total_samples AS (
  SELECT COUNT(*) AS n FROM sample
)
SELECT
  se.channel AS camera_channel,
  COUNT(sd.token) AS key_frame_count,
  (SELECT n FROM total_samples) AS total_sample_count,
  ROUND(COUNT(sd.token) / (SELECT n FROM total_samples), 4) AS completeness_rate
FROM sample_data sd
JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
JOIN sensor se ON se.token = cs.sensor_token
WHERE se.modality = 'camera' AND sd.is_key_frame = true
GROUP BY se.channel
ORDER BY camera_channel;
