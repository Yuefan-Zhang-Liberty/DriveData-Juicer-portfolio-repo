"""Pre-load the Bronze reference/dimension tables (scene, sample,
calibrated_sensor, sensor, ego_pose) needed for the *same* trainval scenes
that flink/bag_simulator.py will stream sample_data for.

This is a deliberate scope boundary, not an oversight: Silver's
silver_sensor_frame.sql inner-joins sample_data against sample/scene/
calibrated_sensor/sensor/ego_pose, so if only sample_data were streamed, the
new rows would silently vanish from Silver rather than proving the "zero code
change downstream" claim. In a real system these dimension tables are
slowly-changing reference data (scene metadata, sensor calibration, ego
poses) loaded via batch/CDC well before the fact stream arrives -- exactly
what this script does, using the same batch tool (Spark) and the same
MERGE INTO idempotent-load pattern as iceberg/build_bronze.py. Only
sample_data itself -- the actual continuously-arriving measurement stream --
is reserved for flink/streaming_ingest.py to discover for the first time.

Usage:
    python flink/preload_bronze_dims.py \
        --warehouse-dir warehouse/iceberg_warehouse \
        --meta-root data/nuscenes_trainval_meta/v1.0-trainval \
        --num-scenes 20
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "iceberg"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spark"))
from spark_session import build_spark  # noqa: E402
from ingest_nuscenes import (  # noqa: E402
    SCENE_SCHEMA, SAMPLE_SCHEMA, CALIBRATED_SENSOR_SCHEMA, SENSOR_SCHEMA, EGO_POSE_SCHEMA,
)

sys.path.insert(0, os.path.dirname(__file__))
from bag_simulator import load_json, build_channel_map, build_scene_plan  # noqa: E402

NAMESPACE = "local.bronze"


def ensure_table(spark, table_name, schema):
    columns_sql = ", ".join(f"`{f.name}` {f.dataType.simpleString()}" for f in schema.fields)
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


def collect_referenced_tokens(plan):
    sample_tokens, cs_tokens, scene_tokens = set(), set(), set()
    for scene_token, _scene_name, rows in plan:
        scene_tokens.add(scene_token)
        for row in rows:
            sample_tokens.add(row["sample_token"])
            cs_tokens.add(row["calibrated_sensor_token"])
    return scene_tokens, sample_tokens, cs_tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--meta-root", required=True)
    parser.add_argument("--num-scenes", type=int, default=20)
    args = parser.parse_args()

    plan = build_scene_plan(args.meta_root, args.num_scenes)
    scene_tokens, sample_tokens, cs_tokens = collect_referenced_tokens(plan)

    scenes = [s for s in load_json(args.meta_root, "scene") if s["token"] in scene_tokens]
    samples = [s for s in load_json(args.meta_root, "sample") if s["token"] in sample_tokens]
    calibrated_sensors = [
        cs for cs in load_json(args.meta_root, "calibrated_sensor") if cs["token"] in cs_tokens
    ]
    sensor_tokens = {cs["sensor_token"] for cs in calibrated_sensors}
    sensors = [s for s in load_json(args.meta_root, "sensor") if s["token"] in sensor_tokens]

    ego_pose_tokens = {
        row["ego_pose_token"]
        for _st, _sn, rows in plan
        for row in rows
    }
    ego_poses = [e for e in load_json(args.meta_root, "ego_pose") if e["token"] in ego_pose_tokens]

    print(f"preloading dims for {len(scene_tokens)} scenes: "
          f"{len(samples)} samples, {len(calibrated_sensors)} calibrated_sensors, "
          f"{len(sensors)} sensors, {len(ego_poses)} ego_poses")

    spark = build_spark(args.warehouse_dir, app_name="preload-bronze-dims")
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE}")

    tables = [
        ("scene", SCENE_SCHEMA, scenes),
        ("sample", SAMPLE_SCHEMA, samples),
        ("calibrated_sensor", CALIBRATED_SENSOR_SCHEMA, calibrated_sensors),
        ("sensor", SENSOR_SCHEMA, sensors),
        ("ego_pose", EGO_POSE_SCHEMA, ego_poses),
    ]
    for table_name, schema, rows in tables:
        field_names = [f.name for f in schema.fields]
        tuples = [tuple(row[name] for name in field_names) for row in rows]
        df = spark.createDataFrame(tuples, schema=schema)
        ensure_table(spark, table_name, schema)
        merge_table(spark, table_name, df)
        count = spark.sql(f"SELECT COUNT(*) c FROM {NAMESPACE}.{table_name}").collect()[0]["c"]
        print(f"{table_name}: {count} total rows after merge")

    spark.stop()


if __name__ == "__main__":
    main()
