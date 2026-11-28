"""
presentation.py

Presentation pack for the final results: slide-sized charts and small tables, each tied to the research
question it answers. Every number comes from Optimizer/results.py's tables (no new metric is defined here).
It also combines the main run's repeats (same attempt 0, retries repeated with --attempt0-from; README
"Repeats"): each arm is reported as the mean and the min-max range across repeats, never one run's ranking.

Research questions (one slide each):
  RQ1   Does evaluator feedback help Claude fix its own code, beyond simply asking again (the control)?
  RQ2   At what cost? Accuracy against API spend, and $ per repaired task.
  RQ3   How does Panacea's coding agent compare with Claude zero-shot on the same tasks?
  RQ4   Where do the models fail? Failure types and difficulty, at attempt 0.
  Side  Does telling the model it ran out of space help?

Usage (from the repo root):
    python Optimizer/presentation.py --index
        runs index only: every run in data/results, its settings and cost, and whether it is reportable
    python Optimizer/presentation.py data/results/<main run> [data/results/<repeat> ...] [--panacea panacea_run.json]
        [--out data/results/presentation/<name>] [--theme light|dark]

Writes to --out (default data/results/presentation/<main run name>/):
    slides.md               one section per slide: the question, its chart, a key-numbers table, what the
                            numbers show in plain words, and the CSV behind them
    charts/*.png            16:9 charts sized for slides
    tables/*.csv            headline (+ per repeat), curves, cells, failure types, difficulty, cut-off
    runs_index.md / .csv    also written to data/results/runs_index.md / .csv
Runs that are dev, synthetic, unfinished or on an old scoring version get a NOT A RESULT banner.
"""

import argparse
import json
import math
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Evaluator.evaluator import SCORING_VERSION  # noqa: E402
from Optimizer import charts as C  # noqa: E402
from Optimizer.report import ZERO_SHOT  # noqa: E402
from Optimizer.results import PANACEA, build  # noqa: E402

RESULTS_DIR = REPO_ROOT / "data" / "results"
ARMS = ["control", "bare_retry", "reflect_fix", "critic"]
FEEDBACK = ["bare_retry", "reflect_fix", "critic"]
LABELS = {ZERO_SHOT: "Claude zero-shot", "control": "Ask again (control)", "bare_retry": "Bare retry",
          "reflect_fix": "Reflect & fix", "critic": "Critic + fix", PANACEA: "Panacea agent"}
CELL_COLS = ["A_true_pass", "B_false_pass", "C_hidden_only_pass", "D_true_fail", "failed"]
CELL_LABELS = ["A true pass", "B false pass", "C hidden-only pass", "D true fail", "API failed"]
W, H, DPI = 10, 5.625, 200  # 16:9


def label(s):
    return LABELS.get(s, s)


def _nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


# =====================================================================
# RUNS INDEX
# =====================================================================

def not_reportable_reasons(meta, finished):
    why = []
    if meta.get("synthetic"):
        why.append("synthetic test data")
    if meta.get("split") != "test":
        why.append(f"{meta.get('split') or 'no'} split (only test runs are results)")
    if meta.get("scoring_version") != SCORING_VERSION:
        why.append(f"scoring v{meta.get('scoring_version')} (current v{SCORING_VERSION})")
    if not finished:
        why.append("unfinished")
    return why


def run_index(results_dir=RESULTS_DIR):
    rows = []
    for d in sorted(p for p in Path(results_dir).iterdir() if (p / "run_meta.json").exists()):
        meta = json.loads((d / "run_meta.json").read_text())
        summ = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
        cost = calls = 0.0
        for f in sorted(d.glob("attempt_*.jsonl")):
            for line in f.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    cost += r.get("cost_usd") or 0
                    calls += r.get("calls") or 0
        finished = bool(meta.get("finished")) or (bool(summ) and not summ.get("incomplete_task_ids"))
        why = not_reportable_reasons(meta, finished)
        rows.append({
            "run": d.name, "started": (meta.get("started") or "")[:10], "split": meta.get("split"),
            "model": meta.get("model"), "tasks": len(meta.get("task_ids", [])),
            "task_list": meta.get("ids_file"), "scoring_version": meta.get("scoring_version"),
            "attempt0_from": meta.get("attempt0_from"), "calls": int(calls), "cost_usd": round(cost, 4),
            "zero_shot_hidden_pass@1": summ.get("attempt_0", {}).get("hidden_pass@1"),
            "finished": finished, "reportable": not why, "why_not": "; ".join(why),
        })
    return pd.DataFrame(rows)


