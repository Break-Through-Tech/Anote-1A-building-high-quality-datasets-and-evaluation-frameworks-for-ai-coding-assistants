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

# Output-length cap shared by every arm, so no arm gets cut off sooner than another.
# Placeholder value until the experiment model and budget are chosen; change it only here.
MAX_TOKENS = 4096


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
    resp = client.messages.create(
        model=cfg["model"], max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
        system=cfg["system_prompt"], messages=[{"role": "user", "content": item["prompt"]}],
    )
    block = resp.content[0] if resp.content else None
    text = block.text if block is not None and hasattr(block, "text") else ""
    return text, resp.usage.output_tokens, cfg["model"]


# Call an open-source model over OpenRouter (OpenAI-compatible request shape).
def call_opensource(client, item, cfg):
    resp = client.chat.completions.create(
        model=cfg["model"], max_tokens=cfg["max_tokens"], temperature=cfg["temperature"],
        messages=[{"role": "system", "content": cfg["system_prompt"]},
                  {"role": "user", "content": item["prompt"]}],
    )
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
    return anthropic.Anthropic(api_key=key)


# Build the OpenRouter client (imported here so the other providers work without the openai package).
def _openrouter_client(key):
    from openai import OpenAI  # OpenRouter speaks the OpenAI API format
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


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

    # run_coding_agent imports ChatAnthropic inside its body and never sets max_tokens (so LangChain's
    # default of 1024 applies). Wrap the class it imports so it gets the shared cap. The clone is not edited.
    import langchain_anthropic
    chat_anthropic = langchain_anthropic.ChatAnthropic
    cap = PROVIDERS["panacea"]["config"]["max_tokens"]

    def capped_chat_anthropic(*args, **kwargs):
        kwargs.setdefault("max_tokens", cap)
        return chat_anthropic(*args, **kwargs)

    langchain_anthropic.ChatAnthropic = capped_chat_anthropic

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
            "max_tokens": MAX_TOKENS,               # shared with every arm (see MAX_TOKENS above)
            "temperature": 0,                       # not set in Panacea; pinned here for reproducibility
        },
        "api_key_env": "ANTHROPIC_API_KEY",
        "output_file": "baseline_run.json",
        "default_n": 5,
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
            "temperature": 0,
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
            "max_tokens": MAX_TOKENS,               # stock Panacea uses LangChain's 1024; set at load time (_load_panacea)
            "temperature": "not set (Anthropic API default)",  # Panacea does not expose it; see panacea_config.md section 7
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
        "default_n": 5,
        "client_factory": lambda key: None,
        "call": call_reference,
    },
}
