"""
charts.py

Charts for one Evaluator-Optimizer loop run (+ Panacea), drawn only from Optimizer/results.py's tables,
so every number on a chart is a number in a CSV. No metric is computed here.

    from Optimizer.results import build
    from Optimizer.charts import draw_all
    tables, meta = build(run_dir, panacea_path)
    figs = draw_all(tables, meta)                    # {name: matplotlib Figure}, e.g. for the notebook
    draw_all(tables, meta, out_dir="charts/")        # also writes <name>.png
or: python Optimizer/results.py data/results/<run> [panacea_run.json] --charts

Charts (table they read):
  01_accuracy_by_attempt   hidden pass@1 at attempts 0-3 per arm, all tasks and C + D; Panacea as a
                           dashed reference line (curves, main)
  02_gain_vs_control       each feedback arm minus the control, with the paired bootstrap 95% CI (curves)
  03_rubric_levels         rubric levels 0-4 for zero-shot, every arm at every retry, and Panacea (main)
  04_by_difficulty         C + D curves per source/difficulty (by_group)
  05_by_failure_type       C + D curves per attempt-0 failure type (by_group)
  06_by_test_format        C + D curves per test format (by_group)
  07_by_task_type          all-task curves per task type, only drawn when the run has more than one (by_group)
  08_repairs_and_breaks    repair rate, false-fix share, break rate, regressions per retry (arm_outcomes)
  09_cost_per_fix          $ per repair, tokens per repair, extra $ per extra repair vs control (arm_outcomes)
  10_accuracy_vs_cost      final hidden pass@1 vs pipeline cost: zero-shot, each arm, Panacea (curves,
                           arm_outcomes, main)

Colors: the dataviz skill's validated palette. Control is neutral ink and the three feedback arms take
categorical slots 1-3 (they pass the all-pairs colorblind check in both themes). No fourth hue passes next
to them, so zero-shot and Panacea are neutral too and are told apart by line style, marker and a direct
label. Rubric levels use one blue ramp (ordinal check passed). Mock and synthetic runs carry a TEST DATA
banner.
"""

import math
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, PercentFormatter

THEMES = {
    "light": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
              "axis": "#c3c2b7",
              "arms": {"control": "#52514e", "bare_retry": "#2a78d6", "reflect_fix": "#eb6834", "critic": "#1baf7a",
                       "zero_shot": "#898781", "panacea": "#0b0b0b"},
              # rubric level 0 (Error) .. 4 (Pass), light -> dark; failed API call = neutral
              "levels": ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"], "failed": "#e1e0d9",
              "level_text": ["#0b0b0b", "#0b0b0b", "#ffffff", "#ffffff", "#ffffff", "#52514e"]},
    "dark": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a",
             "axis": "#383835",
             "arms": {"control": "#c3c2b7", "bare_retry": "#3987e5", "reflect_fix": "#d95926", "critic": "#199e70",
                      "zero_shot": "#898781", "panacea": "#f0efec"},
             "levels": ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"], "failed": "#383835",
             "level_text": ["#ffffff", "#ffffff", "#ffffff", "#0b0b0b", "#0b0b0b", "#c3c2b7"]},
}
MARKERS = {"control": "s", "bare_retry": "o", "reflect_fix": "^", "critic": "D", "zero_shot": "X", "panacea": "*"}
LEVEL_LABELS = ["0 Error/Timeout", "1 Wrong", "2 Partial", "3 Mostly", "4 Pass"]
T = THEMES["light"]


def _color(name):
    return T["arms"].get(name, T["ink2"])


def _nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def _style(ax, ylabel=None, pct=True):
    ax.set_facecolor(T["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(T["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=T["muted"], labelsize=8, length=0)
    ax.grid(axis="y", color=T["grid"], linewidth=0.6)
    ax.set_axisbelow(True)
    if ylabel:
        ax.set_ylabel(ylabel, color=T["ink2"], fontsize=9)
    if pct:
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))


def _fig(w, h, ncols=1, nrows=1, **kw):
    fig, axes = plt.subplots(nrows, ncols, figsize=(w, h), squeeze=False, **kw)
    fig.patch.set_facecolor(T["surface"])
    return fig, axes


def _title(fig, text, sub, banner):
    fig.suptitle(text, x=0.01, ha="left", y=0.995, fontsize=12, color=T["ink"], fontweight="bold")
    fig.text(0.01, 0.945, sub, ha="left", va="top", fontsize=8.5, color=T["ink2"], wrap=True)
    if banner:
        fig.text(0.99, 0.995, banner, ha="right", va="top", fontsize=8, color=T["ink2"], fontstyle="italic")


