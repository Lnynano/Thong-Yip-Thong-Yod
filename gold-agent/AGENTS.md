# AGENTS.md — Gold Trading Agent

## Project
- **Name**: Gold Trading Agent
- **Stack**: Python 3.10+, Claude API (claude-sonnet-4-20250514), Gradio, yfinance
- **Purpose**: Analyze XAUUSD gold prices and give BUY/SELL/HOLD recommendations

## Architecture
- **Deterministic**: `data/`, `indicators/`, `converter/`, `risk/` — pure Python math
- **Stochastic**: `agent/claude_agent.py` — only place where AI reasoning occurs
- Entry point: `main.py` → launches Gradio on port 7860

## Module Responsibilities
| Module | Role |
|--------|------|
| `data/fetch.py` | yfinance XAUUSD OHLCV fetcher |
| `indicators/tech.py` | RSI, MACD, Bollinger Bands |
| `news/sentiment.py` | NewsAPI + sentiment |
| `converter/thai.py` | XAUUSD → THB at 96.5% purity |
| `agent/claude_agent.py` | Claude ReAct loop |
| `risk/metrics.py` | Sharpe, Sortino, MDD, Kelly, EV |
| `ui/dashboard.py` | Gradio production dashboard |

## Key Design Rules
- NEVER ask the LLM to calculate RSI/MACD — pre-compute all math
- Use structured markdown tables for state, not free-form prose
- Always run safety bounds validation after LLM output
- Use Half-Kelly (f*/2) for position sizing with LLM agents
- Use temperature=0 and top_p=0.1 for tool calling
- Implement JSON retry logic and hard max_iterations guard
- Thai gold is 96.5% pure — always apply purity factor

## Thai Gold Conversion
```
1 troy oz    = 31.1035 grams
1 baht-weight = 15.244 grams
Thai purity   = 96.5%
Effective gold per baht-weight = 15.244 × 0.965 = 14.710 grams
```

## ReAct Trajectory
```
τ = (s₀, t₁, a₁, o₁, t₂, a₂, o₂, ..., aₙ, oₙ)
s₀: market state injected via structured prompt
t₁: Claude thinks about what tool to call
a₁: Claude calls get_price → get_indicators → get_news
oₙ: tool results fed back as observations
final: Claude outputs JSON { decision, confidence, reasoning, key_factors, risk_note }
```

## Testing
```bash
python data/fetch.py          # Test price fetcher
python indicators/tech.py     # Test RSI + MACD + Bollinger Bands
python news/sentiment.py      # Test news (mock if no API key)
python converter/thai.py      # Test THB conversion with 96.5% purity
python risk/metrics.py        # Test Sharpe + Sortino + MDD + Kelly + Half-Kelly + EV
python agent/claude_agent.py  # Test full ReAct agent (needs ANTHROPIC_API_KEY)
python main.py                # Launch full Gradio app on http://localhost:7860
```

## Environment Variables (.env)
```
ANTHROPIC_API_KEY=sk-ant-...   # Required for Claude agent
NEWS_API_KEY=...               # Optional (mock headlines if missing)
USD_THB_RATE=34.5              # Update daily for accurate THB pricing
```

## Forbidden
- Never modify `TROY_OZ_TO_GRAMS` or `GRAMS_PER_BAHT_WEIGHT` constants
- Never ask Claude to perform arithmetic (pre-compute everything)
- Never skip safety bounds validation in `agent/claude_agent.py`
- Never use temperature > 0 for tool calling
