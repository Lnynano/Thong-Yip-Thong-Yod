"""
ui/dashboard.py
Gradio dashboard for the Gold Trading Agent.

Features:
  - Auto-refreshes every 5 minutes (gr.Timer)
  - Runs automatically on page load
  - Price + RSI chart (matplotlib)
  - Live USD/THB exchange rate
  - Rotating mock news headlines
  - Fetch timestamp on every price display
  - Sentiment badge on news section
  - Clear API-key-missing message in UI
  - Kelly with plain-English context label
  - Analysis log table (records every run to CSV)
"""

import sys
import os
import numpy as np
import gradio as gr

import matplotlib
matplotlib.use("Agg")          # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

AUTO_REFRESH_SECONDS = 300     # 5 minutes


# ─────────────────────────────────────────────────────────────
# Chart builder
# ─────────────────────────────────────────────────────────────
def _build_chart(df) -> plt.Figure:
    """
    Build a two-panel matplotlib figure: gold price + RSI.

    Top panel  : 90-day closing price line with 20-day SMA overlay.
    Bottom panel: RSI (14) with overbought (70) and oversold (30) bands.

    Args:
        df (pd.DataFrame): DataFrame with 'Close' column indexed by date.

    Returns:
        plt.Figure: Matplotlib figure ready for gr.Plot.
    """
    # Strip timezone from index so matplotlib doesn't complain
    plot_df = df.copy()
    if hasattr(plot_df.index, "tz") and plot_df.index.tz is not None:
        plot_df.index = plot_df.index.tz_localize(None)

    close = plot_df["Close"]
    sma20 = close.rolling(20).mean()

    # RSI series (Wilder's smoothing)
    delta    = close.diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs          = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series  = 100 - (100 / (1 + rs))

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.patch.set_facecolor("#ffffff")

    # ── Top panel: Price ─────────────────────────────────────
    ax1.plot(plot_df.index, close, color="#D4AF37", linewidth=2, label="Gold (XAUUSD)")
    ax1.plot(plot_df.index, sma20, color="#999", linewidth=1,
             linestyle="--", alpha=0.8, label="SMA 20")
    ax1.fill_between(plot_df.index, close, close.min() * 0.999,
                     alpha=0.07, color="#D4AF37")
    ax1.set_ylabel("USD / troy oz", fontsize=9)
    ax1.set_title("Gold Price — Last 90 Days", fontsize=11, fontweight="bold", pad=8)
    ax1.legend(fontsize=9, loc="upper left")
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor("#fafafa")

    # Latest price annotation
    last_price = float(close.iloc[-1])
    ax1.annotate(
        f"  ${last_price:,.2f}",
        xy=(plot_df.index[-1], last_price),
        fontsize=9, color="#D4AF37", fontweight="bold",
    )

    # ── Bottom panel: RSI ────────────────────────────────────
    ax2.plot(plot_df.index, rsi_series, color="#6c5ce7", linewidth=1.5)
    ax2.axhline(70, color="#e74c3c", linestyle="--", alpha=0.7, linewidth=1)
    ax2.axhline(30, color="#27ae60", linestyle="--", alpha=0.7, linewidth=1)
    ax2.fill_between(plot_df.index, rsi_series, 70,
                     where=(rsi_series >= 70), alpha=0.15, color="#e74c3c", interpolate=True)
    ax2.fill_between(plot_df.index, rsi_series, 30,
                     where=(rsi_series <= 30), alpha=0.15, color="#27ae60", interpolate=True)
    ax2.text(plot_df.index[2], 73, "Overbought", color="#e74c3c", fontsize=8, alpha=0.8)
    ax2.text(plot_df.index[2], 22, "Oversold",   color="#27ae60", fontsize=8, alpha=0.8)
    ax2.set_ylabel("RSI (14)", fontsize=9)
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.2)
    ax2.set_facecolor("#fafafa")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

    plt.tight_layout(pad=1.5)
    return fig


