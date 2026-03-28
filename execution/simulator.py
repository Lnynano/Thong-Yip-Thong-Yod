import json
from datetime import datetime

from database.db import save_trade
from database.db import save_portfolio


class TradingSimulator:

    def __init__(self):

        self.cash = 1500.0
        self.gold = 0
        self.last_buy_price = None
        self.cooldown = 0
        self.max_gold = 2

        self.take_profit = 0.005   # +0.5%
        self.stop_loss = -0.01     # -1.0%

    # =========================

    def execute_trade(self, action, price):
        if price is None or price == 0:
            print("Simulator received invalid price. Skipping cycle.")
            return

        # --- FIX: Set a fixed THB amount for Aom NOW ---
        investment_thb = 1000.0
        # Use local time for easier DB reading
        current_time = datetime.now().isoformat()

        # =========================
        # COOLDOWN LOGIC
        # =========================
        if self.cooldown > 0:
            self.cooldown -= 1
            print(f"Cooldown active ({self.cooldown} cycles left)")
            action = "HOLD"

        # =========================
        # AUTO SELL LOGIC (Research-based)
        # =========================
        if self.gold > 0 and self.last_buy_price:
            change = (price - self.last_buy_price) / self.last_buy_price
            if change >= self.take_profit:
                print(f"📈 Take Profit Triggered (+{change*100:.2f}%)")
                action = "SELL"
            elif change <= self.stop_loss:
                print(f"📉 Stop Loss Triggered ({change*100:.2f}%)")
                action = "SELL"

        # =========================
        # BUY (฿1,000 Fixed Amount)
        # =========================
        if action == "BUY":
            if self.cash >= investment_thb:
                # Calculate gold fraction: 1000 / price_per_baht
                gold_gained = investment_thb / price

                self.cash -= investment_thb
                self.gold += gold_gained
                self.last_buy_price = price

                print(
                    f"✅ BUY executed: Spent ฿{investment_thb} for {gold_gained:.4f} Gold")

                save_trade(current_time, "BUY", price, self.gold, self.cash)
            else:
                print(
                    f"❌ Not enough cash (Need ฿{investment_thb}, have ฿{self.cash})")

        # =========================
        # SELL (Sell All Gold)
        # =========================
        elif action == "SELL":
            if self.gold > 0:
                revenue = self.gold * price
                self.cash += revenue

                print(f"✅ SELL executed: Sold gold for ฿{revenue:.2f}")

                self.gold = 0
                self.last_buy_price = None
                self.cooldown = 2  # Prevent immediate re-entry

                save_trade(current_time, "SELL", price, self.gold, self.cash)
            else:
                print("❌ No gold to sell")

        # =========================
        # HOLD
        # =========================
        elif action == "HOLD":
            print("😴 HOLD position")
            # We don't usually save HOLDs to the trade table to keep it clean,
            # but we save it to the portfolio table via print_status below.

    # =========================

    def portfolio_value(self, price):

        return self.cash + (self.gold * price)

    # =========================

    def print_status(self, price):

        total = self.portfolio_value(price)

        print("\nPortfolio Status:")

        print("Cash:", self.cash)

        print("Gold:", self.gold)

        print("Total Value:", total)

        current_time = datetime.now().isoformat()

        save_portfolio(
            current_time,
            total,
            self.gold,
            self.cash
        )

    def get_status(self, current_price):

        profit_percent = 0

        if self.last_buy_price:

            profit_percent = (
                (current_price - self.last_buy_price)
                / self.last_buy_price
            ) * 100

        return {
            "cash": self.cash,
            "gold": self.gold,
            "last_buy_price": self.last_buy_price,
            "profit_percent": round(profit_percent, 4),
            "cooldown": self.cooldown
        }

    def get_trades_today_count(self):
        """
        Connects to the database and counts how many trades 
        have been recorded for the current date.
        """
        import sqlite3
        from datetime import datetime
        import os

        # Point to your database path
        # Adjust this path if your simulator.py is in a different subfolder
        db_path = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), "database", "trading.db")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get current date in YYYY-MM-DD format
            today = datetime.now().strftime('%Y-%m-%d')

            # Query to count trades that happened today
            # We use 'LIKE' because your 'time' column is likely a full timestamp string
            cursor.execute(
                "SELECT COUNT(*) FROM trades WHERE time LIKE ?", (f"{today}%",))
            count = cursor.fetchone()[0]

            conn.close()
            return count
        except Exception as e:
            print(f"Error counting daily trades: {e}")
            return 0
