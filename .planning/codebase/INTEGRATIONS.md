# INTEGRATIONS.md
Generated: 2026-04-17
Focus: tech

## APIs & External Services

**LLM / AI Inference:**
- OpenAI GPT-4o-mini — Primary trading decision engine, news sentiment scoring, daily market analysis, and LightRAG entity extraction
  - SDK/Client: `openai` 2.6.1 (`from openai import OpenAI`)
  - Auth: `OPENAI_API_KEY` env var
  - `temperature=0`, deterministic output — do not change
  - Used in: `gold-agent/agent/trading_agent.py`, `gold-agent/agent/daily_market_agent.py`, `gold-agent/news/sentiment.py`, `gold-agent/knowledge/lightrag_store.py`

**Market Data:**
- Yahoo Finance (yfinance) — 90-day OHLCV data, COMEX Gold Futures ticker `GC=F`
  - SDK/Client: `yfinance` 1.2.0
  - Auth: None (no API key required)
  - Used in: `gold-agent/data/fetch.py`, `gold-agent/backtest.py`
  - Interval: 1-day candles for live; 1-hour candles for backtest (falls back to daily)

- Hua Seng Heng Gold Price API — Live Thai gold shop prices (competition official source)
  - Endpoint: `https://apicheckpricev3.huasengheng.com` (fetched in `gold-agent/data/fetch.py`)
  - Auth: None (public API)
  - Used in: `gold-agent/data/fetch.py` via `get_hsh_price()`

**News:**
- NewsAPI — Live gold-related news headlines
  - Endpoint: `https://newsapi.org`
  - SDK/Client: `requests` (direct HTTP)
  - Auth: `NEWS_API_KEY` env var
  - Fallback: rotating mock headline pool in `gold-agent/news/sentiment.py` when key is absent or request fails
  - Used in: `gold-agent/news/sentiment.py`

**Forex:**
- open.er-api.com — Live USD/THB exchange rate
  - Endpoint: `https://open.er-api.com/v6/latest/USD`
  - Auth: None (free, no key required)
  - Fallback: `USD_THB_RATE` env var (default `34.5`)
  - Used in: `gold-agent/converter/thai.py`

**Competition Logging:**
- GoldTrade Logs API (professor's server) — Submits every BUY/SELL/HOLD signal to the Thammasat University competition server
  - Endpoint: `https://goldtrade-logs-api.poonnatuch.workers.dev/logs`
  - Auth: `Authorization: Bearer <TRADE_LOG_API_KEY>` header
  - Method: POST, JSON payload `{action, price, reason, confidence, signal_source}`
  - Failure mode: prints warning, returns `{"error": "..."}` — non-blocking
  - Used in: `gold-agent/logger/trade_log.py`

## Data Storage

**Databases:**
- MongoDB Atlas (optional) — Persistent storage for portfolio state, trade logs, and daily market cache across Render deploys
  - Connection: `MONGODB_URI` env var (Atlas SRV format)
  - Client: `pymongo` 3.12.0 (lazy init, only when `MONGODB_URI` is set)
  - Collections: `trade_log`, `portfolio`, `daily_market`
  - Auto-detection: each module calls `os.getenv("MONGODB_URI")` at runtime; falls back to local files if unset
  - Used in: `gold-agent/trader/paper_engine.py`, `gold-agent/logger/trade_log.py`, `gold-agent/agent/daily_market_agent.py`

**Local File Fallback (dev mode / no MongoDB):**
- `gold-agent/data/portfolio.json` — Paper trading portfolio state (balance, open position, closed trades, equity history)
- `gold-agent/data/analysis_log.csv` — CSV trade/analysis history (append-only)
- `gold-agent/data/daily_market.json` — Daily macro market bias cache (TTL: 1 day)
- `gold-agent/data/llm_costs.json` — Cumulative LLM token usage and cost tracking
- `gold-agent/data/backtest_log.csv` — Candle-by-candle backtest results
- `gold-agent/data/backtest_trades.csv` — Individual backtest trade records
- `gold-agent/data/ui_state.json` — UI toggle persistence (trade mode, refresh mode)

**Vector/Graph Storage:**
- LightRAG local graph — Knowledge graph built from accumulated news headlines + static gold domain knowledge
  - Location: `gold-agent/data/lightrag/` (persisted to disk, not MongoDB)
  - Embeddings: local `all-MiniLM-L6-v2` model via `sentence-transformers` (no network)
  - LLM extraction: GPT-4o-mini via OpenAI API
  - Seed file: `gold-agent/knowledge/gold_knowledge.txt`
  - Managed by: `gold-agent/knowledge/lightrag_store.py`

**File Storage:**
- Local filesystem only (no S3/GCS/Azure Blob)

**Caching:**
- In-memory sentiment cache: 10-minute TTL keyed by headline hash (`gold-agent/news/sentiment.py`)
- Daily market agent cache: 1-day TTL to MongoDB or local JSON (`gold-agent/agent/daily_market_agent.py`)
- LightRAG dedup guard: tracks last-inserted headline hash to skip duplicate inserts

## Authentication & Identity

**Auth Provider:**
- No user authentication. Single-user local/deployed dashboard. No login, no sessions.
- API key authentication only — keys stored in `.env`, never exposed in UI.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)

