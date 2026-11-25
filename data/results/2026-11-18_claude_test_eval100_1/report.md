# Results: 2026-11-18_claude_test_eval100_1

Model claude-sonnet-4-6, temperature 0.5, max_tokens 4096, task list eval100.txt (100 tasks), split test, scoring_version 5. Status: finished.
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

Truncated answers: 76 ['livecodebench-abc389_g/zero_shot/0', 'livecodebench-abc389_f/zero_shot/0', 'livecodebench-abc390_g/zero_shot/0', 'livecodebench-abc400_g/zero_shot/0', 'livecodebench-arc192_a/zero_shot/0', 'livecodebench-arc193_b/zero_shot/0', 'livecodebench-arc193_a/zero_shot/0', 'livecodebench-arc194_c/zero_shot/0', 'livecodebench-arc194_e/zero_shot/0', 'livecodebench-arc194_a/zero_shot/0', 'livecodebench-arc195_e/zero_shot/0', 'livecodebench-arc195_c/zero_shot/0', 'livecodebench-arc196_c/zero_shot/0', 'livecodebench-3725/zero_shot/0', 'livecodebench-3733/zero_shot/0', 'livecodebench-abc389_g/control/1', 'livecodebench-abc389_g/bare_retry/1', 'livecodebench-abc389_g/reflect_fix/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-abc390_g/control/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc193_b/control/1', 'livecodebench-arc193_b/bare_retry/1', 'livecodebench-arc193_b/reflect_fix/1', 'livecodebench-arc193_b/critic/1', 'livecodebench-arc194_a/control/1', 'livecodebench-arc194_a/bare_retry/1', 'livecodebench-arc194_a/reflect_fix/1', 'livecodebench-arc195_e/control/1', 'livecodebench-arc195_e/bare_retry/1', 'livecodebench-arc195_e/reflect_fix/1', 'livecodebench-arc195_c/control/1', 'livecodebench-arc195_c/bare_retry/1', 'livecodebench-arc195_c/reflect_fix/1', 'livecodebench-arc195_c/critic/1', 'livecodebench-arc196_c/control/1', 'livecodebench-3725/bare_retry/1', 'livecodebench-3725/critic/1', 'livecodebench-abc389_g/control/2', 'livecodebench-abc389_g/bare_retry/2', 'livecodebench-abc389_g/critic/2', 'livecodebench-abc390_g/control/2', 'livecodebench-abc390_g/bare_retry/2', 'livecodebench-arc192_a/bare_retry/2', 'livecodebench-arc193_b/control/2', 'livecodebench-arc193_b/bare_retry/2', 'livecodebench-arc193_b/reflect_fix/2', 'livecodebench-arc195_e/control/2', 'livecodebench-arc195_e/bare_retry/2', 'livecodebench-arc195_e/reflect_fix/2', 'livecodebench-arc195_e/critic/2', 'livecodebench-arc195_c/control/2', 'livecodebench-arc195_c/bare_retry/2', 'livecodebench-arc195_c/reflect_fix/2', 'livecodebench-arc195_c/critic/2', 'livecodebench-arc196_c/control/2', 'livecodebench-arc196_c/reflect_fix/2', 'livecodebench-3725/reflect_fix/2', 'livecodebench-abc389_g/critic/3', 'livecodebench-abc390_g/control/3', 'livecodebench-abc390_g/bare_retry/3', 'livecodebench-arc192_a/control/3', 'livecodebench-arc193_b/control/3', 'livecodebench-arc193_b/bare_retry/3', 'livecodebench-arc193_b/reflect_fix/3', 'livecodebench-arc193_b/critic/3', 'livecodebench-arc194_a/control/3', 'livecodebench-arc194_a/reflect_fix/3', 'livecodebench-arc195_e/control/3', 'livecodebench-arc195_e/reflect_fix/3', 'livecodebench-arc195_c/control/3', 'livecodebench-arc195_c/bare_retry/3', 'livecodebench-arc195_c/reflect_fix/3', 'livecodebench-arc195_c/critic/3', 'livecodebench-arc196_c/control/3', 'livecodebench-3725/reflect_fix/3']
Finalized answers (cut off with no complete code block, then a follow-up call gave the final code): 34 ['livecodebench-abc389_g/control/1', 'livecodebench-abc389_g/reflect_fix/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc193_b/control/1', 'livecodebench-arc193_b/bare_retry/1', 'livecodebench-arc193_b/reflect_fix/1', 'livecodebench-arc193_b/critic/1', 'livecodebench-arc194_a/bare_retry/1', 'livecodebench-arc194_a/reflect_fix/1', 'livecodebench-arc195_e/control/1', 'livecodebench-arc195_e/reflect_fix/1', 'livecodebench-arc195_c/reflect_fix/1', 'livecodebench-3725/critic/1', 'livecodebench-arc193_b/control/2', 'livecodebench-arc193_b/reflect_fix/2', 'livecodebench-arc195_e/bare_retry/2', 'livecodebench-arc195_e/reflect_fix/2', 'livecodebench-arc195_c/reflect_fix/2', 'livecodebench-arc195_c/critic/2', 'livecodebench-arc196_c/control/2', 'livecodebench-arc196_c/reflect_fix/2', 'livecodebench-3725/reflect_fix/2', 'livecodebench-abc389_g/critic/3', 'livecodebench-arc192_a/control/3', 'livecodebench-arc193_b/control/3', 'livecodebench-arc193_b/bare_retry/3', 'livecodebench-arc193_b/reflect_fix/3', 'livecodebench-arc195_e/control/3', 'livecodebench-arc195_e/reflect_fix/3', 'livecodebench-arc195_c/reflect_fix/3', 'livecodebench-arc195_c/critic/3', 'livecodebench-arc196_c/control/3', 'livecodebench-3725/reflect_fix/3']
No code block: 0 
Several code blocks: 119 ['mbpp-603/zero_shot/0', 'mbpp-622/zero_shot/0', 'mbpp-637/zero_shot/0', 'mbpp-720/zero_shot/0', 'mbpp-741/zero_shot/0', 'mbpp-749/zero_shot/0', 'mbpp-754/zero_shot/0', 'mbpp-759/zero_shot/0', 'mbpp-773/zero_shot/0', 'mbpp-781/zero_shot/0', 'mbpp-808/zero_shot/0', 'mbpp-75/zero_shot/0', 'mbpp-235/zero_shot/0', 'mbpp-242/zero_shot/0', 'mbpp-281/zero_shot/0', 'mbpp-286/zero_shot/0', 'mbpp-395/zero_shot/0', 'mbpp-421/zero_shot/0', 'mbpp-445/zero_shot/0', 'livecodebench-abc387_f/zero_shot/0', 'livecodebench-abc387_c/zero_shot/0', 'livecodebench-abc388_d/zero_shot/0', 'livecodebench-abc388_c/zero_shot/0', 'livecodebench-abc388_e/zero_shot/0', 'livecodebench-abc389_g/zero_shot/0', 'livecodebench-abc389_f/zero_shot/0', 'livecodebench-abc389_e/zero_shot/0', 'livecodebench-abc390_c/zero_shot/0', 'livecodebench-abc391_g/zero_shot/0', 'livecodebench-abc392_g/zero_shot/0', 'livecodebench-abc393_d/zero_shot/0', 'livecodebench-abc397_b/zero_shot/0', 'livecodebench-arc193_b/zero_shot/0', 'livecodebench-arc193_a/zero_shot/0', 'livecodebench-arc194_c/zero_shot/0', 'livecodebench-arc194_e/zero_shot/0', 'livecodebench-arc195_c/zero_shot/0', 'livecodebench-arc196_c/zero_shot/0', 'livecodebench-3674/zero_shot/0', 'livecodebench-3737/zero_shot/0', 'livecodebench-3725/zero_shot/0', 'livecodebench-3733/zero_shot/0', 'livecodebench-3786/zero_shot/0', 'livecodebench-3722/zero_shot/0', 'livecodebench-3789/zero_shot/0', 'livecodebench-3750/zero_shot/0', 'livecodebench-3701/zero_shot/0', 'livecodebench-3776/zero_shot/0', 'mbpp-749/control/1', 'mbpp-773/control/1', 'livecodebench-abc389_g/bare_retry/1', 'livecodebench-abc389_g/critic/1', 'livecodebench-abc390_g/control/1', 'livecodebench-arc192_a/control/1', 'livecodebench-arc192_a/bare_retry/1', 'livecodebench-arc192_a/reflect_fix/1', 'livecodebench-arc192_a/critic/1', 'livecodebench-arc193_b/bare_retry/1', 'livecodebench-arc193_b/critic/1', 'livecodebench-arc194_c/control/1', 'livecodebench-arc194_a/control/1', 'livecodebench-arc194_a/bare_retry/1', 'livecodebench-arc194_a/critic/1', 'livecodebench-arc195_e/bare_retry/1', 'livecodebench-arc195_c/control/1', 'livecodebench-arc195_c/bare_retry/1', 'livecodebench-arc195_c/reflect_fix/1', 'livecodebench-3674/control/1', 'livecodebench-3674/critic/1', 'livecodebench-3725/control/1', 'livecodebench-3725/bare_retry/1', 'livecodebench-3776/control/1', 'livecodebench-3776/critic/1', 'mbpp-773/control/2', 'mbpp-235/control/2', 'livecodebench-abc389_g/control/2', 'livecodebench-abc389_g/bare_retry/2', 'livecodebench-abc389_g/critic/2', 'livecodebench-abc390_g/control/2', 'livecodebench-abc390_g/bare_retry/2', 'livecodebench-arc192_a/control/2', 'livecodebench-arc192_a/bare_retry/2', 'livecodebench-arc193_b/control/2', 'livecodebench-arc193_b/bare_retry/2', 'livecodebench-arc193_b/critic/2', 'livecodebench-arc194_c/critic/2', 'livecodebench-arc194_a/bare_retry/2', 'livecodebench-arc195_e/control/2', 'livecodebench-arc195_e/reflect_fix/2', 'livecodebench-arc195_e/critic/2', 'livecodebench-arc195_c/control/2', 'livecodebench-arc195_c/bare_retry/2', 'livecodebench-arc195_c/reflect_fix/2', 'livecodebench-arc196_c/reflect_fix/2', 'livecodebench-3674/control/2', 'livecodebench-3674/reflect_fix/2', 'livecodebench-3725/control/2', 'mbpp-603/control/3', 'mbpp-749/control/3', 'mbpp-773/control/3', 'mbpp-235/bare_retry/3', 'livecodebench-abc389_g/bare_retry/3', 'livecodebench-abc389_g/critic/3', 'livecodebench-abc390_g/bare_retry/3', 'livecodebench-arc193_b/control/3', 'livecodebench-arc193_b/bare_retry/3', 'livecodebench-arc193_b/reflect_fix/3', 'livecodebench-arc193_b/critic/3', 'livecodebench-arc194_c/control/3', 'livecodebench-arc194_c/bare_retry/3', 'livecodebench-arc194_a/bare_retry/3', 'livecodebench-arc194_a/reflect_fix/3', 'livecodebench-arc194_a/critic/3', 'livecodebench-arc195_c/control/3', 'livecodebench-arc195_c/bare_retry/3', 'livecodebench-arc195_c/reflect_fix/3', 'livecodebench-arc196_c/control/3', 'livecodebench-3674/control/3', 'livecodebench-3674/bare_retry/3']
Critiques containing code: 0 
Tasks with missing arm attempts: 0 
Calls with estimated tokens at attempt 0: 0
Tokens per call: {'zero_shot': {'input': 421, 'output': 1306}, 'control': {'input': 1283, 'output': 2314}, 'bare_retry': {'input': 1418, 'output': 1965}, 'reflect_fix': {'input': 2499, 'output': 2287}, 'critic': {'input': 1939, 'output': 1289}}

