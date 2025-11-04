from decimal import Decimal, getcontext, ROUND_DOWN
from typing import Dict, Optional, Tuple
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Set precision for Decimal calculations
getcontext().prec = 10


class RiskManager:
    """Manages trading risk and position sizing."""
    
    def __init__(self, config: Dict, db_manager=None):
        """
        Initialize risk manager.
        
        Args:
            config: Risk management configuration
            db_manager: Database manager instance
        """
        self.config = config
        self.db = db_manager
        
        # Risk parameters
        self.risk_percent_per_trade = Decimal(str(config.get('risk_percent_per_trade', '0.01')))
        self.max_position_size_percent = Decimal(str(config.get('max_position_size_percent', '0.10')))
        self.max_total_exposure_percent = Decimal(str(config.get('max_total_exposure_percent', '0.50')))
        self.default_stop_loss_percent = Decimal(str(config.get('default_stop_loss_percent', '0.015')))
        self.default_take_profit_percent = Decimal(str(config.get('default_take_profit_percent', '0.03')))
        self.use_trailing_stop = config.get('use_trailing_stop', False)
        self.trailing_stop_percent = Decimal(str(config.get('trailing_stop_percent', '0.02')))
        self.max_drawdown_percent = Decimal(str(config.get('max_drawdown_percent', '0.15')))
        self.min_usd_trade_value = Decimal(str(config.get('min_usd_trade_value', '10.0')))
        self.max_concurrent_positions = int(config.get('max_concurrent_positions', 5))
        
        # Track peak equity for drawdown calculation
        self.peak_equity = Decimal('0')
        self.trading_halted = False
        self.halt_reason = None
    
    def calculate_position_size(
        self,
        total_equity: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        product_min_size: Decimal = Decimal('0')
    ) -> Tuple[Decimal, Dict]:
        """
        Calculate position size using risk-based sizing.
        
        Args:
            total_equity: Total portfolio equity
            entry_price: Planned entry price
            stop_loss_price: Stop loss price
            product_min_size: Minimum trade size for product
            
        Returns:
            Tuple of (position_size, metadata)
        """
        metadata = {}
        
        # Calculate risk amount (how much we're willing to lose)
        risk_amount = (total_equity * self.risk_percent_per_trade).quantize(Decimal('0.00000001'))
        metadata['risk_amount'] = float(risk_amount)
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss_price)
        if risk_per_unit <= 0:
            logger.warning("Invalid risk per unit calculation (zero or negative)")
            return Decimal('0'), {'error': 'invalid_risk_per_unit'}
        
        metadata['risk_per_unit'] = float(risk_per_unit)
        
        # Calculate base position size
        position_size = (risk_amount / risk_per_unit).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        metadata['calculated_size'] = float(position_size)
        
        # Check against maximum position size
        max_position_value = total_equity * self.max_position_size_percent
        max_position_size = (max_position_value / entry_price).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        if position_size > max_position_size:
            logger.info(f"Position size capped by max position size: {position_size} -> {max_position_size}")
            position_size = max_position_size
            metadata['capped_by'] = 'max_position_size'
        
        # Check minimum size
        if position_size < product_min_size:
            logger.warning(f"Calculated position size {position_size} below minimum {product_min_size}")
            metadata['error'] = 'below_minimum_size'
            return Decimal('0'), metadata
        
        # Check minimum USD value
        position_value = position_size * entry_price
        if position_value < self.min_usd_trade_value:
            logger.warning(f"Position value {position_value} below minimum {self.min_usd_trade_value}")
            metadata['error'] = 'below_minimum_value'
            return Decimal('0'), metadata
        
        metadata['final_size'] = float(position_size)
        metadata['position_value'] = float(position_value)
        
        return position_size, metadata
    
    def calculate_stop_loss_take_profit(
        self,
        entry_price: Decimal,
        side: str = 'BUY'
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate stop loss and take profit prices.
        
        Args:
            entry_price: Entry price
            side: 'BUY' or 'SELL'
            
        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        if side.upper() == 'BUY':
            stop_loss = (entry_price * (Decimal('1') - self.default_stop_loss_percent))\
                        .quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            take_profit = (entry_price * (Decimal('1') + self.default_take_profit_percent))\
                         .quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        else:  # SELL
            stop_loss = (entry_price * (Decimal('1') + self.default_stop_loss_percent))\
                       .quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
            take_profit = (entry_price * (Decimal('1') - self.default_take_profit_percent))\
                         .quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        return stop_loss, take_profit
    
    def can_open_position(
        self,
        current_positions: int,
        current_exposure: Decimal,
        total_equity: Decimal,
        new_position_value: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new position can be opened based on risk limits.
        
        Args:
            current_positions: Number of open positions
            current_exposure: Current total exposure as decimal (e.g., 0.3 for 30%)
            total_equity: Total portfolio equity
            new_position_value: Value of new position to open
            
        Returns:
            Tuple of (can_open, reason_if_cannot)
        """
        # Check if trading is halted
        if self.trading_halted:
            return False, f"Trading halted: {self.halt_reason}"
        
        # Check max concurrent positions
        if current_positions >= self.max_concurrent_positions:
            return False, f"Maximum concurrent positions reached ({self.max_concurrent_positions})"
        
        # Check total exposure limit
        new_exposure = current_exposure + (new_position_value / total_equity)
        if new_exposure > self.max_total_exposure_percent:
            return False, f"Total exposure limit exceeded ({new_exposure:.2%} > {self.max_total_exposure_percent:.2%})"
        
        return True, None
    
    def check_drawdown(self, current_equity: Decimal) -> bool:
        """
        Check if maximum drawdown has been exceeded.
        
        Args:
            current_equity: Current portfolio equity
            
        Returns:
            True if drawdown limit exceeded
        """
        # Update peak equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            # Resume trading if it was halted
            if self.trading_halted and self.halt_reason == 'max_drawdown':
                self.trading_halted = False
                self.halt_reason = None
                logger.info("Trading resumed: recovered from drawdown")
        
        # Calculate drawdown
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            
            if drawdown > self.max_drawdown_percent:
                if not self.trading_halted:
                    self.trading_halted = True
                    self.halt_reason = 'max_drawdown'
                    logger.critical(f"TRADING HALTED: Maximum drawdown exceeded ({drawdown:.2%} > {self.max_drawdown_percent:.2%})")
                return True
        
        return False
    
    def update_trailing_stop(
        self,
        position: Dict,
        current_price: Decimal
    ) -> Optional[Decimal]:
        """
        Update trailing stop loss if enabled.
        
        Args:
            position: Position dictionary with entry_price and stop_loss
            current_price: Current market price
            
        Returns:
            New stop loss price if updated, None otherwise
        """
        if not self.use_trailing_stop:
            return None
        
        entry_price = Decimal(str(position['entry_price']))
        current_stop = Decimal(str(position.get('stop_loss', 0)))
        
        # Calculate trailing stop
        new_stop = (current_price * (Decimal('1') - self.trailing_stop_percent))\
                   .quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        # Only move stop up, never down
        if new_stop > current_stop and new_stop < current_price:
            logger.info(f"Trailing stop updated: {current_stop} -> {new_stop}")
            return new_stop
        
        return None
    
    def should_close_position(
        self,
        position: Dict,
        current_price: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a position should be closed based on risk parameters.
        
        Args:
            position: Position dictionary
            current_price: Current market price
            
        Returns:
            Tuple of (should_close, reason)
        """
        stop_loss = Decimal(str(position.get('stop_loss', 0)))
        take_profit = Decimal(str(position.get('take_profit', 0)))
        
        # Check stop loss
        if stop_loss > 0 and current_price <= stop_loss:
            return True, 'stop_loss'
        
        # Check take profit
        if take_profit > 0 and current_price >= take_profit:
            return True, 'take_profit'
        
        return False, None
    
    def calculate_portfolio_metrics(
        self,
        total_equity: Decimal,
        positions: list
    ) -> Dict:
        """
        Calculate portfolio-level risk metrics.
        
        Args:
            total_equity: Total portfolio equity
            positions: List of open positions
            
        Returns:
            Dictionary of portfolio metrics
        """
        metrics = {
            'total_equity': float(total_equity),
            'num_positions': len(positions),
            'total_exposure': 0.0,
            'total_unrealized_pnl': 0.0,
            'positions_value': 0.0
        }
        
        if not positions or total_equity <= 0:
            return metrics
        
        total_value = Decimal('0')
        total_pnl = Decimal('0')
        
        for pos in positions:
            try:
                size = Decimal(str(pos['base_size']))
                current_price = Decimal(str(pos.get('current_price', pos['entry_price'])))
                entry_price = Decimal(str(pos['entry_price']))
                
                position_value = size * current_price
                total_value += position_value
                
                # Calculate unrealized PnL
                pnl = (current_price - entry_price) * size
                total_pnl += pnl
                
            except Exception as e:
                logger.error(f"Error calculating metrics for position: {e}")
        
        metrics['positions_value'] = float(total_value)
        metrics['total_exposure'] = float(total_value / total_equity)
        metrics['total_unrealized_pnl'] = float(total_pnl)
        metrics['exposure_percent'] = float((total_value / total_equity) * 100)
        
        return metrics
    
    def get_risk_summary(self) -> Dict:
        """Get current risk management status summary."""
        return {
            'trading_halted': self.trading_halted,
            'halt_reason': self.halt_reason,
            'peak_equity': float(self.peak_equity),
            'max_positions': self.max_concurrent_positions,
            'max_exposure_percent': float(self.max_total_exposure_percent * 100),
            'risk_per_trade_percent': float(self.risk_percent_per_trade * 100),
            'use_trailing_stop': self.use_trailing_stop
        }
