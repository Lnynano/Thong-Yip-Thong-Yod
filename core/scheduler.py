import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# LLM & Agent Imports
from llm.agent import ask_llm
from llm.news_agent import analyze_news_sentiment
from llm.daily_market_agent import analyze_daily_market

# Execution & Data Imports
from execution.simulator import TradingSimulator
from indicators.indicators import compute_indicators
from data.news_fetcher import save_news_to_json
from data.price_memory import add_price

# Global Instances
simulator = TradingSimulator()
scheduler = None
is_running = False
initial_capital = None

# --- CORE TRADING LOGIC ---


def trading_job():
    """Main loop that executes the research-based strategy."""
    now = datetime.now()

    # --- RULE #6: THE KILL SWITCH (April 27) ---
    if now.month == 4 and now.day == 27:
        print("🔴 PROJECT FINAL DAY: LIQUIDATING ALL POSITIONS.")
        status = simulator.get_status(0)
        if status['gold'] > 0:
            simulator.execute_trade("SELL", status['price'])
        stop_scheduler()
        return

    print(f"\n[{now.strftime('%H:%M:%S')}] Running Research-Based Cycle...")

    # 1. Fetch Price & Indicators
    indicators = compute_indicators()
    if indicators is None:
        print("⚠️ No indicators available yet. Skipping...")
        return

    price = indicators["price"]
    rsi = indicators.get("rsi", 50)

    # 2. Get Portfolio Status
    status = simulator.get_status(price)

    # 3. Check Rule #4: How many trades today?
    trades_today = simulator.get_trades_today_count()

    try:
        # 4. Get LLM Decision
        decision_raw = ask_llm(status)
        decision_data = json.loads(decision_raw.strip().replace(
            "```json", "").replace("```", ""))
        action = decision_data["action"].upper()

        # 5. Apply Research & Constraints

        # --- NEW: INSTANT ACTION LOGIC FOR RULE #4 ---
        # If we haven't traded yet today, we IGNORE "HOLD" and act immediately
        if trades_today == 0:
            print(
                "📢 INITIAL STARTUP: No trades found for today. Forcing immediate decision...")
            if status['cash'] >= 1000:
                action = "BUY"
                print(
                    "➡️ Rule #4 Override: Forcing BUY (฿1,000) to satisfy daily trade requirement.")
            elif status['gold'] > 0:
                action = "SELL"
                print(
                    "➡️ Rule #4 Override: Forcing SELL to satisfy daily trade requirement.")
            else:
                print("⚠️ Nothing to trade (No cash and no gold).")
                action = "HOLD"

        # Standard constraint for subsequent runs
        elif action == "BUY" and status['cash'] < 1000:
            print("⚠️ Suggestion was BUY, but Cash < ฿1,000. Overriding to HOLD.")
            action = "HOLD"

        # 6. Execute Action
        if action != "HOLD":
            # This triggers the simulator to save the trade to the DB
            simulator.execute_trade(action, price)
            print(f"✅ ACTION TAKEN: {action} at ฿{price:,.2f}")
            print(
                "🔔 MANUAL ACTION REQUIRED: Please perform this trade in your Aom NOW app!")
        else:
            print("😴 ACTION: HOLD (Daily requirement already met / No signals)")

        simulator.print_status(price)

    except Exception as e:
        print(f"❌ Error in decision processing: {e}")

# --- SCHEDULER CONTROLS ---


def start_scheduler():
    global scheduler, is_running, initial_capital

    if is_running:
        print("Scheduler already running")
        return

    from database.db import get_latest_portfolio
    portfolio = get_latest_portfolio()
    initial_capital = portfolio["total_value"]

    print(f"🚀 Starting scheduler with Capital: ฿{initial_capital:,.2f}")

    scheduler = BackgroundScheduler()

    # Job Timings
    scheduler.add_job(trading_job, "interval",
                      seconds=180)     # Trade every 3 mins
    scheduler.add_job(news_pipeline, "interval",
                      hours=3)      # News every 3 hours
    scheduler.add_job(analyze_daily_market, "interval",
                      hours=1)  # Market analysis
    scheduler.add_job(collect_price, "interval",
                      seconds=6)    # Price collection

    scheduler.start()
    is_running = True

    # Initial Run
    print("\n⚡ Running initial startup cycle...")
    save_news_to_json()
    trading_job()


def stop_scheduler():
    global scheduler, is_running
    if scheduler:
        scheduler.shutdown()
        print("🛑 Scheduler stopped")
    is_running = False


def reset_system():
    global scheduler, is_running, initial_capital
    from database.db import reset_database

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        print("Scheduler stopped for reset.")

    is_running = False
    reset_database()
    initial_capital = None
    print("♻️ System reset complete")

# --- UTILITY FUNCTIONS ---


def collect_price():
    indicators = compute_indicators()
    if indicators:
        price = indicators["price"]
        add_price(price)
        print(f"📈 Collected Thai Gold Price: ฿{price:,.2f}")
    else:
        print("⚠️ Price collection failed (Market closed or API error)")


def news_pipeline():
    save_news_to_json()
    analyze_news_sentiment()


def is_late_night():
    """Returns True if it is currently 8:00 PM (20:00) or later."""
    return datetime.now().hour >= 20
