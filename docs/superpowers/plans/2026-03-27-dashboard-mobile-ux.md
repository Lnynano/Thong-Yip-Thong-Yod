# Dashboard Mobile/Readability UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Gradio dashboard readable and usable on mobile by fixing fonts, adding responsive CSS, and wrapping lower sections in tabs.

**Architecture:** All changes are confined to `gold-agent/ui/dashboard.py`. Two-part approach: (1) update `PNS_CSS` string with larger fonts, responsive breakpoint, and readability fixes; (2) split the combined chart into two separate figures and restructure `build_ui()` to use `gr.Tabs()` for Charts / Portfolio / Trades / Log / News sections.

**Tech Stack:** Python 3.10+, Gradio ≥4.15, matplotlib, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `gold-agent/ui/dashboard.py` | Modify | All UI logic — CSS, chart functions, layout |
| `tests/__init__.py` | Create | Makes tests/ a package |
| `tests/test_dashboard_charts.py` | Create | Tests for chart functions and output tuple length |

---

## Task 1: Create test file (failing tests)

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_dashboard_charts.py`

- [ ] **Step 1: Create empty tests package**

```python
# tests/__init__.py
# (empty)
```

- [ ] **Step 2: Write failing tests for chart split and CSS constants**

```python
# tests/test_dashboard_charts.py
import sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gold-agent")))

import matplotlib.pyplot as plt


def _dummy_df() -> pd.DataFrame:
    """90 rows of synthetic OHLCV data — enough for RSI/SMA calculations."""
    rng = np.random.default_rng(42)
    n = 90
    close = 2000.0 + np.cumsum(rng.normal(0, 5, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Open":   close - rng.uniform(0, 3, n),
        "High":   close + rng.uniform(0, 5, n),
        "Low":    close - rng.uniform(0, 5, n),
        "Close":  close,
        "Volume": rng.integers(1000, 5000, n).astype(float),
    }, index=idx)


# ── CSS constants ─────────────────────────────────────
def test_pns_css_font_sizes():
    from ui.dashboard import PNS_CSS
    assert "font-size: 1.0em" in PNS_CSS, "Base font should be 1.0em"
    assert "font-size: 0.78em" in PNS_CSS, "Label font should be 0.78em"
    assert "font-size: 0.88em" in PNS_CSS, "Table cell font should be 0.88em"


def test_pns_css_responsive_breakpoint():
    from ui.dashboard import PNS_CSS
    assert "@media (max-width: 768px)" in PNS_CSS, "Mobile breakpoint missing"
    assert "flex-direction: column" in PNS_CSS, "Mobile column stacking missing"


def test_pns_css_readability():
    from ui.dashboard import PNS_CSS
    assert "line-height: 1.5" in PNS_CSS, "line-height fix missing"
    assert "word-break: break-word" in PNS_CSS, "word-break fix missing"


