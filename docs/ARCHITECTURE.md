# Trading Bot Architecture

## System Overview

The Coinbase Algorithmic Trading Bot is designed as a modular, event-driven system with clear separation of concerns.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Trading Bot Main Loop                    │
│                       (src/main.py)                          │
└────────────┬────────────────────────────────────────────────┘
             │
             ├──────────────┬──────────────┬──────────────┬────────────────┐
             │              │              │              │                │
    ┌────────▼────────┐ ┌──▼───────┐ ┌───▼─────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Configuration  │ │  API     │ │Strategy │ │    Risk     │ │  Analytics  │
    │     Loader      │ │  Client  │ │ Engine  │ │  Manager    │ │   Engine    │
    └────────┬────────┘ └──┬───────┘ └───┬─────┘ └──────┬──────┘ └──────┬──────┘
             │              │              │              │                │
             │              │              │              │                │
    ┌────────▼──────────────▼──────────────▼──────────────▼────────────────▼──────┐
    │                         Database Manager                                      │
    │                        (SQLite Persistence)                                   │
    └───────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │
                            ┌───────────▼───────────┐
                            │  External Services    │
                            │  - Coinbase API       │
                            │  - WebSocket Feed     │
                            └───────────────────────┘
```

## Core Components

### 1. Main Trading Bot (`src/main.py`)

**Responsibilities:**
- Orchestrates the entire trading system
- Manages the main event loop
- Coordinates between all subsystems
- Handles graceful shutdown

**Key Methods:**
- `run()`: Main trading loop
- `_analyze_product()`: Analyze individual products for signals
- `execute_buy_order()`: Execute buy orders with risk management
- `execute_sell_order()`: Execute sell orders and track PnL
- `_save_performance_snapshot()`: Periodic performance tracking

**Flow:**
1. Initialize all components
2. Get portfolio and balances
3. Find tradable products
4. Start WebSocket for real-time prices
5. Main loop:
   - Check and update open positions
   - Analyze products for signals
   - Execute trades based on signals
   - Update performance metrics
   - Save state to database

### 2. Configuration Loader (`src/config_loader.py`)

**Responsibilities:**
- Load YAML configuration files
- Manage environment variables
- Provide typed configuration access
- Support configuration reloading

**Features:**
- Dot notation access (`config.get('trading.paper_trading_mode')`)
- Environment variable overrides
- Default value support
- Singleton pattern for global access

### 3. API Client (`src/api_client.py`)

**Responsibilities:**
- Wrapper for Coinbase REST API
- WebSocket management for real-time data
- Price feed management
- Historical data retrieval

**Key Methods:**
- `get_portfolio_id()`: Get default portfolio
- `get_account_balances()`: Fetch current balances
- `find_tradable_products()`: Identify tradable pairs
- `get_historical_data()`: Fetch OHLCV candles
- `start_websocket()`: Initialize real-time price feed

**WebSocket Handling:**
- Background thread for WebSocket
- Real-time price updates
- Automatic reconnection (planned)
- Thread-safe price dictionary

### 4. Strategy Engine (`src/strategies/`)

**Architecture:**
- **Base Strategy** (`base_strategy.py`): Abstract base class
- **Concrete Strategies**: Momentum, Mean Reversion, Breakout
- **Hybrid Strategy**: Combines multiple strategies
- **Strategy Factory**: Creates strategy instances

**Strategy Interface:**
```python
class BaseStrategy(ABC):
    def analyze(self, df: pd.DataFrame, product_id: str) -> TradingSignal
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame
    def validate_data(self, df: pd.DataFrame, min_periods: int) -> bool
