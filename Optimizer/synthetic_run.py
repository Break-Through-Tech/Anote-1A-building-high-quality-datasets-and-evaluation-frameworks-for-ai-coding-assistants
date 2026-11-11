"""
synthetic_run.py

TEST DATA ONLY. Writes a fake Evaluator-Optimizer run folder in the format Optimizer/loop.py writes
(run_meta.json, attempt_0.jsonl ... attempt_3.jsonl, the same row fields), so results.py, charts.py and
the notebook can be checked on every case the mock provider never produces: B false passes, C hidden-only
passes, regressions, false fixes, failed API calls, critic calls, and real-looking token counts and prices.
The pass rates are invented: never put these numbers in a report. run_meta.json says "synthetic": true,
and the charts carry a TEST DATA banner.

It follows loop.py's rules: A/B tasks stop at attempt 0; after a public pass later attempts are copied
forward (carried_forward, 0 calls); a failed retry is scored 0 and the next one builds on the last good
attempt; regression = hidden test pass rate below the arm's previous good attempt, null on a failed run;
rubric levels use the evaluator's thresholds (2 under half, 3 half or more).

Usage (from the repo root; Evaluator/self_test.py also calls write_run):
    python Optimizer/synthetic_run.py <out_run_dir> [--seed 7]
    python Optimizer/loop.py --summarize <out_run_dir>
    python Optimizer/results.py <out_run_dir> --charts
"""

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from AI_models.budget_tracker import PRICES_PER_MTOK  # noqa: E402
from Evaluator.evaluator import DATASET_PATH, LEVEL_NAMES, SCORING_VERSION, load_items  # noqa: E402

ARMS = ("control", "bare_retry", "reflect_fix", "critic")
MODEL = "claude-sonnet-4-6"  # only for the prices; run_meta's model says SYNTHETIC
N_HIDDEN = 10

# chance an attempt is fully right, by difficulty; arms get a made-up lift so the charts have shape
BASE = {"easy": 0.75, "medium": 0.5, "hard": 0.25, None: 0.55}
LIFT = {"control": 0.0, "bare_retry": 0.05, "reflect_fix": 0.15, "critic": 0.18}
FAIL_TYPES = ["wrong_answer"] * 3 + ["runtime_error", "timeout", "syntax_error", "load_error"]


def usage(rng, arm, attempt, failed):
    p_in, p_out = PRICES_PER_MTOK[MODEL]
    calls = 2 if arm == "critic" else 1
    tin = sum(rng.randint(250, 900) + (600 if attempt else 0) for _ in range(calls))
    tout = 0 if failed else sum(rng.randint(150, 1100) for _ in range(calls))
    return {"calls": calls, "output_tokens": tout, "input_tokens": tin, "tokens_estimated": int(failed),
            "cost_usd": round((tin * p_in + tout * p_out) / 1e6, 6), "latency_s": round(rng.uniform(2, 25), 2)}


def outcome(rng, p_right):
    """(public_score, hidden test pass rate, failure_type)."""
    u = rng.random()
    if u < p_right:
        return 1.0, 1.0, None
    if u < p_right + 0.10:  # passes public, misses an edge case: false pass
        return 1.0, rng.choice([0.6, 0.7, 0.8, 0.9]), "wrong_answer"
    if u < p_right + 0.15:  # fails public, passes hidden (cell C)
        return 0.0, 1.0, None
    ft = rng.choice(FAIL_TYPES)
    rate = 0.0 if ft in ("syntax_error", "load_error") else rng.choice([0.0, 0.1, 0.3, 0.5, 0.7, 0.9])
    return 0.0, rate, ft


def level(rate, ft):
    if rate == 1.0:
        return 4
    if rate == 0.0:
        return 1 if ft == "wrong_answer" else 0
    return 2 if rate < 0.5 else 3


def row(rng, item, arm, attempt, pub, rate, ft, use, failed, prev):
    if failed:
        pub, rate, ft = 0.0, 0.0, None
    hid = 1.0 if rate == 1.0 else 0.0
    lv = None if failed else level(rate, ft)
    pub_rate = 1.0 if pub == 1.0 else round(rng.random() * 0.6, 3)
    return {
        "task_id": item["id"], "source": item["source"], "difficulty": item["metadata"].get("difficulty"),
        "test_format": item["test_format"], "arm": arm, "attempt": attempt,
        "hidden_score": hid, "hidden_test_pass_rate": rate, "hidden_tests": f"{round(rate * N_HIDDEN)}/{N_HIDDEN}",
        "public_score": pub, "public_test_pass_rate": pub_rate, "public_tests": "3/3" if pub == 1.0 else "1/3",
        "false_pass": (not failed) and pub == 1.0 and hid == 0.0,
        "rubric_level": lv, "level": None if lv is None else LEVEL_NAMES[lv],
        "failure_type": None if failed or hid == 1.0 else (ft or "wrong_answer"),
        "regression": None if prev is None or failed else rate < prev["hidden_test_pass_rate"],
        "carried_forward": False, "failed_run": failed, "error": "adapter_error: synthetic" if failed else None,
        **use, "prompt": "(synthetic)", "critique": "(synthetic)" if arm == "critic" else None, "output": "",
    }


def write_run(out, seed=7, retries=3):
    """Writes a synthetic run of every code-generation eval task to `out`. Returns the task ids."""
    rng = random.Random(seed)
    items = [it for it in load_items(DATASET_PATH) if it["task_type"] == "code_generation"]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = {k: [] for k in range(retries + 1)}
    for it in items:
        diff = it["metadata"].get("difficulty")
        failed0 = rng.random() < 0.02
        pub, rate, ft = outcome(rng, BASE[diff])
        r0 = row(rng, it, "zero_shot", 0, pub, rate, ft, usage(rng, "zero_shot", 0, failed0), failed0, None)
        files[0].append(r0)
        if failed0 or r0["public_score"] == 1.0:
            continue
        for arm in ARMS:
            prev = r0
            for k in range(1, retries + 1):
                if prev["public_score"] == 1.0:
                    files[k].append({**prev, "attempt": k, "regression": False, "carried_forward": True,
                                     "calls": 0, "output_tokens": 0, "input_tokens": 0, "tokens_estimated": 0,
                                     "cost_usd": 0, "latency_s": 0, "prompt": None, "critique": None})
                    continue
                failed = rng.random() < 0.03
                p = BASE[diff] * 0.6 + LIFT[arm] * k / 2 + (0.05 if arm != "control" and prev["hidden_test_pass_rate"] > 0 else 0)
                pub, rate, ft = outcome(rng, min(p, 0.95))
                r = row(rng, it, arm, k, pub, rate, ft, usage(rng, arm, k, failed), failed, prev)
                files[k].append(r)
                if not failed:
                    prev = r
    for k, rows in files.items():
        with open(out / f"attempt_{k}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    ids = [it["id"] for it in items]
    meta = {"scoring_version": SCORING_VERSION, "provider": "synthetic", "model": "SYNTHETIC (test data, not a model)",
            "max_tokens": 4096, "temperature": 0.5, "ids_file": "synthetic", "task_ids": ids, "arms": list(ARMS),
            "retries": retries, "rule": "copy-forward after a public pass", "git_commit": None, "usage_log": None,
            "started": None, "finished": None, "synthetic": True, "seed": seed}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2))
    return ids


def main():
    ap = argparse.ArgumentParser(description="Write a synthetic (fake) loop run, for testing the results views.")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    ids = write_run(args.out, args.seed)
    print(f"wrote {len(ids)} synthetic tasks to {args.out} (TEST DATA)")


if __name__ == "__main__":
    main()
