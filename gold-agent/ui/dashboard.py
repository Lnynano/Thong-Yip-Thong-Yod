"""
ui/dashboard.py
PNS-inspired dark trading dashboard for the Thong Yip Thong Yod.
"""

import sys, os, json, time
import html
import numpy as np
import gradio as gr
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# Thai timezone UTC+7 (no pytz needed)
THAI_TZ = timezone(timedelta(hours=7))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"

_INTERVALS = {"REAL": 1800, "TEST": 15}
_current_mode: str = "REAL"
_last_refresh_time: float = time.time()

# ─────────────────────────────────────────────────────────────
# APScheduler Setup (Background execution)
# ─────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
_scheduler_job_id = "analysis_job"
_cached_outputs = None
import threading
_init_lock = threading.Lock()

def _run_scheduled_analysis():
    """Runs the heavy analysis in the background exactly on time."""
    global _cached_outputs
    try:
        state = _load_ui_state()
        tm = state.get("trade_mode", False)
        print(f"[scheduler] Running analysis (Mode: {_current_mode}, Trade: {tm})")
        _cached_outputs = run_full_analysis(tm)
    except Exception as e:
        print(f"[scheduler] Error in scheduled analysis: {e}")

def _update_scheduler_interval():
    """Updates the background job interval when switching REAL/TEST."""
    interval = _INTERVALS.get(_current_mode, 1800)
    if scheduler.get_job(_scheduler_job_id):
        scheduler.reschedule_job(_scheduler_job_id, trigger='interval', seconds=interval)
    else:
        scheduler.add_job(_run_scheduled_analysis, 'interval', seconds=interval, id=_scheduler_job_id)
    # Trigger immediately on mode change
    scheduler.modify_job(_scheduler_job_id, next_run_time=datetime.now())

def start_scheduler():
    """Called by main.py to start the background loop."""
    if not scheduler.running:
        scheduler.start()
    _update_scheduler_interval()

def update_and_cache_analysis(trade_mode: bool = False):
    """Called by main.py background loop to update the UI globally."""
    global _cached_outputs
    with _init_lock:
        _cached_outputs = run_full_analysis(trade_mode)

def get_latest_ui():
    """Fast UI poller: returns the latest cached results without re-running analysis."""
    global _cached_outputs
    if _cached_outputs is None:
        with _init_lock:
            if _cached_outputs is None:
                _cached_outputs = run_full_analysis(_load_ui_state().get("trade_mode", False))
                
    if _cached_outputs is not None:
        # Dynamically inject the countdown timer and "Last updated" string
        out = list(_cached_outputs)
        
        # Index 2 is `last_updated`
        thai_time = datetime.fromtimestamp(_last_refresh_time, THAI_TZ).strftime("%H:%M:%S")
        interval_str = "30 min" if _current_mode == "REAL" else "15 sec"
        out[2] = f"Last updated: {thai_time} (TH)  ·  auto-refresh every {interval_str}"
        
        # Index 18 is `countdown_box`
        out[18] = _get_countdown_html()
        
        return tuple(out)
        
    return _cached_outputs

# ─────────────────────────────────────────────────────────────
# UI state persistence
# ─────────────────────────────────────────────────────────────
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_UI_STATE_PATH = os.path.join(_BASE_DIR, "data", "ui_state.json")
_UI_STATE_DEFAULTS = {"trade_mode": os.getenv("DEFAULT_TRADE_MODE", "false").lower() == "true", "refresh_mode": "REAL"}

def _load_ui_state() -> dict:
    try:
        with open(_UI_STATE_PATH, "r") as f:
            state = json.load(f)
        return {**_UI_STATE_DEFAULTS, **state}
    except Exception:
        return dict(_UI_STATE_DEFAULTS)

