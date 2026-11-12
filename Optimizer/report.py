"""
report.py

All summaries of one Evaluator-Optimizer loop run: summary.json and the run report. The report is one
text, printed in the terminal and saved as report.md, covering everything in summary.json. Optimizer/loop.py
only runs the experiment and calls write_report() when a run ends. This file imports nothing from loop.py.

Names, the same in summary.json, the report and results.py's tables:
  hidden_pass@1, public_pass@1   failed attempt-0 API calls count 0
  *_excl_failed                  those tasks are left out. Failed retries count 0 in both

Report sections: run health, main results (zero-shot, each arm at attempt 3, Panacea), all tasks by attempt,
the A/B/C/D cells, self-correction (C + D), breakdowns by source/difficulty and failure type, cut-off
sensitivity (the results with and without the tasks where an answer hit max_tokens), whether telling the model
it ran out of space helps (answers cut off again after a cut-off answer, told vs not told), paired tests, task
ids, notes.

Paired tests are exact McNemar tests on per-task hidden pass/fail. p_holm is Holm-adjusted within a family, so
one family's result doesn't depend on which others are present. feedback_vs_control (each feedback arm vs the
control at the last attempt) is the family that answers the research question. With tens of tasks these
tests have little power: "not significant" means this run can't tell, not that there is no difference.

Running this file adds baseline.py run files (Panacea) to the report. It stops if the runs cover different
tasks or were scored by different scoring versions.

Usage (from the repo root):
    python Optimizer/report.py data/results/<run>                        # the loop run only
    python Optimizer/report.py data/results/<run> panacea_run.json       # + Panacea
    python Optimizer/report.py data/results/<run> panacea_run.json --out other_report.md
"""

import argparse
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_SHOT = "zero_shot"
ALPHA = 0.05


def read_rows(run_dir: Path, attempt: int) -> list:
    path = run_dir / f"attempt_{attempt}.jsonl"
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


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


def holm(ps):
    """Holm-adjusted p values, in the same order as ps."""
    order = sorted(range(len(ps)), key=ps.__getitem__)
    adj, running = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, ps[i] * (len(ps) - rank)))
        adj[i] = running
    return adj


def paired_row(family, comparison, attempt, a, b):
    first_only, second_only, p = mcnemar(a, b)
    return {"family": family, "comparison": comparison, "attempt": attempt, "n": len(a),
            "first_passes": sum(a.values()), "second_passes": sum(b.values()),
            "only_first_passes": first_only, "only_second_passes": second_only,
            "both_pass": sum(a[t] and b[t] for t in a), "both_fail": sum(not a[t] and not b[t] for t in a),
            "p_exact_mcnemar": p}


def add_holm(rows):
    """Adds p_holm and significant, correcting within each family."""
    for family in {r["family"] for r in rows}:
        group = [r for r in rows if r["family"] == family]
        for r, adj in zip(group, holm([r["p_exact_mcnemar"] for r in group])):
            r["p_exact_mcnemar"], r["p_holm"], r["significant"] = round(r["p_exact_mcnemar"], 4), round(adj, 4), adj < ALPHA
    return rows


