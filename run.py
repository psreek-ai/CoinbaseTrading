#!/usr/bin/env python3
"""
Unified launcher for the trading bot system.
Usage:
    python run.py               # Start the trading bot
    python run.py scan          # Scan for opportunities
    python run.py convert       # Convert holdings
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        # Default: run the trading bot
        from main import main as run_bot
        sys.exit(run_bot())
    
    command = sys.argv[1].lower()
    
    if command == 'scan':
        # Run the market scanner
        from find_best_opportunities import analyze_all_products
        analyze_all_products()
    
    elif command == 'convert':
        # Run the holdings converter
        from convert_holdings import interactive_mode
        interactive_mode()
    
    elif command == 'bot':
        # Explicitly run the bot
        from main import main as run_bot
        sys.exit(run_bot())
    
    else:
        print(f"Unknown command: {command}")
        print("\nUsage:")
        print("  python run.py           # Start trading bot")
        print("  python run.py bot       # Start trading bot")
        print("  python run.py scan      # Scan for opportunities")
        print("  python run.py convert   # Convert holdings")
        sys.exit(1)


if __name__ == "__main__":
    main()
