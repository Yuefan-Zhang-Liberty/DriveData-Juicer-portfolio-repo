"""Stream driving-log bags from a landing directory into the shared Iceberg
Bronze table, with a lightweight real-time timestamp-monotonicity check.

This is the Flink half of the Kappa-architecture demo: bag_simulator.py drops
one JSONL file per scene into --landing-dir as if bags were arriving from a
fleet upload pipeline; this job continuously monitors that directory, parses
each bag, checks per-scene timestamp ordering with keyed state, and writes
valid rows into local_iceberg.bronze.sample_data -- the exact same Iceberg
table Spark's batch ETL (iceberg/build_bronze.py) already reads and writes.
Rows that fail the check are instead appended to local_iceberg.audit.dq_results
(check_name='timestamp_monotonicity_stream'), reusing the schema the batch
iceberg/dq_checks.py already writes to.

There is no PyFlink API to emit into a Java-style side output from inside
process_element in this version, so both outcomes flow through a single
KeyedProcessFunction output tagged with a dq_status field, then split with two
plain DataStream.filter() calls -- simpler than side outputs and just as
correct for this use case.

Usage:
    mkdir -p flink/jars && curl -sSL -o flink/jars/iceberg-flink-runtime-1.18-1.7.1.jar \
        "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-flink-runtime-1.18/1.7.1/iceberg-flink-runtime-1.18-1.7.1.jar"
    python flink/streaming_ingest.py \
        --warehouse-dir warehouse/iceberg_warehouse \
        --landing-dir data/bag_landing \
        --monitor-interval-seconds 2
"""
import argparse
import glob
import json
import os
import time

from pyflink.common import Duration, Row
from pyflink.common.watermark_strategy import WatermarkStrategy
from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.file_system import FileSource, StreamFormat
from pyflink.datastream.functions import KeyedProcessFunction
from pyflink.datastream.state import ValueStateDescriptor
from pyflink.table import StreamTableEnvironment

SAMPLE_DATA_FIELDS = [
    "token", "sample_token", "ego_pose_token", "calibrated_sensor_token",
    "timestamp", "fileformat", "is_key_frame", "height", "width",
    "filename", "prev", "next",
]

BAG_ROW_TYPE = Types.ROW_NAMED(
    SAMPLE_DATA_FIELDS + ["scene_token", "scene_name"],
    [
        Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(),
        Types.LONG(), Types.STRING(), Types.BOOLEAN(), Types.INT(), Types.INT(),
        Types.STRING(), Types.STRING(), Types.STRING(),
        Types.STRING(), Types.STRING(),
    ],
)

CHECKED_ROW_TYPE = Types.ROW_NAMED(
    SAMPLE_DATA_FIELDS + ["scene_token", "scene_name", "dq_status", "dq_detail"],
    [
        Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(),
        Types.LONG(), Types.STRING(), Types.BOOLEAN(), Types.INT(), Types.INT(),
        Types.STRING(), Types.STRING(), Types.STRING(),
        Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(),
    ],
)

DQ_RESULTS_TYPE = Types.ROW_NAMED(
    ["run_ts", "check_name", "scope_key", "metric_value", "status", "detail"],
    [Types.DOUBLE(), Types.STRING(), Types.STRING(), Types.DOUBLE(), Types.STRING(), Types.STRING()],
)


def parse_bag_line(line):
    d = json.loads(line)
    return Row(
        token=d["token"],
        sample_token=d["sample_token"],
        ego_pose_token=d["ego_pose_token"],
        calibrated_sensor_token=d["calibrated_sensor_token"],
        timestamp=d["timestamp"],
        fileformat=d["fileformat"],
        is_key_frame=d["is_key_frame"],
        height=d["height"],
        width=d["width"],
        filename=d["filename"],
        prev=d["prev"],
        next=d["next"],
        scene_token=d["scene_token"],
        scene_name=d["scene_name"],
    )


class TimestampMonotonicityCheck(KeyedProcessFunction):
    """Per-scene keyed check: flag any sample_data row whose timestamp is
    smaller than the largest timestamp already seen for that scene."""

    def open(self, runtime_context):
        self.last_ts_state = runtime_context.get_state(
            ValueStateDescriptor("last_ts", Types.LONG())
        )

    def process_element(self, value, ctx):
        last_ts = self.last_ts_state.value()
        ts = value.timestamp
        fields = {k: getattr(value, k) for k in SAMPLE_DATA_FIELDS + ["scene_token", "scene_name"]}

        if last_ts is not None and ts < last_ts:
            detail = f"token={value.token} ts={ts} < prior max ts={last_ts} in scene={value.scene_name}"
            yield Row(**fields, dq_status="FAIL", dq_detail=detail)
        else:
            self.last_ts_state.update(ts)
            yield Row(**fields, dq_status="PASS", dq_detail="")


