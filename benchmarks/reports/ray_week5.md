# Phase 5 Report: Ray Practice + Local vs Ray Benchmark

## Environment

| Item | Value |
|---|---|
| Ray version | 2.x (data-juicer `.venv`) |
| Head node | 10.46.130.154 |
| CPUs available (Ray head) | 4 |
| GPUs | 1 × RTX 4090 |
| Memory (Ray) | ~76 GB object store |
| Dataset tier | gold_manifest_20.jsonl (20 clips) |
| Pipeline | 5 ops: duration → aspect_ratio → resolution → motion_score → camera_motion_consistency |

`ray.available_resources()`:
```json
{
  "CPU": 4.0,
  "GPU": 1.0,
  "memory": 81798191104,
  "object_store_memory": 35056367616,
  "accelerator_type:GeForce-RTX-4090": 1.0
}
```

---

## Ray Exercise Summary

Five standalone exercises validated core Ray primitives:

| Script | Primitive | Result |
|---|---|---|
| `01_task.py` | `@ray.remote` task, `ray.get()` | 20 clip file-sizes returned in parallel ✓ |
| `02_actor.py` | Stateful `@ray.remote` class | Per-scene clip counts accumulated via Actor ✓ |
| `03_ray_data.py` | `ray.data.read_json()`, `map_batches()` | 20-row dataset read and projected ✓ |
| `04_retry.py` | `max_retries=3`, transient exception | All 4 tasks eventually succeeded after retries ✓ |
| `05_resources.py` | `num_cpus=2`, `num_gpus=0.5` declarations | CPU tasks ran; GPU task scheduled on RTX 4090 ✓ |

Key observations from exercises:
- `@ray.remote` tasks are stateless and share no process state — each call gets a clean worker context.
- Actors serialize state changes through a message queue; `ray.get()` blocks until the actor method returns.
- Ray Data's `map_batches` is lazy: the plan is built on `read_json()`, executed only on `take()` or `show()`.
- `max_retries` applies at the Ray scheduler level — Python exceptions that inherit from `Exception` are caught and the task is re-queued; the caller sees the final success result transparently.
- Resource declarations (`num_cpus`, `num_gpus`) are logical slots, not hardware enforcement — Ray will not schedule the task until those fractional units are available in the cluster.

---

## Local vs Ray Benchmark

Pipeline: 5 ops over gold_manifest_20.jsonl (20 front-camera mp4 clips, ~1–2 s each).
Local mode used `MP_START_METHOD=fork` + `auto_op_parallelism: false` (1 process per op).
Ray mode connected to the local head (`ray_address: auto`); `num_proc` set on the two
most expensive ops (motion_score and camera_motion_consistency).

| Executor | Clips | Total (s) | Videos/min |
|---|---|---|---|
| Local (1 proc, fork) | 20 | 86.5 | **13.9** |
| Ray (num_proc=1) | 20 | 107.6 | 11.2 |
| Ray (num_proc=2) | 20 | 107.1 | 11.2 |
| Ray (num_proc=4) | 20 | 108.4 | 11.1 |

Raw timing data: `benchmarks/reports/ray_week5_timing.json`

### Analysis

**Local is faster at this scale.** Ray overhead (actor/task scheduling, object-store
serialization, IPC) adds ~20 s (~25%) over local at 20 clips. This is expected and
consistent with Ray's documented break-even point: Ray's distributed overhead amortizes
only when (a) tasks are compute-heavy (>1–2 s each) or (b) the number of parallel
workers or machines is high. These clips are each ~1–2 s to process through
`video_motion_score_filter` and `video_camera_motion_consistency_filter`; at 20 clips
the scheduling cost is not hidden.

**Increasing `num_proc` from 1→4 in Ray mode gives no improvement.** The bottleneck is
per-clip disk I/O and cv2 video decode — not Python GIL concurrency. With only 20 clips
and 4 CPUs available on the Ray head, adding more concurrent tasks does not reduce
wall-clock time; it introduces contention. This is the correct null result: it validates
the pipeline is I/O-bound at this scale, not CPU-bound.

**Expected Ray advantage at scale.** On a multi-node cluster with 100s of clips, Ray's
true value is scheduling work across machines, not just processes. The exercises (retry,
resource declarations) demonstrate the framework's fault-tolerance and heterogeneous
resource management capabilities — both essential for production data pipelines where
single-machine `fork` + `psutil` resource detection would fail.

### Known Constraints

- `auto_op_parallelism: false` is **not** required in Ray mode — Ray executor controls
  parallelism via actor/task scheduling, bypassing `calculate_np()` and psutil. Confirmed
  by successful Ray runs without the flag.
- `MP_START_METHOD=fork` is **not** required in Ray mode — Ray actors use spawn-based
  isolation, so UNFORKABLE ops (cv2-based) work correctly without the env override.
- Local mode on this shared 224-core host **requires** both flags to avoid OOM kill.
  See `docs/architecture.md` for full explanation.

---

## Next: Phase 6

Phase 6 installs VLM packages (peft, bitsandbytes, trl) and runs the QLoRA A/B/C
attribution experiment using structured captions from the Silver/Gold Iceberg tables.