# ─────────────────────────────────────────────────────────────
# HTML helpers
# ─────────────────────────────────────────────────────────────
def _decision_badge(decision: str, confidence: int = 0) -> str:
    """Return a color-coded HTML badge for BUY / SELL / HOLD."""
    styles = {
        "BUY" : ("#155724", "#d4edda", "#c3e6cb", "📈"),
        "SELL": ("#721c24", "#f8d7da", "#f5c6cb", "📉"),
        "HOLD": ("#856404", "#fff3cd", "#ffeaa7", "⏸️"),
    }
    d = decision.upper()
    tc, bg, bc, icon = styles.get(d, ("#555", "#eee", "#ccc", "❓"))
    conf = f"Confidence: {confidence}%" if confidence > 0 else ""
    return (
        f'<div style="text-align:center;padding:28px;border-radius:14px;'
        f'background:{bg};border:3px solid {bc};box-shadow:0 2px 8px rgba(0,0,0,0.08);">'
        f'<div style="font-size:3em;margin-bottom:6px;">{icon}</div>'
        f'<div style="font-size:2.8em;color:{tc};font-weight:900;letter-spacing:5px;">{d}</div>'
        f'<div style="font-size:1em;color:{tc};margin-top:6px;">{conf}</div>'
        f'</div>'
    )


def _news_html(headlines: list, sentiment: str) -> str:
    """Return HTML news block with a colored sentiment badge."""
    badge_styles = {
        "BULLISH": ("#155724", "#d4edda", "📈"),
        "BEARISH": ("#721c24", "#f8d7da", "📉"),
        "NEUTRAL": ("#856404", "#fff3cd", "➡️"),
    }
    tc, bg, icon = badge_styles.get(sentiment, ("#555", "#eee", "❓"))
    badge = (
        f'<span style="background:{bg};color:{tc};padding:4px 14px;'
        f'border-radius:12px;font-weight:bold;font-size:0.9em;">'
        f'{icon} {sentiment}</span>'
    )
    items = "".join(
        f'<li style="margin:7px 0;font-size:0.95em;line-height:1.4;">{h}</li>'
        for h in headlines
    )
    return (
        f'<div style="padding:12px;">'
        f'<div style="margin-bottom:10px;">Overall Sentiment: {badge}</div>'
        f'<ol style="margin:0;padding-left:20px;">{items}</ol>'
        f'</div>'
    )


def _kelly_label(half_kelly_pct: str) -> str:
    """Add a plain-English risk label next to the Kelly percentage."""
    try:
        val = float(half_kelly_pct.replace("%", "").strip())
        if val == 0:
            label = "— do not trade"
        elif val < 3:
            label = "very small (low conviction)"
        elif val < 8:
            label = "small (moderate conviction)"
        elif val < 15:
            label = "moderate"
        else:
            label = "large — double-check signal"
        return f"{half_kelly_pct}  ({label})"
    except Exception:
        return half_kelly_pct


