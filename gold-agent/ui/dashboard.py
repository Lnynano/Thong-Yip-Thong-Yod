"""
ui/dashboard.py
PNS-inspired dark trading dashboard for the Thong Yip Thong Yod.

Layout (top to bottom):
  1. Header bar  — title + LIVE indicator
  2. Price panel — big THB price + USD + change
  3. Decision    — BUY / SELL / HOLD badge + confidence + reasoning
  4. Refresh row — button + last-updated text
  5. Chart       — 90-day price with RSI (dark theme)
  6. Indicators  — RSI value + MACD value
  7. Portfolio   — equity, realised P&L, unrealised, win rate, R:R
  8. Trade log   — colour-coded table of past trades
  9. Analysis log — every Claude decision recorded
  10. News        — headlines + sentiment badge
"""

import sys, os, json, time
import numpy as np
import gradio as gr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

AUTO_REFRESH_SECONDS = 300

# Tracks when the last full analysis ran — used for countdown display
_last_refresh_time: float = time.time()


def _tick_countdown() -> str:
    """Lightweight 1-second tick — only returns the countdown string."""
    elapsed   = time.time() - _last_refresh_time
    remaining = max(0, AUTO_REFRESH_SECONDS - int(elapsed))
    mins      = remaining // 60
    secs      = remaining % 60
    filled    = int((elapsed / AUTO_REFRESH_SECONDS) * 20)
    filled    = min(filled, 20)
    bar       = "#" * filled + "-" * (20 - filled)   # ASCII-safe, renders in any font
    return f"Next auto-refresh in  {mins}:{secs:02d}  [{bar}]"

# ─────────────────────────────────────────────────────────────
# Dark PNS-style CSS
# ─────────────────────────────────────────────────────────────
PNS_CSS = """
/* ── Base ──────────────────────────────────────────── */
body, .gradio-container, .main, .wrap {
    background: #0b0b0b !important;
    color: #c8c8c8 !important;
    font-family: 'Courier New', 'Lucida Console', monospace !important;
    font-size: 1.0em !important;
    line-height: 1.5 !important;
    word-break: break-word !important;
}
footer, .built-with { display: none !important; }
.svelte-1gfkn6j  { display: none !important; }

/* ── Panels / cards ─────────────────────────────────── */
.gr-box, .gr-form, .gr-panel,
.block, .panel, fieldset {
    background: #111111 !important;
    border: 1px solid #1e1e1e !important;
    border-radius: 6px !important;
}

/* ── Labels ─────────────────────────────────────────── */
.label-wrap span, label, .gr-label {
    color: #555555 !important;
    font-size: 0.78em !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    font-family: 'Courier New', monospace !important;
}

/* ── Text inputs / textareas ─────────────────────────── */
textarea, input[type=text], .gr-text-input {
    background: #111 !important;
    border: 1px solid #222 !important;
    color: #cccccc !important;
    font-family: 'Courier New', monospace !important;
    font-size: 0.95em !important;
    line-height: 1.5 !important;
}

/* ── Buttons ─────────────────────────────────────────── */
button.primary { background: #c9f002 !important; color: #000 !important;
                 font-weight: 900 !important; letter-spacing: 0.08em !important;
                 border: none !important; font-family: 'Courier New', monospace !important; }
button.secondary { background: #1a1a1a !important; color: #666 !important;
                   border: 1px solid #2a2a2a !important;
                   font-family: 'Courier New', monospace !important; }

/* ── Dataframe / table ───────────────────────────────── */
.svelte-table, table, .gr-dataframe table {
    background: #0f0f0f !important; color: #bbb !important;
    font-size: 0.88em !important; font-family: 'Courier New', monospace !important;
}
th { background: #161616 !important; color: #555 !important;
     text-transform: uppercase !important; font-size: 0.78em !important;
     letter-spacing: 0.1em !important; border-bottom: 1px solid #222 !important; }
td { border-bottom: 1px solid #1a1a1a !important; }

/* ── Markdown headings ───────────────────────────────── */
h1, h2, h3 { color: #888 !important; letter-spacing: 0.15em !important;
              text-transform: uppercase !important;
              font-family: 'Courier New', monospace !important; }

/* ── Divider ─────────────────────────────────────────── */
hr { border-color: #1e1e1e !important; }

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
"""


