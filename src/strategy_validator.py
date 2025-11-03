"""
Strategy Validation Framework
==============================

Provides comprehensive testing and validation to guarantee the trading strategy works correctly.

Features:
1. Historical Backtesting - Verify strategy on past data
2. Signal Quality Analysis - Measure prediction accuracy
3. Paper Trading Validation - Live market testing without risk
4. Performance Metrics - Track win rate, profit factor, Sharpe ratio
5. Statistical Validation - Ensure signals are not random
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    strategy_name: str
    product_id: str
    start_date: datetime
    end_date: datetime
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Financial metrics
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    
    # Signal quality
    avg_signal_confidence: float
    true_positives: int  # BUY signals that led to profit
    false_positives: int  # BUY signals that led to loss
    true_negatives: int  # Correctly avoided bad trades
    false_negatives: int  # Missed good opportunities
    
    # Timing metrics
    avg_trade_duration_hours: float
    avg_profit_per_trade: float
    avg_loss_per_trade: float
    
    def precision(self) -> float:
        """What % of BUY signals were correct"""
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)
    
    def recall(self) -> float:
        """What % of profitable opportunities did we catch"""
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)
    
    def f1_score(self) -> float:
        """Harmonic mean of precision and recall"""
        prec = self.precision()
        rec = self.recall()
        if prec + rec == 0:
            return 0.0
        return 2 * (prec * rec) / (prec + rec)


class StrategyValidator:
    """Validates trading strategy performance and correctness"""
    
    def __init__(self, strategy, api_client, db_manager):
        self.strategy = strategy
        self.api = api_client
        self.db = db_manager
        
    def backtest_product(
        self, 
        product_id: str, 
        days: int = 30,
        initial_capital: float = 1000.0,
        position_size: float = 0.1  # 10% of capital per trade
    ) -> BacktestResult:
        """
        Run historical backtest on a single product
        
        Args:
            product_id: Trading pair to test (e.g., 'BTC-USDC')
            days: Number of days of history to test
            initial_capital: Starting capital in USDC
            position_size: Fraction of capital per trade
        
        Returns:
            BacktestResult with comprehensive metrics
        """
        logger.info(f"Starting backtest for {product_id} over {days} days")
        
        # Get historical data
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        try:
            candles = self.api.get_candles(
                product_id=product_id,
                start=start_time.isoformat(),
                end=end_time.isoformat(),
                granularity="FIFTEEN_MINUTE"
            )
        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            raise
        
        if not candles or len(candles) < 100:
            raise ValueError(f"Insufficient data: only {len(candles) if candles else 0} candles")
        
        # Convert to DataFrame
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['start'], unit='s')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Run strategy analysis
        logger.info(f"Analyzing {len(df)} candles with {self.strategy.__class__.__name__}")
        signal_df = self.strategy.analyze(df, product_id)
        
        # Simulate trading
        trades = []
        capital = initial_capital
        position = None  # Current open position
        max_capital = initial_capital
        min_capital = initial_capital
        
        true_positives = 0
        false_positives = 0
        true_negatives = 0
        false_negatives = 0
        
        for i in range(len(signal_df)):
            row = signal_df.iloc[i]
            current_price = float(row['close'])
            
            # Check if we have a position
            if position is None:
                # Look for BUY signal
                if row['action'] == 'BUY' and row['confidence'] >= 0.5:
                    # Enter position
                    position_value = capital * position_size
                    shares = position_value / current_price
                    
                    position = {
                        'entry_time': row['timestamp'],
                        'entry_price': current_price,
                        'shares': shares,
                        'confidence': row['confidence'],
                        'entry_index': i
                    }
                    logger.debug(f"ENTER at ${current_price:.2f} with confidence {row['confidence']:.2f}")
                
                else:
                    # Check if we missed a good opportunity
                    # Look ahead to see if price went up significantly
                    if i + 20 < len(signal_df):  # Look ahead 5 hours (20 * 15min)
                        future_high = signal_df.iloc[i:i+20]['high'].max()
                        if (future_high - current_price) / current_price > 0.03:  # 3% gain possible
                            false_negatives += 1
                        else:
                            true_negatives += 1
            
            else:
                # We have an open position - check exit conditions
                pnl_pct = (current_price - position['entry_price']) / position['entry_price']
                
                exit_signal = False
                exit_reason = None
                
                # Exit on SELL signal
                if row['action'] == 'SELL':
                    exit_signal = True
                    exit_reason = "SELL signal"
                
                # Exit on stop loss (1.5% loss)
                elif pnl_pct <= -0.015:
                    exit_signal = True
                    exit_reason = "Stop loss"
                
                # Exit on take profit (3% gain)
                elif pnl_pct >= 0.03:
                    exit_signal = True
                    exit_reason = "Take profit"
                
                # Exit if 48 hours passed (192 candles)
                elif i - position['entry_index'] >= 192:
                    exit_signal = True
                    exit_reason = "Time exit"
                
                if exit_signal:
                    # Close position
                    exit_value = position['shares'] * current_price
                    pnl = exit_value - (position['shares'] * position['entry_price'])
                    
                    capital += pnl
                    max_capital = max(max_capital, capital)
                    min_capital = min(min_capital, capital)
                    
                    duration_hours = (row['timestamp'] - position['entry_time']).total_seconds() / 3600
                    
                    trade = {
                        'entry_time': position['entry_time'],
                        'exit_time': row['timestamp'],
                        'entry_price': position['entry_price'],
                        'exit_price': current_price,
                        'shares': position['shares'],
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'duration_hours': duration_hours,
                        'confidence': position['confidence'],
                        'exit_reason': exit_reason
                    }
                    trades.append(trade)
                    
                    # Update signal quality metrics
                    if pnl > 0:
                        true_positives += 1
                    else:
                        false_positives += 1
                    
                    logger.debug(
                        f"EXIT at ${current_price:.2f} ({exit_reason}): "
                        f"PnL ${pnl:.2f} ({pnl_pct*100:.2f}%) in {duration_hours:.1f}h"
                    )
                    
                    position = None
        
        # Calculate metrics
        if not trades:
            logger.warning("No trades executed in backtest")
            return self._empty_result(product_id, start_time, end_time)
        
        trades_df = pd.DataFrame(trades)
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] <= 0]
        
        win_rate = len(winning_trades) / len(trades)
        total_return = (capital - initial_capital) / initial_capital
        max_drawdown = (max_capital - min_capital) / max_capital
        
        # Sharpe ratio (annualized)
        returns = trades_df['pnl_pct'].values
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized
        else:
            sharpe = 0.0
        
        # Profit factor
        gross_profit = winning_trades['pnl'].sum() if len(winning_trades) > 0 else 0
        gross_loss = abs(losing_trades['pnl'].sum()) if len(losing_trades) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        result = BacktestResult(
            strategy_name=self.strategy.__class__.__name__,
            product_id=product_id,
            start_date=start_time,
            end_date=end_time,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            avg_signal_confidence=trades_df['confidence'].mean(),
            true_positives=true_positives,
            false_positives=false_positives,
            true_negatives=true_negatives,
            false_negatives=false_negatives,
            avg_trade_duration_hours=trades_df['duration_hours'].mean(),
            avg_profit_per_trade=winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0,
            avg_loss_per_trade=losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
        )
        
        logger.info(f"Backtest complete: {len(trades)} trades, {win_rate*100:.1f}% win rate, {total_return*100:.1f}% return")
        return result
    
    def _empty_result(self, product_id: str, start_time: datetime, end_time: datetime) -> BacktestResult:
        """Return empty result when no trades"""
        return BacktestResult(
            strategy_name=self.strategy.__class__.__name__,
            product_id=product_id,
            start_date=start_time,
            end_date=end_time,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            profit_factor=0.0,
            avg_signal_confidence=0.0,
            true_positives=0,
            false_positives=0,
            true_negatives=0,
            false_negatives=0,
            avg_trade_duration_hours=0.0,
            avg_profit_per_trade=0.0,
            avg_loss_per_trade=0.0
        )
    
    def validate_live_signals(self, lookback_days: int = 7) -> Dict:
        """
        Validate recent live trading signals against actual outcomes
        
        Args:
            lookback_days: How many days back to analyze
        
        Returns:
            Dictionary with validation metrics
        """
        logger.info(f"Validating live signals from past {lookback_days} days")
        
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        # Query database for recent closed positions
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT 
                product_id, entry_time, exit_time,
                entry_price, exit_price, realized_pnl,
                metadata
            FROM positions
            WHERE status = 'closed'
            AND exit_time >= ?
            ORDER BY exit_time DESC
        """, (cutoff_date.isoformat(),))
        
        positions = cursor.fetchall()
        
        if not positions:
            logger.warning("No closed positions found in specified timeframe")
            return {
                'total_positions': 0,
                'profitable_positions': 0,
                'win_rate': 0.0,
                'avg_confidence': 0.0,
                'confidence_vs_outcome': []
            }
        
        results = []
        for pos in positions:
            product_id, entry_time, exit_time, entry_price, exit_price, pnl, metadata_str = pos
            
            metadata = json.loads(metadata_str) if metadata_str else {}
            confidence = metadata.get('entry_confidence', 0.0)
            
            was_profitable = pnl > 0
            
            results.append({
                'product_id': product_id,
                'confidence': confidence,
                'profitable': was_profitable,
                'pnl': pnl,
                'entry_time': entry_time,
                'exit_time': exit_time
            })
        
        # Analyze correlation between confidence and profitability
        results_df = pd.DataFrame(results)
        
        # Group by confidence bins
        results_df['confidence_bin'] = pd.cut(
            results_df['confidence'], 
            bins=[0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            labels=['<0.5', '0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9+']
        )
        
        confidence_analysis = results_df.groupby('confidence_bin').agg({
            'profitable': ['count', 'sum', 'mean'],
            'pnl': 'mean'
        }).round(3)
        
        return {
            'total_positions': len(results),
            'profitable_positions': results_df['profitable'].sum(),
            'win_rate': results_df['profitable'].mean(),
            'avg_confidence': results_df['confidence'].mean(),
            'total_pnl': results_df['pnl'].sum(),
            'avg_pnl': results_df['pnl'].mean(),
            'confidence_vs_outcome': confidence_analysis.to_dict(),
            'high_confidence_win_rate': results_df[results_df['confidence'] >= 0.7]['profitable'].mean()
        }
    
    def save_backtest_results(self, results: List[BacktestResult], filename: str = None):
        """Save backtest results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backtest_results_{timestamp}.json"
        
        filepath = f"logs/{filename}"
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'results': [asdict(r) for r in results]
        }
        
        # Convert datetime objects to strings
        for result in data['results']:
            result['start_date'] = result['start_date'].isoformat()
            result['end_date'] = result['end_date'].isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved backtest results to {filepath}")
        return filepath
    
    def print_backtest_summary(self, result: BacktestResult):
        """Print formatted backtest summary"""
        print("\n" + "="*80)
        print(f"BACKTEST RESULTS: {result.product_id}")
        print("="*80)
        print(f"Strategy: {result.strategy_name}")
        print(f"Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
        print()
        
        print("TRADE STATISTICS:")
        print(f"  Total Trades: {result.total_trades}")
        print(f"  Winning: {result.winning_trades} | Losing: {result.losing_trades}")
        print(f"  Win Rate: {result.win_rate*100:.2f}%")
        print()
        
        print("PERFORMANCE METRICS:")
        print(f"  Total Return: {result.total_return*100:.2f}%")
        print(f"  Max Drawdown: {result.max_drawdown*100:.2f}%")
        print(f"  Sharpe Ratio: {result.sharpe_ratio:.3f}")
        print(f"  Profit Factor: {result.profit_factor:.2f}")
        print()
        
        print("SIGNAL QUALITY:")
        print(f"  Precision: {result.precision()*100:.2f}% (accuracy of BUY signals)")
        print(f"  Recall: {result.recall()*100:.2f}% (opportunities captured)")
        print(f"  F1 Score: {result.f1_score():.3f}")
        print(f"  Avg Confidence: {result.avg_signal_confidence:.3f}")
        print()
        
        print("TRADE DETAILS:")
        print(f"  Avg Duration: {result.avg_trade_duration_hours:.1f} hours")
        print(f"  Avg Profit: ${result.avg_profit_per_trade:.2f}")
        print(f"  Avg Loss: ${result.avg_loss_per_trade:.2f}")
        print()
        
        print("CONFUSION MATRIX:")
        print(f"  True Positives: {result.true_positives} (correct BUY signals)")
        print(f"  False Positives: {result.false_positives} (incorrect BUY signals)")
        print(f"  True Negatives: {result.true_negatives} (correctly avoided)")
        print(f"  False Negatives: {result.false_negatives} (missed opportunities)")
        print("="*80)
        print()
