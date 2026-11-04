"""

keeps a record of api calls and their estimated costs

save this file in the AI_models folder

how to use it:
  1 call set_context to identify the task, experiment group, and attempt
  2 call check_budget before sending an api request
  3 call record_call after receiving the response

each model call adds one row to runs/usage_log.csv
this includes calls that generate code and calls that review code

test results are saved separately because testing happens after the api call
use task_id, arm, and attempt to match this log with the test results

new requests stop when the logged total reaches $47
a request that starts below $47 can still push the total over that amount
"""

from __future__ import annotations

import contextvars
import csv
import os
import sys
import threading
import time
from pathlib import Path

LOG_PATH = Path(os.environ.get("USAGE_LOG_PATH", "runs/usage_log.csv"))

# budget amounts in dollars
BUDGET_USD = 50.0
WARN_AT_USD = 40.0   # show a warning when the logged total reaches $40
STOP_AT_USD = 47.0   # stop new requests at $47 to leave a $3 buffer

# store each model's input and output prices per million tokens
# add the exact model name and its prices from the provider's pricing page
# the first number is the input price and the second is the output price
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),  # the experiment model (decided 2026-11-03); Anthropic list price
}

# use these backup prices when a model is missing from the price table
# these are placeholders and may not cover every model's actual price
# price_known is false when these backup prices are used
FALLBACK_PRICE_PER_MTOK = (15.0, 75.0)

# column names for the csv log
FIELDS = [
    "timestamp", "task_id", "arm", "attempt", "call_type", "model",
    "input_tokens", "output_tokens", "estimated", "price_known",
    "cost_usd", "latency_s",
]


class BudgetExceeded(RuntimeError):
    """stops the program when the logged spending reaches the stop limit"""


# remember which task and attempt the current call belongs to
_ctx = contextvars.ContextVar("usage_ctx", default=None)

# allow only one thread at a time to update the log and spending total
_lock = threading.Lock()

# store the spending total and whether the warning has already been shown
_state = {"total": None, "warned": False}


# information about the current api call
def set_context(**fields):
    """
    save details about the call before sending it

    example:
        set_context(task_id="lcb_123", arm="reflect_then_fix",
                    attempt=2, call_type="generator")

    arm means the experiment group or strategy being tested
    call_type identifies whether the model generates code or reviews it

    saved values stay in place until changed or cleared
    if using threads, call this function inside each thread
    """
    current = dict(_ctx.get() or {})
    current.update(fields)
    _ctx.set(current)


def clear_context():
    """clear the saved details about the current call"""
    _ctx.set(None)


