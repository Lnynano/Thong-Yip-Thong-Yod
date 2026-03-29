import json
from datetime import datetime

from database.db import save_trade
from database.db import save_portfolio


class TradingSimulator:

    def __init__(self):

        # เงินเริ่มต้น
        self.cash = 1500.0

        # ถือทอง (fractional)
        self.gold = 0.0

        # ราคาที่ซื้อ
        self.last_buy_price = None

        # cooldown
        self.cooldown = 0

        # ⭐ ซื้อครั้งละ 1000 เท่านั้น
        self.investment_per_trade = 1000.0

        # TP / SL
        self.take_profit = 0.01    # +1%
        self.stop_loss = -0.01     # -1%

    # =========================

    def execute_trade(self, action, price):

        if price is None or price <= 0:

            print("Invalid price")

            return

        current_time = datetime.utcnow().isoformat()

        # =========================
        # COOLDOWN
        # =========================

        if self.cooldown > 0:

            self.cooldown -= 1

            print("Cooldown active")

            action = "HOLD"

        # =========================
        # AUTO TP / SL
        # =========================

        if self.gold > 0 and self.last_buy_price:

            change = (
                price - self.last_buy_price
            ) / self.last_buy_price

            if change >= self.take_profit:

                print("📈 Take Profit Triggered")

                action = "SELL"

            elif change <= self.stop_loss:

                print("📉 Stop Loss Triggered")

                action = "SELL"

        # =========================
        # BUY (only if NO gold)
        # =========================

        if action == "BUY":

            # ⭐ ถ้ามีทองอยู่แล้ว → ห้ามซื้อเพิ่ม

            if self.gold > 0:

                print("Already holding gold → HOLD")

                action = "HOLD"

            elif self.cash >= self.investment_per_trade:

                gold_bought = (
                    self.investment_per_trade
                    / price
                )

                self.cash -= self.investment_per_trade

                self.gold += gold_bought

                self.last_buy_price = price

                print(
                    f"✅ BUY executed → "
                    f"{gold_bought:.6f} gold"
                )

                save_trade(
                    current_time,
                    "BUY",
                    price,
                    self.gold,
                    self.cash
                )

                return

            else:

                print("Not enough cash → HOLD")

                action = "HOLD"

        # =========================
        # SELL
        # =========================

        if action == "SELL":

            if self.gold > 0:

                revenue = (
                    self.gold * price
                )

                self.cash += revenue

                print(
                    f"✅ SELL executed → "
                    f"{revenue:.2f} THB"
                )

                self.gold = 0

                self.last_buy_price = None

                self.cooldown = 1

                save_trade(
                    current_time,
                    "SELL",
                    price,
                    self.gold,
                    self.cash
                )

                return

            else:

                print("No gold to sell → HOLD")

                action = "HOLD"

        # =========================
        # HOLD (always fallback)
        # =========================

        print("😴 HOLD")

        save_trade(
            current_time,
            "HOLD",
            price,
            self.gold,
            self.cash
        )

    # =========================

    def portfolio_value(self, price):

        return self.cash + (
            self.gold * price
        )

    # =========================

    def print_status(self, price):

        total = self.portfolio_value(price)

        print("\nPortfolio Status:")

        print("Cash:", self.cash)

        print("Gold:", round(self.gold, 6))

        print("Total Value:", round(total, 2))

        current_time = datetime.utcnow().isoformat()

        save_portfolio(
            current_time,
            total,
            self.gold,
            self.cash
        )

    # =========================

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

            "profit_percent":
                round(profit_percent, 4),

            "cooldown": self.cooldown

        }

    # =========================

    def get_trades_today_count(self):

        return 0