## Main results (all tasks)
| arm | n | hidden pass@1 | hidden pass@1 (excl. failed) | public pass@1 | false passes | failed API calls | calls | cost $ |
|---|---|---|---|---|---|---|---|---|
| claude zero-shot (attempt 0) | 100 | 0.770 | 0.770 | 0.820 | 5 | 0 | 100 | 2.085 |
| claude + control (attempt 3) | 100 | 0.810 | 0.810 | 0.870 | 6 | 0 | 158 | 4.322 |
| claude + bare_retry (attempt 3) | 100 | 0.830 | 0.830 | 0.880 | 5 | 0 | 151 | 3.805 |
| claude + reflect_fix (attempt 3) | 100 | 0.850 | 0.850 | 0.920 | 7 | 0 | 150 | 4.175 |
| claude + critic (attempt 3) | 100 | 0.840 | 0.840 | 0.900 | 6 | 0 | 184 | 4.198 |

## All tasks by attempt (A and B keep attempt 0)
| arm | hidden pass@1, a0-a1-a2-a3 | excl. failed | public pass@1 |
|---|---|---|---|
| control | 0.770 / 0.790 / 0.810 / 0.810 | 0.770 / 0.790 / 0.810 / 0.810 | 0.820 / 0.840 / 0.860 / 0.870 |
| bare_retry | 0.770 / 0.800 / 0.810 / 0.830 | 0.770 / 0.800 / 0.810 / 0.830 | 0.820 / 0.850 / 0.860 / 0.880 |
| reflect_fix | 0.770 / 0.830 / 0.850 / 0.850 | 0.770 / 0.830 / 0.850 / 0.850 | 0.820 / 0.900 / 0.920 / 0.920 |
| critic | 0.770 / 0.830 / 0.840 / 0.840 | 0.770 / 0.830 / 0.840 / 0.840 | 0.820 / 0.890 / 0.900 / 0.900 |

