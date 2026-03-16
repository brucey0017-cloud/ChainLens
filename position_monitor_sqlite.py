#!/usr/bin/env python3
"""
Position Monitor - Monitor open positions and execute stop-loss/take-profit
SQLite version for local testing
"""

import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Dict, List

# Use SQLite for local testing
DB_PATH = os.path.join(os.path.dirname(__file__), "chainlens.db")


class PositionMonitor:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
    
    def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        cur = self.conn.cursor()
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
                "id": row["id"],
                "strategy": row["strategy"],
                "token_symbol": row["token_symbol"],
                "token_address": row["token_address"],
                "chain": row["chain"],
                "entry_price": float(row["entry_price"]),
                "quantity": float(row["quantity"]),
                "stop_loss": float(row["stop_loss"]),
                "take_profit": float(row["take_profit"]),
                "opened_at": datetime.fromisoformat(row["opened_at"]),
                "is_paper": bool(row["is_paper"])
            })
        
        cur.close()
        return positions
    
    def get_current_price(self, token_address: str, chain: str) -> float:
        """Get current token price (mock for testing)."""
        # Simulate price movement: ±20% from entry
        return random.uniform(0.00008, 0.00012)
    
    def check_stop_loss(self, position: Dict, current_price: float) -> bool:
        """Check if stop-loss is triggered."""
        return current_price <= position["stop_loss"]
    
    def check_take_profit(self, position: Dict, current_price: float) -> bool:
        """Check if take-profit is triggered."""
        return current_price >= position["take_profit"]
    
    def check_time_stop(self, position: Dict, max_hours: int = 72) -> bool:
        """Check if position should be closed due to time limit."""
        age = datetime.now() - position["opened_at"]
        return age > timedelta(hours=max_hours)
    
    def close_position(self, position: Dict, exit_price: float, reason: str):
        """Close a position and record P&L."""
        entry_price = position["entry_price"]
        quantity = position["quantity"]
        
        pnl_usd = (exit_price - entry_price) * quantity
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        
        cur = self.conn.cursor()
        
        # Update trade record
        cur.execute("""
            UPDATE trades
            SET exit_price = ?,
                pnl_usd = ?,
                pnl_pct = ?,
                status = ?,
                closed_at = CURRENT_TIMESTAMP,
                notes = ?
            WHERE id = ?
        """, (exit_price, pnl_usd, pnl_pct, "closed", reason, position["id"]))
        
        # Log risk event
        cur.execute("""
            INSERT INTO risk_events (event_type, trade_id, description, action_taken)
            VALUES (?, ?, ?, ?)
        """, (reason, position["id"], f"Position closed: {reason}", f"Exit at {exit_price}"))
        
        self.conn.commit()
        cur.close()
        
        print(f"  Closed {position['token_symbol']}: {pnl_pct:+.2f}% ({reason})")
    
    def monitor_positions(self):
        """Main monitoring loop."""
        positions = self.get_open_positions()
        
        if not positions:
            print("No open positions")
            return
        
        print(f"Monitoring {len(positions)} open positions...")
        
        for pos in positions:
            current_price = self.get_current_price(pos["token_address"], pos["chain"])
            
            # Check stop-loss
            if self.check_stop_loss(pos, current_price):
                self.close_position(pos, current_price, "stop_loss")
                continue
            
            # Check take-profit
            if self.check_take_profit(pos, current_price):
                self.close_position(pos, current_price, "take_profit")
                continue
            
            # Check time stop
            if self.check_time_stop(pos, max_hours=72):
                self.close_position(pos, current_price, "time_stop")
                continue
            
            # Position still open
            pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            print(f"  {pos['token_symbol']}: {pnl_pct:+.2f}% (open)")
    
    def close(self):
        self.conn.close()


def main():
    print(f"=== Position Monitor - {datetime.now().isoformat()} ===")
    
    monitor = PositionMonitor(DB_PATH)
    try:
        monitor.monitor_positions()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
