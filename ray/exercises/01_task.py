"""Exercise 1: Ray remote tasks.

Distributes a list of video clip paths over parallel Ray workers and returns
each file's size in bytes. Demonstrates @ray.remote, ray.get(), and
ray.init()/ray.shutdown().

Run: python ray/exercises/01_task.py
"""
import os
import glob
import ray


@ray.remote
def get_file_size(path: str) -> dict:
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1
    return {"path": path, "size_bytes": size}


if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)

    clips_dir = os.path.join(os.path.dirname(__file__), "../../data/clips")
    paths = glob.glob(os.path.join(clips_dir, "**/*.mp4"), recursive=True)[:20]
    if not paths:
        # Fallback: use manifest file paths for demo
        manifest = os.path.join(
            os.path.dirname(__file__),
            "../../data_juicer/manifests/gold_manifest_20.jsonl",
        )
        paths = [manifest]

    print(f"Dispatching {len(paths)} tasks to Ray workers...")
    futures = [get_file_size.remote(p) for p in paths]
    results = ray.get(futures)

    total = sum(r["size_bytes"] for r in results if r["size_bytes"] >= 0)
    print(f"Results ({len(results)} files, {total / 1024:.1f} KB total):")
    for r in results[:5]:
        print(f"  {os.path.basename(r['path'])}: {r['size_bytes']} bytes")
    if len(results) > 5:
        print(f"  ... and {len(results) - 5} more")

    ray.shutdown()
    print("Done.")
