# ARCHITECTURE.md
Generated: 2026-04-17
Focus: arch

---

## Pattern Overview

**Overall:** Deterministic pipeline feeding a stochastic ReAct agent loop

**Key Characteristics:**
- All numerical computation (prices, indicators, risk) is deterministic Python — no LLM math
- Only one stochastic component: `gold-agent/agent/trading_agent.py` (GPT-4o-mini ReAct loop)
- LLM receives pre-scored, pre-computed state as structured JSON; it reasons, not calculates
- Background trade scheduler runs independently of the Gradio browser session
- Dual storage: local JSON/CSV for dev, MongoDB Atlas for production

---

## Layers

**Data Acquisition:**
- Purpose: Fetch live market prices, compute raw OHLCV, exchange rates
- Location: `gold-agent/data/fetch.py`
- Contains: yfinance OHLCV fetcher (90-day daily + 5-day intraday H1), Hua Seng Heng live price API, macro indicators (DXY, VIX)
- Depends on: yfinance, requests
- Used by: `agent/trading_agent.py` (via tool calls), `ui/dashboard.py`, `backtest.py`

**Indicators Engine:**
- Purpose: Deterministic technical analysis — RSI (Wilder), MACD, Bollinger Bands
- Location: `gold-agent/indicators/tech.py`
- Contains: `calculate_rsi()`, `calculate_macd()`, `calculate_bollinger_bands()`
- Depends on: pandas, numpy
- Used by: `agent/trading_agent.py` inside the `get_indicators` tool handler

**News & Sentiment:**
- Purpose: Fetch live gold headlines from NewsAPI; score BULLISH/BEARISH/NEUTRAL
- Location: `gold-agent/news/sentiment.py`
- Contains: `get_gold_news()`, `get_sentiment_summary()`, `get_sentiment_strength()`; mock headline pool as fallback
- Depends on: requests (NewsAPI), OpenAI (GPT-4o-mini for sentiment scoring); cached 10-min
- Used by: `agent/trading_agent.py` inside the `get_news` tool handler

**Currency Converter:**
- Purpose: Convert XAUUSD (USD/troy oz) to Thai Baht per baht-weight at 96.5% purity
- Location: `gold-agent/converter/thai.py`
- Contains: `convert_to_thb()`, `fetch_live_usd_thb_rate()`; constants: `TROY_OZ_TO_GRAMS=31.1035`, `GRAMS_PER_BAHT_WEIGHT=15.244`, `THAI_GOLD_PURITY=0.965`
- Depends on: requests (open.er-api.com for live USD/THB); env fallback `USD_THB_RATE=34.5`
- Used by: `ui/dashboard.py`, `backtest.py`

**ReAct Trading Agent:**
- Purpose: GPT-4o-mini agent that calls get_price → get_indicators → get_news then outputs BUY/SELL/HOLD JSON
- Location: `gold-agent/agent/trading_agent.py`
- Contains: `run_agent()`, TOOLS list (3 functions), `_execute_tool()`, `_validate_decision()`, `_parse_json_with_retry()`
- Depends on: OpenAI client, all data/indicators/news/knowledge modules (imported inside tool executor)
- Used by: `ui/dashboard.py` (`run_full_analysis()`), `backtest.py`

**Daily Market Agent:**
- Purpose: Once-per-day macro bias agent; cached result injected into `get_indicators` tool response
- Location: `gold-agent/agent/daily_market_agent.py`
- Contains: `get_daily_market()`; 1-day TTL cache; storage: MongoDB or `data/daily_market.json`
- Depends on: OpenAI, `data/fetch.py`, `news/sentiment.py`
- Used by: `agent/trading_agent.py` (called inside `get_indicators` tool handler)

**Risk Metrics:**
- Purpose: Sharpe, Sortino, Max Drawdown, Kelly Criterion, Half-Kelly, Expected Value
- Location: `gold-agent/risk/metrics.py`
- Contains: `calculate_sharpe()`, `calculate_sortino()`, `calculate_max_drawdown()`, `calculate_kelly()`, `calculate_risk()`
- Depends on: pandas, numpy
- Used by: `ui/dashboard.py`

**Paper Trading Engine:**
- Purpose: Long-only paper portfolio; manages open position, closed trades, equity history
- Location: `gold-agent/trader/paper_engine.py`
- Contains: `open_position()`, `close_position()`, `get_portfolio_summary()`, `check_auto_exits()`; confidence-scaled position sizing; TP/SL/trailing-stop logic
- Depends on: `data/portfolio.json` (dev) or MongoDB `portfolio` collection (prod)
- Used by: `ui/dashboard.py` (`run_full_analysis()`)

