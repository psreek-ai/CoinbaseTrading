"""
Scan all tradable products on Coinbase for the best BUY opportunities.
This script will analyze all available trading pairs and rank them by signal strength.
"""

import sys
import os
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import pandas as pd

# Add src to path for when run from root directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import get_config
from api_client import CoinbaseAPI
from strategies import StrategyFactory
from database import DatabaseManager
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_all_products():
    """Scan all products and find the best opportunities."""
    
    # Load config
    config = get_config()
    
    # Initialize API client
    api_key, api_secret = config.get_api_credentials()
    api = CoinbaseAPI(api_key, api_secret)
    
    # Initialize strategy
    strategy_name = config.get('strategies.active_strategy', 'momentum')
    strategy_config = config.get(f'strategies.{strategy_name}', {})
    
    if strategy_name == 'hybrid':
        strategy_config = config['strategies']
    
    strategy = StrategyFactory.create_strategy(strategy_name, strategy_config)
    
    print("\n" + "=" * 80)
    print("COINBASE OPPORTUNITY SCANNER")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Strategy: {strategy.name}")
    print("=" * 80 + "\n")
    
    # Get configuration for data analysis
    granularity = config.get('trading.candle_granularity', 'FIFTEEN_MINUTE')
    periods = config.get('trading.candle_periods_for_analysis', 200)
    
    # Get portfolio and current holdings
    portfolio_id = api.get_portfolio_id()
    if not portfolio_id:
        logger.error("Could not get portfolio ID")
        return
    
    balances = api.get_account_balances(portfolio_id, min_usd_equivalent=Decimal('1.0'))
    
    print("Current Holdings:")
    print("-" * 80)
    total_equity = Decimal('0')
    holdings = []
    crypto_holdings = []  # Track crypto assets for analysis
    
    for asset, balance in balances.items():
        if balance > 0:
            # Get USD value
            if asset in ['USD', 'USDC']:
                usd_value = balance
                price = None
            else:
                price = api.get_latest_price(f"{asset}-USD")
                if not price:
                    price = api.get_latest_price(f"{asset}-USDC")
                usd_value = balance * price if price else Decimal('0')
                
                # Track crypto for analysis
                if price:
                    crypto_holdings.append({
                        'asset': asset,
                        'balance': balance,
                        'usd_value': usd_value,
                        'price': price
                    })
            
            total_equity += usd_value
            holdings.append({
                'asset': asset,
                'balance': balance,
                'usd_value': usd_value,
                'price': price
            })
            print(f"{asset:10s}: {balance:>15.8f} (${usd_value:>10.2f})")
    
    print("-" * 80)
    print(f"Total Equity: ${total_equity:.2f}")
    print("=" * 80 + "\n")
    
    # Analyze current holdings first
    if crypto_holdings:
        print("ANALYZING YOUR CURRENT HOLDINGS...")
        print("=" * 80)
        
        holding_signals = []
        
        for holding in crypto_holdings:
            asset = holding['asset']
            # Try both USD and USDC pairs
            product_id = f"{asset}-USD"
            
            try:
                print(f"Analyzing {product_id}...", end=" ")
                df = api.get_historical_data(product_id, granularity, periods)
                
                if df.empty or len(df) < 50:
                    print(f"⚠️  Insufficient data")
                    continue
                
                signal = strategy.analyze(df, product_id)
                
                holding_signals.append({
                    'asset': asset,
                    'product_id': product_id,
                    'signal': signal.action,
                    'confidence': signal.confidence,
                    'usd_value': holding['usd_value'],
                    'price': holding['price'],
                    'metadata': signal.metadata
                })
                
                # Color-code the output
                if signal.action == 'SELL':
                    print(f"🔴 SELL signal (confidence: {signal.confidence:.2f})")
                elif signal.action == 'BUY':
                    print(f"🟢 HOLD/BUY signal (confidence: {signal.confidence:.2f})")
                else:
                    print(f"⚪ HOLD (no strong signal)")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                logger.debug(f"Error analyzing {product_id}: {e}")
        
        # Summary of current holdings
        print("\n" + "=" * 80)
        print("RECOMMENDATION FOR YOUR HOLDINGS")
        print("=" * 80 + "\n")
        
        should_sell = [h for h in holding_signals if h['signal'] == 'SELL' and h['confidence'] >= 0.5]
        should_hold = [h for h in holding_signals if h['signal'] != 'SELL' or h['confidence'] < 0.5]
        
        if should_sell:
            print("🔴 Consider SELLING (weak/bearish signals):")
            for h in should_sell:
                reasons = h['metadata'].get('reasons', [])
                print(f"   - {h['asset']}: ${h['usd_value']:.2f} (confidence: {h['confidence']:.1%})")
                if reasons:
                    print(f"     Reasons: {', '.join(reasons)}")
        
        if should_hold:
            print("\n🟢 HOLD (neutral or bullish signals):")
            for h in should_hold:
                print(f"   - {h['asset']}: ${h['usd_value']:.2f} (signal: {h['signal']})")
        
        print("\n" + "=" * 80 + "\n")
    
    # Now continue with finding new opportunities...
    
    # Get all available products
    print("Fetching all available products...")
    try:
        # Request tradability status to get view_only field
        products_response = api.rest_client.get_products(get_tradability_status=True)
        all_products = []
        view_only_count = 0
        disabled_count = 0
        
        if hasattr(products_response, 'products'):
            for product in products_response.products:
                # Check if view_only (this is the key field!)
                if hasattr(product, 'view_only') and product.view_only:
                    view_only_count += 1
                    logger.debug(f"Skipping view-only: {product.product_id}")
                    continue
                
                # Filter for USD and USDC quote currencies, and tradable products
                if (product.quote_currency_id in ['USD', 'USDC'] and 
                    not product.is_disabled and 
                    product.status == 'online' and
                    product.trading_disabled == False):
                    all_products.append(product.product_id)
                else:
                    disabled_count += 1
        
        print(f"Found {len(all_products)} tradable products")
        print(f"Filtered out {view_only_count} view-only products")
        print(f"Filtered out {disabled_count} disabled/offline products\n")
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        return
    
    # Analyze all products
    print("Analyzing all products for BUY signals...")
    print("=" * 80)
    
    opportunities = []
    
    for i, product_id in enumerate(all_products):
        try:
            # Progress indicator
            if (i + 1) % 20 == 0:
                print(f"Progress: {i + 1}/{len(all_products)} products analyzed...")
            
            # Get historical data
            df = api.get_historical_data(product_id, granularity, periods)
            
            if df.empty or len(df) < 50:
                continue
            
            # Get signal
            signal = strategy.analyze(df, product_id)
            
            # Only track BUY signals
            if signal.action == 'BUY' and signal.confidence > 0:
                latest_price = df['Close'].iloc[-1]
                
                opportunities.append({
                    'product_id': product_id,
                    'signal': signal.action,
                    'confidence': signal.confidence,
                    'price': latest_price,
                    'metadata': signal.metadata
                })
                
                # Log strong signals immediately
                if signal.confidence >= 0.6:
                    print(f"🟢 STRONG BUY: {product_id} - Confidence: {signal.confidence:.2f} - Price: ${latest_price:.4f}")
        
        except Exception as e:
            logger.debug(f"Error analyzing {product_id}: {e}")
            continue
    
    print("=" * 80 + "\n")
    
    # Sort opportunities by confidence
    opportunities.sort(key=lambda x: x['confidence'], reverse=True)
    
    # Display top opportunities
    print("\n" + "=" * 80)
    print("TOP TRADING OPPORTUNITIES (Ranked by Signal Strength)")
    print("=" * 80)
    
    if not opportunities:
        print("\n⚠️  No BUY signals found at this time.")
        print("Market may be in a downtrend or consolidating.")
        print("Try again later or adjust strategy parameters.\n")
        return None
    
    print(f"\nFound {len(opportunities)} BUY signals:\n")
    
    # Display top 20
    for i, opp in enumerate(opportunities[:20], 1):
        confidence_bar = "█" * int(opp['confidence'] * 20)
        reasons = opp['metadata'].get('reasons', [])
        score = opp['metadata'].get('score', 0)
        
        print(f"{i:2d}. {opp['product_id']:15s} | Confidence: {opp['confidence']:.2f} {confidence_bar}")
        print(f"    Price: ${opp['price']:>12.4f} | Score: {score}")
        if reasons:
            print(f"    Reasons: {', '.join(reasons)}")
        print()
    
    print("=" * 80 + "\n")
    
    # Show exchange recommendation
    if opportunities:
        best = opportunities[0]
        
        print("\n" + "=" * 80)
        print("RECOMMENDED ACTION")
        print("=" * 80)
        print(f"\n🎯 Best Opportunity: {best['product_id']}")
        print(f"   Signal Confidence: {best['confidence']:.1%}")
        print(f"   Current Price: ${best['price']:.4f}")
        
        if best['metadata'].get('reasons'):
            print(f"   Why: {', '.join(best['metadata']['reasons'])}")
        
        # Calculate what to sell
        crypto_holdings = [h for h in holdings if h['asset'] not in ['USD', 'USDC']]
        
        if crypto_holdings:
            print("\n💰 Current Crypto Holdings to Exchange:")
            for holding in crypto_holdings:
                print(f"   - {holding['asset']}: ${holding['usd_value']:.2f}")
            
            total_crypto_value = sum(h['usd_value'] for h in crypto_holdings)
            print(f"\n   Total Available: ${total_crypto_value:.2f}")
            
            base_currency = best['product_id'].split('-')[0]
            estimated_amount = total_crypto_value / Decimal(str(best['price']))
            
            print(f"\n📊 Estimated {base_currency} you could acquire: {estimated_amount:.4f}")
            print(f"   (at current price of ${best['price']:.4f})")
        
        print("\n⚠️  IMPORTANT: Verify this pair is tradable on your account!")
        print("   Some pairs may show as 'view only' due to regional restrictions.")
        print("   Check your Coinbase app before proceeding.")
        
        print("\n" + "=" * 80)
        
        return {
            'best_opportunity': best,
            'all_opportunities': opportunities,
            'current_holdings': holdings,
            'total_equity': total_equity
        }
    
    return None


