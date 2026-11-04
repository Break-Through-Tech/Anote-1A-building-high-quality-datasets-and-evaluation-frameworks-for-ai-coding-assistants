"""
results.py

Detailed results tables for one Evaluator-Optimizer loop run (Optimizer/loop.py), optionally with
Panacea's zero-shot run (Baseline/baseline.py panacea) beside it. Every table is a pandas DataFrame,
also written as a CSV, and notebooks/results_analysis.ipynb loads them for analysis.

Systems and attempts:
  zero_shot   Claude's attempt 0 (shared by every arm; the official Claude zero-shot result)
  <arm>       control / bare_retry / reflect_fix / critic, attempts 0-3. Attempt 0 is the shared zero-shot
              answer. Tasks that passed their public tests at attempt 0 (cells A and B) keep that answer at
              every attempt, so every arm covers every task at every attempt.
  panacea     Panacea's agent, one run per task (attempt 0 only; no retry arms)

Attempt-0 cells (Claude, and Panacea on its own results):
  A true pass (public pass, hidden pass)    B false pass (public pass, hidden fail)
  C hidden-only pass (public fail, hidden)  D true fail (public fail, hidden fail)    failed (API call failed)
Only C and D go into the arms.

Tables (CSV name -> what it holds):
  attempts.csv         long table: one row per system x task x attempt, every field (the source of the rest),
                       plus the grouping columns source_difficulty, task_type, attempt0_failure_type (Claude's)
  tasks.csv            wide table: one row per task; hidden "passed/total" and rubric level for zero-shot,
                       every arm at attempts 1-3, and Panacea
  main.csv             per system x attempt: hidden pass@1 (failed runs 0 / left out, the latter with a Wilson
                       95% CI), mean hidden test pass rate, public pass@1, false passes, rubric level counts 0-4,
                       calls and cost (this attempt and cumulative)
  curves.csv           per scope x arm x attempt: hidden pass@1 with a Wilson 95% CI, and the gain over the
                       control on the same tasks with a paired bootstrap 95% CI (tasks resampled, 2000 draws,
                       seed 0). Scopes: all = every task whose attempt-0 call worked (summary.json's all_tasks;
                       hidden_pass@1_incl_failed counts failed ones 0), paired = C + D (summary.json's arms),
                       D = the repair targets only
  arm_outcomes.csv     per arm, tasks that went into the arms, at the last attempt: repairs (D now passing hidden,
                       Wilson CI), breaks (C now failing), false fixes (public pass, hidden fail; from D / from C,
                       and as a share of the public "fixes"), regressions (events, tasks, rate per retry that ran),
                       failed API calls, retry calls / tokens / $, $ / tokens / calls per repair, extra repairs and
                       extra $ per extra repair vs the control (negative: more repairs for less money than the
                       control), and the pipeline cost (attempt 0 on every task + the arm's retries)
  cells.csv            per system: A/B/C/D/failed counts, the B tasks' mean hidden test pass rate, task ids
  transitions.csv      per arm x step (0->1, 1->2, 2->3), tasks that went into the arms: fixed, broke, stayed
                       pass / fail, level up / down / same, first public pass at this step, failed API calls.
                       Each step compares with the last good attempt; a failed API call is counted only as one
  retry_value.csv      per arm x attempt 1-3, every task: hidden pass@1 gained, tasks solved, failed API calls,
                       cost of this attempt, $ and calls per extra solved task
  stops.csv            per arm: tasks that went into the arms, by the attempt of their first public pass
  failure_types.csv    per system x attempt: count of each failure_type (hidden scoring)
  failure_moves.csv    per arm: failure_type at attempt 0 -> at attempt 3, tasks that went into the arms
  by_group.csv         main.csv's key numbers and the gain over the control, split by source/difficulty, test
                       format and task type (scope all: every task, failed runs 0; and scope paired: C + D), and by
                       Claude's attempt-0 failure type (paired only). MBPP and LiveCodeBench difficulties are
                       different scales: always grouped by source
  paired_tests.csv     exact McNemar tests on per-task hidden pass/fail: every pair of arms at attempts 1-3,
                       each arm vs its previous attempt, each arm vs zero-shot at attempts 1-3, Panacea vs
                       Claude zero-shot and vs each arm at attempt 3. Raw p values, no correction for the
                       number of tests: with this many tests some small p values appear by chance.

Usage (from the repo root):
    python Optimizer/results.py data/results/<run>                     # loop run only
    python Optimizer/results.py data/results/<run> panacea_run.json    # + Panacea
    python Optimizer/results.py data/results/<run> panacea_run.json --charts   # + PNG charts (Optimizer/charts.py)
CSVs go to data/results/<run>/analysis/ (or --out), charts to analysis/charts/. The run must be finished, and the Panacea run must
cover the same tasks with the same scoring version (same checks as report.py).
"""

