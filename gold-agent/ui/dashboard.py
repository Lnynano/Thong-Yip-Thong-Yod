"""
ui/dashboard.py
Gradio-based interactive dashboard for the Gold Trading Agent.

Layout:
  - Row 1: Live gold price in USD and THB (gram + baht-weight)
  - Row 2: Technical indicators (RSI, MACD)
  - Row 3: Claude's BUY/SELL/HOLD recommendation (color-coded)
  - Row 4: Claude's reasoning trace and key factors
  - Row 5: Risk metrics (Sharpe, Max Drawdown, Kelly)
  - Row 6: News headlines
  - Footer: Refresh / Run Agent button
"""

import sys
import os
import gradio as gr

# Ensure sibling packages are importable when running dashboard.py directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_full_analysis() -> tuple:
    """
    Execute the complete gold analysis pipeline and return all data for the UI.

    Pipeline: fetch → indicators → news → converter → risk → agent

    Returns:
        tuple: (
            price_usd,          # str: formatted USD price
            price_thb_gram,     # str: formatted THB/gram price
            price_thb_bw,       # str: formatted THB/baht-weight price
            rsi_value,          # str: RSI value with signal
            macd_summary,       # str: MACD values
            decision_html,      # str: HTML-colored decision badge
            reasoning,          # str: Claude's reasoning text
            key_factors,        # str: Bullet-point key factors
            sharpe_str,         # str: Sharpe ratio with label
            drawdown_str,       # str: Max drawdown percentage
            kelly_str,          # str: Kelly criterion percentage
            news_text,          # str: Numbered headlines
            status_msg,         # str: Analysis completion status
        )
    """
    status = "Running analysis..."

    try:
        # 1. Fetch price data
        from data.fetch import get_gold_price
        df = get_gold_price()

        if df.empty:
            error_msg = "Failed to fetch price data. Check your internet connection."
            return (
                "N/A", "N/A", "N/A",
                "N/A", "N/A",
                _decision_badge("HOLD"),
                error_msg, "",
                "N/A", "N/A", "N/A",
                "No news available.",
                error_msg,
            )

        current_price = float(df["Close"].iloc[-1])

        # 2. Technical indicators
        from indicators.tech import calculate_rsi, calculate_macd
        rsi = calculate_rsi(df)
        macd = calculate_macd(df)

        rsi_signal = "OVERBOUGHT 🔴" if rsi > 70 else "OVERSOLD 🟢" if rsi < 30 else "NEUTRAL 🟡"
        rsi_str = f"{rsi:.2f}  [{rsi_signal}]"

        macd_trend = "▲ BULLISH" if macd["histogram"] > 0 else "▼ BEARISH"
        macd_str = (f"MACD: {macd['macd']:.4f} | "
                    f"Signal: {macd['signal']:.4f} | "
                    f"Histogram: {macd['histogram']:.4f}  [{macd_trend}]")

        # 3. News headlines
        from news.sentiment import get_gold_news
        headlines = get_gold_news(5)
        news_text = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))

        # 4. THB conversion
        from converter.thai import convert_to_thb, format_thb
        thb_data = convert_to_thb(current_price)
        price_usd = f"${current_price:,.2f} / troy oz"
        price_thb_gram = format_thb(thb_data["thb_per_gram"]) + " / gram"
        price_thb_bw = format_thb(thb_data["thb_per_baht_weight"]) + " / baht-weight"

        # 5. Risk metrics
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        sharpe_str = f"{risk['sharpe']:.4f}  ({risk['sharpe_label']})"
        drawdown_str = risk["drawdown_pct"]
        kelly_str = risk["kelly_pct"] + " of portfolio"

        # 6. Run Claude agent
        from agent.claude_agent import run_agent
        agent_result = run_agent()

        decision = agent_result.get("decision", "HOLD")
        confidence = agent_result.get("confidence", 0)
        reasoning = agent_result.get("reasoning", "No reasoning provided.")
        key_factors = agent_result.get("key_factors", [])

        decision_html = _decision_badge(decision, confidence)
        factors_text = "\n".join(f"• {f}" for f in key_factors) if key_factors else "No factors listed."

        status = f"Analysis complete. Decision: {decision} ({confidence}% confidence)"

        return (
            price_usd,
            price_thb_gram,
            price_thb_bw,
            rsi_str,
            macd_str,
            decision_html,
            reasoning,
            factors_text,
            sharpe_str,
            drawdown_str,
            kelly_str,
            news_text,
            status,
        )

    except Exception as e:
        error_msg = f"Analysis error: {str(e)}"
        print(f"[dashboard.py] {error_msg}")
        return (
            "Error", "Error", "Error",
            "Error", "Error",
            _decision_badge("HOLD"),
            error_msg, "",
            "Error", "Error", "Error",
            "Error fetching news.",
            error_msg,
        )


