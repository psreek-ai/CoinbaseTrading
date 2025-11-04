
import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class BreakoutStrategy(BaseStrategy):
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        self.lookback_period = config.get('lookback_period', 50)
        self.volume_confirmation = config.get('volume_confirmation', True)
        self.volume_threshold = config.get('volume_threshold', 3.0)
        self.atr_period = config.get('atr_period', 14)
        self.atr_multiplier = config.get('atr_multiplier', 1.5)
        self.adx_length = config.get('adx_length', 14)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.volume_ma_short_length = config.get('volume_ma_short_length', 3)
        self.adx_consolidation_threshold = config.get('adx_consolidation_threshold', 20)
        self.adx_trending_threshold = config.get('adx_trending_threshold', 25)
        self.bb_squeeze_threshold = config.get('bb_squeeze_threshold', 4.0)
        self.volume_dry_up_threshold = config.get('volume_dry_up_threshold', 0.8)
        self.atr_expansion_multiplier = config.get('atr_expansion_multiplier', 1.5)
        self.close_strength_threshold = config.get('close_strength_threshold', 0.75)

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            df.ta.atr(length=self.atr_period, append=True)
            
            df.ta.adx(length=self.adx_length, append=True)
            
            df.ta.bbands(length=self.bb_period, std=self.bb_std, append=True)
            
            df['Volume_MA'] = df['Volume'].rolling(window=self.bb_period).mean()
            df['Volume_MA_Short'] = df['Volume'].rolling(window=self.volume_ma_short_length).mean()
            
            df['Rolling_High'] = df['High'].rolling(window=self.lookback_period).max()
            df['Rolling_Low'] = df['Low'].rolling(window=self.lookback_period).min()
            
            df['Prev_Rolling_High'] = df['Rolling_High'].shift(1)
            df['Prev_Rolling_Low'] = df['Rolling_Low'].shift(1)
            
            df['Range_Size'] = df['Rolling_High'] - df['Rolling_Low']
            df['Range_Pct'] = (df['Range_Size'] / df['Close']) * 100
            
            bb_upper = f'BBU_{self.bb_period}_{self.bb_std}'
            bb_lower = f'BBL_{self.bb_period}_{self.bb_std}'
            if bb_upper in df.columns and bb_lower in df.columns:
                df['BB_Width'] = ((df[bb_upper] - df[bb_lower]) / df['Close']) * 100
            
            df.dropna(inplace=True)
            
        except Exception as e:
            logger.error(f"Error adding indicators in BreakoutStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        if not self.validate_data(df, min_periods=max(self.lookback_period, self.atr_period)):
            return TradingSignal('HOLD', confidence=0.0)
        
        df = self.add_indicators(df)
        
        if len(df) < 10:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        atr_col = f'ATRr_{self.atr_period}'
        adx_col = f'ADX_{self.adx_length}'
        
        if atr_col not in df.columns:
            return TradingSignal('HOLD', confidence=0.0)
        
        in_consolidation = False
        if adx_col in df.columns:
            in_consolidation = latest[adx_col] < self.adx_consolidation_threshold
            if latest[adx_col] > self.adx_trending_threshold:
                logger.debug(f"{product_id}: ADX too high ({latest[adx_col]:.1f}), already trending")
                return TradingSignal('HOLD', confidence=0.0)
        
        bb_squeeze = False
        if 'BB_Width' in df.columns:
            bb_squeeze = latest['BB_Width'] < self.bb_squeeze_threshold
        
        volume_drying_up = False
        if 'Volume_MA_Short' in df.columns:
            volume_drying_up = latest['Volume_MA_Short'] < latest['Volume_MA'] * self.volume_dry_up_threshold
        
        volume_high = True
        if self.volume_confirmation:
            volume_high = latest['Volume'] > latest['Volume_MA'] * self.volume_threshold
        
        atr_expanding = False
        if len(df) > 5:
            recent_atr_avg = df[atr_col].iloc[-5:-1].mean()
            atr_expanding = latest[atr_col] > recent_atr_avg * self.atr_expansion_multiplier
        
        buy_score = 0
        buy_reasons = []
        
        upward_breakout = (latest['Close'] > latest['Prev_Rolling_High'] and
                          previous['Close'] <= previous['Prev_Rolling_High'])
        
        if upward_breakout:
            buy_score += 3
            buy_reasons.append(f"Upward breakout above {latest['Prev_Rolling_High']:.2f}")
        
        if in_consolidation:
            buy_score += 2
            buy_reasons.append(f"Breaking from consolidation (ADX: {latest[adx_col]:.1f})")
        
        if bb_squeeze:
            buy_score += 1
            buy_reasons.append(f"BB squeeze detected (width: {latest['BB_Width']:.2f}%)")
        
        if volume_drying_up and volume_high:
            buy_score += 2
            buy_reasons.append("Volume dry-up + expansion")
        elif volume_high:
            buy_score += 1
            buy_reasons.append(f"High volume ({latest['Volume']:.0f})")
        
        candle_range = latest['High'] - latest['Low']
        if candle_range > 0:
            close_strength = (latest['Close'] - latest['Low']) / candle_range
            if close_strength > self.close_strength_threshold:
                buy_score += 1
                buy_reasons.append(f"Strong close ({close_strength:.1%} of candle)")
        
        if atr_expanding:
            buy_score += 1
            buy_reasons.append("ATR expanding (volatility increasing)")

        buy_confidence = min(buy_score / 9.0, 1.0)

        sell_score = 0
        sell_reasons = []
        
        downward_breakout = (latest['Close'] < latest['Prev_Rolling_Low'] and
                            previous['Close'] >= previous['Prev_Rolling_Low'])
        
        if downward_breakout:
            sell_score += 3
            sell_reasons.append(f"Downward breakout below {latest['Prev_Rolling_Low']:.2f}")
        
        if candle_range > 0:
            close_weakness = 1 - ((latest['Close'] - latest['Low']) / candle_range)
            if close_weakness > self.close_strength_threshold:
                sell_score += 1
                sell_reasons.append("Weak close near low")
        
        failed_breakout = (latest['High'] > latest['Prev_Rolling_High'] and
                          latest['Close'] < latest['Prev_Rolling_High'])
        if failed_breakout:
            sell_score += 2
            sell_reasons.append("Failed upward breakout")
        
        sell_confidence = min(sell_score / 5.0, 1.0)

        if buy_confidence > sell_confidence and buy_confidence > 0:
            logger.debug(f"Potential BUY signal for {product_id}: score={buy_score}, confidence={buy_confidence:.2f}")
            return TradingSignal('BUY', confidence=buy_confidence,
                               metadata={'reasons': buy_reasons, 'score': buy_score})
        
        if sell_confidence > buy_confidence and sell_confidence > 0:
            logger.debug(f"Potential SELL signal for {product_id}: score={sell_score}, confidence={sell_confidence:.2f}")
            return TradingSignal('SELL', confidence=sell_confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})

        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'in_consolidation': in_consolidation,
                                   'bb_squeeze': bb_squeeze,
                                   'range_pct': latest['Range_Pct']})
