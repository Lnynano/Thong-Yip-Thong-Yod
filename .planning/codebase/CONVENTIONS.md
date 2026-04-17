# CONVENTIONS.md
Generated: 2026-04-17
Focus: quality

## Overview

Python 3.13 codebase using type hints consistently on function signatures. All source lives under `gold-agent/`. No linting config files (no `.flake8`, `pyproject.toml`, or `.eslintrc`) are present — style is enforced by convention and code review only.

---

## Naming Patterns

**Files:**
- `snake_case.py` throughout — `trading_agent.py`, `paper_engine.py`, `cost_tracker.py`
- Module directories match domain names: `agent/`, `data/`, `indicators/`, `trader/`, `logger/`, `news/`, `risk/`, `converter/`, `knowledge/`, `ui/`

**Functions:**
- Public: `snake_case` — `get_gold_price()`, `execute_paper_trade()`, `calculate_rsi()`
- Private helpers: leading underscore `_snake_case` — `_load()`, `_save()`, `_execute_tool()`, `_fresh_state()`, `_parse_json_with_retry()`, `_calc_fee()`, `_size_pct_by_confidence()`

**Variables:**
- `snake_case` for all local variables
- UPPERCASE module-level constants: `DEFAULT_BALANCE`, `MIN_TRADE_THB`, `CONF_THRESHOLD`, `TAKE_PROFIT_PCT`, `STOP_LOSS_PCT`, `TRAILING_SL_PCT`, `TROY_OZ_TO_GRAMS`, `GRAMS_PER_BAHT_WEIGHT`, `THAI_GOLD_PURITY`
- Private module-level singletons: `_mongo_client`, `_mongo_db`, `_sentiment_cache`, `_last_fetched_at`

**Classes:**
- `PascalCase` for test classes only: `TestExecutePaperTrade`, `TestGetPortfolioSummary`
- No application-level classes — the codebase is entirely procedural/functional

**String literals used as enum values:**
- Decision signals: `"BUY"`, `"SELL"`, `"HOLD"`, `"SKIP"`
- Sentiment: `"BULLISH"`, `"BEARISH"`, `"NEUTRAL"`
- Regime: `"TRENDING UP"`, `"TRENDING DOWN"`, `"RANGING"`, `"VOLATILE"`
- Outcome: `"WIN"`, `"LOSS"`

---

## Module File Pattern

Every module follows this exact structure:

```python
"""
module/filename.py
One-line summary.

Extended description, formulas, design notes.
"""

import os
import json
# stdlib imports first

from openai import OpenAI
# third-party imports second

load_dotenv()

# MODULE-LEVEL CONSTANTS in UPPERCASE
CONSTANT_NAME = value

# Private state singletons (lazy-init)
_private_var = None

# Section dividers use this exact style:
# ─────────────────────────────────────────────────────────────
# Section Name
# ─────────────────────────────────────────────────────────────

def public_function(param: type) -> return_type:
    """Docstring."""
    ...

def _private_helper(param: type) -> return_type:
    """Docstring."""
    ...

# Allow standalone testing
if __name__ == "__main__":
    ...
```

All source files (`fetch.py`, `tech.py`, `sentiment.py`, `paper_engine.py`, `trading_agent.py`, `converter/thai.py`) follow this pattern. Every module ends with `if __name__ == "__main__":` standalone test block.

---

## Type Hints

Type hints are used on all public function signatures. Python 3.10+ union syntax (`X | Y`) is used:

```python
def execute_paper_trade(decision: str, confidence: int, price_thb: float, min_confidence: int | None = None) -> dict:

def _parse_json_with_retry(text: str, attempt: int = 1) -> dict | None:

def get_gold_news(max_headlines: int = 5) -> list[str]:

def get_sentiment_strength(headlines: list[str]) -> dict:

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
```

Return types are always annotated. Internal/private helpers also carry type hints.

---

## Docstring Style

All public functions have docstrings with this structure:

```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """
    One-sentence summary.

    Extended explanation including formula.

    Args:
        df (pd.DataFrame): Description.
        period (int): Description. Default is 14.

    Returns:
        float: Description. Returns 50.0 on failure.
    """
```

Google-style Args/Returns sections. Formulas included inline with math notation (e.g. `RSI = 100 - 100 / (1 + RS)`).

---

## Error Handling Patterns

**Universal pattern: try/except → return safe default.**
Every function that can fail wraps its body in `try/except Exception` and returns a safe default. No exceptions propagate to callers from data-fetching or calculation functions:

```python
# From tech.py — indicator safe default
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    try:
        ...
        return round(rsi_value, 2)
    except Exception as e:
        print(f"[tech.py] Error calculating RSI: {e}")
        return 50.0   # safe neutral default

# From fetch.py — data fetch safe default
def get_gold_price() -> pd.DataFrame:
    try:
        ...
        return df
    except Exception as e:
        print(f"[fetch.py] Error fetching gold price: {e}")
        return pd.DataFrame()   # empty DataFrame signals failure
```

**Non-critical failures are silently swallowed** with a print log. Optional enrichment blocks (DXY/VIX fetch, H1 MTF fetch, LightRAG queries) use bare `except Exception: pass` so optional data never crashes the main flow:

```python
# From trading_agent.py
try:
    from agent.daily_market_agent import get_daily_market
    dm = get_daily_market()
    ...
except Exception:
    daily_summary = ""   # silently continue without this data
```

**Critical JSON parsing uses retry logic** with a second attempt that strips trailing commas — see `_parse_json_with_retry()` in `gold-agent/agent/trading_agent.py`.

**Safety validation layer** (`_validate_decision()` in `gold-agent/agent/trading_agent.py`) catches invalid agent output after parsing:
- Invalid `decision` string → force `"HOLD"`
- `confidence` out of 0–100 → clamp
- `confidence < 40` → force `"HOLD"`

