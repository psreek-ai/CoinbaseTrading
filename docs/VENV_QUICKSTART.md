# 🚀 Quick Start Guide for venv Users

## Your Setup is Ready! ✅

All dependencies are installed in your virtual environment.

## Three Ways to Start the Bot

### Option 1: PowerShell Script (Easiest)
```powershell
.\start_bot.ps1
```

### Option 2: Batch File
```cmd
start_bot.bat
```

### Option 3: Manual Start
```powershell
.\venv\Scripts\python.exe run.py
```

## Current Status

✅ **Python Version:** 3.12.4  
✅ **Virtual Environment:** Active at `.\venv\`  
✅ **Dependencies Installed:**
- coinbase-advanced-py (1.8.2)
- pandas (2.3.1)
- pandas_ta (0.3.14b0)
- numpy (1.26.4)
- python-dotenv (1.1.1)
- pyyaml (6.0.3)
- All other requirements

✅ **.env file:** Present  
✅ **Configuration:** config/config.yaml ready  

## Before First Run

### 1. Verify Your API Credentials

Open `.env` and ensure it has:
```
COINBASE_API_KEY=your_actual_key
COINBASE_API_SECRET=your_actual_secret
```

### 2. Check Paper Trading Mode (IMPORTANT!)

Open `config\config.yaml` and verify:
```yaml
trading:
  paper_trading_mode: true  # ✅ MUST be true for testing!
```

**⚠️ If `false`, real money will be used!**

## Running the Bot

### Quick Start (Recommended)
```powershell
# Just double-click: start_bot.ps1
# Or run from PowerShell:
.\start_bot.ps1
```

The script will:
- Check all prerequisites
- Verify paper trading mode
- Start the bot
- Show you real-time logs

### What You'll See

```
========================================
COINBASE TRADING BOT - QUICK START
========================================

✓ Paper trading mode enabled (safe mode)

Starting trading bot...
Press Ctrl+C to stop

==================================================================
COINBASE ALGORITHMIC TRADING BOT - STARTING
==================================================================
2025-11-02 10:00:00 - INFO - Logging initialized
2025-11-02 10:00:01 - INFO - Database initialized
2025-11-02 10:00:02 - INFO - REST client initialized successfully
2025-11-02 10:00:03 - INFO - Paper Trading Mode: True
2025-11-02 10:00:03 - INFO - Active Strategy: momentum
...
```

## Monitoring

### View Logs in Real-Time
Open a **second** PowerShell window:
```powershell
Get-Content .\logs\trading_bot_*.log -Tail 50 -Wait
```

### Check Database
After running for a while:
```powershell
.\venv\Scripts\python.exe -c "import sqlite3; conn = sqlite3.connect('data/trading_bot.db'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM orders'); print(f'Orders: {cursor.fetchone()[0]}'); conn.close()"
```

## Stopping the Bot

**Press:** `Ctrl + C`  
**Wait for:** "Shutdown complete" message

## Useful Commands

### Activate venv manually
```powershell
.\venv\Scripts\Activate.ps1
```

### Install new packages
```powershell
.\venv\Scripts\python.exe -m pip install package_name
```

### Update all dependencies
```powershell
.\venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
```

### Check installed packages
```powershell
.\venv\Scripts\python.exe -m pip list
```

## Troubleshooting

### "Execution Policy" Error on PowerShell
If you get an error running `.ps1` scripts:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try again:
```powershell
.\start_bot.ps1
```

### "Module not found" Error
Reinstall dependencies:
```powershell
.\venv\Scripts\python.exe -m pip install --force-reinstall -r requirements.txt
```

### Check if venv is working
```powershell
.\venv\Scripts\python.exe --version
.\venv\Scripts\python.exe -m pip list
```

## Next Steps

1. ✅ **Run in paper mode** for 1-2 weeks
2. ✅ **Monitor performance** in database
3. ✅ **Read the logs** to understand behavior
4. ✅ **Try different strategies** in config
5. ✅ **Tune parameters** for your needs

## Configuration Tips

### Change Strategy
Edit `config\config.yaml`:
```yaml
strategies:
  active_strategy: "momentum"  # or mean_reversion, breakout, hybrid
```

### Adjust Risk
```yaml
risk_management:
  risk_percent_per_trade: 0.01  # 1% risk (conservative)
  max_concurrent_positions: 5   # Max 5 positions
```

### Change Timeframe
```yaml
trading:
  candle_granularity: "FIVE_MINUTE"  # or ONE_MINUTE, FIFTEEN_MINUTE, etc.
```

## Quick Reference

| Task | Command |
|------|---------|
| Start bot | `.\start_bot.ps1` |
| Stop bot | `Ctrl + C` |
| View logs | `Get-Content .\logs\*.log -Tail 50 -Wait` |
| Check venv | `.\venv\Scripts\python.exe --version` |
| Install package | `.\venv\Scripts\pip.exe install package` |

## Important Files

- **run.py** - Unified launcher (bot/scan/convert)
- **src\main.py** - Core trading bot
- **config\config.yaml** - All configuration
- **.env** - API credentials (DO NOT SHARE!)
- **data\trading_bot.db** - Database (created on first run)
- **logs\\** - Log files

## Documentation

- **README.md** - Full documentation
- **GETTING_STARTED.md** - Detailed setup guide
- **QUICK_REFERENCE.md** - Quick tips and commands
- **ARCHITECTURE.md** - How it works
- **STARTUP_CHECKLIST.md** - Pre-flight checklist

## Safety Reminders

- ✅ Always use paper mode first
- ✅ Start with small amounts when going live
- ✅ Monitor regularly
- ✅ Set appropriate stop losses
- ✅ Never risk more than you can afford to lose

---

**You're all set!** 🚀

Just run: `.\start_bot.ps1`

**Happy Trading!** 📈
