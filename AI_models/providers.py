"""
providers.py

Everything that's specific to one provider (Claude vs. an open-source model
over OpenRouter) lives here: the small "call this API" function per provider,
and the PROVIDERS dict that ties each one to its config, API key, output
file, and client. baseline.py just loops over items and calls into this -
it doesn't need to know how any one provider's API works.

Add a new provider by adding one more entry to PROVIDERS (plus a call_*
function if its API shape is new) - nothing in baseline.py needs to change.

ATTRIBUTION: the "claude" config below (model, prompt, decoding, Panacea
commit) is early research into Panacea's defaults, done to unblock this
script - it is NOT a finished answer. Identifying and confirming the
comparison config is Task #6 (Nebiyu's), not this task. Treat it as a draft
for Nebiyu to confirm or adjust, not a settled decision.
"""

# --- imports ---
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Where the Panacea clone lives: the repo root, as in panacea_config.md section 4 (and .gitignore).
# Override with PANACEA_PATH.
PANACEA_DIR = Path(os.environ.get("PANACEA_PATH") or Path(__file__).resolve().parent.parent / "panacea")

# Decoding settings shared by every arm, so the arms differ only in how they are orchestrated.
# Change them only here.
MAX_TOKENS = 4096   # output cap; placeholder until the experiment model and budget are chosen
TEMPERATURE = 0.5   # above 0 so the fresh-resample control arm actually resamples
MAX_RETRIES = 2     # the SDK's own retries on temporary API errors (rate limit, overload, timeout, 5xx)


# Raised by an adapter when the provider ran but gave no usable answer (not a model mistake).
# baseline.py records the item as a failed run instead of stopping the whole batch.
class AdapterError(RuntimeError):
    pass


# =====================================================================
# API ADAPTERS
# One small function per provider - this is the only part that actually
# differs between them. Each returns (text, output_tokens, model_used).
# =====================================================================

# Call Claude directly (Anthropic's own SDK / request shape).
def call_claude(client, item, cfg):
    import anthropic
    try:
        resp = client.messages.create(
            model=cfg["model"], max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
            system=cfg["system_prompt"], messages=[{"role": "user", "content": item["prompt"]}],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise SystemExit(f"Anthropic rejected the API key, so every task would fail: {e}")
    except anthropic.APIError as e:  # the SDK already retried temporary errors MAX_RETRIES times
        raise AdapterError(f"{type(e).__name__}: {e}") from e
    block = resp.content[0] if resp.content else None
    text = block.text if block is not None and hasattr(block, "text") else ""
    return text, resp.usage.output_tokens, cfg["model"]


# Call an open-source model over OpenRouter (OpenAI-compatible request shape).
def call_opensource(client, item, cfg):
    import openai
    try:
        resp = client.chat.completions.create(
            model=cfg["model"], max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
            messages=[{"role": "system", "content": cfg["system_prompt"]},
                      {"role": "user", "content": item["prompt"]}],
        )
    except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
        raise SystemExit(f"OpenRouter rejected the API key, so every task would fail: {e}")
    except openai.APIError as e:  # the SDK already retried temporary errors MAX_RETRIES times
        raise AdapterError(f"{type(e).__name__}: {e}") from e
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.completion_tokens if resp.usage else None
    return text, tokens, resp.model  # resp.model: "openrouter/free" auto-routes, record what actually answered


# Flatten a LangChain-style result into plain text (newer langchain-anthropic returns a list of content blocks).
def _to_text(out) -> str:
    if isinstance(out, str):
        return out
    if isinstance(out, list):
        return "".join(b if isinstance(b, str) else b.get("text", "") for b in out)
    return str(out)


# Call Panacea's own coding agent (packages/backend/agents/coding_agent.py, see panacea_config.md).
# `client` is the run_coding_agent function itself (built by _load_panacea below).
def call_panacea(client, item, cfg):
    with tempfile.TemporaryDirectory() as empty_dir:  # prompt-only: the agent's file tools see nothing
        out = _to_text(client(item["prompt"], cwd=empty_dir))
    # run_coding_agent swallows every exception and returns it as a string, so check for it.
    # Not retried here: its ChatAnthropic already retried temporary errors MAX_RETRIES times.
    if out.startswith("Agent error:"):
        raise AdapterError(out[:300])
    return out, None, cfg["model"]  # the function does not expose token usage


# Return the dataset's own reference solution. No API, no cost: a sanity check that the
# whole pipeline (loading, prompts, code extraction, scoring) works. Expect pass@1 = 1.0.
def call_reference(client, item, cfg):
    if not item.get("reference"):
        raise AdapterError("item has no reference solution")
    return "```python\n" + item["reference"] + "\n```", 0, "reference"


# Build the Anthropic client (imported here so the reference provider works without the anthropic package).
def _anthropic_client(key):
    import anthropic
    return anthropic.Anthropic(api_key=key, max_retries=MAX_RETRIES)


# Build the OpenRouter client (imported here so the other providers work without the openai package).
def _openrouter_client(key):
    from openai import OpenAI  # OpenRouter speaks the OpenAI API format
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, max_retries=MAX_RETRIES)


