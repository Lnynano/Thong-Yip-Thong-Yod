# Bounty Hunter Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 Bounty Hunter-inspired features to the Gold Agent dashboard: confluence score, conviction badge, market regime, win/loss filter, shareable P&L card, signal detail expansion, and multi-timeframe analysis.

**Architecture:** Features 1–6 are additive changes to `indicators/tech.py` and `ui/dashboard.py` that extend existing HTML helpers and `run_full_analysis()`. Feature 7 adds intraday data fetching to `data/fetch.py` and pipes it into the Claude agent's `get_indicators` tool response. No new modules are created.

**Tech Stack:** Python 3.10+, Gradio ≥4.15, matplotlib, pandas, yfinance, PIL (Pillow)

---

## File Map

| File | Change |
|------|--------|
| `gold-agent/indicators/tech.py` | Add `calculate_confluence_score()`, `calculate_market_regime()` |
| `gold-agent/data/fetch.py` | Add `get_gold_price_intraday()` |
| `gold-agent/agent/claude_agent.py` | Extend `get_indicators` tool handler to include H1 context |
| `gold-agent/ui/dashboard.py` | Update `_decision_html()`, `_trade_table_html()`, `run_full_analysis()`, `build_ui()`, add `_build_pl_card()` |
| `gold-agent/tests/test_confluence_regime.py` | New — tests for confluence score and market regime |
| `gold-agent/tests/test_pl_card.py` | New — tests for PNG card generation |

---

## Task 1: Confluence Score and Market Regime (indicators/tech.py)

**Files:**
- Modify: `gold-agent/indicators/tech.py`
- Create: `gold-agent/tests/test_confluence_regime.py`

### Step 1.1: Write failing tests

- [ ] Create `gold-agent/tests/test_confluence_regime.py`:

```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import numpy as np
from indicators.tech import calculate_confluence_score, calculate_market_regime


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Helper: build minimal OHLCV DataFrame from close prices."""
    n = len(closes)
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c * 1.005 for c in closes],
        "Low":    [c * 0.995 for c in closes],
        "Close":  closes,
        "Volume": [100000] * n,
    })


def test_confluence_score_neutral():
    """Mid-range closes should produce a score near 5.0."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score = calculate_confluence_score(df, "NEUTRAL")
    assert 0.0 <= score <= 10.0, f"Score out of range: {score}"


def test_confluence_score_bullish_news_raises():
    """BULLISH sentiment should produce higher score than NEUTRAL."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score_neutral = calculate_confluence_score(df, "NEUTRAL")
    score_bullish = calculate_confluence_score(df, "BULLISH")
    assert score_bullish > score_neutral


def test_confluence_score_bearish_news_lowers():
    """BEARISH sentiment should produce lower score than NEUTRAL."""
    closes = [3000.0] * 60
    df = _make_df(closes)
    score_neutral = calculate_confluence_score(df, "NEUTRAL")
    score_bearish = calculate_confluence_score(df, "BEARISH")
    assert score_bearish < score_neutral


def test_confluence_score_range():
    """Score must always be 0–10 regardless of inputs."""
    closes_rising = [2800.0 + i * 10 for i in range(60)]
    closes_falling = [3400.0 - i * 10 for i in range(60)]
    for closes, sentiment in [
        (closes_rising, "BULLISH"),
        (closes_falling, "BEARISH"),
        (closes_rising, "BEARISH"),
    ]:
        score = calculate_confluence_score(_make_df(closes), sentiment)
        assert 0.0 <= score <= 10.0, f"Score {score} out of range"


def test_market_regime_returns_valid_label():
    """Market regime must be one of the four valid labels."""
    closes = [3000.0 + i * 5 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime in ("TRENDING UP", "TRENDING DOWN", "RANGING", "VOLATILE")


def test_market_regime_uptrend():
    """Strongly rising prices should produce TRENDING UP."""
    closes = [2800.0 + i * 15 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime == "TRENDING UP"


def test_market_regime_downtrend():
    """Strongly falling prices should produce TRENDING DOWN."""
    closes = [3700.0 - i * 15 for i in range(60)]
    df = _make_df(closes)
    regime = calculate_market_regime(df)
    assert regime == "TRENDING DOWN"
```

- [ ] Run to confirm failure:
```bash
cd gold-agent && pytest tests/test_confluence_regime.py -v
```
Expected: `ImportError` — functions not yet defined.

