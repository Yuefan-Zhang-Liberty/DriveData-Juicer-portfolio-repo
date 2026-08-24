"""Ingest nuScenes mini metadata JSON into Spark DataFrames with explicit schemas.

Usage:
    python spark/ingest_nuscenes.py \
        --data-root /home/yuefan.zhang/Data_juicer/data/nuscenes \
        --output-dir /home/yuefan.zhang/Data_juicer/warehouse/bronze_parquet

Writes one Parquet dataset per nuScenes table under --output-dir and prints
row counts for a quick sanity check. No schema inference is used anywhere —
every table has an explicit StructType per the phase-1 requirement.
"""
import argparse
import os

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

SCENE_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("log_token", StringType(), False),
    StructField("nbr_samples", IntegerType(), False),
    StructField("first_sample_token", StringType(), False),
    StructField("last_sample_token", StringType(), False),
    StructField("name", StringType(), False),
    StructField("description", StringType(), True),
])

SAMPLE_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("timestamp", LongType(), False),
    StructField("prev", StringType(), True),
    StructField("next", StringType(), True),
    StructField("scene_token", StringType(), False),
])

SAMPLE_DATA_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("sample_token", StringType(), False),
    StructField("ego_pose_token", StringType(), False),
    StructField("calibrated_sensor_token", StringType(), False),
    StructField("timestamp", LongType(), False),
    StructField("fileformat", StringType(), False),
    StructField("is_key_frame", BooleanType(), False),
    StructField("height", IntegerType(), False),
    StructField("width", IntegerType(), False),
    StructField("filename", StringType(), False),
    StructField("prev", StringType(), True),
    StructField("next", StringType(), True),
])

EGO_POSE_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("timestamp", LongType(), False),
    StructField("rotation", ArrayType(DoubleType()), False),
    StructField("translation", ArrayType(DoubleType()), False),
])

CALIBRATED_SENSOR_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("sensor_token", StringType(), False),
    StructField("translation", ArrayType(DoubleType()), False),
    StructField("rotation", ArrayType(DoubleType()), False),
    StructField("camera_intrinsic", ArrayType(ArrayType(DoubleType())), True),
])

SAMPLE_ANNOTATION_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("sample_token", StringType(), False),
    StructField("instance_token", StringType(), False),
    StructField("visibility_token", StringType(), False),
    StructField("attribute_tokens", ArrayType(StringType()), True),
    StructField("translation", ArrayType(DoubleType()), False),
    StructField("size", ArrayType(DoubleType()), False),
    StructField("rotation", ArrayType(DoubleType()), False),
    StructField("prev", StringType(), True),
    StructField("next", StringType(), True),
    StructField("num_lidar_pts", IntegerType(), False),
    StructField("num_radar_pts", IntegerType(), False),
])

CATEGORY_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("name", StringType(), False),
    StructField("description", StringType(), True),
])

SENSOR_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("channel", StringType(), False),
    StructField("modality", StringType(), False),
])

LOG_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("logfile", StringType(), False),
    StructField("vehicle", StringType(), False),
    StructField("date_captured", StringType(), False),
    StructField("location", StringType(), False),
])

INSTANCE_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("category_token", StringType(), False),
    StructField("nbr_annotations", IntegerType(), False),
    StructField("first_annotation_token", StringType(), False),
    StructField("last_annotation_token", StringType(), False),
])

VISIBILITY_SCHEMA = StructType([
    StructField("token", StringType(), False),
    StructField("level", StringType(), False),
    StructField("description", StringType(), True),
])

TABLES = {
    "scene": SCENE_SCHEMA,
    "sample": SAMPLE_SCHEMA,
    "sample_data": SAMPLE_DATA_SCHEMA,
    "ego_pose": EGO_POSE_SCHEMA,
    "calibrated_sensor": CALIBRATED_SENSOR_SCHEMA,
    "sample_annotation": SAMPLE_ANNOTATION_SCHEMA,
    "category": CATEGORY_SCHEMA,
    "sensor": SENSOR_SCHEMA,
    "log": LOG_SCHEMA,
    "instance": INSTANCE_SCHEMA,
    "visibility": VISIBILITY_SCHEMA,
}


def build_spark(app_name="nuscenes-ingest"):
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def load_table(spark, data_root, version, table_name):
    schema = TABLES[table_name]
    path = os.path.join(data_root, version, f"{table_name}.json")
    return spark.read.schema(schema).option("multiLine", True).json(path)


def ingest(spark, data_root, version, output_dir):
    counts = {}
    for table_name in TABLES:
        df = load_table(spark, data_root, version, table_name)
        out_path = os.path.join(output_dir, table_name)
        df.write.mode("overwrite").parquet(out_path)
        counts[table_name] = df.count()
        df.createOrReplaceTempView(table_name)
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True, help="nuScenes dataroot, e.g. .../data/nuscenes")
    parser.add_argument("--version", default="v1.0-mini")
    parser.add_argument("--output-dir", required=True, help="Where to write bronze Parquet tables")
    args = parser.parse_args()

    spark = build_spark()
    counts = ingest(spark, args.data_root, args.version, args.output_dir)
    for name, count in counts.items():
        print(f"{name}: {count} rows")
    spark.stop()


if __name__ == "__main__":
    main()
