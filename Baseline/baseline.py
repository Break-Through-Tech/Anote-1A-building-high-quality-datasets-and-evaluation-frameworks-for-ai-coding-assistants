"""
baseline.py

Runs Task #4's baseline for code generation: sends the same MBPP + HumanEval
problems to a model, scores the results with evaluator.py, and writes a
results file. This file is just the shared framework (loading, scoring,
output) - the actual per-provider API calls and config live in
AI_models/providers.py, see that file for the "claude" vs. "opensource"
details. Scoring logic lives in Evaluator/evaluator.py.

Folder layout (repo root):
    Baseline/baseline.py     <- this file
    Evaluator/evaluator.py   <- scoring (Task #5)
    AI_models/providers.py   <- per-provider config + API calls

Usage (run from the repo root, not from inside Baseline/):
    python Baseline/baseline.py claude 5        # Claude, via Panacea's pinned config
    python Baseline/baseline.py opensource 3    # open-source model, via OpenRouter (free)

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # paste ANTHROPIC_API_KEY and/or OPENROUTER_API_KEY
"""

# --- imports ---
import json
import os
import sys
import time
from pathlib import Path

# This file lives in Baseline/, but Evaluator/ and AI_models/ are sibling
# folders under the repo root - add the repo root to sys.path so
# "Evaluator.evaluator" and "AI_models.providers" can be found no matter
# where this script is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from datasets import load_dataset
from dotenv import load_dotenv

from Evaluator.evaluator import evaluate, from_humaneval, from_mbpp, summarize
from AI_models.providers import PROVIDERS

load_dotenv(REPO_ROOT / ".env")  # .env lives at the repo root, not in Baseline/


# =====================================================================
# LOAD ITEMS
# =====================================================================

# Pull the first n problems from each dataset and convert them to the
# shared schema from evaluator.py. Fixed order (always [:n]) = reproducible.
def load_items(n: int) -> list:
    mbpp = load_dataset("google-research-datasets/mbpp", "full", split=f"test[:{n}]")
    he = load_dataset("openai/openai_humaneval", split=f"test[:{n}]")
    return [from_mbpp(dict(r)) for r in mbpp] + [from_humaneval(dict(r)) for r in he]


# =====================================================================
# RUN + SCORE
# =====================================================================

# Send one item's prompt through the chosen provider's adapter and score the reply.
def run_one(provider_name: str, client, item: dict) -> dict:
    p = PROVIDERS[provider_name]
    start = time.time()
    text, tokens, model_used = p["call"](client, item, p["config"])
    result = evaluate(item, text, latency_s=round(time.time() - start, 2), output_tokens=tokens)
    result["output"] = text            # keep the raw response for manual review
    result["model_used"] = model_used  # which model actually answered (can vary for "opensource")
    return result


# Run every item one at a time (simplest, and keeps rate limits predictable).
def run_all(provider_name: str, client, items: list) -> list:
    return [run_one(provider_name, client, it) for it in items]


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    # `python Baseline/baseline.py <provider> [n]`
    if len(sys.argv) < 2 or sys.argv[1] not in PROVIDERS:
        sys.exit(f"Usage: python Baseline/baseline.py <{'|'.join(PROVIDERS)}> [n]")
    provider_name = sys.argv[1]
    p = PROVIDERS[provider_name]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else p["default_n"]

    # Fail fast with a clear message instead of a raw error.
    api_key = os.environ.get(p["api_key_env"])
    if not api_key:
        sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")

    client = p["client_factory"](api_key)
    results = run_all(provider_name, client, load_items(n))
    summary = summarize(results)

    # Save the output file at the repo root (not inside Baseline/), so it
    # sits next to .env / requirements.txt like before.
    out_path = REPO_ROOT / p["output_file"]
    with open(out_path, "w") as f:
        json.dump({"provider": provider_name, "config": p["config"], "summary": summary,
                   "results": results}, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