def _save_ui_state(**kwargs) -> None:
    try:
        state = _load_ui_state()
        state.update(kwargs)
        os.makedirs(os.path.dirname(_UI_STATE_PATH), exist_ok=True)
        with open(_UI_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

_set_trade_mode_callback = None
_set_interval_callback = None

def _set_mode(mode: str) -> None:
    global _current_mode, _last_refresh_time
    _current_mode = mode
    _last_refresh_time = time.time()
    _save_ui_state(refresh_mode=mode)
    
    if _set_interval_callback:
        interval = _INTERVALS.get(mode, 1800)
        try:
            _set_interval_callback(interval)
        except Exception as e:
            print(f"[dashboard] Failed to set interval: {e}")
            
    _update_scheduler_interval()

def sync_initial_state_to_main():
    """Called by main.py after wiring callbacks to sync the loaded state."""
    state = _load_ui_state()
    if _set_trade_mode_callback:
        _set_trade_mode_callback(state.get("trade_mode", False))
    if _set_interval_callback:
        _set_interval_callback(_INTERVALS.get(state.get("refresh_mode", "REAL"), 1800))

def _get_countdown_html() -> str:
    interval = _INTERVALS.get(_current_mode, 1800)
    next_at = _last_refresh_time + interval
    now = time.time()
    rem = max(0, int(next_at - now))
    m, s = divmod(rem, 60)
    filled = min(20, int((interval - rem) / interval * 20)) if interval > 0 else 20
    bar = "█" * filled + "░" * (20 - filled)
    color = "#c9f002" if rem < 10 else "#aaa"
    return (
        f'<div style="font-family:monospace;color:{color};padding:4px 8px;font-size:13px;">'
        f'Next refresh in {m:02d}:{s:02d} [{bar}]</div>'
    )

PNS_CSS = """
body, .gradio-container, .main, .wrap { background: #0b0b0b !important; color: #c8c8c8 !important; font-family: 'Courier New', monospace !important; }
footer, .built-with, .svelte-1gfkn6j { display: none !important; }
.gr-box, .gr-form, .gr-panel, .block, .panel, fieldset { background: #111111 !important; border: 1px solid #1e1e1e !important; border-radius: 6px !important; }
.label-wrap span, label, .gr-label { color: #555555 !important; font-size: 0.78em !important; letter-spacing: 0.12em !important; text-transform: uppercase !important; }
textarea, input[type=text], .gr-text-input { background: #111 !important; border: 1px solid #222 !important; color: #cccccc !important; }
button.primary { background: #c9f002 !important; color: #000 !important; font-weight: 900 !important; letter-spacing: 0.08em !important; border: none !important; }
button.secondary { background: #1a1a1a !important; color: #666 !important; border: 1px solid #2a2a2a !important; }
input[type="radio"] ~ span, input[type="checkbox"] ~ span { color: #cccccc !important; font-size: 0.88em !important; letter-spacing: 0.08em !important; }
input[type="radio"], input[type="checkbox"] { accent-color: #c9f002 !important; }
.svelte-table, table, .gr-dataframe table { background: #0f0f0f !important; color: #bbb !important; font-size: 0.88em !important; }
th { background: #161616 !important; color: #555 !important; text-transform: uppercase !important; font-size: 0.78em !important; letter-spacing: 0.1em !important; border-bottom: 1px solid #222 !important; }
td { border-bottom: 1px solid #1a1a1a !important; }
h1, h2, h3 { color: #888 !important; letter-spacing: 0.15em !important; text-transform: uppercase !important; }
hr { border-color: #1e1e1e !important; }
@media (max-width: 768px) { .gr-row, .row { flex-direction: column !important; flex-wrap: wrap !important; } .gradio-container { padding: 6px !important; } .block, .panel, fieldset, .gr-box, .gr-form, .gr-panel { padding: 10px !important; } }
"""

# ─────────────────────────────────────────────────────────────
# Charts & HTML Builders
# ─────────────────────────────────────────────────────────────
def _build_price_chart(df) -> plt.Figure:
    plt.close('all')
    plot_df = df.copy()
    if hasattr(plot_df.index, "tz") and plot_df.index.tz is not None:
        plot_df.index = plot_df.index.tz_localize(None)
    close = plot_df["Close"]
    sma20 = close.rolling(20).mean()
    fig, ax = plt.subplots(figsize=(12, 3), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for spine in ax.spines.values(): spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)
    ax.plot(plot_df.index, close, color="#ff7070", linewidth=1.6, zorder=3)
    ax.plot(plot_df.index, sma20, color="#444444", linewidth=1, linestyle="--", alpha=0.6, zorder=2)
    ax.fill_between(plot_df.index, close, close.min() * 0.999, alpha=0.08, color="#ff7070", zorder=1)
    ax.set_ylabel("USD / oz", color="#555", fontsize=9)
    ax.set_title("XAUUSD  —  90D", color="#555", fontsize=9, loc="left", pad=8, fontfamily="monospace")
    ax.annotate(f"  ${float(close.iloc[-1]):,.2f}", xy=(plot_df.index[-1], float(close.iloc[-1])), color="#ff7070", fontsize=9, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7, color="#444")
    plt.tight_layout(pad=1.0)
    return fig

def _build_rsi_chart(df) -> plt.Figure:
    plt.close('all')
    plot_df = df.copy()
    if hasattr(plot_df.index, "tz") and plot_df.index.tz is not None:
        plot_df.index = plot_df.index.tz_localize(None)
    close = plot_df["Close"]
    delta = close.diff()
    ag = delta.clip(lower=0).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rsi_s = 100 - (100 / (1 + ag / al.replace(0, np.nan)))
    fig, ax = plt.subplots(figsize=(12, 2), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for spine in ax.spines.values(): spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)
    ax.plot(plot_df.index, rsi_s, color="#c9f002", linewidth=1.4, zorder=3)
    ax.axhline(70, color="#cc3333", linestyle="--", alpha=0.6, linewidth=0.8)
    ax.axhline(30, color="#33aa55", linestyle="--", alpha=0.6, linewidth=0.8)
    ax.fill_between(plot_df.index, rsi_s, 70, where=(rsi_s >= 70), alpha=0.12, color="#cc3333", interpolate=True)
    ax.fill_between(plot_df.index, rsi_s, 30, where=(rsi_s <= 30), alpha=0.12, color="#33aa55", interpolate=True)
    ax.set_ylabel("RSI 14", color="#555", fontsize=8)
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7, color="#444")
    plt.tight_layout(pad=1.0)
    return fig

