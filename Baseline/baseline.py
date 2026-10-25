"""
baseline.py

Runs Task #4's baseline: sends problems from the unified dataset to a model,
scores the results with evaluator.py, and writes a results file. This file is
just the shared framework (loading, prompting, scoring, output) - the actual
per-provider API calls and config live in AI_models/providers.py, the prompt
detail levels live in AI_models/prompts.py, and scoring lives in
Evaluator/evaluator.py.

Folder layout (repo root):
    Baseline/baseline.py         <- this file
    Baseline/compare_runs.py     <- compares saved runs (prompt levels, providers)
    Evaluator/evaluator.py       <- scoring (Task #5)
    AI_models/providers.py       <- per-provider config + API calls
    AI_models/prompts.py         <- basic / detailed / extreme prompt levels
    data/unified/unified_eval.jsonl  <- the problems

Usage (run from the repo root, not from inside Baseline/):
    python Baseline/baseline.py claude 5                 # Claude, 5 problems per dataset
    python Baseline/baseline.py panacea 3                # Panacea's coding agent
    python Baseline/baseline.py opensource 3             # open-source model via OpenRouter (free)
    python Baseline/baseline.py reference 5              # no API: sanity-checks the pipeline, expect 1.0

    python Baseline/baseline.py claude 5 --level all     # basic, detailed and extreme prompts

Options:
    --level  raw | basic | detailed | extreme | all   (default raw = the dataset's own prompt)
    --task   code_generation                          (bug_fixing / all commented out until
                                                       the bug-fix experiments start)

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # paste ANTHROPIC_API_KEY and/or OPENROUTER_API_KEY
"""

# --- imports ---
import argparse
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

from Evaluator.evaluator import evaluate, load_items, summarize
from AI_models.prompts import ALL_LEVELS, LEVELS, build_prompt
from AI_models.providers import PROVIDERS, AdapterError

try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")  # .env lives at the repo root, not in Baseline/
except ImportError:  # python-dotenv not installed: fall back to the shell environment
    pass


# =====================================================================
# RUN + SCORE
# =====================================================================

# Send one item's prompt (at the given detail level) through the chosen provider's adapter and score the reply.
def run_one(provider_name: str, client, item: dict, level: str = "raw") -> dict:
    p = PROVIDERS[provider_name]
    prompt = build_prompt(item, level)
    start = time.time()
    try:
        text, tokens, model_used = p["call"](client, {**item, "prompt": prompt}, p["config"])
    except AdapterError as e:
        # The provider ran but gave no usable answer. Count it as a failed run, not model output.
        result = evaluate(item, "", latency_s=round(time.time() - start, 2))
        result.update(score=0.0, test_pass_rate=0.0, error=f"adapter_error: {e}", failed_run=True)
        text, model_used = "", None
    else:
        result = evaluate(item, text, latency_s=round(time.time() - start, 2), output_tokens=tokens)
        result["failed_run"] = False
    result["task_type"] = item["task_type"]
    result["prompt_level"] = level
    result["prompt"] = prompt          # exactly what was sent, for comparing levels later
    result["output"] = text            # keep the raw response for manual review
    result["model_used"] = model_used  # which model actually answered (can vary for "opensource")
    return result


# Run every item one at a time (simplest, and keeps rate limits predictable).
def run_all(provider_name: str, client, items: list, level: str = "raw") -> list:
    results = []
    for i, it in enumerate(items, 1):
        r = run_one(provider_name, client, it, level)
        print(f"  [{level}] {i}/{len(items)} {r['id']}: score={r['score']}", file=sys.stderr)
        results.append(r)
    return results


# Break the summary down by task type too, since code generation and bug fixing are compared separately.
def summarize_run(results: list) -> dict:
    summary = summarize(results)
    for tt in sorted({r["task_type"] for r in results}):
        summary[tt] = summarize([r for r in results if r["task_type"] == tt])["overall"]
    summary["failed_runs"] = sum(1 for r in results if r.get("failed_run"))
    return summary


# Output file name: baseline_run.json for raw, baseline_<level>_run.json otherwise
# (both match the *_run.json pattern in .gitignore, so run outputs are never committed).
def output_name(base: str, level: str) -> str:
    return base if level == "raw" else base.replace("_run.json", f"_{level}_run.json")


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Run a provider over the unified dataset and score it.")
    ap.add_argument("provider", choices=list(PROVIDERS))
    ap.add_argument("n", nargs="?", type=int, help="problems per dataset (default: provider's default_n)")
    ap.add_argument("--level", default="raw", choices=list(ALL_LEVELS) + ["all"])
    # Bug fixing is commented out until the bug-fix experiments (secondary set).
    ap.add_argument("--task", default="code_generation", choices=["code_generation"])  # , "bug_fixing", "all"
    args = ap.parse_args()

    provider_name = args.provider
    p = PROVIDERS[provider_name]
    # n = tasks per dataset (first n in file order, so runs are reproducible)
    n = args.n if args.n is not None else p["default_n"]
    levels = list(LEVELS) if args.level == "all" else [args.level]

    # Fail fast with a clear message instead of a raw error.
    api_key = None
    if p["api_key_env"]:
        api_key = os.environ.get(p["api_key_env"])
        if not api_key:
            sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")

    client = p["client_factory"](api_key)
    # "all" keeps every task type; the evaluator skips items it cannot score yet (and says so on stderr)
    items = load_items(task_type=None if args.task == "all" else args.task, n_per_source=n)
    if not items:
        sys.exit("No items to run (check --task).")
    print(f"{provider_name}: {len(items)} items x {len(levels)} level(s): {', '.join(levels)}", file=sys.stderr)

    for level in levels:
        results = run_all(provider_name, client, items, level)
        summary = summarize_run(results)

        # Save the output file at the repo root (not inside Baseline/), so it
        # sits next to .env / requirements.txt like before.
        out_path = REPO_ROOT / output_name(p["output_file"], level)
        with open(out_path, "w") as f:
            json.dump({"provider": provider_name, "prompt_level": level, "task": args.task,
                       "n_per_dataset": n, "config": p["config"], "summary": summary,
                       "results": results}, f, indent=2)
        print(f"\n== {provider_name} / {level} -> {out_path.name}")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
