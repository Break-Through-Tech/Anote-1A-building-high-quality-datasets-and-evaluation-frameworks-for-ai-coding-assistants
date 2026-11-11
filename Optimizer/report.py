"""
report.py

The main results table: one Evaluator-Optimizer loop run (Optimizer/loop.py) next to Panacea's zero-shot
run (Baseline/baseline.py panacea), on the same tasks and the same scoring version.

Rows:
  claude zero-shot       the loop's attempt 0 (the official Claude zero-shot result)
  claude + <arm>         the same tasks after that arm's retries (attempt 3); A and B tasks keep attempt 0
  panacea zero-shot      baseline.py's panacea run file (one agent run per task, no retry arms)

Columns: hidden pass@1 (the headline; failed API runs count 0), hidden pass@1 without failed runs,
public pass@1, false passes, failed runs, calls, cost from the budget log rows.

Below the table: attempt 0's A/B/C/D cells, and exact McNemar tests on the per-task hidden pass/fail
(each arm vs the control arm, each arm vs zero-shot, Panacea vs Claude zero-shot). With tens of tasks
these tests have little power: read them as "is there any sign of a difference", not as proof.

It stops if the runs cover different tasks or were scored by different scoring versions.

Usage (from the repo root):
    python Optimizer/report.py data/results/<run>                        # the loop run only
    python Optimizer/report.py data/results/<run> panacea_run.json       # + Panacea
    python Optimizer/report.py data/results/<run> panacea_run.json --out data/results/<run>/report.md
"""

import argparse
import json
import sys
from math import comb
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Optimizer.loop import read_rows, summarize_run  # noqa: E402


def fmt(x, digits=3):
    return "-" if x is None else (f"{x:.{digits}f}" if isinstance(x, float) else str(x))


