"""Exercise 3: Ray Data map_batches.

Reads the gold manifest JSONL with ray.data.read_json(), applies map_batches()
to extract clip_id and num_frames, and prints 5 results. Demonstrates Ray Data's
lazy execution model and columnar batch processing.

Run: python ray/exercises/03_ray_data.py
"""
import os

import ray


def extract_fields(batch: dict) -> dict:
    return {
        "clip_id": batch["clip_id"],
        "num_frames": batch["num_frames"],
    }


if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)

    manifest = os.path.join(
        os.path.dirname(__file__),
        "../../data_juicer/manifests/gold_manifest_20.jsonl",
    )

    ds = ray.data.read_json(manifest)
    print(f"Dataset schema: {ds.schema()}")
    print(f"Estimated rows: {ds.count()}")

    extracted = ds.map_batches(extract_fields, batch_format="pandas")

    print("\nFirst 5 rows after map_batches:")
    for row in extracted.take(5):
        print(f"  clip_id={row['clip_id']}  num_frames={row['num_frames']}")

    ray.shutdown()
    print("Done.")
