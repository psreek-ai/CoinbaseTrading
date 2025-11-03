"""
Base strategy class and strategy implementations.
All trading strategies inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class TradingSignal:
    """Represents a trading signal."""
    
    def __init__(self, action: str, confidence: float = 0.0, metadata: Dict = None):
        """
        Initialize trading signal.
        
        Args:
            action: 'BUY', 'SELL', or 'HOLD'
            confidence: Signal confidence (0.0 to 1.0)
            metadata: Additional signal information
        """
        self.action = action
        self.confidence = confidence
        self.metadata = metadata or {}
    
    def __repr__(self):
        return f"TradingSignal(action={self.action}, confidence={self.confidence:.2f})"


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""
    
    def __init__(self, config: Dict):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration dictionary
        """
        self.config = config
        self.name = self.__class__.__name__
    
    @abstractmethod
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """
        Analyze market data and generate trading signal.
        
        Args:
            df: DataFrame with OHLCV data and technical indicators
            product_id: Trading pair identifier
            
        Returns:
            TradingSignal object
        """
        pass
    
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators to DataFrame.
        Override in subclasses to add strategy-specific indicators.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added indicators
        """
        return df
    
    def validate_data(self, df: pd.DataFrame, min_periods: int = 26) -> bool:
        """
        Validate that DataFrame has sufficient data for analysis.
        
        Args:
            df: DataFrame to validate
            min_periods: Minimum number of periods required
            
        Returns:
            True if data is valid
        """
        if df.empty or len(df) < min_periods:
            logger.warning(f"Insufficient data for {self.name}: {len(df)} periods")
            return False
        return True