# =====================================================================
# SUMMARY: summary.json
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
    all_ids = [r["task_id"] for r in a0 if r["task_id"] not in incomplete]  # failed runs count 0

    cells = defaultdict(list)
    for r in ok0:
        cells[cell_of(r)].append(r["task_id"])

    def row_at(tid, arm, k):
        """The task's row in this arm at attempt k: attempt 0 for A/B tasks, failed attempt-0 runs and at k = 0."""
        r0 = a0_by_id[tid]
        return r0 if k == 0 or r0["failed_run"] or r0["public_score"] == 1.0 else by_key[(tid, arm, k)]

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
            "failed_runs_by_attempt": [sum(c[k]["failed_run"] for c in chains) for k in range(1, retries + 1)],
            **use,
            "cost_per_repair_usd": round(use["cost_usd"] / repairs, 4) if repairs else None,
            "calls_per_repair": round(use["calls"] / repairs, 2) if repairs else None,
        }

    def all_tasks_stats(task_ids, arm):
        """Every task, attempts 0-3. Failed attempt-0 runs count 0; *_excl_failed leaves them out."""
        by_k = [[row_at(t, arm, k) for t in task_ids] for k in range(retries + 1)]
        excl = lambda rows, f: _mean([r[f] for r in rows if r["task_id"] not in failed0])  # noqa: E731
        return {
            "n": len(task_ids), "n_excl_failed": len(task_ids) - len(failed0),
            "hidden_pass@1_by_attempt": [_mean([r["hidden_score"] for r in rows]) for rows in by_k],
            "hidden_pass@1_excl_failed_by_attempt": [excl(rows, "hidden_score") for rows in by_k],
            "public_pass@1_by_attempt": [_mean([r["public_score"] for r in rows]) for rows in by_k],
            "public_pass@1_excl_failed_by_attempt": [excl(rows, "public_score") for rows in by_k],
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
    all_tasks = {a: all_tasks_stats(all_ids, a) for a in arms}

    def groups(ids, key):
        out = defaultdict(list)
        for t in ids:
            out[key(a0_by_id[t])].append(t)
        return dict(sorted(out.items()))

    # MBPP and LiveCodeBench difficulty are different scales: always grouped by source too
    src_diff = lambda r: f"{r['source']}/{r['difficulty']}"
    ran = [r for r in a0 + list(by_key.values()) if r["calls"] and not r["carried_forward"]]
    where = lambda r: f"{r['task_id']}/{r['arm']}/{r['attempt']}"
    diagnostics = {
        "truncated": [where(r) for r in ran if r.get("stop_reason") == "max_tokens"],
        "finalized": [where(r) for r in ran if r.get("finalized")],
        "no_python_block": [where(r) for r in ran if not r["failed_run"] and r.get("n_python_blocks") == 0],
        "several_python_blocks": [where(r) for r in ran if (r.get("n_python_blocks") or 0) > 1],
        "critiques_with_code": [where(r) for r in ran if r.get("critique_has_code")],
        "tokens_per_call": {a: {"input": round(sum(r["input_tokens"] for r in g) / sum(r["calls"] for r in g)),
                                "output": round(sum(r["output_tokens"] for r in g) / sum(r["calls"] for r in g))}
                            for a in [ZERO_SHOT] + arms if (g := [r for r in ran if r["arm"] == a])},
    }
    # Cut-off sensitivity: the same numbers with and without the tasks where any answer (attempt 0 or any arm)
    # hit max_tokens. A task is dropped for every arm at once, so the arms stay paired.
    cut = lambda r: r.get("stop_reason") == "max_tokens"  # noqa: E731
    cut_ids = sorted({r["task_id"] for r in ran if cut(r)})
    clean_all, clean_paired = [t for t in all_ids if t not in cut_ids], [t for t in paired if t not in cut_ids]
    last = lambda ids, arm: _mean([row_at(t, arm, retries)["hidden_score"] for t in ids])  # noqa: E731
    sensitivity = {
        "cut_off_task_ids": cut_ids,
        "n_all_tasks": len(all_ids), "n_all_tasks_no_cut_off": len(clean_all),
        "n_paired": len(paired), "n_paired_no_cut_off": len(clean_paired),
        "zero_shot": {"answers": len([r for r in ran if r["arm"] == ZERO_SHOT]),
                      "cut_off_answers": sum(cut(r) for r in ran if r["arm"] == ZERO_SHOT),
                      "all_tasks": _mean([a0_by_id[t]["hidden_score"] for t in all_ids]),
                      "all_tasks_no_cut_off": _mean([a0_by_id[t]["hidden_score"] for t in clean_all])},
        "arms": {a: {"answers": len([r for r in ran if r["arm"] == a]),
                     "cut_off_answers": sum(cut(r) for r in ran if r["arm"] == a),
                     "all_tasks": last(all_ids, a), "all_tasks_no_cut_off": last(clean_all, a),
                     "paired": last(paired, a), "paired_no_cut_off": last(clean_paired, a)} for a in arms},
    }

    def after_cut_off(arm):
        """Retry answers whose previous attempt in this arm hit max_tokens: how many were cut off again.
        reflect_fix and critic are told the previous answer ran out of space (told_cut_off); the others aren't."""
        nxt = [r for (t, a, k), r in by_key.items() if a == arm and r["calls"] and not r["carried_forward"]
               and not r["failed_run"] and cut(row_at(t, arm, k - 1))]
        return {"answers": len(nxt), "told": sum(bool(r.get("told_cut_off")) for r in nxt),
                "cut_off_again": sum(cut(r) for r in nxt)}

    final = lambda arm: {t: int(row_at(t, arm, retries)["hidden_score"] == 1.0) for t in all_ids}  # noqa: E731
    zero = {t: int(a0_by_id[t]["hidden_score"] == 1.0) for t in all_ids}
    tests = [paired_row("feedback_vs_control", f"{a} vs control", retries, final(a), final("control"))
             for a in arms if a != "control" and "control" in arms]
    tests += [paired_row("vs_zero_shot", f"{a} vs zero-shot", retries, final(a), zero) for a in arms]
    summary = {
        "scoring_version": meta["scoring_version"], "model": meta["model"], "n_tasks": len(a0),
        "attempt_0": {
            "failed_runs": len(failed0),
            "hidden_pass@1": _mean([r["hidden_score"] for r in a0]),
            "hidden_pass@1_excl_failed": _mean([r["hidden_score"] for r in ok0]),
            "public_pass@1": _mean([r["public_score"] for r in a0]),
            "public_pass@1_excl_failed": _mean([r["public_score"] for r in ok0]),
            "false_passes": len(cells["B_false_pass"]),
            "went_into_arms": len(entered),
            "cells": {c: len(cells[c]) for c in CELLS.values()},
            "cell_ids": {c: cells[c] for c in CELLS.values()},
            **zero_shot_use,
        },
        "all_tasks": all_tasks,
        "paired_task_ids": paired,
        "incomplete_task_ids": incomplete,
        "diagnostics": diagnostics,
        "cut_off_sensitivity": sensitivity,
        "after_cut_off": {a: after_cut_off(a) for a in arms},
        "paired_tests": add_holm(tests),
        "arms": per_arm,
        "all_tasks_by_source_difficulty": {
            g: {"n": len(t), "failed_runs": sum(a0_by_id[x]["failed_run"] for x in t),
                "cells": {c: sum(not a0_by_id[x]["failed_run"] and cell_of(a0_by_id[x]) == c for x in t)
                          for c in CELLS.values()},
                "zero_shot": _mean([a0_by_id[x]["hidden_score"] for x in t]),
                **{a: _mean([row_at(x, a, retries)["hidden_score"] for x in t]) for a in arms}}
            for g, t in groups(all_ids, src_diff).items()},
        "by_source_difficulty": {g: {"n": len(t), **{a: paired_stats(t, a)["hidden_pass@1_by_attempt"] for a in arms}}
                                 for g, t in groups(paired, src_diff).items()},
        "by_attempt0_failure_type": {g: {"n": len(t), **{a: paired_stats(t, a)["hidden_pass@1_by_attempt"] for a in arms}}
                                     for g, t in groups(paired, lambda r: r["failure_type"] or "none").items()},
        "notes": "attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass "
                 "(public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping "
                 "their attempt-0 result. hidden_pass@1 and public_pass@1 count failed attempt-0 API calls as 0; "
                 "*_excl_failed leaves those tasks out. Failed retries count 0 in both. paired_tests: p_holm is "
                 "Holm-adjusted within each family. arms: only the "
                 "tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden "
                 "test pass rate went down from the arm's previous attempt. Costs are from the API's token counts "
                 "(tokens_estimated = calls whose counts were estimated).",
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def fmt(x, digits=3):
    return "-" if x is None else (f"{x:.{digits}f}" if isinstance(x, float) else str(x))


def _table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|",
            *("| " + " | ".join(fmt(x) for x in r) + " |" for r in rows)]


def _curve(xs):
    return " / ".join(fmt(x) for x in xs)


def render_report(s, meta, run_name, baselines=(), extra_tests=()):
    """The run report: the same text in the terminal and in report.md, covering all of summary.json."""
    a, c, d, n = s["attempt_0"], s["attempt_0"]["cells"], s["diagnostics"], s["n_tasks"]
    who, retries, arms = meta.get("provider", meta["model"]), meta["retries"], meta["arms"]
    planned, missing = len(meta["task_ids"]), s["incomplete_task_ids"]
    status = "finished" if n == planned and not missing else (
        f"UNFINISHED: {n} of {planned} tasks done, {len(missing)} with missing arm attempts")
    attempts = [f"a{k}" for k in range(retries + 1)]

    health = [["zero_shot", a["failed_runs"], *["-"] * retries, a["failed_runs"]]]
    health += [[arm, "-", *st["failed_runs_by_attempt"], st["failed_runs"]] for arm, st in s["arms"].items()]

    main = [[f"{who} zero-shot (attempt 0)", n, a["hidden_pass@1"], a["hidden_pass@1_excl_failed"], a["public_pass@1"],
             a["false_passes"], a["failed_runs"], a["calls"], a["cost_usd"]]]
    for arm, st in s["all_tasks"].items():
        main.append([f"{who} + {arm} (attempt {retries})", st["n"], st["hidden_pass@1_by_attempt"][-1],
                     st["hidden_pass@1_excl_failed_by_attempt"][-1], st["public_pass@1_by_attempt"][-1],
                     st["false_passes_by_attempt"][-1], a["failed_runs"] + s["arms"][arm]["failed_runs"],
                     st["calls"], st["cost_usd"]])
    for name, run in baselines:
        bs = run["summary"]
        main.append([f"{run['provider']} zero-shot ({name})", bs["overall"]["n"], bs["overall"]["pass@1"],
                     bs["excluding_failed_runs"]["pass@1"], bs.get("public_pass@1"), bs.get("false_passes"),
                     bs.get("failed_runs", 0), bs.get("calls"), bs.get("cost_usd")])

    arm_rows = [[arm, _curve(st["hidden_pass@1_by_attempt"]), (st.get("gain_over_control_by_attempt") or [None])[-1],
                 f"{st['repairs']}/{st['n_D_repair_targets']}", f"{st['breaks']}/{st['n_C_hidden_only_pass']}",
                 st["false_fixes"], st["regressions"], st["failed_runs"], st["calls"],
                 st["input_tokens"] + st["output_tokens"], st["cost_usd"], fmt(st["cost_per_repair_usd"], 4),
                 st["calls_per_repair"]] for arm, st in s["arms"].items()]
    tests = s["paired_tests"] + list(extra_tests)

    lines = [f"# Results: {run_name}", "",
             f"Model {meta['model']}, temperature {meta.get('temperature')}, max_tokens {meta.get('max_tokens')}, "
             f"task list {meta.get('ids_file')} ({n} tasks), split {meta.get('split')}, scoring_version "
             f"{s['scoring_version']}. Status: {status}.",
             "Pass@1 is on the hidden tests unless marked public. Failed attempt-0 API calls count 0; "
             "\"excl. failed\" leaves those tasks out. Failed retries count 0 in both.", "",
             "## Run health", "Failed API calls per attempt:", *_table(["arm", *attempts, "total"], health), "",
             f"Truncated answers: {len(d['truncated'])} {d['truncated'] or ''}",
             f"Finalized answers (cut off, then a follow-up call gave the final code): "
             f"{len(d.get('finalized', []))} {d.get('finalized') or ''}",
             f"No code block: {len(d['no_python_block'])} {d['no_python_block'] or ''}",
             f"Several code blocks: {len(d['several_python_blocks'])} {d['several_python_blocks'] or ''}",
             f"Critiques containing code: {len(d['critiques_with_code'])} {d['critiques_with_code'] or ''}",
             f"Tasks with missing arm attempts: {len(missing)} {missing or ''}",
             f"Calls with estimated tokens at attempt 0: {a['tokens_estimated']}",
             f"Tokens per call: {d['tokens_per_call']}", "",
             "## Main results (all tasks)",
             *_table(["arm", "n", "hidden pass@1", "hidden pass@1 (excl. failed)", "public pass@1", "false passes",
                      "failed API calls", "calls", "cost $"], main), "",
             "## All tasks by attempt (A and B keep attempt 0)",
             *_table(["arm", "hidden pass@1, " + "-".join(attempts), "excl. failed", "public pass@1"],
                     [[arm, _curve(st["hidden_pass@1_by_attempt"]), _curve(st["hidden_pass@1_excl_failed_by_attempt"]),
                       _curve(st["public_pass@1_by_attempt"])] for arm, st in s["all_tasks"].items()]), "",
             "## Attempt 0 cells",
             *_table(["A true pass", "B false pass", "C hidden-only pass", "D true fail", "failed runs", "went into the arms"],
                     [[c["A_true_pass"], c["B_false_pass"], c["C_hidden_only_pass"], c["D_true_fail"],
                       a["failed_runs"], a["went_into_arms"]]]), "",
             "B tasks pass the public tests, so no arm retries them: they cap every arm equally. "
             "C and D go into the arms; repairs are counted over D, breaks over C.", "",
             f"## Self-correction (the {len(s['paired_task_ids'])} tasks that went into the arms, C + D)",
             *_table(["arm", "hidden pass@1, " + "-".join(attempts), "gain vs control (last)", "repairs (of D)",
                      "breaks (of C)", "false fixes", "regressions", "failed API calls", "calls", "tokens", "cost $",
                      "$ per repair", "calls per repair"], arm_rows), "",
             "## By source and difficulty (all tasks, last attempt)",
             *_table(["group", "n", "A", "B", "C", "D", "failed", "zero-shot", *arms],
                     [[g, x["n"], *x["cells"].values(), x["failed_runs"], x["zero_shot"], *[x[arm] for arm in arms]]
                      for g, x in s["all_tasks_by_source_difficulty"].items()]), ""]
    for title, key in (("Self-correction by source and difficulty (C + D)", "by_source_difficulty"),
                       ("Self-correction by attempt-0 failure type (C + D)", "by_attempt0_failure_type")):
        lines += [f"## {title}", *_table(["group", "n", *arms], [[g, x["n"], *[_curve(x[arm]) for arm in arms]]
                                                                for g, x in s[key].items()]), ""]
    cs = s["cut_off_sensitivity"]
    lines += [f"## Cut-off sensitivity (hidden pass@1 at attempt {retries})",
              f"Tasks where any answer hit max_tokens: {len(cs['cut_off_task_ids'])} of {cs['n_all_tasks']} "
              f"{cs['cut_off_task_ids'] or ''}. The right-hand columns leave those tasks out for every arm. If the "
              "arms compare the same way with and without them, the token limit doesn't change the conclusion. "
              "With 0 tasks left in a column, this run can't tell.",
              *_table(["arm", "cut-off answers", f"all tasks (n={cs['n_all_tasks']})",
                       f"without cut-off tasks (n={cs['n_all_tasks_no_cut_off']})", f"C + D (n={cs['n_paired']})",
                       f"C + D without cut-off tasks (n={cs['n_paired_no_cut_off']})"],
                      [[name, f"{x['cut_off_answers']}/{x['answers']}", x["all_tasks"], x["all_tasks_no_cut_off"],
                        x.get("paired"), x.get("paired_no_cut_off")]
                       for name, x in [("zero-shot", cs["zero_shot"]), *cs["arms"].items()]]), ""]
    lines += ["## Does telling the model it ran out of space help?",
              "Retry answers whose previous attempt in the same arm hit max_tokens. reflect_fix and critic are told "
              "so in the test feedback; control and bare_retry never are. Fewer answers cut off again in the told "
              "arms would mean the note helps.",
              *_table(["arm", "answers after a cut-off answer", "told", "cut off again"],
                      [[arm, x["answers"], x["told"], x["cut_off_again"]] for arm, x in s["after_cut_off"].items()]), ""]
    lines += ["## Paired tests (exact McNemar, hidden pass/fail per task)",
              f"p (Holm) is corrected within each family. Significant: p (Holm) below {ALPHA}. The feedback_vs_control "
              "family answers whether feedback beats a fresh resample.",
              *_table(["family", "comparison", "only first passes", "only second passes", "p", "p (Holm)", "verdict"],
                      [[r["family"], r["comparison"], r["only_first_passes"], r["only_second_passes"],
                        fmt(r["p_exact_mcnemar"]), fmt(r["p_holm"]),
                        "significant" if r["significant"] else "not significant"] for r in tests]), "",
              "## Task ids", *[f"- {name}: {' '.join(ids) or '-'}" for name, ids in a["cell_ids"].items()],
              f"- C + D, every arm finished: {' '.join(s['paired_task_ids']) or '-'}", "",
              "## Notes", s["notes"]]
    return "\n".join(lines)


def write_report(run_dir):
    """Rebuilds summary.json and report.md, and prints the report."""
    meta = json.loads((run_dir / "run_meta.json").read_text())
    text = render_report(summarize_run(run_dir), meta, run_dir.name)
    (run_dir / "report.md").write_text(text + "\n")
    print(text)


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
    ap = argparse.ArgumentParser(description="The run report (+ Panacea).")
    ap.add_argument("run_dir", help="a loop run folder, e.g. data/results/2026-11-03_claude_pilot")
    ap.add_argument("baseline_runs", nargs="*", help="baseline.py run files to add (e.g. panacea_run.json)")
    ap.add_argument("--out", help="default <run_dir>/report.md")
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

    out = loop_outcomes(run_dir, meta)
    extra = []
    for name, run in baselines:
        theirs, p = {r["id"]: int(r["score"] == 1.0) for r in run["results"]}, run["provider"]
        extra.append(paired_row(p, f"{p} vs zero-shot", 0, theirs, out["zero_shot"]))
        extra += [paired_row(p, f"{p} vs {arm}", meta["retries"], theirs, out[arm]) for arm in meta["arms"]]
    text = render_report(s, meta, run_dir.name, baselines, add_holm(extra))
    print(text)
    out_path = Path(args.out) if args.out else run_dir / "report.md"
    out_path.write_text(text + "\n")
    print(f"\nSaved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
