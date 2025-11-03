# Coinbase Trading Bot

A robust automated algorithmic crypto trading bot for Coinbase with advanced strategies, risk management, and market scanning capabilities.

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

- 🤖 **Automated Trading** - Runs continuously with configurable strategies
- 📊 **4 Trading Strategies** - Momentum, Mean Reversion, Breakout, Hybrid
- 🔍 **Market Scanner** - Analyzes all Coinbase products for opportunities
- 💱 **Holdings Converter** - Direct crypto-to-crypto conversion via Coinbase API
- 🛡️ **Risk Management** - Position sizing, stop-loss, drawdown protection
- 📈 **Performance Analytics** - Sharpe ratio, win rate, equity curves
- 💾 **SQLite Database** - Full trade history and metrics tracking

## Documentation

See the `docs/` folder for detailed documentation:

- [Getting Started Guide](docs/GETTING_STARTED.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Quick Reference](docs/QUICK_REFERENCE.md)
- [Project Status](docs/PROJECT_STATUS.md)
- [Startup Checklist](docs/STARTUP_CHECKLIST.md)

## Configuration

Edit `config/config.yaml` to configure:
- Trading strategies and parameters
- Risk management rules
- API settings
- Paper vs live trading mode

## Requirements

- Python 3.9+
- Coinbase Advanced Trade API credentials
- See `requirements.txt` for Python packages

---

For detailed setup instructions, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)
