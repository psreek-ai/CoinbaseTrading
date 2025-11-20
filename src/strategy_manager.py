import logging
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from decimal import Decimal

from strategies.strategy_factory import StrategyFactory
from strategies.base_strategy import TradingSignal

logger = logging.getLogger(__name__)

class StrategyManager:
    """
    Manages multiple trading strategies running in parallel.
    Tracks performance and handles strategy switching.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize StrategyManager.
        
        Args:
            config: Main configuration dictionary
        """
        self.config = config
        self.strategies = {}
        self.performance = {}
        
        # Initialize all available strategies
        self._initialize_strategies()
        
    def _initialize_strategies(self):
        """Initialize all available strategies defined in StrategyFactory."""
        available_strategies = StrategyFactory.list_available_strategies()
        
        for strategy_name in available_strategies:
            try:
                # Get strategy-specific config or empty dict
                strategy_config = self.config.get(f'strategies.{strategy_name}', {})
                
                # For hybrid, we might need the whole strategies config
                if strategy_name == 'hybrid':
                    strategy_config = self.config.get('strategies', {})
                
                strategy = StrategyFactory.create_strategy(strategy_name, strategy_config)
                self.strategies[strategy_name] = strategy
                
                # Initialize performance tracking
                self.performance[strategy_name] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'total_pnl': Decimal('0'),
                    'win_rate': 0.0
                }
                
                logger.info(f"Initialized strategy: {strategy_name}")
                
            except Exception as e:
                logger.error(f"Failed to initialize strategy {strategy_name}: {e}")

    def get_strategy(self, strategy_name: str):
        """Get a specific strategy instance."""
        return self.strategies.get(strategy_name)

    def get_all_signals(self, df: pd.DataFrame, product_id: str) -> Dict[str, TradingSignal]:
        """
        Get signals from all strategies for a given product.
        
        Args:
            df: Market data DataFrame
            product_id: Product ID
            
        Returns:
            Dictionary mapping strategy name to TradingSignal
        """
        signals = {}
        
        for name, strategy in self.strategies.items():
            try:
                # Create a copy of df to prevent strategies from modifying shared data
                signal = strategy.analyze(df.copy(), product_id)
                signals[name] = signal
            except Exception as e:
                logger.error(f"Error getting signal from {name} for {product_id}: {e}")
                signals[name] = TradingSignal('HOLD', confidence=0.0, metadata={'error': str(e)})
                
        return signals

    def update_performance(self, strategy_name: str, pnl: Decimal, is_win: bool):
        """
        Update virtual performance tracking for a strategy.
        
        Args:
            strategy_name: Name of the strategy
            pnl: Profit/Loss amount
            is_win: Whether the trade was a win
        """
        if strategy_name not in self.performance:
            return
            
        stats = self.performance[strategy_name]
        stats['total_trades'] += 1
        if is_win:
            stats['winning_trades'] += 1
        stats['total_pnl'] += pnl
        
        if stats['total_trades'] > 0:
            stats['win_rate'] = stats['winning_trades'] / stats['total_trades']

    def get_performance_summary(self) -> Dict:
        """Get summary of performance for all strategies."""
        return self.performance