# ─────────────────────────────────────────────────────────────
# Charts — dark PNS style (split for mobile tabs)
# ─────────────────────────────────────────────────────────────
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


def _build_equity_chart(equity_history: list) -> plt.Figure:
    """P&L equity curve chart (PNS second-panel style)."""
    BG   = "#0b0b0b"
    LINE = "#c9f002"

    fig, ax = plt.subplots(figsize=(12, 3), facecolor=BG)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)

    if len(equity_history) >= 2:
        values = [e["equity"] for e in equity_history]
        xs     = list(range(len(values)))
        ax.plot(xs, values, color=LINE, linewidth=1.8, zorder=3)
        ax.fill_between(xs, values, values[0], alpha=0.1, color=LINE, zorder=1)
        # Mark start
        ax.axhline(values[0], color="#333", linestyle="--", linewidth=0.8)
        ax.set_ylabel("Equity (THB)", color="#555", fontsize=8)
        ax.set_title("P&L CURVE", color="#555", fontsize=9,
                     loc="left", pad=6, fontfamily="Courier New")
        last = values[-1]
        color = "#c9f002" if last >= values[0] else "#cc3333"
        ax.annotate(f"  ฿{last:,.2f}", xy=(xs[-1], last),
                    color=color, fontsize=9, fontweight="bold")
    else:
        ax.text(0.5, 0.5, "No trade history yet",
                ha="center", va="center", color="#444",
                transform=ax.transAxes, fontsize=10)

    plt.tight_layout(pad=1.0)
    return fig


# ─────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────
def _price_html(price_thb: float, price_usd: float, change_thb: float,
                fetch_time: str, rate: float, rate_src: str) -> str:
    """Large price display panel — PNS style."""
    sign  = "+" if change_thb >= 0 else ""
    color = "#c9f002" if change_thb >= 0 else "#cc3333"
    change_pct = (change_thb / (price_thb - change_thb) * 100) if (price_thb - change_thb) != 0 else 0
    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:8px;">
    XAUUSD  ·  GOLD (THB/BAHT-WEIGHT 96.5%)
  </div>
  <div style="display:flex; align-items:baseline; gap:20px; flex-wrap:wrap;">
    <span style="color:#ffffff; font-size:3.2em; font-weight:900;
                 letter-spacing:-1px;">฿{price_thb:,.2f}</span>
    <span style="color:{color}; font-size:1.3em; font-weight:700;">
      {sign}{change_thb:,.2f} ({sign}{change_pct:.2f}%)
    </span>
  </div>
  <div style="color:#444; font-size:0.78em; margin-top:8px; letter-spacing:0.05em;">
    ${price_usd:,.2f} / troy oz &nbsp;·&nbsp;
    rate {rate:.2f} ({rate_src}) &nbsp;·&nbsp;
    as of {fetch_time} &nbsp;·&nbsp; 15-min delay
  </div>
