"""
Enhanced Trade Logger for Strategy Analysis and Experimentation

This module captures comprehensive trade data including:
- Full market state at decision time
- All indicator values
- Order execution details
- Position lifecycle
- Performance metrics

Data is logged in JSON format for easy analysis and replay.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from decimal import Decimal
import pandas as pd

logger = logging.getLogger(__name__)


class TradeAnalyticsLogger:
    """
    Captures detailed trade data for post-trading analysis and strategy optimization.
    Allows replaying trades with different parameters to identify best strategy.
    """
    
    def __init__(self, log_dir: str = "logs/analytics"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create session-specific file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_file = self.log_dir / f"trade_analytics_{timestamp}.jsonl"
        self.trades_file = self.log_dir / f"trades_{timestamp}.jsonl"
        self.market_state_file = self.log_dir / f"market_state_{timestamp}.jsonl"
        
        logger.info(f"Analytics logger initialized: {self.session_file}")
    
    def _serialize(self, obj: Any) -> Any:
        """Convert non-serializable objects to JSON-compatible format"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, pd.Series):
            return obj.to_dict()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict('records')
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return obj
    
    def _write_jsonl(self, filepath: Path, data: Dict):
        """Write JSON line to file"""
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                json_data = json.dumps(data, default=self._serialize)
                f.write(json_data + '\n')
        except Exception as e:
            logger.error(f"Error writing to {filepath}: {e}")
    
    def log_market_scan(
        self,
        timestamp: datetime,
        scan_results: list,
        total_scanned: int,
        opportunities_found: int,
        scan_duration_seconds: float,
        active_strategy: str,
        market_regime: Optional[str] = None
    ):
        """Log market scan results for analysis"""
        data = {
            'event_type': 'market_scan',
            'timestamp': timestamp.isoformat(),
            'total_scanned': total_scanned,
            'opportunities_found': opportunities_found,
            'scan_duration_seconds': scan_duration_seconds,
            'active_strategy': active_strategy,
            'market_regime': market_regime,
            'top_opportunities': scan_results[:5] if scan_results else []
        }
        self._write_jsonl(self.session_file, data)
    
    def log_signal_analysis(
        self,
        timestamp: datetime,
        product_id: str,
        signal: str,
        confidence: float,
        current_price: float,
        indicators: Dict[str, float],
        candle_data: Optional[pd.DataFrame] = None,
        strategy_name: str = None,
        signal_reasons: list = None,
        signal_score: float = None
    ):
        """
        Log signal generation with full market context.
        This is critical for strategy backtesting and optimization.
        """
        data = {
            'event_type': 'signal_analysis',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'signal': signal,
            'confidence': confidence,
            'current_price': current_price,
            'strategy': strategy_name,
            'signal_score': signal_score,
            'signal_reasons': signal_reasons or [],
            'indicators': indicators,
            'candle_summary': None
        }
        
        # Capture last 5 candles for context
        if candle_data is not None and len(candle_data) >= 5:
            last_candles = candle_data.tail(5)
            data['candle_summary'] = {
                'last_5_candles': [
                    {
                        'timestamp': str(row.name) if hasattr(row.name, '__str__') else str(i),
                        'open': float(row.get('Open', 0)),
                        'high': float(row.get('High', 0)),
                        'low': float(row.get('Low', 0)),
                        'close': float(row.get('Close', 0)),
                        'volume': float(row.get('Volume', 0))
                    }
                    for i, (idx, row) in enumerate(last_candles.iterrows())
                ]
            }
        
        self._write_jsonl(self.market_state_file, data)
    
    def log_entry_decision(
        self,
        timestamp: datetime,
        product_id: str,
        decision: str,  # 'execute', 'skip', 'rejected'
        signal_data: Dict,
        reason: Optional[str] = None,
        balance: Optional[float] = None,
        risk_checks: Optional[Dict] = None,
        spread_analysis: Optional[Dict] = None,
        volume_analysis: Optional[Dict] = None,
        position_sizing: Optional[Dict] = None
    ):
        """
        Log entry decision with all risk management data.
        Essential for understanding why trades were/weren't taken.
        """
        data = {
            'event_type': 'entry_decision',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'decision': decision,
            'reason': reason,
            'signal_data': signal_data,
            'balance_usd': balance,
            'risk_checks': risk_checks or {},
            'spread_analysis': spread_analysis or {},
            'volume_analysis': volume_analysis or {},
            'position_sizing': position_sizing or {}
        }
        self._write_jsonl(self.session_file, data)
    
    def log_order_placement(
        self,
        timestamp: datetime,
        product_id: str,
        order_id: str,
        side: str,
        order_type: str,
        size: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        post_only: bool = False,
        fees_expected: Optional[float] = None,
        slippage_expected: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        """Log order placement details"""
        data = {
            'event_type': 'order_placement',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'order_id': order_id,
            'side': side,
            'order_type': order_type,
            'size': size,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'post_only': post_only,
            'fees_expected': fees_expected,
            'slippage_expected': slippage_expected,
            'metadata': metadata or {}
        }
        self._write_jsonl(self.trades_file, data)
    
    def log_shadow_trade(
        self,
        timestamp: datetime,
        product_id: str,
        strategy_name: str,
        side: str,
        price: float,
        size: float,
        pnl: Optional[float] = None,
        pnl_pct: Optional[float] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Log a 'shadow' trade (simulated trade for a non-active strategy).
        Used to track performance of strategies not currently controlling the bot.
        """
        data = {
            'event_type': 'shadow_trade',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'strategy': strategy_name,
            'side': side,
            'price': price,
            'size': size,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'metadata': metadata or {}
        }
        self._write_jsonl(self.session_file, data)

    def log_order_fill(
        self,
        timestamp: datetime,
        product_id: str,
        order_id: str,
        side: str,
        filled_size: float,
        filled_price: float,
        actual_fees: float,
        actual_slippage: Optional[float] = None,
        fill_time_seconds: Optional[float] = None,
        fills_detail: Optional[list] = None
    ):
        """Log order fill execution details"""
        data = {
            'event_type': 'order_fill',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'order_id': order_id,
            'side': side,
            'filled_size': filled_size,
            'filled_price': filled_price,
            'actual_fees': actual_fees,
            'actual_slippage': actual_slippage,
            'fill_time_seconds': fill_time_seconds,
            'fills_detail': fills_detail or []
        }
        self._write_jsonl(self.trades_file, data)
    
    def log_position_update(
        self,
        timestamp: datetime,
        product_id: str,
        current_price: float,
        entry_price: float,
        position_size: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        cost_basis: Optional[float] = None,
        holding_time_seconds: Optional[int] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop: Optional[float] = None,
        current_signal: Optional[str] = None,
        current_confidence: Optional[float] = None
    ):
        """
        Log position monitoring data.
        Critical for understanding how positions evolve and when to exit.
        """
        data = {
            'event_type': 'position_update',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'current_price': current_price,
            'entry_price': entry_price,
            'cost_basis': cost_basis,
            'position_size': position_size,
            'unrealized_pnl': unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'holding_time_seconds': holding_time_seconds,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'trailing_stop': trailing_stop,
            'current_signal': current_signal,
            'current_confidence': current_confidence
        }
        self._write_jsonl(self.session_file, data)
    
    def log_exit_decision(
        self,
        timestamp: datetime,
        product_id: str,
        decision: str,  # 'hold', 'exit_profit', 'exit_loss', 'exit_signal', 'exit_emergency'
        current_price: float,
        entry_price: float,
        pnl_pct: float,
        exit_reason: str,
        signal_data: Optional[Dict] = None,
        stop_triggered: bool = False,
        take_profit_triggered: bool = False,
        emergency_exit: bool = False
    ):
        """Log exit decision logic"""
        data = {
            'event_type': 'exit_decision',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'decision': decision,
            'current_price': current_price,
            'entry_price': entry_price,
            'pnl_pct': pnl_pct,
            'exit_reason': exit_reason,
            'signal_data': signal_data or {},
            'stop_triggered': stop_triggered,
            'take_profit_triggered': take_profit_triggered,
            'emergency_exit': emergency_exit
        }
        self._write_jsonl(self.session_file, data)
    
    def log_trade_complete(
        self,
        timestamp: datetime,
        product_id: str,
        entry_order_id: str,
        exit_order_id: str,
        side: str,
        entry_price: float,
        exit_price: float,
        position_size: float,
        realized_pnl: float,
        realized_pnl_pct: float,
        total_fees: float,
        entry_fees: float,
        exit_fees: float,
        slippage: float,
        holding_time_seconds: int,
        entry_signal: Dict,
        exit_signal: Dict,
        entry_strategy: str,
        exit_reason: str,
        max_profit_pct: Optional[float] = None,
        max_loss_pct: Optional[float] = None,
        cost_basis: Optional[float] = None
    ):
        """
        Log completed trade with full lifecycle data.
        This is the GOLD STANDARD record for strategy analysis.
        """
        data = {
            'event_type': 'trade_complete',
            'timestamp': timestamp.isoformat(),
            'product_id': product_id,
            'entry_order_id': entry_order_id,
            'exit_order_id': exit_order_id,
            'side': side,
            
            # Pricing
            'entry_price': entry_price,
            'exit_price': exit_price,
            'cost_basis': cost_basis,
            'position_size': position_size,
            
            # Performance
            'realized_pnl': realized_pnl,
            'realized_pnl_pct': realized_pnl_pct,
            'max_profit_pct': max_profit_pct,
            'max_loss_pct': max_loss_pct,
            
            # Costs
            'total_fees': total_fees,
            'entry_fees': entry_fees,
            'exit_fees': exit_fees,
            'slippage': slippage,
            
            # Timing
            'holding_time_seconds': holding_time_seconds,
            'holding_time_minutes': holding_time_seconds / 60,
            'holding_time_hours': holding_time_seconds / 3600,
            
            # Strategy
            'entry_strategy': entry_strategy,
            'entry_signal': entry_signal,
            'exit_reason': exit_reason,
            'exit_signal': exit_signal,
            
            # Metadata for analysis
            'was_winner': realized_pnl > 0,
            'fee_pct': (total_fees / (entry_price * position_size)) * 100 if entry_price * position_size > 0 else 0,
            'profit_after_fees': realized_pnl - total_fees
        }
        self._write_jsonl(self.trades_file, data)
    
    def log_session_summary(
        self,
        timestamp: datetime,
        session_duration_seconds: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        total_fees: float,
        win_rate: float,
        avg_winner: float,
        avg_loser: float,
        largest_winner: float,
        largest_loser: float,
        total_volume: float,
        strategies_used: Dict[str, int],
        products_traded: list
    ):
        """Log session performance summary"""
        data = {
            'event_type': 'session_summary',
            'timestamp': timestamp.isoformat(),
            'session_duration_seconds': session_duration_seconds,
            'session_duration_hours': session_duration_seconds / 3600,
            
            # Trade statistics
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            
            # Performance
            'total_pnl': total_pnl,
            'total_fees': total_fees,
            'net_pnl': total_pnl - total_fees,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'profit_factor': abs(avg_winner / avg_loser) if avg_loser != 0 else 0,
            'largest_winner': largest_winner,
            'largest_loser': largest_loser,
            
            # Volume
            'total_volume': total_volume,
            
            # Strategy breakdown
            'strategies_used': strategies_used,
            'products_traded': products_traded
        }
        self._write_jsonl(self.session_file, data)
    
    def log_error(
        self,
        timestamp: datetime,
        error_type: str,
        error_message: str,
        product_id: Optional[str] = None,
        context: Optional[Dict] = None
    ):
        """Log errors for debugging"""
        data = {
            'event_type': 'error',
            'timestamp': timestamp.isoformat(),
            'error_type': error_type,
            'error_message': error_message,
            'product_id': product_id,
            'context': context or {}
        }
        self._write_jsonl(self.session_file, data)


class TradeReplayEngine:
    """
    Replays logged trades with different strategy parameters.
    Allows testing "what if" scenarios without live trading.
    """
    
    def __init__(self, analytics_file: str):
        self.analytics_file = Path(analytics_file)
        self.trades_file = analytics_file.replace('trade_analytics', 'trades')
        self.market_state_file = analytics_file.replace('trade_analytics', 'market_state')
    
    def load_trades(self) -> list:
        """Load all completed trades from log file"""
        trades = []
        if not Path(self.trades_file).exists():
            return trades
        
        with open(self.trades_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get('event_type') == 'trade_complete':
                        trades.append(data)
                except json.JSONDecodeError:
                    continue
        return trades
    
    def load_market_states(self) -> list:
        """Load all market state snapshots"""
        states = []
        if not Path(self.market_state_file).exists():
            return states
        
        with open(self.market_state_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get('event_type') == 'signal_analysis':
                        states.append(data)
                except json.JSONDecodeError:
                    continue
        return states
    
    def replay_with_params(
        self,
        min_confidence: float = None,
        min_rsi: float = None,
        max_rsi: float = None,
        stop_loss_pct: float = None,
        take_profit_pct: float = None,
        max_holding_hours: float = None
    ) -> Dict:
        """
        Replay trades with different parameters.
        Returns performance metrics for the new parameters.
        """
        trades = self.load_trades()
        states = self.load_market_states()
        
        # Build lookup for market states by product/time
        state_lookup = {}
        for state in states:
            key = f"{state['product_id']}_{state['timestamp']}"
            state_lookup[key] = state
        
        filtered_trades = []
        modified_trades = []
        
        for trade in trades:
            # Apply new filters
            entry_signal = trade.get('entry_signal', {})
            entry_confidence = entry_signal.get('confidence', 1.0)
            
            # Confidence filter
            if min_confidence and entry_confidence < min_confidence:
                continue
            
            # RSI filter (if indicator available)
            indicators = entry_signal.get('indicators', {})
            rsi = indicators.get('RSI')
            if rsi:
                if min_rsi and rsi < min_rsi:
                    continue
                if max_rsi and rsi > max_rsi:
                    continue
            
            # Apply new stop/target levels
            modified_trade = trade.copy()
            entry_price = trade['entry_price']
            exit_price = trade['exit_price']
            
            if stop_loss_pct:
                new_stop = entry_price * (1 - stop_loss_pct / 100)
                if trade['exit_price'] < new_stop:
                    # Would have stopped out
                    modified_trade['exit_price'] = new_stop
                    modified_trade['exit_reason'] = f'Modified stop loss ({stop_loss_pct}%)'
            
            if take_profit_pct:
                new_target = entry_price * (1 + take_profit_pct / 100)
                if trade['exit_price'] > new_target:
                    # Would have hit target
                    modified_trade['exit_price'] = new_target
                    modified_trade['exit_reason'] = f'Modified take profit ({take_profit_pct}%)'
            
            # Recalculate P&L
            new_pnl_pct = ((modified_trade['exit_price'] - entry_price) / entry_price) * 100
            modified_trade['realized_pnl_pct'] = new_pnl_pct
            modified_trade['was_winner'] = new_pnl_pct > 0
            
            modified_trades.append(modified_trade)
        
        # Calculate new performance metrics
        if not modified_trades:
            return {'error': 'No trades match filters'}
        
        winners = [t for t in modified_trades if t['was_winner']]
        losers = [t for t in modified_trades if not t['was_winner']]
        
        total_pnl = sum(t['realized_pnl_pct'] for t in modified_trades)
        avg_winner = sum(t['realized_pnl_pct'] for t in winners) / len(winners) if winners else 0
        avg_loser = sum(t['realized_pnl_pct'] for t in losers) / len(losers) if losers else 0
        
        return {
            'total_trades': len(modified_trades),
            'original_trades': len(trades),
            'trades_filtered': len(trades) - len(modified_trades),
            'winning_trades': len(winners),
            'losing_trades': len(losers),
            'win_rate': len(winners) / len(modified_trades) if modified_trades else 0,
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': total_pnl / len(modified_trades),
            'avg_winner_pct': avg_winner,
            'avg_loser_pct': avg_loser,
            'profit_factor': abs(avg_winner / avg_loser) if avg_loser != 0 else 0,
            'max_winner': max((t['realized_pnl_pct'] for t in modified_trades), default=0),
            'max_loser': min((t['realized_pnl_pct'] for t in modified_trades), default=0),
            'parameters_used': {
                'min_confidence': min_confidence,
                'min_rsi': min_rsi,
                'max_rsi': max_rsi,
                'stop_loss_pct': stop_loss_pct,
                'take_profit_pct': take_profit_pct
            }
        }
