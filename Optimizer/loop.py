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
from collections import defaultdict
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
        text, out_tokens, model_used, in_tokens = p["call"](
            client, {**item, "prompt": prompt, "_arm": arm, "_attempt": attempt, "_role": call_type}, cfg)
        error = None
    except AdapterError as e:  # the SDK already retried temporary errors; no answer, but money may be spent
        text, out_tokens, in_tokens, model_used, error = "", None, None, cfg["model"], f"adapter_error: {e}"
    latency = round(time.time() - start, 2)
    row = bt.record_call(model_used or cfg["model"], input_tokens=in_tokens, output_tokens=out_tokens,
                         prompt_text=system + "\n" + prompt, output_text=text, latency_s=latency)
    bt.clear_context()
    return text, error, {"calls": 1, "output_tokens": row["output_tokens"], "input_tokens": row["input_tokens"],
                         "tokens_estimated": int(row["estimated"]), "cost_usd": row["cost_usd"],
                         "latency_s": latency}


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
# SUMMARY (the charts are the "Results views" task; Optimizer/report.py adds Panacea beside it)
#
# Attempt 0 puts every task (that didn't fail its API call) in one of four cells:
#   A true_pass         public pass, hidden pass   -> done; same result in every arm
#   B false_pass        public pass, hidden fail   -> done; looks right but isn't, and no arm can see it
#   C hidden_only_pass  public fail, hidden pass   -> goes into the arms; can only stay or break
#   D true_fail         public fail, hidden fail   -> goes into the arms; the real repair targets
# Two views of each arm:
#   all_tasks   hidden pass@1 over every task at attempts 0-3 (A and B keep their attempt-0 result).
#               This is the number that goes beside zero-shot and Panacea.
#   paired      only the tasks that went into the arms (C + D): the self-correction view.
#               repairs / repair_rate are over D, breaks over C.
# =====================================================================
CELLS = {(True, True): "A_true_pass", (True, False): "B_false_pass",
         (False, True): "C_hidden_only_pass", (False, False): "D_true_fail"}


def cell_of(row):
    return CELLS[(row["public_score"] == 1.0, row["hidden_score"] == 1.0)]


def _mean(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


def _usage(rows):
    return {"calls": sum(r["calls"] for r in rows), "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "tokens_estimated": sum(r["tokens_estimated"] for r in rows),
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4)}