def mcnemar(a: dict, b: dict):
    """Exact two-sided McNemar test on paired pass/fail (dicts task_id -> 0/1 over the same ids).
    Returns (a only, b only, p)."""
    only_a = sum(a[t] == 1 and b[t] == 0 for t in a)
    only_b = sum(a[t] == 0 and b[t] == 1 for t in a)
    n = only_a + only_b
    if n == 0:
        return only_a, only_b, 1.0
    p = 2 * sum(comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2 ** n
    return only_a, only_b, min(1.0, p)


def loop_outcomes(run_dir: Path, meta: dict) -> dict:
    """Per-task hidden pass (0/1) for zero-shot and for each arm's last attempt. Failed runs count 0."""
    retries = meta["retries"]
    a0 = {r["task_id"]: r for r in read_rows(run_dir, 0)}
    last = {(r["task_id"], r["arm"]): r for r in read_rows(run_dir, retries)}
    out = {"zero_shot": {t: int(r["hidden_score"] == 1.0) for t, r in a0.items()}}
    for arm in meta["arms"]:
        out[arm] = {}
        for t, r0 in a0.items():
            stopped = r0["failed_run"] or r0["public_score"] == 1.0  # never went into the arms
            out[arm][t] = int((r0 if stopped else last[(t, arm)])["hidden_score"] == 1.0)
    return out


def main():
    ap = argparse.ArgumentParser(description="Loop run + Panacea in one results table.")
    ap.add_argument("run_dir", help="a loop run folder, e.g. data/results/2026-11-03_claude_pilot")
    ap.add_argument("baseline_runs", nargs="*", help="baseline.py run files to add (e.g. panacea_run.json)")
    ap.add_argument("--out", help="also write the report to this markdown file")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    meta = json.loads((run_dir / "run_meta.json").read_text())
    s = summarize_run(run_dir)
    ids = set(meta["task_ids"])
    done = {r["task_id"] for r in read_rows(run_dir, 0)}
    if done != ids:
        sys.exit(f"The loop run is unfinished: {len(ids - done)} of {len(ids)} tasks have no attempt 0. "
                 f"Finish it with --resume first.")
    if s["incomplete_task_ids"]:
        sys.exit(f"Tasks with missing arm attempts: {s['incomplete_task_ids']}")

    baselines = []
    for f in args.baseline_runs:
        path = Path(f) if Path(f).exists() else REPO_ROOT / f
        run = json.loads(path.read_text())
        if "summary" not in run or "provider" not in run:
            sys.exit(f"{f} is not a baseline.py run file")
        theirs = {r["id"] for r in run["results"]}
        if theirs != ids:
            sys.exit(f"{f} covers different tasks than the loop run (only in {f}: {sorted(theirs - ids) or '-'}; "
                     f"missing from {f}: {sorted(ids - theirs) or '-'}). Run it with --ids {meta['ids_file']}.")
        if run.get("scoring_version", 1) != meta["scoring_version"]:
            sys.exit(f"{f} was scored by scoring_version {run.get('scoring_version', 1)}, the loop run by "
                     f"{meta['scoring_version']}. Re-run it with the current baseline.py.")
        baselines.append((path.name, run))

    a0, n_failed0 = s["attempt_0"], s["attempt_0"]["failed_runs"]
    n_all = s["n_tasks"]

    def incl_public(st, k):  # public pass@1 with failed attempt-0 runs counted 0, like baseline.py
        p = st["public_pass@1_by_attempt"][k]
        return None if p is None else round(p * st["n"] / n_all, 3)

    head = ["arm", "n", "hidden pass@1", "hidden pass@1 (excl. failed)", "public pass@1", "false passes",
            "failed API calls", "calls", "cost $"]
    who = meta["provider"]
    rows = [[f"{who} zero-shot (attempt 0)", n_all, a0["hidden_pass@1_incl_failed"], a0["hidden_pass@1"],
             round(a0["public_pass@1"] * (n_all - n_failed0) / n_all, 3) if a0["public_pass@1"] is not None else None,
             a0["false_passes"], n_failed0, a0["calls"], a0["cost_usd"]]]
    retries = meta["retries"]
    for arm, st in s["all_tasks"].items():
        rows.append([f"{who} + {arm} (attempt {retries})", n_all, st["hidden_pass@1_incl_failed_by_attempt"][-1],
                     st["hidden_pass@1_by_attempt"][-1], incl_public(st, -1), st["false_passes_by_attempt"][-1],
                     n_failed0 + s["arms"][arm]["failed_runs"], st["calls"], st["cost_usd"]])
    for name, run in baselines:
        bs = run["summary"]
        rows.append([f"{run['provider']} zero-shot ({name})", bs["overall"]["n"], bs["overall"]["pass@1"],
                     bs["excluding_failed_runs"]["pass@1"], bs.get("public_pass@1"), bs.get("false_passes"),
                     bs.get("failed_runs", 0), bs.get("calls"), bs.get("cost_usd")])

    lines = [f"# Results: {run_dir.name}",
             "",
             f"Model {meta['model']}, temperature {meta['temperature']}, max_tokens {meta['max_tokens']}, "
             f"task list {meta['ids_file']} ({n_all} tasks), scoring_version {meta['scoring_version']}. "
             f"pass@1 is on the hidden tests; failed API runs count 0 unless marked excl. failed.",
             "",
             "| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(fmt(x) for x in r) + " |" for r in rows]

    c = a0["cells"]
    lines += ["", "## Attempt 0 cells",
              "| A true pass | B false pass | C hidden-only pass | D true fail | failed runs |",
              "|---|---|---|---|---|",
              f"| {c['A_true_pass']} | {c['B_false_pass']} | {c['C_hidden_only_pass']} | {c['D_true_fail']} | "
              f"{n_failed0} |",
              "",
              "B tasks pass the public tests, so no arm retries them: they cap every arm equally. "
              "C and D go into the arms; repairs are counted over D, breaks over C.",
              "",
              "## Self-correction (tasks that went into the arms, C + D)",
              "| arm | hidden pass@1, attempts 0-3 | repairs (of D) | breaks (of C) | false fixes | regressions | "
              "$ per repair |",
              "|---|---|---|---|---|---|---|"]
    for arm, st in s["arms"].items():
        lines.append(f"| {arm} | {' / '.join(fmt(x) for x in st['hidden_pass@1_by_attempt'])} | "
                     f"{st['repairs']}/{st['n_D_repair_targets']} | {st['breaks']}/{st['n_C_hidden_only_pass']} | "
                     f"{st['false_fixes']} | {st['regressions']} | {fmt(st['cost_per_repair_usd'], 4)} |")

    out = loop_outcomes(run_dir, meta)
    tests = []
    for arm in meta["arms"]:
        if arm != "control" and "control" in out:
            tests.append((f"{arm} vs control", out[arm], out["control"]))
        tests.append((f"{arm} vs zero-shot", out[arm], out["zero_shot"]))
    for name, run in baselines:
        theirs = {r["id"]: int(r["score"] == 1.0) for r in run["results"]}
        tests.append((f"{run['provider']} vs {who} zero-shot", theirs, out["zero_shot"]))
    lines += ["", "## Paired tests (exact McNemar, hidden pass/fail per task)",
              "| comparison | only first passes | only second passes | p |", "|---|---|---|---|"]
    for label, x, y in tests:
        a_only, b_only, p = mcnemar(x, y)
        lines.append(f"| {label} | {a_only} | {b_only} | {p:.3f} |")

    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
        print(f"\nSaved to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