def md_table(df, floats=3):
    def f(v):
        if isinstance(v, float):
            return "-" if math.isnan(v) else f"{v:.{floats}f}"
        return "-" if v is None else str(v)
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(f(v) for v in r) + " |\n" for r in df.itertuples(index=False))


def write_index(out_dirs):
    idx = run_index()
    text = (f"# Runs index\n\nEvery run in `data/results/`. Current scoring version: {SCORING_VERSION}. "
            f"Only finished `test` runs on the current scoring version are results; everything else checks the "
            f"plumbing or the cost.\n\nTotal spent across these runs: ${idx['cost_usd'].sum():.2f}\n\n"
            + md_table(idx))
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)
        idx.to_csv(d / "runs_index.csv", index=False)
        (d / "runs_index.md").write_text(text)
    return idx


# =====================================================================
# COMBINING REPEATS
# =====================================================================

def load_repeats(run_dirs, panacea):
    reps, metas = [], []
    for rd in run_dirs:
        t, m = build(rd, panacea, write=False)
        summ = Path(rd) / "summary.json"
        m = {**m, "_name": Path(rd).name, "_summary": json.loads(summ.read_text()) if summ.exists() else {}}
        reps.append(t)
        metas.append(m)
    first = metas[0]
    for m in metas[1:]:
        for k in ("model", "temperature", "max_tokens", "scoring_version", "arms", "retries", "split"):
            if m.get(k) != first.get(k):
                sys.exit(f"{m['_name']}: {k} is {m.get(k)!r}, {first['_name']} has {first.get(k)!r}. "
                         f"Repeats must share every setting.")
        if set(m["task_ids"]) != set(first["task_ids"]):
            sys.exit(f"{m['_name']} covers different tasks than {first['_name']}.")
    notes = [f"{m['_name']} did not reuse {first['_name']}'s attempt 0 (--attempt0-from), so zero-shot numbers "
             f"also vary between repeats." for m in metas[1:] if m.get("attempt0_from") != first["_name"]]
    return reps, metas, notes


def headline_one(t, last):
    main, curves, pt = t["main"], t["curves"], t["paired_tests"]
    ao = t["arm_outcomes"].set_index("arm")
    present = set(main["system"])
    systems = [(ZERO_SHOT, 0)] + [(a, last) for a in ARMS if a in present] + \
              ([(PANACEA, 0)] if PANACEA in present else [])
    rows = []
    for s, att in systems:
        r = main[(main["system"] == s) & (main["attempt"] == att)]
        if r.empty:
            continue
        r = r.iloc[0]
        row = {"system": s, "attempt": att, "n": r["n"], "hidden_pass@1": r["hidden_pass@1"],
               "public_pass@1": r["public_pass@1"], "false_passes": r["false_passes"],
               "failed_runs": r["failed_runs"], "pipeline_calls": r["cumulative_calls"],
               "pipeline_cost_usd": r["cumulative_cost_usd"]}
        if s in ARMS:
            for scope in ("all", "paired"):
                c = curves[(curves["scope"] == scope) & (curves["arm"] == s) & (curves["attempt"] == last)]
                row[f"gain_vs_control_{scope}"] = c["gain_vs_control"].iloc[0] if len(c) else float("nan")
                if scope == "paired":
                    row["paired_hidden_pass@1"] = c["hidden_pass@1"].iloc[0] if len(c) else float("nan")
            if s in ao.index:
                o = ao.loc[s]
                for k in ("n_paired", "n_D", "n_C", "repairs", "breaks", "false_fixes", "cost_usd",
                          "cost_per_repair_usd", "calls_per_repair"):
                    row["retry_cost_usd" if k == "cost_usd" else k] = o.get(k)
            if s in FEEDBACK:
                p = pt[(pt["family"] == "feedback_vs_control") & (pt["comparison"] == f"{s} vs control")]
                row["significant_vs_control"] = float(bool(p["significant"].iloc[0])) if len(p) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate(frames, keys):
    """mean / min / max across repeats of every numeric column, grouped by keys."""
    df = pd.concat([f.assign(repeat=i + 1) for i, f in enumerate(frames)], ignore_index=True)
    num = [c for c in df.columns if c not in keys + ["repeat"]]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    num = [c for c in num if df[c].notna().any()]
    g = df.groupby(keys, sort=False)[num]
    out = g.mean().add_suffix("_mean").join(g.min().add_suffix("_min")).join(g.max().add_suffix("_max"))
    if "significant_vs_control" in num:
        out["significant_repeats"] = df.groupby(keys, sort=False)["significant_vs_control"].sum(min_count=1)
    return out.reset_index(), df


