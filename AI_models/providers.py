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
import anthropic
from openai import OpenAI  # OpenRouter speaks the OpenAI API format


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
            "max_tokens": 4096,                     # llm.complete() default
            "temperature": 0,                       # not set in Panacea; pinned here for reproducibility
        },
        "api_key_env": "ANTHROPIC_API_KEY",
        "output_file": "baseline_run.json",
        "default_n": 5,
        "client_factory": lambda key: anthropic.Anthropic(api_key=key),
        "call": call_claude,
    },
    "opensource": {
        "config": {
            "base_url": "https://openrouter.ai/api/v1",
            # auto-routes to whatever free model is currently available - the
            # model that actually answered is recorded per-item as "model_used"
            "model": "openrouter/free",
            "system_prompt": "You are an expert coding assistant.",  # same prompt, for a fair comparison
            "max_tokens": 4096,
            "temperature": 0,
        },
        "api_key_env": "OPENROUTER_API_KEY",
        "output_file": "opensource_run.json",
        "default_n": 3,  # free-tier models are rate-limited (~50 requests/day) - keep this small
        "client_factory": lambda key: OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key),
        "call": call_opensource,
    },
}
