"""Data-quality audit of the evaluation set (issue #22). Read-only: it changes no data file.

    python Evaluator/data_audit.py            # data checks only (a few seconds)
    python Evaluator/data_audit.py --rescore  # also scores known-correct answers twice (~1 min)

Writes data/unified/reports/data_audit.md and prints the same text. Every check reports
what it found, so the report can be quoted in the limitations section of the final report.
Nothing here calls an API.
"""
import argparse
import difflib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

UNIFIED = REPO_ROOT / "data" / "unified"
EVAL_PATH = UNIFIED / "unified_eval.jsonl"
POOL_PATH = UNIFIED / "unified_pool.jsonl"
PRIVATE_PATH = UNIFIED / "unified_private_tests.jsonl.gz"
FIXTURES_PATH = REPO_ROOT / "Evaluator" / "fixtures.json"
REPORT_PATH = UNIFIED / "reports" / "data_audit.md"

MIN_DISTINCT_HIDDEN = 5      # the eval set's own rule (data/README.md); hard LiveCodeBench tasks are exempt
NEAR_DUP_RATIO = 0.85        # prompts at least this similar are listed for a person to read
URL_RE = re.compile(r"https?://\S+")


def load():
    ev = pd.read_json(EVAL_PATH, lines=True, dtype=False)
    pool = pd.read_json(POOL_PATH, lines=True, dtype=False)
    private = pd.read_json(PRIVATE_PATH, lines=True, dtype=False)
    hidden = dict(zip(private["id"], private["private_test_cases"]))
    return ev, pool, hidden


def norm(text: str) -> str:
    """Lower case, punctuation and whitespace collapsed: for comparing prompts."""
    return re.sub(r"\W+", " ", text.lower()).strip()


def test_key(t) -> str:
    return json.dumps(t, sort_keys=True)


def test_input(t):
    """The input of one test: the stdin/args for LiveCodeBench, the call for an MBPP assert."""
    if isinstance(t, dict):
        return t.get("input")
    if isinstance(t, str) and t.startswith("assert ") and "==" in t:
        return t[len("assert "):t.index("==")].strip()
    return None


def table(rows, cols) -> str:
    if not rows:
        return "_none_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- checks
def composition(ev):
    g = ev.assign(difficulty=ev["metadata"].apply(lambda m: (m or {}).get("difficulty", "-")))
    rows = (g.groupby(["task_type", "source", "difficulty", "test_format"]).size()
             .reset_index(name="tasks").to_dict("records"))
    return "## 1. What is in the evaluation set\n\n" + f"{len(ev)} tasks.\n\n" + table(
        rows, ["task_type", "source", "difficulty", "test_format", "tasks"])


def uniqueness(ev, pool):
    issues = []
    dup_ids = ev[ev["id"].duplicated()]["id"].tolist()
    dup_prompts = ev[ev["prompt"].duplicated()]["id"].tolist()
    shared_ids = sorted(set(ev["id"]) & set(pool["id"]))
    shared_prompts = len(set(ev["prompt"]) & set(pool["prompt"]))
    near = []
    for src in ev["source"].unique():
        e_src, p_src = ev[ev["source"] == src], pool[pool["source"] == src]
        p_norm = [(r.id, norm(r.prompt)) for r in p_src.itertuples()]
        for r in e_src.itertuples():
            a = norm(r.prompt)
            for pid, b in p_norm:
                sm = difflib.SequenceMatcher(None, a, b)
                if sm.real_quick_ratio() >= NEAR_DUP_RATIO and sm.quick_ratio() >= NEAR_DUP_RATIO \
                        and sm.ratio() >= NEAR_DUP_RATIO:
                    near.append({"eval_id": r.id, "pool_id": pid, "similarity": round(sm.ratio(), 2)})
    for name, vals in [("duplicate ids in eval", dup_ids), ("duplicate prompts in eval", dup_prompts),
                       ("ids in both eval and pool", shared_ids)]:
        issues.append(f"- {name}: **{len(vals)}** {vals[:10] if vals else ''}")
    issues.append(f"- identical prompts in both eval and pool: **{shared_prompts}**")
    text = "## 2. Duplicates and overlap with the pool\n\n" + "\n".join(issues) + "\n\n"
    text += (f"Near-identical prompts between eval and pool (similarity >= {NEAR_DUP_RATIO}, same source). "
             "Read each pair: a pool task used as a few-shot example must not give away an eval answer.\n\n")
    return text + table(near, ["eval_id", "pool_id", "similarity"])


