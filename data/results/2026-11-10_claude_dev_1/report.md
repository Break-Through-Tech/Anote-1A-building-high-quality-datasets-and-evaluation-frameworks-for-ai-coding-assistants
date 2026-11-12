# Results: 2026-11-10_claude_dev_1

Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, task list None (10 tasks), split dev, scoring_version 2. Status: finished.
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

Truncated answers: 13 ['livecodebench-arc190_a/zero_shot/0', 'livecodebench-abc397_g/zero_shot/0', 'livecodebench-3717/zero_shot/0', 'livecodebench-arc190_a/control/1', 'livecodebench-arc190_a/reflect_fix/1', 'livecodebench-abc397_g/control/1', 'livecodebench-abc397_g/reflect_fix/1', 'livecodebench-arc190_a/reflect_fix/2', 'livecodebench-abc397_g/control/2', 'livecodebench-3717/bare_retry/2', 'livecodebench-arc190_a/control/3', 'livecodebench-arc190_a/reflect_fix/3', 'livecodebench-abc397_g/reflect_fix/3']
No code block: 5 ['livecodebench-arc190_a/reflect_fix/1', 'livecodebench-abc397_g/reflect_fix/1', 'livecodebench-arc190_a/control/2', 'livecodebench-abc397_g/control/2', 'livecodebench-abc397_g/control/3']
Several code blocks: 14 ['mbpp-471/zero_shot/0', 'mbpp-227/zero_shot/0', 'mbpp-250/zero_shot/0', 'livecodebench-abc400_c/zero_shot/0', 'livecodebench-arc190_a/zero_shot/0', 'livecodebench-abc397_g/zero_shot/0', 'livecodebench-3717/zero_shot/0', 'livecodebench-arc190_a/critic/1', 'livecodebench-3717/control/1', 'livecodebench-3717/bare_retry/1', 'livecodebench-3717/control/2', 'livecodebench-3717/bare_retry/2', 'livecodebench-3717/control/3', 'livecodebench-3717/bare_retry/3']
Critiques containing code: 0 
Tasks with missing arm attempts: 0 
Calls with estimated tokens at attempt 0: 0
Tokens per call: {'zero_shot': {'input': 411, 'output': 1737}, 'control': {'input': 656, 'output': 2777}, 'bare_retry': {'input': 1826, 'output': 1891}, 'reflect_fix': {'input': 2986, 'output': 3070}, 'critic': {'input': 2337, 'output': 1127}}

## Main results (all tasks)
| arm | n | hidden pass@1 | hidden pass@1 (excl. failed) | public pass@1 | false passes | failed API calls | calls | cost $ |
|---|---|---|---|---|---|---|---|---|
| claude zero-shot (attempt 0) | 10 | 0.600 | 0.600 | 0.700 | 1 | 0 | 10 | 0.273 |
| claude + control (attempt 3) | 10 | 0.600 | 0.600 | 0.700 | 1 | 0 | 19 | 0.665 |
| claude + bare_retry (attempt 3) | 10 | 0.600 | 0.600 | 0.700 | 1 | 0 | 19 | 0.578 |
| claude + reflect_fix (attempt 3) | 10 | 0.600 | 0.600 | 0.700 | 1 | 0 | 19 | 0.768 |
| claude + critic (attempt 3) | 10 | 0.700 | 0.700 | 0.800 | 1 | 0 | 26 | 0.656 |

## All tasks by attempt (A and B keep attempt 0)
| arm | hidden pass@1, a0-a1-a2-a3 | excl. failed | public pass@1 |
|---|---|---|---|
| control | 0.600 / 0.600 / 0.600 / 0.600 | 0.600 / 0.600 / 0.600 / 0.600 | 0.700 / 0.700 / 0.700 / 0.700 |
| bare_retry | 0.600 / 0.600 / 0.600 / 0.600 | 0.600 / 0.600 / 0.600 / 0.600 | 0.700 / 0.700 / 0.700 / 0.700 |
| reflect_fix | 0.600 / 0.600 / 0.600 / 0.600 | 0.600 / 0.600 / 0.600 / 0.600 | 0.700 / 0.700 / 0.700 / 0.700 |
| critic | 0.600 / 0.600 / 0.700 / 0.700 | 0.600 / 0.600 / 0.700 / 0.700 | 0.700 / 0.700 / 0.800 / 0.800 |