def build_tables(reps, metas):
    last = metas[0]["retries"]
    head, head_long = aggregate([headline_one(t, last) for t in reps], ["system"])
    cur, _ = aggregate([t["curves"][["scope", "arm", "attempt", "hidden_pass@1"]] for t in reps],
                       ["scope", "arm", "attempt"])
    cells, _ = aggregate([t["cells"][["system"] + CELL_COLS] for t in reps], ["system"])

    def at_reported_attempt(df):
        return df[((df["system"].isin([ZERO_SHOT, PANACEA])) & (df["attempt"] == 0)) |
                  ((df["system"].isin(ARMS)) & (df["attempt"] == last))]

    ft = []
    for t in reps:
        f = at_reported_attempt(t["failure_types"]).drop(columns="attempt")
        ft.append(f.melt(id_vars="system", var_name="failure_type", value_name="tasks").fillna({"tasks": 0}))
    fail, _ = aggregate(ft, ["system", "failure_type"])
    bg = []
    for t in reps:
        b = t["by_group"]
        b = at_reported_attempt(b[(b["grouping"] == "source_difficulty") & (b["scope"] == "all")])
        bg.append(b[["group", "system", "n", "hidden_pass@1"]])
    diff, _ = aggregate(bg, ["group", "system"])
    co = []
    for m in metas:
        for arm, v in (m["_summary"].get("after_cut_off") or {}).items():
            co.append({"arm": arm, **v})
    cut = pd.DataFrame(co).groupby("arm", sort=False).sum(numeric_only=True).reset_index() if co else pd.DataFrame()
    return {"headline": head, "headline_by_repeat": head_long, "curves": cur, "cells": cells,
            "failure_types": fail, "by_difficulty": diff, "cut_off_note": cut}


# =====================================================================
# CHARTS (16:9, slide sized; palette from Optimizer/charts.py)
# =====================================================================

def _fig(ncols=1):
    fig, axes = plt.subplots(1, ncols, figsize=(W, H), squeeze=False)
    fig.patch.set_facecolor(C.T["surface"])
    return fig, axes[0]


