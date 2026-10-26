"""
self_test.py

One command to check that the rubric and the pipeline work, with no API calls and no files
written. Run it from the repo root after any change to the evaluator, prompts or baseline:
    python Evaluator/self_test.py

1. Evaluator: every test format (a pass and a fail case each), code extraction, the rubric
   levels and their names, the LiveCodeBench import header, the test processes (no stdin, no
   API keys), and that hidden-test results never become feedback.
2. Real data: the hand-written LiveCodeBench solutions in Evaluator/fixtures.json and every
   MBPP reference solution must pass their public AND hidden tests, so the runners agree with
   the dataset.
3. Pipeline: every prompt level and retry-arm prompt builds without leaking the reference or
   hidden tests; the no-API `reference` provider goes through baseline.py's run_one and
   summarize_run (hidden headline, public beside it, failed runs); compare_runs refuses runs on
   different tasks or scoring versions.

evaluator.py keeps its own self-test too (python Evaluator/evaluator.py).
"""

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Evaluator.evaluator import (DATASET_PATH, PRIVATE_TESTS_PATH, SCORING_VERSION, evaluate, extract_code,
                                 format_feedback, load_items, load_private_tests)

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures.json"
F = "```"  # a markdown fence


def check(name: str, cond: bool, detail=""):
    assert cond, f"{name}: {detail}"
    print("ok", name)


# Small items using the dataset's field names.
ADD = {"id": "mbpp-x", "source": "mbpp", "test_format": "assert_list", "entry_point": "add",
       "tests": ["assert add(1, 2) == 3", "assert add(-1, 1) == 0", "assert add(0, 0) == 0", "assert add(2, 2) == 4"]}
ADD_ONE = {**ADD, "tests": ADD["tests"][:1]}  # one test, so a timeout costs one per-test limit, not four
DOUBLE_CHECK = {"id": "humanevalfix-x", "source": "humanevalfix", "test_format": "check_fn", "entry_point": "double",
                "tests": ["def check(f):\n    assert f(2) == 4\n    assert f(0) == 0\n\ncheck(double)"]}
DOUBLE_TESTFN = {"id": "quixbugs-x", "source": "quixbugs", "test_format": "test_functions", "entry_point": "double",
                 "tests": ["def test1():\n    assert double(3) == 6\n    assert double(0) == 0\n\ntest1()"]}
SUM_STDIN = {"id": "livecodebench-x", "source": "livecodebench", "test_format": "stdin_io", "entry_point": "",
             "tests": [{"input": "1 2", "output": "3", "testtype": "stdin"},
                       {"input": "6 4\n", "output": "10\n", "testtype": "stdin"}]}
ADDALL_FN = {"id": "livecodebench-y", "source": "livecodebench", "test_format": "functional_io",
             "entry_point": "addAll",
             "tests": [{"input": "[1, 2, 3]\n4", "output": "10", "testtype": "functional"},
                       {"input": "[]\n0", "output": "0", "testtype": "functional"}]}


def formats():
    good_add, good_double = "def add(a, b):\n    return a + b", "def double(x):\n    return x * 2"
    cases = [  # (name, item, answer, expected pass@1)
        ("assert_list pass", ADD, good_add, 1.0),
        ("assert_list fail", ADD, "def add(a, b):\n    return a + b + 1", 0.0),
        ("check_fn pass", DOUBLE_CHECK, good_double, 1.0),
        ("check_fn fail", DOUBLE_CHECK, "def double(x):\n    return x + 2", 0.0),
        ("test_functions pass", DOUBLE_TESTFN, good_double, 1.0),
        ("test_functions fail", DOUBLE_TESTFN, "def double(x):\n    return x + 3", 0.0),
        ("stdin_io pass", SUM_STDIN, "a, b = map(int, input().split())\nprint(a + b)", 1.0),
        ("stdin_io fail", SUM_STDIN, "a, b = map(int, input().split())\nprint(a * b)", 0.0),
        ("functional_io pass", ADDALL_FN,
         "class Solution:\n    def addAll(self, nums: List[int], k: int) -> int:\n        return sum(nums) + k", 1.0),
        ("functional_io fail", ADDALL_FN,
         "class Solution:\n    def addAll(self, nums: List[int], k: int) -> int:\n        return sum(nums) - k", 0.0),
    ]
    for name, item, answer, want in cases:
        r = evaluate(item, F + "python\n" + answer + "\n" + F)
        check(name, r["score"] == want, r)