## Attempt 0 cells
| A true pass | B false pass | C hidden-only pass | D true fail | failed runs | went into the arms |
|---|---|---|---|---|---|
| 6 | 1 | 0 | 3 | 0 | 3 |

B tasks pass the public tests, so no arm retries them: they cap every arm equally. C and D go into the arms; repairs are counted over D, breaks over C.

## Self-correction (the 3 tasks that went into the arms, C + D)
| arm | hidden pass@1, a0-a1-a2-a3 | gain vs control (last) | repairs (of D) | breaks (of C) | false fixes | regressions | failed API calls | calls | tokens | cost $ | $ per repair | calls per repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/3 | 0/0 | 0 | 2 | 0 | 9 | 30898 | 0.393 | - | - |
| bare_retry | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/3 | 0/0 | 0 | 1 | 0 | 9 | 33454 | 0.305 | - | - |
| reflect_fix | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 | 0/3 | 0/0 | 0 | 3 | 0 | 9 | 54501 | 0.495 | - | - |
| critic | 0.000 / 0.000 / 0.333 / 0.333 | 0.333 | 1/3 | 0/0 | 0 | 1 | 0 | 16 | 55428 | 0.383 | 0.3827 | 16.000 |

## By source and difficulty (all tasks, last attempt)
| group | n | A | B | C | D | failed | zero-shot | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|---|---|---|---|---|---|
| livecodebench/easy | 2 | 2 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| livecodebench/hard | 3 | 0 | 0 | 0 | 3 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.333 |
| livecodebench/medium | 2 | 1 | 1 | 0 | 0 | 0 | 0.500 | 0.500 | 0.500 | 0.500 | 0.500 |
| mbpp/hard | 2 | 2 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| mbpp/medium | 1 | 1 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## Self-correction by source and difficulty (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| livecodebench/hard | 3 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.333 / 0.333 |

## Self-correction by attempt-0 failure type (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| runtime_error | 1 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 1.000 / 1.000 |
| wrong_answer | 2 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 |

## Paired tests (exact McNemar, hidden pass/fail per task)
p (Holm) is corrected within each family. Significant: p (Holm) below 0.05. The feedback_vs_control family answers whether feedback beats a fresh resample.
| family | comparison | only first passes | only second passes | p | p (Holm) | verdict |
|---|---|---|---|---|---|---|
| feedback_vs_control | bare_retry vs control | 0 | 0 | 1.000 | 1.000 | not significant |
| feedback_vs_control | reflect_fix vs control | 0 | 0 | 1.000 | 1.000 | not significant |
| feedback_vs_control | critic vs control | 1 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | control vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | bare_retry vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | reflect_fix vs zero-shot | 0 | 0 | 1.000 | 1.000 | not significant |
| vs_zero_shot | critic vs zero-shot | 1 | 0 | 1.000 | 1.000 | not significant |

## Task ids
- A_true_pass: mbpp-471 mbpp-227 mbpp-250 livecodebench-abc390_a livecodebench-3705 livecodebench-3794
- B_false_pass: livecodebench-abc400_c
- C_hidden_only_pass: -
- D_true_fail: livecodebench-arc190_a livecodebench-abc397_g livecodebench-3717
- C + D, every arm finished: livecodebench-arc190_a livecodebench-abc397_g livecodebench-3717

## Notes
attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass (public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping their attempt-0 result. hidden_pass@1 and public_pass@1 count failed attempt-0 API calls as 0; *_excl_failed leaves those tasks out. Failed retries count 0 in both. paired_tests: p_holm is Holm-adjusted within each family. arms: only the tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden test pass rate went down from the arm's previous attempt. Costs are from the API's token counts (tokens_estimated = calls whose counts were estimated).
