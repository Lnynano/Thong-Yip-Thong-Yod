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


def get_latest_portfolio():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Safety: check if table exists before querying
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='portfolio'")
    if not cursor.fetchone():
        conn.close()
        return {"total_value": 1500.0}  # New Thai Capital

    cursor.execute(
        "SELECT total_value FROM portfolio ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"total_value": row[0]}

    return {"total_value": 1500.0}  # Return 100k if empty


def reset_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear everything
    cursor.execute("DROP TABLE IF EXISTS trades")
    cursor.execute("DROP TABLE IF EXISTS portfolio")

    conn.commit()
    conn.close()

    # Re-initialize the structure so the tables EXIST (but are empty)
    init_db()

    print("Database reset and tables recreated.")
