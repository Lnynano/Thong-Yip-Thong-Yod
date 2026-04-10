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
import html
import numpy as np
import gradio as gr
from datetime import timezone, timedelta

# Thai timezone UTC+7 (no pytz needed)
THAI_TZ = timezone(timedelta(hours=7))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ┌─────────────────────────────────────────────────────────────────────────────
# │  DEV_MODE FLAG
# │  Set to True  → all developer features are visible (local dev)
# │  Set to False → developer features are hidden     (production deploy)
# │
# │  Features controlled by this flag:
# │    1. REFRESH MODE radio  (REAL / TEST 15-sec)
# │    2. TRADE MODE toggle   (enable paper trading)
# │    3. RESET PORTFOLIO button
# │    4. CLEAR LOG button
# │    5. Backtest tab
# └─────────────────────────────────────────────────────────────────────────────
DEV_MODE: bool = False   # ← change to False before deploying

_INTERVALS = {"REAL": 1800, "TEST": 15}
_current_mode: str = "REAL"

# Tracks when the last full analysis ran — used for countdown display
_last_refresh_time: float = time.time()

# ─────────────────────────────────────────────────────────────
# UI state persistence — survives page refresh
# ─────────────────────────────────────────────────────────────
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_UI_STATE_PATH = os.path.join(_BASE_DIR, "data", "ui_state.json")
_UI_STATE_DEFAULTS = {"trade_mode": False, "refresh_mode": "REAL"}


def _load_ui_state() -> dict:
    """Load persisted UI state; returns defaults if file missing or corrupt."""
    try:
        with open(_UI_STATE_PATH, "r") as f:
            state = json.load(f)
        return {**_UI_STATE_DEFAULTS, **state}
    except Exception:
        return dict(_UI_STATE_DEFAULTS)


