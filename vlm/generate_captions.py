"""Phase 6: Generate structured captions for each clip from Silver/Gold Iceberg tables.

Reads ego_motion, object_annotation, scene_quality, and evaluation_slice via Spark,
joins with the full clip manifest, and writes one caption per clip to
vlm/captions/captions_full.jsonl.

Usage (from project root):
    python vlm/generate_captions.py \
        --warehouse-dir warehouse/iceberg_warehouse \
        --manifest data_juicer/manifests/gold_manifest_full.jsonl \
        --clips-dir data/clips \
        --output vlm/captions/captions_full.jsonl
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "iceberg"))
from spark_session import build_spark  # noqa: E402


def fetch_ego_motion(spark) -> dict:
    """Return {scene_token: {avg_speed_mps, total_rot_rad, num_steps}}."""
    df = spark.sql("""
        SELECT scene_token,
               AVG(displacement_m / NULLIF(dt_seconds, 0)) AS avg_speed_mps,
               SUM(ABS(rotation_change_rad))               AS total_rot_rad,
               COUNT(*)                                    AS num_steps
        FROM local.silver.ego_motion
        GROUP BY scene_token
    """)
    result = {}
    for row in df.collect():
        result[row["scene_token"]] = {
            "avg_speed_mps": row["avg_speed_mps"] or 0.0,
            "total_rot_rad": row["total_rot_rad"] or 0.0,
            "num_steps": row["num_steps"],
        }
    return result


def fetch_objects(spark) -> dict:
    """Return {scene_token: {category_name: count}}."""
    df = spark.sql("""
        SELECT sa.scene_token,
               sa.category_name,
               COUNT(*) AS cnt
        FROM local.silver.object_annotation sa
        GROUP BY sa.scene_token, sa.category_name
    """)
    result = defaultdict(dict)
    for row in df.collect():
        result[row["scene_token"]][row["category_name"]] = row["cnt"]
    return dict(result)


def fetch_scene_quality(spark) -> dict:
    """Return {scene_token: {pedestrian_count, long_tail_count}}."""
    try:
        df = spark.sql("""
            SELECT scene_token,
                   SUM(pedestrian_annotation_count) AS ped_count,
                   SUM(long_tail_annotation_count)  AS lt_count
            FROM local.silver.scene_quality
            GROUP BY scene_token
        """)
        result = {}
        for row in df.collect():
            result[row["scene_token"]] = {
                "ped_count": int(row["ped_count"] or 0),
                "lt_count": int(row["lt_count"] or 0),
            }
        return result
    except Exception:
        return {}


def fetch_splits(spark) -> dict:
    """Return {scene_token: split}."""
    df = spark.sql("SELECT scene_token, split FROM local.gold.evaluation_slice")
    return {row["scene_token"]: row["split"] for row in df.collect()}


def build_obj_summary(obj_counts: dict) -> str:
    if not obj_counts:
        return "none"
    parts = [f"{cat}×{n}" for cat, n in sorted(obj_counts.items(), key=lambda x: -x[1])[:5]]
    return ", ".join(parts)


def build_caption(clip: dict, ego: dict, objects: dict, quality: dict, splits: dict) -> str:
    scene_token = clip.get("scene_token") or ""
    scene_name = clip.get("scene_name") or "unknown"
    split = splits.get(scene_token, "unknown")

    em = ego.get(scene_token, {})
    avg_speed = em.get("avg_speed_mps", 0.0)
    total_rot = em.get("total_rot_rad", 0.0)

    obj_counts = objects.get(scene_token, {})
    obj_summary = build_obj_summary(obj_counts)

    q = quality.get(scene_token, {})
    ped_count = q.get("ped_count", 0)
    lt_count = q.get("lt_count", 0)

    return (
        f"Scene {scene_name}, split={split}. "
        f"Ego motion: avg speed {avg_speed:.1f} m/s, total rotation {total_rot:.1f} rad. "
        f"Objects: {obj_summary}. "
        f"Scene quality: {ped_count} pedestrians, {lt_count} long-tail objects. "
        f"Task: Describe the driving scenario and identify any safety-relevant observations."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--clips-dir", default="data/clips")
    parser.add_argument("--output", default="vlm/captions/captions_full.jsonl")
    args = parser.parse_args()

    spark = build_spark(args.warehouse_dir, app_name="vlm-caption-gen")

    print("Fetching Silver/Gold table data...")
    ego = fetch_ego_motion(spark)
    objects = fetch_objects(spark)
    quality = fetch_scene_quality(spark)
    splits = fetch_splits(spark)
    spark.stop()

    print(f"  ego_motion: {len(ego)} scenes")
    print(f"  objects: {len(objects)} scenes")
    print(f"  quality: {len(quality)} scenes")
    print(f"  splits: {len(splits)} scenes")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    clips_dir_abs = os.path.abspath(args.clips_dir)
    n_written = 0
    n_skipped = 0

    with open(args.manifest) as fin, open(args.output, "w") as fout:
        for line in fin:
            clip = json.loads(line)
            clip_id = clip.get("clip_id")
            if not clip_id or clip_id == "corrupt-0":
                n_skipped += 1
                continue

            # Resolve video path relative to manifest directory
            manifest_dir = os.path.dirname(os.path.abspath(args.manifest))
            videos = clip.get("videos", [])
            video_path = os.path.join(manifest_dir, videos[0]) if videos else ""

            caption = build_caption(clip, ego, objects, quality, splits)

            row = {
                "clip_id": clip_id,
                "scene_token": clip.get("scene_token"),
                "scene_name": clip.get("scene_name"),
                "split": splits.get(clip.get("scene_token") or "", "unknown"),
                "caption": caption,
                "video_path": video_path,
                "num_frames": clip.get("num_frames", 0),
            }
            fout.write(json.dumps(row) + "\n")
            n_written += 1

    print(f"\nWrote {n_written} captions to {args.output} ({n_skipped} skipped)")


if __name__ == "__main__":
    main()
