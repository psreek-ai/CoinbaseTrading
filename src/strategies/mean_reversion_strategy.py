
import pandas as pd
import pandas_ta as ta
from typing import Dict
import logging
from .base_strategy import BaseStrategy, TradingSignal

logger = logging.getLogger(__name__)


class MeanReversionStrategy(BaseStrategy):
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_extreme_oversold = config.get('rsi_extreme_oversold', 20)
        self.rsi_extreme_overbought = config.get('rsi_extreme_overbought', 80)
        self.mean_lookback = config.get('mean_lookback', 50)
        self.stoch_length = config.get('stoch_length', 14)
        self.ema_long_length = config.get('ema_long_length', 200)
        self.distance_from_mean_threshold = config.get('distance_from_mean_threshold', -5)
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            # Add Bollinger Bands with explicit column mapping
            bbands = df.ta.bbands(length=self.bb_period, std=self.bb_std)
            if bbands is not None and not bbands.empty:
                df['BB_UPPER'] = bbands[f'BBU_{self.bb_period}_{self.bb_std}']
                df['BB_MIDDLE'] = bbands[f'BBM_{self.bb_period}_{self.bb_std}']
                df['BB_LOWER'] = bbands[f'BBL_{self.bb_period}_{self.bb_std}']
            
            # Add RSI with explicit column mapping
            rsi = df.ta.rsi(length=self.rsi_period)
            if rsi is not None:
                df['RSI'] = rsi
            
            # Add Stochastic with explicit column mapping
            stoch = df.ta.stoch(length=self.stoch_length)
            if stoch is not None and not stoch.empty:
                df['STOCH_K'] = stoch[f'STOCHk_{self.stoch_length}_3_3']
                df['STOCH_D'] = stoch[f'STOCHd_{self.stoch_length}_3_3']
            
            df['SMA'] = df['Close'].rolling(window=self.mean_lookback).mean()
            
            df['EMA_LONG'] = df.ta.ema(length=self.ema_long_length)
            
            df['Distance_From_Mean'] = ((df['Close'] - df['SMA']) / df['SMA']) * 100
            
        except Exception as e:
            logger.error(f"Error adding indicators in MeanReversionStrategy: {e}")
        
        return df
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        if not self.validate_data(df, min_periods=self.mean_lookback):
            return TradingSignal('HOLD', confidence=0.0)
        
        df = self.add_indicators(df)
        
        if len(df) < 2:
            return TradingSignal('HOLD', confidence=0.0)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Check for NaN values in required indicators
        required_cols = ['BB_UPPER', 'BB_LOWER', 'RSI', 'SMA', 'Distance_From_Mean']
        if latest[required_cols].isnull().any():
            logger.warning(f"Indicators for {product_id} have NaN on latest candle. Skipping.")
            return TradingSignal('HOLD', confidence=0.0)
        
        in_uptrend = True
        if 'EMA_LONG' in df.columns and not pd.isna(latest['EMA_LONG']):
            in_uptrend = latest['Close'] > latest['EMA_LONG']
        
        buy_score = 0
        buy_reasons = []
        
        if latest['Close'] <= latest['BB_LOWER']:
            buy_score += 2
            buy_reasons.append(f"Price at/below lower BB ({latest['Close']:.2f} <= {latest['BB_LOWER']:.2f})")
        
        if latest['RSI'] < self.rsi_extreme_oversold:
            buy_score += 2
            buy_reasons.append(f"RSI extremely oversold ({latest['RSI']:.1f})")
        elif latest['RSI'] < 30:
            buy_score += 1
            buy_reasons.append(f"RSI oversold ({latest['RSI']:.1f})")
        
        if 'STOCH_K' in df.columns and 'STOCH_D' in df.columns:
            if not pd.isna(latest['STOCH_K']) and not pd.isna(latest['STOCH_D']):
                stoch_oversold = latest['STOCH_K'] < 20
                stoch_crossing_up = (latest['STOCH_K'] > latest['STOCH_D'] and 
                                    previous['STOCH_K'] <= previous['STOCH_D'])
                
                if stoch_oversold and stoch_crossing_up:
                    buy_score += 2
                    buy_reasons.append(f"Stochastic oversold + bullish cross ({latest['STOCH_K']:.1f})")
                elif stoch_oversold:
                    buy_score += 1
                    buy_reasons.append("Stochastic oversold")
        
        if latest['Distance_From_Mean'] < self.distance_from_mean_threshold:
            buy_score += 1
            buy_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% below mean")
        
        if previous['Close'] < previous['BB_LOWER'] and latest['Close'] > latest['BB_LOWER']:
            buy_score += 1
            buy_reasons.append("Bouncing from lower BB")
        
        if not in_uptrend:
            buy_score = max(0, buy_score - 3)
            buy_reasons.append("⚠️ Below EMA 200 (downtrend)")
        else:
            buy_reasons.append("✓ Above EMA 200 (uptrend)")
        
        buy_confidence = min(buy_score / 7.0, 1.0)

        sell_score = 0
        sell_reasons = []
        
        if latest['Close'] >= latest['BB_UPPER']:
            sell_score += 2
            sell_reasons.append(f"Price at/above upper BB ({latest['Close']:.2f} >= {latest['BB_UPPER']:.2f})")
        
        if latest['RSI'] > self.rsi_extreme_overbought:
            sell_score += 2
            sell_reasons.append(f"RSI extremely overbought ({latest['RSI']:.1f})")
        elif latest['RSI'] > 70:
            sell_score += 1
            sell_reasons.append(f"RSI overbought ({latest['RSI']:.1f})")
        
        if 'STOCH_K' in df.columns and 'STOCH_D' in df.columns:
            if not pd.isna(latest['STOCH_K']) and not pd.isna(latest['STOCH_D']):
                stoch_overbought = latest['STOCH_K'] > 80
                stoch_crossing_down = (latest['STOCH_K'] < latest['STOCH_D'] and 
                                      previous['STOCH_K'] >= previous['STOCH_D'])
                
                if stoch_overbought and stoch_crossing_down:
                    sell_score += 2
                    sell_reasons.append(f"Stochastic overbought + bearish cross ({latest['STOCH_K']:.1f})")
                elif stoch_overbought:
                    sell_score += 1
                    buy_reasons.append("Stochastic overbought")

        if latest['Distance_From_Mean'] > abs(self.distance_from_mean_threshold):
            sell_score += 1
            sell_reasons.append(f"Price {latest['Distance_From_Mean']:.1f}% above mean")

        if previous['Close'] > previous['BB_UPPER'] and latest['Close'] < latest['BB_UPPER']:
            sell_score += 1
            sell_reasons.append("Rejecting from upper BB")

        sell_confidence = min(sell_score / 6.0, 1.0)

        if buy_confidence > sell_confidence and buy_confidence > 0:
            logger.debug(f"Potential BUY signal for {product_id}: score={buy_score}, confidence={buy_confidence:.2f}")
            return TradingSignal('BUY', confidence=buy_confidence,
                               metadata={'reasons': buy_reasons, 'score': buy_score})

        if sell_confidence > buy_confidence and sell_confidence > 0:
            logger.debug(f"Potential SELL signal for {product_id}: score={sell_score}, confidence={sell_confidence:.2f}")
            return TradingSignal('SELL', confidence=sell_confidence,
                               metadata={'reasons': sell_reasons, 'score': sell_score})

        return TradingSignal('HOLD', confidence=0.5,
                           metadata={'rsi': latest['RSI'],
                                   'distance_from_mean': latest['Distance_From_Mean']})
