# Phase 2 — Iceberg & Bronze/Silver/Gold Data Warehouse

Covers `plan.md` §11 (2026-09-03–09-09): converting Bronze into Iceberg tables,
building Silver/Gold on top, and demonstrating Iceberg's core mechanics
(idempotent writes, snapshots/time travel, schema evolution, partition
evolution, compaction) plus a data-quality audit table.

## Setup

- **Catalog**: Iceberg Hadoop catalog `local`, warehouse at
  `warehouse/iceberg_warehouse` (pure filesystem — no Hive metastore process
  available in this no-sudo environment; see `docs/architecture.md`
  environment-deviation notes). Config lives in `iceberg/spark_session.py`,
  shared by every script in this phase.
- **Namespaces**: `local.bronze`, `local.silver`, `local.gold`, `local.audit`.
- **Idempotency mechanism**: every load is `MERGE INTO ... ON <key> WHEN
  MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *`, keyed on each
  table's natural key. This is the concrete contrast with Phase 1's
  `df.write.mode("overwrite")`, which has no such guarantee and no history.

## Tables built

**Bronze** (11 tables, `iceberg/build_bronze.py`, `MERGE INTO local.bronze.<name>` keyed on `token`):
scene, sample, sample_data, ego_pose, calibrated_sensor, sample_annotation,
category, sensor, log, instance, visibility.

Verified idempotent by running the build twice: row counts identical both
times (scene=10, sample=404, sample_data=31206, ego_pose=31206,
calibrated_sensor=120, sample_annotation=18538, category=23, sensor=12,
log=8, instance=911, visibility=4), while snapshot count went 1→2 on every
table.

**Silver** (7 tables, `iceberg/build_silver.py`):

| table | key | rows |
|---|---|---|
| silver_sensor_frame | sample_data_token | 31206 |
| silver_camera_frame | sample_data_token | 14008 |
| silver_lidar_frame | sample_data_token | 3935 |
| silver_ego_motion | ego_pose_token | 3925 |
| silver_object_annotation | sample_annotation_token | 18538 |
| silver_sensor_alignment | scene_token, camera_channel | 60 |
| silver_scene_quality | scene_token | 10 |

Cross-checked against Phase 1: `silver_lidar_frame` (3935 LIDAR_TOP frames)
minus 10 scenes (one non-keyframe first frame each) = 3925 `silver_ego_motion`
rows, matching the adjacent-frame-displacement logic from Phase 1 query 5.
Rerun twice, same idempotency pattern as Bronze (row counts unchanged, 1→2
snapshots per table).

**Gold** (2 of the 5 named tables in scope — honest scoping, see below):

- `gold_long_tail_scene` (key: scene_token, 10 rows) — Phase 1 query 7
  materialized. Per-scene long-tail annotation counts match Phase 1's raw
  output range (scene-0916=381 down to scene-1077=51); all 10 scenes flagged
  `is_long_tail_scene=true` in this 10-scene sample.
- `gold_evaluation_slice` (key: scene_token, 10 rows) — train/val split
  assigned **per log** (`crc32(log_token) % 5 = 4 → val`, else `train`),
  fixing the leakage risk Phase 1 query 9 flagged (a log with multiple scenes
  could otherwise straddle both splits). Result: train=4, val=6; leakage
  check (`GROUP BY log_token HAVING COUNT(DISTINCT split) > 1`) returned
  **zero rows**.

`gold_driving_clip`, `gold_video_quality_sample`, `gold_vlm_training_sample`
are **deferred** — they depend on actual video clips (Phase 3, video
extraction) and quality scores (Phase 4, the new Data-Juicer operator) that
don't exist yet. Building them now would mean placeholder content, which
this project avoids (same principle as the Phase 1 Spark-UI-screenshot
substitution being flagged explicitly rather than silently skipped).

## Data quality audit

`local.audit.dq_results` — append-only Iceberg table
(`run_ts, check_name, scope_key, metric_value, status, detail`), one row per
check per scope. Every run appends a new batch instead of overwriting, so DQ
history accumulates.

8 checks (`iceberg/dq_checks.py` + `iceberg/sql/dq/*.sql`):

| check | scope | result |
|---|---|---|
| fk_integrity | 4 relationship checks (sample→scene, sample_data→sample, sample_annotation→sample, instance→category) | 0 orphans, all PASS |
| sensor_missing_rate | per scene (10 scenes) | 1.0 keyframe coverage vs. 12 expected sensors, all PASS |
| timestamp_monotonicity | per scene (10 scenes) | 0.0 non-increasing links, all PASS |
| ego_pose_jumps | per scene (10 scenes) | 0.0 frames with implied speed > 40 m/s, all PASS |
| calibration_validity | 3 sub-checks (camera intrinsic shape/focal, calibrated_sensor rotation norm, ego_pose rotation norm) | 0.0 violations, all PASS |
| sensor_alignment_deviation | scene × camera channel (60 pairs) | max camera/LiDAR timestamp diff ranges ~1.2–48.3 ms, all within threshold, PASS |
| frame_duplication_rate | 2 sub-checks (duplicate channel+timestamp, duplicate filename) — metadata-level proxy, not pixel dedup; true perceptual dedup deferred to Data-Juicer ops in Phase 3 | 0.0 duplicates, both PASS |
| split_leakage | logs spanning multiple splits | 0.0, PASS |