### Step 1.2: Implement `calculate_confluence_score` and `calculate_market_regime`

- [ ] Append to `gold-agent/indicators/tech.py` (after `get_signal_summary`):

```python
# ─────────────────────────────────────────────────────────────
# Confluence Score  (0–10 scale for UI display)
# ─────────────────────────────────────────────────────────────
def calculate_confluence_score(df: pd.DataFrame, news_sentiment: str = "NEUTRAL") -> float:
    """
    Combine RSI, MACD, Bollinger Bands, and news sentiment into a single
    0–10 confluence score.

    Scoring:
      RSI < 30  (oversold)   : +2   |  RSI > 70 (overbought): -2
      RSI < 40               : +1   |  RSI > 60             : -1
      MACD histogram > 0     : +1.5 |  histogram < 0        : -1.5
      BB %B < 0.30           : +1.5 |  %B > 0.70            : -1.5
      News BULLISH           : +1.5 |  News BEARISH          : -1.5

    Raw range: [-6.5, +6.5]  → mapped linearly to [0, 10].

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column (≥30 rows).
        news_sentiment (str): "BULLISH", "BEARISH", or "NEUTRAL".

    Returns:
        float: Score from 0.0 (extremely bearish) to 10.0 (extremely bullish).
    """
    try:
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)

        raw = 0.0

        # RSI component
        if rsi < 30:
            raw += 2.0
        elif rsi < 40:
            raw += 1.0
        elif rsi > 70:
            raw -= 2.0
        elif rsi > 60:
            raw -= 1.0

        # MACD component
        if macd["histogram"] > 0:
            raw += 1.5
        else:
            raw -= 1.5

        # Bollinger Bands %B component
        if bb["percent_b"] < 0.30:
            raw += 1.5
        elif bb["percent_b"] > 0.70:
            raw -= 1.5

        # News sentiment component
        if news_sentiment == "BULLISH":
            raw += 1.5
        elif news_sentiment == "BEARISH":
            raw -= 1.5

        # Map [-6.5, +6.5] → [0, 10]
        score = (raw + 6.5) / 13.0 * 10.0
        score = max(0.0, min(10.0, score))
        return round(score, 1)

    except Exception as e:
        print(f"[tech.py] Error calculating confluence score: {e}")
        return 5.0


# ─────────────────────────────────────────────────────────────
# Market Regime Detection
# ─────────────────────────────────────────────────────────────
def calculate_market_regime(df: pd.DataFrame) -> str:
    """
    Classify the current market regime from price action.

    Rules (evaluated in order):
      1. VOLATILE    : BB bandwidth > 0.04  (high volatility squeeze breakout)
      2. TRENDING UP : MACD histogram > 0 AND price > SMA20
      3. TRENDING DOWN: MACD histogram < 0 AND price < SMA20
      4. RANGING     : everything else

    Args:
        df (pd.DataFrame): DataFrame with a 'Close' column (≥20 rows).

    Returns:
        str: "TRENDING UP", "TRENDING DOWN", "RANGING", or "VOLATILE"
    """
    try:
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)

        close = df["Close"]
        sma20 = float(close.rolling(20).mean().iloc[-1])
        current_price = float(close.iloc[-1])

        bandwidth = bb["bandwidth"]

        if bandwidth > 0.04:
            return "VOLATILE"
        if macd["histogram"] > 0 and current_price > sma20:
            return "TRENDING UP"
        if macd["histogram"] < 0 and current_price < sma20:
            return "TRENDING DOWN"
        return "RANGING"

    except Exception as e:
        print(f"[tech.py] Error calculating market regime: {e}")
        return "RANGING"
```

### Step 1.3: Run tests to confirm they pass

- [ ] Run:
```bash
cd gold-agent && pytest tests/test_confluence_regime.py -v
```
Expected: All 7 tests PASS.

### Step 1.4: Commit

```bash
cd gold-agent
git add indicators/tech.py tests/test_confluence_regime.py
git commit -m "feat(indicators): add confluence score and market regime detection"
```

---

## Task 2: Signal Detail Expansion + Conviction Badge (_decision_html)

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — `_decision_html()` function (lines 307–347)

### Step 2.1: Update `_decision_html` signature and body

- [ ] Replace the existing `_decision_html` function in `gold-agent/ui/dashboard.py`:

