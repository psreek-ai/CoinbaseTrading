import unittest
import sys
import os
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from strategy_manager import StrategyManager
from strategies.base_strategy import TradingSignal

class TestStrategyManager(unittest.TestCase):
    def setUp(self):
        self.config = {
            'strategies': {
                'active_strategy': 'momentum',
                'momentum': {'rsi_period': 14},
                'mean_reversion': {'rsi_period': 14},
                'breakout': {'lookback_period': 20},
                'hybrid': {'use_momentum': True}
            }
        }
        self.manager = StrategyManager(self.config)

    def test_initialization(self):
        """Test that all strategies are initialized correctly."""
        self.assertIn('momentum', self.manager.strategies)
        self.assertIn('mean_reversion', self.manager.strategies)
        self.assertIn('breakout', self.manager.strategies)
        self.assertIn('hybrid', self.manager.strategies)
        
        # Check performance tracking initialization
        self.assertIn('momentum', self.manager.performance)
        self.assertEqual(self.manager.performance['momentum']['winning_trades'], 0)

    def test_get_all_signals(self):
        """Test retrieving signals from all strategies."""
        # Mock data
        df = pd.DataFrame({'Close': [100, 101, 102]})
        product_id = 'BTC-USD'
        
        # Mock strategy analyze methods
        for name, strategy in self.manager.strategies.items():
            strategy.analyze = MagicMock(return_value=TradingSignal(
                action='BUY', 
                confidence=0.8, 
                metadata={'reason': 'test'}
            ))
            # Mock add_indicators to return df as is
            strategy.add_indicators = MagicMock(return_value=df)

        signals = self.manager.get_all_signals(df, product_id)
        
        self.assertEqual(len(signals), 4)
        self.assertEqual(signals['momentum'].action, 'BUY')
        self.assertEqual(signals['mean_reversion'].confidence, 0.8)

    def test_update_performance(self):
        """Test updating virtual performance metrics."""
        from decimal import Decimal
        # Simulate a win
        self.manager.update_performance('momentum', Decimal('50.0'), True)
        
        self.assertEqual(self.manager.performance['momentum']['total_trades'], 1)
        self.assertEqual(self.manager.performance['momentum']['winning_trades'], 1)
        self.assertEqual(self.manager.performance['momentum']['total_pnl'], Decimal('50.0'))
        
        # Simulate a loss
        self.manager.update_performance('momentum', Decimal('-20.0'), False)
        
        self.assertEqual(self.manager.performance['momentum']['total_trades'], 2)
        self.assertEqual(self.manager.performance['momentum']['winning_trades'], 1) # Wins shouldn't increase
        self.assertEqual(self.manager.performance['momentum']['total_pnl'], Decimal('30.0'))

    def test_get_performance_summary(self):
        """Test generating performance summary for AI."""
        from decimal import Decimal
        self.manager.update_performance('momentum', Decimal('100.0'), True)
        self.manager.update_performance('mean_reversion', Decimal('-50.0'), False)
        
        summary = self.manager.get_performance_summary()
        
        self.assertIn('momentum', summary)
        self.assertIn('mean_reversion', summary)
        self.assertEqual(summary['momentum']['win_rate'], 1.0)
        self.assertEqual(summary['mean_reversion']['win_rate'], 0.0)

if __name__ == '__main__':
    unittest.main()