## Attempt 0 cells
| A true pass | B false pass | C hidden-only pass | D true fail | failed runs | went into the arms |
|---|---|---|---|---|---|
| 77 | 5 | 0 | 18 | 0 | 18 |

B tasks pass the public tests, so no arm retries them: they cap every arm equally. C and D go into the arms; repairs are counted over D, breaks over C.

## Self-correction (the 18 tasks that went into the arms, C + D)
| arm | hidden pass@1, a0-a1-a2-a3 | gain vs control (last) | repairs (of D) | breaks (of C) | false fixes | regressions | failed API calls | calls | tokens | cost $ | $ per repair | calls per repair |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control | 0.000 / 0.111 / 0.222 / 0.222 | 0.000 | 4/18 | 0/0 | 1 | 4 | 0 | 58 | 208670 | 2.237 | 0.5592 | 14.500 |
| bare_retry | 0.000 / 0.167 / 0.222 / 0.333 | 0.111 | 6/18 | 0/0 | 0 | 6 | 0 | 51 | 172534 | 1.720 | 0.2867 | 8.500 |
| reflect_fix | 0.000 / 0.333 / 0.444 / 0.444 | 0.222 | 8/18 | 0/0 | 2 | 4 | 0 | 50 | 239314 | 2.090 | 0.2613 | 6.250 |
| critic | 0.000 / 0.333 / 0.389 / 0.389 | 0.167 | 7/18 | 0/0 | 1 | 3 | 0 | 84 | 271180 | 2.113 | 0.3019 | 12.000 |

