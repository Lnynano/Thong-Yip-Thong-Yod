import sqlite3
import os

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DB_PATH = os.path.join(
    BASE_DIR,
    "database",
    "trading.db"
)


def init_db():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            action TEXT,
            price REAL,
            gold REAL,
            cash REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT,
            total_value REAL,
            gold REAL,
            cash REAL

        )
    """)

    conn.commit()
    conn.close()


def save_trade(time, action, price, gold, cash):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO trades (
            time,
            action,
            price,
            gold,
            cash
        )

        VALUES (?, ?, ?, ?, ?)

    """, (
        time,
        action,
        price,
        gold,
        cash
    ))

    conn.commit()
    conn.close()

    print("Trade saved to database")


def save_portfolio(time, total_value, gold, cash):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO portfolio (
            time,
            total_value,
            gold,
            cash
        )

        VALUES (?, ?, ?, ?)

    """, (
        time,
        total_value,
        gold,
        cash
    ))

    conn.commit()
    conn.close()


# ⭐ เพิ่มอันนี้

def get_recent_trades():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""

        SELECT time,
               action,
               price,
               gold,
               cash

        FROM trades

        ORDER BY id DESC

        LIMIT 100

    """)

    rows = cursor.fetchall()

    conn.close()

    return rows[::-1]


# ⭐ เพิ่มอันนี้

def get_portfolio_history():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""

        SELECT time,
               total_value

        FROM portfolio

        ORDER BY id ASC

        LIMIT 100

    """)

    rows = cursor.fetchall()

    conn.close()

    times = []
    values = []

    for row in rows:

        times.append(row[0])

        values.append(row[1])

    return times, values


def get_latest_portfolio():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""

        SELECT total_value

        FROM portfolio

        ORDER BY id DESC

        LIMIT 1

    """)

    row = cursor.fetchone()

    conn.close()

    if row:

        return {"total_value": row[0]}

    return {"total_value": 10000}


def reset_database():

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("DELETE FROM trades")

    cursor.execute("DELETE FROM portfolio")

    cursor.execute(
        "DELETE FROM sqlite_sequence WHERE name='trades'"
    )

    cursor.execute(
        "DELETE FROM sqlite_sequence WHERE name='portfolio'"
    )

    conn.commit()
    conn.close()

    print("Database reset complete")