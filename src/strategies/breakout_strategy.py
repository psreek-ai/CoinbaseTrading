"""
Breakout trading strategy.
Identifies and trades price breakouts from consolidation.
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    """
    Breakout strategy that identifies price breaking out of ranges.
    
    BUY signals when:
    - Price breaks above recent high
    - Volume confirms the breakout
    - ATR shows increasing volatility
    
    SELL signals when:
    - Price breaks below recent low
    - Or fails to sustain breakout
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        self.lookback_period = config.get('lookback_period', 20)
        self.volume_confirmation = config.get('volume_confirmation', True)
        self.volume_threshold = config.get('volume_threshold', 2.0)
        self.atr_period = config.get('atr_period', 14)
        self.atr_multiplier = config.get('atr_multiplier', 1.5)
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add breakout indicators."""
        try:
            # ATR for volatility
            df.ta.atr(length=self.atr_period, append=True)
            
            # Volume moving average
            df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
            
            # Rolling high and low
            df['Rolling_High'] = df['High'].rolling(window=self.lookback_period).max()
            df['Rolling_Low'] = df['Low'].rolling(window=self.lookback_period).min()
            
            # Shift to get previous period's high/low (to detect breakout)
            df['Prev_Rolling_High'] = df['Rolling_High'].shift(1)
            df['Prev_Rolling_Low'] = df['Rolling_Low'].shift(1)
            
            # Range size
            df['Range_Size'] = df['Rolling_High'] - df['Rolling_Low']
            df['Range_Pct'] = (df['Range_Size'] / df['Close']) * 100
            
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Error adding indicators in BreakoutStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Analyze data and generate breakout signal."""
        
        if not self.validate_data(df, min_periods=max(self.lookback_period, self.atr_period)):
            return TradingSignal('HOLD', confidence=0.0)
        
        df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        atr_col = f'ATRr_{self.atr_period}'
        
        if atr_col not in df.columns:
            return TradingSignal('HOLD', confidence=0.0)
        
        # Volume confirmation
        volume_high = True
        if self.volume_confirmation:
            volume_high = latest['Volume'] > latest['Volume_MA'] * self.volume_threshold
        
        # BUY: Upward breakout
        buy_score = 0
        buy_reasons = []
        
        # Price breaks above previous high
        upward_breakout = (latest['Close'] > latest['Prev_Rolling_High'] and
                          previous['Close'] <= previous['Prev_Rolling_High'])
        
        if upward_breakout:
            buy_score += 3
            buy_reasons.append(f"Upward breakout above {latest['Prev_Rolling_High']:.2f}")
        
        # Strong close (close near high of candle)
        candle_range = latest['High'] - latest['Low']
        if candle_range > 0:
            close_strength = (latest['Close'] - latest['Low']) / candle_range
            if close_strength > 0.8:  # Close in top 20% of candle
                buy_score += 1
                buy_reasons.append("Strong close near high")
        
        # Volume confirmation
        if volume_high:
            buy_score += 1
            buy_reasons.append(f"High volume ({latest['Volume']:.0f})")
        
        # Consolidation before breakout (tight range)
        if latest['Range_Pct'] < 3:  # Range is less than 3% of price
            buy_score += 1
            buy_reasons.append("Breaking from consolidation")
        
        if buy_score >= 3:
            confidence = min(buy_score / 5.0, 1.0)
            logger.info(f"BUY signal for {product_id}: {', '.join(buy_reasons)}")
            return TradingSignal('BUY', confidence=confidence,
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        # SELL: Downward breakout or failed breakout
        sell_score = 0
        sell_reasons = []
        
        # Price breaks below previous low
        downward_breakout = (latest['Close'] < latest['Prev_Rolling_Low'] and
                            previous['Close'] >= previous['Prev_Rolling_Low'])
        
        if downward_breakout:
            sell_score += 3
            sell_reasons.append(f"Downward breakout below {latest['Prev_Rolling_Low']:.2f}")
        
        # Weak close (close near low of candle)
        if candle_range > 0:
            close_weakness = 1 - ((latest['Close'] - latest['Low']) / candle_range)
            if close_weakness > 0.8:  # Close in bottom 20% of candle
                sell_score += 1
                sell_reasons.append("Weak close near low")
        
        # Failed breakout (broke high but closed back in range)
        failed_breakout = (latest['High'] > latest['Prev_Rolling_High'] and
                          latest['Close'] < latest['Prev_Rolling_High'])
        if failed_breakout:
            sell_score += 2
            sell_reasons.append("Failed upward breakout")
        
        if sell_score >= 3:
            confidence = min(sell_score / 5.0, 1.0)
            logger.info(f"SELL signal for {product_id}: {', '.join(sell_reasons)}")
            return TradingSignal('SELL', confidence=confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})
        
        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'range_pct': latest['Range_Pct'],
                                   'close': latest['Close']})
