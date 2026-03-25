"""
ui/dashboard.py
Gradio-based interactive dashboard for the Gold Trading Agent.

Production monitoring features:
  "Production trading agents require real-time monitoring dashboards to track
   reasoning traces, portfolio state, and risk metrics."

  - Live Reasoning Traces : Log LLM's thought process
  - Portfolio Telemetry   : Real-time price + Thai Baht conversion
  - Risk Metrics          : Sharpe, Sortino, MDD, Kelly, Half-Kelly
  - Expected Value Panel  : Win rate, EV analysis
  - Bollinger Bands       : Added to indicator panel
  - 96.5% Purity pricing  : Thai gold at correct purity
"""

import sys
import os
import gradio as gr

# Ensure sibling packages are importable when running dashboard.py directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_full_analysis() -> tuple:
    """
    Execute the complete gold analysis pipeline and return all data for the UI.

    Pipeline:
        Data APIs → Math Engine → LLM Agent → Execution → Gradio UI

    Returns:
        tuple of 18 values for all UI components.
    """
    try:
        # ── 1. Fetch price data ─────────────────────────────────────────────
        from data.fetch import get_gold_price
        df = get_gold_price()

        if df.empty:
            err = "Failed to fetch price data. Check your internet connection."
            return _error_tuple(err)

        current_price = float(df["Close"].iloc[-1])

        # ── 2. Technical indicators ─────────────────────────────────────────
        from indicators.tech import calculate_rsi, calculate_macd, calculate_bollinger_bands
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)
        bb   = calculate_bollinger_bands(df)

        rsi_signal   = "OVERBOUGHT 🔴" if rsi > 70 else "OVERSOLD 🟢" if rsi < 30 else "NEUTRAL 🟡"
        macd_trend   = "▲ BULLISH" if macd["histogram"] > 0 else "▼ BEARISH"
        bb_signal_icon = "🔴" if bb["signal"] == "OVERBOUGHT" else "🟢" if bb["signal"] == "OVERSOLD" else "🟡"

        rsi_str  = f"{rsi:.2f}  [{rsi_signal}]"
        macd_str = (f"MACD: {macd['macd']:.4f} | Signal: {macd['signal']:.4f} | "
                    f"Histogram: {macd['histogram']:.4f}  [{macd_trend}]")
        bb_str   = (f"Upper: {bb['upper']:,.2f} | Mid: {bb['middle']:,.2f} | "
                    f"Lower: {bb['lower']:,.2f} | %B: {bb['percent_b']:.2f} "
                    f"[{bb['signal']} {bb_signal_icon}]")

        # ── 3. News headlines ───────────────────────────────────────────────
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        sentiment = get_sentiment_summary(headlines)
        news_text = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        news_text += f"\n\nOverall Sentiment: {sentiment}"

        # ── 4. THB conversion (96.5% purity) ─────────────────────
        from converter.thai import convert_to_thb, format_thb
        thb_data = convert_to_thb(current_price)
        price_usd     = f"${current_price:,.2f} / troy oz"
        price_thb_gram = format_thb(thb_data["thb_per_gram"]) + " / gram  (100% pure)"
        price_thb_bw   = (
            f"{format_thb(thb_data['thb_per_baht_weight_thai'])} / baht-weight  "
            f"(96.5% Thai gold)"
        )

        # ── 5. Risk metrics ──────────────────────────────────
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        ev   = risk["ev"]

        sharpe_str     = f"{risk['sharpe']:.4f}  ({risk['sharpe_label']})"
        sortino_str    = f"{risk['sortino']:.4f}  ({risk['sortino_label']})"
        drawdown_str   = risk["drawdown_pct"]
        kelly_str      = f"Full: {risk['kelly_pct']}  |  Half-Kelly (recommended): {risk['half_kelly_pct']}"
        ev_str         = (
            f"EV: {ev['ev_pct']}  |  Win Rate: {ev['win_rate']*100:.1f}%  |  "
            f"Reward Ratio: {ev['reward_ratio']:.2f}x  "
            f"({'✅ Positive' if ev['is_positive'] else '❌ Negative'})"
        )

        # ── 6. Run Claude agent ─────────────────────────────────────────────
        from agent.claude_agent import run_agent
        agent_result = run_agent()

        decision     = agent_result.get("decision", "HOLD")
        confidence   = agent_result.get("confidence", 0)
        reasoning    = agent_result.get("reasoning", "No reasoning provided.")
        key_factors  = agent_result.get("key_factors", [])
        risk_note    = agent_result.get("risk_note", "")
        agent_trace  = agent_result.get("agent_trace", [])

        decision_html  = _decision_badge(decision, confidence)
        factors_text   = "\n".join(f"• {f}" for f in key_factors) if key_factors else "No factors listed."
        risk_note_text = f"⚠️ Risk: {risk_note}" if risk_note else ""

        # Format ReAct trace for display
        trace_text = "\n".join(agent_trace) if agent_trace else "No trace available (run agent to see)."

        status = f"✅ Analysis complete — Decision: {decision} ({confidence}% confidence)"

        return (
            price_usd, price_thb_gram, price_thb_bw,
            rsi_str, macd_str, bb_str,
            decision_html,
            reasoning, factors_text, risk_note_text,
            sharpe_str, sortino_str, drawdown_str, kelly_str, ev_str,
            news_text,
            trace_text,
            status,
        )

    except Exception as e:
        err = f"Analysis error: {str(e)}"
        print(f"[dashboard.py] {err}")
        return _error_tuple(err)


