# Data-quality audit

Written by `python Evaluator/data_audit.py --rescore` (issue #22). Read-only checks of `data/unified/`; no API calls.

## 1. What is in the evaluation set

240 tasks.

| task_type | source | difficulty | test_format | tasks |
|---|---|---|---|---|
| bug_fixing | humanevalfix | - | check_fn | 100 |
| bug_fixing | quixbugs | - | assert_list | 31 |
| bug_fixing | quixbugs | - | test_functions | 9 |
| code_generation | livecodebench | easy | functional_io | 11 |
| code_generation | livecodebench | easy | stdin_io | 16 |
| code_generation | livecodebench | hard | functional_io | 6 |
| code_generation | livecodebench | hard | stdin_io | 20 |
| code_generation | livecodebench | medium | functional_io | 14 |
| code_generation | livecodebench | medium | stdin_io | 13 |
| code_generation | mbpp | hard | assert_list | 10 |
| code_generation | mbpp | medium | assert_list | 10 |

## 2. Duplicates and overlap with the pool

- duplicate ids in eval: **0** 
- duplicate prompts in eval: **0** 
- ids in both eval and pool: **0** 
- identical prompts in both eval and pool: **0**

Near-identical prompts between eval and pool (similarity >= 0.85, same source). Read each pair: a pool task used as a few-shot example must not give away an eval answer.

| eval_id | pool_id | similarity |
|---|---|---|
| mbpp-395 | mbpp-602 | 0.92 |

## 3. Public tests (the only feedback the model sees)

| source | tasks | min | median | max | tasks with 1 public test | tasks with none |
|---|---|---|---|---|---|---|
| humanevalfix | 100 | 1 | 1.0 | 1 | 100 | 0 |
| livecodebench | 80 | 1 | 3.0 | 4 | 1 | 0 |
| mbpp | 20 | 3 | 3.0 | 5 | 0 | 0 |
| quixbugs | 40 | 1 | 6.0 | 14 | 1 | 0 |

HumanEval-Fix keeps all its asserts inside one `check` function, so 1 test there means one function, not one assert. The first failing public test is what the feedback arms see, so tasks with a single public test give them very little to work with.

## 4. Hidden tests (scoring only, never shown)

- code-generation tasks without hidden tests: **0** 
- hidden-test rows for tasks not in eval: **0**
- hidden tests that reuse a public test's input: **0 tasks**
- tasks whose hidden list repeats a test: **10** (livecodebench-abc387_b, livecodebench-abc389_b, livecodebench-abc389_a, livecodebench-abc389_g, livecodebench-abc391_a, livecodebench-abc393_a, livecodebench-abc398_a, livecodebench-3674, livecodebench-3704, livecodebench-3783)

Tasks with fewer than 5 distinct hidden tests. With so few tests, a wrong answer can pass by luck, so read these tasks' results with care.

| id | difficulty | hidden | distinct | why allowed |
|---|---|---|---|---|
| livecodebench-abc391_a | easy | 10 | 4 | **breaks the rule** |
| livecodebench-abc393_a | easy | 10 | 2 | **breaks the rule** |
| livecodebench-abc400_g | hard | 4 | 4 | hard tasks are exempt |
| livecodebench-arc195_c | hard | 4 | 4 | hard tasks are exempt |

## 5. Prompt checks

MBPP prompts are one sentence plus a function signature, with no example input or output, so the expected return format is often a guess. A model can fail an MBPP task because the prompt is unclear rather than because it can't code. Flagged prompts (read them by hand; the checks are simple text rules):

| id | first line | flags |
|---|---|---|
| mbpp-749 | Write a function to sort a given list of strings of numbers numerically. https://www.geeks | contains a web link |
| mbpp-781 | Write a python function to check whether the count of divisors is even. https://www.w3reso | contains a web link |
| mbpp-421 | Write a function to concatenate each element of tuple by the delimiter. | one short sentence (12 words), no example |

## 6. Scoring consistency (known-correct answers, scored twice)

26 known-correct answers (MBPP references and the hand-written LiveCodeBench answers in `Evaluator/fixtures.json`), each scored twice on its hidden tests.

- answers that did not pass every hidden test: **0**
- answers scored differently the second time: **0**
- answers that took over 3 s to score (the limit is 6 s per test, so slow code near the limit could pass on one machine and time out on another): **0** []

_none_

## 7. Environment this audit ran in

Python 3.9.6, pandas 2.3.3, numpy 2.0.2, scoring version 5. `requirements.txt` doesn't pin versions, so another machine may install different ones.
