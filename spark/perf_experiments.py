"""Phase-1 Spark performance experiments over nuScenes mini bronze tables.

Compares:
  1. Broadcast join vs. sort-merge join (by disabling autoBroadcastJoinThreshold)
  2. Repeated query with vs. without .cache()
  3. Shuffle partition count: too few (2) vs. default (8) vs. too many (200)
  4. Python UDF vs. built-in Spark SQL expression for the same computation

Each experiment runs the same logical query multiple times and reports
wall-clock time, to be recorded with an explanation in
docs/experiment_log_template.md-style logs and summarized in
benchmarks/reports/spark_week1.md.

Usage:
    python spark/perf_experiments.py --warehouse-dir warehouse/bronze_parquet \
        --report benchmarks/reports/spark_week1_perf.md
"""
import argparse
import math
import os
import time

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, pow as spark_pow, sqrt as spark_sqrt, udf
from pyspark.sql.types import DoubleType

TABLE_NAMES = [
    "scene", "sample", "sample_data", "ego_pose", "calibrated_sensor",
    "sample_annotation", "category", "sensor", "log", "instance", "visibility",
]


def build_spark(shuffle_partitions=8, broadcast_threshold="10485760"):
    return (
        SparkSession.builder.appName("nuscenes-perf-experiments")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.autoBroadcastJoinThreshold", broadcast_threshold)
        .getOrCreate()
    )


def register_tables(spark, warehouse_dir):
    for name in TABLE_NAMES:
        spark.read.parquet(os.path.join(warehouse_dir, name)).createOrReplaceTempView(name)


def timed(fn, repeats=3):
    times = []
    for _ in range(repeats):
        start = time.time()
        fn()
        times.append(time.time() - start)
    return times


def experiment_join_strategy(warehouse_dir, results):
    join_sql = """
        SELECT c.name, COUNT(*) AS cnt
        FROM sample_annotation sa
        JOIN instance i ON i.token = sa.instance_token
        JOIN category c ON c.token = i.category_token
        GROUP BY c.name
    """

    spark_bc = build_spark(broadcast_threshold="10485760")
    register_tables(spark_bc, warehouse_dir)
    plan_bc = spark_bc.sql(join_sql)
    plan_str_bc = plan_bc._jdf.queryExecution().simpleString()
    times_bc = timed(lambda: plan_bc.collect())
    spark_bc.stop()

    spark_smj = build_spark(broadcast_threshold="-1")
    register_tables(spark_smj, warehouse_dir)
    plan_smj = spark_smj.sql(join_sql)
    plan_str_smj = plan_smj._jdf.queryExecution().simpleString()
    times_smj = timed(lambda: plan_smj.collect())
    spark_smj.stop()

    results.append({
        "experiment": "broadcast_join_vs_sort_merge_join",
        "broadcast_join_times_s": [round(t, 3) for t in times_bc],
        "sort_merge_join_times_s": [round(t, 3) for t in times_smj],
        "broadcast_uses_BroadcastHashJoin": "BroadcastHashJoin" in plan_str_bc,
        "sort_merge_uses_SortMergeJoin": "SortMergeJoin" in plan_str_smj,
    })


def experiment_cache(warehouse_dir, results):
    spark = build_spark()
    register_tables(spark, warehouse_dir)

    heavy_sql = """
        SELECT sc.name, COUNT(*) AS cnt
        FROM sample_annotation sa
        JOIN instance i ON i.token = sa.instance_token
        JOIN category c ON c.token = i.category_token
        JOIN sample s ON s.token = sa.sample_token
        JOIN scene sc ON sc.token = s.scene_token
        GROUP BY sc.name
    """
    df = spark.sql(heavy_sql)

    times_uncached = timed(lambda: df.collect(), repeats=3)

    df_cached = spark.sql(heavy_sql).cache()
    df_cached.count()  # materialize cache
    times_cached = timed(lambda: df_cached.collect(), repeats=3)

    results.append({
        "experiment": "cache_vs_no_cache_repeated_query",
        "uncached_times_s": [round(t, 3) for t in times_uncached],
        "cached_times_s": [round(t, 3) for t in times_cached],
    })
    spark.stop()