def extraction():
    good = "def add(a, b):\n    return a + b"
    check("extract: bash block before the code",
          extract_code(f"Run this first:\n{F}bash\npip install nothing\n{F}\nThen:\n{F}python\n{good}\n{F}", "add") == good)
    check("extract: text block before the code",
          extract_code(f"{F}text\nsome notes\n{F}\nCode:\n{F}python\n{good}\n{F}", "add") == good)
    check("extract: python3 tag", extract_code(f"{F}python3\n{good}\n{F}", "add") == good)
    check("extract: Python tag in capitals", extract_code(f"{F}Python\n{good}\n{F}", "add") == good)
    check("extract: indented fence (inside a list)",
          extract_code(f"1. The code:\n   {F}python\n   def add(a, b):\n       return a + b\n   {F}", "add") == good)
    check("extract: solution first, usage after",
          extract_code(f"{F}python\n{good}\n{F}\nUsage:\n{F}python\nprint(add(1, 2))\n{F}", "add") == good)
    draft = "def add(a, b):\n    return a - b"
    check("extract: draft then fix -> the first block that defines the function (Harold's order)",
          extract_code(f"{F}python\n{draft}\n{F}\nFixed:\n{F}python\n{good}\n{F}", "add") == draft)
    check("extract: cut off mid-line -> the code without the half-written line",
          extract_code(f"Sure:\n{F}python\n{good}\nprint(add(1,", "add") == good)
    check("extract: no fence, prose first", extract_code(f"Here is the function.\n{good}", "add") == good)


def levels():
    cases = [  # (name, item, answer, rubric_level, level name, failure_type)
        ("Pass (4)", ADD, "def add(a, b):\n    return a + b", 4, "Pass", None),
        ("Mostly Pass (3): 3 of 4", ADD, "def add(a, b):\n    return a + b if a >= 0 else 99", 3, "Mostly Pass",
         "wrong_answer"),
        ("Partial Pass (2): 1 of 4", ADD, "def add(a, b):\n    return 3", 2, "Partial Pass", "wrong_answer"),
        ("Wrong (1): runs, every answer wrong", ADD, "def add(a, b):\n    return a + b + 1", 1, "Wrong", "wrong_answer"),
        ("Error (0): syntax error", ADD, "def add(a, b) return a", 0, "Error", "syntax_error"),
        ("Error (0): no code", ADD, "", 0, "Error", "no_code"),
        ("Error (0): crash on import", ADD, "import not_a_real_module\ndef add(a, b): return a + b", 0, "Error",
         "load_error"),
        ("Error (0): crashes on every test", ADD, "def add(a, b):\n    return [a][5]", 0, "Error", "runtime_error"),
        ("Timeout (0)", ADD_ONE, "def add(a, b):\n    while True: pass", 0, "Timeout", "timeout"),
        # No test passes and the failures are mixed: the first failing test decides.
        ("mixed, first failure is a wrong answer -> Wrong (1)", ADD,
         "def add(a, b):\n    return a + b + 1 if a > 0 else [][0]", 1, "Wrong", "wrong_answer"),
        ("mixed, first failure is a crash -> Error (0)", ADD,
         "def add(a, b):\n    return [][0] if a > 0 else a + b + 1", 0, "Error", "runtime_error"),
    ]
    for name, item, answer, lvl, lvl_name, failure in cases:
        r = evaluate(item, answer)
        check(f"level {name}", (r["rubric_level"], r["level"], r["failure_type"]) == (lvl, lvl_name, failure),
              (r["rubric_level"], r["level"], r["failure_type"], r["error"]))