```python
def _decision_html(decision: str, confidence: int, reasoning: str,
                   trade_mode: bool = False,
                   key_factors: list | None = None,
                   risk_note: str = "",
                   confluence: float = 5.0,
                   regime: str = "RANGING",
                   bb_lower: float = 0.0,
                   bb_upper: float = 0.0,
                   current_price_thb: float = 0.0) -> str:
    """BUY/SELL/HOLD card with conviction badge, confluence score,
    market regime, signal detail (SL/TP/key factors), and reasoning."""
    cfg = {
        "BUY":  ("#c9f002", "📈"),
        "SELL": ("#cc3333", "📉"),
        "HOLD": ("#555555", "⏸"),
    }
    color, icon = cfg.get(decision.upper(), ("#555", "?"))
    if not trade_mode and decision.upper() in ("BUY", "SELL"):
        color = "#666666"

    # Conviction badge
    if confidence >= 80:
        conviction = "HIGH"
        conv_color = "#c9f002"
    elif confidence >= 60:
        conviction = "MEDIUM"
        conv_color = "#f0a002"
    else:
        conviction = "LOW"
        conv_color = "#cc3333"

    # Regime color
    regime_colors = {
        "TRENDING UP":   "#c9f002",
        "TRENDING DOWN": "#cc3333",
        "VOLATILE":      "#f0a002",
        "RANGING":       "#555555",
    }
    regime_color = regime_colors.get(regime, "#555555")

    # Confluence bar (filled blocks)
    filled = int(round(confluence))
    conf_bar = "█" * filled + "░" * (10 - filled)
    conf_color = "#c9f002" if confluence >= 6 else "#f0a002" if confluence >= 4 else "#cc3333"

    lines = "".join(
        f'<div style="margin:3px 0; color:#888; font-size:0.88em;">{l}</div>'
        for l in reasoning.split("\n") if l.strip()
    )

    trade_tag = (
        '<span style="color:#c9f002; font-size:0.72em; letter-spacing:0.1em; '
        'border:1px solid #2a4400; padding:2px 8px; border-radius:3px; '
        'background:#0d1a00;">WILL TRADE</span>'
        if trade_mode and decision.upper() in ("BUY", "SELL") and confidence >= 65
        else
        '<span style="color:#444; font-size:0.72em; letter-spacing:0.1em; '
        'border:1px solid #222; padding:2px 8px; border-radius:3px;">ANALYSIS ONLY</span>'
    )

    # Key factors list
    factors_html = ""
    if key_factors:
        items = "".join(
            f'<div style="color:#666; font-size:0.82em; margin:2px 0;">▸ {f}</div>'
            for f in key_factors[:4]
        )
        factors_html = f"""
      <div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e1e1e;">
        <div style="color:#444; font-size:0.68em; letter-spacing:0.1em; margin-bottom:6px;">KEY FACTORS</div>
        {items}
      </div>"""

    # Risk note
    risk_html = ""
    if risk_note and risk_note.strip():
        risk_html = f"""
      <div style="margin-top:8px; color:#555; font-size:0.8em;">
        ⚠ {risk_note}
      </div>"""

    # SL / TP suggestion from Bollinger Bands
    sltp_html = ""
    if current_price_thb > 0 and bb_lower > 0 and bb_upper > 0:
        if decision.upper() == "BUY":
            sl_thb = bb_lower
            tp_thb = bb_upper
        elif decision.upper() == "SELL":
            sl_thb = bb_upper
            tp_thb = bb_lower
        else:
            sl_thb = tp_thb = 0.0

        if sl_thb > 0 and tp_thb > 0:
            sltp_html = f"""
      <div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e1e1e;
                  display:flex; gap:24px; flex-wrap:wrap;">
        <div>
          <div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">ENTRY ZONE</div>
          <div style="color:#aaa; font-size:0.9em;">฿{current_price_thb:,.0f}</div>
        </div>
        <div>
          <div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">SL (BB BAND)</div>
          <div style="color:#cc3333; font-size:0.9em;">฿{sl_thb:,.0f}</div>
        </div>
        <div>
          <div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">TP (BB BAND)</div>
          <div style="color:#c9f002; font-size:0.9em;">฿{tp_thb:,.0f}</div>
        </div>
      </div>"""

    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:10px;">
    AGENT RECOMMENDATION
  </div>
  <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
    <span style="color:{color}; font-size:2.8em; font-weight:900;
                 letter-spacing:6px;">{icon} {decision.upper()}</span>
    <div>
      <div style="color:{color}; font-size:1em;">Confidence: {confidence}%</div>
      <div style="color:{conv_color}; font-size:0.75em; letter-spacing:0.12em; font-weight:700;">
        CONVICTION: {conviction}
      </div>
    </div>
    {trade_tag}
  </div>

  <div style="margin-top:12px; display:flex; gap:24px; flex-wrap:wrap; align-items:center;">
    <div>
      <div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">CONFLUENCE</div>
      <div style="color:{conf_color}; font-size:0.82em; font-family:'Courier New',monospace;">
        {conf_bar}  {confluence:.1f}/10
      </div>
    </div>
    <div>
      <div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">MARKET REGIME</div>
      <div style="color:{regime_color}; font-size:0.82em; font-weight:700;">{regime}</div>
    </div>
  </div>

  {sltp_html}

  <div style="margin-top:14px; border-top:1px solid #1e1e1e; padding-top:12px;">
    {lines}
  </div>
  {factors_html}
  {risk_html}
</div>"""
```

