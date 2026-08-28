"""Phase 6: Evaluate fine-tuned VLM checkpoints on val sets.

For each split (A/B/C), generates captions on the val set using the fine-tuned
checkpoint, then computes:
  - JSON field F1: precision/recall/F1 over extracted structured fields
    (speed, rotation, top object categories)
  - Hallucination rate: object categories mentioned in generation but absent
    from ground-truth annotation for that clip

Usage (from project root, with data-juicer venv):
    python vlm/evaluate.py
    python vlm/evaluate.py --splits A B C --checkpoint-dir vlm/checkpoints
"""
import argparse
import json
import os
import re

import torch
from peft import PeftModel
from transformers import AutoTokenizer, Qwen2VLForConditionalGeneration

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models/Qwen2-VL-2B")
CHECKPOINT_DIR = os.path.join(os.path.dirname(__file__), "checkpoints")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

NUSCENES_CATEGORIES = {
    "human.pedestrian.adult", "human.pedestrian.child", "human.pedestrian.wheelchair",
    "vehicle.car", "vehicle.truck", "vehicle.bus.rigid", "vehicle.bicycle",
    "vehicle.motorcycle", "vehicle.trailer", "movable_object.barrier",
    "movable_object.trafficcone", "static_object.bicycle_rack",
}


def load_jsonl(path: str) -> list:
    with open(path) as f:
        return [json.loads(line) for line in f]


def extract_fields(text: str) -> dict:
    """Extract structured fields from a caption string via regex."""
    fields = {}

    m = re.search(r"avg speed ([\d.]+) m/s", text)
    if m:
        fields["avg_speed"] = float(m.group(1))

    m = re.search(r"total rotation ([\d.]+) rad", text)
    if m:
        fields["total_rotation"] = float(m.group(1))

    # Extract any nuScenes category mentions
    mentioned_cats = set()
    for cat in NUSCENES_CATEGORIES:
        short = cat.split(".")[-1]
        if short in text.lower() or cat in text:
            mentioned_cats.add(cat)
    if mentioned_cats:
        fields["categories"] = mentioned_cats

    m = re.search(r"(\d+) pedestrian", text)
    if m:
        fields["pedestrian_count"] = int(m.group(1))

    return fields


def field_f1(pred_fields: dict, gt_fields: dict) -> dict:
    """Compute token-level F1 over field keys present in either pred or gt."""
    pred_keys = set(pred_fields.keys())
    gt_keys = set(gt_fields.keys())
    if not pred_keys and not gt_keys:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    tp = len(pred_keys & gt_keys)
    precision = tp / len(pred_keys) if pred_keys else 0.0
    recall = tp / len(gt_keys) if gt_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def hallucination_rate(generated: str, gt_caption: str) -> float:
    """Fraction of generated category mentions not in ground-truth caption."""
    gen_cats = {cat for cat in NUSCENES_CATEGORIES if cat.split(".")[-1] in generated.lower()}
    gt_cats = {cat for cat in NUSCENES_CATEGORIES if cat.split(".")[-1] in gt_caption.lower()}
    if not gen_cats:
        return 0.0
    false_pos = len(gen_cats - gt_cats)
    return false_pos / len(gen_cats)


def generate_caption(model, tokenizer, prompt: str, max_new_tokens: int = 200) -> str:
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def evaluate_split(split: str, checkpoint_dir: str) -> dict:
    val_path = os.path.join(DATA_DIR, f"val_{split}.jsonl")
    ckpt_path = os.path.join(checkpoint_dir, split)

    if not os.path.exists(val_path):
        return {"error": f"val_{split}.jsonl not found"}
    if not os.path.exists(ckpt_path):
        return {"error": f"checkpoint {ckpt_path} not found"}

    val_rows = load_jsonl(val_path)
    print(f"  Loading checkpoint {ckpt_path}...")

    tokenizer = AutoTokenizer.from_pretrained(ckpt_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, ckpt_path)
    model.eval()

    f1_scores, halluc_rates = [], []
    for row in val_rows:
        prompt = (
            f"<|im_start|>user\n{row['caption']}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        generated = generate_caption(model, tokenizer, prompt)

        pred_fields = extract_fields(generated)
        gt_fields = extract_fields(row["caption"])

        f1 = field_f1(pred_fields, gt_fields)
        h_rate = hallucination_rate(generated, row["caption"])

        f1_scores.append(f1["f1"])
        halluc_rates.append(h_rate)

    del model, base_model
    torch.cuda.empty_cache()

    n = len(f1_scores)
    return {
        "split": split,
        "n_val": n,
        "mean_field_f1": round(sum(f1_scores) / n, 4) if n else 0,
        "mean_hallucination_rate": round(sum(halluc_rates) / n, 4) if n else 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", nargs="+", default=["A", "B", "C"])
    parser.add_argument("--checkpoint-dir", default=CHECKPOINT_DIR)
    parser.add_argument("--output-dir", default=RESULTS_DIR)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    all_results = {}

    for split in args.splits:
        print(f"Evaluating split {split}...")
        result = evaluate_split(split, args.checkpoint_dir)
        all_results[split] = result
        out_path = os.path.join(args.output_dir, f"eval_{split}.json")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  {result}")
        print(f"  Saved to {out_path}")

    # Summary table
    print("\n## Evaluation Results\n")
    print("| Split | Val clips | Field F1 | Hallucination rate |")
    print("|---|---|---|---|")
    for s in args.splits:
        r = all_results.get(s, {})
        if "error" in r:
            print(f"| {s} | — | ERROR: {r['error']} | — |")
        else:
            print(f"| {s} | {r.get('n_val','?')} | {r.get('mean_field_f1','?')} | {r.get('mean_hallucination_rate','?')} |")


if __name__ == "__main__":
    main()
