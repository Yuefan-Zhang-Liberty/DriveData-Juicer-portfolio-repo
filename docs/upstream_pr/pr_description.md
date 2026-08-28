# PR Description Draft

**Title:** `feat(filter): add video_camera_motion_consistency_filter for ego-camera motion quality`

---

## Summary

This PR adds `video_camera_motion_consistency_filter`, a new video filter operator for
measuring and filtering on the geometric consistency and temporal smoothness of camera
motion in video clips.

**Motivation:** Autonomous-driving datasets contain clips with dropped/reordered frames,
brightness flicker, and scene cuts that pass existing quality filters but corrupt
ego-motion-dependent downstream tasks (VLM fine-tuning, depth estimation, camera
calibration). This operator catches those failures with a lightweight, model-free pipeline
(Shi-Tomasi + LK + RANSAC), adding a new quality signal rather than duplicating existing
motion-magnitude filtering.

## Changes

### New operator

`data_juicer/ops/filter/video_camera_motion_consistency_filter.py`

- Computes `camera_motion_consistency = mean_inlier_ratio × motion_smoothness` per video
- `mean_inlier_ratio`: fraction of RANSAC-inlier correspondences per sampled frame pair — measures how well a single rigid camera motion model explains each transition
- `motion_smoothness = 1 / (1 + σ(acceleration) / μ(velocity))` — speed-normalized smoothness; constant-velocity motion → 1, erratic/flickering motion → 0
- Sentinel `-1` for hard failures (corrupted/too-short videos) → excluded by any non-negative `min_consistency`
- 5 stats cached: `video_camera_motion_consistency`, `video_motion_smoothness`, `video_mean_inlier_ratio`, `video_mean_warp_error`, `video_max_motion_jerk`

### Supporting changes

- `data_juicer/utils/constant.py`: 5 new `StatsKeysConstant` attrs
- `data_juicer/ops/filter/__init__.py`: import + `__all__` entry (alphabetical)
- `data_juicer/config/config_all.yaml`: new op entry with all params documented

### Tests

`tests/ops/filter/test_video_camera_motion_consistency_filter.py` — 15 tests:

| Test | What it validates |
|---|---|
| `test_static` | Near-identity homography → high consistency score |
| `test_smooth_pan` | Constant-velocity translation not falsely rejected |
| `test_smooth_rotation` | Constant-velocity rotation not falsely rejected |
| `test_duplicate_frames` | No crash; well-defined score |
| `test_dropped_frames` | No crash; lower score than clean pan |
| `test_reordered_frames` | Markedly lower score than smooth pan |
| `test_brightness_flicker` | Lower score than equivalent non-flickering clip |
| `test_scene_cut` | Markedly lower score than single-texture pan |
| `test_invalid_path` | No crash; `-1` sentinel → filtered |
| `test_corrupted_video` | No crash; `-1` sentinel → filtered |
| `test_single_frame` | No crash; `-1` sentinel → filtered |
| `test_any` | Multi-video `any` strategy |
| `test_all` | Multi-video `all` strategy |
| `test_stats_caching` | `compute_stats_single` is idempotent |
| `test_frame_field` | `frame_field` path parity with `video_motion_score_filter` |

### Documentation

`docs/operators/filter/video_camera_motion_consistency_filter.md` — bilingual
(EN + ZH), algorithm description, parameter table, known limitation (planar-motion
assumption), example YAML.

## Comparison with `video_motion_score_filter`

| | `video_motion_score_filter` | This operator |
|---|---|---|
| Algorithm | Dense Farneback flow | Sparse LK + RANSAC homography |
| Measures | Motion magnitude | Motion geometric consistency + smoothness |
| False positive on scene cuts | High (large flow) | Low (RANSAC inlier_ratio drops) |
| False positive on normal ego-motion | Low | **0% on synthetic smooth pan/rotation** |
| Complementary use | Keep videos that move | Keep videos whose motion is geometrically consistent |

The two operators are designed to be **complementary**: `video_motion_score_filter`
filters out static/near-static clips; this operator filters out clips that move but in a
geometrically incoherent way.

## Test run

```bash
# All 15 new tests pass
pytest tests/ops/filter/test_video_camera_motion_consistency_filter.py -v

# No regression in adjacent operators
pytest tests/ops/filter/test_video_motion_score_filter.py \
       tests/ops/filter/test_video_resolution_filter.py \
       tests/ops/filter/test_video_duration_filter.py -v
```

## Notes

- Operator is registered `UNFORKABLE` (cv2 is not fork-safe) — consistent with existing cv2-based video operators.
- No new pip dependencies: uses only `cv2` and `numpy`, both already required by data-juicer.
- `min_consistency` default of `0.05` is calibrated on real nuScenes mini front-camera clips (which score 0.10–0.25 due to foreground vehicles partially breaking the planar-background assumption) so genuine driving footage is not filtered by default.
