"""
Risk Manager - จัดการความเสี่ยงและ position sizing
"""
from typing import Dict, Tuple
from datetime import datetime

class RiskManager:
    def __init__(self, initial_capital: float = 1500.0):
        self.initial_capital = initial_capital
        self.max_loss_per_trade_pct = 2.0  # ขาดทุนสูงสุด 2% ต่อการเทรด
        self.max_total_loss_pct = 20.0  # ขาดทุนสูงสุดรวม 20%
        self.take_profit_pct = 5.0  # เก็บกำไรที่ 5%
        self.stop_loss_pct = 3.0  # ตัดขาดทุนที่ 3%
        
        # Position sizing rules
        self.min_position_size_pct = 5.0  # ขั้นต่ำ 5% ของ capital
        self.max_position_size_pct = 40.0  # สูงสุด 40% ของ capital
        self.default_position_size_pct = 15.0  # ปกติ 15%
    
    def calculate_position_size(
        self,
        equity: float,
        confidence: float,
        volatility: float,
        pnl_pct: float
    ) -> Dict:
        """
        คำนวณขนาด position ที่เหมาะสม
        Args:
            equity: มูลค่าพอร์ตปัจจุบัน
            confidence: ความมั่นใจในการเทรด (0-100)
            volatility: ความผันผวนของตลาด (0-100)
            pnl_pct: กำไร/ขาดทุนปัจจุบัน (%)
        
        Returns: {
            'position_size_thb': float,
            'position_size_pct': float,
            'reason': str
        }
        """
        # Base position size
        base_pct = self.default_position_size_pct
        
        # ปรับตาม confidence
        if confidence >= 80:
            base_pct *= 1.5  # เพิ่ม 50%
        elif confidence >= 70:
            base_pct *= 1.2  # เพิ่ม 20%
        elif confidence < 60:
            base_pct *= 0.7  # ลด 30%
        
        # ปรับตาม volatility (ยิ่งผันผวนมาก ยิ่งลด position)
        if volatility > 70:
            base_pct *= 0.6  # ลด 40%
        elif volatility > 50:
            base_pct *= 0.8  # ลด 20%
        
        # ปรับตาม PnL (ถ้าขาดทุนมาก ลด position)
        if pnl_pct < -10:
            base_pct *= 0.5  # ลด 50%
        elif pnl_pct < -5:
            base_pct *= 0.7  # ลด 30%
        elif pnl_pct > 5:
            base_pct *= 1.2  # เพิ่ม 20% (ใช้กำไรเทรด)
        
        # จำกัดขอบเขต
        final_pct = max(self.min_position_size_pct, min(base_pct, self.max_position_size_pct))
        position_size_thb = equity * (final_pct / 100)
        
        reason = f"Confidence: {confidence:.0f}%, Volatility: {volatility:.0f}%, PnL: {pnl_pct:+.1f}%"
        
        return {
            'position_size_thb': position_size_thb,
            'position_size_pct': final_pct,
            'reason': reason
        }
    
    def should_take_profit(self, entry_price: float, current_price: float, position_type: str) -> Tuple[bool, str]:
        """
        ตรวจสอบว่าควร take profit หรือไม่
        Args:
            entry_price: ราคาที่เข้า position
            current_price: ราคาปัจจุบัน
            position_type: 'LONG' (ถือทอง) หรือ 'SHORT' (ถือเงิน)
        """
        if position_type == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        if pnl_pct >= self.take_profit_pct:
            return True, f"Take profit at {pnl_pct:+.2f}% (target: {self.take_profit_pct}%)"
        
        return False, ""
    
    def should_stop_loss(self, entry_price: float, current_price: float, position_type: str) -> Tuple[bool, str]:
        """
        ตรวจสอบว่าควร stop loss หรือไม่
        """
        if position_type == 'LONG':
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100
        
        if pnl_pct <= -self.stop_loss_pct:
            return True, f"Stop loss at {pnl_pct:+.2f}% (limit: -{self.stop_loss_pct}%)"
        
        return False, ""
    
    def check_max_drawdown(self, current_equity: float) -> Tuple[bool, str]:
        """
        ตรวจสอบว่าขาดทุนเกินขีดจำกัดหรือไม่
        """
        total_loss_pct = ((current_equity - self.initial_capital) / self.initial_capital) * 100
        
        if total_loss_pct <= -self.max_total_loss_pct:
            return True, f"Max drawdown reached: {total_loss_pct:+.2f}% (limit: -{self.max_total_loss_pct}%)"
        
        return False, ""
    
    def get_risk_level(self, equity: float, pnl_pct: float, volatility: float) -> Dict:
        """
        ประเมินระดับความเสี่ยงปัจจุบัน
        Returns: {
            'level': 'low'|'medium'|'high'|'critical',
            'score': float (0-100),
            'warnings': List[str]
        }
        """
        risk_score = 0
        warnings = []
        
        # ตรวจสอบ drawdown
        if pnl_pct < -15:
            risk_score += 40
            warnings.append(f"Large drawdown: {pnl_pct:+.1f}%")
        elif pnl_pct < -10:
            risk_score += 25
            warnings.append(f"Moderate drawdown: {pnl_pct:+.1f}%")
        elif pnl_pct < -5:
            risk_score += 10
        
        # ตรวจสอบ volatility
        if volatility > 70:
            risk_score += 30
            warnings.append(f"High volatility: {volatility:.0f}")
        elif volatility > 50:
            risk_score += 15
        
        # ตรวจสอบ capital
        capital_ratio = equity / self.initial_capital
        if capital_ratio < 0.85:
            risk_score += 20
            warnings.append(f"Low capital: {capital_ratio:.1%} of initial")
        
        # กำหนดระดับ
        if risk_score >= 70:
            level = 'critical'
        elif risk_score >= 50:
            level = 'high'
        elif risk_score >= 30:
            level = 'medium'
        else:
            level = 'low'
        
        return {
            'level': level,
            'score': risk_score,
            'warnings': warnings
        }
    
    def get_trading_recommendation(
        self,
        equity: float,
        pnl_pct: float,
        volatility: float,
        technical_signal: str,
        confidence: float
    ) -> Dict:
        """
        ให้คำแนะนำการเทรดโดยพิจารณาความเสี่ยง
        """
        risk_assessment = self.get_risk_level(equity, pnl_pct, volatility)
        position_sizing = self.calculate_position_size(equity, confidence, volatility, pnl_pct)
        
        # ตัดสินใจ
        should_trade = True
        adjusted_signal = technical_signal
        reasons = []
        
        # ถ้าความเสี่ยงสูงมาก
        if risk_assessment['level'] == 'critical':
            should_trade = False
            reasons.append("Risk level CRITICAL - trading suspended")
        
        # ถ้าความเสี่ยงสูง
        elif risk_assessment['level'] == 'high':
            if confidence < 75:
                should_trade = False
                reasons.append("High risk + low confidence - skip trade")
            else:
                position_sizing['position_size_thb'] *= 0.5
                reasons.append("High risk - reduced position size by 50%")
        
        # ถ้า volatility สูงมาก
        if volatility > 80:
            should_trade = False
            reasons.append("Extreme volatility - too risky")
        
        return {
            'should_trade': should_trade,
            'signal': adjusted_signal,
            'position_sizing': position_sizing,
            'risk_assessment': risk_assessment,
            'reasons': reasons
        }

if __name__ == "__main__":
    # Test
    rm = RiskManager(initial_capital=1500.0)
    
    # Test position sizing
    result = rm.calculate_position_size(
        equity=1450.0,
        confidence=75.0,
        volatility=45.0,
        pnl_pct=-3.3
    )
    print("Position Sizing:")
    print(f"  Size: {result['position_size_thb']:.2f} THB ({result['position_size_pct']:.1f}%)")
    print(f"  Reason: {result['reason']}")
    
    # Test risk level
    risk = rm.get_risk_level(equity=1450.0, pnl_pct=-3.3, volatility=45.0)
    print(f"\nRisk Level: {risk['level']} (score: {risk['score']:.0f})")
    if risk['warnings']:
        print("Warnings:")
        for w in risk['warnings']:
            print(f"  - {w}")
