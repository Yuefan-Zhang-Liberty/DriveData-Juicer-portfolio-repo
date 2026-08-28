"""Exercise 4: Ray fault tolerance with max_retries.

A task that raises an exception 50% of the time (based on a counter tracked
by a shared Actor). With max_retries=3, Ray re-executes the task automatically
on failure. Demonstrates Ray's built-in retry mechanism for transient errors.

Run: python ray/exercises/04_retry.py
"""
import ray


@ray.remote
class CallTracker:
    def __init__(self):
        self._calls = 0

    def increment(self) -> int:
        self._calls += 1
        return self._calls

    def count(self) -> int:
        return self._calls


@ray.remote(max_retries=3, retry_exceptions=True)
def flaky_task(tracker_handle, task_id: int) -> str:
    call_num = ray.get(tracker_handle.increment.remote())
    # Fail on odd call numbers to simulate transient errors
    if call_num % 2 == 1:
        raise RuntimeError(f"Transient error on call {call_num} for task {task_id}")
    return f"task {task_id} succeeded on call {call_num}"


if __name__ == "__main__":
    ray.init(ignore_reinit_error=True)

    tracker = CallTracker.remote()

    futures = [flaky_task.remote(tracker, i) for i in range(4)]
    results = ray.get(futures)

    total_calls = ray.get(tracker.count.remote())
    print(f"All tasks completed. Total tracker calls (including retries): {total_calls}")
    for r in results:
        print(f"  {r}")

    ray.shutdown()
    print("Done.")