**Trade Scheduler:**
- Purpose: Defines trade windows and per-window quota (Mon-Fri: 6 trades/day; Sat-Sun: 2 trades/day)
- Location: `gold-agent/trader/trade_scheduler.py`
- Contains: `is_in_trade_window()`, `get_quota_pressure()`, window definitions in Thai time (UTC+7)
- Depends on: `data/scheduler_state.json`
- Used by: `ui/dashboard.py` (`run_full_analysis()`)

**Knowledge Graph:**
- Purpose: LightRAG-backed vector + graph store; accumulates news headlines over time; queried for historical gold context
- Location: `gold-agent/knowledge/lightrag_store.py`
- Contains: `insert_headlines()`, `query_gold_context()`; seed file `knowledge/gold_knowledge.txt`
- Depends on: lightrag-hku, sentence-transformers (all-MiniLM-L6-v2), Claude Haiku (entity extraction), `data/lightrag/` directory
- Used by: `agent/trading_agent.py` inside the `get_news` tool handler

**Logger:**
- Purpose: Record every analysis run; track cumulative LLM API costs
- Location: `gold-agent/logger/trade_log.py`, `gold-agent/logger/cost_tracker.py`
- Contains: `append_log()`, `get_log_df()`; `track_usage()`, `get_cost_summary()`
- Depends on: CSV files or MongoDB `trade_log` collection; `data/llm_costs.json`
- Used by: `ui/dashboard.py`

**Gradio Dashboard (UI):**
- Purpose: PNS-style dark trading dashboard; orchestrates the full analysis pipeline
- Location: `gold-agent/ui/dashboard.py`
- Contains: `run_full_analysis()` (pipeline coordinator), `build_ui()`, chart builders, HTML component renderers
- Depends on: all other modules; Gradio ≥4.15, matplotlib
- Entry point for browser interaction

---

## Data Flow

**Live Trading Pipeline (every 30 min when in active window):**

1. `main.py` background thread → calls `run_full_analysis(trade_mode=True/False)` in `ui/dashboard.py`
2. `run_full_analysis()` calls `data.fetch.get_gold_price()` → 90-day OHLCV DataFrame
3. `run_full_analysis()` calls `data.fetch.get_hsh_price()` → live Hua Seng Heng THB price
4. `run_full_analysis()` calls `agent/trading_agent.run_agent()` → ReAct loop starts
5. **ReAct loop:** GPT-4o-mini calls `get_price` tool → `get_indicators` tool → `get_news` tool (each feeds deterministic data back to LLM)
6. Inside `get_indicators`: calls `agent/daily_market_agent.get_daily_market()` (cached), `news/sentiment.get_sentiment_strength()`, `data.fetch.get_macro_indicators()` (DXY, VIX), `data.fetch.get_gold_price_intraday()` (H1 MTF)
7. Inside `get_news`: calls `knowledge/lightrag_store.insert_headlines()` + `query_gold_context()`
8. GPT-4o-mini outputs JSON `{decision, confidence, reasoning, key_factors, risk_note}`
9. `_validate_decision()` applies safety bounds (auto-HOLD below 40% confidence, bad decisions sanitized)
10. `run_full_analysis()` checks `trader/trade_scheduler.is_in_trade_window()` and quota
11. If Trade Mode ON + in window + quota unmet + confidence ≥65%: `trader/paper_engine` executes BUY or SELL
12. `logger/trade_log.append_log()` records the decision
13. `logger/cost_tracker.track_usage()` records token costs
14. Dashboard UI components refresh with new data

**Backtest Pipeline:**

1. `backtest.py` fetches historical OHLCV (yfinance GC=F, 1h candles, 60 days)
2. Iterates candle-by-candle from index 20 (BB warmup) up to `BACKTEST_MAX_CANDLES`
3. For each candle: patches `data.fetch.get_gold_price()` via `unittest.mock` to return the historical slice
4. Calls `agent/trading_agent.run_agent()` → same full ReAct loop
5. Applies same paper engine constants (TP, SL, trailing stop, confidence gate, sizing)
6. Writes per-candle results to `data/backtest_log.csv` and trade records to `data/backtest_trades.csv`

**State Management:**

- **Portfolio state:** `data/portfolio.json` (dev) or MongoDB `portfolio` collection (prod). Schema: `{initial_balance, balance, open_position, closed_trades, equity_history}`
- **Daily market cache:** `data/daily_market.json` (dev) or MongoDB `daily_market` collection (prod). TTL: 1 day.
- **UI state:** `data/ui_state.json` — persists `trade_mode` and `refresh_mode` across page reloads
- **Scheduler state:** `data/scheduler_state.json` — tracks per-window trade counts across days
- **LLM cost tracking:** `data/llm_costs.json` — cumulative token counts and USD/THB costs
- **Knowledge graph:** `data/lightrag/` — LightRAG KV store + graph files (persisted)
- **Analysis log:** `data/analysis_log.csv` (dev) or MongoDB `trade_log` collection — append-only

