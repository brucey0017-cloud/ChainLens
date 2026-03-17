#!/usr/bin/env python3
"""
Position Monitor - Monitor open positions and execute stop-loss/take-profit
Based on Jim Simons' strict risk management principles
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class Config:
    """Position monitoring configuration."""
    
    MAX_HOLDING_HOURS = 72  # Maximum time to hold a position
    PRICE_FETCH_TIMEOUT = 10  # Seconds
    MAX_PRICE_RETRIES = 3


class PositionMonitor:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = None
    
    def _ensure_connection(self):
        """Ensure database connection is established."""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(self.db_url)
    
    def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, strategy, token_symbol, token_address, chain,
                       entry_price, quantity, stop_loss, take_profit,
                       opened_at, is_paper
                FROM trades
                WHERE status = 'open'
                ORDER BY opened_at DESC
            """)
            
            positions = []
            for row in cur.fetchall():
                positions.append({
                    "id": row[0],
                    "strategy": row[1],
                    "token_symbol": row[2],
                    "token_address": row[3],
                    "chain": row[4],
                    "entry_price": float(row[5]),
                    "quantity": float(row[6]),
                    "stop_loss": float(row[7]),
                    "take_profit": float(row[8]),
                    "opened_at": row[9],
                    "is_paper": row[10]
                })
            
            return positions
    
    def get_current_price(self, token_address: str, chain: str) -> float:
        """
        Get current token price from onchainos.
        
        Raises:
            RuntimeError: If price cannot be fetched
        """
        # Import price_fetcher
        sys.path.insert(0, os.path.dirname(__file__))
        
        try:
            from price_fetcher import get_token_price
            
            for attempt in range(Config.MAX_PRICE_RETRIES):
                price = get_token_price(token_address, chain)
                if price and price > 0:
                    return price
                
                logger.warning(f"Price fetch attempt {attempt + 1} failed, retrying...")
            
            # All retries failed
            raise RuntimeError(
                f"Cannot fetch price for {token_address} on {chain} after {Config.MAX_PRICE_RETRIES} attempts. "
                "Cannot safely monitor position - manual intervention required."
            )
            
        except ImportError:
            raise RuntimeError(
                "price_fetcher module not available. "
                "Position monitoring requires real-time price data."
            )
    
    def check_stop_loss(self, position: Dict, current_price: float) -> bool:
        """Check if stop-loss is triggered."""
        return current_price <= position["stop_loss"]
    
    def check_take_profit(self, position: Dict, current_price: float) -> bool:
        """Check if take-profit is triggered."""
        return current_price >= position["take_profit"]
    
    def check_time_stop(self, position: Dict, max_hours: int = None) -> bool:
        """Check if position should be closed due to time limit."""
        if max_hours is None:
            max_hours = Config.MAX_HOLDING_HOURS
        
        # Ensure both datetimes are timezone-aware (UTC)
        now = datetime.now(timezone.utc)
        opened_at = position["opened_at"]
        
        # If opened_at is timezone-naive, assume UTC
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        
        age = now - opened_at
        return age > timedelta(hours=max_hours)
    
    def close_position(self, position: Dict, exit_price: float, reason: str):
        """Close a position and record P&L."""
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        
        pnl_usd = (exit_price - entry_price) * quantity
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            # Update trade record
            cur.execute("""
                UPDATE trades
                SET exit_price = %s,
                    pnl_usd = %s,
                    pnl_pct = %s,
                    status = %s,
                    closed_at = NOW(),
                    notes = %s
                WHERE id = %s
            """, (exit_price, pnl_usd, pnl_pct, "closed", reason, position["id"]))
            
            # Log risk event
            cur.execute("""
                INSERT INTO risk_events (event_type, trade_id, description, action_taken)
                VALUES (%s, %s, %s, %s)
            """, (reason, position["id"], f"Position closed: {reason}", f"Exit at {exit_price}"))
            
            self.conn.commit()
        
        logger.info(f"Closed {position['token_symbol']}: {pnl_pct:+.2f}% ({reason})")
    
    def monitor_positions(self):
        """Main monitoring loop."""
        positions = self.get_open_positions()
        
        if not positions:
            logger.info("No open positions")
            return
        
        logger.info(f"Monitoring {len(positions)} open positions...")
        
        for pos in positions:
            try:
                current_price = self.get_current_price(pos["token_address"], pos["chain"])
            except RuntimeError as e:
                logger.error(f"Cannot monitor {pos['token_symbol']}: {e}")
                # Do NOT close position blindly - this requires manual intervention
                continue
            
            # Check stop-loss
            if self.check_stop_loss(pos, current_price):
                self.close_position(pos, current_price, "stop_loss")
                continue
            
            # Check take-profit
            if self.check_take_profit(pos, current_price):
                self.close_position(pos, current_price, "take_profit")
                continue
            
            # Check time stop
            if self.check_time_stop(pos):
                self.close_position(pos, current_price, "time_stop")
                continue
            
            # Position still open - log current status
            pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            status = "paper" if pos["is_paper"] else "live"
            logger.info(f"  {pos['token_symbol']} [{status}]: {pnl_pct:+.2f}% (open)")
    
    def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()


def main():
    logger.info(f"=== Position Monitor - {datetime.now().isoformat()} ===")
    
    monitor = PositionMonitor(DB_URL)
    try:
        monitor.monitor_positions()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
