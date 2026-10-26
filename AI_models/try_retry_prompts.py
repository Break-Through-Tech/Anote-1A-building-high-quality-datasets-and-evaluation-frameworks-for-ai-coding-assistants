"""
try_retry_prompts.py

Prompt trial for the "Reflection / critique prompt strategies" task: try the four
retry prompts (AI_models/retry_prompts.py) on 10 MBPP tasks. This is NOT the
Evaluator-Optimizer loop (no 3-retry chains, no budget log). It only checks that
each arm's prompt gets a sensible, extractable answer.

For each task:
  1. attempt 0 with the dataset's own prompt
  2. if attempt 0 fails its PUBLIC tests: ONE retry per arm
     (control, bare_retry, reflect_fix, critic), all from the same attempt 0
  3. every answer is scored on public AND hidden tests

Usage (from the repo root):
    python AI_models/try_retry_prompts.py mock          # no API: checks the plumbing, numbers mean nothing
    python AI_models/try_retry_prompts.py claude        # first 10 MBPP tasks, about 10-50 API calls
    python AI_models/try_retry_prompts.py claude --n 5

Writes try_prompts_<provider>_run.json at the repo root (git-ignored by the *_run.json rule):
every prompt, answer, critique and score, for reading the answers by hand.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from Evaluator.evaluator import evaluate, extract_code, format_feedback, load_items
from AI_models.prompts import build_prompt
from AI_models.providers import PROVIDERS, AdapterError
from AI_models import retry_prompts as rp


# Fake model for an offline check: broken stub at attempt 0 for about half the tasks,
# the reference solution on most retries. Its pass rates mean nothing.
def call_mock(client, item, cfg):
    if item.get("_role") == "critic":
        return "- The function returns the wrong value.", 10, "mock"
    h = int(hashlib.md5(f"{item['id']}{item.get('_arm')}".encode()).hexdigest(), 16) % 10
    if item.get("_arm") is None and h < 5 or item.get("_arm") == "control" and h < 6:
        return f"```python\ndef {item['entry_point']}(*args, **kwargs):\n    return None\n```", 10, "mock"
    return "```python\n" + item["reference"] + "\n```", 10, "mock"


MOCK = {"config": {"model": "mock"}, "api_key_env": None, "client_factory": lambda k: None, "call": call_mock}


def ask(p, client, item, prompt, system, tags):
    cfg = {**p["config"], "system_prompt": system}
    try:
        text, out_tokens, _ = p["call"](client, {**item, **tags, "prompt": prompt}, cfg)
    except AdapterError as e:
        return "", 0, f"adapter_error: {e}"
    return text, out_tokens or 0, None


def score(item, text):
    pub = evaluate(item, text, split="public")
    hid = evaluate(item, text, split="private", keep_details=False)
    return pub, {"public": pub["score"], "hidden": hid["score"], "hidden_tests": f"{hid['n_passed']}/{hid['n_tests']}",
                 "failure_type": pub["failure_type"], "rubric_level": pub["rubric_level"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", choices=["claude", "opensource", "mock"])
    ap.add_argument("--n", type=int, default=10, help="first n MBPP tasks (default 10)")
    args = ap.parse_args()
    p = MOCK if args.provider == "mock" else PROVIDERS[args.provider]
    key = os.environ.get(p["api_key_env"]) if p["api_key_env"] else None
    if p["api_key_env"] and not key:
        sys.exit(f"{p['api_key_env']} not set. Copy .env.example to .env and fill it in.")
    client = p["client_factory"](key)
    items = load_items(sources=["mbpp"], n_per_source=args.n)

    rows, totals = [], {"calls": 0, "output_tokens": 0}
    for it in items:
        prompt0 = build_prompt(it, "raw")
        text0, tok, err = ask(p, client, it, prompt0, rp.GENERATOR_SYSTEM, {"_arm": None})
        totals["calls"] += 1; totals["output_tokens"] += tok
        pub0, s0 = score(it, text0)
        row = {"id": it["id"], "attempt0": {**s0, "output": text0, "error": err}, "arms": {}}
        print(f"{it['id']}: attempt 0 public={s0['public']} hidden={s0['hidden']}", file=sys.stderr)
        if s0["public"] != 1.0:
            prev_code, fb = extract_code(text0, it.get("entry_point")), format_feedback(pub0)
            for arm in rp.ARMS:
                critique = None
                if arm == "control":
                    prompt = prompt0
                elif arm == "bare_retry":
                    prompt = rp.bare_retry(it["prompt"], prev_code)
                elif arm == "reflect_fix":
                    prompt = rp.reflect_fix(it["prompt"], prev_code, fb)
                else:
                    critique, tok, _ = ask(p, client, it, rp.critic_review(it["prompt"], prev_code, fb),
                                           rp.CRITIC_SYSTEM, {"_arm": arm, "_role": "critic"})
                    totals["calls"] += 1; totals["output_tokens"] += tok
                    prompt = rp.critic_fix(it["prompt"], prev_code, fb, critique)
                text, tok, err = ask(p, client, it, prompt, rp.GENERATOR_SYSTEM, {"_arm": arm})
                totals["calls"] += 1; totals["output_tokens"] += tok
                _, s = score(it, text)
                row["arms"][arm] = {**s, "prompt": prompt, "critique": critique, "output": text, "error": err}
                print(f"    {arm:<11} public={s['public']} hidden={s['hidden']} ({s['hidden_tests']})", file=sys.stderr)
        rows.append(row)

    out = REPO_ROOT / f"try_prompts_{args.provider}_run.json"
    out.write_text(json.dumps({"provider": args.provider, "totals": totals, "results": rows}, indent=2))

    failed = [r for r in rows if r["arms"]]
    print(f"\n{len(rows)} tasks, {len(failed)} failed attempt 0 and got one retry per arm. "
          f"{totals['calls']} calls, {totals['output_tokens']} output tokens.")
    print("| arm | fixed (public) | fixed (hidden) |\n|---|---|---|")
    for arm in rp.ARMS:
        pub = sum(r["arms"][arm]["public"] == 1.0 for r in failed)
        hid = sum(r["arms"][arm]["hidden"] == 1.0 for r in failed)
        print(f"| {arm} | {pub}/{len(failed)} | {hid}/{len(failed)} |")
    print(f"\nFull prompts and answers: {out.name}")


if __name__ == "__main__":
    main()
