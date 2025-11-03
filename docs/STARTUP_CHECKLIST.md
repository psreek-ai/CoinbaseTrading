# 🚀 Trading Bot Startup Checklist

Use this checklist every time you start the bot to ensure everything is configured correctly.

## Pre-Flight Checklist

### ☐ 1. Environment Setup

```bash
# Check Python version (need 3.9+)
python --version

# Activate virtual environment
.\venv\Scripts\Activate.ps1    # Windows
source venv/bin/activate        # Mac/Linux

# Verify dependencies installed
pip list | grep -E "coinbase|pandas|yaml"
```

**Status:** _______________

---

### ☐ 2. API Credentials

```bash
# Check .env file exists
ls .env    # Mac/Linux
dir .env   # Windows

# Verify content (don't share this!)
cat .env   # Mac/Linux
type .env  # Windows
```

**Required content:**
```
COINBASE_API_KEY=your_key_here
COINBASE_API_SECRET=your_secret_here
```

**API Key Valid:** _______________
**API Secret Valid:** _______________

---

### ☐ 3. Configuration Review

Open `config/config.yaml` and verify:

#### Trading Settings
- [ ] `paper_trading_mode: true` (for testing) or `false` (for live - ⚠️ REAL MONEY)
- [ ] `candle_granularity` set (e.g., "FIVE_MINUTE")
- [ ] `loop_sleep_seconds` set (e.g., 60)

**Paper Trading Enabled:** ☐ YES  ☐ NO

#### Risk Management
- [ ] `risk_percent_per_trade` (default: 0.01 = 1%)
- [ ] `max_position_size_percent` (default: 0.10 = 10%)
- [ ] `default_stop_loss_percent` (default: 0.015 = 1.5%)
- [ ] `max_drawdown_percent` (default: 0.15 = 15%)

**Risk Settings Reviewed:** _______________

#### Strategy Selection
- [ ] `active_strategy` chosen: ________________
  - Options: momentum, mean_reversion, breakout, hybrid

**Strategy Selected:** _______________

---

### ☐ 4. Directory Structure

Verify all directories exist:

```bash
# Check structure
ls -la    # Mac/Linux
dir       # Windows
```

Required directories:
- [ ] `config/` (with config.yaml)
- [ ] `src/` (with all .py files)
- [ ] `logs/` (will be auto-created if missing)
- [ ] `data/` (will be auto-created if missing)

**Directories OK:** _______________

---

### ☐ 5. Database Check

If this is not first run:

```bash
# Check database exists and size
ls -lh data/trading_bot.db    # Mac/Linux
dir data\trading_bot.db        # Windows
```

**Database Size:** _______________
**Last Backup Date:** _______________

---

### ☐ 6. Review Previous Performance (if applicable)

If bot has run before, check last session:

```bash
# View latest log
tail -n 50 logs/trading_bot_*.log    # Mac/Linux
Get-Content logs\trading_bot_*.log -Tail 50    # Windows
```

Review last session:
- [ ] No critical errors
- [ ] Shutdown was clean
- [ ] No stuck positions

**Last Session Clean:** ☐ YES  ☐ NO  ☐ N/A (First Run)

---

### ☐ 7. Portfolio Balance Check

Log into Coinbase and verify:
- [ ] You have funds available
- [ ] Minimum balance: $________________
- [ ] Acceptable for trading: ☐ YES  ☐ NO

**Portfolio Balance:** $_______________

---

### ☐ 8. Risk Tolerance Confirmation

Before starting, confirm you understand:

- [ ] I understand I can lose money
- [ ] I have tested in paper mode (or understand the risks)
- [ ] I am only trading with money I can afford to lose
- [ ] I understand stop losses may not always execute at exact prices
- [ ] I know how to emergency stop the bot (Ctrl+C)

**Risk Acknowledged:** ☐ YES

---

### ☐ 9. Monitoring Plan

How will you monitor the bot?

- [ ] Check logs every: _______________ (e.g., 2 hours)
- [ ] Review positions: _______________ (e.g., twice daily)
- [ ] Check database: _______________ (e.g., daily)

**Monitoring Schedule Set:** _______________

---

### ☐ 10. Emergency Contacts

In case of issues:

**Technical Support:** _______________
**Coinbase Support:** https://help.coinbase.com
**Emergency Stop Command:** `Ctrl + C`

---

## 🚀 LAUNCH SEQUENCE

### If Everything Above is ✅ Checked:

**Option 1: Easy Start (Recommended)**
```bash
python run.py
```

**Option 2: Direct Start**
```bash
cd src
python main.py
```

---

## 🎯 During Operation Checklist

### First 15 Minutes
- [ ] Bot started successfully
- [ ] No immediate errors in console
- [ ] WebSocket connected (check logs)
- [ ] Initial portfolio scan complete

### First Hour
- [ ] Check log file for any warnings
- [ ] Verify bot is analyzing products
- [ ] Confirm no unexpected trades (if paper mode)

### First Day
- [ ] Review all trades executed
- [ ] Check position sizes are reasonable
- [ ] Verify stop losses are set
- [ ] Monitor equity curve

---

## 🛑 Emergency Stop Procedure

If something goes wrong:

1. **Immediate:** Press `Ctrl + C`
2. **Wait:** Let bot shutdown gracefully
3. **Verify:** Check "Shutdown complete" message
4. **Review:** Check last log entries
5. **Manual:** If needed, close positions via Coinbase website

---

## 📊 Success Metrics

Define your goals:

**Daily Goal:** _______________
**Weekly Goal:** _______________
**Maximum Acceptable Loss:** _______________
**When to Stop/Adjust:** _______________

---

## 📝 Session Log

**Date:** _______________
**Time Started:** _______________
**Initial Equity:** $_______________
**Strategy Used:** _______________
**Paper/Live Mode:** _______________

**Notes:**
_______________________________________________
_______________________________________________
_______________________________________________

---

## Post-Session Review

**Time Stopped:** _______________
**Final Equity:** $_______________
**Trades Executed:** _______________
**Win Rate:** _______________%
**Any Issues:** _______________

**Next Session Changes:**
_______________________________________________
_______________________________________________

---

## Quick Reference

**Stop Bot:** `Ctrl + C`
**View Logs:** `tail -f logs/trading_bot_*.log`
**Check Database:** `sqlite3 data/trading_bot.db`
**Emergency Backup:** `cp data/trading_bot.db data/backup_$(date +%Y%m%d).db`

---

**Remember:**
- ✅ Start in paper mode
- ✅ Monitor regularly
- ✅ Start small if going live
- ✅ Have a plan
- ✅ Know when to stop

**Good luck and trade safely! 🚀📈**
