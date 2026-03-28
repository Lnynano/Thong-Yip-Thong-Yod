"""
ทดสอบระบบที่ปรับปรุงใหม่ - Technical Analysis + Risk Management
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from services.technical_analysis import TechnicalAnalysis
from services.risk_manager import RiskManager
from services.agent_brain import AgentBrain
from models.portfolio import PortfolioState
import random

def test_technical_analysis():
    """ทดสอบ Technical Analysis"""
    print("=" * 60)
    print("TEST 1: Technical Analysis")
    print("=" * 60)
    
    ta = TechnicalAnalysis()
    
    # จำลองข้อมูลราคา 50 รอบ
    print("\nSimulating 50 price updates...")
    base_price = 2500
    for i in range(50):
        # สร้างแนวโน้มขึ้น
        trend = i * 2  # ราคาขึ้นเรื่อยๆ
        noise = random.uniform(-20, 20)
        price = base_price + trend + noise
        
        ta.update_price(buy_price=price + 30, sell_price=price)
    
    # วิเคราะห์
    analysis = ta.get_comprehensive_analysis()
    
    print("\n📊 Technical Analysis Results:")
    print(f"  Overall Signal: {analysis['overall_signal']}")
    print(f"  Confidence: {analysis['confidence']:.1f}%")
    print(f"  Buy Score: {analysis['buy_score']:.1f}")
    print(f"  Sell Score: {analysis['sell_score']:.1f}")
    
    print(f"\n  Trend: {analysis['trend']['direction']} (strength: {analysis['trend']['strength']:.1f}%)")
    print(f"  SMA: {analysis['trend']['sma']:.2f}")
    print(f"  Current vs SMA: {analysis['trend']['current_vs_sma']:+.2f}%")
    
    print(f"\n  RSI: {analysis['rsi']['rsi']:.1f} ({analysis['rsi']['signal']})")
    print(f"  Momentum: {analysis['momentum']['momentum']:+.2f}% ({analysis['momentum']['signal']})")
    print(f"  Volatility: {analysis['volatility']:.1f}%")
    
    print(f"\n  Support: {analysis['support_resistance']['support']:.2f}")
    print(f"  Resistance: {analysis['support_resistance']['resistance']:.2f}")
    print(f"  Position: {analysis['support_resistance']['current_position']}")
    
    return analysis

def test_risk_management():
    """ทดสอบ Risk Management"""
    print("\n" + "=" * 60)
    print("TEST 2: Risk Management")
    print("=" * 60)
    
    rm = RiskManager(initial_capital=1500.0)
    
    # Test 1: Position sizing
    print("\n📏 Position Sizing Test:")
    scenarios = [
        {"equity": 1500, "confidence": 80, "volatility": 30, "pnl_pct": 0, "desc": "High confidence, low volatility"},
        {"equity": 1450, "confidence": 60, "volatility": 70, "pnl_pct": -3.3, "desc": "Medium confidence, high volatility, small loss"},
        {"equity": 1350, "confidence": 50, "volatility": 50, "pnl_pct": -10, "desc": "Low confidence, medium volatility, large loss"},
    ]
    
    for scenario in scenarios:
        result = rm.calculate_position_size(
            equity=scenario['equity'],
            confidence=scenario['confidence'],
            volatility=scenario['volatility'],
            pnl_pct=scenario['pnl_pct']
        )
        print(f"\n  Scenario: {scenario['desc']}")
        print(f"    → Position: {result['position_size_thb']:.2f} THB ({result['position_size_pct']:.1f}%)")
        print(f"    → Reason: {result['reason']}")
    
    # Test 2: Stop Loss / Take Profit
    print("\n\n🛡️ Stop Loss / Take Profit Test:")
    entry_price = 2500
    test_prices = [
        (2625, "Take Profit scenario (+5%)"),
        (2425, "Stop Loss scenario (-3%)"),
        (2520, "Normal scenario (+0.8%)"),
    ]
    
    for current_price, desc in test_prices:
        should_tp, tp_reason = rm.should_take_profit(entry_price, current_price, 'LONG')
        should_sl, sl_reason = rm.should_stop_loss(entry_price, current_price, 'LONG')
        
        print(f"\n  {desc} (Entry: {entry_price}, Current: {current_price})")
        if should_tp:
            print(f"    ✅ {tp_reason}")
        elif should_sl:
            print(f"    ⚠️ {sl_reason}")
        else:
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            print(f"    ➡️ Hold position (PnL: {pnl_pct:+.2f}%)")
    
    # Test 3: Risk Level
    print("\n\n⚠️ Risk Level Assessment:")
    risk_scenarios = [
        {"equity": 1500, "pnl_pct": 0, "volatility": 30, "desc": "Normal start"},
        {"equity": 1450, "pnl_pct": -3.3, "volatility": 50, "desc": "Small loss, medium volatility"},
        {"equity": 1300, "pnl_pct": -13.3, "volatility": 75, "desc": "Large loss, high volatility"},
    ]
    
    for scenario in risk_scenarios:
        risk = rm.get_risk_level(
            equity=scenario['equity'],
            pnl_pct=scenario['pnl_pct'],
            volatility=scenario['volatility']
        )
        print(f"\n  {scenario['desc']}")
        print(f"    → Risk Level: {risk['level'].upper()} (score: {risk['score']:.0f})")
        if risk['warnings']:
            print(f"    → Warnings:")
            for w in risk['warnings']:
                print(f"      • {w}")

def test_integrated_decision():
    """ทดสอบการตัดสินใจแบบบูรณาการ"""
    print("\n" + "=" * 60)
    print("TEST 3: Integrated Decision Making")
    print("=" * 60)
    
    # Setup
    agent = AgentBrain()
    portfolio = PortfolioState(initial_capital=1500.0)
    
    # Simulate some price history
    print("\nBuilding price history...")
    for i in range(30):
        price = 2500 + i * 3 + random.uniform(-15, 15)
        agent.technical_analysis.update_price(price + 30, price)
    
    # Test decision
    app_state = {
        'cash_balance': 1450.0,
        'gold_balance': 0.0198,
        'buy_price': 2590.0,
        'sell_price': 2540.0
    }
    
    portfolio.update(
        cash_balance=app_state['cash_balance'],
        gold_balance=app_state['gold_balance'],
        buy_price=app_state['buy_price'],
        sell_price=app_state['sell_price']
    )
    
    macro_news = """
