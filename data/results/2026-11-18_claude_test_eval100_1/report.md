# Results: 2026-11-18_claude_test_eval100_1

Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, task list eval100.txt (100 tasks), split test, scoring_version 5. Status: finished.
Pass@1 is on the hidden tests unless marked public. Failed attempt-0 API calls count 0; "excl. failed" leaves those tasks out. Failed retries count 0 in both.

## Run health
Failed API calls per attempt:
| arm | a0 | a1 | a2 | a3 | total |
|---|---|---|---|---|---|
| zero_shot | 38 | - | - | - | 38 |
| control | - | 0 | 0 | 0 | 0 |
| bare_retry | - | 0 | 0 | 0 | 0 |
| reflect_fix | - | 0 | 0 | 1 | 1 |
| critic | - | 1 | 1 | 1 | 3 |

Truncated answers: 30 ['livecodebench-abc389_g/zero_shot/0', 'livecodebench-abc389_f/zero_shot/0', 'livecodebench-abc390_g/zero_shot/0', 'livecodebench-abc400_g/zero_shot/0', 'livecodebench-arc192_a/zero_shot/0', 'livecodebench-arc193_b/zero_shot/0', 'livecodebench-abc389_g/control/1', 'livecodebench-abc389_g/bare_retry/1', 'livecodebench-abc389_g/reflect_fix/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-abc390_g/control/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc193_b/control/1', 'livecodebench-arc193_b/bare_retry/1', 'livecodebench-arc193_b/reflect_fix/1', 'livecodebench-abc389_g/control/2', 'livecodebench-abc389_g/bare_retry/2', 'livecodebench-abc389_g/critic/2', 'livecodebench-abc390_g/control/2', 'livecodebench-abc390_g/bare_retry/2', 'livecodebench-arc192_a/bare_retry/2', 'livecodebench-arc193_b/control/2', 'livecodebench-arc193_b/bare_retry/2', 'livecodebench-arc193_b/reflect_fix/2', 'livecodebench-abc389_g/critic/3', 'livecodebench-abc390_g/control/3', 'livecodebench-abc390_g/bare_retry/3', 'livecodebench-arc192_a/control/3', 'livecodebench-arc193_b/control/3', 'livecodebench-arc193_b/bare_retry/3']
Finalized answers (cut off with no complete code block, then a follow-up call gave the final code): 11 ['livecodebench-abc389_g/control/1', 'livecodebench-abc389_g/reflect_fix/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc193_b/control/1', 'livecodebench-arc193_b/reflect_fix/1', 'livecodebench-arc193_b/bare_retry/2', 'livecodebench-arc193_b/reflect_fix/2', 'livecodebench-abc389_g/critic/3', 'livecodebench-arc192_a/control/3', 'livecodebench-arc193_b/control/3']
No code block: 0 
Several code blocks: 63 ['mbpp-603/zero_shot/0', 'mbpp-622/zero_shot/0', 'mbpp-637/zero_shot/0', 'mbpp-720/zero_shot/0', 'mbpp-741/zero_shot/0', 'mbpp-749/zero_shot/0', 'mbpp-754/zero_shot/0', 'mbpp-759/zero_shot/0', 'mbpp-773/zero_shot/0', 'mbpp-781/zero_shot/0', 'mbpp-808/zero_shot/0', 'mbpp-75/zero_shot/0', 'mbpp-235/zero_shot/0', 'mbpp-242/zero_shot/0', 'mbpp-281/zero_shot/0', 'mbpp-286/zero_shot/0', 'mbpp-395/zero_shot/0', 'mbpp-421/zero_shot/0', 'mbpp-445/zero_shot/0', 'livecodebench-abc387_f/zero_shot/0', 'livecodebench-abc387_c/zero_shot/0', 'livecodebench-abc388_d/zero_shot/0', 'livecodebench-abc388_c/zero_shot/0', 'livecodebench-abc388_e/zero_shot/0', 'livecodebench-abc389_g/zero_shot/0', 'livecodebench-abc389_f/zero_shot/0', 'livecodebench-abc389_e/zero_shot/0', 'livecodebench-abc390_c/zero_shot/0', 'livecodebench-abc391_g/zero_shot/0', 'livecodebench-abc392_g/zero_shot/0', 'livecodebench-abc393_d/zero_shot/0', 'livecodebench-abc397_b/zero_shot/0', 'livecodebench-arc193_b/zero_shot/0', 'mbpp-749/control/1', 'mbpp-773/control/1', 'livecodebench-abc389_g/bare_retry/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-abc390_g/control/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc192_a/bare_retry/1', 'livecodebench-arc192_a/reflect_fix/1', 'livecodebench-arc192_a/critic/1', 'livecodebench-arc193_b/bare_retry/1', 'livecodebench-arc193_b/reflect_fix/1', 'mbpp-773/control/2', 'mbpp-235/control/2', 'livecodebench-abc389_g/control/2', 'livecodebench-abc389_g/bare_retry/2', 'livecodebench-abc389_g/critic/2', 'livecodebench-abc390_g/control/2', 'livecodebench-abc390_g/bare_retry/2', 'livecodebench-arc192_a/control/2', 'livecodebench-arc192_a/bare_retry/2', 'livecodebench-arc193_b/control/2', 'livecodebench-arc193_b/reflect_fix/2', 'mbpp-603/control/3', 'mbpp-749/control/3', 'mbpp-773/control/3', 'mbpp-235/bare_retry/3', 'livecodebench-abc389_g/bare_retry/3', 'livecodebench-abc389_g/critic/3', 'livecodebench-abc390_g/bare_retry/3', 'livecodebench-arc193_b/control/3']
Critiques containing code: 0 
Tasks with missing arm attempts: 0 
Calls with estimated tokens at attempt 0: 38
Tokens per call: {'zero_shot': {'input': 361, 'output': 669}, 'control': {'input': 1071, 'output': 1998}, 'bare_retry': {'input': 1155, 'output': 1724}, 'reflect_fix': {'input': 2026, 'output': 1713}, 'critic': {'input': 1577, 'output': 897}}