def execute_exchange(result):
    """Execute the exchange from current holdings to best opportunity using Convert API."""
    
    if not result:
        return
    
    best = result['best_opportunity']
    holdings = result['current_holdings']
    
    print("\n" + "=" * 80)
    print("CONVERSION PLAN (Using Coinbase Convert API)")
    print("=" * 80)
    
    # Get crypto holdings (exclude USD/USDC)
    crypto_holdings = [h for h in holdings if h['asset'] not in ['USD', 'USDC']]
    
    if not crypto_holdings:
        print("\n⚠️  No crypto holdings to convert.")
        print("You only have USD/USDC. The bot will use this for buying.\n")
        return
    
    config = get_config()
    paper_mode = config.get('trading.paper_trading_mode', True)
    
    mode_str = "PAPER TRADING" if paper_mode else "🔴 LIVE TRADING"
    print(f"\nMode: {mode_str}")
    print(f"\nTarget: {best['product_id']} (Confidence: {best['confidence']:.1%})")
    print("\nConversions:")
    print("-" * 80)
    
    # Show conversions
    total_value = Decimal('0')
    for i, holding in enumerate(crypto_holdings, 1):
        asset = holding['asset']
        balance = holding['balance']
        usd_value = holding['usd_value']
        total_value += usd_value
        
        base_currency = best['product_id'].split('-')[0]
        
        print(f"{i}. Convert {balance:.8f} {asset} → {base_currency}")
        print(f"   Value: ${usd_value:.2f}")
    
    # Estimated total
    base_currency = best['product_id'].split('-')[0]
    estimated_amount = total_value / Decimal(str(best['price']))
    
    print("-" * 80)
    print(f"Total Value: ${total_value:.2f}")
    print(f"Estimated {base_currency}: {estimated_amount:.8f}")
    print("-" * 80)
    
    # Confirmation
    print("\n⚠️  CONFIRMATION REQUIRED")
    
    if not paper_mode:
        print("🔴 WARNING: You are in LIVE TRADING mode!")
        print("🔴 This will execute REAL conversions on Coinbase!")
    
    response = input("\nProceed with conversion? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n❌ Conversion cancelled.\n")
        return
    
    # Execute conversions
    print("\n" + "=" * 80)
    print("EXECUTING CONVERSIONS...")
    print("=" * 80 + "\n")
    
    # Load API
    api_key, api_secret = config.get_api_credentials()
    from api_client import CoinbaseAPI
    api = CoinbaseAPI(api_key, api_secret)
    
    successful = []
    failed = []
    
    import time
    
    for holding in crypto_holdings:
        from_asset = holding['asset']
        amount = str(holding['balance'])
        to_asset = base_currency
        
        print(f"Converting {amount} {from_asset} → {to_asset}...")
        
        try:
            if paper_mode:
                # Simulate
                print(f"   [PAPER MODE] Simulated conversion")
                successful.append(holding)
                time.sleep(0.5)
            else:
                # Real conversion
                quote_response = api.rest_client.create_convert_quote(
                    from_account=from_asset,
                    to_account=to_asset,
                    amount=amount
                )
                
                if hasattr(quote_response, 'trade'):
                    trade = quote_response.trade
                    print(f"   Quote: {trade.source_amount} {trade.source_currency} → {trade.target_amount} {trade.target_currency}")
                    
                    # Commit conversion
                    commit_response = api.rest_client.commit_convert_trade(
                        trade_id=trade.id,
                        from_account=from_asset,
                        to_account=to_asset
                    )
                    
                    print(f"   ✅ Conversion successful!")
                    successful.append(holding)
                else:
                    print(f"   ❌ Failed to get quote")
                    failed.append(holding)
                
                time.sleep(1)  # Rate limiting
        
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed.append(holding)
            logger.error(f"Conversion error for {from_asset}: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("CONVERSION SUMMARY")
    print("=" * 80)
    
    if successful:
        print(f"\n✅ Successful: {len(successful)}")
        for h in successful:
            print(f"   - {h['asset']} (${h['usd_value']:.2f})")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}")
        for h in failed:
            print(f"   - {h['asset']} (${h['usd_value']:.2f})")
    
    print("\n" + "=" * 80)
    
    if successful and not paper_mode:
        print(f"\n✅ CONVERSIONS COMPLETE! Check your {base_currency} balance.\n")
    elif successful and paper_mode:
        print("\n✅ PAPER MODE: Conversions simulated.")
        print("Set paper_trading_mode: false in config.yaml for real trading.\n")


if __name__ == "__main__":
    try:
        result = analyze_all_products()
        
        if result:
            # Ask if user wants to execute the exchange
            print("\n" + "=" * 80)
            response = input("Would you like to execute this exchange? (yes/no): ").strip().lower()
            
            if response == 'yes':
                execute_exchange(result)
            else:
                print("\n✅ Analysis complete. No trades executed.\n")
        
    except KeyboardInterrupt:
        print("\n\n❌ Scan cancelled by user.\n")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
