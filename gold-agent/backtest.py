#!/usr/bin/env python3
"""
backtest.py
Replay historical OHLCV data day-by-day through the Claude gold agent.

Usage:
    cd gold-agent
    python backtest.py

Notes:
    - Starts from day 20 (minimum for Bollinger Bands to be valid)
    - Uses a fixed USD/THB rate of 34.5 for consistent conversion
    - News uses mock headlines (not real historical news)
    - Each day makes 1 Claude API call (~12 calls total for 31-row dataset)
"""

import sys
import os
import io
import pandas as pd
from unittest.mock import patch

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Embedded historical data ─────────────────────────────────────────────────
CSV_DATA = """Date,Open,High,Low,Close,Volume
2025-12-17,4012.30,4045.60,3998.20,4032.50,285123
2025-12-18,4032.50,4060.10,4015.40,4055.20,292110
2025-12-19,4055.20,4088.40,4030.10,4072.80,301223
2025-12-20,4072.80,4095.00,4048.60,4060.30,295332
2025-12-21,4060.30,4075.80,4022.40,4035.60,280998
2025-12-22,4035.60,4062.90,4010.30,4050.20,288776
2025-12-23,4050.20,4080.50,4038.60,4075.40,300112
2025-12-24,4075.40,4102.30,4050.10,4090.70,310554
2025-12-25,4090.70,4115.20,4072.80,4105.60,315667
2025-12-26,4105.60,4130.40,4088.90,4122.30,320110
2025-12-27,4122.30,4155.60,4100.20,4148.90,332441
2025-12-28,4148.90,4170.80,4120.50,4155.10,338220
2025-12-29,4155.10,4188.60,4135.20,4175.30,345998
2025-12-30,4175.30,4205.90,4150.00,4190.80,350776
2025-12-31,4190.80,4215.40,4170.60,4202.50,360112
2026-01-01,4202.50,4228.70,4180.40,4215.90,365443
2026-01-02,4215.90,4245.20,4195.10,4238.40,372110
2026-01-03,4238.40,4268.90,4210.00,4255.70,380221
2026-01-04,4255.70,4280.60,4232.40,4272.80,388990
2026-01-05,4272.80,4305.40,4250.10,4295.60,395210
2026-01-06,4295.60,4320.80,4275.30,4308.40,400554
2026-01-07,4308.40,4345.90,4290.10,4335.20,410002
2026-01-08,4335.20,4362.40,4310.60,4348.70,415334
2026-01-09,4348.70,4380.50,4330.40,4372.10,420776
2026-01-10,4372.10,4405.90,4350.20,4395.60,428990
2026-01-11,4395.60,4425.80,4370.50,4412.40,435210
2026-01-12,4412.40,4440.20,4390.60,4428.80,440554
2026-01-13,4428.80,4465.70,4410.10,4455.30,450112
2026-01-14,4455.30,4480.60,4430.40,4468.20,455667
2026-01-15,4468.20,4495.80,4445.00,4482.90,460110
2026-01-16,4482.90,4520.40,4460.30,4505.60,470554
2026-01-17,4505.60,4540.80,4485.20,4528.70,480002
2026-01-18,4528.70,4565.10,4510.40,4552.30,490334
2026-01-19,4552.30,4588.90,4530.20,4575.80,500776
2026-01-20,4575.80,4605.40,4550.60,4588.20,510998
2026-01-21,4588.20,4615.90,4560.10,4595.40,505210
2026-01-22,4595.40,4620.80,4570.30,4602.10,498554
2026-01-23,4602.10,4635.20,4580.60,4625.70,490112
"""

# ── Constants ─────────────────────────────────────────────────────────────────
USD_THB_RATE        = 34.5      # fixed rate for consistent backtesting
TROY_OZ_GRAMS       = 31.1035
BAHT_WEIGHT_GRAMS   = 15.244
PURITY              = 0.965
INITIAL_BALANCE_THB = 1500.0
CONFIDENCE_GATE     = 65
MIN_BALANCE_THB     = 1000.0
POSITION_SIZE_PCT   = 0.95
MIN_ROWS            = 20        # need 20 rows for Bollinger Bands(20)


