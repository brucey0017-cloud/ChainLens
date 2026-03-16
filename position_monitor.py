#!/usr/bin/env python3
"""
Position Monitor - Monitor open positions and execute stop-loss/take-profit
Based on Jim Simons' strict risk management principles
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class PositionMonitor:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = psycopg2.connect(db_url)
    
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
        
        cur.close()
        return positions
    
    def get_current_price(self, token_address: str, chain: str) -> float:
        """Get current token price (placeholder)."""
        # TODO: Implement real price fetching from onchainos
        # For now, simulate price movement
        import random
        return random.uniform(0.8, 1.2)
    
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
    
    monitor = PositionMonitor(DB_URL)
    try:
        monitor.monitor_positions()
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