# Import Panacea's run_coding_agent from the pinned clone and check we are on the pinned commit.
def _load_panacea(key):
    backend = PANACEA_DIR / "packages" / "backend"
    if not (backend / "agents" / "coding_agent.py").exists():
        raise SystemExit(f"Panacea not found at {PANACEA_DIR}. Clone it (panacea_config.md, section 4) "
                         f"or set PANACEA_PATH.")
    want = PROVIDERS["panacea"]["config"]["panacea_commit"]
    have = subprocess.run(["git", "-C", str(PANACEA_DIR), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if have != want:
        raise SystemExit(f"Panacea is at {have[:7] or 'unknown'}, expected pinned commit {want[:7]}. "
                         f"Run: git -C {PANACEA_DIR} checkout {want}")
    os.environ["ANTHROPIC_API_KEY"] = key  # run_coding_agent reads the key from the environment

    # run_coding_agent imports ChatAnthropic inside its body and sets neither max_tokens nor temperature
    # (so LangChain's 1024 tokens and the API's temperature 1.0 apply). Wrap the class it imports so it
    # gets the shared settings. The clone is not edited.
    import langchain_anthropic
    chat_anthropic = langchain_anthropic.ChatAnthropic
    cfg = PROVIDERS["panacea"]["config"]

    def shared_settings_chat_anthropic(*args, **kwargs):
        kwargs.setdefault("max_tokens", cfg["max_tokens"])
        kwargs.setdefault("temperature", cfg["temperature"])
        kwargs.setdefault("max_retries", cfg["max_retries"])
        return chat_anthropic(*args, **kwargs)

    langchain_anthropic.ChatAnthropic = shared_settings_chat_anthropic

    sys.path.insert(0, str(backend))
    from agents.coding_agent import run_coding_agent
    return run_coding_agent


# =====================================================================
# PROVIDERS
# =====================================================================
PROVIDERS = {
    "claude": {
        "config": {
            "panacea_repo": "https://github.com/anote-ai/Panacea",
            "panacea_commit": "bea399509efbab4ac242042b64f8b28b8865691e",  # main as of 2026-09-15
            "model": "claude-sonnet-4-6",           # Panacea's DEFAULT_MODEL / coding agent model
            "system_prompt": "You are an expert coding assistant.",  # coding_agent.py
            "max_tokens": MAX_TOKENS,               # shared with every arm (see above)
            "temperature": TEMPERATURE,             # shared with every arm (see above)
            "max_retries": MAX_RETRIES,             # shared with every arm (see above)
        },
        "api_key_env": "ANTHROPIC_API_KEY",
        "output_file": "baseline_run.json",
        "default_n": 3,  # same default for every provider, so runs line up
        "client_factory": _anthropic_client,
        "call": call_claude,
    },
    "opensource": {
        "config": {
            "base_url": "https://openrouter.ai/api/v1",
            # auto-routes to whatever free model is currently available - the
            # model that actually answered is recorded per-item as "model_used"
            "model": "openrouter/free",
            "system_prompt": "You are an expert coding assistant.",  # same prompt, for a fair comparison
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "max_retries": MAX_RETRIES,
        },
        "api_key_env": "OPENROUTER_API_KEY",
        "output_file": "opensource_run.json",
        "default_n": 3,  # free-tier models are rate-limited (~50 requests/day) - keep this small
        "client_factory": _openrouter_client,
        "call": call_opensource,
    },
    "panacea": {
        "config": {
            "panacea_repo": "https://github.com/anote-ai/Autonomous-Intelligence",
            "panacea_commit": "bea399509efbab4ac242042b64f8b28b8865691e",  # same pin as "claude" above
            "component": "packages/backend/agents/coding_agent.py :: run_coding_agent",
            "model": "claude-sonnet-4-6",           # hardcoded inside run_coding_agent
            "system_prompt": "You are an expert coding assistant.",  # hardcoded inside run_coding_agent
            "tools": ["read_file", "list_files"],
            "max_iterations": 5,
            # Stock Panacea sets none of these (LangChain's 1024 tokens, the API's temperature 1.0).
            # We set them at load time (_load_panacea), a flagged deviation; see panacea_config.md.
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "max_retries": MAX_RETRIES,
        },
        "api_key_env": "ANTHROPIC_API_KEY",
        "output_file": "panacea_run.json",
        "default_n": 3,  # the agent loop makes several API calls per item, keep it small first
        "client_factory": _load_panacea,
        "call": call_panacea,
    },
    "reference": {
        "config": {"note": "returns each item's reference solution; pipeline sanity check, no API"},
        "api_key_env": None,
        "output_file": "reference_run.json",
        "default_n": 3,
        "client_factory": lambda key: None,
        "call": call_reference,
    },
}
