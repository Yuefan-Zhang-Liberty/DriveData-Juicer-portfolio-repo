-- LiDAR-modality subset of silver_sensor_frame. Key: sample_data_token.
SELECT *
FROM local.silver.sensor_frame
WHERE modality = 'lidar'
