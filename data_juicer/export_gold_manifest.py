"""Export a Data-Juicer JSONL manifest of front-camera video clips built from
Gold/Silver-layer nuScenes frame sequences.

nuScenes mini ships individual camera JPEGs, not video files, and only has 10
scenes -- nowhere near the 500-clip run-scale tier Phase 3 needs. This script
bridges both gaps: it stitches each scene's CAM_FRONT frame sequence into many
overlapping fixed-length clips via a sliding window (ffmpeg concat demuxer,
per-frame duration taken from real consecutive-frame timestamp deltas rather
than an assumed constant fps), then writes the full manifest plus three
deterministic size-tiered slices (20/100/500) for the functional/stability/perf
validation stages. One clip is deliberately left corrupted (0 bytes) and
inserted near the front of the manifest to exercise Data-Juicer's
skip_op_error handling.

Usage:
    python data_juicer/export_gold_manifest.py \
        --warehouse-dir warehouse/iceberg_warehouse \
        --nuscenes-root data/nuscenes \
        --clips-dir data/clips \
        --manifest-dir data_juicer/manifests \
        --window-frames 24 --stride-frames 4
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "iceberg"))
from spark_session import build_spark  # noqa: E402

CAPTION_TEMPLATE = "<__dj__video> front-camera clip from nuScenes {scene_name}, {num_frames} frames <|__dj__eoc|>"


def fetch_frames(spark):
    df = spark.sql("""
        SELECT scf.scene_token, scf.scene_name, scf.timestamp, scf.filename, ges.split
        FROM local.silver.camera_frame scf
        JOIN local.gold.evaluation_slice ges ON ges.scene_token = scf.scene_token
        WHERE scf.channel = 'CAM_FRONT'
        ORDER BY scf.scene_token, scf.timestamp
    """)
    by_scene = defaultdict(list)
    for row in df.collect():
        by_scene[(row["scene_token"], row["scene_name"], row["split"])].append(
            (row["timestamp"], row["filename"])
        )
    return by_scene


def build_clip_plan(by_scene, window_frames, stride_frames):
    clips = []
    for (scene_token, scene_name, split), frames in by_scene.items():
        frames = sorted(frames)
        n = len(frames)
        idx = 0
        clip_num = 0
        while idx + window_frames <= n:
            window = frames[idx : idx + window_frames]
            clips.append({
                "clip_id": f"{scene_name}-{clip_num:04d}",
                "scene_token": scene_token,
                "scene_name": scene_name,
                "split": split,
                "frames": window,
                "start_ts": window[0][0],
                "end_ts": window[-1][0],
                "num_frames": len(window),
            })
            idx += stride_frames
            clip_num += 1
    clips.sort(key=lambda c: (c["scene_name"], c["clip_id"]))
    return clips


def encode_clip(clip, nuscenes_root, clips_dir):
    out_dir = os.path.join(clips_dir, clip["scene_name"])
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{clip['clip_id']}.mp4")

    concat_path = out_path + ".concat.txt"
    frames = clip["frames"]
    with open(concat_path, "w") as f:
        for i, (ts, filename) in enumerate(frames):
            abs_path = os.path.abspath(os.path.join(nuscenes_root, filename))
            f.write(f"file '{abs_path}'\n")
            if i < len(frames) - 1:
                duration = max((frames[i + 1][0] - ts) / 1e6, 1e-3)
                f.write(f"duration {duration:.6f}\n")
        # ffmpeg concat quirk: repeat the last file so its preceding duration takes effect
        f.write(f"file '{os.path.abspath(os.path.join(nuscenes_root, frames[-1][1]))}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
            "-vsync", "vfr", "-pix_fmt", "yuv420p", "-loglevel", "error", out_path,
        ],
        check=True,
    )
    os.remove(concat_path)
    return out_path


def write_corrupt_clip(clips_dir):
    out_dir = os.path.join(clips_dir, "_corrupt")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "corrupt-0.mp4")
    with open(out_path, "wb") as f:
        f.write(b"")
    return out_path


def to_manifest_row(clip, video_path, manifest_dir):
    # Data-Juicer resolves relative video paths against dirname(dataset_path),
    # i.e. manifest_dir -- not the project root or cwd.
    rel_path = os.path.relpath(video_path, manifest_dir)
    return {
        "videos": [rel_path],
        "text": CAPTION_TEMPLATE.format(scene_name=clip["scene_name"], num_frames=clip["num_frames"]),
        "clip_id": clip["clip_id"],
        "scene_token": clip["scene_token"],
        "scene_name": clip["scene_name"],
        "split": clip["split"],
        "start_ts": clip["start_ts"],
        "end_ts": clip["end_ts"],
        "num_frames": clip["num_frames"],
    }


def write_jsonl(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--nuscenes-root", required=True)
    parser.add_argument("--clips-dir", required=True)
    parser.add_argument("--manifest-dir", required=True)
    parser.add_argument("--window-frames", type=int, default=24)
    parser.add_argument("--stride-frames", type=int, default=4)
    args = parser.parse_args()

    manifest_dir = os.path.abspath(args.manifest_dir)
    spark = build_spark(args.warehouse_dir, app_name="export-gold-manifest")
    by_scene = fetch_frames(spark)
    spark.stop()

    clips = build_clip_plan(by_scene, args.window_frames, args.stride_frames)
    print(f"planned {len(clips)} clips across {len(by_scene)} scenes "
          f"(window={args.window_frames} frames, stride={args.stride_frames} frames)")

    rows = []
    for clip in clips:
        video_path = encode_clip(clip, args.nuscenes_root, args.clips_dir)
        rows.append(to_manifest_row(clip, video_path, manifest_dir))

    corrupt_path = write_corrupt_clip(args.clips_dir)
    corrupt_row = {
        "videos": [os.path.relpath(corrupt_path, manifest_dir)],
        "text": "<__dj__video> deliberately corrupted (0-byte) clip for skip_op_error testing <|__dj__eoc|>",
        "clip_id": "corrupt-0",
        "scene_token": None,
        "scene_name": None,
        "split": None,
        "start_ts": None,
        "end_ts": None,
        "num_frames": 0,
    }
    rows.insert(1, corrupt_row)

    full_path = os.path.join(args.manifest_dir, "gold_manifest_full.jsonl")
    write_jsonl(rows, full_path)
    for tier in (20, 100, 500):
        tier_path = os.path.join(args.manifest_dir, f"gold_manifest_{tier}.jsonl")
        write_jsonl(rows[:tier], tier_path)
        print(f"wrote {tier_path} ({min(tier, len(rows))} rows)")
    print(f"wrote {full_path} ({len(rows)} rows total, including 1 deliberately corrupted clip)")


if __name__ == "__main__":
    main()