## Main results (all tasks)
| arm | n | hidden pass@1 | hidden pass@1 (excl. failed) | public pass@1 | false passes | failed API calls | calls | cost $ |
|---|---|---|---|---|---|---|---|---|
| claude zero-shot (attempt 0) | 100 | 0.480 | 0.774 | 0.520 | 4 | 38 | 100 | 1.112 |
| claude + control (attempt 3) | 100 | 0.500 | 0.806 | 0.550 | 5 | 38 | 132 | 2.174 |
| claude + bare_retry (attempt 3) | 100 | 0.520 | 0.839 | 0.560 | 4 | 38 | 127 | 1.904 |
| claude + reflect_fix (attempt 3) | 100 | 0.550 | 0.887 | 0.610 | 6 | 39 | 116 | 1.621 |
| claude + critic (attempt 3) | 100 | 0.540 | 0.871 | 0.590 | 5 | 41 | 131 | 1.676 |

## All tasks by attempt (A and B keep attempt 0)
| arm | hidden pass@1, a0-a1-a2-a3 | excl. failed | public pass@1 |
|---|---|---|---|
| control | 0.480 / 0.490 / 0.500 / 0.500 | 0.774 / 0.790 / 0.806 / 0.806 | 0.520 / 0.530 / 0.540 / 0.550 |
| bare_retry | 0.480 / 0.500 / 0.500 / 0.520 | 0.774 / 0.806 / 0.806 / 0.839 | 0.520 / 0.540 / 0.540 / 0.560 |
| reflect_fix | 0.480 / 0.540 / 0.550 / 0.550 | 0.774 / 0.871 / 0.887 / 0.887 | 0.520 / 0.600 / 0.610 / 0.610 |
| critic | 0.480 / 0.540 / 0.540 / 0.540 | 0.774 / 0.871 / 0.871 / 0.871 | 0.520 / 0.590 / 0.590 / 0.590 |

## Attempt 0 cells
| A true pass | B false pass | C hidden-only pass | D true fail | failed runs | went into the arms |
|---|---|---|---|---|---|
| 48 | 4 | 0 | 10 | 38 | 10 |

B tasks pass the public tests, so no arm retries them: they cap every arm equally. C and D go into the arms; repairs are counted over D, breaks over C.

