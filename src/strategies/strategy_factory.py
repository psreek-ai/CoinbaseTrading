"""
Strategy factory and hybrid strategy implementation.
"""

from typing import Dict, List
import logging
from .base_strategy import BaseStrategy, TradingSignal
from .momentum_strategy import MomentumStrategy
from .mean_reversion_strategy import MeanReversionStrategy
from .breakout_strategy import BreakoutStrategy
import pandas as pd

logger = logging.getLogger(__name__)


class HybridStrategy(BaseStrategy):
    """
    Hybrid strategy that combines multiple strategies.
    Requires agreement from multiple strategies for stronger signals.
    """
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        self.use_momentum = config.get('use_momentum', True)
        self.use_mean_reversion = config.get('use_mean_reversion', True)
        self.use_breakout = config.get('use_breakout', False)
        self.min_signals_required = config.get('min_signals_required', 2)
        
        # Initialize sub-strategies
        self.strategies = []
        
        if self.use_momentum:
            momentum_config = config.get('momentum', {})
            self.strategies.append(MomentumStrategy(momentum_config))
        
        if self.use_mean_reversion:
            mean_reversion_config = config.get('mean_reversion', {})
            self.strategies.append(MeanReversionStrategy(mean_reversion_config))
        
        if self.use_breakout:
            breakout_config = config.get('breakout', {})
            self.strategies.append(BreakoutStrategy(breakout_config))
        
        logger.info(f"HybridStrategy initialized with {len(self.strategies)} sub-strategies")
    
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal:
        """Combine signals from multiple strategies."""
        
        if not self.validate_data(df):
            return TradingSignal('HOLD', confidence=0.0)
        
        # Collect signals from all strategies
        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(df.copy(), product_id)
                signals.append({
                    'strategy': strategy.name,
                    'signal': signal
                })
            except Exception as e:
                logger.error(f"Error in {strategy.name} for {product_id}: {e}")
        
        if not signals:
            return TradingSignal('HOLD', confidence=0.0)
        
        # Count BUY, SELL, HOLD signals
        buy_count = sum(1 for s in signals if s['signal'].action == 'BUY')
        sell_count = sum(1 for s in signals if s['signal'].action == 'SELL')
        
        # Calculate average confidence for each action
        buy_confidence = sum(s['signal'].confidence for s in signals 
                            if s['signal'].action == 'BUY') / max(buy_count, 1)
        sell_confidence = sum(s['signal'].confidence for s in signals 
                             if s['signal'].action == 'SELL') / max(sell_count, 1)
        
        # Build metadata
        metadata = {
            'strategies_used': [s['strategy'] for s in signals],
            'buy_votes': buy_count,
            'sell_votes': sell_count,
            'total_strategies': len(signals),
            'individual_signals': [
                {
                    'strategy': s['strategy'],
                    'action': s['signal'].action,
                    'confidence': s['signal'].confidence
                } for s in signals
            ]
        }
        
        # Decision logic: require minimum number of agreeing signals
        if buy_count >= self.min_signals_required and buy_count > sell_count:
            logger.info(f"HYBRID BUY for {product_id}: {buy_count}/{len(signals)} strategies agree")
            return TradingSignal('BUY', confidence=buy_confidence, metadata=metadata)
        
        if sell_count >= self.min_signals_required and sell_count > buy_count:
            logger.info(f"HYBRID SELL for {product_id}: {sell_count}/{len(signals)} strategies agree")
            return TradingSignal('SELL', confidence=sell_confidence, metadata=metadata)
        
        # Mixed or insufficient signals
        return TradingSignal('HOLD', confidence=0.5, metadata=metadata)


class StrategyFactory:
    """Factory for creating trading strategies."""
    
    @staticmethod
    def create_strategy(strategy_name: str, config: Dict) -> BaseStrategy:
        """
        Create a strategy instance.
        
        Args:
            strategy_name: Name of strategy to create
            config: Strategy configuration
            
        Returns:
            Strategy instance
        """
        strategies = {
            'momentum': MomentumStrategy,
            'mean_reversion': MeanReversionStrategy,
            'breakout': BreakoutStrategy,
            'hybrid': HybridStrategy
        }
        
        if strategy_name not in strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}. "
                           f"Available: {list(strategies.keys())}")
        
        strategy_class = strategies[strategy_name]
        return strategy_class(config)
    
    @staticmethod
    def list_available_strategies() -> List[str]:
        """Get list of available strategy names."""
        return ['momentum', 'mean_reversion', 'breakout', 'hybrid']