def _legend(fig, names, extra=()):
    handles = [Line2D([], [], color=_color(a), marker=MARKERS.get(a, "o"), lw=2, ms=6, label=a) for a in names]
    handles += list(extra)
    fig.legend(handles=handles, loc="lower center", ncol=len(handles), frameon=False, fontsize=8.5,
               labelcolor=T["ink2"], bbox_to_anchor=(0.5, 0.0))


def _label_ends(ax, items, x, min_gap):
    """Direct labels at the line ends, nudged apart. items = [(y, text)]."""
    placed = []
    for y, text in sorted([i for i in items if not _nan(i[0])], key=lambda i: i[0]):
        yy = y if not placed or y - placed[-1] >= min_gap else placed[-1] + min_gap
        placed.append(yy)
        ax.annotate(text, (x, y), xytext=(x + 0.12, yy), textcoords="data", va="center", fontsize=8,
                    color=T["ink2"], annotation_clip=False,
                    arrowprops=None if abs(yy - y) < 1e-9 else dict(arrowstyle="-", color=T["axis"], lw=0.6))


def _curves(ax, d, arms, last, label=True, refs=(), ylim=(-0.03, 1.05)):
    """d: rows with arm, attempt, hidden_pass@1. refs: [(name, y)] drawn as dashed reference lines."""
    ends = []
    for arm in arms:
        a = d[d["arm"] == arm].sort_values("attempt")
        if a.empty:
            continue
        ax.plot(a["attempt"], a["hidden_pass@1"], color=_color(arm), lw=2, marker=MARKERS.get(arm, "o"), ms=6,
                markeredgecolor=T["surface"], markeredgewidth=1.2, zorder=3)
        ends.append((a["hidden_pass@1"].iloc[-1], f"{arm} {a['hidden_pass@1'].iloc[-1]:.0%}"))
    for name, y in refs:
        if _nan(y):
            continue
        ax.hlines(y, -0.2, last, color=_color(name), lw=1.2, ls=(0, (4, 3)), zorder=2)
        ends.append((y, f"{name} {y:.0%}"))
    ax.set_xticks(range(last + 1))
    ax.set_xticklabels(["a0\nzero-shot"] + [f"a{k}" for k in range(1, last + 1)])
    ax.set_xlim(-0.2, last + (0.95 if label else 0.2))
    ax.set_ylim(*ylim)
    if label:
        _label_ends(ax, ends, last, (ylim[1] - ylim[0]) * 0.055)


def _save(fig, out_dir, name):
    if out_dir:
        fig.savefig(Path(out_dir) / f"{name}.png", dpi=160, facecolor=T["surface"])


# =====================================================================
# CHARTS
# =====================================================================
def accuracy_by_attempt(t, arms, last, banner):
    c, main = t["curves"], t["main"]
    pan = main[(main["system"] == "panacea") & (main["attempt"] == 0)]
    pan_y = pan["hidden_pass@1_excl_failed"].iloc[0] if len(pan) else None
    fig, axes = _fig(10.5, 4.6, ncols=2)
    for ax, scope, name, refs in ((axes[0, 0], "all", "All tasks (A and B keep attempt 0)", [("panacea", pan_y)]),
                                  (axes[0, 1], "paired", "Tasks that went into the arms (C + D)", [])):
        d = c[c["scope"] == scope]
        _style(ax, "hidden pass@1" if scope == "all" else None)
        _curves(ax, d, arms, last, refs=refs)
        ax.set_title(f"{name}, n = {int(d['n'].max()) if len(d) else 0}", fontsize=9.5, color=T["ink"], loc="left")
    extra = ([Line2D([], [], color=_color("panacea"), lw=1.2, ls=(0, (4, 3)), label="panacea (zero-shot)")]
             if pan_y is not None else [])
    _title(fig, "Hidden-test pass rate by attempt, per arm",
           "Attempt 0 is the shared Claude zero-shot answer. Tasks whose attempt-0 API call failed are left out "
           "(main.csv and curves.csv also count them as 0). Panacea: its own failed runs left out.", banner)
    _legend(fig, arms, extra)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    return fig


