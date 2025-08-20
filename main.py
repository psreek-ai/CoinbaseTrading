# main_trading_bot.py

import os
import time
import json
import logging
import uuid
from threading import Thread, Lock
from datetime import datetime, timedelta, UTC
from decimal import Decimal, getcontext
from itertools import permutations

# Import third-party libraries
from dotenv import load_dotenv
import pandas as pd
import pandas_ta as ta

# Import Coinbase SDK
from coinbase.rest import RESTClient
from coinbase.websocket import WSClient

# --- CONFIGURATION ---
# Set precision for Decimal calculations
getcontext().prec = 10

# --- TRADING PARAMETERS ---
# Supported Granularities: 'ONE_MINUTE', 'FIVE_MINUTE', 'FIFTEEN_MINUTE', 'THIRTY_MINUTE', 'ONE_HOUR', 'TWO_HOUR', 'SIX_HOUR', 'ONE_DAY'
CANDLE_GRANULARITY = 'FIVE_MINUTE'
CANDLE_PERIODS_FOR_ANALYSIS = 100 # Number of candles to fetch for TA

# Paper trading / safety flags
# When True the bot will not submit live orders, it will simulate and log intended trades.
PAPER_TRADING_MODE = True

# Risk management defaults
# Risk percent per trade expressed as a Decimal (e.g., 0.01 = 1%)
RISK_PERCENT = Decimal('0.01')

# Default stop loss percent (1.5% below entry)
DEFAULT_STOP_LOSS_PCT = Decimal('0.015')

# Default take profit percent (3% above entry)
DEFAULT_TAKE_PROFIT_PCT = Decimal('0.03')

# --- RISK MANAGEMENT ---
# Percentage of the source currency to use in a conversion trade.
# For a BUY on GRT-ETH, this is the percentage of your ETH balance to spend.
TRADE_SIZE_PERCENT = 10.0 

# --- EXECUTION PARAMETERS ---
LOOP_SLEEP_SECONDS = 60 # Check for signals every 60 seconds

# --- LOGGING SETUP ---
# Create a logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

log_filename = f"logs/trading_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_filename),
                        logging.StreamHandler()
                    ])

# --- GLOBAL STATE ---
# Use a thread-safe dictionary for latest prices (Python dicts are thread-safe for simple atomics)
latest_prices = {}
# Global state to track if we are in a position for a specific product
# Example: {"BTC-ETH": True, "GRT-BTC": False}
bot_state = {
    "positions": {}
}
# In-memory order tracking and simulated positions (used for paper-trade mode)
orders = {}
simulated_positions = {}
# Lock to protect shared structures in multi-threaded environment
state_lock = Lock()

# ==============================================================================
# SECTION 1: COINBASE API INTERACTION
# ==============================================================================

def initialize_api_clients():
    """Loads API keys and initializes REST and WebSocket clients."""
    load_dotenv()
    api_key = os.getenv("COINBASE_API_KEY")
    api_secret = os.getenv("COINBASE_API_SECRET")

    if not api_key or not api_secret:
        logging.error("API key and secret not found. Please set them in the .env file.")
        return None, None
    
    try:
        rest_client = RESTClient(api_key=api_key, api_secret=api_secret)
        ws_client = WSClient(api_key=api_key, api_secret=api_secret, on_message=on_websocket_message)
        logging.info("Successfully initialized REST and WebSocket clients.")
        return rest_client, ws_client
    except Exception as e:
        logging.error(f"Error initializing API clients: {e}")
        return None, None


def get_portfolio_id(client: RESTClient):
    """Fetches the UUID of the first available portfolio."""
    try:
        portfolios_response = client.get_portfolios()
        if portfolios_response.portfolios and len(portfolios_response.portfolios) > 0:
            portfolio_id = portfolios_response.portfolios[0].uuid
            logging.info(f"Successfully retrieved portfolio ID: {portfolio_id}")
            return portfolio_id
        else:
            logging.error("No portfolios found for this account.")
            return None
    except Exception as e:
        logging.error(f"Error fetching portfolio ID: {e}")
        return None

