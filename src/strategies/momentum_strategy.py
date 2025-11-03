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
            # Bollinger Bands (pandas_ta appends std parameter TWICE to column names)
            bbands = df.ta.bbands(length=self.bb_period, std=self.bb_std)
            if bbands is not None and not bbands.empty:
                df = pd.concat([df, bbands], axis=1)
            
            # MACD
            macd = df.ta.macd(fast=self.macd_fast, slow=self.macd_slow, 
                             signal=self.macd_signal)
            if macd is not None and not macd.empty:
                df = pd.concat([df, macd], axis=1)
            
            # RSI
            rsi = df.ta.rsi(length=self.rsi_period)
            if rsi is not None:
                df[f'RSI_{self.rsi_period}'] = rsi
            
            # ADX - Trend strength indicator
            adx = df.ta.adx(length=14)
            if adx is not None and not adx.empty:
                df = pd.concat([df, adx], axis=1)
            
            # EMA - Trend direction filters
            df['EMA_20'] = df.ta.ema(length=20)
            df['EMA_50'] = df.ta.ema(length=50)
            
            # Volume moving average
            df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
            
            # Only drop rows where critical indicators are NaN (not all columns)
            # This preserves data where some non-critical indicators might be NaN
            critical_indicators = [
                f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}',
                f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}',
                f'RSI_{self.rsi_period}',
                f'BBL_{self.bb_period}_{self.bb_std}',
                f'BBM_{self.bb_period}_{self.bb_std}',
                f'BBU_{self.bb_period}_{self.bb_std}'
            ]
            # Only drop if ANY critical indicator is missing
            existing_critical = [col for col in critical_indicators if col in df.columns]
            if existing_critical:
                initial_len = len(df)
                df.dropna(subset=existing_critical, inplace=True)
                
                if len(df) < initial_len * 0.5:  # Lost more than half the data
                    logger.debug(f"Significant data loss after indicator calculation: {initial_len} -> {len(df)} rows")
            
        except Exception as e:
            logger.error(f"Error adding indicators in MomentumStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Analyze data and generate momentum signal with improved logic."""
        
        # Validate data
        if not self.validate_data(df):
            return TradingSignal('HOLD', confidence=0.0)
        
        # Add indicators if not already present
        macd_check = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        if macd_check not in df.columns:
            df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        # Get latest and previous candles
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Column names (pandas_ta format - NOTE: std appears TWICE in BB column names)
        upper_bb_col = f'BBU_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        middle_bb_col = f'BBM_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        lower_bb_col = f'BBL_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        macd_col = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        macd_signal_col = f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        rsi_col = f'RSI_{self.rsi_period}'
        adx_col = 'ADX_14'
        
        # Check for required columns
        required_cols = [upper_bb_col, middle_bb_col, lower_bb_col, 
                        macd_col, macd_signal_col, rsi_col]
        if not all(col in df.columns for col in required_cols):
            return TradingSignal('HOLD', confidence=0.0)
        
        # Filter: Only trade in strong trends (ADX > 15)
        if adx_col in df.columns and latest[adx_col] < 15:
            return TradingSignal('HOLD', confidence=0.0)
        
        # CRITICAL FILTER: Confirm trend direction with EMAs
        bullish_trend = True
        bearish_trend = True
        if 'EMA_20' in df.columns and 'EMA_50' in df.columns:
            bullish_trend = bool(latest['EMA_20'] > latest['EMA_50'])
            bearish_trend = bool(latest['EMA_20'] < latest['EMA_50'])
        
        # Detect MACD crossovers
        macd_crossed_up = bool(latest[macd_col] > latest[macd_signal_col]) and bool(previous[macd_col] <= previous[macd_signal_col])
        
        macd_crossed_down = bool(latest[macd_col] < latest[macd_signal_col]) and bool(previous[macd_col] >= previous[macd_signal_col])
        
        # Volume confirmation with HIGHER threshold (2.5x instead of 1.5x)
        volume_high = bool(latest['Volume'] > latest['Volume_MA'] * 2.5)
        
        # Check BUY conditions - IMPROVED LOGIC
        buy_score = 0
        buy_reasons = []
        
        # CRITICAL FIX: Buy pullback to middle BB, NOT extension above upper BB
        price_near_middle_bb = bool(abs(latest['Close'] - latest[middle_bb_col]) / latest['Close'] < 0.015)  # Within 1.5%
        if price_near_middle_bb and bullish_trend:
            buy_score += 2
            buy_reasons.append("Pullback to middle BB in uptrend")
        
        if macd_crossed_up:
            buy_score += 2  # MACD crossover is stronger signal
            buy_reasons.append("MACD bullish crossover")
        
        # RSI confirmation (momentum building, not overbought)
        rsi_in_momentum_zone = bool(50 < latest[rsi_col] < 75)
        if rsi_in_momentum_zone:
            buy_score += 1
            buy_reasons.append(f"RSI confirming momentum ({latest[rsi_col]:.1f})")
        
        # IMPROVED: Higher volume threshold
        if volume_high:
            buy_score += 1
            buy_reasons.append("Strong volume confirmation (>2.5x average)")
        
        # EMA trend alignment
        if bullish_trend:
            buy_score += 1
            buy_reasons.append("EMA bullish alignment")
        
        # --- NEW LOGIC: Calculate confidence and let main loop filter ---
        
        # Calculate buy confidence (max score is 6)
        buy_confidence = min(buy_score / 6.0, 1.0)
        
        # Check SELL conditions - IMPROVED
        sell_score = 0
        sell_reasons = []
        
        if macd_crossed_down:
            sell_score += 2
            sell_reasons.append("MACD bearish crossover")
        
        # ADX falling (trend weakening)
        if adx_col in df.columns and len(df) > 3:
            adx_falling = bool(latest[adx_col] < df.iloc[-3][adx_col])
            if adx_falling:
                sell_score += 1
                sell_reasons.append("ADX falling, trend weakening")
        
        # RSI momentum lost
        if bool(latest[rsi_col] < 40):
            sell_score += 1
            sell_reasons.append(f"RSI momentum lost ({latest[rsi_col]:.1f})")
        
        # Price below middle BB
        price_below_middle = bool(latest['Close'] < latest[middle_bb_col])
        if price_below_middle:
            sell_score += 1
            sell_reasons.append("Price below middle BB")
        
        # Calculate sell confidence (max score is 5)
        sell_confidence = min(sell_score / 5.0, 1.0)
        
        # Return the strongest signal
        if buy_confidence > sell_confidence and buy_confidence > 0:
            logger.debug(f"BUY signal for {product_id}: score={buy_score}, confidence={buy_confidence:.2f}")
            return TradingSignal('BUY', confidence=buy_confidence, 
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        if sell_confidence > buy_confidence and sell_confidence > 0:
            logger.debug(f"SELL signal for {product_id}: score={sell_score}, confidence={sell_confidence:.2f}")
            return TradingSignal('SELL', confidence=sell_confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})

        # HOLD
        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'latest_rsi': latest[rsi_col],
                                   'latest_close': latest['Close'],
                                   'adx': latest[adx_col] if adx_col in df.columns else None})

