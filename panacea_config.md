# Panacea comparison target (Task #6, DRAFT for team review)

Status: based on a read-only pass over the code. Nothing has been installed or run yet, so the install and run steps below are untested.

Panacea repo: https://github.com/anote-ai/Autonomous-Intelligence
Commit inspected: `bea399509efbab4ac242042b64f8b28b8865691e` (2026-09-15). This is the same commit `Baseline/BASELINE.md` already pins.

---

## 1. Which doc is accurate

**CLAUDE.md is the accurate one.** CODEBASE_SETUP.md describes a layout that does not exist in the repo.

| Question | CLAUDE.md | CODEBASE_SETUP.md | README.md | Reality in code |
|---|---|---|---|---|
| Layout | `packages/` | `backend/` + `frontend/` | `backend/` | `packages/` is the live monorepo (backend, cli, vscode, web, sdk, ...). A legacy `backend/` also exists at root. There is no `frontend/`. |
| Backend framework | Flask | FastAPI | (not stated) | Flask. `packages/backend/app.py` does `from flask import Flask`. No FastAPI import anywhere. The Makefile mentions `uvicorn` but falls back to `python app.py`. |
| Port | 5000 | 8000 | (not stated) | 5000 (`app.run(... port=5000)`, compose `5000:5000`). |
| Database | MySQL | PostgreSQL | MySQL (says compose starts MySQL) | MySQL (`mysql-connector-python`, `mysql:8.0` in compose). No Postgres or `psycopg` anywhere. |

- **CLAUDE.md** matches on all four points.
- **CODEBASE_SETUP.md** is wrong on all four. It looks like it describes an older or different layout.
- **README.md** is partly right. It correctly lists MySQL, Redis and Tika in compose. But its `cp backend/.env.example backend/.env` points at the legacy `backend/` dir. The root `docker-compose.yml` actually builds `./packages/backend`.
- **Two backends exist.**
  - `packages/backend/` is the current Flask API (uses the `services/llm.py` provider layer).
  - `backend/` at root is the older Flask app (a 2300+ line `app.py`, Ray, document Q&A agents). The root `pyproject.toml` and its tests still point at it.
  - Only `packages/backend/` is relevant to coding.
- **Python version:** the `packages/backend` Dockerfile uses 3.11.

---

## 2. Candidate coding components

| # | Component | Location | What it does | Default provider / model | How to give it one task |
|---|---|---|---|---|---|
| A | **`run_coding_agent`** (LangChain agent) | `packages/backend/agents/coding_agent.py` | Tool-calling agent with `read_file` and `list_files` only, `max_iterations=5`, system prompt "You are an expert coding assistant." **Not wired to any endpoint**, only called from tests. | Anthropic, `claude-sonnet-4-6` (hardcoded) | Import and call `run_coding_agent(prompt, cwd)`. Returns a string. |
| B | **`anote` CLI** (`ask`, `fix`, `generate`, `explain`, `test`, etc.) | `packages/cli/src` | Agent loop over the Claude Agent SDK, with the long Anote system prompt (Understand, Explore, Plan, Execute, Verify) and file/bash tools. | Anthropic via `@anthropic-ai/claude-agent-sdk`. **The model is not passed to the SDK**, so it uses the SDK default. `gpt-*`, `gemini*`, `ollama/*`, `local/*` route to other adapters where the model is pinned. | `anote ask "prompt" --no-edit` (also reads stdin), or `runAgentStream({prompt, cwd, allowedTools, model})` from Node. |
| C | **VS Code extension** | `packages/vscode/src` | Chat sidebar, explain/fix/refactor/test actions, diff review. Uses the same Claude Agent SDK. | Setting `anote.model`, default `claude-sonnet-4-6` | GUI only. No headless entry point. |
| D | **Backend chat API** | `packages/backend/api_endpoints/chat`, `services/streaming.py` | `POST /api/chat/stream`. Despite the `stream_agent_response` name, it is a **single bare LLM call** with no system prompt and no tools. Needs MySQL, JWT auth and credits. | Anthropic `claude-sonnet-4-6` default. Also OpenAI, Gemini, Ollama. | HTTP POST with a JWT. Needs the full docker stack. |
| E | **TS SDK / Python SDK** | `packages/sdk`, `packages/sdk-py` | Thin clients for the hosted or local backend API. | n/a (backend decides) | `AnoteClient.chat(...)` against a running backend. |
| F | **Legacy document agents** | `backend/agents/` (`autonomous_agent`, `reactive_agent`, `multi_agent_system`) | Document Q&A and RAG agents with a `run_python` tool. **Not coding assistants.** | `DEFAULT_AGENT_MODEL_TYPE=0` (OpenAI `gpt-4o`), or Anthropic `claude-3-5-sonnet-20241022` | Legacy backend only. Skip. |
| G | **MCP server** | `backend/mcp/mcp_server.py` | FastMCP server with document and chat-history tools (retrieve chunks, ingest doc, DB query). **No coding tools.** Needs the legacy DB and Ray. | n/a | Not a coding component. Skip. |
| H | Web, desktop, mobile, Slack/SMS/WhatsApp bots | `packages/web`, `desktop`, `mobile`, `bots` | Chat UIs and bots that call the backend. | Web model list: `claude-sonnet-4-6` first | Not headless. Skip. |