## By source and difficulty (all tasks, last attempt)
| group | n | A | B | C | D | failed | zero-shot | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|---|---|---|---|---|---|
| livecodebench/easy | 27 | 27 | 0 | 0 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| livecodebench/hard | 26 | 14 | 3 | 0 | 9 | 0 | 0.538 | 0.577 | 0.615 | 0.577 | 0.577 |
| livecodebench/medium | 27 | 24 | 0 | 0 | 3 | 0 | 0.889 | 0.963 | 0.926 | 0.963 | 0.963 |
| mbpp/hard | 10 | 4 | 2 | 0 | 4 | 0 | 0.400 | 0.500 | 0.600 | 0.700 | 0.600 |
| mbpp/medium | 10 | 8 | 0 | 0 | 2 | 0 | 0.800 | 0.800 | 0.900 | 1.000 | 1.000 |

## Self-correction by source and difficulty (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| livecodebench/hard | 9 | 0.000 / 0.000 / 0.111 / 0.111 | 0.000 / 0.000 / 0.111 / 0.222 | 0.000 / 0.111 / 0.111 / 0.111 | 0.000 / 0.111 / 0.111 / 0.111 |
| livecodebench/medium | 3 | 0.000 / 0.333 / 0.667 / 0.667 | 0.000 / 0.333 / 0.333 / 0.333 | 0.000 / 0.333 / 0.667 / 0.667 | 0.000 / 0.333 / 0.667 / 0.667 |
| mbpp/hard | 4 | 0.000 / 0.250 / 0.250 / 0.250 | 0.000 / 0.500 / 0.500 / 0.500 | 0.000 / 0.500 / 0.750 / 0.750 | 0.000 / 0.500 / 0.500 / 0.500 |
| mbpp/medium | 2 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.500 | 0.000 / 1.000 / 1.000 / 1.000 | 0.000 / 1.000 / 1.000 / 1.000 |

