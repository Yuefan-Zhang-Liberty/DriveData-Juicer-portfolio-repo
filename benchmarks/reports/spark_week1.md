# Spark Week 1 — Business SQL Benchmark Report

| Query | Input tables (rows) | Output rows | Elapsed (s) |
|---|---|---|---|
| scene_duration_and_sample_count | sample=404, scene=10 | 10 | 0.79 |
| annotation_count_by_category | category=23, instance=911, sample_annotation=18538 | 18 | 0.353 |
| camera_completeness_rate | calibrated_sensor=120, sample=404, sample_data=31206, sensor=12 | 6 | 0.436 |
| camera_lidar_time_diff | calibrated_sensor=120, sample=404, sample_data=31206, sensor=12 | 6 | 0.639 |
| ego_pose_adjacent_motion | calibrated_sensor=120, ego_pose=31206, sample=404, sample_data=31206, scene=10, sensor=12 | 10 | 1.304 |
| high_pedestrian_density_scenes | category=23, instance=911, sample=404, sample_annotation=18538, scene=10 | 9 | 0.447 |
| long_tail_category_scenes | category=23, instance=911, sample=404, sample_annotation=18538, scene=10 | 35 | 0.398 |
| object_distribution_by_time_of_day | category=23, instance=911, sample=404, sample_annotation=18538, scene=10 | 25 | 0.322 |
| train_val_scene_leakage_by_log | log=8, scene=10 | 8 | 0.314 |
| missing_calibration_or_sensor_data | calibrated_sensor=120, sample=404, sample_data=31206, scene=10, sensor=12 | 0 | 0.713 |