## Self-correction (the 10 tasks that went into the arms, C + D)
| arm | hidden pass@1, a0-a1-a2-a3 | gain vs control (last) | repairs (of D) | breaks (of C) | false fixes | regressions | failed API calls | calls | tokens | cost $ | $ per repair | calls per repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 0.000 / 0.100 / 0.200 / 0.200 | 0.000 | 2/10 | 0/0 | 1 | 1 | 0 | 32 | 98206 | 1.062 | 0.5309 | 16.000 |
| bare_retry | 0.000 / 0.200 / 0.200 / 0.400 | 0.200 | 4/10 | 0/0 | 0 | 2 | 0 | 27 | 77735 | 0.792 | 0.1980 | 6.750 |
| reflect_fix | 0.000 / 0.600 / 0.700 / 0.700 | 0.500 | 7/10 | 0/0 | 2 | 0 | 1 | 16 | 59831 | 0.508 | 0.0726 | 2.290 |
| critic | 0.000 / 0.600 / 0.600 / 0.600 | 0.400 | 6/10 | 0/0 | 1 | 0 | 3 | 31 | 76689 | 0.564 | 0.0940 | 5.170 |

## By source and difficulty (all tasks, last attempt)
| group | n | A | B | C | D | failed | zero-shot | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|---|---|---|---|---|---|
| livecodebench/easy | 27 | 16 | 0 | 0 | 0 | 11 | 0.593 | 0.593 | 0.593 | 0.593 | 0.593 |
| livecodebench/hard | 26 | 9 | 2 | 0 | 3 | 12 | 0.346 | 0.346 | 0.385 | 0.385 | 0.385 |
| livecodebench/medium | 27 | 11 | 0 | 0 | 1 | 15 | 0.407 | 0.444 | 0.407 | 0.444 | 0.444 |
| mbpp/hard | 10 | 4 | 2 | 0 | 4 | 0 | 0.400 | 0.500 | 0.600 | 0.700 | 0.600 |
| mbpp/medium | 10 | 8 | 0 | 0 | 2 | 0 | 0.800 | 0.800 | 0.900 | 1.000 | 1.000 |

## Self-correction by source and difficulty (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| livecodebench/hard | 3 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.333 | 0.000 / 0.333 / 0.333 / 0.333 | 0.000 / 0.333 / 0.333 / 0.333 |
| livecodebench/medium | 1 | 0.000 / 0.000 / 1.000 / 1.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 1.000 / 1.000 / 1.000 | 0.000 / 1.000 / 1.000 / 1.000 |
| mbpp/hard | 4 | 0.000 / 0.250 / 0.250 / 0.250 | 0.000 / 0.500 / 0.500 / 0.500 | 0.000 / 0.500 / 0.750 / 0.750 | 0.000 / 0.500 / 0.500 / 0.500 |
| mbpp/medium | 2 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.500 | 0.000 / 1.000 / 1.000 / 1.000 | 0.000 / 1.000 / 1.000 / 1.000 |

## Self-correction by attempt-0 failure type (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| wrong_answer | 10 | 0.000 / 0.100 / 0.200 / 0.200 | 0.000 / 0.200 / 0.200 / 0.400 | 0.000 / 0.600 / 0.700 / 0.700 | 0.000 / 0.600 / 0.600 / 0.600 |

## Cut-off sensitivity (hidden pass@1 at attempt 3)
Tasks where any answer hit max_tokens: 6 of 100 ['livecodebench-abc389_f', 'livecodebench-abc389_g', 'livecodebench-abc390_g', 'livecodebench-abc400_g', 'livecodebench-arc192_a', 'livecodebench-arc193_b']. The right-hand columns leave those tasks out for every arm. If the arms compare the same way with and without them, the token limit doesn't change the conclusion. With 0 tasks left in a column, this run can't tell.
| arm | cut-off answers | all tasks (n=100) | without cut-off tasks (n=94) | C + D (n=10) | C + D without cut-off tasks (n=6) |
|---|---|---|---|---|---|
| zero-shot | 6/100 | 0.480 | 0.500 | - | - |
| control | 10/27 | 0.500 | 0.511 | 0.200 | 0.167 |
| bare_retry | 8/26 | 0.520 | 0.532 | 0.400 | 0.500 |
| reflect_fix | 3/13 | 0.550 | 0.553 | 0.700 | 0.833 |
| critic | 3/16 | 0.540 | 0.543 | 0.600 | 0.667 |

