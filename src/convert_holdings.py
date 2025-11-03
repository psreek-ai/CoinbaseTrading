"""
Convert your current crypto holdings to a target cryptocurrency using Coinbase Convert API.
This uses the native convert feature which is simpler than sell/buy orders.
"""

import sys
import os
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import time

# Add src to path for when run from root directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import get_config
from api_client import CoinbaseAPI
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def convert_to_target(target_asset: str, source_assets: list = None):
    """
    Convert holdings to target asset using Coinbase Convert API.
    
    Args:
        target_asset: The crypto to convert TO (e.g., 'ZKC', 'BTC', 'ETH')
        source_assets: List of assets to convert FROM. If None, converts all crypto except USD/USDC
    """
    
    # Load config
    config = get_config()
    
    # Initialize API client
    api_key, api_secret = config.get_api_credentials()
    api = CoinbaseAPI(api_key, api_secret)
    
    # Check paper trading mode
    paper_mode = config.get('trading.paper_trading_mode', True)
    
    print("\n" + "=" * 80)
    print("COINBASE CRYPTO CONVERTER")
    print("=" * 80)
    print(f"Mode: {'PAPER TRADING (SIMULATION)' if paper_mode else '🔴 LIVE TRADING'}")
    print(f"Target Asset: {target_asset}")
    print("=" * 80 + "\n")
    
    # Get portfolio and balances
    portfolio_id = api.get_portfolio_id()
    if not portfolio_id:
        logger.error("Could not get portfolio ID")
        return
    
    balances = api.get_account_balances(portfolio_id, min_usd_equivalent=Decimal('1.0'))
    
    print("Current Holdings:")
    print("-" * 80)
    
    # Identify what to convert
    crypto_to_convert = []
    total_value_to_convert = Decimal('0')
    
    for asset, balance in balances.items():
        # Skip stablecoins and the target asset
        if asset in ['USD', 'USDC', 'USDT', 'DAI', target_asset]:
            print(f"{asset:10s}: {balance:>15.8f} (keeping)")
            continue
        
        # If specific source assets provided, only convert those
        if source_assets and asset not in source_assets:
            print(f"{asset:10s}: {balance:>15.8f} (keeping)")
            continue
        
        # Get USD value
        price = api.get_latest_price(f"{asset}-USD")
        if not price:
            price = api.get_latest_price(f"{asset}-USDC")
        
        if price:
            usd_value = balance * price
            total_value_to_convert += usd_value
            crypto_to_convert.append({
                'asset': asset,
                'balance': balance,
                'usd_value': usd_value,
                'price': price
            })
            print(f"{asset:10s}: {balance:>15.8f} (${usd_value:>10.2f}) → will convert")
    
    print("-" * 80)
    print(f"Total Value to Convert: ${total_value_to_convert:.2f}")
    print("=" * 80 + "\n")
    
    if not crypto_to_convert:
        print("⚠️  No crypto holdings to convert!\n")
        return
    
    # Get target asset price
    target_price = api.get_latest_price(f"{target_asset}-USD")
    if not target_price:
        target_price = api.get_latest_price(f"{target_asset}-USDC")
    
    if target_price:
        estimated_target = total_value_to_convert / target_price
        print(f"📊 Estimated {target_asset} you'll receive: ~{estimated_target:.4f}")
        print(f"   (at current price ${target_price:.4f})\n")
    
    # Confirmation
    print("=" * 80)
    print("CONVERSION PLAN")
    print("=" * 80)
    
    for i, holding in enumerate(crypto_to_convert, 1):
        print(f"{i}. Convert {holding['balance']:.8f} {holding['asset']} → {target_asset}")
        print(f"   Value: ${holding['usd_value']:.2f}")
    
    print("=" * 80 + "\n")
    
    if not paper_mode:
        print("🔴 WARNING: LIVE TRADING MODE ENABLED!")
        print("🔴 This will execute REAL conversions on Coinbase!\n")
    
    response = input("Proceed with conversions? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("\n❌ Conversion cancelled.\n")
        return
    
    # Execute conversions
    print("\n" + "=" * 80)
    print("EXECUTING CONVERSIONS...")
    print("=" * 80 + "\n")
    
    successful_conversions = []
    failed_conversions = []
    
    for holding in crypto_to_convert:
        from_asset = holding['asset']
        amount = str(holding['balance'])
        
        print(f"Converting {amount} {from_asset} → {target_asset}...")
        
        try:
            if paper_mode:
                # Simulate conversion
                print(f"   [PAPER MODE] Simulated conversion")
                print(f"   Would convert: {amount} {from_asset} to {target_asset}")
                successful_conversions.append(holding)
                time.sleep(0.5)  # Simulate API delay
            else:
                # Real conversion using Coinbase Convert API
                # Create a convert quote
                quote_response = api.rest_client.create_convert_quote(
                    from_account=from_asset,
                    to_account=target_asset,
                    amount=amount
                )
                
                if hasattr(quote_response, 'trade'):
                    trade = quote_response.trade
                    print(f"   Quote ID: {trade.id}")
                    print(f"   From: {trade.source_amount} {trade.source_currency}")
                    print(f"   To: {trade.target_amount} {trade.target_currency}")
                    
                    # Commit the conversion
                    commit_response = api.rest_client.commit_convert_trade(
                        trade_id=trade.id,
                        from_account=from_asset,
                        to_account=target_asset
                    )
                    
                    print(f"   ✅ Conversion successful!")
                    successful_conversions.append(holding)
                else:
                    print(f"   ❌ Failed to get conversion quote")
                    failed_conversions.append(holding)
                
                time.sleep(1)  # Rate limiting
        
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed_conversions.append(holding)
            logger.error(f"Conversion error for {from_asset}: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("CONVERSION SUMMARY")
    print("=" * 80)
    
    if successful_conversions:
        print(f"\n✅ Successful: {len(successful_conversions)}")
        for holding in successful_conversions:
            print(f"   - {holding['asset']} (${holding['usd_value']:.2f})")
    
    if failed_conversions:
        print(f"\n❌ Failed: {len(failed_conversions)}")
        for holding in failed_conversions:
            print(f"   - {holding['asset']} (${holding['usd_value']:.2f})")
    
    print("\n" + "=" * 80)
    
    if successful_conversions and not paper_mode:
        print("\n✅ CONVERSIONS COMPLETE!")
        print(f"Check your Coinbase account for {target_asset} balance.\n")
    elif successful_conversions and paper_mode:
        print("\n✅ PAPER MODE: Conversions simulated successfully!")
        print("Set paper_trading_mode: false in config.yaml to execute real conversions.\n")


def interactive_mode():
    """Interactive mode to select target asset."""
    
    print("\n" + "=" * 80)
    print("INTERACTIVE CRYPTO CONVERTER")
    print("=" * 80 + "\n")
    
    # Load config and get balances
    config = get_config()
    api_key, api_secret = config.get_api_credentials()
    api = CoinbaseAPI(api_key, api_secret)
    
    portfolio_id = api.get_portfolio_id()
    balances = api.get_account_balances(portfolio_id, min_usd_equivalent=Decimal('1.0'))
    
    print("Your Current Holdings:")
    for i, (asset, balance) in enumerate(balances.items(), 1):
        price = api.get_latest_price(f"{asset}-USD") or api.get_latest_price(f"{asset}-USDC")
        value = balance * price if price else balance
        print(f"{i}. {asset}: {balance:.8f} (${value:.2f})")
    
    print("\n" + "=" * 80)
    target = input("\nEnter target crypto symbol (e.g., BTC, ETH, SOL): ").strip().upper()
    
    if not target:
        print("❌ No target specified. Exiting.\n")
        return
    
    # Ask which assets to convert
    print(f"\nConvert ALL crypto to {target}? (yes/no)")
    convert_all = input("Choice: ").strip().lower()
    
    if convert_all == 'yes':
        convert_to_target(target)
    else:
        print("\nEnter asset symbols to convert (comma-separated, e.g., ETH,NEAR):")
        source_input = input("Assets: ").strip().upper()
        source_assets = [a.strip() for a in source_input.split(',') if a.strip()]
        
        if source_assets:
            convert_to_target(target, source_assets)
        else:
            print("❌ No source assets specified. Exiting.\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert crypto holdings using Coinbase Convert API')
    parser.add_argument('--target', type=str, help='Target crypto symbol (e.g., BTC, ZKC)')
    parser.add_argument('--from', dest='from_assets', type=str, help='Comma-separated source assets (e.g., ETH,NEAR)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    
    args = parser.parse_args()
    
    try:
        if args.interactive or (not args.target and not args.from_assets):
            interactive_mode()
        elif args.target:
            source_list = None
            if args.from_assets:
                source_list = [a.strip().upper() for a in args.from_assets.split(',')]
            
            convert_to_target(args.target.upper(), source_list)
        else:
            print("Usage:")
            print("  Interactive: python convert_holdings.py -i")
            print("  Direct: python convert_holdings.py --target BTC")
            print("  Specific: python convert_holdings.py --target BTC --from ETH,NEAR")
    
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user.\n")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