def to_bronze_row(r):
    return Row(**{k: getattr(r, k) for k in SAMPLE_DATA_FIELDS})


def to_dq_result_row(r):
    return Row(
        run_ts=time.time(),
        check_name="timestamp_monotonicity_stream",
        scope_key=r.scene_token,
        metric_value=float(r.timestamp),
        status=r.dq_status,
        detail=r.dq_detail,
    )


def build_hadoop_jars(pyspark_dir):
    pyspark_jars = os.path.join(pyspark_dir, "jars")
    return sorted(glob.glob(os.path.join(pyspark_jars, "*.jar")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--landing-dir", required=True)
    parser.add_argument("--iceberg-flink-jar", default="flink/jars/iceberg-flink-runtime-1.18-1.7.1.jar")
    parser.add_argument("--monitor-interval-seconds", type=float, default=2.0)
    args = parser.parse_args()

    warehouse_dir = os.path.abspath(args.warehouse_dir)
    landing_dir = os.path.abspath(args.landing_dir)
    os.makedirs(landing_dir, exist_ok=True)

    import pyspark
    pyspark_dir = os.path.dirname(pyspark.__file__)
    hadoop_jars = build_hadoop_jars(pyspark_dir)
    if not hadoop_jars:
        raise RuntimeError(f"no pyspark jars found under {pyspark_dir}/jars")

    all_jars = [os.path.abspath(args.iceberg_flink_jar)] + hadoop_jars

    env = StreamExecutionEnvironment.get_execution_environment()
    env.add_jars(*[f"file://{p}" for p in all_jars])
    # The Iceberg sink commits a new snapshot on checkpoint completion (two-phase
    # commit); without checkpointing enabled it buffers writes and never commits,
    # no matter how long the job runs.
    env.enable_checkpointing(5000)

    table_env = StreamTableEnvironment.create(env)
    table_env.execute_sql(f"""
        CREATE CATALOG local_iceberg WITH (
            'type'='iceberg',
            'catalog-type'='hadoop',
            'warehouse'='{warehouse_dir}'
        )
    """)
    table_env.execute_sql("USE CATALOG local_iceberg")
    table_env.execute_sql("CREATE DATABASE IF NOT EXISTS audit")

    file_source = FileSource.for_record_stream_format(
        StreamFormat.text_line_format(), landing_dir
    ).monitor_continuously(
        Duration.of_seconds(int(args.monitor_interval_seconds))
    ).build()

    raw = env.from_source(file_source, WatermarkStrategy.no_watermarks(), "bag-source")
    parsed = raw.map(parse_bag_line, output_type=BAG_ROW_TYPE)
    checked = parsed.key_by(lambda r: r.scene_token).process(
        TimestampMonotonicityCheck(), output_type=CHECKED_ROW_TYPE
    )

    valid = checked.filter(lambda r: r.dq_status == "PASS").map(
        to_bronze_row, output_type=Types.ROW_NAMED(
            SAMPLE_DATA_FIELDS,
            [Types.STRING(), Types.STRING(), Types.STRING(), Types.STRING(),
             Types.LONG(), Types.STRING(), Types.BOOLEAN(), Types.INT(), Types.INT(),
             Types.STRING(), Types.STRING(), Types.STRING()],
        )
    )
    alerts = checked.filter(lambda r: r.dq_status == "FAIL").map(
        to_dq_result_row, output_type=DQ_RESULTS_TYPE
    )

    valid_view = table_env.from_data_stream(valid)
    table_env.create_temporary_view("valid_bags", valid_view)

    alerts_view = table_env.from_data_stream(alerts)
    table_env.create_temporary_view("bag_alerts", alerts_view)

    # Both inserts must run as one Flink job (a StatementSet) sharing the same
    # source/process pipeline -- two separate execute_sql() calls would each
    # submit their own job and read the landing directory independently.
    statements = table_env.create_statement_set()
    statements.add_insert_sql("""
        INSERT INTO local_iceberg.bronze.sample_data
        SELECT token, sample_token, ego_pose_token, calibrated_sensor_token,
               `timestamp`, fileformat, is_key_frame, height, width, filename, `prev`, `next`
        FROM valid_bags
    """)
    statements.add_insert_sql("""
        INSERT INTO local_iceberg.audit.dq_results
        SELECT run_ts, check_name, scope_key, metric_value, status, detail
        FROM bag_alerts
    """)
    result = statements.execute()
    print("streaming job submitted, monitoring", landing_dir, "-- kill this process to stop it")
    # The FileSource never terminates in continuous-monitoring mode, so this
    # blocks forever; run_streaming_demo.sh stops the job by killing this process.
    result.wait()


if __name__ == "__main__":
    main()