### Step 2.2: Verify visually — no automated test needed for HTML output

- [ ] Run the dashboard manually:
```bash
cd gold-agent && python ui/dashboard.py
```
Open `http://localhost:7860` and confirm the decision card shows CONVICTION badge, CONFLUENCE bar, and REGIME label. (You can abort with Ctrl+C after checking.)

### Step 2.3: Commit

```bash
cd gold-agent
git add ui/dashboard.py
git commit -m "feat(ui): add conviction badge, confluence bar, regime label, and SL/TP to decision card"
```

---

## Task 3: Wire Confluence + Regime into `run_full_analysis`

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — `run_full_analysis()` and `_error_outputs()`

### Step 3.1: Update `run_full_analysis` to compute and pass new values

- [ ] In `run_full_analysis()`, replace the existing **step 3 (Indicators)** block (currently lines 548–556) with:

```python
        # 3. Indicators
        from indicators.tech import (calculate_rsi, calculate_macd,
                                     calculate_bollinger_bands,
                                     calculate_confluence_score,
                                     calculate_market_regime)
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)
        rsi_signal  = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
        macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"
        rsi_str  = f"{rsi:.1f}  —  {rsi_signal}"
        macd_str = f"{macd['histogram']:+.2f}  —  {macd_signal}"
        indicators_str = f"RSI {rsi:.1f} {rsi_signal}  ·  MACD {macd['histogram']:+.3f} {macd_signal}"
        regime = calculate_market_regime(df)
        # sentiment known after step 4 — placeholder until then
        _bb_lower_thb = 0.0
        _bb_upper_thb = 0.0
```

- [ ] After the news block (step 4) and THB conversion (step 5), add confluence computation. Replace the line:
```python
        dec_block    = _decision_html(decision, confidence, reasoning, trade_mode)
```
with:
```python
        # Convert BB bands to THB for SL/TP display
        _bb_lower_thb = bb["lower"] * rate * 0.965 / 31.1035 * 96.5
        _bb_upper_thb = bb["upper"] * rate * 0.965 / 31.1035 * 96.5
        # Simpler: scale from USD using the same ratio as thb_now/price_usd
        thb_per_usd_oz = thb_now / price_usd if price_usd > 0 else 0.0
        _bb_lower_thb = round(bb["lower"] * thb_per_usd_oz, 0)
        _bb_upper_thb = round(bb["upper"] * thb_per_usd_oz, 0)

        confluence = calculate_confluence_score(df, sentiment)

        dec_block = _decision_html(
            decision, confidence, reasoning, trade_mode,
            key_factors=agent.get("key_factors", []),
            risk_note=agent.get("risk_note", ""),
            confluence=confluence,
            regime=regime,
            bb_lower=_bb_lower_thb,
            bb_upper=_bb_upper_thb,
            current_price_thb=thb_now,
        )
```

### Step 3.2: Update `_error_outputs` to pass default values to `_decision_html`

- [ ] In `_error_outputs()`, replace:
```python
        _decision_html("HOLD", 0, msg, trade_mode),
```
with:
```python
        _decision_html("HOLD", 0, msg, trade_mode,
                       key_factors=[], risk_note="",
                       confluence=5.0, regime="RANGING",
                       bb_lower=0.0, bb_upper=0.0, current_price_thb=0.0),
```

