"""Phase 6: Build A/B/C training splits for VLM attribution experiment.

Runs dj-process at three filter levels and intersects surviving clip_ids
with the caption file to produce train/val JSONL for each split.

Split A: no filter (all clips)
Split B: 4 existing ops (duration, aspect_ratio, resolution, motion_score)
Split C: 5 ops (B + camera_motion_consistency_filter)

Usage (from project root, with data-juicer venv on PATH):
    python vlm/build_splits.py \
        --captions vlm/captions/captions_full.jsonl \
        --manifest data_juicer/manifests/gold_manifest_full.jsonl \
        --output-dir vlm/data
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_BIN = os.path.join(PROJECT_ROOT, "data-juicer/.venv/bin")
DJ_PROCESS = os.path.join(VENV_BIN, "dj-process")


def load_captions(path: str) -> dict:
    captions = {}
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            captions[row["clip_id"]] = row
    return captions


def load_manifest(path: str) -> list:
    rows = []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            if row.get("clip_id") and row["clip_id"] != "corrupt-0":
                rows.append(row)
    return rows


def run_filter(manifest_path: str, yaml_path: str, output_path: str, env: dict) -> set:
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    result = subprocess.run(
        [DJ_PROCESS, "--config", yaml_path],
        cwd=PROJECT_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  dj-process exited {result.returncode}", file=sys.stderr)
        print(result.stderr[-1000:], file=sys.stderr)

    surviving = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                row = json.loads(line)
                cid = row.get("clip_id")
                if cid:
                    surviving.add(cid)
    return surviving


def make_yaml(tmp_dir: str, name: str, manifest: str, output: str, ops: list) -> str:
    config = {
        "project_name": f"split-{name}",
        "dataset_path": manifest,
        "export_path": output,
        "work_dir": os.path.join(tmp_dir, f"workdir_{name}"),
        "open_tracer": False,
        "process": ops,
    }
    path = os.path.join(tmp_dir, f"split_{name}.yaml")
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


def write_split(clip_ids: set, captions: dict, manifest_rows: list, output_dir: str, name: str):
    rows = [captions[cid] for cid in sorted(clip_ids) if cid in captions]
    # 80/20 train/val split by clip order (deterministic)
    split_point = int(len(rows) * 0.8)
    train_rows = rows[:split_point]
    val_rows = rows[split_point:]

    for subset, data in [("train", train_rows), ("val", val_rows)]:
        path = os.path.join(output_dir, f"{subset}_{name}.jsonl")
        with open(path, "w") as f:
            for row in data:
                f.write(json.dumps(row) + "\n")
        print(f"  {path}: {len(data)} rows")

    # Also write clip_id list for inspection
    splits_dir = os.path.join(os.path.dirname(output_dir), "splits")
    os.makedirs(splits_dir, exist_ok=True)
    with open(os.path.join(splits_dir, f"split_{name}.txt"), "w") as f:
        for cid in sorted(clip_ids):
            f.write(cid + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--captions", default="vlm/captions/captions_full.jsonl")
    parser.add_argument("--manifest", default="data_juicer/manifests/gold_manifest_full.jsonl")
    parser.add_argument("--filter-manifest", default="data_juicer/manifests/gold_manifest_100.jsonl",
                        help="Smaller manifest used for dj-process filter runs (B/C splits). "
                             "Using tier-100 here keeps filter runs tractable (~10 min); split A "
                             "uses all clips from --captions regardless of this value.")
    parser.add_argument("--output-dir", default="vlm/data")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    captions = load_captions(args.captions)
    manifest_rows = load_manifest(args.manifest)
    all_clip_ids = {r["clip_id"] for r in manifest_rows}
    manifest_abs = os.path.abspath(args.manifest)
    filter_manifest_abs = os.path.abspath(args.filter_manifest)

    local_env = {"MP_START_METHOD": "fork"}

    ops_B = [
        {"video_duration_filter": {"min_duration": 1, "max_duration": 5, "auto_op_parallelism": False}},
        {"video_aspect_ratio_filter": {"min_ratio": "1/2", "max_ratio": "2/1", "any_or_all": "any", "auto_op_parallelism": False}},
        {"video_resolution_filter": {"min_width": 800, "max_width": 4096, "min_height": 400, "max_height": 4096, "any_or_all": "any", "auto_op_parallelism": False}},
        {"video_motion_score_filter": {"min_score": 0.25, "sampling_fps": 2, "any_or_all": "any", "auto_op_parallelism": False}},
    ]
    ops_C = ops_B + [
        {"video_camera_motion_consistency_filter": {"min_consistency": 0.05, "any_or_all": "any", "auto_op_parallelism": False}},
    ]

    with tempfile.TemporaryDirectory() as tmp:
        # Split A: no filter
        print("Split A (no filter)...")
        split_A = all_clip_ids
        write_split(split_A, captions, manifest_rows, args.output_dir, "A")

        # Split B: 4 existing ops
        print("Split B (4 ops)...")
        out_B = os.path.join(tmp, "result_B.jsonl")
        yaml_B = make_yaml(tmp, "B", filter_manifest_abs, out_B, ops_B)
        split_B = run_filter(filter_manifest_abs, yaml_B, out_B, local_env)
        write_split(split_B, captions, manifest_rows, args.output_dir, "B")

        # Split C: 5 ops (B + camera_motion_consistency)
        print("Split C (5 ops)...")
        out_C = os.path.join(tmp, "result_C.jsonl")
        yaml_C = make_yaml(tmp, "C", filter_manifest_abs, out_C, ops_C)
        split_C = run_filter(filter_manifest_abs, yaml_C, out_C, local_env)
        write_split(split_C, captions, manifest_rows, args.output_dir, "C")

    print(f"\nSummary:")
    print(f"  A (no filter):  {len(split_A)} clips")
    print(f"  B (4 ops):      {len(split_B)} clips")
    print(f"  C (5 ops):      {len(split_C)} clips")


if __name__ == "__main__":
    main()