def get_account_balances(client: RESTClient, portfolio_id: str):
    """
    Fetches all non-zero account balances using the get_portfolio_breakdown endpoint.
    """
    try:
        portfolio_breakdown = client.get_portfolio_breakdown(portfolio_uuid=portfolio_id)
        balances = {}
        if portfolio_breakdown and portfolio_breakdown.breakdown and portfolio_breakdown.breakdown.spot_positions:
            for asset in portfolio_breakdown.breakdown.spot_positions:
                balance = Decimal(asset.total_balance_crypto)
                # Filter out very small "dust" balances
                if balance > Decimal('1e-8'):
                    balances[asset.asset] = balance
        logging.info(f"Retrieved balances using portfolio breakdown: {balances}")
        return balances
    except Exception as e:
        logging.error(f"Error fetching account balances via portfolio breakdown: {e}")
        return {}

def find_tradable_products(client: RESTClient, balances: dict) -> list:
    """
    Finds all products that can be traded using the assets currently in the portfolio as the source currency.
    """
    tradable_products = []
    portfolio_assets = set(balances.keys())
    
    try:
        products_response = client.get_products()
        all_products = products_response.products
        
        for product in all_products:
            # A tradable product is one where the quote currency (what you spend)
            # is an asset you hold in your portfolio.
            if product.quote_currency_id in portfolio_assets:
                # We also don't want to trade an asset for itself (e.g., ETH-ETH)
                if product.base_currency_id != product.quote_currency_id:
                    # Add a check to ensure the product is online and not disabled for trading.
                    if product.status == 'online' and not product.trading_disabled:
                        tradable_products.append(product.product_id)
        
        logging.info(f"Found {len(tradable_products)} tradable products based on current portfolio.")
        logging.debug(f"Tradable product list: {tradable_products}")
        return tradable_products
    except Exception as e:
        logging.error(f"Error finding tradable products: {e}")
        return []

def get_product_details(client: RESTClient, product_ids: list) -> dict:
    """
    Fetches and caches the trading rules (like min size) for a list of products.
    This function is defensive: different SDK versions/response shapes may expose
    fields under different attribute names or dict keys. We attempt several common
    names and fall back to safe defaults.
    """
    def _safe_decimal(obj, *candidates, default=Decimal('0')):
        # Try attribute access, dict access, and to_dict() fallback
        for name in candidates:
            try:
                # attribute
                val = getattr(obj, name, None)
                if val is None and isinstance(obj, dict):
                    val = obj.get(name)
                if val is None and hasattr(obj, "to_dict"):
                    try:
                        val = obj.to_dict().get(name)
                    except Exception:
                        val = None
                if val is not None:
                    # convert to Decimal safely
                    return Decimal(str(val))
            except Exception:
                continue
        return default

    details = {}
    for product_id in product_ids:
        try:
            product_info = client.get_product(product_id=product_id)
            # Common field name variations observed across SDKs / API versions:
            base_min_candidates = ("base_min_size", "base_minimum_size", "min_base_size", "base_min")
            min_market_candidates = ("min_market_funds", "min_quote_size", "min_market_size", "min_order_funds")
            base_min_size = _safe_decimal(product_info, *base_min_candidates, default=Decimal('0'))
            min_market_funds = _safe_decimal(product_info, *min_market_candidates, default=Decimal('0'))

            details[product_id] = {
                "base_min_size": base_min_size,
                "min_market_funds": min_market_funds
            }

            # If both values are zero, log at debug level to reduce noise
            if base_min_size == 0 and min_market_funds == 0:
                logging.debug(f"Product {product_id} returned no min size info; defaults applied.")
            else:
                logging.debug(f"Product {product_id} details: base_min_size={base_min_size}, min_market_funds={min_market_funds}")

        except Exception as e:
            logging.error(f"Could not fetch product details for {product_id}: {e}")
            # Ensure a safe default entry so caller can rely on keys existing
            details.setdefault(product_id, {"base_min_size": Decimal('0'), "min_market_funds": Decimal('0')})
    return details

