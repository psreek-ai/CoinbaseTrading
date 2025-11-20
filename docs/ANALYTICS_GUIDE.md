# Trade Analytics & Strategy Experimentation Guide

## Overview

The enhanced logging system captures **every detail** of your trading session in structured JSON format, allowing you to:

1. **Replay trades** with different parameters without risking real money
2. **Identify optimal strategy** configurations through experimentation
3. **Understand why trades won or lost** with full market context
4. **Backtest improvements** before deploying them live

## How It Works

### 1. Automatic Data Collection

When you run the bot, it creates three log files in `logs/analytics/`:

```
logs/analytics/
├── trade_analytics_20241104_120000.jsonl    # Main events log
├── trades_20241104_120000.jsonl             # Trade lifecycle
└── market_state_20241104_120000.jsonl       # Market snapshots
```

### What Gets Logged

#### Market Scans
- All products scanned
- Signals generated (BUY/SELL/HOLD)
- Indicator values (RSI, ADX, MACD, etc.)
- Confidence scores
- Last 5 candles for context

#### Entry Decisions
- Why trade was taken or skipped
- Balance and risk checks
- Spread analysis
- Volume flow analysis
- Position sizing calculations

#### Order Execution
- Order placement details
- Expected fees and slippage
- Actual fill prices
- Fill time
- Order type (limit vs market)

#### Position Monitoring
- Current price updates
- Unrealized P&L
- Holding time
- Current signals
- Stop-loss/take-profit status

#### Exit Decisions
- Exit reason (profit, loss, signal, emergency)
- Final P&L
- Total fees paid
- Holding duration
- Max profit/loss during position

#### Completed Trades (GOLD STANDARD)
```json
{
  "event_type": "trade_complete",
  "product_id": "BTC-USD",
  "entry_price": 50000.00,
  "exit_price": 51500.00,
  "realized_pnl_pct": 3.00,
  "total_fees": 0.20,
  "holding_time_hours": 2.5,
  "entry_signal": {
    "confidence": 0.72,
    "indicators": {"RSI": 65, "ADX": 28},
    "reasons": ["MACD bullish crossover", "Strong volume"]
  },
  "exit_reason": "3% PROFIT + SELL SIGNAL",
  "was_winner": true
}
```

## Using the Analytics Tools

### After 1 Hour of Trading

Run the analysis script:

```bash
# Analyze most recent session
python analyze_trades.py --latest

# Or specify a specific file
python analyze_trades.py logs/analytics/trade_analytics_20241104_120000.jsonl
```

#### Sample Output

```
📊 TRADING STATISTICS
--------------------------------------------------------------------------------
Total Trades:        15
Winners:             9 (60.0%)
Losers:              6 (40.0%)
Win Rate:            60.0%

Total P&L:           +4.50%
Average P&L:         +0.30%
Average Winner:      +1.20%
Average Loser:       -0.80%
Profit Factor:       1.50

⏱️  HOLDING TIME ANALYSIS
--------------------------------------------------------------------------------
Average Holding:     2.50 hours (150 minutes)
Avg Winner Holding:  3.20 hours
Avg Loser Holding:   1.50 hours

🏆 PRODUCT PERFORMANCE
--------------------------------------------------------------------------------
Product          Trades   Win Rate   Total P&L
BTC-USD          5        80.0%      +3.20%
ETH-USD          4        50.0%      +0.80%
SOL-USD          3        33.3%      -1.10%

🎯 SIGNAL CONFIDENCE ANALYSIS
--------------------------------------------------------------------------------
Confidence       Trades   Win Rate   Avg P&L
70-80%           6        83.3%      +1.50%
60-70%           7        57.1%      +0.20%
50-60%           2        0.0%       -1.20%
```

### Running Experiments

Test different parameters against your actual trades:

```bash
python run_experiments.py --latest
```

#### What It Tests

1. **Higher Confidence Thresholds**
   - 65%: Only trade most confident signals
   - 70%: Ultra-selective trading

2. **Stop Loss Variations**
   - 1.5%: Tighter stops (exit losers faster)
   - 2.5%: Wider stops (more room to breathe)

