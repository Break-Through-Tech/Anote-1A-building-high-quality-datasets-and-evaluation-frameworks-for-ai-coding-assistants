"""
compare_runs.py

Reads the *_run.json files written by baseline.py and prints one comparison
table: pass@1 and test pass rate per run, split by task type. Use it to compare
prompt levels (basic / detailed / extreme) or providers (claude / panacea / ...).

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
    runs.sort(key=lambda r: (r["provider"], LEVEL_ORDER.get(r.get("prompt_level", "raw"), 9)))

    task_types = sorted({tt for r in runs for tt in r["summary"] if tt in ("code_generation", "bug_fixing")})
    head = ["provider", "level", "n", "failed"] + [f"{tt} pass@1" for tt in task_types] + ["overall pass@1", "test pass rate", "mean tokens"]
    rows = []
    for r in runs:
        s = r["summary"]
        o = s["overall"]
        rows.append([r["provider"], r.get("prompt_level", "raw"), str(o["n"]), str(s.get("failed_runs", 0))]
                    + [fmt(s.get(tt, {}).get("pass@1")) for tt in task_types]
                    + [fmt(o["pass@1"]), fmt(o["test_pass_rate"]), fmt(o["output_tokens"])])

    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    table = "\n".join(lines)
    print(table)

    # Per-dataset breakdown, since the mix of easy/hard datasets drives the overall number.
    sources = sorted({k for r in runs for k in r["summary"] if k not in ("overall", "failed_runs", *task_types)})
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