def get_total_equity(balances: dict, preferred_quote: str = "USD") -> Decimal:
    """
    Estimate total equity denominated in preferred_quote using latest_prices.
    This is an approximate method: it tries to convert each asset into preferred_quote
    using latest_prices dictionary. Missing price data will be skipped.
    """
    total = Decimal('0')
    for asset, bal in balances.items():
        try:
            bal_dec = Decimal(bal)
        except Exception:
            continue

        if asset == preferred_quote:
            total += bal_dec
            continue

        # Try direct pair asset-preferred_quote
        direct = f"{asset}-{preferred_quote}"
        inverse = f"{preferred_quote}-{asset}"
        price = latest_prices.get(direct) or latest_prices.get(inverse)
        if price:
            # if inverse exists, price represents quote in form preferred_quote-asset (we need 1/price)
            try:
                price_dec = Decimal(price)
                if direct in latest_prices:
                    total += bal_dec * price_dec
                else:
                    # inverse provided (preferred_quote-asset), convert using 1/price
                    if price_dec > 0:
                        total += bal_dec / price_dec
            except Exception:
                continue
        else:
            # As a fallback, skip asset (could be extended to fetch spot price via REST)
            logging.debug(f"No price available to convert {asset} to {preferred_quote}; skipping in equity calc.")
            continue
    return total

def get_historical_data(client: RESTClient, product_id: str, granularity: str, periods: int) -> pd.DataFrame:
    """Fetches historical OHLCV data and returns it as a Pandas DataFrame."""
    if periods > 300:
        logging.warning("Coinbase API limits candle requests to 300 periods. Fetching 300.")
        periods = 300
    
    granularity_map = {
        'ONE_MINUTE': timedelta(minutes=1), 'FIVE_MINUTE': timedelta(minutes=5),
        'FIFTEEN_MINUTE': timedelta(minutes=15), 'THIRTY_MINUTE': timedelta(minutes=30),
        'ONE_HOUR': timedelta(hours=1), 'TWO_HOUR': timedelta(hours=2),
        'SIX_HOUR': timedelta(hours=6), 'ONE_DAY': timedelta(days=1)
    }
    
    delta = granularity_map.get(granularity)
    if not delta:
        logging.error(f"Unsupported granularity: {granularity}")
        return pd.DataFrame()

    end_time = datetime.now(UTC)
    start_time = end_time - (delta * periods)

    try:
        candles_data = client.get_candles(
            product_id=product_id,
            start=str(int(start_time.timestamp())),
            end=str(int(end_time.timestamp())),
            granularity=granularity
        )
        
        if not hasattr(candles_data, 'candles') or not candles_data.candles:
            logging.warning(f"No valid candle data returned for {product_id}. API Response: {candles_data}")
            return pd.DataFrame()

        # Manually construct a list of dictionaries from the Candle object attributes.
        candles_list = [{
            'start': candle.start,
            'low': candle.low,
            'high': candle.high,
            'open': candle.open,
            'close': candle.close,
            'volume': candle.volume
        } for candle in candles_data.candles]
        
        df = pd.DataFrame(candles_list)

        if df.empty or 'start' not in df.columns:
            logging.warning(f"Malformed or empty DataFrame for {product_id} after processing. API Response: {candles_data}")
            return pd.DataFrame()

        df['time'] = pd.to_datetime(df['start'], unit='s')
        df.set_index('time', inplace=True)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        logging.error(f"An exception occurred while fetching or processing historical data for {product_id}: {e}", exc_info=True)
        return pd.DataFrame()

# ==============================================================================
# SECTION 2: REAL-TIME DATA (WEBSOCKET)
# ==============================================================================

def on_websocket_message(msg):
    """Callback function to process incoming WebSocket messages."""
    try:
        msg_data = json.loads(msg)
        if msg_data.get('channel') == 'ticker' and 'events' in msg_data:
            for event in msg_data['events']:
                for ticker in event.get('tickers', []):
                    product_id = ticker.get('product_id')
                    price = ticker.get('price')
                    if product_id and price:
                        latest_prices[product_id] = Decimal(price)
    except json.JSONDecodeError:
        logging.warning(f"Could not decode WebSocket message: {msg}")
    except Exception as e:
        logging.error(f"Error in WebSocket message handler: {e}")


def start_websocket(ws_client, product_ids):
    """Initializes and starts the WebSocket client in a separate thread."""
    if not product_ids:
        logging.warning("No products to subscribe to for WebSocket.")
        return
        
    def run_ws():
        ws_client.open()
        ws_client.subscribe(product_ids=product_ids, channels=["ticker"])
        logging.info(f"Subscribed to ticker for: {product_ids}")
        ws_client.run_forever_with_exception_check()
        ws_client.close()

    ws_thread = Thread(target=run_ws, name="WebSocketThread", daemon=True)
    ws_thread.start()
    logging.info("WebSocket client thread started.")
    time.sleep(5) 

# ==============================================================================
# SECTION 3: TRADING STRATEGY & SIGNAL GENERATION
# ==============================================================================

