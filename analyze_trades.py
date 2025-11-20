"""
Trade Analytics Analysis Script

Analyzes trade logs to identify best strategy parameters.
Run this after an hour of trading to experiment with different configurations.

Usage:
    python analyze_trades.py logs/analytics/trade_analytics_20241104_120000.jsonl
    python analyze_trades.py --latest  # Analyze most recent session
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import argparse


def load_jsonl(filepath):
    """Load JSONL file"""
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    return data


def analyze_session(analytics_file, trades_file, market_state_file):
    """Analyze a trading session"""
    
    print("=" * 80)
    print(f"TRADE ANALYTICS REPORT")
    print(f"Session File: {analytics_file}")
    print("=" * 80)
    print()
    
    # Load data
    analytics = load_jsonl(analytics_file) if Path(analytics_file).exists() else []
    trades = load_jsonl(trades_file) if Path(trades_file).exists() else []
    market_states = load_jsonl(market_state_file) if Path(market_state_file).exists() else []
    
    # Filter for completed trades
    completed_trades = [t for t in trades if t.get('event_type') == 'trade_complete']
    
    if not completed_trades:
        print("❌ No completed trades found in this session.")
        print(f"   Total events in analytics log: {len(analytics)}")
        print(f"   Total events in trades log: {len(trades)}")
        return
    
    # Basic Statistics
    print("📊 TRADING STATISTICS")
    print("-" * 80)
    
    total_trades = len(completed_trades)
    winners = [t for t in completed_trades if t.get('was_winner', False)]
    losers = [t for t in completed_trades if not t.get('was_winner', False)]
    
    total_pnl = sum(t.get('realized_pnl_pct', 0) for t in completed_trades)
    total_fees = sum(t.get('total_fees', 0) for t in completed_trades)
    
    avg_winner = sum(t.get('realized_pnl_pct', 0) for t in winners) / len(winners) if winners else 0
    avg_loser = sum(t.get('realized_pnl_pct', 0) for t in losers) / len(losers) if losers else 0
    
    print(f"Total Trades:        {total_trades}")
    print(f"Winners:             {len(winners)} ({len(winners)/total_trades*100:.1f}%)")
    print(f"Losers:              {len(losers)} ({len(losers)/total_trades*100:.1f}%)")
    print(f"Win Rate:            {len(winners)/total_trades*100:.1f}%")
    print()
    print(f"Total P&L:           {total_pnl:+.2f}%")
    print(f"Average P&L:         {total_pnl/total_trades:+.2f}%")
    print(f"Average Winner:      {avg_winner:+.2f}%")
    print(f"Average Loser:       {avg_loser:+.2f}%")
    print(f"Profit Factor:       {abs(avg_winner/avg_loser):.2f}" if avg_loser != 0 else "N/A")
    print()
    print(f"Total Fees Paid:     ${total_fees:.4f}")
    print(f"Fee % of P&L:        {abs(total_fees/total_pnl)*100:.1f}%" if total_pnl != 0 else "N/A")
    print()
    
    # Holding Time Analysis
    print("⏱️  HOLDING TIME ANALYSIS")
    print("-" * 80)
    
    holding_times = [t.get('holding_time_hours', 0) for t in completed_trades if t.get('holding_time_hours')]
    if holding_times:
        avg_holding = sum(holding_times) / len(holding_times)
        max_holding = max(holding_times)
        min_holding = min(holding_times)
        
        print(f"Average Holding:     {avg_holding:.2f} hours ({avg_holding*60:.0f} minutes)")
        print(f"Max Holding:         {max_holding:.2f} hours")
        print(f"Min Holding:         {min_holding:.2f} hours")
        
        # Winners vs losers holding time
        winner_holding = [t.get('holding_time_hours', 0) for t in winners if t.get('holding_time_hours')]
        loser_holding = [t.get('holding_time_hours', 0) for t in losers if t.get('holding_time_hours')]
        
        if winner_holding and loser_holding:
            avg_winner_hold = sum(winner_holding) / len(winner_holding)
            avg_loser_hold = sum(loser_holding) / len(loser_holding)
            print(f"Avg Winner Holding:  {avg_winner_hold:.2f} hours")
            print(f"Avg Loser Holding:   {avg_loser_hold:.2f} hours")
    print()
    
    # Product Performance
    print("🏆 PRODUCT PERFORMANCE")
    print("-" * 80)
    
    product_stats = defaultdict(lambda: {'trades': 0, 'winners': 0, 'pnl': 0})
    for trade in completed_trades:
        product_id = trade.get('product_id', 'UNKNOWN')
        product_stats[product_id]['trades'] += 1
        product_stats[product_id]['pnl'] += trade.get('realized_pnl_pct', 0)
        if trade.get('was_winner', False):
            product_stats[product_id]['winners'] += 1
    
    # Sort by P&L
    sorted_products = sorted(product_stats.items(), key=lambda x: x[1]['pnl'], reverse=True)
    
    print(f"{'Product':<15} {'Trades':<8} {'Win Rate':<10} {'Total P&L':>12}")
    print("-" * 80)
    for product_id, stats in sorted_products[:10]:
        win_rate = stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        print(f"{product_id:<15} {stats['trades']:<8} {win_rate:<9.1f}% {stats['pnl']:>+11.2f}%")
    print()
    
    # Exit Reason Analysis
    print("🚪 EXIT REASON ANALYSIS")
    print("-" * 80)
    
    exit_reasons = defaultdict(lambda: {'count': 0, 'pnl': 0})
    for trade in completed_trades:
        reason = trade.get('exit_reason', 'unknown')
        exit_reasons[reason]['count'] += 1
        exit_reasons[reason]['pnl'] += trade.get('realized_pnl_pct', 0)
    
    print(f"{'Exit Reason':<40} {'Count':<8} {'Avg P&L':>12}")
    print("-" * 80)
    for reason, stats in sorted(exit_reasons.items(), key=lambda x: x[1]['count'], reverse=True):
        avg_pnl = stats['pnl'] / stats['count'] if stats['count'] > 0 else 0
        print(f"{reason:<40} {stats['count']:<8} {avg_pnl:>+11.2f}%")
    print()
    
    # Strategy Performance
    print("📈 STRATEGY PERFORMANCE")
    print("-" * 80)
    
    strategy_stats = defaultdict(lambda: {'trades': 0, 'winners': 0, 'pnl': 0})
    for trade in completed_trades:
        strategy = trade.get('entry_strategy', 'unknown')
        strategy_stats[strategy]['trades'] += 1
        strategy_stats[strategy]['pnl'] += trade.get('realized_pnl_pct', 0)
        if trade.get('was_winner', False):
            strategy_stats[strategy]['winners'] += 1
    
    print(f"{'Strategy':<20} {'Trades':<8} {'Win Rate':<10} {'Total P&L':>12}")
    print("-" * 80)
    for strategy, stats in sorted(strategy_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
        win_rate = stats['winners'] / stats['trades'] * 100 if stats['trades'] > 0 else 0
        print(f"{strategy:<20} {stats['trades']:<8} {win_rate:<9.1f}% {stats['pnl']:>+11.2f}%")
    print()
    
    # Signal Analysis
    print("🎯 SIGNAL CONFIDENCE ANALYSIS")
    print("-" * 80)
    
    confidence_buckets = {
        '50-60%': [],
        '60-70%': [],
        '70-80%': [],
        '80-90%': [],
        '90-100%': []
    }
    
    for trade in completed_trades:
        entry_signal = trade.get('entry_signal', {})
        confidence = entry_signal.get('confidence', 0)
        
        if 0.5 <= confidence < 0.6:
            confidence_buckets['50-60%'].append(trade)
        elif 0.6 <= confidence < 0.7:
            confidence_buckets['60-70%'].append(trade)
        elif 0.7 <= confidence < 0.8:
            confidence_buckets['70-80%'].append(trade)
        elif 0.8 <= confidence < 0.9:
            confidence_buckets['80-90%'].append(trade)
        elif confidence >= 0.9:
            confidence_buckets['90-100%'].append(trade)
    
    print(f"{'Confidence':<15} {'Trades':<8} {'Win Rate':<10} {'Avg P&L':>12}")
    print("-" * 80)
    for bucket, trades_list in confidence_buckets.items():
        if trades_list:
            count = len(trades_list)
            winners_count = len([t for t in trades_list if t.get('was_winner', False)])
            win_rate = winners_count / count * 100
            avg_pnl = sum(t.get('realized_pnl_pct', 0) for t in trades_list) / count
            print(f"{bucket:<15} {count:<8} {win_rate:<9.1f}% {avg_pnl:>+11.2f}%")
    print()
    
    # Recommendations
    print("💡 OPTIMIZATION RECOMMENDATIONS")
    print("-" * 80)
    
    if avg_winner > 0 and avg_loser < 0:
        expectancy = (len(winners)/total_trades * avg_winner) + (len(losers)/total_trades * avg_loser)
        print(f"✓ Expectancy: {expectancy:+.2f}% per trade")
        
        if expectancy > 0:
            print("✓ Positive expectancy - strategy is profitable")
        else:
            print("✗ Negative expectancy - needs improvement")
        print()
    
    # Fee analysis
    avg_fee_per_trade = total_fees / total_trades
    if avg_fee_per_trade > abs(total_pnl / total_trades) * 0.3:
        print("⚠️  Fees are consuming >30% of profit - consider:")
        print("   - Increasing position sizes to reduce fee % impact")
        print("   - Ensuring limit orders (maker rebates)")
        print("   - Reducing trade frequency")
        print()
    
    # Win rate optimization
    if len(winners) / total_trades < 0.5:
        print("⚠️  Win rate <50% - consider:")
        print("   - Tightening entry criteria (higher confidence threshold)")
        print("   - Better signal filtering")
        print("   - Reviewing losing trades for patterns")
        print()
    
    # Holding time optimization
    if holding_times and avg_holding < 1:
        print("⚠️  Average holding time <1 hour - consider:")
        print("   - Increasing take profit targets")
        print("   - Using hourly timeframes for more stable signals")
        print("   - Reducing overtrading")
        print()
    
    print("=" * 80)
    print("✅ Analysis complete!")
    print()
    print("💡 To experiment with different parameters:")
    print(f"   from trade_logger import TradeReplayEngine")
    print(f"   engine = TradeReplayEngine('{analytics_file}')")
    print(f"   results = engine.replay_with_params(min_confidence=0.65, stop_loss_pct=2.0)")
    print("=" * 80)


def find_latest_session():
    """Find the most recent analytics file"""
    log_dir = Path('logs/analytics')
    if not log_dir.exists():
        return None
    
    analytics_files = list(log_dir.glob('trade_analytics_*.jsonl'))
    if not analytics_files:
        return None
    
    # Sort by modification time
    latest = max(analytics_files, key=lambda p: p.stat().st_mtime)
    return latest


def main():
    parser = argparse.ArgumentParser(description='Analyze trading session logs')
    parser.add_argument('file', nargs='?', help='Path to trade_analytics_*.jsonl file')
    parser.add_argument('--latest', action='store_true', help='Analyze most recent session')
    
    args = parser.parse_args()
    
    if args.latest:
        analytics_file = find_latest_session()
        if not analytics_file:
            print("❌ No analytics files found in logs/analytics/")
            sys.exit(1)
        print(f"📂 Analyzing latest session: {analytics_file}")
        print()
    elif args.file:
        analytics_file = Path(args.file)
        if not analytics_file.exists():
            print(f"❌ File not found: {analytics_file}")
            sys.exit(1)
    else:
        analytics_file = find_latest_session()
        if not analytics_file:
            print("❌ No analytics files found. Please specify a file or use --latest")
            print()
            print("Usage:")
            print("  python analyze_trades.py logs/analytics/trade_analytics_20241104_120000.jsonl")
            print("  python analyze_trades.py --latest")
            sys.exit(1)
        print(f"📂 No file specified, analyzing latest session: {analytics_file}")
        print()
    
    # Derive related files
    analytics_file = str(analytics_file)
    trades_file = analytics_file.replace('trade_analytics', 'trades')
    market_state_file = analytics_file.replace('trade_analytics', 'market_state')
    
    analyze_session(analytics_file, trades_file, market_state_file)


if __name__ == '__main__':
    main()