def gain_vs_control(t, arms, last, banner):
    fb = [a for a in arms if a != "control"]
    c = t["curves"]
    fig, axes = _fig(10.5, 4.3, ncols=2, sharey=True)
    w = 0.8 / max(1, len(fb))
    for ax, scope, name in ((axes[0, 0], "all", "All tasks"), (axes[0, 1], "paired", "C + D only")):
        d = c[(c["scope"] == scope) & (c["attempt"] > 0)]
        _style(ax, "hidden pass@1 minus control" if scope == "all" else None)
        ax.axhline(0, color=T["axis"], lw=1)
        for i, arm in enumerate(fb):
            a = d[d["arm"] == arm].sort_values("attempt")
            x = a["attempt"] + (i - (len(fb) - 1) / 2) * w
            y = a["gain_vs_control"].astype(float)
            lo = (y - a["gain_ci_low"].astype(float)).clip(lower=0)
            hi = (a["gain_ci_high"].astype(float) - y).clip(lower=0)
            ax.errorbar(x, y, yerr=[lo, hi], fmt=MARKERS.get(arm, "o"), color=_color(arm), ms=6, lw=1.2,
                        capsize=0, markeredgecolor=T["surface"], markeredgewidth=1, zorder=3)
        ax.set_xticks(range(1, last + 1))
        ax.set_xticklabels([f"a{k}" for k in range(1, last + 1)])
        ax.set_title(f"{name}, n = {int(d['n'].max()) if len(d) else 0}", fontsize=9.5, color=T["ink"], loc="left")
    _title(fig, "Each feedback arm vs the control (fresh resample)",
           "Points: difference in hidden pass@1 on the same tasks. Bars: paired bootstrap 95% CI. Above 0 = the "
           "feedback helped. Exact McNemar tests: paired_tests.csv.", banner)
    _legend(fig, fb)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    return fig


def rubric_levels(t, arms, last, banner):
    m = t["main"]
    rows = [("zero_shot", 0, "zero-shot (a0)")]
    for arm in arms:
        rows += [(arm, k, f"{arm} a{k}") for k in range(1, last + 1)]
    if "panacea" in set(m["system"]):
        rows.append(("panacea", 0, "panacea"))
    fig, axes = _fig(10, 0.36 * len(rows) + 1.9)
    ax = axes[0, 0]
    _style(ax, pct=False)
    ax.grid(False)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    for i, (s, k, label) in enumerate(rows):
        r = m[(m["system"] == s) & (m["attempt"] == k)].iloc[0]
        counts = [r[f"level_{lv}"] for lv in range(5)] + [r["level_none"]]
        left = 0.0
        for j, n in enumerate(counts):
            share = n / r["n"] if r["n"] else 0
            if share:
                ax.barh(i, share, left=left, height=0.7, color=(T["levels"] + [T["failed"]])[j],
                        edgecolor=T["surface"], linewidth=2, zorder=3)
                if share >= 0.06:
                    ax.text(left + share / 2, i, str(int(n)), ha="center", va="center", fontsize=7,
                            color=T["level_text"][j])
            left += share
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[2] for r in rows], fontsize=8, color=T["ink2"])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    handles = [matplotlib.patches.Patch(color=c, label=l) for c, l in zip(T["levels"], LEVEL_LABELS)]
    handles.append(matplotlib.patches.Patch(color=T["failed"], label="failed API call"))
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, fontsize=8, labelcolor=T["ink2"])
    _title(fig, "Rubric levels on the hidden tests",
           "Share of all tasks at each level; numbers inside are task counts. Every arm covers every task "
           "(A and B keep attempt 0).", banner)
    h = fig.get_figheight()
    fig.subplots_adjust(left=0.12, right=0.98, top=1 - 0.75 / h, bottom=0.75 / h)
    return fig


def by_group(t, arms, last, banner, grouping, scope, heading, note):
    d = t["by_group"]
    d = d[(d["grouping"] == grouping) & (d["scope"] == scope) & d["system"].isin(arms)].rename(columns={"system": "arm"})
    order = {"easy": 0, "medium": 1, "hard": 2}
    groups = sorted(d["group"].unique(), key=lambda g: (g.split("/")[0], order.get(g.split("/")[-1], 9), g))
    if not groups:
        return None
    ncols = min(3, len(groups))
    nrows = math.ceil(len(groups) / ncols)
    fig, axes = _fig(3.6 * ncols + 0.6, 2.9 * nrows + 1.2, ncols=ncols, nrows=nrows, sharey=True)
    for i, ax in enumerate(axes.flat):
        if i >= len(groups):
            ax.set_visible(False)
            continue
        gd = d[d["group"] == groups[i]]
        _style(ax, "hidden pass@1" if i % ncols == 0 else None)
        _curves(ax, gd, arms, last, label=False)
        fin = gd[gd["attempt"] == last].set_index("arm")
        gains = "  ".join(f"{a.split('_')[0]} {fin.loc[a, 'gain_vs_control']:+.0%}" for a in arms
                          if a != "control" and a in fin.index and not _nan(fin.loc[a, "gain_vs_control"]))
        ax.set_title(f"{groups[i]}  (n = {int(gd['n'].max())})", fontsize=9, color=T["ink"], loc="left", pad=16)
        if gains:
            ax.text(0, 1.02, f"a{last} vs control: {gains}", transform=ax.transAxes, fontsize=7, color=T["ink2"],
                    va="bottom")
    _title(fig, heading, note, banner)
    _legend(fig, arms)
    fig.tight_layout(rect=(0, 0.07 if nrows == 1 else 0.04, 1, 0.9 if nrows == 1 else 0.93))
    return fig


