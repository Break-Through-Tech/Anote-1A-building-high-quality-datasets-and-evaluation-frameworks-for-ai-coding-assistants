"""
evaluator.py

Scores model-generated Python code for the code-generation task (Task #5).
Converts MBPP/HumanEval rows into one shared item format, runs the generated
code against each item's tests in a sandboxed subprocess, and reports pass@1.
"""

# --- imports ---
import json
import os
import re
import subprocess
import sys
import tempfile

# --- config ---
TIMEOUT_S = 10  # max seconds a candidate's code + tests are allowed to run


# =====================================================================
# UNIFIED ITEM SCHEMA
# Every dataset gets converted to one shape so the same scorer works
# for all of them:
#   id          -> unique string, e.g. "mbpp-11"
#   task_type   -> always "code_generation" here
#   source      -> "mbpp" | "humaneval" | ...
#   prompt      -> exactly what gets sent to the model
#   reference   -> ground-truth solution (for humans; not used in scoring)
#   tests       -> list of python snippets; each must run without raising
# =====================================================================

# Convert one raw MBPP row into the shared item format.
def from_mbpp(row: dict) -> dict:
    """MBPP fields: task_id, text, code, test_list, test_setup_code, challenge_test_list."""
    # MBPP's text prompt doesn't name the function, but the tests do -
    # show the model one test so it knows what to call the function.
    prompt = (f"{row['text']}\nYour code should pass this test:\n{row['test_list'][0]}\n"
              f"Return only the Python code.")
    setup = row.get("test_setup_code") or ""
    tests = [(setup + "\n" + t).strip() for t in row["test_list"]]
    return {"id": f"mbpp-{row['task_id']}", "task_type": "code_generation", "source": "mbpp",
            "prompt": prompt, "reference": row["code"], "tests": tests}


# Convert one raw HumanEval row into the shared item format.
def from_humaneval(row: dict) -> dict:
    """HumanEval fields: task_id, prompt, canonical_solution, test, entry_point."""
    prompt = f"Complete this Python function. Return the full function.\n\n{row['prompt']}"
    # `test` defines check(candidate); calling it on the entry point runs
    # every assertion inside it as ONE combined test.
    test = f"{row['test']}\ncheck({row['entry_point']})"
    return {"id": f"humaneval-{row['task_id']}", "task_type": "code_generation",
            "source": "humaneval", "prompt": prompt,
            "reference": row["prompt"] + row["canonical_solution"], "tests": [test]}


# =====================================================================
# RUNNING MODEL-GENERATED CODE
# =====================================================================

# Matches a ```python ... ``` fenced block, if the model wrapped its answer in one.
_CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


# Pull the actual code out of a model response (strip markdown fencing if present).
def extract_code(text: str) -> str:
    """Return the first fenced code block if there is one, else the raw text."""
    m = _CODE_BLOCK.search(text)
    return m.group(1).strip() if m else text.strip()


# Small script run in its own subprocess: loads the candidate code once,
# then runs each test against it and reports pass/fail per test.
_HARNESS = r'''
import json, sys
results, ns = [], {}
try:
    exec(compile(open(sys.argv[1]).read(), "candidate", "exec"), ns)
    load_error = None
except BaseException as e:
    load_error = repr(e)
for t in json.load(open(sys.argv[2])):
    if load_error is not None:
        results.append(False)
        continue
    try:
        exec(t, ns)
        results.append(True)
    except BaseException:
        results.append(False)
print("__RESULT__" + json.dumps({"results": results, "load_error": load_error}))
'''


