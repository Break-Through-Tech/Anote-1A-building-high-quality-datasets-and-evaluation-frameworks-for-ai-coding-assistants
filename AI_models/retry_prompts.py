"""
retry_prompts.py

Prompts for the self-correction arms of the Evaluator-Optimizer loop
(Task: "Reflection / critique prompt strategies"). Attempt 0 is the normal
zero-shot prompt from prompts.py, shared by every arm. A task whose attempt 0
fails its PUBLIC tests then goes into each arm, and every retry in an arm uses
that arm's one fixed strategy:

    arm               what the retry prompt contains                          API calls per retry
    ----------------  ------------------------------------------------------  -------------------
    control           the original prompt again (fresh resample)              1
                      no old code, no feedback
    bare_retry        problem + previous code + "it failed, try again"        1
                      (no test details)
    reflect_fix       problem + previous code + first failing public test     1
                      (input, expected, actual, error); the model explains
                      the error, then fixes it
    critic            call 1 (critic): reviews the code + failing test,       2
                      writes a diagnosis, no code
                      call 2 (generator): problem + previous code + failing
                      test + the critic's diagnosis -> fixed code

The failing-test text comes from Evaluator.evaluator.format_feedback(public_result).

Rules (same as prompts.py):
- Only the item's prompt, the model's own previous code, and PUBLIC test feedback
  go into a prompt. Never hidden tests, the reference, or metadata.
  format_feedback() refuses hidden-test results.
- Each retry shows only the LATEST attempt, not the whole history, so prompt size
  stays about the same from retry to retry and the arms stay comparable on tokens.
- Every prompt ends with the same output contract (one ```python block), so
  extract_code() treats every arm the same way.

Try them on 10 MBPP tasks: python AI_models/try_retry_prompts.py claude
"""

ARMS = ("control", "bare_retry", "reflect_fix", "critic")

GENERATOR_SYSTEM = "You are an expert coding assistant."  # same as the baseline / Panacea system prompt
CRITIC_SYSTEM = ("You are a meticulous code reviewer. You find the root cause of failing code. "
                 "You never write the corrected code yourself.")

OUTPUT_CONTRACT = ("Reply with the complete corrected solution in exactly one ```python code block. "
                   "Keep the same function name and signature (or, for a stdin program, a complete program "
                   "that reads standard input and prints the answer). No example usage or test code.")


def _context(problem: str, prev_code: str) -> str:
    return (f"## Task\n{problem}\n\n"
            f"## Your previous solution\n```python\n{prev_code.strip() or '# (no code was produced)'}\n```")


# --- control: fresh resample --------------------------------------------------
# The control arm sends the attempt-0 prompt (prompts.build_prompt) again unchanged.
# It exists to separate "feedback helped" from "a second sample got lucky".


# --- bare retry -----------------------------------------------------------------
def bare_retry(problem: str, prev_code: str) -> str:
    return (f"{_context(problem, prev_code)}\n\n"
            "## Result\nYour previous solution failed the tests. Try again.\n\n"
            f"{OUTPUT_CONTRACT}")


# --- reflect, then fix -------------------------------------------------------------
def reflect_fix(problem: str, prev_code: str, feedback: str) -> str:
    return (f"{_context(problem, prev_code)}\n\n"
            f"## Test results\n{feedback}\n\n"
            "## What to do\n"
            "1. In 2-4 sentences, explain why your solution produced this result: point to the line or "
            "logic that is wrong, and say what the correct behavior is.\n"
            "2. Then fix the root cause. Do not special-case the failing test: the solution will also be "
            "checked on other tests you have not seen.\n\n"
            f"{OUTPUT_CONTRACT} Put the explanation before the code block.")


# --- separate critic (two calls) ---------------------------------------------------
def critic_review(problem: str, prev_code: str, feedback: str) -> str:
    return (f"Review this solution, which fails its tests.\n\n{_context(problem, prev_code)}\n\n"
            f"## Test results\n{feedback}\n\n"
            "## Your review\n"
            "Explain in at most 6 short bullet points:\n"
            "- the root cause of the failure (which line or logic, and why it is wrong),\n"
            "- any other bugs or edge cases (empty input, large input, off-by-one, wrong output format) "
            "the solution would also get wrong,\n"
            "- what the fix should do, in words.\n"
            "Do NOT write the corrected code.")


def critic_fix(problem: str, prev_code: str, feedback: str, critique: str) -> str:
    return (f"{_context(problem, prev_code)}\n\n"
            f"## Test results\n{feedback}\n\n"
            f"## Reviewer's diagnosis\n{critique.strip()}\n\n"
            "Fix the solution using the diagnosis. Do not special-case the failing test: the solution will "
            "also be checked on other tests you have not seen.\n\n"
            f"{OUTPUT_CONTRACT}")


if __name__ == "__main__":
    # Self-test: every arm's prompt builds, includes the code + feedback it should, and nothing it shouldn't.
    problem, code = "Write add(a, b).\n\ndef add(a, b):", "def add(a, b):\n    return a - b"
    fb = "1 of 2 public tests failed.\n\nFailing test (wrong answer):\n  Test: assert add(1, 2) == 3\n  Expected: 3\n  Got: -1"
    br = bare_retry(problem, code)
    assert code in br and "Expected" not in br, br
    rf = reflect_fix(problem, code, fb)
    assert code in rf and "Expected: 3" in rf and "explain" in rf
    cr = critic_review(problem, code, fb)
    assert "Do NOT write the corrected code" in cr and fb in cr
    cf = critic_fix(problem, code, fb, "- subtracts instead of adding")
    assert "subtracts instead of adding" in cf and fb in cf
    for p in (br, rf, cf):
        assert p.endswith(OUTPUT_CONTRACT) or OUTPUT_CONTRACT in p
    print("ok: retry prompts for", ", ".join(ARMS))
