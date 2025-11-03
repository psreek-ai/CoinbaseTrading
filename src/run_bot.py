#!/usr/bin/env python3
"""
Quick start script for the trading bot.
Performs basic checks before starting.
"""

import os
import sys
from pathlib import Path

def check_requirements():
    """Check if all requirements are met."""
    errors = []
    warnings = []
    
    # Check Python version
    if sys.version_info < (3, 9):
        errors.append(f"Python 3.9+ required. You have {sys.version}")
    
    # Check for .env file
    if not Path('.env').exists():
        errors.append(".env file not found. Create it with your API credentials.")
    
    # Check for config file
    config_path = Path('config/config.yaml')
    if not config_path.exists():
        errors.append("config/config.yaml not found.")
    
    # Try importing required packages
    required_packages = [
        'yaml',
        'pandas',
        'numpy',
        'pandas_ta',
        'dotenv',
        'coinbase'
    ]
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            errors.append(f"Required package '{package}' not installed. Run: pip install -r requirements.txt")
    
    # Check if in paper trading mode
    try:
        import yaml
        with open('config/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            paper_mode = config.get('trading', {}).get('paper_trading_mode', True)
            
            if not paper_mode:
                warnings.append("⚠️  LIVE TRADING MODE ENABLED - Real money will be used!")
            else:
                print("✅ Paper trading mode enabled (safe mode)")
    except Exception as e:
        warnings.append(f"Could not check paper trading mode: {e}")
    
    return errors, warnings

def main():
    """Main entry point."""
    print("=" * 70)
    print("COINBASE TRADING BOT - STARTUP CHECK")
    print("=" * 70)
    print()
    
    errors, warnings = check_requirements()
    
    # Display warnings
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
        print()
    
    # Display errors
    if errors:
        print("ERRORS - Cannot start bot:")
        for error in errors:
            print(f"  ❌ {error}")
        print()
        print("Fix the errors above and try again.")
        return 1
    
    print("✅ All checks passed!")
    print()
    print("Starting trading bot...")
    print("=" * 70)
    print()
    
    # Add src directory to path and run main
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import and run
    try:
        from main import main as run_bot
        run_bot()
    except KeyboardInterrupt:
        print("\n\nBot stopped by user.")
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
