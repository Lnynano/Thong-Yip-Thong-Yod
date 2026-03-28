"""
Technical Analysis Service - วิเคราะห์ทางเทคนิคเพื่อช่วยตัดสินใจเทรด
"""
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import json
from pathlib import Path
import statistics

class TechnicalAnalysis:
    def __init__(self):
        self.price_history_file = Path(__file__).parent.parent / "cache" / "price_history.json"
        self.price_history_file.parent.mkdir(exist_ok=True)
        self.price_history = self._load_price_history()
    
    def update_price(self, buy_price: float, sell_price: float):
        """บันทึกราคาปัจจุบัน"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'buy_price': buy_price,
            'sell_price': sell_price,
            'mid_price': (buy_price + sell_price) / 2
        }
        
        self.price_history.append(entry)
        
        # เก็บแค่ 1000 รายการล่าสุด
        if len(self.price_history) > 1000:
            self.price_history = self.price_history[-1000:]
        
        self._save_price_history()
    
    def get_trend(self, periods: int = 20) -> Dict:
        """
        วิเคราะห์แนวโน้มราคา
        Returns: {
            'direction': 'up'|'down'|'sideways',
            'strength': float (0-100),
            'sma': float,
            'current_vs_sma': float (%)
        }
        """
        if len(self.price_history) < periods:
            return {
                'direction': 'unknown',
                'strength': 0,
                'sma': 0,
                'current_vs_sma': 0
            }
        
        recent_prices = [p['mid_price'] for p in self.price_history[-periods:]]
        current_price = recent_prices[-1]
        
        # Simple Moving Average
        sma = statistics.mean(recent_prices)
        
        # แนวโน้ม: เปรียบเทียบราคาปัจจุบันกับ SMA
        diff_pct = ((current_price - sma) / sma) * 100
        
        if diff_pct > 1.0:
            direction = 'up'
            strength = min(abs(diff_pct) * 20, 100)
        elif diff_pct < -1.0:
            direction = 'down'
            strength = min(abs(diff_pct) * 20, 100)
        else:
            direction = 'sideways'
            strength = 50
        
        return {
            'direction': direction,
            'strength': strength,
            'sma': sma,
            'current_vs_sma': diff_pct
        }
    
    def get_volatility(self, periods: int = 20) -> float:
        """
        คำนวณความผันผวนของราคา (Standard Deviation)
        Returns: volatility (0-100)
        """
        if len(self.price_history) < periods:
            return 50.0  # default medium volatility
        
        recent_prices = [p['mid_price'] for p in self.price_history[-periods:]]
        
        if len(recent_prices) < 2:
            return 50.0
        
        stdev = statistics.stdev(recent_prices)
        mean_price = statistics.mean(recent_prices)
        
        # Coefficient of Variation (%)
        cv = (stdev / mean_price) * 100
        
        # แปลงเป็น 0-100 scale
        volatility = min(cv * 10, 100)
        
        return volatility
    
    def get_support_resistance(self) -> Dict:
        """
        หาระดับ Support และ Resistance
        Returns: {
            'support': float,
            'resistance': float,
            'current_position': str ('near_support'|'near_resistance'|'middle')
        }
        """
        if len(self.price_history) < 50:
            return {
                'support': 0,
                'resistance': 0,
                'current_position': 'unknown'
            }
        
        recent_prices = [p['mid_price'] for p in self.price_history[-50:]]
        current_price = recent_prices[-1]
        
        # Support = ราคาต่ำสุดใน 50 periods
        support = min(recent_prices)
        
        # Resistance = ราคาสูงสุดใน 50 periods
        resistance = max(recent_prices)
        
        # ตำแหน่งปัจจุบัน
        range_size = resistance - support
        if range_size == 0:
            position = 'middle'
        else:
            position_pct = (current_price - support) / range_size
            
            if position_pct < 0.3:
                position = 'near_support'
            elif position_pct > 0.7:
                position = 'near_resistance'
            else:
                position = 'middle'
        
        return {
            'support': support,
            'resistance': resistance,
            'current_position': position
        }
    
    def get_momentum(self, periods: int = 10) -> Dict:
        """
        คำนวณ momentum (อัตราการเปลี่ยนแปลงราคา)
        Returns: {
            'momentum': float (% change),
            'signal': 'strong_buy'|'buy'|'neutral'|'sell'|'strong_sell'
        }
        """
        if len(self.price_history) < periods:
            return {
                'momentum': 0,
                'signal': 'neutral'
            }
        
        old_price = self.price_history[-periods]['mid_price']
        current_price = self.price_history[-1]['mid_price']
        
        momentum = ((current_price - old_price) / old_price) * 100
        
        # สัญญาณ
        if momentum > 2.0:
            signal = 'strong_buy'
        elif momentum > 0.5:
            signal = 'buy'
        elif momentum < -2.0:
            signal = 'strong_sell'
        elif momentum < -0.5:
            signal = 'sell'
        else:
            signal = 'neutral'
        
        return {
            'momentum': momentum,
            'signal': signal
        }
    
    def get_rsi(self, periods: int = 14) -> Dict:
        """
        คำนวณ RSI (Relative Strength Index)
        Returns: {
            'rsi': float (0-100),
            'signal': 'overbought'|'oversold'|'neutral'
        }
        """
        if len(self.price_history) < periods + 1:
            return {
                'rsi': 50,
                'signal': 'neutral'
            }
        
        recent_prices = [p['mid_price'] for p in self.price_history[-(periods+1):]]
        
        # คำนวณ gains และ losses
        gains = []
        losses = []
        
        for i in range(1, len(recent_prices)):
            change = recent_prices[i] - recent_prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = statistics.mean(gains) if gains else 0
        avg_loss = statistics.mean(losses) if losses else 0
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        # สัญญาณ
        if rsi > 70:
            signal = 'overbought'  # ควรขาย
        elif rsi < 30:
            signal = 'oversold'  # ควรซื้อ
        else:
            signal = 'neutral'
        
        return {
            'rsi': rsi,
            'signal': signal
        }
    
    def get_comprehensive_analysis(self) -> Dict:
        """
        วิเคราะห์แบบครบถ้วน รวมทุก indicator
        """
        trend = self.get_trend()
        volatility = self.get_volatility()
        support_resistance = self.get_support_resistance()
        momentum = self.get_momentum()
        rsi = self.get_rsi()
        
        # คำนวณคะแนนรวม (buy/sell score)
        buy_score = 0
        sell_score = 0
        
        # Trend
        if trend['direction'] == 'up':
            buy_score += trend['strength'] / 100 * 30
        elif trend['direction'] == 'down':
            sell_score += trend['strength'] / 100 * 30
        
        # Momentum
        if momentum['signal'] in ['strong_buy', 'buy']:
            buy_score += 20
        elif momentum['signal'] in ['strong_sell', 'sell']:
            sell_score += 20
        
        # RSI
        if rsi['signal'] == 'oversold':
            buy_score += 25
        elif rsi['signal'] == 'overbought':
            sell_score += 25
        
        # Support/Resistance
        if support_resistance['current_position'] == 'near_support':
            buy_score += 15
        elif support_resistance['current_position'] == 'near_resistance':
            sell_score += 15
        
        # สรุปสัญญาณ
        if buy_score > sell_score + 20:
            overall_signal = 'BUY'
            confidence = min(buy_score, 100)
        elif sell_score > buy_score + 20:
            overall_signal = 'SELL'
            confidence = min(sell_score, 100)
        else:
            overall_signal = 'HOLD'
            confidence = 50
        
        return {
            'trend': trend,
            'volatility': volatility,
            'support_resistance': support_resistance,
            'momentum': momentum,
            'rsi': rsi,
            'overall_signal': overall_signal,
            'confidence': confidence,
            'buy_score': buy_score,
            'sell_score': sell_score
        }
    
    def _load_price_history(self) -> List[Dict]:
        """โหลดประวัติราคา"""
        if not self.price_history_file.exists():
            return []
        
        try:
            with open(self.price_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    
    def _save_price_history(self):
        """บันทึกประวัติราคา"""
        try:
            with open(self.price_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.price_history, f, indent=2)
        except Exception as e:
            print(f"Error saving price history: {e}")

if __name__ == "__main__":
    # Test
    ta = TechnicalAnalysis()
    
    # Simulate some price data
    import random
    base_price = 2500
    for i in range(50):
        price = base_price + random.uniform(-50, 50)
        ta.update_price(price + 30, price)
    
    analysis = ta.get_comprehensive_analysis()
    print("Technical Analysis:")
    print(f"  Overall Signal: {analysis['overall_signal']}")
    print(f"  Confidence: {analysis['confidence']:.1f}%")
    print(f"  Trend: {analysis['trend']['direction']} (strength: {analysis['trend']['strength']:.1f})")
    print(f"  RSI: {analysis['rsi']['rsi']:.1f} ({analysis['rsi']['signal']})")
    print(f"  Momentum: {analysis['momentum']['momentum']:.2f}% ({analysis['momentum']['signal']})")
