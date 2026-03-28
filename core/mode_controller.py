import yfinance as yf
import random

# =========================
# GLOBAL STATE
# =========================

MODE = "REAL"

historical_prices = []
current_index = 0


# =========================
# SET MODE
# =========================

def set_mode(mode):

    global MODE

    MODE = mode

    print(f"Mode set to: {MODE}")


def get_mode():

    return MODE


# =========================
# LOAD TEST DATA
# =========================

def load_test_data():

    global historical_prices
    global current_index

    print("📥 Loading historical data...")

    # โหลด 5 วันย้อนหลัง
    data = yf.download(
        "GC=F",
        period="5d",
        interval="1m",
        progress=False
    )

    if data.empty:

        print("❌ No historical data")

        historical_prices = []

        return

    # flatten MultiIndex
    if hasattr(data.columns, "levels"):

        data.columns = data.columns.droplevel(1)

    closes = data["Close"].tolist()

    # =========================
    # สุ่ม 1 วัน (2880 จุด)
    # =========================

    if len(closes) > 2880:

        start = random.randint(
            0,
            len(closes) - 2880
        )

        historical_prices = closes[
            start:start + 2880
        ]

    else:

        historical_prices = closes

    current_index = 0

    print(
        f"✅ Loaded {len(historical_prices)} test prices"
    )


# =========================
# GET NEXT TEST PRICE
# =========================

def get_next_test_price():

    global current_index

    if len(historical_prices) == 0:

        print("⚠ No test data loaded")

        return None

    # loop กลับไปเริ่มใหม่
    if current_index >= len(historical_prices):

        current_index = 0

    price = historical_prices[current_index]

    current_index += 1

    return float(price)

# =========================
# TIME CONFIGURATION
# =========================

def get_time_config():

    """
    คืนค่า interval ตาม mode
    REAL vs TEST
    """

    if MODE == "REAL":

        return {

            "price_interval": 6,      # collect price ทุก 6 วิ
            "trade_interval": 180,    # AI trade ทุก 180 วิ

        }

    elif MODE == "TEST":

        return {

            "price_interval": 0.5,    # collect เร็วขึ้น
            "trade_interval": 15,     # AI เร็วขึ้น

        }

    else:

        # fallback

        return {

            "price_interval": 6,
            "trade_interval": 180,

        }