def _build_equity_chart(equity_history: list) -> plt.Figure:
    plt.close('all')
    fig, ax = plt.subplots(figsize=(12, 3), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for spine in ax.spines.values(): spine.set_color("#1e1e1e")
    ax.tick_params(colors="#444", labelsize=8)
    ax.grid(True, color="#1a1a1a", linewidth=0.6)
    if len(equity_history) >= 2:
        values = [e["equity"] for e in equity_history]
        xs = list(range(len(values)))
        ax.plot(xs, values, color="#c9f002", linewidth=1.8, zorder=3)
        ax.fill_between(xs, values, values[0], alpha=0.1, color="#c9f002", zorder=1)
        ax.axhline(values[0], color="#333", linestyle="--", linewidth=0.8)
        ax.set_ylabel("Equity (THB)", color="#555", fontsize=8)
        ax.set_title("P&L CURVE", color="#555", fontsize=9, loc="left", pad=6, fontfamily="monospace")
        last = values[-1]
        color = "#c9f002" if last >= values[0] else "#cc3333"
        ax.annotate(f"  ฿{last:,.2f}", xy=(xs[-1], last), color=color, fontsize=9, fontweight="bold")
    else:
        ax.text(0.5, 0.5, "No trade history yet", ha="center", va="center", color="#444", transform=ax.transAxes, fontsize=10)
    plt.tight_layout(pad=1.0)
    return fig

def _build_pl_card(portfolio: dict) -> str | None:
    import tempfile
    try:
        pnl = portfolio.get("total_pnl", 0.0)
        pnl_pct = portfolio.get("total_pnl_pct", 0.0)
        win_rate = portfolio.get("win_rate", 0.0)
        wins = portfolio.get("wins", 0)
        losses = portfolio.get("losses", 0)
        trades = portfolio.get("total_trades", 0)
        rr = portfolio.get("rr_ratio", 0.0)
        equity = portfolio.get("total_equity", 0.0)
        pnl_color = "#c9f002" if pnl >= 0 else "#cc3333"
        sign = "+" if pnl >= 0 else ""

        fig, ax = plt.subplots(figsize=(7, 3.5), facecolor="#0b0b0b")
        ax.set_facecolor("#0b0b0b")
        ax.axis("off")
        ax.text(0.04, 0.92, "THONG YIP THONG YOD", transform=ax.transAxes, color="#555", fontsize=10, fontfamily="monospace", fontweight="bold", va="top")
        ax.text(0.04, 0.80, "PAPER TRADING  ·  XAUUSD", transform=ax.transAxes, color="#333", fontsize=7, fontfamily="monospace", va="top")
        ax.text(0.04, 0.60, f"{sign}฿{pnl:,.2f}  ({sign}{pnl_pct:.2f}%)", transform=ax.transAxes, color=pnl_color, fontsize=22, fontfamily="monospace", fontweight="black", va="top")
        ax.text(0.04, 0.35, "TOTAL P&L", transform=ax.transAxes, color="#555", fontsize=7, fontfamily="monospace", va="top")

        stats = [("WIN RATE", f"{win_rate:.1f}%"), ("W / L", f"{wins} / {losses}"), ("TRADES", str(trades)), ("R:R", f"{rr:.2f}:1" if rr > 0 else "-"), ("EQUITY", f"฿{equity:,.0f}")]
        x = 0.04
        for label, val in stats:
            ax.text(x, 0.18, label, transform=ax.transAxes, color="#555", fontsize=6.5, fontfamily="monospace", va="top")
            ax.text(x, 0.10, val, transform=ax.transAxes, color="#cccccc", fontsize=9, fontfamily="monospace", fontweight="bold", va="top")
            x += 0.19
        ax.plot([0.04, 0.96], [0.03, 0.03], color="#c9f002", linewidth=1.5, transform=ax.transAxes, clip_on=False)
        plt.tight_layout(pad=0.4)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="tytyd_pl_card_")
        fig.savefig(tmp.name, dpi=150, bbox_inches="tight", facecolor="#0b0b0b", edgecolor="none")
        plt.close(fig)
        return tmp.name
    except Exception as e:
        print(f"[dashboard] P&L card generation failed: {e}")
        return None

def _price_html(price_thb, price_usd, change_thb, fetch_time, rate, rate_src) -> str:
    sign = "+" if change_thb >= 0 else ""
    color = "#c9f002" if change_thb >= 0 else "#cc3333"
    change_pct = (change_thb / (price_thb - change_thb) * 100) if (price_thb - change_thb) != 0 else 0
    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f; border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:8px;">
    {"HUA SENG HENG  ·  LIVE" if rate_src == "hsh" else "XAUUSD  ·  YFINANCE (CONVERTED)"}  ·  GOLD (THB/BAHT-WEIGHT 96.5%)
  </div>
  <div style="display:flex; align-items:baseline; gap:20px; flex-wrap:wrap;">
    <span style="color:#ffffff; font-size:3.2em; font-weight:900; letter-spacing:-1px;">฿{price_thb:,.2f}</span>
    <span style="color:{color}; font-size:1.3em; font-weight:700;">{sign}{change_thb:,.2f} ({sign}{change_pct:.2f}%)</span>
  </div>
  <div style="color:#444; font-size:0.78em; margin-top:8px; letter-spacing:0.05em;">
    ${price_usd:,.2f} / troy oz &nbsp;·&nbsp; {"HSH live price" if rate_src == "hsh" else f"rate {rate:.2f} ({html.escape(str(rate_src))})"} &nbsp;·&nbsp; as of {html.escape(str(fetch_time))}
  </div>