def _style(ax, pct=True, axis="y"):
    ax.set_facecolor(C.T["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(C.T["axis"])
    ax.tick_params(colors=C.T["ink2"], labelsize=10, length=0)
    ax.grid(axis=axis, color=C.T["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    if pct:
        (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(PercentFormatter(1.0, decimals=0))


def _title(fig, title, sub, banner):
    fig.text(0.02, 0.965, title, fontsize=17, fontweight="bold", color=C.T["ink"], va="top")
    fig.text(0.02, 0.9, textwrap.fill(sub, 135), fontsize=10, color=C.T["ink2"], va="top", linespacing=1.4)
    if banner:
        fig.text(0.98, 0.965, banner, fontsize=10, color="#c0392b", fontweight="bold", ha="right", va="top")


def _save(fig, out, name):
    fig.savefig(out / f"{name}.png", dpi=DPI, facecolor=C.T["surface"])
    plt.close(fig)
    return f"charts/{name}.png"


def _reps(R, what="line = mean", spread="band = min-max"):
    return "One run (no repeats yet)." if R == 1 else f"{what.capitalize()} of {R} repeats; {spread} across repeats."


def _rng(row, col):
    m, lo, hi = row.get(f"{col}_mean"), row.get(f"{col}_min"), row.get(f"{col}_max")
    return m, lo, hi


def chart_gain(tb, R, banner, out):
    h = tb["headline"].set_index("system")
    arms = [a for a in FEEDBACK if a in h.index]
    fig, (ax,) = _fig()
    n = h.loc["control", "n_paired_mean"] if "n_paired_mean" in h.columns and "control" in h.index else 0
    _title(fig, "RQ1  Does feedback beat simply asking again?",
           f"Hidden-test pass rate gain over the control at the last retry, on the {n:.0f} tasks that went into the "
           f"retry arms (failed at attempt 0). " + _reps(R, "bar = mean", "line = min-max"), banner)
    fig.subplots_adjust(left=0.17, right=0.80, top=0.80, bottom=0.12)
    _style(ax, axis="x")
    if not n or _nan(n):
        ax.text(0.5, 0.5, "No task failed at attempt 0, so no arm had anything to fix.", ha="center",
                transform=ax.transAxes, fontsize=12, color=C.T["ink2"])
        ax.set_yticks([])
        return _save(fig, out, "rq1_gain_vs_control")
    for i, a in enumerate(arms):
        m, lo, hi = _rng(h.loc[a], "gain_vs_control_paired")
        ax.barh(i, m, color=C._color(a), height=0.55)
        if R > 1:
            ax.plot([lo, hi], [i, i], color=C.T["ink"], lw=1.6)
        sig = h.loc[a].get("significant_repeats", float("nan"))
        txt = f"{m * 100:+.0f} pts" + (f"  ({lo * 100:+.0f} to {hi * 100:+.0f})" if R > 1 else "")
        txt += "" if _nan(sig) else f"\nsignificant in {sig:.0f}/{R}"
        ax.annotate(txt, (max(hi if R > 1 else m, 0), i), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=10.5, color=C.T["ink2"], annotation_clip=False)
    ax.axvline(0, color=C.T["ink"], lw=1)
    ax.set_yticks(range(len(arms)), [label(a) for a in arms], fontsize=12)
    ax.invert_yaxis()
    lim = max(0.1, *(abs(v) for a in arms for v in _rng(h.loc[a], "gain_vs_control_paired") if not _nan(v)))
    ax.set_xlim(-lim * 1.15, lim * 1.15)
    ax.set_xlabel("gain over control (percentage points; 0 = no better than asking again)", color=C.T["ink2"])
    return _save(fig, out, "rq1_gain_vs_control")


def chart_curves(tb, R, banner, out, last):
    cur = tb["curves"]
    h = tb["headline"].set_index("system")
    fig, axes = _fig(2)
    _title(fig, "RQ1  Pass rate after each retry",
           "Hidden-test pass@1 by attempt (a0 = Claude zero-shot, shared). " + _reps(R), banner)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.78, bottom=0.17, wspace=0.18)
    for ax, scope, name in ((axes[0], "all", "All tasks"), (axes[1], "paired", "Tasks that failed at a0 (C + D)")):
        _style(ax)
        d = cur[cur["scope"] == scope]
        for a in ARMS:
            x = d[d["arm"] == a].sort_values("attempt")
            if x.empty:
                continue
            ax.plot(x["attempt"], x["hidden_pass@1_mean"], color=C._color(a), lw=2.4,
                    marker=C.MARKERS.get(a, "o"), ms=7, label=label(a), markeredgecolor=C.T["surface"])
            if R > 1:
                ax.fill_between(x["attempt"], x["hidden_pass@1_min"], x["hidden_pass@1_max"],
                                color=C._color(a), alpha=0.12, lw=0)
        if scope == "all" and PANACEA in h.index:
            y = h.loc[PANACEA, "hidden_pass@1_mean"]
            ax.axhline(y, color=C._color(PANACEA), ls=(0, (4, 3)), lw=1.4)
            ax.text(last, y, f" Panacea {y:.0%}", va="bottom", ha="right", fontsize=9.5, color=C.T["ink2"])
        ax.set_xticks(range(last + 1), ["a0"] + [f"retry {k}" for k in range(1, last + 1)])
        ax.set_ylim(-0.03, 1.05)
        ax.set_title(name, loc="left", fontsize=12, color=C.T["ink"])
    hs, ls = axes[0].get_legend_handles_labels()
    fig.legend(hs, ls, loc="lower center", ncol=len(ls), frameon=False, fontsize=10.5, labelcolor=C.T["ink2"])
    return _save(fig, out, "rq1_accuracy_by_attempt")


def chart_cost(tb, R, banner, out):
    h = tb["headline"]
    fig, (ax,) = _fig()
    _title(fig, "RQ2  What does the accuracy cost?",
           f"Hidden-test pass@1 on all tasks vs total API spend for the pipeline (attempt 0 + that arm's retries). "
           + _reps(R, "points = mean", "bars = min-max"), banner)
    fig.subplots_adjust(left=0.09, right=0.72, top=0.80, bottom=0.12)
    _style(ax)
    ax.grid(axis="x", color=C.T["grid"], linewidth=0.7)
    labels = []
    for _, r in h.iterrows():
        s = r["system"]
        x, xl, xh = _rng(r, "pipeline_cost_usd")
        y, yl, yh = _rng(r, "hidden_pass@1")
        if _nan(x):
            continue
        ax.errorbar(x, y, xerr=[[max(0, x - xl)], [max(0, xh - x)]] if R > 1 else None,
                    yerr=[[max(0, y - yl)], [max(0, yh - y)]] if R > 1 else None,
                    fmt=C.MARKERS.get(s, "o"), color=C._color(s), ms=11, capsize=3, lw=1.2,
                    markeredgecolor=C.T["surface"])
        extra = "" if _nan(r.get("cost_per_repair_usd_mean")) else f", ${r['cost_per_repair_usd_mean']:.3f}/repair"
        labels.append((x, y, f"{label(s)}  {y:.0%}{extra}"))
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ylo, yhi = ax.get_ylim()
    gap, placed = (yhi - ylo) * 0.055, []
    for x, y, txt in sorted(labels, key=lambda v: v[1]):
        yy = y if not placed or y - placed[-1] >= gap else placed[-1] + gap
        placed.append(yy)
        ax.annotate(txt, (x, y), xytext=(x, yy), textcoords="data", va="center", fontsize=10, color=C.T["ink2"],
                    annotation_clip=False, xycoords="data",
                    arrowprops=None if abs(yy - y) < 1e-9 else dict(arrowstyle="-", color=C.T["axis"], lw=0.6))
        ax.texts[-1].set_position((x + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.035, yy))
    ax.set_xlabel("API cost of the whole pipeline (USD)", color=C.T["ink2"])
    ax.set_ylabel("hidden pass@1", color=C.T["ink2"])
    return _save(fig, out, "rq2_accuracy_vs_cost")


def chart_panacea(tb, banner, out):
    h = tb["headline"].set_index("system")
    cells = tb["cells"].set_index("system")
    if PANACEA not in h.index:
        return None
    fig, axes = _fig(2)
    _title(fig, "RQ3  Panacea vs Claude zero-shot",
           "Same tasks, same scoring. Hidden tests are never shown to either system; public tests are the "
           "examples in the prompt.", banner)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.78, bottom=0.17, wspace=0.35)
    ax = axes[0]
    _style(ax)
    systems = [ZERO_SHOT, PANACEA]
    for j, (col, nm, alpha) in enumerate((("public_pass@1", "public tests", 0.45), ("hidden_pass@1", "hidden tests", 1))):
        vals = [h.loc[s, f"{col}_mean"] for s in systems]
        bars = ax.bar([i + (j - 0.5) * 0.36 for i in range(2)], vals, width=0.34, alpha=alpha,
                      color=[C._color("bare_retry")] * 2, label=nm)
        ax.bar_label(bars, labels=[f"{v:.0%}" for v in vals], fontsize=10.5, color=C.T["ink2"], padding=2)
    ax.set_xticks(range(2), [label(s) for s in systems], fontsize=11.5)
    ax.set_ylim(0, 1.12)
    ax.legend(frameon=False, fontsize=10, labelcolor=C.T["ink2"], loc="upper right")
    ax.set_title("pass@1", loc="left", fontsize=12, color=C.T["ink"])
    ax = axes[1]
    _style(ax, pct=False, axis="x")
    names = {"claude": ZERO_SHOT, PANACEA: PANACEA}
    colors = [C.T["arms"]["critic"], C.T["arms"]["reflect_fix"], C.T["arms"]["bare_retry"], C.T["arms"]["control"],
              C.T["grid"]]
    rows = [s for s in ("claude", PANACEA) if s in cells.index]
    for i, s in enumerate(rows):
        left = 0
        for col, colr, nm in zip(CELL_COLS, colors, CELL_LABELS):
            v = cells.loc[s, f"{col}_mean"]
            if v:
                ax.barh(i, v, left=left, color=colr, height=0.55)
                ax.text(left + v / 2, i, f"{v:.0f}", ha="center", va="center", fontsize=10,
                        color="#ffffff" if col != "failed" else C.T["ink2"])
            left += v
    ax.set_yticks(range(len(rows)), [label(names[s]) for s in rows], fontsize=11.5)
    ax.invert_yaxis()
    ax.set_xlabel("tasks", color=C.T["ink2"])
    ax.set_title("Where each task lands (public / hidden)", loc="left", fontsize=12, color=C.T["ink"])
    fig.legend(handles=[Patch(color=c, label=n) for c, n in zip(colors, CELL_LABELS)], frameon=False, fontsize=9.5,
               ncol=5, loc="lower center", labelcolor=C.T["ink2"])
    return _save(fig, out, "rq3_panacea_vs_claude")


def chart_failures(tb, banner, out):
    f = tb["failure_types"]
    d = tb["by_difficulty"]
    systems = [s for s in (ZERO_SHOT, PANACEA) if s in set(f["system"])]
    fig, axes = _fig(2)
    _title(fig, "RQ4  Where do the models fail? (attempt 0, no retries)",
           "Left: how each task ended on the hidden tests. Right: pass@1 by source and difficulty "
           "(MBPP and LiveCodeBench difficulty are different scales).", banner)
    fig.subplots_adjust(left=0.15, right=0.98, top=0.78, bottom=0.22, wspace=0.3)
    ax = axes[0]
    _style(ax, pct=False, axis="x")
    types = [t for t in f.groupby("failure_type")["tasks_mean"].sum().sort_values(ascending=False).index
             if f[f["failure_type"] == t]["tasks_mean"].sum() > 0]
    palette = {"passed": C.T["arms"]["critic"], "wrong_answer": C.T["arms"]["reflect_fix"],
               "timeout": C.T["arms"]["bare_retry"]}
    greys = ["#52514e", "#898781", "#b5b3ab", "#d6d5cf", "#e8e7e2"]
    for i, s in enumerate(systems):
        left, gi = 0, 0
        for t in types:
            v = f[(f["system"] == s) & (f["failure_type"] == t)]["tasks_mean"].sum()
            colr = palette.get(t)
            if colr is None:
                colr, gi = greys[gi % len(greys)], gi + 1
            if v:
                ax.barh(i, v, left=left, color=colr, height=0.55, label=t.replace("_", " ") if i == 0 else None)
            left += v
    ax.set_yticks(range(len(systems)), [label(s).replace(" ", "\n", 1) for s in systems], fontsize=11)
    ax.invert_yaxis()
    ax.set_xlabel("tasks", color=C.T["ink2"])
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.16),
              labelcolor=C.T["ink2"])
    ax = axes[1]
    _style(ax)
    groups = list(dict.fromkeys(d["group"]))
    wbar = 0.8 / max(1, len(systems))
    for j, s in enumerate(systems):
        vals = [d[(d["group"] == g) & (d["system"] == s)]["hidden_pass@1_mean"].sum() for g in groups]
        ax.bar([i + (j - (len(systems) - 1) / 2) * wbar for i in range(len(groups))], vals, width=wbar * 0.95,
               color=C._color(s) if s != ZERO_SHOT else C.T["arms"]["bare_retry"], label=label(s))
    ns = [int(d[d["group"] == g]["n_mean"].iloc[0]) for g in groups]
    short = [g.replace("livecodebench", "LCB").replace("mbpp", "MBPP").replace("/", " ") for g in groups]
    ax.set_xticks(range(len(groups)), [f"{g}\n(n={n})" for g, n in zip([x.replace(" ", "\n") for x in short], ns)], fontsize=9.5)
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=C.T["ink2"])
    return _save(fig, out, "rq4_where_models_fail")