---

## 3. Recommended config and why

**Component A, `run_coding_agent`, pinned at commit `bea3995`.**

Config:
- Model: `claude-sonnet-4-6` (hardcoded in the function)
- System prompt: "You are an expert coding assistant."
- Tools: `read_file`, `list_files` (cwd-scoped)
- `max_iterations=5`
- Decoding: stock Panacea sets neither `max_tokens` nor `temperature` in the function (LangChain's 1024 tokens, the API's temperature 1.0). **We set both at load time** (`_load_panacea` in `AI_models/providers.py` wraps `langchain_anthropic.ChatAnthropic`), to the values every arm shares: `max_tokens` 4096, `temperature` 0.5, `max_retries` 2. The clone itself is not edited. This is a flagged deviation from stock Panacea, to be reported to Natan in the next update.

Why:
- **Reproducible on a laptop.** It is a plain Python function. No Docker, MySQL, Redis, Tika or auth. Only three pip packages plus one API key.
- **Closest to "prompt in, code out".** `run_coding_agent(prompt) -> str`.
- **Same inputs as our baseline.**
  - Same model, same system prompt and same user-prompt shape as `Baseline/BASELINE.md`.
  - Our prompt strings from `data/unified/unified_eval.jsonl` go in unchanged.
  - It does not depend on files in a repo, so static evaluation works.
- **Version is pinned.** One commit, one hardcoded model, no config file to drift.
- **Other candidates fall short.**
  - B does not pin the model on the Anthropic path. It also runs on the same engine as Claude Code, so it is confounded with the Claude Code arm.
  - C has no headless mode.
  - D is a bare LLM call, so it would just duplicate our baseline.
  - F and G are not coding tools.

Caveats to be honest about:
- **This arm will likely look very close to the zero-shot baseline.** Same model and nearly the same prompt. The tools only read files, so with a self-contained prompt they add little. This is a fair comparison, but it is not "Panacea at its best". Raise this with Natan (see section 7).
- **The function is unused by the Panacea app.** It has tests but no caller.
- **Errors are swallowed.** Any exception comes back as a string starting with `Agent error:`. Our harness must check for that prefix and count it as a failed run, not as model output.
- **Output type may vary.** `result["output"]` may be a list of content blocks with newer `langchain-anthropic` versions. Pinning the versions in `requirements.txt` avoids this. Normalize to text in our wrapper anyway.
- **Not tested here.** I have not run it.

Optional second config if the advisor wants a "product" view: B, the `anote` CLI, with an OpenAI or Ollama model string so the model is pinned. See open questions.

---

## 4. Exact install and run steps (untested)

```bash
# 1. Get Panacea at the pinned commit (from the team repo root)
git clone https://github.com/anote-ai/Autonomous-Intelligence panacea
git -C panacea checkout bea399509efbab4ac242042b64f8b28b8865691e

# 2. Python 3.11 or 3.12 venv. Install ONLY the packages the coding agent needs.
#    (Do not use the full requirements.txt: it pulls chromadb, mysql-connector, PyMuPDF, etc.)
python3.11 -m venv .venv-panacea
source .venv-panacea/bin/activate
pip install anthropic==0.40.0 langchain==0.3.30 langchain-anthropic==0.3.0

# 3. Set the key in your shell or .env (never commit it)
export ANTHROPIC_API_KEY=...   # set the value yourself

# 4. Run one task
python - <<'PY'
import sys
sys.path.insert(0, "panacea/packages/backend")
from agents.coding_agent import run_coding_agent

out = run_coding_agent("Write a Python function that returns the nth Fibonacci number.", cwd=".")
assert not out.startswith("Agent error:"), out   # errors are returned as strings
print(out)
PY
```

Notes:
- `sys.path.insert(0, ...)` is needed because `agents` is a top-level package under `packages/backend/`.
- If step 2 fails on a pin conflict, fall back to `pip install -r panacea/packages/backend/requirements.txt` in a fresh venv. That needs build tools for `mysql-connector-python` and `PyMuPDF`.
- Do **not** run `docker compose up`. It is not needed for this config.