```

**Signal Flow:**
1. Receive OHLCV DataFrame
2. Add technical indicators
3. Validate data sufficiency
4. Analyze indicators
5. Return TradingSignal with action and confidence

**Strategies:**

**Momentum Strategy:**
- Indicators: MACD, RSI, Bollinger Bands, Volume
- Buy: Price above upper BB + MACD cross up + RSI 50-70 + High volume
- Sell: Price below middle BB + MACD cross down + RSI > 75

**Mean Reversion Strategy:**
- Indicators: Bollinger Bands, RSI, SMA, Distance from Mean
- Buy: Price at/below lower BB + RSI < 20 + Below mean
- Sell: Price at/above upper BB + RSI > 80 + Above mean

**Breakout Strategy:**
- Indicators: Rolling High/Low, ATR, Volume
- Buy: Price breaks above range + Volume confirmation + Tight consolidation
- Sell: Price breaks below range + Failed breakout

**Hybrid Strategy:**
- Combines multiple strategies
- Requires agreement from N strategies
- Weighted confidence scoring

### 5. Risk Manager (`src/risk_management.py`)

**Responsibilities:**
- Position sizing calculations
- Portfolio-level risk controls
- Stop loss and take profit management
- Drawdown protection
- Exposure limits

**Risk Controls:**

**Position Sizing:**
- 1% risk rule: Risk only 1% of capital per trade
- Formula: `Position Size = Risk Amount / (Entry Price - Stop Loss)`
- Respects minimum trade sizes
- Caps at maximum position size (10% default)

**Portfolio Controls:**
- Maximum concurrent positions (5 default)
- Maximum total exposure (50% default)
- Maximum drawdown halt (15% default)

**Stop Loss / Take Profit:**
- Configurable default percentages
- Trailing stop support
- Automatic position closure

**Drawdown Protection:**
- Tracks peak equity
- Calculates current drawdown
- Halts trading if max drawdown exceeded
- Resumes when recovered

### 6. Analytics Engine (`src/analytics.py`)

**Responsibilities:**
- Calculate performance metrics
- Generate performance reports
- Track equity curve
- Risk-adjusted returns

**Metrics:**

**Sharpe Ratio:**
- Measures risk-adjusted returns
- Formula: `(Mean Return - Risk Free Rate) / Std Dev of Returns`
- Annualized for comparison

**Sortino Ratio:**
- Like Sharpe but uses downside deviation
- Focuses on harmful volatility
- Better for asymmetric returns

**Win Rate:**
- Percentage of profitable trades
- Average win vs average loss
- Profit factor (total wins / total losses)

**Maximum Drawdown:**
- Largest peak-to-trough decline
- Identifies worst-case scenario
- Critical for risk assessment

**Expectancy:**
- Expected value per trade
- Formula: `(Win Rate × Avg Win) - (Loss Rate × Avg Loss)`

### 7. Database Manager (`src/database.py`)

**Schema:**

**Orders Table:**
- Tracks all orders (entry and exit)
- Status tracking (submitted, filled, cancelled)
- Metadata for debugging

**Positions Table:**
- Open and closed positions
- Real-time price updates
- Unrealized and realized PnL
- Entry/exit timestamps

**Trade History Table:**
- Completed trades
- Entry and exit prices
- PnL and PnL percentage
- Holding time
- Strategy used
- Exit reason

**Performance Metrics Table:**
- Periodic performance snapshots
- Equity, PnL, win rate
- Sharpe and Sortino ratios
- Drawdown tracking

**Equity Curve Table:**
- Time-series equity data
- Cash vs positions breakdown
- Used for performance visualization

**Bot State Table:**
- Key-value store for bot state
- Persistent configuration
- Runtime data

## Data Flow

### Trade Execution Flow

```
1. Market Data → Historical Data Fetch
                 ↓
2. Historical Data → Strategy Analysis
                     ↓
3. Trading Signal → Risk Manager Validation
                    ↓
4. Risk Approved → Position Sizing Calculation
                   ↓
5. Position Size → Order Execution (Paper/Live)
                   ↓
6. Order Filled → Database Update (Order + Position)
                  ↓
7. Position Open → Monitoring Loop
                   ↓
8. Exit Trigger → Sell Order Execution
                  ↓
9. Position Closed → Trade History + Analytics
```

### Monitoring Loop Flow

```
1. Get Open Positions from Database
   ↓
2. For Each Position:
   - Get Current Price
   - Update Position Price in DB
   - Check Stop Loss / Take Profit
   - Update Trailing Stop (if enabled)
   ↓
3. Trigger Exit if Needed
   ↓
4. Update Performance Metrics
   ↓
5. Save Equity Snapshot
```

## Configuration System

### Configuration Hierarchy

```
config.yaml (base configuration)
    ↓
Environment Variables (.env)
    ↓