# =====================================================================
# SLIDES.MD
# =====================================================================

def fmt(r, col, pct=False, pts=False, money=False, R=1):
    m, lo, hi = _rng(r, col)
    if _nan(m):
        return "-"
    f = (lambda v: f"{v * 100:+.0f} pts") if pts else (lambda v: f"{v:.0%}") if pct else \
        (lambda v: f"${v:.3f}") if money else (lambda v: f"{v:.1f}" if v != int(v) else f"{v:.0f}")
    return f(m) if R == 1 or lo == hi else f"{f(m)} ({f(lo)} to {f(hi)})"


def write_slides(tb, metas, notes, R, banner, charts, out, panacea):
    m0 = metas[0]
    h = tb["headline"].set_index("system")
    lines = [f"# Results slides: {m0['_name']}" + (f" + {R - 1} repeat(s)" if R > 1 else ""), ""]
    if banner:
        lines += [f"> **{banner}.** These numbers check the pipeline; do not present them as findings.", ""]
    lines += [f"- Runs: {', '.join(m['_name'] for m in metas)}",
              f"- Model {m0['model']}, temperature {m0['temperature']}, max_tokens {m0['max_tokens']}, "
              f"{len(m0['task_ids'])} tasks, {m0['retries']} retries, scoring v{m0['scoring_version']}",
              f"- Panacea: {Path(panacea).name if panacea else 'not included'}",
              "- Ranges are min to max across repeats. Pass@1 is on the hidden tests unless it says public."]
    lines += [f"- Note: {n}" for n in notes] + [""]

    # RQ1
    n = h.loc["control"].get("n_paired_mean", 0) if "control" in h.index else 0
    lines += ["## Slide: RQ1. Does feedback help Claude fix its own code?", "",
              "Question: when Claude's first answer fails, does showing it test feedback fix more tasks than just "
              "asking again (the control)?", "",
              f"Chart: `{charts['gain']}` (backup: `{charts['curves']}`)", ""]
    t = pd.DataFrame([{"arm": label(a), "pass@1 on retried tasks": fmt(h.loc[a], "paired_hidden_pass@1", pct=True, R=R),
                       "gain vs control": fmt(h.loc[a], "gain_vs_control_paired", pts=True, R=R),
                       "repairs": fmt(h.loc[a], "repairs", R=R), "breaks": fmt(h.loc[a], "breaks", R=R),
                       "significant": "-" if a == "control" else f"{h.loc[a].get('significant_repeats', 0):.0f}/{R}"}
                      for a in ARMS if a in h.index])
    lines += [md_table(t), "What the numbers show:", ""]
    if not n or _nan(n):
        lines += ["- No task failed at attempt 0, so the retry arms had nothing to fix in this run.", ""]
    else:
        lines += [f"- {n:.0f} task(s) failed at attempt 0 and went into the arms; each task is worth about {100 / n:.0f} points."]
        for a in FEEDBACK:
            if a in h.index:
                r = h.loc[a]
                lines.append(f"- {label(a)}: {fmt(r, 'gain_vs_control_paired', pts=True, R=R)} vs the control; "
                             f"significant (McNemar, Holm p < 0.05) in {r.get('significant_repeats', 0):.0f} of {R} repeat(s).")
        lines += ["- \"Not significant\" means this run can't tell the arms apart, not that they are equal.", ""]
    lines += ["Source: `tables/headline.csv` (gain_vs_control_paired, repairs, breaks, significant_repeats), "
              "`tables/curves.csv`", ""]

    # RQ2
    lines += ["## Slide: RQ2. At what cost?", "", f"Chart: `{charts['cost']}`", ""]
    t = pd.DataFrame([{"system": label(s), "pass@1 (all tasks)": fmt(h.loc[s], "hidden_pass@1", pct=True, R=R),
                       "pipeline cost": fmt(h.loc[s], "pipeline_cost_usd", money=True, R=R),
                       "calls": fmt(h.loc[s], "pipeline_calls", R=R),
                       "$ per repair": fmt(h.loc[s], "cost_per_repair_usd", money=True, R=R) if s in ARMS else "-"}
                      for s in h.index])
    lines += [md_table(t), "Source: `tables/headline.csv` (pipeline_cost_usd, cost_per_repair_usd)", ""]

    # RQ3
    lines += ["## Slide: RQ3. Panacea vs Claude zero-shot", ""]
    if PANACEA in h.index:
        cells = tb["cells"].set_index("system")
        lines += [f"Chart: `{charts['panacea']}`", ""]
        rows = []
        for s, cs in ((ZERO_SHOT, "claude"), (PANACEA, PANACEA)):
            row = {"system": label(s), "hidden pass@1": fmt(h.loc[s], "hidden_pass@1", pct=True, R=R),
                   "public pass@1": fmt(h.loc[s], "public_pass@1", pct=True, R=R),
                   "false passes": fmt(h.loc[s], "false_passes", R=R),
                   "cost": fmt(h.loc[s], "pipeline_cost_usd", money=True, R=R)}
            for c, nm in zip(CELL_COLS, CELL_LABELS):
                row[nm] = fmt(cells.loc[cs], c, R=R) if cs in cells.index else "-"
            rows.append(row)
        lines += [md_table(pd.DataFrame(rows)),
                  "False pass = passes the public tests but fails the hidden ones (looks right, isn't).", "",
                  "Source: `tables/headline.csv`, `tables/cells.csv`", ""]
    else:
        lines += ["Panacea is not in this pack yet. Run `python Baseline/baseline.py panacea --ids <same task list>`, "
                  "then rerun this script with `--panacea <that file>`.", ""]

    # RQ4
    lines += ["## Slide: RQ4. Where do the models fail?", "", f"Chart: `{charts['fail']}`", ""]
    f = tb["failure_types"]
    f = f[f["system"].isin([ZERO_SHOT, PANACEA])].pivot_table(index="failure_type", columns="system",
                                                               values="tasks_mean", aggfunc="sum").fillna(0)
    f = f[(f.sum(axis=1) > 0)].rename(columns=label).reset_index()
    lines += [md_table(f, floats=1), "Source: `tables/failure_types.csv`, `tables/by_difficulty.csv`", ""]

    # side question
    lines += ["## Slide (optional): Does telling the model it ran out of space help?", ""]
    cut = tb["cut_off_note"]
    if cut.empty or not cut["answers"].sum():
        lines += ["No retry followed a cut-off answer in these runs, so this can't be answered yet.", ""]
    else:
        cut = cut.assign(arm=cut["arm"].map(label))
        lines += [md_table(cut, floats=0),
                  "Reflect & fix and Critic are told; the control and bare retry never are. Fewer \"cut off again\" "
                  "in the told arms would mean the note helps. Summed over repeats.", "",
                  "Source: `tables/cut_off_note.csv` (summary.json after_cut_off)", ""]

    lines += ["## Reproduce", "", "```bash",
              f"python Optimizer/presentation.py {' '.join('data/results/' + m['_name'] for m in metas)}"
              + (f" --panacea {panacea}" if panacea else ""), "```", ""]
    (out / "slides.md").write_text("\n".join(lines))