def lcb_header():
    fn = {**ADDALL_FN, "tests": [{"input": "[4, 6]\n0", "output": "2", "testtype": "functional"}]}
    code = "class Solution:\n    def addAll(self, nums, k):\n        return gcd(nums[0], nums[1]) if inf > 0 else k"
    check("LCB header: inf and gcd without imports (functional_io)", evaluate(fn, code)["score"] == 1.0)
    st = {**SUM_STDIN, "tests": [{"input": "4 6", "output": "2", "testtype": "stdin"}]}
    check("LCB header: gcd without import (stdin_io)",
          evaluate(st, "a, b = map(int, input().split())\nprint(gcd(a, b))")["score"] == 1.0)
    r = evaluate(ADD, "def add(a, b):\n    return gcd(a, b) * 0 + a + b")
    check("no header for MBPP: gcd is not defined", r["score"] == 0.0 and "NameError" in (r["error"] or ""), r["error"])


def test_processes():
    item = {**ADD, "tests": ["assert f() == 1"]}
    start = time.time()
    r = evaluate(item, "def f():\n    return int(input())")
    elapsed = time.time() - start
    check("input() in a function test fails at once (stdin is closed)",
          r["details"][0]["status"] == "runtime_error" and "EOFError" in r["details"][0]["error"] and elapsed < 3,
          (r["details"][0], round(elapsed, 1)))

    old = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-self-test-not-a-real-key"
    try:
        r = evaluate({**ADD, "tests": ["assert f() is None"]},
                     "def f():\n    import os\n    return os.environ.get('ANTHROPIC_API_KEY')")
        check("code under test can't read ANTHROPIC_API_KEY (function test)", r["score"] == 1.0, r["details"])
        st = {**SUM_STDIN, "tests": [{"input": "", "output": "None", "testtype": "stdin"}]}
        r = evaluate(st, "import os\nprint(os.environ.get('ANTHROPIC_API_KEY'))")
        check("code under test can't read ANTHROPIC_API_KEY (stdin program)", r["score"] == 1.0, r["details"])
    finally:
        if old is None:
            del os.environ["ANTHROPIC_API_KEY"]
        else:
            os.environ["ANTHROPIC_API_KEY"] = old


def hidden_feedback():
    item = {**ADD, "private_tests": ["assert add(10, 5) == 15"]}
    r = evaluate(item, "def add(a, b):\n    return a - b", split="private")
    try:
        format_feedback(r)
        refused = False
    except ValueError:
        refused = True
    check("format_feedback refuses hidden-test results", refused)
    check("public results still give feedback", "Got: -1" in format_feedback(evaluate(ADD, "def add(a, b):\n    return a - b")))


# Real data: hand-written LiveCodeBench solutions and every MBPP reference must pass public AND hidden tests.
def dataset():
    for path in (DATASET_PATH, PRIVATE_TESTS_PATH, FIXTURES_PATH):
        assert path.exists(), f"{path} not found (the data files are in git; pull, or rebuild with the notebooks)"
    items = {it["id"]: it for it in load_items()}
    fixtures = {k: v for k, v in json.loads(FIXTURES_PATH.read_text()).items() if not k.startswith("_")}
    answers = [(i, code) for i, code in fixtures.items()]
    answers += [(i, it["reference"]) for i, it in items.items() if it["source"] == "mbpp"]
    start = time.time()
    for task_id, code in answers:
        for split in ("public", "private"):
            r = evaluate(items[task_id], F + "python\n" + code + "\n" + F, split=split)
            bad = [(d["i"], d["status"], d["error"]) for d in r["details"] if d["status"] != "pass"][:2]
            assert r["score"] == 1.0, (task_id, split, r["error"], bad)
    n_fix = len(fixtures)
    print(f"ok {n_fix} LiveCodeBench fixtures and {len(answers) - n_fix} MBPP references pass public + hidden tests "
          f"({time.time() - start:.0f}s)")


# Every string inside a result (nested dicts and lists), to search for leaked hidden-test text.
def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