def _decision_badge(decision: str, confidence: int = 0) -> str:
    """
    Generate an HTML-styled badge for the trading decision.

    Colors:
      - BUY  → green background
      - SELL → red background
      - HOLD → yellow/orange background

    Args:
        decision (str): "BUY", "SELL", or "HOLD".
        confidence (int): Confidence percentage (0–100).

    Returns:
        str: HTML string for the badge.
    """
    colors = {
        "BUY": ("#1a7a1a", "#e6f7e6", "📈"),
        "SELL": ("#8b0000", "#fde8e8", "📉"),
        "HOLD": ("#7a5c00", "#fff8e1", "⏸️"),
    }
    decision_upper = decision.upper()
    color, bg, icon = colors.get(decision_upper, ("#555", "#eee", "❓"))

    conf_text = f" ({confidence}% confidence)" if confidence > 0 else ""

    return (
        f'<div style="text-align:center; padding:20px; border-radius:12px; '
        f'background-color:{bg}; border: 2px solid {color};">'
        f'<span style="font-size:3em; color:{color}; font-weight:bold;">'
        f'{icon} {decision_upper}</span>'
        f'<br><span style="font-size:1.2em; color:{color};">{conf_text}</span>'
        f'</div>'
    )


def build_ui() -> gr.Blocks:
    """
    Build and return the Gradio Blocks dashboard layout.

    The UI includes:
      - Gold price panel (USD + THB)
      - Technical indicator panel (RSI + MACD)
      - Claude decision panel with color-coded badge
      - Reasoning trace and key factors
      - Risk metrics panel
      - News headlines panel
      - Refresh button to re-run the full agent pipeline

    Returns:
        gr.Blocks: The configured Gradio application instance.
    """
    with gr.Blocks(
        title="Gold Trading Agent 🥇",
        theme=gr.themes.Soft(),
        css="""
            .header-text { text-align: center; }
            .metric-box { border: 1px solid #ddd; border-radius: 8px; padding: 10px; }
            footer { display: none !important; }
        """
    ) as demo:

        # ── Header ──────────────────────────────────────────────────────────
        gr.Markdown(
            """
            # 🥇 Gold Trading Agent
            **AI-powered gold market analysis using Claude + Technical Indicators**

            *Prices are fetched live from Yahoo Finance. Click **Run Analysis** to start.*
            """,
            elem_classes="header-text"
        )

        # ── Controls ────────────────────────────────────────────────────────
        with gr.Row():
            run_btn = gr.Button("▶ Run Analysis", variant="primary", scale=2)
            status_box = gr.Textbox(
                label="Status",
                value="Click 'Run Analysis' to begin.",
                interactive=False,
                scale=3,
            )

        # ── Price Panel ─────────────────────────────────────────────────────
        gr.Markdown("## 💰 Live Gold Price")
        with gr.Row():
            price_usd = gr.Textbox(label="USD (per troy oz)", interactive=False)
            price_thb_gram = gr.Textbox(label="THB (per gram)", interactive=False)
            price_thb_bw = gr.Textbox(label="THB (per baht-weight)", interactive=False)

        # ── Technical Indicators ────────────────────────────────────────────
        gr.Markdown("## 📊 Technical Indicators")
        with gr.Row():
            rsi_box = gr.Textbox(label="RSI (14-period)", interactive=False)
            macd_box = gr.Textbox(label="MACD (12,26,9)", interactive=False)

        # ── Claude Decision ─────────────────────────────────────────────────
        gr.Markdown("## 🤖 Claude's Recommendation")
        decision_html = gr.HTML(value=_decision_badge("HOLD"))

        # ── Reasoning & Key Factors ─────────────────────────────────────────
        with gr.Row():
            with gr.Column():
                gr.Markdown("### 💬 Reasoning")
                reasoning_box = gr.Textbox(
                    label="",
                    value="Run analysis to see Claude's reasoning.",
                    lines=4,
                    interactive=False,
                )
            with gr.Column():
                gr.Markdown("### 🔑 Key Factors")
                factors_box = gr.Textbox(
                    label="",
                    value="",
                    lines=4,
                    interactive=False,
                )

        # ── Risk Metrics ────────────────────────────────────────────────────
        gr.Markdown("## ⚖️ Risk Metrics (90-day)")
        with gr.Row():
            sharpe_box = gr.Textbox(label="Sharpe Ratio (annualized)", interactive=False)
            drawdown_box = gr.Textbox(label="Max Drawdown", interactive=False)
            kelly_box = gr.Textbox(label="Kelly Criterion (position size)", interactive=False)

        # ── News Headlines ───────────────────────────────────────────────────
        gr.Markdown("## 📰 Latest Gold News")
        news_box = gr.Textbox(
            label="",
            value="News will appear after analysis.",
            lines=6,
            interactive=False,
        )

        # ── Disclaimer ───────────────────────────────────────────────────────
        gr.Markdown(
            """
            ---
            ⚠️ **Disclaimer**: This is a university project for educational purposes only.
            This is NOT financial advice. Always consult a licensed financial advisor before
            making investment decisions. Past performance does not guarantee future results.
            """,
            elem_classes="header-text"
        )

        # ── Event wiring ─────────────────────────────────────────────────────
        outputs = [
            price_usd, price_thb_gram, price_thb_bw,
            rsi_box, macd_box,
            decision_html,
            reasoning_box, factors_box,
            sharpe_box, drawdown_box, kelly_box,
            news_box,
            status_box,
        ]

        run_btn.click(
            fn=run_full_analysis,
            inputs=[],
            outputs=outputs,
        )

    return demo


# Allow standalone testing
if __name__ == "__main__":
    demo = build_ui()
    demo.launch(server_port=7860, share=False)