# Run `code` and its tests in a subprocess with a timeout.
# NOTE: this is a crash/timeout guard, not a security sandbox - only run it
# somewhere disposable, since it does execute whatever code the model wrote.
def run_tests(code: str, tests: list, timeout: int = TIMEOUT_S) -> dict:
    """Run `code` once, then each test snippet in the same namespace."""
    with tempfile.TemporaryDirectory() as d:
        cand, tst, harness = (os.path.join(d, n) for n in ("cand.py", "tests.json", "h.py"))
        open(cand, "w").write(code)
        json.dump(tests, open(tst, "w"))
        open(harness, "w").write(_HARNESS)
        try:
            p = subprocess.run([sys.executable, "-I", harness, cand, tst],
                               capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return {"results": [False] * len(tests), "error": "timeout"}
        for line in p.stdout.splitlines():
            if line.startswith("__RESULT__"):
                out = json.loads(line[len("__RESULT__"):])
                return {"results": out["results"], "error": out["load_error"]}
        return {"results": [False] * len(tests), "error": (p.stderr or "no output")[-300:]}


# =====================================================================
# SCORING
# =====================================================================

# Score one model output against one item. This is the main entry point.
def evaluate(item: dict, output: str, latency_s: float = None, output_tokens: int = None) -> dict:
    """
    score          = pass@1: 1.0 if every test passes, else 0.0  (primary metric)
    test_pass_rate = fraction of individual tests passed          (partial credit, diagnostic)
    latency_s / output_tokens are passed through so runs can be compared on speed and cost.
    """
    r = run_tests(extract_code(output), item["tests"])
    n, passed = len(item["tests"]), sum(r["results"])
    return {"id": item["id"], "source": item["source"],
            "score": 1.0 if n and passed == n else 0.0,
            "test_pass_rate": passed / n if n else 0.0,
            "error": r["error"], "latency_s": latency_s, "output_tokens": output_tokens}


# Roll up a list of evaluate() results into overall + per-dataset averages.
def summarize(results: list) -> dict:
    """Overall and per-dataset means: the row you'd put in a comparison table."""
    def agg(rs):
        def mean(k):
            v = [r[k] for r in rs if r.get(k) is not None]
            return round(sum(v) / len(v), 3) if v else None
        return {"n": len(rs), "pass@1": mean("score"), "test_pass_rate": mean("test_pass_rate"),
                "latency_s": mean("latency_s"), "output_tokens": mean("output_tokens")}
    out = {"overall": agg(results)}
    for src in sorted({r["source"] for r in results}):
        out[src] = agg([r for r in results if r["source"] == src])
    return out


# =====================================================================
# SELF-TEST - run `python evaluator.py` to check everything still works.
# =====================================================================
if __name__ == "__main__":
    # Fake rows using the exact field names of the real datasets.
    mbpp_row = {"task_id": 1, "text": "Write a function to add two numbers.", "code": "def add(a,b): return a+b",
                "test_list": ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"],
                "test_setup_code": "", "challenge_test_list": []}
    he_row = {"task_id": "HumanEval/0", "prompt": "def double(x):\n    \"\"\"Return x times 2.\"\"\"\n",
              "canonical_solution": "    return x * 2\n",
              "test": "def check(candidate):\n    assert candidate(2) == 4\n    assert candidate(0) == 0\n",
              "entry_point": "double"}
    mbpp, he = from_mbpp(mbpp_row), from_humaneval(he_row)

    # Each case: (item, model output, expected pass@1 score).
    cases = [
        (mbpp, "```python\ndef add(a, b):\n    return a + b\n```", 1.0),
        (mbpp, "def add(a, b):\n    return a - b", 0.0),
        (mbpp, "def add(a, b):\n    while True: pass", 0.0),   # infinite loop -> timeout
        (mbpp, "def add(a, b) return a", 0.0),                   # syntax error
        (he, "def double(x):\n    return x * 2", 1.0),
        (he, "def double(x):\n    return x + 2", 0.0),
        (he, mbpp_row["code"], 0.0),                              # wrong function name
    ]
    for item, out, want in cases:
        r = evaluate(item, out)
        assert r["score"] == want, (item["id"], out, r)
        print("ok", item["id"], r["score"], r["error"])

    # Partial credit check: passes 1 of 2 MBPP asserts.
    r = evaluate(mbpp, "def add(a, b):\n    return 3", 0.0)
    assert r["score"] == 0.0 and r["test_pass_rate"] == 0.5, r

    print(summarize([evaluate(mbpp, cases[0][1], 1.0, 50), evaluate(he, cases[5][1], 2.0, 70)]))
    print("ALL TESTS PASSED")
