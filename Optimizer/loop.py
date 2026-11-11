"""
loop.py

Evaluator-Optimizer loop v1 (Milestone #2). For every task:

  attempt 0   the zero-shot answer (the dataset's own prompt), shared by every arm.
              If it passes its PUBLIC tests, or the API call failed, the task stops here.
  attempts 1-3, for each of the four arms separately, each starting from attempt 0:
      control      the attempt-0 prompt again (fresh resample, no old code, no feedback)
      bare_retry   the arm's previous code + "it failed, try again"
      reflect_fix  the arm's previous code + the first failing public test; explain, then fix
      critic       call 1: a reviewer diagnoses the code + failing test (no code)
                   call 2: the generator fixes the code using the diagnosis
  Every retry shows only that arm's LATEST attempt (retry_prompts.py).

Copy-forward rule (v1): once an arm's code passes its public tests, its later attempts copy that
attempt with no API call (carried_forward = true, 0 calls), so every arm has attempts 1-3.

Every attempt is scored on the hidden tests (the reported result; the model never sees them) and on
the public tests (the only feedback). Every API call, critic calls included, is logged through
AI_models/budget_tracker.py (runs/usage_log.csv), keyed by (task_id, arm, attempt), with the token
counts the API returns.

Attempt 0 is the official Claude zero-shot result (baseline.py claude is not used for experiment
numbers); Panacea's zero-shot run comes from baseline.py panacea, and Optimizer/report.py puts the two
side by side. summary.json splits attempt 0 into four cells (A true pass, B false pass, C hidden-only
pass, D true fail; see SUMMARY) and reports each arm both over all tasks and over C + D only.

Results go to data/results/<run>/ : run_meta.json, attempt_0.jsonl ... attempt_3.jsonl, summary.json.
A task's rows are written once the whole task is done, so a crash or budget stop never leaves half
a task. See Optimizer/LOOP.md for the row fields.

Usage (from the repo root):
    python Optimizer/loop.py mock --split dev                     # no API: checks the plumbing
    python Optimizer/loop.py claude --split dev                   # dev pilot: 10 pool tasks not in eval
    python Optimizer/loop.py claude --split dev --resume          # continue after a stop
    python Optimizer/loop.py claude --split test --ids <list>     # the test run, once prompts are frozen
    python Optimizer/loop.py --summarize data/results/<run>       # rebuild summary.json and report.md
"""

import argparse
import datetime
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from Evaluator.evaluator import (SCORING_VERSION, _PYTHON_TAGS, _fenced_blocks, evaluate, extract_code,
                                 format_feedback, load_items)
from AI_models.prompts import build_prompt
from AI_models.providers import PROVIDERS, AdapterError
from AI_models import retry_prompts as rp
from AI_models import budget_tracker as bt
from Baseline.baseline import read_task_list, select_ids
from Optimizer.report import ZERO_SHOT, read_rows, write_report

RESULTS_DIR = REPO_ROOT / "data" / "results"
RETRIES = 3
POOL_PATH = REPO_ROOT / "data" / "unified" / "unified_pool.jsonl"
FULL_PRIVATE_PATH = REPO_ROOT / "data" / "code_generation" / "code_generation_private_tests.jsonl"
DEV_SEED = 0
DEV_LAYOUT = {("mbpp", "medium", "assert_list"): 1, ("mbpp", "hard", "assert_list"): 2,
              ("livecodebench", "easy", "stdin_io"): 1, ("livecodebench", "easy", "functional_io"): 1,
              ("livecodebench", "medium", "stdin_io"): 1, ("livecodebench", "medium", "functional_io"): 1,
              ("livecodebench", "hard", "stdin_io"): 2, ("livecodebench", "hard", "functional_io"): 1}


def dev_items():
    """DEV_LAYOUT's stratified sample of pool tasks not in eval, with >= 5 distinct hidden tests attached."""
    if not FULL_PRIVATE_PATH.exists():
        sys.exit(f"{FULL_PRIVATE_PATH} not found. Run notebooks/code_generation_EDA_pipeline.ipynb to build it.")
    eval_ids = {it["id"] for it in load_items(task_type=None, scorable_only=False)}
    pool = {it["id"]: it for it in load_items(POOL_PATH) if it["id"] not in eval_ids}
    hidden = {}
    with open(FULL_PRIVATE_PATH) as f:
        for line in f:
            r = json.loads(line)
            if r["id"] in pool and len({json.dumps(t, sort_keys=True) for t in r["private_test_cases"]}) >= 5:
                hidden[r["id"]] = r["private_test_cases"]
    rng, picked = random.Random(DEV_SEED), []
    for (src, diff, fmt), n in DEV_LAYOUT.items():
        group = [it for i, it in pool.items() if i in hidden
                 and (it["source"], it["metadata"].get("difficulty"), it["test_format"]) == (src, diff, fmt)]
        picked += rng.sample(group, n)
    return [{**it, "private_tests": hidden[it["id"]]} for it in picked]


