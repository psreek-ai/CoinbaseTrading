"""
Base strategy class and strategy implementations.
All trading strategies inherit from BaseStrategy.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal
import pandas as pd
import logging
import json
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Create a separate logger for strategy signals
signal_logger = logging.getLogger('strategy_signals')
signal_logger.setLevel(logging.DEBUG)
signal_logger.propagate = False  # Don't propagate to root logger


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
    
    def to_dict(self) -> Dict:
        """Convert signal to dictionary for logging"""
        return {
            'action': self.action,
            'confidence': self.confidence,
            'metadata': self.metadata
        }


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
        self.log_signals = False
        self.signal_log_file = None
    
    def enable_signal_logging(self, log_file: str = None):
        """
        Enable detailed signal logging.
        
        Args:
            log_file: Path to log file (default: logs/strategy_signals.log)
        """
        self.log_signals = True
        
        if log_file is None:
            log_file = "logs/strategy_signals.log"
        
        self.signal_log_file = log_file
        
        # Ensure logs directory exists
        Path(log_file).parent.mkdir(exist_ok=True)
        
        # Add file handler to signal_logger if not already present
        if not signal_logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            signal_logger.addHandler(handler)
        
        logger.info(f"Strategy signal logging enabled: {log_file}")
    
    def _log_signal(self, product_id: str, signal: TradingSignal, indicators: Dict = None):
        """
        Log strategy signal with full context.
        
        Args:
            product_id: Product being analyzed
            signal: Generated trading signal
            indicators: Current indicator values
        """
        if not self.log_signals:
            return
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'strategy': self.name,
            'product_id': product_id,
            'signal': signal.to_dict(),
            'indicators': indicators or {}
        }
        
        # Log as formatted JSON
        signal_logger.debug(json.dumps(log_entry, indent=2, default=str))
    
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
