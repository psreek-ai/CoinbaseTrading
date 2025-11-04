# 🚀 Quick Reference Guide

**Last Updated**: November 4, 2025 (Signal-Confirmed Exits)

## Essential Commands

### Trading Bot
```powershell
# Start the bot (unified launcher)
python run.py

# Or with full path
.\venv\Scripts\python.exe run.py

# Stop the bot
Ctrl + C
```

**What to Watch For in Logs:**
- `"ADX falling, trend weakening"` - Filtering ranging markets
- `"EMA bullish alignment"` - Trend confirmation
- `"Spread analysis: Best Ask=$X, Spread=0.2%"` - Pre-trade checks
- `"Volume flow: 65% buy pressure (strong_buy)"` - Volume confirmation
- `"[PAPER] Limit order (post-only) simulated"` - Maker order execution
- `"Pullback to middle BB in uptrend"` - Improved momentum entry
- `"[PROFIT EXIT] ... 5%"` - Signal-confirmed profit exit
- `"[LOSS EXIT] ... 2%"` - Signal-confirmed loss exit
- `"[WEBSOCKET] Order update received"` - Real-time Coinbase user-channel events

### Market Scanner
```powershell
# Scan all Coinbase products for best opportunities
python run.py scan

# Or with full path
.\venv\Scripts\python.exe run.py scan
```

### Crypto Converter
```powershell
# Interactive conversion tool
python run.py convert

# Or with full path
.\venv\Scripts\python.exe run.py convert
```

### Database Queries
```powershell
# Open database
sqlite3 data/trading_bot.db

# Recent trades with maker/taker info
SELECT product_id, side, entry_price, exit_price, pnl, pnl_percent, 
       order_metadata->>'$.maker_fills' as maker_count
FROM trade_history 
ORDER BY exit_time DESC 
LIMIT 10;

# Current performance
SELECT * FROM performance_metrics ORDER BY timestamp DESC LIMIT 1;

# Open positions
SELECT product_id, entry_price, current_price, unrealized_pnl 
FROM positions 
WHERE status = 'open';

# Exit
.quit
```

## Configuration Quick Edit

### Paper vs Live Trading
```yaml
# config/config.yaml
trading:
  paper_trading_mode: true   # ✅ Safe testing (RECOMMENDED for new optimizations)
  paper_trading_mode: false  # 🔴 REAL MONEY! (Only after 24-48hr paper testing)
```

### Change Strategy
```yaml
strategies:
  active_strategy: "momentum"        # Trending markets (NOW: with ADX >25 filter)
  active_strategy: "mean_reversion"  # Range-bound (NOW: with Stochastic + EMA 200)
  active_strategy: "breakout"        # Consolidation (NOW: with 50-bar lookback)
  active_strategy: "hybrid"          # Conservative (all improvements)
```

### Adjust Risk
```yaml
risk_management:
  risk_percent_per_trade: 0.01  # 1% risk per trade
  max_position_size_percent: 0.10  # 10% max per position
  max_drawdown_percent: 0.15  # Stop at 15% loss
  max_spread_percent: 0.005   # NEW: Reject if spread >0.5%
  min_buy_pressure: 0.45      # NEW: Require 45% buy volume
```

### Signal Confidence
```yaml
trading:
  min_signal_confidence: 0.50  # Only trade signals >= 50%
  min_signal_confidence: 0.70  # More conservative (70%+)
```

### Timeframe
```yaml
trading:
  candle_granularity: "FIVE_MINUTE"     # 5min candles
  candle_granularity: "FIFTEEN_MINUTE"  # 15min candles (RECOMMENDED)
  candle_granularity: "ONE_HOUR"        # 1hr candles
```

## Exit Strategy Cheat Sheet

- **Profit Exit**: Price ≥ cost_basis * 1.05 **AND** signal is HOLD or SELL → `[PROFIT EXIT]`
- **Ride Winners**: Price ≥ cost_basis * 1.05 **AND** signal is BUY → stay in trade
- **Loss Exit**: Price ≤ cost_basis * 0.98 **AND** signal is SELL with ≥60% confidence → `[LOSS EXIT]`
- **Monitor Loss**: Price ≤ cost_basis * 0.98 but signal not strong → `[LOSS WARNING]`

Logs live in `logs/trading_bot_*.log`. Full explanation: `EXIT_STRATEGY.md`.

## Trading Strategies Cheat Sheet

### Momentum Strategy
**Best for**: Strong trends  
**Signals**: MACD crossovers, RSI 50-70, BB breakouts  
**Parameters to tweak**:
```yaml
momentum:
  rsi_overbought: 70  # Lower = more aggressive (e.g., 65)
  macd_fast: 12       # Faster = more signals
  bb_period: 20       # Shorter = more sensitive
```

### Mean Reversion Strategy  
**Best for**: Sideways markets  
**Signals**: Extreme RSI (<20, >80), BB extremes  
**Parameters to tweak**:
```yaml
mean_reversion:
  rsi_extreme_oversold: 20   # Higher = more conservative
  rsi_extreme_overbought: 80 # Lower = more conservative
  bb_period: 20              # Standard deviation threshold
```

### Breakout Strategy
**Best for**: Consolidation periods  
**Signals**: Range breaks + volume  
**Parameters to tweak**:
```yaml
breakout:
  range_lookback: 50        # Periods to define range
  breakout_threshold: 0.02  # 2% break required
  volume_multiplier: 1.5    # Volume must be 1.5x average
```