def check_signals(df: pd.DataFrame) -> str:
    """
    Analyzes the DataFrame with technical indicators and returns a trading signal.
    """
    if df.empty or len(df) < 26: 
        return 'HOLD'

    try:
        df.ta.bbands(length=20, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.rsi(length=14, append=True)
    except Exception as e:
        logging.error(f"Error calculating technical indicators: {e}")
        return 'HOLD'

    df.dropna(inplace=True)
    if len(df) < 2: 
        return 'HOLD'

    latest = df.iloc[-1]
    previous = df.iloc[-2]
    
    upper_bb_col = 'BBU_20_2.0'
    middle_bb_col = 'BBM_20_2.0'
    macd_col = 'MACD_12_26_9'
    macd_signal_col = 'MACDs_12_26_9'
    rsi_col = 'RSI_14'

    macd_crossed_up = (latest[macd_col] > latest[macd_signal_col]) and \
                      (previous[macd_col] <= previous[macd_signal_col])

    if (latest['Close'] > latest[upper_bb_col] and
        macd_crossed_up and
        50 < latest[rsi_col] < 70):
        logging.info(f"BUY SIGNAL DETECTED for {df.name}: Close={latest['Close']:.2f}, Upper BB={latest[upper_bb_col]:.2f}, MACD Cross=True, RSI={latest[rsi_col]:.2f}")
        return 'BUY'

    macd_crossed_down = (latest[macd_col] < latest[macd_signal_col]) and \
                        (previous[macd_col] >= previous[macd_signal_col])

    if (latest['Close'] < latest[middle_bb_col] or
        macd_crossed_down or
        latest[rsi_col] > 75):
        logging.info(f"SELL SIGNAL DETECTED for {df.name}: Close={latest['Close']:.2f}, Middle BB={latest[middle_bb_col]:.2f}, MACD Cross Down={macd_crossed_down}, RSI={latest[rsi_col]:.2f}")
        return 'SELL'

    return 'HOLD'

# ==============================================================================
# SECTION 4: TRADE EXECUTION & RISK MANAGEMENT
# ==============================================================================

def execute_buy_order(client: RESTClient, product_id_to_buy: str, balances: dict, product_details: dict):
    """
    Executes a crypto-to-crypto buy order implementing:
    - 1% risk sizing (RISK_PERCENT)
    - atomic bracket order (entry + stop loss + take profit) when not in PAPER_TRADING_MODE
    - order tracking and basic reconciliation
    """
    base_currency, quote_currency = product_id_to_buy.split('-')

    quote_balance = balances.get(quote_currency)
    if not quote_balance or Decimal(quote_balance) <= 0:
        logging.warning(f"Cannot execute buy for {product_id_to_buy}: No balance for source currency {quote_currency}.")
        return

    # Estimate total equity in quote currency (attempt USD conversion if possible)
    total_equity = get_total_equity(balances, preferred_quote=quote_currency)
    if total_equity <= 0:
        logging.warning("Total equity calculation failed or is zero; aborting buy.")
        return

    # Determine entry price from latest_prices fallback
    entry_price = latest_prices.get(product_id_to_buy)
    if not entry_price:
        # Try to fetch a last price via REST fallback
        try:
            prod = client.get_product(product_id=product_id_to_buy)
            entry_price = Decimal(prod.price) if getattr(prod, "price", None) else None
        except Exception:
            entry_price = None

    if not entry_price:
        logging.warning(f"No entry price available for {product_id_to_buy}; skipping buy.")
        return
    entry_price = Decimal(entry_price)

    # Calculate stop-loss and take-profit prices
    stop_loss_price = (entry_price * (Decimal(1) - DEFAULT_STOP_LOSS_PCT)).quantize(Decimal('0.00000001'))
    take_profit_price = (entry_price * (Decimal(1) + DEFAULT_TAKE_PROFIT_PCT)).quantize(Decimal('0.00000001'))

    # Position sizing using 1% risk rule
    risk_amount = (total_equity * RISK_PERCENT).quantize(Decimal('0.00000001'))
    # risk_per_unit = entry_price - stop_loss_price
    risk_per_unit = (entry_price - stop_loss_price)
    if risk_per_unit <= 0:
        logging.warning("Calculated non-positive risk per unit; aborting buy.")
        return

    position_size_base = (risk_amount / risk_per_unit).quantize(Decimal('0.00000001'))
    # Ensure position respects minimums
    min_size = product_details.get(product_id_to_buy, {}).get("base_min_size", Decimal('0'))
    if position_size_base < min_size:
        logging.warning(f"Calculated position size {position_size_base} is below min_size {min_size}; aborting buy.")
        return

    client_order_id = str(uuid.uuid4())
    logging.info(f"Placing bracket BUY for {product_id_to_buy}: size={position_size_base} entry={entry_price} SL={stop_loss_price} TP={take_profit_price} (client_order_id={client_order_id})")

    # Paper-trade mode: simulate immediate fill and update simulated_positions
    if PAPER_TRADING_MODE:
        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id_to_buy,
                "type": "bracket_buy",
                "status": "filled",  # simulate immediate fill
                "base_size": position_size_base,
                "entry_price": entry_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "timestamp": datetime.utcnow().isoformat()
            }
            simulated_positions[product_id_to_buy] = {
                "base_size": position_size_base,
                "entry_price": entry_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price
            }
            bot_state["positions"][product_id_to_buy] = True
        logging.info(f"[PAPER] Simulated bracket BUY placed and filled for {product_id_to_buy}: {orders[client_order_id]}")
        return

    # Live mode: attempt to place an atomic bracket order via SDK
    try:
        # Using an SDK bracket order method (name may vary by SDK)
        order = client.trigger_bracket_order_gtc_buy(
            client_order_id=client_order_id,
            product_id=product_id_to_buy,
            base_size=str(position_size_base),
            stop_loss=str(stop_loss_price),
            limit_price=str(take_profit_price)
        )

        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id_to_buy,
                "type": "bracket_buy",
                "status": "submitted",
                "client_response": order
            }

        # Basic success handling: if SDK returns success and an immediate fill flag, mark position
        if getattr(order, "success", False) or getattr(order, "order_state", "") == "filled":
            with state_lock:
                bot_state["positions"][product_id_to_buy] = True
                orders[client_order_id]["status"] = "filled"
            logging.info(f"Bracket BUY executed and marked filled for {product_id_to_buy} (client_order_id={client_order_id})")
        else:
            logging.info(f"Bracket BUY submitted for {product_id_to_buy} (client_order_id={client_order_id}). Awaiting fills. Response: {order}")

    except Exception as e:
        logging.error(f"Exception during BRACKET BUY order execution for {product_id_to_buy}: {e}", exc_info=True)
        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id_to_buy,
                "type": "bracket_buy",
                "status": "error",
                "error": str(e)
            }

