# TESTING
Generated: 2026-04-17
Focus: quality

---

## Test Framework

- **Runner:** pytest 9.0.2
- **Mocking:** `unittest.mock` (patch, MagicMock, patch.object)
- **Total tests:** 61 passing (as of Apr 17 2026)
- **Test command:** `cd gold-agent && pytest` (run from `gold-agent/` subdirectory)

---

## Test Directory Structure

```
gold-agent/tests/
├── __init__.py
├── test_paper_engine.py        # 29 tests — paper trading engine
├── test_confluence_regime.py   # 8 tests  — technical indicator scoring
├── test_sentiment.py           # 5 tests  — news sentiment analysis
├── test_lightrag_store.py      # 5 tests  — LightRAG knowledge store
├── test_agent_news_tool.py     # 3 tests  — agent tool handler
└── test_pl_card.py             # 2 tests  — P&L card image generation

tests/                          # root-level tests (separate pytest scope)
└── test_dashboard_charts.py    # dashboard chart tests
```

---

## Coverage by Module

| Module | Test File | Coverage | Notes |
|---|---|---|---|
| `trader/paper_engine.py` | test_paper_engine.py | High | BUY/SELL/HOLD, portfolio summary, trade history, equity, resets, edge cases |
| `indicators/tech.py` | test_confluence_regime.py | Medium | `calculate_confluence_score`, `calculate_market_regime` — RSI/MACD/BB math untested directly |
| `news/sentiment.py` | test_sentiment.py | Medium | GPT path, fallback path, empty key path |
| `knowledge/lightrag_store.py` | test_lightrag_store.py | Medium | insert, query, failure modes |
| `agent/trading_agent.py` | test_agent_news_tool.py | Low | Only `_execute_tool("get_news")` tested |
| `ui/dashboard.py` | test_pl_card.py | Low | Only `_build_pl_card()` — no dashboard render or refresh tests |

---

## Coverage Gaps

| Module | What's Missing |
|---|---|
| `data/fetch.py` | No tests at all (yfinance calls) |
| `converter/thai.py` | No tests (USD/THB conversion math) |
| `backtest.py` | No tests (entire backtest pipeline) |
| `agent/trading_agent.py` | `run_full_analysis()` integration path untested |
| `trader/paper_engine.py` | Trailing stop paths only partially covered |
| `trader/trade_scheduler.py` | No tests (quota enforcement, window detection) |
| `logger/cost_tracker.py` | No tests (LLM cost persistence) |
| `logger/trade_log.py` | No tests (CSV append/read) |
| `risk/metrics.py` | No tests (Sharpe, Sortino, Kelly, drawdown) |
| `agent/daily_market_agent.py` | No tests (daily macro bias agent) |
| `news/sentiment.py` | `get_gold_news()` (NewsAPI call) untested |

---

## Mocking Patterns

### Primary pattern — patch.object on module-level functions
```python
with patch.object(pe, "_load", return_value=fresh()), \
     patch.object(pe, "_save") as mock_save:
    result = pe.execute_paper_trade("BUY", 70, PRICE)
```
Used throughout `test_paper_engine.py`. Avoids touching `data/portfolio.json`.

### API mocking — patch constructor then configure return value
```python
with patch("news.sentiment.OpenAI") as mock_openai:
    mock_openai.return_value.chat.completions.create.return_value = mock_response
    result = get_sentiment_summary(["Gold headline"])
```

### Thread worker patching — patch the worker function, not internals
```python
with patch("knowledge.lightrag_store._insert_in_thread") as mock_worker:
    insert_headlines(["Gold rises on Fed news"])
mock_worker.assert_called_once_with([...])
```
Required because LightRAG uses `ThreadPoolExecutor` — patching internal async ops doesn't work.

### Environment variable mocking
```python
with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
    ...
```

### State capture via side_effect
```python
captured = {}
def capture_save(state):
    captured.update(state)
with patch.object(pe, "_save", side_effect=capture_save):
    pe.execute_paper_trade("BUY", 70, PRICE)
# inspect captured state directly
```

---

## Test Data Helpers

`test_paper_engine.py` defines reusable state builders:
- `fresh()` — clean portfolio state, mirrors `_fresh_state()`
- `state_with_position(entry_price)` — state with open BUY at given price
- `state_with_closed_trade(pnl)` — state with one completed trade

`test_confluence_regime.py` uses:
- `_make_df(closes)` — build minimal OHLCV DataFrame from close price list

---

## Running Tests

```bash
# From gold-agent/ directory (required for module imports)
cd gold-agent
pytest

# Specific module
pytest tests/test_paper_engine.py
pytest tests/test_confluence_regime.py -v

# With coverage (if pytest-cov installed)
pytest --cov=. --cov-report=term-missing
```

> **Note:** Tests must be run from `gold-agent/` not the repo root. Several test files use `sys.path.insert(0, ...)` to resolve module paths. The root `tests/` directory has a separate pytest scope and may require running from the repo root.