---

## 5. Required env vars (names only)

Required for the recommended config:
- `ANTHROPIC_API_KEY`

Not needed for the recommended config, but used elsewhere in Panacea:
- Providers: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL`, `OPENAI_BASE_URL` (CLI `local/` models)
- Backend stack: `JWT_SECRET_KEY`, `PROVIDER_KEY_ENCRYPTION_KEY`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `REDIS_URL`, `APP_ENV`, `IS_PROD`, `PORT`, `CHROMA_PERSIST_DIR`, `UPLOAD_FOLDER`, `AVATAR_FOLDER`
- Auth and billing: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`, `FRONTEND_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_BASIC`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_ENTERPRISE`

For the optional CLI config (B), `ANTHROPIC_API_KEY` must be set even when using a non-Anthropic model. `packages/cli/src/index.ts` exits early if it is missing, before any command runs.

---

## 6. How it plugs into the 3-arm comparison

- **Shared inputs.** One test set, `data/unified/unified_eval.jsonl` (code generation: MBPP + LiveCodeBench). Each row gives the same `prompt` string to every arm, and every arm runs from the same task list (`baseline.py --ids`, `data/unified/task_lists/`).
- **Arm 1, zero-shot baseline.**
  - `Baseline/baseline.py claude` (already in the repo): `claude-sonnet-4-6` with the shared settings (`max_tokens` 4096, temperature 0.5, 2 SDK retries).
- **Arm 2, our agentic pipeline.**
  - Router, then task-specific prompt, then Evaluator-Optimizer retry loop.
  - Uses the same underlying model as arms 1 and 3, so gains come from orchestration and not from a stronger model.
- **Arm 3, Panacea.**
  - Add a `call_panacea(client, item, cfg)` adapter in `AI_models/providers.py`, same `(text, tokens, model_used)` return shape as `call_claude`.
  - It calls `run_coding_agent(item["prompt"], cwd=<empty temp dir>)`.
  - Treat an `Agent error:` prefix as a failed run.
  - Record `model_used = "claude-sonnet-4-6"` and the Panacea commit hash in `panacea_run.json`.
  - Token usage is not exposed by the function, so report cost separately or estimate it.
- **Arms 4 and 5, Claude Code and Codex** (advisor request).
  - Different kind of arm (agentic CLIs with their own tools).
  - Run headless on the same prompt in an empty temp dir. Capture the final code only.
  - Label them as "agent products, not matched on model" in the report.
- **Scoring.** All arms go through the same scorers: exact-match, AST-diff, CodeBLEU and static Pass@1 (via the MCP scoring server). Extract the code block from each output the same way for every arm.
- **Fairness controls.**
  - Same prompts, same scorer, same code extraction.
  - Fixed Panacea commit.
  - Run each arm on the same items in the same order.
  - Log the model that actually answered.
  - Same decoding settings for every arm: Panacea gets our `max_tokens`, `temperature` and `max_retries` at load time (section 3).

---

## 7. Open questions for our advisor

1. **Which Panacea do you mean by "Panacea"?**
   - The coding agent (`run_coding_agent`) is close to a bare model call, so the arm may match the baseline.
   - Or the `anote` CLI, which is the fuller coding product but runs on the Claude Agent SDK, the same engine as Claude Code.
   - Or the multi-agent orchestrator in the legacy `backend/`, which is built for document Q&A, not code.
2. **Is a near-baseline Panacea arm acceptable?** With a self-contained prompt and read-only file tools, we expect little difference from zero-shot.
3. **Temperature and `max_tokens`. Decided by the team (2026-10-25):** we set both on Panacea at load time, to the values every arm shares (temperature 0.5, `max_tokens` 4096), and tell Natan in the next update. This deviates from stock Panacea. Temperature 0.5 needs a model that still accepts it (such as `claude-sonnet-4-6`); it is settled again when the experiment model is chosen.
4. **Repo name.** `Baseline/BASELINE.md` links `anote-ai/Panacea`, but this task used `anote-ai/Autonomous-Intelligence`. The commit hash matches. Confirm which is the canonical repo.
5. **Cost.** The Panacea arm needs a paid Anthropic key (a few cents per handful of tasks). Is there a team key, or should we use the OpenRouter free tier for the open-source arm only?
6. **Static evaluation vs tools.** Panacea's agent can read files. Should we give it the task's repo files in `cwd`, or keep it prompt-only to match the baseline?
7. **Claude Code and Codex arms.** Confirm we should run them headless in an empty directory and score only their final code output, since they have no static mode.
