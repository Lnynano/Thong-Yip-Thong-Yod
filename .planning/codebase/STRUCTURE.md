# STRUCTURE
Generated: 2026-04-17
Focus: arch

---

## Repository Root

```
Gold_Agent/                         # repo root
├── gold-agent/                     # PRIMARY application (all active code lives here)
│   ├── agent/                      # AI decision-making layer
│   │   ├── claude_agent.py         # Legacy shim — forwards to trading_agent.py
│   │   ├── trading_agent.py        # Active ReAct loop, tool calling, analysis pipeline
│   │   └── daily_market_agent.py   # Daily macro bias agent (cached once/day)
│   ├── backtest.py                 # Historical agent replay against OHLCV data
│   ├── converter/
│   │   └── thai.py                 # USD → THB conversion, baht-weight calculation
│   ├── data/
│   │   ├── fetch.py                # yfinance OHLCV + live price fetch
│   │   ├── portfolio.json          # Live paper trading state (do not edit directly)
│   │   ├── llm_costs.json          # Persistent LLM API cost tracking
│   │   ├── ui_state.json           # UI state persistence (trade mode toggle, etc.)
│   │   ├── daily_market.json       # Cached daily macro bias output
│   │   ├── analysis_log.csv        # Analysis decisions (duplicate of logger/)
│   │   ├── backtest_log.csv        # Per-candle backtest decisions
│   │   ├── backtest_trades.csv     # Backtest completed trade records
│   │   └── lightrag/               # LightRAG knowledge graph data files
│   │       ├── graph_chunk_entity_relation.graphml
│   │       ├── kv_store_*.json     # Key-value stores (docs, entities, relations, cache)
│   │       └── vdb_*.json          # Vector databases (chunks, entities, relationships)
│   ├── indicators/
│   │   └── tech.py                 # RSI (Wilder), MACD, Bollinger Bands, confluence score, market regime
│   ├── knowledge/
│   │   ├── lightrag_store.py       # LightRAG wrapper — insert headlines, query context
│   │   └── gold_knowledge.txt      # Static gold market domain knowledge seed
│   ├── logger/
│   │   ├── cost_tracker.py         # LLM API cost accumulation and JSON persistence
│   │   ├── trade_log.py            # CSV trade analysis log (append/read/clear)
│   │   └── analysis_log.csv        # CSV log written by trade_log.py
│   ├── main.py                     # Alternative entry point (not primary)
│   ├── news/
│   │   └── sentiment.py            # NewsAPI headlines → GPT sentiment (BULLISH/BEARISH/NEUTRAL)
│   ├── requirements.txt            # Python dependencies (no version pins)
│   ├── risk/
│   │   └── metrics.py              # Sharpe, Sortino, Max Drawdown, Kelly, Half-Kelly, EV
│   ├── tests/                      # Pytest test suite (61 tests)
│   │   ├── test_paper_engine.py
│   │   ├── test_confluence_regime.py
│   │   ├── test_sentiment.py
│   │   ├── test_lightrag_store.py
│   │   ├── test_agent_news_tool.py
│   │   └── test_pl_card.py
│   ├── trader/
│   │   ├── paper_engine.py         # Long-only paper trading engine, state in portfolio.json
│   │   └── trade_scheduler.py      # Trading window scheduler and quota enforcement
│   ├── ui/
│   │   └── dashboard.py            # PRIMARY ENTRY POINT — Gradio dark dashboard
│   ├── .env                        # API keys (gitignored in theory)
│   └── .env.example                # Environment variable template
│
├── generate_report.py              # Standalone report generator (not dashboard-integrated)
├── render.yaml                     # Render.com deployment config
├── CLAUDE.md                       # Project instructions for AI assistants
├── README.md
├── LICENSE
│
├── dashboard/                      # ABANDONED — old dashboard attempt
│   ├── dashboard/
│   └── trading/
├── core/                           # EMPTY — abandoned restructure
├── llm/                            # EMPTY — abandoned module
│
├── docs/
│   └── superpowers/
│       ├── plans/                  # Historical implementation plans
│       └── specs/                  # Historical design specs
│
├── tests/                          # Root-level test directory (separate pytest scope)
│   └── test_dashboard_charts.py
│
└── .planning/
    └── codebase/                   # This codebase map
```

---

## Entry Points

| Entry Point | Purpose |
|---|---|
| `gold-agent/ui/dashboard.py` | **Primary.** Run with `python ui/dashboard.py`. Starts Gradio on port 7860. |
| `gold-agent/backtest.py` | Run with `python backtest.py`. Replays agent against historical OHLCV data. |
| `gold-agent/main.py` | Alternative CLI entry point (less used). |
| `generate_report.py` | Standalone report generator (repo root, not integrated). |

---

## Key Data Files

| File | Format | Purpose | Mutate via |
|---|---|---|---|
| `data/portfolio.json` | JSON | Paper trading state (balance, position, trade history) | `paper_engine.py` methods only |
| `data/llm_costs.json` | JSON | Cumulative LLM API costs by model | `logger/cost_tracker.py` |
| `data/ui_state.json` | JSON | UI toggle states (trade mode on/off) | `ui/dashboard.py` |
| `data/daily_market.json` | JSON | Cached daily macro bias (refreshed once/day) | `daily_market_agent.py` |
| `logger/analysis_log.csv` | CSV | Append-only analysis decision history | `logger/trade_log.py` |
| `data/backtest_log.csv` | CSV | Per-candle backtest analysis log | `backtest.py` |
| `data/backtest_trades.csv` | CSV | Completed backtest trade records | `backtest.py` |
| `data/lightrag/` | Various | LightRAG knowledge graph persistence | `knowledge/lightrag_store.py` |
| `knowledge/gold_knowledge.txt` | Plain text | Static seed knowledge (inserted once on init) | Manual only |

---

## Configuration Files

| File | Purpose |
|---|---|
| `gold-agent/.env` | Runtime secrets (OPENAI_API_KEY, NEWS_API_KEY, etc.) |
| `gold-agent/.env.example` | Template for .env setup |
| `render.yaml` | Render.com deployment configuration |
| `CLAUDE.md` | AI assistant instructions and architecture constraints |
| `gold-agent/AGENTS.md` | Agent-specific instructions |

---

## Module Import Path Notes

- All imports are relative to `gold-agent/` as the working directory
- Tests use `sys.path.insert(0, ...)` to resolve parent package
- `agent/claude_agent.py` is a shim — actual logic is in `trading_agent.py`
- The `dashboard/`, `core/`, and `llm/` directories at repo root are inactive remnants

---

## Where to Place New Code

| Type of code | Location |
|---|---|
| New technical indicator | `gold-agent/indicators/tech.py` |
| New data source / fetch | `gold-agent/data/fetch.py` |
| New agent tool | `gold-agent/agent/trading_agent.py` → `_execute_tool()` |
| New risk metric | `gold-agent/risk/metrics.py` |
| New UI panel/tab | `gold-agent/ui/dashboard.py` |
| New test | `gold-agent/tests/test_<module>.py` |
| New persistent data | `gold-agent/data/<name>.json` or `.csv` |