## Does telling the model it ran out of space help?
Retry answers whose previous attempt in the same arm hit max_tokens. reflect_fix and critic are told so in the test feedback; control and bare_retry never are. Fewer answers cut off again in the told arms would mean the note helps.
| arm | answers after a cut-off answer | told | cut off again |
|---|---|---|---|
| control | 10 | 0 | 9 |
| bare_retry | 10 | 0 | 6 |
| reflect_fix | 5 | 5 | 3 |
| critic | 5 | 5 | 3 |

## Paired tests (exact McNemar, hidden pass/fail per task)
p (Holm) is corrected within each family. Significant: p (Holm) below 0.05. The feedback_vs_control family answers whether feedback beats a fresh resample.
| family | comparison | only first passes | only second passes | p | p (Holm) | verdict |
|---|---|---|---|---|---|---|
| feedback_vs_control | bare_retry vs control | 3 | 1 | 0.625 | 0.625 | not significant |
| feedback_vs_control | reflect_fix vs control | 5 | 0 | 0.062 | 0.188 | not significant |
| feedback_vs_control | critic vs control | 4 | 0 | 0.125 | 0.250 | not significant |
| vs_zero_shot | control vs zero-shot | 2 | 0 | 0.500 | 0.500 | not significant |
| vs_zero_shot | bare_retry vs zero-shot | 4 | 0 | 0.125 | 0.250 | not significant |
| vs_zero_shot | reflect_fix vs zero-shot | 7 | 0 | 0.016 | 0.062 | not significant |
| vs_zero_shot | critic vs zero-shot | 6 | 0 | 0.031 | 0.094 | not significant |

## Task ids
- A_true_pass: mbpp-637 mbpp-720 mbpp-741 mbpp-754 mbpp-759 mbpp-808 mbpp-75 mbpp-242 mbpp-281 mbpp-286 mbpp-421 mbpp-445 livecodebench-abc387_b livecodebench-abc387_f livecodebench-abc387_a livecodebench-abc387_c livecodebench-abc388_d livecodebench-abc388_b livecodebench-abc388_c livecodebench-abc388_a livecodebench-abc388_e livecodebench-abc389_b livecodebench-abc389_a livecodebench-abc389_f livecodebench-abc389_e livecodebench-abc390_c livecodebench-abc391_a livecodebench-abc391_g livecodebench-abc391_b livecodebench-abc392_g livecodebench-abc392_b livecodebench-abc392_c livecodebench-abc393_a livecodebench-abc393_d livecodebench-abc393_b livecodebench-abc394_c livecodebench-abc394_a livecodebench-abc395_c livecodebench-abc395_b livecodebench-abc396_c livecodebench-abc396_d livecodebench-abc397_b livecodebench-abc398_b livecodebench-abc398_d livecodebench-abc398_a livecodebench-abc399_e livecodebench-abc399_b livecodebench-abc400_a
- B_false_pass: mbpp-622 mbpp-781 livecodebench-abc400_g livecodebench-arc191_d
- C_hidden_only_pass: -
- D_true_fail: mbpp-603 mbpp-749 mbpp-773 mbpp-235 mbpp-305 mbpp-395 livecodebench-abc389_g livecodebench-abc390_g livecodebench-arc192_a livecodebench-arc193_b
- C + D, every arm finished: mbpp-603 mbpp-749 mbpp-773 mbpp-235 mbpp-305 mbpp-395 livecodebench-abc389_g livecodebench-abc390_g livecodebench-arc192_a livecodebench-arc193_b

## Notes
attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass (public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping their attempt-0 result. hidden_pass@1 and public_pass@1 count failed attempt-0 API calls as 0; *_excl_failed leaves those tasks out. Failed retries count 0 in both. paired_tests: p_holm is Holm-adjusted within each family. arms: only the tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden test pass rate went down from the arm's previous attempt. Costs are from the API's token counts (tokens_estimated = calls whose counts were estimated).
