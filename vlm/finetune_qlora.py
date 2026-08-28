"""Phase 6: QLoRA fine-tuning of Qwen2-VL-2B on nuScenes driving captions.

Trains a LoRA adapter on top of Qwen2-VL-2B-Instruct using the structured
captions from generate_captions.py. Parameterized by split (A/B/C) for the
attribution experiment.

Usage (from project root, with data-juicer venv):
    python vlm/finetune_qlora.py --split A --output-dir vlm/checkpoints/A
    python vlm/finetune_qlora.py --split B --output-dir vlm/checkpoints/B
    python vlm/finetune_qlora.py --split C --output-dir vlm/checkpoints/C
"""
import argparse
import json
import os

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
    Qwen2VLForConditionalGeneration,
    Trainer,
    TrainingArguments,
)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models/Qwen2-VL-2B")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_jsonl(path: str) -> list:
    rows = []
    with open(path) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def format_prompt(row: dict) -> str:
    return (
        f"<|im_start|>user\n{row['caption']}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


def format_target(row: dict) -> str:
    # Target is the structured caption itself (self-supervised on the structured template)
    return row["caption"] + "<|im_end|>"


def build_hf_dataset(rows: list, tokenizer, max_length: int = 512) -> Dataset:
    prompts = [format_prompt(r) for r in rows]
    targets = [format_target(r) for r in rows]

    encodings = tokenizer(
        [p + t for p, t in zip(prompts, targets)],
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    # Mask prompt tokens in labels (only train on the assistant response)
    prompt_lens = [
        len(tokenizer(p, add_special_tokens=False)["input_ids"])
        for p in prompts
    ]
    labels = encodings["input_ids"].clone()
    for i, plen in enumerate(prompt_lens):
        labels[i, :plen] = -100

    return Dataset.from_dict({
        "input_ids": encodings["input_ids"].tolist(),
        "attention_mask": encodings["attention_mask"].tolist(),
        "labels": labels.tolist(),
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["A", "B", "C"], required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-dir", default=MODEL_DIR)
    parser.add_argument("--num-epochs", type=int, default=3)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=512)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    train_path = os.path.join(DATA_DIR, f"train_{args.split}.jsonl")
    val_path = os.path.join(DATA_DIR, f"val_{args.split}.jsonl")
    train_rows = load_jsonl(train_path)
    val_rows = load_jsonl(val_path)
    print(f"Split {args.split}: {len(train_rows)} train, {len(val_rows)} val")

    # QLoRA: 4-bit quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = Qwen2VLForConditionalGeneration.from_pretrained(
        args.model_dir,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_dataset = build_hf_dataset(train_rows, tokenizer, args.max_length)
    val_dataset = build_hf_dataset(val_rows, tokenizer, args.max_length)

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        fp16=True,
        logging_steps=10,
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
    )
    trainer.train()

    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"Checkpoint saved to {args.output_dir}")


if __name__ == "__main__":
    main()