## Self-correction by attempt-0 failure type (C + D)
| group | n | control | bare_retry | reflect_fix | critic |
|---|---|---|---|---|---|
| runtime_error | 1 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 / 0.000 |
| wrong_answer | 17 | 0.000 / 0.118 / 0.235 / 0.235 | 0.000 / 0.176 / 0.235 / 0.353 | 0.000 / 0.353 / 0.471 / 0.471 | 0.000 / 0.353 / 0.412 / 0.412 |

## Cut-off sensitivity (hidden pass@1 at attempt 3)
Tasks where any answer hit max_tokens: 15 of 100 ['livecodebench-3725', 'livecodebench-3733', 'livecodebench-abc389_f', 'livecodebench-abc389_g', 'livecodebench-abc390_g', 'livecodebench-abc400_g', 'livecodebench-arc192_a', 'livecodebench-arc193_a', 'livecodebench-arc193_b', 'livecodebench-arc194_a', 'livecodebench-arc194_c', 'livecodebench-arc194_e', 'livecodebench-arc195_c', 'livecodebench-arc195_e', 'livecodebench-arc196_c']. The right-hand columns leave those tasks out for every arm. If the arms compare the same way with and without them, the token limit doesn't change the conclusion. With 0 tasks left in a column, this run can't tell.
| arm | cut-off answers | all tasks (n=100) | without cut-off tasks (n=85) | C + D (n=18) | C + D without cut-off tasks (n=8) |
|---|---|---|---|---|---|
| zero-shot | 15/100 | 0.770 | 0.859 | - | - |
| control | 21/48 | 0.810 | 0.882 | 0.222 | 0.250 |
| bare_retry | 15/47 | 0.830 | 0.906 | 0.333 | 0.500 |
| reflect_fix | 15/36 | 0.850 | 0.929 | 0.444 | 0.750 |
| critic | 10/39 | 0.840 | 0.918 | 0.389 | 0.625 |

## Does telling the model it ran out of space help?
Retry answers whose previous attempt in the same arm hit max_tokens. reflect_fix and critic are told so in the test feedback; control and bare_retry never are. Fewer answers cut off again in the told arms would mean the note helps.
| arm | answers after a cut-off answer | told | cut off again |
|---|---|---|---|
| control | 23 | 0 | 19 |
| bare_retry | 22 | 0 | 13 |
| reflect_fix | 19 | 19 | 12 |
| critic | 17 | 17 | 8 |

## Paired tests (exact McNemar, hidden pass/fail per task)
p (Holm) is corrected within each family. Significant: p (Holm) below 0.05. The feedback_vs_control family answers whether feedback beats a fresh resample.
| family | comparison | only first passes | only second passes | p | p (Holm) | verdict |
|---|---|---|---|---|---|---|
| feedback_vs_control | bare_retry vs control | 3 | 1 | 0.625 | 0.750 | not significant |
| feedback_vs_control | reflect_fix vs control | 5 | 1 | 0.219 | 0.656 | not significant |
| feedback_vs_control | critic vs control | 4 | 1 | 0.375 | 0.750 | not significant |
| vs_zero_shot | control vs zero-shot | 4 | 0 | 0.125 | 0.125 | not significant |
| vs_zero_shot | bare_retry vs zero-shot | 6 | 0 | 0.031 | 0.062 | not significant |
| vs_zero_shot | reflect_fix vs zero-shot | 8 | 0 | 0.008 | 0.031 | significant |
| vs_zero_shot | critic vs zero-shot | 7 | 0 | 0.016 | 0.047 | significant |

