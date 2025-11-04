"""
Database manager for persisting trading bot state, orders, and performance metrics.
Uses SQLite for simplicity and portability.
"""

import sqlite3
import json
import threading
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations for the trading bot."""
    
    def __init__(self, db_path: str = "data/trading_bot.db"):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self.db_lock = threading.Lock()  # Thread safety for concurrent DB access
        self._initialize_database()
    
    def _initialize_database(self):
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Orders table - using TEXT for Decimal precision
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_order_id TEXT UNIQUE NOT NULL,
                product_id TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                status TEXT NOT NULL,
                base_size TEXT,
                quote_size TEXT,
                entry_price TEXT,
                stop_loss TEXT,
                take_profit TEXT,
                filled_price TEXT,
                filled_size TEXT,
                fees TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                filled_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                metadata TEXT
            )
        """)
        
        # Positions table - using TEXT for Decimal precision
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                base_size TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                current_price TEXT,
                stop_loss TEXT,
                take_profit TEXT,
                unrealized_pnl TEXT,
                realized_pnl TEXT DEFAULT '0',
                entry_order_id TEXT,
                opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                status TEXT DEFAULT 'open',
                metadata TEXT
            )
        """)
        
        # Performance metrics table - using TEXT for Decimal precision
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_equity TEXT,
                available_balance TEXT,
                total_positions_value TEXT,
                daily_pnl TEXT,
                total_pnl TEXT,
                win_rate TEXT,
                sharpe_ratio TEXT,
                sortino_ratio TEXT,
                max_drawdown TEXT,
                num_trades INTEGER,
                num_wins INTEGER,
                num_losses INTEGER,
                metadata TEXT
            )
        """)
        
        # Trade history table - using TEXT for Decimal precision
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                exit_price TEXT NOT NULL,
                size TEXT NOT NULL,
                pnl TEXT NOT NULL,
                pnl_percent TEXT NOT NULL,
                fees TEXT DEFAULT '0',
                holding_time_seconds INTEGER,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP NOT NULL,
                strategy TEXT,
                exit_reason TEXT,
                metadata TEXT
            )
        """)
        
        # Bot state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Equity curve table - using TEXT for Decimal precision
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equity_curve (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                equity TEXT NOT NULL,
                cash TEXT NOT NULL,
                positions_value TEXT NOT NULL
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_history_product ON trade_history(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_curve_timestamp ON equity_curve(timestamp)")
        
        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    def _decimal_to_str(self, value: Any) -> Optional[str]:
        """
        Convert Decimal values to string for storage.
        
        Args:
            value: Value to convert (Decimal, float, int, or None)
            
        Returns:
            String representation or None
        """
        if value is None:
            return None
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (float, int)):
            return str(Decimal(str(value)))
        return str(value)
    
    def _str_to_decimal(self, value: Any) -> Optional[Decimal]:
        """
        Convert string values back to Decimal.
        
        Args:
            value: Value to convert (string or None)
            
        Returns:
            Decimal or None
        """
        if value is None or value == '' or value == 'None':
            return None
        try:
            return Decimal(str(value))
        except Exception as e:
            logger.warning(f"Could not convert '{value}' to Decimal: {e}")
            return None
    
    def insert_order(self, order_data: Dict[str, Any]) -> int:
        """Insert a new order record."""
        with self.db_lock:
            cursor = self.conn.cursor()
            
            # Convert Decimal to string and handle metadata
            processed_data = self._process_order_data(order_data)
            
            try:
                cursor.execute("""
                    INSERT INTO orders (
                        client_order_id, product_id, side, order_type, status,
                        base_size, quote_size, entry_price, stop_loss, take_profit, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    processed_data['client_order_id'],
                    processed_data['product_id'],
                    processed_data['side'],
                    processed_data['order_type'],
                    processed_data['status'],
                    self._decimal_to_str(processed_data.get('base_size')),
                    self._decimal_to_str(processed_data.get('quote_size')),
                    self._decimal_to_str(processed_data.get('entry_price')),
                    self._decimal_to_str(processed_data.get('stop_loss')),
                    self._decimal_to_str(processed_data.get('take_profit')),
                    json.dumps(processed_data.get('metadata', {}))
                ))
                
                self.conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed: orders.client_order_id" in str(e):
                    # Log the duplicate and check if it's the same order
                    logger = logging.getLogger(__name__)
                    logger.error(f"Duplicate client_order_id: {processed_data['client_order_id']}")
                    
                    # Check if this exact order already exists
                    cursor.execute("SELECT id FROM orders WHERE client_order_id = ?", 
                                 (processed_data['client_order_id'],))
                    existing = cursor.fetchone()
                    if existing:
                        logger.warning(f"Order already exists in database with id {existing[0]}, skipping insert")
                        return existing[0]
                # Re-raise if it's a different integrity error or we couldn't handle it
                raise
    
    def update_order_status(self, client_order_id: str, status: str, 
                          filled_price: float = None, filled_size: float = None,
                          fees: float = None):
        """Update order status and fill information."""
        with self.db_lock:
            cursor = self.conn.cursor()
            
            update_fields = ["status = ?"]
            params = [status]
            
            if filled_price is not None:
                update_fields.append("filled_price = ?")
                params.append(self._decimal_to_str(filled_price))
            
            if filled_size is not None:
                update_fields.append("filled_size = ?")
                params.append(self._decimal_to_str(filled_size))
            
            if fees is not None:
                update_fields.append("fees = ?")
                params.append(self._decimal_to_str(fees))
            
            if status == 'filled':
                update_fields.append("filled_at = CURRENT_TIMESTAMP")
            elif status == 'cancelled':
                update_fields.append("cancelled_at = CURRENT_TIMESTAMP")
            
            params.append(client_order_id)
            
            query = f"UPDATE orders SET {', '.join(update_fields)} WHERE client_order_id = ?"
            cursor.execute(query, params)
            self.conn.commit()
    
    def insert_position(self, position_data: Dict[str, Any]) -> int:
        """Insert a new position record."""
        with self.db_lock:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO positions (
                    product_id, base_size, entry_price, current_price,
                    stop_loss, take_profit, entry_order_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_data['product_id'],
                self._decimal_to_str(position_data['base_size']),
                self._decimal_to_str(position_data['entry_price']),
                self._decimal_to_str(position_data.get('current_price', position_data['entry_price'])),
                self._decimal_to_str(position_data.get('stop_loss', 0)),
                self._decimal_to_str(position_data.get('take_profit', 0)),
                position_data.get('entry_order_id'),
                json.dumps(position_data.get('metadata', {}))
            ))
            
            self.conn.commit()
            return cursor.lastrowid
    
    def update_position(self, product_id: str, **kwargs):
        """Update position fields."""
        with self.db_lock:
            cursor = self.conn.cursor()
            
            update_fields = []
            params = []
            
            for key, value in kwargs.items():
                if value is not None:
                    update_fields.append(f"{key} = ?")
                    if isinstance(value, (Decimal, float, int)):
                        params.append(self._decimal_to_str(value))
                    else:
                        params.append(value)
            
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(product_id)
            
            query = f"UPDATE positions SET {', '.join(update_fields)} WHERE product_id = ? AND status = 'open'"
            cursor.execute(query, params)
            self.conn.commit()
    
    def close_position(self, product_id: str, exit_price: float, realized_pnl: float):
        """Close a position."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE positions 
            SET status = 'closed', 
                current_price = ?,
                realized_pnl = ?,
                closed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ? AND status = 'open'
        """, (float(exit_price), float(realized_pnl), product_id))
        
        self.conn.commit()
    
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE status = 'open'")
        
        positions = []
        for row in cursor.fetchall():
            positions.append(dict(row))
        
        return positions
    
    def get_position(self, product_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific open position."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE product_id = ? AND status = 'open'", (product_id,))
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def insert_trade_history(self, trade_data: Dict[str, Any]):
        """Insert completed trade into history."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO trade_history (
                product_id, side, entry_price, exit_price, size,
                pnl, pnl_percent, fees, holding_time_seconds,
                entry_time, exit_time, strategy, exit_reason, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['product_id'],
            trade_data['side'],
            float(trade_data['entry_price']),
            float(trade_data['exit_price']),
            float(trade_data['size']),
            float(trade_data['pnl']),
            float(trade_data['pnl_percent']),
            float(trade_data.get('fees', 0)),
            trade_data.get('holding_time_seconds'),
            trade_data['entry_time'],
            trade_data['exit_time'],
            trade_data.get('strategy'),
            trade_data.get('exit_reason'),
            json.dumps(trade_data.get('metadata', {}))
        ))
        
        self.conn.commit()
    
    def insert_performance_metrics(self, metrics: Dict[str, Any]):
        """Insert performance metrics snapshot."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO performance_metrics (
                total_equity, available_balance, total_positions_value,
                daily_pnl, total_pnl, win_rate, sharpe_ratio, sortino_ratio,
                max_drawdown, num_trades, num_wins, num_losses, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            float(metrics.get('total_equity', 0)),
            float(metrics.get('available_balance', 0)),
            float(metrics.get('total_positions_value', 0)),
            float(metrics.get('daily_pnl', 0)),
            float(metrics.get('total_pnl', 0)),
            float(metrics.get('win_rate', 0)),
            float(metrics.get('sharpe_ratio', 0)),
            float(metrics.get('sortino_ratio', 0)),
            float(metrics.get('max_drawdown', 0)),
            metrics.get('num_trades', 0),
            metrics.get('num_wins', 0),
            metrics.get('num_losses', 0),
            json.dumps(metrics.get('metadata', {}))
        ))
        
        self.conn.commit()
    
    def insert_equity_snapshot(self, equity: float, cash: float, positions_value: float):
        """Insert equity curve data point."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO equity_curve (equity, cash, positions_value)
            VALUES (?, ?, ?)
        """, (float(equity), float(cash), float(positions_value)))
        
        self.conn.commit()
    
    def get_trade_statistics(self, days: int = None) -> Dict[str, Any]:
        """Get trading statistics."""
        cursor = self.conn.cursor()
        
        where_clause = ""
        params = []
        if days:
            where_clause = "WHERE exit_time >= datetime('now', '-' || ? || ' days')"
            params.append(days)
        
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                AVG(pnl) as avg_pnl,
                SUM(pnl) as total_pnl,
                AVG(CASE WHEN pnl > 0 THEN pnl ELSE NULL END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl ELSE NULL END) as avg_loss,
                MAX(pnl) as max_win,
                MIN(pnl) as max_loss,
                AVG(holding_time_seconds) as avg_holding_time
            FROM trade_history
            {where_clause}
        """, params)
        
        row = cursor.fetchone()
        stats = dict(row) if row else {}
        
        if stats.get('total_trades', 0) > 0:
            stats['win_rate'] = stats['wins'] / stats['total_trades']
            if stats['avg_loss'] and stats['avg_loss'] != 0:
                stats['profit_factor'] = abs(stats['avg_win'] / stats['avg_loss']) if stats['avg_win'] else 0
            else:
                stats['profit_factor'] = None
        
        return stats
    
    def get_equity_curve(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get equity curve data."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT timestamp, equity, cash, positions_value
            FROM equity_curve
            WHERE timestamp >= datetime('now', '-' || ? || ' days')
            ORDER BY timestamp ASC
        """, (days,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def set_bot_state(self, key: str, value: Any):
        """Set bot state value."""
        cursor = self.conn.cursor()
        
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        cursor.execute("""
            INSERT OR REPLACE INTO bot_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value_str))
        
        self.conn.commit()
    
    def get_bot_state(self, key: str, default: Any = None) -> Any:
        """Get bot state value."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM bot_state WHERE key = ?", (key,))
        
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row['value'])
            except json.JSONDecodeError:
                return row['value']
        
        return default
    
    def _process_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process order data, converting Decimals to floats."""
        processed = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                processed[key] = float(value)
            else:
                processed[key] = value
        return processed
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
