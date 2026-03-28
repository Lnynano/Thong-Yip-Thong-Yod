import sqlite3
import json
import os

from django.shortcuts import render, redirect

import core.scheduler as scheduler

from database.db import init_db

from core.mode_controller import (
    set_mode,
    get_mode
)

from core.scheduler import (
    start_test_mode,
    stop_scheduler,
    start_scheduler
)


# =========================
# DATABASE PATH
# =========================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

DB_PATH = os.path.join(
    BASE_DIR,
    "database",
    "trading.db"
)


# =========================
# DASHBOARD VIEW
# =========================

def dashboard_view(request):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    # =========================
    # LOAD TRADES
    # =========================

    cursor.execute("""
        SELECT time, action, price, gold, cash
        FROM trades
        ORDER BY id DESC
        LIMIT 50
    """)

    trades = cursor.fetchall()

    # =========================
    # LOAD PORTFOLIO
    # =========================

    cursor.execute("""
        SELECT time, total_value
        FROM portfolio
        ORDER BY id ASC
        LIMIT 500
    """)

    portfolio = cursor.fetchall()

    conn.close()

    times = [p[0] for p in portfolio]
    values = [p[1] for p in portfolio]

    # =========================
    # PROFIT CALCULATION
    # =========================

    START_CAPITAL = 1500

    latest_value = (
        values[-1]
        if values
        else START_CAPITAL
    )

    profit = latest_value - START_CAPITAL

    profit_percent = (
        (latest_value / START_CAPITAL - 1)
        * 100
    )

    # =========================
    # CURRENT MODE
    # =========================

    current_mode = get_mode()

    # =========================
    # CONTEXT
    # =========================

    context = {

        "trades": trades,

        "times": json.dumps(times),

        "values": json.dumps(values),

        "status": scheduler.is_running,

        "profit": profit,

        "profit_percent": profit_percent,

        "mode": current_mode

    }

    return render(
        request,
        "dashboard.html",
        context
    )


# =========================
# START BOT
# =========================

def start_bot(request):

    print("🚀 Starting Bot")

    init_db()

    start_scheduler()

    return redirect("/")


# =========================
# STOP BOT
# =========================

def stop_bot(request):

    print("⛔ Stopping Bot")

    stop_scheduler()

    return redirect("/")


# =========================
# RESET BOT
# =========================

def reset_bot(request):

    print("🔄 Reset System")

    scheduler.reset_system()

    return redirect("/")


# =========================
# SET REAL MODE
# =========================

def set_real_mode(request):

    print("🟢 Switching to REAL mode")

    stop_scheduler()

    set_mode("REAL")

    start_scheduler()

    return redirect("/")


# =========================
# SET TEST MODE
# =========================

def set_test_mode(request):

    print("🧪 Switching to TEST mode")

    stop_scheduler()

    start_test_mode()

    return redirect("/")