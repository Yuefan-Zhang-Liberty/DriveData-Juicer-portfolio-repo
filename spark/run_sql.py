"""Run all Phase-1 business SQL queries against the bronze Parquet tables.

For each .sql file under spark/sql/, this script registers all bronze tables
as temp views, executes the query, and records input row counts (per source
table referenced), output row count, and wall-clock execution time. Results
are written to benchmarks/reports/spark_week1.md.

Usage:
    python spark/run_sql.py \
        --warehouse-dir /home/yuefan.zhang/Data_juicer/warehouse/bronze_parquet \
        --sql-dir /home/yuefan.zhang/Data_juicer/spark/sql \
        --report /home/yuefan.zhang/Data_juicer/benchmarks/reports/spark_week1.md
"""
import argparse
import glob
import os
import re
import time

from pyspark.sql import SparkSession

TABLE_NAMES = [
    "scene", "sample", "sample_data", "ego_pose", "calibrated_sensor",
    "sample_annotation", "category", "sensor", "log", "instance", "visibility",
]


def build_spark():
    return (
        SparkSession.builder.appName("nuscenes-sql-runner")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def register_tables(spark, warehouse_dir):
    counts = {}
    for name in TABLE_NAMES:
        df = spark.read.parquet(os.path.join(warehouse_dir, name))
        df.createOrReplaceTempView(name)
        counts[name] = df.count()
    return counts


def strip_comments(sql_text):
    lines = [line for line in sql_text.splitlines() if not line.strip().startswith("--")]
    return "\n".join(lines).strip()


def referenced_tables(sql_text, table_counts):
    lowered = sql_text.lower()
    return sorted(
        name for name in table_counts
        if re.search(rf"\b{re.escape(name)}\b", lowered)
    )


def run_all(spark, sql_dir, table_counts):
    results = []
    for path in sorted(glob.glob(os.path.join(sql_dir, "*.sql"))):
        with open(path) as f:
            raw = f.read()
        query = strip_comments(raw)
        name_match = re.search(r"-- name:\s*(\S+)", raw)
        query_name = name_match.group(1) if name_match else os.path.basename(path)

        start = time.time()
        df = spark.sql(query)
        out_count = df.count()
        elapsed = time.time() - start

        inputs = referenced_tables(raw, table_counts)
        input_desc = ", ".join(f"{t}={table_counts[t]}" for t in inputs)

        results.append({
            "file": os.path.basename(path),
            "name": query_name,
            "input_tables": input_desc,
            "output_rows": out_count,
            "elapsed_s": round(elapsed, 3),
        })
        print(f"{query_name}: input=[{input_desc}] output_rows={out_count} elapsed={elapsed:.3f}s")
    return results


def write_report(results, report_path):
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    lines = [
        "# Spark Week 1 — Business SQL Benchmark Report",
        "",
        "| Query | Input tables (rows) | Output rows | Elapsed (s) |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['name']} | {r['input_tables']} | {r['output_rows']} | {r['elapsed_s']} |")
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--sql-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    spark = build_spark()
    table_counts = register_tables(spark, args.warehouse_dir)
    results = run_all(spark, args.sql_dir, table_counts)
    write_report(results, args.report)
    spark.stop()


if __name__ == "__main__":
    main()