def _save_ui_state(**kwargs) -> None:
    """Merge kwargs into saved UI state file."""
    try:
        state = _load_ui_state()
        state.update(kwargs)
        os.makedirs(os.path.dirname(_UI_STATE_PATH), exist_ok=True)
        with open(_UI_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass  # non-critical


def _set_mode(mode: str) -> None:
    """Switch between REAL and TEST mode; resets countdown."""
    global _current_mode, _last_refresh_time
    _current_mode = mode
    _last_refresh_time = time.time()
    _save_ui_state(refresh_mode=mode)


def _tick_countdown() -> str:
    """Lightweight 1-second tick — only returns the countdown string."""
    interval  = _INTERVALS.get(_current_mode, 300)
    elapsed   = time.time() - _last_refresh_time
    remaining = max(0, interval - int(elapsed))
    mins      = remaining // 60
    secs      = remaining % 60
    filled    = int((elapsed / interval) * 20)
    filled    = min(filled, 20)
    bar       = "#" * filled + "-" * (20 - filled)   # ASCII-safe, renders in any font

    return f"Next refresh in  {mins}:{secs:02d}  [{bar}] "

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

/* ── Radio & Checkbox choice text — override dark label rule ── */
input[type="radio"] ~ span,
input[type="radio"] + span,
input[type="checkbox"] ~ span,
input[type="checkbox"] + span {
    color: #cccccc !important;
    font-family: 'Courier New', monospace !important;
    font-size: 0.88em !important;
    letter-spacing: 0.08em !important;
}
input[type="radio"], input[type="checkbox"] {
    accent-color: #c9f002 !important;
}

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


def _build_pl_card(portfolio: dict) -> str | None:
    """
    Generate a branded PNG P&L performance card for social sharing.

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
        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.text(0.04, 0.92, "THONG YIP THONG YOD",
                transform=ax.transAxes, color=GRAY,
                fontsize=10, fontfamily="monospace",
                fontweight="bold", va="top")
        ax.text(0.04, 0.80, "PAPER TRADING  ·  XAUUSD",
                transform=ax.transAxes, color="#333",
                fontsize=7, fontfamily="monospace", va="top")

        ax.text(0.04, 0.60,
                f"{sign}฿{pnl:,.2f}  ({sign}{pnl_pct:.2f}%)",
                transform=ax.transAxes, color=pnl_color,
                fontsize=22, fontfamily="monospace",
                fontweight="black", va="top")

        ax.text(0.04, 0.35, "TOTAL P&L",
                transform=ax.transAxes, color=GRAY,
                fontsize=7, fontfamily="monospace", va="top")

        stats = [
            ("WIN RATE",  f"{win_rate:.1f}%"),
            ("W / L",     f"{wins} / {losses}"),
            ("TRADES",    str(trades)),
            ("R:R",       f"{rr:.2f}:1" if rr > 0 else "-"),
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

        ax.plot([0.04, 0.96], [0.03, 0.03],
                color=ACCENT, linewidth=1.5, transform=ax.transAxes, clip_on=False)

        plt.tight_layout(pad=0.4)

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


# ─────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────
def _price_html(price_thb: float, price_usd: float, change_thb: float,
                fetch_time: str, rate: float, rate_src: str) -> str:
    """Large price display panel — PNS style."""
    sign  = "+" if change_thb >= 0 else ""
    color = "#c9f002" if change_thb >= 0 else "#cc3333"
    change_pct = (change_thb / (price_thb - change_thb) * 100) if (price_thb - change_thb) != 0 else 0
    safe_time = html.escape(str(fetch_time))
    safe_src  = html.escape(str(rate_src))
    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f;
            border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:8px;">
    {"HUA SENG HENG  ·  LIVE" if rate_src == "hsh" else "XAUUSD  ·  YFINANCE (CONVERTED)"}  ·  GOLD (THB/BAHT-WEIGHT 96.5%)
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
    {"HSH live price" if rate_src == "hsh" else f"rate {rate:.2f} ({safe_src})"} &nbsp;·&nbsp;
    as of {safe_time} &nbsp;·&nbsp; {"live" if rate_src == "hsh" else "15-min delay"}
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
    filled = max(0, min(10, int(round(confluence))))
    conf_bar = "█" * filled + "░" * (10 - filled)
    conf_color = "#c9f002" if confluence >= 6 else "#f0a002" if confluence >= 4 else "#cc3333"

    lines = "".join(
        f'<div style="margin:3px 0; color:#888; font-size:0.88em;">{html.escape(l)}</div>'
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
            f'<div style="color:#666; font-size:0.82em; margin:2px 0;">▸ {html.escape(f)}</div>'
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
        ⚠ {html.escape(risk_note)}
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


def _trade_table_html(trades: list, open_position: dict | None = None,
                      filter_mode: str = "ALL") -> str:
    """HTML trade journal table — PNS style. Shows open position at top if present."""
    # Apply win/loss filter (open position row always shown regardless of filter)
    if filter_mode == "WIN":
        trades = [t for t in trades if t.get("outcome") == "WIN"]
    elif filter_mode == "LOSS":
        trades = [t for t in trades if t.get("outcome") == "LOSS"]

    if not trades and not open_position:
        return '<div style="color:#333; font-size:0.85em; padding:16px; ' \
               'font-family:Courier New,monospace;">No closed trades yet.</div>'

    rows = ""

    # ── Open position row (BUY in progress) ──────────────────
    if open_position:
        unreal     = open_position.get("unrealized", 0)
        unreal_pct = open_position.get("unrealized_pct", 0)
        sign       = "+" if unreal >= 0 else ""
        unreal_col = "#c9f002" if unreal >= 0 else "#cc3333"
        entry_d    = open_position.get("entry_time", "")[:16]
        rows += f"""
        <tr style="background:#0d1a0d; border-left:3px solid #c9f002;">
          <td style="color:#c9f002; padding:6px 10px; font-size:0.8em;">{entry_d}</td>
          <td style="color:#c9f002; font-weight:700; padding:6px 10px;">OPEN ▶</td>
          <td style="color:#aaa; padding:6px 10px;">฿{open_position['entry_price']:,.0f}</td>
          <td style="color:#444; padding:6px 10px;">—</td>
          <td style="color:#777; padding:6px 10px;">{open_position['size_bw']:.5f} bw</td>
          <td style="color:{unreal_col}; font-weight:700; padding:6px 10px;">
            {sign}฿{unreal:,.2f} ({sign}{unreal_pct:.2f}%)
          </td>
        </tr>"""

    # ── Closed trade rows ─────────────────────────────────────
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
# Backtest HTML builder
# ─────────────────────────────────────────────────────────────
def _backtest_summary_html(summary: dict) -> str:
    """Render backtest summary stats card."""
    ret     = summary.get("return_pct", 0)
    col     = "#c9f002" if ret >= 0 else "#cc3333"
    sign    = "+" if ret >= 0 else ""
    pnl     = summary.get("total_pnl", 0)
    pnl_col = "#c9f002" if pnl >= 0 else "#cc3333"

    def stat(label, val, vc="#c8c8c8"):
        return (f'<div style="flex:1; min-width:130px; padding:10px 14px; '
                f'background:#111; border:1px solid #1e1e1e; border-radius:4px; margin:4px;">'
                f'<div style="color:#444; font-size:0.68em; letter-spacing:0.12em;">{label}</div>'
                f'<div style="color:{vc}; font-size:1.1em; font-weight:700;">{val}</div></div>')

    return f"""
<div style="font-family:'Courier New',monospace; padding:16px 20px;
            background:#0f0f0f; border:1px solid #1e1e1e; border-radius:6px; margin-bottom:12px;">
  <div style="color:#555; font-size:0.7em; letter-spacing:0.15em; margin-bottom:10px;">
    BACKTEST RESULTS &nbsp;·&nbsp; {summary.get('period_start','—')} → {summary.get('period_end','—')}
    &nbsp;·&nbsp; {summary.get('calendar_days', summary.get('days_run', 0))} calendar days
    &nbsp;·&nbsp; {summary.get('candles_run', summary.get('days_run', 0))} x {summary.get('interval','—')} candles
  </div>
  <div style="display:flex; flex-wrap:wrap;">
    {stat("RETURN",         f"{sign}{ret:.2f}%",                  col)}
    {stat("FINAL EQUITY",   f"฿{summary.get('final_equity',0):,.2f}")}
    {stat("TOTAL P&L",      f"{'+'if pnl>=0 else ''}฿{pnl:,.2f}", pnl_col)}
    {stat("WIN RATE",       f"{summary.get('win_rate',0):.1f}%")}
    {stat("TRADES",         str(summary.get('total_trades',0)))}
    {stat("WINS",           str(summary.get('wins',0)),            "#c9f002")}
    {stat("LOSSES",         str(summary.get('losses',0)),          "#cc3333")}
    {stat("CALENDAR DAYS",  str(summary.get('calendar_days', summary.get('days_run', 0))))}
    {stat("CANDLES",        f"{summary.get('candles_run', summary.get('days_run',0))} x {summary.get('interval','—')}")}
  </div>
</div>"""


def _backtest_trades_html(closed_trades: list) -> str:
    """Render closed trades table for backtest."""
    if not closed_trades:
        return '<div style="color:#555; padding:16px; font-family:Courier New,monospace;">No closed trades.</div>'

    rows = ""
    for t in closed_trades:
        oc  = "#c9f002" if t["outcome"] == "WIN" else "#cc3333"
        sym = "▲" if t["outcome"] == "WIN" else "▼"
        pnl_s = f"{'+'if t['pnl_thb']>=0 else ''}฿{t['pnl_thb']:,.2f}"
        rows += (
            f'<tr>'
            f'<td style="padding:6px 10px; color:#888;">{t["entry_date"]}</td>'
            f'<td style="padding:6px 10px; color:#888;">{t["exit_date"]}</td>'
            f'<td style="padding:6px 10px; color:#bbb;">฿{t["entry_price"]:,.0f}</td>'
            f'<td style="padding:6px 10px; color:#bbb;">฿{t["exit_price"]:,.0f}</td>'
            f'<td style="padding:6px 10px; color:{oc}; font-weight:700;">{pnl_s}</td>'
            f'<td style="padding:6px 10px; color:{oc}; font-weight:700;">{sym} {t["outcome"]}</td>'
            f'</tr>'
        )

    return f"""
<div style="font-family:'Courier New',monospace; overflow-x:auto;">
  <table style="width:100%; border-collapse:collapse; background:#0f0f0f; color:#bbb;">
    <thead>
      <tr style="border-bottom:1px solid #222;">
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">ENTRY DATE</th>
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">EXIT DATE</th>
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">ENTRY ฿</th>
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">EXIT ฿</th>
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">P&L</th>
        <th style="color:#444; text-align:left; padding:8px 10px; font-size:0.75em; letter-spacing:0.1em;">RESULT</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _backtest_equity_chart(daily_log: list):
    """Build equity curve chart from backtest daily log."""
    import matplotlib.pyplot as plt
    if not daily_log:
        return None
    BG   = "#0b0b0b"
    LINE = "#c9f002"
    dates   = [d["date"] for d in daily_log]
    equities= [d["equity_thb"] for d in daily_log]
    fig, ax = plt.subplots(figsize=(12, 3), facecolor=BG)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)
    ax.plot(dates, equities, color=LINE, linewidth=1.8)
    ax.fill_between(dates, equities, min(equities) * 0.999, alpha=0.1, color=LINE)
    ax.axhline(y=1500, color="#444", linewidth=1, linestyle="--", alpha=0.5)
    ax.set_ylabel("Equity (฿)", color="#555", fontsize=9)
    ax.set_title("BACKTEST  —  EQUITY CURVE", color="#555", fontsize=9,
                 loc="left", pad=8, fontfamily="Courier New")
    step = max(1, len(dates) // 8)
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                       rotation=30, ha="right", fontsize=7, color="#444")
    plt.tight_layout(pad=1.0)
    return fig


