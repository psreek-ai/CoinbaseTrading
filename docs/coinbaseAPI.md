# Coinbase Advanced API SDK Capabilities

This document details the complete capabilities of the Coinbase Advanced API as exposed by the `coinbase-advanced-py` Python SDK. It is based on a review of the SDK's source code, including its REST and WebSocket clients.

## Introduction

The `coinbase-advanced-py` SDK provides two primary clients for interacting with the Coinbase Advanced API:
1.  **`RESTClient`**: For accessing authenticated and public REST API endpoints. This client is used for managing accounts, placing orders, and retrieving historical data.
2.  **`WSClient` / `WSUserClient`**: For subscribing to real-time data feeds via WebSockets, including public market data and private user account updates.

---

## Authentication

The SDK handles authentication automatically when API keys are provided. You can provide credentials in three ways:

1.  **Environment Variables**: By setting `COINBASE_API_KEY` and `COINBASE_API_SECRET`.
2.  **Constructor Arguments**: By passing `api_key` and `api_secret` directly to the client constructor.
3.  **Key File**: By passing a `key_file` (either a file path or a file-like object) containing the JSON-formatted API key and secret to the constructor.

For users who need to generate JWTs manually, the SDK provides a `jwt_generator` module:

* `build_rest_jwt(uri, key_var, secret_var)`: Builds a JWT token for a specific REST API endpoint.
* `build_ws_jwt(key_var, secret_var)`: Builds a JWT token for authenticating a WebSocket connection.
* `format_jwt_uri(method, path)`: A helper function to correctly format the URI required for the REST JWT.

---

## 1. REST API Capabilities (`RESTClient`)

The `RESTClient` class provides methods for a wide range of trading and account management functions.

### Accounts

Manage your portfolios and account balances.
* `get_accounts(limit, cursor, retail_portfolio_id)`: Gets a list of all authenticated accounts for the current user.
* `get_account(account_uuid)`: Gets detailed information for a single account by its UUID.

### Products & Market Data

Access product information and market data. This section includes both authenticated (private) and unauthenticated (public) endpoints.

**Authenticated Endpoints:**
* `get_products(...)`: Lists available currency pairs for trading with various filters like `product_type`, `product_ids`, and `limit`.
* `get_product(product_id, ...)`: Gets information for a single product by its ID.
* `get_product_book(product_id, limit, ...)`: Gets the order book (bids and asks) for a single product.
* `get_best_bid_ask(product_ids)`: Gets the best (top-level) bid and ask for one or more products.
* `get_candles(product_id, start, end, granularity, ...)`: Gets historical candlestick (OHLCV) data for a single product within a time range.
* `get_market_trades(product_id, limit, start, end, ...)`: Gets a snapshot of the last trades (ticks) for a single product.

**Public (Unauthenticated) Endpoints:**
The SDK provides public-facing methods that do not require authentication.
* `get_unix_time()`: Gets the current API server time.
* `get_public_products(...)`: Gets a list of available currency pairs (public version).
* `get_public_product(product_id)`: Gets information on a single product (public version).
* `get_public_product_book(product_id, limit, ...)`: Gets the order book for a single product (public version).
* `get_public_candles(product_id, start, end, granularity, ...)`: Gets historical candlestick data (public version).
* `get_public_market_trades(product_id, limit, ...)`: Gets recent trades (public version).

### Orders

This is the most comprehensive capability, allowing for full order lifecycle management.

**Order Creation:**
The SDK provides a base `create_order` function and numerous helpers for specific order types.

* **Market Orders**:
    * `market_order(client_order_id, product_id, side, ...)`: Base function for market orders.
    * `market_order_buy(client_order_id, product_id, quote_size, ...)`: Places a market buy order.
    * `market_order_sell(client_order_id, product_id, base_size, ...)`: Places a market sell order.
* **Limit Orders (Good-Till-Cancelled - GTC)**:
    * `limit_order_gtc(client_order_id, product_id, side, base_size, limit_price, ...)`
    * `limit_order_gtc_buy(...)`
    * `limit_order_gtc_sell(...)`
* **Limit Orders (Good-Till-Date - GTD)**:
    * `limit_order_gtd(client_order_id, product_id, side, base_size, limit_price, end_time, ...)`
    * `limit_order_gtd_buy(...)`
    * `limit_order_gtd_sell(...)`