def _error_tuple(msg: str) -> tuple:
    """Return a safe all-error tuple matching the output count (18 outputs)."""
    return (
        "N/A", "N/A", "N/A",
        "N/A", "N/A", "N/A",
        _decision_badge("HOLD"),
        msg, "", "",
        "N/A", "N/A", "N/A", "N/A", "N/A",
        "No news available.",
        "No trace.",
        msg,
    )


def _decision_badge(decision: str, confidence: int = 0) -> str:
    """
    Generate an HTML-styled badge for the trading decision.

    Decisions are color-coded for instant visual clarity.
        BUY  → green  (bullish signal)
        SELL → red    (bearish signal)
        HOLD → yellow (mixed / uncertain)

    Args:
        decision (str): "BUY", "SELL", or "HOLD".
        confidence (int): Confidence percentage (0–100).

    Returns:
        str: HTML string for the badge.
    """
    styles = {
        "BUY" : ("#155724", "#d4edda", "#c3e6cb", "📈"),
        "SELL": ("#721c24", "#f8d7da", "#f5c6cb", "📉"),
        "HOLD": ("#856404", "#fff3cd", "#ffeaa7", "⏸️"),
    }
    decision_upper = decision.upper()
    text_color, bg_color, border_color, icon = styles.get(
        decision_upper, ("#555", "#eee", "#ccc", "❓")
    )
    conf_text = f"Confidence: {confidence}%" if confidence > 0 else ""

    return (
        f'<div style="text-align:center; padding:24px; border-radius:14px; '
        f'background:{bg_color}; border:3px solid {border_color}; '
        f'box-shadow:0 2px 8px rgba(0,0,0,0.1);">'
        f'<div style="font-size:3.5em; margin-bottom:8px;">{icon}</div>'
        f'<div style="font-size:2.5em; color:{text_color}; font-weight:900; '
        f'letter-spacing:4px;">{decision_upper}</div>'
        f'<div style="font-size:1.1em; color:{text_color}; margin-top:8px; '
        f'font-weight:500;">{conf_text}</div>'
        f'</div>'
    )


