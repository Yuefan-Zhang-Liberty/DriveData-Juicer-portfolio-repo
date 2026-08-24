"""Build Iceberg Gold tables.

Only 2 of the 5 named Gold tables are in scope for Phase 2:
  - gold_long_tail_scene  (needs only Bronze/Silver metadata, ready now)
  - gold_evaluation_slice (needs only Bronze/Silver metadata, ready now)

gold_driving_clip, gold_video_quality_sample and gold_vlm_training_sample
need actual video clips (Phase 3) and quality/motion-consistency scores
(Phase 4's new operator) that don't exist yet -- deferred rather than
populated with placeholder content.

Usage:
    python iceberg/build_gold.py --warehouse-dir warehouse/iceberg_warehouse
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from spark_session import build_spark  # noqa: E402

NAMESPACE = "local.gold"
SQL_DIR = os.path.join(os.path.dirname(__file__), "sql", "gold")

TABLE_SPECS = [
    ("long_tail_scene", "gold_long_tail_scene.sql", ["scene_token"]),
    ("evaluation_slice", "gold_evaluation_slice.sql", ["scene_token"]),
]


def read_sql(sql_file):
    with open(os.path.join(SQL_DIR, sql_file)) as f:
        return f.read()


def ensure_table(spark, table_name, df):
    columns_sql = ", ".join(f"`{f.name}` {f.dataType.simpleString()}" for f in df.schema.fields)
    spark.sql(f"CREATE TABLE IF NOT EXISTS {NAMESPACE}.{table_name} ({columns_sql}) USING iceberg")


def merge_table(spark, table_name, df, key_columns):
    df.createOrReplaceTempView(f"src_{table_name}")
    on_clause = " AND ".join(f"t.{k} = s.{k}" for k in key_columns)
    spark.sql(f"""
        MERGE INTO {NAMESPACE}.{table_name} t
        USING src_{table_name} s
        ON {on_clause}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)


def build_gold(spark):
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE}")
    counts = {}
    for table_name, sql_file, key_columns in TABLE_SPECS:
        df = spark.sql(read_sql(sql_file))
        ensure_table(spark, table_name, df)
        merge_table(spark, table_name, df, key_columns)
        counts[table_name] = spark.sql(f"SELECT COUNT(*) AS c FROM {NAMESPACE}.{table_name}").collect()[0]["c"]
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    args = parser.parse_args()

    spark = build_spark(args.warehouse_dir, app_name="iceberg-build-gold")
    counts = build_gold(spark)
    for name, count in counts.items():
        snap_count = spark.sql(f"SELECT COUNT(*) AS c FROM {NAMESPACE}.{name}.snapshots").collect()[0]["c"]
        print(f"{name}: {count} rows, {snap_count} snapshots")
    spark.stop()


if __name__ == "__main__":
    main()
