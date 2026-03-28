# 🚀 Quick Reference - Profit Optimization System

## 📋 Quick Commands

### Test the System
```bash
python test_profit_system.py
```

### Run Trading Bot (Simulation)
```bash
python intelligent_trader.py --mode simulation
```

### View Dashboard
```bash
python run_dashboard.py
# Open: http://localhost:7860
```

### Check Logs
```bash
# Trade log
cat logs/intelligent_trade_log.json

# System log
cat intelligent_trader.log

# Price history
cat cache/price_history.json
```

---

## 🎯 Key Indicators Explained

### RSI (Relative Strength Index)
- **< 30**: Oversold → Good time to BUY
- **30-70**: Neutral → Wait for clearer signal
- **> 70**: Overbought → Good time to SELL

### Momentum
- **> +2%**: Strong uptrend → BUY signal
- **+0.5% to +2%**: Weak uptrend → Cautious BUY
- **-0.5% to +0.5%**: Sideways → HOLD
- **-2% to -0.5%**: Weak downtrend → Cautious SELL
- **< -2%**: Strong downtrend → SELL signal

### Trend
- **UP**: Price above SMA → Bullish
- **DOWN**: Price below SMA → Bearish
- **SIDEWAYS**: Price near SMA → Neutral

### Volatility
- **< 30%**: Low volatility → Can trade larger positions
- **30-60%**: Medium volatility → Normal position size
- **> 60%**: High volatility → Reduce position size

---

## 🛡️ Risk Management Rules

### Position Sizing
- **High confidence (>80%) + Low volatility (<30%)**: 30-40% of equity
- **Medium confidence (60-80%) + Medium volatility (30-60%)**: 15-20% of equity
- **Low confidence (<60%) + High volatility (>60%)**: 5-10% of equity

### Stop Loss
- Automatically triggered at **-3%** loss
- Example: Buy at 2500 → Stop loss at 2425

### Take Profit
- Automatically triggered at **+5%** profit
- Example: Buy at 2500 → Take profit at 2625

### Max Drawdown
- Trading stops if total loss exceeds **-20%**
- Example: Start with 1500 THB → Stop if equity < 1200 THB

---

## 📊 Decision Making Logic

### BUY Conditions (All must be true)
1. ✅ RSI < 40 (preferably < 30)
2. ✅ Momentum > 0
3. ✅ Trend = UP or SIDEWAYS
4. ✅ Fundamental news = Bullish
5. ✅ Risk level = Low or Medium
6. ✅ Confidence > 60%

### SELL Conditions (All must be true)
1. ✅ RSI > 60 (preferably > 70)
2. ✅ Momentum < 0
3. ✅ Trend = DOWN or SIDEWAYS
4. ✅ Fundamental news = Bearish
5. ✅ Risk level = Low or Medium
6. ✅ Confidence > 60%

### HOLD Conditions (Any is true)
1. ⚠️ Confidence < 60%
2. ⚠️ Risk level = High or Critical
3. ⚠️ Volatility > 80%
4. ⚠️ No clear signal from indicators

---

## 🔧 Configuration Quick Guide

### Adjust Risk Tolerance
Edit `services/risk_manager.py`:
```python
# More conservative (safer)
self.stop_loss_pct = 2.0  # Stop loss at -2%
self.take_profit_pct = 3.0  # Take profit at +3%
self.max_position_size_pct = 30.0  # Max 30% per trade

# More aggressive (riskier)
self.stop_loss_pct = 5.0  # Stop loss at -5%
self.take_profit_pct = 8.0  # Take profit at +8%
self.max_position_size_pct = 50.0  # Max 50% per trade
```

### Adjust Confidence Threshold
Edit `intelligent_trader.py`:
```python
# More conservative (trade less often)
self.min_confidence_to_trade = 70.0  # Need 70% confidence

# More aggressive (trade more often)
self.min_confidence_to_trade = 50.0  # Need 50% confidence
```

### Adjust Technical Indicators
Edit `services/technical_analysis.py`:
```python
# Longer-term analysis
def get_trend(self, periods: int = 50):  # Use 50-period SMA
def get_rsi(self, periods: int = 21):  # Use 21-period RSI

# Shorter-term analysis
def get_trend(self, periods: int = 10):  # Use 10-period SMA
def get_rsi(self, periods: int = 7):  # Use 7-period RSI
```

---

## 📈 Reading the Logs

