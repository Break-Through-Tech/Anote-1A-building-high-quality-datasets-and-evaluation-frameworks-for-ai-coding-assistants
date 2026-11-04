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
AI_models/budget_tracker.py (runs/usage_log.csv), keyed by (task_id, arm, attempt). Output tokens
come from the API; input tokens are the tracker's estimate (about 4 characters per token).

Results go to data/results/<run>/ : run_meta.json, attempt_0.jsonl ... attempt_3.jsonl, summary.json.
A task's rows are written once the whole task is done, so a crash or budget stop never leaves half
a task. See Optimizer/LOOP.md for the row fields.

Usage (from the repo root):
    python Optimizer/loop.py mock --ids smoke.txt          # no API: checks the plumbing, numbers mean nothing
    python Optimizer/loop.py claude --ids pilot.txt        # the pilot
    python Optimizer/loop.py claude --ids pilot.txt --resume   # continue after a stop
    python Optimizer/loop.py claude --ids pilot.txt --arms control reflect_fix
    python Optimizer/loop.py --summarize data/results/<run>    # rebuild summary.json only
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from Evaluator.evaluator import SCORING_VERSION, evaluate, extract_code, format_feedback, load_items
from AI_models.prompts import build_prompt
from AI_models.providers import PROVIDERS, AdapterError
from AI_models import retry_prompts as rp
from AI_models import budget_tracker as bt
from Baseline.baseline import read_task_list, select_ids

RESULTS_DIR = REPO_ROOT / "data" / "results"
RETRIES = 3
ZERO_SHOT = "zero_shot"


# =====================================================================
# MOCK PROVIDER (no API). Broken stub at attempt 0 for about half the tasks, then the reference
# on some retries, depending on arm and attempt, so stopping and copy-forward get exercised.
# Its pass rates mean nothing. LiveCodeBench has no references, so its mock answers always fail.
# =====================================================================
def call_mock(client, item, cfg):
    if item.get("_role") == "critic":
        return "- The function returns the wrong value.", 12, "mock"
    h = int(hashlib.md5(f"{item['id']}|{item.get('_arm')}|{item.get('_attempt')}".encode()).hexdigest(), 16) % 10
    stub = f"```python\ndef {item.get('entry_point') or 'solve'}(*args, **kwargs):\n    return None\n```"
    if item.get("_attempt", 0) == 0:
        good = h >= 5
    else:
        good = h >= 6
    return ("```python\n" + item["reference"] + "\n```" if good and item.get("reference") else stub), 40, "mock"


MOCK = {"config": {"model": "mock", "max_tokens": None, "temperature": None},
        "api_key_env": None, "client_factory": lambda k: None, "call": call_mock}


# =====================================================================
# CALLS (every one goes through the budget tracker)
# =====================================================================
def ask(p, client, item, prompt, system, task_id, arm, attempt, call_type):
    """One API call. Returns (text, error, usage) where usage = {calls, output_tokens, input_tokens_est,
    latency_s}. An AdapterError is returned as an error, not raised; BudgetExceeded is raised."""
    cfg = {**p["config"], "system_prompt": system}
    bt.set_context(task_id=task_id, arm=arm, attempt=attempt, call_type=call_type)
    bt.check_budget()  # raises BudgetExceeded at the stop limit
    start = time.time()
    try:
        text, out_tokens, model_used = p["call"](
            client, {**item, "prompt": prompt, "_arm": arm, "_attempt": attempt, "_role": call_type}, cfg)
        error = None
    except AdapterError as e:  # the SDK already retried temporary errors; no answer, but money may be spent
        text, out_tokens, model_used, error = "", None, cfg["model"], f"adapter_error: {e}"
    latency = round(time.time() - start, 2)
    row = bt.record_call(model_used or cfg["model"], output_tokens=out_tokens,
                         prompt_text=system + "\n" + prompt, output_text=text, latency_s=latency)
    bt.clear_context()
    return text, error, {"calls": 1, "output_tokens": row["output_tokens"],
                         "input_tokens_est": row["input_tokens"], "latency_s": latency}


def _add_usage(a, b):
    return {k: round(a.get(k, 0) + b.get(k, 0), 2) for k in ("calls", "output_tokens", "input_tokens_est", "latency_s")}


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
        # hidden test pass rate went down from this arm's previous attempt (null at attempt 0)
        "regression": None if prev_row is None else hid_rate < prev_row["hidden_test_pass_rate"],
        "carried_forward": False,
        "failed_run": failed, "error": error or (hidden["error"] if hidden["error"] else None),
        **usage,
        "prompt": prompt, "critique": critique, "output": output,
    }


