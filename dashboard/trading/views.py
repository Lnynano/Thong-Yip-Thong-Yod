import sqlite3
import json
import os

import core.scheduler as scheduler

from django.shortcuts import render

from database.db import init_db


# ⭐ เพิ่ม DB_PATH ตรงนี้

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

def dashboard_view(request):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    # trades

    cursor.execute("""
        SELECT time, action, price, gold, cash
        FROM trades
        ORDER BY id DESC
        LIMIT 20
    """)

    trades = cursor.fetchall()

    # portfolio

    cursor.execute("""
        SELECT time, total_value
        FROM portfolio
        ORDER BY id ASC
        LIMIT 200
    """)

    portfolio = cursor.fetchall()

    conn.close()

    times = [p[0] for p in portfolio]

    values = [p[1] for p in portfolio]

    # =====================
    # PROFIT CALCULATION
    # =====================

    latest_value = values[-1] if values else 0

    initial = scheduler.initial_capital

    if initial is None:
        initial = latest_value

    START_CAPITAL = 10000

    latest_value = values[-1] if values else START_CAPITAL

    profit = latest_value - START_CAPITAL

    profit_percent = (
        (latest_value / START_CAPITAL - 1) * 100
    )

    context = {

        "trades": trades,

        "times": json.dumps(times),

        "values": json.dumps(values),

        "status": scheduler.is_running,

        "profit": profit,

        "profit_percent": profit_percent

    }

    return render(
        request,
        "dashboard.html",
        context
    )


def start_bot(request):

    init_db()

    scheduler.start_scheduler()

    return dashboard_view(request)


def stop_bot(request):

    init_db()

    scheduler.stop_scheduler()

    return dashboard_view(request)


def reset_bot(request):

    scheduler.reset_system()

    return dashboard_view(request)