**Result: 0 FAIL rows out of 100 total DQ rows** on the first run. Rerunning
appended another 100 rows (200 total, 16 snapshots — 8 checks × 2 runs),
confirming the append-only design: DQ history is never overwritten, unlike a
`CREATE OR REPLACE TABLE` approach would produce.

## Experiments (`iceberg/experiments.py`)

Each experiment uses a dedicated demo table under `local.audit` so
Bronze/Silver/Gold content is never touched.

1. **Idempotent rerun** (`idempotency_demo`) — same 3-row `MERGE INTO` run
   twice: rows stayed at 3 both times, snapshots went 1 → 2. Confirms
   `MERGE INTO` is idempotent on data but still versioned.
2. **Time travel** (`time_travel_demo`) — inserted 2 rows, captured snapshot
   id `4685380735047462271`, then `UPDATE`d `id=1`'s value from `'original'`
   to `'changed'`. Current read returns `'changed'`; `SELECT ... VERSION AS
   OF 4685380735047462271` returns `'original'` — the pre-update state is
   fully recoverable.
3. **Schema evolution** (same table) — `ALTER TABLE ... ADD COLUMN score
   DOUBLE`: file count stayed at 2, snapshot count stayed at 2 (no new
   snapshot, no data rewrite — pure metadata operation). Existing row reads
   back `score = NULL` for the new column.
4. **Partition evolution** (`partition_evolution_demo`, `PARTITIONED BY
   (bucket(4, scene_token))`) — batch 1 (3 rows) wrote files under
   `spec_id=0` (`{0: 2}`). After `ALTER TABLE ... ADD PARTITION FIELD
   truncate(4, scene_token)`, batch 2 (2 rows) wrote files under the new
   `spec_id=1`, while batch 1's files stayed at `spec_id=0`
   (`{0: 2, 1: 2}`) — old data files keep their original layout; only new
   writes use the new partition spec.
5. **Small-file compaction** (`compaction_demo`) — 20 single-row `INSERT
   INTO` statements produced 20 data files. `CALL
   local.system.rewrite_data_files(table => 'audit.compaction_demo')`
   reported `rewritten_data_files_count=20, added_data_files_count=1`; file
   count after: **1**.

Raw output also saved to `benchmarks/reports/iceberg_week2_experiments.md`.

## Iceberg vs. plain Parquet, a traditional database, and Hive tables

- **vs. plain Parquet** (Phase 1's approach): plain Parquet is just files in
  a directory — there's no metadata layer, so there's no snapshot isolation,
  no safe concurrent writes (two overlapping writers can corrupt a
  directory listing), and `df.write.mode("overwrite")` has no history: once
  it runs, the previous data is gone. Iceberg adds a metadata layer
  (manifests + snapshots) on top of the same file formats, so every write is
  atomic and versioned, and old snapshots stay queryable until explicitly
  expired.
- **vs. a traditional (row-store) database**: a database like Postgres owns
  its own storage engine — row-oriented pages, its own file format, tied to
  one running server process. Iceberg is a table *format*, not a database:
  it's columnar (Parquet/ORC/Avro underneath), lives directly on object
  storage/HDFS, and any engine (Spark, Trino, Flink) can read or write the
  same table without going through a database server. Time travel is native
  to Iceberg's snapshot model; most OLTP databases have no equivalent
  without bolting on temporal tables or WAL replay.
- **vs. a Hive table**: Hive tracks a table's contents by *listing files
  under a partition directory* — correctness depends on directory listing
  being consistent, renames being atomic (often false on object storage),
  and adding a partition meaning a physical subdirectory. Iceberg tracks
  every data file explicitly in a manifest, so there's no directory listing
  at read time, no reliance on atomic renames, and partition evolution
  (this phase's experiment 4) changes how *new* data is organized without
  touching or requiring a rewrite of existing files — something a
  Hive-partitioned table can't do without a full data migration.

## Known limitations / honest scoping

- Only 2 of the 5 Gold tables named in `plan.md` are built now; the other 3
  need artifacts from Phase 3/4 (see Gold section above).
- `frame_duplication_rate` is a metadata-level proxy (duplicate records by
  channel+timestamp or filename), not true pixel/perceptual duplicate
  detection — that requires decoding video frames, which is Phase 3/4's job
  via Data-Juicer's dedup operators.
- Dataset is still the 10-scene nuScenes mini sample from Phase 0/1; all row
  counts above scale with that sample size, not the full nuScenes dataset.

## Files

- `iceberg/spark_session.py`, `iceberg/build_bronze.py`,
  `iceberg/build_silver.py`, `iceberg/build_gold.py`, `iceberg/dq_checks.py`,
  `iceberg/experiments.py`
- `iceberg/sql/{silver,gold,dq}/*.sql`
- `benchmarks/reports/iceberg_week2_experiments.md` (raw experiment output)