# helper functions
def estimate_tokens(text: str) -> int:
    """
    guess the token count when the api does not provide it
    use about one token for every four characters
    this is a rough estimate and can be too high or too low
    """
    return max(1, len(text or "") // 4)


def _price(model: str):
    """look up the model's prices or use the backup prices"""
    price = PRICES_PER_MTOK.get(model)
    if price is None:
        return FALLBACK_PRICE_PER_MTOK, False
    return price, True


def _load_total() -> float:
    """add up the costs already saved in the csv file"""
    if not LOG_PATH.exists():
        return 0.0
    total = 0.0
    with open(LOG_PATH, newline="") as f:
        for row in csv.DictReader(f):
            try:
                total += float(row["cost_usd"])
            except (KeyError, TypeError, ValueError):
                pass
    return total


def _ensure_total():
    """load the saved spending total if it has not been loaded yet"""
    # the calling function must hold the lock before using this function
    if _state["total"] is None:
        _state["total"] = _load_total()
    return _state["total"]


def total_spent() -> float:
    """return the total spending recorded by this tracker"""
    with _lock:
        return _ensure_total()


def _append(row: dict):
    """add one row to the csv file and create the folder if needed"""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow(row)


# functions used by the rest of the project
def check_budget():
    """
    call this before sending each api request
    block the request if the logged total has reached $47
    this does not check how much the next request might cost
    """
    spent = total_spent()
    if spent >= STOP_AT_USD:
        raise BudgetExceeded(
            f"Logged spend ${spent:.2f} has reached the stop limit "
            f"${STOP_AT_USD:.2f} (budget ${BUDGET_USD:.2f}). Check the provider "
            f"dashboard before raising STOP_AT_USD."
        )


def record_call(model, input_tokens=None, output_tokens=None,
                prompt_text="", output_text="", latency_s=None):
    """
    call this after receiving an api response
    calculate the estimated cost and save the call in the csv log
    return the saved row

    use the token counts from the api response when available
    if a count is missing, guess it from the matching text
    estimated is true if either token count was guessed

    latency_s is how long the request took in seconds
    """
    estimated = False
    if input_tokens is None:
        input_tokens, estimated = estimate_tokens(prompt_text), True
    if output_tokens is None:
        output_tokens, estimated = estimate_tokens(output_text), True

    (price_in, price_out), price_known = _price(model)
    cost = (input_tokens * price_in + output_tokens * price_out) / 1_000_000

    ctx = _ctx.get() or {}
    row = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "task_id": ctx.get("task_id"),
        "arm": ctx.get("arm"),
        "attempt": ctx.get("attempt"),
        "call_type": ctx.get("call_type", "generator"),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated": estimated,
        "price_known": price_known,
        "cost_usd": round(cost, 6),
        "latency_s": latency_s,
    }

    # save the call and update the total while holding the lock
    with _lock:
        _ensure_total()
        _append(row)
        _state["total"] += cost
        total = _state["total"]
        should_warn = total >= WARN_AT_USD and not _state["warned"]
        if should_warn:
            _state["warned"] = True

    # show the budget warning only once during this program run
    if should_warn:
        print(f"[usage_log] WARNING: logged spend ${total:.2f} passed "
              f"${WARN_AT_USD:.2f} of the ${BUDGET_USD:.2f} budget.",
              file=sys.stderr)

    # remind the user to add the model's actual prices
    if not price_known:
        print(f"[usage_log] No price set for model '{model}'; using the "
              f"high fallback. Add it to PRICES_PER_MTOK.", file=sys.stderr)
    return row


def summarize(path=None):
    """
    summarize calls, tokens, and costs for each experiment group and call type
    read the default log unless a different file path is provided
    """
    import pandas as pd
    df = pd.read_csv(path or LOG_PATH)
    return (
        df.groupby(["arm", "call_type"], dropna=False)
        .agg(calls=("cost_usd", "size"),
             input_tokens=("input_tokens", "sum"),
             output_tokens=("output_tokens", "sum"),
             cost_usd=("cost_usd", "sum"))
        .round(4)
        .reset_index()
    )


def estimate_main_run(model, n_tasks, n_failed, retries=3, plain_arms=3,
                      critic_arms=1, avg_input_first=600, avg_input_retry=1500,
                      avg_output=500):
    """
    estimate the cost of running the full experiment

    n_tasks is the total number of tasks
    n_failed is the number that fail the first attempt
    retries is the maximum number of extra attempts per failed task
    plain_arms is the number of strategies using one call per retry
    critic_arms is the number of strategies using two calls per retry

    replace the example token averages with averages from a small test run

    this assumes every failed task uses all allowed retries
    stopping retries early can lower the cost
    actual costs can be higher if token use exceeds these averages
    """
    (price_in, price_out), known = _price(model)

    first_calls = n_tasks
    retry_calls = n_failed * retries * (plain_arms + 2 * critic_arms)

    in_tokens = first_calls * avg_input_first + retry_calls * avg_input_retry
    out_tokens = (first_calls + retry_calls) * avg_output
    cost = (in_tokens * price_in + out_tokens * price_out) / 1_000_000
    return {
        "calls": first_calls + retry_calls,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "est_cost_usd": round(cost, 2),
        "price_known": known,
    }