def execute_sell_order(client: RESTClient, product_id: str, base_balance: Decimal, product_details: dict):
    """
    Executes a crypto-to-crypto sell order. In live mode this will place a market sell
    and attempt to cancel associated stop/take orders. In paper mode this simulates the sell.
    """
    if base_balance <= 0:
        logging.warning(f"Attempted to sell {product_id} with zero base currency balance.")
        return

    # Check against minimum base size
    min_size = product_details.get(product_id, {}).get("base_min_size", Decimal('0'))
    if base_balance < min_size:
        logging.warning(f"SELL order for {product_id} skipped. Balance {base_balance:.8f} is below minimum trade size of {min_size}.")
        return

    logging.info(f"Attempting to place SELL order for {product_id}: base_size={base_balance}")

    client_order_id = str(uuid.uuid4())

    # Paper-trade: simulate immediate sell and clear simulated position
    if PAPER_TRADING_MODE:
        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id,
                "type": "market_sell",
                "status": "filled",
                "base_size": base_balance,
                "timestamp": datetime.utcnow().isoformat()
            }
            if product_id in simulated_positions:
                del simulated_positions[product_id]
            bot_state["positions"][product_id] = False
        logging.info(f"[PAPER] Simulated market SELL filled for {product_id}: {orders[client_order_id]}")
        return

    try:
        order = client.market_order_sell(
            client_order_id=client_order_id,
            product_id=product_id,
            base_size=str(base_balance)  # Ensure proper formatting
        )

        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id,
                "type": "market_sell",
                "status": "submitted",
                "client_response": order
            }

        if getattr(order, "success", False) or getattr(order, "order_state", "") == "filled":
            with state_lock:
                bot_state["positions"][product_id] = False
                orders[client_order_id]["status"] = "filled"
            logging.info(f"Market SELL executed and marked filled for {product_id} (client_order_id={client_order_id})")
        else:
            logging.info(f"Market SELL submitted for {product_id} (client_order_id={client_order_id}). Response: {order}")

        # Optionally cancel associated protective orders if API exposes a cancel_orders method
        try:
            client.cancel_orders(product_id=product_id)
        except Exception:
            logging.debug("No cancel_orders method available or cancel failed; continuing.")

    except Exception as e:
        logging.error(f"Exception during SELL order execution for {product_id}: {e}", exc_info=True)
        with state_lock:
            orders[client_order_id] = {
                "product_id": product_id,
                "type": "market_sell",
                "status": "error",
                "error": str(e)
            }


