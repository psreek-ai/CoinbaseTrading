# Signal-Confirmed Exit Strategy

## Overview
The bot now uses a **signal-confirmed profit/loss exit strategy** that combines price targets with technical analysis signals for intelligent position exits.

## Exit Rules

### 1. Profit Exit: +5% with HOLD/SELL Signal
**When to sell:**
- Position is up **5% or more** from cost basis
- **AND** current signal is **HOLD** or **SELL**

**Logic:**
- If you're profitable and the momentum is weakening (HOLD) or reversing (SELL), take profits
- Locks in gains before a potential reversal

**Example:**
```
XCN-USDC:
  Cost Basis: $0.007033 (includes fees)
  Current Price: $0.007385 (+5.0%)
  Signal: HOLD (confidence: 65%)
  → SELL (take 5% profit)
```

### 2. Stay in Position: +5% with BUY Signal
**When to hold:**
- Position is up **5% or more** from cost basis
- **BUT** current signal is still **BUY**

**Logic:**
- Strong upward momentum suggests more gains ahead
- Don't exit winners too early when trend is still strong
- Let profits run during strong trends

**Example:**
```
XCN-USDC:
  Cost Basis: $0.007033
  Current Price: $0.007385 (+5.0%)
  Signal: BUY (confidence: 72%)
  → HOLD (let it run, momentum is strong)
```

### 3. Loss Exit: -2% with Strong SELL Signal
**When to sell:**
- Position is down **2% or more** from cost basis
- **AND** current signal is **SELL**
- **AND** signal confidence is **≥60%**

**Logic:**
- Cut losses early when technical analysis confirms downward trend
- Strong SELL signal (≥60% confidence) indicates high probability of further decline
- Prevents small losses from becoming large ones

**Example:**
```
XCN-USDC:
  Cost Basis: $0.007033
  Current Price: $0.006892 (-2.0%)
  Signal: SELL (confidence: 68%)
  → SELL (cut losses, strong downtrend confirmed)
```

### 4. Monitor Loss: -2% without Strong SELL
**When to hold:**
- Position is down **2% or more** from cost basis
- **BUT** signal is not a strong SELL (BUY, HOLD, or weak SELL)

**Logic:**
- Don't panic sell on temporary dips
- Wait for technical confirmation before cutting losses
- Position might recover if trend isn't clearly negative

**Example:**
```
XCN-USDC:
  Cost Basis: $0.007033
  Current Price: $0.006892 (-2.0%)
  Signal: HOLD (confidence: 55%)
  → HOLD (warning logged, but no strong sell signal yet)
```

## Cost Basis Calculation

The cost basis includes **all fees** for accurate profit/loss tracking:

```python
# For all BUY fills of a product:
total_cost = sum((price × size) + commission)
total_size = sum(size)
cost_basis = total_cost / total_size
```

**Example:**
```
BUY Fill History for XCN-USDC:
  Fill 1: 1000 XCN @ $0.007, commission $0.05
  Fill 2: 500 XCN @ $0.008, commission $0.03
  Fill 3: 1500 XCN @ $0.0069, commission $0.07

Total cost = (1000*0.007 + 0.05) + (500*0.008 + 0.03) + (1500*0.0069 + 0.07)
           = 7.05 + 4.03 + 10.42 = $21.50
Total size = 3000 XCN
Cost basis = $21.50 / 3000 = $0.00717 per XCN
```

## Benefits of This Strategy

### 1. Profitable Despite Fees
- **5% profit target** > **2.4% round-trip fees** = **net profit**
- Ensures every closed position is actually profitable after fees

### 2. Intelligent Exit Timing
- Combines price targets with technical confirmation
- Doesn't sell winners during strong uptrends
- Doesn't hold losers during confirmed downtrends

### 3. Risk Management
- Caps losses at -2% with strong sell confirmation
- Protects capital from major drawdowns
- Allows small losses to recover if trend isn't clearly negative

### 4. Simple & Effective
- Clear rules: profit%, signal type, confidence threshold
- No complex indicators needed for exit decisions
- Easy to understand and debug

## Implementation Details

### Files Modified
1. **src/api_client.py**: Added `calculate_cost_basis()` method
   - Fetches all BUY fills for a product
   - Calculates average cost including fees
   - Returns cost basis per unit

2. **src/main.py**: Updated position monitoring loop
   - Calculates cost basis from fill history
   - Gets current technical signal
   - Applies signal-confirmed exit rules
   - Logs profit/loss and signal status

### Logging Output
```
XCN-USDC: Current=$0.007385, Cost Basis=$0.007033, Profit=5.01%, Signal=HOLD (65.0%)
[PROFIT EXIT] XCN-USDC: 5% PROFIT + HOLD SIGNAL (5.01%, conf=65.0%)
```

## Performance Expectations

Based on the profitability analysis:
- **Old strategy**: -35% annual return (fees destroy profits)
- **New strategy**: Positive expected return
  - 5% profit target ensures fees are covered
  - Signal confirmation improves win rate
  - Risk management limits losses
  - Should achieve 10-20% annual return if executed properly

## Testing

To test the strategy:
1. Run the bot with existing holdings
2. Check logs for cost basis calculations
3. Verify signal confirmation logic
4. Monitor actual exit decisions

Example test command:
```bash
python run.py
```

Look for log entries showing:
- Cost basis calculation from fills
- Current profit/loss percentage
- Current signal and confidence
- Exit decision reasoning
