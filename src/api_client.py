"""
Coinbase API wrapper and market data management.
"""

import time
import json
import logging
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Dict, List, Optional
from threading import Thread, Lock

import pandas as pd
from coinbase.rest import RESTClient
from coinbase.websocket import WSClient

logger = logging.getLogger(__name__)


class CoinbaseAPI:
    """Wrapper for Coinbase API interactions."""
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Coinbase API client.
        
        Args:
            api_key: Coinbase API key
            api_secret: Coinbase API secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Initialize clients
        self.rest_client = None
        self.ws_client = None
        self.user_ws_client = None  # For user channel (order updates)
        
        # Latest prices from WebSocket
        self.latest_prices = {}
        
        # Order updates from user channel
        self.order_updates = {}
        self.order_update_callbacks = []
        
        # Level 2 order book data
        self.order_books = {}
        
        # Rate limiting to prevent HTTP 429 errors
        self._rate_limit_lock = Lock()
        self._last_request_time = 0
        self._min_request_interval = 0.2  # 200ms between requests (~5 req/sec max)
        
        # Initialize REST client
        self._initialize_rest_client()
    
    def _initialize_rest_client(self):
        """Initialize REST API client."""
        try:
            self.rest_client = RESTClient(
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            logger.info("REST client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing REST client: {e}")
            raise
    
    def _rate_limit(self):
        """Enforce rate limiting between API requests."""
        with self._rate_limit_lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            
            if time_since_last < self._min_request_interval:
                sleep_time = self._min_request_interval - time_since_last
                time.sleep(sleep_time)
            
            self._last_request_time = time.time()
    
    def _initialize_ws_client(self):
        """Initialize WebSocket client."""
        try:
            self.ws_client = WSClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                on_message=self._on_websocket_message
            )
            logger.info("WebSocket client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing WebSocket client: {e}")
            raise
    
    def _on_websocket_message(self, msg):
        """Handle incoming WebSocket messages."""
        try:
            msg_data = json.loads(msg)
            
            # Handle ticker channel (price updates)
            if msg_data.get('channel') == 'ticker' and 'events' in msg_data:
                for event in msg_data['events']:
                    for ticker in event.get('tickers', []):
                        product_id = ticker.get('product_id')
                        price = ticker.get('price')
                        
                        if product_id and price:
                            self.latest_prices[product_id] = Decimal(str(price))
            
            # Handle ticker_batch channel (efficient multi-product price updates)
            elif msg_data.get('channel') == 'ticker_batch' and 'events' in msg_data:
                for event in msg_data['events']:
                    for ticker in event.get('tickers', []):
                        product_id = ticker.get('product_id')
                        price = ticker.get('price')
                        
                        if product_id and price:
                            self.latest_prices[product_id] = Decimal(str(price))
            
            # Handle user channel (order updates)
            elif msg_data.get('channel') == 'user' and 'events' in msg_data:
                for event in msg_data['events']:
                    for order in event.get('orders', []):
                        order_id = order.get('order_id')
                        if order_id:
                            # Store update
                            self.order_updates[order_id] = {
                                'order_id': order_id,
                                'product_id': order.get('product_id'),
                                'side': order.get('order_side'),
                                'status': order.get('status'),
                                'filled_size': Decimal(str(order.get('filled_size', 0))),
                                'average_price': Decimal(str(order.get('average_filled_price', 0))),
                                'timestamp': datetime.now(UTC).isoformat()
                            }
                            
                            # Call registered callbacks
                            for callback in self.order_update_callbacks:
                                try:
                                    callback(self.order_updates[order_id])
                                except Exception as e:
                                    logger.error(f"Error in order update callback: {e}")
                            
                            logger.info(f"Order update: {order_id} - {order.get('status')}")
            
            # Handle level2 channel (full order book)
            elif msg_data.get('channel') == 'level2' and 'events' in msg_data:
                for event in msg_data['events']:
                    product_id = event.get('product_id')
                    if product_id:
                        # Update order book
                        if product_id not in self.order_books:
                            self.order_books[product_id] = {
                                'bids': [],
                                'asks': [],
                                'last_update': None
                            }
                        
                        # Process snapshot or update
                        if event.get('type') == 'snapshot':
                            self.order_books[product_id]['bids'] = [
                                {'price': Decimal(str(bid['price'])), 'size': Decimal(str(bid['size']))}
                                for bid in event.get('updates', []) if bid.get('side') == 'bid'
                            ]
                            self.order_books[product_id]['asks'] = [
                                {'price': Decimal(str(ask['price'])), 'size': Decimal(str(ask['size']))}
                                for ask in event.get('updates', []) if ask.get('side') == 'offer'
                            ]
                        else:
                            # Apply incremental updates
                            for update in event.get('updates', []):
                                price = Decimal(str(update.get('price', 0)))
                                size = Decimal(str(update.get('size', 0)))
                                side = update.get('side')
                                
                                book_side = self.order_books[product_id]['bids'] if side == 'bid' else self.order_books[product_id]['asks']
                                
                                # Remove if size is 0, otherwise update/add
                                if size == 0:
                                    book_side[:] = [level for level in book_side if level['price'] != price]
                                else:
                                    # Find and update or append
                                    found = False
                                    for level in book_side:
                                        if level['price'] == price:
                                            level['size'] = size
                                            found = True
                                            break
                                    if not found:
                                        book_side.append({'price': price, 'size': size})
                                        # Sort: bids descending, asks ascending
                                        book_side.sort(key=lambda x: x['price'], reverse=(side == 'bid'))
                        
                        self.order_books[product_id]['last_update'] = datetime.now(UTC).isoformat()
                            
        except json.JSONDecodeError:
            logger.warning(f"Could not decode WebSocket message: {msg}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    def start_websocket(self, product_ids: List[str], enable_user_channel: bool = False):
        """
        Start WebSocket connection in background thread.
        
        Args:
            product_ids: List of product IDs to subscribe to
            enable_user_channel: Whether to enable user channel for order updates
        """
        if not product_ids:
            logger.warning("No products to subscribe to")
            return
        
        self._initialize_ws_client()
        
        def run_ws():
            try:
                self.ws_client.open()
                
                # Subscribe to ticker channel for prices
                self.ws_client.subscribe(product_ids=product_ids, channels=["ticker"])
                logger.info(f"Subscribed to ticker for {len(product_ids)} products")
                
                # Subscribe to user channel for order updates if enabled
                if enable_user_channel:
                    self.ws_client.subscribe(product_ids=product_ids, channels=["user"])
                    logger.info(f"Subscribed to user channel for real-time order updates")
                
                self.ws_client.run_forever_with_exception_check()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                if self.ws_client:
                    self.ws_client.close()
        
        ws_thread = Thread(target=run_ws, name="WebSocketThread", daemon=True)
        ws_thread.start()
        logger.info("WebSocket thread started")
        
        # Wait for initial connection
        time.sleep(3)
    
    def register_order_update_callback(self, callback):
        """
        Register a callback function for order updates.
        
        Args:
            callback: Function to call when order updates are received.
                      Should accept a dict with order details.
        """
        self.order_update_callbacks.append(callback)
        logger.info(f"Registered order update callback: {callback.__name__}")
    
    def get_order_update(self, order_id: str) -> Optional[Dict]:
        """
        Get latest order update from WebSocket.
        
        Args:
            order_id: Order ID to get update for
            
        Returns:
            Latest order update or None
        """
        return self.order_updates.get(order_id)
    
    def subscribe_level2(self, product_ids: List[str]):
        """
        Subscribe to Level 2 order book data.
        
        Args:
            product_ids: Products to subscribe to
        """
        if not self.ws_client:
            logger.warning("WebSocket not initialized, cannot subscribe to level2")
            return
        
        try:
            self.ws_client.subscribe(product_ids=product_ids, channels=["level2"])
            logger.info(f"Subscribed to level2 order book for {len(product_ids)} products")
        except Exception as e:
            logger.error(f"Error subscribing to level2: {e}")
    
    def get_order_book(self, product_id: str, depth: int = 10) -> Optional[Dict]:
        """
        Get Level 2 order book for a product.
        
        Args:
            product_id: Product to get order book for
            depth: Number of levels to return (default 10)
            
        Returns:
            Order book with bids and asks
        """
        if product_id not in self.order_books:
            logger.debug(f"No order book data for {product_id}")
            return None
        
        book = self.order_books[product_id]
        
        return {
            'product_id': product_id,
            'bids': book['bids'][:depth],
            'asks': book['asks'][:depth],
            'spread': book['asks'][0]['price'] - book['bids'][0]['price'] if book['bids'] and book['asks'] else Decimal('0'),
            'mid_price': (book['asks'][0]['price'] + book['bids'][0]['price']) / Decimal('2') if book['bids'] and book['asks'] else Decimal('0'),
            'last_update': book['last_update']
        }
    
    def get_market_depth(self, product_id: str) -> Optional[Dict]:
        """
        Analyze market depth (liquidity) from order book.
        
        Args:
            product_id: Product to analyze
            
        Returns:
            Market depth metrics
        """
        book = self.get_order_book(product_id, depth=50)
        
        if not book or not book['bids'] or not book['asks']:
            return None
        
        # Calculate total liquidity within 1% of mid price
        mid_price = book['mid_price']
        threshold = mid_price * Decimal('0.01')  # 1%
        
        bid_depth = sum(
            level['size'] * level['price']
            for level in book['bids']
            if mid_price - level['price'] <= threshold
        )
        
        ask_depth = sum(
            level['size'] * level['price']
            for level in book['asks']
            if level['price'] - mid_price <= threshold
        )
        
        return {
            'product_id': product_id,
            'mid_price': mid_price,
            'spread': book['spread'],
            'spread_bps': (book['spread'] / mid_price) * Decimal('10000'),  # Basis points
            'bid_depth_1pct': bid_depth,
            'ask_depth_1pct': ask_depth,
            'total_depth_1pct': bid_depth + ask_depth,
            'imbalance': (bid_depth - ask_depth) / (bid_depth + ask_depth) if (bid_depth + ask_depth) > 0 else Decimal('0')
        }
    
    def get_portfolio_id(self) -> Optional[str]:
        """Get the default portfolio ID."""
        try:
            response = self.rest_client.get_portfolios()
            if response.portfolios and len(response.portfolios) > 0:
                portfolio_id = response.portfolios[0].uuid
                logger.info(f"Retrieved portfolio ID: {portfolio_id}")
                return portfolio_id
            else:
                logger.error("No portfolios found")
                return None
        except Exception as e:
            logger.error(f"Error getting portfolio ID: {e}")
            return None
    
    def get_all_portfolios(self) -> List[Dict]:
        """
        Get all portfolios for the account.
        
        Returns:
            List of portfolio details
        """
        try:
            response = self.rest_client.get_portfolios()
            
            portfolios = []
            if response.portfolios:
                for portfolio in response.portfolios:
                    portfolios.append({
                        'uuid': portfolio.uuid,
                        'name': getattr(portfolio, 'name', 'Default'),
                        'type': getattr(portfolio, 'type', 'DEFAULT'),
                        'deleted': getattr(portfolio, 'deleted', False)
                    })
            
            logger.info(f"Retrieved {len(portfolios)} portfolios")
            return portfolios
            
        except Exception as e:
            logger.error(f"Error getting portfolios: {e}")
            return []
    
    def create_portfolio(self, name: str) -> Optional[str]:
        """
        Create a new portfolio.
        
        Args:
            name: Portfolio name
            
        Returns:
            Portfolio UUID if successful
        """
        try:
            response = self.rest_client.create_portfolio(name=name)
            
            if response and hasattr(response, 'portfolio'):
                portfolio_id = response.portfolio.uuid
                logger.info(f"Created portfolio: {name} ({portfolio_id})")
                return portfolio_id
            
            logger.error(f"Failed to create portfolio: {name}")
            return None
            
        except Exception as e:
            logger.error(f"Error creating portfolio: {e}")
            return None
    
    def get_account_balances(
        self,
        portfolio_id: str,
        min_usd_equivalent: Decimal = Decimal('5')
    ) -> Dict[str, Decimal]:
        """
        Get account balances with filtering.
        
        Args:
            portfolio_id: Portfolio UUID
            min_usd_equivalent: Minimum USD value to include
            
        Returns:
            Dictionary of {asset: balance}
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            breakdown = self.rest_client.get_portfolio_breakdown(
                portfolio_uuid=portfolio_id
            )
            
            balances = {}
            
            if breakdown and breakdown.breakdown and breakdown.breakdown.spot_positions:
                for asset in breakdown.breakdown.spot_positions:
                    try:
                        balance = Decimal(str(asset.total_balance_crypto))
                        balance_usd = Decimal(str(getattr(asset, "total_balance_fiat", 0) or 0))
                        
                        if balance > Decimal('1e-8') and balance_usd >= min_usd_equivalent:
                            balances[asset.asset] = balance
                    except Exception as e:
                        logger.debug(f"Error processing asset: {e}")
                        continue
            
            logger.info(f"Retrieved {len(balances)} balances (>= ${min_usd_equivalent})")
            return balances
            
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            return {}
    
    def find_tradable_products(
        self,
        balances: Dict[str, Decimal]
    ) -> List[str]:
        """
        Find tradable products based on current balances.
        
        Args:
            balances: Dictionary of current balances
            
        Returns:
            List of tradable product IDs
        """
        tradable = []
        portfolio_assets = set(balances.keys())
        
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            response = self.rest_client.get_products()
            all_products = response.products
            
            for product in all_products:
                # Can trade if we hold the quote currency
                if (product.quote_currency_id in portfolio_assets and
                    product.base_currency_id != product.quote_currency_id and
                    product.status == 'online' and
                    not product.trading_disabled):
                    tradable.append(product.product_id)
            
            logger.info(f"Found {len(tradable)} tradable products")
            return tradable
            
        except Exception as e:
            logger.error(f"Error finding tradable products: {e}")
            return []
    
    def get_product_details(self, product_ids: List[str]) -> Dict[str, Dict]:
        """
        Get trading rules for products.
        
        Args:
            product_ids: List of product IDs
            
        Returns:
            Dictionary of product details
        """
        details = {}
        
        for product_id in product_ids:
            try:
                # Apply rate limiting before API call
                self._rate_limit()
                
                product_info = self.rest_client.get_product(product_id=product_id)
                
                # Extract minimum sizes with fallbacks
                base_min_size = Decimal('0')
                min_market_funds = Decimal('0')
                
                for attr in ['base_min_size', 'base_minimum_size', 'min_base_size']:
                    val = getattr(product_info, attr, None)
                    if val:
                        base_min_size = Decimal(str(val))
                        break
                
                for attr in ['min_market_funds', 'min_quote_size', 'min_market_size']:
                    val = getattr(product_info, attr, None)
                    if val:
                        min_market_funds = Decimal(str(val))
                        break
                
                details[product_id] = {
                    'base_min_size': base_min_size,
                    'min_market_funds': min_market_funds
                }
                
            except Exception as e:
                logger.error(f"Error getting details for {product_id}: {e}")
                details[product_id] = {
                    'base_min_size': Decimal('0'),
                    'min_market_funds': Decimal('0')
                }
        
        return details
    
    def get_historical_data(
        self,
        product_id: str,
        granularity: str,
        periods: int
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        
        Args:
            product_id: Product ID to fetch data for
            granularity: Candle granularity (e.g., 'FIVE_MINUTE')
            periods: Number of periods to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        granularity_map = {
            'ONE_MINUTE': timedelta(minutes=1),
            'FIVE_MINUTE': timedelta(minutes=5),
            'FIFTEEN_MINUTE': timedelta(minutes=15),
            'THIRTY_MINUTE': timedelta(minutes=30),
            'ONE_HOUR': timedelta(hours=1),
            'TWO_HOUR': timedelta(hours=2),
            'SIX_HOUR': timedelta(hours=6),
            'ONE_DAY': timedelta(days=1)
        }
        
        delta = granularity_map.get(granularity)
        if not delta:
            logger.error(f"Unsupported granularity: {granularity}")
            return pd.DataFrame()
        
        # Limit to API maximum
        periods = min(periods, 300)
        
        end_time = datetime.now(UTC)
        start_time = end_time - (delta * periods)
        
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            candles_data = self.rest_client.get_candles(
                product_id=product_id,
                start=str(int(start_time.timestamp())),
                end=str(int(end_time.timestamp())),
                granularity=granularity
            )
            
            if not hasattr(candles_data, 'candles') or not candles_data.candles:
                logger.warning(f"No candle data for {product_id}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            data = []
            for candle in candles_data.candles:
                data.append({
                    'start': candle.start,
                    'Open': float(candle.open),
                    'High': float(candle.high),
                    'Low': float(candle.low),
                    'Close': float(candle.close),
                    'Volume': float(candle.volume)
                })
            
            df = pd.DataFrame(data)
            
            if df.empty:
                return df
            
            # Convert Unix timestamps to datetime (fix for FutureWarning)
            df['time'] = pd.to_datetime(df['start'].astype(int), unit='s')
            df.set_index('time', inplace=True)
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {product_id}: {e}")
            return pd.DataFrame()
    
    def get_latest_price(self, product_id: str) -> Optional[Decimal]:
        """
        Get latest price for a product.
        
        Args:
            product_id: Product ID
            
        Returns:
            Latest price or None
        """
        # Try WebSocket price first
        if product_id in self.latest_prices:
            return self.latest_prices[product_id]
        
        # Fallback to REST API
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            product = self.rest_client.get_product(product_id=product_id)
            price = getattr(product, 'price', None)
            if price:
                return Decimal(str(price))
        except Exception as e:
            logger.error(f"Error getting price for {product_id}: {e}")
        
        return None
    
    def preview_order(
        self,
        product_id: str,
        side: str,
        size: Decimal
    ) -> Optional[Dict]:
        """
        Preview an order without executing it.
        
        Args:
            product_id: Product to trade
            side: BUY or SELL
            size: Order size
            
        Returns:
            Order preview details including fees and expected price
        """
        try:
            response = self.rest_client.preview_market_order(
                product_id=product_id,
                side=side,
                quote_size=str(size) if side == "BUY" else None,
                base_size=str(size) if side == "SELL" else None
            )
            
            if not response:
                logger.warning(f"No preview response for {side} {product_id}")
                return None
            
            # Extract preview details
            preview = {
                'product_id': product_id,
                'side': side,
                'base_size': Decimal(str(getattr(response, 'base_size', 0))),
                'quote_size': Decimal(str(getattr(response, 'quote_size', 0))),
                'commission_total': Decimal(str(getattr(response, 'commission_total', 0))),
                'slippage': Decimal(str(getattr(response, 'slippage', 0))),
                'best_bid': Decimal(str(getattr(response, 'best_bid', 0))),
                'best_ask': Decimal(str(getattr(response, 'best_ask', 0))),
                'average_filled_price': Decimal(str(getattr(response, 'average_filled_price', 0))),
                'order_total': Decimal(str(getattr(response, 'order_total', 0)))
            }
            
            logger.info(f"Order preview: {side} {size} {product_id} - "
                       f"Fee: ${preview['commission_total']:.4f}, "
                       f"Slippage: {preview['slippage']:.4f}%")
            
            return preview
            
        except Exception as e:
            logger.error(f"Error previewing order: {e}")
            return None
    
    def get_transaction_summary(
        self,
        portfolio_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        """
        Get transaction summary including fees paid.
        
        Args:
            portfolio_id: Portfolio UUID
            start_date: Start date for summary (defaults to today)
            end_date: End date for summary (defaults to now)
            
        Returns:
            Transaction summary with fee totals
        """
        try:
            # Default to today if not specified
            if not start_date:
                start_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            if not end_date:
                end_date = datetime.now(UTC)
            
            response = self.rest_client.get_transaction_summary(
                account_uuid=portfolio_id,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat()
            )
            
            if not response:
                return None
            
            summary = {
                'total_volume': Decimal(str(getattr(response, 'total_volume', 0))),
                'total_fees': Decimal(str(getattr(response, 'total_fees', 0))),
                'fee_tier': getattr(response, 'fee_tier', {}),
                'margin_rate': getattr(response, 'margin_rate', {}),
                'goods_and_services_tax': getattr(response, 'goods_and_services_tax', {}),
                'advanced_trade_only_volume': Decimal(str(getattr(response, 'advanced_trade_only_volume', 0))),
                'advanced_trade_only_fees': Decimal(str(getattr(response, 'advanced_trade_only_fees', 0))),
                'coinbase_pro_volume': Decimal(str(getattr(response, 'coinbase_pro_volume', 0))),
                'coinbase_pro_fees': Decimal(str(getattr(response, 'coinbase_pro_fees', 0)))
            }
            
            logger.info(f"Transaction summary - Total fees: ${summary['total_fees']:.2f}, "
                       f"Volume: ${summary['total_volume']:.2f}")
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting transaction summary: {e}")
            return None
    
    def check_api_permissions(self) -> Dict[str, bool]:
        """
        Check API key permissions.
        
        Returns:
            Dictionary of permission status
        """
        try:
            response = self.rest_client.get_api_key_permissions()
            
            if not response:
                logger.warning("No permissions response received")
                return {}
            
            permissions = {
                'can_view': getattr(response, 'can_view', False),
                'can_trade': getattr(response, 'can_trade', False),
                'can_transfer': getattr(response, 'can_transfer', False),
                'portfolio_uuid': getattr(response, 'portfolio_uuid', None),
                'portfolio_type': getattr(response, 'portfolio_type', None)
            }
            
            logger.info(f"API Permissions - View: {permissions['can_view']}, "
                       f"Trade: {permissions['can_trade']}, "
                       f"Transfer: {permissions['can_transfer']}")
            
            return permissions
            
        except Exception as e:
            logger.error(f"Error checking API permissions: {e}")
            return {}
    
    def create_stop_limit_order(
        self,
        product_id: str,
        side: str,
        base_size: Decimal,
        limit_price: Decimal,
        stop_price: Decimal
    ) -> Optional[Dict]:
        """
        Create a stop-limit order (executes at exchange level, not locally).
        
        Args:
            product_id: Product to trade
            side: BUY or SELL
            base_size: Order size
            limit_price: Limit price to execute at
            stop_price: Stop price to trigger order
            
        Returns:
            Order details if successful
        """
        try:
            response = self.rest_client.stop_limit_order_gtc(
                client_order_id=f"stop_limit_{datetime.now(UTC).timestamp()}",
                product_id=product_id,
                side=side,
                base_size=str(base_size),
                limit_price=str(limit_price),
                stop_price=str(stop_price),
                stop_direction="STOP_DIRECTION_STOP_DOWN" if side == "SELL" else "STOP_DIRECTION_STOP_UP"
            )
            
            if not response:
                logger.error(f"No response from stop-limit order for {product_id}")
                return None
            
            order = {
                'order_id': getattr(response, 'order_id', None),
                'product_id': product_id,
                'side': side,
                'type': 'stop_limit',
                'base_size': base_size,
                'limit_price': limit_price,
                'stop_price': stop_price,
                'status': getattr(response, 'status', None)
            }
            
            logger.info(f"Stop-limit order created: {side} {base_size} {product_id} @ "
                       f"stop=${stop_price}, limit=${limit_price}")
            
            return order
            
        except Exception as e:
            logger.error(f"Error creating stop-limit order: {e}")
            return None
    
    def create_bracket_order(
        self,
        product_id: str,
        side: str,
        base_size: Decimal,
        limit_price: Decimal,
        stop_loss_price: Decimal,
        take_profit_price: Decimal
    ) -> Optional[Dict]:
        """
        Create a bracket order (entry + simultaneous stop-loss and take-profit).
        
        Args:
            product_id: Product to trade
            side: BUY or SELL
            base_size: Order size
            limit_price: Entry limit price
            stop_loss_price: Stop loss price
            take_profit_price: Take profit price
            
        Returns:
            Order details if successful
        """
        try:
            response = self.rest_client.trigger_bracket_order_gtc(
                client_order_id=f"bracket_{datetime.now(UTC).timestamp()}",
                product_id=product_id,
                side=side,
                base_size=str(base_size),
                limit_price=str(limit_price),
                stop_trigger_price=str(stop_loss_price),
                take_profit_limit_price=str(take_profit_price)
            )
            
            if not response:
                logger.error(f"No response from bracket order for {product_id}")
                return None
            
            order = {
                'order_id': getattr(response, 'order_id', None),
                'product_id': product_id,
                'side': side,
                'type': 'bracket',
                'base_size': base_size,
                'limit_price': limit_price,
                'stop_loss_price': stop_loss_price,
                'take_profit_price': take_profit_price,
                'status': getattr(response, 'status', None)
            }
            
            logger.info(f"Bracket order created: {side} {base_size} {product_id} @ ${limit_price} "
                       f"[SL: ${stop_loss_price}, TP: ${take_profit_price}]")
            
            return order
            
        except Exception as e:
            logger.error(f"Error creating bracket order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        try:
            response = self.rest_client.cancel_orders(order_ids=[order_id])
            
            if response and hasattr(response, 'results'):
                for result in response.results:
                    if result.success:
                        logger.info(f"Order {order_id} cancelled successfully")
                        return True
            
            logger.warning(f"Failed to cancel order {order_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
        Get order status.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Order details
        """
        try:
            response = self.rest_client.get_order(order_id=order_id)
            
            if not response:
                return None
            
            order = {
                'order_id': order_id,
                'product_id': getattr(response, 'product_id', None),
                'side': getattr(response, 'side', None),
                'status': getattr(response, 'status', None),
                'filled_size': Decimal(str(getattr(response, 'filled_size', 0))),
                'average_filled_price': Decimal(str(getattr(response, 'average_filled_price', 0))),
                'type': getattr(response, 'order_type', None)
            }
            
            return order
            
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return None
    
    def close(self):
        """Close API connections."""
        if self.ws_client:
            try:
                self.ws_client.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
        
        if self.user_ws_client:
            try:
                self.user_ws_client.close()
                logger.info("User WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing user WebSocket: {e}")