=== MARKET NEWS & ANALYSIS ===

📰 Top Headlines:
  1. Gold prices surge amid geopolitical tensions in Middle East
  2. Federal Reserve maintains interest rates at 5.25-5.50%
  3. US inflation drops to 3.2% YoY, below expectations

📊 Key Market Factors:
  • Gold spot price: $2,465.30/oz
  • 24h change: +$18.50 (+0.76%)
  • US Dollar Index (DXY): 104.25
  • VIX (Fear Index): 16.80

📈 Overall Sentiment: BULLISH
"""
    
    print("\n🧠 Making Decision...")
    decision = agent.make_decision(
        app_state=app_state,
        macro_news=macro_news,
        portfolio_state=portfolio,
        simulation=True
    )
    
    print("\n" + "=" * 60)
    print("DECISION RESULT")
    print("=" * 60)
    print(f"\n⚡ Action: {decision['action']}")
    print(f"🎯 Confidence: {decision['confidence']:.1f}%")
    
    print(f"\n📊 Technical Analysis:")
    ta = decision['technical_analysis']
    print(f"  • Signal: {ta['overall_signal']}")
    print(f"  • Trend: {ta['trend']['direction']} ({ta['trend']['strength']:.0f}%)")
    print(f"  • RSI: {ta['rsi']['rsi']:.1f} ({ta['rsi']['signal']})")
    print(f"  • Momentum: {ta['momentum']['momentum']:+.2f}%")
    
    print(f"\n🛡️ Risk Assessment:")
    risk = decision['risk_assessment']
    print(f"  • Level: {risk['level'].upper()}")
    print(f"  • Score: {risk['score']:.0f}")
    if risk['warnings']:
        print(f"  • Warnings:")
        for w in risk['warnings']:
            print(f"    - {w}")
    
    print(f"\n💭 Reasoning:")
    print(decision['reasoning'])

def main():
    """รันการทดสอบทั้งหมด"""
    print("""
╔══════════════════════════════════════════════════════════╗
║     🧪 Testing Profit Optimization System               ║
║     Technical Analysis + Risk Management                ║
╚══════════════════════════════════════════════════════════╝
""")
    
    try:
        # Test 1: Technical Analysis
        test_technical_analysis()
        
        # Test 2: Risk Management
        test_risk_management()
        
        # Test 3: Integrated Decision
        test_integrated_decision()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Review the results above")
        print("2. Run simulation: python intelligent_trader.py --mode simulation")
        print("3. Check logs: cat logs/intelligent_trade_log.json")
        print("4. Read guide: cat PROFIT_OPTIMIZATION.md")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
