# Evaluator-Optimizer loop v1

`Optimizer/loop.py` runs the main experiment for the research question: does evaluator feedback help a coding model correct itself, and at what cost?

## How a task runs
1. **Attempt 0**: `claude-sonnet-4-6` answers the dataset's own prompt (zero-shot). Every arm shares this answer.
   - Its public tests pass → the task stops (if the hidden tests fail, that's a *false pass*).
   - The API call failed (`failed_run`) → the task stops and is left out of the arm comparison.
2. **Otherwise**, the task goes into each of the four arms separately, all starting from attempt 0, for up to 3 retries:

| arm | retry prompt | calls per retry |
|---|---|---|
| `control` | the attempt-0 prompt again: a fresh resample, with no old code and no feedback | 1 |
| `bare_retry` | the arm's previous code + "it failed, try again" | 1 |
| `reflect_fix` | the arm's previous code + the first failing **public** test; the model explains the error, then fixes it | 1 |
| `critic` | a reviewer call diagnoses the code and the failing test (no code), then the generator fixes it | 2 |

   - Retries 2–3 build on that arm's **own** latest attempt. Prompts show only the latest attempt, not the history (`AI_models/retry_prompts.py`).
   - **Copy-forward rule (v1):** once an arm's code passes its public tests, its later attempts copy that attempt with **no API call** (`carried_forward: true`). Every arm has attempts 1–3, so the curves line up.
   - After a failed API call on a retry, the next retry builds on the last good attempt.
3. **Scoring:** every attempt is scored on the **hidden** tests (the reported result; the model never sees them) and on the public tests (the only feedback).

Every setting is shared by every arm: temperature 0.5 (so the control really resamples), `max_tokens` 4096. Feedback arms only count as helping if they beat the control.

## Running it
```bash
python Optimizer/loop.py mock --ids smoke.txt              # no API: checks the plumbing (numbers mean nothing)
python Optimizer/loop.py claude --ids pilot.txt            # the pilot (10 tasks)
python Optimizer/loop.py claude --ids pilot.txt --resume   # continue after a budget stop or Ctrl-C
python Optimizer/loop.py --summarize data/results/<run>    # rebuild summary.json
```

Options:
- `--arms control reflect_fix` runs a subset of arms.
- `--retries 3`.
- `--name` sets the run folder name.
- `--out` sets the folder that holds the run folders.

Notes on running:
- Before a real run, estimate its cost: `python -c "from AI_models.budget_tracker import estimate_main_run as e; print(e('claude-sonnet-4-6', n_tasks=10, n_failed=5))"`. That assumes every failed task uses all 3 retries in every arm. Copy-forward makes it cheaper.
- A task's rows are written only once the whole task is done. A crash or budget stop loses at most the unfinished task. Its API calls are still in the usage log, because that money was spent.

## Budget log
- Every API call goes through `AI_models/budget_tracker.py`, critic calls included. That's one row in `runs/usage_log.csv` with `task_id`, `arm` (`zero_shot` for attempt 0), `attempt`, `call_type` (`generator` / `critic`), tokens and cost. Copied-forward attempts make no call and get no row.
- New calls stop at $47 of the $50 budget.
- Output tokens come from the API. Input tokens are **estimated** (about 4 characters per token, `estimated=True`), so costs are approximate.
- Mock runs write their own `usage_log.csv` inside the run folder, never the real one.

## Results: `data/results/<date>_<provider>_<task list>/`
| file | rows |
|---|---|
| `run_meta.json` | the settings: scoring version, provider, model, temperature, `max_tokens`, task ids, arms, retries, git commit, start/finish |
| `attempt_0.jsonl` | one per task |
| `attempt_1.jsonl` … `attempt_3.jsonl` | one per (task that failed attempt 0's public tests × arm) |
| `summary.json` | the numbers below |

Row fields (the same in every attempt file):

| field | meaning |
|---|---|
| `task_id`, `source`, `difficulty`, `test_format` | from the dataset. MBPP and LiveCodeBench difficulty are different scales: never pool them |
| `arm`, `attempt` | `zero_shot` at attempt 0, else the arm name; 0–3 |
| `hidden_score`, `hidden_test_pass_rate`, `hidden_tests` | pass@1 on the hidden tests (the headline), the fraction passed, and `"7/10"`. Counts only: no hidden test text is ever stored |
| `public_score`, `public_test_pass_rate`, `public_tests` | the same on the public tests |
| `false_pass` | passes the public tests but fails the hidden ones (a *false fix* when it happens on a retry) |
| `rubric_level`, `level`, `failure_type` | from the hidden scoring (`Evaluator/evaluator.py`) |
| `regression` | the hidden test pass rate went **down** from this arm's previous attempt (null at attempt 0) |
| `carried_forward` | copied from the previous attempt after a public pass; no call made |
| `failed_run`, `error` | the API call failed after the SDK's retries (scored 0) / the error name |
| `calls`, `output_tokens`, `input_tokens_est`, `latency_s` | per attempt (critic attempts sum both calls); they match the usage-log rows |
| `prompt`, `critique`, `output` | exactly what was sent and returned (`critique` only in the critic arm) |

`summary.json` is computed on the **paired set**: the tasks that failed attempt 0's public tests and finished every arm. Per arm, it has:
- hidden and public pass@1 at attempts 0–3
- gain over the control at each attempt
- repairs: hidden fails at attempt 0, passes at attempt 3
- false fixes at attempt 3
- regressions
- failed runs
- calls, tokens, estimated $ and $ per repair

The same curves are also split by source/difficulty and by attempt 0's failure type.