def experiment_partition_count(warehouse_dir, results):
    join_sql = """
        SELECT c.name, COUNT(*) AS cnt
        FROM sample_annotation sa
        JOIN instance i ON i.token = sa.instance_token
        JOIN category c ON c.token = i.category_token
        JOIN sample s ON s.token = sa.sample_token
        JOIN scene sc ON sc.token = s.scene_token
        GROUP BY c.name
    """
    partition_results = {}
    for n_partitions in [2, 8, 200]:
        spark = build_spark(shuffle_partitions=n_partitions)
        register_tables(spark, warehouse_dir)
        df = spark.sql(join_sql)
        times = timed(lambda: df.collect(), repeats=3)
        partition_results[n_partitions] = [round(t, 3) for t in times]
        spark.stop()

    results.append({
        "experiment": "shuffle_partitions_2_vs_8_vs_200",
        "partition_2_times_s": partition_results[2],
        "partition_8_times_s": partition_results[8],
        "partition_200_times_s": partition_results[200],
    })


def experiment_udf_vs_builtin(warehouse_dir, results):
    spark = build_spark()
    register_tables(spark, warehouse_dir)

    lidar_pose = spark.sql("""
        SELECT
          sc.name AS scene_name,
          ep.timestamp,
          ep.translation
        FROM sample_data sd
        JOIN calibrated_sensor cs ON cs.token = sd.calibrated_sensor_token
        JOIN sensor se ON se.token = cs.sensor_token
        JOIN ego_pose ep ON ep.token = sd.ego_pose_token
        JOIN sample s ON s.token = sd.sample_token
        JOIN scene sc ON sc.token = s.scene_token
        WHERE se.channel = 'LIDAR_TOP'
    """)

    from pyspark.sql.window import Window
    from pyspark.sql.functions import lag

    w = Window.partitionBy("scene_name").orderBy("timestamp")
    with_lag = lidar_pose.withColumn("prev_translation", lag("translation").over(w))
    with_lag = with_lag.filter(col("prev_translation").isNotNull())

    # Built-in expression version
    builtin_df = with_lag.withColumn(
        "displacement_m",
        spark_sqrt(
            spark_pow(col("translation")[0] - col("prev_translation")[0], 2) +
            spark_pow(col("translation")[1] - col("prev_translation")[1], 2) +
            spark_pow(col("translation")[2] - col("prev_translation")[2], 2)
        )
    )
    times_builtin = timed(lambda: builtin_df.select("displacement_m").collect(), repeats=3)

    # Python UDF version (same math, forces row-by-row Python execution)
    def euclidean_distance(a, b):
        return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))

    dist_udf = udf(euclidean_distance, DoubleType())
    udf_df = with_lag.withColumn(
        "displacement_m", dist_udf(col("translation"), col("prev_translation"))
    )
    times_udf = timed(lambda: udf_df.select("displacement_m").collect(), repeats=3)

    results.append({
        "experiment": "python_udf_vs_builtin_expression",
        "builtin_times_s": [round(t, 3) for t in times_builtin],
        "python_udf_times_s": [round(t, 3) for t in times_udf],
    })
    spark.stop()


def write_report(results, report_path):
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    lines = ["# Spark Week 1 — Performance Experiments", ""]
    for r in results:
        lines.append(f"## {r['experiment']}")
        lines.append("")
        for k, v in r.items():
            if k == "experiment":
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    results = []
    experiment_join_strategy(args.warehouse_dir, results)
    experiment_cache(args.warehouse_dir, results)
    experiment_partition_count(args.warehouse_dir, results)
    experiment_udf_vs_builtin(args.warehouse_dir, results)

    for r in results:
        print(r)

    write_report(results, args.report)


if __name__ == "__main__":
    main()