### Example Trade Log Entry
```json
{
  "timestamp": "2026-03-28T14:30:00",
  "decision": {
    "action": "BUY 225.00 THB (Technical: BUY, RSI: 28)",
    "confidence": 78.5,
    "technical_analysis": {
      "overall_signal": "BUY",
      "rsi": {"rsi": 28.5, "signal": "oversold"},
      "momentum": {"momentum": 1.8, "signal": "buy"},
      "trend": {"direction": "up", "strength": 65}
    },
    "risk_assessment": {
      "level": "low",
      "score": 15
    }
  },
  "result": "[SIM] Bought 0.0869g for 225.00 THB @ 2590.00",
  "portfolio": {
    "equity": 1500.29,
    "pnl": 0.29,
    "pnl_pct": 0.02
  }
}
```

### What to Look For:
- **Confidence > 70%**: High-quality trade
- **Risk level = low**: Safe trade
- **RSI < 30 or > 70**: Strong signal
- **PnL trending up**: System is profitable

---

## 🎓 Common Scenarios

### Scenario 1: Strong Buy Signal
```
RSI: 25 (oversold)
Momentum: +2.5% (strong buy)
Trend: UP (strength: 70%)
News: Bullish (geopolitical tension)
Risk: Low
→ BUY 350 THB (30% of equity)
```

### Scenario 2: Weak Signal
```
RSI: 55 (neutral)
Momentum: +0.3% (weak)
Trend: SIDEWAYS
News: Neutral
Risk: Medium
→ HOLD (wait for better opportunity)
```

### Scenario 3: High Risk
```
RSI: 35 (slightly oversold)
Momentum: +1.2% (buy)
Trend: UP
News: Bullish
Risk: HIGH (volatility 85%, drawdown -12%)
→ HOLD or small BUY (risk too high)
```

### Scenario 4: Take Profit
```
Entry: 2500 THB
Current: 2630 THB
PnL: +5.2%
→ SELL 70% (take profit, keep 30% for further gains)
```

### Scenario 5: Stop Loss
```
Entry: 2500 THB
Current: 2425 THB
PnL: -3.0%
→ SELL 50% (cut loss, reassess)
```

---

## 🐛 Troubleshooting

### Issue: Confidence always low
**Solution**: Check if price history has enough data (need 20+ entries)
```bash
cat cache/price_history.json | grep timestamp | wc -l
```

### Issue: No trades happening
**Possible causes**:
1. Confidence threshold too high → Lower in `intelligent_trader.py`
2. Risk level always high → Check volatility and PnL
3. No clear signals → Wait for market movement

### Issue: Too many trades
**Solution**: Increase confidence threshold
```python
self.min_confidence_to_trade = 70.0  # Increase from 60.0
```

### Issue: Losses accumulating
**Check**:
1. Stop loss working? → Should trigger at -3%
2. Risk management active? → Check risk_assessment in logs
3. Market conditions? → High volatility = reduce trading

---

## 📞 Quick Help

### View Technical Analysis
```python
from services.technical_analysis import TechnicalAnalysis
ta = TechnicalAnalysis()
# ... update prices ...
analysis = ta.get_comprehensive_analysis()
print(f"Signal: {analysis['overall_signal']}")
print(f"RSI: {analysis['rsi']['rsi']:.1f}")
```

### View Risk Assessment
```python
from services.risk_manager import RiskManager
rm = RiskManager(initial_capital=1500.0)
risk = rm.get_risk_level(equity=1450, pnl_pct=-3.3, volatility=45)
print(f"Risk: {risk['level']}")
```

### Manual Trade Simulation
```python
from services.agent_brain import AgentBrain
from models.portfolio import PortfolioState

agent = AgentBrain()
portfolio = PortfolioState(initial_capital=1500.0)

app_state = {
    'cash_balance': 1500.0,
    'gold_balance': 0.0,
    'buy_price': 2590.0,
    'sell_price': 2540.0
}

decision = agent.make_decision(
    app_state=app_state,
    macro_news="Bullish news...",
    portfolio_state=portfolio,
    simulation=True
)

print(f"Action: {decision['action']}")
print(f"Confidence: {decision['confidence']:.1f}%")
```

---

## 🎯 Success Metrics

### Good Performance
- ✅ Win rate > 60%
- ✅ Average PnL > 0
- ✅ Max drawdown < 15%
- ✅ Confidence on winning trades > 70%

### Warning Signs
- ⚠️ Win rate < 50%
- ⚠️ Drawdown > 15%
- ⚠️ Many low-confidence trades (<60%)
- ⚠️ Frequent stop losses

### Action Items
1. Review trade logs
2. Adjust risk parameters
3. Increase confidence threshold
4. Reduce position sizes
5. Wait for better market conditions

---

## 📚 Documentation Links

- Full guide: `PROFIT_OPTIMIZATION.md`
- Thai summary: `สรุปการปรับปรุง.md`
- Technical details: `WHAT_WAS_ADDED.md`
- Main README: `README.md`

---

**Remember**: Start with simulation mode, monitor results, adjust parameters, then go live! 🚀