def _bars(ax, o, arms, col, fmt, heading, sub, pct=True, tick=None):
    _style(ax, None, pct=pct)
    vals = [o.set_index("arm").loc[a, col] for a in arms]
    for i, (a, v) in enumerate(zip(arms, vals)):
        if _nan(v):
            ax.text(i, 0, "n/a", ha="center", va="bottom", fontsize=7.5, color=T["muted"])
            continue
        ax.bar(i, v, width=0.6, color=_color(a), zorder=3)
        ax.text(i, v, fmt(v), ha="center", va="bottom" if v >= 0 else "top", fontsize=7.5, color=T["ink2"])
    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels([a.replace("_", "\n") for a in arms], fontsize=7.5)
    ax.set_xlim(-0.6, len(arms) - 0.4)
    ax.set_title(heading, fontsize=9, color=T["ink"], loc="left", pad=16)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=7, color=T["ink2"], va="bottom")
    if tick:
        ax.yaxis.set_major_formatter(FuncFormatter(tick))
    ok = [v for v in vals if not _nan(v)] or [0]
    top, bottom = max(ok + [0]), min(ok + [0])
    if pct:
        ax.set_ylim(0, 1.08 if top > 0.8 else max(0.05, top * 1.25))
    else:
        span = (top - bottom) or 1
        ax.set_ylim(bottom - 0.15 * span if bottom < 0 else 0, top + 0.2 * span)
        ax.axhline(0, color=T["axis"], lw=1)


def repairs_and_breaks(t, arms, last, banner):
    o = t["arm_outcomes"]
    pct = lambda v: f"{v:.0%}"  # noqa: E731
    fig, axes = _fig(12, 4.0, ncols=4)
    _bars(axes[0, 0], o, arms, "repair_rate", pct, "Repair rate", f"D tasks passing hidden at a{last} (of {o['n_D'].iloc[0]})")
    _bars(axes[0, 1], o, arms, "false_fix_share", pct, "False-fix share", "public pass but hidden fail, of public 'fixes'")
    _bars(axes[0, 2], o, arms, "break_rate", pct, "Break rate", f"C tasks failing hidden at a{last} (of {o['n_C'].iloc[0]})")
    _bars(axes[0, 3], o, arms, "regression_rate_per_retry", pct, "Regressions per retry",
          "hidden test pass rate fell vs the last good attempt")
    _title(fig, "Repairs, false fixes, breaks and regressions (tasks that went into the arms)",
           "Higher is better only for repair rate. Counts and the repair-rate Wilson CI: arm_outcomes.csv.", banner)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def cost_per_fix(t, arms, last, banner):
    o = t["arm_outcomes"]
    usd = lambda v: ("-" if v < 0 else "") + (f"${abs(v):.3f}" if abs(v) < 1 else f"${abs(v):.2f}")  # noqa: E731
    dollars = lambda v, _: ("-" if v < 0 else "") + f"${abs(v):g}"  # noqa: E731
    fig, axes = _fig(12, 4.0, ncols=3)
    _bars(axes[0, 0], o, arms, "cost_per_repair_usd", usd, "$ per repair", "the arm's retry cost / repairs",
          pct=False, tick=dollars)
    _bars(axes[0, 1], o, arms, "tokens_per_repair", lambda v: f"{v / 1000:.1f}k", "Tokens per repair",
          "input + output tokens of the arm's retries / repairs", pct=False, tick=lambda v, _: f"{v / 1000:g}k")
    fb = [a for a in arms if a != "control"]
    if "extra_cost_per_extra_repair_usd" in o and fb:
        _bars(axes[0, 2], o, fb, "extra_cost_per_extra_repair_usd", usd, "Extra $ per extra repair vs control",
              "n/a = no more repairs than the control; below 0 = more repairs for less", pct=False, tick=dollars)
    else:
        axes[0, 2].set_visible(False)
    _title(fig, "What a fix costs", "Retries only (attempt 0 is shared by every arm). Critic retries make 2 calls.",
           banner)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def accuracy_vs_cost(t, arms, last, banner):
    c, o, m = t["curves"], t["arm_outcomes"].set_index("arm"), t["main"]
    allc = c[c["scope"] == "all"]
    z = m[(m["system"] == "zero_shot") & (m["attempt"] == 0)].iloc[0]
    pts = [("zero_shot", z["cost_usd"], allc[allc["attempt"] == 0]["hidden_pass@1"].iloc[0])]
    pts += [(a, o.loc[a, "pipeline_cost_usd"], allc[(allc["arm"] == a) & (allc["attempt"] == last)]["hidden_pass@1"].iloc[0])
            for a in arms]
    pan = m[(m["system"] == "panacea") & (m["attempt"] == 0)]
    note = ""
    if len(pan):
        p = pan.iloc[0]
        if p["cost_usd"] > 0:
            pts.append(("panacea", p["cost_usd"], p["hidden_pass@1_excl_failed"]))
        else:
            note = " Panacea has no logged cost, so it is not shown."
    fig, axes = _fig(7.5, 4.8)
    ax = axes[0, 0]
    _style(ax, "hidden pass@1, all tasks")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))
    for a, x, y in pts:
        ax.scatter([x], [y], s=200 if a == "panacea" else 70, color=_color(a), marker=MARKERS.get(a, "o"),
                   edgecolor=T["surface"], linewidth=1.5, zorder=3)
        ax.annotate(f"{a} {y:.0%}", (x, y), xytext=(7, 4), textcoords="offset points", fontsize=8, color=T["ink2"])
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    ax.set_xlim(0, max(xs) * 1.3 if max(xs) > 0 else 1)
    ax.set_ylim(max(0, min(ys) - 0.1), min(1.05, max(ys) + 0.1))
    ax.set_xlabel("pipeline cost: attempt 0 on every task + the arm's retries", color=T["muted"], fontsize=8)
    _title(fig, "Accuracy vs cost", f"Final (a{last}) hidden pass@1. Up and left is better.{note}", banner)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


