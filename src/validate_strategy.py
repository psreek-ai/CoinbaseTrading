#!/usr/bin/env python3
"""
Standalone Strategy Validation Tool

Run comprehensive validation tests to guarantee the strategy works:
1. Backtest on historical data
2. Validate signal quality
3. Test paper trading performance

Usage:
    python src/validate_strategy.py --product BTC-USDC --days 30
    python src/validate_strategy.py --all-products --days 7
    python src/validate_strategy.py --validate-live --lookback 14
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_config
from api_client import CoinbaseClient
from database import DatabaseManager
from strategies.momentum_strategy import MomentumStrategy
from strategy_validator import StrategyValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backtest_single_product(validator: StrategyValidator, product_id: str, days: int):
    """Run backtest on a single product"""
    print(f"\n{'='*80}")
    print(f"BACKTESTING {product_id}")
    print(f"{'='*80}\n")
    
    try:
        result = validator.backtest_product(product_id, days=days)
        validator.print_backtest_summary(result)
        return result
    except Exception as e:
        logger.error(f"Failed to backtest {product_id}: {e}")
        return None


def backtest_multiple_products(validator: StrategyValidator, days: int):
    """Run backtest on top products"""
    # Top liquid products on Coinbase
    products = [
        'BTC-USDC', 'ETH-USDC', 'SOL-USDC', 'XRP-USDC',
        'ADA-USDC', 'DOGE-USDC', 'AVAX-USDC', 'LINK-USDC'
    ]
    
    results = []
    for product_id in products:
        result = backtest_single_product(validator, product_id, days)
        if result:
            results.append(result)
    
    # Print aggregate summary
    if results:
        print("\n" + "="*80)
        print("AGGREGATE RESULTS ACROSS ALL PRODUCTS")
        print("="*80)
        print(f"Products Tested: {len(results)}")
        print(f"Total Trades: {sum(r.total_trades for r in results)}")
        print(f"Avg Win Rate: {sum(r.win_rate for r in results) / len(results) * 100:.2f}%")
        print(f"Avg Return: {sum(r.total_return for r in results) / len(results) * 100:.2f}%")
        print(f"Avg Sharpe: {sum(r.sharpe_ratio for r in results) / len(results):.3f}")
        print(f"Avg Precision: {sum(r.precision() for r in results) / len(results) * 100:.2f}%")
        print(f"Avg F1 Score: {sum(r.f1_score() for r in results) / len(results):.3f}")
        print("="*80)
        
        # Save results
        filename = validator.save_backtest_results(results)
        print(f"\nDetailed results saved to: {filename}")
    
    return results


def validate_live_performance(validator: StrategyValidator, lookback_days: int):
    """Validate recent live trading performance"""
    print(f"\n{'='*80}")
    print(f"LIVE TRADING VALIDATION (Past {lookback_days} days)")
    print(f"{'='*80}\n")
    
    metrics = validator.validate_live_signals(lookback_days)
    
    print(f"Total Closed Positions: {metrics['total_positions']}")
    print(f"Profitable Positions: {metrics['profitable_positions']}")
    print(f"Win Rate: {metrics['win_rate']*100:.2f}%")
    print(f"Average Confidence: {metrics['avg_confidence']:.3f}")
    print(f"Total P&L: ${metrics.get('total_pnl', 0):.2f}")
    print(f"Avg P&L per Trade: ${metrics.get('avg_pnl', 0):.2f}")
    print(f"\nHigh Confidence (≥0.7) Win Rate: {metrics.get('high_confidence_win_rate', 0)*100:.2f}%")
    
    print("\n" + "="*80)
    print("CONFIDENCE vs OUTCOME ANALYSIS")
    print("="*80)
    print("\nThis shows if higher confidence signals are more profitable:")
    if 'confidence_vs_outcome' in metrics:
        print("\nConfidence Range | Total Trades | Winners | Win Rate | Avg P&L")
        print("-" * 70)
        for conf_range, data in metrics['confidence_vs_outcome'].items():
            print(f"{conf_range:^16} | {data.get('count', 0):^12} | "
                  f"{data.get('sum', 0):^7} | {data.get('mean', 0)*100:^8.1f}% | "
                  f"${data.get('pnl_mean', 0):^8.2f}")
    
    print("\n" + "="*80)
    print("VALIDATION VERDICT:")
    if metrics['total_positions'] == 0:
        print("⚠️  NO DATA - Run bot for at least a week to collect data")
    elif metrics['total_positions'] < 10:
        print("⚠️  INSUFFICIENT DATA - Need at least 10 trades for statistical significance")
    elif metrics['win_rate'] < 0.4:
        print("❌ STRATEGY NOT WORKING - Win rate too low (<40%)")
    elif metrics.get('high_confidence_win_rate', 0) < metrics['win_rate']:
        print("⚠️  SIGNAL QUALITY ISSUE - High confidence trades performing worse")
    elif metrics['win_rate'] >= 0.55 and metrics.get('high_confidence_win_rate', 0) >= 0.6:
        print("✅ STRATEGY WORKING WELL - Good win rate with confidence correlation")
    elif metrics['win_rate'] >= 0.5:
        print("✅ STRATEGY WORKING - Acceptable performance")
    else:
        print("⚠️  MARGINAL PERFORMANCE - Monitor closely")
    
    print("="*80)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Validate trading strategy performance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backtest BTC over 30 days
  python src/validate_strategy.py --product BTC-USDC --days 30
  
  # Backtest top 8 products
  python src/validate_strategy.py --all-products --days 30
  
  # Validate live trading performance
  python src/validate_strategy.py --validate-live --lookback 7
  
  # Full validation (backtest + live)
  python src/validate_strategy.py --all-products --days 30 --validate-live --lookback 14
        """
    )
    
    parser.add_argument(
        '--product',
        type=str,
        help='Product ID to backtest (e.g., BTC-USDC)'
    )
    
    parser.add_argument(
        '--all-products',
        action='store_true',
        help='Backtest top 8 liquid products'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days of history to backtest (default: 30)'
    )
    
    parser.add_argument(
        '--validate-live',
        action='store_true',
        help='Validate recent live trading performance'
    )
    
    parser.add_argument(
        '--lookback',
        type=int,
        default=7,
        help='Days to look back for live validation (default: 7)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not (args.product or args.all_products or args.validate_live):
        parser.error("Must specify --product, --all-products, or --validate-live")
    
    print("\n" + "="*80)
    print("STRATEGY VALIDATION FRAMEWORK")
    print("="*80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Load configuration
    logger.info("Loading configuration...")
    config = load_config()
    
    # Initialize components
    logger.info("Initializing API client...")
    api = CoinbaseClient(config)
    
    logger.info("Initializing database...")
    db = DatabaseManager(config['database']['path'])
    
    logger.info("Initializing strategy...")
    strategy = MomentumStrategy(config)
    
    logger.info("Initializing validator...")
    validator = StrategyValidator(strategy, api, db)
    
    # Run requested validations
    if args.product:
        backtest_single_product(validator, args.product, args.days)
    
    if args.all_products:
        backtest_multiple_products(validator, args.days)
    
    if args.validate_live:
        validate_live_performance(validator, args.lookback)
    
    print("\n✅ Validation complete!\n")


if __name__ == '__main__':
    main()