</div>"""

def _trade_mode_html(trade_mode: bool) -> str:
    from trader.trade_scheduler import current_window_quota_met, _current_window, _load_state
    window = _current_window()
    quota_met = current_window_quota_met()
    used = 0
    min_needed = 2
    
    if window:
        state = _load_state()
        used = state.get("windows", {}).get(window["name"], 0)
        min_needed = window["min_trades"]
        
    if not window:
        quota_text = f"<span style='color:#555555; font-weight:bold; font-size:0.85em; letter-spacing:0.1em;'>[ ⏸ OUTSIDE TRADING WINDOW ]</span>"
    elif quota_met:
        quota_text = f"<span style='color:#c9f002; font-weight:bold; font-size:0.85em; letter-spacing:0.1em;'>[ ✅ QUOTA MET : {used}/{min_needed} TRADES ]</span>"
    else:
        quota_text = f"<span style='color:#ff9900; font-weight:bold; font-size:0.85em; letter-spacing:0.1em;'>[ ⚠️ QUOTA NOT MET : {used}/{min_needed} TRADES ]</span>"

    if trade_mode:
        return f'<div style="font-family:Courier New,monospace; padding:10px 24px; background:#0d1a00; border:1px solid #2a4400; border-radius:6px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;"><span style="color:#c9f002; font-size:1.1em; font-weight:900; letter-spacing:0.15em;">● TRADE MODE : ON</span><span style="color:#555; font-size:0.78em;">Paper trades will execute automatically on BUY / SELL signals ≥ 65% confidence</span> {quota_text}</div>'
    return f'<div style="font-family:Courier New,monospace; padding:10px 24px; background:#111; border:1px solid #222; border-radius:6px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;"><span style="color:#555; font-size:1.1em; font-weight:900; letter-spacing:0.15em;">○ TRADE MODE : OFF</span><span style="color:#444; font-size:0.78em;">Analysis running — no trades will be placed</span> {quota_text}</div>'

def _decision_html(decision, confidence, reasoning, trade_mode=False, key_factors=None, risk_note="", confluence=5.0, regime="RANGING", bb_lower=0.0, bb_upper=0.0, current_price_thb=0.0) -> str:
    cfg = {"BUY": ("#c9f002", "📈"), "SELL": ("#cc3333", "📉"), "HOLD": ("#555555", "⏸")}
    color, icon = cfg.get(decision.upper(), ("#555", "?"))
    if not trade_mode and decision.upper() in ("BUY", "SELL"): color = "#666666"
    conviction, conv_color = ("HIGH", "#c9f002") if confidence >= 80 else ("MEDIUM", "#f0a002") if confidence >= 60 else ("LOW", "#cc3333")
    regime_color = {"TRENDING UP": "#c9f002", "TRENDING DOWN": "#cc3333", "VOLATILE": "#f0a002", "RANGING": "#555555"}.get(regime, "#555555")
    filled = max(0, min(10, int(round(confluence))))
    conf_bar = "█" * filled + "░" * (10 - filled)
    conf_color = "#c9f002" if confluence >= 6 else "#f0a002" if confluence >= 4 else "#cc3333"
    lines = "".join(f'<div style="margin:3px 0; color:#888; font-size:0.88em;">{html.escape(l)}</div>' for l in reasoning.split("\n") if l.strip())
    trade_tag = '<span style="color:#c9f002; font-size:0.72em; letter-spacing:0.1em; border:1px solid #2a4400; padding:2px 8px; border-radius:3px; background:#0d1a00;">WILL TRADE</span>' if trade_mode and decision.upper() in ("BUY", "SELL") and confidence >= 65 else '<span style="color:#444; font-size:0.72em; letter-spacing:0.1em; border:1px solid #222; padding:2px 8px; border-radius:3px;">ANALYSIS ONLY</span>'
    
    factors_html = ""
    if key_factors:
        items = "".join(f'<div style="color:#666; font-size:0.82em; margin:2px 0;">▸ {html.escape(f)}</div>' for f in key_factors[:4])
        factors_html = f'<div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e1e1e;"><div style="color:#444; font-size:0.68em; letter-spacing:0.1em; margin-bottom:6px;">KEY FACTORS</div>{items}</div>'
    
    risk_html = f'<div style="margin-top:8px; color:#555; font-size:0.8em;">⚠ {html.escape(risk_note)}</div>' if risk_note and risk_note.strip() else ""
    
    sltp_html = ""
    if current_price_thb > 0 and bb_lower > 0 and bb_upper > 0:
        sl_thb, tp_thb = (bb_lower, bb_upper) if decision.upper() == "BUY" else (bb_upper, bb_lower) if decision.upper() == "SELL" else (0.0, 0.0)
        if sl_thb > 0 and tp_thb > 0:
            sltp_html = f'<div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e1e1e; display:flex; gap:24px; flex-wrap:wrap;"><div><div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">ENTRY ZONE</div><div style="color:#aaa; font-size:0.9em;">฿{current_price_thb:,.0f}</div></div><div><div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">SL (BB BAND)</div><div style="color:#cc3333; font-size:0.9em;">฿{sl_thb:,.0f}</div></div><div><div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">TP (BB BAND)</div><div style="color:#c9f002; font-size:0.9em;">฿{tp_thb:,.0f}</div></div></div>'

    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f; border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:10px;">AGENT RECOMMENDATION</div>
  <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
    <span style="color:{color}; font-size:2.8em; font-weight:900; letter-spacing:6px;">{icon} {decision.upper()}</span>
    <div><div style="color:{color}; font-size:1em;">Confidence: {confidence}%</div><div style="color:{conv_color}; font-size:0.75em; letter-spacing:0.12em; font-weight:700;">CONVICTION: {conviction}</div></div>
    {trade_tag}
  </div>
  <div style="margin-top:12px; display:flex; gap:24px; flex-wrap:wrap; align-items:center;">
    <div><div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">CONFLUENCE</div><div style="color:{conf_color}; font-size:0.82em; font-family:'Courier New',monospace;">{conf_bar}  {confluence:.1f}/10</div></div>
    <div><div style="color:#444; font-size:0.68em; letter-spacing:0.1em;">MARKET REGIME</div><div style="color:{regime_color}; font-size:0.82em; font-weight:700;">{regime}</div></div>
  </div>
  {sltp_html}
  <div style="margin-top:14px; border-top:1px solid #1e1e1e; padding-top:12px;">{lines}</div>
  {factors_html}{risk_html}
</div>"""

def _portfolio_html(p: dict) -> str:
    eq_color = "#c9f002" if p["total_pnl"] >= 0 else "#cc3333"
    rl_color = "#c9f002" if p["realized_pnl"] >= 0 else "#cc3333"
    ur_color = "#c9f002" if p["unrealized_pnl"] >= 0 else "#cc3333"
    sign = lambda v: "+" if v >= 0 else ""
    pos_block = ""
    if p["open_position"]:
        op = p["open_position"]
        oc = "#c9f002" if op["unrealized"] >= 0 else "#cc3333"
        pos_block = f'<div style="margin-top:14px; border-top:1px solid #1e1e1e; padding-top:12px; color:#555; font-size:0.78em;">OPEN POSITION &nbsp;·&nbsp; Entry ฿{op["entry_price"]:,.0f} &nbsp;·&nbsp; Size {op["size_bw"]:.5f} bw &nbsp;·&nbsp; Unrealised <span style="color:{oc};">{sign(op["unrealized"])}฿{op["unrealized"]:,.2f} ({sign(op["unrealized_pct"])}{op["unrealized_pct"]:.2f}%)</span> &nbsp;·&nbsp; Since {op["entry_time"]}</div>'
    def stat(label, value, color="#c8c8c8"):
        return f'<div style="min-width:120px;"><div style="color:#555; font-size:0.65em; letter-spacing:0.1em; margin-bottom:4px;">{label}</div><div style="color:{color}; font-size:1.25em; font-weight:700;">{value}</div></div>'
    return f"""
<div style="font-family:'Courier New',monospace; padding:20px 24px; background:#0f0f0f; border:1px solid #1e1e1e; border-radius:6px;">
  <div style="color:#555; font-size:0.72em; letter-spacing:0.15em; margin-bottom:14px;">PORTFOLIO  &nbsp;·&nbsp; PAPER TRADING</div>
  <div style="display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start;">
    {stat("TOTAL EQUITY", f"฿{p['total_equity']:,.2f}", eq_color if p['total_pnl'] != 0 else '#c8c8c8')}
    {stat("REALIZED P&L", f"{sign(p['realized_pnl'])}฿{p['realized_pnl']:,.2f}", rl_color)}
    {stat("UNREALIZED", f"{sign(p['unrealized_pnl'])}฿{p['unrealized_pnl']:,.2f}", ur_color)}
    {stat("WIN RATE", f"{p['win_rate']:.1f}%", '#c9f002' if p['win_rate'] >= 50 else '#cc3333')}
    {stat("W / L", f"{p['wins']} / {p['losses']}")}
    {stat("TRADES", str(p['total_trades']))}
    {stat("R:R", f"{p['rr_ratio']:.2f}:1" if p['rr_ratio'] > 0 else "—")}
    {stat("BALANCE", f"฿{p['initial_balance']:,.0f}", "#555")}
    {stat("LLM COST", f"฿{p.get('llm_cost_thb', 0):,.2f}", '#cc3333' if p.get('llm_cost_thb', 0) > 50 else '#888')}
    {stat("NET BUDGET", f"฿{p.get('net_budget', p['initial_balance']):,.2f}", '#c9f002' if p.get('net_budget', 1500) > 1400 else '#cc3333')}
  </div>
  {pos_block}
</div>"""