# =====================================================================

def main():
    ap = argparse.ArgumentParser(description="Slide charts and tables for the final results (+ runs index).")
    ap.add_argument("runs", nargs="*", help="main run folder, then its repeats")
    ap.add_argument("--panacea", help="baseline.py panacea run file on the same tasks")
    ap.add_argument("--out", help="output folder (default data/results/presentation/<main run>)")
    ap.add_argument("--theme", choices=["light", "dark"], default="light")
    ap.add_argument("--index", action="store_true", help="only write the runs index")
    args = ap.parse_args()

    if args.index or not args.runs:
        idx = write_index([RESULTS_DIR])
        print(md_table(idx[["run", "split", "tasks", "scoring_version", "cost_usd", "reportable", "why_not"]]))
        print(f"-> {RESULTS_DIR}/runs_index.md")
        return

    C.T = C.THEMES[args.theme]
    reps, metas, notes = load_repeats(args.runs, args.panacea)
    R = len(reps)
    out = Path(args.out) if args.out else RESULTS_DIR / "presentation" / metas[0]["_name"]
    (out / "charts").mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(parents=True, exist_ok=True)

    why = sorted({w for m in metas for w in not_reportable_reasons(m, True)})
    banner = ("TEST DATA - NOT A RESULT" if any(m.get("synthetic") for m in metas)
              else "DEV RUN - NOT A RESULT" if why else "")

    tb = build_tables(reps, metas)
    for name, t in tb.items():
        t.to_csv(out / "tables" / f"{name}.csv", index=False)
    last = metas[0]["retries"]
    charts = {"gain": chart_gain(tb, R, banner, out / "charts"),
              "curves": chart_curves(tb, R, banner, out / "charts", last),
              "cost": chart_cost(tb, R, banner, out / "charts"),
              "panacea": chart_panacea(tb, banner, out / "charts"),
              "fail": chart_failures(tb, banner, out / "charts")}
    write_slides(tb, metas, notes, R, banner, charts, out, args.panacea)
    write_index([RESULTS_DIR, out])
    print(f"{R} run(s){'; ' + banner if banner else ''}")
    print(f"charts: {sum(1 for c in charts.values() if c)} PNGs, tables: {len(tb)} CSVs, slides.md, runs_index.md")
    print(f"-> {out}/")


if __name__ == "__main__":
    main()
