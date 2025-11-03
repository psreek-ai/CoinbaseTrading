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
            
            # Stochastic Oscillator - CRITICAL for timing
            df.ta.stoch(length=14, append=True)
            
            # Simple Moving Average
            df['SMA'] = df['Close'].rolling(window=self.mean_lookback).mean()
            
            # EMA 200 for long-term trend filter
            df['EMA_200'] = df.ta.ema(length=200)
            
            # Calculate distance from mean (as percentage)
            df['Distance_From_Mean'] = ((df['Close'] - df['SMA']) / df['SMA']) * 100
            
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Error adding indicators in MeanReversionStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Analyze data and generate mean reversion signal with improved filters."""
        
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
        stoch_k_col = 'STOCHk_14_3_3'  # Stochastic %K
        stoch_d_col = 'STOCHd_14_3_3'  # Stochastic %D
        
        if not all(col in df.columns for col in [upper_bb_col, lower_bb_col, rsi_col]):
            return TradingSignal('HOLD', confidence=0.0)
        
        # CRITICAL FILTER: Only buy reversions in long-term uptrend
        in_uptrend = True
        if 'EMA_200' in df.columns:
            in_uptrend = latest['Close'] > latest['EMA_200']
        
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
        
        # Stochastic oversold and crossing up
        if stoch_k_col in df.columns and stoch_d_col in df.columns:
            stoch_oversold = latest[stoch_k_col] < 20
            stoch_crossing_up = latest[stoch_k_col] > latest[stoch_d_col] and previous[stoch_k_col] <= previous[stoch_d_col]
            
            if stoch_oversold and stoch_crossing_up:
                buy_score += 2
                buy_reasons.append(f"Stochastic oversold + bullish cross ({latest[stoch_k_col]:.1f})")
            elif stoch_oversold:
                buy_score += 1
                buy_reasons.append("Stochastic oversold")
        
        # Price significantly below mean
        if latest['Distance_From_Mean'] < -5:  # More than 5% below mean
            buy_score += 1
            buy_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% below mean")
        
        # Price bouncing from lower BB
        if previous['Close'] < previous[lower_bb_col] and latest['Close'] > latest[lower_bb_col]:
            buy_score += 1
            buy_reasons.append("Bouncing from lower BB")
        
        # CRITICAL: Only buy if in long-term uptrend
        if not in_uptrend:
            buy_score = max(0, buy_score - 3)  # Heavily penalize counter-trend
            buy_reasons.append("⚠️ Below EMA 200 (downtrend)")
        else:
            buy_reasons.append("✓ Above EMA 200 (uptrend)")
        
        # --- NEW LOGIC: Calculate confidence and let main loop filter ---
        
        # Calculate buy confidence (max score is 7)
        buy_confidence = min(buy_score / 7.0, 1.0)

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
        
        # Stochastic overbought and crossing down
        if stoch_k_col in df.columns and stoch_d_col in df.columns:
            stoch_overbought = latest[stoch_k_col] > 80
            stoch_crossing_down = latest[stoch_k_col] < latest[stoch_d_col] and previous[stoch_k_col] >= previous[stoch_d_col]
            
            if stoch_overbought and stoch_crossing_down:
                sell_score += 2
                sell_reasons.append(f"Stochastic overbought + bearish cross ({latest[stoch_k_col]:.1f})")
            elif stoch_overbought:
                sell_score += 1
                sell_reasons.append("Stochastic overbought")
        
        # Price significantly above mean
        if latest['Distance_From_Mean'] > 5:  # More than 5% above mean
            sell_score += 1
            sell_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% above mean")
        
        # Price rejecting from upper BB
        if previous['Close'] > previous[upper_bb_col] and latest['Close'] < latest[upper_bb_col]:
            sell_score += 1
            sell_reasons.append("Rejecting from upper BB")
        
        # Calculate sell confidence (max score is 6)
        sell_confidence = min(sell_score / 6.0, 1.0)
        
        # Return the strongest signal, even if low confidence
        if buy_confidence > sell_confidence and buy_confidence > 0:
            logger.debug(f"Potential BUY signal for {product_id}: score={buy_score}, confidence={buy_confidence:.2f}")
            return TradingSignal('BUY', confidence=buy_confidence,
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        if sell_confidence > buy_confidence and sell_confidence > 0:
            logger.debug(f"Potential SELL signal for {product_id}: score={sell_score}, confidence={sell_confidence:.2f}")
            return TradingSignal('SELL', confidence=sell_confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})

        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'rsi': latest[rsi_col],
                                   'distance_from_mean': latest['Distance_From_Mean']})
