# SKILL: Gold Trading Signal Analysis

## Metadata
- **Name:** trading-signal-analysis
- **Triggers:** "analyze signal", "why did it BUY", "explain decision", "backtest config", "run backtest", "check indicators"
- **Description:** Modular skill for analyzing, explaining, and improving gold trading signals

---

## What This Skill Does

When activated, this skill gives the AI agent specific procedural knowledge about:
1. How to read and explain a trading signal decision
2. How to run a backtest with custom indicator config
3. How to interpret backtest results and find the best config

Without this skill, the agent would have to figure out the project structure from scratch every time. With it, it loads only this focused knowledge — saving tokens and improving accuracy.

---

## Skill 1: Explain a Trading Signal

**Trigger:** User asks "why did the agent BUY/SELL/HOLD?"

**Procedure:**
1. Read `data/backtest_log.csv` — find the candle row in question
2. Check `decision`, `confidence`, `reasoning` columns
3. Cross-reference with indicator values at that time (RSI, MACD, BB)
4. Check if `quota_pressure` or `failsafe_pressure` was active (may have forced a trade)
5. Explain in plain language

**Key files:**
- `data/backtest_log.csv` — per-candle decisions
- `data/backtest_trades.csv` — completed trades with entry/exit
- `agent/trading_agent.py` — SYSTEM_PROMPT shows exact rules used

---

## Skill 2: Run Backtest with Custom Config

**Trigger:** User asks to backtest with specific indicators on/off

**Procedure:**
1. Edit `backtest.py` line ~632: `run_backtest(config={...})`
2. Available flags (all default `True`):
   - `use_macd` — MACD histogram + crossover signals
   - `use_bb` — Bollinger Bands %B signals
   - `use_news` — News sentiment scoring
   - `use_dxy_vix` — DXY/VIX macro signals
   - `use_h1_mtf` — H1 multi-timeframe analysis
   - `use_daily_bias` — Daily trend bias from daily agent
   - `use_volume_spike` — Volume spike detection
3. Run: `cd gold-agent && python backtest.py`
4. First run fetches and caches price data. Subsequent runs reuse cache for fair comparison.
5. Check header — confirms which flags are ON/OFF

**Example:**
```python
run_backtest(config={
    "use_macd": True,
    "use_bb": True,
    "use_news": False,   # disable news
    "use_dxy_vix": True,
    "use_h1_mtf": False, # disable multi-timeframe
    "use_daily_bias": True,
    "use_volume_spike": True,
})
```

---

## Skill 3: Interpret Backtest Results

**Trigger:** User shares backtest output and asks what it means

**Key metrics to focus on:**
| Metric | What it means |
|---|---|
| Win Rate | % of trades that were profitable |
| R:R Ratio | Avg win ÷ Avg loss — above 1.0 is good |
| Agent Alpha | Agent return minus Buy-and-Hold return — positive means agent beats passive |
| Days met quota | How many days hit the min 2 trades/window requirement |
| Total fees | Cost of trading — subtract from P&L for real profit |

**Spread reminder:** Every trade starts -200 THB from the HSH buy-sell spread. Real profit = backtest P&L minus spread costs.

---

## Architecture Context

```
gold-agent/
├── agent/trading_agent.py   ← GPT-4o-mini ReAct loop, SYSTEM_PROMPT, indicator config flags
├── backtest.py              ← Replay historical candles through the agent
├── trader/trade_scheduler.py← Trading windows (M-F: 06-12, 12-18, 18-02 / Sat-Sun: 09:30-17:30)
├── notifier/discord_notify.py← Discord @everyone alert on BUY/SELL signals
├── data/fetch.py            ← yfinance OHLCV + HSH live price (sell/buy/spread)
└── logger/trade_log.py      ← Professor's API + CSV + MongoDB logging
```

---

## Spread Rule (Critical)
HSH gold has ~200 THB buy-sell spread. The agent is instructed (SYSTEM_PROMPT constraint #6):
- Only BUY if expected price rise exceeds the spread
- HOLD if market is flat or uncertain
- This rule prevents trading into guaranteed losses