def _run_backtest_ui() -> tuple:
    """Called by the dashboard Run Backtest button."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from backtest import run_backtest
        result  = run_backtest()
        summary = result["summary"]
        trades  = result["closed_trades"]
        log     = result["daily_log"]
        summary_html = _backtest_summary_html(summary)
        trades_html  = _backtest_trades_html(trades)
        eq_chart     = _backtest_equity_chart(log)
        cal  = summary.get('calendar_days', summary['days_run'])
        bars = summary.get('candles_run',  summary['days_run'])
        ivl  = summary.get('interval', '?')
        status = (f"✅ Backtest complete  ·  {cal} calendar days  ·  {bars}x{ivl} candles  ·  "
                  f"Return {'+' if summary['return_pct']>=0 else ''}{summary['return_pct']:.2f}%  ·  "
                  f"Win rate {summary['win_rate']:.1f}%")
        return summary_html, trades_html, eq_chart, status
    except Exception as e:
        err = f'<div style="color:#cc3333; padding:16px; font-family:Courier New,monospace;">Backtest failed: {html.escape(str(e))}</div>'
        return err, err, None, f"❌ Backtest error: {str(e)}"


# ─────────────────────────────────────────────────────────────
# Main analysis pipeline
# ─────────────────────────────────────────────────────────────
def run_full_analysis(trade_mode: bool = False) -> tuple:
    """
    Run the complete pipeline and return values for all UI outputs.

    Args:
        trade_mode: When True, paper trades are executed automatically.
                    When False, analysis runs but NO trades are placed.

    Returns 18 values:
        price_html, decision_html_out,
        last_updated, price_chart_fig, rsi_chart_fig, rsi_str, macd_str,
        portfolio_html, equity_chart, outcome_bar_html,
        trade_table_html, news_html_out, log_df,
        indicators_str, status, trade_mode_status_html,
        dxy_str, vix_str
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
        regime = calculate_market_regime(df)

        # 3b. Macro indicators — DXY + VIX
        dxy_str = "N/A"
        vix_str = "N/A"
        try:
            from data.fetch import get_macro_indicators
            macro = get_macro_indicators()
            if macro.get("dxy"):
                dxy_str = macro["dxy"]["label"]
            if macro.get("vix"):
                vix_str = macro["vix"]["label"]
        except Exception:
            pass

        indicators_str = (
            f"RSI {rsi:.1f} {rsi_signal}  ·  MACD {macd['histogram']:+.3f} {macd_signal}"
            f"  ·  DXY {dxy_str}  ·  VIX {vix_str}"
        )

        # 4. News
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        sentiment = get_sentiment_summary(headlines)
        news_block = _news_html(headlines, sentiment)

        # 5. THB price — Hua Seng Heng live API (primary) / yfinance conversion (fallback)
        from data.fetch import get_hsh_price
        from converter.thai import convert_to_thb
        hsh = get_hsh_price()
        if hsh:
            # Primary: real Hua Seng Heng price (competition-grade)
            thb_now  = hsh["sell"]            # price you PAY to buy gold
            rate     = 0.0                    # not applicable — direct THB quote
            rate_src = "hsh"
            # Approximate previous THB price using yfinance USD ratio
            thb_prev = thb_now * (prev_usd / price_usd) if price_usd > 0 else thb_now
        else:
            # Fallback: convert XAUUSD → THB via exchange rate
            thb      = convert_to_thb(price_usd)
            thb_now  = thb["thb_per_baht_weight_thai"]
            thb_prev = thb_now * (prev_usd / price_usd) if price_usd > 0 else thb_now
            rate     = thb["usd_thb_rate"]
            rate_src = thb["rate_source"]
        change = thb_now - thb_prev

        # 6. Trading agent
        from agent.trading_agent import run_agent
        agent      = run_agent()
        decision   = agent.get("decision", "HOLD")
        confidence = agent.get("confidence", 0)
        reasoning  = agent.get("reasoning", "No reasoning.")

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "your_key_here":
            reasoning = ("OPENAI_API_KEY not set.\n"
                         "Add it to your .env file to enable GPT analysis.")

        # 7. Paper trade execution — ONLY when trade_mode is ON AND scheduler allows
        from trader.paper_engine import execute_paper_trade, get_portfolio_summary, \
                                        get_trade_history, get_equity_history, get_recent_outcomes
        from trader.trade_scheduler import can_trade_now, record_trade
        if trade_mode and can_trade_now():
            trade_result = execute_paper_trade(decision, confidence, thb_now)
            if trade_result.get("action") not in ("DISABLED", "SKIP", None):
                record_trade()
        elif trade_mode and not can_trade_now():
            trade_result = {"action": "SKIP", "reason": "Outside trading window"}
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

        # 8. Log analysis (internal CSV/MongoDB + professor's API)
        from logger.trade_log import log_analysis, get_recent_logs, send_trade_log
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        log_analysis(decision=decision, confidence=confidence,
                     price_usd=f"${price_usd:,.2f}",
                     price_thb=f"฿{thb_now:,.0f}",
                     rsi=rsi_str, macd=macd_str,
                     sharpe=f"{risk['sharpe']:.2f}", reasoning=reasoning)
        # Send to professor's trade log API (competition requirement)
        send_trade_log(action=decision, price_thb=thb_now,
                       reason=reasoning, confidence=confidence)
        log_df = get_recent_logs(50)

        # Build HTML blocks
        price_block  = _price_html(thb_now, price_usd, change, fetch_time, rate, rate_src)
        # Scale BB bands from USD to THB using same ratio as current price
        thb_per_usd_oz = thb_now / price_usd if price_usd > 0 else 0.0
        bb_lower_thb = round(bb["lower"] * thb_per_usd_oz, 0)
        bb_upper_thb = round(bb["upper"] * thb_per_usd_oz, 0)

        confluence = calculate_confluence_score(df, sentiment)

        dec_block = _decision_html(
            decision, confidence, reasoning, trade_mode,
            key_factors=agent.get("key_factors", []),
            risk_note=agent.get("risk_note", ""),
            confluence=confluence,
            regime=regime,
            bb_lower=bb_lower_thb,
            bb_upper=bb_upper_thb,
            current_price_thb=thb_now,
        )
        port_block   = _portfolio_html(portfolio)
        outcome_bar  = _outcome_bar_html(outcomes)
        trade_table  = _trade_table_html(trades, portfolio.get("open_position"))
        thai_now     = __import__('datetime').datetime.now(THAI_TZ).strftime("%H:%M:%S")
        last_updated = f"Last updated: {thai_now} (TH)  ·  auto-refresh every 30 min"
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
            dxy_str, vix_str,
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
        _decision_html("HOLD", 0, msg, trade_mode,
                       key_factors=[], risk_note="",
                       confluence=5.0, regime="RANGING",
                       bb_lower=0.0, bb_upper=0.0, current_price_thb=0.0),
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
        "N/A", "N/A",
    )


