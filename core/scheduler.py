from core.mode_controller import get_time_config
from core.mode_controller import (
    get_mode,
    get_next_test_price,
    load_test_data
)
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler

from llm.agent import ask_llm
from llm.news_agent import analyze_news_sentiment
from llm.daily_market_agent import analyze_daily_market

from execution.simulator import TradingSimulator
from indicators.indicators import compute_indicators

from data.news_fetcher import save_news_to_json

from data.price_memory import add_price
from data.price_memory import get_price_history

from data.price import fetch_gold_price

import json
from datetime import datetime

last_price = None

simulator = TradingSimulator()

scheduler = None
is_running = False
initial_capital = None


# ===============================
# CORE TRADING LOGIC
# ===============================

def trading_job():

    now = datetime.now()

    print(
        f"\n[{now.strftime('%H:%M:%S')}] "
        "Running trading cycle..."
    )

    indicators = compute_indicators()

    if indicators is None:

        print("⚠️ No indicators available")

        return

    price = indicators["price"]

    # ===========================
    # Portfolio Status
    # ===========================

    status = simulator.get_status(price)

    # ===========================
    # Count trades today ⭐
    # ===========================

    trades_today = simulator.get_trades_today_count()

    status["trades_today"] = trades_today

    # ===========================
    # First trade bias ⭐
    # ===========================

    if trades_today == 0:

        print(
            "🧠 First Trade Mode Active"
        )

        status["first_trade_bias"] = True

    else:

        status["first_trade_bias"] = False

    # ===========================
    # Ask LLM
    # ===========================

    try:

        decision = ask_llm(status)

        decision = decision.strip()

        # Clean markdown json

        if decision.startswith("```"):

            decision = (
                decision
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

        decision_data = json.loads(
            decision
        )

        action = decision_data[
            "action"
        ].upper()

        reason = decision_data.get(
            "reason",
            "No reason"
        )

        print(
            f"🧠 Decision: {action}"
        )

        print(
            f"📝 Reason: {reason}"
        )

        # ===========================
        # Soft Constraints ⭐
        # ===========================

        if (
            action == "BUY"
            and status["cash"] < 1000
        ):

            print(
                "⚠️ BUY rejected "
                "(cash too low)"
            )

            action = "HOLD"

        if (
            action == "SELL"
            and status["gold"] <= 0
        ):

            print(
                "⚠️ SELL rejected "
                "(no gold)"
            )

            action = "HOLD"

        # ===========================
        # Execute Trade
        # ===========================

        if action != "HOLD":

            simulator.execute_trade(
                action,
                price
            )

            print(
                f"✅ EXECUTED "
                f"{action} @ {price}"
            )

        else:

            print("😴 HOLD")

        simulator.print_status(price)

    except Exception as e:

        print(
            f"❌ Decision Error: {e}"
        )


# ===============================
# PRICE COLLECTION
# ===============================


def collect_price():

    mode = get_mode()

    if mode == "TEST":

        price = get_next_test_price()

        if price is None:

            print("No test price")

            return

    else:

        indicators = compute_indicators()

        price = indicators["price"]

    add_price(price)

    print("📈 Price collected:", price)


# ===============================
# NEWS PIPELINE
# ===============================

def news_pipeline():

    save_news_to_json()

    analyze_news_sentiment()


# ===============================
# SCHEDULER CONTROL
# ===============================


def start_scheduler():

    global scheduler
    global is_running
    global initial_capital

    config = get_time_config()
    price_interval = config["price_interval"]
    trade_interval = config["trade_interval"]

    if is_running:
        print("Scheduler already running")
        return

    from database.db import get_latest_portfolio
    portfolio = get_latest_portfolio()
    initial_capital = portfolio["total_value"]

    print(
        "🚀 Initial Capital:",
        initial_capital
    )

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        collect_price,
        "interval",
        seconds=price_interval
    )

    scheduler.add_job(
        trading_job,
        "interval",
        seconds=trade_interval
    )

    scheduler.add_job(
        news_pipeline,
        "interval",
        hours=3
    )

    scheduler.add_job(
        analyze_daily_market,
        "interval",
        hours=1
    )

    print("\nFetching news at startup...")
    save_news_to_json()

    print("\nRunning first cycle...")
    trading_job()

    print("\nRunning daily market analysis...")
    analyze_daily_market()

    scheduler.start()
    is_running = True
    print("✅ Scheduler started in background.")


def stop_scheduler():

    global scheduler
    global is_running
    print("Stopping scheduler...")

    if scheduler is not None:
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
                print("✅ Scheduler shut down successfully.")
            else:
                print("ℹ️ Scheduler exists but is not running.")
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")
    else:
        print("ℹ️ No scheduler instance found to stop.")

    scheduler = None
    is_running = False


def reset_system():

    global scheduler
    global is_running
    global initial_capital

    from database.db import reset_database

    if scheduler:

        scheduler.shutdown()

        print("Scheduler stopped")

    is_running = False

    reset_database()

    initial_capital = None

    print("♻️ System reset complete")


def start_test_mode():

    global scheduler
    global is_running

    print("🧪 Starting TEST MODE")

    stop_scheduler()

    from core.mode_controller import set_mode
    set_mode("TEST")

    print("📊 Loading test data...")
    load_test_data()

    start_scheduler()
