"""
Scan all tradable products on Coinbase for the best BUY opportunities.
This script uses the TradingBot's unified scanning logic to ensure consistency.
"""

import sys
import os
from decimal import Decimal
from datetime import datetime

# Add src to path for when run from root directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import get_config
from main import TradingBot
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_all_products():
    """Scan all products and find the best opportunities using TradingBot's unified logic."""
    
    # Load config
    config = get_config()
    
    # Initialize the TradingBot (this handles API, strategy, database setup)
    bot = TradingBot(config)
    
    print("\n" + "=" * 80)
    print("COINBASE OPPORTUNITY SCANNER")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Strategy: {bot.strategy.name}")
    print("=" * 80 + "\n")
    
    # Get current holdings
    portfolio_id = bot.api.get_portfolio_id()
    balances = bot.api.get_account_balances(portfolio_id, min_usd_equivalent=Decimal('1.0'))
    
    # Analyze current holdings (uses MarketScanner's logic)
    bot.market_scanner.analyze_current_holdings(balances, bot._shutdown_event)
    
    # Scan all products for opportunities (uses MarketScanner's optimized parallel scanning)
    print("\nFetching all available products...")
    opportunities = bot.market_scanner.scan_all_products(bot._shutdown_event)
    
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
        
        # Get current holdings
        portfolio_id = bot.api.get_portfolio_id()
        balances = bot.api.get_account_balances(portfolio_id, min_usd_equivalent=Decimal('1.0'))
        
        holdings = []
        total_equity = Decimal('0')
        for asset, balance in balances.items():
            if balance > 0:
                if asset in ['USD', 'USDC']:
                    usd_value = balance
                else:
                    price = bot.api.get_latest_price(f"{asset}-USD")
                    if not price:
                        price = bot.api.get_latest_price(f"{asset}-USDC")
                    usd_value = balance * price if price else Decimal('0')
                
                total_equity += usd_value
                holdings.append({
                    'asset': asset,
                    'balance': balance,
                    'usd_value': usd_value
                })
        
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
            'total_equity': total_equity,
            'bot': bot
        }
    
    return None


def execute_exchange(result):
    """Execute the exchange from current holdings to best opportunity using Convert API."""
    
    if not result:
        return
    
    best = result['best_opportunity']
    holdings = result['current_holdings']
    bot = result['bot']
    
    print("\n" + "=" * 80)
    print("CONVERSION PLAN (Using Coinbase Convert API)")
    print("=" * 80)
    
    # Get crypto holdings (exclude USD/USDC)
    crypto_holdings = [h for h in holdings if h['asset'] not in ['USD', 'USDC']]
    
    if not crypto_holdings:
        print("\n⚠️  No crypto holdings to convert.")
        print("You only have USD/USDC. The bot will use this for buying.\n")
        return
    
    config = bot.config
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
                # Real conversion using bot's API client
                quote_response = bot.api.rest_client.create_convert_quote(
                    from_account=from_asset,
                    to_account=to_asset,
                    amount=amount
                )
                
                if hasattr(quote_response, 'trade'):
                    trade = quote_response.trade
                    print(f"   Quote: {trade.source_amount} {trade.source_currency} → {trade.target_amount} {trade.target_currency}")
                    
                    # Commit conversion
                    commit_response = bot.api.rest_client.commit_convert_trade(
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
