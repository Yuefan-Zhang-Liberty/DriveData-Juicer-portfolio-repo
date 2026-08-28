"""Phase 5 benchmark: Local vs Ray executor at 1 / 2 / 4 worker concurrency.

Runs the 5-op Data-Juicer pipeline over the tier-20 manifest under four
execution configurations, measures wall-clock time, and emits a Markdown
timing table.

Usage (from project root, with data-juicer venv active and ray head running):
    python data_juicer/run_ray_benchmark.py

Ray concurrency is controlled via num_proc on the two most expensive ops
(video_motion_score_filter and video_camera_motion_consistency_filter). Local
mode always uses auto_op_parallelism: false (1 worker).

Output: benchmarks/reports/ray_week5_timing.json  (raw)
        printed Markdown table (copy-paste into ray_week5.md)
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_TIER20 = os.path.join(PROJECT_ROOT, "data_juicer/manifests/gold_manifest_20.jsonl")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data_juicer/outputs/benchmark")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "benchmarks/reports")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


def count_manifest(path: str) -> int:
    with open(path) as f:
        return sum(1 for _ in f)


def make_local_yaml(tmp_dir: str) -> str:
    config = {
        "project_name": "benchmark-local",
        "dataset_path": MANIFEST_TIER20,
        "export_path": os.path.join(OUTPUT_DIR, "local_result.jsonl"),
        "work_dir": os.path.join(OUTPUT_DIR, "local_workdir"),
        "open_tracer": False,
        "process": [
            {"video_duration_filter": {"min_duration": 1, "max_duration": 5, "auto_op_parallelism": False}},
            {"video_aspect_ratio_filter": {"min_ratio": "1/2", "max_ratio": "2/1", "any_or_all": "any", "auto_op_parallelism": False}},
            {"video_resolution_filter": {"min_width": 800, "max_width": 4096, "min_height": 400, "max_height": 4096, "any_or_all": "any", "auto_op_parallelism": False}},
            {"video_motion_score_filter": {"min_score": 0.25, "sampling_fps": 2, "any_or_all": "any", "auto_op_parallelism": False}},
            {"video_camera_motion_consistency_filter": {"min_consistency": 0.05, "any_or_all": "any", "auto_op_parallelism": False}},
        ],
    }
    path = os.path.join(tmp_dir, "benchmark_local.yaml")
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


def make_ray_yaml(tmp_dir: str, num_proc: int, label: str) -> str:
    config = {
        "project_name": f"benchmark-ray-{label}",
        "dataset_path": MANIFEST_TIER20,
        "export_path": os.path.join(OUTPUT_DIR, f"ray_{label}_result.jsonl"),
        "work_dir": os.path.join(OUTPUT_DIR, f"ray_{label}_workdir"),
        "executor_type": "ray",
        "ray_address": "auto",
        "open_tracer": False,
        "process": [
            {"video_duration_filter": {"min_duration": 1, "max_duration": 5}},
            {"video_aspect_ratio_filter": {"min_ratio": "1/2", "max_ratio": "2/1", "any_or_all": "any"}},
            {"video_resolution_filter": {"min_width": 800, "max_width": 4096, "min_height": 400, "max_height": 4096, "any_or_all": "any"}},
            {"video_motion_score_filter": {"min_score": 0.25, "sampling_fps": 2, "any_or_all": "any", "num_proc": num_proc}},
            {"video_camera_motion_consistency_filter": {"min_consistency": 0.05, "any_or_all": "any", "num_proc": num_proc}},
        ],
    }
    path = os.path.join(tmp_dir, f"benchmark_ray_{label}.yaml")
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


def run_config(yaml_path: str, env: dict | None = None) -> float:
    start = time.perf_counter()
    result = subprocess.run(
        ["dj-process", "--config", yaml_path],
        cwd=PROJECT_ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        print(f"  WARNING: dj-process exited {result.returncode}", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
    return elapsed


def main():
    n_clips = count_manifest(MANIFEST_TIER20)
    print(f"Manifest: {MANIFEST_TIER20} ({n_clips} clips)\n")

    configs = []
    timings = []

    with tempfile.TemporaryDirectory() as tmp:
        configs = [
            ("Local (1 proc, fork)", make_local_yaml(tmp), {"MP_START_METHOD": "fork"}),
            ("Ray (num_proc=1)", make_ray_yaml(tmp, 1, "np1"), None),
            ("Ray (num_proc=2)", make_ray_yaml(tmp, 2, "np2"), None),
            ("Ray (num_proc=4)", make_ray_yaml(tmp, 4, "np4"), None),
        ]

        for label, yaml_path, env in configs:
            print(f"Running {label}...")
            elapsed = run_config(yaml_path, env)
            vpm = n_clips / elapsed * 60
            timings.append({"label": label, "elapsed_s": round(elapsed, 2), "videos_per_min": round(vpm, 1)})
            print(f"  {elapsed:.1f}s  ({vpm:.1f} videos/min)")

    # Emit JSON
    raw_path = os.path.join(REPORTS_DIR, "ray_week5_timing.json")
    with open(raw_path, "w") as f:
        json.dump({"n_clips": n_clips, "timings": timings}, f, indent=2)
    print(f"\nRaw timing saved to {raw_path}")

    # Emit Markdown table
    print("\n## Benchmark results\n")
    print("| Executor | Clips | Total (s) | Videos/min |")
    print("|---|---|---|---|")
    for t in timings:
        print(f"| {t['label']} | {n_clips} | {t['elapsed_s']} | {t['videos_per_min']} |")


if __name__ == "__main__":
    main()