def _outcome_bar_html(outcomes: list) -> str:
    if not outcomes: return '<div style="color:#333; font-size:0.8em; padding:8px;">No trades yet</div>'
    squares = "".join(f'<span style="display:inline-block; width:18px; height:18px; background:{"#c9f002" if o == "WIN" else "#cc3333"}; margin:2px; border-radius:2px;" title="{o}"></span>' for o in outcomes)
    return f'<div style="padding:8px 0;">{squares}</div>'

def _trade_table_html(trades: list, open_position: dict | None = None, filter_mode: str = "ALL") -> str:
    if filter_mode == "WIN": trades = [t for t in trades if t.get("outcome") == "WIN"]
    elif filter_mode == "LOSS": trades = [t for t in trades if t.get("outcome") == "LOSS"]
    if not trades and not open_position: return '<div style="color:#333; font-size:0.85em; padding:16px; font-family:Courier New,monospace;">No closed trades yet.</div>'
    rows = ""
    if open_position:
        unreal, unreal_pct = open_position.get("unrealized", 0), open_position.get("unrealized_pct", 0)
        sign, unreal_col = ("+" if unreal >= 0 else ""), ("#c9f002" if unreal >= 0 else "#cc3333")
        rows += f'<tr style="background:#0d1a0d; border-left:3px solid #c9f002;"><td style="color:#c9f002; padding:6px 10px; font-size:0.8em;">{open_position.get("entry_time", "")[:16]}</td><td style="color:#c9f002; font-weight:700; padding:6px 10px;">OPEN ▶</td><td style="color:#aaa; padding:6px 10px;">฿{open_position["entry_price"]:,.0f}</td><td style="color:#444; padding:6px 10px;">—</td><td style="color:#777; padding:6px 10px;">{open_position["size_bw"]:.5f} bw</td><td style="color:{unreal_col}; font-weight:700; padding:6px 10px;">{sign}฿{unreal:,.2f} ({sign}{unreal_pct:.2f}%)</td></tr>'
    for t in trades:
        oc, sign = ("#c9f002" if t["outcome"] == "WIN" else "#cc3333"), ("+" if t["pnl_thb"] >= 0 else "")
        rows += f'<tr><td style="color:#555; padding:6px 10px;">{t.get("exit_time", "—")[:16]}</td><td style="color:{oc}; font-weight:700; padding:6px 10px;">{t["outcome"]}</td><td style="color:#888; padding:6px 10px;">฿{t["entry_price"]:,.0f}</td><td style="color:#888; padding:6px 10px;">฿{t["exit_price"]:,.0f}</td><td style="color:#777; padding:6px 10px;">{t["size_bw"]:.5f} bw</td><td style="color:{oc}; font-weight:700; padding:6px 10px;">{sign}฿{t["pnl_thb"]:,.2f} ({sign}{t["pnl_pct"]:.2f}%)</td></tr>'
    return f'<div style="font-family:\'Courier New\',monospace; overflow-x:auto;"><table style="width:100%; border-collapse:collapse; font-size:0.83em; background:#0f0f0f; color:#bbb;"><thead><tr style="border-bottom:1px solid #222;"><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">TIME</th><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">RESULT</th><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">ENTRY</th><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">EXIT</th><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">SIZE</th><th style="color:#444; text-align:left; padding:8px 10px; letter-spacing:0.1em; font-size:0.75em;">P&L</th></tr></thead><tbody>{rows}</tbody></table></div>'

def _news_html(headlines: list, sentiment: str) -> str:
    col, sym = {"BULLISH": ("#c9f002", "▲"), "BEARISH": ("#cc3333", "▼"), "NEUTRAL": ("#888", "—")}.get(sentiment, ("#888", "—"))
    items = "".join(f'<div style="padding:5px 0; border-bottom:1px solid #1a1a1a; color:#888; font-size:0.88em;">{i+1}. {h}</div>' for i, h in enumerate(headlines))
    return f'<div style="font-family:\'Courier New\',monospace; padding:16px 20px; background:#0f0f0f; border:1px solid #1e1e1e; border-radius:6px;"><div style="margin-bottom:10px;"><span style="color:#555; font-size:0.7em; letter-spacing:0.1em;">SENTIMENT &nbsp;</span><span style="color:{col}; font-weight:700; font-size:0.9em;">{sym} {sentiment}</span></div>{items}</div>'

