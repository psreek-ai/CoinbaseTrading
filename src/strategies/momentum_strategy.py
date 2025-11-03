"""
Momentum-based trading strategy.
Uses MACD, RSI, Bollinger Bands, and volume confirmation.
"""

import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    Momentum strategy that identifies trending markets.
    
    BUY signals when:
    - Price breaks above upper Bollinger Band
    - MACD crosses above signal line
    - RSI between 50-70 (strong but not overbought)
    - Volume is above average
    
    SELL signals when:
    - Price drops below middle Bollinger Band
    - MACD crosses below signal line
    - RSI above 75 (overbought)
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # Extract parameters from config
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.macd_fast = config.get('macd_fast', 12)
        self.macd_slow = config.get('macd_slow', 26)
        self.macd_signal = config.get('macd_signal', 9)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.volume_threshold = config.get('volume_threshold', 1.5)
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum indicators to DataFrame."""
        # Need at least 50 periods for reliable indicators
        min_required = max(self.bb_period, self.macd_slow) + 10
        if len(df) < min_required:
            logger.debug(f"Insufficient data for indicators: {len(df)} < {min_required} periods")
            return df
        
        try:
            # Bollinger Bands
            try:
                bbands = df.ta.bbands(length=self.bb_period, std=self.bb_std)
                if bbands is not None and not bbands.empty:
                    df = pd.concat([df, bbands], axis=1)
            except Exception as e:
                logger.debug(f"Bollinger Bands calculation failed: {e}")
            
            # MACD
            try:
                macd = df.ta.macd(fast=self.macd_fast, slow=self.macd_slow, 
                                 signal=self.macd_signal)
                if macd is not None and not macd.empty:
                    df = pd.concat([df, macd], axis=1)
            except Exception as e:
                logger.debug(f"MACD calculation failed: {e}")
            
            # RSI
            try:
                rsi = df.ta.rsi(length=self.rsi_period)
                if rsi is not None:
                    df[f'RSI_{self.rsi_period}'] = rsi
            except Exception as e:
                logger.debug(f"RSI calculation failed: {e}")
            
            # Volume moving average
            try:
                df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
            except Exception as e:
                logger.debug(f"Volume MA calculation failed: {e}")
            
            # Remove NaN values only if we have enough data
            initial_len = len(df)
            df.dropna(inplace=True)
            
            if len(df) < initial_len * 0.5:  # Lost more than half the data
                logger.debug(f"Significant data loss after indicator calculation: {initial_len} -> {len(df)} rows")
            
        except Exception as e:
            logger.error(f"Error adding indicators in MomentumStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Analyze data and generate momentum signal."""
        
        # Validate data
        if not self.validate_data(df):
            return TradingSignal('HOLD', confidence=0.0)
        
        # Add indicators
        df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        # Get latest and previous candles
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Column names (pandas_ta format)
        upper_bb_col = f'BBU_{self.bb_period}_{self.bb_std}'
        middle_bb_col = f'BBM_{self.bb_period}_{self.bb_std}'
        lower_bb_col = f'BBL_{self.bb_period}_{self.bb_std}'
        macd_col = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        macd_signal_col = f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        rsi_col = f'RSI_{self.rsi_period}'
        
        # Check for required columns
        required_cols = [upper_bb_col, middle_bb_col, lower_bb_col, 
                        macd_col, macd_signal_col, rsi_col]
        if not all(col in df.columns for col in required_cols):
            logger.debug(f"Missing required indicators for {product_id} (insufficient data)")
            return TradingSignal('HOLD', confidence=0.0)
        
        # Detect MACD crossovers
        macd_crossed_up = (latest[macd_col] > latest[macd_signal_col] and
                          previous[macd_col] <= previous[macd_signal_col])
        
        macd_crossed_down = (latest[macd_col] < latest[macd_signal_col] and
                            previous[macd_col] >= previous[macd_signal_col])
        
        # Volume confirmation
        volume_high = latest['Volume'] > latest['Volume_MA'] * self.volume_threshold
        
        # Check BUY conditions
        price_above_upper_bb = latest['Close'] > latest[upper_bb_col]
        rsi_in_buy_zone = 50 < latest[rsi_col] < self.rsi_overbought
        
        buy_score = 0
        buy_reasons = []
        
        if price_above_upper_bb:
            buy_score += 1
            buy_reasons.append("Price above upper BB")
        
        if macd_crossed_up:
            buy_score += 2  # MACD crossover is stronger signal
            buy_reasons.append("MACD bullish crossover")
        
        if rsi_in_buy_zone:
            buy_score += 1
            buy_reasons.append(f"RSI in momentum zone ({latest[rsi_col]:.1f})")
        
        if volume_high:
            buy_score += 1
            buy_reasons.append("High volume")
        
        # BUY signal (need at least 3 points)
        if buy_score >= 3:
            confidence = min(buy_score / 5.0, 1.0)
            logger.info(f"BUY signal for {product_id}: {', '.join(buy_reasons)}")
            return TradingSignal('BUY', confidence=confidence, 
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        # Check SELL conditions
        price_below_middle_bb = latest['Close'] < latest[middle_bb_col]
        rsi_overbought = latest[rsi_col] > 75
        
        sell_score = 0
        sell_reasons = []
        
        if price_below_middle_bb:
            sell_score += 2
            sell_reasons.append("Price below middle BB")
        
        if macd_crossed_down:
            sell_score += 2
            sell_reasons.append("MACD bearish crossover")
        
        if rsi_overbought:
            sell_score += 1
            sell_reasons.append(f"RSI overbought ({latest[rsi_col]:.1f})")
        
        # SELL signal (need at least 2 points)
        if sell_score >= 2:
            confidence = min(sell_score / 5.0, 1.0)
            logger.info(f"SELL signal for {product_id}: {', '.join(sell_reasons)}")
            return TradingSignal('SELL', confidence=confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})
        
        # HOLD
        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'latest_rsi': latest[rsi_col],
                                   'latest_close': latest['Close']})