def carry_forward(prev_row, attempt):
    return {**prev_row, "attempt": attempt, "regression": False, "carried_forward": True,
            "calls": 0, "output_tokens": 0, "input_tokens_est": 0, "latency_s": 0.0,
            "prompt": None, "critique": None}


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
                usage = _add_usage(usage, u)
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
def read_rows(run_dir: Path, attempt: int) -> list:
    path = run_dir / f"attempt_{attempt}.jsonl"
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def append_task(run_dir: Path, rows_by_attempt: dict):
    for k, rows in sorted(rows_by_attempt.items()):
        with open(run_dir / f"attempt_{k}.jsonl", "a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


def git_commit():
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


# =====================================================================
# SUMMARY (minimal; the charts are the "Results views" task)
# =====================================================================
def _price(model):
    return bt.PRICES_PER_MTOK.get(model, bt.FALLBACK_PRICE_PER_MTOK)


def summarize_run(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "run_meta.json").read_text())
    retries = meta["retries"]
    a0 = read_rows(run_dir, 0)
    by_key = {(r["task_id"], r["arm"], r["attempt"]): r for k in range(1, retries + 1) for r in read_rows(run_dir, k)}
    arms = meta["arms"]
    price_in, price_out = _price(meta["model"])

    ok0 = [r for r in a0 if not r["failed_run"]]
    failed = [r for r in ok0 if r["public_score"] != 1.0]  # the paired set that goes into the arms
    # keep only tasks with every arm complete (a resumed run always has them, but be safe)
    failed = [r for r in failed if all((r["task_id"], a, retries) in by_key for a in arms)]
    ids = [r["task_id"] for r in failed]

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    def chain(tid, arm):
        return [next(r for r in a0 if r["task_id"] == tid)] + [by_key[(tid, arm, k)] for k in range(1, retries + 1)]

    def arm_stats(task_ids, arm):
        chains = [chain(t, arm) for t in task_ids]
        rows = [r for c in chains for r in c[1:]]
        fixes = sum(c[0]["hidden_score"] == 0.0 and c[-1]["hidden_score"] == 1.0 for c in chains)
        calls = sum(r["calls"] for r in rows)
        out_tok = sum(r["output_tokens"] for r in rows)
        in_tok = sum(r["input_tokens_est"] for r in rows)
        cost = (in_tok * price_in + out_tok * price_out) / 1_000_000
        return {
            "n": len(chains),
            "hidden_pass@1_by_attempt": [mean([c[k]["hidden_score"] for c in chains]) for k in range(retries + 1)],
            "public_pass@1_by_attempt": [mean([c[k]["public_score"] for c in chains]) for k in range(retries + 1)],
            "repairs": fixes,
            "repair_rate": round(fixes / len(chains), 3) if chains else None,
            "false_fixes": sum(c[-1]["false_pass"] for c in chains),
            "regressions": sum(bool(r["regression"]) for r in rows),
            "failed_runs": sum(r["failed_run"] for r in rows),
            "calls": calls, "output_tokens": out_tok, "input_tokens_est": in_tok,
            "est_cost_usd": round(cost, 4),
            "est_cost_per_repair_usd": round(cost / fixes, 4) if fixes else None,
            "calls_per_repair": round(calls / fixes, 2) if fixes else None,
        }

    per_arm = {a: arm_stats(ids, a) for a in arms}
    if "control" in per_arm:
        ctrl = per_arm["control"]["hidden_pass@1_by_attempt"]
        for a in arms:
            mine = per_arm[a]["hidden_pass@1_by_attempt"]
            per_arm[a]["gain_over_control_by_attempt"] = [
                None if m is None or c is None else round(m - c, 3) for m, c in zip(mine, ctrl)]

    def group_table(key):
        groups = defaultdict(list)
        for r in failed:
            groups[key(r)].append(r["task_id"])
        return {g: {"n": len(t), **{a: arm_stats(t, a)["hidden_pass@1_by_attempt"] for a in arms}}
                for g, t in sorted(groups.items())}

    summary = {
        "scoring_version": meta["scoring_version"], "model": meta["model"], "n_tasks": len(a0),
        "attempt_0": {
            "failed_runs": len(a0) - len(ok0),
            "hidden_pass@1": mean([r["hidden_score"] for r in ok0]),
            "public_pass@1": mean([r["public_score"] for r in ok0]),
            "false_passes": sum(r["false_pass"] for r in ok0),
            "failed_public": len(failed),
        },
        "paired_task_ids": ids,
        "arms": per_arm,
        # MBPP and LiveCodeBench difficulty are different scales: always grouped by source too
        "by_source_difficulty": group_table(lambda r: f"{r['source']}/{r['difficulty']}"),
        "by_attempt0_failure_type": group_table(lambda r: r["failure_type"] or "none"),
        "notes": "Arm stats are on the tasks that failed attempt 0's public tests. Input tokens and costs are "
                 "estimates (budget_tracker). regression = hidden test pass rate went down from the arm's "
                 "previous attempt.",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def print_summary(s: dict):
    a = s["attempt_0"]
    print(f"\n{s['n_tasks']} tasks. Attempt 0: hidden pass@1 {a['hidden_pass@1']}, public {a['public_pass@1']}, "
          f"{a['false_passes']} false passes, {a['failed_runs']} failed runs, "
          f"{a['failed_public']} failed public tests and went into the arms.")
    if not s["paired_task_ids"]:
        return
    print("\nHidden pass@1 on those tasks, attempts 0-3:")
    print("| arm | a0 | a1 | a2 | a3 | gain vs control (a3) | repairs | false fixes | regressions | calls | est $ |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, st in s["arms"].items():
        h = st["hidden_pass@1_by_attempt"]
        g = (st.get("gain_over_control_by_attempt") or [None])[-1]
        print(f"| {arm} | " + " | ".join(str(x) for x in h) + f" | {g} | {st['repairs']}/{st['n']} | "
              f"{st['false_fixes']} | {st['regressions']} | {st['calls']} | {st['est_cost_usd']} |")


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Evaluator-Optimizer loop v1.")
    ap.add_argument("provider", nargs="?", choices=["claude", "opensource", "mock"])
    ap.add_argument("--ids", help="task list in data/unified/task_lists/ (e.g. pilot.txt)")
    ap.add_argument("--arms", nargs="+", choices=list(rp.ARMS), default=list(rp.ARMS))
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--name", help="run folder name (default <date>_<provider>_<ids>)")
    ap.add_argument("--out", default=str(RESULTS_DIR), help="folder that holds the run folders (default data/results)")
    ap.add_argument("--resume", action="store_true", help="continue a run, skipping tasks already in attempt_0.jsonl")
    ap.add_argument("--summarize", metavar="RUN_DIR", help="only rebuild summary.json for an existing run")
    args = ap.parse_args()

    if args.summarize:
        print_summary(summarize_run(Path(args.summarize)))
        return
    if not args.provider or not args.ids:
        ap.error("provider and --ids are required (every arm and run must use a fixed task list)")

    p = MOCK if args.provider == "mock" else PROVIDERS[args.provider]
    model = p["config"]["model"]
    stem = Path(args.ids).stem
    name = args.name or f"{datetime.date.today().isoformat()}_{args.provider}_{stem}"
    run_dir = Path(args.out).resolve() / name

    if args.provider == "mock":  # keep mock rows out of the team's real budget log
        bt.LOG_PATH = run_dir / "usage_log.csv"
        bt.PRICES_PER_MTOK.setdefault("mock", (0.0, 0.0))

    key = os.environ.get(p["api_key_env"]) if p["api_key_env"] else None
    if p["api_key_env"] and not key:
        sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")

    items = select_ids(load_items(), read_task_list(args.ids))
    meta = {"scoring_version": SCORING_VERSION, "provider": args.provider, "model": model,
            "max_tokens": p["config"].get("max_tokens"), "temperature": p["config"].get("temperature"),
            "ids_file": args.ids, "task_ids": [it["id"] for it in items], "arms": args.arms,
            "retries": args.retries, "rule": "copy-forward after a public pass",
            "git_commit": git_commit(), "usage_log": str(bt.LOG_PATH),
            "started": datetime.datetime.now().isoformat(timespec="seconds"), "finished": None}

    meta_path = run_dir / "run_meta.json"
    done = set()
    if run_dir.exists() and any(run_dir.glob("attempt_*.jsonl")):
        if not args.resume:
            sys.exit(f"{run_dir} already has results. Use --resume to continue it, or --name for a new run.")
        old = json.loads(meta_path.read_text())
        for k in ("scoring_version", "provider", "model", "max_tokens", "temperature", "task_ids", "arms", "retries"):
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

    print_summary(summarize_run(run_dir))
    print(f"\nResults: {run_dir}/  (usage log: {bt.LOG_PATH})")
    if stopped:
        sys.exit(1)


if __name__ == "__main__":
    main()