SPLITS = [
    ("04_by_difficulty", "source_difficulty", "paired", "By source and difficulty (C + D tasks)",
     "MBPP difficulty (static complexity) and LiveCodeBench difficulty (platform) are different scales: compare "
     "arms within a panel, not panels."),
    ("05_by_failure_type", "attempt0_failure_type", "paired", "By attempt-0 failure type (C + D tasks)",
     "Grouped by why Claude's zero-shot answer failed its hidden tests (C tasks: none, hidden pass)."),
    ("06_by_test_format", "test_format", "paired", "By test format (C + D tasks)",
     "stdin_io programs vs functions (functional_io, assert_list)."),
    ("07_by_task_type", "task_type", "all", "By task type (all tasks)",
     "Experiments use code generation only; this chart appears when a run has more than one task type."),
]


def draw_all(tables, meta, out_dir=None, theme="light", close=False):
    """Every chart as {name: Figure}. With out_dir, also writes <name>.png there. close=True closes each figure
    after saving (for scripts)."""
    global T
    T = THEMES[theme]
    arms, last = list(meta["arms"]), int(meta["retries"])
    synthetic = meta.get("synthetic") or meta.get("provider") in ("mock", "synthetic") or meta.get("model") == "mock"
    banner = "TEST DATA (mock/synthetic run): the numbers mean nothing" if synthetic else ""
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    figs = {"01_accuracy_by_attempt": accuracy_by_attempt(tables, arms, last, banner)}
    if "control" in arms and len(arms) > 1:
        figs["02_gain_vs_control"] = gain_vs_control(tables, arms, last, banner)
    figs["03_rubric_levels"] = rubric_levels(tables, arms, last, banner)
    for name, grouping, scope, heading, note in SPLITS:
        bg = tables["by_group"]
        if grouping == "task_type" and bg.loc[bg["grouping"] == grouping, "group"].nunique() < 2:
            continue
        fig = by_group(tables, arms, last, banner, grouping, scope, heading, note)
        if fig is not None:
            figs[name] = fig
    if not tables["arm_outcomes"].empty:
        figs["08_repairs_and_breaks"] = repairs_and_breaks(tables, arms, last, banner)
        figs["09_cost_per_fix"] = cost_per_fix(tables, arms, last, banner)
        figs["10_accuracy_vs_cost"] = accuracy_vs_cost(tables, arms, last, banner)
    for name, fig in figs.items():
        _save(fig, out_dir, name)
        if close:
            plt.close(fig)
    return figs
