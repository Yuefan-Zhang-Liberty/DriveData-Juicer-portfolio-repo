"""Exercise 5: CPU and GPU resource declarations.

Declares tasks with explicit num_cpus and num_gpus resource requests.
Demonstrates how Ray's resource model works: resources are reserved slots,
not hardware enforcement — a task declared with num_gpus=0.5 will be
scheduled only when 0.5 GPU units are available, even if it doesn't call
any CUDA code. Prints ray.available_resources() before and after.

Run: python ray/exercises/05_resources.py
"""
import ray


@ray.remote(num_cpus=2)
def cpu_bound_task(n: int) -> int:
    # Simulate work that benefits from 2 CPUs (Ray reserves 2 CPU slots).
    return sum(range(n))


@ray.remote(num_cpus=1, num_gpus=0.5)
def gpu_aware_task(label: str) -> str:
    # Ray will only schedule this when 0.5 GPU fractional units are free.
    # On hosts without a GPU, this blocks unless num_gpus=0 is used.
    # Here we use 0.5 to demonstrate the declaration; no actual CUDA calls.
    import os
    gpu_ids = os.environ.get("CUDA_VISIBLE_DEVICES", "none")
    return f"{label}: CUDA_VISIBLE_DEVICES={gpu_ids}"


if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)

    resources = ray.available_resources()
    print("Available resources before tasks:")
    for k in ("CPU", "GPU", "memory"):
        print(f"  {k}: {resources.get(k, 0)}")

    # Run CPU-bound tasks (2 CPUs each)
    cpu_futures = [cpu_bound_task.remote(10_000_000) for _ in range(3)]
    cpu_results = ray.get(cpu_futures)
    print(f"\nCPU task results (sum 0..N): {cpu_results[:3]}")

    # Only run GPU task if a GPU is available
    if resources.get("GPU", 0) >= 0.5:
        gpu_future = gpu_aware_task.remote("gpu_task")
        print(f"\nGPU task result: {ray.get(gpu_future)}")
    else:
        print("\nNo GPU available on this host — skipping gpu_aware_task.")
        print("(Declaration compiled and validated; Ray would schedule it when GPU units are free.)")

    ray.shutdown()
    print("Done.")
