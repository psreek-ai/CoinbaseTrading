# Enhanced Trade Analytics System

## Quick Start

### 1. Run Your Bot
```bash
python run.py
```
*(Let it trade for at least 1 hour to collect data)*

### 2. Analyze Performance
```bash
python analyze_trades.py --latest
```
**Output:** Win rate, P&L, best products, exit reasons, etc.

### 3. Find Best Strategy
```bash
python run_experiments.py --latest
```
**Output:** Tests 9 parameter combinations, recommends optimal config

### 4. Apply Improvements
Update `config/config.yaml` with recommended parameters

### 5. Test & Iterate
Run another hour, compare results, repeat

---

## What's New

### Comprehensive Logging
Every trading session creates detailed analytics in `logs/analytics/`:

- **trade_analytics_*.jsonl** - All events (scans, decisions, errors)
- **trades_*.jsonl** - Complete trade lifecycle  
- **market_state_*.jsonl** - Market conditions at signal time

### Data Captured

✅ **Market Scans** - All signals with indicators (RSI, ADX, MACD)  
✅ **Entry Decisions** - Why trades were taken/skipped  
✅ **Order Execution** - Fills, fees, slippage  
✅ **Position Monitoring** - P&L updates, holding time  
✅ **Exit Decisions** - Profit/loss/signal/emergency  
✅ **Trade Complete** - Full lifecycle with all metrics

### Strategy Experimentation

Test different parameters **without risking money**:

```python
from trade_logger import TradeReplayEngine

engine = TradeReplayEngine('logs/analytics/trade_analytics_20241104_120000.jsonl')

# Test tighter entry criteria
result = engine.replay_with_params(
    min_confidence=0.70,  # Higher threshold
    min_rsi=60,           # Stronger momentum
    stop_loss_pct=2.0     # Wider stops
)

print(f"Win Rate: {result['win_rate']*100:.1f}%")
print(f"P&L: {result['total_pnl_pct']:+.2f}%")
```

---

## Analysis Tools

### analyze_trades.py

**Shows:**
- Trade statistics (win rate, P&L, profit factor)
- Holding time analysis (winners vs losers)
- Product performance (best/worst assets)
- Exit reason breakdown
- Signal confidence correlation
- Optimization recommendations

**Usage:**
```bash
python analyze_trades.py --latest
python analyze_trades.py logs/analytics/trade_analytics_20241104_120000.jsonl
```

### run_experiments.py

**Tests:**
- Higher confidence thresholds (65%, 70%)
- Tighter/wider stop losses (1.5%, 2.5%)
- Different take profits (2%, 4%)
- RSI filters (55-75 range)
- Combined optimizations

**Outputs:**
- Performance comparison table
- Best configuration ranking
- Exact config.yaml changes to make

**Usage:**
```bash
python run_experiments.py --latest
python run_experiments.py logs/analytics/trade_analytics_20241104_120000.jsonl
```

---

## Example Workflow

### Day 1: Baseline
```bash
# Run bot with current settings
python run.py  # Let run for 1 hour

# Analyze results
python analyze_trades.py --latest
```

**Results:**
- 15 trades
- 60% win rate
- +2.5% total P&L
- Average P&L: +0.17%

### Day 1: Optimize
```bash
# Test different parameters
python run_experiments.py --latest
```

**Recommendations:**
- Increase min_confidence to 0.65
- Set RSI range 55-75
- Widen stops to 2.5%

**Expected improvement:** +1.2% P&L

### Day 2: Test Improvements
```bash
# Update config.yaml with recommended settings
# Run bot again
python run.py  # 1 hour

# Compare
python analyze_trades.py --latest
```

**New results:**
- 12 trades (fewer but higher quality)
- 75% win rate (+15%)
- +3.7% total P&L (+1.2%)
- Average P&L: +0.31% (+0.14%)

**✅ Improvement confirmed!**

---

## Key Files

