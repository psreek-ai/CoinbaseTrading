
import sys
import time
import logging
import signal as signal_module
import json
from pathlib import Path
from decimal import Decimal
from datetime import datetime, UTC
from typing import Dict, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config
from database import DatabaseManager
from api_client import CoinbaseAPI
from strategies import StrategyFactory
from risk_management import RiskManager
from analytics import PerformanceAnalytics
from trade_executor import TradeExecutor
from market_scanner import MarketScanner

class TradingBot:
    
    def __init__(self, config_path: str = None):
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
        
        # Initialize new components
        self.trade_executor = TradeExecutor(
            self.api,
            self.db,
            self.risk_manager,
            self.config.get('trading.paper_trading_mode', True),
            self.config.get('strategies.active_strategy')
        )
        self.market_scanner = MarketScanner(
            self.api,
            self.strategy,
            self.config
        )

        # Bot state
        self.portfolio_id = None
        self.paper_trading = self.config.get('trading.paper_trading_mode', True)
        
        # Track initial equity for performance calculation
        self.initial_equity = Decimal('0')
        
        # Register order update callback
        self.api.register_order_update_callback(self._on_order_update)
        
        logger.info(f"Paper Trading Mode: {self.paper_trading}")
        logger.info(f"Active Strategy: {self.config.get('strategies.active_strategy')}")
        
        # Shutdown event
        self._shutdown_event = Event()

    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received. Cleaning up...")
        self._shutdown_event.set()

    def _setup_logging(self):
        """Configure logging."""
        global logger
        
        log_level = getattr(logging, self.config.get('logging.level', 'INFO'))
        log_dir = Path(self.config.get('logging.log_directory', 'logs'))
        log_dir.mkdir(exist_ok=True)
        
        # Use same timestamp for all log files in this session
        self.log_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f"trading_bot_{self.log_timestamp}.log"
        
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
        
        # Enable API response logging if configured
        if self.config.get('logging.log_api_responses', False):
            # Use same timestamp as main log file
            log_dir = Path(self.config.get('logging.log_directory', 'logs'))
            log_file = log_dir / f"api_responses_{self.log_timestamp}.log"
            errors_only = self.config.get('logging.log_api_errors_only', False)
            api.enable_api_logging(log_file=str(log_file), errors_only=errors_only)
        
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
    
    def _auto_convert_holdings(self, sell_signals: List[Dict], hold_signals: List[Dict], buy_opportunities: List[Dict]):
        """
        Automatically convert holdings into BUY opportunities.
        - SELL signals: Always convert (weak holdings)
        - HOLD signals: Convert only if BUY confidence is significantly higher (e.g., 20% better)
        
        Uses Coinbase Convert API for direct crypto-to-crypto conversion.
        
        Args:
            sell_signals: List of holdings with SELL signals
            hold_signals: List of holdings with HOLD signals
            buy_opportunities: List of BUY opportunities from market scan
        """
        if not buy_opportunities:
            return
        
        if not sell_signals and not hold_signals:
            return
        
        # Sort sell signals by confidence (strongest sell first - priority conversions)
        sell_signals.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Sort hold signals by confidence (weakest hold first - easier to justify conversion)
        hold_signals.sort(key=lambda x: x.get('confidence', 0), reverse=False)
        
        # Sort buy opportunities by confidence (strongest buy first)
        buy_opportunities.sort(key=lambda x: x['confidence'], reverse=True)
        
        logger.info("\n" + "=" * 80)
        logger.info("AUTO-CONVERSION ANALYSIS")
        logger.info("=" * 80)
        
        if sell_signals:
            logger.info("Assets with SELL signals (priority conversions):")
            for s in sell_signals:
                logger.info(f"  - {s['asset']:10s}: ${s['usd_value']:>10.2f} (confidence: {s['confidence']:.1%})")
        
        if hold_signals:
            logger.info("\nAssets with HOLD signals (convert if BUY is much stronger):")
            for h in hold_signals:
                logger.info(f"  - {h['asset']:10s}: ${h['usd_value']:>10.2f} (confidence: {h.get('confidence', 0):.1%})")
        
        logger.info("\nTop BUY opportunities:")
        for b in buy_opportunities[:5]:
            product_id = b['product_id']
            target_asset = product_id.split('-')[0]  # Extract base currency (e.g., 'BTC' from 'BTC-USD')
            logger.info(f"  - {target_asset:10s}: {product_id} (confidence: {b['confidence']:.1%})")
        
        logger.info("=" * 80 + "\n")
        
        # Conversion threshold: HOLD signals require BUY to be 20% more confident
        confidence_threshold = 0.20
        
        # Convert each holding into the top BUY opportunities
        conversions_made = 0
        buy_index = 0
        
        # Process SELL signals first (priority)
        for sell in sell_signals:
            if buy_index >= len(buy_opportunities):
                logger.info(f"All BUY opportunities used, stopping conversions")
                break
            
            from_asset = sell['asset']
            from_balance = sell.get('balance', Decimal('0'))
            
            # Skip if balance is 0 or invalid
            if from_balance <= 0:
                logger.warning(f"Skipping {from_asset}: zero or invalid balance ({from_balance})")
                continue
            
            # Get the next BUY opportunity
            buy_opp = buy_opportunities[buy_index]
            product_id = buy_opp['product_id']
            to_asset = product_id.split('-')[0]  # Extract base currency
            
            # Skip if trying to convert to same asset
            if from_asset == to_asset:
                logger.info(f"Skipping conversion: {from_asset} to {to_asset} (same asset)")
                buy_index += 1
                continue
            
            logger.info(f"[CONVERT SELL] {from_asset} -> {to_asset}")
            logger.info(f"   Selling: {from_asset} (${sell['usd_value']:.2f}, SELL confidence: {sell['confidence']:.1%})")
            logger.info(f"   Buying: {to_asset} (BUY confidence: {buy_opp['confidence']:.1%})")
            
            # Market sell to USDC to provide buying power
            try:
                logger.info(f"Market selling {from_asset} to USDC for buying power")
                
                # Determine the product ID (ETH-USDC, BTC-USDC, etc.)
                sell_product_id = f"{from_asset}-USDC"
                
                # Place market sell order directly via API
                sell_result = self.api.place_market_order(
                    product_id=sell_product_id,
                    side='SELL',
                    size=float(from_balance)
                )
                
                if sell_result and sell_result.get('success'):
                    logger.info(f"[SUCCESS] Market sold {from_asset} for USDC")
                    logger.info(f"   Order ID: {sell_result.get('order_id')}")
                    logger.info(f"   Bot will use this USDC to buy {to_asset} in trading cycle")
                    
                    conversions_made += 1
                    buy_index += 1
                    
                    # Log to trade history
                    self._log_trade_history({
                        'timestamp': datetime.now(UTC).isoformat(),
                        'action': 'MARKET_SELL_TO_USDC',
                        'product_id': sell_product_id,
                        'from_asset': from_asset,
                        'amount': str(from_balance),
                        'sell_confidence': sell['confidence'],
                        'reason': f'Convert SELL to USDC for buying {to_asset}',
                        'order_id': sell_result.get('order_id', 'N/A')
                    })
                    
                    # Rate limiting between orders
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"[FAILED] Could not market sell {from_asset} to USDC")
                    
            except Exception as e:
                logger.error(f"[ERROR] Market sell error {from_asset} -> USDC: {e}")
            
            # Rate limiting between conversions
            time.sleep(1)
            buy_index += 1
        
        # Process HOLD signals - only convert if BUY confidence is significantly better
        logger.info("\n--- Processing HOLD signals (require 20% better BUY confidence) ---\n")
        
        for hold in hold_signals:
            if buy_index >= len(buy_opportunities):
                logger.info(f"All BUY opportunities used, stopping conversions")
                break
            
            from_asset = hold['asset']
            from_balance = hold.get('balance', Decimal('0'))
            hold_confidence = hold.get('confidence', 0)
            
            # Skip if balance is 0 or invalid
            if from_balance <= 0:
                logger.warning(f"Skipping {from_asset}: zero or invalid balance ({from_balance})")
                continue
            
            # Get the next BUY opportunity
            buy_opp = buy_opportunities[buy_index]
            product_id = buy_opp['product_id']
            to_asset = product_id.split('-')[0]
            buy_confidence = buy_opp['confidence']
            
            # Skip if trying to convert to same asset
            if from_asset == to_asset:
                logger.info(f"Skipping conversion: {from_asset} to {to_asset} (same asset)")
                buy_index += 1
                continue
            
            # Check if BUY is significantly better than HOLD
            confidence_diff = buy_confidence - hold_confidence
            
            if confidence_diff < confidence_threshold:
                logger.info(f"[SKIP HOLD] {from_asset} (conf: {hold_confidence:.1%}) -> {to_asset} (conf: {buy_confidence:.1%})")
                logger.info(f"   Reason: BUY not strong enough (diff: {confidence_diff:.1%}, need: {confidence_threshold:.1%})")
                buy_index += 1
                continue
            
            logger.info(f"[CONVERT HOLD] {from_asset} -> {to_asset}")
            logger.info(f"   From: {from_asset} (${hold['usd_value']:.2f}, HOLD confidence: {hold_confidence:.1%})")
            logger.info(f"   To: {to_asset} (BUY confidence: {buy_confidence:.1%})")
            logger.info(f"   Improvement: {confidence_diff:.1%}")
            
            # Market sell to USDC to provide buying power
            try:
                logger.info(f"Market selling {from_asset} to USDC for buying power")
                
                sell_product_id = f"{from_asset}-USDC"
                
                sell_result = self.api.place_market_order(
                    product_id=sell_product_id,
                    side='SELL',
                    size=float(from_balance)
                )
                
                if sell_result and sell_result.get('success'):
                    logger.info(f"[SUCCESS] Market sold {from_asset} for USDC")
                    logger.info(f"   Order ID: {sell_result.get('order_id')}")
                    logger.info(f"   Bot will use this USDC to buy {to_asset} in trading cycle")
                    
                    conversions_made += 1
                    
                    self._log_trade_history({
                        'timestamp': datetime.now(UTC).isoformat(),
                        'action': 'MARKET_SELL_HOLD_TO_USDC',
                        'product_id': sell_product_id,
                        'from_asset': from_asset,
                        'amount': str(from_balance),
                        'hold_confidence': hold_confidence,
                        'buy_confidence': buy_confidence,
                        'confidence_improvement': confidence_diff,
                        'reason': f'Convert HOLD to USDC for buying {to_asset}',
                        'order_id': sell_result.get('order_id', 'N/A')
                    })
                else:
                    logger.error(f"[FAILED] Could not market sell {from_asset} to USDC")
                    
            except Exception as e:
                logger.error(f"[ERROR] Conversion error {from_asset} -> {to_asset}: {e}")
            
            # Rate limiting between conversions
            time.sleep(1)
            buy_index += 1
        
        if conversions_made > 0:
            logger.info("\n" + "=" * 80)
            logger.info(f"[COMPLETE] AUTO-CONVERSION: {conversions_made} conversions executed")
            logger.info("=" * 80 + "\n")
    
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
                        logger.debug(f"[SCAN] {product_id:15s} - Insufficient data (< 50 candles)")
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
                        # For HOLD, use debug level
                        logger.debug(f"[SCAN] {product_id:15s} - HOLD      @ ${latest_price:>10.4f} | {indicators}")
                    
                    # Return ALL BUY signals (both above and below threshold) for tracking
                    if signal.action == 'BUY':
                        return {
                            'product_id': product_id,
                            'signal': signal.action,
                            'confidence': signal.confidence,
                            'price': latest_price,
                            'metadata': signal.metadata,
                            'above_threshold': signal.confidence >= min_confidence
                        }
                    
                except Exception as e:
                    logger.warning(f"[SCAN] {product_id:15s} - Error: {e}")
                    
                return None
            
            # Process products in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(analyze_product_quick, product_id): product_id 
                          for product_id in all_products}
                
                completed = 0
                all_buy_signals = []  # Track ALL BUY signals for top 3 logging
                
                for future in as_completed(futures):
                    if self._shutdown_event.is_set():
                        logger.info("Shutdown requested, stopping scan...")
                        break
                    
                    completed += 1
                    if completed % 25 == 0:  # Progress update every 25 products
                        logger.info(f"Scanned {completed}/{len(all_products)} products...")
                    
                    result = future.result()
                    if result:
                        all_buy_signals.append(result)
                        if result['above_threshold']:
                            opportunities.append(result)
            
            # Sort all BUY signals by confidence
            all_buy_signals.sort(key=lambda x: x['confidence'], reverse=True)
            self._top_buy_signals = all_buy_signals[:3]  # Store top 3 for logging
            
            logger.debug(f"Total BUY signals found: {len(all_buy_signals)}")
            
            # Sort opportunities (above threshold) by confidence
            opportunities.sort(key=lambda x: x['confidence'], reverse=True)
            
            logger.info(f"Scan complete: Found {len(opportunities)} opportunities above {min_confidence:.0%} confidence")
            if len(all_buy_signals) > 0:
                logger.info(f"(Total BUY signals including below threshold: {len(all_buy_signals)})")
            
        except Exception as e:
            logger.error(f"Error in product scan: {e}", exc_info=True)
        
        return opportunities
    
    def _check_open_orders(self):
        """
        Check status of all open/submitted orders and handle fills, cancellations, expirations.
        This is the persistent order manager that runs in the main loop.
        """
        try:
            # Get all submitted/open orders from database
            cursor = self.db.conn.cursor()
            cursor.execute("""
                SELECT client_order_id, product_id, side, base_size, entry_price, 
                       stop_loss, take_profit, metadata, created_at
                FROM orders 
                WHERE status IN ('submitted', 'open', 'pending')
                ORDER BY created_at ASC
            """)
            
            open_orders = cursor.fetchall()
            
            if not open_orders:
                return  # No orders to check
            
            logger.debug(f"Checking status of {len(open_orders)} open orders...")
            
            for order_row in open_orders:
                order_id = order_row[0]
                product_id = order_row[1]
                side = order_row[2]
                base_size = Decimal(str(order_row[3]))
                entry_price = Decimal(str(order_row[4]))
                stop_loss = Decimal(str(order_row[5])) if order_row[5] else None
                take_profit = Decimal(str(order_row[6])) if order_row[6] else None
                metadata = json.loads(order_row[7]) if order_row[7] else {}
                created_at = order_row[8]
                
                # Check if order has timed out (5 minutes for limit orders)
                try:
                    created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    age_seconds = (datetime.now(UTC) - created_time).total_seconds()
                    
                    if age_seconds > 300:  # 5 minutes timeout
                        logger.warning(f"Order {order_id} has timed out ({age_seconds:.0f}s) - cancelling")
                        
                        try:
                            cancel_result = self.api.cancel_order(order_id)
                            if cancel_result:
                                logger.info(f"Cancelled timed-out order: {order_id}")
                                cursor = self.db.conn.cursor()
                                cursor.execute(
                                    "UPDATE orders SET status = 'cancelled', metadata = json_set(metadata, '$.timeout_cancelled', ?) WHERE client_order_id = ?",
                                    (datetime.utcnow().isoformat(), order_id)
                                )
                                self.db.conn.commit()
                        except Exception as e:
                            logger.error(f"Failed to cancel timed-out order {order_id}: {e}")
                        
                        continue
                except Exception as e:
                    logger.debug(f"Could not parse order timestamp: {e}")
                
                # Query API for current order status
                try:
                    order_status = self.api.get_order_status(order_id)
                    
                    if not order_status:
                        logger.warning(f"Could not get status for order {order_id}")
                        continue
                    
                    api_status = order_status['status']
                    
                    # Handle different statuses
                    if api_status == 'FILLED':
                        logger.info(f"Order {order_id} ({side} {product_id}) has FILLED!")
                        
                        # Get fill details
                        fills = self.api.get_fills(order_id=order_id)
                        actual_fill_price = entry_price
                        actual_commission = Decimal('0')
                        
                        if fills:
                            total_size = sum(Decimal(str(f['size'])) for f in fills)
                            weighted_price = sum(Decimal(str(f['price'])) * Decimal(str(f['size'])) for f in fills)
                            actual_fill_price = weighted_price / total_size if total_size > 0 else entry_price
                            actual_commission = sum(Decimal(str(f['commission'])) for f in fills)
                        
                        # Update order in database
                        cursor = self.db.conn.cursor()
                        cursor.execute(
                            """UPDATE orders SET status = 'filled', filled_price = ?, 
                               metadata = json_set(metadata, '$.filled_at', ?, '$.actual_commission', ?) 
                               WHERE client_order_id = ?""",
                            (float(actual_fill_price), datetime.utcnow().isoformat(), float(actual_commission), order_id)
                        )
                        self.db.conn.commit()
                        
                        # If this was a BUY order, create the position and bracket orders
                        if side == 'BUY':
                            logger.info(f"Creating position for {product_id}...")
                            
                            # Create stop-loss and take-profit orders
                            stop_order = None
                            tp_order = None
                            
                            if stop_loss:
                                logger.info(f"Creating stop-loss order at ${stop_loss}...")
                                stop_order = self.api.create_stop_limit_order(
                                    product_id=product_id,
                                    side='SELL',
                                    base_size=float(base_size),
                                    limit_price=float(stop_loss * Decimal('0.99')),
                                    stop_price=float(stop_loss)
                                )
                            
                            if take_profit:
                                logger.info(f"Creating take-profit order at ${take_profit}...")
                                tp_order = self.api.place_limit_order_gtc(
                                    product_id=product_id,
                                    side='SELL',
                                    price=float(take_profit),
                                    size=float(base_size),
                                    post_only=False
                                )
                            
                            # Create position in database
                            self.db.insert_position({
                                'product_id': product_id,
                                'base_size': base_size,
                                'entry_price': actual_fill_price,
                                'current_price': actual_fill_price,
                                'stop_loss': stop_loss,
                                'take_profit': take_profit,
                                'entry_order_id': order_id,
                                'metadata': {
                                    **metadata,
                                    'fees_paid': float(actual_commission),
                                    'stop_order_id': stop_order['order_id'] if stop_order else None,
                                    'tp_order_id': tp_order['order_id'] if tp_order else None
                                }
                            })
                            
                            logger.info(f"Position opened for {product_id} at ${actual_fill_price}")
                        
                        # --- REFACTORED SELL FILL HANDLING ---
                        elif side == 'SELL':
                            logger.info(f"[LIVE] Exit order {order_id} FILLED for {product_id} at ${actual_fill_price}")
                            
                            # Find the corresponding open position in the database
                            position = self.db.get_position(product_id)
                            
                            if not position:
                                logger.warning(f"Got a SELL fill for {order_id}, but no open position found in DB for {product_id}")
                                continue
                            
                            # 1. Determine Exit Reason & PnL
                            entry_price = Decimal(str(position['entry_price']))
                            position_size = Decimal(str(position['base_size']))
                            pnl = (actual_fill_price - entry_price) * position_size
                            pnl_percent = ((actual_fill_price - entry_price) / entry_price) * 100
                            
                            position_metadata = position.get('metadata', {})
                            if isinstance(position_metadata, str):
                                position_metadata = json.loads(position_metadata)
                            
                            exit_reason = 'unknown_exit'
                            if order_id == position_metadata.get('stop_order_id'):
                                exit_reason = 'stop_loss'
                            elif order_id == position_metadata.get('tp_order_id'):
                                exit_reason = 'take_profit'
                            
                            logger.info(f"[LIVE] Closing {product_id}. Reason: {exit_reason}. PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
                            
                            # 2. Close the position in the database
                            self.db.close_position(product_id, float(actual_fill_price), float(pnl))
                            
                            # 3. Record in trade history
                            entry_time = position.get('opened_at')
                            exit_time = datetime.now(UTC).isoformat()
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
                                'side': 'BUY',  # The original entry side
                                'entry_price': float(entry_price),
                                'exit_price': float(actual_fill_price),
                                'size': float(position_size),
                                'pnl': float(pnl),
                                'pnl_percent': float(pnl_percent),
                                'fees': float(actual_commission) + float(position_metadata.get('fees_paid', 0)),
                                'holding_time_seconds': holding_time,
                                'entry_time': entry_time,
                                'exit_time': exit_time,
                                'strategy': position_metadata.get('strategy', self.strategy.name),
                                'exit_reason': exit_reason,
                                'metadata': {'fill_order_id': order_id, 'live_trade': True}
                            })
                            
                            # 4. CRITICAL: Cancel the other outstanding bracket order
                            other_order_id = None
                            if exit_reason == 'stop_loss':
                                other_order_id = position_metadata.get('tp_order_id')  # SL filled, cancel TP
                            elif exit_reason == 'take_profit':
                                other_order_id = position_metadata.get('stop_order_id')  # TP filled, cancel SL
                            
                            if other_order_id:
                                logger.info(f"Cancelling other bracket order: {other_order_id}")
                                try:
                                    self.api.cancel_order(other_order_id)
                                    # Update the cancelled order in DB
                                    cursor = self.db.conn.cursor()
                                    cursor.execute(
                                        "UPDATE orders SET status = 'cancelled' WHERE client_order_id = ?",
                                        (other_order_id,)
                                    )
                                    self.db.conn.commit()
                                except Exception as e:
                                    logger.warning(f"Failed to cancel other order {other_order_id}: {e}")
                        # --- END REFACTORED SELL FILL HANDLING ---
                    
                    elif api_status in ['CANCELLED', 'EXPIRED']:
                        logger.info(f"Order {order_id} is {api_status}")
                        cursor = self.db.conn.cursor()
                        cursor.execute(
                            "UPDATE orders SET status = ? WHERE client_order_id = ?",
                            (api_status.lower(), order_id)
                        )
                        self.db.conn.commit()
                    
                    elif api_status in ['OPEN', 'PENDING']:
                        # Still waiting - update status if needed
                        cursor = self.db.conn.cursor()
                        cursor.execute(
                            "UPDATE orders SET status = ? WHERE client_order_id = ?",
                            (api_status.lower(), order_id)
                        )
                        self.db.conn.commit()
                    
                except Exception as e:
                    logger.error(f"Error checking order {order_id}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in _check_open_orders: {e}", exc_info=True)
    
    def run(self):
        # Set up signal handlers
        signal_module.signal(signal_module.SIGINT, self._signal_handler)
        signal_module.signal(signal_module.SIGTERM, self._signal_handler)
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
        
        while not self._shutdown_event.is_set():
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
                
                # CRITICAL: Check status of all open orders (persistent order management)
                logger.info("Checking open orders status...")
                self._check_open_orders()
                
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
                        # Update position price in DB for PnL tracking (all modes)
                        self.db.update_position(product_id, current_price=float(current_price))
                        
                        # --- REFACTORED EXIT LOGIC ---
                        # Paper trading MUST poll for SL/TP as it has no real exchange orders
                        if self.paper_trading:
                            # Check if should close based on polling
                            should_close, reason = self.risk_manager.should_close_position(
                                position, current_price
                            )
                            
                            if should_close:
                                logger.info(f"[PAPER] Closing position {product_id}: {reason}")
                                self.execute_sell_order(product_id, position, reason)
                            
                            # Update trailing stop if enabled
                            elif self.risk_manager.use_trailing_stop:
                                new_stop = self.risk_manager.update_trailing_stop(
                                    position, current_price
                                )
                                if new_stop:
                                    self.db.update_position(product_id, stop_loss=float(new_stop))
                        
                        # In live mode, SL/TP exits are handled by _check_open_orders()
                        # which reacts to FILLED events from exchange's native orders.
                        # This eliminates the race condition between bot polling and exchange execution.
                        # --- END REFACTORED EXIT LOGIC ---
                
                # Run full market scan every cycle
                logger.info("=" * 80)
                logger.info("RUNNING FULL MARKET SCAN FOR BEST OPPORTUNITIES")
                logger.info("=" * 80)
                
                best_opportunities = []
                
                try:
                    # Get ALL balances (low threshold to capture everything)
                    # analyze_current_holdings will filter to $10+ minimum
                    all_balances = self.api.get_account_balances(
                        self.portfolio_id,
                        min_usd_equivalent=Decimal('0.01')
                    )
                    
                    # Analyze current holdings and get SELL/HOLD signals
                    # (automatically filters to $10+ positions)
                    holding_signals = self.market_scanner.analyze_current_holdings(all_balances, self._shutdown_event)
                    
                    # Then scan all products for new opportunities
                    best_opportunities = self.market_scanner.scan_all_products(self._shutdown_event)
                    
                    # DEBUG: Log what we got
                    logger.info(f"DEBUG: holding_signals type: {type(holding_signals)}, value: {holding_signals}")
                    logger.info(f"DEBUG: best_opportunities count: {len(best_opportunities) if best_opportunities else 0}")
                    
                    # AUTO-CONVERT: If we have holdings and BUY opportunities, convert weak to strong
                    if holding_signals and best_opportunities:
                        sell_signals = holding_signals.get('sell', [])
                        hold_signals = holding_signals.get('hold', [])
                        
                        logger.info(f"DEBUG: sell_signals count: {len(sell_signals)}, hold_signals count: {len(hold_signals)}")
                        
                        if sell_signals or hold_signals:
                            logger.info("=" * 80)
                            logger.info(f"AUTO-CONVERT: {len(sell_signals)} SELL + {len(hold_signals)} HOLD assets, {len(best_opportunities)} BUY opportunities")
                            logger.info("=" * 80)
                            
                            # Convert weak holdings into strong opportunities
                            self._auto_convert_holdings(sell_signals, hold_signals, best_opportunities)
                    
                    if best_opportunities:
                        logger.info(f"Found {len(best_opportunities)} strong opportunities:")
                        for opp in best_opportunities[:5]:  # Show top 5
                            logger.info(f"  {opp['product_id']}: {opp['signal']} (confidence: {opp['confidence']:.2f})")
                    else:
                        logger.info("No strong BUY opportunities found at this time.")
                        
                        # Show top 3 candidates even though they didn't meet threshold
                        if hasattr(self, '_top_buy_signals') and self._top_buy_signals:
                            threshold = self.config.get('trading.min_signal_confidence', 0.5)
                            logger.info(f"Top {len(self._top_buy_signals)} BUY candidates (below {threshold:.0%} threshold):")
                            for i, signal in enumerate(self._top_buy_signals[:3], 1):
                                reason = signal['metadata'].get('reason', 'momentum signal')
                                logger.info(f"  #{i} {signal['product_id']:15s} @ ${signal['price']:>10.4f} | "
                                          f"Confidence: {signal['confidence']:.1%} | {reason}")
                        else:
                            logger.info("No BUY signals detected at all (market conditions unfavorable)")
                        
                except Exception as e:
                    logger.error(f"Error during full market scan: {e}")
                
                # Use the best opportunities for trading analysis
                if best_opportunities:
                    # Get product details for top opportunities
                    top_products = [opp['product_id'] for opp in best_opportunities[:10]]
                    product_details = self.api.get_product_details(top_products)
                    
                    logger.info(f"Analyzing top {len(top_products)} opportunities for potential trades...")
                    
                    # Process top opportunities sequentially to avoid race conditions
                    for opp in best_opportunities[:10]:
                        if self._shutdown_event.is_set():
                            break
                        
                        try:
                            product_id = opp['product_id']
                            signal_type = opp['signal']
                            
                            if signal_type == 'BUY':
                                # Execute buy order through TradeExecutor
                                result = self.trade_executor.execute_buy_order(
                                    product_id=product_id,
                                    balances=balances,
                                    product_details=product_details.get(product_id),
                                    signal_metadata=opp
                                )
                                
                                if result:
                                    logger.info("Trade executed, restarting cycle...")
                                    break
                        except Exception as e:
                            logger.error(f"Error executing trade for {product_id}: {e}", exc_info=True)
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
                self._shutdown_event.set()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(loop_sleep)
        
        # Cleanup
        self._shutdown()

    def _process_buy_opportunity(
        self,
        opportunity: Dict,
        balances: Dict,
        product_details: Dict
    ) -> bool:
        """
        Processes a single buy opportunity.

        Returns:
            True if a trade was executed
        """
        product_id = opportunity['product_id']
        signal_metadata = opportunity['metadata']

        base_currency = product_id.split('-')[0]

        # Check if we already have a position
        existing_position = self.db.get_position(product_id)
        if existing_position:
            logger.info(f"Already have position in {product_id}, skipping.")
            return False

        if base_currency not in balances:
            self.trade_executor.execute_buy_order(
                product_id,
                balances,
                product_details,
                signal_metadata
            )
            return True
        else:
            logger.info(f"Already holding {base_currency}, skipping buy for {product_id}")
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
    
    # Create and run bot
    try:
        bot = TradingBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
