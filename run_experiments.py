"""
Strategy Parameter Experiment Runner

Tests different strategy parameters against historical trades
to find optimal configuration.

Usage:
    python run_experiments.py --latest
    python run_experiments.py logs/analytics/trade_analytics_20241104_120000.jsonl
"""

import sys
import argparse
from pathlib import Path
from trade_logger import TradeReplayEngine


def run_experiments(analytics_file):
    """Run multiple parameter experiments"""
    
    print("=" * 80)
    print("STRATEGY PARAMETER OPTIMIZATION")
    print(f"Data Source: {analytics_file}")
    print("=" * 80)
    print()
    
    engine = TradeReplayEngine(analytics_file)
    
    # Load baseline
    print("📊 Loading baseline performance...")
    baseline = engine.replay_with_params()
    
    if 'error' in baseline:
        print(f"❌ {baseline['error']}")
        return
    
    print(f"✓ Loaded {baseline['total_trades']} completed trades")
    print()
    
    # Display baseline
    print("BASELINE PERFORMANCE (Current Configuration)")
    print("-" * 80)
    print(f"Total Trades:        {baseline['total_trades']}")
    print(f"Win Rate:            {baseline['win_rate']*100:.1f}%")
    print(f"Total P&L:           {baseline['total_pnl_pct']:+.2f}%")
    print(f"Average P&L:         {baseline['avg_pnl_pct']:+.2f}%")
    print(f"Average Winner:      {baseline['avg_winner_pct']:+.2f}%")
    print(f"Average Loser:       {baseline['avg_loser_pct']:+.2f}%")
    print(f"Profit Factor:       {baseline['profit_factor']:.2f}")
    print()
    
    # Experiment configurations
    experiments = [
        {
            'name': 'Higher Confidence (65%)',
            'params': {'min_confidence': 0.65},
            'description': 'Only trade signals with 65%+ confidence'
        },
        {
            'name': 'Higher Confidence (70%)',
            'params': {'min_confidence': 0.70},
            'description': 'Only trade signals with 70%+ confidence'
        },
        {
            'name': 'Tighter Stop Loss (1.5%)',
            'params': {'stop_loss_pct': 1.5},
            'description': 'Exit losers faster at -1.5%'
        },
        {
            'name': 'Wider Stop Loss (2.5%)',
            'params': {'stop_loss_pct': 2.5},
            'description': 'Give losers more room at -2.5%'
        },
        {
            'name': 'Lower Take Profit (2%)',
            'params': {'take_profit_pct': 2.0},
            'description': 'Take profits faster at +2%'
        },
        {
            'name': 'Higher Take Profit (4%)',
            'params': {'take_profit_pct': 4.0},
            'description': 'Let winners run to +4%'
        },
        {
            'name': 'RSI Filter (55-75)',
            'params': {'min_rsi': 55, 'max_rsi': 75},
            'description': 'Only trade when RSI between 55-75'
        },
        {
            'name': 'Confidence + RSI',
            'params': {'min_confidence': 0.65, 'min_rsi': 55, 'max_rsi': 75},
            'description': 'Combined: 65% confidence + RSI 55-75'
        },
        {
            'name': 'Optimized Setup',
            'params': {
                'min_confidence': 0.65,
                'min_rsi': 55,
                'max_rsi': 75,
                'stop_loss_pct': 2.0,
                'take_profit_pct': 3.0
            },
            'description': 'Conservative: 65% conf, RSI 55-75, -2% SL, +3% TP'
        }
    ]
    
    results = []
    
    print("🧪 RUNNING EXPERIMENTS")
    print("=" * 80)
    print()
    
    for exp in experiments:
        print(f"Testing: {exp['name']}")
        print(f"  {exp['description']}")
        
        result = engine.replay_with_params(**exp['params'])
        
        if 'error' in result:
            print(f"  ❌ {result['error']}")
            print()
            continue
        
        # Calculate improvement
        pnl_improvement = result['total_pnl_pct'] - baseline['total_pnl_pct']
        wr_improvement = (result['win_rate'] - baseline['win_rate']) * 100
        
        # Display key metrics
        print(f"  Trades:        {result['total_trades']} "
              f"({'−' if result['trades_filtered'] > 0 else ''}{result['trades_filtered']} filtered)")
        print(f"  Win Rate:      {result['win_rate']*100:.1f}% "
              f"({wr_improvement:+.1f}%)")
        print(f"  Total P&L:     {result['total_pnl_pct']:+.2f}% "
              f"({pnl_improvement:+.2f}%)")
        print(f"  Avg P&L:       {result['avg_pnl_pct']:+.2f}%")
        print(f"  Profit Factor: {result['profit_factor']:.2f}")
        
        # Performance indicator
        if pnl_improvement > 0.5:
            print(f"  ✅ SIGNIFICANT IMPROVEMENT ({pnl_improvement:+.2f}%)")
        elif pnl_improvement > 0:
            print(f"  ✓ Slight improvement ({pnl_improvement:+.2f}%)")
        elif pnl_improvement > -0.5:
            print(f"  ≈ Similar performance ({pnl_improvement:+.2f}%)")
        else:
            print(f"  ❌ Worse performance ({pnl_improvement:+.2f}%)")
        
        print()
        
        results.append({
            **exp,
            **result,
            'pnl_improvement': pnl_improvement,
            'wr_improvement': wr_improvement
        })
    
    # Summary ranking
    print("=" * 80)
    print("📊 EXPERIMENT RANKING (by Total P&L)")
    print("=" * 80)
    print()
    
    results_sorted = sorted(results, key=lambda x: x['total_pnl_pct'], reverse=True)
    
    print(f"{'Rank':<6} {'Experiment':<30} {'P&L':<12} {'Win Rate':<10} {'Trades':<8}")
    print("-" * 80)
    
    for i, result in enumerate(results_sorted, 1):
        rank_symbol = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        print(f"{rank_symbol:<6} {result['name']:<30} "
              f"{result['total_pnl_pct']:+10.2f}% "
              f"{result['win_rate']*100:>7.1f}% "
              f"{result['total_trades']:>6}")
    
    print()
    print("=" * 80)
    
    # Best configuration
    best = results_sorted[0]
    print("🏆 RECOMMENDED CONFIGURATION")
    print("=" * 80)
    print(f"Best Performer: {best['name']}")
    print(f"Description:    {best['description']}")
    print()
    print("Parameters:")
    for key, value in best['parameters_used'].items():
        if value is not None:
            print(f"  {key}: {value}")
    print()
    print("Expected Results:")
    print(f"  Total Trades:      {best['total_trades']}")
    print(f"  Win Rate:          {best['win_rate']*100:.1f}%")
    print(f"  Total P&L:         {best['total_pnl_pct']:+.2f}%")
    print(f"  Average P&L:       {best['avg_pnl_pct']:+.2f}%")
    print(f"  Profit Factor:     {best['profit_factor']:.2f}")
    print(f"  Improvement:       {best['pnl_improvement']:+.2f}% vs baseline")
    print()
    print("=" * 80)
    
    # Configuration recommendation
    print()
    print("📝 TO APPLY THIS CONFIGURATION:")
    print("-" * 80)
    print("Update config/config.yaml:")
    print()
    
    params = best['parameters_used']
    if params.get('min_confidence'):
        print(f"  trading:")
        print(f"    min_signal_confidence: {params['min_confidence']:.2f}")
        print()
    
    if params.get('min_rsi') or params.get('max_rsi'):
        print(f"  strategies:")
        print(f"    momentum:")
        if params.get('min_rsi'):
            print(f"      rsi_momentum_buy_lower_bound: {int(params['min_rsi'])}")
        if params.get('max_rsi'):
            print(f"      rsi_momentum_buy_upper_bound: {int(params['max_rsi'])}")
        print()
    
    if params.get('stop_loss_pct') or params.get('take_profit_pct'):
        print(f"  risk_management:")
        if params.get('stop_loss_pct'):
            print(f"    default_stop_loss_percent: {params['stop_loss_pct']/100:.4f}  # {params['stop_loss_pct']}%")
        if params.get('take_profit_pct'):
            print(f"    default_take_profit_percent: {params['take_profit_pct']/100:.4f}  # {params['take_profit_pct']}%")
    
    print()
    print("=" * 80)


