"""Run the 8 Phase-2 data quality checks and append results to
local.audit.dq_results (Iceberg, append-only -- every run adds a new batch
tagged with its own run_ts, so DQ history accumulates across runs instead of
being overwritten).

Usage:
    python iceberg/dq_checks.py --warehouse-dir warehouse/iceberg_warehouse
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from spark_session import build_spark  # noqa: E402
from pyspark.sql.functions import lit  # noqa: E402

NAMESPACE = "local.audit"
SQL_DIR = os.path.join(os.path.dirname(__file__), "sql", "dq")

CHECKS = [
    "fk_integrity",
    "sensor_missing_rate",
    "timestamp_monotonicity",
    "ego_pose_jumps",
    "calibration_validity",
    "sensor_alignment_deviation",
    "frame_duplication_rate",
    "split_leakage",
]


def read_sql(check_name):
    with open(os.path.join(SQL_DIR, f"{check_name}.sql")) as f:
        return f.read()


def ensure_table(spark):
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {NAMESPACE}.dq_results (
            run_ts DOUBLE,
            check_name STRING,
            scope_key STRING,
            metric_value DOUBLE,
            status STRING,
            detail STRING
        ) USING iceberg
    """)


def run_checks(spark, run_ts):
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE}")
    ensure_table(spark)
    results = {}
    for check_name in CHECKS:
        df = spark.sql(read_sql(check_name))
        df = df.withColumn("run_ts", lit(run_ts)).withColumn("check_name", lit(check_name))
        df = df.select("run_ts", "check_name", "scope_key", "metric_value", "status", "detail")
        df.createOrReplaceTempView(f"dq_src_{check_name}")
        spark.sql(f"INSERT INTO {NAMESPACE}.dq_results SELECT * FROM dq_src_{check_name}")
        rows = df.collect()
        results[check_name] = rows
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    args = parser.parse_args()

    spark = build_spark(args.warehouse_dir, app_name="iceberg-dq-checks")
    run_ts = time.time()
    results = run_checks(spark, run_ts)

    fail_count = 0
    for check_name, rows in results.items():
        for r in rows:
            print(f"[{r['status']:4}] {check_name:28} {r['scope_key']:35} {r['metric_value']:>10} {r['detail']}")
            if r["status"] == "FAIL":
                fail_count += 1
    print(f"\n{fail_count} FAIL rows out of {sum(len(r) for r in results.values())} total DQ rows (run_ts={run_ts})")
    spark.stop()


if __name__ == "__main__":
    main()