import argparse
import json
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Optimizer.loop import CELLS, ZERO_SHOT, read_rows  # noqa: E402
from Optimizer.report import mcnemar  # noqa: E402

PANACEA = "panacea"
LEVELS = [0, 1, 2, 3, 4]
N_BOOT = 2000
TASK_TYPES = {"mbpp": "code_generation", "livecodebench": "code_generation",
              "quixbugs": "bug_fixing", "humanevalfix": "bug_fixing"}
# grouping column -> scopes it is reported on (attempt-0 failure type only makes sense for C + D)
GROUPINGS = {"source_difficulty": ("all", "paired"), "test_format": ("all", "paired"),
             "task_type": ("all", "paired"), "attempt0_failure_type": ("paired",)}


def _counts(s):
    """'7/10' -> (7, 10)."""
    a, b = str(s).split("/")
    return int(a), int(b)


def wilson(k, n, z=1.96):
    """Wilson 95% interval for k passes out of n."""
    if not n:
        return None, None
    p, d = k / n, 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 3), round((c + h) / d, 3)


def boot_delta(a, b, n_boot=N_BOOT, seed=0):
    """Paired bootstrap 95% CI for mean(a - b) over the same tasks (tasks resampled)."""
    d = np.asarray(a, float) - np.asarray(b, float)
    if not len(d):
        return None, None
    means = d[np.random.default_rng(seed).integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    return round(float(np.percentile(means, 2.5)), 3), round(float(np.percentile(means, 97.5)), 3)


def _gain(m, c):
    """Arm minus control, from the rounded means (the way summary.json computes it)."""
    return None if m is None or c is None else round(round(m, 3) - round(c, 3), 3)


def _cell(public_score, hidden_score, failed):
    return "failed" if failed else CELLS[(public_score == 1.0, hidden_score == 1.0)]


# =====================================================================
# LOAD: one long table
# =====================================================================
def _loop_row(r, system, attempt, from_attempt0=False):
    hp, ht = _counts(r["hidden_tests"])
    pp, pt = _counts(r["public_tests"])
    return {
        "system": system, "task_id": r["task_id"], "attempt": attempt,
        "source": r["source"], "difficulty": r["difficulty"], "test_format": r["test_format"],
        "hidden_score": r["hidden_score"], "hidden_passed": hp, "hidden_total": ht,
        "hidden_test_pass_rate": r["hidden_test_pass_rate"],
        "rubric_level": r["rubric_level"], "level": r["level"], "failure_type": r["failure_type"],
        "public_score": r["public_score"], "public_passed": pp, "public_total": pt,
        "false_pass": r["false_pass"], "failed_run": r["failed_run"],
        "carried_forward": r.get("carried_forward", False) or from_attempt0,
        "regression": r.get("regression"),
        # an attempt-0 answer repeated at a later attempt cost nothing more
        "calls": 0 if from_attempt0 else r["calls"],
        "input_tokens": 0 if from_attempt0 else r["input_tokens"],
        "output_tokens": 0 if from_attempt0 else r["output_tokens"],
        "cost_usd": 0.0 if from_attempt0 else r["cost_usd"],
    }


def load(run_dir, panacea_path=None):
    """Returns (attempts DataFrame, meta). Checks the run is complete and the Panacea run matches it."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run_meta.json").read_text())
    retries, arms = meta["retries"], meta["arms"]
    a0 = {r["task_id"]: r for r in read_rows(run_dir, 0)}
    if set(a0) != set(meta["task_ids"]):
        sys.exit(f"The loop run is unfinished: {len(set(meta['task_ids']) - set(a0))} tasks have no attempt 0. "
                 f"Finish it with --resume first.")
    later = {(r["task_id"], r["arm"], r["attempt"]): r for k in range(1, retries + 1) for r in read_rows(run_dir, k)}

    rows = []
    for tid, r0 in a0.items():
        cell = _cell(r0["public_score"], r0["hidden_score"], r0["failed_run"])
        rows.append({**_loop_row(r0, ZERO_SHOT, 0), "cell": cell})
        for arm in arms:
            rows.append({**_loop_row(r0, arm, 0), "cell": cell})
            for k in range(1, retries + 1):
                if cell in ("C_hidden_only_pass", "D_true_fail"):
                    if (tid, arm, k) not in later:
                        sys.exit(f"{tid}: arm {arm} has no attempt {k}. Finish the run with --resume first.")
                    rows.append({**_loop_row(later[(tid, arm, k)], arm, k), "cell": cell})
                else:  # A, B or failed: stopped at attempt 0
                    rows.append({**_loop_row(r0, arm, k, from_attempt0=True), "cell": cell})

    if panacea_path:
        path = Path(panacea_path) if Path(panacea_path).exists() else REPO_ROOT / panacea_path
        run = json.loads(path.read_text())
        theirs = {r["id"] for r in run["results"]}
        if theirs != set(a0):
            sys.exit(f"{path.name} covers different tasks than the loop run (only there: "
                     f"{sorted(theirs - set(a0)) or '-'}; missing: {sorted(set(a0) - theirs) or '-'}).")
        if run.get("scoring_version", 1) != meta["scoring_version"]:
            sys.exit(f"{path.name} has scoring_version {run.get('scoring_version', 1)}, the loop run "
                     f"{meta['scoring_version']}.")
        for r in run["results"]:
            info = a0[r["id"]]
            pub = r.get("public") or {}
            failed = bool(r.get("failed_run"))
            rows.append({
                "system": PANACEA, "task_id": r["id"], "attempt": 0,
                "source": info["source"], "difficulty": info["difficulty"], "test_format": info["test_format"],
                "hidden_score": r["score"], "hidden_passed": r["n_passed"], "hidden_total": r["n_tests"],
                "hidden_test_pass_rate": r["test_pass_rate"], "rubric_level": r["rubric_level"],
                "level": r["level"], "failure_type": None if failed else r["failure_type"],
                "public_score": pub.get("score", 0.0), "public_passed": pub.get("n_passed", 0),
                "public_total": pub.get("n_tests", 0), "false_pass": bool(r.get("false_pass")),
                "failed_run": failed, "carried_forward": False, "regression": None,
                "calls": r.get("calls"), "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"), "cost_usd": r.get("cost_usd"),
                "cell": _cell(pub.get("score", 0.0), r["score"], failed),
            })
    df = pd.DataFrame(rows)
    df["rubric_level"] = df["rubric_level"].astype("Int64")  # 0-4, blank for a failed API call
    df["in_arms"] = df["cell"].isin(["C_hidden_only_pass", "D_true_fail"]) & (df["system"] != PANACEA)
    df["source_difficulty"] = df["source"] + "/" + df["difficulty"].fillna("-")
    df["task_type"] = df["source"].map(TASK_TYPES).fillna("other")
    z0 = df[(df["system"] == ZERO_SHOT) & (df["attempt"] == 0)].set_index("task_id")
    why = z0["failure_type"].fillna("none (hidden pass)").where(~z0["failed_run"], "failed_api_call")
    df["attempt0_failure_type"] = df["task_id"].map(why)  # Claude's, for every system
    return df, meta


def systems(df):
    """Display order: zero-shot, the arms, Panacea."""
    names = list(dict.fromkeys(df["system"]))
    return [ZERO_SHOT] + [s for s in names if s not in (ZERO_SHOT, PANACEA)] + ([PANACEA] if PANACEA in names else [])


# =====================================================================
# TABLES
# =====================================================================
def _stats(g, failed0):
    """One system at one attempt. failed0 = tasks whose attempt-0 call failed (left out of *_excl_failed)."""
    ok = g[~g["task_id"].isin(failed0)]
    lo, hi = wilson(int(ok["hidden_score"].sum()), len(ok))
    out = {"n": len(g), "n_excl_failed": len(ok),
           "hidden_pass@1": round(g["hidden_score"].mean(), 3),
           "hidden_pass@1_excl_failed": round(ok["hidden_score"].mean(), 3) if len(ok) else None,
           "excl_failed_ci_low": lo, "excl_failed_ci_high": hi,
           "mean_hidden_test_pass_rate": round(g["hidden_test_pass_rate"].mean(), 3),
           "public_pass@1": round(g["public_score"].mean(), 3),
           "false_passes": int(g["false_pass"].sum()), "failed_runs": int(g["failed_run"].sum())}
    for lv in LEVELS:
        out[f"level_{lv}"] = int((g["rubric_level"] == lv).sum())
    out["level_none"] = int(g["rubric_level"].isna().sum())  # failed API calls get no level
    return out


def _attempt0_failed_ids(df, system):
    return set(df.loc[(df["system"] == system) & (df["attempt"] == 0) & df["failed_run"], "task_id"])


def main_table(df):
    rows = []
    for s in systems(df):
        d = df[df["system"] == s]
        failed0 = _attempt0_failed_ids(df, s)
        cum_calls = cum_cost = 0
        for k in sorted(d["attempt"].unique()):
            g = d[d["attempt"] == k]
            st = _stats(g, failed0)
            # an arm's attempt 0 is the shared zero-shot answer, so its cumulative cost starts with that cost
            calls, cost = g["calls"].sum(), g["cost_usd"].fillna(0).sum()
            cum_calls += calls
            cum_cost += cost
            rows.append({"system": s, "attempt": int(k), **st, "calls": int(calls), "cost_usd": round(cost, 4),
                         "cumulative_calls": int(cum_calls), "cumulative_cost_usd": round(cum_cost, 4)})
    return pd.DataFrame(rows)


def cells_table(df):
    rows = []
    for s in ([ZERO_SHOT] + ([PANACEA] if PANACEA in set(df["system"]) else [])):
        d = df[(df["system"] == s) & (df["attempt"] == 0)]
        row = {"system": "claude" if s == ZERO_SHOT else s, "n": len(d)}
        for c in list(CELLS.values()) + ["failed"]:
            row[c] = int((d["cell"] == c).sum())
        b = d[d["cell"] == "B_false_pass"]
        row["B_mean_hidden_test_pass_rate"] = round(b["hidden_test_pass_rate"].mean(), 3) if len(b) else None
        for c in list(CELLS.values()) + ["failed"]:
            row[f"{c}_ids"] = " ".join(sorted(d.loc[d["cell"] == c, "task_id"]))
        rows.append(row)
    return pd.DataFrame(rows)


def _arms(df):
    return [s for s in systems(df) if s not in (ZERO_SHOT, PANACEA)]


SCOPES = {"all": lambda d, failed0: d[~d["task_id"].isin(failed0)],
          "paired": lambda d, failed0: d[d["in_arms"]],
          "D": lambda d, failed0: d[d["in_arms"] & (d["cell"] == "D_true_fail")]}


def curves_table(df, n_boot=N_BOOT):
    failed0 = _attempt0_failed_ids(df, ZERO_SHOT)
    arms = _arms(df)
    rows = []
    for scope, pick in SCOPES.items():
        ctrl = pick(df[df["system"] == "control"], failed0) if "control" in arms else None
        for arm in arms:
            d = pick(df[df["system"] == arm], failed0)
            for k in sorted(d["attempt"].unique()):
                g = d[d["attempt"] == k].sort_values("task_id")
                n, passes = len(g), int(g["hidden_score"].sum())
                lo, hi = wilson(passes, n)
                row = {"scope": scope, "arm": arm, "attempt": int(k), "n": n, "hidden_passes": passes,
                       "hidden_pass@1": round(passes / n, 3), "ci_low": lo, "ci_high": hi,
                       "hidden_pass@1_incl_failed": (round(passes / (n + len(failed0)), 3)
                                                     if scope == "all" else None),
                       "public_pass@1": round(g["public_score"].mean(), 3),
                       "false_passes": int(g["false_pass"].sum()),
                       "mean_hidden_test_pass_rate": round(g["hidden_test_pass_rate"].mean(), 3),
                       "gain_vs_control": None, "gain_ci_low": None, "gain_ci_high": None}
                if ctrl is not None:
                    c = ctrl[ctrl["attempt"] == k].sort_values("task_id")  # the same tasks, same order
                    row["gain_vs_control"] = _gain(g["hidden_score"].mean(), c["hidden_score"].mean())
                    if arm != "control":
                        row["gain_ci_low"], row["gain_ci_high"] = boot_delta(
                            g["hidden_score"].to_numpy(), c["hidden_score"].to_numpy(), n_boot)
                rows.append(row)
    return pd.DataFrame(rows)


def _is_true(s):
    return s.map(lambda x: x is True)


def arm_outcomes_table(df):
    zs = df[df["system"] == ZERO_SHOT]
    zs_cost, zs_calls = zs["cost_usd"].fillna(0).sum(), int(zs["calls"].sum())
    rows = []
    for arm in _arms(df):
        d = df[(df["system"] == arm) & df["in_arms"]]
        last = int(df.loc[df["system"] == arm, "attempt"].max())
        fin, retries = d[d["attempt"] == last], d[d["attempt"] > 0]
        D, C = fin[fin["cell"] == "D_true_fail"], fin[fin["cell"] == "C_hidden_only_pass"]
        ran = retries[~retries["carried_forward"].astype(bool) & ~retries["failed_run"]]
        reg = retries[_is_true(retries["regression"])]
        repairs, breaks = int((D["hidden_score"] == 1.0).sum()), int((C["hidden_score"] == 0.0).sum())
        ff_d, ff_c = int(D["false_pass"].sum()), int(C["false_pass"].sum())
        public_fixes = int((fin["public_score"] == 1.0).sum())
        calls, tin, tout = int(retries["calls"].sum()), int(retries["input_tokens"].sum()), int(retries["output_tokens"].sum())
        cost = retries["cost_usd"].fillna(0).sum()
        lo, hi = wilson(repairs, len(D))
        per = lambda x: round(x / repairs, 4) if repairs else None  # noqa: E731
        rows.append({
            "arm": arm, "attempt": last, "n_paired": len(fin), "n_D": len(D), "n_C": len(C),
            "repairs": repairs, "repair_rate": round(repairs / len(D), 3) if len(D) else None,
            "repair_ci_low": lo, "repair_ci_high": hi,
            "breaks": breaks, "break_rate": round(breaks / len(C), 3) if len(C) else None,
            "public_fixes": public_fixes, "false_fixes": ff_d + ff_c,
            "false_fixes_from_D": ff_d, "false_fixes_from_C": ff_c,
            "false_fix_share": round((ff_d + ff_c) / public_fixes, 3) if public_fixes else None,
            "regression_events": len(reg), "tasks_with_regression": reg["task_id"].nunique(),
            "retries_that_ran": len(ran),
            "regression_rate_per_retry": round(len(reg) / len(ran), 3) if len(ran) else None,
            "failed_api_calls": int(retries["failed_run"].sum()),
            "calls": calls, "input_tokens": tin, "output_tokens": tout,
            "cost_usd": round(cost, 4),
            "cost_per_repair_usd": per(cost), "tokens_per_repair": round((tin + tout) / repairs) if repairs else None,
            "calls_per_repair": round(calls / repairs, 2) if repairs else None,
            "pipeline_calls": zs_calls + calls, "pipeline_cost_usd": round(zs_cost + round(cost, 4), 4),
        })
    t = pd.DataFrame(rows)
    if not t.empty and "control" in set(t["arm"]):
        c = t[t["arm"] == "control"].iloc[0]
        t["extra_repairs_vs_control"] = t["repairs"] - c["repairs"]
        t["extra_cost_vs_control_usd"] = (t["cost_usd"] - c["cost_usd"]).round(4)
        t["extra_cost_per_extra_repair_usd"] = [
            round(ec / er, 4) if er > 0 and arm != "control" else None
            for arm, ec, er in zip(t["arm"], t["extra_cost_vs_control_usd"], t["extra_repairs_vs_control"])]
    return t


def transitions_table(df):
    rows = []
    for arm in _arms(df):
        d = df[(df["system"] == arm) & df["in_arms"]]
        if d.empty:
            continue
        hs, lv, ps, fr = (d.pivot(index="task_id", columns="attempt", values=c)
                          for c in ("hidden_score", "rubric_level", "public_score", "failed_run"))
        fr = fr.astype(bool)
        # A failed API call is not the model changing its code: like the loop, the next attempt builds on the
        # last good one. So each step compares with the last good attempt, and a step whose attempt is a
        # failed call is counted only in failed_api_calls (not as fixed / broke / a level move).
        hs_good, lv_good = hs.mask(fr).ffill(axis=1), lv.astype("Float64").mask(fr).ffill(axis=1)
        for k in range(1, int(d["attempt"].max()) + 1):
            ran = ~fr[k]
            prev, cur = hs_good[k - 1] == 1.0, hs[k] == 1.0
            lp, lc = lv_good[k - 1], lv[k].astype("Float64")
            both = ran & lp.notna() & lc.notna()
            first_public = ran & (ps[k] == 1.0) & (ps[list(range(0, k))] != 1.0).all(axis=1)
            rows.append({
                "arm": arm, "step": f"{k - 1}->{k}", "n": len(hs),
                "fixed": int((ran & ~prev & cur).sum()), "broke": int((ran & prev & ~cur).sum()),
                "stayed_pass": int((ran & prev & cur).sum()), "stayed_fail": int((ran & ~prev & ~cur).sum()),
                "level_up": int((both & (lc > lp)).sum()), "level_down": int((both & (lc < lp)).sum()),
                "level_same": int((both & (lc == lp)).sum()),
                "first_public_pass": int(first_public.sum()),
                "failed_api_calls": int(fr[k].sum()),
                "hidden_pass@1_after": round(hs[k].mean(), 3),
            })
    return pd.DataFrame(rows)


def retry_value_table(df):
    rows = []
    for arm in _arms(df):
        d = df[df["system"] == arm]
        for k in range(1, int(d["attempt"].max()) + 1):
            before, now = d[d["attempt"] == k - 1], d[d["attempt"] == k]
            solved = int(now["hidden_score"].sum()) - int(before["hidden_score"].sum())
            cost, calls = now["cost_usd"].sum(), int(now["calls"].sum())
            rows.append({
                "arm": arm, "attempt": k,
                "hidden_pass@1": round(now["hidden_score"].mean(), 3),
                "gain_over_previous": round(now["hidden_score"].mean() - before["hidden_score"].mean(), 3),
                # a failed API call scores 0 at its attempt, so it can show as a dip here and a gain next time
                "extra_tasks_solved": solved, "failed_api_calls": int(now["failed_run"].sum()), "calls": calls,
                "input_tokens": int(now["input_tokens"].sum()), "output_tokens": int(now["output_tokens"].sum()),
                "cost_usd": round(cost, 4),
                "cost_per_extra_solved_usd": round(cost / solved, 4) if solved > 0 else None,
                "calls_per_extra_solved": round(calls / solved, 2) if solved > 0 else None,
            })
    return pd.DataFrame(rows)


def stops_table(df):
    rows = []
    for arm in _arms(df):
        d = df[(df["system"] == arm) & df["in_arms"]]
        if d.empty:
            continue
        ps = d.pivot(index="task_id", columns="attempt", values="public_score")
        first = ps.apply(lambda r: next((int(k) for k in ps.columns if k > 0 and r[k] == 1.0), None), axis=1)
        row = {"arm": arm, "n": len(ps)}
        for k in ps.columns[1:]:
            row[f"first_public_pass_at_{int(k)}"] = int((first == k).sum())
        row["never"] = int(first.isna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


def failure_types_table(df):
    d = df.assign(failure_type=df["failure_type"].fillna("passed").where(~df["failed_run"], "failed_api_call"))
    t = d.groupby(["system", "attempt", "failure_type"]).size().unstack(fill_value=0).reset_index()
    t["order"] = t["system"].map({s: i for i, s in enumerate(systems(df))})
    return t.sort_values(["order", "attempt"]).drop(columns="order").reset_index(drop=True)


def failure_moves_table(df):
    rows = []
    for arm in _arms(df):
        d = df[(df["system"] == arm) & df["in_arms"]]
        if d.empty:
            continue
        last = int(d["attempt"].max())
        lab = d.assign(ft=d["failure_type"].fillna("passed").where(~d["failed_run"], "failed_api_call"))
        w = lab.pivot(index="task_id", columns="attempt", values="ft")
        for (a, b), n in w.groupby([0, last]).size().items():
            rows.append({"arm": arm, "attempt_0": a, f"attempt_{last}": b, "tasks": int(n)})
    return pd.DataFrame(rows)


def by_group_table(df):
    rows = []
    for name, scopes in GROUPINGS.items():
        for scope in scopes:
            d = df if scope == "all" else df[df["in_arms"]]
            rows += _group_rows(d, name, scope)
    t = pd.DataFrame(rows)
    ctrl = t[t["system"] == "control"].set_index(["grouping", "scope", "group", "attempt"])["hidden_pass@1"]
    if len(ctrl):
        keys = list(zip(t["grouping"], t["scope"], t["group"], t["attempt"]))
        t["gain_vs_control"] = [_gain(m, ctrl.get(key)) if s not in (ZERO_SHOT, PANACEA) else None
                                for s, m, key in zip(t["system"], t["hidden_pass@1"], keys)]
    t["order"] = t["system"].map({s: i for i, s in enumerate(systems(df))})
    return (t.sort_values(["grouping", "scope", "group", "order", "attempt"]).drop(columns="order")
            .reset_index(drop=True))


def _group_rows(d, name, scope):
    rows = []
    for (s, k, grp), g in d.groupby(["system", "attempt", name]):
        rows.append({"grouping": name, "scope": scope, "group": grp, "system": s, "attempt": int(k), "n": len(g),
                     "hidden_pass@1": round(g["hidden_score"].mean(), 3),
                     "mean_hidden_test_pass_rate": round(g["hidden_test_pass_rate"].mean(), 3),
                     "public_pass@1": round(g["public_score"].mean(), 3),
                     "false_passes": int(g["false_pass"].sum()),
                     **{f"level_{lv}": int((g["rubric_level"] == lv).sum()) for lv in LEVELS}})
    return rows


def paired_tests_table(df):
    def passes(system, k):
        d = df[(df["system"] == system) & (df["attempt"] == k)]
        return dict(zip(d["task_id"], (d["hidden_score"] == 1.0).astype(int)))

    arms = _arms(df)
    last = int(df["attempt"].max())
    tests = []
    for k in range(1, last + 1):
        for a, b in combinations(arms, 2):
            tests.append(("arm vs arm", f"{a} vs {b}", k, (a, k), (b, k)))
    for arm in arms:
        for k in range(1, last + 1):
            tests.append(("attempt vs previous", f"{arm}: attempt {k} vs {k - 1}", k, (arm, k), (arm, k - 1)))
    for arm in arms:
        for k in range(1, last + 1):
            tests.append(("arm vs zero-shot", f"{arm} vs zero-shot", k, (arm, k), (ZERO_SHOT, 0)))
    if PANACEA in set(df["system"]):
        tests.append(("panacea", "panacea vs claude zero-shot", 0, (PANACEA, 0), (ZERO_SHOT, 0)))
        for arm in arms:
            tests.append(("panacea", f"panacea vs {arm}", last, (PANACEA, 0), (arm, last)))
    rows = []
    for kind, label, k, x, y in tests:
        a, b = passes(*x), passes(*y)
        first_only, second_only, p = mcnemar(a, b)
        rows.append({"kind": kind, "comparison": label, "attempt": k, "n": len(a),
                     "first_passes": sum(a.values()), "second_passes": sum(b.values()),
                     "only_first_passes": first_only, "only_second_passes": second_only,
                     "both_pass": sum(a[t] and b[t] for t in a), "both_fail": sum(not a[t] and not b[t] for t in a),
                     "p_exact_mcnemar": round(p, 4)})
    return pd.DataFrame(rows)


def tasks_table(df):
    info = df[(df["system"] == ZERO_SHOT)][["task_id", "source", "difficulty", "test_format", "cell"]]
    out = info.rename(columns={"cell": "claude_cell"}).set_index("task_id")
    d = df.assign(hidden=df["hidden_passed"].astype(str) + "/" + df["hidden_total"].astype(str))
    for s in systems(df):
        g = d[d["system"] == s]
        ks = [0] if s in (ZERO_SHOT, PANACEA) else sorted(k for k in g["attempt"].unique() if k > 0)
        for k in ks:
            gk = g[g["attempt"] == k].set_index("task_id")
            tag = s if s in (ZERO_SHOT, PANACEA) else f"{s}_a{int(k)}"
            out[f"{tag}_hidden"] = gk["hidden"]
            out[f"{tag}_level"] = gk["rubric_level"]
        if s == PANACEA:
            out["panacea_cell"] = g.set_index("task_id")["cell"]
    return out.reset_index()


TABLES = {"main": main_table, "curves": curves_table, "arm_outcomes": arm_outcomes_table,
          "cells": cells_table, "transitions": transitions_table,
          "retry_value": retry_value_table, "stops": stops_table, "failure_types": failure_types_table,
          "failure_moves": failure_moves_table, "by_group": by_group_table, "paired_tests": paired_tests_table,
          "tasks": tasks_table}


def build(run_dir, panacea_path=None, out_dir=None, write=True):
    """All tables as {name: DataFrame}, plus 'attempts' (the long table). Writes them as CSVs unless write=False."""
    df, meta = load(run_dir, panacea_path)
    tables = {"attempts": df, **{name: fn(df) for name, fn in TABLES.items()}}
    if write:
        out = Path(out_dir) if out_dir else Path(run_dir) / "analysis"
        out.mkdir(parents=True, exist_ok=True)
        for name, t in tables.items():
            t.to_csv(out / f"{name}.csv", index=False)
        (out / "README.txt").write_text(__doc__)
    return tables, meta


def main():
    ap = argparse.ArgumentParser(description="Detailed results tables (CSV) for one loop run (+ Panacea).")
    ap.add_argument("run_dir")
    ap.add_argument("panacea_run", nargs="?", help="baseline.py panacea run file (e.g. panacea_run.json)")
    ap.add_argument("--out", help="folder for the CSVs (default <run_dir>/analysis)")
    ap.add_argument("--charts", action="store_true", help="also draw the PNG charts (Optimizer/charts.py)")
    ap.add_argument("--theme", choices=["light", "dark"], default="light", help="chart theme")
    args = ap.parse_args()
    tables, meta = build(args.run_dir, args.panacea_run, args.out)
    out = Path(args.out) if args.out else Path(args.run_dir) / "analysis"
    for name, t in tables.items():
        print(f"{name}.csv: {len(t)} rows")
    if args.charts:
        import matplotlib
        matplotlib.use("Agg")  # no window: write the PNGs only
        from Optimizer.charts import draw_all
        figs = draw_all(tables, meta, out / "charts", theme=args.theme, close=True)
        print(f"charts: {len(figs)} PNGs in charts/")
    print(f"-> {out}/")


if __name__ == "__main__":
    main()
