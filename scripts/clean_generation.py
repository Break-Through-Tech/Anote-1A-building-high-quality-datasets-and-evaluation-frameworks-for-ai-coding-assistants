"""
clean_generation.py

Loads the raw MBPP (sanitized) dataset and converts it into our project's
unified schema for code generation tasks, saving the result as JSONL.
"""

import json
import os
from datasets import load_from_disk

RAW_PATH = "data/raw/mbpp"
OUTPUT_PATH = "data/processed/generation.jsonl"


def build_record(row, split_name):
    """Map one MBPP row into our unified schema."""
    prompt = row["prompt"]
    ground_truth = row["code"]

    # Combine test_imports + test_list into one test_cases block
    test_cases = row["test_imports"] + row["test_list"]

    record = {
        "id": f"mbpp_{split_name}_{row['task_id']}",
        "source_dataset": "MBPP_sanitized",
        "task_type": "generation",
        "language": "python",
        "prompt": prompt,
        "input_code": "",  # no starting code for pure generation
        "ground_truth": ground_truth,
        "test_cases": test_cases,
        "has_tests": len(test_cases) > 0,
        "prompt_length": len(prompt.split()),
        "code_length": len(ground_truth.split()),
        "license": "CC-BY-4.0",  # MBPP license 
        "notes": f"source_file={row['source_file']}",
    }
    return record


def is_valid(record):
    """Basic quality filter: drop malformed rows."""
    if not record["prompt"] or not record["ground_truth"]:
        return False
    if not record["has_tests"]:
        return False
    return True


def main():
    ds = load_from_disk(RAW_PATH)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    seen_prompts = set()
    kept = 0
    dropped = 0

    with open(OUTPUT_PATH, "w") as f:
        for split_name in ["train", "validation", "test"]:
            for row in ds[split_name]:
                record = build_record(row, split_name)

                # Deduplicate on prompt text
                if record["prompt"] in seen_prompts:
                    dropped += 1
                    continue

                if not is_valid(record):
                    dropped += 1
                    continue

                seen_prompts.add(record["prompt"])
                f.write(json.dumps(record) + "\n")
                kept += 1

    print(f"Done. Kept {kept} records, dropped {dropped} (dupes/malformed).")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()