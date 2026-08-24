"""Build Iceberg Bronze tables from nuScenes mini metadata JSON.

Reuses the explicit schemas / TABLES dict from spark/ingest_nuscenes.py so
the two ingestion paths (Parquet for Phase 1, Iceberg for Phase 2) never
drift apart. Every table is loaded via MERGE INTO keyed on the nuScenes
"token" primary key, so rerunning this script against unchanged source data
leaves row counts unchanged while still advancing each table's snapshot
history (idempotent write, not a duplicate-producing append).

Usage:
    python iceberg/build_bronze.py \
        --data-root /home/yuefan.zhang/Data_juicer/data/nuscenes \
        --warehouse-dir /home/yuefan.zhang/Data_juicer/warehouse/iceberg_warehouse
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spark"))
sys.path.insert(0, os.path.dirname(__file__))

from ingest_nuscenes import TABLES, load_table  # noqa: E402
from spark_session import build_spark  # noqa: E402

NAMESPACE = "local.bronze"


def ensure_table(spark, table_name, schema):
    columns_sql = ", ".join(f"{f.name} {f.dataType.simpleString()}" for f in schema.fields)
    spark.sql(f"CREATE TABLE IF NOT EXISTS {NAMESPACE}.{table_name} ({columns_sql}) USING iceberg")


def merge_table(spark, table_name, df):
    df.createOrReplaceTempView(f"src_{table_name}")
    spark.sql(f"""
        MERGE INTO {NAMESPACE}.{table_name} t
        USING src_{table_name} s
        ON t.token = s.token
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)


def build_bronze(spark, data_root, version):
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE}")
    counts = {}
    for table_name, schema in TABLES.items():
        df = load_table(spark, data_root, version, table_name)
        ensure_table(spark, table_name, schema)
        merge_table(spark, table_name, df)
        counts[table_name] = spark.sql(f"SELECT COUNT(*) AS c FROM {NAMESPACE}.{table_name}").collect()[0]["c"]
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--version", default="v1.0-mini")
    parser.add_argument("--warehouse-dir", required=True)
    args = parser.parse_args()

    spark = build_spark(args.warehouse_dir, app_name="iceberg-build-bronze")
    counts = build_bronze(spark, args.data_root, args.version)
    for name, count in counts.items():
        snap_count = spark.sql(f"SELECT COUNT(*) AS c FROM {NAMESPACE}.{name}.snapshots").collect()[0]["c"]
        print(f"{name}: {count} rows, {snap_count} snapshots")
    spark.stop()


if __name__ == "__main__":
    main()
