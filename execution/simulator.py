import json
from datetime import datetime

from database.db import save_trade
from database.db import save_portfolio


class TradingSimulator:

    def __init__(self):

        # เงินเริ่มต้น
        self.cash = 10000

        # ทองเริ่มต้น
        self.gold = 0

        # ราคาที่ซื้อ
        self.last_buy_price = None

        # cooldown หลัง SELL
        self.cooldown = 0

        # strategy config

        self.max_gold = 2

        self.take_profit = 0.001   # +0.3%
        self.stop_loss = -0.003    # -0.5%

    # =========================

    def execute_trade(self, action, price):

        amount = 1

        current_time = datetime.utcnow().isoformat()

        # =========================
        # COOLDOWN LOGIC
        # =========================

        if self.cooldown > 0:

            self.cooldown -= 1

            print("Cooldown active")

            action = "HOLD"

        # =========================
        # AUTO SELL LOGIC
        # =========================

        if self.gold > 0 and self.last_buy_price:

            change = (
                price - self.last_buy_price
            ) / self.last_buy_price

            # Take Profit

            if change >= self.take_profit:

                print("Take Profit Triggered")

                action = "SELL"

            # Stop Loss

            elif change <= self.stop_loss:

                print("Stop Loss Triggered")

                action = "SELL"

        # =========================
        # BUY
        # =========================

        if action == "BUY":

            cost = price * amount

            if self.gold >= self.max_gold:

                print("Max gold limit reached")

                return

            if self.cash >= cost:

                self.cash -= cost

                self.gold += amount

                # ⭐ สำคัญมาก

                self.last_buy_price = price

                print("BUY executed")

                save_trade(
                    current_time,
                    "BUY",
                    price,
                    self.gold,
                    self.cash
                )

            else:

                print("Not enough cash")

        # =========================
        # SELL
        # =========================

        elif action == "SELL":

            if self.gold >= amount:

                self.cash += price * amount

                self.gold -= amount

                print("SELL executed")

                save_trade(
                    current_time,
                    "SELL",
                    price,
                    self.gold,
                    self.cash
                )

                if self.gold == 0:

                    self.last_buy_price = None

                    # ⭐ cooldown หลัง SELL

                    self.cooldown = 3

            else:

                print("No gold to sell")

        # =========================
        # HOLD
        # =========================

        elif action == "HOLD":

            print("HOLD position")

            save_trade(
                current_time,
                "HOLD",
                price,
                self.gold,
                self.cash
            )

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

        current_time = datetime.utcnow().isoformat()

        save_portfolio(
            current_time,
            total,
            self.gold,
            self.cash
        )