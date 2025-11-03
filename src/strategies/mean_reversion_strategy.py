"""
Mean reversion trading strategy.
Buys when price is oversold and sells when overbought.
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy that profits from price returning to average.
    
    BUY signals when:
    - Price touches or breaks below lower Bollinger Band
    - RSI is extremely oversold (< 20)
    - Price is significantly below moving average
    
    SELL signals when:
    - Price touches or breaks above upper Bollinger Band
    - RSI is extremely overbought (> 80)
    - Price is significantly above moving average
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_extreme_oversold = config.get('rsi_extreme_oversold', 20)
        self.rsi_extreme_overbought = config.get('rsi_extreme_overbought', 80)
        self.mean_lookback = config.get('mean_lookback', 50)
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add mean reversion indicators."""
        try:
            # Bollinger Bands
            df.ta.bbands(length=self.bb_period, std=self.bb_std, append=True)
            
            # RSI
            df.ta.rsi(length=self.rsi_period, append=True)
            
            # Simple Moving Average
            df['SMA'] = df['Close'].rolling(window=self.mean_lookback).mean()
            
            # Calculate distance from mean (as percentage)
            df['Distance_From_Mean'] = ((df['Close'] - df['SMA']) / df['SMA']) * 100
            
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Error adding indicators in MeanReversionStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Analyze data and generate mean reversion signal."""
        
        if not self.validate_data(df, min_periods=self.mean_lookback):
            return TradingSignal('HOLD', confidence=0.0)
        
        df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Column names
        upper_bb_col = f'BBU_{self.bb_period}_{self.bb_std}'
        lower_bb_col = f'BBL_{self.bb_period}_{self.bb_std}'
        rsi_col = f'RSI_{self.rsi_period}'
        
        if not all(col in df.columns for col in [upper_bb_col, lower_bb_col, rsi_col]):
            return TradingSignal('HOLD', confidence=0.0)
        
        # BUY conditions (oversold - expecting bounce)
        buy_score = 0
        buy_reasons = []
        
        # Price below lower BB
        if latest['Close'] <= latest[lower_bb_col]:
            buy_score += 2
            buy_reasons.append(f"Price at/below lower BB ({latest['Close']:.2f} <= {latest[lower_bb_col]:.2f})")
        
        # Extreme RSI oversold
        if latest[rsi_col] < self.rsi_extreme_oversold:
            buy_score += 2
            buy_reasons.append(f"RSI extremely oversold ({latest[rsi_col]:.1f})")
        elif latest[rsi_col] < 30:
            buy_score += 1
            buy_reasons.append(f"RSI oversold ({latest[rsi_col]:.1f})")
        
        # Price significantly below mean
        if latest['Distance_From_Mean'] < -5:  # More than 5% below mean
            buy_score += 1
            buy_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% below mean")
        
        # Price bouncing from lower BB
        if previous['Close'] < previous[lower_bb_col] and latest['Close'] > latest[lower_bb_col]:
            buy_score += 1
            buy_reasons.append("Bouncing from lower BB")
        
        if buy_score >= 3:
            confidence = min(buy_score / 5.0, 1.0)
            logger.info(f"BUY signal for {product_id}: {', '.join(buy_reasons)}")
            return TradingSignal('BUY', confidence=confidence,
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        # SELL conditions (overbought - expecting pullback)
        sell_score = 0
        sell_reasons = []
        
        # Price above upper BB
        if latest['Close'] >= latest[upper_bb_col]:
            sell_score += 2
            sell_reasons.append(f"Price at/above upper BB ({latest['Close']:.2f} >= {latest[upper_bb_col]:.2f})")
        
        # Extreme RSI overbought
        if latest[rsi_col] > self.rsi_extreme_overbought:
            sell_score += 2
            sell_reasons.append(f"RSI extremely overbought ({latest[rsi_col]:.1f})")
        elif latest[rsi_col] > 70:
            sell_score += 1
            sell_reasons.append(f"RSI overbought ({latest[rsi_col]:.1f})")
        
        # Price significantly above mean
        if latest['Distance_From_Mean'] > 5:  # More than 5% above mean
            sell_score += 1
            sell_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% above mean")
        
        # Price rejecting from upper BB
        if previous['Close'] > previous[upper_bb_col] and latest['Close'] < latest[upper_bb_col]:
            sell_score += 1
            sell_reasons.append("Rejecting from upper BB")
        
        if sell_score >= 3:
            confidence = min(sell_score / 5.0, 1.0)
            logger.info(f"SELL signal for {product_id}: {', '.join(sell_reasons)}")
            return TradingSignal('SELL', confidence=confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})
        
        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'rsi': latest[rsi_col],
                                   'distance_from_mean': latest['Distance_From_Mean']})
