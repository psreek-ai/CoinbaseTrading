
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
            # Add Bollinger Bands with explicit column mapping
            bbands = df.ta.bbands(length=self.bb_period, std=self.bb_std)
            if bbands is not None and not bbands.empty:
                df['BB_UPPER'] = bbands[f'BBU_{self.bb_period}_{self.bb_std}']
                df['BB_MIDDLE'] = bbands[f'BBM_{self.bb_period}_{self.bb_std}']
                df['BB_LOWER'] = bbands[f'BBL_{self.bb_period}_{self.bb_std}']
            
            # Add MACD with explicit column mapping
            macd = df.ta.macd(fast=self.macd_fast, slow=self.macd_slow, 
                             signal=self.macd_signal)
            if macd is not None and not macd.empty:
                df['MACD'] = macd[f'MACD_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
                df['MACD_SIGNAL'] = macd[f'MACDs_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
                df['MACD_HIST'] = macd[f'MACDh_{self.macd_fast}_{self.macd_slow}_{self.macd_signal}']
            
            # Add RSI with explicit column mapping
            rsi = df.ta.rsi(length=self.rsi_period)
            if rsi is not None:
                df['RSI'] = rsi
            
            # Add ADX with explicit column mapping
            adx = df.ta.adx(length=self.adx_length)
            if adx is not None and not adx.empty:
                df['ADX'] = adx[f'ADX_{self.adx_length}']
                if f'DMP_{self.adx_length}' in adx.columns:
                    df['DI_PLUS'] = adx[f'DMP_{self.adx_length}']
                if f'DMN_{self.adx_length}' in adx.columns:
                    df['DI_MINUS'] = adx[f'DMN_{self.adx_length}']
            
            # Add EMAs
            df['EMA_FAST'] = df.ta.ema(length=self.ema_fast_length)
            df['EMA_SLOW'] = df.ta.ema(length=self.ema_slow_length)
            
            # Add Volume MA
            df['Volume_MA'] = df['Volume'].rolling(window=self.volume_ma_length).mean()
            
        except Exception as e:
            logger.error(f"Error adding indicators in MomentumStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        if not self.validate_data(df):
            return TradingSignal('HOLD', confidence=0.0)
        
        # Check if indicators are present, if not add them
        if 'MACD' not in df.columns:
            df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Check for NaN values in required indicators
        required_cols = ['BB_UPPER', 'BB_MIDDLE', 'BB_LOWER', 'MACD', 'MACD_SIGNAL', 'RSI']
        if latest[required_cols].isnull().any():
            logger.warning(f"Indicators for {product_id} have NaN on latest candle. Skipping.")
            return TradingSignal('HOLD', confidence=0.0)
        
        # Check ADX if available
        if 'ADX' in df.columns and not pd.isna(latest['ADX']) and latest['ADX'] < self.adx_threshold:
            return TradingSignal('HOLD', confidence=0.0)
        
        # Trend analysis using EMAs
        bullish_trend = True
        bearish_trend = True
        if 'EMA_FAST' in df.columns and 'EMA_SLOW' in df.columns:
            if not pd.isna(latest['EMA_FAST']) and not pd.isna(latest['EMA_SLOW']):
                bullish_trend = bool(latest['EMA_FAST'] > latest['EMA_SLOW'])
                bearish_trend = bool(latest['EMA_FAST'] < latest['EMA_SLOW'])
        
        # MACD crossovers
        macd_crossed_up = bool(latest['MACD'] > latest['MACD_SIGNAL']) and bool(previous['MACD'] <= previous['MACD_SIGNAL'])
        macd_crossed_down = bool(latest['MACD'] < latest['MACD_SIGNAL']) and bool(previous['MACD'] >= previous['MACD_SIGNAL'])
        
        # Volume confirmation
        volume_high = False
        if 'Volume_MA' in df.columns and not pd.isna(latest['Volume_MA']):
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
        price_near_middle_bb = bool(abs(latest['Close'] - latest['BB_MIDDLE']) / latest['Close'] < self.price_proximity_threshold)
        if price_near_middle_bb and bullish_trend:
            buy_score += 20.0
            buy_reasons.append("Pullback to middle BB in uptrend")
        
        if bullish_trend:
            buy_score += 20.0
            buy_reasons.append("EMA bullish alignment")
        
        # MODERATE IMPORTANCE (15 points each) - Momentum confirmation
        rsi_in_momentum_zone = bool(self.rsi_momentum_buy_lower_bound < latest['RSI'] < self.rsi_momentum_buy_upper_bound)
        if rsi_in_momentum_zone:
            buy_score += 15.0
            buy_reasons.append(f"RSI confirming momentum ({latest['RSI']:.1f})")
        
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
        if bool(latest['RSI'] < self.rsi_momentum_sell_upper_bound):
            sell_score += 20.0
            sell_reasons.append(f"RSI momentum lost ({latest['RSI']:.1f})")
        
        price_below_middle = bool(latest['Close'] < latest['BB_MIDDLE'])
        if price_below_middle:
            sell_score += 20.0
            sell_reasons.append("Price below middle BB")
        
        # SUPPORTING FACTORS (20 points) - Weakening trend
        if 'ADX' in df.columns and not pd.isna(latest['ADX']) and len(df) > 3:
            if not pd.isna(df.iloc[-3]['ADX']):
                adx_falling = bool(latest['ADX'] < df.iloc[-3]['ADX'])
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
                           metadata={'latest_rsi': latest['RSI'],
                                   'latest_close': latest['Close'],
                                   'adx': latest['ADX'] if 'ADX' in df.columns and not pd.isna(latest['ADX']) else None,
                                   'buy_score': buy_score,
                                   'sell_score': sell_score})
