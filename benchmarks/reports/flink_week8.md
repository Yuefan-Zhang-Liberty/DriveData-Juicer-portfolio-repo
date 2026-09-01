# Phase 8 Report: Flink Streaming Ingestion into the Shared Iceberg Bronze Table (Kappa Architecture Demo)

## Motivation

Phases 1-6 built a batch-only pipeline: Spark ingests nuScenes metadata into Bronze,
builds Silver/Gold, and Ray runs Data-Juicer filtering over the derived clips. That
architecture assumes the full dataset is already sitting on disk before any job runs.
Real AV fleets don't work that way — driving-log "bags" arrive continuously as vehicles
finish routes and upload to object storage, not as one big batch. A production system
needs an incremental ingestion layer so a newly-arrived bag becomes queryable within
seconds, not at the next scheduled batch run.

This is the classic Kappa/Lambda pattern: a low-latency streaming path handles new data
as it arrives, a batch path keeps doing large-scale reprocessing (Silver/Gold
re-aggregation), and both write to the *same* table. Apache Iceberg's snapshot isolation
is explicitly designed to support exactly this — concurrent batch and stream writers on
one table, each producing its own linearizable snapshot history. This phase adds Flink
as the streaming half of that pattern, sharing the Bronze `sample_data` table Spark's
batch ETL (`iceberg/build_bronze.py`) already owns.

## What's simplified vs. production, disclosed up front

| Simplification here | What production would do |
|---|---|
| Flink `FileSource` in continuous-monitoring mode watching a local landing directory | A message queue (Kafka/Pulsar) as the durable, replayable ingestion buffer |
| Only 1 of the 8 batch DQ checks (`timestamp_monotonicity`) ported to streaming form | All checks with a meaningful per-record streaming form ported; full-table checks (fk_integrity, split_leakage) stay batch-only regardless of scale |
| A bounded, scripted demo run (`flink/run_streaming_demo.sh`: start job, run simulator, grace period, stop job) | A long-lived, supervised streaming job (e.g. under Flink's Application Mode with HA and restart policies) |
| "Bag" = one scene's CAM_FRONT `sample_data` rows, simulated by `flink/bag_simulator.py` from real, previously-un-ingested trainval metadata | Actual bag files uploaded by vehicles, parsed by a real bag-reader |
| Bronze reference/dimension tables (scene, sample, calibrated_sensor, sensor, ego_pose) for the streamed scenes pre-loaded via a batch script (`flink/preload_bronze_dims.py`) before the demo | Slowly-changing dimension tables loaded via their own batch/CDC pipeline, independently of and ahead of the fact-table stream — same shape, just running continuously in production instead of as a one-off script |

None of these are load-bearing shortcuts around the actual technical claim — the claim is
"two engines, two write paths, one physical Iceberg table, verified by snapshot history,"
and every simplification above is orthogonal to that.

## Environment

| Item | Value |
|---|---|
| Flink | PyFlink 1.18.1 |
| Iceberg connector | `iceberg-flink-runtime-1.18:1.7.1` (Spark side stays on `iceberg-spark-runtime-3.3_2.12:1.4.3` — different library versions against the same table format, confirmed compatible) |
| Catalog | Hadoop catalog, same `warehouse/iceberg_warehouse` path as Spark, catalog name `local_iceberg` on the Flink side vs. `local` on the Spark side (same physical location) |
| Hadoop classpath | Reused directly from the shared `.venv`'s `pyspark/jars/*` via `HADOOP_CLASSPATH` — no separate Hadoop install |
| Checkpointing | Enabled at 5s intervals — required for the Iceberg Flink sink's two-phase commit; without it, writes buffer but never commit a snapshot |

Installing `apache-flink==1.18.1` into the shared `.venv` downgraded several dependencies
also used by pyspark/ray (numpy 2.2.6→1.24.4, pyarrow 25.0.1→11.0.0, protobuf, py4j, dill).
This was verified, not assumed safe: re-running `iceberg/dq_checks.py` against the
existing warehouse after the downgrade still produced `0 FAIL rows out of 100 total DQ
rows`, confirming no regression to the Phase 1-6 pipeline.

## Demo results

Run: `flink/run_streaming_demo.sh --num-scenes 20 --interval-seconds 10 --inject-faults`
against the real project warehouse (`warehouse/iceberg_warehouse`), streaming 20 real,
previously-un-ingested nuScenes trainval scenes (scene-0001 .. scene-0020) one at a time
into a landing directory monitored by `flink/streaming_ingest.py`.

- **20/20 bags landed and ingested.** 4,565 `sample_data` rows written by the Flink job
  into `local.bronze.sample_data`, landing-to-queryable latency bounded by the 5s
  checkpoint interval (each bag typically became queryable within one checkpoint of
  landing).
- **Fault injection and detection, exact match.** `bag_simulator.py --inject-faults`
  swapped one timestamp pair in every 5th scene (scene-0005, scene-0010, scene-0015,
  scene-0020). The streaming `TimestampMonotonicityCheck` (per-scene `KeyedProcessFunction`
  holding `last_ts` in Flink keyed state) flagged **exactly 4** rows as `FAIL`, one per
  faulted scene, each with the correct out-of-order token/timestamp pair recorded in
  `local.audit.dq_results` — the same table and schema the batch `iceberg/dq_checks.py`
  already writes to, tagged `check_name='timestamp_monotonicity_stream'`. All 16
  non-faulted scenes produced zero false positives.
- **Dual-engine snapshot authorship — the core claim, directly verified.**
  `local.bronze.sample_data.snapshots` shows 20 new snapshots with
  `summary['engine-name'] = 'flink'` (`engine-version = 1.18.1`,
  `iceberg-version = Apache Iceberg 1.7.1`) appended alongside the pre-existing
  Spark-authored snapshots from Phases 1-6 — two independent engines, two independent
  write paths, one physical table.
- **Zero-code-change downstream propagation, directly verified.** Re-running the existing
  batch `iceberg/build_silver.py` unmodified picked up all 20 newly-streamed scenes: e.g.
  `local.silver.camera_frame` shows 223 CAM_FRONT rows for scene-0005 (224 raw rows minus
  the 1 excluded out-of-order row) with no changes to `silver_camera_frame.sql` or
  `silver_sensor_frame.sql`.
- All 4 checks in `flink/verify_streaming_ingest.py` reported **PASS** against the real
  warehouse after the run.

## Honesty note: decoupled from the in-progress blob transfer

This demo used already-downloaded trainval **metadata** (`sample_data.json`, etc.), not
the camera-image blobs that were being transferred to this host in parallel while this
phase was implemented. The two are independent artifacts — metadata ingestion doesn't
need the JPEGs to exist on disk — so this ran as a genuine "previously-un-ingested real
data landing for the first time" demo (Bronze only had the 10 mini scenes before this),
just not literally synchronized with that unrelated network transfer.

## Next

Once the trainval blob transfer completes and passes integrity verification, rerun the
full pipeline (Spark/Iceberg ETL → Data-Juicer filtering → Ray benchmark → VLM QLoRA
ablation) at trainval scale, independently of this phase.