def find_latest_session():
    """Find the most recent analytics file"""
    log_dir = Path('logs/analytics')
    if not log_dir.exists():
        return None
    
    analytics_files = list(log_dir.glob('trade_analytics_*.jsonl'))
    if not analytics_files:
        return None
    
    latest = max(analytics_files, key=lambda p: p.stat().st_mtime)
    return str(latest)


def main():
    parser = argparse.ArgumentParser(description='Run strategy parameter experiments')
    parser.add_argument('file', nargs='?', help='Path to trade_analytics_*.jsonl file')
    parser.add_argument('--latest', action='store_true', help='Use most recent session')
    
    args = parser.parse_args()
    
    if args.latest:
        analytics_file = find_latest_session()
        if not analytics_file:
            print("❌ No analytics files found in logs/analytics/")
            sys.exit(1)
    elif args.file:
        analytics_file = args.file
        if not Path(analytics_file).exists():
            print(f"❌ File not found: {analytics_file}")
            sys.exit(1)
    else:
        analytics_file = find_latest_session()
        if not analytics_file:
            print("❌ No analytics files found. Please specify a file or use --latest")
            print()
            print("Usage:")
            print("  python run_experiments.py logs/analytics/trade_analytics_20241104_120000.jsonl")
            print("  python run_experiments.py --latest")
            sys.exit(1)
    
    run_experiments(analytics_file)


if __name__ == '__main__':
    main()
