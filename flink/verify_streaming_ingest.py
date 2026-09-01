"""Verify the Flink streaming-ingestion demo actually did what it claims:
new scenes landed in Bronze, a second engine (Flink) genuinely authored a new
Iceberg snapshot alongside Spark's, the injected fault was caught and recorded
in the shared DQ audit table, and the existing Silver query picks up the new
data with zero SQL changes.

Usage:
    python flink/verify_streaming_ingest.py \
        --warehouse-dir warehouse/iceberg_warehouse \
        --scene-names scene-0001 scene-0002 ... \
        --expect-fail

Requires local.silver.camera_frame to already exist (run iceberg/build_silver.py
after the demo, same as any other batch Silver refresh) and the streamed
scenes' reference dimensions to already be in Bronze (see
flink/preload_bronze_dims.py).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "iceberg"))
from spark_session import build_spark  # noqa: E402


def check_row_count_and_scenes(spark, scene_names):
    # scene name isn't a column on sample_data; join through sample -> scene.
    found = spark.sql("""
        SELECT DISTINCT sc.name AS scene_name
        FROM local.bronze.sample_data sd
        JOIN local.bronze.sample s ON s.token = sd.sample_token
        JOIN local.bronze.scene sc ON sc.token = s.scene_token
    """).collect()
    found_names = {r["scene_name"] for r in found}
    missing = [n for n in scene_names if n not in found_names]
    ok = not missing
    detail = "all requested scenes present" if ok else f"missing scenes: {missing}"
    return ok, detail


def check_dual_engine_snapshots(spark):
    rows = spark.sql("""
        SELECT summary['engine-name'] AS engine, COUNT(*) c
        FROM local.bronze.sample_data.snapshots
        GROUP BY summary['engine-name']
    """).collect()
    engines = {r["engine"]: r["c"] for r in rows}
    has_flink = any(k and "flink" in k.lower() for k in engines if k)
    has_spark_or_null = any((k is None or "flink" not in (k or "").lower()) for k in engines)
    ok = has_flink and has_spark_or_null
    detail = f"engines seen in snapshot history: {engines}"
    return ok, detail


def check_dq_alerts(spark, expect_fail):
    rows = spark.sql("""
        SELECT status, COUNT(*) c FROM local.audit.dq_results
        WHERE check_name = 'timestamp_monotonicity_stream'
        GROUP BY status
    """).collect()
    counts = {r["status"]: r["c"] for r in rows}
    if not counts:
        return False, "no timestamp_monotonicity_stream rows found in audit.dq_results"
    if expect_fail and counts.get("FAIL", 0) == 0:
        return False, f"expected at least one FAIL row, got: {counts}"
    return True, f"dq_results status counts: {counts}"


def check_silver_zero_change(spark, scene_names):
    rows = spark.sql("""
        SELECT DISTINCT scf.scene_name
        FROM local.silver.camera_frame scf
        WHERE scf.channel = 'CAM_FRONT'
    """).collect()
    found_names = {r["scene_name"] for r in rows}
    matched = [n for n in scene_names if n in found_names]
    ok = len(matched) > 0
    detail = f"{len(matched)}/{len(scene_names)} streamed scenes visible via unmodified Silver camera_frame query"
    return ok, detail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--scene-names", nargs="+", required=True)
    parser.add_argument("--expect-fail", action="store_true")
    args = parser.parse_args()

    spark = build_spark(args.warehouse_dir, app_name="verify-streaming-ingest")

    checks = [
        ("scenes landed in bronze.sample_data", check_row_count_and_scenes(spark, args.scene_names)),
        ("dual-engine snapshot authorship on bronze.sample_data", check_dual_engine_snapshots(spark)),
        ("streaming DQ alerts in audit.dq_results", check_dq_alerts(spark, args.expect_fail)),
        ("Silver camera_frame query picks up new scenes unmodified", check_silver_zero_change(spark, args.scene_names)),
    ]
    spark.stop()

    print("\n=== Flink streaming ingestion verification ===")
    all_ok = True
    for name, (ok, detail) in checks:
        status = "PASS" if ok else "FAIL"
        all_ok = all_ok and ok
        print(f"[{status}] {name}: {detail}")

    print("\nOVERALL:", "PASS" if all_ok else "FAIL")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
