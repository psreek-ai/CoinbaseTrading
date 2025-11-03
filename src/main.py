"""
Robust Automated Algorithmic Crypto Trading Bot for Coinbase
============================================================

Features:
- Multiple trading strategies (Momentum, Mean Reversion, Breakout, Hybrid)
- Advanced risk management with position sizing and portfolio-level controls
- Performance analytics (Sharpe ratio, win rate, equity curve tracking)
- Database persistence for orders, positions, and metrics
- Configurable via YAML files
- Paper trading mode for testing
- WebSocket real-time price feeds
- Comprehensive logging and error handling

Author: AI Trading Bot System
Version: 2.1 (Enhanced Edition)
"""

import sys
import time
import logging
import signal
from pathlib import Path
from decimal import Decimal
from datetime import datetime, UTC
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from database import DatabaseManager
from api_client import CoinbaseAPI
from strategies import StrategyFactory
from risk_management import RiskManager
from analytics import PerformanceAnalytics

# Global shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info("Shutdown signal received. Cleaning up...")
    shutdown_requested = True


class TradingBot:
    """Main trading bot class."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize trading bot.
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = get_config(config_path)
        
        # Setup logging
        self._setup_logging()
        
        logger.info("=" * 80)
        logger.info("COINBASE ALGORITHMIC TRADING BOT - STARTING")
        logger.info("=" * 80)
        
        # Initialize components
        self.db = self._initialize_database()
        self.api = self._initialize_api()
        self.strategy = self._initialize_strategy()
        self.risk_manager = self._initialize_risk_manager()
        self.analytics = self._initialize_analytics()
        
        # Bot state
        self.portfolio_id = None
        self.paper_trading = self.config.get('trading.paper_trading_mode', True)
        
        # Track initial equity for performance calculation
        self.initial_equity = Decimal('0')
        
        # Register order update callback
        self.api.register_order_update_callback(self._on_order_update)
        
        logger.info(f"Paper Trading Mode: {self.paper_trading}")
        logger.info(f"Active Strategy: {self.config.get('strategies.active_strategy')}")
        
    def _setup_logging(self):
        """Configure logging."""
        global logger
        
        log_level = getattr(logging, self.config.get('logging.level', 'INFO'))
        log_dir = Path(self.config.get('logging.log_directory', 'logs'))
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"trading_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Logging initialized. Log file: {log_file}")
    
    def _initialize_database(self) -> DatabaseManager:
        """Initialize database."""
        db_path = self.config.get('database.path', 'data/trading_bot.db')
        logger.info(f"Initializing database: {db_path}")
        return DatabaseManager(db_path)
    
    def _initialize_api(self) -> CoinbaseAPI:
        """Initialize Coinbase API client."""
        logger.info("Initializing Coinbase API client")
        api_key, api_secret = self.config.get_api_credentials()
        api = CoinbaseAPI(api_key, api_secret)
        
        # Check API permissions
        permissions = api.check_api_permissions()
        if permissions:
            if not permissions.get('can_view'):
                logger.critical("API key does not have VIEW permissions!")
            if not permissions.get('can_trade') and not self.config.get('trading.paper_trading_mode', True):
                logger.critical("API key does not have TRADE permissions - LIVE TRADING DISABLED")
            logger.info(f"API Permissions: View={permissions.get('can_view')}, "
                       f"Trade={permissions.get('can_trade')}, "
                       f"Transfer={permissions.get('can_transfer')}")
        
        return api
    
    def _initialize_strategy(self) -> object:
        """Initialize trading strategy."""
        strategy_name = self.config.get('strategies.active_strategy', 'momentum')
        strategy_config = self.config.get(f'strategies.{strategy_name}', {})
        
        # For hybrid strategy, include all strategy configs
        if strategy_name == 'hybrid':
            strategy_config = self.config['strategies']
        
        logger.info(f"Initializing {strategy_name} strategy")
        return StrategyFactory.create_strategy(strategy_name, strategy_config)
    
    def _initialize_risk_manager(self) -> RiskManager:
        """Initialize risk manager."""
        logger.info("Initializing risk management system")
        risk_config = self.config.get('risk_management', {})
        return RiskManager(risk_config, self.db)
    
    def _initialize_analytics(self) -> PerformanceAnalytics:
        """Initialize performance analytics."""
        logger.info("Initializing performance analytics")
        analytics_config = self.config.get('analytics', {})
        return PerformanceAnalytics(analytics_config, self.db)
    
    def _get_total_equity(self, balances: Dict[str, Decimal]) -> Decimal:
        """
        Calculate total equity in USD equivalent.
        
        Args:
            balances: Dictionary of asset balances
            
        Returns:
            Total equity in USD
        """
        total = Decimal('0')
        
        for asset, balance in balances.items():
            if asset == 'USD' or asset == 'USDC':
                total += balance
            else:
                # Try to get USD price
                price = self.api.get_latest_price(f"{asset}-USD")
                if price:
                    total += balance * price
                else:
                    # Try USDC as fallback
                    price = self.api.get_latest_price(f"{asset}-USDC")
                    if price:
                        total += balance * price
        
        return total
    
    def _on_order_update(self, order_update: Dict):
        """
        Callback for real-time order updates via WebSocket user channel.
        
        Args:
            order_update: Order update details
        """
        order_id = order_update.get('order_id')
        status = order_update.get('status')
        product_id = order_update.get('product_id')
        
        logger.info(f"[WEBSOCKET] Order update received: {order_id} - {status} ({product_id})")
        
        # Update order status in database
        if status in ['FILLED', 'CANCELLED', 'EXPIRED', 'FAILED']:
            try:
                # Update order in database
                # Note: Database update logic would go here
                logger.info(f"Order {order_id} reached final state: {status}")
                
                # If filled, update position
                if status == 'FILLED':
                    filled_size = order_update.get('filled_size', Decimal('0'))
                    avg_price = order_update.get('average_price', Decimal('0'))
                    logger.info(f"Order filled: {filled_size} @ ${avg_price}")
                    
            except Exception as e:
                logger.error(f"Error updating order from WebSocket callback: {e}")
    
    def execute_buy_order(
        self,
        product_id: str,
        balances: Dict[str, Decimal],
        product_details: Dict,
        signal_metadata: Dict
    ):
        """
        Execute a buy order with full risk management and order preview.
        
        Args:
            product_id: Product to buy
            balances: Current balances
            product_details: Product trading rules
            signal_metadata: Metadata from trading signal
        """
        base_currency, quote_currency = product_id.split('-')
        
        # Check if we already have this asset
        if base_currency in balances:
            logger.info(f"Already holding {base_currency}, skipping buy")
            return
        
        # Check quote balance
        quote_balance = balances.get(quote_currency, Decimal('0'))
        if quote_balance <= 0:
            logger.warning(f"No {quote_currency} balance to buy {product_id}")
            return
        
        # Get total equity
        total_equity = self._get_total_equity(balances)
        if total_equity <= 0:
            logger.warning("Cannot calculate total equity")
            return
        
        # Get entry price with best bid/ask analysis
        bid_ask = self.api.get_best_bid_ask([product_id])
        
        if bid_ask and product_id in bid_ask:
            best_ask = bid_ask[product_id]['best_ask']
            spread = bid_ask[product_id]['spread']
            spread_pct = bid_ask[product_id]['spread_pct']
            
            # Check if spread is reasonable
            max_spread_pct = 0.5  # 0.5% max spread
            if spread_pct and spread_pct > max_spread_pct:
                logger.warning(f"Spread too wide ({spread_pct:.2f}% > {max_spread_pct}%), skipping entry")
                return
            
            # Place limit order slightly better than best ask (try to earn maker rebate)
            tick_size = Decimal('0.01')  # Adjust based on product
            entry_price = best_ask - tick_size if best_ask else self.api.get_latest_price(product_id)
            
            logger.info(f"Spread analysis: Best Ask=${best_ask}, Spread={spread_pct:.3f}%, Entry=${entry_price}")
        else:
            # Fallback to latest price if bid/ask not available
            entry_price = self.api.get_latest_price(product_id)
            if not entry_price:
                logger.warning(f"No price available for {product_id}")
                return
        
        # Analyze volume flow for confirmation
        volume_flow = self.api.analyze_volume_flow(product_id, lookback_trades=100)
        buy_pressure = volume_flow.get('buy_pressure', 0.5)
        net_pressure = volume_flow.get('net_pressure', 'neutral')
        
        logger.info(f"Volume flow: {buy_pressure:.1%} buy pressure ({net_pressure})")
        
        # Require moderate buy pressure for entry
        if buy_pressure < 0.45:
            logger.warning(f"Insufficient buy pressure ({buy_pressure:.1%}), skipping entry")
            return
        
        # Calculate stop loss and take profit
        stop_loss, take_profit = self.risk_manager.calculate_stop_loss_take_profit(
            entry_price, side='BUY'
        )
        
        # Calculate position size
        product_info = product_details.get(product_id, {})
        min_size = product_info.get('base_min_size', Decimal('0'))
        
        position_size, sizing_metadata = self.risk_manager.calculate_position_size(
            total_equity, entry_price, stop_loss, min_size
        )
        
        if position_size <= 0:
            logger.warning(f"Position size calculation failed: {sizing_metadata}")
            return
        
        # Check if we can open this position
        open_positions = self.db.get_open_positions()
        current_exposure = Decimal('0')
        
        for pos in open_positions:
            try:
                size = Decimal(str(pos['base_size']))
                price = Decimal(str(pos.get('current_price', pos['entry_price'])))
                current_exposure += (size * price) / total_equity
            except Exception as e:
                logger.error(f"Error calculating exposure: {e}")
        
        position_value = position_size * entry_price
        can_open, reason = self.risk_manager.can_open_position(
            len(open_positions), current_exposure, total_equity, position_value
        )
        
        if not can_open:
            logger.warning(f"Cannot open position: {reason}")
            return
        
        # Preview the order first
        logger.info(f"Previewing order for {product_id}...")
        preview = self.api.preview_order(
            product_id=product_id,
            side='BUY',
            size=position_size
        )
        
        if not preview:
            logger.error("Order preview failed - aborting trade")
            return
        
        # Check fees and slippage
        max_fee_percent = self.config.get('risk_management.max_fee_percent', Decimal('1.0'))
        max_slippage_percent = self.config.get('risk_management.max_slippage_percent', Decimal('0.5'))
        
        fee_percent = (preview['commission_total'] / position_value) * Decimal('100')
        slippage_percent = preview['slippage']
        
        if fee_percent > max_fee_percent:
            logger.warning(f"Fee too high: {fee_percent:.2f}% > {max_fee_percent}% - aborting trade")
            return
        
        if slippage_percent > max_slippage_percent:
            logger.warning(f"Slippage too high: {slippage_percent:.2f}% > {max_slippage_percent}% - aborting trade")
            return
        
        # Use preview's average price for more accurate entry
        actual_entry_price = preview['average_filled_price']
        actual_size = preview['base_size']
        
        # Execute order
        logger.info("=" * 60)
        logger.info(f"EXECUTING BUY ORDER: {product_id}")
        logger.info(f"Size: {actual_size} | Entry: {actual_entry_price}")
        logger.info(f"Fee: ${preview['commission_total']:.4f} ({fee_percent:.2f}%)")
        logger.info(f"Slippage: {slippage_percent:.2f}%")
        logger.info(f"Stop Loss: {stop_loss} | Take Profit: {take_profit}")
        logger.info(f"Position Value: ${position_value:.2f}")
        logger.info("=" * 60)
        
        if self.paper_trading:
            # Paper trading: Simulate limit order with post-only
            order_id = f"PAPER_LIMIT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{product_id}"
            
            # Save to database with preview data
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'BUY',
                'order_type': 'limit_gtc_post_only',
                'status': 'filled',
                'base_size': actual_size,
                'entry_price': actual_entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'metadata': {
                    'signal': signal_metadata,
                    'sizing': sizing_metadata,
                    'preview': {
                        'commission': float(preview['commission_total']),
                        'slippage': float(slippage_percent),
                        'fee_percent': float(fee_percent)
                    },
                    'volume_flow': {
                        'buy_pressure': float(buy_pressure),
                        'net_pressure': net_pressure
                    },
                    'spread_analysis': {
                        'spread_pct': spread_pct if 'spread_pct' in locals() else None
                    },
                    'paper_trade': True,
                    'post_only': True  # Flag that this earns maker rebates
                }
            })
            
            # Open position with preview data
            self.db.insert_position({
                'product_id': product_id,
                'base_size': actual_size,
                'entry_price': actual_entry_price,
                'current_price': actual_entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'entry_order_id': order_id,
                'metadata': {
                    'strategy': self.strategy.name,
                    'signal': signal_metadata,
                    'fees_paid': float(preview['commission_total']),
                    'bracket_order': True  # Simulated bracket order
                }
            })
            
            # Start WebSocket for this product to monitor in real-time
            try:
                open_positions = self.db.get_open_positions()
                position_products = [p['product_id'] for p in open_positions]
                if position_products and not hasattr(self.api, 'websocket_running'):
                    # Paper trading: ticker only
                    self.api.start_websocket(position_products, enable_user_channel=False)
                    logger.info(f"WebSocket started for {len(position_products)} open positions")
                elif position_products:
                    # WebSocket already running, just log
                    logger.debug(f"Monitoring {len(position_products)} positions via WebSocket")
            except Exception as e:
                logger.warning(f"Could not start WebSocket: {e}")
            
            logger.info(f"[PAPER] Limit order (post-only) simulated: {order_id}")
            
        else:
            # Live trading: Place limit order with post-only for maker rebates
            logger.info("Placing live limit order with post-only (earning maker rebates)...")
            
            limit_order = self.api.place_limit_order_gtc(
                product_id=product_id,
                side='BUY',
                price=entry_price,
                size=actual_size,
                post_only=True  # CRITICAL: Ensures maker order (earns rebates)
            )
            
            if not limit_order:
                logger.error("Failed to place limit order")
                return
            
            order_id = limit_order['order_id']
            
            # Monitor order for fill (wait up to 30 seconds)
            logger.info(f"Monitoring limit order {order_id} for fill...")
            import time
            filled = False
            for i in range(30):
                time.sleep(1)
                order_status = self.api.get_order_status(order_id)
                if order_status and order_status['status'] in ['FILLED', 'CANCELLED', 'EXPIRED']:
                    filled = order_status['status'] == 'FILLED'
                    logger.info(f"Order {order_id} status: {order_status['status']}")
                    break
            
            if not filled:
                logger.warning(f"Limit order not filled within 30s - consider adjusting price")
                # Could implement price adjustment logic here
                return
            
            # Get actual fill details
            fills = self.api.get_fills(order_id=order_id)
            actual_fill_price = entry_price
            actual_commission = Decimal('0')
            
            if fills:
                # Calculate average fill price and total commission
                total_size = sum(f['size'] for f in fills)
                weighted_price = sum(f['price'] * f['size'] for f in fills)
                actual_fill_price = weighted_price / total_size if total_size > 0 else entry_price
                actual_commission = sum(f['commission'] for f in fills)
                
                # Log maker/taker status
                maker_count = sum(1 for f in fills if f.get('liquidity_indicator') == 'MAKER')
                logger.info(f"Fill details: {maker_count}/{len(fills)} fills were MAKER (earning rebates)")
            
            # Save to database
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'BUY',
                'order_type': 'limit_gtc_post_only',
                'status': 'filled',
                'base_size': actual_size,
                'entry_price': actual_fill_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'metadata': {
                    'signal': signal_metadata,
                    'sizing': sizing_metadata,
                    'preview': {
                        'commission': float(preview['commission_total']),
                        'slippage': float(slippage_percent),
                        'fee_percent': float(fee_percent)
                    },
                    'actual_fills': {
                        'commission': float(actual_commission),
                        'avg_price': float(actual_fill_price),
                        'num_fills': len(fills) if fills else 0
                    },
                    'live_trade': True,
                    'post_only': True
                }
            })
            
            # Now create stop-loss and take-profit orders
            logger.info(f"Creating stop-loss order at ${stop_loss}...")
            stop_order = self.api.create_stop_limit_order(
                product_id=product_id,
                side='SELL',
                base_size=actual_size,
                limit_price=stop_loss * Decimal('0.99'),  # Limit slightly below stop
                stop_price=stop_loss
            )
            
            logger.info(f"Creating take-profit order at ${take_profit}...")
            tp_order = self.api.place_limit_order_gtc(
                product_id=product_id,
                side='SELL',
                price=take_profit,
                size=actual_size,
                post_only=False  # Take profit can be taker
            )
            
            # Open position with actual fill price
            self.db.insert_position({
                'product_id': product_id,
                'base_size': actual_size,
                'entry_price': actual_fill_price,
                'current_price': actual_fill_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'entry_order_id': order_id,
                'metadata': {
                    'strategy': self.strategy.name,
                    'signal': signal_metadata,
                    'fees_paid': float(actual_commission),
                    'stop_order_id': stop_order['order_id'] if stop_order else None,
                    'tp_order_id': tp_order['order_id'] if tp_order else None,
                    'post_only_entry': True
                }
            })
            
            # Start WebSocket to monitor (with user channel for live trading)
            try:
                open_positions = self.db.get_open_positions()
                position_products = [p['product_id'] for p in open_positions]
                if position_products and not hasattr(self.api, 'websocket_running'):
                    # Live trading: enable user channel for real-time order updates
                    self.api.start_websocket(position_products, enable_user_channel=True)
                    logger.info(f"WebSocket started with user channel for {len(position_products)} open positions")
            except Exception as e:
                logger.warning(f"Could not start WebSocket: {e}")
            
            logger.info(f"[LIVE] Bracket order created: {order_id}")
    
    def execute_sell_order(
        self,
        product_id: str,
        position: Dict,
        exit_reason: str = 'signal'
    ):
        """
        Execute a sell order.
        
        Args:
            product_id: Product to sell
            position: Position data
            exit_reason: Reason for exit
        """
        base_currency = product_id.split('-')[0]
        
        position_size = Decimal(str(position['base_size']))
        entry_price = Decimal(str(position['entry_price']))
        
        # Get current price
        current_price = self.api.get_latest_price(product_id)
        if not current_price:
            logger.warning(f"No price available for {product_id}")
            return
        
        # Calculate PnL
        pnl = (current_price - entry_price) * position_size
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
        
        logger.info("=" * 60)
        logger.info(f"EXECUTING SELL ORDER: {product_id}")
        logger.info(f"Size: {position_size} | Exit Price: {current_price}")
        logger.info(f"Entry: {entry_price} | PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
        logger.info(f"Exit Reason: {exit_reason}")
        logger.info("=" * 60)
        
        if self.paper_trading:
            order_id = f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S')}_{product_id}_SELL"
            
            # Save sell order
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'SELL',
                'order_type': 'market',
                'status': 'filled',
                'base_size': position_size,
                'filled_price': current_price,
                'metadata': {
                    'exit_reason': exit_reason,
                    'paper_trade': True
                }
            })
            
            # Close position
            self.db.close_position(product_id, float(current_price), float(pnl))
            
            # Record trade history
            entry_time = position.get('opened_at')
            exit_time = datetime.utcnow().isoformat()
            
            holding_time = None
            if entry_time:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                    holding_time = int((exit_dt - entry_dt).total_seconds())
                except:
                    pass
            
            self.db.insert_trade_history({
                'product_id': product_id,
                'side': 'BUY',  # Original side
                'entry_price': entry_price,
                'exit_price': current_price,
                'size': position_size,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'entry_time': entry_time or datetime.utcnow().isoformat(),
                'exit_time': exit_time,
                'holding_time_seconds': holding_time,
                'strategy': self.strategy.name,
                'exit_reason': exit_reason
            })
            
            logger.info(f"[PAPER] SELL order executed: {order_id}")
        else:
            # Live trading
            logger.critical("LIVE TRADING NOT YET IMPLEMENTED")
            pass
    
    def _analyze_current_holdings(self, balances: Dict[str, Decimal]):
        """
        Analyze current crypto holdings to determine if they should be held or sold (OPTIMIZED).
        Uses parallel processing for faster analysis.
        
        Args:
            balances: Current account balances
        """
        crypto_holdings = []
        
        # Identify crypto assets (not USD/USDC)
        for asset, balance in balances.items():
            if asset not in ['USD', 'USDC'] and balance > 0:
                # Get current price
                price = self.api.get_latest_price(f"{asset}-USD")
                if not price:
                    price = self.api.get_latest_price(f"{asset}-USDC")
                
                if price:
                    usd_value = balance * price
                    crypto_holdings.append({
                        'asset': asset,
                        'balance': balance,
                        'usd_value': usd_value,
                        'price': price
                    })
        
        if not crypto_holdings:
            logger.info("No crypto holdings to analyze")
            return
        
        logger.info(f"Analyzing {len(crypto_holdings)} current holdings in parallel...")
        
        granularity = self.config.get('trading.candle_granularity', 'FIFTEEN_MINUTE')
        periods = self.config.get('trading.candle_periods_for_analysis', 200)
        min_sell_confidence = self.config.get('trading.min_signal_confidence', 0.5)
        
        def analyze_holding(holding):
            """Analyze a single holding."""
            asset = holding['asset']
            product_id = f"{asset}-USD"
            
            try:
                df = self.api.get_historical_data(product_id, granularity, periods)
                
                if df.empty or len(df) < 50:
                    logger.debug(f"Insufficient data for {product_id}")
                    return None
                
                signal = self.strategy.analyze(df, product_id)
                
                return {
                    'asset': asset,
                    'product_id': product_id,
                    'signal': signal.action,
                    'confidence': signal.confidence,
                    'usd_value': holding['usd_value'],
                    'metadata': signal.metadata
                }
            
            except Exception as e:
                logger.debug(f"Error analyzing holding {product_id}: {e}")
                return None
        
        # OPTIMIZATION: Analyze holdings in parallel
        holding_signals = []
        max_workers = self.config.get('trading.max_holdings_workers', 3)
        max_workers = min(max_workers, len(crypto_holdings))  # Don't exceed number of holdings
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze_holding, h): h for h in crypto_holdings}
            
            for future in as_completed(futures):
                if shutdown_requested:
                    logger.info("Shutdown requested, stopping holdings analysis...")
                    break
                
                result = future.result()
                if result:
                    holding_signals.append(result)
                    
                    # Log the signal
                    if result['signal'] == 'SELL' and result['confidence'] >= min_sell_confidence:
                        logger.warning(f"[SELL] {result['asset']}: SELL signal (confidence: {result['confidence']:.2f}) - Value: ${result['usd_value']:.2f}")
                        reasons = result['metadata'].get('reasons', [])
                        if reasons:
                            logger.warning(f"   Reasons: {', '.join(reasons)}")
                    elif result['signal'] == 'BUY':
                        logger.info(f"[BUY/HOLD] {result['asset']}: BUY/HOLD signal (confidence: {result['confidence']:.2f}) - Value: ${result['usd_value']:.2f}")
                    else:
                        logger.info(f"[HOLD] {result['asset']}: HOLD (no strong signal) - Value: ${result['usd_value']:.2f}")
        
        # Summary
        should_sell = [h for h in holding_signals if h['signal'] == 'SELL' and h['confidence'] >= min_sell_confidence]
        
        if should_sell:
            logger.warning(f"WARNING: {len(should_sell)} holdings have SELL signals:")
            for h in should_sell:
                logger.warning(f"   - {h['asset']}: ${h['usd_value']:.2f} (confidence: {h['confidence']:.1%})")
    
    def _scan_all_products(self):
        """
        Scan all tradable products for opportunities (OPTIMIZED).
        Uses parallel processing and caching for faster scanning.
        
        Returns:
            List of opportunities sorted by confidence
        """
        opportunities = []
        
        try:
            # Get all available products with tradability status
            products_response = self.api.rest_client.get_products(get_tradability_status=True)
            all_products = []
            
            if hasattr(products_response, 'products'):
                for product in products_response.products:
                    # Skip view-only products
                    if hasattr(product, 'view_only') and product.view_only:
                        continue
                    
                    # Filter for USD/USDC and tradable products
                    if (product.quote_currency_id in ['USD', 'USDC'] and 
                        not product.is_disabled and 
                        product.status == 'online' and
                        product.trading_disabled == False):
                        all_products.append(product.product_id)
            
            logger.info(f"Scanning {len(all_products)} tradable products in parallel...")
            
            granularity = self.config.get('trading.candle_granularity', 'FIFTEEN_MINUTE')
            periods = self.config.get('trading.candle_periods_for_analysis', 200)
            min_confidence = self.config.get('trading.min_signal_confidence', 0.5)
            
            # OPTIMIZATION: Use parallel processing with ThreadPoolExecutor
            # Scan products in batches to avoid overwhelming the API
            max_workers = self.config.get('trading.max_scan_workers', 10)
            max_workers = min(max_workers, len(all_products))  # Don't exceed number of products
            
            def analyze_product_quick(product_id):
                """Quick product analysis for scanning."""
                try:
                    # Get historical data
                    df = self.api.get_historical_data(product_id, granularity, periods)
                    
                    if df.empty or len(df) < 50:
                        logger.info(f"[SCAN] {product_id:15s} - Insufficient data (< 50 candles)")
                        return None
                    
                    # Add indicators first so we can display them
                    df = self.strategy.add_indicators(df)
                    
                    # Get signal
                    signal = self.strategy.analyze(df, product_id)
                    latest_price = df['Close'].iloc[-1]
                    
                    # Extract key indicators for display (check what columns actually exist)
                    adx = None
                    rsi = None
                    
                    # Try to find ADX column
                    adx_cols = [col for col in df.columns if 'ADX' in col]
                    if adx_cols:
                        adx = df[adx_cols[0]].iloc[-1]
                    
                    # Try to find RSI column
                    rsi_cols = [col for col in df.columns if 'RSI' in col]
                    if rsi_cols:
                        rsi = df[rsi_cols[0]].iloc[-1]
                    
                    # Build indicator string
                    indicators = ""
                    if adx is not None and rsi is not None:
                        indicators = f"ADX:{adx:5.1f} RSI:{rsi:5.1f}"
                    elif adx is not None:
                        indicators = f"ADX:{adx:5.1f}"
                    elif rsi is not None:
                        indicators = f"RSI:{rsi:5.1f}"
                    
                    # Log each product scan with details
                    if signal.action == 'BUY':
                        confidence_pct = f"{signal.confidence:.1%}"
                        reason = getattr(signal, 'reason', signal.metadata.get('reason', ''))
                        logger.info(f"[SCAN] {product_id:15s} - BUY {confidence_pct:>6s} @ ${latest_price:>10.4f} | {indicators} | {reason}")
                    elif signal.action == 'SELL':
                        reason = getattr(signal, 'reason', signal.metadata.get('reason', ''))
                        logger.info(f"[SCAN] {product_id:15s} - SELL      @ ${latest_price:>10.4f} | {indicators} | {reason}")
                    else:
                        # For HOLD, show indicators
                        logger.info(f"[SCAN] {product_id:15s} - HOLD      @ ${latest_price:>10.4f} | {indicators}")
                    
                    # Only return BUY signals above minimum confidence
                    if signal.action == 'BUY' and signal.confidence >= min_confidence:
                        return {
                            'product_id': product_id,
                            'signal': signal.action,
                            'confidence': signal.confidence,
                            'price': latest_price,
                            'metadata': signal.metadata
                        }
                    
                except Exception as e:
                    logger.warning(f"[SCAN] {product_id:15s} - Error: {e}")
                    
                return None
            
            # Process products in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(analyze_product_quick, product_id): product_id 
                          for product_id in all_products}
                
                completed = 0
                for future in as_completed(futures):
                    if shutdown_requested:
                        logger.info("Shutdown requested, stopping scan...")
                        break
                    
                    completed += 1
                    if completed % 25 == 0:  # Progress update every 25 products
                        logger.info(f"Scanned {completed}/{len(all_products)} products...")
                    
                    result = future.result()
                    if result:
                        opportunities.append(result)
            
            # Sort by confidence
            opportunities.sort(key=lambda x: x['confidence'], reverse=True)
            
            logger.info(f"Scan complete: Found {len(opportunities)} opportunities above {min_confidence:.0%} confidence")
            
        except Exception as e:
            logger.error(f"Error in product scan: {e}", exc_info=True)
        
        return opportunities
    
    def run(self):
        """Main trading loop."""
        global shutdown_requested
        
        # Get portfolio ID
        self.portfolio_id = self.api.get_portfolio_id()
        if not self.portfolio_id:
            logger.error("Could not get portfolio ID. Exiting.")
            return
        
        # Get initial balances and set initial equity
        initial_balances = self.api.get_account_balances(
            self.portfolio_id,
            self.risk_manager.min_usd_trade_value
        )
        self.initial_equity = self._get_total_equity(initial_balances)
        self.risk_manager.peak_equity = self.initial_equity
        
        logger.info(f"Initial Equity: ${self.initial_equity:.2f}")
        
        # WebSocket will be started dynamically when positions are opened
        # This keeps the bot lightweight during scanning and only monitors active positions
        logger.info("WebSocket will be enabled for open positions")
        
        # Main loop
        loop_sleep = self.config.get('trading.loop_sleep_seconds', 60)
        max_products_analyze = self.config.get('trading.max_products_to_analyze', 20)
        
        logger.info("Starting main trading loop...")
        logger.info("Press Ctrl+C to stop")
        
        cycle_count = 0
        last_fee_check = datetime.now(UTC).date()
        
        while not shutdown_requested:
            try:
                cycle_count += 1
                logger.info("")
                logger.info("=" * 80)
                logger.info(f"TRADING CYCLE #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("=" * 80)
                
                # Check daily fees (once per day)
                current_date = datetime.now(UTC).date()
                if current_date > last_fee_check:
                    logger.info("Checking daily fee summary...")
                    fee_summary = self.api.get_transaction_summary(self.portfolio_id)
                    if fee_summary:
                        logger.info(f"Today's Fees: ${fee_summary['total_fees']:.2f}, "
                                   f"Volume: ${fee_summary['total_volume']:.2f}")
                    last_fee_check = current_date
                
                # Get current balances
                balances = self.api.get_account_balances(
                    self.portfolio_id,
                    self.risk_manager.min_usd_trade_value
                )
                
                if not balances:
                    logger.warning("No balances found. Waiting...")
                    time.sleep(loop_sleep)
                    continue
                
                # Calculate current equity
                current_equity = self._get_total_equity(balances)
                logger.info(f"Current Equity: ${current_equity:.2f}")
                
                # Check drawdown
                if self.risk_manager.check_drawdown(current_equity):
                    logger.critical("MAXIMUM DRAWDOWN EXCEEDED - Trading halted!")
                    time.sleep(loop_sleep)
                    continue
                
                # Get open positions and check stop loss/take profit
                open_positions = self.db.get_open_positions()
                logger.info(f"Open Positions: {len(open_positions)}")
                
                for position in open_positions:
                    product_id = position['product_id']
                    current_price = self.api.get_latest_price(product_id)
                    
                    if current_price:
                        # Update position price
                        self.db.update_position(product_id, current_price=float(current_price))
                        
                        # Check if should close
                        should_close, reason = self.risk_manager.should_close_position(
                            position, current_price
                        )
                        
                        if should_close:
                            logger.info(f"Closing position {product_id}: {reason}")
                            self.execute_sell_order(product_id, position, reason)
                        
                        # Update trailing stop if enabled
                        elif self.risk_manager.use_trailing_stop:
                            new_stop = self.risk_manager.update_trailing_stop(
                                position, current_price
                            )
                            if new_stop:
                                self.db.update_position(product_id, stop_loss=float(new_stop))
                
                # Run full market scan every cycle
                logger.info("=" * 80)
                logger.info("RUNNING FULL MARKET SCAN FOR BEST OPPORTUNITIES")
                logger.info("=" * 80)
                
                best_opportunities = []
                
                try:
                    # First, analyze current holdings
                    self._analyze_current_holdings(balances)
                    
                    # Then scan all products for new opportunities
                    best_opportunities = self._scan_all_products()
                    if best_opportunities:
                        logger.info(f"Found {len(best_opportunities)} strong opportunities:")
                        for opp in best_opportunities[:5]:  # Show top 5
                            logger.info(f"  {opp['product_id']}: {opp['signal']} (confidence: {opp['confidence']:.2f})")
                    else:
                        logger.info("No strong BUY opportunities found at this time.")
                except Exception as e:
                    logger.error(f"Error during full market scan: {e}")
                
                # Use the best opportunities for trading analysis
                if best_opportunities:
                    # Get product details for top opportunities
                    top_products = [opp['product_id'] for opp in best_opportunities[:10]]
                    product_details = self.api.get_product_details(top_products)
                    
                    logger.info(f"Analyzing top {len(top_products)} opportunities for potential trades...")
                    
                    # Parallel analysis of top opportunities
                    with ThreadPoolExecutor(max_workers=3) as executor:
                        futures = {}
                        
                        for opp in best_opportunities[:10]:
                            product_id = opp['product_id']
                            future = executor.submit(
                                self._analyze_product,
                                product_id,
                                balances,
                                product_details
                            )
                            futures[future] = product_id
                        
                        # Process results
                        for future in as_completed(futures):
                            if shutdown_requested:
                                break
                            
                            try:
                                result = future.result()
                                if result:
                                    # A trade was executed, break to restart cycle
                                    logger.info("Trade executed, restarting cycle...")
                                    break
                            except Exception as e:
                                logger.error(f"Error in analysis: {e}", exc_info=True)
                else:
                    logger.info("No opportunities to analyze for trades.")
                
                # Save performance snapshot every N cycles
                if cycle_count % 10 == 0:
                    self._save_performance_snapshot(current_equity)
                
                # Save equity curve
                cash = sum(balances.get(asset, Decimal('0')) 
                          for asset in ['USD', 'USDC'])
                positions_value = current_equity - cash
                self.db.insert_equity_snapshot(
                    float(current_equity),
                    float(cash),
                    float(positions_value)
                )
                
                logger.info(f"Cycle complete. Sleeping {loop_sleep}s...")
                time.sleep(loop_sleep)
                
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(loop_sleep)
        
        # Cleanup
        self._shutdown()
    
    def _analyze_product(
        self,
        product_id: str,
        balances: Dict,
        product_details: Dict
    ) -> bool:
        """
        Analyze a single product for trading signals.
        
        Returns:
            True if a trade was executed
        """
        try:
            # Get historical data
            granularity = self.config.get('trading.candle_granularity', 'FIVE_MINUTE')
            periods = self.config.get('trading.candle_periods_for_analysis', 100)
            
            df = self.api.get_historical_data(product_id, granularity, periods)
            
            if df.empty:
                return False
            
            # Get trading signal
            signal = self.strategy.analyze(df, product_id)
            
            if signal.action == 'HOLD':
                return False
            
            # Check minimum confidence threshold
            min_confidence = self.config.get('trading.min_signal_confidence', 0.5)
            
            logger.info(f"Signal for {product_id}: {signal.action} (confidence: {signal.confidence:.2f})")
            
            if signal.confidence < min_confidence:
                logger.info(f"Signal confidence {signal.confidence:.2f} below threshold {min_confidence:.2f}, skipping")
                return False
            
            # Execute based on signal
            if signal.action == 'BUY':
                base_currency = product_id.split('-')[0]
                
                # Check if we already have a position
                existing_position = self.db.get_position(product_id)
                if existing_position:
                    logger.info(f"Already have position in {product_id}")
                    return False
                
                if base_currency not in balances:
                    self.execute_buy_order(
                        product_id,
                        balances,
                        product_details,
                        signal.metadata
                    )
                    return True
                else:
                    logger.info(f"Already holding {base_currency}, skipping buy")
            
            elif signal.action == 'SELL':
                # Check if we have a position
                position = self.db.get_position(product_id)
                if position:
                    self.execute_sell_order(product_id, position, 'signal')
                    return True
                else:
                    logger.info(f"No position in {product_id} to sell")
            
            return False
            
        except Exception as e:
            logger.error(f"Error analyzing {product_id}: {e}", exc_info=True)
            return False
    
    def _save_performance_snapshot(self, current_equity: Decimal):
        """Save performance metrics snapshot."""
        try:
            # Get trade statistics
            stats = self.db.get_trade_statistics(days=30)
            
            # Get equity curve
            equity_data = self.db.get_equity_curve(days=30)
            equity_curve = [row['equity'] for row in equity_data]
            
            # Get open positions
            open_positions = self.db.get_open_positions()
            
            # Calculate portfolio metrics
            portfolio_metrics = self.risk_manager.calculate_portfolio_metrics(
                current_equity, open_positions
            )
            
            # Save to database
            metrics = {
                'total_equity': float(current_equity),
                'available_balance': float(current_equity - Decimal(str(portfolio_metrics['positions_value']))),
                'total_positions_value': portfolio_metrics['positions_value'],
                'total_pnl': stats.get('total_pnl', 0),
                'win_rate': stats.get('win_rate', 0),
                'num_trades': stats.get('total_trades', 0),
                'num_wins': stats.get('wins', 0),
                'num_losses': stats.get('losses', 0)
            }
            
            self.db.insert_performance_metrics(metrics)
            logger.info("Performance snapshot saved")
            
        except Exception as e:
            logger.error(f"Error saving performance snapshot: {e}")
    
    def _shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down trading bot...")
        
        # Close API connections
        if self.api:
            self.api.close()
        
        # Close database
        if self.db:
            self.db.close()
        
        logger.info("Shutdown complete")


def main():
    """Main entry point."""
    print("=" * 80)
    print("COINBASE ALGORITHMIC CRYPTO TRADING BOT")
    print("=" * 80)
    print()
    print("DISCLAIMER: This trading bot is for educational purposes only.")
    print("It is NOT financial advice. Trading cryptocurrency involves significant risk.")
    print("Use this software at your own risk.")
    print()
    print("=" * 80)
    print()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run bot
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
