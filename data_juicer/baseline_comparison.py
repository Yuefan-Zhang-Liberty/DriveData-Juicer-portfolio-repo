"""Compare VideoCameraMotionConsistencyFilter against a plain frame-difference
motion-consistency baseline, to support Phase 4's completion gate: the new
operator's false-positive rate on normal camera motion must be lower than the
baseline's.

Usage:
    .venv/bin/python3 data_juicer/baseline_comparison.py
"""

import json
import os
import sys

import cv2
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "data-juicer"))

from data_juicer.ops.filter.video_camera_motion_consistency_filter import (  # noqa: E402
    VideoCameraMotionConsistencyFilter,
)
from data_juicer.utils.constant import Fields, StatsKeys  # noqa: E402

DEFAULT_THRESHOLD = 0.05


def _make_background(h=240, w=320, seed=0):
    rng = np.random.RandomState(seed)
    bg = rng.randint(0, 255, size=(h + 100, w + 100, 3), dtype=np.uint8)
    bg[::10, :, :] = 0
    bg[:, ::10, :] = 0
    return bg


def _pan_frames(num_frames=15, h=240, w=320, step=2, seed=2):
    bg = _make_background(h, w, seed=seed)
    frames = []
    for i in range(num_frames):
        y, x = 50 + i * step, 50 + i * step
        frames.append(bg[y : y + h, x : x + w].copy())
    return frames