# ─────────────────────────────────────────────────────────────
# Main analysis pipeline
# ─────────────────────────────────────────────────────────────
def run_full_analysis() -> tuple:
    """
    Run the complete pipeline and return values for all 13 UI components.

    Pipeline: price → indicators → news → THB → risk → Claude → chart

    Returns:
        tuple of 13 values:
            price_usd, price_thb, chart_fig,
            rsi_str, macd_str,
            decision_html,
            reasoning,
            sharpe_str, drawdown_str, kelly_str,
            news_html,
            last_updated,
            status
    """
    try:
        # ── 1. Price ────────────────────────────────────────────────────────
        from data.fetch import get_gold_price, get_fetch_time
        df = get_gold_price()

        if df.empty:
            return _error_tuple("Failed to fetch price data. Check your internet connection.")

        current_price = float(df["Close"].iloc[-1])
        fetch_time    = get_fetch_time()

        # ── 2. Chart ────────────────────────────────────────────────────────
        try:
            chart_fig = _build_chart(df)
        except Exception as e:
            print(f"[dashboard.py] Chart error: {e}")
            chart_fig = None

        # ── 3. Indicators ───────────────────────────────────────────────────
        from indicators.tech import calculate_rsi, calculate_macd
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)

        rsi_signal = "Overbought 🔴" if rsi > 70 else "Oversold 🟢" if rsi < 30 else "Neutral 🟡"
        macd_trend = "▲ Bullish" if macd["histogram"] > 0 else "▼ Bearish"
        rsi_str  = f"{rsi:.1f}  —  {rsi_signal}"
        macd_str = f"Histogram: {macd['histogram']:+.2f}  —  {macd_trend}"

        # ── 4. News ─────────────────────────────────────────────────────────
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        sentiment = get_sentiment_summary(headlines)
        news_block = _news_html(headlines, sentiment)

        # ── 5. THB conversion (live rate) ───────────────────────────────────
        from converter.thai import convert_to_thb, format_thb
        thb      = convert_to_thb(current_price)
        rate_src = "live" if thb["rate_source"] == "live" else "manual"
        price_usd = f"${current_price:,.2f}  (as of {fetch_time}, 15-min delay)"
        price_thb = (
            f"{format_thb(thb['thb_per_baht_weight_thai'])} / baht-weight  "
            f"(96.5% purity · rate {thb['usd_thb_rate']:.2f} {rate_src})"
        )

        # ── 6. Risk metrics ─────────────────────────────────────────────────
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        sharpe_str   = f"{risk['sharpe']:.2f}  ({risk['sharpe_label']})"
        drawdown_str = risk["drawdown_pct"]
        kelly_str    = _kelly_label(risk["half_kelly_pct"])

        # ── 7. Claude agent ─────────────────────────────────────────────────
        from agent.claude_agent import run_agent
        agent = run_agent()

        decision   = agent.get("decision", "HOLD")
        confidence = agent.get("confidence", 0)
        reasoning  = agent.get("reasoning", "No reasoning available.")

        # Surface API key error clearly in the UI
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key or api_key == "your_key_here":
            reasoning = (
                "⚠️  ANTHROPIC_API_KEY is not set.\n"
                "Open your .env file and add:\n\n"
                "    ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "The BUY/SELL/HOLD decision above is a default HOLD until a key is configured."
            )

        last_updated = f"Last updated: {fetch_time}  (auto-refreshes every 5 min)"
        status       = f"✅  {decision}  —  {confidence}% confidence  ·  fetched {fetch_time}"

        # ── 8. Write to log ─────────────────────────────────────────────────
        from logger.trade_log import log_analysis, get_recent_logs
        log_analysis(
            decision=decision, confidence=confidence,
            price_usd=price_usd, price_thb=price_thb,
            rsi=rsi_str, macd=macd_str,
            sharpe=sharpe_str, reasoning=reasoning,
        )
        log_df = get_recent_logs(50)

        return (
            price_usd, price_thb,
            chart_fig,
            rsi_str, macd_str,
            _decision_badge(decision, confidence),
            reasoning,
            sharpe_str, drawdown_str, kelly_str,
            news_block,
            last_updated,
            status,
            log_df,
        )

    except Exception as e:
        err = f"Analysis error: {e}"
        print(f"[dashboard.py] {err}")
        return _error_tuple(err)


def _error_tuple(msg: str) -> tuple:
    """Return safe defaults for all 14 outputs on error."""
    import pandas as pd
    from logger.trade_log import get_recent_logs
    return (
        "N/A", "N/A",
        None,
        "N/A", "N/A",
        _decision_badge("HOLD"),
        msg,
        "N/A", "N/A", "N/A",
        f"<div style='padding:12px;color:#721c24;'>{msg}</div>",
        "Last updated: —",
        msg,
        get_recent_logs(50),
    )


