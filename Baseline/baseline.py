"""
baseline.py

Runs Task #4's baseline: sends problems from the unified dataset to a model,
scores the results with evaluator.py, and writes a results file. Every answer is
scored twice: on the hidden tests (the headline pass@1; the model never sees them)
and on the public tests (pass@1 shown beside it). An answer that passes the public
tests but fails the hidden ones is a "false pass". This file is
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
    python Baseline/baseline.py claude --ids smoke.txt   # exactly the tasks in data/unified/task_lists/smoke.txt
    python Baseline/baseline.py claude 2 --source mbpp   # 2 MBPP tasks only

Options:
    n        problems per dataset, first n in file order (default 3 for every provider)
    --level  raw | basic | detailed | extreme | all   (default raw = the dataset's own prompt)
    --task   code_generation                          (bug_fixing / all commented out until
                                                       the bug-fix experiments start)
    --source only this dataset (repeat for several)
    --ids    a task list from data/unified/task_lists/; every arm run from the same list gets the
             same tasks. Not combined with n or --source.

The run file is rewritten after every item, so an error or Ctrl-C keeps the finished ones.
API errors left after the SDK's own retries count as a failed run (score 0), and pass@1 is
reported both with and without failed runs. Run files record the evaluator's scoring_version,
and compare_runs.py refuses to compare runs scored by different versions.

To check the whole pipeline without any API calls: python Evaluator/self_test.py

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
from collections import Counter
from pathlib import Path

# This file lives in Baseline/, but Evaluator/ and AI_models/ are sibling
# folders under the repo root - add the repo root to sys.path so
# "Evaluator.evaluator" and "AI_models.providers" can be found no matter
# where this script is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env before importing providers.py, which reads PANACEA_PATH when it is imported.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")  # .env lives at the repo root, not in Baseline/
except ImportError:  # python-dotenv not installed: fall back to the shell environment
    pass

from Evaluator.evaluator import SCORING_VERSION, evaluate, load_items, summarize
from AI_models.prompts import ALL_LEVELS, LEVELS, build_prompt
from AI_models.providers import PROVIDERS, AdapterError

TASK_LISTS_DIR = REPO_ROOT / "data" / "unified" / "task_lists"  # shared task-id lists, one id per line


# =====================================================================
# RUN + SCORE
# =====================================================================

# Score one answer on the hidden tests (the headline: the model never sees them) and on the public tests
# (the ones feedback may show). Hidden results keep counts only, so no hidden test text lands in run files.
# Tasks without hidden tests (bug fixing) are scored on their public tests, and say so in "scored_on".
def score_both(item: dict, text: str, latency_s: float = None, output_tokens: int = None) -> dict:
    public = evaluate(item, text, latency_s, output_tokens, split="public")
    try:
        hidden = evaluate(item, text, latency_s, output_tokens, split="private", keep_details=False)
    except KeyError:  # no hidden tests for this task
        return {**public, "scored_on": "public", "public": None, "false_pass": None}
    if hidden["error"]:  # keep only the error's name: its message can quote a hidden input
        hidden["error"] = hidden["error"].split(":")[0]
    keep = ("score", "test_pass_rate", "rubric_level", "level", "failure_type", "n_tests", "n_passed",
            "details", "error")
    return {**hidden, "scored_on": "hidden", "public": {k: public[k] for k in keep},
            "false_pass": public["score"] == 1.0 and hidden["score"] == 0.0}


# Send one item's prompt (at the given detail level) through the chosen provider's adapter and score the reply.
def run_one(provider_name: str, client, item: dict, level: str = "raw") -> dict:
    p = PROVIDERS[provider_name]
    prompt = build_prompt(item, level)
    start = time.time()
    try:
        text, tokens, model_used = p["call"](client, {**item, "prompt": prompt}, p["config"])
    except AdapterError as e:
        # The provider ran but gave no usable answer. Count it as a failed run (score 0 on both test sets),
        # not model output, and leave it out of the rubric levels.
        result = score_both(item, "", latency_s=round(time.time() - start, 2))
        result.update(score=0.0, test_pass_rate=0.0, rubric_level=None, level=None,
                      error=f"adapter_error: {e}", failed_run=True)
        text, model_used = "", None
    else:
        result = score_both(item, text, latency_s=round(time.time() - start, 2), output_tokens=tokens)
        result["failed_run"] = False
    result["task_type"] = item["task_type"]
    result["prompt_level"] = level
    result["prompt"] = prompt          # exactly what was sent, for comparing levels later
    result["output"] = text            # keep the raw response for manual review
    result["model_used"] = model_used  # which model actually answered (can vary for "opensource")
    return result


# Run every item one at a time (simplest, and keeps rate limits predictable).
# `save` is called after every item, so a crash or Ctrl-C keeps the finished ones.
def run_all(provider_name: str, client, items: list, level: str = "raw", save=None) -> list:
    results = []
    for i, it in enumerate(items, 1):
        r = run_one(provider_name, client, it, level)
        print(f"  [{level}] {i}/{len(items)} {r['id']}: score={r['score']}", file=sys.stderr)
        results.append(r)
        if save:
            save(results)
    return results


# Break the summary down by task type too, since code generation and bug fixing are compared separately.
# pass@1 is reported both with failed runs (counted as 0) and without them.
def summarize_run(results: list) -> dict:
    summary = summarize(results)
    for tt in sorted({r["task_type"] for r in results}):
        summary[tt] = summarize([r for r in results if r["task_type"] == tt])["overall"]
    summary["failed_runs"] = sum(1 for r in results if r.get("failed_run"))
    summary["excluding_failed_runs"] = summarize([r for r in results if not r.get("failed_run")])["overall"]
    # Public pass@1 beside the hidden headline, and answers that pass public tests but fail hidden ones.
    public = [(r.get("public") or r)["score"] for r in results]  # public-scored rows have no "public" block
    public = [s for s in public if s is not None]
    summary["public_pass@1"] = round(sum(public) / len(public), 3) if public else None
    summary["false_passes"] = sum(1 for r in results if r.get("false_pass"))
    summary["scored_on"] = dict(Counter(r.get("scored_on") for r in results))  # hidden, or public if no hidden tests
    return summary


# Write the run file through a temp file, so an interrupted write never leaves a half-written file.
def write_run(out_path: Path, run: dict):
    tmp = out_path.with_name(out_path.name + ".tmp")  # *_run.json.tmp, git-ignored
    with open(tmp, "w") as f:
        json.dump(run, f, indent=2)
    os.replace(tmp, out_path)


# Read a shared task list (one id per line, # comments allowed) from data/unified/task_lists/.
def read_task_list(name: str) -> list:
    path = Path(name)
    if not path.exists():
        path = TASK_LISTS_DIR / name
    if not path.exists():
        sys.exit(f"Task list {name} not found (looked in {TASK_LISTS_DIR}).")
    ids = [line.split("#")[0].strip() for line in path.read_text().splitlines()]
    return [i for i in ids if i]


# Keep exactly the tasks in `ids`, in the list's order. Stops if any id is missing or can't be scored yet,
# so every arm run from the same list gets the same tasks.
def select_ids(items: list, ids: list) -> list:
    by_id = {it["id"]: it for it in items}
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"{len(missing)} id(s) in the task list are not in the dataset or can't be scored yet: "
                 f"{', '.join(missing)}")
    return [by_id[i] for i in ids]


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
    ap.add_argument("--source", action="append", help="only this dataset, e.g. mbpp (repeat for several)")
    ap.add_argument("--ids", help="task list in data/unified/task_lists/ (e.g. smoke.txt); not combined with n or --source")
    args = ap.parse_args()
    if args.ids and (args.n is not None or args.source):
        ap.error("--ids picks the exact tasks, so it can't be combined with n or --source")

    provider_name = args.provider
    p = PROVIDERS[provider_name]
    # n = tasks per dataset (first n in file order, so runs are reproducible); not used with --ids
    n = None if args.ids else (args.n if args.n is not None else p["default_n"])
    levels = list(LEVELS) if args.level == "all" else [args.level]

    # Fail fast with a clear message instead of a raw error.
    api_key = None
    if p["api_key_env"]:
        api_key = os.environ.get(p["api_key_env"])
        if not api_key:
            sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")

    # The evaluator skips items it cannot score yet (and says so on stderr).
    # Bug fixing commented out: task_type=None if args.task == "all" else args.task
    items = load_items(task_type=args.task, sources=args.source, n_per_source=n)
    if args.ids:
        items = select_ids(items, read_task_list(args.ids))
    if not items:
        sys.exit("No items to run (check --task / --source).")

    client = p["client_factory"](api_key)
    print(f"{provider_name}: {len(items)} items x {len(levels)} level(s): {', '.join(levels)}", file=sys.stderr)

    for level in levels:
        # Save the output file at the repo root (not inside Baseline/), so it
        # sits next to .env / requirements.txt like before. Rewritten after every item.
        out_path = REPO_ROOT / output_name(p["output_file"], level)

        def save(results, level=level, out_path=out_path):
            write_run(out_path, {"scoring_version": SCORING_VERSION,
                                 "provider": provider_name, "prompt_level": level, "task": args.task,
                                 "n_per_dataset": n, "sources": args.source, "ids_file": args.ids,
                                 "config": p["config"], "summary": summarize_run(results),
                                 "results": results})

        results = run_all(provider_name, client, items, level, save=save)
        print(f"\n== {provider_name} / {level} -> {out_path.name}")
        print(json.dumps(summarize_run(results), indent=2))


if __name__ == "__main__":
    main()
