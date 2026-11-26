# Results slides: 2026-11-18_claude_test_eval100_1

- Runs: 2026-11-18_claude_test_eval100_1
- Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, 100 tasks, 3 retries, scoring v5
- Panacea: not included
- Ranges are min to max across repeats. Pass@1 is on the hidden tests unless it says public.

## Slide: RQ1. Does feedback help Claude fix its own code?

Question: when Claude's first answer fails, does showing it test feedback fix more tasks than just asking again (the control)?

Chart: `charts/rq1_gain_vs_control.png` (backup: `charts/rq1_accuracy_by_attempt.png`)

| arm | pass@1 on retried tasks | gain vs control | repairs | breaks | significant |
|---|---|---|---|---|---|
| Ask again (control) | 22% | +0 pts | 4 | 0 | - |
| Bare retry | 33% | +11 pts | 6 | 0 | 0/1 |
| Reflect & fix | 44% | +22 pts | 8 | 0 | 0/1 |
| Critic + fix | 39% | +17 pts | 7 | 0 | 0/1 |

What the numbers show:

- 18 task(s) failed at attempt 0 and went into the arms; each task is worth about 6 points.
- Bare retry: +11 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- Reflect & fix: +22 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- Critic + fix: +17 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- "Not significant" means this run can't tell the arms apart, not that they are equal.

Source: `tables/headline.csv` (gain_vs_control_paired, repairs, breaks, significant_repeats), `tables/curves.csv`

## Slide: RQ2. At what cost?

Chart: `charts/rq2_accuracy_vs_cost.png`

| system | pass@1 (all tasks) | pipeline cost | calls | $ per repair |
|---|---|---|---|---|
| Claude zero-shot | 77% | $2.085 | 100 | - |
| Ask again (control) | 81% | $4.322 | 158 | $0.559 |
| Bare retry | 83% | $3.805 | 151 | $0.287 |
| Reflect & fix | 85% | $4.175 | 150 | $0.261 |
| Critic + fix | 84% | $4.198 | 184 | $0.302 |

Source: `tables/headline.csv` (pipeline_cost_usd, cost_per_repair_usd)

## Slide: RQ3. Panacea vs Claude zero-shot

Panacea is not in this pack yet. Run `python Baseline/baseline.py panacea --ids <same task list>`, then rerun this script with `--panacea <that file>`.

## Slide: RQ4. Where do the models fail?

Chart: `charts/rq4_where_models_fail.png`

| failure_type | Claude zero-shot |
|---|---|
| passed | 77.0 |
| runtime_error | 1.0 |
| timeout | 2.0 |
| wrong_answer | 20.0 |

Source: `tables/failure_types.csv`, `tables/by_difficulty.csv`

## Slide (optional): Does telling the model it ran out of space help?

| arm | answers | told | cut_off_again |
|---|---|---|---|
| Ask again (control) | 23 | 0 | 19 |
| Bare retry | 22 | 0 | 13 |
| Reflect & fix | 19 | 19 | 12 |
| Critic + fix | 17 | 17 | 8 |

Reflect & fix and Critic are told; the control and bare retry never are. Fewer "cut off again" in the told arms would mean the note helps. Summed over repeats.

Source: `tables/cut_off_note.csv` (summary.json after_cut_off)

## Reproduce

```bash
python Optimizer/presentation.py data/results/2026-11-18_claude_test_eval100_1
```
