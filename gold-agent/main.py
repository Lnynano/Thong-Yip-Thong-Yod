"""
main.py
Entry point for the Gold Trading Agent application.

End-to-end architecture:
  Data APIs → Math Engine → LLM Agent → Execution → Gradio UI

Module pipeline:
  data.fetch → indicators.tech → news.sentiment →
  converter.thai → agent.claude_agent → risk.metrics → ui.dashboard

Key design decisions:
  - Deterministic pipeline : fetch, indicators, converter, risk
  - Stochastic component   : claude_agent only
  - Safety bounds          : validated in claude_agent before display
  - AGENTS.md              : see AGENTS.md for AI-readable project rules

Usage:
    python main.py

The Gradio dashboard launches on http://localhost:7860
"""

import sys
import os

# Ensure all subpackages are importable regardless of working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))


def verify_environment() -> bool:
    """
    Verify that required environment variables are configured.

    Prints warnings for missing optional keys and errors for required keys.

    Returns:
        bool: True if the minimum required config is present, False otherwise.
    """
    print("=" * 60)
    print("  Gold Trading Agent — Environment Check")
    print("=" * 60)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_key_here":
        print("  ❌ ANTHROPIC_API_KEY: Not set (agent will return default HOLD)")
    else:
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"  ✅ ANTHROPIC_API_KEY: {masked}")

    news_key = os.getenv("NEWS_API_KEY", "")
    if not news_key or news_key == "your_key_here":
        print("  ⚠️  NEWS_API_KEY: Not set (will use mock headlines)")
    else:
        print("  ✅ NEWS_API_KEY: Configured")

    usd_thb = os.getenv("USD_THB_RATE", "34.5")
    print(f"  ✅ USD_THB_RATE: {usd_thb}")

    print("=" * 60)
    return True  # App runs even without API keys (graceful degradation)


def run_cli_test():
    """
    Run a quick command-line test of all modules without launching the UI.
    Useful for verifying module imports and basic functionality.
    """
    print("\n[main.py] Running CLI pipeline test...")

    try:
        print("\n1. Fetching gold price...")
        from data.fetch import get_gold_price, get_latest_price
        df = get_gold_price()
        price = get_latest_price()
        print(f"   ✅ Price: ${price:.2f} | Rows: {len(df)}")
    except Exception as e:
        print(f"   ❌ Fetch error: {e}")
        return

    try:
        print("\n2. Calculating indicators...")
        from indicators.tech import calculate_rsi, calculate_macd
        rsi = calculate_rsi(df)
        macd = calculate_macd(df)
        print(f"   ✅ RSI: {rsi:.2f} | MACD histogram: {macd['histogram']:.4f}")
    except Exception as e:
        print(f"   ❌ Indicators error: {e}")

    try:
        print("\n3. Fetching news...")
        from news.sentiment import get_gold_news, get_sentiment_summary
        headlines = get_gold_news(3)
        sentiment = get_sentiment_summary(headlines)
        print(f"   ✅ {len(headlines)} headlines | Sentiment: {sentiment}")
    except Exception as e:
        print(f"   ❌ News error: {e}")

    try:
        print("\n4. Converting to THB (96.5% Thai gold purity)...")
        from converter.thai import convert_to_thb
        thb = convert_to_thb(price)
        print(f"   ✅ ฿{thb['thb_per_gram']:.2f}/g (pure) | "
              f"฿{thb['thb_per_baht_weight_thai']:.2f}/baht-wt (96.5% Thai)")
    except Exception as e:
        print(f"   ❌ Converter error: {e}")

    try:
        print("\n5. Computing risk metrics...")
        from risk.metrics import calculate_risk
        risk = calculate_risk(df)
        ev = risk["ev"]
        print(f"   ✅ Sharpe: {risk['sharpe']:.4f} ({risk['sharpe_label']}) | "
              f"Sortino: {risk['sortino']:.4f} | "
              f"MaxDD: {risk['drawdown_pct']}")
        print(f"   ✅ Full Kelly: {risk['kelly_pct']} | "
              f"Half-Kelly (recommended): {risk['half_kelly_pct']} | "
              f"EV: {ev['ev_pct']} ({'Positive' if ev['is_positive'] else 'Negative'})")
    except Exception as e:
        print(f"   ❌ Risk metrics error: {e}")

    print("\n[main.py] CLI test complete. Launching Gradio UI...\n")


def main():
    """
    Main entry point: verifies environment, runs quick test, then launches UI.
    """
    verify_environment()

    # Quick sanity check of all modules
    run_cli_test()

    # Import and launch the Gradio dashboard
    try:
        from ui.dashboard import build_ui
        demo = build_ui()

        print("\n" + "=" * 60)
        print("  🥇 Gold Trading Agent is starting!")
        print("  📊 Dashboard: http://localhost:7860")
        print("  Press Ctrl+C to stop.")
        print("=" * 60 + "\n")

        demo.launch(
            server_name="0.0.0.0",   # Listen on all interfaces
            server_port=7860,
            share=False,             # Set True to get a public Gradio link
            show_error=True,
        )

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Failed to launch dashboard: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
