# Baseline configuration

Both baselines below run from one shared script, `baseline.py` - same
loading, same scoring, same output format. The only thing that differs
per provider is the small "call this API" function; see the file for that.

Locked comparison baseline, per Natan's 9/15/26 guidance: one model, one
prompt, fixed decoding, one Panacea commit. Not meant to be "perfect" -
this is what later prompting/routing/evaluator work gets compared against.

**Attribution:** the Panacea config below is early research (done to unblock
`baseline.py`, Task #4), not a finished decision. Identifying and
confirming the comparison config is Task #6, owned by Nebiyu. Treat this as a
draft for him to confirm or adjust, not a settled answer.

## Panacea version
- Repo: https://github.com/anote-ai/Panacea
- Commit: `bea399509efbab4ac242042b64f8b28b8865691e` (main, 2026-09-15)

## Model
- `claude-sonnet-4-6` - Panacea's own default (`packages/web/src/constants/models.ts`, `DEFAULT_MODEL`), and the team's experiment model for every arm (decided 2026-11-03)

## Prompt
- System prompt: "You are an expert coding assistant." (`packages/backend/agents/coding_agent.py`)
- User prompt: the task's `prompt` field from `data/unified/unified_eval.jsonl`, sent unchanged at `--level raw` (other levels: `AI_models/prompts.py`)

## Decoding parameters
Shared by every arm (Claude, Panacea, open-source), set once at the top of `AI_models/providers.py`. These are our settings, not Panacea's:
- `max_tokens`: 8192 (`MAX_TOKENS`). Stock Panacea's coding agent sets none, so LangChain's 1024 applies there.
- `temperature`: 0.5 (`TEMPERATURE`) - above 0 so the fresh-resample control arm actually resamples. Stock Panacea sets none (API default 1.0). Works only on SDK 0.x (API version `2023-06-01`, hence the pin in `requirements.txt`) and on models that still accept temperature, such as `claude-sonnet-4-6`, the experiment model (decided 2026-11-03).
- `max_retries`: 2 (`MAX_RETRIES`) - the SDK's own retries on temporary API errors. An error left after them is a failed run for that task, scored 0, and pass@1 is reported both with and without failed runs.

Panacea gets all three at load time through a wrapper around `ChatAnthropic`: a flagged deviation from stock Panacea (see `panacea_config.md`).

## Scope
- Task type: code generation only
- Datasets: the code-generation tasks in `data/unified/unified_eval.jsonl` (MBPP 20, LiveCodeBench 80). All 100 are scorable.
- Scoring: every answer is scored on the **hidden tests** (the headline pass@1) and on the public tests (public pass@1 beside it). An answer that passes the public tests but fails the hidden ones is counted as a **false pass**. Each result also carries the rubric level (`rubric_level` 0–4 and its name `level`) and `failure_type`; see `data/README.md`, "Scoring".

## Run it
```
pip install -r requirements.txt
cp .env.example .env   # paste your ANTHROPIC_API_KEY
python Baseline/baseline.py claude --ids smoke.txt
```
**Which runs count for the experiment (decided 2026-11-03):** the Claude zero-shot result is the Evaluator-Optimizer loop's attempt 0 (`Optimizer/loop.py`), not this script's `claude` run, so there is one Claude zero-shot number. This script supplies the **Panacea** zero-shot arm: run `python Baseline/baseline.py panacea --ids <the loop run's task list>`, then `python Optimizer/report.py data/results/<run> panacea_run.json`. The `claude` provider stays for quick checks; `reference` checks the pipeline with no API.

**Budget log:** every Claude API call goes into `runs/usage_log.csv` at the repo root, with the API's token counts, and stops at $47 of the $50 budget. That covers the `claude` provider (one row per task, arm `baseline_claude`) and each call Panacea's agent makes (arm `baseline_panacea`). The run files also carry `calls`, `input_tokens` and `cost_usd` per task, and the totals in `summary`. A budget stop ends the run after the last finished task. The log is committed: `git pull` before a paid run, then commit and push `runs/usage_log.csv` right after it (see `Optimizer/LOOP.md`, "Budget log").

Writes `baseline_run.json` with this config, per-item results, and pass@1 scores, rewritten after every task. Each provider has its own file (`panacea_run.json`, `opensource_run.json`, `reference_run.json`; `_<level>` is added for prompt levels other than `raw`). Run every arm from the same `--ids` task list (`data/unified/task_lists/`), then compare with `python Baseline/compare_runs.py`. Run files record `scoring_version` (now 2: hidden-test headline); `compare_runs` refuses to mix versions, so re-run any run file without `scoring_version` (those scored public tests only).

Before spending API calls, check that the data flows through scoring, the pipeline and the loop with `python Evaluator/self_test.py` (about 40 s on the real tasks and their public and hidden tests, no API, nothing written outside a temporary folder).

## Status
- [ ] Run on a small sample
- [ ] Results reviewed by the team
- [ ] Confirmed or adjusted at next meeting

---

# Open-source comparison (OpenRouter)

Second locked config, for Task #4's "or other open-source LLMs." Runs over
OpenRouter instead of local hardware, on a free-tier model - $0 cost.

## Model
- `openrouter/free` via OpenRouter - auto-routes to whatever free model is currently available, so the config doesn't go stale. The actual model that answered each request is recorded per-item as `model_used` in `opensource_run.json`.

## Prompt & decoding
- Same system prompt and the same shared settings as the Claude baseline (`MAX_TOKENS`, `TEMPERATURE`, `MAX_RETRIES` in `AI_models/providers.py`), for a fair comparison.

## Run it
```
pip install -r requirements.txt
cp .env.example .env   # paste your OPENROUTER_API_KEY
python Baseline/baseline.py opensource 3
```
Writes `opensource_run.json`. Free-tier models are rate-limited (~50 requests/day without purchased credits) - keep the sample small.

## Status
- [ ] Run on a small sample
- [ ] Results compared against the Claude baseline