def public_tests(ev):
    rows = []
    for src, g in ev.groupby("source"):
        n = g["tests"].apply(len)
        rows.append({"source": src, "tasks": len(g), "min": n.min(), "median": n.median(), "max": n.max(),
                     "tasks with 1 public test": int((n == 1).sum()), "tasks with none": int((n == 0).sum())})
    text = "## 3. Public tests (the only feedback the model sees)\n\n" + table(
        rows, ["source", "tasks", "min", "median", "max", "tasks with 1 public test", "tasks with none"])
    return text + ("\nHumanEval-Fix keeps all its asserts inside one `check` function, so 1 test there "
                   "means one function, not one assert. The first failing public test is what the feedback "
                   "arms see, so tasks with a single public test give them very little to work with.\n")


def hidden_tests(ev, hidden):
    cg = ev[ev["task_type"] == "code_generation"]
    missing = [i for i in cg["id"] if i not in hidden]
    extra = sorted(set(hidden) - set(cg["id"]))
    low, repeats, copies = [], [], []
    for r in cg.itertuples():
        tests = hidden.get(r.id, [])
        distinct = len({test_key(t) for t in tests})
        diff = (r.metadata or {}).get("difficulty")
        if distinct < MIN_DISTINCT_HIDDEN:
            low.append({"id": r.id, "difficulty": diff, "hidden": len(tests), "distinct": distinct,
                        "why allowed": "hard tasks are exempt" if diff == "hard" else "**breaks the rule**"})
        if distinct < len(tests):
            repeats.append(r.id)
        public_inputs = {test_input(t) for t in r.tests} - {None}
        n_copy = sum(test_input(t) in public_inputs for t in tests)
        if n_copy:
            copies.append({"id": r.id, "hidden tests with a public input": n_copy})
    text = "## 4. Hidden tests (scoring only, never shown)\n\n"
    text += f"- code-generation tasks without hidden tests: **{len(missing)}** {missing[:10] if missing else ''}\n"
    text += f"- hidden-test rows for tasks not in eval: **{len(extra)}**\n"
    text += f"- hidden tests that reuse a public test's input: **{len(copies)} tasks**\n"
    text += f"- tasks whose hidden list repeats a test: **{len(repeats)}** ({', '.join(repeats)})\n\n"
    text += (f"Tasks with fewer than {MIN_DISTINCT_HIDDEN} distinct hidden tests. With so few tests, "
             "a wrong answer can pass by luck, so read these tasks' results with care.\n\n")
    text += table(low, ["id", "difficulty", "hidden", "distinct", "why allowed"])
    if copies:
        text += "\n" + table(copies, ["id", "hidden tests with a public input"])
    return text


def prompts(ev):
    rows = []
    for r in ev.itertuples():
        flags = []
        if URL_RE.search(r.prompt):
            flags.append("contains a web link")
        if r.task_type == "code_generation" and r.entry_point and r.source == "mbpp" \
                and f"def {r.entry_point}" not in r.prompt:
            flags.append("function name not in prompt")
        if r.source == "mbpp":
            words = len(r.prompt.split("\n")[0].split())
            if words <= 12:
                flags.append(f"one short sentence ({words} words), no example")
        ref = (r.reference or "").strip()
        if r.task_type == "bug_fixing":
            # the buggy code is meant to be in the prompt; it must differ from the fix
            if ref and ref == ((r.metadata or {}).get("buggy_code") or "").strip():
                flags.append("**buggy code is the same as the fix**")
        elif len(ref) > 40 and re.search(re.escape(ref) + r"\s*(```|$)", r.prompt):
            # the whole reference, ending where a code block ends (a reference that is only the
            # start of a longer line, as in some bug fixes, is not a leak)
            flags.append("**reference solution appears in the prompt**")
        if flags:
            rows.append({"id": r.id, "first line": r.prompt.split("\n")[0][:90].replace("|", "/"),
                         "flags": "; ".join(flags)})
    text = "## 5. Prompt checks\n\n"
    text += ("MBPP prompts are one sentence plus a function signature, with no example input or output, "
             "so the expected return format is often a guess. A model can fail an MBPP task because the "
             "prompt is unclear rather than because it can't code. Flagged prompts (read them by hand; "
             "the checks are simple text rules):\n\n")
    return text + table(rows, ["id", "first line", "flags"])