```
CoinbaseTrading/
├── src/
│   └── trade_logger.py           # Analytics logger & replay engine
├── analyze_trades.py              # Performance analysis script
├── run_experiments.py             # Parameter optimization script
├── logs/
│   └── analytics/                 # Analytics data (auto-created)
│       ├── trade_analytics_*.jsonl
│       ├── trades_*.jsonl
│       └── market_state_*.jsonl
└── docs/
    └── ANALYTICS_GUIDE.md         # Full documentation
```

---

## Integration Points

### Already Integrated:
✅ MarketScanner - Logs all signals with indicators  
✅ TradeExecutor - Logs entry decisions, orders, fills  
✅ Main loop - Logs position updates, exit decisions  
✅ Automatic - No configuration needed

### What Gets Logged Automatically:

**Every market scan:**
- Product, signal, confidence, price
- RSI, ADX, and all indicators
- Last 5 candles for context

**Every trade decision:**
- Entry/skip reason
- Balance, risk checks
- Spread and volume analysis

**Every order:**
- Placement details
- Fill confirmation
- Actual fees & slippage

**Every position update:**
- Current P&L
- Holding time
- Current signal

**Every exit:**
- Exit reason
- Final P&L
- Total fees
- Complete trade summary

---

## Benefits

### 1. Data-Driven Decisions
- Know exactly what works
- No guesswork
- Quantified improvements

### 2. Risk-Free Testing
- Test strategies on real data
- No money at risk
- Instant feedback

### 3. Continuous Improvement
- Optimize every hour
- Track what works
- Compound your edge

### 4. Full Transparency
- Understand every trade
- See why trades won/lost
- Learn from mistakes

---

## Metrics to Track

**Daily:**
- [ ] Win rate >55%
- [ ] Profit factor >1.5
- [ ] Avg P&L >0.3% per trade
- [ ] Fees <20% of P&L

**Weekly:**
- [ ] Positive P&L days
- [ ] Best products identified
- [ ] Strategy refined

**Monthly:**
- [ ] Consistent profitability
- [ ] Compounding returns
- [ ] Drawdown <15%

---

## Advanced Usage

### Custom Experiments

```python
from trade_logger import TradeReplayEngine

engine = TradeReplayEngine('logs/analytics/trade_analytics_20241104_120000.jsonl')

# Very conservative
conservative = engine.replay_with_params(
    min_confidence=0.75,
    min_rsi=60,
    max_rsi=70,
    stop_loss_pct=1.0
)

# Very aggressive  
aggressive = engine.replay_with_params(
    min_confidence=0.55,
    stop_loss_pct=3.0
)

print(f"Conservative: {conservative['win_rate']*100:.1f}% WR, {conservative['total_pnl_pct']:+.2f}%")
print(f"Aggressive: {aggressive['win_rate']*100:.1f}% WR, {aggressive['total_pnl_pct']:+.2f}%")
```

### Extract Specific Data

```python
import json

# Load all completed trades
with open('logs/analytics/trades_20241104_120000.jsonl', 'r') as f:
    for line in f:
        trade = json.loads(line)
        if trade['event_type'] == 'trade_complete' and trade['was_winner']:
            print(f"{trade['product_id']}: +{trade['realized_pnl_pct']:.2f}% "
                  f"({trade['holding_time_hours']:.1f}h)")
```

---

## Troubleshooting

**No analytics files?**
- Check `logs/analytics/` exists
- Verify bot ran with updated code

**Experiments show no trades?**
- Parameters too strict (all trades filtered)
- Try looser filters

**Analysis errors?**
- Need at least 1 completed trade
- Check JSONL files aren't corrupted

---

## Next Steps

1. ✅ Run bot for 1 hour
2. ✅ Analyze with `python analyze_trades.py --latest`
3. ✅ Optimize with `python run_experiments.py --latest`
4. ✅ Apply best configuration
5. ✅ Test and iterate

**Remember:** Every hour generates insights. Use them!

For complete documentation, see `docs/ANALYTICS_GUIDE.md`
