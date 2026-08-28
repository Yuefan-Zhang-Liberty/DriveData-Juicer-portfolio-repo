# Feature Issue: `video_camera_motion_consistency_filter` operator

**Title:** `[Feature] Add video_camera_motion_consistency_filter for autonomous-driving footage quality`

---

## Motivation

Autonomous-driving datasets (nuScenes, Waymo, KITTI) are recorded from ego-vehicle cameras
under real-world conditions that introduce several types of temporal corruption:

- **Dropped or reordered frames** from sensor-sync issues
- **Brightness flicker** from exposure auto-adjustment
- **Scene cuts** from clip assembly errors
- **Corrupted timing** from timestamp jitter

Existing Data-Juicer video operators (`video_motion_score_filter`,
`video_duration_filter`, `video_resolution_filter`) catch gross quality failures but do
not specifically measure whether the **global camera motion** across a clip is
geometrically consistent and physically smooth — the key property needed for ego-motion
reconstruction, camera calibration verification, and VLM fine-tuning data curation.

## Algorithm

For each pair of adjacent sampled frames (at configurable `sampling_fps`):

1. Shi-Tomasi corner detection on the previous frame (`cv2.goodFeaturesToTrack`)
2. Lucas-Kanade optical flow tracks corners into the current frame (`cv2.calcOpticalFlowPyrLK`)
3. RANSAC homography fitted to the tracked correspondences (`cv2.findHomography`)
4. `inlier_ratio = RANSAC_inliers / total_correspondences` and per-step velocity extracted from inlier displacement

Per-video aggregation:
- `mean_inlier_ratio`: how well a single rigid camera-motion model explains each frame pair
- `motion_smoothness = 1 / (1 + σ(acceleration) / μ(velocity))`: smoothness of the motion trajectory, speed-normalized for cross-clip comparability
- `camera_motion_consistency = mean_inlier_ratio × motion_smoothness` (product of two [0,1] quantities → interpretable [0,1] score)
- Sentinel `-1` for videos that yield no valid tracked pair (too short, corrupted, unreadable)

Five stats are cached: `video_camera_motion_consistency`, `video_motion_smoothness`,
`video_mean_inlier_ratio`, `video_mean_warp_error`, `video_max_motion_jerk`.

## Comparison with `video_motion_score_filter`

| Property | `video_motion_score_filter` | `video_camera_motion_consistency_filter` |
|---|---|---|
| Algorithm | Dense Farneback optical flow → magnitude | Shi-Tomasi + LK + RANSAC homography |
| What it measures | How much the video moves | How consistently and smoothly it moves |
| Score for static video | Low (filtered by min_score) | High (not falsely rejected) |
| Score for scene cut | High (large motion) | Low (RANSAC inlier_ratio drops) |
| Score for brightness flicker | Unchanged | Low (LK correspondences break down) |
| False positive on normal ego-motion | Medium | Low (calibrated default `min_consistency=0.05`) |

## Test coverage

15 unit tests including: static video, smooth pan, smooth rotation, duplicate frames,
dropped frames, reordered frames, brightness flicker, scene cut, invalid path, corrupted
video, single frame, `any`/`all` multi-video strategy, stats caching (idempotency),
`frame_field` support.

## Benchmark results

Compared against a frame-difference baseline on synthetic smooth-pan/rotation clips:
- Frame-difference baseline false-positive rate on normal motion: **100%** (motion detected → rejected)
- `video_camera_motion_consistency_filter` false-positive rate: **0%** (smooth motion correctly passes)

See `benchmarks/reports/dj_week4.md` in the contributor's fork for full methodology
and nuScenes real-data results.

## Implementation notes

- Follows `video_motion_score_filter.py` structure exactly: `UNFORKABLE` + `@OPERATORS` registration, `VideoCapture` context manager, dual `frame_field`/`video_key` path in `compute_stats_single`, `get_keep_boolean` + `any`/`all` in `process_single`.
- No new dependencies: only `cv2` (already a data-juicer requirement), `numpy`.
- Operator is `UNFORKABLE` (cv2 is not fork-safe) — consistent with existing cv2-based operators.
- 5 new `StatsKeysConstant` attrs added to `data_juicer/utils/constant.py`.
- Registered in `data_juicer/ops/filter/__init__.py` and `data_juicer/config/config_all.yaml`.

## Files changed

- `data_juicer/ops/filter/video_camera_motion_consistency_filter.py` (new, ~400 lines)
- `data_juicer/utils/constant.py` (5 new StatsKeys attrs)
- `data_juicer/ops/filter/__init__.py` (1 import, 1 `__all__` entry)
- `data_juicer/config/config_all.yaml` (1 new op entry)
- `tests/ops/filter/test_video_camera_motion_consistency_filter.py` (new, 15 tests)
- `docs/operators/filter/video_camera_motion_consistency_filter.md` (new, bilingual)