3. **Take Profit Variations**
   - 2%: Take profits faster
   - 4%: Let winners run longer

4. **RSI Filters**
   - 55-75: Trade only in momentum zone
   - Exclude overbought/oversold extremes

5. **Combined Optimizations**
   - Best combination of filters

#### Sample Experiment Output

```
🧪 RUNNING EXPERIMENTS
================================================================================

Testing: Higher Confidence (65%)
  Only trade signals with 65%+ confidence
  Trades:        12 (−3 filtered)
  Win Rate:      75.0% (+15.0%)
  Total P&L:     +6.20% (+1.70%)
  ✅ SIGNIFICANT IMPROVEMENT (+1.70%)

Testing: Tighter Stop Loss (1.5%)
  Exit losers faster at -1.5%
  Trades:        15 (−0 filtered)
  Win Rate:      60.0% (+0.0%)
  Total P&L:     +3.80% (−0.70%)
  ❌ Worse performance (−0.70%)

📊 EXPERIMENT RANKING
================================================================================
Rank   Experiment                       P&L         Win Rate   Trades
🥇     Higher Confidence (65%)         +6.20%       75.0%      12
🥈     Confidence + RSI                +5.50%       73.3%      11
🥉     Higher Take Profit (4%)         +5.10%       60.0%      15

🏆 RECOMMENDED CONFIGURATION
  Best Performer: Higher Confidence (65%)
  Expected Results:
    Win Rate:          75.0%
    Total P&L:         +6.20%
    Improvement:       +1.70% vs baseline
```

## Strategy Optimization Workflow

### Step 1: Run Trading Bot for 1 Hour

```bash
python run.py
```

Let it trade normally. It automatically logs everything.

### Step 2: Analyze Results

```bash
python analyze_trades.py --latest
```

Review:
- ✅ Win rate (target: >55%)
- ✅ Profit factor (target: >1.5)
- ✅ Average winner > Average loser
- ⚠️ Fee percentage (<20% of P&L)
- ⚠️ Exit reasons (are stops too tight?)

### Step 3: Run Experiments

```bash
python run_experiments.py --latest
```

This tests 9 different parameter combinations instantly.

### Step 4: Apply Best Configuration

The script shows you exactly what to change in `config.yaml`:

```yaml
trading:
  min_signal_confidence: 0.65  # ← Was 0.60

strategies:
  momentum:
    rsi_momentum_buy_lower_bound: 55  # ← Was 50
    rsi_momentum_buy_upper_bound: 75  # ← Was 80

risk_management:
  default_stop_loss_percent: 0.020   # ← Was 0.015 (1.5% → 2.0%)
  default_take_profit_percent: 0.035 # ← Was 0.030 (3.0% → 3.5%)
```

### Step 5: Test Improved Configuration

Run bot for another hour with new settings and compare.

## Advanced: Custom Experiments

You can write custom experiments in Python:

```python
from trade_logger import TradeReplayEngine

# Load your data
engine = TradeReplayEngine('logs/analytics/trade_analytics_20241104_120000.jsonl')

# Custom experiment: Very conservative
result = engine.replay_with_params(
    min_confidence=0.75,
    min_rsi=60,
    max_rsi=70,
    stop_loss_pct=1.0,
    take_profit_pct=2.0
)

print(f"Win Rate: {result['win_rate']*100:.1f}%")
print(f"Total P&L: {result['total_pnl_pct']:+.2f}%")
print(f"Trades: {result['total_trades']}")

# Compare aggressive vs conservative
aggressive = engine.replay_with_params(min_confidence=0.55)
conservative = engine.replay_with_params(min_confidence=0.70)

print(f"Aggressive: {aggressive['total_trades']} trades, {aggressive['total_pnl_pct']:+.2f}%")
print(f"Conservative: {conservative['total_trades']} trades, {conservative['total_pnl_pct']:+.2f}%")
```

## What Makes This Powerful

### 1. Risk-Free Testing
- Test parameters on **real market data**
- No money at risk
- Instant results

### 2. Scientific Approach
- **Data-driven** decisions, not guesswork
- See exactly what works
- Quantify improvements

