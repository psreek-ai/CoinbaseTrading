"""
Coinbase API wrapper and market data management.
"""

import time
import json
import logging
from datetime import datetime, timedelta, UTC
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional
from threading import Thread, Lock
from pathlib import Path

import pandas as pd
from coinbase.rest import RESTClient
from coinbase.websocket import WSClient

from exceptions import (
    APIError,
    PortfolioError,
    OrderError,
    RateLimitError,
    AuthenticationError,
    InvalidRequestError,
    APINetworkError
)

logger = logging.getLogger(__name__)

# Create a separate logger for API responses
api_response_logger = logging.getLogger('api_responses')
api_response_logger.setLevel(logging.DEBUG)
api_response_logger.propagate = False  # Don't propagate to root logger


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
        self._min_request_interval = 0.2  # 200ms between requests (~5 req/sec max) - fallback
        
        # Dynamic rate limiting from Coinbase response headers
        self._rate_limit_remaining = None  # x-ratelimit-remaining
        self._rate_limit_limit = None      # x-ratelimit-limit  
        self._rate_limit_reset = None      # x-ratelimit-reset (timestamp)
        
        # API response logging configuration
        self.log_api_responses = False
        self.log_api_errors_only = False
        
        # Initialize REST client
        self._initialize_rest_client()
    
    def enable_api_logging(self, log_file: str = None, errors_only: bool = False):
        """
        Enable detailed API response logging.
        
        Args:
            log_file: Path to log file (default: logs/api_responses.log)
            errors_only: If True, only log failed API calls
        """
        self.log_api_responses = True
        self.log_api_errors_only = errors_only
        
        if log_file is None:
            log_file = "logs/api_responses.log"
        
        # Ensure logs directory exists
        Path(log_file).parent.mkdir(exist_ok=True)
        
        # Add file handler to api_response_logger if not already present
        if not api_response_logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
                # No datefmt specified - uses default format with milliseconds
            )
            handler.setFormatter(formatter)
            api_response_logger.addHandler(handler)
        
        logger.info(f"API response logging enabled: {log_file} (errors_only={errors_only})")
    
    def _log_api_call(self, method: str, endpoint: str, params: Dict = None, 
                     response: any = None, error: Exception = None):
        """
        Log API call details for debugging.
        
        Args:
            method: HTTP method or SDK method name
            endpoint: API endpoint or description
            params: Request parameters
            response: API response object
            error: Exception if call failed
        """
        if not self.log_api_responses:
            return
        
        # Skip logging if errors_only is True and there's no error
        if self.log_api_errors_only and error is None:
            return
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'method': method,
            'endpoint': endpoint,
            'params': params or {},
        }
        
        if error:
            log_entry['status'] = 'ERROR'
            log_entry['error'] = str(error)
            log_entry['error_type'] = type(error).__name__
        else:
            log_entry['status'] = 'SUCCESS'
            
            # Try to serialize response
            try:
                if response is None:
                    log_entry['response'] = None
                elif isinstance(response, (str, int, float, bool)):
                    log_entry['response'] = response
                elif isinstance(response, (dict, list)):
                    log_entry['response'] = response
                elif isinstance(response, pd.DataFrame):
                    log_entry['response'] = f"DataFrame({len(response)} rows, {len(response.columns)} cols)"
                    log_entry['response_preview'] = response.head(3).to_dict() if not response.empty else {}
                elif hasattr(response, '__dict__'):
                    # SDK response object - try to extract relevant data
                    log_entry['response_type'] = type(response).__name__
                    log_entry['response_attributes'] = {
                        k: str(v)[:200] for k, v in response.__dict__.items() 
                        if not k.startswith('_')
                    }
                else:
                    log_entry['response'] = str(response)[:500]
            except Exception as e:
                log_entry['response'] = f"<Unable to serialize: {e}>"
        
        # Log as formatted JSON
        api_response_logger.debug(json.dumps(log_entry, indent=2, default=str))
    
    def _initialize_rest_client(self):
        """Initialize REST API client with rate limit headers enabled."""
        try:
            self.rest_client = RESTClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                rate_limit_headers=True  # Enable rate limit headers in responses
            )
            logger.info("REST client initialized successfully with rate limit headers")
        except Exception as e:
            logger.error(f"Error initializing REST client: {e}")
            raise
    
    def _rate_limit(self):
        """
        Enforce adaptive rate limiting between API requests.
        Uses Coinbase response headers (x-ratelimit-remaining, x-ratelimit-reset) when available,
        falls back to static 200ms delay otherwise.
        """
        with self._rate_limit_lock:
            current_time = time.time()
            time_since_last = current_time - self._last_request_time
            
            # Calculate adaptive delay based on rate limit headers
            sleep_time = self._min_request_interval  # Default fallback
            
            if self._rate_limit_remaining is not None and self._rate_limit_reset is not None:
                # If we're running low on requests, slow down
                if self._rate_limit_remaining < 10:
                    # Calculate time until reset
                    time_until_reset = max(0, self._rate_limit_reset - current_time)
                    
                    if self._rate_limit_remaining > 0:
                        # Spread remaining requests evenly until reset
                        sleep_time = time_until_reset / self._rate_limit_remaining
                        logger.debug(f"Adaptive rate limit: {self._rate_limit_remaining} requests left, "
                                   f"sleeping {sleep_time:.3f}s")
                    else:
                        # Out of requests, wait until reset
                        sleep_time = time_until_reset + 0.1  # Small buffer
                        logger.warning(f"Rate limit exhausted, waiting {sleep_time:.1f}s until reset")
                        
                elif self._rate_limit_remaining > 100:
                    # Plenty of capacity, minimal delay
                    sleep_time = 0.05  # 50ms
                else:
                    # Moderate capacity, standard delay
                    sleep_time = self._min_request_interval
            
            # Apply rate limiting delay
            if time_since_last < sleep_time:
                actual_sleep = sleep_time - time_since_last
                time.sleep(actual_sleep)
            
            self._last_request_time = time.time()
    
    def _update_rate_limits(self, response):
        """
        Extract and update rate limit info from Coinbase API response headers.
        
        Args:
            response: API response object that may contain rate limit headers
        """
        try:
            # Check if response has headers attribute (some SDK responses do)
            if hasattr(response, '__dict__'):
                headers = getattr(response, 'headers', None) or getattr(response, '_headers', None)
                
                if headers:
                    # Extract rate limit headers (case-insensitive)
                    for key, value in headers.items():
                        key_lower = key.lower()
                        
                        if key_lower == 'x-ratelimit-remaining':
                            self._rate_limit_remaining = int(value)
                        elif key_lower == 'x-ratelimit-limit':
                            self._rate_limit_limit = int(value)
                        elif key_lower == 'x-ratelimit-reset':
                            self._rate_limit_reset = int(value)
                    
                    if self._rate_limit_remaining is not None:
                        logger.debug(f"Rate limit updated: {self._rate_limit_remaining}/{self._rate_limit_limit} "
                                   f"remaining, resets at {self._rate_limit_reset}")
        except Exception as e:
            # Don't fail if header extraction fails, just use static rate limiting
            logger.debug(f"Could not extract rate limit headers: {e}")
    
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
            """WebSocket runner with automatic reconnection."""
            reconnect_delay = 10  # seconds
            max_reconnect_delay = 300  # 5 minutes
            
            while not self._shutdown_event.is_set():
                try:
                    logger.info("Initializing WebSocket connection...")
                    self._initialize_ws_client()
                    
                    self.ws_client.open()
                    logger.info("WebSocket connection opened")
                    
                    # Subscribe to ticker channel for prices
                    self.ws_client.subscribe(product_ids=product_ids, channels=["ticker"])
                    logger.info(f"Subscribed to ticker for {len(product_ids)} products")
                    
                    # Subscribe to user channel for order updates if enabled
                    if enable_user_channel:
                        self.ws_client.subscribe(product_ids=product_ids, channels=["user"])
                        logger.info(f"Subscribed to user channel for real-time order updates")
                    
                    # Reset reconnect delay on successful connection
                    reconnect_delay = 10
                    
                    # Run WebSocket until it disconnects
                    self.ws_client.run_forever_with_exception_check()
                    
                except Exception as e:
                    if self._shutdown_event.is_set():
                        logger.info("WebSocket shutting down gracefully")
                        break
                    
                    logger.error(f"WebSocket error: {e}")
                    logger.info(f"Attempting to reconnect in {reconnect_delay} seconds...")
                    
                    # Wait before reconnecting, but check for shutdown periodically
                    for _ in range(reconnect_delay):
                        if self._shutdown_event.is_set():
                            break
                        time.sleep(1)
                    
                    # Exponential backoff for reconnect delay
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    
                finally:
                    if self.ws_client:
                        try:
                            self.ws_client.close()
                        except Exception as close_error:
                            logger.debug(f"Error closing WebSocket: {close_error}")
            
            logger.info("WebSocket thread exited")
        
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_portfolios',
                endpoint='/portfolios',
                params={},
                response=response
            )
            
            if response.portfolios and len(response.portfolios) > 0:
                portfolio_id = response.portfolios[0].uuid
                logger.info(f"Retrieved portfolio ID: {portfolio_id}")
                return portfolio_id
            else:
                raise PortfolioError("No portfolios found for this API key.")
        except Exception as e:
            logger.error(f"Error getting portfolio ID: {e}")
            
            # Log API error
            self._log_api_call(
                method='get_portfolios',
                endpoint='/portfolios',
                params={},
                error=e
            )
            
            raise APIError(f"Failed to get portfolio ID: {e}") from e
    
    def get_all_portfolios(self) -> List[Dict]:
        """
        Get all portfolios for the account.
        
        Returns:
            List of portfolio details
        """
        try:
            response = self.rest_client.get_portfolios()
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_portfolios',
                endpoint='/portfolios',
                params={},
                response=response
            )
            
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
            
            # Log API error
            self._log_api_call(
                method='get_portfolios',
                endpoint='/portfolios',
                params={},
                error=e
            )
            
            raise APIError(f"Failed to get portfolios: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='create_portfolio',
                endpoint='/portfolios',
                params={'name': name},
                response=response
            )
            
            if response and hasattr(response, 'portfolio'):
                portfolio_id = response.portfolio.uuid
                logger.info(f"Created portfolio: {name} ({portfolio_id})")
                return portfolio_id
            
            raise PortfolioError(f"Failed to create portfolio: {name}")
            
        except Exception as e:
            logger.error(f"Error creating portfolio: {e}")
            
            # Log API error
            self._log_api_call(
                method='create_portfolio',
                endpoint='/portfolios',
                params={'name': name},
                error=e
            )
            
            raise PortfolioError(f"Failed to create portfolio '{name}': {e}") from e
    
    def get_account_balances(
        self,
        portfolio_id: str,
        min_usd_equivalent: Decimal = Decimal('5')
    ) -> Dict[str, Decimal]:
        """
        Get account balances with filtering and pagination support.
        
        Args:
            portfolio_id: Portfolio UUID
            min_usd_equivalent: Minimum USD value to include
            
        Returns:
            Dictionary of {asset: balance}
        """
        try:
            balances = {}
            cursor = None
            page_count = 0
            
            # Paginate through all portfolio breakdown pages
            while True:
                page_count += 1
                
                # Apply rate limiting before API call
                self._rate_limit()
                
                # Get portfolio breakdown with pagination
                if cursor:
                    breakdown = self.rest_client.get_portfolio_breakdown(
                        portfolio_uuid=portfolio_id,
                        cursor=cursor
                    )
                else:
                    breakdown = self.rest_client.get_portfolio_breakdown(
                        portfolio_uuid=portfolio_id
                    )
                
                # Update rate limits from response headers
                self._update_rate_limits(breakdown)
                
                # Log API response
                self._log_api_call(
                    method='get_portfolio_breakdown',
                    endpoint=f'/portfolios/{portfolio_id}/breakdown',
                    params={'portfolio_uuid': portfolio_id, 'cursor': cursor},
                    response=breakdown
                )
                
                # Process balances from this page
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
                
                # Check if there are more pages
                if hasattr(breakdown.breakdown, 'pagination') and breakdown.breakdown.pagination:
                    cursor = getattr(breakdown.breakdown.pagination, 'next_cursor', None)
                    if cursor:
                        logger.debug(f"Fetching next page of balances (page {page_count + 1})...")
                        continue
                
                # No more pages
                break
            
            logger.info(f"Retrieved {len(balances)} balances (>= ${min_usd_equivalent}) from {page_count} page(s)")
            return balances
            
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            self._log_api_call(
                method='get_portfolio_breakdown',
                endpoint=f'/portfolios/{portfolio_id}/breakdown',
                params={'portfolio_uuid': portfolio_id},
                error=e
            )
            raise APIError(f"Failed to get account balances: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_products',
                endpoint='/products',
                params={},
                response=response
            )
            
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
            
            # Log API error
            self._log_api_call(
                method='get_products',
                endpoint='/products',
                params={},
                error=e
            )
            
            raise APIError(f"Failed to find tradable products: {e}") from e
    
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
                
                # Update rate limits from response headers
                self._update_rate_limits(product_info)
                
                # Log API call - DISABLED for products to reduce log volume
                # self._log_api_call(
                #     method='get_product',
                #     endpoint=f'/products/{product_id}',
                #     params={'product_id': product_id},
                #     response=product_info
                # )
                
                # Extract minimum sizes with fallbacks
                base_min_size = Decimal('0')
                min_market_funds = Decimal('0')
                base_increment = Decimal('0.00000001')  # Default for most products
                
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
                
                # Get base_increment for order size precision
                increment_val = getattr(product_info, 'base_increment', None)
                if increment_val:
                    base_increment = Decimal(str(increment_val))
                
                details[product_id] = {
                    'base_min_size': base_min_size,
                    'min_market_funds': min_market_funds,
                    'base_increment': base_increment
                }
                
            except Exception as e:
                logger.error(f"Error getting details for {product_id}: {e}")
                
                # Log API error - DISABLED for products to reduce log volume
                # self._log_api_call(
                #     method='get_product',
                #     endpoint=f'/products/{product_id}',
                #     params={'product_id': product_id},
                #     error=e
                # )
                
                details[product_id] = {
                    'base_min_size': Decimal('0'),
                    'min_market_funds': Decimal('0'),
                    'base_increment': Decimal('0.00000001')
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
            
            # Update rate limits from response headers
            self._update_rate_limits(candles_data)
            
            # Log API response - DISABLED for candles to reduce log volume
            # self._log_api_call(
            #     method='get_candles',
            #     endpoint=f'/products/{product_id}/candles',
            #     params={
            #         'product_id': product_id,
            #         'start': start_time.isoformat(),
            #         'end': end_time.isoformat(),
            #         'granularity': granularity,
            #         'requested_periods': periods
            #     },
            #     response=candles_data
            # )
            
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
            # Log API error - DISABLED for candles to reduce log volume
            # self._log_api_call(
            #     method='get_candles',
            #     endpoint=f'/products/{product_id}/candles',
            #     params={
            #         'product_id': product_id,
            #         'granularity': granularity,
            #         'periods': periods
            #     },
            #     error=e
            # )
            raise APIError(f"Failed to fetch historical data for {product_id}: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(product)
            
            # Log API call
            self._log_api_call(
                method='get_product',
                endpoint=f'/products/{product_id}',
                params={'product_id': product_id},
                response=product
            )
            
            price = getattr(product, 'price', None)
            if price:
                return Decimal(str(price))
        except Exception as e:
            logger.error(f"Error getting price for {product_id}: {e}")
            
            # Log API error
            self._log_api_call(
                method='get_product',
                endpoint=f'/products/{product_id}',
                params={'product_id': product_id},
                error=e
            )
        
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='preview_market_order',
                endpoint='/orders/preview',
                params={
                    'product_id': product_id,
                    'side': side,
                    'size': str(size)
                },
                response=response
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
            
            # Log API error
            self._log_api_call(
                method='preview_market_order',
                endpoint='/orders/preview',
                params={
                    'product_id': product_id,
                    'side': side,
                    'size': str(size)
                },
                error=e
            )
            
            raise OrderError(f"Failed to preview order: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_transaction_summary',
                endpoint='/transaction_summary',
                params={
                    'account_uuid': portfolio_id,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                response=response
            )
            
            if not response:
                raise APIError("No response received for transaction summary.")
            
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
            
            # Log API error
            self._log_api_call(
                method='get_transaction_summary',
                endpoint='/transaction_summary',
                params={
                    'account_uuid': portfolio_id,
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None
                },
                error=e
            )
            
            raise APIError(f"Failed to get transaction summary: {e}") from e
    
    def check_api_permissions(self) -> Dict[str, bool]:
        """
        Check API key permissions.
        
        Returns:
            Dictionary of permission status
        """
        try:
            response = self.rest_client.get_api_key_permissions()
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_api_key_permissions',
                endpoint='/key_permissions',
                params={},
                response=response
            )
            
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
            
            # Log API error
            self._log_api_call(
                method='get_api_key_permissions',
                endpoint='/key_permissions',
                params={},
                error=e
            )
            
            raise APIError(f"Failed to check API permissions: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='stop_limit_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'base_size': str(base_size),
                    'limit_price': str(limit_price),
                    'stop_price': str(stop_price)
                },
                response=response
            )
            
            if not response:
                raise OrderError(f"No response from stop-limit order for {product_id}")
            
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
            
            # Log API error
            self._log_api_call(
                method='stop_limit_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'base_size': str(base_size),
                    'limit_price': str(limit_price),
                    'stop_price': str(stop_price)
                },
                error=e
            )
            
            raise OrderError(f"Failed to create stop-limit order: {e}") from e
    
    def place_market_order(
        self,
        product_id: str,
        side: str,
        size: float
    ) -> Optional[Dict]:
        """
        Place a market order.
        
        Args:
            product_id: Product to trade
            side: BUY or SELL
            size: Order size in base currency
            
        Returns:
            Order details if successful
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            # Get product details to determine proper precision
            try:
                product_details = self.get_product_details([product_id])
                if product_id in product_details:
                    base_increment = product_details[product_id].get('base_increment', Decimal('0.00000001'))
                    # Round size to match base_increment precision
                    size_decimal = Decimal(str(size))
                    # Quantize to the proper precision
                    rounded_size = size_decimal.quantize(base_increment, rounding=ROUND_DOWN)
                    size = float(rounded_size)
                    logger.info(f"Rounded order size from {size_decimal} to {rounded_size} (increment: {base_increment})")
            except Exception as details_error:
                logger.warning(f"Could not get product details for {product_id}, using size as-is: {details_error}")
            
            try:
                # Use quote_size for BUY (spending USDC), base_size for SELL (selling crypto)
                response = self.rest_client.market_order(
                    client_order_id=f"market_{datetime.now(UTC).timestamp()}",
                    product_id=product_id,
                    side=side,
                    quote_size=str(size) if side == "BUY" else None,
                    base_size=str(size) if side == "SELL" else None
                )
                
                # Update rate limits
                self._update_rate_limits(response)
                
                # Log API call
                self._log_api_call(
                    method='market_order',
                    endpoint='/orders',
                    params={
                        'product_id': product_id,
                        'side': side,
                        'size': str(size)
                    },
                    response=response
                )
            except Exception as order_error:
                # Log the failed API call
                self._log_api_call(
                    method='market_order',
                    endpoint='/orders',
                    params={
                        'product_id': product_id,
                        'side': side,
                        'size': str(size)
                    },
                    error=order_error
                )
                raise
            
            if not response:
                raise OrderError(f"No response from market order for {product_id}")
            
            # Check if order was successful
            if not response.success:
                error_msg = f"Market order failed for {product_id}"
                if hasattr(response, 'error_response') and response.error_response:
                    if hasattr(response.error_response, 'error'):
                        error_msg += f": {response.error_response.error} - {response.error_response.message}"
                    else:
                        error_msg += f": {response.error_response}"
                elif hasattr(response, 'failure_reason') and response.failure_reason:
                    error_msg += f": {response.failure_reason}"
                logger.error(f"[DEBUG] Response type: {type(response)}")
                logger.error(f"[DEBUG] Response details: {response}")
                if hasattr(response, '__dict__'):
                    logger.error(f"[DEBUG] Response dict: {response.__dict__}")
                raise OrderError(error_msg)
            
            # Extract order ID safely
            order_id = None
            if hasattr(response, 'success_response') and response.success_response:
                if hasattr(response.success_response, 'order_id'):
                    order_id = response.success_response.order_id
                elif isinstance(response.success_response, dict):
                    order_id = response.success_response.get('order_id')
            
            order = {
                'success': response.success,
                'order_id': order_id,
                'product_id': product_id,
                'side': side,
                'type': 'market',
                'size': size
            }
            
            logger.info(f"Market order placed: {side} {size} {product_id} - Order ID: {order_id}")
            
            return order
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            
            # Log API error
            self._log_api_call(
                method='market_order',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'size': str(size)
                },
                error=e
            )
            
            raise OrderError(f"Failed to place market order: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='trigger_bracket_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'base_size': str(base_size),
                    'limit_price': str(limit_price),
                    'stop_loss_price': str(stop_loss_price),
                    'take_profit_price': str(take_profit_price)
                },
                response=response
            )
            
            if not response:
                raise OrderError(f"No response from bracket order for {product_id}")
            
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
            
            # Log API error
            self._log_api_call(
                method='trigger_bracket_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'base_size': str(base_size),
                    'limit_price': str(limit_price),
                    'stop_loss_price': str(stop_loss_price),
                    'take_profit_price': str(take_profit_price)
                },
                error=e
            )
            
            raise OrderError(f"Failed to create bracket order: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='cancel_orders',
                endpoint='/orders/batch_cancel',
                params={'order_ids': [order_id]},
                response=response
            )
            
            if response and hasattr(response, 'results'):
                for result in response.results:
                    if result.success:
                        logger.info(f"Order {order_id} cancelled successfully")
                        return True
            
            logger.warning(f"Failed to cancel order {order_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            
            # Log API error
            self._log_api_call(
                method='cancel_orders',
                endpoint='/orders/batch_cancel',
                params={'order_ids': [order_id]},
                error=e
            )
            
            raise OrderError(f"Failed to cancel order {order_id}: {e}") from e
    
    def convert_crypto(self, from_asset: str, to_asset: str, amount: str) -> Optional[Dict]:
        """
        Convert one cryptocurrency to another using Coinbase Convert API.
        This is more efficient than selling and buying separately.
        
        Args:
            from_asset: Source cryptocurrency symbol (e.g., 'ETH', 'BTC')
            to_asset: Target cryptocurrency symbol (e.g., 'SOL', 'USDC')
            amount: Amount of source asset to convert
            
        Returns:
            Dict with conversion details if successful, None otherwise
            {
                'trade_id': str,
                'from_amount': str,
                'from_currency': str,
                'to_amount': str,
                'to_currency': str,
                'exchange_rate': str,
                'status': str
            }
        """
        try:
            # Get account IDs for source and target currencies (with pagination)
            logger.info(f"Getting account IDs for {from_asset} and {to_asset}")
            
            from_account_id = None
            to_account_id = None
            all_accounts = []
            cursor = None
            page_num = 1
            
            # Fetch all pages of accounts
            while True:
                if cursor:
                    accounts_response = self.rest_client.get_accounts(cursor=cursor)
                else:
                    accounts_response = self.rest_client.get_accounts()
                
                self._update_rate_limits(accounts_response)
                
                if hasattr(accounts_response, 'accounts'):
                    all_accounts.extend(accounts_response.accounts)
                    logger.info(f"[DEBUG] Page {page_num}: Retrieved {len(accounts_response.accounts)} accounts")
                    page_num += 1
                    
                    # Check if there are more pages
                    if hasattr(accounts_response, 'has_next') and accounts_response.has_next:
                        cursor = accounts_response.cursor
                    else:
                        break
                else:
                    logger.error(f"[DEBUG] accounts_response has no 'accounts' attribute")
                    logger.error(f"[DEBUG] accounts_response type: {type(accounts_response)}")
                    logger.error(f"[DEBUG] accounts_response: {accounts_response}")
                    break
            
            # Now search through all accounts
            logger.info(f"[DEBUG] Total accounts retrieved: {len(all_accounts)}")
            for account in all_accounts:
                logger.debug(f"  Account: currency={account.currency}, uuid={account.uuid}, available_balance={getattr(account, 'available_balance', 'N/A')}")
                
                account_currency = account.currency
                
                # Match exact currency first (prioritize over ETH2 mapping)
                if account_currency == from_asset and not from_account_id:
                    from_account_id = account.uuid
                    logger.info(f"  -> Matched {from_asset} account: {account.uuid}")
                elif account_currency == to_asset and not to_account_id:
                    to_account_id = account.uuid
                    logger.info(f"  -> Matched {to_asset} account: {account.uuid}")
            
            # If still not found, try ETH/ETH2 mapping as fallback
            if from_asset == 'ETH' and not from_account_id:
                for account in all_accounts:
                    if account.currency == 'ETH2':
                        from_account_id = account.uuid
                        logger.info(f"  -> Fallback: Matched {from_asset} to ETH2 account")
                        break
            
            if to_asset == 'ETH' and not to_account_id:
                for account in all_accounts:
                    if account.currency == 'ETH2':
                        to_account_id = account.uuid
                        logger.info(f"  -> Fallback: Matched {to_asset} to ETH2 account")
                        break
            
            if not from_account_id or not to_account_id:
                # Log all account currencies for debugging
                all_currencies = [acc.currency for acc in all_accounts]
                logger.error(f"[DEBUG] All available currencies: {sorted(set(all_currencies))}")
            
            if not from_account_id:
                raise APIError(f"Could not find account ID for {from_asset}")
            
            if not to_account_id:
                raise APIError(f"Could not find account ID for {to_asset}")
            
            logger.info(f"From account: {from_account_id} ({from_asset})")
            logger.info(f"To account: {to_account_id} ({to_asset})")
            
            # Step 1: Create a convert quote
            logger.info(f"Creating convert quote: {amount} {from_asset} -> {to_asset}")
            
            try:
                quote_response = self.rest_client.create_convert_quote(
                    from_account=from_account_id,
                    to_account=to_account_id,
                    amount=amount
                )
                
                # Update rate limits
                self._update_rate_limits(quote_response)
                
                # Log API call with UUIDs
                self._log_api_call(
                    method='create_convert_quote',
                    endpoint='/convert/quote',
                    params={
                        'from_account_id': from_account_id,
                        'from_currency': from_asset,
                        'to_account_id': to_account_id,
                        'to_currency': to_asset,
                        'amount': amount
                    },
                    response=quote_response
                )
            except Exception as quote_error:
                # Log the failed API call with UUIDs
                self._log_api_call(
                    method='create_convert_quote',
                    endpoint='/convert/quote',
                    params={
                        'from_account_id': from_account_id,
                        'from_currency': from_asset,
                        'to_account_id': to_account_id,
                        'to_currency': to_asset,
                        'amount': amount
                    },
                    error=quote_error
                )
                raise
            
            # Log HTTP response details
            logger.info(f"[HTTP RESPONSE] create_convert_quote:")
            logger.info(f"  Response type: {type(quote_response)}")
            logger.info(f"  Response object: {quote_response}")
            if hasattr(quote_response, '__dict__'):
                logger.info(f"  Response attributes: {quote_response.__dict__}")
            
            # Debug: Log the full response structure
            logger.info(f"[DEBUG] Convert quote response type: {type(quote_response)}")
            logger.info(f"[DEBUG] Convert quote response has 'trade': {hasattr(quote_response, 'trade')}")
            if hasattr(quote_response, 'trade'):
                logger.info(f"[DEBUG] Trade is None: {quote_response.trade is None}")
                if quote_response.trade:
                    logger.info(f"[DEBUG] Trade object type: {type(quote_response.trade)}")
                    # Log all attributes of trade object
                    trade_attrs = {attr: getattr(quote_response.trade, attr, 'N/A') for attr in dir(quote_response.trade) if not attr.startswith('_')}
                    logger.info(f"[DEBUG] Trade attributes: {trade_attrs}")
            
            if not hasattr(quote_response, 'trade') or not quote_response.trade:
                raise APIError("Failed to get conversion quote - no trade in response")
            
            trade = quote_response.trade
            trade_id = trade.id
            
            # Extract conversion details
            from_amount = getattr(trade, 'amount', {}).get('value', amount)
            from_currency = getattr(trade, 'source_currency', from_asset)
            to_amount = getattr(trade, 'subtotal', {}).get('value', 'unknown')
            to_currency = getattr(trade, 'target_currency', to_asset) if hasattr(trade, 'target_currency') else to_asset
            exchange_rate = getattr(trade, 'exchange_rate', {}).get('value', 'unknown')
            
            logger.info(f"Quote received: {from_amount} {from_currency} -> {to_amount} {to_currency} (rate: {exchange_rate})")
            
            # Step 2: Commit the conversion
            logger.info(f"Committing conversion with trade ID: {trade_id}")
            
            commit_response = self.rest_client.commit_convert_trade(
                trade_id=trade_id,
                from_account=from_account_id,
                to_account=to_account_id
            )
            
            # Log HTTP response details
            logger.info(f"[HTTP RESPONSE] commit_convert_trade:")
            logger.info(f"  Response type: {type(commit_response)}")
            logger.info(f"  Response object: {commit_response}")
            if hasattr(commit_response, '__dict__'):
                logger.info(f"  Response attributes: {commit_response.__dict__}")
            
            # Update rate limits
            self._update_rate_limits(commit_response)
            
            # Log API call
            self._log_api_call(
                method='commit_convert_trade',
                endpoint=f'/convert/trade/{trade_id}',
                params={
                    'trade_id': trade_id,
                    'from_account': from_account_id,
                    'to_account': to_account_id
                },
                response=commit_response
            )
            
            if not hasattr(commit_response, 'trade') or not commit_response.trade:
                raise APIError("Failed to commit conversion - no trade in response")
            
            committed_trade = commit_response.trade
            status = getattr(committed_trade, 'status', 'unknown')
            
            logger.info(f"[SUCCESS] Conversion committed: {from_amount} {from_currency} -> {to_amount} {to_currency} (status: {status})")
            
            return {
                'trade_id': trade_id,
                'from_amount': from_amount,
                'from_currency': from_currency,
                'to_amount': to_amount,
                'to_currency': to_currency,
                'exchange_rate': exchange_rate,
                'status': status
            }
            
        except Exception as e:
            logger.error(f"Error converting {from_asset} to {to_asset}: {e}")
            
            # Log API error
            self._log_api_call(
                method='convert_crypto',
                endpoint='/convert',
                params={
                    'from_account': from_asset,
                    'to_account': to_asset,
                    'amount': amount
                },
                error=e
            )
            
            raise APIError(f"Failed to convert {from_asset} to {to_asset}: {e}") from e
    
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
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_order',
                endpoint=f'/orders/historical/{order_id}',
                params={'order_id': order_id},
                response=response
            )
            
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
            
            # Log API error
            self._log_api_call(
                method='get_order',
                endpoint=f'/orders/historical/{order_id}',
                params={'order_id': order_id},
                error=e
            )
            
            raise OrderError(f"Failed to get order status for {order_id}: {e}") from e
    
    def get_best_bid_ask(self, product_ids: List[str]) -> Dict:
        """
        Get best bid/ask prices for multiple products simultaneously.
        Critical for spread analysis and optimal limit order placement.
        
        Args:
            product_ids: List of product IDs to get bid/ask for
            
        Returns:
            Dictionary of {product_id: {'best_bid', 'best_ask', 'spread', 'spread_pct'}}
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            response = self.rest_client.get_best_bid_ask(product_ids=product_ids)
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_best_bid_ask',
                endpoint='/best_bid_ask',
                params={'product_ids': product_ids},
                response=response
            )
            
            if not response or not hasattr(response, 'pricebooks'):
                raise APIError("No pricebooks in best bid/ask response")
            
            result = {}
            for pricebook in response.pricebooks:
                product_id = pricebook.product_id
                
                # Get best bid (highest buy price)
                best_bid = None
                if pricebook.bids and len(pricebook.bids) > 0:
                    best_bid = Decimal(str(pricebook.bids[0].price))
                
                # Get best ask (lowest sell price)
                best_ask = None
                if pricebook.asks and len(pricebook.asks) > 0:
                    best_ask = Decimal(str(pricebook.asks[0].price))
                
                # Calculate spread
                spread = None
                spread_pct = None
                if best_bid and best_ask:
                    spread = best_ask - best_bid
                    spread_pct = (spread / best_bid) * 100
                
                result[product_id] = {
                    'best_bid': best_bid,
                    'best_ask': best_ask,
                    'spread': spread,
                    'spread_pct': float(spread_pct) if spread_pct else None
                }
            
            logger.debug(f"Retrieved best bid/ask for {len(result)} products")
            return result
            
        except Exception as e:
            logger.error(f"Error getting best bid/ask: {e}")
            
            # Log API error
            self._log_api_call(
                method='get_best_bid_ask',
                endpoint='/best_bid_ask',
                params={'product_ids': product_ids},
                error=e
            )
            
            raise APIError(f"Failed to get best bid/ask: {e}") from e
    
    def place_limit_order_gtc(
        self,
        product_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        post_only: bool = True
    ) -> Optional[Dict]:
        """
        Place a Good-Til-Cancelled limit order with optional post-only flag.
        Post-only ensures maker order (earns rebates instead of paying taker fees).
        
        Args:
            product_id: Product to trade
            side: BUY or SELL
            price: Limit price
            size: Order size
            post_only: If True, order will only execute as maker (earns rebates)
            
        Returns:
            Order details if successful
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            response = self.rest_client.limit_order_gtc(
                client_order_id=f"limit_gtc_{datetime.now(UTC).timestamp()}",
                product_id=product_id,
                side=side,
                base_size=str(size),
                limit_price=str(price),
                post_only=post_only
            )
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API response
            self._log_api_call(
                method='limit_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'price': str(price),
                    'size': str(size),
                    'post_only': post_only
                },
                response=response
            )
            
            if not response:
                raise OrderError(f"No response from limit order for {product_id}")
            
            # Extract order ID safely from response
            order_id = None
            if hasattr(response, 'success_response') and response.success_response:
                if hasattr(response.success_response, 'order_id'):
                    order_id = response.success_response.order_id
                elif isinstance(response.success_response, dict):
                    order_id = response.success_response.get('order_id')
            elif hasattr(response, 'order_id'):
                order_id = response.order_id
            elif isinstance(response, dict):
                order_id = response.get('order_id')
            
            # If still no order_id, log the response structure for debugging
            if not order_id:
                logger.error(f"Could not extract order_id from response. Response type: {type(response)}")
                logger.error(f"Response attributes: {dir(response)}")
                if hasattr(response, '__dict__'):
                    logger.error(f"Response dict: {response.__dict__}")
            
            order = {
                'order_id': order_id,
                'product_id': product_id,
                'side': side,
                'type': 'limit_gtc',
                'price': price,
                'size': size,
                'post_only': post_only,
                'status': getattr(response, 'status', 'submitted')
            }
            
            rebate_note = " (earning maker rebates)" if post_only else ""
            logger.info(f"Limit order placed: {side} {size} {product_id} @ ${price}{rebate_note}")
            
            return order
            
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            self._log_api_call(
                method='limit_order_gtc',
                endpoint='/orders',
                params={
                    'product_id': product_id,
                    'side': side,
                    'price': str(price),
                    'size': str(size)
                },
                error=e
            )
            raise OrderError(f"Failed to place limit order: {e}") from e
    
    def get_fills(
        self,
        order_id: Optional[str] = None,
        product_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get fill history for orders (actual execution details).
        Critical for tracking real execution quality and slippage.
        
        Args:
            order_id: Specific order ID to get fills for
            product_id: Filter by product
            start_date: Start date for fills
            limit: Maximum number of fills to return
            
        Returns:
            List of fill details with actual execution prices
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            # Build parameters
            params = {}
            if order_id:
                params['order_ids'] = [order_id]
            if product_id:
                params['product_ids'] = [product_id]
            if start_date:
                params['start_sequence_timestamp'] = start_date.isoformat()
            if limit:
                params['limit'] = limit
            
            response = self.rest_client.get_fills(**params)
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_fills',
                endpoint='/orders/historical/fills',
                params=params,
                response=response
            )
            
            if not response or not hasattr(response, 'fills'):
                return []
            
            fills = []
            for fill in response.fills:
                fills.append({
                    'entry_id': getattr(fill, 'entry_id', None),
                    'trade_id': getattr(fill, 'trade_id', None),
                    'order_id': getattr(fill, 'order_id', None),
                    'trade_time': getattr(fill, 'trade_time', None),
                    'trade_type': getattr(fill, 'trade_type', None),
                    'price': Decimal(str(getattr(fill, 'price', 0))),
                    'size': Decimal(str(getattr(fill, 'size', 0))),
                    'commission': Decimal(str(getattr(fill, 'commission', 0))),
                    'product_id': getattr(fill, 'product_id', None),
                    'side': getattr(fill, 'side', None),
                    'liquidity_indicator': getattr(fill, 'liquidity_indicator', None)  # MAKER or TAKER
                })
            
            logger.info(f"Retrieved {len(fills)} fills")
            return fills
            
        except Exception as e:
            logger.error(f"Error getting fills: {e}")
            
            # Log API error
            self._log_api_call(
                method='get_fills',
                endpoint='/orders/historical/fills',
                params={
                    'order_id': order_id,
                    'product_id': product_id,
                    'limit': limit
                },
                error=e
            )
            
            raise APIError(f"Failed to get fills: {e}") from e
    
    def calculate_cost_basis(self, product_id: str) -> Optional[Decimal]:
        """
        Calculate the average cost basis for a product based on all BUY fills.
        Includes commission fees in the cost calculation for accurate profitability tracking.
        
        This is critical for profit-based exit strategies - you need to know the true
        cost (including fees) to determine when you've reached a profit target.
        
        Formula: total_cost = sum((price × size) + commission) / sum(size)
        
        Args:
            product_id: The product to calculate cost basis for (e.g., 'XCN-USDC')
            
        Returns:
            Average cost per unit including fees, or None if no BUY fills found
            
        Example:
            If you bought XCN in 3 separate orders:
            - Order 1: 1000 XCN @ $0.007, commission $0.05
            - Order 2: 500 XCN @ $0.008, commission $0.03
            - Order 3: 1500 XCN @ $0.0069, commission $0.07
            
            total_cost = (1000*0.007 + 0.05) + (500*0.008 + 0.03) + (1500*0.0069 + 0.07)
                       = 7.05 + 4.03 + 10.42 = $21.50
            total_size = 1000 + 500 + 1500 = 3000
            cost_basis = 21.50 / 3000 = $0.00717 per XCN
        """
        try:
            # Get all fills for this product (not filtered by order_id, to get ALL fills)
            # We'll fetch more than default to get complete history
            all_fills = self.get_fills(product_id=product_id, limit=1000)
            
            if not all_fills:
                logger.warning(f"No fills found for {product_id}")
                return None
            
            # Filter to only BUY fills (we don't want SELL fills in cost basis)
            buy_fills = [f for f in all_fills if f['side'] == 'BUY']
            
            if not buy_fills:
                logger.warning(f"No BUY fills found for {product_id}")
                return None
            
            # Calculate total cost and total size
            total_cost = Decimal('0')
            total_size = Decimal('0')
            
            for fill in buy_fills:
                price = fill['price']
                size = fill['size']
                commission = fill['commission']
                
                # Cost for this fill = (price per unit × quantity) + fees
                fill_cost = (price * size) + commission
                total_cost += fill_cost
                total_size += size
            
            if total_size == 0:
                logger.warning(f"Total size is 0 for {product_id}")
                return None
            
            # Average cost basis per unit
            cost_basis = total_cost / total_size
            
            logger.info(f"Cost basis for {product_id}: ${cost_basis:.6f} "
                       f"(from {len(buy_fills)} BUY fills, total size: {total_size})")
            
            return cost_basis
            
        except Exception as e:
            logger.error(f"Error calculating cost basis for {product_id}: {e}")
            return None
    
    def get_market_trades(
        self,
        product_id: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get recent market trades for volume flow and liquidity analysis.
        Shows buy vs sell pressure in real-time.
        
        Args:
            product_id: Product to get trades for
            limit: Number of recent trades to fetch
            
        Returns:
            List of recent trades with side, price, size
        """
        try:
            # Apply rate limiting before API call
            self._rate_limit()
            
            response = self.rest_client.get_market_trades(
                product_id=product_id,
                limit=limit
            )
            
            # Update rate limits from response headers
            self._update_rate_limits(response)
            
            # Log API call
            self._log_api_call(
                method='get_market_trades',
                endpoint=f'/products/{product_id}/ticker',
                params={'product_id': product_id, 'limit': limit},
                response=response
            )
            
            if not response or not hasattr(response, 'trades'):
                return []
            
            trades = []
            for trade in response.trades:
                trades.append({
                    'trade_id': getattr(trade, 'trade_id', None),
                    'product_id': getattr(trade, 'product_id', None),
                    'price': Decimal(str(getattr(trade, 'price', 0))),
                    'size': Decimal(str(getattr(trade, 'size', 0))),
                    'time': getattr(trade, 'time', None),
                    'side': getattr(trade, 'side', None)  # BUY or SELL
                })
            
            logger.debug(f"Retrieved {len(trades)} market trades for {product_id}")
            return trades
            
        except Exception as e:
            logger.error(f"Error getting market trades for {product_id}: {e}")
            
            # Log API error
            self._log_api_call(
                method='get_market_trades',
                endpoint=f'/products/{product_id}/ticker',
                params={'product_id': product_id, 'limit': limit},
                error=e
            )
            
            raise APIError(f"Failed to get market trades for {product_id}: {e}") from e
    
    def analyze_volume_flow(
        self,
        product_id: str,
        lookback_trades: int = 100
    ) -> Dict:
        """
        Analyze buy vs sell volume flow to gauge market pressure.
        
        Args:
            product_id: Product to analyze
            lookback_trades: Number of recent trades to analyze
            
        Returns:
            Dictionary with buy_pressure, sell_pressure, net_pressure
        """
        try:
            trades = self.get_market_trades(product_id, limit=lookback_trades)
            
            if not trades:
                return {
                    'buy_volume': Decimal('0'),
                    'sell_volume': Decimal('0'),
                    'buy_pressure': 0.5,
                    'net_pressure': 'neutral'
                }
            
            buy_volume = sum(t['size'] for t in trades if t['side'] == 'BUY')
            sell_volume = sum(t['size'] for t in trades if t['side'] == 'SELL')
            total_volume = buy_volume + sell_volume
            
            buy_pressure = float(buy_volume / total_volume) if total_volume > 0 else 0.5
            
            # Classify pressure
            if buy_pressure > 0.6:
                net_pressure = 'strong_buy'
            elif buy_pressure > 0.55:
                net_pressure = 'moderate_buy'
            elif buy_pressure < 0.4:
                net_pressure = 'strong_sell'
            elif buy_pressure < 0.45:
                net_pressure = 'moderate_sell'
            else:
                net_pressure = 'neutral'
            
            result = {
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'buy_pressure': buy_pressure,
                'net_pressure': net_pressure
            }
            
            logger.debug(f"{product_id} volume flow: {buy_pressure:.1%} buy pressure ({net_pressure})")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing volume flow: {e}")
            return {
                'buy_volume': Decimal('0'),
                'sell_volume': Decimal('0'),
                'buy_pressure': 0.5,
                'net_pressure': 'neutral'
            }
    
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