### Step 3.3: Smoke test

- [ ] Run:
```bash
cd gold-agent && python -c "
from ui.dashboard import run_full_analysis
result = run_full_analysis(False)
print('Output count:', len(result))
print('Decision HTML snippet:', result[1][:200])
"
```
Expected: Output count: 16, Decision HTML contains "CONFLUENCE" and "CONVICTION".

### Step 3.4: Commit

```bash
cd gold-agent
git add ui/dashboard.py
git commit -m "feat(ui): wire confluence score and market regime into run_full_analysis"
```

---

## Task 4: Win/Loss Filter on Trade Journal

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — `_trade_table_html()`, `build_ui()`

### Step 4.1: Add filter parameter to `_trade_table_html`

- [ ] Replace the `_trade_table_html` signature line:
```python
def _trade_table_html(trades: list, open_position: dict | None = None) -> str:
```
with:
```python
def _trade_table_html(trades: list, open_position: dict | None = None,
                      filter_mode: str = "ALL") -> str:
```

- [ ] Add filtering logic at the start of the function body, right after the docstring / before `rows = ""`:

```python
    # Apply win/loss filter (open position row always shown regardless of filter)
    if filter_mode == "WIN":
        trades = [t for t in trades if t.get("outcome") == "WIN"]
    elif filter_mode == "LOSS":
        trades = [t for t in trades if t.get("outcome") == "LOSS"]
```

### Step 4.2: Add filter radio to the Trades tab in `build_ui()`

- [ ] In `build_ui()`, find the `with gr.Tab("Trades"):` block and replace it:

```python
            with gr.Tab("Trades"):
                trade_filter = gr.Radio(
                    choices=["ALL", "WIN", "LOSS"],
                    value="ALL",
                    label="FILTER",
                    interactive=True,
                )
                outcome_bar = gr.HTML()
                trade_table = gr.HTML()
```

- [ ] After the `reset_btn.click(...)` wiring, add the filter wiring. The filter button calls a lightweight function that reads current portfolio state and re-renders:

```python
        def _filter_trades(filter_mode: str):
            from trader.paper_engine import get_trade_history, get_portfolio_summary
            trades = get_trade_history(20)
            portfolio = get_portfolio_summary(0)
            return _trade_table_html(trades, portfolio.get("open_position"), filter_mode)

        trade_filter.change(
            fn=_filter_trades,
            inputs=[trade_filter],
            outputs=[trade_table],
        )
```

- [ ] Also update the `_reset` function inside `build_ui` to pass filter_mode="ALL":
```python
        def _reset():
            from trader.paper_engine import reset_portfolio, get_portfolio_summary, \
                                            get_trade_history, get_equity_history, get_recent_outcomes
            reset_portfolio()
            p = get_portfolio_summary(0)
            try:
                eq = _build_equity_chart(get_equity_history())
            except Exception:
                eq = None
            return (_portfolio_html(p), eq,
                    _outcome_bar_html(get_recent_outcomes(15)),
                    _trade_table_html(get_trade_history(20), p.get("open_position"), "ALL"))
```

### Step 4.3: Smoke test

- [ ] Run:
```bash
cd gold-agent && python -c "
from ui.dashboard import _trade_table_html
fake_trades = [
    {'outcome': 'WIN', 'pnl_thb': 50, 'pnl_pct': 3.5, 'entry_price': 48000,
     'exit_price': 49700, 'size_bw': 0.03, 'exit_time': '2026-01-01 12:00:00'},
    {'outcome': 'LOSS', 'pnl_thb': -30, 'pnl_pct': -2.0, 'entry_price': 49000,
     'exit_price': 48020, 'size_bw': 0.03, 'exit_time': '2026-01-02 12:00:00'},
]
win_html = _trade_table_html(fake_trades, None, 'WIN')
loss_html = _trade_table_html(fake_trades, None, 'LOSS')
assert 'LOSS' not in win_html or 'OPEN' in win_html, 'WIN filter failed'
assert 'WIN' not in loss_html.replace('WILL TRADE', ''), 'LOSS filter failed'
print('Filter test passed')
"
```
Expected: `Filter test passed`.

### Step 4.4: Commit

```bash
cd gold-agent
git add ui/dashboard.py
git commit -m "feat(ui): add WIN/LOSS filter to trade journal"
```

