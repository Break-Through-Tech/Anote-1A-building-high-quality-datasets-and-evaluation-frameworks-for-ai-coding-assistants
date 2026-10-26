"""
evaluator.py

Scores model-generated Python code for the code-generation task (Task #5).
Loads items from the final dataset (data/unified/unified_eval.jsonl, built by
notebooks/unified_dataset.ipynb), runs the generated code against each item's
tests in a subprocess, and reports pass@1, a 5-level rubric score, and a
per-test breakdown (which test failed, expected, actual, error).

Test runners (picked by the item's `test_format`):
    assert_list, check_fn, test_functions -> Python snippets run against the code (MBPP, bug fixing)
    functional_io                         -> LiveCodeBench LeetCode-style: call Solution().<entry_point>(*args)
    stdin_io                              -> LiveCodeBench AtCoder-style: run the program with stdin, compare stdout

Public vs. private (hidden) tests:
    evaluate(item, output)                   -> public tests (item["tests"]); safe to show as feedback
    evaluate(item, output, split="private")  -> hidden tests from unified_private_tests.jsonl.gz; scoring only,
                                                NEVER show these to the model (format_feedback refuses them)
"""

# --- imports ---
import ast
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
from collections import Counter
from pathlib import Path

# --- config ---
TIMEOUT_S = 10            # max seconds for loading the candidate's code (imports, top-level work)
PER_TEST_TIMEOUT_S = 6    # max seconds per test (LiveCodeBench's hidden tests include large inputs)
MAX_TOTAL_TIMEOUT_S = 90  # hard cap for one evaluate() call, whatever the number of tests
MAX_FIELD_CHARS = 400     # test / expected / actual / error strings are cut to this length in results
REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = REPO_ROOT / "data" / "unified" / "unified_eval.jsonl"                   # the final dataset
PRIVATE_TESTS_PATH = REPO_ROOT / "data" / "unified" / "unified_private_tests.jsonl.gz"  # hidden tests
# test_format values run_tests can execute.
PYTHON_TEST_FORMATS = {"assert_list", "check_fn", "test_functions"}
IO_TEST_FORMATS = {"functional_io", "stdin_io"}
SCORABLE_FORMATS = PYTHON_TEST_FORMATS | IO_TEST_FORMATS
SPLITS = {"public": "public", "private": "private", "hidden": "private"}  # "hidden" is an alias

# LiveCodeBench starter code uses List, Optional, defaultdict, ... without importing them.
# LiveCodeBench's own grader adds the same kind of header, so we do too (LiveCodeBench items only).
LCB_HEADER = ("from typing import *\nfrom collections import *\nfrom functools import *\n"
              "from itertools import *\nfrom heapq import *\nfrom bisect import *\n"
              "import math, string, re, sys, heapq, bisect, itertools, functools, collections\n"
              "sys.setrecursionlimit(10**6)\n")

# 5-level rubric (proposed; confirm with the team). Computed from the test results:
RUBRIC = {
    0: "no valid code (empty, or a syntax error)",
    1: "valid code, passes no tests (crash, timeout or wrong answers)",
    2: "passes some tests (under half)",
    3: "passes most tests (half or more, not all)",
    4: "passes every test",
}


# =====================================================================
# UNIFIED ITEM SCHEMA
# Every row of the final dataset has one shape, so the same scorer works
# for all of them:
#   id          -> unique string, e.g. "mbpp-11"
#   task_type   -> "code_generation" | "bug_fixing"
#   source      -> "mbpp" | "livecodebench" | "quixbugs" | "humanevalfix"
#   prompt      -> exactly what gets sent to the model
#   reference   -> ground-truth solution (for humans; not used in scoring)
#   tests       -> public tests: python snippets, or {"input", "output"} dicts for LiveCodeBench
#   test_format -> which kind of tests (see SCORABLE_FORMATS)
#   entry_point -> function the tests call
#   metadata    -> task-specific details (difficulty, ...); never sent to the model
# =====================================================================

