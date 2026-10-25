"""
compare_runs.py

Reads the *_run.json files written by baseline.py and prints one comparison
table: pass@1 and test pass rate per run, split by task type. Use it to compare
prompt levels (basic / detailed / extreme) or providers (claude / panacea / ...).
Runs are only compared if they covered exactly the same task ids (run every arm
from the same --ids task list).

Usage (from the repo root):
    python Baseline/compare_runs.py                      # every *_run.json at the repo root
    python Baseline/compare_runs.py baseline_basic_run.json baseline_extreme_run.json
    python Baseline/compare_runs.py --out comparison.md  # also save the table as markdown
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEVEL_ORDER = {"raw": 0, "basic": 1, "detailed": 2, "extreme": 3}


def fmt(x):
    return "-" if x is None else f"{x:.3f}"


# Stop unless every run covered the same task ids; otherwise the pass rates are not comparable.
def check_same_tasks(runs: list):
    ids = {r["_file"]: {res["id"] for res in r["results"]} for r in runs}
    first_file, first = next(iter(ids.items()))
    problems = []
    for file, these in ids.items():
        if these != first:
            only_here, missing = sorted(these - first), sorted(first - these)
            problems.append(f"  {file} vs {first_file}: only in {file}: {only_here or '-'}; "
                            f"missing from {file}: {missing or '-'}")
    if problems:
        sys.exit("Runs cover different tasks, so they can't be compared. "
                 "Run every arm from the same --ids task list.\n" + "\n".join(problems))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="run files (default: all *_run.json at the repo root)")
    ap.add_argument("--out", help="also write the table to this markdown file")
    args = ap.parse_args()

    paths = [Path(f) for f in args.files] or sorted(REPO_ROOT.glob("*_run.json"))
    runs = []
    for path in paths:
        run = json.loads(path.read_text())
        run["_file"] = path.name
        runs.append(run)
    if not runs:
        sys.exit("No *_run.json files found. Run Baseline/baseline.py first.")
    check_same_tasks(runs)
    runs.sort(key=lambda r: (r["provider"], LEVEL_ORDER.get(r.get("prompt_level", "raw"), 9)))

    task_types = sorted({tt for r in runs for tt in r["summary"] if tt in ("code_generation", "bug_fixing")})
    head = (["provider", "level", "n", "failed"] + [f"{tt} pass@1" for tt in task_types]
            + ["overall pass@1", "pass@1 (excl. failed)", "test pass rate", "mean tokens"])
    rows = []
    for r in runs:
        s = r["summary"]
        o = s["overall"]
        rows.append([r["provider"], r.get("prompt_level", "raw"), str(o["n"]), str(s.get("failed_runs", 0))]
                    + [fmt(s.get(tt, {}).get("pass@1")) for tt in task_types]
                    + [fmt(o["pass@1"]), fmt(s.get("excluding_failed_runs", {}).get("pass@1")),
                       fmt(o["test_pass_rate"]), fmt(o["output_tokens"])])

    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    table = "\n".join(lines)
    print(table)

    # Per-dataset breakdown, since the mix of easy/hard datasets drives the overall number.
    not_sources = ("overall", "failed_runs", "excluding_failed_runs", "code_generation", "bug_fixing")
    sources = sorted({k for r in runs for k in r["summary"] if k not in not_sources})
    print("\nPer dataset pass@1:")
    sub_head = ["provider", "level"] + sources
    sub = ["| " + " | ".join(sub_head) + " |", "|" + "|".join("---" for _ in sub_head) + "|"]
    for r in runs:
        sub.append("| " + " | ".join([r["provider"], r.get("prompt_level", "raw")]
                                      + [fmt(r["summary"].get(src, {}).get("pass@1")) for src in sources]) + " |")
    print("\n".join(sub))

    if args.out:
        Path(args.out).write_text(table + "\n\nPer dataset pass@1:\n\n" + "\n".join(sub) + "\n")
        print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
