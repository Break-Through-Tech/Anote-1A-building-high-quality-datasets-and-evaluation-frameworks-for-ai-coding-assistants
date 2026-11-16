# Results: 2026-11-11_claude_dev_1

Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, task list None (10 tasks), split dev, scoring_version 3. Status: finished.
Pass@1 is on the hidden tests unless marked public. Failed attempt-0 API calls count 0; "excl. failed" leaves those tasks out. Failed retries count 0 in both.

## Run health
Failed API calls per attempt:
| arm | a0 | a1 | a2 | a3 | total |
|---|---|---|---|---|---|
| zero_shot | 0 | - | - | - | 0 |
| control | - | 0 | 0 | 0 | 0 |
| bare_retry | - | 0 | 0 | 0 | 0 |
| reflect_fix | - | 0 | 0 | 0 | 0 |
| critic | - | 0 | 0 | 0 | 0 |

Truncated answers: 4 ['livecodebench-arc195_b/zero_shot/0', 'livecodebench-arc190_a/zero_shot/0', 'livecodebench-arc190_a/control/1', 'livecodebench-arc190_a/bare_retry/1']
No code block: 2 ['livecodebench-arc190_a/control/2', 'livecodebench-arc190_a/control/3']
Several code blocks: 8 ['mbpp-471/zero_shot/0', 'mbpp-227/zero_shot/0', 'mbpp-250/zero_shot/0', 'livecodebench-arc195_b/zero_shot/0', 'livecodebench-arc194_d/zero_shot/0', 'livecodebench-arc190_a/zero_shot/0', 'livecodebench-arc190_a/bare_retry/1', 'livecodebench-arc190_a/bare_retry/2']
Critiques containing code: 0 
Tasks with missing arm attempts: 0 
Calls with estimated tokens at attempt 0: 0
Tokens per call: {'zero_shot': {'input': 430, 'output': 1528}, 'control': {'input': 886, 'output': 2103}, 'bare_retry': {'input': 2296, 'output': 2713}, 'reflect_fix': {'input': 3092, 'output': 2729}, 'critic': {'input': 3207, 'output': 1246}}

## Main results (all tasks)
| arm | n | hidden pass@1 | hidden pass@1 (excl. failed) | public pass@1 | false passes | failed API calls | calls | cost $ |
|---|---|---|---|---|---|---|---|---|
| claude zero-shot (attempt 0) | 10 | 0.800 | 0.800 | 0.900 | 1 | 0 | 10 | 0.242 |
| claude + control (attempt 3) | 10 | 0.800 | 0.800 | 0.900 | 1 | 0 | 13 | 0.345 |
| claude + bare_retry (attempt 3) | 10 | 0.800 | 0.800 | 0.900 | 1 | 0 | 13 | 0.385 |
| claude + reflect_fix (attempt 3) | 10 | 0.800 | 0.800 | 0.900 | 1 | 0 | 13 | 0.393 |
| claude + critic (attempt 3) | 10 | 0.800 | 0.800 | 0.900 | 1 | 0 | 16 | 0.412 |

## All tasks by attempt (A and B keep attempt 0)
| arm | hidden pass@1, a0-a1-a2-a3 | excl. failed | public pass@1 |
|---|---|---|---|
| control | 0.800 / 0.800 / 0.800 / 0.800 | 0.800 / 0.800 / 0.800 / 0.800 | 0.900 / 0.900 / 0.900 / 0.900 |
| bare_retry | 0.800 / 0.800 / 0.800 / 0.800 | 0.800 / 0.800 / 0.800 / 0.800 | 0.900 / 0.900 / 0.900 / 0.900 |
| reflect_fix | 0.800 / 0.800 / 0.800 / 0.800 | 0.800 / 0.800 / 0.800 / 0.800 | 0.900 / 0.900 / 0.900 / 0.900 |
| critic | 0.800 / 0.800 / 0.800 / 0.800 | 0.800 / 0.800 / 0.800 / 0.800 | 0.900 / 0.900 / 0.900 / 0.900 |

## Attempt 0 cells
| A true pass | B false pass | C hidden-only pass | D true fail | failed runs | went into the arms |
|---|---|---|---|---|---|
| 8 | 1 | 0 | 1 | 0 | 1 |

B tasks pass the public tests, so no arm retries them: they cap every arm equally. C and D go into the arms; repairs are counted over D, breaks over C.

## Self-correction (the 1 tasks that went into the arms, C + D)
| arm | hidden pass@1, a0-a1-a2-a3 | gain vs control (last) | repairs (of D) | breaks (of C) | false fixes | regressions | failed API calls | calls | tokens | cost $ | $ per repair | calls per repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/1 | 0/0 | 0 | 1 | 0 | 3 | 8967 | 0.103 | - | - |
| bare_retry | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/1 | 0/0 | 0 | 1 | 0 | 3 | 15026 | 0.143 | - | - |
| reflect_fix | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/1 | 0/0 | 0 | 0 | 0 | 3 | 17465 | 0.151 | - | - |
| critic | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/1 | 0/0 | 0 | 0 | 0 | 6 | 26716 | 0.170 | - | - |

## By source and difficulty (all tasks, last attempt)
| group | n | A | B | C | D | failed | zero-shot | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|---|---|---|---|---|---|
| livecodebench/easy | 2 | 2 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| livecodebench/hard | 5 | 3 | 1 | 0 | 1 | 0 | 0.600 | 0.600 | 0.600 | 0.600 | 0.600 |
| mbpp/hard | 2 | 2 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| mbpp/medium | 1 | 1 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Self-correction by source and difficulty (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| livecodebench/hard | 1 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 |

## Self-correction by attempt-0 failure type (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| wrong_answer | 1 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 |

## Paired tests (exact McNemar, hidden pass/fail per task)
p (Holm) is corrected within each family. Significant: p (Holm) below 0.05. The feedback_vs_control family answers whether feedback beats a fresh resample.
| family | comparison | only first passes | only second passes | p | p (Holm) | verdict |
|---|---|---|---|---|---|---|
| feedback_vs_control | bare_retry vs control | 0 | 0 | 1.000 | 1.000 | not significant |
| feedback_vs_control | reflect_fix vs control | 0 | 0 | 1.000 | 1.000 | not significant |
| feedback_vs_control | critic vs control | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | control vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | bare_retry vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | reflect_fix vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | critic vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |

## Task ids
- A_true_pass: mbpp-471 mbpp-227 mbpp-250 livecodebench-abc390_a livecodebench-3705 livecodebench-arc194_d livecodebench-3784 livecodebench-3770
- B_false_pass: livecodebench-arc195_b
- C_hidden_only_pass: -
- D_true_fail: livecodebench-arc190_a
- C + D, every arm finished: livecodebench-arc190_a

## Notes
attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass (public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping their attempt-0 result. hidden_pass@1 and public_pass@1 count failed attempt-0 API calls as 0; *_excl_failed leaves those tasks out. Failed retries count 0 in both. paired_tests: p_holm is Holm-adjusted within each family. arms: only the tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden test pass rate went down from the arm's previous attempt. Costs are from the API's token counts (tokens_estimated = calls whose counts were estimated).