**Cost Tracking:**
- Custom LLM cost tracker: `gold-agent/logger/cost_tracker.py`
  - Tracks token usage per call, cumulative USD and THB cost
  - Persisted to `gold-agent/data/llm_costs.json`
  - Budget: `COMPETITION_BUDGET_THB` env var (default `1500` THB)
  - GPT-4o-mini pricing: $0.150/1M input tokens, $0.600/1M output tokens

**Logs:**
- `print()` statements throughout all modules (no structured logging framework)
- Analysis history: CSV or MongoDB via `gold-agent/logger/trade_log.py`

## CI/CD & Deployment

**Hosting:**
- Render.com (free tier web service)
- Config: `render.yaml` at project root
- Build command: `pip install -r gold-agent/requirements.txt`
- Start command: `cd gold-agent && python main.py`

**CI Pipeline:**
- None (no GitHub Actions, CircleCI, etc.)

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` — OpenAI API access (all LLM calls fail without this)
- `TRADE_LOG_API_KEY` — Competition server logging (skipped with warning if absent)
- `NEWS_API_KEY` — Live headlines (falls back to mock pool if absent)
- `MONGODB_URI` — Atlas connection string (falls back to local JSON/CSV if absent)

**Optional env vars:**
- `USD_THB_RATE` — Fallback forex rate, default `34.5`
- `TRADE_LOOP_INTERVAL_SEC` — Background scheduler interval, default `300` (5 min)
- `TRADE_FEE_PCT` — Trade fee percentage, default `0.005` (0.5%)
- `TRADE_FEE_FLAT_THB` — Flat fee per trade in THB, default `0`
- `COMPETITION_BUDGET_THB` — Budget for cost tracking, default `1500`
- `BACKTEST_MAX_CANDLES` — Cap candles in backtest run, default `50`
- `DEV_MODE` — Controlled via hardcoded flag in `gold-agent/ui/dashboard.py` (not env var); set `DEV_MODE = True` to show developer controls

**Secrets location:**
- `gold-agent/.env` (gitignored)
- Template: `gold-agent/.env.example` (committed, safe — no real values)
- On Render: injected as service environment variables via `render.yaml` `envVars` block

## Webhooks & Callbacks

**Incoming:**
- None (no webhooks received from external services)

**Outgoing:**
- GoldTrade Logs API: POST to `https://goldtrade-logs-api.poonnatuch.workers.dev/logs` on every agent decision (BUY/SELL/HOLD). Fire-and-forget, errors are logged but non-blocking.

---

*Integration audit: 2026-04-17*