Runtime Overrides
```

### Configuration Categories

1. **API Settings**: Credentials, timeouts, retries
2. **Trading Parameters**: Granularity, loop timing, analysis limits
3. **Risk Management**: Risk %, position limits, stop loss/TP
4. **Strategy Settings**: Per-strategy parameters
5. **Analytics**: Metric calculation settings
6. **Database**: Path, backup settings
7. **Logging**: Level, file settings

## Error Handling

### Error Handling Strategy

1. **API Errors**: Retry with exponential backoff
2. **Data Errors**: Skip and log, continue processing
3. **Order Errors**: Log to database, alert if critical
4. **Fatal Errors**: Graceful shutdown, save state

### Logging Levels

- **DEBUG**: Detailed diagnostic information
- **INFO**: General operational messages
- **WARNING**: Unexpected but handled situations
- **ERROR**: Errors that don't stop execution
- **CRITICAL**: Fatal errors requiring shutdown

## Concurrency Model

### Threading Model

1. **Main Thread**: Trading loop and strategy analysis
2. **WebSocket Thread**: Real-time price updates (daemon)
3. **ThreadPoolExecutor**: Parallel product analysis (max 3 workers)

### Thread Safety

- **Database**: Thread-safe SQLite operations
- **Price Dictionary**: Thread-safe read/write
- **Position State**: Database-backed, atomic operations

## Scalability Considerations

### Current Limits

- Max products to analyze: 20 per cycle
- Max WebSocket subscriptions: 100
- Parallel workers: 3

### Optimization Opportunities

1. **Caching**: Cache product details, reduce API calls
2. **Batching**: Batch database operations
3. **Async IO**: Convert to async for better concurrency
4. **Data Pipeline**: Stream processing for real-time signals

## Security Considerations

1. **API Credentials**: Stored in .env, never committed
2. **Paper Trading Default**: Safe mode by default
3. **Risk Limits**: Hard-coded maximum limits
4. **Database**: Local SQLite, no external exposure
5. **Logging**: Sanitize sensitive data

## Future Enhancements

### Planned Features

1. **Backtesting Engine**: Test strategies on historical data
2. **Alert System**: Email/SMS notifications
3. **Web Dashboard**: Real-time monitoring UI
4. **Multiple Exchanges**: Support beyond Coinbase
5. **Machine Learning**: ML-based strategy optimization
6. **Order Types**: Limit orders, iceberg orders
7. **Advanced Risk**: Correlation analysis, portfolio optimization

### Architecture Improvements

1. **Microservices**: Split into separate services
2. **Message Queue**: Decouple components with RabbitMQ/Redis
3. **Time Series DB**: InfluxDB for metrics
4. **Container Deployment**: Docker + Kubernetes
5. **Cloud Deployment**: AWS/GCP deployment

## Testing Strategy

### Test Coverage Areas

1. **Unit Tests**: Individual component testing
2. **Integration Tests**: Component interaction testing
3. **Strategy Tests**: Backtest verification
4. **Paper Trading**: End-to-end testing

### Test Structure

```
tests/
├── test_strategies.py
├── test_risk_management.py
├── test_analytics.py
├── test_database.py
└── test_api_client.py
```

## Deployment

### Development Setup

1. Virtual environment
2. Local SQLite database
3. Paper trading mode
4. Debug logging

### Production Setup

1. Dedicated server/VPS
2. Database backups
3. Live trading (after thorough testing)
4. INFO/WARNING logging
5. Monitoring and alerts
6. Failover mechanisms

## Performance Benchmarks

### Target Performance

- Analysis cycle: < 60 seconds
- Order execution: < 5 seconds
- Database operations: < 100ms
- Memory usage: < 500MB
- CPU usage: < 50%

## Maintenance

### Regular Tasks

1. Review logs daily
2. Check performance metrics weekly
3. Update strategies monthly
4. Database backup daily (automated)
5. Dependency updates quarterly

### Monitoring Checklist

- [ ] Bot is running
- [ ] No critical errors in logs
- [ ] Positions are being managed correctly
- [ ] Performance metrics are being saved
- [ ] Database is not corrupted
- [ ] API credentials are valid
- [ ] Risk limits are respected

---

**Last Updated**: 2025-01-02
**Version**: 2.0
