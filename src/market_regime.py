"""
Market Regime Detector
Analyzes market conditions to determine if the market is trending or ranging.
This helps select the optimal trading strategy for current conditions.
"""

import pandas as pd
import pandas_ta as ta
import logging
from typing import Dict, Optional, Literal
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Enumeration of market regimes"""
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class MarketRegimeDetector:
    """
    Detects market regime using ADX and other technical indicators.
    
    Key Concepts:
    - TRENDING: Strong directional movement (ADX > 25). Best for Momentum strategies.
    - RANGING: Market moving sideways (ADX < 20). Best for Mean Reversion strategies.
    - VOLATILE: High volatility without clear trend. Trade with caution or stay flat.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the regime detector.
        
        Args:
            config: Configuration dictionary with regime detection parameters
        """
        # ADX thresholds
        self.adx_trending_threshold = config.get('adx_trending_threshold', 25)
        self.adx_ranging_threshold = config.get('adx_ranging_threshold', 20)
        self.adx_period = config.get('adx_period', 14)
        
        # Additional indicators for regime confirmation
        self.volatility_lookback = config.get('volatility_lookback', 20)
        self.volatility_threshold = config.get('volatility_threshold', 2.0)
        
        # EMA for trend direction
        self.ema_fast = config.get('regime_ema_fast', 20)
        self.ema_slow = config.get('regime_ema_slow', 50)
        
        # Reference product for regime detection (typically BTC-USD)
        self.reference_product = config.get('regime_reference_product', 'BTC-USD')
        
        # Timeframe for regime analysis (use higher timeframe for stability)
        self.regime_timeframe = config.get('regime_timeframe', 'ONE_HOUR')
        
        # Cache the last regime to avoid excessive recalculation
        self.last_regime = MarketRegime.UNKNOWN
        self.last_regime_time = None
        self.regime_cache_duration = config.get('regime_cache_duration_seconds', 300)  # 5 minutes
        
        logger.info(f"Market Regime Detector initialized:")
        logger.info(f"  Reference: {self.reference_product} @ {self.regime_timeframe}")
        logger.info(f"  ADX Trending: >{self.adx_trending_threshold}")
        logger.info(f"  ADX Ranging: <{self.adx_ranging_threshold}")
    
    def detect_regime(self, df: pd.DataFrame, use_cache: bool = True) -> Dict:
        """
        Detect the current market regime.
        
        Args:
            df: DataFrame with OHLCV data (must have columns: open, high, low, close, volume)
            use_cache: Whether to use cached regime if still valid
            
        Returns:
            Dictionary with regime info:
            {
                'regime': MarketRegime enum,
                'adx': float,
                'confidence': float (0-1),
                'trend_direction': str ('up', 'down', 'neutral'),
                'volatility': float,
                'metadata': dict with additional details
            }
        """
        # Check cache
        if use_cache and self._is_cache_valid():
            logger.debug(f"Using cached regime: {self.last_regime.value}")
            return self._build_regime_response(self.last_regime, None)
        
        # Validate data
        if df is None or df.empty:
            logger.warning("Empty dataframe provided for regime detection")
            return self._build_regime_response(MarketRegime.UNKNOWN, None)
        
        min_required = max(self.adx_period, self.ema_slow, self.volatility_lookback) + 10
        if len(df) < min_required:
            logger.warning(f"Insufficient data for regime detection: {len(df)} < {min_required}")
            return self._build_regime_response(MarketRegime.UNKNOWN, None)
        
        try:
            # Calculate indicators
            df = self._add_indicators(df.copy())
            
            # Get latest values
            latest = df.iloc[-1]
            adx = latest.get('ADX')
            
            if pd.isna(adx):
                logger.warning("ADX calculation failed")
                return self._build_regime_response(MarketRegime.UNKNOWN, None)
            
            # Determine regime based on ADX
            if adx > self.adx_trending_threshold:
                regime = MarketRegime.TRENDING
            elif adx < self.adx_ranging_threshold:
                regime = MarketRegime.RANGING
            else:
                # In between - check volatility and other factors
                regime = self._determine_intermediate_regime(df, latest)
            
            # Get additional context
            trend_direction = self._get_trend_direction(latest)
            volatility = latest.get('ATR', 0) / latest.get('Close', 1) * 100 if latest.get('ATR') else 0
            
            # Calculate confidence
            confidence = self._calculate_confidence(adx, regime)
            
            # Update cache
            self.last_regime = regime
            self.last_regime_time = datetime.now()
            
            result = {
                'regime': regime,
                'adx': float(adx),
                'confidence': confidence,
                'trend_direction': trend_direction,
                'volatility': volatility,
                'metadata': {
                    'ema_fast': latest.get('EMA_FAST'),
                    'ema_slow': latest.get('EMA_SLOW'),
                    'atr': latest.get('ATR'),
                    'di_plus': latest.get('DMP'),
                    'di_minus': latest.get('DMN'),
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            logger.info(f"Market Regime: {regime.value.upper()} | ADX: {adx:.1f} | "
                       f"Direction: {trend_direction} | Confidence: {confidence:.1%}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}", exc_info=True)
            return self._build_regime_response(MarketRegime.UNKNOWN, None)
    
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators for regime detection"""
        try:
            # ADX (Average Directional Index) - measures trend strength
            adx = df.ta.adx(length=self.adx_period)
            if adx is not None and not adx.empty:
                adx_cols = [c for c in adx.columns if c.startswith('ADX')]
                dmp_cols = [c for c in adx.columns if c.startswith('DMP')]
                dmn_cols = [c for c in adx.columns if c.startswith('DMN')]
                
                if adx_cols:
                    df['ADX'] = adx[adx_cols[0]]
                if dmp_cols:
                    df['DMP'] = adx[dmp_cols[0]]
                if dmn_cols:
                    df['DMN'] = adx[dmn_cols[0]]
            
            # ATR (Average True Range) - measures volatility
            atr = df.ta.atr(length=self.adx_period)
            if atr is not None and not atr.empty:
                df['ATR'] = atr
            
            # EMAs for trend direction
            df['EMA_FAST'] = df.ta.ema(length=self.ema_fast)
            df['EMA_SLOW'] = df.ta.ema(length=self.ema_slow)
            
            # Bollinger Bandwidth (measure of volatility)
            bbands = df.ta.bbands(length=20, std=2.0)
            if bbands is not None and not bbands.empty:
                lower_cols = [c for c in bbands.columns if c.startswith('BBL')]
                mid_cols = [c for c in bbands.columns if c.startswith('BBM')]
                upper_cols = [c for c in bbands.columns if c.startswith('BBU')]
                
                if lower_cols and mid_cols and upper_cols:
                    upper = bbands[upper_cols[0]]
                    lower = bbands[lower_cols[0]]
                    mid = bbands[mid_cols[0]]
                    df['BB_WIDTH'] = (upper - lower) / mid
            
            return df
            
        except Exception as e:
            logger.error(f"Error adding regime indicators: {e}", exc_info=True)
            return df
    
    def _determine_intermediate_regime(self, df: pd.DataFrame, latest: pd.Series) -> MarketRegime:
        """
        Determine regime when ADX is between trending and ranging thresholds.
        Uses additional indicators to break the tie.
        """
        # Check volatility
        bb_width = latest.get('BB_WIDTH', 0)
        
        # High volatility without strong ADX = VOLATILE
        if bb_width > 0.1:  # Bollinger Bandwidth > 10%
            return MarketRegime.VOLATILE
        
        # Check if EMAs are converging (ranging) or diverging (trending)
        ema_fast = latest.get('EMA_FAST')
        ema_slow = latest.get('EMA_SLOW')
        
        if ema_fast and ema_slow:
            ema_separation = abs(ema_fast - ema_slow) / ema_slow
            if ema_separation < 0.01:  # EMAs within 1% = ranging
                return MarketRegime.RANGING
            elif ema_separation > 0.03:  # EMAs separated by >3% = trending
                return MarketRegime.TRENDING
        
        # Default to ranging in uncertain conditions (safer)
        return MarketRegime.RANGING
    
    def _get_trend_direction(self, latest: pd.Series) -> str:
        """Determine trend direction using EMAs"""
        ema_fast = latest.get('EMA_FAST')
        ema_slow = latest.get('EMA_SLOW')
        di_plus = latest.get('DMP')
        di_minus = latest.get('DMN')
        
        # Primary: EMA crossover
        if ema_fast and ema_slow:
            if ema_fast > ema_slow * 1.01:  # Fast above slow by 1%
                return 'up'
            elif ema_fast < ema_slow * 0.99:  # Fast below slow by 1%
                return 'down'
        
        # Secondary: Directional Movement
        if di_plus and di_minus:
            if di_plus > di_minus * 1.1:
                return 'up'
            elif di_minus > di_plus * 1.1:
                return 'down'
        
        return 'neutral'
    
    def _calculate_confidence(self, adx: float, regime: MarketRegime) -> float:
        """
        Calculate confidence in the regime detection.
        Higher ADX = higher confidence in trending/ranging classification.
        """
        if regime == MarketRegime.TRENDING:
            # Confidence increases as ADX goes above threshold
            # Max confidence at ADX 40+
            confidence = min(1.0, (adx - self.adx_trending_threshold) / 15)
            return max(0.5, confidence)
        
        elif regime == MarketRegime.RANGING:
            # Confidence increases as ADX goes below threshold
            # Max confidence at ADX 10 or below
            confidence = min(1.0, (self.adx_ranging_threshold - adx) / 10)
            return max(0.5, confidence)
        
        elif regime == MarketRegime.VOLATILE:
            return 0.6  # Moderate confidence
        
        else:  # UNKNOWN
            return 0.0
    
    def _is_cache_valid(self) -> bool:
        """Check if cached regime is still valid"""
        if self.last_regime_time is None:
            return False
        
        elapsed = (datetime.now() - self.last_regime_time).total_seconds()
        return elapsed < self.regime_cache_duration
    
    def _build_regime_response(self, regime: MarketRegime, adx: Optional[float]) -> Dict:
        """Build a standardized regime response"""
        return {
            'regime': regime,
            'adx': adx if adx else 0.0,
            'confidence': 0.0 if regime == MarketRegime.UNKNOWN else 0.5,
            'trend_direction': 'neutral',
            'volatility': 0.0,
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'cached': regime == self.last_regime
            }
        }
    
    def get_recommended_strategy(self, regime_info: Dict) -> str:
        """
        Get recommended strategy name based on regime.
        
        Args:
            regime_info: Output from detect_regime()
            
        Returns:
            Strategy name: 'momentum', 'mean_reversion', or 'breakout'
        """
        regime = regime_info['regime']
        trend_direction = regime_info['trend_direction']
        confidence = regime_info['confidence']
        
        # Low confidence - use conservative strategy
        if confidence < 0.4:
            logger.info("Low confidence in regime - using mean_reversion (conservative)")
            return 'mean_reversion'
        
        # High confidence regime selection
        if regime == MarketRegime.TRENDING:
            logger.info(f"TRENDING market detected - using momentum strategy ({trend_direction})")
            return 'momentum'
        
        elif regime == MarketRegime.RANGING:
            logger.info("RANGING market detected - using mean_reversion strategy")
            return 'mean_reversion'
        
        elif regime == MarketRegime.VOLATILE:
            # Volatile markets can benefit from breakout strategies
            logger.info("VOLATILE market detected - using breakout strategy")
            return 'breakout'
        
        else:  # UNKNOWN
            logger.warning("Unknown regime - defaulting to mean_reversion (safest)")
            return 'mean_reversion'
    
    def should_trade(self, regime_info: Dict) -> bool:
        """
        Determine if trading should be allowed based on regime.
        Can be used to pause trading during extremely unfavorable conditions.
        
        Args:
            regime_info: Output from detect_regime()
            
        Returns:
            True if trading should proceed, False to pause
        """
        regime = regime_info['regime']
        confidence = regime_info['confidence']
        volatility = regime_info['volatility']
        
        # Don't trade if regime is unknown
        if regime == MarketRegime.UNKNOWN:
            logger.warning("Market regime unknown - trading paused")
            return False
        
        # Don't trade in extremely high volatility (potential flash crash)
        if volatility > 5.0:  # ATR > 5% of price
            logger.warning(f"Extreme volatility ({volatility:.2f}%) - trading paused")
            return False
        
        # Don't trade with very low confidence
        if confidence < 0.3:
            logger.warning(f"Low regime confidence ({confidence:.1%}) - trading paused")
            return False
        
        return True