</div>"""


def _trade_mode_html(trade_mode: bool) -> str:
    """Trade mode status banner."""
    if trade_mode:
        return (
            '<div style="font-family:Courier New,monospace; padding:10px 24px; '
            'background:#0d1a00; border:1px solid #2a4400; border-radius:6px; '
            'display:flex; align-items:center; gap:12px;">'
            '<span style="color:#c9f002; font-size:1.1em; font-weight:900; '
            'letter-spacing:0.15em;">● TRADE MODE : ON</span>'
            '<span style="color:#555; font-size:0.78em;">'
            'Paper trades will execute automatically on BUY / SELL signals ≥ 65% confidence'
            '</span></div>'
        )
    return (
        '<div style="font-family:Courier New,monospace; padding:10px 24px; '
        'background:#111; border:1px solid #222; border-radius:6px; '
        'display:flex; align-items:center; gap:12px;">'
        '<span style="color:#555; font-size:1.1em; font-weight:900; '
        'letter-spacing:0.15em;">○ TRADE MODE : OFF</span>'
        '<span style="color:#444; font-size:0.78em;">'
        'Analysis running — no trades will be placed'
        '</span></div>'
    )


def _decision_html(decision: str, confidence: int, reasoning: str,
                   trade_mode: bool = False) -> str:
    """BUY/SELL/HOLD card with reasoning — PNS style."""
    cfg = {
        "BUY":  ("#c9f002", "📈"),
        "SELL": ("#cc3333", "📉"),
        "HOLD": ("#555555", "⏸"),
    }
    color, icon = cfg.get(decision.upper(), ("#555", "?"))
    # Dim the signal color when trade mode is off
    if not trade_mode and decision.upper() in ("BUY", "SELL"):
        color = "#666666"
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
    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:10px;">
    AGENT RECOMMENDATION
  </div>
  <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
    <span style="color:{color}; font-size:2.8em; font-weight:900;
                 letter-spacing:6px;">{icon} {decision.upper()}</span>
    <span style="color:{color}; font-size:1em;">Confidence: {confidence}%</span>
    {trade_tag}
  </div>
  <div style="margin-top:14px; border-top:1px solid #1e1e1e; padding-top:12px;">
    {lines}
  </div>
</div>"""


def _portfolio_html(p: dict) -> str:
    """Portfolio stats bar — PNS style."""
    eq_color  = "#c9f002" if p["total_pnl"] >= 0 else "#cc3333"
    rl_color  = "#c9f002" if p["realized_pnl"] >= 0 else "#cc3333"
    ur_color  = "#c9f002" if p["unrealized_pnl"] >= 0 else "#cc3333"
    sign      = lambda v: "+" if v >= 0 else ""

    pos_block = ""
    if p["open_position"]:
        op = p["open_position"]
        oc = "#c9f002" if op["unrealized"] >= 0 else "#cc3333"
        pos_block = f"""
      <div style="margin-top:14px; border-top:1px solid #1e1e1e; padding-top:12px;
                  color:#555; font-size:0.78em;">
        OPEN POSITION &nbsp;·&nbsp;
        Entry ฿{op["entry_price"]:,.0f} &nbsp;·&nbsp;
        Size {op["size_bw"]:.5f} bw &nbsp;·&nbsp;
        Unrealised
        <span style="color:{oc};">{sign(op["unrealized"])}฿{op["unrealized"]:,.2f}
        ({sign(op["unrealized_pct"])}{op["unrealized_pct"]:.2f}%)</span>
        &nbsp;·&nbsp; Since {op["entry_time"]}
      </div>"""

    def stat(label, value, color="#c8c8c8"):
        return f"""
      <div style="min-width:120px;">
        <div style="color:#555; font-size:0.65em; letter-spacing:0.1em;
                    margin-bottom:4px;">{label}</div>
        <div style="color:{color}; font-size:1.25em; font-weight:700;">{value}</div>
      </div>"""

    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:14px;">
    PORTFOLIO  &nbsp;·&nbsp; PAPER TRADING
  </div>
  <div style="display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start;">
    {stat("TOTAL EQUITY",  f"฿{p['total_equity']:,.2f}",
          eq_color if p['total_pnl'] != 0 else '#c8c8c8')}
    {stat("REALIZED P&L",  f"{sign(p['realized_pnl'])}฿{p['realized_pnl']:,.2f}", rl_color)}
    {stat("UNREALIZED",    f"{sign(p['unrealized_pnl'])}฿{p['unrealized_pnl']:,.2f}", ur_color)}
    {stat("WIN RATE",      f"{p['win_rate']:.1f}%",
          '#c9f002' if p['win_rate'] >= 50 else '#cc3333')}
    {stat("W / L",         f"{p['wins']} / {p['losses']}")}
    {stat("TRADES",        str(p['total_trades']))}
    {stat("R:R",           f"{p['rr_ratio']:.2f}:1" if p['rr_ratio'] > 0 else "—")}
    {stat("BALANCE",       f"฿{p['initial_balance']:,.0f}", "#555")}
  </div>
  {pos_block}
