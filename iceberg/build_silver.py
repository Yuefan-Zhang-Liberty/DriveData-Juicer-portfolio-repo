"""Build Iceberg Silver tables by joining Bronze Iceberg tables.

Each table's transformation lives in iceberg/sql/silver/<name>.sql (reviewable,
diffable, same split as spark/sql/*.sql in Phase 1). Loads are idempotent
MERGE INTOs keyed on the natural key(s) listed in TABLE_SPECS below.

Usage:
    python iceberg/build_silver.py --warehouse-dir warehouse/iceberg_warehouse
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from spark_session import build_spark  # noqa: E402

NAMESPACE = "local.silver"
SQL_DIR = os.path.join(os.path.dirname(__file__), "sql", "silver")

# (table_name, sql_file, merge_key_columns). Order matters: sensor_frame must
# be built before camera_frame/lidar_frame; object_annotation and
# sensor_alignment must be built before scene_quality.
TABLE_SPECS = [
    ("sensor_frame", "silver_sensor_frame.sql", ["sample_data_token"]),
    ("camera_frame", "silver_camera_frame.sql", ["sample_data_token"]),
    ("lidar_frame", "silver_lidar_frame.sql", ["sample_data_token"]),
    ("ego_motion", "silver_ego_motion.sql", ["ego_pose_token"]),
    ("object_annotation", "silver_object_annotation.sql", ["sample_annotation_token"]),
    ("sensor_alignment", "silver_sensor_alignment.sql", ["scene_token", "camera_channel"]),
    ("scene_quality", "silver_scene_quality.sql", ["scene_token"]),
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


def build_silver(spark):
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

    spark = build_spark(args.warehouse_dir, app_name="iceberg-build-silver")
    counts = build_silver(spark)
    for name, count in counts.items():
        snap_count = spark.sql(f"SELECT COUNT(*) AS c FROM {NAMESPACE}.{name}.snapshots").collect()[0]["c"]
        print(f"{name}: {count} rows, {snap_count} snapshots")
    spark.stop()


if __name__ == "__main__":
    main()
