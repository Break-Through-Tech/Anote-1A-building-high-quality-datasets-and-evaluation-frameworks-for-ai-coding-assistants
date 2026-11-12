# Evaluator-Optimizer loop v1

`Optimizer/loop.py` runs the main experiment for the research question: does evaluator feedback help a coding model correct itself, and at what cost?

## How a task runs
1. **Attempt 0**: `claude-sonnet-4-6` answers the dataset's own prompt (zero-shot). Every arm shares this answer, and it is the **official Claude zero-shot result** (decided 2026-11-03; `baseline.py claude` is not used for experiment numbers). Attempt 0 puts each task in one of four cells:

| cell | public tests | hidden tests | what happens |
|---|---|---|---|
| **A** true pass | pass | pass | stops; the same result in every arm |
| **B** false pass | pass | fail | stops. The code misses edge cases, but nothing the model can see says so, so no arm can fix it. B caps every arm equally |
| **C** hidden-only pass | fail | pass | goes into the arms; can only stay right or **break** |
| **D** true fail | fail | fail | goes into the arms; the real **repair** targets |

   - The API call failed (`failed_run`) → the task stops. It's left out of the arm comparison, counted 0 in `hidden_pass@1` and `public_pass@1`, and left out of the `*_excl_failed` numbers.
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

Every setting is shared by every arm: temperature 0.5 (so the control really resamples), `max_tokens` 8192. Feedback arms only count as helping if they beat the control.

## Running it
```bash
python Optimizer/loop.py mock --split dev                     # no API: checks the plumbing
python Optimizer/loop.py claude --split dev                   # dev pilot: 10 pool tasks not in eval
python Optimizer/loop.py claude --split dev --resume          # continue after a stop
python Optimizer/loop.py claude --split test --ids <list>     # the test run, once prompts are frozen
python Optimizer/loop.py --summarize data/results/<run>       # rebuild summary.json and report.md
python Baseline/baseline.py panacea --ids <list>              # Panacea's zero-shot arm, same tasks as the test run
python Optimizer/report.py data/results/<run> panacea_run.json   # add Panacea to report.md
```

Every run writes `report.md` itself and prints the same text in the terminal. `--summarize` rebuilds it without Panacea, so run `report.py` again afterwards if the run has a Panacea file.

`--split dev` needs `data/code_generation/code_generation_private_tests.jsonl` (git-ignored; built by the code-generation notebook). Dev runs check the plumbing and measure tokens; they are never reported as results. The frozen-prompt check applies to `--split test` only.

**Detailed tables and charts:** `python Optimizer/results.py data/results/<run> panacea_run.json --charts` writes CSVs to `data/results/<run>/analysis/` and PNGs to `analysis/charts/` (leave out `--charts` for CSVs only). `notebooks/results_analysis.ipynb` shows the same tables and charts. The tables cover:
- every system at every attempt: hidden passed, rubric levels, false passes, cost
- the curves per arm with Wilson 95% intervals, and each arm's gain over the control with a paired bootstrap 95% interval
- per arm: repairs, breaks, false fixes, regressions, failed calls, and $ / tokens / calls per repair
- the A/B/C/D cells for Claude and Panacea
- movement between attempts, what each retry buys, and when arms stop
- failure types; breakdowns by source/difficulty, test format, task type and attempt-0 failure type; every paired test; one row per task

`Optimizer/charts.py` draws the charts from those tables only, so every number on a chart is in a CSV. It has 9 charts: curves with Panacea as a reference line, gain vs control, rubric levels, the breakdowns, repairs and breaks, cost per fix, and accuracy vs cost. The docstrings of `results.py` and `charts.py` list every table and chart.

**Test data:** `python Optimizer/synthetic_run.py <folder>` writes a fake run of all 100 tasks with invented outcomes, so the tables and charts can be tried on cases a mock run never produces (B and C tasks, false fixes, regressions). Its charts carry a TEST DATA banner. Never report those numbers. `Evaluator/self_test.py` uses it to check the tables against `summary.json`.

`loop.py` only runs the experiment. `report.py` owns every summary: it builds `summary.json` and the report, which is the same text in the terminal and in `report.md` and covers everything in `summary.json`. It imports nothing from `loop.py`. Running `report.py` adds Panacea to that report, and stops if the runs cover different tasks or scoring versions. The sections are: run health, main results, all tasks by attempt, the A/B/C/D cells, self-correction (C + D), breakdowns, paired tests, task ids and notes.