---

## Logging

**No logging framework.** All output uses `print()` with a module-name tag prefix:

```python
print(f"[fetch.py] Fetched {len(df)} rows. Latest close: {df['Close'].iloc[-1]:.2f} USD")
print(f"[tech.py] RSI({period}): {rsi_value:.2f}")
print(f"[paper_engine.py] OPENED  {size_bw:.5f} bw @ {price_thb:,.0f} THB  conf={confidence}%")
print(f"[trading_agent.py] Iteration {iteration}/{max_iterations}")
print(f"[sentiment.py] GPT sentiment: {label}")
print(f"[thai.py] ${usd_price:.2f}/oz -> {thb_per_baht_weight_thai:.2f} THB/bw")
```

Pattern: `[module_filename.py] Message with relevant values`.

Log level distinction: all logs use `print()` — no debug/info/warn/error separation. Critical errors are logged before returning defaults; non-critical failures log and continue.

---

## Import Organization

**Within each file (3-tier, no blank lines between):**
1. Standard library (`os`, `json`, `csv`, `re`, `hashlib`, `time`, `random`, `datetime`)
2. Third-party (`openai`, `yfinance`, `pandas`, `numpy`, `requests`, `dotenv`)
3. Internal project imports appear **inside function bodies** to avoid circular imports:

```python
# From trading_agent.py — internal imports deferred to function body
def _execute_tool(tool_name: str, tool_input: dict) -> str:
    import sys
    import os
    sys.path.insert(0, os.path.abspath(...))

    if tool_name == "get_price":
        from data.fetch import get_gold_price
        ...
    elif tool_name == "get_indicators":
        from indicators.tech import calculate_rsi, calculate_macd
        ...
```

`sys.path.insert(0, ...)` is used in several files to resolve the `gold-agent/` root as an import base, as there is no package installation or `pyproject.toml`.

**`load_dotenv()`** is called at module top level in every module that reads env vars.

---

## Constants and Magic Numbers

All domain-specific numeric constants are named at module level:

| Constant | Value | File | Meaning |
|---|---|---|---|
| `DEFAULT_BALANCE` | `1500.0` | `paper_engine.py` | Starting THB capital |
| `MIN_TRADE_THB` | `1000.0` | `paper_engine.py` | Minimum trade size |
| `CONF_THRESHOLD` | `65` | `paper_engine.py` | Confidence gate % |
| `TAKE_PROFIT_PCT` | `0.015` | `paper_engine.py` | +1.5% auto TP |
| `STOP_LOSS_PCT` | `-0.010` | `paper_engine.py` | -1.0% auto SL |
| `TRAILING_SL_PCT` | `0.007` | `paper_engine.py` | 0.7% trailing stop |
| `LOSS_COOLDOWN` | `1` | `paper_engine.py` | Post-loss skip rounds |
| `THAI_GOLD_PURITY` | `0.965` | `converter/thai.py` | 96.5% purity |
| `GRAMS_PER_BAHT_WEIGHT` | `15.244` | `converter/thai.py` | Baht-weight mass |
| `TROY_OZ_TO_GRAMS` | `31.1035` | `converter/thai.py` | Troy oz conversion |
| `DEFAULT_USD_THB_RATE` | `34.5` | `converter/thai.py` | Fallback FX rate |
| `_CACHE_TTL` | `600` | `news/sentiment.py` | Sentiment cache 10 min |

Inline magic numbers are rare — scoring weights in `trading_agent.py` (`buy_score += 2`, `buy_score += 1`) are the main exceptions, documented with inline comments.

---

## State and Data Flow

**No global mutable state in business logic.** Data is passed explicitly between functions. The paper engine stores state in `data/portfolio.json` (or MongoDB), loaded fresh on each call via `_load()` and persisted via `_save()`.

**Module-level singletons** are used only for infrastructure (MongoDB client, sentiment cache, fetch timestamp). These are initialized lazily and accessed via accessor functions.

**Monetary values:**
- Internal calculations: USD
- UI layer and portfolio state: THB (baht-weight)
- Conversion via `gold-agent/converter/thai.py`

---

## Design Constraints (From CLAUDE.md — Do Not Override)

- `temperature=0` on all LLM calls — deterministic decisions
- Confidence gate: agent must reach ≥65% to trigger a trade
- RSI uses Wilder's smoothing (EWM with `alpha=1/period`), not simple EMA
- Long-only paper engine — no short positions
- Purity constant = 96.5% (0.965)
- `data/portfolio.json` — never modify directly, use `paper_engine.py` methods
- `logger/trade_log.csv` — append only, never overwrite
- Max iterations = 8 in the ReAct loop (infinite loop guard)

---

## Return Value Patterns

Functions return typed dicts rather than dataclasses or objects. Dict keys are documented in docstrings. Failure returns a pre-defined `default` dict at the top of the function:

```python
# From tech.py
default = {"macd": 0.0, "signal": 0.0, "histogram": 0.0}
try:
    ...
    return result
except Exception as e:
    print(f"[tech.py] Error calculating MACD: {e}")
    return default
```

Action results from `execute_paper_trade()` always include `"action"` key with value `"OPENED"`, `"CLOSED"`, `"SKIP"`, or `"HOLD"`.

---

## MongoDB / JSON Dual-Storage Pattern

Both `paper_engine.py` and `trade_log.py` implement this identical pattern:

1. Check if `MONGODB_URI` env var is set
2. Try MongoDB operation
3. On failure or absence, fall back to local JSON/CSV file
4. Print `[module.py] MongoDB X failed, using JSON/CSV: {e}` on fallback

This pattern must be preserved in any new persistence-backed module.
