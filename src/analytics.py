"""
Performance analytics and reporting.
Calculates trading performance metrics like Sharpe ratio, win rate, etc.
"""

import numpy as np
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class PerformanceAnalytics:
    """Calculates and tracks trading performance metrics."""
    
    def __init__(self, config: Dict, db_manager=None):
        """
        Initialize performance analytics.
        
        Args:
            config: Analytics configuration
            db_manager: Database manager instance
        """
        self.config = config
        self.db = db_manager
        self.risk_free_rate = config.get('risk_free_rate', 0.04)  # Annual risk-free rate
    
    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        period: str = 'daily'
    ) -> Optional[float]:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: List of period returns
            period: 'daily', 'hourly', or 'minute'
            
        Returns:
            Sharpe ratio or None if insufficient data
        """
        if not returns or len(returns) < 2:
            return None
        
        returns_array = np.array(returns)
        
        # Calculate excess returns
        periods_per_year = {
            'daily': 365,
            'hourly': 365 * 24,
            'minute': 365 * 24 * 60
        }
        
        periods = periods_per_year.get(period, 365)
        risk_free_return = self.risk_free_rate / periods
        
        excess_returns = returns_array - risk_free_return
        
        # Calculate Sharpe ratio
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        
        # Annualize
        annualized_sharpe = sharpe * np.sqrt(periods)
        
        return float(annualized_sharpe)
    
    def calculate_sortino_ratio(
        self,
        returns: List[float],
        period: str = 'daily'
    ) -> Optional[float]:
        """
        Calculate Sortino ratio (only considers downside volatility).
        
        Args:
            returns: List of period returns
            period: 'daily', 'hourly', or 'minute'
            
        Returns:
            Sortino ratio or None if insufficient data
        """
        if not returns or len(returns) < 2:
            return None
        
        returns_array = np.array(returns)
        
        periods_per_year = {
            'daily': 365,
            'hourly': 365 * 24,
            'minute': 365 * 24 * 60
        }
        
        periods = periods_per_year.get(period, 365)
        risk_free_return = self.risk_free_rate / periods
        
        excess_returns = returns_array - risk_free_return
        
        # Calculate downside deviation (only negative returns)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0.0
        
        downside_deviation = np.std(downside_returns)
        
        sortino = np.mean(excess_returns) / downside_deviation
        
        # Annualize
        annualized_sortino = sortino * np.sqrt(periods)
        
        return float(annualized_sortino)
    
    def calculate_max_drawdown(self, equity_curve: List[float]) -> Dict:
        """
        Calculate maximum drawdown from equity curve.
        
        Args:
            equity_curve: List of equity values over time
            
        Returns:
            Dictionary with drawdown metrics
        """
        if not equity_curve or len(equity_curve) < 2:
            return {'max_drawdown': 0.0, 'max_drawdown_percent': 0.0}
        
        equity_array = np.array(equity_curve)
        
        # Calculate running maximum
        running_max = np.maximum.accumulate(equity_array)
        
        # Calculate drawdown
        drawdown = running_max - equity_array
        drawdown_percent = drawdown / running_max
        
        max_dd = np.max(drawdown)
        max_dd_pct = np.max(drawdown_percent)
        
        # Find when max drawdown occurred
        max_dd_idx = np.argmax(drawdown_percent)
        
        return {
            'max_drawdown': float(max_dd),
            'max_drawdown_percent': float(max_dd_pct),
            'max_drawdown_index': int(max_dd_idx)
        }
    
    def calculate_win_rate(self, trades: List[Dict]) -> Dict:
        """
        Calculate win rate and related metrics.
        
        Args:
            trades: List of completed trades
            
        Returns:
            Dictionary with win rate metrics
        """
        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0
            }
        
        wins = [t for t in trades if t.get('pnl', 0) > 0]
        losses = [t for t in trades if t.get('pnl', 0) < 0]
        breakevens = [t for t in trades if t.get('pnl', 0) == 0]
        
        total = len(trades)
        win_count = len(wins)
        loss_count = len(losses)
        
        win_rate = win_count / total if total > 0 else 0.0
        
        # Calculate average win/loss
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0.0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0.0
        
        # Profit factor
        total_wins = sum(t['pnl'] for t in wins)
        total_losses = abs(sum(t['pnl'] for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        # Expectancy
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        
        return {
            'total_trades': total,
            'wins': win_count,
            'losses': loss_count,
            'breakevens': len(breakevens),
            'win_rate': win_rate,
            'avg_win': float(avg_win),
            'avg_loss': float(avg_loss),
            'profit_factor': float(profit_factor),
            'expectancy': float(expectancy)
        }
    
    def calculate_risk_reward_ratio(self, trades: List[Dict]) -> Optional[float]:
        """
        Calculate average risk/reward ratio.
        
        Args:
            trades: List of completed trades
            
        Returns:
            Average risk/reward ratio
        """
        if not trades:
            return None
        
        ratios = []
        for trade in trades:
            pnl = trade.get('pnl', 0)
            # Risk is typically the stop loss distance
            # For simplicity, use absolute PnL
            if pnl < 0:
                # This was a loss (risk realized)
                risk = abs(pnl)
                if trade.get('max_profit'):
                    reward = trade['max_profit']
                    if risk > 0:
                        ratios.append(reward / risk)
        
        return float(np.mean(ratios)) if ratios else None
    
    def generate_performance_report(
        self,
        equity_curve: List[float],
        trades: List[Dict],
        current_equity: float,
        initial_equity: float,
        days: int = 30
    ) -> Dict:
        """
        Generate comprehensive performance report.
        
        Args:
            equity_curve: List of equity values
            trades: List of completed trades
            current_equity: Current portfolio equity
            initial_equity: Starting equity
            days: Number of days for report
            
        Returns:
            Performance report dictionary
        """
        # Calculate returns from equity curve
        returns = []
        if len(equity_curve) > 1:
            for i in range(1, len(equity_curve)):
                if equity_curve[i-1] != 0:
                    ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                    returns.append(ret)
        
        # Calculate metrics
        sharpe = self.calculate_sharpe_ratio(returns, period='daily')
        sortino = self.calculate_sortino_ratio(returns, period='daily')
        drawdown = self.calculate_max_drawdown(equity_curve)
        win_metrics = self.calculate_win_rate(trades)
        
        # Calculate total return
        total_return = ((current_equity - initial_equity) / initial_equity) if initial_equity > 0 else 0.0
        
        # Calculate annualized return
        if days > 0:
            annualized_return = ((current_equity / initial_equity) ** (365 / days)) - 1
        else:
            annualized_return = 0.0
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'period_days': days,
            'initial_equity': initial_equity,
            'current_equity': current_equity,
            'total_return': total_return,
            'total_return_percent': total_return * 100,
            'annualized_return': annualized_return,
            'annualized_return_percent': annualized_return * 100,
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'max_drawdown': drawdown['max_drawdown'],
            'max_drawdown_percent': drawdown['max_drawdown_percent'] * 100,
            'total_trades': win_metrics['total_trades'],
            'wins': win_metrics['wins'],
            'losses': win_metrics['losses'],
            'win_rate': win_metrics['win_rate'],
            'win_rate_percent': win_metrics['win_rate'] * 100,
            'avg_win': win_metrics['avg_win'],
            'avg_loss': win_metrics['avg_loss'],
            'profit_factor': win_metrics['profit_factor'],
            'expectancy': win_metrics['expectancy']
        }
        
        return report
    
    def save_performance_snapshot(self, metrics: Dict):
        """Save performance metrics to database."""
        if self.db:
            try:
                self.db.insert_performance_metrics(metrics)
                logger.info("Performance snapshot saved to database")
            except Exception as e:
                logger.error(f"Error saving performance snapshot: {e}")
    
    def get_historical_performance(self, days: int = 30) -> Dict:
        """
        Get historical performance data from database.
        
        Args:
            days: Number of days to retrieve
            
        Returns:
            Performance data dictionary
        """
        if not self.db:
            return {}
        
        try:
            # Get trade statistics
            trade_stats = self.db.get_trade_statistics(days=days)
            
            # Get equity curve
            equity_data = self.db.get_equity_curve(days=days)
            
            return {
                'trade_statistics': trade_stats,
                'equity_curve': equity_data
            }
        except Exception as e:
            logger.error(f"Error retrieving historical performance: {e}")
            return {}