def rescore(ev, hidden):
    """Score known-correct answers twice on their hidden tests: they must pass, the same way, both times."""
    from Evaluator.evaluator import evaluate
    fixtures = {k: v for k, v in json.loads(FIXTURES_PATH.read_text()).items() if not k.startswith("_")}
    answers = []
    for r in ev[ev["task_type"] == "code_generation"].itertuples():
        code = r.reference or fixtures.get(r.id)
        if code:
            answers.append(({**r._asdict(), "private_tests": hidden[r.id]}, f"```python\n{code}\n```"))
    rows, slow = [], []
    for item, out in answers:
        runs = []
        for _ in range(2):
            t0 = time.time()
            res = evaluate(item, out, split="private", keep_details=False)
            runs.append((res["score"], res.get("n_passed"), round(time.time() - t0, 2)))
        same = runs[0][:2] == runs[1][:2]
        rows.append({"id": item["id"], "score run 1": runs[0][0], "score run 2": runs[1][0],
                     "same": same, "seconds": max(runs[0][2], runs[1][2])})
        if max(runs[0][2], runs[1][2]) > 3:
            slow.append(item["id"])
    not_pass = [r for r in rows if r["score run 1"] != 1.0 or r["score run 2"] != 1.0]
    differ = [r for r in rows if not r["same"]]
    text = "## 6. Scoring consistency (known-correct answers, scored twice)\n\n"
    text += (f"{len(rows)} known-correct answers (MBPP references and the hand-written LiveCodeBench "
             f"answers in `Evaluator/fixtures.json`), each scored twice on its hidden tests.\n\n")
    text += f"- answers that did not pass every hidden test: **{len(not_pass)}**\n"
    text += f"- answers scored differently the second time: **{len(differ)}**\n"
    text += (f"- answers that took over 3 s to score (the limit is 6 s per test, so slow code near the limit "
             f"could pass on one machine and time out on another): **{len(slow)}** {slow}\n\n")
    return text + table(not_pass + differ, ["id", "score run 1", "score run 2", "same", "seconds"])


def environment():
    import platform
    import numpy
    from Evaluator.evaluator import SCORING_VERSION
    text = "## 7. Environment this audit ran in\n\n"
    text += (f"Python {platform.python_version()}, pandas {pd.__version__}, numpy {numpy.__version__}, "
             f"scoring version {SCORING_VERSION}. `requirements.txt` doesn't pin versions, so another machine "
             "may install different ones.\n")
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rescore", action="store_true", help="also score known-correct answers twice (~1 min)")
    ap.add_argument("--no-write", action="store_true", help="print only; don't write the report file")
    args = ap.parse_args()

    ev, pool, hidden = load()
    parts = ["# Data-quality audit\n",
             "Written by `python Evaluator/data_audit.py" + (" --rescore" if args.rescore else "") + "` "
             "(issue #22). Read-only checks of `data/unified/`; no API calls.\n",
             composition(ev), uniqueness(ev, pool), public_tests(ev), hidden_tests(ev, hidden), prompts(ev)]
    if args.rescore:
        parts.append(rescore(ev, hidden))
    parts.append(environment())
    report = "\n".join(parts)
    print(report)
    if not args.no_write:
        REPORT_PATH.write_text(report)
        print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
