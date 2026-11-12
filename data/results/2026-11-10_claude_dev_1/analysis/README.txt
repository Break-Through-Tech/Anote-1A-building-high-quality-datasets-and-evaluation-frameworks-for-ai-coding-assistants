
results.py

Detailed results tables for one Evaluator-Optimizer loop run (Optimizer/loop.py), optionally with
Panacea's zero-shot run (Baseline/baseline.py panacea) beside it. Every table is a pandas DataFrame,
also written as a CSV, and notebooks/results_analysis.ipynb loads them for analysis.

Systems and attempts:
  zero_shot   Claude's attempt 0 (shared by every arm; the official Claude zero-shot result)
  <arm>       control / bare_retry / reflect_fix / critic, attempts 0-3. Attempt 0 is the shared zero-shot
              answer. Tasks that passed their public tests at attempt 0 (cells A and B) keep that answer at
              every attempt, so every arm covers every task at every attempt.
  panacea     Panacea's agent, one run per task (attempt 0 only; no retry arms)

Attempt-0 cells (Claude, and Panacea on its own results):
  A true pass (public pass, hidden pass)    B false pass (public pass, hidden fail)
  C hidden-only pass (public fail, hidden)  D true fail (public fail, hidden fail)    failed (API call failed)
Only C and D go into the arms.

Tables (CSV name -> what it holds):
  attempts.csv         long table: one row per system x task x attempt, every field (the source of the rest),
                       plus the grouping columns source_difficulty, task_type, attempt0_failure_type (Claude's)
  tasks.csv            wide table: one row per task; hidden "passed/total" and rubric level for zero-shot,
                       every arm at attempts 1-3, and Panacea
  main.csv             per system x attempt: hidden pass@1 (failed runs 0 / left out, the latter with a Wilson
                       95% CI), mean hidden test pass rate, public pass@1, false passes, rubric level counts 0-4,
                       calls and cost (this attempt and cumulative)
  curves.csv           per scope x arm x attempt: hidden pass@1 with a Wilson 95% CI, and the gain over the
                       control on the same tasks with a paired bootstrap 95% CI (tasks resampled, 2000 draws,
                       seed 0). Scopes: all = every task, failed attempt-0 calls counted 0 (summary.json's all_tasks;
                       hidden_pass@1_excl_failed leaves them out), paired = C + D (summary.json's arms),
                       D = the repair targets only
  arm_outcomes.csv     per arm, tasks that went into the arms, at the last attempt: repairs (D now passing hidden,
                       Wilson CI), breaks (C now failing), false fixes (public pass, hidden fail; from D / from C,
                       and as a share of the public "fixes"), regressions (events, tasks, rate per retry that ran),
                       failed API calls, retry calls / tokens / $, $ / tokens / calls per repair, extra repairs and
                       extra $ per extra repair vs the control (negative: more repairs for less money than the
                       control), and the pipeline cost (attempt 0 on every task + the arm's retries)
  cells.csv            per system: A/B/C/D/failed counts, the B tasks' mean hidden test pass rate, task ids
  transitions.csv      per arm x step (0->1, 1->2, 2->3), tasks that went into the arms: fixed, broke, stayed
                       pass / fail, level up / down / same, first public pass at this step, failed API calls.
                       Each step compares with the last good attempt; a failed API call is counted only as one
  retry_value.csv      per arm x attempt 1-3, every task: hidden pass@1 gained, tasks solved, failed API calls,
                       cost of this attempt, $ and calls per extra solved task
  stops.csv            per arm: tasks that went into the arms, by the attempt of their first public pass
  failure_types.csv    per system x attempt: count of each failure_type (hidden scoring)
  failure_moves.csv    per arm: failure_type at attempt 0 -> at attempt 3, tasks that went into the arms
  by_group.csv         main.csv's key numbers and the gain over the control, split by source/difficulty, test
                       format and task type (scope all: every task, failed runs 0; and scope paired: C + D), and by
                       Claude's attempt-0 failure type (paired only). MBPP and LiveCodeBench difficulties are
                       different scales: always grouped by source
  paired_tests.csv     exact McNemar tests on per-task hidden pass/fail: every pair of arms at attempts 1-3,
                       each arm vs its previous attempt, each arm vs zero-shot at attempts 1-3, Panacea vs
                       zero-shot and vs each arm at attempt 3. p_exact_mcnemar is raw; p_holm is Holm-adjusted
                       within its family and significant means p_holm < 0.05. Families: feedback_vs_control
                       (each feedback arm vs the control at the last attempt: the research question),
                       vs_zero_shot (each arm at the last attempt), panacea, exploratory (the rest).

Usage (from the repo root):
    python Optimizer/results.py data/results/<run>                     # loop run only
    python Optimizer/results.py data/results/<run> panacea_run.json    # + Panacea
    python Optimizer/results.py data/results/<run> panacea_run.json --charts   # + PNG charts (Optimizer/charts.py)
CSVs go to data/results/<run>/analysis/ (or --out), charts to analysis/charts/. The run must be finished, and the Panacea run must
cover the same tasks with the same scoring version (same checks as report.py).
