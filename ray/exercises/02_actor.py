"""Exercise 2: Ray stateful Actor.

A ClipCounter actor accumulates per-scene clip counts from manifest rows.
Demonstrates @ray.remote class, actor handle creation, and remote method calls.

Run: python ray/exercises/02_actor.py
"""
import json
import os
from collections import defaultdict

import ray


@ray.remote
class ClipCounter:
    def __init__(self):
        self._counts: dict = defaultdict(int)

    def add(self, scene_name: str, n: int = 1) -> None:
        self._counts[scene_name] += n

    def get_counts(self) -> dict:
        return dict(self._counts)

    def total(self) -> int:
        return sum(self._counts.values())


if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)

    manifest = os.path.join(
        os.path.dirname(__file__),
        "../../data_juicer/manifests/gold_manifest_20.jsonl",
    )

    counter = ClipCounter.remote()

    with open(manifest) as f:
        for line in f:
            row = json.loads(line)
            scene = row.get("scene_name") or "unknown"
            counter.add.remote(scene)

    counts = ray.get(counter.get_counts.remote())
    total = ray.get(counter.total.remote())

    print(f"Clip counts by scene ({total} total):")
    for scene, n in sorted(counts.items()):
        print(f"  {scene}: {n}")

    ray.shutdown()
    print("Done.")