### 3. Continuous Improvement
- Run bot for 1 hour
- Analyze and optimize
- Apply improvements
- Repeat

### 4. Full Context
Every trade has:
- Market conditions at entry
- Indicator values
- Competing signals
- Actual execution details
- Complete exit logic

## Example: Finding Your Edge

### Scenario: You noticed many small losers

**Step 1: Analyze**
```bash
python analyze_trades.py --latest
```

**Output shows:**
```
Exit Reason Analysis:
  stop_loss hit          8 trades    -1.2% avg
  emergency exit         2 trades    -2.0% avg
```

**Hypothesis:** Stops are too tight for hourly timeframe.

**Step 2: Experiment**
```bash
python run_experiments.py --latest
```

**Results:**
- 1.5% stops: -0.7% worse (too tight)
- 2.0% stops: BASELINE
- 2.5% stops: +1.2% better ✅

**Step 3: Apply**
Update config:
```yaml
risk_management:
  default_stop_loss_percent: 0.025  # 2.5%
```

**Step 4: Verify**
Run for another hour, compare results.

## Logs Location

```
logs/
├── analytics/                              # Strategy experiment data
│   ├── trade_analytics_20241104_120000.jsonl
│   ├── trades_20241104_120000.jsonl
│   └── market_state_20241104_120000.jsonl
└── trading_bot_20241104_120000.log        # Standard logs
```

## File Formats

All files are **JSONL** (JSON Lines):
- One JSON object per line
- Easy to parse
- Can be processed with `jq`, Python, or any language
- Append-only (crash-safe)

### Example: Extract all winners

```bash
# Using jq
cat logs/analytics/trades_20241104_120000.jsonl | \
  jq -r 'select(.event_type == "trade_complete" and .was_winner == true) | 
  "\(.product_id): +\(.realized_pnl_pct)%"'
```

### Example: Find best products

```bash
cat logs/analytics/trades_20241104_120000.jsonl | \
  jq -r 'select(.event_type == "trade_complete") | 
  "\(.product_id),\(.realized_pnl_pct)"' | \
  awk -F, '{sum[$1]+=$2; count[$1]++} 
  END {for (p in sum) print p, sum[p]/count[p]}' | \
  sort -k2 -rn
```

## Key Metrics to Track

### Daily Review
- [ ] Win rate >55%
- [ ] Profit factor >1.5
- [ ] Average P&L per trade >0.3%
- [ ] Fees <20% of gross P&L

### Weekly Review
- [ ] Consistent positive days
- [ ] Improving win rate
- [ ] Best products identified
- [ ] Strategy parameters optimized

### Monthly Review
- [ ] Compounding returns
- [ ] Drawdown within limits (<15%)
- [ ] Strategy adapting to market

## Troubleshooting

### No analytics files generated
- Check `logs/analytics/` directory exists
- Verify bot is running with new code
- Look for errors in main log

### Experiments show no improvement
- Need more data (run longer)
- Try wider parameter ranges
- Market conditions may be challenging
- Review individual trade reasons

### Analysis script errors
- Ensure JSONL files aren't corrupted
- Check file permissions
- Verify Python environment

## Best Practices

1. **Run at least 1 hour** before analyzing
   - Minimum 10-15 trades for statistical validity
   - More data = better insights

2. **Compare apples to apples**
   - Same market conditions
   - Same timeframe
   - Same strategy type

3. **Don't overfit**
   - Parameters that work on 10 trades may not scale
   - Test on multiple sessions
   - Allow for market variation

4. **Document changes**
   - Keep notes on parameter changes
   - Track what worked and what didn't
   - Build your edge over time

## Next Steps

After enhancing the logging system:

1. ✅ Run bot for 1 hour
2. ✅ Run `python analyze_trades.py --latest`
3. ✅ Run `python run_experiments.py --latest`
4. ✅ Apply recommended configuration
5. ✅ Test and compare
6. ✅ Iterate to perfection

---

**Remember:** The goal is to find YOUR edge through data, not guesswork. Every hour of trading generates insights. Use them wisely!