# ==============================================================================
# SECTION 5: MAIN BOT LOGIC
# ==============================================================================

def main_loop(rest_client, ws_client):
    """The main function to run the trading bot."""
    portfolio_id = get_portfolio_id(rest_client)
    if not portfolio_id:
        logging.error("Could not get portfolio ID. Exiting.")
        return
    
    # Main trading loop
    while True:
        try:
            logging.info("--- New Trading Cycle ---")
            
            # 1. Get balances and find all possible tradable pairs
            balances = get_account_balances(rest_client, portfolio_id)
            if not balances:
                logging.warning("No balances found. Sleeping.")
                time.sleep(LOOP_SLEEP_SECONDS)
                continue

            tradable_products = find_tradable_products(rest_client, balances)
            if not tradable_products:
                logging.warning("No tradable crypto-to-crypto pairs found in portfolio. Sleeping.")
                time.sleep(LOOP_SLEEP_SECONDS)
                continue
            
            # Get trading rules for all potential products for this cycle
            product_details = get_product_details(rest_client, tradable_products)

            # 2. Scan all tradable products for signals
            for product_id in tradable_products:
                logging.info(f"--- Analyzing {product_id} ---")

                historical_df = get_historical_data(rest_client, product_id, CANDLE_GRANULARITY, CANDLE_PERIODS_FOR_ANALYSIS)
                if historical_df.empty:
                    # This is now the expected behavior for pairs with no data, so no warning needed.
                    continue
                
                historical_df.name = product_id # For logging purposes in check_signals

                signal = check_signals(historical_df)
                logging.info(f"Generated Signal for {product_id}: {signal}")

                # 3. Execute Trading Logic
                if signal == 'BUY':
                    # Prevent buying an asset you already hold a significant amount of
                    base_currency = product_id.split('-')[0]
                    if base_currency not in balances:
                        execute_buy_order(rest_client, product_id, balances, product_details)
                        # Break after one trade to re-evaluate on the next cycle with new balances
                        break 
                    else:
                        logging.info(f"Skipping BUY for {product_id} as {base_currency} is already in portfolio.")
                
                elif signal == 'SELL':
                    base_currency = product_id.split('-')[0]
                    base_balance = balances.get(base_currency, Decimal(0))
                    if base_balance > 0:
                        execute_sell_order(rest_client, product_id, base_balance, product_details)
                        # Break after one trade to re-evaluate
                        break
                else:
                    logging.info(f"Holding or waiting for a signal on {product_id}.")
            
            logging.info(f"--- Cycle End. Sleeping for {LOOP_SLEEP_SECONDS} seconds. ---")
            time.sleep(LOOP_SLEEP_SECONDS)

        except KeyboardInterrupt:
            logging.info("Shutdown signal received. Closing WebSocket and exiting.")
            if ws_client:
                ws_client.close()
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(LOOP_SLEEP_SECONDS)

def initial_setup_and_start():
    """Handles one-time setup before starting the main loop."""
    logging.info("--- Trading Bot Starting ---")
    rest_client, ws_client = initialize_api_clients()
    if not rest_client or not ws_client:
        return

    portfolio_id = get_portfolio_id(rest_client)
    if not portfolio_id:
        return
        
    initial_balances = get_account_balances(rest_client, portfolio_id)
    tradable_products = find_tradable_products(rest_client, initial_balances)
    
    start_websocket(ws_client, tradable_products)
    
    main_loop(rest_client, ws_client)


if __name__ == "__main__":
    print("Disclaimer: This trading bot is for educational purposes only.")
    print("It is not financial advice. Trading cryptocurrency involves significant risk.")
    print("Use this script at your own risk.\n")
    initial_setup_and_start()