def summarize_run(run_dir: Path) -> dict:
    meta = json.loads((run_dir / "run_meta.json").read_text())
    retries, arms = meta["retries"], meta["arms"]
    a0 = read_rows(run_dir, 0)
    a0_by_id = {r["task_id"]: r for r in a0}
    by_key = {(r["task_id"], r["arm"], r["attempt"]): r for k in range(1, retries + 1) for r in read_rows(run_dir, k)}

    ok0 = [r for r in a0 if not r["failed_run"]]
    failed0 = [r["task_id"] for r in a0 if r["failed_run"]]
    entered = [r for r in ok0 if r["public_score"] != 1.0]  # C + D: the tasks that went into the arms
    # keep only tasks with every arm complete (rows are written per finished task, but be safe)
    incomplete = [r["task_id"] for r in entered if not all((r["task_id"], a, retries) in by_key for a in arms)]
    paired = [r["task_id"] for r in entered if r["task_id"] not in incomplete]
    scored = [r["task_id"] for r in ok0 if r["task_id"] not in incomplete]  # A + B + paired

    cells = defaultdict(list)
    for r in ok0:
        cells[cell_of(r)].append(r["task_id"])

    def row_at(tid, arm, k):
        """The task's row in this arm at attempt k: attempt 0 for A/B tasks and at k = 0."""
        r0 = a0_by_id[tid]
        return r0 if k == 0 or r0["public_score"] == 1.0 else by_key[(tid, arm, k)]

    def chain(tid, arm):
        return [row_at(tid, arm, k) for k in range(retries + 1)]

    def paired_stats(task_ids, arm):
        chains = [chain(t, arm) for t in task_ids]
        rows = [r for c in chains for r in c[1:]]
        targets = [c for c in chains if c[0]["hidden_score"] == 0.0]  # D
        keepers = [c for c in chains if c[0]["hidden_score"] == 1.0]  # C
        repairs = sum(c[-1]["hidden_score"] == 1.0 for c in targets)
        use = _usage(rows)
        return {
            "n": len(chains), "n_D_repair_targets": len(targets), "n_C_hidden_only_pass": len(keepers),
            "hidden_pass@1_by_attempt": [_mean([c[k]["hidden_score"] for c in chains]) for k in range(retries + 1)],
            "public_pass@1_by_attempt": [_mean([c[k]["public_score"] for c in chains]) for k in range(retries + 1)],
            "repairs": repairs,
            "repair_rate": round(repairs / len(targets), 3) if targets else None,
            "breaks": sum(c[-1]["hidden_score"] == 0.0 for c in keepers),
            "false_fixes": sum(c[-1]["false_pass"] for c in chains),
            "regressions": sum(bool(r["regression"]) for r in rows),
            "failed_runs": sum(r["failed_run"] for r in rows),
            **use,
            "cost_per_repair_usd": round(use["cost_usd"] / repairs, 4) if repairs else None,
            "calls_per_repair": round(use["calls"] / repairs, 2) if repairs else None,
        }

    def all_tasks_stats(task_ids, arm):
        """Every task, attempts 0-3. failed attempt-0 runs are left out here and counted 0 in *_incl_failed."""
        n_incl = len(task_ids) + len(failed0)
        by_k = [[row_at(t, arm, k) for t in task_ids] for k in range(retries + 1)]
        hidden = [sum(r["hidden_score"] for r in rows) for rows in by_k]
        return {
            "n": len(task_ids),
            "hidden_pass@1_by_attempt": [_mean([r["hidden_score"] for r in rows]) for rows in by_k],
            "hidden_pass@1_incl_failed_by_attempt": [round(h / n_incl, 3) if n_incl else None for h in hidden],
            "public_pass@1_by_attempt": [_mean([r["public_score"] for r in rows]) for rows in by_k],
            "false_passes_by_attempt": [sum(r["false_pass"] for r in rows) for rows in by_k],
            # what the whole pipeline cost: attempt 0 on every task + this arm's retries
            "cost_usd": round(zero_shot_use["cost_usd"] + per_arm[arm]["cost_usd"], 4),
            "calls": zero_shot_use["calls"] + per_arm[arm]["calls"],
        }

    zero_shot_use = _usage(a0)
    per_arm = {a: paired_stats(paired, a) for a in arms}
    if "control" in per_arm:
        ctrl = per_arm["control"]["hidden_pass@1_by_attempt"]
        for a in arms:
            mine = per_arm[a]["hidden_pass@1_by_attempt"]
            per_arm[a]["gain_over_control_by_attempt"] = [
                None if m is None or c is None else round(m - c, 3) for m, c in zip(mine, ctrl)]
    all_tasks = {a: all_tasks_stats(scored, a) for a in arms}

    def groups(ids, key):
        out = defaultdict(list)
        for t in ids:
            out[key(a0_by_id[t])].append(t)
        return dict(sorted(out.items()))

    # MBPP and LiveCodeBench difficulty are different scales: always grouped by source too
    src_diff = lambda r: f"{r['source']}/{r['difficulty']}"
    summary = {
        "scoring_version": meta["scoring_version"], "model": meta["model"], "n_tasks": len(a0),
        "attempt_0": {
            "failed_runs": len(failed0),
            "hidden_pass@1": _mean([r["hidden_score"] for r in ok0]),
            "hidden_pass@1_incl_failed": _mean([r["hidden_score"] for r in a0]),
            "public_pass@1": _mean([r["public_score"] for r in ok0]),
            "false_passes": len(cells["B_false_pass"]),
            "went_into_arms": len(entered),
            "cells": {c: len(cells[c]) for c in CELLS.values()},
            "cell_ids": {c: cells[c] for c in CELLS.values()},
            **zero_shot_use,
        },
        "all_tasks": all_tasks,
        "paired_task_ids": paired,
        "incomplete_task_ids": incomplete,
        "arms": per_arm,
        "all_tasks_by_source_difficulty": {
            g: {"n": len(t), "cells": {c: sum(cell_of(a0_by_id[x]) == c for x in t) for c in CELLS.values()},
                "zero_shot": _mean([a0_by_id[x]["hidden_score"] for x in t]),
                **{a: _mean([row_at(x, a, retries)["hidden_score"] for x in t]) for a in arms}}
            for g, t in groups(scored, src_diff).items()},
        "by_source_difficulty": {g: {"n": len(t), **{a: paired_stats(t, a)["hidden_pass@1_by_attempt"] for a in arms}}
                                 for g, t in groups(paired, src_diff).items()},
        "by_attempt0_failure_type": {g: {"n": len(t), **{a: paired_stats(t, a)["hidden_pass@1_by_attempt"] for a in arms}}
                                     for g, t in groups(paired, lambda r: r["failure_type"] or "none").items()},
        "notes": "attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass "
                 "(public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping "
                 "their attempt-0 result; *_incl_failed counts failed attempt-0 API calls as 0. arms: only the "
                 "tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden "
                 "test pass rate went down from the arm's previous attempt. Costs are from the API's token counts "
                 "(tokens_estimated = calls whose counts were estimated).",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def print_summary(s: dict):
    a = s["attempt_0"]
    c = a["cells"]
    print(f"\n{s['n_tasks']} tasks, {a['failed_runs']} failed attempt-0 runs. Attempt 0: hidden pass@1 "
          f"{a['hidden_pass@1']}, public {a['public_pass@1']}.")
    print(f"  A true pass {c['A_true_pass']} | B false pass {c['B_false_pass']} | "
          f"C hidden-only pass {c['C_hidden_only_pass']} | D true fail {c['D_true_fail']} "
          f"-> {a['went_into_arms']} went into the arms")
    if not s["all_tasks"]:
        return
    print("\nAll tasks, hidden pass@1 at attempts 0-3 (A and B keep attempt 0):")
    print("| arm | a0 | a1 | a2 | a3 | false passes (a3) | calls | $ |")
    print("|---|---|---|---|---|---|---|---|")
    for arm, st in s["all_tasks"].items():
        print(f"| {arm} | " + " | ".join(str(x) for x in st["hidden_pass@1_by_attempt"])
              + f" | {st['false_passes_by_attempt'][-1]} | {st['calls']} | {st['cost_usd']} |")
    if not s["paired_task_ids"]:
        return
    print(f"\nOnly the {len(s['paired_task_ids'])} tasks that went into the arms (C + D):")
    print("| arm | a0 | a1 | a2 | a3 | gain vs control (a3) | repairs (of D) | breaks (of C) | false fixes "
          "| regressions | calls | $ |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, st in s["arms"].items():
        h = st["hidden_pass@1_by_attempt"]
        g = (st.get("gain_over_control_by_attempt") or [None])[-1]
        print(f"| {arm} | " + " | ".join(str(x) for x in h) + f" | {g} | {st['repairs']}/{st['n_D_repair_targets']} | "
              f"{st['breaks']}/{st['n_C_hidden_only_pass']} | {st['false_fixes']} | {st['regressions']} | "
              f"{st['calls']} | {st['cost_usd']} |")


# =====================================================================
# ENTRY POINT
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Evaluator-Optimizer loop v1.")
    # Claude only (the experiment model) plus the no-API mock; opensource was dropped from the loop (2026-11-03).
    ap.add_argument("provider", nargs="?", choices=["claude", "mock"])
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

    if args.provider != "mock" and rp.fingerprint() != rp.FROZEN_FINGERPRINT:
        sys.exit("AI_models/retry_prompts.py changed since the prompts were frozen "
                 f"({rp.FROZEN_DATE}). Changing them is a team decision: see that file's docstring.")
    items = select_ids(load_items(), read_task_list(args.ids))
    meta = {"scoring_version": SCORING_VERSION, "provider": args.provider, "model": model,
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
        for k in ("scoring_version", "provider", "model", "max_tokens", "temperature", "task_ids", "arms", "retries",
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

    print_summary(summarize_run(run_dir))
    print(f"\nResults: {run_dir}/  (usage log: {bt.LOG_PATH})")
    if stopped:
        sys.exit(1)


if __name__ == "__main__":
    main()
