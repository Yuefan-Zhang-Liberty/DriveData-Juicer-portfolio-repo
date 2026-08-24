-- Calibration sanity checks: camera_intrinsic must be 3x3 with positive
-- focal lengths; sensor/ego-pose rotation quaternions must have unit norm.
SELECT 'camera_intrinsic_shape_or_focal' AS scope_key,
       CAST(COUNT(*) AS DOUBLE) AS metric_value,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       'camera calibrated_sensor rows with non-3x3 intrinsic or non-positive focal length' AS detail
FROM local.bronze.calibrated_sensor cs
JOIN local.bronze.sensor se ON se.token = cs.sensor_token
WHERE se.modality = 'camera'
  AND (SIZE(cs.camera_intrinsic) != 3
       OR SIZE(cs.camera_intrinsic[0]) != 3
       OR cs.camera_intrinsic[0][0] <= 0
       OR cs.camera_intrinsic[1][1] <= 0)

UNION ALL

SELECT 'calibrated_sensor_rotation_unit_norm',
       CAST(COUNT(*) AS DOUBLE),
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       'calibrated_sensor rotation quaternions with norm outside [0.99, 1.01]'
FROM local.bronze.calibrated_sensor
WHERE SQRT(rotation[0]*rotation[0] + rotation[1]*rotation[1] + rotation[2]*rotation[2] + rotation[3]*rotation[3])
      NOT BETWEEN 0.99 AND 1.01

UNION ALL

SELECT 'ego_pose_rotation_unit_norm',
       CAST(COUNT(*) AS DOUBLE),
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       'ego_pose rotation quaternions with norm outside [0.99, 1.01]'
FROM local.bronze.ego_pose
WHERE SQRT(rotation[0]*rotation[0] + rotation[1]*rotation[1] + rotation[2]*rotation[2] + rotation[3]*rotation[3])
      NOT BETWEEN 0.99 AND 1.01