The paired tests are exact McNemar tests on per-task pass/fail. `p_holm` is corrected within a family, and the verdict is significant when it is below 0.05. Read `feedback_vs_control` first (each feedback arm vs the control at attempt 3): it answers whether feedback beats a fresh resample. The other families are `vs_zero_shot`, `panacea` and, in `paired_tests.csv` only, `exploratory`. "Not significant" means this run can't tell, not that there is no difference.

Providers: `claude` and `mock` only (`opensource` was dropped from the loop on 2026-11-03).

Options:
- `--arms control reflect_fix` runs a subset of arms.
- `--retries 3`.
- `--name` sets the run folder name.
- `--out` sets the folder that holds the run folders.

Notes on running:
- Before a real run, estimate its cost: `python -c "from AI_models.budget_tracker import estimate_main_run as e; print(e('claude-sonnet-4-6', n_tasks=10, n_failed=5))"`. That assumes every failed task uses all 3 retries in every arm. Copy-forward makes it cheaper.
- A task's rows are written only once the whole task is done. A crash or budget stop loses at most the unfinished task. Its API calls are still in the usage log, because that money was spent.

## Before a paid run: checklist
Run every step from the repo root, in order, and stop at the first one that fails.
1. **Up to date:** `git pull`, so the usage log has everyone's spending. Check that `git status` is clean, so `run_meta.json` records the commit you actually ran.
2. **Nobody else is running a paid job right now** (ask the team). The $47 stop only sees your local log.
3. **Setup:** `pip install -r requirements.txt` (pins `anthropic<1`), and `.env` holds `ANTHROPIC_API_KEY`.
4. **Checks pass:** `python Evaluator/self_test.py` ends with `ALL TESTS PASSED`. That includes the check that the retry prompts are still the frozen ones (see below).
5. **Plumbing:** `python Optimizer/loop.py mock --split dev` finishes. It makes no API calls and writes no real usage-log rows.
6. **Money:** check what's been spent with `python -c "from AI_models.budget_tracker import total_spent as t; print(t())"`. Estimate the new run (see "Notes on running"). Spent plus estimate must stay under $47.
7. **Run:** `python Optimizer/loop.py claude --split dev`. After a budget stop or Ctrl-C, continue with `--resume`.
8. **Right after:** commit and push `runs/usage_log.csv` and the new `data/results/<run>/` folder.
9. **Panacea, test split only:** skip this for dev runs, because `baseline.py` can't load pool tasks. For the test run, in `.venv-panacea`, run `python Baseline/baseline.py panacea --ids <list>` with the same list (see `panacea_config.md`). Then do step 8 again for the log and `panacea_run.json`.
10. **Results:** run `python Optimizer/results.py data/results/<run> panacea_run.json --charts`, and open `notebooks/results_analysis.ipynb`.

**Frozen retry prompts (decided 2026-11-04; dev split added 2026-11-10):** the retry prompts in `AI_models/retry_prompts.py` stay frozen for the test split, because prompts tuned on the 100 eval tasks would bias the result. They may change during dev runs (`--split dev`, pool tasks not in eval). Every run records `retry_prompts_fingerprint` in `run_meta.json`. A `--split test` run refuses to start if the prompts differ from `FROZEN_FINGERPRINT`, and `--resume` refuses a run made with other prompts. `Evaluator/self_test.py` also checks the fingerprint, so it fails after a prompt edit until the fingerprint is updated. Changing a prompt is a team decision: update `FROZEN_FINGERPRINT` and `FROZEN_DATE` with the reason, and never compare runs across the change.

