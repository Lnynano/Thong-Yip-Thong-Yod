# Thong Yip Thong Yod — AI Gold Trading Agent

AI-powered gold trading dashboard built for Thammasat University Data Science project (CN240).
Fetches live XAUUSD prices, runs technical analysis, asks GPT-4o-mini for BUY/SELL/HOLD, and executes paper trades automatically via a Gradio dashboard.

---

## Quick Start

```bash
# 1. Install dependencies
cd gold-agent
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY and NEWS_API_KEY

# 3. Run
python main.py
# Dashboard opens at http://localhost:7860
```

---

## Architecture

```
gold-agent/
├── agent/
│   ├── trading_agent.py      ← Main ReAct agent (GPT-4o-mini, runs every 30 min)
│   └── daily_market_agent.py ← Daily macro context agent (runs once/day, cached)
│
├── data/fetch.py             ← yfinance XAUUSD OHLCV + intraday prices
├── indicators/tech.py        ← RSI (Wilder), MACD, Bollinger Bands
├── news/sentiment.py         ← NewsAPI headlines + GPT-4o-mini sentiment scoring
├── converter/thai.py         ← XAUUSD → THB/baht-weight (96.5% Thai gold purity)
├── risk/metrics.py           ← Sharpe, Sortino, Max Drawdown, Kelly, EV
├── trader/
│   ├── paper_engine.py       ← Long-only paper trading, state in portfolio.json
│   └── trade_scheduler.py    ← Trade window & quota tracker (6/day weekday, 2/day weekend)
├── knowledge/
│   ├── lightrag_store.py     ← LightRAG knowledge graph (accumulates news over time)
│   └── gold_knowledge.txt    ← Static gold market domain knowledge seed
├── logger/trade_log.py       ← CSV analysis log (append-only)
├── ui/dashboard.py           ← Gradio dark dashboard
├── backtest.py               ← Walk-forward historical replay
└── main.py                   ← Entry point
```

### Multi-Agent Flow

```
daily_market_agent  ──(once/day)──► macro bias (Uptrend/Downtrend/Sideways)
                                            │
                                            ▼
trading_agent  ──► get_price ──► get_indicators (includes DXY + macro bias) ──► get_news ──► BUY/SELL/HOLD
                                            │
                                            ▼
                                    paper_engine  ──► portfolio.json
```

---

## Environment Variables

Copy `gold-agent/.env.example` to `gold-agent/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | GPT-4o-mini for trading decisions |
| `NEWS_API_KEY` | No | Live gold news headlines (mock headlines used if missing) |
| `USD_THB_RATE` | No | Fallback USD/THB rate if live fetch fails (default: 34.5) |
| `MONGODB_URI` | No | MongoDB Atlas for cloud state (local JSON files used if missing) |

---

## Key Design Decisions

| Decision | Value | Reason |
|---|---|---|
| Model | `gpt-4o-mini` | Cheapest capable model — LLM costs come from the ฿1,500 budget |
| Confidence gate | 65% | Must be ≥65% confident to trigger a trade |
| Trade mode | OFF by default | User must consciously toggle ON |
| Temperature | 0 | Deterministic decisions |
| RSI smoothing | Wilder (SMMA) | Correct implementation, not simple EMA |
| Position sizing | Long-only, 95% of balance | No short selling |
| Thai gold purity | 96.5% (0.965) | Gold Traders Association of Thailand standard |

---

## Trade Schedule

| Day | Windows | Trades |
|---|---|---|
| Mon–Fri | 00:00–02:00 + 06:00–11:59 | 2 |
| Mon–Fri | 12:00–17:59 | 2 |
| Mon–Fri | 18:00–23:59 | 2 |
| Sat–Sun | 09:30–17:30 | 2 |

---

## Running Tests

```bash
cd gold-agent
pytest

# Or specific modules
pytest tests/test_paper_engine.py
pytest tests/test_sentiment.py
```

---

## Backtest

Replays real historical GC=F data candle-by-candle through the live agent pipeline.

```bash
cd gold-agent
python backtest.py

# Control number of candles (default 50) to manage API costs
BACKTEST_MAX_CANDLES=20 python backtest.py
```

---

## Generate PDF Report

```bash
cd ..  # root of repo
pip install reportlab
python generate_report.py
# Output: Thong_Yip_Thong_Yod_Report.pdf
```

---

## Tech Stack

- **Python 3.10+**
- **OpenAI API** (GPT-4o-mini) — trading decisions + sentiment
- **Gradio ≥4.15** — dashboard UI
- **yfinance** — XAUUSD price data
- **LightRAG** — knowledge graph for accumulating market context
- **MongoDB Atlas** (optional) — cloud state persistence

---

## Project Context

- **University:** Thammasat University — Data Science (CN240)
- **Team:** Team 3
- **Competition:** Multiple teams compete with the same ฿1,500 capital — highest profit wins
- **Trading period:** April 21–27, 2026 via Hua Seng Heng ออมทอง app