# ─────────────────────────────────────────────────────────────
# UI Layout
# ─────────────────────────────────────────────────────────────
def build_ui() -> gr.Blocks:
    """Build and return the PNS-style Gradio dashboard."""

    # Restore UI state from last session
    _saved = _load_ui_state()
    _init_trade_mode: bool = _saved["trade_mode"]
    _init_refresh_mode: str = _saved["refresh_mode"]
    # Apply saved refresh mode to global so countdown starts correctly
    _set_mode(_init_refresh_mode)

    with gr.Blocks(title="Thong Yip Thong Yod") as demo:

        # ── Header ──────────────────────────────────────────
        gr.HTML("""
        <div style="font-family:'Courier New',monospace; padding:14px 24px;
                    background:#0f0f0f; border-bottom:1px solid #1e1e1e;
                    display:flex; justify-content:space-between; align-items:center;">
          <span style="color:#888; font-size:1.1em; font-weight:700;
                       letter-spacing:0.2em;"> Thong Yip Thong Yod</span>
          <span style="color:#555; font-size:0.75em; letter-spacing:0.1em;">
            XAUUSD &nbsp;·&nbsp; PAPER TRADING &nbsp;·&nbsp;
            <span style="color:#c9f002;">● LIVE</span>
          </span>
        </div>""")

        # ── Trade Mode toggle — hidden in production (DEV_MODE=False) ──
        with gr.Row(visible=DEV_MODE):
            trade_mode_toggle = gr.Checkbox(
                label="TRADE MODE  —  enable to execute paper trades automatically",
                value=_init_trade_mode,
                scale=3,
            )
            gr.HTML(
                '<div style="font-family:Courier New,monospace; color:#444; '
                'font-size:0.75em; padding:12px 0; line-height:1.5em;">'
                'OFF = analysis only &nbsp;|&nbsp; ON = trades execute on BUY/SELL ≥ 65% conf'
                '</div>'
            )

        # ── Mode selector (REAL / TEST) — hidden in production (DEV_MODE=False) ──
        with gr.Row(visible=DEV_MODE):
            mode_radio = gr.Radio(
                choices=["REAL", "TEST"],
                value=_init_refresh_mode,
                label="REFRESH MODE  —  REAL = every 30 min  ·  TEST = every 15 sec",
                interactive=True,
                scale=3,
            )
            gr.HTML(
                '<div style="font-family:Courier New,monospace; color:#444; '
                'font-size:0.75em; padding:12px 0; line-height:1.5em;">'
                'Switch to TEST for fast 15-second cycles when market is closed'
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
                gr.Markdown("## MACRO")
                with gr.Row():
                    dxy_box  = gr.Textbox(label="DXY  —  US Dollar Index  (↑ bearish gold  ·  ↓ bullish gold)", interactive=False)
                    vix_box  = gr.Textbox(label="VIX  —  Fear Index  (>20 bullish gold  ·  <15 neutral)", interactive=False)

            with gr.Tab("Portfolio"):
                portfolio_html = gr.HTML()
                gr.Markdown("## P&L CURVE")
                equity_chart = gr.Plot(label="")
                with gr.Row():
                    share_btn = gr.Button("📤  SHARE P&L CARD",
                                          variant="secondary", scale=1, size="sm")
                    pl_card_file = gr.File(label="Download P&L Card", visible=False)
                # RESET PORTFOLIO — hidden in production (DEV_MODE=False)
                with gr.Row(visible=DEV_MODE):
                    reset_btn = gr.Button("↺  RESET PORTFOLIO",
                                         variant="secondary", scale=1, size="sm")
                    gr.HTML('<div style="color:#333; font-size:0.75em; padding:8px; '
                            'font-family:Courier New;">Paper trading only — no real money.</div>')

            with gr.Tab("Trades"):
                trade_filter = gr.Radio(
                    choices=["ALL", "WIN", "LOSS"],
                    value="ALL",
                    label="FILTER",
                    interactive=True,
                )
                outcome_bar = gr.HTML()
                trade_table = gr.HTML()

            with gr.Tab("Log"):
                log_table = gr.Dataframe(
                    headers=["Timestamp", "Decision", "Confidence %", "Price USD",
                             "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"],
                    label="", interactive=False, wrap=True,
                )
                # CLEAR LOG — hidden in production (DEV_MODE=False)
                with gr.Row(visible=DEV_MODE):
                    clear_log_btn = gr.Button("🗑  CLEAR LOG",
                                             variant="secondary", scale=1, size="sm")

            with gr.Tab("News"):
                news_html = gr.HTML()

            with gr.Tab("Backtest", visible=DEV_MODE):
                gr.HTML(
                    '<div style="font-family:Courier New,monospace; color:#555; '
                    'font-size:0.75em; padding:8px 0; letter-spacing:0.08em;">'
                    'Replay 20 days of historical XAUUSD data through the trading agent.  '
                    'Uses embedded CSV data — no live API needed for price.  '
                    'Each run costs ~20 GPT-4o-mini calls.'
                    '</div>'
                )
                bt_run_btn      = gr.Button("▶  RUN BACKTEST", variant="primary", size="sm")
                bt_status       = gr.Textbox(value="—", label="STATUS", interactive=False, max_lines=1)
                bt_summary_html = gr.HTML()
                gr.Markdown("## EQUITY CURVE")
                bt_equity_chart = gr.Plot(label="")
                gr.Markdown("## CLOSED TRADES")
                bt_trades_html  = gr.HTML()

        # ── Status bar (outside tabs, always visible) ────────
        status_box = gr.Textbox(label="STATUS  ·  last action",
                                value="Starting...",
                                interactive=False, max_lines=1)

        # ── Hidden indicators passthrough ────────────────────
        indicators_hidden = gr.Textbox(visible=False)

        # ── Output order (18 outputs) ────────────────────────
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
            dxy_box, vix_box,
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

        # Mode selector wires to module-level _current_mode
        mode_radio.change(fn=_set_mode, inputs=[mode_radio], outputs=[])

        # Two timers: REAL (300s) and TEST (15s).
        # Each checks _current_mode before running — only the active mode fires.
        def _run_if_real(trade_mode):
            if _current_mode != "REAL":
                return [gr.update()] * len(outputs)
            return list(run_full_analysis(trade_mode))

        def _run_if_test(trade_mode):
            if _current_mode != "TEST":
                return [gr.update()] * len(outputs)
            return list(run_full_analysis(trade_mode))

        try:
            real_timer = gr.Timer(value=1800)  # 30 minutes
            real_timer.tick(fn=_run_if_real, inputs=[trade_mode_toggle], outputs=outputs)

            test_timer = gr.Timer(value=15)
            test_timer.tick(fn=_run_if_test, inputs=[trade_mode_toggle], outputs=outputs)
        except Exception as e:
            print(f"[dashboard] gr.Timer not available ({e}); auto-refresh disabled.")

        # Countdown ticker — fires every 30 seconds (was 1s; 1s caused Render WebSocket congestion)
        try:
            countdown_timer = gr.Timer(value=30)
            countdown_timer.tick(
                fn=_tick_countdown,
                inputs=[],
                outputs=[countdown_box],
            )
        except Exception as e:
            print(f"[dashboard] Countdown timer not available ({e})")

        # Toggle change: notify background scheduler + refresh UI
        def _on_trade_mode_change(enabled: bool):
            # Persist so the toggle survives page refresh
            _save_ui_state(trade_mode=enabled)
            # Update the background scheduler flag so trades fire
            # even when no browser tab is open.
            try:
                from main import set_trade_mode
                set_trade_mode(enabled)
            except Exception:
                pass  # non-critical if called outside main.py context
            return run_full_analysis(enabled)

        trade_mode_toggle.change(
            fn=_on_trade_mode_change,
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
                    _trade_table_html(get_trade_history(20), p.get("open_position"), "ALL"))

        reset_btn.click(fn=_reset, inputs=[],
                        outputs=[portfolio_html, equity_chart, outcome_bar, trade_table])

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

        # Clear log
        def _clear():
            from logger.trade_log import clear_log, get_recent_logs
            clear_log()
            return get_recent_logs(50)

        clear_log_btn.click(fn=_clear, inputs=[], outputs=[log_table])

        # ── Backtest button ───────────────────────────────────
        bt_run_btn.click(
            fn=_run_backtest_ui,
            inputs=[],
            outputs=[bt_summary_html, bt_trades_html, bt_equity_chart, bt_status],
        )

    return demo


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    build_ui().launch(server_name="0.0.0.0", server_port=port, share=False, theme=gr.themes.Base(), css=PNS_CSS)