* **Limit Orders (Immediate-or-Cancel - IOC)**:
    * `limit_order_ioc(client_order_id, product_id, side, base_size, limit_price, ...)`
    * `limit_order_ioc_buy(...)`
    * `limit_order_ioc_sell(...)`
* **Limit Orders (Fill-or-Kill - FOK)**:
    * `limit_order_fok(client_order_id, product_id, side, base_size, limit_price, ...)`
    * `limit_order_fok_buy(...)`
    * `limit_order_fok_sell(...)`
* **Stop-Limit Orders (GTC)**:
    * `stop_limit_order_gtc(client_order_id, product_id, side, base_size, limit_price, stop_price, ...)`
    * `stop_limit_order_gtc_buy(...)`
    * `stop_limit_order_gtc_sell(...)`
* **Stop-Limit Orders (GTD)**:
    * `stop_limit_order_gtd(client_order_id, product_id, side, base_size, limit_price, stop_price, end_time, ...)`
    * `stop_limit_order_gtd_buy(...)`
    * `stop_limit_order_gtd_sell(...)`
* **Trigger Bracket Orders (GTC)**:
    * `trigger_bracket_order_gtc(client_order_id, product_id, side, base_size, limit_price, stop_trigger_price, ...)`
    * `trigger_bracket_order_gtc_buy(...)`
    * `trigger_bracket_order_gtc_sell(...)`
* **Trigger Bracket Orders (GTD)**:
    * `trigger_bracket_order_gtd(client_order_id, product_id, side, base_size, limit_price, stop_trigger_price, end_time, ...)`
    * `trigger_bracket_order_gtd_buy(...)`
    * `trigger_bracket_order_gtd_sell(...)`

**Order Preview:**
All order types have a corresponding `preview_` method (e.g., `preview_market_order`, `preview_limit_order_gtc`, `preview_stop_limit_order_gtd`) that allows you to simulate the order and see fees, slippage, and totals before executing.

**Order & Position Management:**
* `list_orders(...)`: Lists historical orders with filters like `product_ids`, `order_status`, `limit`, etc..
* `get_order(order_id)`: Retrieves a single order by its ID.
* `get_fills(...)`: Lists historical fills with filters like `order_ids`, `product_ids`, `limit`, etc..
* `edit_order(order_id, size, price)`: Edits an existing order.
* `preview_edit_order(order_id, size, price)`: Simulates an order edit.
* `cancel_orders(order_ids)`: Cancels one or more open orders.
* `close_position(client_order_id, product_id, size)`: Places an order to close an open position for a product.

### Portfolios

Manage your retail portfolios.
* `get_portfolios(portfolio_type)`: Lists all portfolios for a user.
* `create_portfolio(name)`: Creates a new portfolio.
* `get_portfolio_breakdown(portfolio_uuid, ...)`: Gets the breakdown of a specific portfolio.
* `move_portfolio_funds(value, currency, source_portfolio_uuid, target_portfolio_uuid)`: Transfers funds between two portfolios.
* `edit_portfolio(portfolio_uuid, name)`: Modifies a portfolio's name.
* `delete_portfolio(portfolio_uuid)`: Deletes a portfolio by its ID.

### Futures (CFM - Coinbase Financial Markets)

Manage regulated futures trading.
* `get_futures_balance_summary()`: Gets the futures balance summary for your account.
* `list_futures_positions()`: Lists all open positions in CFM futures products.
* `get_futures_position(product_id)`: Gets the position for a specific CFM futures product.
* `schedule_futures_sweep(usd_amount)`: Schedules a sweep of funds from your futures account to your spot wallet.
* `list_futures_sweeps()`: Lists pending or processing sweeps.
* `cancel_pending_futures_sweep()`: Cancels any pending fund sweep.
* `get_intraday_margin_setting()`: Gets the status of your intraday margin setting.
* `get_current_margin_window(margin_profile_type)`: Gets the current margin window (intraday or overnight).
* `set_intraday_margin_setting(setting)`: Opts in or out of intraday margin leverage.

### Perpetuals (INTX)

Manage perpetual futures trading.
* `allocate_portfolio(portfolio_uuid, symbol, amount, currency)`: Allocates more funds to an isolated position.
* `get_perps_portfolio_summary(portfolio_uuid)`: Gets a summary of your perpetuals portfolio.
* `list_perps_positions(portfolio_uuid)`: Lists open positions in your perpetuals portfolio.
* `get_perps_position(portfolio_uuid, symbol)`: Gets a specific open position.
* `get_perps_portfolio_balances(portfolio_uuid)`: Gets asset balances for a given portfolio.
* `opt_in_or_out_multi_asset_collateral(portfolio_uuid, multi_asset_collateral_enabled)`: Enables or disables multi-asset collateral.

