"""Phase-2 Iceberg experiments: idempotent rerun, time travel, schema
evolution, partition evolution, small-file compaction. Each experiment uses
a small dedicated demo table under local.audit so Bronze/Silver/Gold content
built by build_bronze.py / build_silver.py / build_gold.py is never touched.

Usage:
    python iceberg/experiments.py --warehouse-dir warehouse/iceberg_warehouse \
        --report benchmarks/reports/iceberg_week2_experiments.md
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from spark_session import build_spark  # noqa: E402

NAMESPACE = "local.audit"


def snapshot_count(spark, table):
    return spark.sql(f"SELECT COUNT(*) AS c FROM {table}.snapshots").collect()[0]["c"]


def file_count(spark, table):
    return spark.sql(f"SELECT COUNT(*) AS c FROM {table}.files").collect()[0]["c"]


def row_count(spark, table):
    return spark.sql(f"SELECT COUNT(*) AS c FROM {table}").collect()[0]["c"]


def experiment_idempotent_rerun(spark, results):
    table = f"{NAMESPACE}.idempotency_demo"
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    spark.sql(f"CREATE TABLE {table} (id INT, val STRING) USING iceberg")

    def merge_fixed_rows():
        spark.sql("""
            CREATE OR REPLACE TEMP VIEW src_idempotency AS
            SELECT * FROM VALUES (1, 'a'), (2, 'b'), (3, 'c') AS t(id, val)
        """)
        spark.sql(f"""
            MERGE INTO {table} t USING src_idempotency s ON t.id = s.id
            WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *
        """)

    merge_fixed_rows()
    rows_1, snaps_1 = row_count(spark, table), snapshot_count(spark, table)
    merge_fixed_rows()
    rows_2, snaps_2 = row_count(spark, table), snapshot_count(spark, table)

    results.append({
        "experiment": "idempotent_rerun",
        "rows_after_run_1": rows_1,
        "snapshots_after_run_1": snaps_1,
        "rows_after_run_2": rows_2,
        "snapshots_after_run_2": snaps_2,
        "idempotent": rows_1 == rows_2,
    })


def experiment_time_travel_and_schema_evolution(spark, results):
    table = f"{NAMESPACE}.time_travel_demo"
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    spark.sql(f"CREATE TABLE {table} (id INT, val STRING) USING iceberg")
    spark.sql(f"INSERT INTO {table} VALUES (1, 'original'), (2, 'original')")
    snap_before = spark.sql(f"SELECT snapshot_id FROM {table}.snapshots ORDER BY committed_at").collect()[-1]["snapshot_id"]

    spark.sql(f"UPDATE {table} SET val = 'changed' WHERE id = 1")
    current_val = spark.sql(f"SELECT val FROM {table} WHERE id = 1").collect()[0]["val"]
    time_travel_val = spark.sql(f"SELECT val FROM {table} VERSION AS OF {snap_before} WHERE id = 1").collect()[0]["val"]

    files_before_alter = file_count(spark, table)
    snaps_before_alter = snapshot_count(spark, table)
    spark.sql(f"ALTER TABLE {table} ADD COLUMN score DOUBLE")
    files_after_alter = file_count(spark, table)
    snaps_after_alter = snapshot_count(spark, table)
    new_column_value = spark.sql(f"SELECT score FROM {table} WHERE id = 1").collect()[0]["score"]

    results.append({
        "experiment": "time_travel",
        "snapshot_before_update": snap_before,
        "current_value_after_update": current_val,
        "value_read_via_time_travel": time_travel_val,
        "time_travel_recovers_old_value": time_travel_val == "original",
    })
    results.append({
        "experiment": "schema_evolution",
        "files_before_add_column": files_before_alter,
        "files_after_add_column": files_after_alter,
        "snapshots_before_add_column": snaps_before_alter,
        "snapshots_after_add_column": snaps_after_alter,
        "existing_row_new_column_value": new_column_value,
        "add_column_rewrote_no_data": files_before_alter == files_after_alter,
    })


def experiment_partition_evolution(spark, results):
    table = f"{NAMESPACE}.partition_evolution_demo"
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    spark.sql(f"CREATE TABLE {table} (scene_token STRING, val INT) USING iceberg PARTITIONED BY (bucket(4, scene_token))")
    spark.sql(f"INSERT INTO {table} VALUES ('scene-a', 1), ('scene-b', 2), ('scene-c', 3)")
    spec_counts_before = {
        r["spec_id"]: r["c"]
        for r in spark.sql(f"SELECT spec_id, COUNT(*) AS c FROM {table}.files GROUP BY spec_id").collect()
    }

    spark.sql(f"ALTER TABLE {table} ADD PARTITION FIELD truncate(4, scene_token)")
    spark.sql(f"INSERT INTO {table} VALUES ('scene-d', 4), ('scene-e', 5)")
    spec_counts_after = {
        r["spec_id"]: r["c"]
        for r in spark.sql(f"SELECT spec_id, COUNT(*) AS c FROM {table}.files GROUP BY spec_id").collect()
    }

    results.append({
        "experiment": "partition_evolution",
        "file_count_by_spec_id_after_batch_1": spec_counts_before,
        "file_count_by_spec_id_after_batch_2": spec_counts_after,
        "old_files_kept_old_spec": spec_counts_after.get(0) == spec_counts_before.get(0),
        "new_files_use_new_spec": 1 in spec_counts_after,
    })


def experiment_compaction(spark, results):
    table = f"{NAMESPACE}.compaction_demo"
    spark.sql(f"DROP TABLE IF EXISTS {table}")
    spark.sql(f"CREATE TABLE {table} (id INT, val STRING) USING iceberg")
    for i in range(20):
        spark.sql(f"INSERT INTO {table} VALUES ({i}, 'v{i}')")
    files_before = file_count(spark, table)

    rewrite_result = spark.sql(f"CALL local.system.rewrite_data_files(table => 'audit.compaction_demo')").collect()[0]
    files_after = file_count(spark, table)

    results.append({
        "experiment": "small_file_compaction",
        "files_before": files_before,
        "rewritten_data_files_count": rewrite_result["rewritten_data_files_count"],
        "added_data_files_count": rewrite_result["added_data_files_count"],
        "files_after": files_after,
    })


def write_report(results, report_path):
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    lines = ["# Phase 2 — Iceberg Experiments", ""]
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

    spark = build_spark(args.warehouse_dir, app_name="iceberg-experiments")
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {NAMESPACE}")

    results = []
    experiment_idempotent_rerun(spark, results)
    experiment_time_travel_and_schema_evolution(spark, results)
    experiment_partition_evolution(spark, results)
    experiment_compaction(spark, results)

    for r in results:
        print(r)
    write_report(results, args.report)
    spark.stop()


if __name__ == "__main__":
    main()
