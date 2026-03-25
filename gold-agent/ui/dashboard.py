"""
ui/dashboard.py
Gradio dashboard for the Gold Trading Agent.
"""

import sys
import os
import gradio as gr

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_full_analysis() -> tuple:
    """
    Run the full pipeline and return values for all UI components.

    Returns:
        tuple: (price_usd, price_thb, rsi, macd, decision_html,
                reasoning, sharpe, drawdown, kelly, news, status)
    """
    try:
        # 1. Price
        from data.fetch import get_gold_price
        df = get_gold_price()
        if df.empty:
            return _error_tuple("Failed to fetch price. Check internet connection.")

        current_price = float(df["Close"].iloc[-1])

        # 2. Indicators
        from indicators.tech import calculate_rsi, calculate_macd
        rsi  = calculate_rsi(df)
        macd = calculate_macd(df)

        rsi_signal = "Overbought 🔴" if rsi > 70 else "Oversold 🟢" if rsi < 30 else "Neutral 🟡"
        macd_trend = "▲ Bullish" if macd["histogram"] > 0 else "▼ Bearish"
        rsi_str  = f"{rsi:.1f}  —  {rsi_signal}"
        macd_str = f"Histogram: {macd['histogram']:.4f}  —  {macd_trend}"

        # 3. News
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(5)
        news_text = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))

        # 4. THB conversion
        from converter.thai import convert_to_thb, format_thb
        thb = convert_to_thb(current_price)
        price_usd = f"${current_price:,.2f}"
        price_thb = f"{format_thb(thb['thb_per_baht_weight_thai'])}  (96.5% purity)"

        # 5. Risk metrics
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        sharpe_str   = f"{risk['sharpe']:.2f}  ({risk['sharpe_label']})"
        drawdown_str = risk["drawdown_pct"]
        kelly_str    = f"{risk['half_kelly_pct']}  of portfolio"

        # 6. Claude agent
        from agent.claude_agent import run_agent
        result = run_agent()
        decision   = result.get("decision", "HOLD")
        confidence = result.get("confidence", 0)
        reasoning  = result.get("reasoning", "No reasoning available.")

        status = f"Done  —  {decision}  ({confidence}% confidence)"

        return (
            price_usd, price_thb,
            rsi_str, macd_str,
            _decision_badge(decision, confidence),
            reasoning,
            sharpe_str, drawdown_str, kelly_str,
            news_text,
            status,
        )

    except Exception as e:
        return _error_tuple(f"Error: {e}")


def _error_tuple(msg: str) -> tuple:
    """Return safe defaults for all 11 outputs on error."""
    return (
        "N/A", "N/A",
        "N/A", "N/A",
        _decision_badge("HOLD"),
        msg,
        "N/A", "N/A", "N/A",
        "No news available.",
        msg,
    )


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


def build_ui() -> gr.Blocks:
    """Build and return the Gradio dashboard."""
    with gr.Blocks(
        title="Gold Trading Agent 🥇",
        theme=gr.themes.Soft(),
        css="footer { display:none !important; } .center { text-align:center; }"
    ) as demo:

        # Header
        gr.Markdown("# 🥇 Gold Trading Agent", elem_classes="center")
        gr.Markdown("AI-powered gold market analysis — Click **Run Analysis** to start.",
                    elem_classes="center")

        # Run button + status
        with gr.Row():
            run_btn    = gr.Button("▶  Run Analysis", variant="primary", scale=1, size="lg")
            status_box = gr.Textbox(label="Status", value="Ready.", interactive=False, scale=3)

        gr.Markdown("---")

        # Price
        gr.Markdown("## 💰 Live Price")
        with gr.Row():
            price_usd = gr.Textbox(label="USD / troy oz", interactive=False)
            price_thb = gr.Textbox(label="THB / baht-weight", interactive=False)

        # Indicators
        gr.Markdown("## 📊 Indicators")
        with gr.Row():
            rsi_box  = gr.Textbox(label="RSI (14)", interactive=False)
            macd_box = gr.Textbox(label="MACD", interactive=False)

        gr.Markdown("---")

        # Decision
        gr.Markdown("## 🤖 Recommendation")
        decision_html = gr.HTML(value=_decision_badge("HOLD"))

        # Reasoning
        reasoning_box = gr.Textbox(
            label="Claude's Reasoning",
            value="Run analysis to see the recommendation.",
            lines=4,
            interactive=False,
        )

        gr.Markdown("---")

        # Risk
        gr.Markdown("## ⚖️ Risk")
        with gr.Row():
            sharpe_box   = gr.Textbox(label="Sharpe Ratio", interactive=False)
            drawdown_box = gr.Textbox(label="Max Drawdown (90 days)", interactive=False)
            kelly_box    = gr.Textbox(label="Suggested Position Size", interactive=False)

        gr.Markdown("---")

        # News
        gr.Markdown("## 📰 Gold News")
        news_box = gr.Textbox(
            label="",
            value="News will appear after analysis.",
            lines=6,
            interactive=False,
        )

        # Disclaimer
        gr.Markdown(
            "⚠️ *For educational purposes only — not financial advice.*",
            elem_classes="center"
        )

        # Wire up
        outputs = [
            price_usd, price_thb,
            rsi_box, macd_box,
            decision_html,
            reasoning_box,
            sharpe_box, drawdown_box, kelly_box,
            news_box,
            status_box,
        ]
        run_btn.click(fn=run_full_analysis, inputs=[], outputs=outputs)

    return demo


if __name__ == "__main__":
    build_ui().launch(server_port=7860, share=False)