## Troubleshooting Quick Fixes

### Bot Won't Start

**Issue**: `.env` not found  
**Fix**: 
```powershell
# Create .env file
New-Item -Path ".env" -ItemType File
# Add:
# COINBASE_API_KEY=your_key_here
# COINBASE_API_SECRET=your_secret_here
```

**Issue**: Config file missing  
**Fix**: 
```powershell
# Check config exists
Test-Path "config/config.yaml"
# Should return: True
```

**Issue**: Module not found  
**Fix**:
```powershell
# Reinstall dependencies
pip install -r requirements.txt
```

### No Trades Executing

**Check 1**: Paper trading mode
```yaml
# In config.yaml - make sure it's what you intend
paper_trading_mode: true/false
```

**Check 2**: Signal confidence too high
```yaml
# Lower threshold if no signals
min_signal_confidence: 0.40  # From 0.50
```

**Check 3**: Check logs
```powershell
# View latest log
Get-Content .\logs\trading_bot_*.log -Tail 50
```

**Check 4**: Market conditions
```powershell
# Run scanner to see if ANY signals exist
.\scan_opportunities.ps1
```

### API Errors

**Error**: Unauthorized (401)  
**Fix**: Check API credentials in `.env`, verify key is active

**Error**: Forbidden (403)  
**Fix**: Ensure API key has `trade` permission, not just `view`

**Error**: Rate limited (429)  
**Fix**: Increase `loop_sleep_seconds` in config.yaml

### Scanner Shows "View Only"

**This is normal** - Scanner now filters these automatically  
**If your pick is view-only**: 
- It won't appear in final results
- Choose from the filtered list instead

## Performance Monitoring

### Check Win Rate
```sql
SELECT 
  COUNT(*) as total_trades,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
  ROUND(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate_pct
FROM trade_history;
```

### Check Total P&L
```sql
SELECT 
  ROUND(SUM(pnl), 2) as total_pnl,
  ROUND(AVG(pnl), 2) as avg_pnl_per_trade,
  ROUND(MAX(pnl), 2) as best_trade,
  ROUND(MIN(pnl), 2) as worst_trade
FROM trade_history;
```

### View Equity Curve
```sql
SELECT date(timestamp) as day, 
       ROUND(total_value, 2) as equity
FROM equity_curve 
ORDER BY timestamp DESC 
LIMIT 30;
```

## Log Locations

```
logs/trading_bot_YYYYMMDD_HHMMSS.log  # Main bot log
data/trading_bot.db                    # SQLite database
```

**View live log**:
```powershell
Get-Content .\logs\trading_bot_*.log -Tail 50 -Wait
```

## Common Workflows

### Daily Check
```powershell
# 1. Check if bot is running
Get-Process python

# 2. View recent activity
Get-Content .\logs\trading_bot_*.log -Tail 20

# 3. Check P&L
sqlite3 data/trading_bot.db "SELECT SUM(pnl) FROM trade_history;"
```

### Find New Opportunity
```powershell
# 1. Run scanner
.\scan_opportunities.ps1

# 2. Get top recommendation (e.g., AUDIO-USDC)

# 3. Convert holdings
.\venv\Scripts\python.exe convert_holdings.py --target AUDIO --from ETH,NEAR
```

### Strategy Optimization
```powershell
# 1. Check current performance
sqlite3 data/trading_bot.db "SELECT * FROM performance_metrics ORDER BY timestamp DESC LIMIT 1;"

# 2. Try different strategy
# Edit config.yaml: active_strategy: "breakout"

# 3. Restart bot
Ctrl+C  # Stop
.\start_bot.ps1  # Restart

# 4. Monitor for improvement
```

## Environment Variables

Create `.env` file:
```env
# Required
COINBASE_API_KEY=organizations/xxx-xxx/apiKeys/xxx-xxx
COINBASE_API_SECRET=-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----

# Optional
LOG_LEVEL=INFO
DATABASE_PATH=data/trading_bot.db
```

## Safety Checklist

Before live trading:
- [ ] Tested in paper mode for 1+ week
- [ ] Win rate > 50%
- [ ] Max drawdown acceptable
- [ ] API key has correct permissions
- [ ] `paper_trading_mode: false` in config
- [ ] Risk limits appropriate for account size
- [ ] Monitoring plan in place

## File Locations Reference

```
├── config/config.yaml          # Main configuration
├── .env                        # API credentials
├── data/trading_bot.db         # Database
├── logs/trading_bot_*.log      # Log files
├── src/main.py                 # Main bot code
├── find_best_opportunities.py  # Scanner
├── convert_holdings.py         # Converter
└── run.py                      # Unified launcher
```

## Emergency Stop

```powershell
# Graceful shutdown
Ctrl + C

# Force kill (if frozen)
Get-Process python | Stop-Process -Force

# Check no processes running
Get-Process python
```

## Getting Help

1. **Check logs**: `logs/trading_bot_*.log`
2. **Check database**: `sqlite3 data/trading_bot.db`
3. **Review config**: `config/config.yaml`
4. **Read docs**: `GETTING_STARTED.md`, `ARCHITECTURE.md`

---

**Pro tip**: Keep this file open while trading for quick reference! 📌