</div>"""


def _outcome_bar_html(outcomes: list) -> str:
    """Coloured WIN/LOSS square bar — like PNS bottom bar."""
    if not outcomes:
        return '<div style="color:#333; font-size:0.8em; padding:8px;">No trades yet</div>'
    squares = ""
    for o in outcomes:
        c = "#c9f002" if o == "WIN" else "#cc3333"
        squares += f'<span style="display:inline-block; width:18px; height:18px; ' \
                   f'background:{c}; margin:2px; border-radius:2px;" title="{o}"></span>'
    return f'<div style="padding:8px 0;">{squares}</div>'


def _trade_table_html(trades: list) -> str:
    """HTML trade journal table — PNS style."""
    if not trades:
        return '<div style="color:#333; font-size:0.85em; padding:16px; ' \
               'font-family:Courier New,monospace;">No closed trades yet.</div>'

    rows = ""
    for t in trades:
        oc    = "#c9f002" if t["outcome"] == "WIN" else "#cc3333"
        sign  = "+" if t["pnl_thb"] >= 0 else ""
        exit_d = t["exit_time"][:16] if t.get("exit_time") else "—"
        rows += f"""
        <tr>
          <td style="color:#555; padding:6px 10px;">{exit_d}</td>
          <td style="color:{oc}; font-weight:700; padding:6px 10px;">{t['outcome']}</td>
          <td style="color:#888; padding:6px 10px;">฿{t['entry_price']:,.0f}</td>
          <td style="color:#888; padding:6px 10px;">฿{t['exit_price']:,.0f}</td>
          <td style="color:#777; padding:6px 10px;">{t['size_bw']:.5f} bw</td>
          <td style="color:{oc}; font-weight:700; padding:6px 10px;">
            {sign}฿{t['pnl_thb']:,.2f} ({sign}{t['pnl_pct']:.2f}%)
          </td>
        </tr>"""

    return f"""
<div style="font-family:'Courier New',monospace; overflow-x:auto;">
  <table style="width:100%; border-collapse:collapse; font-size:0.83em;
                background:#0f0f0f; color:#bbb;">
    <thead>
      <tr style="border-bottom:1px solid #222;">
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">TIME</th>
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">RESULT</th>
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">ENTRY</th>
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">EXIT</th>
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">SIZE</th>
        <th style="color:#444; text-align:left; padding:8px 10px;
                   letter-spacing:0.1em; font-size:0.75em;">P&L</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _news_html(headlines: list, sentiment: str) -> str:
    """News block with sentiment badge."""
    cfg  = {"BULLISH": ("#c9f002", "▲"), "BEARISH": ("#cc3333", "▼"), "NEUTRAL": ("#888", "—")}
    col, sym = cfg.get(sentiment, ("#888", "—"))
    items = "".join(
        f'<div style="padding:5px 0; border-bottom:1px solid #1a1a1a; '
        f'color:#888; font-size:0.88em;">{i+1}. {h}</div>'
        for i, h in enumerate(headlines)
    )
    return f"""
<div style="font-family:'Courier New',monospace; padding:16px 20px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="margin-bottom:10px;">
    <span style="color:#555; font-size:0.7em; letter-spacing:0.1em;">SENTIMENT &nbsp;</span>
    <span style="color:{col}; font-weight:700; font-size:0.9em;">{sym} {sentiment}</span>
  </div>
  {items}
</div>"""