def _rotate_frames(num_frames=15, h=240, w=320, angle_step=1.5, seed=3):
    bg = _make_background(h, w, seed=seed)
    crop = bg[50 : 50 + h, 50 : 50 + w]
    center = (w // 2, h // 2)
    frames = []
    for i in range(num_frames):
        mat = cv2.getRotationMatrix2D(center, angle_step * i, 1.0)
        frames.append(cv2.warpAffine(crop, mat, (w, h)))
    return frames


def _scene_cut_frames(num_frames=16, h=240, w=320, seed=90):
    half = num_frames // 2
    first = _pan_frames(num_frames=half, h=h, w=w, step=2, seed=seed)
    second_bg = _make_background(h, w, seed=seed + 1)
    crop2 = second_bg[50 : 50 + h, 50 : 50 + w]
    second = [crop2.copy() for _ in range(num_frames - half)]
    return first + second


def _flicker_frames(num_frames=15, h=240, w=320, seed=91):
    frames = _pan_frames(num_frames=num_frames, h=h, w=w, step=2, seed=seed)
    flickered = []
    for i, frame in enumerate(frames):
        factor = 1.6 if i % 2 == 0 else 0.4
        flickered.append(np.clip(frame.astype(np.float32) * factor, 0, 255).astype(np.uint8))
    return flickered


def _reordered_frames(num_frames=15, h=240, w=320, seed=92):
    frames = _pan_frames(num_frames=num_frames, h=h, w=w, step=2, seed=seed)
    rng = np.random.RandomState(seed)
    shuffled = list(frames)
    rng.shuffle(shuffled)
    return shuffled


def _write_video(path, frames, fps=10):
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()


def frame_difference_consistency(video_path, sampling_fps=2):
    """Plain frame-difference baseline: mean absolute pixel difference between
    consecutive sampled grayscale frames, treated as a velocity proxy; its
    frame-to-frame variability (like our motion_smoothness, but computed on raw
    pixel-diff magnitude instead of homography-tracked camera translation) gives
    a consistency score in the same [0, 1] shape as our operator's score, so both
    can be compared against the same threshold. This baseline can't distinguish
    "the camera moved" from "the scene got brighter/darker" or "the frame is
    more/less textured" -- it can only see raw pixel change.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return -1

    fps = cap.get(cv2.CAP_PROP_FPS)
    effective_fps = min(sampling_fps, fps) if fps and fps > 0 else sampling_fps
    sampling_step = max(round(fps / effective_fps), 1) if fps and fps > 0 else 1

    diffs = []
    prev_gray = None
    frame_count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev_gray is not None:
            diffs.append(float(np.mean(np.abs(gray - prev_gray))))
        prev_gray = gray
        frame_count += sampling_step
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count)
    cap.release()

    if len(diffs) < 2:
        return -1
    acceleration = np.diff(diffs)
    return float(1.0 / (1.0 + np.std(acceleration)))


def our_consistency(video_path, op):
    sample = {op.video_key: [video_path], Fields.stats: {}}
    sample = op.compute_stats_single(sample)
    return sample[Fields.stats][StatsKeys.video_camera_motion_consistency][0]


def evaluate(name, video_paths, op, threshold=DEFAULT_THRESHOLD):
    ours_scores = [our_consistency(p, op) for p in video_paths]
    baseline_scores = [frame_difference_consistency(p) for p in video_paths]

    ours_fp = sum(1 for s in ours_scores if s < threshold)
    baseline_fp = sum(1 for s in baseline_scores if s < threshold)
    n = len(video_paths)

    return {
        "name": name,
        "n": n,
        "ours_scores": ours_scores,
        "baseline_scores": baseline_scores,
        "ours_false_positive_rate": ours_fp / n if n else 0.0,
        "baseline_false_positive_rate": baseline_fp / n if n else 0.0,
    }


def discriminative_power(name, normal_paths, faulty_clips, op):
    """For each method, find the threshold that would be required to reject every
    synthetic faulty clip (score < threshold for all of them), then measure what
    fraction of genuinely-normal clips that same threshold would also reject. A
    method that separates faulty from normal motion well needs only a small
    threshold to catch all faults, so its false-positive rate on normal clips stays
    low; a method that can't tell them apart needs a threshold high enough to reach
    into the normal-clip score range too.

    faulty_clips is a list of (fault_name, path) pairs so per-fault-type scores can
    be reported alongside the aggregate -- the aggregate alone is sensitive to
    whichever single fault type happens to be hardest to separate.
    """
    normal_ours = [our_consistency(p, op) for p in normal_paths]
    normal_baseline = [frame_difference_consistency(p) for p in normal_paths]
    faulty_ours = {name: our_consistency(p, op) for name, p in faulty_clips}
    faulty_baseline = {name: frame_difference_consistency(p) for name, p in faulty_clips}

    ours_threshold = max(faulty_ours.values()) + 1e-6
    baseline_threshold = max(faulty_baseline.values()) + 1e-6

    ours_fp = sum(1 for s in normal_ours if s < ours_threshold)
    baseline_fp = sum(1 for s in normal_baseline if s < baseline_threshold)
    n = len(normal_paths)

    return {
        "name": name,
        "n_normal": n,
        "n_faulty": len(faulty_clips),
        "ours_threshold_to_catch_all_faulty": ours_threshold,
        "baseline_threshold_to_catch_all_faulty": baseline_threshold,
        "ours_false_positive_rate_on_normal": ours_fp / n if n else 0.0,
        "baseline_false_positive_rate_on_normal": baseline_fp / n if n else 0.0,
        "normal_ours_score_range": [min(normal_ours), float(np.mean(normal_ours)), max(normal_ours)],
        "normal_baseline_score_range": [min(normal_baseline), float(np.mean(normal_baseline)), max(normal_baseline)],
        "faulty_ours_scores_by_type": faulty_ours,
        "faulty_baseline_scores_by_type": faulty_baseline,
    }


def main():
    tmp_dir = os.path.join(REPO_ROOT, "data_juicer", "work_dir", "phase4_baseline_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    pan_path = os.path.join(tmp_dir, "pan.mp4")
    _write_video(pan_path, _pan_frames(num_frames=15))
    rotate_path = os.path.join(tmp_dir, "rotate.mp4")
    _write_video(rotate_path, _rotate_frames(num_frames=15))

    # a few more pan clips at different (still smooth/constant) speeds and seeds,
    # so the "normal camera motion" sample isn't just n=2.
    synthetic_paths = [pan_path, rotate_path]
    for i, (step, seed) in enumerate([(1, 10), (3, 11), (4, 12), (2, 13)]):
        p = os.path.join(tmp_dir, f"pan_extra_{i}.mp4")
        _write_video(p, _pan_frames(num_frames=15, step=step, seed=seed))
        synthetic_paths.append(p)

    op = VideoCameraMotionConsistencyFilter(min_consistency=DEFAULT_THRESHOLD)
    results = [evaluate("synthetic_smooth_motion", synthetic_paths, op)]

    manifest_path = os.path.join(REPO_ROOT, "data_juicer", "manifests", "gold_manifest_20.jsonl")
    real_paths = []
    if os.path.exists(manifest_path):
        manifest_dir = os.path.dirname(manifest_path)
        with open(manifest_path) as f:
            for line in f:
                row = json.loads(line)
                if "_corrupt" in row["videos"][0]:
                    continue
                real_paths.append(os.path.normpath(os.path.join(manifest_dir, row["videos"][0])))
        results.append(evaluate("real_gold_clips_20tier", real_paths, op))

    for r in results:
        print(f"== {r['name']} (n={r['n']}) ==")
        print(f"  ours false-positive rate:     {r['ours_false_positive_rate']:.2%}")
        print(f"  baseline false-positive rate: {r['baseline_false_positive_rate']:.2%}")
        print(f"  ours scores:     {[round(s, 3) for s in r['ours_scores']]}")
        print(f"  baseline scores: {[round(s, 3) for s in r['baseline_scores']]}")

    # discriminative-power comparison: build synthetic faulty clips (scene cut,
    # flicker, reordered frames) and measure the false-positive cost, on normal
    # motion, of setting each method's threshold high enough to reject them all.
    # Restricted to the synthetic normal clips (not the real gold clips): real
    # driving footage naturally scores low (~0.10-0.25, see class docstring's
    # parallax limitation) for reasons unrelated to these synthetic faults, so
    # mixing it in here would conflate two different, separately-documented
    # effects rather than isolating discriminative power.
    faulty_clips = []
    for fault_name, builder in [
        ("scene_cut", _scene_cut_frames),
        ("flicker", _flicker_frames),
        ("reordered", _reordered_frames),
    ]:
        p = os.path.join(tmp_dir, f"{fault_name}.mp4")
        _write_video(p, builder())
        faulty_clips.append((fault_name, p))

    disc_result = discriminative_power(
        "discriminative_power_synthetic_faulty_vs_normal", synthetic_paths, faulty_clips, op
    )
    results.append(disc_result)

    print(f"== {disc_result['name']} (n_normal={disc_result['n_normal']}, n_faulty={disc_result['n_faulty']}) ==")
    print(
        f"  ours threshold needed to catch all faulty:     "
        f"{disc_result['ours_threshold_to_catch_all_faulty']:.3f}"
    )
    print(
        f"  baseline threshold needed to catch all faulty: "
        f"{disc_result['baseline_threshold_to_catch_all_faulty']:.3f}"
    )
    print(f"  ours false-positive rate on normal clips:     {disc_result['ours_false_positive_rate_on_normal']:.2%}")
    print(
        f"  baseline false-positive rate on normal clips: "
        f"{disc_result['baseline_false_positive_rate_on_normal']:.2%}"
    )
    print(f"  normal ours score range (min/mean/max):     {[round(s, 3) for s in disc_result['normal_ours_score_range']]}")
    print(f"  normal baseline score range (min/mean/max): {[round(s, 3) for s in disc_result['normal_baseline_score_range']]}")
    print(f"  faulty ours scores by type:     {disc_result['faulty_ours_scores_by_type']}")
    print(f"  faulty baseline scores by type: {disc_result['faulty_baseline_scores_by_type']}")

    out_path = os.path.join(REPO_ROOT, "data_juicer", "work_dir", "phase4_baseline_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
