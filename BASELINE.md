# Baseline configuration

Locked comparison baseline, per Natan's 9/15/26 guidance: one model, one
prompt, fixed decoding, one Panacea commit. Not meant to be "perfect" -
this is what later prompting/routing/evaluator work gets compared against.

**Attribution:** the Panacea config below is early research (done to unblock
`panacea_baseline.py`, Task #4), not a finished decision. Identifying and
confirming the comparison config is Task #6, owned by Nebiyu. Treat this as a
draft for him and us to confirm or adjust, not a finished product.

## Panacea version
- Repo: https://github.com/anote-ai/Panacea
- Commit: `bea399509efbab4ac242042b64f8b28b8865691e` (main, 2026-09-15)

## Model
- `claude-sonnet-4-6` - Panacea's own default (`packages/web/src/constants/models.ts`, `DEFAULT_MODEL`)

## Prompt
- System prompt: "You are an expert coding assistant." (`packages/backend/agents/coding_agent.py`)
- User prompt: the dataset problem text (see `evaluator.py`, `from_mbpp` / `from_humaneval`)

## Decoding parameters
- `max_tokens`: 4096 - Panacea's `llm.py` default
- `temperature`: 0 - not set by Panacea; pinned here for reproducibility (flagged deviation)

## Scope
- Task type: code generation only
- Datasets: MBPP (full, test split), HumanEval (test split)

## Run it
```
pip install -r requirements.txt
cp .env.example .env   # paste your ANTHROPIC_API_KEY
python panacea_baseline.py 5
```
Writes `baseline_run.json` with this config, per-item results, and pass@1 scores.

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
- Same system prompt and settings as the Claude baseline (`max_tokens`: 4096, `temperature`: 0), for a fair comparison.

## Run it
```
pip install -r requirements.txt
cp .env.example .env   # paste your OPENROUTER_API_KEY
python opensource_baseline.py 3
```
Writes `opensource_run.json`. Free-tier models are rate-limited (~50 requests/day without purchased credits) - keep the sample small.

## Status
- [ ] Run on a small sample
- [ ] Results compared against the Claude baseline
