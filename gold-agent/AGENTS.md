# AGENTS.md — Gold Trading Agent

## Project
- **Name**: Thong Yip Thong Yod — Gold Trading Agent
- **Stack**: Python 3.10+, OpenAI API (gpt-4o-mini), Gradio, yfinance
- **Purpose**: Analyze XAUUSD gold prices and give BUY/SELL/HOLD recommendations

## Agents
| Agent | Model | Runs | Role |
|---|---|---|---|
| `agent/trading_agent.py` | gpt-4o-mini | Every 30 min (in active window) | Main ReAct agent — price + indicators + news → decision |
| `agent/daily_market_agent.py` | gpt-4o-mini | Once per day (cached) | Macro trend agent — 30-day bias injection |

## Architecture
- **Deterministic**: `data/`, `indicators/`, `converter/`, `risk/` — pure Python math
- **Stochastic**: `agent/trading_agent.py` — only place where AI reasoning occurs
- Entry point: `main.py` → launches Gradio on port 7860

## Module Responsibilities
| Module | Role |
|--------|------|
| `data/fetch.py` | yfinance XAUUSD OHLCV fetcher (daily + intraday) |
| `indicators/tech.py` | RSI (Wilder), MACD, Bollinger Bands |
| `news/sentiment.py` | NewsAPI headlines + GPT-4o-mini sentiment |
| `converter/thai.py` | XAUUSD → THB at 96.5% purity |
| `agent/trading_agent.py` | GPT-4o-mini ReAct loop |
| `agent/daily_market_agent.py` | Daily macro context (cached) |
| `risk/metrics.py` | Sharpe, Sortino, MDD, Kelly, EV |
| `trader/paper_engine.py` | Long-only paper trading state |
| `trader/trade_scheduler.py` | Trade window & quota tracking |
| `ui/dashboard.py` | Gradio production dashboard |

## Key Design Rules
- NEVER ask the LLM to calculate RSI/MACD — pre-compute all math
- Use structured markdown tables for state, not free-form prose
- Always run safety bounds validation after LLM output
- Use Half-Kelly (f*/2) for position sizing with LLM agents
- Use temperature=0 for tool calling
- Implement JSON retry logic and hard max_iterations guard
- Thai gold is 96.5% pure — always apply purity factor
- Confidence gate: must be ≥65% to execute a trade

## Thai Gold Conversion
```
1 troy oz     = 31.1035 grams
1 baht-weight = 15.244 grams
Thai purity   = 96.5%
Effective gold per baht-weight = 15.244 × 0.965 = 14.710 grams
```

## ReAct Trajectory
```
τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)
s₀: market state injected via structured prompt
t₁: agent thinks about what tool to call
a₁: agent calls get_price → get_indicators → get_news
oₙ: tool results fed back as observations
final: agent outputs JSON { decision, confidence, reasoning, key_factors, risk_note }
```

## Testing
```bash
cd gold-agent
python data/fetch.py          # Test price fetcher
python indicators/tech.py     # Test RSI + MACD + Bollinger Bands
python news/sentiment.py      # Test news (mock if no API key)
python converter/thai.py      # Test THB conversion with 96.5% purity
python risk/metrics.py        # Test Sharpe + Sortino + MDD + Kelly + Half-Kelly + EV
python agent/trading_agent.py # Test full ReAct agent (needs OPENAI_API_KEY)
python main.py                # Launch full Gradio app on http://localhost:7860
```

## Environment Variables (.env)
```
OPENAI_API_KEY=sk-...         # Required for trading agent
NEWS_API_KEY=...              # Optional (mock headlines if missing)
USD_THB_RATE=34.5             # Update daily for accurate THB pricing
MONGODB_URI=...               # Optional (local JSON files if missing)
```

## Forbidden
- Never modify `TROY_OZ_TO_GRAMS` or `GRAMS_PER_BAHT_WEIGHT` constants
- Never ask the LLM to perform arithmetic (pre-compute everything)
- Never skip safety bounds validation in `agent/trading_agent.py`
- Never use temperature > 0 for tool calling
- Never lower the 65% confidence gate