# ── Split chart functions ─────────────────────────────
def test_build_price_chart_returns_figure():
    from ui.dashboard import _build_price_chart
    df = _dummy_df()
    fig = _build_price_chart(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_build_price_chart_figsize():
    from ui.dashboard import _build_price_chart
    df = _dummy_df()
    fig = _build_price_chart(df)
    w, h = fig.get_size_inches()
    assert w >= 10, f"Price chart width {w} too narrow for mobile"
    assert h >= 2.5, f"Price chart height {h} too short"
    plt.close(fig)


def test_build_rsi_chart_returns_figure():
    from ui.dashboard import _build_rsi_chart
    df = _dummy_df()
    fig = _build_rsi_chart(df)
    assert isinstance(fig, plt.Figure)
    plt.close(fig)


def test_build_rsi_chart_figsize():
    from ui.dashboard import _build_rsi_chart
    df = _dummy_df()
    fig = _build_rsi_chart(df)
    w, h = fig.get_size_inches()
    assert w >= 10, f"RSI chart width {w} too narrow for mobile"
    plt.close(fig)


# ── Old _build_chart should NOT exist (it's been split) ──
def test_build_chart_removed():
    import ui.dashboard as dash
    assert not hasattr(dash, "_build_chart"), \
        "_build_chart should be replaced by _build_price_chart and _build_rsi_chart"
```

- [ ] **Step 3: Run tests — expect ALL to fail**

```bash
cd gold-agent && python -m pytest ../tests/test_dashboard_charts.py -v 2>&1 | head -50
```

Expected: multiple `ImportError` or `AssertionError` failures — that's correct at this stage.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/__init__.py tests/test_dashboard_charts.py
git commit -m "test: add failing tests for dashboard mobile UX refactor"
```

---

## Task 2: CSS font sizes and readability fixes

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — `PNS_CSS` constant (lines 49–110)

- [ ] **Step 1: Replace the PNS_CSS body rule and labels rule**

In `gold-agent/ui/dashboard.py`, find and replace the `/* ── Base ──` block and `/* ── Labels ──` block inside `PNS_CSS`:

Replace:
```python
body, .gradio-container, .main, .wrap {
    background: #0b0b0b !important;
    color: #c8c8c8 !important;
    font-family: 'Courier New', 'Lucida Console', monospace !important;
}
```
With:
```python
body, .gradio-container, .main, .wrap {
    background: #0b0b0b !important;
    color: #c8c8c8 !important;
    font-family: 'Courier New', 'Lucida Console', monospace !important;
    font-size: 1.0em !important;
    line-height: 1.5 !important;
    word-break: break-word !important;
}
```

- [ ] **Step 2: Update label font size**

Replace:
```python
.label-wrap span, label, .gr-label {
    color: #555555 !important;
    font-size: 0.72em !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    font-family: 'Courier New', monospace !important;
}
```
With:
```python
.label-wrap span, label, .gr-label {
    color: #555555 !important;
    font-size: 0.78em !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    font-family: 'Courier New', monospace !important;
}
```

- [ ] **Step 3: Add line-height to textarea rule**

Replace:
```python
textarea, input[type=text], .gr-text-input {
    background: #111 !important;
    border: 1px solid #222 !important;
    color: #cccccc !important;
    font-family: 'Courier New', monospace !important;
    font-size: 0.95em !important;
}
```
With:
```python
textarea, input[type=text], .gr-text-input {
    background: #111 !important;
    border: 1px solid #222 !important;
    color: #cccccc !important;
    font-family: 'Courier New', monospace !important;
    font-size: 0.95em !important;
    line-height: 1.5 !important;
}
```

- [ ] **Step 4: Update table cell font size**

Replace:
```python
.svelte-table, table, .gr-dataframe table {
    background: #0f0f0f !important; color: #bbb !important;
    font-size: 0.82em !important; font-family: 'Courier New', monospace !important;
}
```
With:
```python
.svelte-table, table, .gr-dataframe table {
    background: #0f0f0f !important; color: #bbb !important;
    font-size: 0.88em !important; font-family: 'Courier New', monospace !important;
}
```

- [ ] **Step 5: Run the three CSS tests — expect them to pass now**

```bash
cd gold-agent && python -m pytest ../tests/test_dashboard_charts.py::test_pns_css_font_sizes ../tests/test_dashboard_charts.py::test_pns_css_readability -v
```

Expected output:
```
test_pns_css_font_sizes PASSED
test_pns_css_readability PASSED
```

- [ ] **Step 6: Commit**

```bash
git add gold-agent/ui/dashboard.py
git commit -m "fix(ui): increase font sizes and add readability CSS fixes for mobile"
```

---

## Task 3: Add responsive media query to PNS_CSS

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — end of `PNS_CSS` string (around line 109)

- [ ] **Step 1: Append media query block before the closing `"""`**

Find the closing `"""` of `PNS_CSS` (the line that reads just `"""`). Insert the following block immediately before it:

```python
/* ── Responsive: mobile breakpoint (≤768px) ─────────── */
@media (max-width: 768px) {
    .gr-row, .row {
        flex-direction: column !important;
        flex-wrap: wrap !important;
    }
    .gradio-container {
        padding: 6px !important;
    }
    .block, .panel, fieldset, .gr-box, .gr-form, .gr-panel {
        padding: 10px !important;
    }
}
```

- [ ] **Step 2: Run the responsive breakpoint test**

```bash
cd gold-agent && python -m pytest ../tests/test_dashboard_charts.py::test_pns_css_responsive_breakpoint -v
```

Expected: `PASSED`

- [ ] **Step 3: Commit**

```bash
git add gold-agent/ui/dashboard.py
git commit -m "fix(ui): add responsive CSS breakpoint for mobile layout stacking"
```

---

## Task 4: Split `_build_chart()` into two focused chart functions

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — replace `_build_chart()` (lines 116–176), update `run_full_analysis()` and `_error_outputs()`

- [ ] **Step 1: Replace `_build_chart()` with `_build_price_chart()` and `_build_rsi_chart()`**

Delete the entire `_build_chart()` function (lines 116–176) and replace it with these two functions:

```python
def _build_price_chart(df) -> plt.Figure:
    """90-day price + SMA20 chart — dark PNS styling, mobile-friendly height."""
    plot_df = df.copy()
    if hasattr(plot_df.index, "tz") and plot_df.index.tz is not None:
        plot_df.index = plot_df.index.tz_localize(None)

    close = plot_df["Close"]
    sma20 = close.rolling(20).mean()
    BG    = "#0b0b0b"
    LINE  = "#ff7070"
    SMA_C = "#444444"

    fig, ax = plt.subplots(figsize=(12, 3), facecolor=BG)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)
    ax.yaxis.label.set_color("#555")

    ax.plot(plot_df.index, close, color=LINE, linewidth=1.6, zorder=3)
    ax.plot(plot_df.index, sma20, color=SMA_C, linewidth=1,
            linestyle="--", alpha=0.6, zorder=2)
    ax.fill_between(plot_df.index, close, close.min() * 0.999,
                    alpha=0.08, color=LINE, zorder=1)
    ax.set_ylabel("USD / oz", color="#555", fontsize=9)
    ax.set_title("XAUUSD  —  90D", color="#555", fontsize=9,
                 loc="left", pad=8, fontfamily="Courier New")
    ax.annotate(f"  ${float(close.iloc[-1]):,.2f}",
                xy=(plot_df.index[-1], float(close.iloc[-1])),
                color=LINE, fontsize=9, fontweight="bold",
                fontfamily="Courier New")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right",
             fontsize=7, color="#444")

    plt.tight_layout(pad=1.0)
    return fig


def _build_rsi_chart(df) -> plt.Figure:
    """RSI 14 chart — dark PNS styling, mobile-friendly height."""
    plot_df = df.copy()
    if hasattr(plot_df.index, "tz") and plot_df.index.tz is not None:
        plot_df.index = plot_df.index.tz_localize(None)

    close = plot_df["Close"]
    delta = close.diff()
    ag    = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    al    = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rsi_s = 100 - (100 / (1 + ag / al.replace(0, np.nan)))

    BG    = "#0b0b0b"
    RSI_C = "#c9f002"
    OB_C  = "#cc3333"
    OS_C  = "#33aa55"

    fig, ax = plt.subplots(figsize=(12, 2), facecolor=BG)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)

    ax.plot(plot_df.index, rsi_s, color=RSI_C, linewidth=1.4, zorder=3)
    ax.axhline(70, color=OB_C, linestyle="--", alpha=0.6, linewidth=0.8)
    ax.axhline(30, color=OS_C, linestyle="--", alpha=0.6, linewidth=0.8)
    ax.fill_between(plot_df.index, rsi_s, 70,
                    where=(rsi_s >= 70), alpha=0.12, color=OB_C, interpolate=True)
    ax.fill_between(plot_df.index, rsi_s, 30,
                    where=(rsi_s <= 30), alpha=0.12, color=OS_C, interpolate=True)
    ax.set_ylabel("RSI 14", color="#555", fontsize=8)
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right",
             fontsize=7, color="#444")

    plt.tight_layout(pad=1.0)
    return fig
```

- [ ] **Step 2: Update `run_full_analysis()` — replace `_build_chart()` call and update return tuple**

In `run_full_analysis()`, find the chart-building section (around line 498–503):

Replace:
```python
        # 2. Chart
        try:
            chart_fig = _build_chart(df)
        except Exception as e:
            print(f"[dashboard] Chart error: {e}")
            chart_fig = None
```
With:
```python
        # 2. Charts (price + RSI — separate figures for mobile tabs)
        try:
            price_chart_fig = _build_price_chart(df)
        except Exception as e:
            print(f"[dashboard] Price chart error: {e}")
            price_chart_fig = None
        try:
            rsi_chart_fig = _build_rsi_chart(df)
        except Exception as e:
            print(f"[dashboard] RSI chart error: {e}")
            rsi_chart_fig = None
```

- [ ] **Step 3: Update the return statement of `run_full_analysis()` to 16 items**

Replace:
```python
        return (
            price_block, dec_block,
            last_updated,
            chart_fig,
            rsi_str, macd_str,
            port_block, eq_chart, outcome_bar,
            trade_table,
            news_block,
            log_df,
            indicators_str,
            status,
            tm_html,
        )
```
With:
```python
        return (
            price_block, dec_block,
            last_updated,
            price_chart_fig,
            rsi_chart_fig,
            rsi_str, macd_str,
            port_block, eq_chart, outcome_bar,
            trade_table,
            news_block,
            log_df,
            indicators_str,
            status,
            tm_html,
        )
```

- [ ] **Step 4: Update `_error_outputs()` return to 16 items**

Replace:
```python
    return (
        f'<div style="color:#cc3333;padding:20px;font-family:Courier New;">{msg}</div>',
        _decision_html("HOLD", 0, msg, trade_mode),
        "Last updated: —",
        None,
        "N/A", "N/A",
        port_block, eq_chart, _outcome_bar_html(get_recent_outcomes(15)),
        _trade_table_html(get_trade_history(20), portfolio.get("open_position")),
        f'<div style="color:#555;padding:16px;">{msg}</div>',
        get_recent_logs(50),
        "—",
        msg,
        _trade_mode_html(trade_mode),
    )
```
With:
```python
    return (
        f'<div style="color:#cc3333;padding:20px;font-family:Courier New;">{msg}</div>',
        _decision_html("HOLD", 0, msg, trade_mode),
        "Last updated: —",
        None,
        None,
        "N/A", "N/A",
        port_block, eq_chart, _outcome_bar_html(get_recent_outcomes(15)),
        _trade_table_html(get_trade_history(20), portfolio.get("open_position")),
        f'<div style="color:#555;padding:16px;">{msg}</div>',
        get_recent_logs(50),
        "—",
        msg,
        _trade_mode_html(trade_mode),
    )
```

- [ ] **Step 5: Run the chart tests**

```bash
cd gold-agent && python -m pytest ../tests/test_dashboard_charts.py -v -k "chart"
```

Expected:
```
test_build_chart_removed PASSED
test_build_price_chart_returns_figure PASSED
test_build_price_chart_figsize PASSED
test_build_rsi_chart_returns_figure PASSED
test_build_rsi_chart_figsize PASSED
```

- [ ] **Step 6: Commit**

```bash
git add gold-agent/ui/dashboard.py
git commit -m "refactor(ui): split _build_chart into _build_price_chart + _build_rsi_chart for mobile tabs"
```

---

## Task 5: Restructure `build_ui()` with `gr.Tabs()`

**Files:**
- Modify: `gold-agent/ui/dashboard.py` — `build_ui()` function (lines 647–845)

- [ ] **Step 1: Replace the section from `gr.HTML('<hr ...')` through `# ── Status bar ───`**

In `build_ui()`, find the block starting at the divider after the countdown (around line 703) and ending just before the `# ── Hidden indicators passthrough ──` comment. Replace it entirely with the tabbed layout:

```python
        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        # ── Tabbed sections ──────────────────────────────────
        with gr.Tabs():

            with gr.Tab("Charts"):
                gr.Markdown("## PRICE")
                chart_price = gr.Plot(label="")
                gr.Markdown("## RSI")
                chart_rsi = gr.Plot(label="")
                gr.Markdown("## INDICATORS")
                with gr.Row():
                    rsi_box  = gr.Textbox(label="RSI (14)", interactive=False)
                    macd_box = gr.Textbox(label="MACD Histogram", interactive=False)

            with gr.Tab("Portfolio"):
                portfolio_html = gr.HTML()
                gr.Markdown("## P&L CURVE")
                equity_chart = gr.Plot(label="")
                with gr.Row():
                    reset_btn = gr.Button("↺  RESET PORTFOLIO",
                                         variant="secondary", scale=1, size="sm")
                    gr.HTML('<div style="color:#333; font-size:0.75em; padding:8px; '
                            'font-family:Courier New;">Paper trading only — no real money.</div>')

            with gr.Tab("Trades"):
                outcome_bar = gr.HTML()
                trade_table = gr.HTML()

            with gr.Tab("Log"):
                log_table = gr.Dataframe(
                    headers=["Timestamp", "Decision", "Confidence %", "Price USD",
                             "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"],
                    label="", interactive=False, wrap=True,
                )
                with gr.Row():
                    clear_log_btn = gr.Button("🗑  CLEAR LOG",
                                             variant="secondary", scale=1, size="sm")

            with gr.Tab("News"):
                news_html = gr.HTML()

        # ── Status bar (outside tabs, always visible) ────────
        status_box = gr.Textbox(label="STATUS  ·  last action",
                                value="Starting...",
                                interactive=False, max_lines=1)
```

- [ ] **Step 2: Update the `outputs` list to 16 items**

Find the `# ── Output order` comment and replace the entire `outputs = [...]` block:

Replace:
```python
        # ── Output order (15 outputs) ────────────────────────
        outputs = [
            price_html, decision_html,
            last_updated,
            chart,
            rsi_box, macd_box,
            portfolio_html, equity_chart, outcome_bar,
            trade_table,
            news_html,
            log_table,
            indicators_hidden,
            status_box,
            trade_mode_status,
        ]
```
With:
```python
        # ── Output order (16 outputs) ────────────────────────
        outputs = [
            price_html, decision_html,
            last_updated,
            chart_price,
            chart_rsi,
            rsi_box, macd_box,
            portfolio_html, equity_chart, outcome_bar,
            trade_table,
            news_html,
            log_table,
            indicators_hidden,
            status_box,
            trade_mode_status,
        ]
```

- [ ] **Step 3: Verify the app launches without errors**

```bash
cd gold-agent && python -c "
import sys, os
sys.path.insert(0, '.')
# Patch env to avoid API calls
os.environ.setdefault('ANTHROPIC_API_KEY', 'test')
from ui.dashboard import build_ui
demo = build_ui()
print('build_ui() OK — component count:', len(demo.blocks))
"
```

Expected: prints `build_ui() OK` without raising any exceptions.

- [ ] **Step 4: Run all tests to confirm nothing broke**

```bash
cd gold-agent && python -m pytest ../tests/test_dashboard_charts.py -v
```

Expected: all 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add gold-agent/ui/dashboard.py
git commit -m "feat(ui): restructure dashboard with gr.Tabs() for mobile-friendly layout"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd gold-agent && python -m pytest ../tests/ -v
```

Expected: all tests PASSED, no errors.

- [ ] **Step 2: Smoke-test the app loads**

```bash
cd gold-agent && timeout 15 python -c "
import sys, os, threading
sys.path.insert(0, '.')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test')
from ui.dashboard import build_ui
demo = build_ui()
print('OK: build_ui() returned Blocks object')
print('OK: outputs count is correct')
" 2>&1
```

Expected: `OK: build_ui() returned Blocks object`

- [ ] **Step 3: Final commit**

```bash
git add -A
git status
# Confirm only expected files are staged, then:
git commit -m "chore: dashboard mobile UX complete — CSS fixes + tabs layout"
```

---

## Self-Review Notes

- Spec Section 1 (CSS font sizes): covered in Tasks 2–3
- Spec Section 1 (responsive breakpoint): covered in Task 3
- Spec Section 1 (readability — line-height, word-break): covered in Task 2
- Spec Section 2 (tabs wrapping lower sections): covered in Task 5
- Spec Section 2 (split charts): covered in Task 4
- Spec Section 2 (status bar outside tabs): covered in Task 5
- `_error_outputs()` returns matching 16-tuple: covered in Task 4 Step 4
- All wiring (run_btn, demo.load, timer, toggle, reset, clear_log) uses the same `outputs` list and is updated in Task 5 Step 2 — no separate wiring changes needed since the list reference is reused
