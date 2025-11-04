
import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    
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
        self.adx_length = config.get('adx_length', 14)
        self.ema_fast_length = config.get('ema_fast_length', 20)
        self.ema_slow_length = config.get('ema_slow_length', 50)
        self.volume_ma_length = config.get('volume_ma_length', 20)
        self.adx_threshold = config.get('adx_threshold', 15)
        self.volume_confirmation_multiplier = config.get('volume_confirmation_multiplier', 2.5)
        self.price_proximity_threshold = config.get('price_proximity_threshold', 0.015)
        self.rsi_momentum_buy_lower_bound = config.get('rsi_momentum_buy_lower_bound', 50)
        self.rsi_momentum_buy_upper_bound = config.get('rsi_momentum_buy_upper_bound', 75)
        self.rsi_momentum_sell_upper_bound = config.get('rsi_momentum_sell_upper_bound', 40)

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        min_required = max(self.bb_period, self.macd_slow) + 10
        if len(df) < min_required:
            logger.debug(f"Insufficient data for indicators: {len(df)} < {min_required} periods")
            return df
        
        try:
            bbands = df.ta.bbands(length=self.bb_period, std=self.bb_std)
            if bbands is not None and not bbands.empty:
                df = pd.concat([df, bbands], axis=1)
            
            macd = df.ta.macd(fast=self.macd_fast, slow=self.macd_slow, 
                             signal=self.macd_signal)
            if macd is not None and not macd.empty:
                df = pd.concat([df, macd], axis=1)
            
            rsi = df.ta.rsi(length=self.rsi_period)
            if rsi is not None:
                df[f'RSI_{self.rsi_period}'] = rsi
            
            adx = df.ta.adx(length=self.adx_length)
            if adx is not None and not adx.empty:
                df = pd.concat([df, adx], axis=1)
            
            df[f'EMA_{self.ema_fast_length}'] = df.ta.ema(length=self.ema_fast_length)
            df[f'EMA_{self.ema_slow_length}'] = df.ta.ema(length=self.ema_slow_length)
            
            df['Volume_MA'] = df['Volume'].rolling(window=self.volume_ma_length).mean()
            
            critical_indicators = [
                f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}',
                f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}',
                f'RSI_{self.rsi_period}',
                f'BBL_{self.bb_period}_{self.bb_std}',
                f'BBM_{self.bb_period}_{self.bb_std}',
                f'BBU_{self.bb_period}_{self.bb_std}'
            ]
            existing_critical = [col for col in critical_indicators if col in df.columns]
            if existing_critical:
                initial_len = len(df)
                df.dropna(subset=existing_critical, inplace=True)
                
                if len(df) < initial_len * 0.5:
                    logger.debug(f"Significant data loss after indicator calculation: {initial_len} -> {len(df)} rows")
            
        except Exception as e:
            logger.error(f"Error adding indicators in MomentumStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        if not self.validate_data(df):
            return TradingSignal('HOLD', confidence=0.0)
        
        macd_check = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        if macd_check not in df.columns:
            df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        upper_bb_col = f'BBU_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        middle_bb_col = f'BBM_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        lower_bb_col = f'BBL_{self.bb_period}_{self.bb_std}_{self.bb_std}'
        macd_col = f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        macd_signal_col = f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}'
        rsi_col = f'RSI_{self.rsi_period}'
        adx_col = f'ADX_{self.adx_length}'
        
        required_cols = [upper_bb_col, middle_bb_col, lower_bb_col, 
                        macd_col, macd_signal_col, rsi_col]
        if not all(col in df.columns for col in required_cols):
            return TradingSignal('HOLD', confidence=0.0)
        
        if adx_col in df.columns and latest[adx_col] < self.adx_threshold:
            return TradingSignal('HOLD', confidence=0.0)
        
        bullish_trend = True
        bearish_trend = True
        ema_fast_col = f'EMA_{self.ema_fast_length}'
        ema_slow_col = f'EMA_{self.ema_slow_length}'
        if ema_fast_col in df.columns and ema_slow_col in df.columns:
            bullish_trend = bool(latest[ema_fast_col] > latest[ema_slow_col])
            bearish_trend = bool(latest[ema_fast_col] < latest[ema_slow_col])
        
        macd_crossed_up = bool(latest[macd_col] > latest[macd_signal_col]) and bool(previous[macd_col] <= previous[macd_signal_col])
        
        macd_crossed_down = bool(latest[macd_col] < latest[macd_signal_col]) and bool(previous[macd_col] >= previous[macd_signal_col])
        
        volume_high = bool(latest['Volume'] > latest['Volume_MA'] * self.volume_confirmation_multiplier)
        
        # WEIGHTED SCORING SYSTEM for better confidence granularity
        # Max total: 100 points for perfect signal
        buy_score = 0.0
        buy_reasons = []
        
        # CRITICAL FACTORS (30 points each) - Strong momentum indicators
        if macd_crossed_up:
            buy_score += 30.0
            buy_reasons.append("MACD bullish crossover")
        
        # HIGH IMPORTANCE (20 points each) - Trend confirmation
        price_near_middle_bb = bool(abs(latest['Close'] - latest[middle_bb_col]) / latest['Close'] < self.price_proximity_threshold)
        if price_near_middle_bb and bullish_trend:
            buy_score += 20.0
            buy_reasons.append("Pullback to middle BB in uptrend")
        
        if bullish_trend:
            buy_score += 20.0
            buy_reasons.append("EMA bullish alignment")
        
        # MODERATE IMPORTANCE (15 points each) - Momentum confirmation
        rsi_in_momentum_zone = bool(self.rsi_momentum_buy_lower_bound < latest[rsi_col] < self.rsi_momentum_buy_upper_bound)
        if rsi_in_momentum_zone:
            buy_score += 15.0
            buy_reasons.append(f"RSI confirming momentum ({latest[rsi_col]:.1f})")
        
        # SUPPORTING FACTORS (15 points) - Volume validation
        if volume_high:
            buy_score += 15.0
            buy_reasons.append(f"Strong volume confirmation (>{self.volume_confirmation_multiplier}x average)")
        
        buy_confidence = min(buy_score / 100.0, 1.0)
        
        # SELL SCORING (weighted)
        sell_score = 0.0
        sell_reasons = []
        
        # CRITICAL FACTORS (35 points) - Strong reversal signal
        if macd_crossed_down:
            sell_score += 35.0
            sell_reasons.append("MACD bearish crossover")
        
        # HIGH IMPORTANCE (25 points) - Trend breakdown
        if bearish_trend:
            sell_score += 25.0
            sell_reasons.append("EMA bearish alignment")
        
        # MODERATE IMPORTANCE (20 points each) - Momentum loss
        if bool(latest[rsi_col] < self.rsi_momentum_sell_upper_bound):
            sell_score += 20.0
            sell_reasons.append(f"RSI momentum lost ({latest[rsi_col]:.1f})")
        
        price_below_middle = bool(latest['Close'] < latest[middle_bb_col])
        if price_below_middle:
            sell_score += 20.0
            sell_reasons.append("Price below middle BB")
        
        # SUPPORTING FACTORS (20 points) - Weakening trend
        if adx_col in df.columns and len(df) > 3:
            adx_falling = bool(latest[adx_col] < df.iloc[-3][adx_col])
            if adx_falling:
                sell_score += 20.0
                sell_reasons.append("ADX falling, trend weakening")
        
        sell_confidence = min(sell_score / 100.0, 1.0)
        
        # Determine signal based on confidence comparison
        if buy_confidence > sell_confidence and buy_confidence > 0:
            logger.debug(f"BUY signal for {product_id}: score={buy_score:.1f}/100, confidence={buy_confidence:.1%}")
            return TradingSignal('BUY', confidence=buy_confidence, 
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        if sell_confidence > buy_confidence and sell_confidence > 0:
            logger.debug(f"SELL signal for {product_id}: score={sell_score:.1f}/100, confidence={sell_confidence:.1%}")
            return TradingSignal('SELL', confidence=sell_confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})

        # HOLD signal - confidence reflects proximity to action threshold
        # Higher scores indicate closer to triggering a signal
        hold_confidence = max(buy_confidence, sell_confidence)
        return TradingSignal('HOLD', confidence=hold_confidence,
                           metadata={'latest_rsi': latest[rsi_col],
                                   'latest_close': latest['Close'],
                                   'adx': latest[adx_col] if adx_col in df.columns else None,
                                   'buy_score': buy_score,
                                   'sell_score': sell_score})