# Load items from the final dataset. File order is fixed, so the same arguments give the same items.
def load_items(path: Path = DATASET_PATH, task_type: str = "code_generation", sources: list = None,
               n_per_source: int = None, scorable_only: bool = True) -> list:
    """
    task_type     -> keep only this task type (None keeps all)
    sources       -> keep only these sources, e.g. ["mbpp"] (None keeps all)
    n_per_source  -> first n items of each source (None keeps all)
    scorable_only -> skip items whose test_format run_tests can't execute yet,
                     so no API calls are spent on tasks that can't be scored
    """
    if not Path(path).exists():
        sys.exit(f"{path} not found. Run notebooks/unified_dataset.ipynb to build the final dataset.")
    with open(path) as f:
        items = [json.loads(line) for line in f if line.strip()]
    if task_type:
        items = [it for it in items if it["task_type"] == task_type]
    if sources:
        items = [it for it in items if it["source"] in sources]
    if scorable_only:
        skipped = Counter(it["source"] for it in items if it["test_format"] not in SCORABLE_FORMATS)
        if skipped:
            print(f"[evaluator] skipping {sum(skipped.values())} items with no test runner yet: {dict(skipped)}",
                  file=sys.stderr)
        items = [it for it in items if it["test_format"] in SCORABLE_FORMATS]
    if n_per_source:
        kept, per_source = [], Counter()
        for it in items:
            per_source[it["source"]] += 1
            if per_source[it["source"]] <= n_per_source:
                kept.append(it)
        items = kept
    return items


# Hidden tests, loaded once on first use (the file is ~28 MB compressed).
_PRIVATE_CACHE = {}


def load_private_tests(path: Path = PRIVATE_TESTS_PATH) -> dict:
    """id -> list of hidden tests. Scoring only: never put these in a prompt."""
    key = str(path)
    if key not in _PRIVATE_CACHE:
        if not Path(path).exists():
            sys.exit(f"{path} not found. Run notebooks/unified_dataset.ipynb to build the hidden tests.")
        with gzip.open(path, "rt") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        _PRIVATE_CACHE[key] = {r["id"]: r["private_test_cases"] for r in rows}
    return _PRIVATE_CACHE[key]


# The tests for one item and split. Private tests can also be attached to the item as
# "private_tests" (e.g. in the self-test), which skips reading the file.
def get_tests(item: dict, split: str = "public") -> list:
    split = SPLITS.get(split)
    if split is None:
        raise ValueError("split must be 'public' or 'private' (alias 'hidden')")
    if split == "public":
        return item["tests"]
    if "private_tests" in item:
        return item["private_tests"]
    private = load_private_tests()
    if item["id"] not in private:
        raise KeyError(f"{item['id']} has no hidden tests (only the 100 code-generation tasks do)")
    return private[item["id"]]


# Convert one raw MBPP row into the shared item format (used by the self-test below;
# real runs load already-converted items with load_items()).
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


# Convert one raw HumanEval row into the shared item format (self-test only; HumanEval
# is no longer in the dataset).
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
# GETTING THE CODE OUT OF A MODEL RESPONSE
# =====================================================================