---

## Key Abstractions

**ReAct Tool Interface:**
- Purpose: Defines the contract between GPT-4o-mini and the deterministic math layer
- Pattern: OpenAI function-calling schema; 3 tools: `get_price`, `get_indicators`, `get_news`
- Each tool executor pre-computes all values; LLM receives structured JSON state
- File: `gold-agent/agent/trading_agent.py` (TOOLS list + `_execute_tool()`)

**Safety Bounds Validator:**
- Purpose: Post-LLM output validation; ensures decision is BUY/SELL/HOLD, confidence in [0,100], auto-HOLD at <40%
- Pattern: Execution router — LLM output passes through validator before any trade action
- File: `gold-agent/agent/trading_agent.py` (`_validate_decision()`)

**Dual Storage Abstraction:**
- Purpose: Transparent fallback from MongoDB Atlas to local JSON/CSV
- Pattern: Each module calls `os.getenv("MONGODB_URI")` — if set, uses MongoDB; otherwise uses file
- Modules: `trader/paper_engine.py`, `agent/daily_market_agent.py`, `logger/trade_log.py`

**Confidence Gate:**
- Purpose: Hard threshold preventing low-conviction trades
- Value: 65% minimum confidence to execute any BUY or SELL
- Implemented in: `trader/paper_engine.py` (`CONF_THRESHOLD = 65`)
- Also enforced in: `ui/dashboard.py` before calling `open_position()` / `close_position()`

**Confidence-Scaled Position Sizing:**
- Purpose: Higher conviction = larger bet; prevents oversizing on weak signals
- Scale: 65-74% → 60% of balance; 75-84% → 80%; 85%+ → 95%
- File: `gold-agent/trader/paper_engine.py` (`_size_pct_by_confidence()`)

---

## Entry Points

**Primary (Gradio dashboard):**
- Location: `gold-agent/main.py`
- Triggers: `python main.py` or `python ui/dashboard.py`
- Responsibilities: Environment check, CLI pipeline test, start background scheduler thread (`threading.Thread`), launch Gradio on port 7860

**Backtest:**
- Location: `gold-agent/backtest.py`
- Triggers: `python backtest.py` from `gold-agent/` directory
- Responsibilities: Historical candle replay, mock data patching, CSV output

**Agent-only test:**
- Location: `gold-agent/agent/trading_agent.py` (`__main__`)
- Triggers: `python agent/trading_agent.py`
- Responsibilities: Single ReAct run, print trace to stdout

---

## Error Handling

**Strategy:** Each layer fails silently with a safe default; the pipeline continues with degraded data

**Patterns:**
- `data/fetch.py`: returns empty DataFrame on yfinance failure
- `agent/trading_agent.py`: returns `{decision: "HOLD", confidence: 0}` on API error; JSON retry with trailing-comma strip; max_iterations=8 guard against infinite loops
- `news/sentiment.py`: falls back to mock headline pool if NewsAPI key missing; sentiment cached 10 min to avoid duplicate API calls
- `converter/thai.py`: falls back to `USD_THB_RATE` env var if live rate fetch fails
- `knowledge/lightrag_store.py`: skips insert if same headlines seen (hash dedup); runs in single-threaded executor to avoid asyncio conflicts with Gradio
- `trader/paper_engine.py`: skips trade if balance below `MIN_TRADE_THB=1000 THB`; applies loss cooldown (skip 1 cycle after a loss)
- All modules: `try/except Exception` with `print()` logging; non-critical failures do not propagate

---

## Cross-Cutting Concerns

**Logging:** `print()` statements with `[module_name]` prefix prefix (e.g., `[trading_agent.py]`, `[fetch.py]`). No structured logging framework. Analysis decisions additionally recorded in `logger/trade_log.py`.

**Thai Time:** All timestamps in UTC+7 (`timezone(timedelta(hours=7))`). No pytz dependency — uses stdlib `datetime.timezone`.

**Monetary Display:** UI always shows THB. Internal calculations in USD. Conversion applied in `converter/thai.py` and `ui/dashboard.py`.

**Authentication:** All secrets in `.env` file: `OPENAI_API_KEY`, `NEWS_API_KEY`, `TRADE_LOG_API_KEY`, `MONGODB_URI`. Loaded via `python-dotenv` in each module.

**DEV_MODE flag:** `gold-agent/ui/dashboard.py` line 46: `DEV_MODE: bool = False`. When False, hides reset/clear/backtest controls in production. Set to True for local dev.
