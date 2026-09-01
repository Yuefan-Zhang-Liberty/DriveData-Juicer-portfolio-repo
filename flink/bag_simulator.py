"""Simulate driving-log "bags" trickling into a landing directory over time.

Real AV fleets don't deliver their whole dataset in one batch -- logs land
continuously as vehicles finish routes and upload. This script recreates that
arrival pattern using real, previously-unseen nuScenes trainval metadata (the
10-scene mini set is already fully ingested into Bronze; these 850 scenes are
not), so the Flink job on the other end is ingesting genuinely new data, not a
replay of something already in the lake.

One "bag" = one scene's CAM_FRONT sample_data rows, matching the granularity
export_gold_manifest.py already uses for clip generation. Each bag is written
as a single JSONL file (one row per line) with a --interval-seconds pause
before the next drops, so a continuously-monitoring file source sees them
arrive one at a time rather than all at once.

Usage:
    python flink/bag_simulator.py \
        --meta-root data/nuscenes_trainval_meta/v1.0-trainval \
        --landing-dir data/bag_landing \
        --num-scenes 20 --interval-seconds 10 --inject-faults
"""
import argparse
import json
import os
import random
import time

SAMPLE_DATA_FIELDS = [
    "token", "sample_token", "ego_pose_token", "calibrated_sensor_token",
    "timestamp", "fileformat", "is_key_frame", "height", "width",
    "filename", "prev", "next",
]


def load_json(meta_root, name):
    with open(os.path.join(meta_root, f"{name}.json")) as f:
        return json.load(f)


def build_channel_map(meta_root):
    sensor = load_json(meta_root, "sensor")
    calibrated_sensor = load_json(meta_root, "calibrated_sensor")
    sensor_channel = {s["token"]: s["channel"] for s in sensor}
    return {
        cs["token"]: sensor_channel[cs["sensor_token"]]
        for cs in calibrated_sensor
        if cs["sensor_token"] in sensor_channel
    }


def build_scene_plan(meta_root, num_scenes):
    scenes = load_json(meta_root, "scene")
    samples = load_json(meta_root, "sample")
    sample_data = load_json(meta_root, "sample_data")
    channel_of = build_channel_map(meta_root)

    sample_scene = {s["token"]: s["scene_token"] for s in samples}
    scene_name = {s["token"]: s["name"] for s in scenes}

    by_scene = {}
    for row in sample_data:
        if channel_of.get(row["calibrated_sensor_token"]) != "CAM_FRONT":
            continue
        scene_token = sample_scene.get(row["sample_token"])
        if scene_token is None:
            continue
        by_scene.setdefault(scene_token, []).append(row)

    plan = []
    for scene in scenes:
        rows = by_scene.get(scene["token"])
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: r["timestamp"])
        plan.append((scene["token"], scene_name[scene["token"]], rows))
        if len(plan) >= num_scenes:
            break
    return plan


def inject_fault(rows):
    if len(rows) < 2:
        return rows
    rows = list(rows)
    i = random.randrange(len(rows) - 1)
    rows[i]["timestamp"], rows[i + 1]["timestamp"] = rows[i + 1]["timestamp"], rows[i]["timestamp"]
    return rows


def write_bag(landing_dir, scene_token, scene_name, rows):
    out_path = os.path.join(landing_dir, f"{scene_name}.jsonl")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w") as f:
        for row in rows:
            record = {k: row[k] for k in SAMPLE_DATA_FIELDS}
            record["scene_token"] = scene_token
            record["scene_name"] = scene_name
            f.write(json.dumps(record) + "\n")
    os.replace(tmp_path, out_path)  # atomic: the file source never sees a partial write
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta-root", required=True)
    parser.add_argument("--landing-dir", required=True)
    parser.add_argument("--num-scenes", type=int, default=20)
    parser.add_argument("--interval-seconds", type=float, default=10)
    parser.add_argument("--inject-faults", action="store_true", help="swap one timestamp pair every 5th bag")
    args = parser.parse_args()

    os.makedirs(args.landing_dir, exist_ok=True)
    plan = build_scene_plan(args.meta_root, args.num_scenes)
    print(f"planned {len(plan)} bags (scenes) from real, previously-un-ingested trainval metadata")

    faulty_scenes = []
    for i, (scene_token, scene_name, rows) in enumerate(plan):
        if args.inject_faults and i % 5 == 4:
            rows = inject_fault(rows)
            faulty_scenes.append(scene_name)
        out_path = write_bag(args.landing_dir, scene_token, scene_name, rows)
        print(f"[{i + 1}/{len(plan)}] landed {out_path} ({len(rows)} CAM_FRONT rows"
              f"{', FAULT INJECTED' if scene_name in faulty_scenes else ''})")
        if i < len(plan) - 1:
            time.sleep(args.interval_seconds)

    print(f"done. {len(plan)} bags landed, {len(faulty_scenes)} with an injected out-of-order timestamp: {faulty_scenes}")


if __name__ == "__main__":
    main()
