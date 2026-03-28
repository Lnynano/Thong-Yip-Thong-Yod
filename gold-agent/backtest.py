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
2026-01-24,4625.70,4650.40,4600.20,4638.90,485667
2026-01-25,4638.90,4665.80,4610.30,4652.40,480110
2026-01-26,4652.40,4680.90,4630.50,4668.10,475554
2026-01-27,4668.10,4705.20,4650.20,4695.60,470002
2026-01-28,4695.60,4725.40,4670.30,4710.80,465334
2026-01-29,4710.80,4740.10,4685.00,4725.30,460776
2026-01-30,4725.30,4755.90,4700.40,4740.20,455998
2026-01-31,4740.20,4770.60,4715.10,4755.80,450210
2026-02-01,4755.80,4788.40,4730.30,4772.50,445554
2026-02-02,4772.50,4805.20,4750.40,4788.90,440112
2026-02-03,4788.90,4820.60,4765.10,4805.40,435667
2026-02-04,4805.40,4835.80,4780.30,4822.70,430110
2026-02-05,4822.70,4850.90,4800.60,4835.20,425554
2026-02-06,4835.20,4865.40,4810.10,4852.90,420002
2026-02-07,4852.90,4880.20,4830.40,4868.30,415334
2026-02-08,4868.30,4905.10,4850.00,4890.60,410776
2026-02-09,4890.60,4920.80,4865.20,4905.40,405998
2026-02-10,4905.40,4935.70,4880.30,4920.80,400210
2026-02-11,4920.80,4950.20,4900.50,4935.60,395554
2026-02-12,4935.60,4965.10,4910.20,4950.90,390112
2026-02-13,4950.90,4980.40,4930.10,4968.20,385667
2026-02-14,4968.20,4995.60,4940.30,4982.50,380110
2026-02-15,4982.50,5010.20,4960.10,4998.30,375554
2026-02-16,4998.30,5035.40,4980.50,5025.70,370002
2026-02-17,5025.70,5055.80,5000.20,5040.90,365334
2026-02-18,5040.90,5070.60,5020.10,5055.20,360776
2026-02-19,5055.20,5085.90,5035.30,5070.40,355998
2026-02-20,5070.40,5100.20,5050.60,5085.90,350210
2026-02-21,5085.90,5120.30,5070.20,5105.40,345554
2026-02-22,5105.40,5135.80,5080.10,5120.60,340112
2026-02-23,5120.60,5150.20,5100.30,5135.90,335667
2026-02-24,4312.50,4345.20,4298.10,4330.40,298123
2026-02-25,4330.40,4362.90,4315.00,4355.10,305442
2026-02-26,4355.10,4380.75,4338.60,4372.30,287654
2026-02-27,4372.30,4395.50,4350.20,4360.80,310223
2026-02-28,4360.80,4378.90,4325.40,4338.20,295112
2026-03-01,4338.20,4350.00,4305.30,4315.60,280554
2026-03-02,4315.60,4342.10,4290.75,4335.90,301221
2026-03-03,4335.90,4368.40,4320.00,4358.70,322198
2026-03-04,4358.70,4390.10,4345.60,4385.30,334210
2026-03-05,4385.30,4412.80,4362.40,4405.90,345876
2026-03-06,4405.90,4430.20,4388.00,4422.60,352144
2026-03-07,4422.60,4445.00,4395.30,4410.20,348221
2026-03-08,4410.20,4432.10,4375.40,4388.50,330998
2026-03-09,4388.50,4415.90,4360.20,4402.80,319004
2026-03-10,4402.80,4438.60,4385.70,4425.40,341776
2026-03-11,4425.40,4452.30,4400.00,4440.90,355112
2026-03-12,4440.90,4475.60,4422.50,4468.20,368990
2026-03-13,4468.20,4498.40,4445.30,4485.70,372211
2026-03-14,4485.70,4510.90,4460.00,4498.60,365554
2026-03-15,4498.60,4525.20,4472.30,4510.40,378220
2026-03-16,4510.40,4540.80,4490.50,4528.90,389002
2026-03-17,4528.90,4565.30,4510.20,4552.70,402115
2026-03-18,4552.70,4588.40,4530.00,4575.20,415334
2026-03-19,4575.20,4595.60,4542.10,4560.80,398112
2026-03-20,4560.80,4580.40,4525.00,4540.30,385009
2026-03-21,4540.30,4562.70,4508.90,4522.10,372884
2026-03-22,4522.10,4545.60,4495.00,4510.80,360775
2026-03-23,4510.80,4532.40,4478.60,4495.20,348221
2026-03-24,4495.20,4520.00,4455.30,4470.60,336110
2026-03-25,4470.60,4505.80,4428.40,4452.10,365443
2026-03-26,4520.00,4541.87,4352.94,4394.38,376719"""

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