# A complete ```python ... ``` fenced block, if the model wrapped its answer in one.
_CODE_BLOCK = re.compile(r"```(?:python|py|python3)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
# An opening fence with no closing one (the answer was cut off by max_tokens).
_OPEN_FENCE = re.compile(r"```(?:python|py|python3)?[ \t]*\n(.*)$", re.DOTALL | re.IGNORECASE)
# Where code starts in an unfenced answer that opens with prose.
_CODE_START = re.compile(r"^(?:def |class |import |from |@|if __name__)", re.MULTILINE)


def _parses(code: str) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # e.g. "invalid escape sequence" in some references
            ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


# Pull the actual code out of a model response.
def extract_code(text: str, entry_point: str = None) -> str:
    """
    1. Complete fenced blocks: the first one that defines `entry_point` (or class Solution),
       else the first block. Models often put the solution first and example usage after.
    2. A fence that was opened but never closed (truncated answer): everything after it,
       minus a half-written last line if that is what breaks parsing.
    3. No fence: the raw text, or, if it doesn't parse, the text from the first line that
       looks like code (def / class / import / from / @).
    """
    text = text or ""
    blocks = [b.strip() for b in _CODE_BLOCK.findall(text)]
    if blocks:
        if entry_point:
            for b in blocks:
                if re.search(rf"\bdef\s+{re.escape(entry_point)}\s*\(", b):
                    return b
        for b in blocks:
            if "class Solution" in b:
                return b
        return blocks[0]
    m = _OPEN_FENCE.search(text)
    if m:
        code = m.group(1).rstrip()
        if not _parses(code) and "\n" in code:
            trimmed = code.rsplit("\n", 1)[0].rstrip()  # drop the line that was cut mid-way
            if _parses(trimmed):
                return trimmed
        return code
    raw = text.strip()
    if raw and not _parses(raw):
        m = _CODE_START.search(raw)
        if m and _parses(raw[m.start():]):
            return raw[m.start():].strip()
    return raw


# =====================================================================
# RUNNING MODEL-GENERATED CODE
# NOTE: these are crash/timeout guards, not a security sandbox - only run them
# somewhere disposable, since they execute whatever code the model wrote.
# =====================================================================

# Shared helpers for both harness scripts: short reprs and readable error messages
# that point at the line in the candidate's code ("solution.py").
_COMMON = r'''
import json, os, sys, signal, traceback, contextlib, ast, math
MAXC = int(os.environ.get("EVAL_MAXC", "400"))

def short(x):
    try:
        s = x if isinstance(x, str) else repr(x)
    except BaseException as e:
        s = "<unprintable %s>" % type(e).__name__
    return s if len(s) <= MAXC else s[:MAXC] + " ...[truncated]"

def fmt_exc(e, src_lines):
    msg = "%s: %s" % (type(e).__name__, e) if str(e) else type(e).__name__
    if isinstance(e, SyntaxError) and e.lineno:
        return short("%s (line %s)" % (msg, e.lineno))
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "solution.py"]
    if frames:
        f = frames[-1]
        line = src_lines[f.lineno - 1].strip() if 0 < f.lineno <= len(src_lines) else ""
        msg += " (line %d: %s)" % (f.lineno, line)
    return short(msg)
'''

# Runs in its own subprocess: loads the candidate code once, then runs each test
# against it with a per-test time limit, and writes one JSON line per test to a
# results file (so a hard kill still keeps the finished tests).
#   mode "assert"     -> each test is a python snippet; for `assert X == Y` it records X (actual) and Y (expected)
#   mode "functional" -> each test is {"input", "output"}; calls Solution().<entry>(*args) and compares
_HARNESS = _COMMON + r'''
cand_path, tests_path, out_path, mode, entry, per_test, load_timeout, header_path = sys.argv[1:9]
per_test, load_timeout = float(per_test), float(load_timeout)
src = open(cand_path).read()
src_lines = src.splitlines()
tests = json.load(open(tests_path))
out = open(out_path, "w")
def emit(d):
    out.write(json.dumps(d) + "\n"); out.flush()

class TestTimeout(BaseException):
    pass
def _alarm(*a):
    raise TestTimeout()
signal.signal(signal.SIGALRM, _alarm)
devnull = open(os.devnull, "w")
ns = {"__name__": "solution"}

def ev(node):
    return eval(compile(ast.Expression(node), "<test>", "eval"), ns)

def run_assert(t, rec):
    tree = ast.parse(t)
    *setup, last = tree.body
    if setup:
        exec(compile(ast.Module(setup, []), "<test>", "exec"), ns)
    if isinstance(last, ast.Assert):
        test = last.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            actual, expected = ev(test.left), ev(test.comparators[0])
            rec["actual"], rec["expected"] = short(actual), short(expected)
            ns["__a"], ns["__e"] = actual, expected
            cmp = ast.Compare(ast.Name("__a", ast.Load()), test.ops, [ast.Name("__e", ast.Load())])
            ok = ev(ast.fix_missing_locations(cmp))
        elif isinstance(test, ast.Call) and len(test.args) >= 2:   # np.allclose(f(x), y), math.isclose(...)
            actual, expected = ev(test.args[0]), ev(test.args[1])
            rec["actual"], rec["expected"] = short(actual), short(expected)
            ns["__a"], ns["__e"] = actual, expected
            call = ast.Call(test.func, [ast.Name("__a", ast.Load()), ast.Name("__e", ast.Load())] + test.args[2:],
                            test.keywords)
            ok = ev(ast.fix_missing_locations(ast.copy_location(call, test)))
        else:
            ok = ev(test)
        if not ok:
            rec["status"], rec["error"] = "wrong_answer", "AssertionError"
            return
    else:
        exec(compile(ast.Module([last], []), "<test>", "exec"), ns)   # check(f) style: raises on failure
    rec["status"] = "pass"

def same(a, b):
    if isinstance(a, tuple):
        a = list(a)
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-6)
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b

def run_functional(t, rec):
    args = [json.loads(line) for line in t["input"].split("\n") if line.strip()]
    expected = json.loads(t["output"])
    rec["expected"] = short(t["output"])
    if "Solution" in ns:
        fn = getattr(ns["Solution"](), entry)
    else:
        fn = ns[entry]
    actual = fn(*args)
    try:
        rec["actual"] = short(json.dumps(list(actual) if isinstance(actual, tuple) else actual))
    except (TypeError, ValueError):
        rec["actual"] = short(actual)
    rec["status"] = "pass" if same(actual, expected) else "wrong_answer"

load_error = None
signal.setitimer(signal.ITIMER_REAL, load_timeout)
try:
    with contextlib.redirect_stdout(devnull):
        if header_path != "-":
            exec(compile(open(header_path).read(), "<header>", "exec"), ns)
        exec(compile(src, "solution.py", "exec"), ns)
except TestTimeout:
    load_error = "timeout while loading the code"
except BaseException as e:
    load_error = fmt_exc(e, src_lines)
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
emit({"load_error": load_error})
if load_error is None:
    for i, t in enumerate(tests):
        rec = {"i": i, "status": "runtime_error", "expected": None, "actual": None, "error": None}
        try:
            signal.setitimer(signal.ITIMER_REAL, per_test)
            with contextlib.redirect_stdout(devnull):
                (run_assert if mode == "assert" else run_functional)(t, rec)
        except TestTimeout:
            rec["status"], rec["error"] = "timeout", "timed out after %gs" % per_test
        except AssertionError as e:
            rec["status"], rec["error"] = "wrong_answer", fmt_exc(e, src_lines)
        except BaseException as e:
            rec["status"], rec["error"] = "runtime_error", fmt_exc(e, src_lines)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        emit(rec)
'''

# Runs one stdin program: header (LiveCodeBench imports), then the candidate as __main__.
# On a crash it prints a short, readable error to stderr and exits 1.
_STDIN_RUNNER = _COMMON + r'''
src = open(sys.argv[1]).read()
src_lines = src.splitlines()
g = {"__name__": "__main__"}
try:
    if sys.argv[2] != "-":
        exec(compile(open(sys.argv[2]).read(), "<header>", "exec"), g)
    exec(compile(src, "solution.py", "exec"), g)
except SystemExit as e:
    if e.code not in (None, 0):
        sys.stderr.write("__ERR__" + "SystemExit: %s" % e.code); sys.exit(1)
except BaseException as e:
    sys.stdout.flush()
    sys.stderr.write("__ERR__" + fmt_exc(e, src_lines)); sys.exit(1)
'''


def _short(s, n=MAX_FIELD_CHARS):
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= n else s[:n] + " ...[truncated]"


# Display string for a test (the assert line, or the input), cut for logs and feedback.
def _test_text(t) -> str:
    return _short(t["input"] if isinstance(t, dict) else t)


# Compare stdout with the expected output, line by line, ignoring surrounding whitespace.
# Numbers that differ only by float rounding (1e-6) count as equal.
def outputs_match(actual: str, expected: str) -> bool:
    a = [ln.split() for ln in (actual or "").strip().splitlines()]
    e = [ln.split() for ln in (expected or "").strip().splitlines()]
    a = [ln for ln in a if ln]
    e = [ln for ln in e if ln]
    if a == e:
        return True
    if len(a) != len(e) or any(len(x) != len(y) for x, y in zip(a, e)):
        return False
    for x_line, y_line in zip(a, e):
        for x, y in zip(x_line, y_line):
            if x == y:
                continue
            try:
                fx, fy = float(x), float(y)
            except ValueError:
                return False
            if not abs(fx - fy) <= 1e-6 * max(1.0, abs(fy)):
                return False
    return True


def _run_stdin_tests(code: str, tests: list, header: str, per_test: float) -> dict:
    details = []
    with tempfile.TemporaryDirectory() as d:
        cand, runner, hdr = (os.path.join(d, n) for n in ("solution.py", "runner.py", "header.py"))
        open(cand, "w").write(code)
        open(runner, "w").write(_STDIN_RUNNER)
        if header:
            open(hdr, "w").write(header)
        env = {**os.environ, "EVAL_MAXC": str(MAX_FIELD_CHARS)}
        for i, t in enumerate(tests):
            rec = {"i": i, "status": "runtime_error", "test": _test_text(t),
                   "expected": _short(t["output"]), "actual": None, "error": None}
            try:
                p = subprocess.run([sys.executable, "-I", runner, cand, hdr if header else "-"],
                                   input=t["input"], capture_output=True, text=True, timeout=per_test, cwd=d,
                                   env=env)
            except subprocess.TimeoutExpired:
                rec["status"], rec["error"] = "timeout", f"timed out after {per_test:g}s"
            else:
                rec["actual"] = _short(p.stdout)
                if p.returncode != 0:
                    err = p.stderr.split("__ERR__", 1)[-1].strip() if p.stderr else f"exit code {p.returncode}"
                    rec["error"] = _short(err.splitlines()[-1] if "__ERR__" not in p.stderr else err)
                elif outputs_match(p.stdout, t["output"]):
                    rec["status"] = "pass"
                else:
                    rec["status"] = "wrong_answer"
            details.append(rec)
    return {"details": details, "load_error": None}


def _run_harness(code: str, tests: list, mode: str, entry: str, header: str, per_test: float) -> dict:
    with tempfile.TemporaryDirectory() as d:
        cand, tst, out, harness, hdr = (os.path.join(d, n) for n in
                                        ("solution.py", "tests.json", "out.jsonl", "h.py", "header.py"))
        open(cand, "w").write(code)
        json.dump(tests, open(tst, "w"))
        open(harness, "w").write(_HARNESS)
        if header:
            open(hdr, "w").write(header)
        budget = min(MAX_TOTAL_TIMEOUT_S, TIMEOUT_S + per_test * max(1, len(tests)) + 5)
        killed = False
        try:
            subprocess.run([sys.executable, "-I", harness, cand, tst, out, mode, entry or "", str(per_test),
                            str(TIMEOUT_S), hdr if header else "-"],
                           capture_output=True, text=True, timeout=budget, cwd=d,
                           env={**os.environ, "EVAL_MAXC": str(MAX_FIELD_CHARS)})
        except subprocess.TimeoutExpired:
            killed = True
        lines = []
        if os.path.exists(out):
            for line in open(out):
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:  # half-written last line from a kill
                    break
    if not lines:
        err = "timeout while loading the code" if killed else "the test harness crashed"
        return {"details": [], "load_error": err}
    load_error, recs = lines[0].get("load_error"), lines[1:]
    if load_error:
        return {"details": [], "load_error": load_error}
    # Tests the harness never reported: the next one hung (or crashed the process), the rest never ran.
    for i in range(len(recs), len(tests)):
        hung = i == len(recs)
        recs.append({"i": i, "status": "timeout" if (hung and killed) else "runtime_error",
                     "expected": None, "actual": None,
                     "error": ("timed out (process killed)" if killed else "test process crashed") if hung
                     else "not run (an earlier test hung or crashed)"})
    for r, t in zip(recs, tests):
        r["test"] = _test_text(t)
        if mode == "functional" and r.get("expected") is None:
            r["expected"] = _short(t.get("output"))
    return {"details": recs, "load_error": None}


# Run `code` against `tests` with the runner for `test_format`.
def run_tests(code: str, tests: list, test_format: str = "assert_list", entry_point: str = "",
              source: str = "", per_test: float = PER_TEST_TIMEOUT_S) -> dict:
    """
    Returns {"results": [bool per test], "details": [per-test dict], "error": str or None}.
    Each details entry: i, status (pass | wrong_answer | runtime_error | timeout), test, expected,
    actual, error. If the code can't even load, details are filled with status "load_error".
    """
    header = LCB_HEADER if source == "livecodebench" else ""
    if test_format == "stdin_io":
        r = _run_stdin_tests(code, tests, header, per_test)
    elif test_format == "functional_io":
        r = _run_harness(code, tests, "functional", entry_point, header, per_test)
    elif test_format in PYTHON_TEST_FORMATS:
        r = _run_harness(code, tests, "assert", entry_point, header, per_test)
    else:
        raise ValueError(f"no test runner for test_format={test_format!r}")
    if r["load_error"]:
        r["details"] = [{"i": i, "status": "load_error", "test": _test_text(t), "expected": None,
                         "actual": None, "error": r["load_error"]} for i, t in enumerate(tests)]
    details = r["details"]
    first_err = r["load_error"] or next((d["error"] for d in details if d["status"] != "pass" and d["error"]),
                                        None)
    return {"results": [d["status"] == "pass" for d in details], "details": details, "error": first_err}


# =====================================================================
# SCORING
# =====================================================================

def rubric_level(syntax_ok: bool, n_passed: int, n_tests: int) -> int:
    if not syntax_ok:
        return 0
    if n_tests == 0 or n_passed == 0:
        return 1
    if n_passed == n_tests:
        return 4
    return 3 if n_passed / n_tests >= 0.5 else 2


# Why the attempt failed, for failure analysis: no_code / syntax_error / load_error (crashes on import),
# or the status of the first failing test (wrong_answer / runtime_error / timeout).
def failure_type(syntax_ok: bool, code: str, details: list):
    if not code.strip():
        return "no_code"
    if not syntax_ok:
        return "syntax_error"
    failing = [d for d in details if d["status"] != "pass"]
    if not failing:
        return None
    return failing[0]["status"]


# Score one model output against one item. This is the main entry point.
def evaluate(item: dict, output: str, latency_s: float = None, output_tokens: int = None,
             split: str = "public", keep_details: bool = True) -> dict:
    """
    score          = pass@1: 1.0 if every test passes, else 0.0  (primary metric)
    test_pass_rate = fraction of individual tests passed          (partial credit, diagnostic)
    rubric_level   = 0-4, see RUBRIC                               (graded score)
    syntax_ok      = the extracted code parses as Python
    failure_type   = None if it passed, else no_code | syntax_error | load_error | wrong_answer |
                     runtime_error | timeout
    details        = one dict per test: i, status, test, expected, actual, error
    split          = "public" (item["tests"], OK to show as feedback) or "private" (hidden tests, scoring only)
    latency_s / output_tokens are passed through so runs can be compared on speed and cost.
    Unsupported test formats get score None, which summarize() leaves out of the averages.
    """
    split = SPLITS.get(split, split)
    fmt = item.get("test_format", "assert_list")
    base = {"id": item["id"], "source": item["source"], "split": split,
            "latency_s": latency_s, "output_tokens": output_tokens}
    if fmt not in SCORABLE_FORMATS:
        # Don't report a fake 0.0: summarize() skips None when averaging.
        return {**base, "score": None, "test_pass_rate": None, "rubric_level": None, "syntax_ok": None,
                "failure_type": None, "n_tests": 0, "n_passed": 0, "details": [],
                "error": f"no test runner for test_format={fmt!r} yet"}
    tests = get_tests(item, split)
    code = extract_code(output, item.get("entry_point"))
    syntax_ok = bool(code.strip()) and _parses(code)
    if syntax_ok:
        r = run_tests(code, tests, fmt, item.get("entry_point", ""), item["source"])
        details, error = r["details"], r["error"]
    else:
        error = "no code in the answer" if not code.strip() else _syntax_error(code)
        details = [{"i": i, "status": "load_error", "test": _test_text(t), "expected": None, "actual": None,
                    "error": error} for i, t in enumerate(tests)]
    n, passed = len(tests), sum(d["status"] == "pass" for d in details)
    return {**base,
            "score": 1.0 if n and passed == n else 0.0,
            "test_pass_rate": passed / n if n else 0.0,
            "rubric_level": rubric_level(syntax_ok, passed, n),
            "syntax_ok": syntax_ok,
            "failure_type": failure_type(syntax_ok, code, details),
            "n_tests": n, "n_passed": passed,
            "passed_tests": [d["i"] for d in details if d["status"] == "pass"],
            "details": details if keep_details else [],
            "error": error}


def _syntax_error(code: str) -> str:
    try:
        ast.parse(code)
    except SyntaxError as e:
        return _short(f"SyntaxError: {e.msg} (line {e.lineno})")
    except ValueError as e:
        return _short(f"ValueError: {e}")
    return None


# =====================================================================
# FEEDBACK FOR THE RETRY LOOP
# =====================================================================

# Turn a PUBLIC evaluate() result into text for a hint prompt: the first `max_tests` failing tests
# with expected / actual / error. Refuses private results, so hidden tests can't leak into a prompt.
def format_feedback(result: dict, max_tests: int = 1) -> str:
    if result.get("split") != "public":
        raise ValueError("format_feedback only accepts public-test results; hidden tests are never shown")
    if result.get("score") == 1.0:
        return "All public tests passed."
    if result.get("failure_type") in ("no_code", "syntax_error"):
        return f"Your answer could not be run: {result['error']}"
    failing = [d for d in result["details"] if d["status"] != "pass"][:max_tests]
    if failing and failing[0]["status"] == "load_error":
        return f"Your code crashed before any test could run: {failing[0]['error']}"
    parts = [f"{result['n_tests'] - result['n_passed']} of {result['n_tests']} public tests failed."]
    labels = {"wrong_answer": "wrong answer", "runtime_error": "runtime error", "timeout": "time limit exceeded"}
    for d in failing:
        test_label = "Input" if result.get("source") == "livecodebench" else "Test"
        lines = [f"Failing test ({labels.get(d['status'], d['status'])}):", _field(test_label, d["test"])]
        if d.get("expected") is not None:
            lines.append(_field("Expected", d["expected"]))
        if d.get("actual") is not None and d["status"] == "wrong_answer":
            lines.append(_field("Got", d["actual"]))
        if d.get("error") and d["status"] != "wrong_answer":
            lines.append(f"  Error: {d['error']}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# One "  Label: value" line; multi-line values (stdin input / output) go in an indented block.
def _field(label: str, value) -> str:
    value = str(value).rstrip("\n")
    if "\n" not in value:
        return f"  {label}: {value}"
    return f"  {label}:\n" + "\n".join("    " + ln for ln in value.splitlines())


# Roll up a list of evaluate() results into overall + per-dataset averages.
def summarize(results: list) -> dict:
    """Overall and per-dataset means: the row you'd put in a comparison table."""
    def agg(rs):
        def mean(k):
            v = [r[k] for r in rs if r.get(k) is not None]
            return round(sum(v) / len(v), 3) if v else None
        return {"n": len(rs), "pass@1": mean("score"), "test_pass_rate": mean("test_pass_rate"),
                "rubric_level": mean("rubric_level"), "latency_s": mean("latency_s"),
                "output_tokens": mean("output_tokens")}
    out = {"overall": agg(results)}
    for src in sorted({r["source"] for r in results}):
        out[src] = agg([r for r in results if r["source"] == src])
    return out


# =====================================================================
# SELF-TEST - run `python Evaluator/evaluator.py` to check everything still works.
# Add --reference to also score every MBPP reference solution on its hidden tests.
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
    mbpp["entry_point"] = "add"

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
        print("ok", item["id"], r["score"], r["failure_type"], r["error"])

    # Partial credit check: passes 1 of 2 MBPP asserts.
    r = evaluate(mbpp, "def add(a, b):\n    return 3", 0.0)
    assert r["score"] == 0.0 and r["test_pass_rate"] == 0.5 and r["rubric_level"] == 3, r

    # Per-test detail: expected / actual for `assert f(x) == y`.
    r = evaluate(mbpp, "def add(a, b):\n    return a - b")
    d = r["details"][0]
    assert d["status"] == "wrong_answer" and d["expected"] == "3" and d["actual"] == "-1", d
    assert r["failure_type"] == "wrong_answer" and r["rubric_level"] == 1, r
    assert "Expected: 3" in format_feedback(r) and "Got: -1" in format_feedback(r)
    # Runtime error points at the line in the candidate's code.
    r = evaluate(mbpp, "def add(a, b):\n    x = [a]\n    return x[5]")
    assert r["details"][0]["status"] == "runtime_error" and "IndexError" in r["details"][0]["error"], r
    assert "line 3" in r["details"][0]["error"], r["details"][0]
    # Timeout is per test, and is reported as such.
    r = evaluate(mbpp, "def add(a, b):\n    while True: pass")
    assert r["failure_type"] == "timeout", r
    # Syntax errors are rubric level 0 and never run.
    r = evaluate(mbpp, "def add(a, b) return a")
    assert r["rubric_level"] == 0 and not r["syntax_ok"] and r["failure_type"] == "syntax_error", r
    # Code that crashes on import.
    r = evaluate(mbpp, "import not_a_real_module\ndef add(a, b): return a + b")
    assert r["details"][0]["status"] == "load_error" and "ModuleNotFoundError" in r["error"], r
    # Printing inside the solution doesn't break the harness.
    assert evaluate(mbpp, "def add(a, b):\n    print('hi', a)\n    return a + b")["score"] == 1.0

    # extract_code: truncated answer (opening fence, no closing fence) and prose before code.
    assert extract_code("Here you go:\n```python\ndef add(a, b):\n    return a + b\n") .startswith("def add")
    assert extract_code("Sure!\n```python\ndef add(a, b):\n    return a + b\nprint(add(1,") == \
        "def add(a, b):\n    return a + b"
    assert extract_code("The answer is below.\ndef add(a, b):\n    return a + b") == "def add(a, b):\n    return a + b"
    # Prefer the block that defines the entry point over an earlier example block.
    two = "```python\nprint(add(1, 2))\n```\n\n```python\ndef add(a, b):\n    return a + b\n```"
    assert evaluate(mbpp, two)["score"] == 1.0

    # LiveCodeBench stdin tests: program reads stdin, prints the answer.
    lcb = {"id": "livecodebench-x", "source": "livecodebench", "test_format": "stdin_io", "entry_point": "",
           "tests": [{"input": "1 2\n", "output": "3\n", "testtype": "stdin"},
                     {"input": "5 5\n", "output": "10", "testtype": "stdin"}]}
    assert evaluate(lcb, "a, b = map(int, input().split())\nprint(a + b)")["score"] == 1.0
    r = evaluate(lcb, "a, b = map(int, input().split())\nprint(a * b)")
    assert r["test_pass_rate"] == 0.0 and r["details"][0]["actual"].strip() == "2", r
    r = evaluate(lcb, "import sys\nx = sys.stdin.read().split()\nprint(x[5])")
    assert r["details"][0]["status"] == "runtime_error" and "IndexError" in r["details"][0]["error"], r
    assert evaluate(lcb, "while True: pass")["failure_type"] == "timeout"
    assert outputs_match("0.3333333\n", "0.33333333") and not outputs_match("1 2", "1 3")
    # main() guarded by __name__ == "__main__" still runs.
    assert evaluate(lcb, "def main():\n    a, b = map(int, input().split())\n    print(a + b)\n"
                         "if __name__ == '__main__':\n    main()")["score"] == 1.0

    # LiveCodeBench functional tests: class Solution, one JSON value per line of input.
    fn = {"id": "livecodebench-y", "source": "livecodebench", "test_format": "functional_io",
          "entry_point": "addAll", "tests": [{"input": "[1, 2, 3]\n4", "output": "10", "testtype": "functional"},
                                             {"input": "[]\n0", "output": "0", "testtype": "functional"}]}
    good = "class Solution:\n    def addAll(self, nums: List[int], k: int) -> int:\n        return sum(nums) + k"
    assert evaluate(fn, good)["score"] == 1.0  # List works without an import (LiveCodeBench header)
    r = evaluate(fn, good.replace("+ k", "- k"))
    assert r["details"][0]["expected"] == "10" and r["details"][0]["actual"] == "2", r["details"][0]

    # check_fn items (HumanEvalFix style): the test calls check() on the entry point itself.
    fix = {"id": "fix-x", "source": "humanevalfix", "test_format": "check_fn",
           "tests": ["def check(f):\n    assert f(2) == 4\n\ncheck(double)"]}
    assert evaluate(fix, "```python\ndef double(x):\n    return x * 2\n```")["score"] == 1.0
    assert evaluate(fix, "def double(x):\n    return x + 3")["score"] == 0.0

    # Hidden tests are scored but never formatted as feedback.
    hid = {**mbpp, "private_tests": ["assert add(10, 5) == 15"]}
    r = evaluate(hid, "def add(a, b):\n    return a + b", split="private")
    assert r["split"] == "private" and r["score"] == 1.0
    try:
        format_feedback(r)
        raise AssertionError("private feedback should be refused")
    except ValueError:
        pass

    print(summarize([evaluate(mbpp, cases[0][1], 1.0, 50), evaluate(he, cases[5][1], 2.0, 70)]))

    # The final dataset, if it has been built: every item has the fields evaluate() needs.
    if DATASET_PATH.exists():
        items = load_items()
        assert items and all({"id", "source", "prompt", "tests", "test_format"} <= it.keys() for it in items)
        print(f"ok load_items: {len(items)} scorable code-generation items from {DATASET_PATH.name}")
        if "--reference" in sys.argv and PRIVATE_TESTS_PATH.exists():
            # Every MBPP reference must pass its public AND hidden tests, or the scorer is wrong.
            for it in [i for i in items if i["source"] == "mbpp"]:
                ref = "```python\n" + it["reference"] + "\n```"
                for sp in ("public", "private"):
                    r = evaluate(it, ref, split=sp)
                    assert r["score"] == 1.0, (it["id"], sp, r["error"], r["details"][:2])
            print("ok reference solutions pass public + hidden tests on every MBPP task")
    print("ALL TESTS PASSED")
