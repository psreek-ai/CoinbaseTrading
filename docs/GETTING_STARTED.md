# 🎯 GETTING STARTED - Complete Step-by-Step Guide

Follow these steps exactly to get your trading bot running.

## Prerequisites

- ✅ Windows, macOS, or Linux computer
- ✅ Python 3.9 or higher installed
- ✅ Coinbase account
- ✅ Internet connection
- ✅ Basic command line knowledge

---

## Step 1: Verify Python Installation

Open a terminal/command prompt and run:

```bash
python --version
```

**Expected output:** `Python 3.9.x` or higher

❌ If you get an error or version is too old:
- Download Python from https://www.python.org/downloads/
- During installation, check "Add Python to PATH"
- Restart terminal and try again

---

## Step 2: Create Virtual Environment

A virtual environment keeps this project's dependencies separate from your system.

**Windows (PowerShell):**
```powershell
cd C:\Users\prathyooshan\Desktop\Work\LLMCodes\CoinbaseTrading
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
cd ~/path/to/CoinbaseTrading
python3 -m venv venv
source venv/bin/activate
```

✅ **Success indicator:** Your prompt should now show `(venv)` at the beginning

---

## Step 3: Install Dependencies

With the virtual environment activated:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will install:
- `python-dotenv` - Environment variable management
- `pyyaml` - Configuration file handling
- `coinbase-advanced-py` - Coinbase API SDK
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `pandas-ta` - Technical analysis indicators

⏱️ **Time:** 2-5 minutes depending on internet speed

✅ **Verify installation:**
```bash
pip list
```

You should see all the packages listed above.

---

## Step 4: Get Coinbase API Credentials

### 4.1 Log into Coinbase

Go to https://www.coinbase.com and log in.

### 4.2 Navigate to API Settings

1. Click your profile icon (top right)
2. Go to **Settings**
3. Click **API** in the left sidebar
4. Click **New API Key**

### 4.3 Configure API Permissions

**Required permissions:**
- ✅ View (for reading account data)
- ✅ Trade (for executing orders)
- ✅ Transfer (for managing positions)

**Portfolio Access:**
- Select the portfolio you want to trade with

### 4.4 Copy Your Credentials

You'll receive:
- **API Key** (looks like: `organizations/xxx/apiKeys/xxx`)
- **API Secret** (long string of random characters)

⚠️ **IMPORTANT:**
- Copy these immediately - the secret is only shown once!
- Keep them SECRET - anyone with these can trade your account
- Never commit them to git or share them

---

## Step 5: Create .env File

Create a file named `.env` in the project root directory.

**Windows:**
```powershell
notepad .env
```

**macOS/Linux:**
```bash
nano .env
```

**Add this content:**
```
COINBASE_API_KEY=your_api_key_here
COINBASE_API_SECRET=your_api_secret_here
```

Replace `your_api_key_here` and `your_api_secret_here` with your actual credentials.

**Example:**
```
COINBASE_API_KEY=organizations/abc-123/apiKeys/def-456
COINBASE_API_SECRET=-----BEGIN EC PRIVATE KEY-----\nMIGkAgEBBDD... (long string) ...==\n-----END EC PRIVATE KEY-----\n
```

✅ **Save and close** the file

---

## Step 6: Review Configuration

Open `config/config.yaml` in a text editor.

**Critical settings to verify:**

```yaml
trading:
  paper_trading_mode: true  # ✅ MUST be true for testing!

risk_management:
  risk_percent_per_trade: 0.01  # 1% risk per trade
  max_position_size_percent: 0.10  # Max 10% per position

strategies:
  active_strategy: "momentum"  # Choose: momentum, mean_reversion, breakout, hybrid
```

**For your first run, use these safe defaults:**
- ✅ `paper_trading_mode: true` (simulated trading, no real money)
- ✅ `active_strategy: "momentum"` (good for trending markets)
- ✅ Keep all risk settings at defaults

📝 **Save any changes**

---

## Step 7: First Test Run

### 7.1 Run the Startup Check

```bash
python run.py
```

This will:
- ✅ Check Python version
- ✅ Verify .env file exists
- ✅ Check all dependencies
- ✅ Confirm paper trading mode
- ✅ Start the bot if all checks pass

### 7.2 Expected Output

```
==================================================================
COINBASE TRADING BOT - STARTUP CHECK
==================================================================

✅ Paper trading mode enabled (safe mode)
✅ All checks passed!

Starting trading bot...
==================================================================

==================================================================
COINBASE ALGORITHMIC TRADING BOT - STARTING
==================================================================
2025-01-02 10:00:00 - INFO - Logging initialized
2025-01-02 10:00:01 - INFO - Database initialized
2025-01-02 10:00:02 - INFO - REST client initialized successfully
2025-01-02 10:00:03 - INFO - Paper Trading Mode: True
2025-01-02 10:00:03 - INFO - Active Strategy: momentum
...
```

✅ **If you see this, congratulations! Your bot is running!**

---

## Step 8: Monitor Your First Session

### What to Watch

**Console Output:**
- Look for "Trading Cycle" messages every 60 seconds
- Check for "Signal for X: BUY/SELL" messages
- Watch for any ERROR or WARNING messages

**Log Files:**
In a new terminal (keep bot running in the first one):

```bash
# Windows
Get-Content logs\trading_bot_*.log -Tail 50 -Wait

# macOS/Linux
tail -f logs/trading_bot_*.log
```

**What you'll see:**
- Portfolio scanning
- Product analysis
- Signal generation
- Order execution (simulated in paper mode)
- Position updates

### Let It Run

**Recommended:** Let it run for at least 1-2 hours for your first test.

