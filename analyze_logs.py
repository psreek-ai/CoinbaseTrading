import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

def analyze_log_file(filepath):
    print(f"Analyzing {filepath}...")
    
    stats = defaultdict(lambda: {
        'total_signals': 0,
        'buy_signals': 0,
        'sell_signals': 0,
        'hold_signals': 0,
        'total_confidence': 0.0,
        'buy_confidence_sum': 0.0,
        'high_confidence_buys': 0  # > 70%
    })
    
    top_opportunities = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if data.get('event_type') == 'signal_analysis':
                        strategy = data.get('strategy')
                        signal = data.get('signal')
                        confidence = data.get('confidence', 0.0)
                        product_id = data.get('product_id')
                        
                        if not strategy:
                            continue
                            
                        s = stats[strategy]
                        s['total_signals'] += 1
                        s['total_confidence'] += confidence
                        
                        if signal == 'BUY':
                            s['buy_signals'] += 1
                            s['buy_confidence_sum'] += confidence
                            if confidence > 0.7:
                                s['high_confidence_buys'] += 1
                                top_opportunities.append({
                                    'strategy': strategy,
                                    'product': product_id,
                                    'confidence': confidence,
                                    'timestamp': data.get('timestamp')
                                })
                        elif signal == 'SELL':
                            s['sell_signals'] += 1
                        else:
                            s['hold_signals'] += 1
                            
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Print Summary
    print("\n" + "="*80)
    print(f"{'STRATEGY':<20} | {'TOTAL':<8} | {'BUY':<6} | {'SELL':<6} | {'HIGH CONF':<10} | {'AVG BUY CONF':<12}")
    print("-" * 80)
    
    for strategy, s in stats.items():
        avg_buy_conf = (s['buy_confidence_sum'] / s['buy_signals']) * 100 if s['buy_signals'] > 0 else 0
        print(f"{strategy:<20} | {s['total_signals']:<8} | {s['buy_signals']:<6} | {s['sell_signals']:<6} | {s['high_confidence_buys']:<10} | {avg_buy_conf:>10.1f}%")

    print("\n" + "="*80)
    print("TOP 10 HIGH CONFIDENCE OPPORTUNITIES FOUND:")
    top_opportunities.sort(key=lambda x: x['confidence'], reverse=True)
    for opp in top_opportunities[:10]:
        print(f"{opp['timestamp']} | {opp['strategy']:<15} | {opp['product']:<15} | {opp['confidence']:.1%}")

if __name__ == "__main__":
    log_path = Path("logs/analytics/market_state_20251119_213246.jsonl")
    if log_path.exists():
        analyze_log_file(log_path)
    else:
        print(f"File not found: {log_path}")