# =====================================================================
# MOCK PROVIDER (no API). Broken stub at attempt 0 for about half the tasks, then the reference
# on some retries, depending on arm and attempt, so stopping and copy-forward get exercised.
# Its pass rates mean nothing. LiveCodeBench has no references, so its mock answers always fail.
# =====================================================================
def call_mock(client, item, cfg):
    if item.get("_role") == "critic":
        return "- The function returns the wrong value.", 12, "mock", None
    h = int(hashlib.md5(f"{item['id']}|{item.get('_arm')}|{item.get('_attempt')}".encode()).hexdigest(), 16) % 10
    stub = f"```python\ndef {item.get('entry_point') or 'solve'}(*args, **kwargs):\n    return None\n```"
    if item.get("_attempt", 0) == 0:
        good = h >= 5
    else:
        good = h >= 6
    text = "```python\n" + item["reference"] + "\n```" if good and item.get("reference") else stub
    return text, 40, "mock", None  # no input count: the tracker estimates it (estimated=True)


MOCK = {"config": {"model": "mock", "max_tokens": None, "temperature": None},
        "api_key_env": None, "client_factory": lambda k: None, "call": call_mock}


# =====================================================================
# CALLS (every one goes through the budget tracker)
# =====================================================================
def ask(p, client, item, prompt, system, task_id, arm, attempt, call_type):
    """One API call. Returns (text, error, usage) where usage = {calls, output_tokens, input_tokens,
    tokens_estimated, latency_s}. Token counts come from the API; tokens_estimated counts the calls whose
    counts had to be estimated (a failed call, or the mock). An AdapterError is returned as an error, not
    raised; BudgetExceeded is raised."""
    cfg = {**p["config"], "system_prompt": system}
    bt.set_context(task_id=task_id, arm=arm, attempt=attempt, call_type=call_type)
    bt.check_budget()  # raises BudgetExceeded at the stop limit
    start = time.time()
    try:
        res = p["call"](client, {**item, "prompt": prompt, "_arm": arm, "_attempt": attempt, "_role": call_type}, cfg)
        text, out_tokens, model_used, in_tokens = res[:4]
        stop_reason = res[4] if len(res) > 4 else None
        error = None
    except AdapterError as e:  # the SDK already retried temporary errors; no answer, but money may be spent
        text, out_tokens, in_tokens, model_used, error = "", None, None, cfg["model"], f"adapter_error: {e}"
        stop_reason = None
    latency = round(time.time() - start, 2)
    row = bt.record_call(model_used or cfg["model"], input_tokens=in_tokens, output_tokens=out_tokens,
                         prompt_text=system + "\n" + prompt, output_text=text, latency_s=latency)
    bt.clear_context()
    return text, error, {"calls": 1, "output_tokens": row["output_tokens"], "input_tokens": row["input_tokens"],
                         "tokens_estimated": int(row["estimated"]), "cost_usd": row["cost_usd"],
                         "latency_s": latency, "stop_reason": stop_reason}


USAGE_KEYS = ("calls", "output_tokens", "input_tokens", "tokens_estimated", "cost_usd", "latency_s")


def _add_usage(a, b):
    return {k: round(a.get(k, 0) + b.get(k, 0), 6) for k in USAGE_KEYS}


# =====================================================================
# SCORING
# =====================================================================
def score(item, text):
    """Public result with full details (the only thing feedback is built from) and a hidden result with
    counts only. The hidden error keeps only its exception name: its message can quote a hidden input."""
    public = evaluate(item, text, split="public")
    hidden = evaluate(item, text, split="private", keep_details=False)
    if hidden["error"]:
        hidden["error"] = hidden["error"].split(":")[0]
    return public, hidden