## Task ids
- A_true_pass: mbpp-637 mbpp-720 mbpp-741 mbpp-754 mbpp-759 mbpp-808 mbpp-75 mbpp-242 mbpp-281 mbpp-286 mbpp-421 mbpp-445 livecodebench-abc387_b livecodebench-abc387_f livecodebench-abc387_a livecodebench-abc387_c livecodebench-abc388_d livecodebench-abc388_b livecodebench-abc388_c livecodebench-abc388_a livecodebench-abc388_e livecodebench-abc389_b livecodebench-abc389_a livecodebench-abc389_f livecodebench-abc389_e livecodebench-abc390_c livecodebench-abc391_a livecodebench-abc391_g livecodebench-abc391_b livecodebench-abc392_g livecodebench-abc392_b livecodebench-abc392_c livecodebench-abc393_a livecodebench-abc393_d livecodebench-abc393_b livecodebench-abc394_c livecodebench-abc394_a livecodebench-abc395_c livecodebench-abc395_b livecodebench-abc396_c livecodebench-abc396_d livecodebench-abc397_b livecodebench-abc398_b livecodebench-abc398_d livecodebench-abc398_a livecodebench-abc399_e livecodebench-abc399_b livecodebench-abc400_a livecodebench-arc193_a livecodebench-arc194_e livecodebench-3708 livecodebench-3677 livecodebench-3720 livecodebench-3731 livecodebench-3714 livecodebench-3737 livecodebench-3704 livecodebench-3751 livecodebench-3760 livecodebench-3779 livecodebench-3733 livecodebench-3768 livecodebench-3764 livecodebench-3786 livecodebench-3722 livecodebench-3791 livecodebench-3789 livecodebench-3750 livecodebench-3817 livecodebench-3832 livecodebench-3747 livecodebench-3723 livecodebench-3778 livecodebench-3785 livecodebench-3783 livecodebench-3799 livecodebench-3811
- B_false_pass: mbpp-622 mbpp-781 livecodebench-abc400_g livecodebench-arc191_d livecodebench-3701
- C_hidden_only_pass: -
- D_true_fail: mbpp-603 mbpp-749 mbpp-773 mbpp-235 mbpp-305 mbpp-395 livecodebench-abc389_g livecodebench-abc390_g livecodebench-arc192_a livecodebench-arc193_b livecodebench-arc194_c livecodebench-arc194_a livecodebench-arc195_e livecodebench-arc195_c livecodebench-arc196_c livecodebench-3674 livecodebench-3725 livecodebench-3776
- C + D, every arm finished: mbpp-603 mbpp-749 mbpp-773 mbpp-235 mbpp-305 mbpp-395 livecodebench-abc389_g livecodebench-abc390_g livecodebench-arc192_a livecodebench-arc193_b livecodebench-arc194_c livecodebench-arc194_a livecodebench-arc195_e livecodebench-arc195_c livecodebench-arc196_c livecodebench-3674 livecodebench-3725 livecodebench-3776

## Notes
attempt_0.cells: A true pass, B false pass (public pass, hidden fail), C hidden-only pass (public fail, hidden pass), D true fail. all_tasks: hidden pass@1 over every task, A and B keeping their attempt-0 result. hidden_pass@1 and public_pass@1 count failed attempt-0 API calls as 0; *_excl_failed leaves those tasks out. Failed retries count 0 in both. paired_tests: p_holm is Holm-adjusted within each family. arms: only the tasks that went into the arms (C + D); repair_rate is over D, breaks over C. regression = hidden test pass rate went down from the arm's previous attempt. Costs are from the API's token counts (tokens_estimated = calls whose counts were estimated).
