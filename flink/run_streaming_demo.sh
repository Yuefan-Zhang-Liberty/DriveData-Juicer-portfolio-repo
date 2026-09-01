#!/usr/bin/env bash
# Bounded demo run of the Kappa-architecture ingestion pipeline:
# 1. start flink/streaming_ingest.py in the background, monitoring --landing-dir
# 2. run flink/bag_simulator.py in the foreground, dropping bags one at a time
# 3. wait a grace period so the last bag clears a checkpoint, then stop the job
#
# Usage:
#   flink/run_streaming_demo.sh \
#     --warehouse-dir warehouse/iceberg_warehouse \
#     --meta-root data/nuscenes_trainval_meta/v1.0-trainval \
#     --landing-dir data/bag_landing \
#     --num-scenes 20 --interval-seconds 10 --inject-faults
set -euo pipefail

WAREHOUSE_DIR=""
META_ROOT=""
LANDING_DIR=""
NUM_SCENES=20
INTERVAL_SECONDS=10
INJECT_FAULTS=""
GRACE_SECONDS=30
JOB_STARTUP_GRACE_SECONDS=90

while [[ $# -gt 0 ]]; do
  case "$1" in
    --warehouse-dir) WAREHOUSE_DIR="$2"; shift 2 ;;
    --meta-root) META_ROOT="$2"; shift 2 ;;
    --landing-dir) LANDING_DIR="$2"; shift 2 ;;
    --num-scenes) NUM_SCENES="$2"; shift 2 ;;
    --interval-seconds) INTERVAL_SECONDS="$2"; shift 2 ;;
    --inject-faults) INJECT_FAULTS="--inject-faults"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$WAREHOUSE_DIR" || -z "$META_ROOT" || -z "$LANDING_DIR" ]]; then
  echo "usage: $0 --warehouse-dir DIR --meta-root DIR --landing-dir DIR [--num-scenes N] [--interval-seconds S] [--inject-faults]" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate

HADOOP_CLASSPATH="$(python -c 'import pyspark, os; print(os.path.join(os.path.dirname(pyspark.__file__), "jars", "*"))')"
export HADOOP_CLASSPATH
export PYTHONUNBUFFERED=1

LOG_FILE="$(mktemp /tmp/flink_streaming_ingest.XXXXXX.log)"
echo "streaming_ingest.py log: $LOG_FILE"

python -u flink/streaming_ingest.py \
  --warehouse-dir "$WAREHOUSE_DIR" \
  --landing-dir "$LANDING_DIR" \
  > "$LOG_FILE" 2>&1 &
FLINK_PID=$!
echo "streaming_ingest.py started, pid=$FLINK_PID"

cleanup() {
  if kill -0 "$FLINK_PID" 2>/dev/null; then
    echo "stopping streaming_ingest.py (pid=$FLINK_PID)"
    kill "$FLINK_PID" 2>/dev/null || true
    wait "$FLINK_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "waiting up to ${JOB_STARTUP_GRACE_SECONDS}s for the Flink job to submit..."
for ((i = 0; i < JOB_STARTUP_GRACE_SECONDS; i++)); do
  if grep -q "streaming job submitted" "$LOG_FILE" 2>/dev/null; then
    echo "job submitted after ${i}s"
    break
  fi
  if ! kill -0 "$FLINK_PID" 2>/dev/null; then
    echo "streaming_ingest.py exited early -- see $LOG_FILE" >&2
    exit 1
  fi
  sleep 1
done

python flink/bag_simulator.py \
  --meta-root "$META_ROOT" \
  --landing-dir "$LANDING_DIR" \
  --num-scenes "$NUM_SCENES" \
  --interval-seconds "$INTERVAL_SECONDS" \
  $INJECT_FAULTS

echo "all bags landed, waiting ${GRACE_SECONDS}s grace period for the last checkpoint to commit..."
sleep "$GRACE_SECONDS"

echo "demo run complete. streaming_ingest.py log kept at: $LOG_FILE"
