# STACK.md
Generated: 2026-04-17
Focus: tech

## Languages

**Primary:**
- Python 3.13.7 - All application code (agents, indicators, UI, data pipeline)

**Secondary:**
- None (pure Python project)

## Runtime

**Environment:**
- CPython 3.13.7 (system runtime on Windows 11 dev, Linux on Render)

**Package Manager:**
- pip (standard)
- Lockfile: Not present — `requirements.txt` pins no versions except `gradio>=4.15.0`
- Virtual environment: `.venv/` present in `gold-agent/` (not committed)

## Frameworks

**Core UI:**
- Gradio 6.9.0 — Gradio dashboard served at `http://localhost:7860`. Entry via `gold-agent/ui/dashboard.py`. Uses `gr.Timer`, `gr.Blocks`, tab layout.

**LLM / AI:**
- openai 2.6.1 — Chat completions (`gpt-4o-mini`, `temperature=0`). Used in `gold-agent/agent/trading_agent.py`, `gold-agent/agent/daily_market_agent.py`, `gold-agent/news/sentiment.py`, and via LightRAG in `gold-agent/knowledge/lightrag_store.py`.
- lightrag-hku 1.4.12 — Knowledge graph RAG engine. Manages entity extraction + vector storage in `gold-agent/data/lightrag/`. Initialized in `gold-agent/knowledge/lightrag_store.py`.
- sentence-transformers 5.3.0 — Local embedding model `all-MiniLM-L6-v2` (384-dim). Used exclusively inside LightRAG for embedding documents. No network calls for embeddings.

**Testing:**
- pytest 9.0.2 — Test runner. Config: implicit (no `pytest.ini` or `pyproject.toml`). Run from `gold-agent/` root.
- unittest.mock — Used extensively for patching `_load`/`_save` in paper engine tests.

**Build/Dev:**
- No build step — plain Python scripts
- `python-dotenv` 1.2.1 — `.env` loading via `load_dotenv()` called at the top of each module

## Key Dependencies

**Critical:**
- `openai` 2.6.1 — All LLM inference (trading decisions, news sentiment, daily market agent, LightRAG extraction). Everything breaks without a valid `OPENAI_API_KEY`.
- `gradio` 6.9.0 — Entire UI layer. `gold-agent/ui/dashboard.py` is 900+ lines of `gr.Blocks` layout.
- `yfinance` 1.2.0 — OHLCV data source. Ticker `GC=F` (COMEX Gold Futures). Used in `gold-agent/data/fetch.py` and `gold-agent/backtest.py`.

**Data & Analysis:**
- `pandas` 2.3.3 — DataFrame backbone for OHLCV data, trade logs, CSV I/O. Used across nearly all modules.
- `numpy` 2.4.3 — Numerical arrays for RSI/MACD/Bollinger computations in `gold-agent/indicators/tech.py`. Also used for embedding arrays in `gold-agent/knowledge/lightrag_store.py`.
- `matplotlib` 3.10.8 — Chart rendering (backend `Agg`). Produces 90-day price + RSI overlays in `gold-agent/ui/dashboard.py`.

**Infrastructure:**
- `requests` 2.32.5 — HTTP calls to NewsAPI, open.er-api.com (forex), Hua Seng Heng price API, and the professor's GoldTrade Logs API.
- `pymongo` 3.12.0 — MongoDB Atlas client. Optional; auto-detected at runtime via `MONGODB_URI`. Used in `gold-agent/trader/paper_engine.py`, `gold-agent/logger/trade_log.py`, `gold-agent/agent/daily_market_agent.py`.
- `dnspython` — Required by pymongo for SRV connection strings (Atlas).
- `python-dotenv` 1.2.1 — Environment variable loading from `gold-agent/.env`.

## Configuration

**Environment:**
- Loaded from `gold-agent/.env` via `python-dotenv` at module import time
- Template: `gold-agent/.env.example`
- Key required vars: `OPENAI_API_KEY`, `TRADE_LOG_API_KEY`, `NEWS_API_KEY`, `MONGODB_URI`
- Key optional vars: `USD_THB_RATE` (default `34.5`), `TRADE_LOOP_INTERVAL_SEC` (default `300`), `TRADE_FEE_PCT` (default `0.005`), `TRADE_FEE_FLAT_THB` (default `0`), `COMPETITION_BUDGET_THB` (default `1500`)

**Build:**
- No build config. `requirements.txt` at `gold-agent/requirements.txt`.
- Deploy config: `render.yaml` at project root (Render.com web service).

## Platform Requirements

**Development:**
- Python 3.10+ (type hints, union syntax used throughout)
- pip + virtualenv recommended
- Windows 11 (dev machine confirmed) or Linux

**Production:**
- Render.com (free tier web service, Python runtime)
- Build: `pip install -r gold-agent/requirements.txt`
- Start: `cd gold-agent && python main.py`
- Health check path: `/`
- Note: Render free tier sleeps after 15 min inactivity; background scheduler thread keeps trading alive independently of HTTP requests.

---

*Stack analysis: 2026-04-17*