---

## Step 9: Check Results

After letting it run for a while, stop the bot:

**Press:** `Ctrl + C`

Wait for "Shutdown complete" message.

### View Database

```bash
# Install SQLite browser (optional)
# Or use command line:

sqlite3 data/trading_bot.db

# Inside SQLite prompt:
SELECT * FROM orders;
SELECT * FROM positions;
SELECT * FROM trade_history;

# Exit SQLite:
.quit
```

### Review Performance

**Python script to check stats:**

Create `check_stats.py`:
```python
import sqlite3

conn = sqlite3.connect('data/trading_bot.db')
cursor = conn.cursor()

# Get trade count
cursor.execute("SELECT COUNT(*) FROM trade_history")
print(f"Total trades: {cursor.fetchone()[0]}")

# Get performance
cursor.execute("""
    SELECT 
        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
        COUNT(*) as total,
        SUM(pnl) as total_pnl
    FROM trade_history
""")
wins, total, pnl = cursor.fetchone()
if total > 0:
    print(f"Win rate: {wins/total*100:.1f}%")
    print(f"Total PnL: ${pnl:.2f}")

conn.close()
```

Run it:
```bash
python check_stats.py
```

---

## Step 10: Customize for Your Needs

### Change Strategy

Edit `config/config.yaml`:
```yaml
strategies:
  active_strategy: "mean_reversion"  # Try different strategies
```

### Adjust Risk

```yaml
risk_management:
  risk_percent_per_trade: 0.005  # More conservative (0.5%)
  # or
  risk_percent_per_trade: 0.02   # More aggressive (2%)
```

### Change Timeframe

```yaml
trading:
  candle_granularity: "FIFTEEN_MINUTE"  # Longer timeframe
  # or
  candle_granularity: "ONE_MINUTE"  # Shorter timeframe (faster signals)
```

**After any changes:** Restart the bot

---

## Step 11: Going Live (When Ready)

⚠️ **ONLY after extensive paper trading testing!**

### Prerequisites for Live Trading

- ✅ Run in paper mode for at least 1-2 weeks
- ✅ Understand the strategy performance
- ✅ Comfortable with win rate and drawdowns
- ✅ Have risk capital you can afford to lose
- ✅ Start with small amounts ($100-500)

### Enable Live Trading

1. **Backup your config:**
   ```bash
   cp config/config.yaml config/config.yaml.backup
   ```

2. **Edit config:**
   ```yaml
   trading:
     paper_trading_mode: false  # ⚠️ REAL MONEY!
   ```

3. **Reduce risk for first live run:**
   ```yaml
   risk_management:
     risk_percent_per_trade: 0.005  # 0.5% only
     max_concurrent_positions: 2    # Limit positions
   ```

4. **Start bot and monitor CLOSELY:**
   ```bash
   python run.py
   ```

5. **Watch every trade for first few hours**

---

## Troubleshooting

### "API credentials not found"

**Solution:**
- Check `.env` file exists in project root
- Verify credentials are correct (no extra spaces)
- Make sure you're in the correct directory

### "Import 'yaml' could not be resolved"

**Solution:**
```bash
# Make sure virtual environment is activated
# Then reinstall:
pip install --force-reinstall pyyaml
```

### "No portfolios found"

**Solution:**
- Log into Coinbase website
- Ensure you have a portfolio
- Verify API key has permission to access it

### "Position size below minimum"

**Solution:**
- You need more balance (at least $50-100)
- Or adjust `min_usd_trade_value` in config

### Bot not finding any signals

**Possible reasons:**
- Market conditions don't match strategy
- Try different strategy
- Adjust strategy parameters
- Wait longer (signals aren't constant)

---

## Next Steps

### Learn More

1. **Read QUICK_REFERENCE.md** - Common tasks and tips
2. **Read ARCHITECTURE.md** - How it works internally
3. **Read STARTUP_CHECKLIST.md** - Pre-flight checklist

### Optimize

1. **Test different strategies** in paper mode
2. **Tune parameters** for your style
3. **Track performance** over weeks
4. **Adjust risk** as you learn

### Expand

1. **Create custom strategies** (extend BaseStrategy)
2. **Add new indicators**
3. **Implement backtesting**
4. **Build a dashboard**

---

## Important Reminders

### ⚠️ Risk Warnings

- Crypto trading is EXTREMELY risky
- You can lose all your money
- Past performance ≠ future results
- Start small, test thoroughly
- Never trade with money you can't afford to lose

### 🛡️ Safety Tips

- Always test in paper mode first
- Start with minimum amounts live
- Monitor regularly
- Have stop losses
- Know when to stop

### 📊 Realistic Expectations

- Not every day will be profitable
- Drawdowns are normal
- 50-60% win rate is good
- Consistency matters more than big wins
- It takes time to learn what works

---

## Support

If you have issues:

1. Check the logs in `logs/` directory
2. Review this guide again
3. Check QUICK_REFERENCE.md
4. Verify all configuration settings
5. Ensure API credentials are correct

---

## Checklist Summary

- [ ] Python 3.9+ installed and verified
- [ ] Virtual environment created and activated
- [ ] Dependencies installed successfully
- [ ] Coinbase API credentials obtained
- [ ] .env file created with credentials
- [ ] config.yaml reviewed (paper_trading: true)
- [ ] First test run completed
- [ ] Logs reviewed, no critical errors
- [ ] Understanding how to stop bot (Ctrl+C)
- [ ] Comfortable with paper trading results

**If all checked:** You're ready to start automated trading! 🚀

**Good luck and trade safely!** 📈

---

**Need help?** Review documentation or check logs for specific error messages.