# ─────────────────────────────────────────────────────────────
# UI layout
# ─────────────────────────────────────────────────────────────
def build_ui() -> gr.Blocks:
    """Build and return the Gradio dashboard."""
    with gr.Blocks(
        title="Gold Trading Agent 🥇",
        theme=gr.themes.Soft(),
        css="""
            .center { text-align: center; }
            .small-note { font-size: 0.8em; color: #888; }
            footer { display: none !important; }
        """,
    ) as demo:

        # ── Header ──────────────────────────────────────────────────────────
        gr.Markdown("# 🥇 Gold Trading Agent", elem_classes="center")
        gr.Markdown(
            "AI-powered gold market analysis · Updates every 5 minutes automatically",
            elem_classes="center",
        )

        gr.Markdown("---")

        # ── 1. Recommendation ───────────────────────────────────────────────
        gr.Markdown("## 🤖 Recommendation")
        decision_html = gr.HTML(value=_decision_badge("HOLD"))

        # ── 2. Status ───────────────────────────────────────────────────────
        status_box = gr.Textbox(label="Status", value="Starting...", interactive=False)

        # ── 3. Refresh button + last updated ────────────────────────────────
        with gr.Row():
            run_btn      = gr.Button("🔄  Refresh Now", variant="primary", scale=1)
            last_updated = gr.Textbox(
                label="", value="Loading...", interactive=False, scale=4,
                elem_classes="small-note",
            )

        # ── Price (fits naturally before chart) ─────────────────────────────
        with gr.Row():
            price_usd = gr.Textbox(label="USD / troy oz", interactive=False)
            price_thb = gr.Textbox(label="THB / baht-weight", interactive=False)

        gr.Markdown("---")

        # ── 4. Chart ────────────────────────────────────────────────────────
        chart = gr.Plot(label="Gold Price & RSI — 90 Days")

        # ── 5. Indicators ────────────────────────────────────────────────────
        gr.Markdown("## 📊 Indicators")
        with gr.Row():
            rsi_box  = gr.Textbox(label="RSI (14)", interactive=False)
            macd_box = gr.Textbox(label="MACD", interactive=False)

        gr.Markdown("---")

        # ── 6. Claude's Reasoning ────────────────────────────────────────────
        reasoning_box = gr.Textbox(
            label="Claude's Reasoning",
            value="Waiting for first analysis...",
            lines=4,
            interactive=False,
        )

        gr.Markdown("---")

        # ── Risk ─────────────────────────────────────────────────────────────
        gr.Markdown("## ⚖️ Risk  (90-day window)")
        with gr.Row():
            sharpe_box   = gr.Textbox(label="Sharpe Ratio", interactive=False)
            drawdown_box = gr.Textbox(label="Max Drawdown", interactive=False)
            kelly_box    = gr.Textbox(label="Suggested Position Size", interactive=False)

        gr.Markdown("---")

        # ── News ─────────────────────────────────────────────────────────────
        gr.Markdown("## 📰 Gold News")
        news_box = gr.HTML(value="<div style='padding:12px;color:#888;'>Loading news...</div>")

        gr.Markdown("---")

        # ── Analysis Log ─────────────────────────────────────────────────────
        gr.Markdown("## 📋 Analysis Log")
        log_table = gr.Dataframe(
            headers=["Timestamp", "Decision", "Confidence %", "Price USD",
                     "Price THB (baht-wt)", "RSI", "MACD", "Sharpe", "Reasoning"],
            label="",
            interactive=False,
            wrap=True,
        )
        with gr.Row():
            clear_btn = gr.Button("🗑️  Clear Log", variant="secondary", scale=1)
            gr.Markdown(
                "*Every analysis run is saved here automatically.*",
                elem_classes="small-note",
            )

        # ── Disclaimer ───────────────────────────────────────────────────────
        gr.Markdown(
            "⚠️ *For educational purposes only — not financial advice.*",
            elem_classes="center",
        )

        # ── Output list (14 total — order matches run_full_analysis return) ──
        outputs = [
            price_usd, price_thb,
            chart,
            rsi_box, macd_box,
            decision_html,
            reasoning_box,
            sharpe_box, drawdown_box, kelly_box,
            news_box,
            last_updated,
            status_box,
            log_table,
        ]

        run_btn.click(fn=run_full_analysis, inputs=[], outputs=outputs)
        demo.load(fn=run_full_analysis, inputs=[], outputs=outputs)
        gr.Timer(value=AUTO_REFRESH_SECONDS).tick(
            fn=run_full_analysis, inputs=[], outputs=outputs
        )

        # Clear log button — wipes CSV then refreshes the table
        def _clear_and_reload():
            from logger.trade_log import clear_log, get_recent_logs
            clear_log()
            return get_recent_logs(50)

        clear_btn.click(fn=_clear_and_reload, inputs=[], outputs=[log_table])

    return demo


if __name__ == "__main__":
    build_ui().launch(server_port=7860, share=False)
