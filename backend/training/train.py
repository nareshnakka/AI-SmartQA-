"""
QEOS Model Fine-Tuning Scaffold (Phase 3)

Train a domain-specific quality engineering model on your organization's data.

Prerequisites:
  pip install -r requirements-training.txt
  GPU with 16GB+ VRAM recommended (or use cloud training)

Steps:
  1. Prepare training data (see data/format.json for schema)
  2. Run: python train.py --data data/samples.jsonl --output models/qeos-v1
  3. Deploy with Ollama: ollama create qeos-qe -f Modelfile
  4. Set DEFAULT_LLM_PROVIDER=ollama and DEFAULT_LLM_MODEL=qeos-qe
"""

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def validate_training_record(record: dict) -> bool:
    required = {"instruction", "input", "output"}
    return required.issubset(record.keys())


def format_for_finetuning(records: list[dict]) -> list[dict]:
    """Convert to HuggingFace/OpenAI fine-tuning format."""
    formatted = []
    for r in records:
        if not validate_training_record(r):
            continue
        formatted.append({
            "messages": [
                {"role": "system", "content": r.get("instruction", "You are a QA engineer.")},
                {"role": "user", "content": r["input"]},
                {"role": "assistant", "content": r["output"]},
            ]
        })
    return formatted


def main():
    parser = argparse.ArgumentParser(description="QEOS Model Fine-Tuning")
    parser.add_argument("--data", type=Path, required=True, help="Training JSONL file")
    parser.add_argument("--output", type=Path, default=Path("models/qeos-v1"))
    parser.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Validate data only")
    args = parser.parse_args()

    records = load_jsonl(args.data)
    valid = [r for r in records if validate_training_record(r)]
    print(f"Loaded {len(records)} records, {len(valid)} valid")

    if args.dry_run:
        formatted = format_for_finetuning(valid)
        print(f"Would fine-tune {len(formatted)} examples on {args.base_model}")
        return

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig, get_peft_model
        from trl import SFTTrainer
    except ImportError:
        print("Install training dependencies: pip install -r requirements-training.txt")
        print("Or use --dry-run to validate your training data format.")
        return

    formatted = format_for_finetuning(valid)
    args.output.mkdir(parents=True, exist_ok=True)

    # Save formatted data for inspection
    with open(args.output / "training_data.json", "w") as f:
        json.dump(formatted, f, indent=2)

    print(f"Training data saved to {args.output / 'training_data.json'}")
    print(f"To complete fine-tuning, configure SFTTrainer with base model: {args.base_model}")
    print("See docs/QEOS-NATIVE-INTELLIGENCE.md for full instructions.")


if __name__ == "__main__":
    main()