def make_row(item, arm, attempt, prompt, output, public, hidden, usage, critique=None, error=None,
             prev_row=None):
    failed = error is not None
    hid_score = 0.0 if failed else hidden["score"]
    hid_rate = 0.0 if failed else hidden["test_pass_rate"]
    pub_score = 0.0 if failed else public["score"]
    return {
        "task_id": item["id"], "source": item["source"], "difficulty": item["metadata"].get("difficulty"),
        "test_format": item["test_format"], "arm": arm, "attempt": attempt,
        "hidden_score": hid_score, "hidden_test_pass_rate": round(hid_rate, 3),
        "hidden_tests": f"{hidden['n_passed']}/{hidden['n_tests']}",
        "public_score": pub_score, "public_test_pass_rate": round(0.0 if failed else public["test_pass_rate"], 3),
        "public_tests": f"{public['n_passed']}/{public['n_tests']}",
        "false_pass": (not failed) and pub_score == 1.0 and hid_score == 0.0,
        "rubric_level": None if failed else hidden["rubric_level"],
        "level": None if failed else hidden["level"],
        "failure_type": None if failed else hidden["failure_type"],
        # hidden test pass rate went down from this arm's previous attempt (null at attempt 0, and null on
        # a failed run: an API error is not the model making the code worse)
        "regression": None if prev_row is None or failed else hid_rate < prev_row["hidden_test_pass_rate"],
        "carried_forward": False,
        "n_python_blocks": sum(tag in _PYTHON_TAGS for tag, _, _ in _fenced_blocks(output or "")),
        "critique_has_code": None if critique is None else ("```" in critique or "def " in critique),
        "failed_run": failed, "error": error or (hidden["error"] if hidden["error"] else None),
        **usage,
        "prompt": prompt, "critique": critique, "output": output,
    }


def carry_forward(prev_row, attempt):
    return {**prev_row, "attempt": attempt, "regression": False, "carried_forward": True,
            **{k: 0 for k in USAGE_KEYS}, "prompt": None, "critique": None}


# =====================================================================
# ONE TASK
# =====================================================================
def run_task(p, client, item, arms, retries):
    """Returns {attempt: [rows]} for one task."""
    tid = item["id"]
    prompt0 = build_prompt(item, "raw")
    text0, err0, use0 = ask(p, client, item, prompt0, rp.GENERATOR_SYSTEM, tid, ZERO_SHOT, 0, "generator")
    pub0, hid0 = score(item, text0)
    row0 = make_row(item, ZERO_SHOT, 0, prompt0, text0, pub0, hid0, use0, error=err0)
    out = {0: [row0]}
    status = f"public={row0['public_score']} hidden={row0['hidden_score']}"
    print(f"{tid}: attempt 0 {status}" + (" (failed run)" if err0 else ""), file=sys.stderr)
    if err0 or row0["public_score"] == 1.0:
        return out  # failed run, or passed its public tests: no arms

    for arm in arms:
        prev_row, prev_public = row0, pub0
        for k in range(1, retries + 1):
            if prev_row["public_score"] == 1.0:  # copy-forward rule
                out.setdefault(k, []).append(carry_forward(prev_row, k))
                continue
            prev_code = extract_code(prev_row["output"], item.get("entry_point"))
            usage, critique, error = {}, None, None
            if arm == "control":
                prompt = prompt0
            elif arm == "bare_retry":
                prompt = rp.bare_retry(item["prompt"], prev_code)
            elif arm == "reflect_fix":
                prompt = rp.reflect_fix(item["prompt"], prev_code, format_feedback(prev_public))
            elif arm == "critic":
                fb = format_feedback(prev_public)
                critique, error, usage = ask(p, client, item, rp.critic_review(item["prompt"], prev_code, fb),
                                             rp.CRITIC_SYSTEM, tid, arm, k, "critic")
                prompt = rp.critic_fix(item["prompt"], prev_code, fb, critique)
            else:
                raise ValueError(arm)
            if error is None:
                text, error, u = ask(p, client, item, prompt, rp.GENERATOR_SYSTEM, tid, arm, k, "generator")
                usage = {**_add_usage(usage, u), "stop_reason": u["stop_reason"]}
            else:
                text = ""
            public, hidden = score(item, text)
            row = make_row(item, arm, k, prompt, text, public, hidden, usage, critique, error, prev_row)
            out.setdefault(k, []).append(row)
            print(f"    {arm:<11} attempt {k} public={row['public_score']} hidden={row['hidden_score']} "
                  f"({row['hidden_tests']})" + (" (failed run)" if error else ""), file=sys.stderr)
            if not error:  # a failed run keeps the last good attempt as the one to build on
                prev_row, prev_public = row, public
            # after a failed run, the row in the file is the failed one, but the next prompt builds on prev_row
    return out


