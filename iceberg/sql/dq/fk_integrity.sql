-- Scene/sample/annotation/instance foreign-key integrity. One row per relation.
SELECT 'sample_to_scene' AS scope_key,
       CAST(COUNT(*) AS DOUBLE) AS metric_value,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
       'sample rows whose scene_token has no matching scene' AS detail
FROM local.bronze.sample s
LEFT JOIN local.bronze.scene sc ON sc.token = s.scene_token
WHERE sc.token IS NULL

UNION ALL

SELECT 'sample_data_to_sample',
       CAST(COUNT(*) AS DOUBLE),
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       'sample_data rows whose sample_token has no matching sample'
FROM local.bronze.sample_data sd
LEFT JOIN local.bronze.sample s ON s.token = sd.sample_token
WHERE s.token IS NULL

UNION ALL

SELECT 'sample_annotation_to_sample',
       CAST(COUNT(*) AS DOUBLE),
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       'sample_annotation rows whose sample_token has no matching sample'
FROM local.bronze.sample_annotation sa
LEFT JOIN local.bronze.sample s ON s.token = sa.sample_token
WHERE s.token IS NULL

UNION ALL

SELECT 'instance_to_category',
       CAST(COUNT(*) AS DOUBLE),
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       'instance rows whose category_token has no matching category'
FROM local.bronze.instance i
LEFT JOIN local.bronze.category c ON c.token = i.category_token
WHERE c.token IS NULL
