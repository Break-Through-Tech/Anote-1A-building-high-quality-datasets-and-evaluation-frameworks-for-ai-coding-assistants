# Results slides: 2026-11-12_claude_dev_2

> **DEV RUN - NOT A RESULT.** These numbers check the pipeline; do not present them as findings.

- Runs: 2026-11-12_claude_dev_2
- Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, 10 tasks, 3 retries, scoring v4
- Panacea: not included
- Ranges are min to max across repeats. Pass@1 is on the hidden tests unless it says public.

## Slide: RQ1. Does feedback help Claude fix its own code?

Question: when Claude's first answer fails, does showing it test feedback fix more tasks than just asking again (the control)?

Chart: `charts/rq1_gain_vs_control.png` (backup: `charts/rq1_accuracy_by_attempt.png`)

| arm | pass@1 on retried tasks | gain vs control | repairs | breaks | significant |
|---|---|---|---|---|---|
| Ask again (control) | 100% | +0 pts | 1 | 0 | - |
| Bare retry | 0% | -100 pts | 0 | 0 | 0/1 |
| Reflect & fix | 100% | +0 pts | 1 | 0 | 0/1 |
| Critic + fix | 0% | -100 pts | 0 | 0 | 0/1 |

What the numbers show:

- 1 task(s) failed at attempt 0 and went into the arms; each task is worth about 100 points.
- Bare retry: -100 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- Reflect & fix: +0 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- Critic + fix: -100 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 1 repeat(s).
- "Not significant" means this run can't tell the arms apart, not that they are equal.

Source: `tables/headline.csv` (gain_vs_control_paired, repairs, breaks, significant_repeats), `tables/curves.csv`

## Slide: RQ2. At what cost?

Chart: `charts/rq2_accuracy_vs_cost.png`

| system | pass@1 (all tasks) | pipeline cost | calls | $ per repair |
|---|---|---|---|---|
| Claude zero-shot | 60% | $0.274 | 10 | - |
| Ask again (control) | 70% | $0.296 | 11 | $0.022 |
| Bare retry | 60% | $0.352 | 13 | - |
| Reflect & fix | 70% | $0.338 | 12 | $0.064 |
| Critic + fix | 60% | $0.314 | 12 | - |

Source: `tables/headline.csv` (pipeline_cost_usd, cost_per_repair_usd)

## Slide: RQ3. Panacea vs Claude zero-shot

Panacea is not in this pack yet. Run `python Baseline/baseline.py panacea --ids <same task list>`, then rerun this script with `--panacea <that file>`.

## Slide: RQ4. Where do the models fail?

Chart: `charts/rq4_where_models_fail.png`

| failure_type | Claude zero-shot |
|---|---|
| passed | 6.0 |
| timeout | 1.0 |
| wrong_answer | 3.0 |

Source: `tables/failure_types.csv`, `tables/by_difficulty.csv`

## Slide (optional): Does telling the model it ran out of space help?

| arm | answers | told | cut_off_again |
|---|---|---|---|
| Ask again (control) | 1 | 0 | 0 |
| Bare retry | 1 | 0 | 0 |
| Reflect & fix | 1 | 1 | 0 |
| Critic + fix | 1 | 1 | 0 |

Reflect & fix and Critic are told; the control and bare retry never are. Fewer "cut off again" in the told arms would mean the note helps. Summed over repeats.

Source: `tables/cut_off_note.csv` (summary.json after_cut_off)

## Reproduce

```bash
python Optimizer/presentation.py data/results/2026-11-12_claude_dev_2
```