### Converts

Handle crypto-to-crypto conversions.
* `create_convert_quote(from_account, to_account, amount, ...)`: Creates a convert quote for a specified amount.
* `get_convert_trade(trade_id, from_account, to_account)`: Gets information about a specific convert trade.
* `commit_convert_trade(trade_id, from_account, to_account)`: Commits a convert trade created with `create_convert_quote`.

### Payments

Manage your linked payment methods.
* `list_payment_methods()`: Gets a list of all payment methods for the current user.
* `get_payment_method(payment_method_id)`: Gets information for a specific payment method by its ID.

### Fees

Retrieve information on your transaction fees.
* `get_transaction_summary(...)`: Gets a summary of transactions, fee tiers, total volume, and fees.

### API Key Management

* `get_api_key_permissions()`: Gets information about the permissions of the API key being used.

### Generic (Base) Methods

For endpoints not yet implemented as helper functions, you can use the base request methods:
* `get(url_path, params, ...)`
* `post(url_path, data, ...)`
* `put(url_path, data, ...)`
* `delete(url_path, ...)`

---

## 2. WebSocket API Capabilities (`WSClient` / `WSUserClient`)

The SDK provides clients for real-time data streaming. `WSClient` can access all channels, while `WSUserClient` is pre-configured for the private user-only channels (`user` and `futures_balance_summary`).

### Client Connection & Management

The client provides methods to manage the WebSocket lifecycle:
* `open()` / `open_async()`: Opens the connection.
* `close()` / `close_async()`: Closes the connection.
* `subscribe(product_ids, channels)` / `subscribe_async(...)`: Subscribes to one or more channels for a list of products.
* `unsubscribe(product_ids, channels)` / `unsubscribe_async(...)`: Unsubscribes from channels.
* `unsubscribe_all()` / `unsubscribe_all_async()`: Unsubscribes from all current subscriptions.
* **Callbacks**: The constructor accepts `on_message`, `on_open`, and `on_close` functions to handle events.
* **Error Handling**: The client features automatic retries on disconnection (which can be disabled) and provides methods like `run_forever_with_exception_check()` to catch exceptions in the main thread.

### Public Data Channels

These channels are available via the `WSClient` and do not require authentication (though authentication is supported). For each, the SDK provides `[channel]()`, `[channel]_async()`, `[channel]_unsubscribe()`, and `[channel]_unsubscribe_async()` methods.

* **`heartbeats`**: A keep-alive signal.
* **`candles`**: Real-time OHLCV (candlestick) data.
* **`market_trades`**: A live feed of all executed trades for a product.
* **`status`**: Real-time updates on product trading status (online, offline, auction, etc.).
* **`ticker`**: 24-hour statistics, best bid/ask, and last trade price.
* **`ticker_batch`**: A batched version of the `ticker` channel for lower-latency.
* **`level2`**: Real-time, full order book (Level 2) data, including updates as they happen.

### Private (Authenticated) Data Channels

These channels require authentication and provide data specific to your account. They are available on both `WSClient` and `WSUserClient`.

* **`user`**: Provides real-time updates on your own orders (placed, filled, canceled) and positions. This is essential for event-driven trading.
* **`futures_balance_summary`**: Pushes real-time updates of your futures account balance.

### WebSocket Message Structure

The `on_message` callback receives a raw JSON message. The SDK provides a `WebsocketResponse` class to easily parse this message.

A typical `WebsocketResponse` object has the following top-level attributes:
* `channel`: The name of the channel that sent the message (e.g., "ticker", "user").
* `client_id`: A unique client identifier.
* `timestamp`: The time the message was sent.
* `sequence_num`: A sequential number for message ordering.
* `events`: A list containing the actual data payload(s).

The structure of the objects inside the `events` list depends on the `channel`. For example:
* **`candles` channel**: `events` contains a list of `WSCandle` objects.
* **`ticker` channel**: `events` contains a list of `WSTicker` objects.
* **`user` channel**: `events` contains a list of `UserOrders` or `UserPositions` objects.
* **`futures_balance_summary` channel**: `events` contains a `WSFCMBalanceSummary` object.