def usd_to_thb_per_bw(price_usd: float) -> float:
    """Convert USD/oz → THB per baht-weight (Thai 96.5% purity)."""
    thb_per_oz    = price_usd * USD_THB_RATE
    thb_per_gram  = thb_per_oz / TROY_OZ_GRAMS
    thb_per_bw    = thb_per_gram * BAHT_WEIGHT_GRAMS * PURITY
    return round(thb_per_bw, 2)


def run_backtest() -> None:
    # ── Load data ─────────────────────────────────────────────────────────────
    df_full = pd.read_csv(io.StringIO(CSV_DATA), parse_dates=["Date"])
    df_full = df_full.set_index("Date")
    df_full.index.name = "Date"

    print("=" * 65)
    print("  GOLD AGENT BACKTEST")
    print(f"  Data  : {df_full.index[0].date()} → {df_full.index[-1].date()}  ({len(df_full)} rows)")
    print(f"  Start : day {MIN_ROWS} (Bollinger Bands require {MIN_ROWS} rows)")
    print(f"  Rate  : USD/THB = {USD_THB_RATE} (fixed)")
    print(f"  Capital: ฿{INITIAL_BALANCE_THB:,.0f}  |  Gate: {CONFIDENCE_GATE}% confidence")
    print("=" * 65)

    # ── Paper trading state (in-memory, no portfolio.json touched) ────────────
    balance_thb    = INITIAL_BALANCE_THB
    open_position  = None    # dict when a trade is open
    closed_trades  = []
    daily_log      = []

    import data.fetch as fetch_module
    from agent.claude_agent import run_agent

    for i in range(MIN_ROWS - 1, len(df_full)):
        window     = df_full.iloc[: i + 1].copy()
        date       = df_full.index[i]
        price_usd  = float(window["Close"].iloc[-1])
        price_thb  = usd_to_thb_per_bw(price_usd)

        print(f"\n{'─'*65}")
        print(f"  Day {i+1:2d} | {date.date()} | ${price_usd:,.2f} | ฿{price_thb:,.0f}/bw")
        print(f"{'─'*65}")

        # ── Call Claude with patched data ──────────────────────────────────────
        with patch.object(fetch_module, "get_gold_price", return_value=window):
            agent = run_agent()

        decision   = agent["decision"]
        confidence = agent["confidence"]
        reasoning  = agent["reasoning"]
        key_factors = agent.get("key_factors", [])

        print(f"  Decision   : {decision} @ {confidence}%")
        print(f"  Reasoning  : {reasoning[:120]}{'...' if len(reasoning) > 120 else ''}")
        if key_factors:
            print(f"  Key factors: {', '.join(key_factors[:3])}")

        # ── Paper trade execution ──────────────────────────────────────────────
        action  = "HOLD"
        pnl_thb = 0.0

        if decision == "BUY" and confidence >= CONFIDENCE_GATE:
            if open_position is None:
                if balance_thb >= MIN_BALANCE_THB:
                    cost    = round(balance_thb * POSITION_SIZE_PCT, 2)
                    size_bw = cost / price_thb
                    balance_thb   -= cost
                    open_position  = {
                        "entry_date"  : str(date.date()),
                        "entry_price" : price_thb,
                        "size_bw"     : size_bw,
                        "cost_thb"    : cost,
                    }
                    action = "OPENED"
                    print(f"  >> BUY executed  | cost ฿{cost:,.2f} | size {size_bw:.6f} bw")
                else:
                    action = "SKIP (low balance)"
            else:
                action = "SKIP (already holding)"

        elif decision == "SELL" and confidence >= CONFIDENCE_GATE:
            if open_position is not None:
                proceeds = open_position["size_bw"] * price_thb
                pnl_thb  = round(proceeds - open_position["cost_thb"], 2)
                outcome  = "WIN" if pnl_thb >= 0 else "LOSS"
                balance_thb += proceeds
                trade = {
                    "entry_date"  : open_position["entry_date"],
                    "exit_date"   : str(date.date()),
                    "entry_price" : open_position["entry_price"],
                    "exit_price"  : price_thb,
                    "size_bw"     : open_position["size_bw"],
                    "cost_thb"    : open_position["cost_thb"],
                    "pnl_thb"     : pnl_thb,
                    "pnl_pct"     : round(pnl_thb / open_position["cost_thb"] * 100, 2),
                    "outcome"     : outcome,
                }
                closed_trades.append(trade)
                open_position = None
                action = f"CLOSED [{outcome}]"
                print(f"  >> SELL executed | proceeds ฿{proceeds:,.2f} | P&L {pnl_thb:+.2f} [{outcome}]")
            else:
                action = "SKIP (no position)"

        # ── Current equity ─────────────────────────────────────────────────────
        unrealized = 0.0
        if open_position:
            unrealized = (open_position["size_bw"] * price_thb) - open_position["cost_thb"]
        equity = round(balance_thb + (open_position["size_bw"] * price_thb if open_position else 0), 2)

        print(f"  Action     : {action}")
        print(f"  Equity     : ฿{equity:,.2f}  (cash ฿{balance_thb:,.2f} + unrealized ฿{unrealized:+.2f})")

        daily_log.append({
            "date"       : str(date.date()),
            "price_usd"  : price_usd,
            "price_thb"  : price_thb,
            "decision"   : decision,
            "confidence" : confidence,
            "action"     : action,
            "pnl_thb"    : pnl_thb,
            "equity_thb" : equity,
        })

    # ── Final summary ─────────────────────────────────────────────────────────
    last_price_thb = daily_log[-1]["price_thb"] if daily_log else 0
    final_equity   = balance_thb
    if open_position:
        final_equity += open_position["size_bw"] * last_price_thb

    wins      = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses    = [t for t in closed_trades if t["outcome"] == "LOSS"]
    total_pnl = sum(t["pnl_thb"] for t in closed_trades)
    win_rate  = len(wins) / len(closed_trades) * 100 if closed_trades else 0.0
    ret_pct   = (final_equity - INITIAL_BALANCE_THB) / INITIAL_BALANCE_THB * 100

    print(f"\n{'='*65}")
    print("  BACKTEST RESULTS")
    print(f"{'='*65}")
    print(f"  Period       : {daily_log[0]['date']} → {daily_log[-1]['date']}")
    print(f"  Days run     : {len(daily_log)}")
    print(f"  Closed trades: {len(closed_trades)}  (wins {len(wins)}  losses {len(losses)})")
    print(f"  Win rate     : {win_rate:.1f}%")
    print(f"  Total P&L    : ฿{total_pnl:+,.2f}")
    print(f"  Initial      : ฿{INITIAL_BALANCE_THB:,.2f}")
    print(f"  Final equity : ฿{final_equity:,.2f}")
    print(f"  Return       : {ret_pct:+.2f}%")

    if open_position:
        unrealized_final = (open_position["size_bw"] * last_price_thb) - open_position["cost_thb"]
        print(f"\n  [OPEN POSITION]")
        print(f"  Entered {open_position['entry_date']} @ ฿{open_position['entry_price']:,.0f}")
        print(f"  Unrealized P&L: ฿{unrealized_final:+,.2f}")

    if closed_trades:
        print(f"\n  {'─'*63}")
        print(f"  {'Entry':12} {'Exit':12} {'Entry ฿':>10} {'Exit ฿':>10} {'P&L ฿':>8} {'%':>6}  Result")
        print(f"  {'─'*63}")
        for t in closed_trades:
            flag = "✓" if t["outcome"] == "WIN" else "✗"
            print(
                f"  {t['entry_date']:12} {t['exit_date']:12} "
                f"{t['entry_price']:>10,.0f} {t['exit_price']:>10,.0f} "
                f"{t['pnl_thb']:>+8.2f} {t['pnl_pct']:>+5.2f}%  {flag} {t['outcome']}"
            )

    print(f"{'='*65}\n")


if __name__ == "__main__":
    run_backtest()