# ─────────────────────────────────────────────────────────────
# Main analysis pipeline
# ─────────────────────────────────────────────────────────────
def run_full_analysis(trade_mode: bool = False) -> tuple:
    """
    Run the complete pipeline and return values for all UI outputs.

    Args:
        trade_mode: When True, paper trades are executed automatically.
                    When False, analysis runs but NO trades are placed.

    Returns 15 values:
        price_html, decision_html_out,
        last_updated, chart_fig, rsi_str, macd_str,
        portfolio_html, equity_chart, outcome_bar_html,
        trade_table_html, news_html_out, log_df,
        indicators_str, status, trade_mode_status_html
    """
    global _last_refresh_time
    _last_refresh_time = time.time()   # reset countdown

    try:
        # 1. Price
        from data.fetch import get_gold_price, get_fetch_time
        df = get_gold_price()
        if df.empty:
            return _error_outputs("Failed to fetch price data.", trade_mode)

        price_usd   = float(df["Close"].iloc[-1])
        prev_usd    = float(df["Close"].iloc[-2]) if len(df) > 1 else price_usd
        fetch_time  = get_fetch_time()

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

        # 3. Indicators
        from indicators.tech import calculate_rsi, calculate_macd
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)
        rsi_signal  = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
        macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"
        rsi_str  = f"{rsi:.1f}  —  {rsi_signal}"
        macd_str = f"{macd['histogram']:+.2f}  —  {macd_signal}"
        indicators_str = f"RSI {rsi:.1f} {rsi_signal}  ·  MACD {macd['histogram']:+.3f} {macd_signal}"

        # 4. News
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        sentiment = get_sentiment_summary(headlines)
        news_block = _news_html(headlines, sentiment)

        # 5. THB conversion
        from converter.thai import convert_to_thb
        thb      = convert_to_thb(price_usd)
        thb_now  = thb["thb_per_baht_weight_thai"]
        thb_prev = thb_now * (prev_usd / price_usd) if price_usd > 0 else thb_now
        change   = thb_now - thb_prev
        rate     = thb["usd_thb_rate"]
        rate_src = thb["rate_source"]

        # 6. Claude agent
        from agent.claude_agent import run_agent
        agent      = run_agent()
        decision   = agent.get("decision", "HOLD")
        confidence = agent.get("confidence", 0)
        reasoning  = agent.get("reasoning", "No reasoning.")

        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key or api_key == "your_key_here":
            reasoning = ("ANTHROPIC_API_KEY not set.\n"
                         "Add it to your .env file to enable Claude analysis.")

        # 7. Paper trade execution — ONLY when trade_mode is ON
        from trader.paper_engine import execute_paper_trade, get_portfolio_summary, \
                                        get_trade_history, get_equity_history, get_recent_outcomes
        if trade_mode:
            trade_result = execute_paper_trade(decision, confidence, thb_now)
        else:
            trade_result = {"action": "DISABLED", "reason": "Trade mode is OFF"}

        portfolio    = get_portfolio_summary(thb_now)
        trades       = get_trade_history(20)
        equity_hist  = get_equity_history()
        outcomes     = get_recent_outcomes(15)

        try:
            eq_chart = _build_equity_chart(equity_hist)
        except Exception:
            eq_chart = None

        # 8. Log analysis
        from logger.trade_log import log_analysis, get_recent_logs
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        log_analysis(decision=decision, confidence=confidence,
                     price_usd=f"${price_usd:,.2f}",
                     price_thb=f"฿{thb_now:,.0f}",
                     rsi=rsi_str, macd=macd_str,
                     sharpe=f"{risk['sharpe']:.2f}", reasoning=reasoning)
        log_df = get_recent_logs(50)

        # Build HTML blocks
        price_block  = _price_html(thb_now, price_usd, change, fetch_time, rate, rate_src)
        dec_block    = _decision_html(decision, confidence, reasoning, trade_mode)
        port_block   = _portfolio_html(portfolio)
        outcome_bar  = _outcome_bar_html(outcomes)
        trade_table  = _trade_table_html(trades)
        last_updated = f"Last updated: {fetch_time}  ·  auto-refresh every 5 min"
        tm_html      = _trade_mode_html(trade_mode)

        # Status bar message
        action = trade_result.get("action", "")
        if not trade_mode:
            status = f"📊 ANALYSIS ONLY  ·  {decision} {confidence}%  ·  Trade mode is OFF"
        elif action == "OPENED":
            status = f"✅ OPENED position  ·  {trade_result['size_bw']:.5f} bw @ ฿{trade_result['price_thb']:,.0f}"
        elif action == "CLOSED":
            pnl = trade_result.get("pnl_thb", 0)
            status = f"{'🟢' if pnl >= 0 else '🔴'} CLOSED  ·  P&L {'+' if pnl>=0 else ''}฿{pnl:.2f}  ·  {trade_result['outcome']}"
        elif action == "SKIP":
            status = f"⏸  {trade_result.get('reason', 'No trade')}  ·  {decision} {confidence}%"
        else:
            status = f"HOLD  ·  no trade action  ·  fetched {fetch_time}"

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

    except Exception as e:
        err = f"Error: {e}"
        print(f"[dashboard] {err}")
        return _error_outputs(err, trade_mode)


