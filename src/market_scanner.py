
import logging
from decimal import Decimal
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from api_client import CoinbaseAPI
from strategies import BaseStrategy

logger = logging.getLogger(__name__)

class MarketScanner:
    def __init__(
        self,
        api: CoinbaseAPI,
        strategy: BaseStrategy,
        config: Dict
    ):
        self.api = api
        self.strategy = strategy
        self.config = config
        self._top_buy_signals = []

    def scan_all_products(self, shutdown_event):
        """
        Scan all tradable products for opportunities (OPTIMIZED).
        Uses parallel processing and caching for faster scanning.

        Returns:
            List of opportunities sorted by confidence
        """
        opportunities = []

        try:
            # Get all available products with tradability status
            products_response = self.api.rest_client.get_products(get_tradability_status=True)
            all_products = []

            if hasattr(products_response, 'products'):
                for product in products_response.products:
                    # Skip view-only products
                    if hasattr(product, 'view_only') and product.view_only:
                        continue

                    # Filter for USD/USDC and tradable products
                    if (product.quote_currency_id in ['USD', 'USDC'] and
                        not product.is_disabled and
                        product.status == 'online' and
                        product.trading_disabled == False):
                        all_products.append(product.product_id)

            logger.info(f"Scanning {len(all_products)} tradable products in parallel...")

            granularity = self.config.get('trading.candle_granularity', 'FIFTEEN_MINUTE')
            periods = self.config.get('trading.candle_periods_for_analysis', 200)
            min_confidence = self.config.get('trading.min_signal_confidence', 0.5)

            # OPTIMIZATION: Use parallel processing with ThreadPoolExecutor
            # Scan products in batches to avoid overwhelming the API
            max_workers = self.config.get('trading.max_scan_workers', 10)
            max_workers = min(max_workers, len(all_products))  # Don't exceed number of products

            def analyze_product_quick(product_id):
                """Quick product analysis for scanning."""
                # Check shutdown event before processing
                if shutdown_event.is_set():
                    return None
                    
                try:
                    # Get historical data
                    df = self.api.get_historical_data(product_id, granularity, periods)

                    if df.empty or len(df) < 50:
                        logger.debug(f"[SCAN] {product_id:15s} - Insufficient data (< 50 candles)")
                        return None

                    # Check shutdown event before heavy computation
                    if shutdown_event.is_set():
                        return None

                    # Add indicators first so we can display them
                    df = self.strategy.add_indicators(df)

                    # Get signal
                    signal = self.strategy.analyze(df, product_id)
                    latest_price = df['Close'].iloc[-1]

                    # Extract key indicators for display (check what columns actually exist)
                    adx = None
                    rsi = None

                    # Try to find ADX column
                    adx_cols = [col for col in df.columns if 'ADX' in col]
                    if adx_cols:
                        adx = df[adx_cols[0]].iloc[-1]

                    # Try to find RSI column
                    rsi_cols = [col for col in df.columns if 'RSI' in col]
                    if rsi_cols:
                        rsi = df[rsi_cols[0]].iloc[-1]

                    # Build indicator string
                    indicators = ""
                    if adx is not None and rsi is not None:
                        indicators = f"ADX:{adx:5.1f} RSI:{rsi:5.1f}"
                    elif adx is not None:
                        indicators = f"ADX:{adx:5.1f}"
                    elif rsi is not None:
                        indicators = f"RSI:{rsi:5.1f}"

                    # Log each product scan with details (always show confidence)
                    confidence_pct = f"{signal.confidence:.1%}"
                    if signal.action == 'BUY':
                        reason = getattr(signal, 'reason', signal.metadata.get('reason', ''))
                        logger.info(f"[SCAN] {product_id:15s} - BUY  {confidence_pct:>6s} @ ${latest_price:>10.4f} | {indicators} | {reason}")
                    elif signal.action == 'SELL':
                        reason = getattr(signal, 'reason', signal.metadata.get('reason', ''))
                        logger.info(f"[SCAN] {product_id:15s} - SELL {confidence_pct:>6s} @ ${latest_price:>10.4f} | {indicators} | {reason}")
                    else:
                        # For HOLD, use debug level
                        logger.debug(f"[SCAN] {product_id:15s} - HOLD {confidence_pct:>6s} @ ${latest_price:>10.4f} | {indicators}")

                    # Return ALL BUY signals (both above and below threshold) for tracking
                    if signal.action == 'BUY':
                        return {
                            'product_id': product_id,
                            'signal': signal.action,
                            'confidence': signal.confidence,
                            'price': latest_price,
                            'metadata': signal.metadata,
                            'above_threshold': signal.confidence >= min_confidence
                        }

                except Exception as e:
                    logger.warning(f"[SCAN] {product_id:15s} - Error: {e}")

                return None

            # Process products in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(analyze_product_quick, product_id): product_id
                          for product_id in all_products}

                completed = 0
                all_buy_signals = []  # Track ALL BUY signals for top 3 logging

                for future in as_completed(futures):
                    if shutdown_event.is_set():
                        logger.info("Shutdown requested during scan - cancelling remaining tasks...")
                        # Cancel all pending futures
                        for f in futures:
                            f.cancel()
                        break

                    completed += 1
                    if completed % 25 == 0:  # Progress update every 25 products
                        logger.info(f"Scanned {completed}/{len(all_products)} products...")

                    result = future.result()
                    if result:
                        all_buy_signals.append(result)
                        if result['above_threshold']:
                            opportunities.append(result)

            # Sort all BUY signals by confidence
            all_buy_signals.sort(key=lambda x: x['confidence'], reverse=True)
            self._top_buy_signals = all_buy_signals[:3]  # Store top 3 for logging

            logger.debug(f"Total BUY signals found: {len(all_buy_signals)}")

            # Sort opportunities (above threshold) by confidence
            opportunities.sort(key=lambda x: x['confidence'], reverse=True)

            logger.info(f"Scan complete: Found {len(opportunities)} opportunities above {min_confidence:.0%} confidence")
            if len(all_buy_signals) > 0:
                logger.info(f"(Total BUY signals including below threshold: {len(all_buy_signals)})")


        except Exception as e:
            logger.error(f"Error in product scan: {e}", exc_info=True)

        return opportunities

    def analyze_current_holdings(self, balances: Dict[str, Decimal], shutdown_event):
        """
        Analyze current crypto holdings to determine if they should be held or sold (OPTIMIZED).
        Uses parallel processing for faster analysis.

        Args:
            balances: Current account balances
        """
        crypto_holdings = []
        min_holding_value = Decimal('10.0')  # Minimum $10 to match risk management settings

        # Identify crypto assets (not USD/USDC/DAI/stablecoins)
        stablecoins = {'USD', 'USDC', 'DAI', 'USDT', 'BUSD', 'EURC', 'TUSD', 'PYUSD'}
        
        for asset, balance in balances.items():
            if asset not in stablecoins and balance > 0:
                # Get current price
                price = self.api.get_latest_price(f"{asset}-USD")
                if not price:
                    price = self.api.get_latest_price(f"{asset}-USDC")

                if price:
                    usd_value = balance * price
                    
                    # Skip small holdings (less than $10)
                    if usd_value < min_holding_value:
                        logger.debug(f"Skipping small holding: {asset} (${usd_value:.4f})")
                        continue
                    
                    crypto_holdings.append({
                        'asset': asset,
                        'balance': balance,
                        'usd_value': usd_value,
                        'price': price
                    })

        if not crypto_holdings:
            logger.info("No crypto holdings to analyze (excluding stablecoins and small positions)")
            return {'sell': [], 'hold': []}

        logger.info(f"Analyzing {len(crypto_holdings)} current holdings in parallel...")

        granularity = self.config.get('trading.candle_granularity', 'FIFTEEN_MINUTE')
        periods = self.config.get('trading.candle_periods_for_analysis', 200)
        min_sell_confidence = self.config.get('trading.min_signal_confidence', 0.5)

        def analyze_holding(holding):
            """Analyze a single holding."""
            # Check shutdown event before processing
            if shutdown_event.is_set():
                return None
                
            asset = holding['asset']
            product_id = f"{asset}-USD"

            try:
                df = self.api.get_historical_data(product_id, granularity, periods)

                if df.empty or len(df) < 50:
                    logger.debug(f"Insufficient data for {product_id}")
                    return None
                
                # Check shutdown event before heavy computation
                if shutdown_event.is_set():
                    return None

                signal = self.strategy.analyze(df, product_id)

                return {
                    'asset': asset,
                    'product_id': product_id,
                    'signal': signal.action,
                    'confidence': signal.confidence,
                    'balance': holding['balance'],  # Add balance for conversions
                    'usd_value': holding['usd_value'],
                    'metadata': signal.metadata
                }

            except Exception as e:
                logger.debug(f"Error analyzing holding {product_id}: {e}")
                return None

        # OPTIMIZATION: Analyze holdings in parallel
        holding_signals = []
        max_workers = self.config.get('trading.max_holdings_workers', 3)
        max_workers = min(max_workers, len(crypto_holdings))  # Don't exceed number of holdings

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(analyze_holding, h): h for h in crypto_holdings}

            for future in as_completed(futures):
                if shutdown_event.is_set():
                    logger.info("Shutdown requested during holdings analysis - cancelling remaining tasks...")
                    # Cancel all pending futures
                    for f in futures:
                        f.cancel()
                    break

                result = future.result()
                if result:
                    holding_signals.append(result)

                    # Log the signal
                    if result['signal'] == 'SELL' and result['confidence'] >= min_sell_confidence:
                        logger.warning(f"[SELL] {result['asset']}: SELL signal (confidence: {result['confidence']:.1%}) - Value: ${result['usd_value']:.2f}")
                        reasons = result['metadata'].get('reasons', [])
                        if reasons:
                            logger.warning(f"   Reasons: {', '.join(reasons)}")
                    elif result['signal'] == 'BUY':
                        logger.info(f"[BUY/HOLD] {result['asset']}: BUY/HOLD signal (confidence: {result['confidence']:.1%}) - Value: ${result['usd_value']:.2f}")
                    else:
                        logger.info(f"[HOLD] {result['asset']}: HOLD signal (confidence: {result['confidence']:.1%}) - Value: ${result['usd_value']:.2f}")

        # Summary and return SELL/HOLD signals for potential conversion
        should_sell = [h for h in holding_signals if h['signal'] == 'SELL' and h['confidence'] >= min_sell_confidence]
        hold_signals = [h for h in holding_signals if h['signal'] not in ['SELL', 'BUY']]

        if should_sell:
            logger.warning(f"WARNING: {len(should_sell)} holdings have SELL signals:")
            for h in should_sell:
                logger.warning(f"   - {h['asset']}: ${h['usd_value']:.2f} (confidence: {h['confidence']:.1%})")

        # Return both SELL and HOLD signals for potential conversion
        # SELL signals will be converted first, HOLD signals can be converted if BUY is much stronger
        return {'sell': should_sell, 'hold': hold_signals}
