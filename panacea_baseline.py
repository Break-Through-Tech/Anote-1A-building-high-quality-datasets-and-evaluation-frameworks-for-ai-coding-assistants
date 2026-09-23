"""
panacea_baseline.py

Runs the Claude baseline (Task #4) for code generation: sends MBPP + HumanEval
problems to Claude using Panacea's own default settings (pinned below for
reproducibility), scores the results with evaluator.py, and writes
baseline_run.json.

ATTRIBUTION: the config values below (model, prompt, decoding, Panacea commit)
are early research into Panacea's defaults, done to unblock this script - they
are NOT a finished answer. Identifying and confirming the comparison config is
Task #6 (Nebiyu's), not this task (#4). Treat BASELINE below as a draft for
Nebiyu to confirm or adjust, not a settled decision.

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # then paste your real ANTHROPIC_API_KEY (.env is gitignored)
Usage:
    python panacea_baseline.py 10   # 10 problems from each dataset -> baseline_run.json
"""

# --- imports ---
import json
import os
import sys
import time

import anthropic
from datasets import load_dataset
from dotenv import load_dotenv

from evaluator import evaluate, from_humaneval, from_mbpp, summarize

load_dotenv()  # reads .env into the environment if present; no-op if it doesn't exist


# =====================================================================
# 1. PINNED CONFIG (draft - Task #6 / Nebiyu owns confirming this)
# Every value here was read directly out of the Panacea repo (see the
# comment on each line) so the baseline is exactly reproducible. This is
# research input for Task #6, not a finalized decision - swap in Nebiyu's
# confirmed config once Task #6 is done.
# =====================================================================
BASELINE = {
    "panacea_repo": "https://github.com/anote-ai/Panacea",
    "panacea_commit": "bea399509efbab4ac242042b64f8b28b8865691e",  # main as of 2026-09-15
    "model": "claude-sonnet-4-6",          # Panacea's DEFAULT_MODEL / coding agent model
    "system_prompt": "You are an expert coding assistant.",  # coding_agent.py
    "max_tokens": 4096,                    # llm.complete() default
    "temperature": 0,                      # not set in Panacea; pinned here for reproducibility
    "max_iterations": 5,                   # coding_agent.py AgentExecutor (unused: no agent loop here)
    "datasets": ["google-research-datasets/mbpp (full, test)", "openai/openai_humaneval (test)"],
}


# =====================================================================
# 2. LOAD ITEMS
# =====================================================================

# Pull the first n problems from each dataset and convert them to the
# shared schema from evaluator.py. Fixed order (always [:n]) = reproducible.
def load_items(n: int) -> list:
    mbpp = load_dataset("google-research-datasets/mbpp", "full", split=f"test[:{n}]")
    he = load_dataset("openai/openai_humaneval", split=f"test[:{n}]")
    return [from_mbpp(dict(r)) for r in mbpp] + [from_humaneval(dict(r)) for r in he]


# =====================================================================
# 3. RUN + SCORE
# =====================================================================

# Send one item's prompt to Claude and score the reply.
def run_one(client, item: dict) -> dict:
    start = time.time()
    resp = client.messages.create(
        model=BASELINE["model"],
        max_tokens=BASELINE["max_tokens"],
        temperature=BASELINE["temperature"],
        system=BASELINE["system_prompt"],
        messages=[{"role": "user", "content": item["prompt"]}],
    )
    block = resp.content[0] if resp.content else None
    text = block.text if block is not None and hasattr(block, "text") else ""
    result = evaluate(item, text, latency_s=round(time.time() - start, 2),
                      output_tokens=resp.usage.output_tokens)
    result["output"] = text  # keep the raw response for manual review
    return result


# Run every item one at a time (simplest, and keeps rate limits predictable).
def run_all(client, items: list) -> list:
    return [run_one(client, it) for it in items]


# =====================================================================
# 4. ENTRY POINT
# =====================================================================
def main():
    # Sample size comes from the command line: `python panacea_baseline.py 10`.
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    # Fail fast with a clear message instead of a raw KeyError.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in.")

    client = anthropic.Anthropic(api_key=api_key)
    results = run_all(client, load_items(n))
    summary = summarize(results)

    # Save everything (config + per-item results + summary) for reproducibility.
    with open("baseline_run.json", "w") as f:
        json.dump({"config": BASELINE, "summary": summary, "results": results}, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
