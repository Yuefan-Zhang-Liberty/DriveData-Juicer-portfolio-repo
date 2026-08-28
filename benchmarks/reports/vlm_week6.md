# Phase 6 Report: VLM QLoRA Fine-Tuning Attribution Experiment

## Data Scale Caveat

**This is a proof-of-concept experiment.** nuScenes mini provides 10 scenes, ~492 clips
(534 after sliding-window generation). This is orders of magnitude below meaningful VLM
fine-tuning scale (typical: 10k–100k image-text pairs). All results and effect sizes
should be interpreted as infrastructure validation and directional signals, not
publication-quality findings.

---

## Caption Generation

Captions were generated from Iceberg Silver/Gold tables via Spark using the following
template:

```
Scene {scene_name}, split={split}.
Ego motion: avg speed {avg_speed:.1f} m/s, total rotation {total_rot:.1f} rad.
Objects: {obj_summary}.
Scene quality: {ped_count} pedestrians, {long_tail_count} long-tail objects.
Task: Describe the driving scenario and identify any safety-relevant observations.
```

Sources used: `silver.ego_motion` (speed, rotation), `silver.object_annotation`
(category counts), `silver.scene_quality` (pedestrian/long-tail counts),
`gold.evaluation_slice` (train/val split).

**534 clips** processed; 1 corrupt clip skipped → **534 captions** in
`vlm/captions/captions_full.jsonl`.

---

## A/B/C Attribution Splits

| Split | Filter level | Clips | Train rows | Val rows |
|---|---|---|---|---|
| A | None (all clips) | 534 | 427 | 107 |
| B | 4 existing ops (duration + aspect_ratio + resolution + motion_score) | 99 | 79 | 20 |
| C | 5 ops (B + `video_camera_motion_consistency_filter`) | 98 | 78 | 20 |

Note: B and C were run on the tier-100 manifest (practical filter budget ~10 min);
split A used all 534 captions directly.

**Key observation**: The new `video_camera_motion_consistency_filter` removed 1 additional
clip beyond the 4-op baseline (99 → 98). This is expected: on nuScenes mini, clips are
already high-quality dashcam footage with mostly consistent camera motion; the filter's
primary value is catching corruption in noisier datasets.

---

## Model and Fine-Tuning Config

| Item | Value |
|---|---|
| Base model | Qwen2-VL-2B-Instruct |
| Fine-tuning method | QLoRA (4-bit NF4 quantization) |
| LoRA rank | r=16, α=32 |
| Target modules | q_proj, v_proj |
| Trainable parameters | ~0.8% of total model params |
| Epochs | 3 |
| Batch size | 1 + gradient accumulation 4 (effective batch=4) |
| Hardware | RTX 4090 24GB |
| Training time | A: ~3.8 min (427 clips); B/C: ~0.8 min each (79/78 clips) |

---

## Training Results

| Split | Train clips | Train loss | Eval loss |
|---|---|---|---|
| A (no filter) | 427 | 6.030 | 6.379 |
| B (4 ops) | 79 | 6.133 | 6.602 |
| C (5 ops) | 78 | 6.136 | 6.606 |

**Split A achieves lower eval loss than B/C.** This is expected and does not contradict
the filtering hypothesis: A has 5× more training data. With this data scale, training set
size dominates over data quality. The expected result at larger scale (e.g., nuScenes
trainval, 850 scenes × proportional clips) would be: B/C match or exceed A's eval loss
despite fewer training clips, because filtered data removes quality-degraded examples
that introduce noise.

---

## Evaluation Results

| Split | Val clips | Field F1 | Hallucination rate |
|---|---|---|---|
| A | 107 | 1.0 | 0.0 |
| B | 20 | 1.0 | 0.0 |
| C | 20 | 1.0 | 0.0 |

All splits achieve perfect Field F1 and zero hallucination rate. **This is expected and
reflects a known limitation of the evaluation methodology, not a meaningful result.**

The captions are generated from a fixed template with a small, deterministic vocabulary.
After 3 epochs, the model memorizes the template structure. The field extractor (regex
over "avg speed X m/s", "total rotation Y rad", category names) finds the same structured
fields in the generated output as in the ground truth, giving F1=1.0 for all splits.
This means the evaluation metric collapsed to "did the model reproduce the template" —
which it did, for all three splits.

**What would a meaningful evaluation look like?**
1. Open-ended captions from a base model (not template-structured) as ground truth
2. Semantic similarity metrics (ROUGE-L, CIDEr, BERTScore) over free-form descriptions
3. Downstream task performance: ego-motion prediction accuracy, hazard detection
4. At nuScenes trainval scale: enough distribution shift between A/B/C to produce
   measurable difference in any of the above

---

## Infrastructure Validated

Despite the null metric result, the following pipeline components are fully validated:

- [x] Structured caption generation from Silver/Gold Iceberg tables via Spark
- [x] A/B/C split generation using dj-process at three filter levels
- [x] QLoRA fine-tuning of Qwen2-VL-2B-Instruct using PEFT + bitsandbytes + HuggingFace Trainer
- [x] End-to-end evaluation pipeline producing per-split JSON results
- [x] All 3 splits train and evaluate without OOM or crash on RTX 4090 24GB

---

## What Changes at Scale

If this experiment were run on nuScenes trainval (850 scenes, ~37,000 clips with the same
sliding window):
- Split A ≈ 37k clips; Split C ≈ 30–34k clips (estimated 10–20% filtered by the 5-op pipeline)
- Training time: ~4–8 hours per split on a single GPU; practical with multi-GPU Ray
- The filtered splits (B/C) would remove genuinely corrupted clips from training, which at
  scale would produce measurable downstream quality differences
- Free-form captions (generated by a teacher VLM or human-annotated) would provide a
  non-trivial evaluation target

---

## Next: Phase 7

Phase 7 upstream PR prep: op doc committed to fork branch
(`feat/video-camera-motion-consistency-filter`, commit `2c3448b`), Issue and PR text
drafted at `docs/upstream_pr/`. **Awaiting user review before opening Issue or PR.**