# Prompts, retry prompts, baseline.py and compare_runs.py, all in memory with the no-API reference provider.
def pipeline():
    from AI_models import retry_prompts as rp
    from AI_models.prompts import ALL_LEVELS, build_prompt
    from Baseline.baseline import run_one, summarize_run
    from Baseline.compare_runs import check_same_scoring, check_same_tasks

    items = load_items()
    hidden = load_private_tests()
    for it in items:
        ref = (it.get("reference") or "").strip()
        for lvl in ALL_LEVELS:
            p = build_prompt(it, lvl)
            assert p.strip() and not (ref and ref in p), (it["id"], lvl)
    check(f"prompts: {len(ALL_LEVELS)} levels build for all {len(items)} tasks, no reference in any", True)

    # Retry prompts get the previous code and PUBLIC feedback only.
    mbpp = next(it for it in items if it["source"] == "mbpp")
    wrong = f"def {mbpp['entry_point']}(*args):\n    return None"
    fb = format_feedback(evaluate(mbpp, wrong))
    prompts = [rp.bare_retry(mbpp["prompt"], wrong), rp.reflect_fix(mbpp["prompt"], wrong, fb),
               rp.critic_review(mbpp["prompt"], wrong, fb), rp.critic_fix(mbpp["prompt"], wrong, fb, "- returns None")]
    leaked = [t for t in hidden[mbpp["id"]] for p in prompts if t in p]
    check("retry prompts: previous code + public feedback, no hidden test",
          all(wrong in p for p in prompts) and fb in prompts[1] and not leaked, leaked[:1])

    # baseline.py: the reference provider must pass hidden and public tests, and keep hidden test text out of results.
    mbpp_items = [it for it in items if it["source"] == "mbpp"][:3]
    lcb_item = next(it for it in items if it["source"] == "livecodebench")  # no reference -> failed run
    results = [run_one("reference", None, it) for it in mbpp_items + [lcb_item]]
    ok = all(r["scored_on"] == "hidden" and r["score"] == 1.0 and r["public"]["score"] == 1.0
             and r["level"] == "Pass" and r["false_pass"] is False for r in results[:3])
    check("baseline: reference answers pass hidden (headline) and public tests", ok, results[0])
    failed = results[3]
    check("baseline: a provider error is a failed run with score 0 and no level",
          failed["failed_run"] and failed["score"] == 0.0 and failed["level"] is None, failed)
    texts = list(_strings(results))
    leaked = [t for it in mbpp_items for t in hidden[it["id"]] if any(t[:200] in s for s in texts)]
    check("baseline: no hidden test text in the results", not leaked, leaked[:1])
    s = summarize_run(results)
    check("baseline: summary has hidden pass@1, public pass@1, false passes, levels, failed runs",
          s["overall"]["pass@1"] == 0.75 and s["public_pass@1"] == 0.75 and s["false_passes"] == 0
          and s["overall"]["levels"] == {"Pass": 3} and s["failed_runs"] == 1, s)

    # compare_runs: same tasks and same scoring version, or it stops.
    run = {"_file": "a_run.json", "scoring_version": SCORING_VERSION, "results": results}
    check_same_tasks([run, {**run, "_file": "b_run.json"}])
    check_same_scoring([run, {**run, "_file": "b_run.json"}])
    for name, fn, other in [("different tasks", check_same_tasks, {**run, "_file": "b_run.json", "results": results[:2]}),
                            ("an older scoring version", check_same_scoring,  # no field = version 1
                             {"_file": "old_run.json", "results": results})]:
        try:
            fn([run, other])
            refused = False
        except SystemExit:
            refused = True
        check(f"compare_runs refuses runs with {name}", refused)


if __name__ == "__main__":
    t0 = time.time()
    formats()
    extraction()
    levels()
    lcb_header()
    test_processes()
    hidden_feedback()
    dataset()
    pipeline()
    print(f"ALL TESTS PASSED ({time.time() - t0:.0f}s)")
