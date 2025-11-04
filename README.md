# Coinbase Trading Bot

Professional-grade automated cryptocurrency trading system with enterprise-level optimizations and institutional execution quality.

## ✨ Recent Updates (November 4, 2025)

🚀 **Signal-Confirmed Exit & Logging Overhaul** (builds on the Nov 3 execution upgrades):
- **Intelligent exits**: 5% profit and -2% loss thresholds now obey current BUY/HOLD/SELL signals.
- **True P&L tracking**: Cost basis calculation aggregates every fill and fee before making exit calls.
- **Unified logging**: Trading, REST, and WebSocket logs share the same timestamp for easier correlation.
- **Strategy resilience**: Momentum strategy Bollinger references fixed so confidence scoring reflects reality.

## Quick Start

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Start the trading bot
python run.py

# Scan for best opportunities
python run.py scan

# Convert holdings
python run.py convert
```

## Features

- 🤖 **Automated Trading** - Runs continuously with optimized execution
- 📊 **4 Trading Strategies** - Momentum, Mean Reversion, Breakout, Hybrid (all enhanced with ADX/EMA filters)
- 🏹 **Signal-Confirmed Exits** - 5% profit / -2% loss rules respect live momentum signals before closing trades.
- 💹 **Optimal Execution** - Limit orders earning 0.4% maker rebates (not paying 0.6% taker fees)
- 🔍 **Market Scanner** - Analyzes 600+ Coinbase products for opportunities
- 💱 **Holdings Converter** - Direct crypto-to-crypto conversion via Coinbase API
- 🛡️ **Advanced Risk Management** - Position sizing, stop-loss, spread protection, volume confirmation
- � **Real-Time Monitoring** - REST + WebSocket logging with synchronized timestamps and order callbacks.
- �📈 **Performance Analytics** - Sharpe ratio, win rate, equity curves
- 💾 **SQLite Database** - Full trade history and execution tracking

## Documentation

See the `docs/` folder for detailed documentation:

- **[User Guide](docs/USER_GUIDE.md)** - Comprehensive feature overview and usage
- **[Getting Started](docs/GETTING_STARTED.md)** - Step-by-step setup guide
- **[Optimization Changelog](docs/OPTIMIZATION_CHANGELOG.md)** - November 4, 2025 enhancements & fixes
- **[Project Status](docs/PROJECT_STATUS.md)** - Current status and testing results
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Command cheat sheet
- **[Architecture](docs/ARCHITECTURE.md)** - System design overview
- **[API Reference](docs/coinbaseAPI.md)** - Coinbase API documentation
- **[Exit Strategy](EXIT_STRATEGY.md)** - Detailed signal-confirmed exit rules

## Configuration

Edit `config/config.yaml` to configure:
- Trading strategies and parameters (now with ADX/EMA/Stochastic)
- Risk management rules (spread limits, volume confirmation)
- API settings
- Signal-confirmed exit behaviour (5% profit / -2% loss) is coded in `src/main.py` and requires no config changes
- Paper vs live trading mode (paper recommended for testing optimizations)

## Requirements

- Python 3.9+
- Coinbase Advanced Trade API credentials
- See `requirements.txt` for Python packages

---

For detailed setup instructions, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
