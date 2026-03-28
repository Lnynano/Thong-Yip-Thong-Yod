"""
Agent Brain - Decision making logic using ReAct framework
Analyzes market conditions and makes trading decisions
"""
from datetime import datetime
from typing import Dict, Any
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.news_service import NewsService
from services.technical_analysis import TechnicalAnalysis
from services.risk_manager import RiskManager

class AgentBrain:
    def __init__(self):
        self.latest_thought = ""
        self.decision_history = []
        self.news_service = NewsService()
        self.technical_analysis = TechnicalAnalysis()
        self.risk_manager = RiskManager(initial_capital=1500.0)
        self.last_entry_price = None  # ติดตามราคาที่เข้า position
    
    def fetch_macro_news(self) -> str:
        """
        Fetch macroeconomic news affecting gold prices
        Uses NewsService to get real market data
        """
        try:
            news_data = self.news_service.fetch_gold_news()
            return self.news_service.format_for_agent(news_data)
        except Exception as e:
            print(f"Error fetching news: {e}")
            # Fallback to basic news
            return "Market data temporarily unavailable"
    
    def make_decision(
        self,
        app_state: Dict[str, float],
        macro_news: str,
        portfolio_state: Any,
        simulation: bool = False
    ) -> Dict[str, Any]:
        """
        Make trading decision using ReAct framework + Technical Analysis + Risk Management
        Returns: {observation, reasoning, action, confidence, technical_analysis, risk_assessment}
        """
        # อัปเดตราคาใน Technical Analysis
        self.technical_analysis.update_price(
            app_state['buy_price'],
            app_state['sell_price']
        )
        
        # OBSERVATION
        observation = self._observe(app_state, portfolio_state)
        
        # TECHNICAL ANALYSIS
        tech_analysis = self.technical_analysis.get_comprehensive_analysis()
        
        # REASONING (รวม technical + fundamental)
        reasoning = self._reason(app_state, macro_news, portfolio_state, tech_analysis)
        
        # RISK ASSESSMENT
        equity = portfolio_state.equity
        pnl_pct = ((equity - portfolio_state.initial_capital) / portfolio_state.initial_capital) * 100
        
        risk_recommendation = self.risk_manager.get_trading_recommendation(
            equity=equity,
            pnl_pct=pnl_pct,
            volatility=tech_analysis['volatility'],
            technical_signal=tech_analysis['overall_signal'],
            confidence=tech_analysis['confidence']
        )
        
        # ACTION (ใช้ technical + risk management)
        action = self._decide_action(
            app_state,
            portfolio_state,
            reasoning,
            tech_analysis,
            risk_recommendation
        )
        
        # Calculate confidence (รวม technical + fundamental)
        confidence = self._calculate_confidence(reasoning, tech_analysis, risk_recommendation)
        
        decision = {
            "timestamp": datetime.now().isoformat(),
            "observation": observation,
            "reasoning": reasoning,
            "action": action,
            "confidence": confidence,
            "technical_analysis": tech_analysis,
            "risk_assessment": risk_recommendation['risk_assessment'],
            "simulation": simulation
        }
        
        self.latest_thought = self._format_thought(decision)
        self.decision_history.append(decision)
        
        return decision
    
    def _observe(self, app_state: Dict, portfolio_state: Any) -> str:
        """Observation phase - what do we see?"""
        obs = f"""
Current State:
- Cash: {app_state['cash_balance']:.2f} THB
- Gold: {app_state['gold_balance']:.4f} g
- Buy Price: {app_state['buy_price']:.2f} THB/g
- Sell Price: {app_state['sell_price']:.2f} THB/g
- Spread: {app_state['buy_price'] - app_state['sell_price']:.2f} THB/g
- Traded Today: {portfolio_state.has_traded_today()}
"""
        return obs.strip()
    
    def _reason(self, app_state: Dict, macro_news: str, portfolio_state: Any, tech_analysis: Dict) -> str:
        """Reasoning phase - analyze and think (รวม technical + fundamental)"""
        reasoning_parts = []
        
        # Check daily trade requirement
        if not portfolio_state.has_traded_today():
            reasoning_parts.append("⚠️ CRITICAL: Must execute at least one trade today (VC Rule #2)")
        
        # Analyze price spread
        spread = app_state['buy_price'] - app_state['sell_price']
        spread_pct = (spread / app_state['sell_price']) * 100
        
        if spread_pct < 1.5:
            reasoning_parts.append(f"✅ Price spread: {spread:.2f} THB ({spread_pct:.2f}%) - GOOD for buying")
        elif spread_pct < 2.5:
            reasoning_parts.append(f"⚠️ Price spread: {spread:.2f} THB ({spread_pct:.2f}%) - MODERATE")
        else:
            reasoning_parts.append(f"❌ Price spread: {spread:.2f} THB ({spread_pct:.2f}%) - HIGH (risky)")
        
        # TECHNICAL ANALYSIS
        reasoning_parts.append("\n📊 TECHNICAL ANALYSIS:")
        reasoning_parts.append(f"  • Trend: {tech_analysis['trend']['direction'].upper()} (strength: {tech_analysis['trend']['strength']:.0f}%)")
        reasoning_parts.append(f"  • RSI: {tech_analysis['rsi']['rsi']:.1f} ({tech_analysis['rsi']['signal']})")
        reasoning_parts.append(f"  • Momentum: {tech_analysis['momentum']['momentum']:+.2f}% ({tech_analysis['momentum']['signal']})")
        reasoning_parts.append(f"  • Volatility: {tech_analysis['volatility']:.0f}%")
        reasoning_parts.append(f"  • Position: {tech_analysis['support_resistance']['current_position']}")
        reasoning_parts.append(f"  • Overall Signal: {tech_analysis['overall_signal']} (confidence: {tech_analysis['confidence']:.0f}%)")
        
        # Analyze macro news sentiment
        news_lower = macro_news.lower()
        bullish_signals = [
            'bullish', 'surge', 'rally', 'tension', 'crisis', 
            'uncertainty', 'inflation', 'fear', 'geopolitical', 'rise', 'gain'
        ]
        bearish_signals = [
            'bearish', 'drop', 'decline', 'strong dollar', 
            'rate hike', 'inflation drops', 'rates maintain', 'fall', 'weak'
        ]
        
        bullish_count = sum(1 for signal in bullish_signals if signal in news_lower)
        bearish_count = sum(1 for signal in bearish_signals if signal in news_lower)
        
        if bullish_count > bearish_count:
            reasoning_parts.append(f"\n📈 FUNDAMENTAL: Bullish for gold ({bullish_count} bullish vs {bearish_count} bearish signals)")
        elif bearish_count > bullish_count:
            reasoning_parts.append(f"\n📉 FUNDAMENTAL: Bearish for gold ({bearish_count} bearish vs {bullish_count} bullish signals)")
        else:
            reasoning_parts.append("\n➡️ FUNDAMENTAL: Neutral sentiment")
        
        # Portfolio analysis
        equity = portfolio_state.equity
        pnl = equity - portfolio_state.initial_capital
        pnl_pct = (pnl / portfolio_state.initial_capital) * 100
        
        if pnl > 0:
            reasoning_parts.append(f"\n💰 PnL: {pnl:+.2f} THB ({pnl_pct:+.2f}%) - In profit")
        elif pnl < -50:
            reasoning_parts.append(f"\n⚠️ PnL: {pnl:+.2f} THB ({pnl_pct:+.2f}%) - Significant loss")
        else:
            reasoning_parts.append(f"\n📊 PnL: {pnl:+.2f} THB ({pnl_pct:+.2f}%)")
        
        # Position analysis
        gold_ratio = (portfolio_state.gold_value / equity) * 100 if equity > 0 else 0
        cash_ratio = (portfolio_state.cash_balance / equity) * 100 if equity > 0 else 0
        reasoning_parts.append(f"📦 Position: {gold_ratio:.1f}% gold, {cash_ratio:.1f}% cash")
        
        # Check liquidation deadline
        days_left = portfolio_state.days_until_deadline()
        if days_left <= 7:
            reasoning_parts.append(f"\n⏰ WARNING: Only {days_left} days until mandatory liquidation!")
        
        return "\n".join(reasoning_parts)
    
    def _decide_action(
        self,
        app_state: Dict,
        portfolio_state: Any,
        reasoning: str,
        tech_analysis: Dict,
        risk_recommendation: Dict
    ) -> str:
        """
        Action phase - ตัดสินใจโดยใช้ Technical + Fundamental + Risk Management
        """
        # Check if liquidation is required
        if portfolio_state.days_until_deadline() == 0:
            return "SELL_ALL (Mandatory liquidation)"
        
        cash = app_state['cash_balance']
        gold = app_state['gold_balance']
        spread = app_state['buy_price'] - app_state['sell_price']
        spread_pct = (spread / app_state['sell_price']) * 100
        equity = portfolio_state.equity
        pnl = equity - portfolio_state.initial_capital
        pnl_pct = (pnl / portfolio_state.initial_capital) * 100
        
        # ตรวจสอบ Stop Loss / Take Profit
        if gold > 0 and self.last_entry_price:
            should_tp, tp_reason = self.risk_manager.should_take_profit(
                self.last_entry_price,
                app_state['sell_price'],
                'LONG'
            )
            if should_tp:
                sell_amount = gold * 0.7  # ขาย 70% เก็บกำไร
                return f"SELL {sell_amount:.4f} g ({tp_reason})"
            
            should_sl, sl_reason = self.risk_manager.should_stop_loss(
                self.last_entry_price,
                app_state['sell_price'],
                'LONG'
            )
            if should_sl:
                sell_amount = gold * 0.5  # ขาย 50% ตัดขาดทุน
                return f"SELL {sell_amount:.4f} g ({sl_reason})"
        
        # ถ้า Risk Manager บอกว่าไม่ควรเทรด
        if not risk_recommendation['should_trade']:
            reasons = ", ".join(risk_recommendation['reasons'])
            return f"HOLD ({reasons})"
        
        # ใช้ Technical Signal เป็นหลัก
        tech_signal = tech_analysis['overall_signal']
        position_sizing = risk_recommendation['position_sizing']
        
        # If haven't traded today, must trade
        if not portfolio_state.has_traded_today():
            if cash >= 100 and tech_signal != 'SELL':
                # ซื้อตาม position sizing
                amount = min(position_sizing['position_size_thb'], cash)
                amount = max(amount, 100)  # ขั้นต่ำ 100 THB
                self.last_entry_price = app_state['buy_price']
                return f"BUY {amount:.2f} THB (Daily requirement + {tech_signal})"
            elif gold > 0:
                sell_amount = min(gold * 0.3, gold)
                return f"SELL {sell_amount:.4f} g (Daily requirement)"
        
        # Normal trading logic - ใช้ Technical + Risk Management
        if tech_signal == 'BUY' and cash >= 100:
            # ซื้อตาม position sizing ที่คำนวณจาก risk manager
            amount = min(position_sizing['position_size_thb'], cash)
            
            # ปรับตาม RSI
            if tech_analysis['rsi']['signal'] == 'oversold':
                amount *= 1.2  # เพิ่ม 20% ถ้า oversold
            
            # ปรับตาม momentum
            if tech_analysis['momentum']['signal'] in ['strong_buy']:
                amount *= 1.3  # เพิ่ม 30% ถ้า momentum แรง
            
            # ปรับตาม support/resistance
            if tech_analysis['support_resistance']['current_position'] == 'near_support':
                amount *= 1.2  # เพิ่ม 20% ถ้าใกล้ support
            
            amount = min(amount, cash)
            amount = max(amount, 100)  # ขั้นต่ำ 100 THB
            
            self.last_entry_price = app_state['buy_price']
            return f"BUY {amount:.2f} THB (Technical: {tech_signal}, RSI: {tech_analysis['rsi']['rsi']:.0f})"
        
        elif tech_signal == 'SELL' and gold > 0:
            # ขายตาม risk management
            if pnl > 0:  # กำไรอยู่ = ขายเก็บกำไร
                sell_ratio = 0.70
            elif pnl < -50:  # ขาดทุนมาก = cut loss
                sell_ratio = 0.60
            else:
                sell_ratio = 0.40
            
            # ปรับตาม RSI
            if tech_analysis['rsi']['signal'] == 'overbought':
                sell_ratio *= 1.2  # ขายมากขึ้นถ้า overbought
            
            # ปรับตาม momentum
            if tech_analysis['momentum']['signal'] in ['strong_sell']:
                sell_ratio *= 1.3  # ขายมากขึ้นถ้า momentum ลง
            
            sell_amount = min(gold * sell_ratio, gold)
            return f"SELL {sell_amount:.4f} g (Technical: {tech_signal}, PnL: {pnl:+.2f})"
        
        else:
            # HOLD - ไม่มีสัญญาณชัดเจน
            return f"HOLD (Technical: {tech_signal}, Confidence: {tech_analysis['confidence']:.0f}%)"
    
    def _calculate_confidence(self, reasoning: str, tech_analysis: Dict, risk_recommendation: Dict) -> float:
        """Calculate confidence level (0-100) รวม technical + fundamental + risk"""
        confidence = 50.0
        
        # Technical confidence
        confidence += (tech_analysis['confidence'] - 50) * 0.5  # น้ำหนัก 50%
        
        # Fundamental signals
        if "CRITICAL" in reasoning:
            confidence += 20
        if "Bullish" in reasoning or "Bearish" in reasoning:
            confidence += 15
        if "WARNING" in reasoning:
            confidence -= 10
        
        # Risk assessment
        risk_level = risk_recommendation['risk_assessment']['level']
        if risk_level == 'low':
            confidence += 10
        elif risk_level == 'high':
            confidence -= 15
        elif risk_level == 'critical':
            confidence -= 30
        
        return min(100.0, max(0.0, confidence))
    
    def _format_thought(self, decision: Dict) -> str:
        """Format decision as readable thought process"""
        return f"""
[{decision['timestamp']}]
{decision['observation']}

💭 Reasoning:
{decision['reasoning']}

⚡ Action: {decision['action']}
🎯 Confidence: {decision['confidence']:.1f}%
"""
    
    def get_latest_thought(self) -> str:
        """Get the latest thinking process"""
        return self.latest_thought
    
    def simulate_buy(self, amount_thb: float, portfolio_state: Any) -> str:
        """Simulate buy action without actual execution"""
        return f"[SIMULATION] BUY {amount_thb} THB - No actual trade executed"
    
    def simulate_sell(self, amount_gold: float, portfolio_state: Any) -> str:
        """Simulate sell action without actual execution"""
        return f"[SIMULATION] SELL {amount_gold} g - No actual trade executed"
    
    def simulate_sell_all(self, portfolio_state: Any) -> str:
        """Simulate sell all action"""
        return f"[SIMULATION] SELL ALL - No actual trade executed"
