import sqlite3
import json
import os
import core.scheduler as scheduler
from django.shortcuts import render, redirect  # Added redirect
from database.db import init_db

# Build path to the database
BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "database", "trading.db")


def dashboard_view(request):
    trades = []
    times = []
    values = []

    # ✅ Fixed: Capital set to 1,500 to match your simulator
    START_CAPITAL = 1500.0

    current_cash = START_CAPITAL
    current_gold = 0.0
    last_price = 0.0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. Get Trades (Showing all 5 columns: time, action, price, gold, cash)
        cursor.execute(
            "SELECT time, action, price, gold, cash FROM trades ORDER BY id DESC LIMIT 20")
        trades = cursor.fetchall()

        # 2. Get Portfolio History for Chart
        cursor.execute(
            "SELECT time, total_value, gold, cash FROM portfolio ORDER BY id ASC")
        portfolio_data = cursor.fetchall()

        if portfolio_data:
            # We don't json.dumps here because we use |safe in HTML
            times = [p[0] for p in portfolio_data]
            values = [p[1] for p in portfolio_data]

            latest_entry = portfolio_data[-1]
            current_gold = latest_entry[2]
            current_cash = latest_entry[3]

        if trades:
            last_price = trades[0][2]

        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

    # Profit Calculation
    latest_total_value = values[-1] if values else START_CAPITAL
    profit = latest_total_value - START_CAPITAL
    profit_percent = ((latest_total_value / START_CAPITAL) - 1) * 100

    context = {
        "trades": trades,
        "times": times,  # Send list directly
        "values": values,  # Send list directly
        "status": scheduler.is_running,
        "cash": current_cash,
        "gold": current_gold,
        "last_price": last_price,
        "total_value": latest_total_value,
        "profit": profit,
        "profit_percent": round(profit_percent, 2),
    }
    return render(request, "dashboard.html", context)

# ✅ FIXED: Use redirect so the URL goes back to '/'


def start_bot(request):
    scheduler.start_scheduler()
    return redirect('/')


def stop_bot(request):
    scheduler.stop_scheduler()
    return redirect('/')


def reset_bot(request):
    scheduler.reset_system()
    return redirect('/')