# =====================================================================
# FILES
# =====================================================================
def append_task(run_dir: Path, rows_by_attempt: dict):
    for k, rows in sorted(rows_by_attempt.items()):
        with open(run_dir / f"attempt_{k}.jsonl", "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


def git_commit():
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Evaluator-Optimizer loop v1.")
    # Claude only (the experiment model) plus the no-API mock; opensource was dropped from the loop (2026-11-03).
    ap.add_argument("provider", nargs="?", choices=["claude", "mock"])
    ap.add_argument("--split", choices=["dev", "test"],
                    help="dev: 10 stratified pool tasks not in eval (seed 0); test: the eval tasks in --ids")
    ap.add_argument("--ids", help="task list in data/unified/task_lists/ (e.g. pilot.txt)")
    ap.add_argument("--arms", nargs="+", choices=list(rp.ARMS), default=list(rp.ARMS))
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--name", help="run folder name (default <date>_<provider>_<ids>)")
    ap.add_argument("--out", default=str(RESULTS_DIR), help="folder that holds the run folders (default data/results)")
    ap.add_argument("--resume", action="store_true", help="continue a run, skipping tasks already in attempt_0.jsonl")
    ap.add_argument("--summarize", metavar="RUN_DIR", help="only rebuild summary.json for an existing run")
    args = ap.parse_args()

    if args.summarize:
        write_report(Path(args.summarize))
        return
    if not args.provider or not args.split:
        ap.error("provider and --split are required")
    if (args.split == "test") != bool(args.ids):
        ap.error("--split test needs --ids; --split dev picks its own tasks")

    p = MOCK if args.provider == "mock" else PROVIDERS[args.provider]
    model = p["config"]["model"]
    stem = args.split + (f"_{Path(args.ids).stem}" if args.ids else "")
    name = args.name or f"{datetime.date.today().isoformat()}_{args.provider}_{stem}"
    run_dir = Path(args.out).resolve() / name

    if args.provider == "mock":  # keep mock rows out of the team's real budget log
        bt.LOG_PATH = run_dir / "usage_log.csv"
        bt.PRICES_PER_MTOK.setdefault("mock", (0.0, 0.0))

    key = os.environ.get(p["api_key_env"]) if p["api_key_env"] else None
    if p["api_key_env"] and not key:
        sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")

    if args.provider != "mock" and args.split == "test" and rp.fingerprint() != rp.FROZEN_FINGERPRINT:
        sys.exit("AI_models/retry_prompts.py changed since the prompts were frozen "
                 f"({rp.FROZEN_DATE}). Changing them is a team decision: see that file's docstring.")
    items = dev_items() if args.split == "dev" else select_ids(load_items(), read_task_list(args.ids))
    meta = {"scoring_version": SCORING_VERSION, "split": args.split, "provider": args.provider, "model": model,
            "max_tokens": p["config"].get("max_tokens"), "temperature": p["config"].get("temperature"),
            "ids_file": args.ids, "task_ids": [it["id"] for it in items], "arms": args.arms,
            "retries": args.retries, "rule": "copy-forward after a public pass",
            "retry_prompts_fingerprint": rp.fingerprint(),
            "git_commit": git_commit(), "usage_log": str(bt.LOG_PATH),
            "started": datetime.datetime.now().isoformat(timespec="seconds"), "finished": None}

    meta_path = run_dir / "run_meta.json"
    done = set()
    if run_dir.exists() and any(run_dir.glob("attempt_*.jsonl")):
        if not args.resume:
            sys.exit(f"{run_dir} already has results. Use --resume to continue it, or --name for a new run.")
        old = json.loads(meta_path.read_text())
        for k in ("scoring_version", "split", "provider", "model", "max_tokens", "temperature", "task_ids", "arms", "retries",
                  "retry_prompts_fingerprint"):
            if old.get(k) != meta[k]:
                sys.exit(f"Can't resume {run_dir}: {k} differs ({old.get(k)!r} vs {meta[k]!r}).")
        meta = {**old, "finished": None}
        done = {r["task_id"] for r in read_rows(run_dir, 0)}
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2))

    client = p["client_factory"](key)
    todo = [it for it in items if it["id"] not in done]
    print(f"{args.provider} ({model}): {len(todo)} of {len(items)} tasks to run, arms {', '.join(args.arms)}, "
          f"-> {run_dir}", file=sys.stderr)
    stopped = None
    try:
        for it in todo:
            append_task(run_dir, run_task(p, client, it, args.arms, args.retries))
    except bt.BudgetExceeded as e:
        stopped = str(e)
        print(f"\nStopped: {e}\nThe unfinished task was not written; rerun with --resume after checking.",
              file=sys.stderr)
    else:
        meta["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        meta_path.write_text(json.dumps(meta, indent=2))

    write_report(run_dir)
    print(f"\nResults: {run_dir}/  (usage log: {bt.LOG_PATH})")
    if stopped:
        sys.exit(1)


if __name__ == "__main__":
    main()
