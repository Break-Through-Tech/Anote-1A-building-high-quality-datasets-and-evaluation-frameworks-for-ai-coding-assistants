"""
self_test.py

One command to check that the data flows through the rubric and the pipeline correctly, with no
API calls and no files written outside a temporary folder. Run it from the repo root after any change
to the data, the evaluator, the prompts, the baseline or the loop:
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
4. Loop: Optimizer/loop.py on one real MBPP task scripted into each attempt-0 cell (A true pass,
   B false pass, C hidden-only pass, D true fail, a failed run): the cells, all-task and C + D
   numbers, failed runs, copy-forward, one usage-log row per call, no hidden test text;
   results.py's tables against summary.json; and report.py's McNemar test.
5. Results views: a synthetic run of all 100 code-generation tasks (Optimizer/synthetic_run.py; invented
   outcomes, so every cell, false fixes, regressions and failed calls appear) plus a fake Panacea run:
   results.py's curves, arm outcomes and breakdowns against summary.json, the confidence intervals,
   Panacea in the tables, and every chart in charts.py drawn in both themes.
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
                                       "call": lambda client, item, cfg: (fenced(fixtures[item["id"]]), 0, "fixture", 0)}
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


# =====================================================================
# 4. LOOP: Optimizer/loop.py's run_task + summarize_run and report.py's McNemar, with a scripted model
# =====================================================================
def loop(items, hidden):
    """One real MBPP task in five copies, each scripted into one attempt-0 outcome:
         A reference                      -> true pass
         B right on the public tests only -> false pass (public pass, hidden fail)
         C right on the first test only, scored against that one public test as its "hidden" set
                                          -> hidden-only pass (the one place the hidden set is not the real one)
         D do-nothing stub                -> true fail
         E API error                      -> failed run
       Retries: control gives a stub (breaks C, never repairs D); bare_retry fixes D at attempt 2;
       reflect_fix has an API error at attempt 1, then fixes D; critic never fixes D.
       Everything is written to a temporary folder, including the usage log."""
    import tempfile
    from AI_models import budget_tracker as bt
    from AI_models.providers import AdapterError
    from Optimizer import loop as lp
    from Optimizer import report
    from Optimizer.results import build

    it = next(i for i in items.values() if i["source"] == "mbpp" and i["reference"].count(i["entry_point"] + "(") == 1)
    n_pub, real_hidden = len(it["tests"]), hidden[it["id"]]
    assert len(real_hidden) > n_pub, "the B case needs more hidden tests than public ones"
    variants = {t: {**it, "id": f"{it['id']}#{t}", "private_tests": it["tests"][:1] if t == "C" else real_hidden}
                for t in "ABCDE"}
    ref, wrong, k1, kpub = (fenced(it["reference"]), fenced(stub(it)), fenced(first_k_correct(it, 1)),
                            fenced(first_k_correct(it, n_pub)))

    def call(client, item, cfg):
        t, arm, k, role = item["id"][-1], item["_arm"], item["_attempt"], item["_role"]
        if role == "critic":
            return "- returns None", 5, "mock", 50
        if k == 0:
            if t == "E":
                raise AdapterError("scripted API error")
            return {"A": ref, "B": kpub, "C": k1, "D": wrong}[t], 10, "mock", 100
        if arm == "reflect_fix" and k == 1:
            raise AdapterError("scripted API error")
        if t == "C":
            return (wrong if arm == "control" else k1), 10, "mock", 100
        fixed = arm in ("bare_retry", "reflect_fix") and k >= 2
        return (ref if fixed else wrong), 10, "mock", 100

    p = {"config": {"model": "mock", "max_tokens": None, "temperature": None}, "call": call}
    arms = list(lp.rp.ARMS)
    old_log, old_prices = bt.LOG_PATH, dict(bt.PRICES_PER_MTOK)
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        bt.LOG_PATH, bt._state["total"] = run_dir / "usage_log.csv", None
        bt.PRICES_PER_MTOK["mock"] = (1.0, 1.0)
        try:
            (run_dir / "run_meta.json").write_text(json.dumps(
                {"scoring_version": SCORING_VERSION, "model": "mock", "arms": arms, "retries": 3,
                 "task_ids": [variants[t]["id"] for t in "ABCDE"]}))
            for t in "ABCDE":
                lp.append_task(run_dir, lp.run_task(p, None, variants[t], arms, 3))
            s = report.summarize_run(run_dir)
            tables, _ = build(run_dir, write=False)
            rows = [r for k in range(4) for r in report.read_rows(run_dir, k)]
            with open(bt.LOG_PATH) as f:
                n_logged = sum(1 for _ in f) - 1
        finally:
            bt.LOG_PATH, bt._state["total"] = old_log, None
            bt.PRICES_PER_MTOK.clear()
            bt.PRICES_PER_MTOK.update(old_prices)

    a0 = s["attempt_0"]
    check("loop: attempt 0 splits into cells A/B/C/D, plus one failed run",
          a0["cells"] == {"A_true_pass": 1, "B_false_pass": 1, "C_hidden_only_pass": 1, "D_true_fail": 1}
          and a0["failed_runs"] == 1 and a0["went_into_arms"] == 2 and a0["false_passes"] == 1, a0)
    final = {a: s["all_tasks"][a]["hidden_pass@1_by_attempt"][-1] for a in arms}
    excl = {a: s["all_tasks"][a]["hidden_pass@1_excl_failed_by_attempt"][-1] for a in arms}
    check("loop: all-task hidden pass@1 at attempt 3 (A and B keep attempt 0; failed runs counted 0 / left out)",
          final == {"control": 0.2, "bare_retry": 0.6, "reflect_fix": 0.6, "critic": 0.4}
          and excl == {"control": 0.25, "bare_retry": 0.75, "reflect_fix": 0.75, "critic": 0.5}
          and all(s["all_tasks"][a]["hidden_pass@1_excl_failed_by_attempt"][0] == 0.5 for a in arms), (final, excl))
    st = s["arms"]
    check("loop: repairs counted over D, breaks over C",
          [(st[a]["repairs"], st[a]["n_D_repair_targets"], st[a]["breaks"], st[a]["n_C_hidden_only_pass"]) for a in arms]
          == [(0, 1, 1, 1), (1, 1, 0, 1), (1, 1, 0, 1), (0, 1, 0, 1)], st)
    by = {(r["task_id"][-1], r["arm"], r["attempt"]): r for r in rows}
    failed_retry = by[("D", "reflect_fix", 1)]
    carried = by[("D", "bare_retry", 3)]
    check("loop: an API error on a retry is a failed run, not a regression; the next retry builds on the last good one",
          failed_retry["failed_run"] and failed_retry["regression"] is None and st["reflect_fix"]["failed_runs"] == 2
          and by[("D", "reflect_fix", 2)]["hidden_score"] == 1.0, failed_retry)
    check("loop: after a public pass, later attempts are copied forward with no call",
          carried["carried_forward"] and carried["calls"] == 0 and carried["hidden_score"] == 1.0
          and by[("A", "zero_shot", 0)]["calls"] == 1 and ("A", "control", 1) not in by, carried)
    check("loop: critic attempts make two calls, and every call is one usage-log row",
          by[("D", "critic", 1)]["calls"] == 2 and n_logged == sum(r["calls"] for r in rows),
          (n_logged, sum(r["calls"] for r in rows)))
    check("loop: token counts are the API's (only failed calls are estimated)",
          by[("A", "zero_shot", 0)]["tokens_estimated"] == 0 and by[("E", "zero_shot", 0)]["tokens_estimated"] == 1
          and by[("A", "zero_shot", 0)]["input_tokens"] == 100, by[("A", "zero_shot", 0)])
    secret = _hidden_texts(real_hidden)
    leaked = [t[:40] for t in secret for x in _strings(rows) if t in x]
    check("loop: no hidden test text in any prompt, critique or row", not leaked, leaked[:2])
    main, tr = tables["main"], tables["transitions"]
    last = main[main["attempt"] == 3].set_index("system")["hidden_pass@1"].to_dict()
    check("results: main table matches summary.json (every arm, attempt 3, all tasks incl. failed runs as 0)",
          all(last[a] == s["all_tasks"][a]["hidden_pass@1_by_attempt"][-1] for a in arms), last)
    check("results: cells table matches, and transitions count the fix and the break",
          tables["cells"].iloc[0][["A_true_pass", "B_false_pass", "C_hidden_only_pass", "D_true_fail", "failed"]].tolist()
          == [1, 1, 1, 1, 1]
          and tr.groupby("arm")[["fixed", "broke"]].sum().to_dict("index")
          == {"control": {"fixed": 0, "broke": 1}, "bare_retry": {"fixed": 1, "broke": 0},
              "reflect_fix": {"fixed": 1, "broke": 0}, "critic": {"fixed": 0, "broke": 0}}, tr)
    check("results: per-task table has hidden passed/total and level for every arm and attempt",
          len(tables["tasks"]) == 5 and {f"{a}_a{k}_hidden" for a in arms for k in (1, 2, 3)} <= set(tables["tasks"]))
    check("loop: the retry prompts are the frozen ones (AI_models/retry_prompts.py, FROZEN_FINGERPRINT)",
          lp.rp.fingerprint() == lp.rp.FROZEN_FINGERPRINT, lp.rp.FROZEN_DATE)
    check("report: exact McNemar (3 vs 0 discordant -> p = 0.25; none -> p = 1)",
          report.mcnemar({1: 1, 2: 1, 3: 1, 4: 0}, {1: 0, 2: 0, 3: 0, 4: 0}) == (3, 0, 0.25)
          and report.mcnemar({1: 1}, {1: 1})[2] == 1.0)
    check("report: Holm adjustment (0.01, 0.04, 0.03 -> 0.03, 0.06, 0.06)",
          [round(p, 4) for p in report.holm([0.01, 0.04, 0.03])] == [0.03, 0.06, 0.06])


def results_views():
    """Synthetic run (test data) -> summary.json, results.py tables and charts.py charts, in a temp folder."""
    import tempfile
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from Optimizer import report
    from Optimizer.charts import draw_all
    from Optimizer.results import build
    from Optimizer.synthetic_run import write_run

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        write_run(run_dir, seed=7)
        s = report.summarize_run(run_dir)
        # a fake Panacea run in baseline.py's format, from the synthetic attempt 0 (outcomes flipped on a few)
        a0 = report.read_rows(run_dir, 0)
        pan = [{"id": r["task_id"], "score": float(i % 3 == 0) if r["failed_run"] else r["hidden_score"],
                "n_passed": 10 if r["hidden_score"] == 1.0 else 3, "n_tests": 10, "test_pass_rate": r["hidden_test_pass_rate"],
                "rubric_level": r["rubric_level"] if r["rubric_level"] is not None else 1, "level": r["level"] or "Wrong",
                "failure_type": r["failure_type"], "public": {"score": r["public_score"], "n_passed": 1, "n_tests": 3},
                "false_pass": r["false_pass"], "failed_run": False, "calls": 3, "input_tokens": 3000,
                "output_tokens": 1500, "cost_usd": 0.0315} for i, r in enumerate(a0)]
        pan_path = Path(tmp) / "panacea_run.json"
        pan_path.write_text(json.dumps({"scoring_version": SCORING_VERSION, "results": pan}))
        tables, meta = build(run_dir, pan_path, write=False)
        n_png = {}
        for theme in ("light", "dark"):
            out = Path(tmp) / f"charts_{theme}"
            draw_all(tables, meta, out, theme=theme, close=True)
            n_png[theme] = len(list(out.glob("*.png")))
        plt.close("all")

    arms, cells = meta["arms"], s["attempt_0"]["cells"]
    check("views: the synthetic run has every attempt-0 cell, failed runs, false fixes and regressions",
          min(cells.values()) > 0 and s["attempt_0"]["failed_runs"] > 0
          and all(s["arms"][a]["false_fixes"] > 0 and s["arms"][a]["regressions"] > 0 for a in arms), cells)
    c = tables["curves"]
    curve = lambda scope, a, col="hidden_pass@1": c[(c["scope"] == scope) & (c["arm"] == a)].sort_values("attempt")[col].tolist()  # noqa: E731
    check("views: curves match summary.json (all tasks, incl. failed as 0, C + D, gain over control)",
          all(curve("all", a) == s["all_tasks"][a]["hidden_pass@1_by_attempt"]
              and curve("all", a, "hidden_pass@1_excl_failed") == s["all_tasks"][a]["hidden_pass@1_excl_failed_by_attempt"]
              and curve("paired", a) == s["arms"][a]["hidden_pass@1_by_attempt"]
              and curve("paired", a, "gain_vs_control") == s["arms"][a]["gain_over_control_by_attempt"] for a in arms))
    o = tables["arm_outcomes"].set_index("arm")
    pairs = {"repairs": "repairs", "breaks": "breaks", "false_fixes": "false_fixes", "regression_events": "regressions",
             "failed_api_calls": "failed_runs", "n_D": "n_D_repair_targets", "n_C": "n_C_hidden_only_pass",
             "calls": "calls", "cost_usd": "cost_usd", "cost_per_repair_usd": "cost_per_repair_usd"}
    bad = [(a, mine, o.loc[a, mine], s["arms"][a][theirs]) for a in arms for mine, theirs in pairs.items()
           if abs(o.loc[a, mine] - s["arms"][a][theirs]) > 1e-9]
    bad += [(a, "pipeline", o.loc[a, "pipeline_cost_usd"], s["all_tasks"][a]["cost_usd"]) for a in arms
            if abs(o.loc[a, "pipeline_cost_usd"] - s["all_tasks"][a]["cost_usd"]) > 1e-9]
    check("views: arm outcomes match summary.json (repairs, breaks, false fixes, regressions, failed calls, cost)",
          not bad, bad[:3])
    bg = tables["by_group"]

    def groups(grouping, rename=lambda g: g):
        d = bg[(bg["grouping"] == grouping) & (bg["scope"] == "paired") & bg["system"].isin(arms)]
        return {rename(g): {"n": int(x["n"].max()), **{a: x[x["system"] == a].sort_values("attempt")["hidden_pass@1"].tolist()
                                                     for a in arms}} for g, x in d.groupby("group")}
    check("views: breakdowns match summary.json (source/difficulty, attempt-0 failure type; C + D)",
          groups("source_difficulty") == s["by_source_difficulty"]
          and groups("attempt0_failure_type", lambda g: "none" if g == "none (hidden pass)" else g)
          == s["by_attempt0_failure_type"])
    inside = (c["ci_low"] <= c["hidden_pass@1"]) & (c["hidden_pass@1"] <= c["ci_high"])
    g = c.dropna(subset=["gain_ci_low"])
    check("views: every Wilson and bootstrap interval contains its estimate",
          inside.all() and ((g["gain_ci_low"] <= g["gain_vs_control"]) & (g["gain_vs_control"] <= g["gain_ci_high"])).all()
          and len(g) == 3 * 3 * 4)
    m, pt = tables["main"], tables["paired_tests"]
    check("views: Panacea is in the main, cells and paired-test tables",
          (m["system"] == "panacea").sum() == 1 and (tables["cells"]["system"] == "panacea").sum() == 1
          and (pt["family"] == "panacea").sum() == 1 + len(arms))
    keep = ["comparison", "attempt", "only_first_passes", "only_second_passes", "p_exact_mcnemar", "p_holm", "significant"]
    in_csv = pt[pt["family"].isin(["feedback_vs_control", "vs_zero_shot"])][keep].to_dict("records")
    key = lambda r: (r["comparison"], r["attempt"])  # noqa: E731
    check("report: summary.json's paired tests match results.py's (raw p, Holm p, verdict)",
          sorted(in_csv, key=key) == sorted([{k: r[k] for k in keep} for r in s["paired_tests"]], key=key))
    rep = report.render_report(s, meta, "run")
    check("report: has run health and every arm's final hidden pass@1 from summary.json",
          "## Run health" in rep and all(report.fmt(s["all_tasks"][a]["hidden_pass@1_by_attempt"][-1]) in rep for a in arms))
    check("views: every chart is drawn in both themes (9 for a code-generation run)",
          n_png == {"light": 9, "dark": 9}, n_png)


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
    loop(items, hidden)
    results_views()
    print(f"ALL TESTS PASSED ({time.time() - t0:.0f}s)")
