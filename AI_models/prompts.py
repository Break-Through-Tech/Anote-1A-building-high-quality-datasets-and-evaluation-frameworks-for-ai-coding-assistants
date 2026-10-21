"""
prompts.py

Prompt-detail levels for the prompt generation strategy (Task: curate 3 prompts
per task type, at different levels of detail, then save / compare / analyze).

Two task types, three levels each:

    task_type        level      what the model is given
    ---------------  ---------  ------------------------------------------------
    code_generation  basic      the problem, one line of instruction
                     detailed   + role, rules (keep signature, imports, output format)
                     extreme    + numbered requirements, edge-case checklist,
                                  strict output contract, silent self-check
    bug_fixing       basic      the buggy code only, "fix the bug"
                     detailed   + the specification + output format rules
                     extreme    + step-by-step debugging procedure, minimal-fix
                                  rule, strict output contract

A fourth level, "raw", sends the unified dataset's own prompt unchanged. That is
what the original baseline did, so old and new runs stay comparable.

Only `item["prompt"]` and `item["metadata"]["buggy_code"]` are read. Reference
solutions and tests are never put in a prompt.
"""

import re

LEVELS = ("basic", "detailed", "extreme")
ALL_LEVELS = ("raw",) + LEVELS

# The unified bug-fix prompt is "<instruction>\n\nSpecification:\n<spec>\n\nBuggy code:\n```python\n<code>\n```".
# Pull the spec back out so each level can include or leave it out.
_BUGFIX_PARTS = re.compile(r"Specification:\n(.*?)\n\nBuggy code:\n```python\n(.*?)\n```\s*$", re.DOTALL)


# =====================================================================
# CODE GENERATION
# =====================================================================
def _codegen(problem: str, level: str) -> str:
    if level == "basic":
        return f"Write Python code for this task.\n\n{problem}"

    if level == "detailed":
        return (
            "You are an expert Python programmer. Solve the task below.\n\n"
            f"Task:\n{problem}\n\n"
            "Rules:\n"
            "- Keep the function name and signature exactly as given.\n"
            "- Include any imports the code needs.\n"
            "- Return the complete, working function in a single ```python code block.\n"
            "- Do not include example usage, tests, or explanation."
        )

    return (
        "You are a senior Python engineer. Your solution will be checked automatically "
        "against hidden unit tests, so it must be correct, not just plausible.\n\n"
        f"## Task\n{problem}\n\n"
        "## Requirements\n"
        "1. Implement exactly what the task describes. If it includes examples or a docstring, "
        "your function must reproduce every example's output.\n"
        "2. Keep the function name, parameter names, and parameter order exactly as given. "
        "Do not add required parameters.\n"
        "3. Use only the Python standard library. Add every import you use.\n"
        "4. Do not read from input() or stdin, do not print, and do not use global state. "
        "Return the result.\n"
        "5. Handle edge cases: empty inputs, a single element, zero, negative numbers, "
        "duplicates, and large inputs. Prefer an efficient approach over brute force when "
        "the input could be large.\n"
        "6. If the task is ambiguous, choose the most standard interpretation and follow it.\n\n"
        "## Before you answer (do this silently)\n"
        "Trace your function by hand on the examples in the task and on one edge case. "
        "Fix anything that does not match.\n\n"
        "## Output format\n"
        "Reply with exactly one ```python code block containing the complete solution, "
        "and nothing else: no explanation, no example usage, no test code."
    )


# =====================================================================
# BUG FIXING
# =====================================================================
def _bugfix(item: dict, level: str) -> str:
    m = _BUGFIX_PARTS.search(item["prompt"])
    spec = m.group(1).strip() if m else None
    code = (m.group(2) if m else (item.get("metadata") or {}).get("buggy_code", "")).strip()
    if m is None and not code:  # cannot split the prompt: fall back to the dataset's own wording
        return item["prompt"]

    if level == "basic":
        return f"Fix the bug in this Python code.\n\n```python\n{code}\n```"

    spec_block = f"Specification:\n{spec}\n\n" if spec else ""

    if level == "detailed":
        return (
            "You are an expert Python debugger. The function below has a bug. "
            "Fix it so that it matches the specification.\n\n"
            f"{spec_block}Buggy code:\n```python\n{code}\n```\n\n"
            "Rules:\n"
            "- Do not change the function name or signature.\n"
            "- Return the complete corrected function (plus any helper code it needs) "
            "in a single ```python code block.\n"
            "- Do not include tests or explanation."
        )

    return (
        "You are a senior Python engineer doing a careful code fix. Your fix will be checked "
        "automatically against hidden unit tests, so it must be correct.\n\n"
        f"## Specification\n{spec if spec else '(none given; infer the intended behavior from the code and its docstring)'}\n\n"
        f"## Buggy code\n```python\n{code}\n```\n\n"
        "## Procedure (do this silently)\n"
        "1. Work out what the function is supposed to do from the specification and any examples.\n"
        "2. Trace the buggy code by hand on an example and find the first place the result "
        "diverges from the expected one.\n"
        "3. Identify the root cause. Bugs in this kind of task are usually small: a wrong "
        "operator, an off-by-one, a wrong variable, a missing or inverted condition, or "
        "missing logic.\n"
        "4. Make the smallest change that fixes the root cause. Do not rewrite working code "
        "and do not change behavior that is already correct.\n"
        "5. Re-trace the fixed code on the example and on one edge case.\n\n"
        "## Constraints\n"
        "- Do not change the function name, parameters, or return type.\n"
        "- Keep helper functions and imports the code relies on.\n\n"
        "## Output format\n"
        "Reply with exactly one ```python code block containing the complete corrected code, "
        "and nothing else: no explanation, no tests."
    )


# =====================================================================
# ENTRY POINT
# =====================================================================
def build_prompt(item: dict, level: str) -> str:
    """Return the prompt text for `item` at the given detail level."""
    if level == "raw":
        return item["prompt"]
    if level not in LEVELS:
        raise ValueError(f"unknown prompt level {level!r}; use one of {ALL_LEVELS}")
    if item["task_type"] == "bug_fixing":
        return _bugfix(item, level)
    return _codegen(item["prompt"], level)


if __name__ == "__main__":
    # Self-test: every level builds for both task types, nothing leaks, bug-fix parsing is lossless.
    import json
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "data" / "unified" / "unified_eval.jsonl"
    rows = [json.loads(line) for line in open(path)]
    n = 0
    for r in rows:
        for lvl in ALL_LEVELS:
            p = build_prompt(r, lvl)
            assert p.strip(), (r["id"], lvl)
            if r["task_type"] == "bug_fixing" and lvl != "raw":
                assert r["metadata"]["buggy_code"].strip() in p, (r["id"], lvl)
            # Bug-fix references can be a substring of the buggy code (e.g. a deleted "+ 1.0"),
            # so the leak check only means something for code generation.
            ref = (r.get("reference") or "").strip()
            if r["task_type"] == "code_generation":
                assert not ref or ref not in p, f"reference leaked into prompt: {r['id']} {lvl}"
            n += 1
    sizes = {lvl: sum(len(build_prompt(r, lvl)) for r in rows) // len(rows) for lvl in ALL_LEVELS}
    print(f"ok: {n} prompts built from {len(rows)} items; mean chars per level: {sizes}")
    assert sizes["basic"] < sizes["detailed"] < sizes["extreme"], sizes
    sys.exit(0)
