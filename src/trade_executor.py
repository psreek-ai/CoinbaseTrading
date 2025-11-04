
import logging
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from typing import Dict

from api_client import CoinbaseAPI
from database import DatabaseManager
from risk_management import RiskManager


logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(
        self,
        api: CoinbaseAPI,
        db: DatabaseManager,
        risk_manager: RiskManager,
        paper_trading: bool,
        strategy_name: str
    ):
        self.api = api
        self.db = db
        self.risk_manager = risk_manager
        self.paper_trading = paper_trading
        self.strategy_name = strategy_name

    def execute_buy_order(
        self,
        product_id: str,
        balances: Dict[str, Decimal],
        product_details: Dict,
        signal_metadata: Dict
    ):
        """
        Execute a buy order with full risk management and order preview.

        Args:
            product_id: Product to buy
            balances: Current balances
            product_details: Product trading rules
            signal_metadata: Metadata from trading signal
        """
        base_currency, quote_currency = product_id.split('-')

        # Check if we already have this asset
        if base_currency in balances:
            logger.info(f"Already holding {base_currency}, skipping buy")
            return

        # Check quote balance
        quote_balance = balances.get(quote_currency, Decimal('0'))
        if quote_balance <= 0:
            logger.warning(f"No {quote_currency} balance to buy {product_id}")
            return

        # Get total equity
        total_equity = self._get_total_equity(balances)
        if total_equity <= 0:
            logger.warning("Cannot calculate total equity")
            return

        # Get entry price with best bid/ask analysis
        bid_ask = self.api.get_best_bid_ask([product_id])

        if bid_ask and product_id in bid_ask:
            best_ask = bid_ask[product_id]['best_ask']
            spread = bid_ask[product_id]['spread']
            spread_pct = bid_ask[product_id]['spread_pct']

            # Check if spread is reasonable
            max_spread_pct = 0.5  # 0.5% max spread
            if spread_pct and spread_pct > max_spread_pct:
                logger.warning(f"Spread too wide ({spread_pct:.2f}% > {max_spread_pct}%), skipping entry")
                return

            # Place limit order slightly better than best ask (try to earn maker rebate)
            tick_size = Decimal('0.01')  # Adjust based on product
            entry_price = best_ask - tick_size if best_ask else self.api.get_latest_price(product_id)

            logger.info(f"Spread analysis: Best Ask=${best_ask}, Spread={spread_pct:.3f}%, Entry=${entry_price}")
        else:
            # Fallback to latest price if bid/ask not available
            entry_price = self.api.get_latest_price(product_id)
            if not entry_price:
                logger.warning(f"No price available for {product_id}")
                return

        # Analyze volume flow for confirmation
        volume_flow = self.api.analyze_volume_flow(product_id, lookback_trades=100)
        buy_pressure = volume_flow.get('buy_pressure', 0.5)
        net_pressure = volume_flow.get('net_pressure', 'neutral')

        logger.info(f"Volume flow: {buy_pressure:.1%} buy pressure ({net_pressure})")

        # Require moderate buy pressure for entry
        if buy_pressure < 0.45:
            logger.warning(f"Insufficient buy pressure ({buy_pressure:.1%}), skipping entry")
            return

        # Calculate stop loss and take profit
        stop_loss, take_profit = self.risk_manager.calculate_stop_loss_take_profit(
            entry_price, side='BUY'
        )

        # Calculate position size
        product_info = product_details.get(product_id, {})
        min_size = product_info.get('base_min_size', Decimal('0'))

        position_size, sizing_metadata = self.risk_manager.calculate_position_size(
            total_equity, entry_price, stop_loss, min_size
        )

        if position_size <= 0:
            logger.warning(f"Position size calculation failed: {sizing_metadata}")
            return

        # Check if we can open this position
        open_positions = self.db.get_open_positions()
        current_exposure = Decimal('0')

        for pos in open_positions:
            try:
                size = Decimal(str(pos['base_size']))
                price = Decimal(str(pos.get('current_price', pos['entry_price'])))
                current_exposure += (size * price) / total_equity
            except Exception as e:
                logger.error(f"Error calculating exposure: {e}")

        position_value = position_size * entry_price
        can_open, reason = self.risk_manager.can_open_position(
            len(open_positions), current_exposure, total_equity, position_value
        )

        if not can_open:
            logger.warning(f"Cannot open position: {reason}")
            return

        # Preview the order first
        logger.info(f"Previewing order for {product_id}...")
        preview = self.api.preview_order(
            product_id=product_id,
            side='BUY',
            size=position_size
        )

        if not preview:
            logger.error("Order preview failed - aborting trade")
            return

        # Check fees and slippage
        max_fee_percent = self.risk_manager.max_fee_percent
        max_slippage_percent = self.risk_manager.max_slippage_percent

        fee_percent = (preview['commission_total'] / position_value) * Decimal('100')
        slippage_percent = preview['slippage']

        if fee_percent > max_fee_percent:
            logger.warning(f"Fee too high: {fee_percent:.2f}% > {max_fee_percent}% - aborting trade")
            return

        if slippage_percent > max_slippage_percent:
            logger.warning(f"Slippage too high: {slippage_percent:.2f}% > {max_slippage_percent}% - aborting trade")
            return

        # Use preview's average price if available, otherwise use our calculated entry price
        actual_entry_price = preview.get('average_filled_price') or entry_price
        actual_size = preview['base_size']
        
        # Round size to product's base_increment to avoid precision errors
        if product_details:
            base_increment = product_details.get('base_increment', '0.00000001')
            actual_size = float(Decimal(str(actual_size)).quantize(
                Decimal(str(base_increment)), 
                rounding=ROUND_DOWN
            ))
            logger.debug(f"Rounded size to base_increment {base_increment}: {actual_size}")

        # Execute order
        logger.info("=" * 60)
        logger.info(f"EXECUTING BUY ORDER: {product_id}")
        logger.info(f"Size: {actual_size} | Entry: ${actual_entry_price}")
        logger.info(f"Fee: ${preview['commission_total']:.4f} ({fee_percent:.2f}%)")
        logger.info(f"Slippage: {slippage_percent:.2f}%")
        logger.info(f"Stop Loss: {stop_loss} | Take Profit: {take_profit}")
        logger.info(f"Position Value: ${position_value:.2f}")
        logger.info("=" * 60)

        if self.paper_trading:
            # Paper trading: Simulate limit order with post-only
            order_id = f"PAPER_LIMIT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{product_id}"

            # Save to database with preview data
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'BUY',
                'order_type': 'limit_gtc_post_only',
                'status': 'filled',
                'base_size': actual_size,
                'entry_price': actual_entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'metadata': {
                    'signal': signal_metadata,
                    'sizing': sizing_metadata,
                    'preview': {
                        'commission': float(preview['commission_total']),
                        'slippage': float(slippage_percent),
                        'fee_percent': float(fee_percent)
                    },
                    'volume_flow': {
                        'buy_pressure': float(buy_pressure),
                        'net_pressure': net_pressure
                    },
                    'spread_analysis': {
                        'spread_pct': spread_pct if 'spread_pct' in locals() else None
                    },
                    'paper_trade': True,
                    'post_only': True  # Flag that this earns maker rebates
                }
            })

            # Open position with preview data
            self.db.insert_position({
                'product_id': product_id,
                'base_size': actual_size,
                'entry_price': actual_entry_price,
                'current_price': actual_entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'entry_order_id': order_id,
                'metadata': {
                    'strategy': self.strategy_name,
                    'signal': signal_metadata,
                    'fees_paid': float(preview['commission_total']),
                    'bracket_order': True  # Simulated bracket order
                }
            })

            # Start WebSocket for this product to monitor in real-time
            try:
                open_positions = self.db.get_open_positions()
                position_products = [p['product_id'] for p in open_positions]
                if position_products and not hasattr(self.api, 'websocket_running'):
                    # Paper trading: ticker only
                    self.api.start_websocket(position_products, enable_user_channel=False)
                    logger.info(f"WebSocket started for {len(position_products)} open positions")
                elif position_products:
                    # WebSocket already running, just log
                    logger.debug(f"Monitoring {len(position_products)} positions via WebSocket")
            except Exception as e:
                logger.warning(f"Could not start WebSocket: {e}")

            logger.info(f"[PAPER] Limit order (post-only) simulated: {order_id}")

        else:
            # Live trading: Place limit order with post-only for maker rebates
            logger.info("Placing live limit order with post-only (earning maker rebates)...")

            limit_order = self.api.place_limit_order_gtc(
                product_id=product_id,
                side='BUY',
                price=entry_price,
                size=actual_size,
                post_only=True  # CRITICAL: Ensures maker order (earns rebates)
            )

            if not limit_order:
                logger.error("Failed to place limit order")
                return

            order_id = limit_order.get('order_id')
            if not order_id:
                logger.error(f"Order placed but no order_id returned: {limit_order}")
                return
            
            logger.info(f"Limit order placed: {order_id}")

            # Save order to database with 'submitted' status
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'BUY',
                'order_type': 'limit_gtc_post_only',
                'status': 'submitted',
                'base_size': actual_size,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'metadata': {
                    'signal': signal_metadata,
                    'sizing': sizing_metadata,
                    'post_only': True,
                    'submitted_at': datetime.utcnow().isoformat()
                }
            })

            # Monitor order for fill (wait up to 30 seconds)
            logger.info(f"Monitoring limit order {order_id} for fill...")
            import time
            filled = False
            for i in range(30):
                time.sleep(1)
                order_status = self.api.get_order_status(order_id)
                if order_status and order_status['status'] in ['FILLED', 'CANCELLED', 'EXPIRED']:
                    filled = order_status['status'] == 'FILLED'
                    logger.info(f"Order {order_id} status: {order_status['status']}")
                    break

            if not filled:
                logger.warning(f"Limit order {order_id} not filled within 30s - cancelling to prevent ghost order")

                # CRITICAL: Cancel the order to prevent it from becoming a ghost order
                try:
                    cancel_result = self.api.cancel_order(order_id)
                    if cancel_result:
                        logger.info(f"Successfully cancelled unfilled order: {order_id}")

                        # Update order status in database
                        cursor = self.db.conn.cursor()
                        cursor.execute(
                            "UPDATE orders SET status = 'cancelled', metadata = json_set(metadata, '$.cancelled_at', ?) WHERE client_order_id = ?",
                            (datetime.utcnow().isoformat(), order_id)
                        )
                        self.db.conn.commit()
                    else:
                        logger.error(f"Failed to cancel order {order_id} - GHOST ORDER RISK!")
                        logger.error("This order may fill later without the bot's knowledge!")
                except Exception as e:
                    logger.error(f"Exception while cancelling order {order_id}: {e}")
                    logger.error("CRITICAL: Ghost order may exist on exchange!")

                return

            # Get actual fill details
            fills = self.api.get_fills(order_id=order_id)
            actual_fill_price = entry_price
            actual_commission = Decimal('0')

            if fills:
                # Calculate average fill price and total commission
                total_size = sum(f['size'] for f in fills)
                weighted_price = sum(f['price'] * f['size'] for f in fills)
                actual_fill_price = weighted_price / total_size if total_size > 0 else entry_price
                actual_commission = sum(f['commission'] for f in fills)

                # Log maker/taker status
                maker_count = sum(1 for f in fills if f.get('liquidity_indicator') == 'MAKER')
                logger.info(f"Fill details: {maker_count}/{len(fills)} fills were MAKER (earning rebates)")

            # Save to database
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'BUY',
                'order_type': 'limit_gtc_post_only',
                'status': 'filled',
                'base_size': actual_size,
                'entry_price': actual_fill_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'metadata': {
                    'signal': signal_metadata,
                    'sizing': sizing_metadata,
                    'preview': {
                        'commission': float(preview['commission_total']),
                        'slippage': float(slippage_percent),
                        'fee_percent': float(fee_percent)
                    },
                    'actual_fills': {
                        'commission': float(actual_commission),
                        'avg_price': float(actual_fill_price),
                        'num_fills': len(fills) if fills else 0
                    },
                    'live_trade': True,
                    'post_only': True
                }
            })

            # Now create stop-loss and take-profit orders
            logger.info(f"Creating stop-loss order at ${stop_loss}...")
            stop_order = self.api.create_stop_limit_order(
                product_id=product_id,
                side='SELL',
                base_size=actual_size,
                limit_price=stop_loss * Decimal('0.99'),  # Limit slightly below stop
                stop_price=stop_loss
            )

            logger.info(f"Creating take-profit order at ${take_profit}...")
            tp_order = self.api.place_limit_order_gtc(
                product_id=product_id,
                side='SELL',
                price=take_profit,
                size=actual_size,
                post_only=False  # Take profit can be taker
            )

            # Open position with actual fill price
            self.db.insert_position({
                'product_id': product_id,
                'base_size': actual_size,
                'entry_price': actual_fill_price,
                'current_price': actual_fill_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'entry_order_id': order_id,
                'metadata': {
                    'strategy': self.strategy_name,
                    'signal': signal_metadata,
                    'fees_paid': float(actual_commission),
                    'stop_order_id': stop_order['order_id'] if stop_order else None,
                    'tp_order_id': tp_order['order_id'] if tp_order else None,
                    'post_only_entry': True
                }
            })

            # Start WebSocket to monitor (with user channel for live trading)
            try:
                open_positions = self.db.get_open_positions()
                position_products = [p['product_id'] for p in open_positions]
                if position_products and not hasattr(self.api, 'websocket_running'):
                    # Live trading: enable user channel for real-time order updates
                    self.api.start_websocket(position_products, enable_user_channel=True)
                    logger.info(f"WebSocket started with user channel for {len(position_products)} open positions")
            except Exception as e:
                logger.warning(f"Could not start WebSocket: {e}")

            logger.info(f"[LIVE] Bracket order created: {order_id}")

    def execute_sell_order(
        self,
        product_id: str,
        position: Dict,
        exit_reason: str = 'signal'
    ):
        """
        Execute a sell order.

        Args:
            product_id: Product to sell
            position: Position data
            exit_reason: Reason for exit
        """
        base_currency = product_id.split('-')[0]

        position_size = Decimal(str(position['base_size']))
        entry_price = Decimal(str(position['entry_price']))

        # Get current price
        current_price = self.api.get_latest_price(product_id)
        if not current_price:
            logger.warning(f"No price available for {product_id}")
            return

        # Calculate PnL
        pnl = (current_price - entry_price) * position_size
        pnl_percent = ((current_price - entry_price) / entry_price) * 100

        logger.info("=" * 60)
        logger.info(f"EXECUTING SELL ORDER: {product_id}")
        logger.info(f"Size: {position_size} | Exit Price: {current_price}")
        logger.info(f"Entry: {entry_price} | PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
        logger.info(f"Exit Reason: {exit_reason}")
        logger.info("=" * 60)

        if self.paper_trading:
            order_id = f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S')}_{product_id}_SELL"

            # Save sell order
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'SELL',
                'order_type': 'market',
                'status': 'filled',
                'base_size': position_size,
                'filled_price': current_price,
                'metadata': {
                    'exit_reason': exit_reason,
                    'paper_trade': True
                }
            })

            # Close position
            self.db.close_position(product_id, float(current_price), float(pnl))

            # Record trade history
            entry_time = position.get('opened_at')
            exit_time = datetime.utcnow().isoformat()

            holding_time = None
            if entry_time:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                    holding_time = int((exit_dt - entry_dt).total_seconds())
                except:
                    pass

            self.db.insert_trade_history({
                'product_id': product_id,
                'side': 'BUY',  # Original side
                'entry_price': entry_price,
                'exit_price': current_price,
                'size': position_size,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'entry_time': entry_time or datetime.utcnow().isoformat(),
                'exit_time': exit_time,
                'holding_time_seconds': holding_time,
                'strategy': self.strategy_name,
                'exit_reason': exit_reason
            })

            logger.info(f"[PAPER] SELL order executed: {order_id}")
        else:
            # Live trading: Place market sell order
            logger.info("Placing live market SELL order...")

            # First, cancel any open SL/TP orders for this position
            metadata = position.get('metadata', {})
            stop_order_id = metadata.get('stop_order_id')
            tp_order_id = metadata.get('tp_order_id')

            cancelled_orders = []
            if stop_order_id:
                try:
                    cancel_result = self.api.cancel_order(stop_order_id)
                    if cancel_result:
                        logger.info(f"Cancelled stop-loss order: {stop_order_id}")
                        cancelled_orders.append(stop_order_id)
                except Exception as e:
                    logger.warning(f"Could not cancel stop-loss order {stop_order_id}: {e}")

            if tp_order_id:
                try:
                    cancel_result = self.api.cancel_order(tp_order_id)
                    if cancel_result:
                        logger.info(f"Cancelled take-profit order: {tp_order_id}")
                        cancelled_orders.append(tp_order_id)
                except Exception as e:
                    logger.warning(f"Could not cancel take-profit order {tp_order_id}: {e}")

            # Place market sell order
            sell_order = self.api.place_market_order(
                product_id=product_id,
                side='SELL',
                size=float(position_size)
            )

            if not sell_order:
                logger.error(f"Failed to place market SELL order for {product_id}")
                return

            order_id = sell_order['order_id']
            logger.info(f"Market SELL order placed: {order_id}")

            # Wait for fill confirmation (market orders fill quickly)
            import time
            filled = False
            actual_fill_price = current_price
            actual_commission = Decimal('0')

            for i in range(10):  # Wait up to 10 seconds for market order fill
                time.sleep(1)
                order_status = self.api.get_order_status(order_id)
                if order_status and order_status['status'] == 'FILLED':
                    filled = True
                    logger.info(f"Market SELL order filled: {order_id}")

                    # Get actual fill details
                    fills = self.api.get_fills(order_id=order_id)
                    if fills:
                        total_size = sum(Decimal(str(f['size'])) for f in fills)
                        weighted_price = sum(Decimal(str(f['price'])) * Decimal(str(f['size'])) for f in fills)
                        actual_fill_price = weighted_price / total_size if total_size > 0 else current_price
                        actual_commission = sum(Decimal(str(f['commission'])) for f in fills)

                        logger.info(f"Fill price: {actual_fill_price}, Commission: {actual_commission}")
                    break

            if not filled:
                logger.error(f"Market SELL order did not fill within 10 seconds: {order_id}")
                logger.error("CRITICAL: Position may still be open on exchange but bot cannot confirm!")
                return

            # Recalculate PnL with actual fill price
            pnl = (actual_fill_price - entry_price) * position_size
            pnl_percent = ((actual_fill_price - entry_price) / entry_price) * 100

            # Save sell order to database
            self.db.insert_order({
                'client_order_id': order_id,
                'product_id': product_id,
                'side': 'SELL',
                'order_type': 'market',
                'status': 'filled',
                'base_size': position_size,
                'filled_price': actual_fill_price,
                'metadata': {
                    'exit_reason': exit_reason,
                    'fees_paid': float(actual_commission),
                    'cancelled_orders': cancelled_orders,
                    'paper_trade': False
                }
            })

            # Close position in database
            self.db.close_position(product_id, float(actual_fill_price), float(pnl))

            # Record trade history
            entry_time = position.get('opened_at')
            exit_time = datetime.utcnow().isoformat()

            holding_time = None
            if entry_time:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                    holding_time = int((exit_dt - entry_dt).total_seconds())
                except:
                    pass

            self.db.insert_trade_history({
                'product_id': product_id,
                'side': 'BUY',  # Original entry side
                'entry_price': entry_price,
                'exit_price': actual_fill_price,
                'size': position_size,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'entry_time': entry_time or datetime.utcnow().isoformat(),
                'exit_time': exit_time,
                'holding_time_seconds': holding_time,
                'strategy': self.strategy_name,
                'exit_reason': exit_reason
            })

            logger.info(f"[LIVE] SELL order executed: {order_id}")
            logger.info(f"[LIVE] PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
            logger.info(f"[LIVE] Position closed for {product_id}")

    def _get_total_equity(self, balances: Dict[str, Decimal]) -> Decimal:
        """
        Calculate total equity in USD equivalent.

        Args:
            balances: Dictionary of asset balances

        Returns:
            Total equity in USD
        """
        total = Decimal('0')

        for asset, balance in balances.items():
            if asset == 'USD' or asset == 'USDC':
                total += balance
            else:
                # Try to get USD price
                price = self.api.get_latest_price(f"{asset}-USD")
                if price:
                    total += balance * price
                else:
                    # Try USDC as fallback
                    price = self.api.get_latest_price(f"{asset}-USDC")
                    if price:
                        total += balance * price

        return total