# ─────────────────────────────────────────────────────────────
# Main analysis pipeline
# ─────────────────────────────────────────────────────────────
def run_full_analysis(trade_mode: bool = False) -> tuple:
    global _last_refresh_time
    _last_refresh_time = time.time()

    try:
        from data.fetch import get_gold_price, get_fetch_time
        df = get_gold_price()
        if df.empty: return _error_outputs("Failed to fetch price data.", trade_mode)

        price_usd = float(df["Close"].iloc[-1])
        prev_usd = float(df["Close"].iloc[-2]) if len(df) > 1 else price_usd
        fetch_time = get_fetch_time()

        try: price_chart_fig = _build_price_chart(df)
        except Exception: price_chart_fig = None
        try: rsi_chart_fig = _build_rsi_chart(df)
        except Exception: rsi_chart_fig = None

        from indicators.tech import calculate_rsi, calculate_macd, calculate_bollinger_bands, calculate_confluence_score, calculate_market_regime
        rsi = calculate_rsi(df)
        macd = calculate_macd(df)
        bb = calculate_bollinger_bands(df)
        rsi_signal = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
        macd_signal = "BULLISH" if macd["histogram"] > 0 else "BEARISH"
        rsi_str = f"{rsi:.1f}  —  {rsi_signal}"
        macd_str = f"{macd['histogram']:+.2f}  —  {macd_signal}"
        regime = calculate_market_regime(df)

        dxy_str, vix_str = "N/A", "N/A"
        try:
            from data.fetch import get_macro_indicators
            macro = get_macro_indicators()
            if macro.get("dxy"): dxy_str = macro["dxy"]["label"]
            if macro.get("vix"): vix_str = macro["vix"]["label"]
        except Exception: pass

        indicators_str = f"RSI {rsi:.1f} {rsi_signal}  ·  MACD {macd['histogram']:+.3f} {macd_signal}  ·  DXY {dxy_str}  ·  VIX {vix_str}"

        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        sentiment = get_sentiment_summary(headlines)
        news_block = _news_html(headlines, sentiment)

        from data.fetch import get_hsh_price
        from converter.thai import convert_to_thb, fetch_live_usd_thb_rate, TROY_OZ_TO_GRAMS, GRAMS_PER_BAHT_WEIGHT, THAI_GOLD_PURITY
        hsh = get_hsh_price()
        if hsh:
            thb_now = hsh["sell"]
            rate_src = "hsh"
            thb_prev = thb_now * (prev_usd / price_usd) if price_usd > 0 else thb_now
            try:
                _usd_thb = fetch_live_usd_thb_rate()
                if _usd_thb > 0:
                    price_usd = round(hsh["sell"] * TROY_OZ_TO_GRAMS / (_usd_thb * GRAMS_PER_BAHT_WEIGHT * THAI_GOLD_PURITY), 2)
                    rate = _usd_thb
                else: rate = 0.0
            except Exception: rate = 0.0
        else:
            thb = convert_to_thb(price_usd)
            thb_now = thb["thb_per_baht_weight_thai"]
            thb_prev = thb_now * (prev_usd / price_usd) if price_usd > 0 else thb_now
            rate = thb["usd_thb_rate"]
            rate_src = thb["rate_source"]
        change = thb_now - thb_prev

        from trader.paper_engine import _load
        p_state = _load()
        num_open = len(p_state.get("open_positions", []))

        from agent.trading_agent import run_agent
        from trader.trade_scheduler import can_trade_now, trades_remaining_today, minutes_until_window_end, current_window_quota_met, record_trade
        _quota_pressure = can_trade_now() and not current_window_quota_met()
        agent = run_agent(quota_pressure=_quota_pressure, open_positions=num_open)
        decision = agent.get("decision", "HOLD")
        confidence = agent.get("confidence", 0)
        reasoning = agent.get("reasoning", "No reasoning.")

        failsafe_triggered = False

        _mins_left = minutes_until_window_end()
        if (decision == "HOLD" and can_trade_now() and _mins_left is not None and _mins_left <= 90 and not current_window_quota_met()):
            
            failsafe_triggered = True   # ✅ ADD
            
            agent = run_agent(quota_pressure=True, failsafe_pressure=True, open_positions=num_open)
            decision = agent.get("decision", "HOLD")
            confidence = agent.get("confidence", 0)
            reasoning = agent.get("reasoning", "No reasoning.")
            
            if decision == "HOLD":
                from trader.paper_engine import _load
                p_state = _load()
                has_positions = len(p_state.get("open_positions", [])) > 0
                
                if has_positions:
                    decision, confidence, reasoning = "SELL", 65, "[FAILSAFE] Window closing, quota not met. Forced SELL signal."
                else:
                    decision, confidence, reasoning = "BUY", 65, "[FAILSAFE] Window closing, quota not met. Forced BUY signal."

        if decision in ("BUY", "SELL") and can_trade_now(): record_trade()

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "your_key_here": reasoning = "OPENAI_API_KEY not set.\nAdd it to your .env file to enable GPT analysis."

        from trader.paper_engine import execute_paper_trade, get_portfolio_summary, get_trade_history, get_equity_history, get_recent_outcomes
        if trade_mode and can_trade_now():

            # ✅ FIX: failsafe override
            if failsafe_triggered:
                _min_conf = 50

            else:
                _min_conf = 50 if _quota_pressure else None
                
            trade_result = execute_paper_trade(decision, confidence, thb_now, min_confidence=_min_conf)
        elif trade_mode and not can_trade_now(): trade_result = {"action": "SKIP", "reason": "Outside trading window"}
        else: trade_result = {"action": "DISABLED", "reason": "Trade mode is OFF"}

        portfolio = get_portfolio_summary(thb_now)
        try:
            from logger.cost_tracker import get_cost_summary
            cost = get_cost_summary()
            portfolio["llm_cost_thb"] = cost["total_cost_thb"]
            portfolio["net_budget"] = cost["budget_remaining"]
        except Exception:
            portfolio["llm_cost_thb"] = 0.0
            portfolio["net_budget"] = portfolio["initial_balance"]

        trades = get_trade_history(20)
        equity_hist = get_equity_history()
        outcomes = get_recent_outcomes(15)
        try: eq_chart = _build_equity_chart(equity_hist)
        except Exception: eq_chart = None

        from logger.trade_log import log_analysis, get_recent_logs, send_trade_log
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        log_analysis(decision=decision, confidence=confidence, price_usd=f"${price_usd:,.2f}", price_thb=f"฿{thb_now:,.0f}", rsi=rsi_str, macd=macd_str, sharpe=f"{risk['sharpe']:.2f}", reasoning=reasoning)
        send_trade_log(action=decision, price_thb=thb_now, reason=reasoning, confidence=confidence)

        try:
            from notifier.discord_notify import send_signal
            will_trade = decision in ("BUY", "SELL") and confidence >= 65 and trade_mode
            send_signal(decision, confidence, thb_now, reasoning, will_trade=will_trade)
        except Exception as e: print(f"[discord] Error: {e}")

        log_df = get_recent_logs(50)
        price_block = _price_html(thb_now, price_usd, change, fetch_time, rate, rate_src)
        thb_per_usd_oz = thb_now / price_usd if price_usd > 0 else 0.0
        bb_lower_thb = round(bb["lower"] * thb_per_usd_oz, 0)
        bb_upper_thb = round(bb["upper"] * thb_per_usd_oz, 0)
        confluence = calculate_confluence_score(df, sentiment)

        dec_block = _decision_html(decision, confidence, reasoning, trade_mode, key_factors=agent.get("key_factors", []), risk_note=agent.get("risk_note", ""), confluence=confluence, regime=regime, bb_lower=bb_lower_thb, bb_upper=bb_upper_thb, current_price_thb=thb_now)
        port_block = _portfolio_html(portfolio)
        outcome_bar = _outcome_bar_html(outcomes)
        trade_table = _trade_table_html(trades, portfolio.get("open_position"))
        thai_now = datetime.fromtimestamp(_last_refresh_time, THAI_TZ).strftime("%H:%M:%S")
        interval_str = "30 min" if _current_mode == "REAL" else "15 sec"
        last_updated = f"Last updated: {thai_now} (TH)  ·  auto-refresh every {interval_str}"
        tm_html = _trade_mode_html(trade_mode)

        action = trade_result.get("action", "")
        if not trade_mode: status = f"📊 ANALYSIS ONLY  ·  {decision} {confidence}%  ·  Trade mode is OFF"
        elif action == "OPENED": status = f"✅ OPENED position  ·  {trade_result['size_bw']:.5f} bw @ ฿{trade_result['price_thb']:,.0f}"
        elif action == "CLOSED":
            pnl = trade_result.get("pnl_thb", 0)
            status = f"{'🟢' if pnl >= 0 else '🔴'} CLOSED  ·  P&L {'+' if pnl>=0 else ''}฿{pnl:.2f}  ·  {trade_result.get('trade', {}).get('outcome', 'WIN' if pnl >= 0 else 'LOSS')}"
        elif action == "SKIP": status = f"⏸  {trade_result.get('reason', 'No trade')}  ·  {decision} {confidence}%"
        else: status = f"HOLD  ·  no trade action  ·  fetched {fetch_time}"

        return (price_block, dec_block, last_updated, price_chart_fig, rsi_chart_fig, rsi_str, macd_str, port_block, eq_chart, outcome_bar, trade_table, news_block, log_df, indicators_str, status, tm_html, dxy_str, vix_str, _get_countdown_html())

    except Exception as e:
        err = f"Error: {e}"
        print(f"[dashboard] {err}")
        return _error_outputs(err, trade_mode)

