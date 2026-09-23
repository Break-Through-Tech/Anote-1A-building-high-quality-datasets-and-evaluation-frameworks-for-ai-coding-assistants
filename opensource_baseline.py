"""
opensource_baseline.py

Runs the open-source model baseline (Task #4's "or other open-source LLMs")
for code generation. Uses OpenRouter instead of local hardware - it's a
hosted API call to an open-source model, so nothing runs on your machine.
Same MBPP + HumanEval problems, same evaluator.py scoring, as panacea_baseline.py.

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # then paste your real OPENROUTER_API_KEY (.env is gitignored)
Usage:
    python opensource_baseline.py 10   # 10 problems from each dataset -> opensource_run.json
"""

# --- imports ---
import json
import os
import sys
import time

from datasets import load_dataset
from dotenv import load_dotenv
from openai import OpenAI  # OpenRouter speaks the OpenAI API format

from evaluator import evaluate, from_humaneval, from_mbpp, summarize

load_dotenv()  # reads .env into the environment if present; no-op if it doesn't exist


# =====================================================================
# 1. PINNED CONFIG
# Same idea as panacea_baseline.py's BASELINE dict: lock the model and
# settings so this run is reproducible.
# =====================================================================
CONFIG = {
    "provider": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    # "openrouter/free" auto-routes to whatever free model is currently
    # available, so it won't go stale like a hardcoded model id would.
    # The actual model that answered each request is recorded per-item
    # below (resp.model), since it can vary call to call.
    "model": "openrouter/free",
    "system_prompt": "You are an expert coding assistant.",  # same prompt as the Claude baseline
    "max_tokens": 4096,
    "temperature": 0,
    "datasets": ["google-research-datasets/mbpp (full, test)", "openai/openai_humaneval (test)"],
}


# =====================================================================
# 2. LOAD ITEMS
# =====================================================================

# Pull the first n problems from each dataset (same items as the Claude
# baseline, so the two runs are directly comparable).
def load_items(n: int) -> list:
    mbpp = load_dataset("google-research-datasets/mbpp", "full", split=f"test[:{n}]")
    he = load_dataset("openai/openai_humaneval", split=f"test[:{n}]")
    return [from_mbpp(dict(r)) for r in mbpp] + [from_humaneval(dict(r)) for r in he]


# =====================================================================
# 3. RUN + SCORE
# =====================================================================

# Send one item's prompt to the model over OpenRouter and score the reply.
def run_one(client, item: dict) -> dict:
    start = time.time()
    resp = client.chat.completions.create(
        model=CONFIG["model"],
        max_tokens=CONFIG["max_tokens"],
        temperature=CONFIG["temperature"],
        messages=[{"role": "system", "content": CONFIG["system_prompt"]},
                {"role": "user", "content": item["prompt"]}],
    )
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.completion_tokens if resp.usage else None
    result = evaluate(item, text, latency_s=round(time.time() - start, 2), output_tokens=tokens)
    result["output"] = text          # keep the raw response for manual review
    result["model_used"] = resp.model  # openrouter/free can route to a different model each call
    return result


# Run every item one at a time - free-tier models are rate-limited (about
# 50 requests/day without purchased credits), so keep samples small.
def run_all(client, items: list) -> list:
    return [run_one(client, it) for it in items]


# =====================================================================
# 4. ENTRY POINT
# =====================================================================
def main():
    # Sample size comes from the command line: `python opensource_baseline.py 5`.
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3  # small default - stay inside free rate limits

    # Fail fast with a clear message instead of a raw error.
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY not set. Copy .env.example to .env and fill it in.")

    client = OpenAI(base_url=CONFIG["base_url"], api_key=api_key)
    results = run_all(client, load_items(n))
    summary = summarize(results)

    # Save everything (config + per-item results + summary) for reproducibility.
    with open("opensource_run.json", "w") as f:
        json.dump({"config": CONFIG, "summary": summary, "results": results}, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
