from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from llm.agent import ask_llm
from llm.news_agent import analyze_news_sentiment
from llm.daily_market_agent import analyze_daily_market

from execution.simulator import TradingSimulator
from indicators.indicators import compute_indicators

from data.news_fetcher import save_news_to_json

from data.price_memory import add_price
from indicators.indicators import compute_indicators

import json


simulator = TradingSimulator()

scheduler = BackgroundScheduler()

is_running = False
scheduler = None
initial_capital = None


def trading_job():

    print("\nRunning trading cycle...")

    indicators = compute_indicators()

    if indicators is None:

        print("No indicators available")

        return

    price = indicators["price"]

    status = simulator.get_status(price)

    decision = ask_llm(status)

    print("Decision:", decision)

    decision = decision.strip()

    # ลบ ```json ``` ถ้ามี
    if decision.startswith("```"):

        decision = decision.replace("```json", "")
        decision = decision.replace("```", "")
        decision = decision.strip()

    decision_data = json.loads(decision)

    simulator.execute_trade(
        decision_data["action"],
        price
    )

    simulator.print_status(price)


def start_scheduler():

    global scheduler
    global is_running
    global initial_capital

    from database.db import get_latest_portfolio

    portfolio = get_latest_portfolio()

    initial_capital = portfolio["total_value"]

    print("Initial Capital:", initial_capital)

    if is_running:
        print("Scheduler already running")
        return

    print("Starting scheduler...")

    scheduler = BlockingScheduler()

    scheduler.add_job(
        trading_job,
        "interval",
        seconds=180
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

    scheduler.add_job(
        collect_price,
        "interval",
        seconds=6
    )

    print("\nFetching news at startup...")
    save_news_to_json()

    print("\nRunning first cycle immediately...")
    trading_job()

    print("\nRunning daily market analysis at startup...")
    analyze_daily_market()

    is_running = True   # ⭐ สำคัญ

    import threading

    thread = threading.Thread(
        target=scheduler.start
    )

    thread.daemon = True
    thread.start()


def stop_scheduler():

    global scheduler
    global is_running

    if scheduler:

        scheduler.shutdown()

        print("Scheduler stopped")

    is_running = False   # ⭐ สำคัญ

def collect_price():

    indicators = compute_indicators()

    price = indicators["price"]

    add_price(price)

    print("Collected price:", price)


def reset_system():

    global scheduler
    global is_running
    global initial_capital

    from database.db import reset_database

    # stop bot ก่อน

    if scheduler:

        scheduler.shutdown()

        print("Scheduler stopped")

    is_running = False

    # reset DB

    reset_database()

    # reset capital

    initial_capital = None

    print("System reset complete")

def news_pipeline():

    save_news_to_json()

    analyze_news_sentiment()