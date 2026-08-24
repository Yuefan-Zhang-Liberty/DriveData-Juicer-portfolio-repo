-- One row per sample_data record, enriched with sensor channel/modality,
-- ego pose, and sample/scene context. Key: sample_data_token.
SELECT
  sd.token AS sample_data_token,
  sc.token AS scene_token,
  sc.name AS scene_name,
  s.token AS sample_token,
  se.channel,
  se.modality,
  sd.timestamp,
  sd.is_key_frame,
  sd.filename,
  sd.height,
  sd.width,
  ep.translation AS ego_translation,
  ep.rotation AS ego_rotation,
  cs.translation AS sensor_translation,
  cs.rotation AS sensor_rotation,
  cs.camera_intrinsic
FROM local.bronze.sample_data sd
JOIN local.bronze.sample s ON s.token = sd.sample_token
JOIN local.bronze.scene sc ON sc.token = s.scene_token
JOIN local.bronze.calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
JOIN local.bronze.sensor se ON se.token = cs.sensor_token
JOIN local.bronze.ego_pose ep ON ep.token = sd.ego_pose_token