---

## Task 5: Shareable P&L Card PNG

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — add `_build_pl_card()`, update `build_ui()`
- Create: `gold-agent/tests/test_pl_card.py`

### Step 5.1: Write failing test

- [ ] Create `gold-agent/tests/test_pl_card.py`:

```python
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tempfile
from ui.dashboard import _build_pl_card


def test_pl_card_returns_png_path():
    """_build_pl_card must return a path to a real PNG file."""
    portfolio = {
        "total_equity": 1650.0,
        "initial_balance": 1500.0,
        "total_pnl": 150.0,
        "total_pnl_pct": 10.0,
        "win_rate": 66.7,
        "wins": 2,
        "losses": 1,
        "total_trades": 3,
        "rr_ratio": 1.8,
        "realized_pnl": 150.0,
    }
    path = _build_pl_card(portfolio)
    assert path is not None, "Should return a path"
    assert os.path.exists(path), f"File not found: {path}"
    assert path.endswith(".png"), f"Should be PNG: {path}"
    # Check file is non-empty
    assert os.path.getsize(path) > 1000, "PNG file too small (likely corrupt)"


def test_pl_card_negative_pnl():
    """Card should still generate when P&L is negative."""
    portfolio = {
        "total_equity": 1400.0,
        "initial_balance": 1500.0,
        "total_pnl": -100.0,
        "total_pnl_pct": -6.67,
        "win_rate": 33.3,
        "wins": 1,
        "losses": 2,
        "total_trades": 3,
        "rr_ratio": 0.8,
        "realized_pnl": -100.0,
    }
    path = _build_pl_card(portfolio)
    assert path is not None
    assert os.path.exists(path)
```

- [ ] Run to confirm failure:
```bash
cd gold-agent && pytest tests/test_pl_card.py -v
```
Expected: `ImportError` — `_build_pl_card` not yet defined.

### Step 5.2: Implement `_build_pl_card`

- [ ] Add to `gold-agent/ui/dashboard.py`, after `_build_equity_chart`:

```python
def _build_pl_card(portfolio: dict) -> str | None:
    """
    Generate a branded PNG P&L performance card for social sharing.

    Creates a dark PNS-styled card showing: total P&L, win rate, trades,
    R:R ratio, and a Thong Yip Thong Yod branding footer.

    Args:
        portfolio: dict from get_portfolio_summary()

    Returns:
        str: Absolute path to the generated PNG file, or None on failure.
    """
    import tempfile

    try:
        BG      = "#0b0b0b"
        ACCENT  = "#c9f002"
        RED     = "#cc3333"
        GRAY    = "#555555"
        LGRAY   = "#888888"

        pnl       = portfolio.get("total_pnl", 0.0)
        pnl_pct   = portfolio.get("total_pnl_pct", 0.0)
        win_rate  = portfolio.get("win_rate", 0.0)
        wins      = portfolio.get("wins", 0)
        losses    = portfolio.get("losses", 0)
        trades    = portfolio.get("total_trades", 0)
        rr        = portfolio.get("rr_ratio", 0.0)
        equity    = portfolio.get("total_equity", 0.0)
        pnl_color = ACCENT if pnl >= 0 else RED
        sign      = "+" if pnl >= 0 else ""

        fig, ax = plt.subplots(figsize=(7, 3.5), facecolor=BG)
        ax.set_facecolor(BG)
        ax.axis("off")

        # Border
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.patch.set_linewidth(2)

        # Title
        ax.text(0.04, 0.92, "🥇 THONG YIP THONG YOD",
                transform=ax.transAxes, color=GRAY,
                fontsize=10, fontfamily="monospace",
                fontweight="bold", va="top", letter_spacing=0.1)
        ax.text(0.04, 0.80, "PAPER TRADING  ·  XAUUSD",
                transform=ax.transAxes, color="#333",
                fontsize=7, fontfamily="monospace", va="top")

        # P&L — large
        ax.text(0.04, 0.60,
                f"{sign}฿{pnl:,.2f}  ({sign}{pnl_pct:.2f}%)",
                transform=ax.transAxes, color=pnl_color,
                fontsize=22, fontfamily="monospace",
                fontweight="black", va="top")

        ax.text(0.04, 0.35, "TOTAL P&L",
                transform=ax.transAxes, color=GRAY,
                fontsize=7, fontfamily="monospace", va="top")

        # Stats row
        stats = [
            ("WIN RATE",  f"{win_rate:.1f}%"),
            ("W / L",     f"{wins} / {losses}"),
            ("TRADES",    str(trades)),
            ("R:R",       f"{rr:.2f}:1" if rr > 0 else "—"),
            ("EQUITY",    f"฿{equity:,.0f}"),
        ]
        x = 0.04
        for label, val in stats:
            ax.text(x, 0.18, label, transform=ax.transAxes,
                    color=GRAY, fontsize=6.5, fontfamily="monospace", va="top")
            ax.text(x, 0.10, val, transform=ax.transAxes,
                    color="#cccccc", fontsize=9, fontfamily="monospace",
                    fontweight="bold", va="top")
            x += 0.19

        # Bottom accent line
        ax.axhline(y=0.03, xmin=0.04, xmax=0.96,
                   color=ACCENT, linewidth=1.5, transform=ax.transAxes)

        plt.tight_layout(pad=0.4)

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".png", delete=False,
            prefix="tytyd_pl_card_"
        )
        fig.savefig(tmp.name, dpi=150, bbox_inches="tight",
                    facecolor=BG, edgecolor="none")
        plt.close(fig)
        return tmp.name

    except Exception as e:
        print(f"[dashboard] P&L card generation failed: {e}")
        return None
```

