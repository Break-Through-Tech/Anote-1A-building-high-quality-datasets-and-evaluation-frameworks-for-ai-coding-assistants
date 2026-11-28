# Results slides: 2026-11-18_claude_test_eval100_1 + 2 repeat(s)

- Runs: 2026-11-18_claude_test_eval100_1, 2026-11-25_claude_test_eval100_1, 2026-11-25_claude_test_eval100_2
- Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, 100 tasks, 3 retries, scoring v5
- Panacea: panacea_run.json
- Ranges are min to max across repeats. Pass@1 is on the hidden tests unless it says public.

## Slide: RQ1. Does feedback help Claude fix its own code?

Question: when Claude's first answer fails, does showing it test feedback fix more tasks than just asking again (the control)?

Chart: `charts/rq1_gain_vs_control.png` (backup: `charts/rq1_accuracy_by_attempt.png`)

| arm | pass@1 on retried tasks | gain vs control | repairs | breaks | significant |
|---|---|---|---|---|---|
| Ask again (control) | 28% (22% to 33%) | +0 pts | 5 (4 to 6) | 0 | - |
| Bare retry | 39% (33% to 44%) | +11 pts | 7 (6 to 8) | 0 | 0/3 |
| Reflect & fix | 46% (39% to 56%) | +19 pts (+6 pts to +28 pts) | 8.3 (7 to 10) | 0 | 0/3 |
| Critic + fix | 43% (39% to 44%) | +15 pts (+11 pts to +17 pts) | 7.7 (7 to 8) | 0 | 0/3 |

What the numbers show:

- 18 task(s) failed at attempt 0 and went into the arms; each task is worth about 6 points.
- Bare retry: +11 pts vs the control; significant (McNemar, Holm p < 0.05) in 0 of 3 repeat(s).
- Reflect & fix: +19 pts (+6 pts to +28 pts) vs the control; significant (McNemar, Holm p < 0.05) in 0 of 3 repeat(s).
- Critic + fix: +15 pts (+11 pts to +17 pts) vs the control; significant (McNemar, Holm p < 0.05) in 0 of 3 repeat(s).
- "Not significant" means this run can't tell the arms apart, not that they are equal.

Source: `tables/headline.csv` (gain_vs_control_paired, repairs, breaks, significant_repeats), `tables/curves.csv`

## Slide: RQ2. At what cost?

Chart: `charts/rq2_accuracy_vs_cost.png`

| system | pass@1 (all tasks) | pipeline cost | calls | $ per repair |
|---|---|---|---|---|
| Claude zero-shot | 77% | $2.085 | 100 | - |
| Ask again (control) | 82% (81% to 83%) | $4.125 ($4.025 to $4.322) | 152 (149 to 158) | $0.424 ($0.324 to $0.559) |
| Bare retry | 84% (83% to 85%) | $3.655 ($3.476 to $3.805) | 148 (145 to 151) | $0.230 ($0.174 to $0.287) |
| Reflect & fix | 85% (84% to 87%) | $4.219 ($4.125 to $4.358) | 149 (146 to 151) | $0.263 ($0.204 to $0.325) |
| Critic + fix | 85% (84% to 85%) | $4.038 ($3.858 to $4.198) | 178.7 (173 to 184) | $0.257 ($0.222 to $0.302) |
| Panacea agent | 72% | $4.089 | 199 | - |

Source: `tables/headline.csv` (pipeline_cost_usd, cost_per_repair_usd)

## Slide: RQ3. Panacea vs Claude zero-shot

Chart: `charts/rq3_panacea_vs_claude.png`

| system | hidden pass@1 | public pass@1 | false passes | cost | A true pass | B false pass | C hidden-only pass | D true fail | API failed |
|---|---|---|---|---|---|---|---|---|---|
| Claude zero-shot | 77% | 82% | 5 | $2.085 | 77 | 5 | 0 | 18 | 0 |
| Panacea agent | 72% | 80% | 10 | $4.089 | 70 | 10 | 2 | 16 | 2 |

False pass = passes the public tests but fails the hidden ones (looks right, isn't).

Source: `tables/headline.csv`, `tables/cells.csv`

## Slide: RQ4. Where do the models fail?

Chart: `charts/rq4_where_models_fail.png`

| failure_type | Panacea agent | Claude zero-shot |
|---|---|---|
| failed_api_call | 2.0 | 0.0 |
| passed | 72.0 | 77.0 |
| runtime_error | 0.0 | 1.0 |
| syntax_error | 1.0 | 0.0 |
| timeout | 3.0 | 2.0 |
| wrong_answer | 22.0 | 20.0 |

Source: `tables/failure_types.csv`, `tables/by_difficulty.csv`

## Slide (optional): Does telling the model it ran out of space help?

| arm | answers | told | cut_off_again |
|---|---|---|---|
| Ask again (control) | 67 | 0 | 55 |
| Bare retry | 54 | 0 | 30 |
| Reflect & fix | 59 | 59 | 37 |
| Critic + fix | 52 | 52 | 26 |

Reflect & fix and Critic are told; the control and bare retry never are. Fewer "cut off again" in the told arms would mean the note helps. Summed over repeats.

Source: `tables/cut_off_note.csv` (summary.json after_cut_off)

## Reproduce

```bash
python Optimizer/presentation.py data/results/2026-11-18_claude_test_eval100_1 data/results/2026-11-25_claude_test_eval100_1 data/results/2026-11-25_claude_test_eval100_2 --panacea panacea_run.json
```
