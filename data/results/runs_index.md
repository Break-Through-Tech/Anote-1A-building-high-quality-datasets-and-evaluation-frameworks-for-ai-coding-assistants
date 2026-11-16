# Runs index

Every run in `data/results/`. Current scoring version: 5. Only finished `test` runs on the current scoring version are results; everything else checks the plumbing or the cost.

Total spent across these runs: $8.70

| run | started | split | model | tasks | task_list | scoring_version | attempt0_from | calls | cost_usd | zero_shot_hidden_pass@1 | finished | reportable | why_not |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-10_claude_dev_1 | 2026-11-10 | dev | claude-sonnet-4-6 | 10 | - | 2 | - | 53 | 1.848 | 0.600 | True | False | dev split (only test runs are results); scoring v2 (current v5) |
| 2026-11-10_claude_dev_2 | 2026-11-10 | dev | claude-sonnet-4-6 | 10 | - | 3 | - | 52 | 2.756 | 0.700 | True | False | dev split (only test runs are results); scoring v3 (current v5) |
| 2026-11-11_claude_dev_1 | 2026-11-11 | dev | claude-sonnet-4-6 | 10 | - | 3 | - | 25 | 0.808 | 0.800 | True | False | dev split (only test runs are results); scoring v3 (current v5) |
| 2026-11-11_claude_dev_2 | 2026-11-11 | dev | claude-sonnet-4-6 | 10 | - | 3 | 2026-11-11_claude_dev_1 | 25 | 0.891 | 0.800 | True | False | dev split (only test runs are results); scoring v3 (current v5) |
| 2026-11-11_claude_dev_3 | 2026-11-11 | dev | claude-sonnet-4-6 | 10 | - | 3 | 2026-11-11_claude_dev_1 | 25 | 0.894 | 0.800 | True | False | dev split (only test runs are results); scoring v3 (current v5) |
| 2026-11-12_claude_dev_1 | 2026-11-12 | dev | claude-sonnet-4-6 | 10 | - | 3 | 2026-11-11_claude_dev_1 | 29 | 1.026 | 0.800 | True | False | dev split (only test runs are results); scoring v3 (current v5) |
| 2026-11-12_claude_dev_2 | 2026-11-12 | dev | claude-sonnet-4-6 | 10 | - | 4 | - | 18 | 0.478 | 0.600 | True | False | dev split (only test runs are results); scoring v4 (current v5) |