### Step 5.3: Add download button to Portfolio tab

- [ ] In `build_ui()`, find the `with gr.Tab("Portfolio"):` block and add after `equity_chart = gr.Plot(...)`:

```python
                with gr.Row():
                    share_btn = gr.Button("📤  SHARE P&L CARD",
                                          variant="secondary", scale=1, size="sm")
                    pl_card_file = gr.File(label="Download P&L Card", visible=False)
```

- [ ] Wire the share button (add after reset_btn.click wiring):

```python
        def _generate_pl_card():
            from trader.paper_engine import get_portfolio_summary
            portfolio = get_portfolio_summary(0)
            path = _build_pl_card(portfolio)
            if path:
                return gr.File(value=path, visible=True)
            return gr.File(visible=False)

        share_btn.click(
            fn=_generate_pl_card,
            inputs=[],
            outputs=[pl_card_file],
        )
```

### Step 5.4: Run tests

- [ ] Run:
```bash
cd gold-agent && pytest tests/test_pl_card.py -v
```
Expected: Both tests PASS.

### Step 5.5: Commit

```bash
cd gold-agent
git add ui/dashboard.py tests/test_pl_card.py
git commit -m "feat(ui): add shareable P&L card PNG generation and download button"
```

---

## Task 6: Multi-Timeframe Analysis H1 (data/fetch.py + claude_agent.py)

**Files:**
- Modify: `gold-agent/data/fetch.py`
- Modify: `gold-agent/agent/claude_agent.py` — `_execute_tool` → `get_indicators` handler

### Step 6.1: Add `get_gold_price_intraday` to fetch.py

- [ ] Append to `gold-agent/data/fetch.py`:

```python
def get_gold_price_intraday(interval: str = "1h", days: int = 5) -> pd.DataFrame:
    """
    Fetch recent intraday XAUUSD data for multi-timeframe analysis.

    Args:
        interval: yfinance interval string — "1h" or "15m". Default "1h".
        days: Number of calendar days to look back. Default 5.

    Returns:
        pd.DataFrame: OHLCV DataFrame indexed by datetime, or empty on failure.
    """
    try:
        from datetime import datetime, timedelta
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=days)

        ticker = yf.Ticker("GC=F")
        df = ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=interval,
        )

        if df.empty:
            print(f"[fetch.py] Intraday ({interval}): No data returned.")
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)
        print(f"[fetch.py] Intraday ({interval}): {len(df)} bars fetched.")
        return df

    except Exception as e:
        print(f"[fetch.py] Error fetching intraday ({interval}): {e}")
        return pd.DataFrame()
```

### Step 6.2: Extend `get_indicators` tool handler in claude_agent.py

- [ ] In `_execute_tool()`, find the `elif tool_name == "get_indicators":` block and replace just the `result = {...}` construction and `return` (keeping all the calculation code above it):