def _error_outputs(msg: str, trade_mode: bool = False) -> tuple:
    from logger.trade_log import get_recent_logs
    from trader.paper_engine import get_portfolio_summary, get_trade_history, \
                                     get_equity_history, get_recent_outcomes

    portfolio  = get_portfolio_summary(0)
    port_block = _portfolio_html(portfolio)
    eq_hist    = get_equity_history()

    try:
        eq_chart = _build_equity_chart(eq_hist)
    except Exception:
        eq_chart = None

    return (
        f'<div style="color:#cc3333;padding:20px;font-family:Courier New;">{msg}</div>',
        _decision_html("HOLD", 0, msg, trade_mode),
        "Last updated: —",
        None,
        None,
        "N/A", "N/A",
        port_block, eq_chart, _outcome_bar_html(get_recent_outcomes(15)),
        _trade_table_html(get_trade_history(20)),
        f'<div style="color:#555;padding:16px;">{msg}</div>',
        get_recent_logs(50),
        "—",
        msg,
        _trade_mode_html(trade_mode),
    )


# ─────────────────────────────────────────────────────────────
# UI Layout
# ─────────────────────────────────────────────────────────────
def build_ui() -> gr.Blocks:
    """Build and return the PNS-style Gradio dashboard."""

    with gr.Blocks(title="Thong Yip Thong Yod", theme=gr.themes.Base(), css=PNS_CSS) as demo:

        # ── Header ──────────────────────────────────────────
        gr.HTML("""
        <div style="font-family:'Courier New',monospace; padding:14px 24px;
                    background:#0f0f0f; border-bottom:1px solid #1e1e1e;
                    display:flex; justify-content:space-between; align-items:center;">
          <span style="color:#888; font-size:1.1em; font-weight:700;
                       letter-spacing:0.2em;">🥇 Thong Yip Thong Yod</span>
          <span style="color:#555; font-size:0.75em; letter-spacing:0.1em;">
            XAUUSD &nbsp;·&nbsp; PAPER TRADING &nbsp;·&nbsp;
            <span style="color:#c9f002;">● LIVE</span>
          </span>
        </div>""")

        # ── Trade Mode toggle (top of page, always visible) ──
        with gr.Row():
            trade_mode_toggle = gr.Checkbox(
                label="TRADE MODE  —  enable to execute paper trades automatically",
                value=False,
                scale=3,
            )
            gr.HTML(
                '<div style="font-family:Courier New,monospace; color:#444; '
                'font-size:0.75em; padding:12px 0; line-height:1.5em;">'
                'OFF = analysis only &nbsp;|&nbsp; ON = trades execute on BUY/SELL ≥ 65% conf'
                '</div>'
            )

        # ── Trade mode status banner ─────────────────────────
        trade_mode_status = gr.HTML()

        # ── 1. Price ─────────────────────────────────────────
        price_html = gr.HTML()

        # ── 2. Decision + Reasoning ──────────────────────────
        decision_html = gr.HTML()

        # ── 3. Refresh row ───────────────────────────────────
        with gr.Row():
            run_btn      = gr.Button("⟳  REFRESH NOW", variant="primary", scale=1, size="sm")
            last_updated = gr.Textbox(value="Loading...", interactive=False,
                                      show_label=False, scale=5, max_lines=1)

        # Countdown bar — updated every second by a lightweight timer
        countdown_box = gr.Textbox(
            value=_tick_countdown(),
            show_label=False,
            interactive=False,
            max_lines=1,
            elem_id="countdown-box",
        )

        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        # ── 4. Chart ─────────────────────────────────────────
        gr.Markdown("## PRICE  &  RSI")
        chart = gr.Plot(label="")

        # ── 5. Indicators ────────────────────────────────────
        gr.Markdown("## INDICATORS")
        with gr.Row():
            rsi_box  = gr.Textbox(label="RSI (14)", interactive=False)
            macd_box = gr.Textbox(label="MACD Histogram", interactive=False)

        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        # ── 6. Portfolio ─────────────────────────────────────
        gr.Markdown("## PORTFOLIO")
        portfolio_html = gr.HTML()

        # ── 7. P&L Curve ─────────────────────────────────────
        gr.Markdown("## P&L CURVE")
        equity_chart = gr.Plot(label="")

        # ── 8. Trade history bar + journal ───────────────────
        gr.Markdown("## TRADE JOURNAL")
        outcome_bar  = gr.HTML()
        trade_table  = gr.HTML()

        with gr.Row():
            reset_btn = gr.Button("↺  RESET PORTFOLIO", variant="secondary", scale=1, size="sm")
            gr.HTML('<div style="color:#333; font-size:0.75em; padding:8px; '
                    'font-family:Courier New;">Paper trading only — no real money.</div>')

        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        # ── 9. Analysis log ──────────────────────────────────
        gr.Markdown("## ANALYSIS LOG")
        log_table = gr.Dataframe(
            headers=["Timestamp", "Decision", "Confidence %", "Price USD",
                     "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"],
            label="", interactive=False, wrap=True,
        )
        with gr.Row():
            clear_log_btn = gr.Button("🗑  CLEAR LOG", variant="secondary", scale=1, size="sm")

        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        # ── 10. News ─────────────────────────────────────────
        gr.Markdown("## GOLD NEWS")
        news_html = gr.HTML()

        # ── Status bar ───────────────────────────────────────
        status_box = gr.Textbox(label="STATUS  ·  last action",
                                value="Starting...",
                                interactive=False, max_lines=1)

        # ── Hidden indicators passthrough ────────────────────
        indicators_hidden = gr.Textbox(visible=False)

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

        # ── Wire up refresh button, page load, and timer ─────
        # All three read trade_mode_toggle so the checkbox state
        # is always respected — including during auto-refresh.
        run_btn.click(
            fn=run_full_analysis,
            inputs=[trade_mode_toggle],
            outputs=outputs,
        )
        demo.load(
            fn=run_full_analysis,
            inputs=[trade_mode_toggle],
            outputs=outputs,
        )

        # Auto-refresh every 5 minutes — runs full analysis
        try:
            analysis_timer = gr.Timer(value=AUTO_REFRESH_SECONDS)
            analysis_timer.tick(
                fn=run_full_analysis,
                inputs=[trade_mode_toggle],
                outputs=outputs,
            )
        except Exception as e:
            # Fallback: older Gradio builds — warn but don't crash
            print(f"[dashboard] gr.Timer not available ({e}); auto-refresh disabled.")

        # Countdown ticker — fires every 1 second, very lightweight
        try:
            countdown_timer = gr.Timer(value=1)
            countdown_timer.tick(
                fn=_tick_countdown,
                inputs=[],
                outputs=[countdown_box],
            )
        except Exception as e:
            print(f"[dashboard] Countdown timer not available ({e})")

        # Toggle change instantly refreshes the banner + dims/lights decision
        trade_mode_toggle.change(
            fn=run_full_analysis,
            inputs=[trade_mode_toggle],
            outputs=outputs,
        )

        # Reset portfolio
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
                    _trade_table_html(get_trade_history(20)))

        reset_btn.click(fn=_reset, inputs=[],
                        outputs=[portfolio_html, equity_chart, outcome_bar, trade_table])

        # Clear log
        def _clear():
            from logger.trade_log import clear_log, get_recent_logs
            clear_log()
            return get_recent_logs(50)

        clear_log_btn.click(fn=_clear, inputs=[], outputs=[log_table])

    return demo


if __name__ == "__main__":
    build_ui().launch(server_port=7860, share=False)