## Budget log
- Every API call goes through `AI_models/budget_tracker.py`, critic calls included. That's one row in `runs/usage_log.csv` (always at the repo root, wherever you start the script) with `task_id`, `arm` (`zero_shot` for attempt 0), `attempt`, `call_type` (`generator` / `critic`), tokens and cost. Copied-forward attempts make no call and get no row.
- The same log covers `baseline.py`'s `claude` and `panacea` runs (arms `baseline_claude`, `baseline_panacea`), so the stop counts all Claude spending on this machine.
- New calls stop at $47 of the $50 budget.
- Input and output tokens come from the API. Only a failed call has estimated counts (about 4 characters per token, `estimated=True`).
- Mock runs write their own `usage_log.csv` inside the run folder, never the real one.
- **The log is committed (decided 2026-11-03).** The $47 stop only sees the rows in your local copy, so: `git pull` before any paid run, and commit and push `runs/usage_log.csv` right after it. Two people running paid jobs at the same time would each miss the other's spending, and their logs would conflict on merge.

## Results: `data/results/<date>_<provider>_<task list>/`
| file | rows |
|---|---|
| `run_meta.json` | the settings: scoring version, provider, model, temperature, `max_tokens`, task ids, arms, retries, `retry_prompts_fingerprint`, git commit, start/finish |
| `attempt_0.jsonl` | one per task |
| `attempt_1.jsonl` … `attempt_3.jsonl` | one per (task that failed attempt 0's public tests × arm) |
| `summary.json` | the numbers below |
| `report.md` | the same text the terminal prints: run health, main table, attempts, cells, self-correction, breakdowns, paired tests with Holm p values, task ids |

Row fields (the same in every attempt file):

| field | meaning |
|---|---|
| `task_id`, `source`, `difficulty`, `test_format` | from the dataset. MBPP and LiveCodeBench difficulty are different scales: never pool them |
| `arm`, `attempt` | `zero_shot` at attempt 0, else the arm name; 0–3 |
| `hidden_score`, `hidden_test_pass_rate`, `hidden_tests` | pass@1 on the hidden tests (the headline), the fraction passed, and `"7/10"`. Counts only: no hidden test text is ever stored |
| `public_score`, `public_test_pass_rate`, `public_tests` | the same on the public tests |
| `false_pass` | passes the public tests but fails the hidden ones (a *false fix* when it happens on a retry) |
| `rubric_level`, `level`, `failure_type` | from the hidden scoring (`Evaluator/evaluator.py`) |
| `regression` | the hidden test pass rate went **down** from this arm's previous attempt (null at attempt 0 and on a failed run) |
| `carried_forward` | copied from the previous attempt after a public pass; no call made |
| `failed_run`, `error` | the API call failed after the SDK's retries (scored 0) / the error name |
| `calls`, `input_tokens`, `output_tokens`, `tokens_estimated`, `cost_usd`, `latency_s` | per attempt (critic attempts sum both calls); they match the usage-log rows. `tokens_estimated` = calls whose counts were estimated |
| `prompt`, `critique`, `output` | exactly what was sent and returned (`critique` only in the critic arm) |

`summary.json` has the fields below. Everywhere, `hidden_pass@1` and `public_pass@1` count failed attempt-0 API calls as 0, and `*_excl_failed` leaves those tasks out. Failed retries count 0 in both.
- `attempt_0`: hidden and public pass@1, failed runs, the A/B/C/D cell counts and ids, calls and cost.
- `all_tasks`, per arm: hidden and public pass@1 over **every** task at attempts 0–3 (A and B keep their attempt-0 result), each also as `*_excl_failed`, false passes, and the whole pipeline's calls and cost (attempt 0 + the arm's retries). This is the number to put beside zero-shot and Panacea.
- `arms`, per arm, on the **paired set** only (C + D, every arm finished): the self-correction view.
  - hidden and public pass@1 at attempts 0–3, and gain over the control
  - repairs (D tasks that pass hidden at attempt 3) and `repair_rate` over D
  - breaks (C tasks that fail hidden at attempt 3)
  - false fixes at attempt 3, regressions, failed runs (total and per attempt)
  - calls, tokens, $, $ per repair
- `all_tasks_by_source_difficulty`: cells, failed runs, zero-shot and each arm's final hidden pass@1 per group. `by_source_difficulty` and `by_attempt0_failure_type`: the paired curves split the same way.
- `diagnostics`: truncated answers, missing or several code blocks, critiques with code, tokens per call.
- `paired_tests`: the `feedback_vs_control` and `vs_zero_shot` families, with raw p, `p_holm` and `significant`.

`python Evaluator/self_test.py` checks all of this with a scripted model on a real task, no API.
