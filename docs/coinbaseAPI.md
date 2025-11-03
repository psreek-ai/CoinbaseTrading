# Coinbase Advanced API SDK: Granular Capabilities Reference

This document provides a detailed, granular reference of all classes, methods, parameters, and response objects available in the `coinbase-advanced-py` SDK, based on the repository source code.

## 1. REST API Client (`RESTClient`)

This is the primary client for making REST API calls for trading, account management, and data retrieval.

### `RESTClient` Constructor

The client is initialized with the following parameters:

```python
RESTClient(
    api_key: Optional[str] = os.getenv(API_ENV_KEY),
    api_secret: Optional[str] = os.getenv(API_SECRET_ENV_KEY),
    key_file: Optional[Union[IO, str]] = None,
    base_url: str = "api.coinbase.com",
    timeout: Optional[int] = None,
    verbose: Optional[bool] = False,
    rate_limit_headers: Optional[bool] = False
)
````

  * **`api_key`**: Your CDP API Key.
  * **`api_secret`**: Your CDP API Secret (private key).
  * **`key_file`**: Path to or file-like object of the JSON key file downloaded from CDP.
  * **`base_url`**: The base URL for API requests.
  * **`timeout`**: Optional request timeout in seconds.
  * **`verbose`**: Enables debug-level logging.
  * **`rate_limit_headers`**: If `True`, appends rate limit headers (`x-ratelimit-remaining`, etc.) to the JSON response body.

### Base REST Methods

These generic methods are available to call any endpoint.

  * `get(url_path, params: Optional[dict] = None, public=False, **kwargs)`: Performs a GET request.
  * `post(url_path, params: Optional[dict] = None, data: Optional[dict] = None, **kwargs)`: Performs a POST request.
  * `put(url_path, params: Optional[dict] = None, data: Optional[dict] = None, **kwargs)`: Performs a PUT request.
  * `delete(url_path, params: Optional[dict] = None, data: Optional[dict] = None, **kwargs)`: Performs a DELETE request.

-----

### API Capabilities (by Module)

#### Accounts

  * **`get_accounts(limit: Optional[int] = None, cursor: Optional[str] = None, retail_portfolio_id: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/accounts`
      * **Returns**: `ListAccountsResponse`
          * `accounts: List[Account]`
          * `has_next: Optional[bool]`
          * `cursor: Optional[str]`
          * `size: Optional[int]`
  * **`get_account(account_uuid: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/accounts/{account_uuid}`
      * **Returns**: `GetAccountResponse`
          * `account: Optional[Account]`

**Nested Response Objects (Accounts):**

  * **`Account`**:
      * `uuid: Optional[str]`
      * `name: Optional[str]`
      * `currency: Optional[str]`
      * `available_balance: Optional[Amount]`
      * `default: Optional[bool]`
      * `active: Optional[bool]`
      * `created_at: Optional[str]`
      * `updated_at: Optional[str]`
      * `deleted_at: Optional[str]`
      * `type: Optional[str]`
      * `ready: Optional[bool]`
      * `hold: Optional[Dict[str, Any]]`
      * `retail_portfolio_id: Optional[str]`
      * `platform: Optional[str]`
  * **`Amount`** (Common Type):
      * `value: Optional[str]`
      * `currency: Optional[str]`

-----

#### Products, Market Data, & Public Endpoints

  * **`get_products(limit: Optional[int] = None, offset: Optional[int] = None, product_type: Optional[str] = None, product_ids: Optional[List[str]] = None, contract_expiry_type: Optional[str] = None, expiring_contract_status: Optional[str] = None, get_tradability_status: Optional[bool] = False, get_all_products: Optional[bool] = False, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/products`
      * **Returns**: `ListProductsResponse`
          * `products: Optional[List[Product]]`
          * `num_products: Optional[int]`

  * **`get_product(product_id: str, get_tradability_status: Optional[bool] = False, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/products/{product_id}`
      * **Returns**: `GetProductResponse` (Contains all fields from the `Product` object below)

  * **`get_product_book(product_id: str, limit: Optional[int] = None, aggregation_price_increment: Optional[str] = None, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/product_book`
      * **Returns**: `GetProductBookResponse`
          * `pricebook: PriceBook`
          * `last: Optional[str]`
          * `mid_market: Optional[str]`
          * `spread_bps: Optional[str]`
          * `spread_absolute: Optional[str]`

  * **`get_best_bid_ask(product_ids: Optional[List[str]] = None, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/best_bid_ask`
      * **Returns**: `GetBestBidAskResponse`
          * `pricebooks: Optional[List[PriceBook]]`

  * **`get_candles(product_id: str, start: str, end: str, granularity: str, limit: Optional[int] = None, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/products/{product_id}/candles`
      * **Returns**: `GetProductCandlesResponse`
          * `candles: Optional[List[Candle]]`

  * **`get_market_trades(product_id: str, limit: int, start: Optional[str] = None, end: Optional[str] = None, **kwargs)`**

      * **Endpoint**: `[GET] /api/v3/brokerage/products/{product_id}/ticker`
      * **Returns**: `GetMarketTradesResponse`
          * `trades: Optional[List[HistoricalMarketTrade]]`
          * `best_bid: Optional[str]`
          * `best_ask: Optional[str]`

  * **`get_unix_time(**kwargs)`** (Public)

      * **Endpoint**: `[GET] /api/v3/brokerage/time`
      * **Returns**: `GetServerTimeResponse`
          * `iso: Optional[str]`
          * `epochSeconds: Optional[int]`
          * `epochMillis: Optional[int]`

  * **Public Endpoint Variants**:

      * `get_public_product_book(...)` -\> `GetProductBookResponse`
      * `get_public_products(...)` -\> `ListProductsResponse`
      * `get_public_product(...)` -\> `GetProductResponse`
      * `get_public_candles(...)` -\> `GetProductCandlesResponse`
      * `get_public_market_trades(...)` -\> `GetMarketTradesResponse`

**Nested Response Objects (Products):**

  * **`Product`**:
      * `product_id: str`
      * `price: str`
      * `price_percentage_change_24h: str`
      * `volume_24h: str`
      * `volume_percentage_change_24h: str`
      * `base_increment: str`
      * `quote_increment: str`
      * `quote_min_size: str`
      * `quote_max_size: str`
      * `base_min_size: str`
      * `base_max_size: str`
      * `base_name: str`
      * `quote_name: str`
      * `watched: bool`
      * `is_disabled: bool`
      * `new: bool`
      * `status: str`
      * `cancel_only: bool`
      * `limit_only: bool`
      * `post_only: bool`
      * `trading_disabled: bool`
      * `auction_mode: bool`
      * `product_type: Optional[str]`
      * `quote_currency_id: Optional[str]`
      * `base_currency_id: Optional[str]`
      * `fcm_trading_session_details: Optional[Dict[str, Any]]`
      * `mid_market_price: Optional[str]`
      * `alias: Optional[str]`
      * `alias_to: Optional[List[str]]`
      * `base_display_symbol: str`
      * `quote_display_symbol: Optional[str]`
      * `view_only: Optional[bool]`
      * `price_increment: Optional[str]`
      * `display_name: Optional[str]`
      * `product_venue: Optional[str]`
      * `approximate_quote_24h_volume: Optional[str]`
      * `future_product_details: Optional[Dict[str, Any]]`
  * **`PriceBook`**:
      * `product_id: str`
      * `bids: List[L2Level]`
      * `asks: List[L2Level]`
      * `time: Optional[Dict[str, Any]]`
  * **`L2Level`**:
      * `price: str`
      * `size: str`
  * **`Candle`**:
      * `start: Optional[str]`
      * `low: Optional[str]`
      * `high: Optional[str]`
      * `open: Optional[str]`
      * `close: Optional[str]`
      * `volume: Optional[str]`
  * **`HistoricalMarketTrade`**:
      * `trade_id: Optional[str]`
      * `product_id: Optional[str]`
      * `price: Optional[str]`
      * `size: Optional[str]`
      * `time: Optional[str]`
      * `side: Optional[str]`
      * `exchange: Optional[str]`

-----

#### Orders

  * **`create_order(client_order_id: str, product_id: str, side: str, order_configuration, self_trade_prevention_id: Optional[str] = None, leverage: Optional[str] = None, margin_type: Optional[str] = None, retail_portfolio_id: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/orders`
      * **Returns**: `CreateOrderResponse`
          * `success: bool`
          * `failure_reason: Optional[Dict[str, Any]]`
          * `order_id: Optional[str]`
          * `success_response: Optional[CreateOrderSuccess]`
          * `error_response: Optional[CreateOrderError]`
          * `order_configuration: Optional[OrderConfiguration]`
  * **Order Creation Helpers**: These functions call `create_order` with a pre-filled `order_configuration`:
      * `market_order(...)`
      * `market_order_buy(client_order_id, product_id, quote_size, base_size, ...)`
      * `market_order_sell(client_order_id, product_id, base_size, ...)`
      * `limit_order_ioc(...)`
      * `limit_order_ioc_buy(client_order_id, product_id, base_size, limit_price, ...)`
      * `limit_order_ioc_sell(...)`
      * `limit_order_gtc(...)`
      * `limit_order_gtc_buy(client_order_id, product_id, base_size, limit_price, post_only, ...)`
      * `limit_order_gtc_sell(...)`
      * `limit_order_gtd(...)`
      * `limit_order_gtd_buy(client_order_id, product_id, base_size, limit_price, end_time, post_only, ...)`
      * `limit_order_gtd_sell(...)`
      * `limit_order_fok(...)`
      * `limit_order_fok_buy(client_order_id, product_id, base_size, limit_price, ...)`
      * `limit_order_fok_sell(...)`
      * `stop_limit_order_gtc(...)`
      * `stop_limit_order_gtc_buy(client_order_id, product_id, base_size, limit_price, stop_price, stop_direction, ...)`
      * `stop_limit_order_gtc_sell(...)`
      * `stop_limit_order_gtd(...)`
      * `stop_limit_order_gtd_buy(client_order_id, product_id, base_size, limit_price, stop_price, end_time, stop_direction, ...)`
      * `stop_limit_order_gtd_sell(...)`
      * `trigger_bracket_order_gtc(...)`
      * `trigger_bracket_order_gtc_buy(client_order_id, product_id, base_size, limit_price, stop_trigger_price, ...)`
      * `trigger_bracket_order_gtc_sell(...)`
      * `trigger_bracket_order_gtd(...)`
      * `trigger_bracket_order_gtd_buy(client_order_id, product_id, base_size, limit_price, stop_trigger_price, end_time, ...)`
      * `trigger_bracket_order_gtd_sell(...)`
  * **`cancel_orders(order_ids: List[str], **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/orders/batch_cancel`
      * **Returns**: `CancelOrdersResponse`
          * `results: Optional[List[CancelOrderObject]]`
  * **`edit_order(order_id: str, size: Optional[str] = None, price: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/vj/brokerage/orders/edit`
      * **Returns**: `EditOrderResponse`
          * `success: bool`
          * `success_response: Optional[EditOrderSuccess]`
          * `error_response: Optional[EditOrderError]`
          * `errors: Optional[List[EditOrderErrors]]`
  * **`preview_edit_order(order_id: str, size: Optional[str] = None, price: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/orders/edit_preview`
      * **Returns**: `EditOrderPreviewResponse`
          * `errors: List[EditOrderErrors]`
          * `slippage: Optional[str]`
          * `order_total: Optional[str]`
          * `commission_total: Optional[str]`
          * `quote_size: Optional[str]`
          * `base_size: Optional[str]`
          * `best_bid: Optional[str]`
          * `average_filled_price: Optional[str]`
  * **`list_orders(order_ids: Optional[List[str]] = None, product_ids: Optional[List[str]] = None, order_status: Optional[List[str]] = None, limit: Optional[int] = None, ...)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/orders/historical/batch`
      * **Returns**: `ListOrdersResponse`
          * `orders: List[Order]`
          * `sequence: Optional[int]`
          * `has_next: bool`
          * `cursor: Optional[str]`
  * **`get_fills(order_ids: Optional[List[str]] = None, trade_ids: Optional[List[str]] = None, product_ids: Optional[List[str]] = None, ...)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/orders/historical/fills`
      * **Returns**: `ListFillsResponse`
          * `fills: Optional[List[Fill]]`
          * `cursor: Optional[str]`
  * **`get_order(order_id: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/orders/historical/{order_id}`
      * **Returns**: `GetOrderResponse`
          * `order: Optional[Order]`
  * **`preview_order(product_id: str, side: str, order_configuration, leverage: Optional[str] = None, margin_type: Optional[str] = None, retail_portfolio_id: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/orders/preview`
      * **Returns**: `PreviewOrderResponse`
          * `order_total: str`
          * `commission_total: str`
          * `errs: List[Dict[str, Any]]`
          * `warning: List[Dict[str, Any]]`
          * `quote_size: str`
          * `base_size: str`
          * `best_bid: str`
          * `best_ask: str`
          * `leverage: Optional[str]`
          * `slippage: Optional[str]`
          * `preview_id: Optional[str]`
  * **Order Preview Helpers**: These functions call `preview_order` with a pre-filled `order_configuration`:
      * `preview_market_order(...)`
      * `preview_market_order_buy(...)`
      * `preview_market_order_sell(...)`
      * `preview_limit_order_ioc(...)`
      * `preview_limit_order_ioc_buy(...)`
      * `preview_limit_order_ioc_sell(...)`
      * `preview_limit_order_gtc(...)`
      * `preview_limit_order_gtc_buy(...)`
      * `preview_limit_order_gtc_sell(...)`
      * `preview_limit_order_gtd(...)`
      * `preview_limit_order_gtd_buy(...)`
      * `preview_limit_order_gtd_sell(...)`
      * `preview_limit_order_fok(...)`
      * `preview_limit_order_fok_buy(...)`
      * `preview_limit_order_fok_sell(...)`
      * `preview_stop_limit_order_gtc(...)`
      * `preview_stop_limit_order_gtc_buy(...)`
      * `preview_stop_limit_order_gtc_sell(...)`
      * `preview_stop_limit_order_gtd(...)`
      * `preview_stop_limit_order_gtd_buy(...)`
      * `preview_stop_limit_order_gtd_sell(...)`
      * `preview_trigger_bracket_order_gtc(...)`
      * `preview_trigger_bracket_order_gtc_buy(...)`
      * `preview_trigger_bracket_order_gtc_sell(...)`
      * `preview_trigger_bracket_order_gtd(...)`
      * `preview_trigger_bracket_order_gtd_buy(...)`
      * `preview_trigger_bracket_order_gtd_sell(...)`
  * **`close_position(client_order_id: str, product_id: str, size: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/orders/close_position`
      * **Returns**: `ClosePositionResponse` (Shares structure with `CreateOrderResponse`)

**Nested Response Objects (Orders):**

  * **`Order`**:
      * `order_id: str`
      * `product_id: str`
      * `user_id: str`
      * `order_configuration: OrderConfiguration`
      * `side: str`
      * `client_order_id: str`
      * `status: str`
      * `time_in_force: Optional[str]`
      * `created_time: str`
      * `completion_percentage: str`
      * `filled_size: Optional[str]`
      * `average_filled_price: str`
      * `fee: Optional[str]`
      * `number_of_fills: str`
      * `filled_value: Optional[str]`
      * `pending_cancel: bool`
      * `size_in_quote: bool`
      * `total_fees: str`
      * `total_value_after_fees: str`
      * `trigger_status: Optional[str]`
      * `order_type: Optional[str]`
      * `reject_reason: Optional[str]`
      * `settled: Optional[bool]`
      * `product_type: Optional[str]`
      * `leverage: Optional[str]`
      * `margin_type: Optional[str]`
      * `retail_portfolio_id: Optional[str]`
  * **`Fill`**:
      * `entry_id: str`
      * `trade_id: str`
      * `order_id: str`
      * `trade_time: str`
      * `trade_type: str`
      * `price: str`
      * `size: str`
      * `commission: str`
      * `product_id: str`
      * `sequence_timestamp: str`
      * `liquidity_indicator: str`
      * `size_in_quote: str`
      * `user_id: str`
      * `side: str`
      * `retail_portfolio_id: str`
  * **`OrderConfiguration`**: Contains one of the following objects:
      * `market_market_ioc: MarketMarketIoc` (`quote_size: str`, `base_size: str`)
      * `sor_limit_ioc: SorLimitIoc` (`base_size: str`, `limit_price: str`)
      * `limit_limit_gtc: LimitLimitGtc` (`base_size: str`, `limit_price: str`, `post_only: bool`)
      * `limit_limit_gtd: LimitLimitGtd` (`base_size: str`, `limit_price: str`, `end_time: str`, `post_only: bool`)
      * `limit_limit_fok: LimitLimitFok` (`base_size: str`, `limit_price: str`)
      * `stop_limit_stop_limit_gtc: StopLimitStopLimitGtc` (`base_size: str`, `limit_price: str`, `stop_price: str`, `stop_direction: str`)
      * `stop_limit_stop_limit_gtd: StopLimitStopLimitGtd` (`base_size: str`, `limit_price: str`, `stop_price: str`, `end_time: str`, `stop_direction: str`)
      * `trigger_bracket_gtc: TriggerBracketGtc` (`base_size: str`, `limit_price: str`, `stop_trigger_price: str`)
      * `trigger_bracket_gtd: TriggerBracketGtd` (`base_size: str`, `limit_price: str`, `stop_trigger_price: str`, `end_time: str`)

-----

#### Portfolios

  * **`get_portfolios(portfolio_type: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/portfolios`
      * **Returns**: `ListPortfoliosResponse`
          * `portfolios: Optional[List[Portfolio]]`
  * **`create_portfolio(name: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/portfolios`
      * **Returns**: `CreatePortfolioResponse`
          * `portfolio: Optional[Portfolio]`
  * **`get_portfolio_breakdown(portfolio_uuid: str, currency: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/portfolios/{portfolio_uuid}`
      * **Returns**: `GetPortfolioBreakdownResponse`
          * `breakdown: Optional[PortfolioBreakdown]`
  * **`move_portfolio_funds(value: str, currency: str, source_portfolio_uuid: str, target_portfolio_uuid: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/portfolios/move_funds`
      * **Returns**: `MovePortfolioFundsResponse`
          * `source_portfolio_uuid: Optional[str]`
          * `target_portfolio_uuid: Optional[str]`
  * **`edit_portfolio(portfolio_uuid: str, name: str, **kwargs)`**
      * **Endpoint**: `[PUT] /api/v3/brokerage/portfolios/{portfolio_uuid}`
      * **Returns**: `EditPortfolioResponse`
          * `portfolio: Optional[Portfolio]`
  * **`delete_portfolio(portfolio_uuid: str, **kwargs)`**
      * **Endpoint**: `[DELETE] /api/v3/brokerage/portfolios/{portfolio_uuid}`
      * **Returns**: `DeletePortfolioResponse`

**Nested Response Objects (Portfolios):**

  * **`Portfolio`**:
      * `name: Optional[str]`
      * `uuid: Optional[str]`
      * `type: Optional[str]`
  * **`PortfolioBreakdown`**:
      * `portfolio: Optional[Portfolio]`
      * `portfolio_balances: Optional[PortfolioBalances]`
      * `spot_positions: Optional[List[PortfolioPosition]]`
      * `perp_positions: Optional[List[PortfolioPosition]]`
      * `futures_positions: Optional[List[PortfolioPosition]]`
  * **`PortfolioBalances`**:
      * `total_balance: Optional[Amount]`
      * `total_futures_balance: Optional[Amount]`
      * `total_cash_equivalent_balance: Optional[Amount]`
      * `total_crypto_balance: Optional[Amount]`
  * **`PortfolioPosition`**:
      * `asset: Optional[str]`
      * `account_uuid: Optional[str]`
      * `total_balance_fiat: Optional[float]`
      * `total_balance_crypto: Optional[float]`
      * `available_to_trade_fiat: Optional[float]`
      * `allocation: Optional[float]`
      * `one_day_change: Optional[float]`
      * `cost_basis: Optional[Amount]`

-----

#### Futures (CFM)

  * **`get_futures_balance_summary(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/balance_summary`
      * **Returns**: `GetFuturesBalanceSummaryResponse`
          * `balance_summary: Optional[FCMBalanceSummary]`
  * **`list_futures_positions(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/positions`
      * **Returns**: `ListFuturesPositionsResponse`
          * `positions: Optional[List[FCMPosition]]`
  * **`get_futures_position(product_id: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/positions/{product_id}`
      * **Returns**: `GetFuturesPositionResponse`
          * `position: Optional[FCMPosition]`
  * **`schedule_futures_sweep(usd_amount: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/cfm/sweeps/schedule`
      * **Returns**: `ScheduleFuturesSweepResponse`
          * `success: Optional[bool]`
  * **`list_futures_sweeps(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/sweeps`
      * **Returns**: `ListFuturesSweepsResponse`
          * `sweeps: List[FCMSweep]`
  * **`cancel_pending_futures_sweep(**kwargs)`**
      * **Endpoint**: `[DELETE] /api/v3/brokerage/cfm/sweeps`
      * **Returns**: `CancelPendingFuturesSweepResponse`
          * `success: Optional[bool]`
  * **`get_intraday_margin_setting(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/intraday/margin_setting`
      * **Returns**: `GetIntradayMarginSettingResponse`
          * `setting: Optional[str]`
  * **`get_current_margin_window(margin_profile_type: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/cfm/intraday/current_margin_window`
      * **Returns**: `GetCurrentMarginWindowResponse`
          * `margin_window: Optional[MarginWindow]`
          * `is_intraday_margin_killswitch_enabled: Optional[bool]`
  * **`set_intraday_margin_setting(setting: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/cfm/intraday/margin_setting`
      * **Returns**: `SetIntradayMarginSettingResponse`

**Nested Response Objects (Futures):**

  * **`FCMBalanceSummary`**:
      * `futures_buying_power: Optional[Amount]`
      * `total_usd_balance: Optional[Amount]`
      * `cbi_usd_balance: Optional[Amount]`
      * `cfm_usd_balance: Optional[Amount]`
      * `total_open_orders_hold_amount: Optional[Amount]`
      * `unrealized_pnl: Optional[Amount]`
      * `daily_realized_pnl: Optional[Amount]`
      * `initial_margin: Optional[Amount]`
      * `available_margin: Optional[Amount]`
      * `liquidation_threshold: Optional[Amount]`
      * `liquidation_buffer_amount: Optional[Amount]`
      * `liquidation_buffer_percentage: Optional[str]`
  * **`FCMPosition`**:
      * `product_id: Optional[str]`
      * `expiration_time: Optional[Dict[str, Any]]`
      * `side: Optional[str]`
      * `number_of_contracts: Optional[str]`
      * `current_price: Optional[str]`
      * `avg_entry_price: Optional[str]`
      * `unrealized_pnl: Optional[str]`
      * `daily_realized_pnl: Optional[str]`
  * **`FCMSweep`**:
      * `id: str`
      * `requested_amount: Amount`
      * `status: str`
      * `schedule_time: Dict[str, Any]`
  * **`MarginWindow`**:
      * `margin_window_type: str`
      * `end_time: str`

-----

#### Perpetuals (INTX)

  * **`allocate_portfolio(portfolio_uuid: str, symbol: str, amount: str, currency: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/intx/allocate`
      * **Returns**: `AllocatePortfolioResponse` (Empty body on success)
  * **`get_perps_portfolio_summary(portfolio_uuid: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/intx/portfolio/{portfolio_uuid}`
      * **Returns**: `GetPerpetualsPortfolioSummaryResponse`
          * `portfolios: Optional[List[PerpetualPortfolio]]`
          * `summary: Optional[PortfolioSummary]`
  * **`list_perps_positions(portfolio_uuid: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/intx/positions/{portfolio_uuid}`
      * **Returns**: `ListPerpetualsPositionsResponse`
          * `positions: Optional[List[Position]]`
          * `summary: Optional[PositionSummary]`
  * **`get_perps_position(portfolio_uuid: str, symbol: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/intx/positions/{portfolio_uuid}/{symbol}`
      * **Returns**: `GetPerpetualsPositionResponse`
          * `position: Optional[Position]`
  * **`get_perps_portfolio_balances(portfolio_uuid: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/intx/balances/{portfolio_uuid}`
      * **Returns**: `GetPortfolioBalancesResponse`
          * `portfolio_balances: Optional[List[PortfolioBalance]]`
  * **`opt_in_or_out_multi_asset_collateral(portfolio_uuid: str, multi_asset_collateral_enabled: bool, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/intx/multi_asset_collateral`
      * **Returns**: `OptInOutMultiAssetCollateralResponse`
          * `cross_collateral_enabled: Optional[bool]`

**Nested Response Objects (Perpetuals):**

  * **`PerpetualPortfolio`**:
      * `portfolio_uuid: Optional[str]`
      * `collateral: Optional[str]`
      * `position_notional: Optional[str]`
      * `open_position_notional: Optional[str]`
      * `portfolio_initial_margin: Optional[str]`
      * `portfolio_maintenance_margin: Optional[str]`
      * `unrealized_pnl: Optional[Amount]`
      * `total_balance: Optional[Amount]`
  * **`PortfolioSummary`**:
      * `unrealized_pnl: Optional[Amount]`
      * `buying_power: Optional[Amount]`
      * `total_balance: Optional[Amount]`
      * `max_withdrawal_amount: Optional[Amount]`
  * **`Position`**:
      * `product_id: Optional[str]`
      * `portfolio_uuid: Optional[str]`
      * `symbol: Optional[str]`
      * `vwap: Optional[Amount]`
      * `entry_vwap: Optional[Amount]`
      * `position_side: Optional[str]`
      * `margin_type: Optional[str]`
      * `net_size: Optional[str]`
      * `buy_order_size: Optional[str]`
      * `sell_order_size: Optional[str]`
      * `im_contribution: Optional[str]`
      * `unrealized_pnl: Optional[Amount]`
      * `mark_price: Optional[Amount]`
      * `liquidation_price: Optional[Amount]`
      * `leverage: Optional[str]`
      * `position_notional: Optional[Amount]`
  * **`PortfolioBalance`**:
      * `portfolio_uuid: Optional[str]`
      * `balances: Optional[List[Balance]]`
  * **`Balance`**:
      * `asset: Dict[str, Any]`
      * `quantity: str`
      * `hold: str`
      * `collateral_value: str`
      * `collateral_weight: str`
      * `max_withdraw_amount: str`

-----

#### Converts

  * **`create_convert_quote(from_account: str, to_account: str, amount: str, user_incentive_id: Optional[str] = None, code_val: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/convert/quote`
      * **Returns**: `CreateConvertQuoteResponse`
          * `trade: Optional[ConvertTrade]`
  * **`get_convert_trade(trade_id: str, from_account: str, to_account: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/convert/trade/{trade_id}`
      * **Returns**: `GetConvertTradeResponse`
          * `trade: Optional[ConvertTrade]`
  * **`commit_convert_trade(trade_id: str, from_account: str, to_account: str, **kwargs)`**
      * **Endpoint**: `[POST] /api/v3/brokerage/convert/trade/{trade_id}`
      * **Returns**: `CommitConvertTradeResponse`
          * `trade: Optional[ConvertTrade]`

**Nested Response Objects (Converts):**

  * **`ConvertTrade`**:
      * `id: Optional[str]`
      * `status: Optional[str]`
      * `user_entered_amount: Optional[Amount]`
      * `amount: Optional[Amount]`
      * `subtotal: Optional[Amount]`
      * `total: Optional[Amount]`
      * `fees: Optional[List[Fee]]`
      * `total_fee: Optional[Fee]`
      * `source: Optional[ConvertTradePaymentMethod]`
      * `target: Optional[ConvertTradePaymentMethod]`
      * `unit_price: Optional[Dict[str, Any]]`
      * `source_currency: Optional[str]`
      * `exchange_rate: Optional[Amount]`
  * **`Fee`**:
      * `title: Optional[str]`
      * `description: Optional[str]`
      * `amount: Optional[Amount]`
      * `label: Optional[str]`

-----

#### Payments

  * **`list_payment_methods(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/payment_methods`
      * **Returns**: `ListPaymentMethodsResponse`
          * `payment_methods: Optional[List[PaymentMethod]]`
  * **`get_payment_method(payment_method_id: str, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/payment_methods/{payment_method_id}`
      * **Returns**: `GetPaymentMethodResponse`
          * `payment_method: Optional[PaymentMethod]`

**Nested Response Objects (Payments):**

  * **`PaymentMethod`**:
      * `id: Optional[str]`
      * `type: Optional[str]`
      * `name: Optional[str]`
      * `currency: Optional[str]`
      * `verified: Optional[bool]`
      * `allow_buy: Optional[bool]`
      * `allow_sell: Optional[bool]`
      * `allow_deposit: Optional[bool]`
      * `allow_withdraw: Optional[bool]`
      * `created_at: Optional[str]`
      * `updated_at: Optional[str]`

-----

#### Fees

  * **`get_transaction_summary(product_type: Optional[str] = None, contract_expiry_type: Optional[str] = None, product_venue: Optional[str] = None, **kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/transaction_summary`
      * **Returns**: `GetTransactionSummaryResponse`
          * `total_volume: float`
          * `total_fees: float`
          * `fee_tier: FeeTier`
          * `margin_rate: Optional[Dict[str, Any]]`
          * `goods_and_services_tax: Optional[Dict[str, Any]]`
          * `advanced_trade_only_volumes: Optional[float]`
          * `advanced_trade_only_fees: Optional[float]`

**Nested Response Objects (Fees):**

  * **`FeeTier`**:
      * `pricing_tier: Optional[str]`
      * `usd_from: Optional[str]`
      * `usd_to: Optional[str]`
      * `taker_fee_rate: Optional[str]`
      * `maker_fee_rate: Optional[str]`

-----

#### Data API

  * **`get_api_key_permissions(**kwargs)`**
      * **Endpoint**: `[GET] /api/v3/brokerage/key_permissions`
      * **Returns**: `GetAPIKeyPermissionsResponse`
          * `can_view: Optional[bool]`
          * `can_trade: Optional[bool]`
          * `can_transfer: Optional[bool]`
          * `portfolio_uuid: Optional[str]`
          * `portfolio_type: Optional[str]`

-----

## 2\. WebSocket API Clients (`WSClient` & `WSUserClient`)

These clients are used for streaming real-time data.

### Constructors

  * **`WSClient(...)`**:
      * **Default URL**: `wss://advanced-trade-ws.coinbase.com`
      * Used for all channels, including public and private.
  * **`WSUserClient(...)`**:
      * **Default URL**: `wss://advanced-trade-ws-user.coinbase.com`
      * Specialized client for private channels: `user` and `futures_balance_summary`.

Both constructors accept these parameters from `WSBase`:

```python
(
    api_key: Optional[str] = os.getenv(API_ENV_KEY),
    api_secret: Optional[str] = os.getenv(API_SECRET_ENV_KEY),
    key_file: Optional[Union[IO, str]] = None,
    base_url: str = ...,
    timeout: Optional[int] = None,
    max_size: Optional[int] = 10 * 1024 * 1024,
    on_message: Optional[Callable[[str], None]] = None,
    on_open: Optional[Callable[[], None]] = None,
    on_close: Optional[Callable[[], None]] = None,
    retry: Optional[bool] = True,
    verbose: Optional[bool] = False
)
```

  * **`on_message`**: **(Required)** Callback function that handles incoming messages.
  * **`on_open`**: Callback function for when the connection opens.
  * **`on_close`**: Callback function for when the connection closes.
  * **`retry`**: Enables automatic reconnection (default: `True`).

### Core WebSocket Methods

  * `open()` / `open_async()`: Opens the WebSocket connection and starts the message handling loop.
  * `close()` / `close_async()`: Closes the WebSocket connection.
  * `subscribe(product_ids: List[str], channels: List[str])` / `subscribe_async(...)`: Subscribes to specified channels.
  * `unsubscribe(product_ids: List[str], channels: List[str])` / `unsubscribe_async(...)`: Unsubscribes from specified channels.
  * `unsubscribe_all()` / `unsubscribe_all_async()`: Unsubscribes from all currently subscribed channels.
  * `run_forever_with_exception_check()` / `run_forever_with_exception_check_async()`: Runs an infinite loop, checking for background exceptions.
  * `sleep_with_exception_check(sleep: int)` / `sleep_with_exception_check_async(sleep: int)`: Sleeps for a duration, checking for background exceptions.
  * `raise_background_exception()`: Raises any exception caught in the message handler thread.

### Channel Helper Methods

The `WSClient` provides helper methods for all channels. `WSUserClient` only provides helpers for `heartbeats`, `user`, and `futures_balance_summary`. Each has a synchronous and `_async` version, as well as `_unsubscribe` and `_unsubscribe_async` versions.

  * `heartbeats()`: Subscribes to the keep-alive channel.
  * `candles(product_ids: List[str])`: Subscribes to real-time candlestick data.
  * `market_trades(product_ids: List[str])`: Subscribes to real-time executed trades.
  * `status(product_ids: List[str])`: Subscribes to product status changes.
  * `ticker(product_ids: List[str])`: Subscribes to 24hr stats and price updates.
  * `ticker_batch(product_ids: List[str])`: A batched version of the ticker channel.
  * `level2(product_ids: List[str])`: Subscribes to the real-time, full order book.
  * `user(product_ids: List[str])`: **(Private)** Subscribes to user-specific order and position updates.
  * `futures_balance_summary()`: **(Private)** Subscribes to real-time futures balance updates.

### WebSocket Response Parsing

The `on_message` callback receives a JSON string, which can be parsed using the `WebsocketResponse` class.

**`WebsocketResponse` (Top-Level Object):**

  * `channel: str`: The channel of the message (e.g., "ticker", "user").
  * `client_id: str`: A unique client identifier.
  * `timestamp: str`: The message timestamp.
  * `sequence_num: int`: The message sequence number.
  * `events: List[Event]`: A list of event data objects.

**`Event` (Wrapper Object):**
The attributes of this object *change* based on the `channel`.

  * **If `channel == "heartbeats"`**:
      * `current_time: Optional[str]`
      * `heartbeat_counter: Optional[str]`
  * **If `channel == "candles"`**:
      * `type: Optional[str]`
      * `candles: List[WSCandle]`
  * **If `channel == "market_trades"`**:
      * `type: Optional[str]`
      * `trades: List[WSHistoricalMarketTrade]`
  * **If `channel == "status"`**:
      * `type: Optional[str]`
      * `products: List[WSProduct]`
  * **If `channel == "ticker"` or `"ticker_batch"`**:
      * `type: Optional[str]`
      * `tickers: List[WSTicker]`
  * **If `channel == "l2_data"`**:
      * `type: Optional[str]`
      * `product_id: Optional[str]`
      * `updates: List[L2Update]`
  * **If `channel == "user"`**:
      * `type: Optional[str]`
      * `orders: Optional[List[UserOrders]]`
      * `positions: Optional[UserPositions]`
  * **If `channel == "futures_balance_summary"`**:
      * `type: Optional[str]`
      * `fcm_balance_summary: WSFCMBalanceSummary`

**Nested WebSocket Data Types:**

  * **`WSCandle`**:
      * `start: Optional[str]`
      * `high: Optional[str]`
      * `low: Optional[str]`
      * `open: Optional[str]`
      * `close: Optional[str]`
      * `volume: Optional[str]`
      * `product_id: Optional[str]`
  * **`WSHistoricalMarketTrade`**:
      * `product_id: Optional[str]`
      * `trade_id: Optional[str]`
      * `price: Optional[str]`
      * `size: Optional[str]`
      * `time: Optional[str]`
      * `side: Optional[str]`
  * **`WSProduct`**:
      * `product_type: Optional[str]`
      * `id: Optional[str]`
      * `base_currency: Optional[str]`
      * `quote_currency: Optional[str]`
      * `base_increment: Optional[str]`
      * `quote_increment: Optional[str]`
      * `display_name: Optional[str]`
      * `status: Optional[str]`
      * `status_message: Optional[str]`
      * `min_market_funds: Optional[str]`
  * **`WSTicker`**:
      * `type: Optional[str]`
      * `product_id: Optional[str]`
      * `price: Optional[str]`
      * `volume_24_h: Optional[str]`
      * `low_24_h: Optional[str]`
      * `high_24_h: Optional[str]`
      * `low_52_w: Optional[str]`
      * `high_52_w: Optional[str]`
      * `price_percent_chg_24_h: Optional[str]`
      * `best_bid: Optional[str]`
      * `best_ask: Optional[str]`
      * `best_bid_quantity: Optional[str]`
      * `best_ask_quantity: Optional[str]`
  * **`L2Update`**:
      * `side: Optional[str]` (e.g., "bid", "ask")
      * `event_time: Optional[str]`
      * `price_level: Optional[str]`
      * `new_quantity: Optional[str]`
  * **`UserOrders`**:
      * `avg_price: Optional[str]`
      * `cancel_reason: Optional[str]`
      * `client_order_id: Optional[str]`
      * `completion_percentage: Optional[str]`
      * `cumulative_quantity: Optional[str]`
      * `filled_value: Optional[str]`
      * `leaves_quantity: Optional[str]`
      * `limit_price: Optional[str]`
  * `order_id: Optional[str]`
      * `order_side: Optional[str]`
      * `order_type: Optional[str]`
      * `product_id: Optional[str]`
      * `product_type: Optional[str]`
      * `reject_reason: Optional[str]`
      * `status: Optional[str]`
      * `time_in_force: Optional[str]`
      * `total_fees: Optional[str]`
      * `creation_time: Optional[str]`
  * **`UserPositions`**:
      * `perpetual_futures_positions: Optional[List[UserFuturesPositions]]`
      * `expiring_futures_positions: Optional[List[UserExpFuturesPositions]]`
  * **`UserFuturesPositions`** (Perpetuals):
      * `product_id: Optional[str]`
      * `portfolio_uuid: Optional[str]`
      * `vwap: Optional[str]`
      * `entry_vwap: Optional[str]`
      * `position_side: Optional[str]`
      * `margin_type: Optional[str]`
      * `net_size: Optional[str]`
      * `leverage: Optional[str]`
      * `mark_price: Optional[str]`
      * `liquidation_price: Optional[str]`
      * `unrealized_pnl: Optional[str]`
  * **`UserExpFuturesPositions`** (Expiring):
      * `product_id: Optional[str]`
      * `side: Optional[str]`
      * `number_of_contracts: Optional[str]`
      * `realized_pnl: Optional[str]`
      * `unrealized_pnl: Optional[str]`
  * **`WSFCMBalanceSummary`**:
      * `futures_buying_power: Optional[str]`
      * `total_usd_balance: Optional[str]`
      * `cbi_usd_balance: Optional[str]`
      * `cfm_usd_balance: Optional[str]`
      * `total_open_orders_hold_amount: Optional[str]`
      * `unrealized_pnl: Optional[str]`
      * `daily_realized_pnl: Optional[str]`
      * `initial_margin: Optional[str]`
      * `available_margin: Optional[str]`
      * `liquidation_threshold: Optional[str]`
      * `intraday_margin_window_measure: Optional[FCMMarginWindowMeasure]`
      * `overnight_margin_window_measure: Optional[FCMMarginWindowMeasure]`
  * **`FCMMarginWindowMeasure`**:
      * `margin_window_type: Optional[str]`
      * `margin_level: Optional[str]`
      * `initial_margin: Optional[str]`
      * `maintenance_margin: Optional[str]`
      * `futures_buying_power: Optional[str]`

-----

## 3\. Authentication Utilities (`jwt_generator`)

For users who wish to generate JWTs manually, the SDK provides these helper functions.

  * **`build_rest_jwt(uri: str, key_var: str, secret_var: str) -> str`**
      * Builds a JWT for REST API authentication.
      * `uri`: The formatted URI, e.g., "GET api.coinbase.com/api/v3/brokerage/accounts".
  * **`build_ws_jwt(key_var: str, secret_var: str) -> str`**
      * Builds a JWT for WebSocket authentication.
  * **`format_jwt_uri(method: str, path: str) -> str`**
      * A helper to create the `uri` string needed for `build_rest_jwt`.