def _error_outputs(msg: str, trade_mode: bool = False) -> tuple:
    from logger.trade_log import get_recent_logs
    from trader.paper_engine import get_portfolio_summary, get_trade_history, get_equity_history, get_recent_outcomes
    portfolio = get_portfolio_summary(0)
    port_block = _portfolio_html(portfolio)
    try: eq_chart = _build_equity_chart(get_equity_history())
    except Exception: eq_chart = None
    return (f'<div style="color:#cc3333;padding:20px;font-family:Courier New;">{msg}</div>', _decision_html("HOLD", 0, msg, trade_mode, key_factors=[], risk_note="", confluence=5.0, regime="RANGING", bb_lower=0.0, bb_upper=0.0, current_price_thb=0.0), "Last updated: —", None, None, "N/A", "N/A", port_block, eq_chart, _outcome_bar_html(get_recent_outcomes(15)), _trade_table_html(get_trade_history(20), portfolio.get("open_position")), f'<div style="color:#555;padding:16px;">{msg}</div>', get_recent_logs(50), "—", msg, _trade_mode_html(trade_mode), "N/A", "N/A", _get_countdown_html())

# ─────────────────────────────────────────────────────────────
# UI Layout
# ─────────────────────────────────────────────────────────────
def build_ui() -> gr.Blocks:
    _saved = _load_ui_state()
    _init_trade_mode: bool = _saved["trade_mode"]
    _init_refresh_mode: str = _saved["refresh_mode"]
    _set_mode(_init_refresh_mode)

    with gr.Blocks(title="Thong Yip Thong Yod") as demo:
        gr.HTML("""<div style="font-family:'Courier New',monospace; padding:14px 24px; background:#0f0f0f; border-bottom:1px solid #1e1e1e; display:flex; justify-content:space-between; align-items:center;"><span style="color:#888; font-size:1.1em; font-weight:700; letter-spacing:0.2em;"> Thong Yip Thong Yod</span><span style="color:#555; font-size:0.75em; letter-spacing:0.1em;">XAUUSD &nbsp;·&nbsp; PAPER TRADING &nbsp;·&nbsp; <span style="color:#c9f002;">● LIVE</span></span></div>""")

        with gr.Row(visible=DEV_MODE):
            trade_mode_toggle = gr.Checkbox(label="TRADE MODE  —  enable to execute paper trades automatically", value=_init_trade_mode, scale=3)
            gr.HTML('<div style="font-family:Courier New,monospace; color:#444; font-size:0.75em; padding:12px 0; line-height:1.5em;">OFF = analysis only &nbsp;|&nbsp; ON = trades execute on BUY/SELL ≥ 65% conf</div>')

        with gr.Row(visible=DEV_MODE):
            mode_radio = gr.Radio(choices=["REAL", "TEST"], value=_init_refresh_mode, label="REFRESH MODE  —  REAL = every 30 min  ·  TEST = every 15 sec", interactive=True, scale=3)
            gr.HTML('<div style="font-family:Courier New,monospace; color:#444; font-size:0.75em; padding:12px 0; line-height:1.5em;">Switch to TEST for fast 15-second cycles when market is closed</div>')

        trade_mode_status = gr.HTML()
        price_html = gr.HTML()
        decision_html = gr.HTML()

        with gr.Row():
            run_btn = gr.Button("⟳  REFRESH NOW", variant="primary", scale=1, size="sm")
            last_updated = gr.Textbox(value="Loading...", interactive=False, show_label=False, scale=5, max_lines=1)

        countdown_box = gr.HTML(value=_get_countdown_html(), elem_id="countdown-box")
        gr.HTML('<hr style="border-color:#1e1e1e; margin:4px 0;">')

        with gr.Tabs():
            with gr.Tab("Charts"):
                gr.Markdown("## PRICE")
                chart_price = gr.Plot(label="")
                gr.Markdown("## RSI")
                chart_rsi = gr.Plot(label="")
                gr.Markdown("## INDICATORS")
                with gr.Row():
                    rsi_box = gr.Textbox(label="RSI (14)", interactive=False)
                    macd_box = gr.Textbox(label="MACD Histogram", interactive=False)
                gr.Markdown("## MACRO")
                with gr.Row():
                    dxy_box = gr.Textbox(label="DXY  —  US Dollar Index  (↑ bearish gold  ·  ↓ bullish gold)", interactive=False)
                    vix_box = gr.Textbox(label="VIX  —  Fear Index  (>20 bullish gold  ·  <15 neutral)", interactive=False)

            with gr.Tab("Portfolio"):
                portfolio_html = gr.HTML()
                gr.Markdown("## P&L CURVE")
                equity_chart = gr.Plot(label="")
                with gr.Row():
                    share_btn = gr.Button("📤  SHARE P&L CARD", variant="secondary", scale=1, size="sm")
                    pl_card_file = gr.File(label="Download P&L Card", visible=False)
                with gr.Row(visible=DEV_MODE):
                    reset_btn = gr.Button("↺  RESET PORTFOLIO", variant="secondary", scale=1, size="sm")
                    gr.HTML('<div style="color:#333; font-size:0.75em; padding:8px; font-family:Courier New;">Paper trading only — no real money.</div>')

            with gr.Tab("Trades"):
                trade_filter = gr.Radio(choices=["ALL", "WIN", "LOSS"], value="ALL", label="FILTER", interactive=True)
                outcome_bar = gr.HTML()
                trade_table = gr.HTML()

            with gr.Tab("Log"):
                log_table = gr.Dataframe(headers=["Timestamp", "Decision", "Confidence %", "Price USD", "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"], label="", interactive=False, wrap=True)
                with gr.Row(visible=DEV_MODE):
                    clear_log_btn = gr.Button("🗑  CLEAR LOG", variant="secondary", scale=1, size="sm")

            with gr.Tab("News"):
                news_html = gr.HTML()

        status_box = gr.Textbox(label="STATUS  ·  last action", value="Starting...", interactive=False, max_lines=1)
        indicators_hidden = gr.Textbox(visible=False)

        outputs = [price_html, decision_html, last_updated, chart_price, chart_rsi, rsi_box, macd_box, portfolio_html, equity_chart, outcome_bar, trade_table, news_html, log_table, indicators_hidden, status_box, trade_mode_status, dxy_box, vix_box, countdown_box]

        # ── UI Sync Timer ────────────────────────────────────────────────────
        # This replaces the old gr.Timer logic. It simply fetches the latest 
        # cached results from the APScheduler background job every 2 seconds.
        # This ensures the UI updates instantly when you return to the tab.
        ui_sync_timer = gr.Timer(value=2)
        ui_sync_timer.tick(fn=get_latest_ui, inputs=[], outputs=outputs)

        # ── Manual Refresh ───────────────────────────────────────────────────
        def force_refresh(trade_mode):
            update_and_cache_analysis(trade_mode)
            # Reset scheduler timer so it doesn't double-fire immediately after
            if _set_interval_callback:
                _set_interval_callback(_INTERVALS.get(_current_mode, 1800))
            return _cached_outputs

        run_btn.click(fn=force_refresh, inputs=[trade_mode_toggle], outputs=outputs)
        demo.load(fn=get_latest_ui, inputs=[], outputs=outputs)

        mode_radio.change(fn=_set_mode, inputs=[mode_radio], outputs=[])

        def _on_trade_mode_change(enabled: bool):
            _save_ui_state(trade_mode=enabled)
            update_and_cache_analysis(enabled)
            if _set_interval_callback:
                _set_interval_callback(_INTERVALS.get(_current_mode, 1800))
            return _cached_outputs

        trade_mode_toggle.change(fn=_on_trade_mode_change, inputs=[trade_mode_toggle], outputs=outputs)

        def _reset():
            from trader.paper_engine import reset_portfolio, get_portfolio_summary, get_trade_history, get_equity_history, get_recent_outcomes
            reset_portfolio()
            p = get_portfolio_summary(0)
            try: eq = _build_equity_chart(get_equity_history())
            except Exception: eq = None
            return (_portfolio_html(p), eq, _outcome_bar_html(get_recent_outcomes(15)), _trade_table_html(get_trade_history(20), p.get("open_position"), "ALL"))
        reset_btn.click(fn=_reset, inputs=[], outputs=[portfolio_html, equity_chart, outcome_bar, trade_table])

        def _generate_pl_card():
            from trader.paper_engine import get_portfolio_summary
            path = _build_pl_card(get_portfolio_summary(0))
            return gr.File(value=path, visible=True) if path else gr.File(visible=False)
        share_btn.click(fn=_generate_pl_card, inputs=[], outputs=[pl_card_file])

        def _filter_trades(filter_mode: str):
            from trader.paper_engine import get_trade_history, get_portfolio_summary
            return _trade_table_html(get_trade_history(20), get_portfolio_summary(0).get("open_position"), filter_mode)
        trade_filter.change(fn=_filter_trades, inputs=[trade_filter], outputs=[trade_table])

        def _clear():
            from logger.trade_log import clear_log, get_recent_logs
            clear_log()
            return get_recent_logs(50)
        clear_log_btn.click(fn=_clear, inputs=[], outputs=[log_table])

    return demo

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    start_scheduler()
    build_ui().launch(server_name="0.0.0.0", server_port=port, share=False, theme=gr.themes.Base(), css=PNS_CSS)