```python
            # Multi-timeframe: H1 context
            h1_context = {}
            try:
                from data.fetch import get_gold_price_intraday
                from indicators.tech import calculate_rsi, calculate_macd
                df_h1 = get_gold_price_intraday(interval="1h", days=5)
                if not df_h1.empty and len(df_h1) >= 15:
                    h1_rsi   = calculate_rsi(df_h1, period=14)
                    h1_macd  = calculate_macd(df_h1)
                    h1_trend = "BULLISH" if h1_macd["histogram"] > 0 else "BEARISH"
                    h1_rsi_sig = ("OVERBOUGHT" if h1_rsi > 70
                                  else "OVERSOLD" if h1_rsi < 30
                                  else "NEUTRAL")
                    h1_context = {
                        "interval": "H1",
                        "bars": len(df_h1),
                        "rsi": round(h1_rsi, 2),
                        "rsi_signal": h1_rsi_sig,
                        "macd_histogram": h1_macd["histogram"],
                        "trend": h1_trend,
                        "note": "H1 RSI and MACD for intraday momentum confirmation",
                    }
            except Exception as e:
                print(f"[claude_agent.py] H1 MTF fetch failed (non-critical): {e}")

            # Structured state
            result = {
                "note": "All values are pre-computed deterministically. Do NOT recalculate.",
                "timeframe": "D1 (primary)",
                "rsi": {
                    "value"  : rsi,
                    "signal" : rsi_signal,
                    "period" : 14,
                    "interpretation": f"RSI={rsi:.1f} ({rsi_signal})",
                },
                "macd": {
                    "macd_line" : macd["macd"],
                    "signal_line": macd["signal"],
                    "histogram" : macd["histogram"],
                    "trend"     : macd_signal,
                    "params"    : "EMA12 - EMA26, Signal=EMA9",
                    "interpretation": f"Histogram={macd['histogram']:.4f} ({macd_signal})",
                },
                "bollinger_bands": {
                    "upper"     : bb["upper"],
                    "middle"    : bb["middle"],
                    "lower"     : bb["lower"],
                    "percent_b" : bb["percent_b"],
                    "bandwidth" : bb["bandwidth"],
                    "signal"    : bb["signal"],
                    "interpretation": f"%B={bb['percent_b']:.2f} ({bb['signal']})",
                },
            }
            if h1_context:
                result["h1_intraday"] = h1_context
                result["mtf_note"] = (
                    "H1 and D1 aligned = stronger signal. "
                    "H1 and D1 diverging = wait for confirmation."
                )
            return json.dumps(result)
```

### Step 6.3: Smoke test MTF

- [ ] Run:
```bash
cd gold-agent && python -c "
from data.fetch import get_gold_price_intraday
df = get_gold_price_intraday('1h', 5)
print('H1 bars:', len(df))
print(df.tail(3))
"
```
Expected: prints H1 bar count (typically 20–30 bars for 5 calendar days).

### Step 6.4: Commit

```bash
cd gold-agent
git add data/fetch.py agent/claude_agent.py
git commit -m "feat(agent): add multi-timeframe H1 analysis to get_indicators tool"
```

---

## Self-Review

**Spec coverage check:**
- [x] Feature 1 — Confluence Score: Task 1 + Task 3
- [x] Feature 2 — Conviction Badge: Task 2 (`_decision_html`)
- [x] Feature 3 — Market Regime: Task 1 + Task 2 + Task 3
- [x] Feature 4 — Win/Loss Filter: Task 4
- [x] Feature 5 — Shareable P&L Card: Task 5
- [x] Feature 6 — Signal Detail Expansion (key factors, risk note, SL/TP): Task 2
- [x] Feature 7 — Multi-Timeframe Analysis: Task 6

**Placeholder scan:** No TBDs or "implement later" present.

**Type consistency:**
- `calculate_confluence_score(df, news_sentiment)` → used in Task 3 with same signature ✓
- `calculate_market_regime(df)` → used in Task 3 with same signature ✓
- `_decision_html(decision, confidence, reasoning, trade_mode, key_factors, risk_note, confluence, regime, bb_lower, bb_upper, current_price_thb)` → called in Task 3 and `_error_outputs` Task 3.2 ✓
- `_trade_table_html(trades, open_position, filter_mode)` → called in Task 4 filter function and reset ✓
- `_build_pl_card(portfolio)` → tested in Task 5.1 and called in Task 5.3 ✓
- `get_gold_price_intraday(interval, days)` → used in Task 6.2 ✓
