"""
self_test.py

One command to check that the data flows through the rubric and the pipeline correctly, with no
API calls and no files written. Run it from the repo root after any change to the data, the
evaluator, the prompts or the baseline:
    python Evaluator/self_test.py

Everything runs on the real code-generation tasks in data/unified/unified_eval.jsonl, with their
real public tests (`tests`) and real hidden tests (unified_private_tests.jsonl.gz):
1. Data: every task's public and hidden tests are read (the counts match the files and the
   metadata); correct code passes them (the MBPP references, and Evaluator/fixtures.json for
   LiveCodeBench, which ships no references); a do-nothing answer fails every task's hidden tests.
2. Evaluator: a pass and a fail per test format, every rubric level, code extraction from
   different reply shapes, the LiveCodeBench import header, the subprocess isolation (no stdin,
   no API keys), and feedback that shows public tests only.
3. Pipeline: prompts and retry prompts, baseline.py's run_one / summarize_run (hidden tests as
   the headline, public beside them), and compare_runs' guards.
The hand-written parts are answers and edge cases only (broken code, odd reply formats); the
tests they are scored on are always the real ones.

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


def fenced(code: str) -> str:
    return f"{F}python\n{code}\n{F}"


# A do-nothing answer in the shape each format expects: it runs, but answers nothing.
def stub(item: dict) -> str:
    if item["test_format"] == "stdin_io":
        return "pass"
    if item["test_format"] == "functional_io":
        return f"class Solution:\n    def {item['entry_point']}(self, *args):\n        return None"
    return f"def {item['entry_point']}(*args, **kwargs):\n    return None"


# The real tasks the checks use.
def load():
    for path in (DATASET_PATH, PRIVATE_TESTS_PATH, FIXTURES_PATH):
        assert path.exists(), f"{path} not found (the data files are in git; pull, or rebuild with the notebooks)"
    items = {it["id"]: it for it in load_items(scorable_only=False)}  # every code-generation task
    hidden = load_private_tests()
    fixtures = {k: v for k, v in json.loads(FIXTURES_PATH.read_text()).items() if not k.startswith("_")}
    return items, hidden, fixtures


# =====================================================================
# 1. DATA: the real tests are read, correct code passes them, wrong code fails them
# =====================================================================
def data(items, hidden, fixtures):
    check(f"data: all {len(items)} code-generation tasks have a test runner",
          len(load_items()) == len(items))
    check(f"data: hidden tests exist for exactly the {len(items)} code-generation tasks", set(hidden) == set(items),
          sorted(set(hidden) ^ set(items))[:5])

    # Every task: evaluate() sees as many tests as the files hold, and a do-nothing answer fails the hidden ones.
    start, n_public, n_hidden = time.time(), 0, 0
    for it in items.values():
        pub = evaluate(it, stub(it), split="public")
        hid = evaluate(it, stub(it), split="private", keep_details=False)
        assert pub["n_tests"] == len(it["tests"]) > 0, (it["id"], "public count", pub["n_tests"])
        assert hid["n_tests"] == len(hidden[it["id"]]) == it["metadata"]["num_private_tests"], \
            (it["id"], "hidden count", hid["n_tests"], it["metadata"]["num_private_tests"])
        assert hid["score"] == 0.0, (it["id"], "a do-nothing answer passes every hidden test")
        n_public, n_hidden = n_public + pub["n_tests"], n_hidden + hid["n_tests"]
    check(f"data: {n_public} public + {n_hidden} hidden tests read for {len(items)} tasks; a do-nothing answer "
          f"fails the hidden tests of every task ({time.time() - start:.0f}s)", True)

    # Correct code passes every real test: MBPP references, and the hand-written LiveCodeBench solutions.
    start = time.time()
    answers = [(i, it["reference"]) for i, it in items.items() if it["source"] == "mbpp"] + list(fixtures.items())
    for task_id, code in answers:
        for split in ("public", "private"):
            r = evaluate(items[task_id], fenced(code), split=split)
            bad = [(d["i"], d["status"], d["error"]) for d in r["details"] if d["status"] != "pass"][:2]
            assert r["score"] == 1.0, (task_id, split, r["error"], bad)
    n_ref = sum(1 for it in items.values() if it["source"] == "mbpp")
    check(f"data: {n_ref} MBPP references and {len(fixtures)} LiveCodeBench solutions pass all their public and "
          f"hidden tests ({time.time() - start:.0f}s)", True)

    # Public stdin outputs have no trailing newline, hidden ones do: the stdin solutions pass both.
    stdin_ids = [i for i in fixtures if items[i]["test_format"] == "stdin_io"]
    no_nl = sum(not t["output"].endswith("\n") for i in stdin_ids for t in items[i]["tests"])
    with_nl = sum(t["output"].endswith("\n") for i in stdin_ids for t in hidden[i])
    check(f"data: stdin output compare handles {no_nl} public outputs without and {with_nl} hidden outputs with "
          f"a trailing newline", no_nl > 0 and with_nl > 0)


# =====================================================================
# 2. EVALUATOR, on real tasks
# =====================================================================
def formats(items, fixtures):
    examples = {"assert_list": next(it for it in items.values() if it["source"] == "mbpp")}
    for task_id in fixtures:
        examples.setdefault(items[task_id]["test_format"], items[task_id])
    for fmt, it in sorted(examples.items()):
        good = it["reference"] or fixtures[it["id"]]
        r_pass, r_fail = evaluate(it, fenced(good)), evaluate(it, fenced(stub(it)))
        check(f"format {fmt} ({it['id']}): correct code passes, a do-nothing answer fails",
              r_pass["score"] == 1.0 and r_fail["score"] == 0.0, (r_pass["error"], r_fail["score"]))


# An answer that is the reference for its first k calls and returns None after that. Tests share one
# process, so with one call per test it passes exactly the first k tests.
def first_k_correct(item: dict, k: int) -> str:
    ep = item["entry_point"]
    return (f"{item['reference']}\n\n_correct, _calls = {ep}, [0]\n\n"
            f"def {ep}(*args, **kwargs):\n    _calls[0] += 1\n"
            f"    return _correct(*args, **kwargs) if _calls[0] <= {k} else None\n")


def levels(items):
    it = next(i for i in items.values() if i["source"] == "mbpp" and i["reference"].count(i["entry_point"] + "(") == 1)
    ep, ref = it["entry_point"], it["reference"]
    n_hidden = len(load_private_tests()[it["id"]])
    one_test = {**it, "tests": it["tests"][:1]}  # one real test, so the timeout case costs one time limit
    cases = [  # (name, item, answer, split, rubric_level, level, failure_type)
        ("Pass (4): the reference", it, ref, "private", 4, "Pass", None),
        (f"Mostly Pass (3): right on {n_hidden - 1} of {n_hidden} hidden tests", it, first_k_correct(it, n_hidden - 1),
         "private", 3, "Mostly Pass", "wrong_answer"),
        (f"Partial Pass (2): right on 1 of {n_hidden} hidden tests", it, first_k_correct(it, 1), "private", 2,
         "Partial Pass", "wrong_answer"),
        ("Wrong (1): runs, every answer wrong", it, stub(it), "public", 1, "Wrong", "wrong_answer"),
        ("Error (0): syntax error", it, ref.replace(":", "", 1), "public", 0, "Error", "syntax_error"),
        ("Error (0): no code", it, "", "public", 0, "Error", "no_code"),
        ("Error (0): crash on import", it, "import not_a_real_module\n" + ref, "public", 0, "Error", "load_error"),
        ("Error (0): crashes on every test", it, f"def {ep}(*args, **kwargs):\n    return [][0]", "public", 0,
         "Error", "runtime_error"),
        ("Timeout (0)", one_test, f"def {ep}(*args, **kwargs):\n    while True: pass", "public", 0, "Timeout",
         "timeout"),
        # No test passes and the failures are mixed: the first failing test decides.
        ("mixed, first failure a wrong answer -> Wrong (1)", it,
         f"_calls = [0]\ndef {ep}(*args, **kwargs):\n    _calls[0] += 1\n    return None if _calls[0] == 1 else [][0]",
         "public", 1, "Wrong", "wrong_answer"),
        ("mixed, first failure a crash -> Error (0)", it,
         f"_calls = [0]\ndef {ep}(*args, **kwargs):\n    _calls[0] += 1\n    return [][0] if _calls[0] == 1 else None",
         "public", 0, "Error", "runtime_error"),
    ]
    for name, item, answer, split, lvl, lvl_name, failure in cases:
        r = evaluate(item, answer, split=split)
        check(f"level {name} [{it['id']} {split} tests]",
              (r["rubric_level"], r["level"], r["failure_type"]) == (lvl, lvl_name, failure),
              (r["rubric_level"], r["level"], r["failure_type"], r["n_passed"], r["error"]))


def extraction(items, fixtures):
    it = next(i for i in items.values() if i["source"] == "mbpp")
    ep, ref = it["entry_point"], it["reference"].strip()
    replies = {
        "bash block before the code": f"Run this first:\n{F}bash\npip install nothing\n{F}\nThen:\n{fenced(ref)}",
        "text block before the code": f"{F}text\nsome notes\n{F}\nCode:\n{fenced(ref)}",
        "python3 tag": f"{F}python3\n{ref}\n{F}",
        "Python tag in capitals": f"{F}Python\n{ref}\n{F}",
        "indented fence (inside a list)": "1. The code:\n   " + fenced(ref).replace("\n", "\n   "),
        "solution first, usage after": f"{fenced(ref)}\nUsage:\n{F}python\nprint({ep}(1))\n{F}",
        "cut off mid-line (no closing fence)": f"Sure:\n{F}python\n{ref}\nprint({ep}(",
        "no fence, prose first": f"Here is the function.\n{ref}",
    }
    for name, reply in replies.items():
        r = evaluate(it, reply)
        check(f"extract: {name} -> passes {it['id']}'s real tests", r["score"] == 1.0, (extract_code(reply, ep), r["error"]))
    draft_then_fix = f"{fenced(stub(it))}\nFixed:\n{fenced(ref)}"
    check("extract: draft then fix -> the first block that defines the function (Harold's order)",
          extract_code(draft_then_fix, ep) == stub(it))
    st = next(items[i] for i in fixtures if items[i]["test_format"] == "stdin_io")
    reply = f"Compile nothing:\n{F}bash\npython3 main.py < in.txt\n{F}\n{fenced(fixtures[st['id']])}"
    check(f"extract: bash block before a stdin program -> passes {st['id']}'s real tests",
          evaluate(st, reply)["score"] == 1.0)


def lcb_header(items, fixtures):
    fn = items["livecodebench-3720"]
    # Correct, but uses inf, heappush and heappop without importing them (LiveCodeBench's header provides them).
    code = ("class Solution:\n    def minMaxWeight(self, n, edges, threshold):\n"
            "        into = [[] for _ in range(n)]\n        for a, b, w in edges:\n            into[b].append((a, w))\n"
            "        best = [inf] * n\n        best[0] = 0\n        heap = [(0, 0)]\n        while heap:\n"
            "            d, u = heappop(heap)\n            if d > best[u]:\n                continue\n"
            "            for v, w in into[u]:\n                if max(d, w) < best[v]:\n"
            "                    best[v] = max(d, w)\n                    heappush(heap, (best[v], v))\n"
            "        return -1 if inf in best else max(best)")
    ok = all(evaluate(fn, fenced(code), split=s)["score"] == 1.0 for s in ("public", "private"))
    check(f"LCB header: inf / heappush / heappop without imports pass {fn['id']}'s real tests", ok)
    st = items["livecodebench-abc387_b"]
    code = "X = int(input())\nprint(sum(prod(p) for p in product(range(1, 10), repeat=2) if prod(p) != X))"
    ok = all(evaluate(st, fenced(code), split=s)["score"] == 1.0 for s in ("public", "private"))
    check(f"LCB header: prod / product without imports pass {st['id']}'s real tests", ok)
    mb = next(i for i in items.values() if i["source"] == "mbpp")
    r = evaluate(mb, f"def {mb['entry_point']}(*args, **kwargs):\n    return gcd(1, 1)")
    check(f"no header for MBPP: gcd is not defined ({mb['id']})", "NameError" in (r["error"] or ""), r["error"])


def isolation(items, fixtures):
    it = next(i for i in items.values() if i["source"] == "mbpp")
    start = time.time()
    r = evaluate(it, f"def {it['entry_point']}(*args, **kwargs):\n    return input()")
    elapsed = time.time() - start
    first = r["details"][0]
    check("input() in a function test fails at once (stdin is closed)",
          first["status"] == "runtime_error" and "EOFError" in first["error"] and elapsed < 3, (first, round(elapsed, 1)))

    guard = "import os\nassert os.environ.get('ANTHROPIC_API_KEY') is None, 'the API key is visible'\n"
    st = next(items[i] for i in fixtures if items[i]["test_format"] == "stdin_io")
    old = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-self-test-not-a-real-key"
    try:
        check(f"code under test can't read ANTHROPIC_API_KEY ({it['id']}, function tests)",
              evaluate(it, fenced(guard + it["reference"]))["score"] == 1.0)
        check(f"code under test can't read ANTHROPIC_API_KEY ({st['id']}, stdin program)",
              evaluate(st, fenced(guard + fixtures[st["id"]]))["score"] == 1.0)
    finally:
        if old is None:
            del os.environ["ANTHROPIC_API_KEY"]
        else:
            os.environ["ANTHROPIC_API_KEY"] = old


def feedback(items, hidden):
    it = next(i for i in items.values() if i["source"] == "mbpp")
    fb = format_feedback(evaluate(it, stub(it)))
    check(f"feedback shows the real failing public test with expected and actual ({it['id']})",
          it["tests"][0] in fb and "Expected:" in fb and "Got: None" in fb, fb)
    check("feedback contains no hidden test", not any(t in fb for t in hidden[it["id"]]))
    try:
        format_feedback(evaluate(it, stub(it), split="private"))
        refused = False
    except ValueError:
        refused = True
    check("format_feedback refuses hidden-test results", refused)


# =====================================================================
# 3. PIPELINE: prompts, baseline.py and compare_runs.py, in memory, no API
# =====================================================================

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


# Text of a hidden test long enough that finding it somewhere can't be a coincidence.
def _hidden_texts(tests: list) -> list:
    texts = [t if isinstance(t, str) else t["input"] for t in tests]
    return [t[:200] for t in texts if len(t) >= 30]


def pipeline(items, hidden, fixtures):
    from AI_models import retry_prompts as rp
    from AI_models.prompts import ALL_LEVELS, build_prompt
    from AI_models.providers import PROVIDERS
    from Baseline.baseline import run_one, summarize_run
    from Baseline.compare_runs import check_same_scoring, check_same_tasks

    for it in items.values():
        ref = (it.get("reference") or "").strip()
        secret = _hidden_texts(hidden[it["id"]])
        for lvl in ALL_LEVELS:
            p = build_prompt(it, lvl)
            assert p.strip() and not (ref and ref in p), (it["id"], lvl, "reference in prompt")
            assert not any(t in p for t in secret), (it["id"], lvl, "hidden test in prompt")
    check(f"prompts: {len(ALL_LEVELS)} levels build for all {len(items)} tasks, no reference or hidden test in any",
          True)

    # Retry prompts get the previous code and PUBLIC feedback only.
    mb = next(it for it in items.values() if it["source"] == "mbpp")
    wrong = stub(mb)
    fb = format_feedback(evaluate(mb, wrong))
    prompts = [rp.bare_retry(mb["prompt"], wrong), rp.reflect_fix(mb["prompt"], wrong, fb),
               rp.critic_review(mb["prompt"], wrong, fb), rp.critic_fix(mb["prompt"], wrong, fb, "- returns None")]
    leaked = [t for t in hidden[mb["id"]] for p in prompts if t in p]
    check(f"retry prompts: previous code + real public feedback, no hidden test ({mb['id']})",
          all(wrong in p for p in prompts) and fb in prompts[1] and not leaked, leaked[:1])

    # baseline.py on real tasks: the reference provider (MBPP) and the LiveCodeBench solutions through run_one.
    PROVIDERS["self_test_fixtures"] = {**PROVIDERS["reference"],
                                       "call": lambda client, item, cfg: (fenced(fixtures[item["id"]]), 0, "fixture")}
    try:
        mbpp = [it for it in items.values() if it["source"] == "mbpp"]
        lcb = [items[i] for i in fixtures]
        no_ref = next(it for it in items.values() if it["source"] == "livecodebench" and it["id"] not in fixtures)
        results = ([run_one("reference", None, it) for it in mbpp] +
                   [run_one("self_test_fixtures", None, it) for it in lcb] +
                   [run_one("reference", None, no_ref)])  # LiveCodeBench ships no reference -> failed run
    finally:
        del PROVIDERS["self_test_fixtures"]
    scored, failed = results[:-1], results[-1]
    counts_ok = all(r["n_tests"] == len(hidden[r["id"]]) and r["public"]["n_tests"] == len(items[r["id"]]["tests"])
                    for r in scored)
    check(f"baseline: run_one scores {len(scored)} answers on every real hidden test (headline) and every public test",
          counts_ok)
    check("baseline: correct answers pass hidden and public tests, no false passes",
          all(r["scored_on"] == "hidden" and r["score"] == 1.0 and r["public"]["score"] == 1.0 and r["level"] == "Pass"
              and r["false_pass"] is False for r in scored), [r["id"] for r in scored if r["score"] != 1.0])
    check("baseline: a provider error is a failed run with score 0 and no level",
          failed["failed_run"] and failed["score"] == 0.0 and failed["level"] is None, failed)
    texts = list(_strings(results))
    leaked = [(r["id"], t[:40]) for r in results for t in _hidden_texts(hidden[r["id"]]) if any(t in s for s in texts)]
    check("baseline: no hidden test text in the results", not leaked, leaked[:2])
    s = summarize_run(results)
    n = len(scored)
    check("baseline: summary has hidden pass@1, public pass@1, false passes, levels and failed runs",
          s["overall"]["pass@1"] == round(n / (n + 1), 3) and s["public_pass@1"] == round(n / (n + 1), 3)
          and s["false_passes"] == 0 and s["overall"]["levels"] == {"Pass": n} and s["failed_runs"] == 1, s)

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
    items, hidden, fixtures = load()
    data(items, hidden, fixtures)
    formats(items, fixtures)
    levels(items)
    extraction(items, fixtures)
    lcb_header(items, fixtures)
    isolation(items, fixtures)
    feedback(items, hidden)
    pipeline(items, hidden, fixtures)
    print(f"ALL TESTS PASSED ({time.time() - t0:.0f}s)")