def build_ui() -> gr.Blocks:
    """
    Build and return the Gradio Blocks dashboard layout.

    Layout:
      - Real-time price panel (USD + THB with 96.5% Thai gold purity)
      - Technical indicators (RSI + MACD + Bollinger Bands)
      - Claude decision badge (BUY/SELL/HOLD, color-coded)
      - Reasoning + key factors + risk note
      - Risk metrics (Sharpe, Sortino, MDD, Kelly, Half-Kelly, EV)
      - News headlines with sentiment
      - Live ReAct agent trace log

    Returns:
        gr.Blocks: The configured Gradio application instance.
    """
    with gr.Blocks(
        title="Gold Trading Agent 🥇",
        theme=gr.themes.Soft(),
        css="""
            .header-text { text-align: center; }
            .metric-label { font-weight: bold; color: #444; }
            .slide-ref { font-size: 0.75em; color: #888; font-style: italic; }
            footer { display: none !important; }
        """
    ) as demo:

        # ── Header ──────────────────────────────────────────────────────────
        gr.Markdown(
            """
            # 🥇 Gold Trading Agent
            ### AI-Powered Analysis · Claude ReAct Loop

            Click **▶ Run Analysis** to start the full pipeline.
            """,
            elem_classes="header-text"
        )

        # ── Controls ────────────────────────────────────────────────────────
        with gr.Row():
            run_btn    = gr.Button("▶ Run Analysis", variant="primary", scale=2, size="lg")
            status_box = gr.Textbox(
                label="Status",
                value="Click 'Run Analysis' to begin.",
                interactive=False,
                scale=3,
            )

        # ── Price Panel ─────────────────────────────────────────────────────
        gr.Markdown("## 💰 Live Gold Price  *(Thai Gold Purity 96.5%)*")
        with gr.Row():
            price_usd      = gr.Textbox(label="USD (per troy oz)", interactive=False)
            price_thb_gram = gr.Textbox(label="THB (per gram, 100% pure)", interactive=False)
            price_thb_bw   = gr.Textbox(label="THB (per baht-weight, 96.5% Thai gold)", interactive=False)

        # ── Technical Indicators ─────────────────────────────────────────────
        gr.Markdown("## 📊 Technical Indicators  *(Pre-computed deterministically)*")
        with gr.Row():
            rsi_box  = gr.Textbox(label="RSI (14-period)", interactive=False)
            macd_box = gr.Textbox(label="MACD (EMA12 - EMA26, Signal=EMA9)", interactive=False)
        bb_box = gr.Textbox(label="Bollinger Bands (period=20, ±2σ)", interactive=False)

        # ── Claude Decision ─────────────────────────────────────────────────
        gr.Markdown("## 🤖 Claude's Recommendation  *(ReAct + Safety Bounds)*")
        decision_html = gr.HTML(value=_decision_badge("HOLD"))

        # ── Reasoning, Key Factors, Risk Note ────────────────────────────────
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### 💬 Claude's Reasoning  *(Math + Macro synthesis)*")
                reasoning_box = gr.Textbox(
                    label="",
                    value="Run analysis to see Claude's reasoning.",
                    lines=4,
                    interactive=False,
                )
            with gr.Column(scale=1):
                gr.Markdown("### 🔑 Key Factors")
                factors_box = gr.Textbox(label="", value="", lines=4, interactive=False)

        risk_note_box = gr.Textbox(
            label="⚠️ Risk Note  (Safety Bounds)",
            value="",
            interactive=False,
        )

        # ── Risk Metrics ─────────────────────────────────────────────────────
        gr.Markdown("## ⚖️ Risk Metrics  *(Sharpe · Sortino · MDD · Kelly · EV)*")
        with gr.Row():
            sharpe_box   = gr.Textbox(label="Sharpe Ratio", interactive=False)
            sortino_box  = gr.Textbox(label="Sortino Ratio (downside only)", interactive=False)
            drawdown_box = gr.Textbox(label="Max Drawdown", interactive=False)
        with gr.Row():
            kelly_box = gr.Textbox(
                label="Kelly Criterion — Half-Kelly recommended for LLM agents",
                interactive=False,
            )
            ev_box = gr.Textbox(
                label="Expected Value Analysis  (EV = W×R_W - L×R_L)",
                interactive=False,
            )

        # ── News Headlines ───────────────────────────────────────────────────
        gr.Markdown("## 📰 Latest Gold News  *(The LLM Advantage: macro catalysts)*")
        news_box = gr.Textbox(
            label="",
            value="News will appear after analysis.",
            lines=6,
            interactive=False,
        )

        # ── ReAct Agent Trace ─────────────────────────────────────
        gr.Markdown(
            "## 🔍 ReAct Agent Trace  *(Live Reasoning Traces)*  "
            "<span class='slide-ref'>τ = (s₀, t₁, a₁, o₁, ..., aₙ, oₙ)</span>"
        )
        trace_box = gr.Textbox(
            label="",
            value="Agent trace will appear here after analysis.",
            lines=8,
            interactive=False,
        )

        # ── Disclaimer ───────────────────────────────────────────────────────
        gr.Markdown(
            """
            ---
            ⚠️ **Disclaimer**: This is a university project for educational purposes only.
            This is **NOT financial advice**. Always consult a licensed financial advisor.
            Past performance does not guarantee future results.
            """,
            elem_classes="header-text"
        )

        # ── Event wiring (18 outputs) ────────────────────────────────────────
        outputs = [
            price_usd, price_thb_gram, price_thb_bw,        # 3
            rsi_box, macd_box, bb_box,                       # 3
            decision_html,                                   # 1
            reasoning_box, factors_box, risk_note_box,      # 3
            sharpe_box, sortino_box, drawdown_box,           # 3
            kelly_box, ev_box,                               # 2
            news_box,                                        # 1
            trace_box,                                       # 1
            status_box,                                      # 1  → total: 18
        ]

        run_btn.click(fn=run_full_analysis, inputs=[], outputs=outputs)

    return demo


# ─────────────────────────────────────────────────────────────
# Standalone testing
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    demo = build_ui()
    demo.launch(server_port=7860, share=False)
