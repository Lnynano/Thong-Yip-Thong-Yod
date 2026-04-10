"""
logger/cost_tracker.py
Tracks cumulative LLM API costs and deducts from the ฿1,500 competition budget.

GPT-4o-mini pricing (as of 2025):
    Input  : $0.150 / 1M tokens
    Output : $0.600 / 1M tokens

Costs are converted to THB using the live USD/THB rate (or env fallback).
Persisted to data/llm_costs.json so totals survive restarts.

Usage:
    from logger.cost_tracker import track_usage, get_cost_summary

    response = client.chat.completions.create(...)
    track_usage(response.usage, source="trading_agent")

    summary = get_cost_summary()
    print(f"Total LLM cost: {summary['total_thb']:.2f} THB")
"""

import json
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

_THAI_TZ = timezone(timedelta(hours=7))

# ── GPT-4o-mini pricing (USD per token) ──────────────────────
_INPUT_PRICE_PER_TOKEN  = 0.150 / 1_000_000   # $0.150 / 1M tokens
_OUTPUT_PRICE_PER_TOKEN = 0.600 / 1_000_000   # $0.600 / 1M tokens

# ── Persistence ──────────────────────────────────────────────
_COST_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "llm_costs.json")


def _load() -> dict:
    """Load cumulative cost data from JSON file."""
    try:
        if os.path.exists(_COST_FILE):
            with open(_COST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "total_input_tokens":  0,
        "total_output_tokens": 0,
        "total_cost_usd":      0.0,
        "total_cost_thb":      0.0,
        "call_count":          0,
        "calls": [],   # recent call log (capped at 100)
    }


def _save(data: dict) -> None:
    """Persist cost data to JSON file."""
    try:
        os.makedirs(os.path.dirname(_COST_FILE), exist_ok=True)
        with open(_COST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[cost_tracker.py] Save failed: {e}")


def _get_usd_thb_rate() -> float:
    """Get USD/THB rate for cost conversion."""
    try:
        return float(os.getenv("USD_THB_RATE", "34.5"))
    except (ValueError, TypeError):
        return 34.5


def track_usage(usage, source: str = "unknown") -> dict:
    """
    Record token usage from an OpenAI API response.

    Args:
        usage  : response.usage object (has prompt_tokens, completion_tokens, total_tokens)
        source : identifier for the caller (e.g. "trading_agent", "sentiment", "daily_market")

    Returns:
        dict: {"cost_usd": float, "cost_thb": float, "tokens": int}
    """
    if usage is None:
        return {"cost_usd": 0.0, "cost_thb": 0.0, "tokens": 0}

    input_tokens  = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0

    cost_usd = (input_tokens * _INPUT_PRICE_PER_TOKEN +
                output_tokens * _OUTPUT_PRICE_PER_TOKEN)
    rate     = _get_usd_thb_rate()
    cost_thb = cost_usd * rate

    # Update persistent totals
    data = _load()
    data["total_input_tokens"]  += input_tokens
    data["total_output_tokens"] += output_tokens
    data["total_cost_usd"]       = round(data["total_cost_usd"] + cost_usd, 6)
    data["total_cost_thb"]       = round(data["total_cost_thb"] + cost_thb, 4)
    data["call_count"]          += 1

    # Append to recent calls log (keep last 100)
    data["calls"].append({
        "time":           datetime.now(_THAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "source":         source,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "cost_usd":       round(cost_usd, 6),
        "cost_thb":       round(cost_thb, 4),
    })
    if len(data["calls"]) > 100:
        data["calls"] = data["calls"][-100:]

    _save(data)

    print(f"[cost_tracker.py] {source}: {input_tokens}+{output_tokens} tokens "
          f"= ${cost_usd:.4f} ({cost_thb:.2f} THB)  "
          f"cumulative: {data['total_cost_thb']:.2f} THB")

    return {"cost_usd": cost_usd, "cost_thb": cost_thb,
            "tokens": input_tokens + output_tokens}


def get_cost_summary() -> dict:
    """
    Return cumulative LLM cost summary.

    Returns:
        dict: {
            "total_input_tokens"  : int,
            "total_output_tokens" : int,
            "total_tokens"        : int,
            "total_cost_usd"      : float,
            "total_cost_thb"      : float,
            "call_count"          : int,
            "budget_thb"          : float,   # total competition budget
            "budget_remaining"    : float,   # budget minus LLM costs
            "budget_pct_used"     : float,   # % of budget spent on LLM
        }
    """
    data   = _load()
    budget = float(os.getenv("COMPETITION_BUDGET_THB", "1500"))
    return {
        "total_input_tokens":  data["total_input_tokens"],
        "total_output_tokens": data["total_output_tokens"],
        "total_tokens":        data["total_input_tokens"] + data["total_output_tokens"],
        "total_cost_usd":      data["total_cost_usd"],
        "total_cost_thb":      data["total_cost_thb"],
        "call_count":          data["call_count"],
        "budget_thb":          budget,
        "budget_remaining":    round(budget - data["total_cost_thb"], 2),
        "budget_pct_used":     round(data["total_cost_thb"] / budget * 100, 2) if budget > 0 else 0.0,
    }


def reset_costs() -> None:
    """Reset all cost tracking data. Use with caution."""
    _save({
        "total_input_tokens":  0,
        "total_output_tokens": 0,
        "total_cost_usd":      0.0,
        "total_cost_thb":      0.0,
        "call_count":          0,
        "calls":               [],
    })
    print("[cost_tracker.py] Cost data reset.")
