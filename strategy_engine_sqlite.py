#!/usr/bin/env python3
"""
Strategy Engine - Implement Jim Simons' multi-strategy approach
Strategies: Triple Confirmation, Resonance, Contrarian, Arbitrage
SQLite version for local testing
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Use SQLite for local testing
DB_PATH = os.path.join(os.path.dirname(__file__), "chainlens.db")


class StrategyEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
    
    def get_recent_signals(self, hours: int = 1) -> List[Dict]:
        """Get unprocessed signals from last N hours."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, source, token_symbol, token_address, chain, signal_score, raw_data, timestamp
            FROM signals
            WHERE processed = 0
              AND timestamp > DATETIME('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
        """, (hours,))
        
        signals = []
        for row in cur.fetchall():
            signals.append({
                "id": row["id"],
                "source": row["source"],
                "token_symbol": row["token_symbol"],
                "token_address": row["token_address"],
                "chain": row["chain"],
                "signal_score": float(row["signal_score"]) if row["signal_score"] else 0.0,
                "raw_data": json.loads(row["raw_data"]),
                "timestamp": datetime.fromisoformat(row["timestamp"])
            })
        
        cur.close()
        return signals
    
    def mark_signals_processed(self, signal_ids: List[int]):
        """Mark signals as processed."""
        if not signal_ids:
            return
        
        cur = self.conn.cursor()
        cur.execute(f"""
            UPDATE signals
            SET processed = 1
            WHERE id IN ({','.join(['?' for _ in signal_ids])})
        """, signal_ids)
        self.conn.commit()
        cur.close()
    
    def get_token_risk_score(self, token_address: str, chain: str) -> Optional[float]:
        """Get token risk score from auditor (placeholder)."""
        # TODO: Call token_auditor.py
        # For now, return a mock score
        return 65.0
    
    def strategy_triple_confirmation(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 1: Triple Confirmation
        Requires: Smart Money + Twitter + Risk Score > 60
        """
        trades = []
        
        # Group signals by token
        token_signals = {}
        for sig in signals:
            key = (sig["token_address"], sig["chain"])
            if key not in token_signals:
                token_signals[key] = []
            token_signals[key].append(sig)
        
        # Check for triple confirmation
        for (token_addr, chain), sigs in token_signals.items():
            sources = set(s["source"] for s in sigs)
            
            if "smart_money" not in sources:
                continue
            
            max_score = max(s["signal_score"] for s in sigs)
            if max_score < 0.6:
                continue
            
            risk_score = self.get_token_risk_score(token_addr, chain)
            if risk_score is None or risk_score < 60:
                continue
            
            token_symbol = sigs[0]["token_symbol"]
            trades.append({
                "strategy": "triple_confirmation",
                "token_symbol": token_symbol,
                "token_address": token_addr,
                "chain": chain,
                "direction": "buy",
                "signal_score": max_score,
                "risk_score": risk_score,
                "position_size_pct": self._calculate_position_size(max_score, 2, 5),
                "stop_loss_pct": -15.0,
                "take_profit_pct": 30.0,
                "hold_hours": 24
            })
        
        return trades
    
    def strategy_contrarian(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 3: Contrarian
        Buy when price drops >20% but fundamentals are strong
        """
        trades = []
        
        # TODO: Implement price drop detection
        
        return trades
    
    def _calculate_position_size(self, signal_score: float, min_pct: float, max_pct: float) -> float:
        """Calculate position size based on signal strength."""
        normalized = (signal_score - 0.5) / 0.5
        normalized = max(0, min(1, normalized))
        return min_pct + (max_pct - min_pct) * normalized
    
    def execute_paper_trades(self, trades: List[Dict]):
        """Execute paper trades (record in database)."""
        if not trades:
            return
        
        cur = self.conn.cursor()
        
        # Initial capital for paper trading
        initial_capital = 10000.0
        
        for trade in trades:
            # Placeholder for current price
            entry_price = self._get_current_mock_price(trade["token_symbol"], trade["token_address"], trade["chain"])
            if entry_price is None:
                print(f"Could not get price for {trade['token_symbol']}. Skipping trade.", file=sys.stderr)
                continue

            position_size_usd = (trade["position_size_pct"] / 100) * initial_capital
            quantity = position_size_usd / entry_price
            
            cur.execute("""
                INSERT INTO trades (
                    strategy, token_symbol, token_address, chain, direction,
                    entry_price, quantity, position_size_pct, position_size_usd,
                    stop_loss, take_profit, is_paper, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade["strategy"],
                trade["token_symbol"],
                trade["token_address"],
                trade["chain"],
                trade["direction"],
                entry_price,
                quantity,
                trade["position_size_pct"],
                position_size_usd,
                entry_price * (1 + trade["stop_loss_pct"] / 100),
                entry_price * (1 + trade["take_profit_pct"] / 100),
                1,  # Paper trade
                "open"
            ))
        
        self.conn.commit()
        cur.close()
        
        print(f"Executed {len(trades)} paper trades")
    
    def _get_current_mock_price(self, symbol: str, address: str, chain: str) -> Optional[float]:
        """
        Mock price fetching. In real scenario, would call onchainos token price.
        For now, generate random prices to simulate activity.
        """
        import random
        # This should be replaced by actual onchainos call
        # Example: onchainos token price --chain <chain> --token <address>
        
        # Let's assume some prices for common tokens for testing
        if symbol == "OKB": return random.uniform(90, 100)
        if symbol == "USDT": return random.uniform(0.99, 1.01)
        if symbol == "WETH": return random.uniform(2000, 2200)
        
        # Default random price if not a common token
        return random.uniform(0.00005, 0.00015)
        
    def run(self):
        """Main execution loop."""
        print(f"=== Strategy Engine - {datetime.now().isoformat()} ===")
        
        signals = self.get_recent_signals(hours=1)
        print(f"Processing {len(signals)} signals...")
        
        if not signals:
            print("No signals to process")
            return
        
        all_trades = []
        
        trades_1 = self.strategy_triple_confirmation(signals)
        all_trades.extend(trades_1)
        print(f"  Triple Confirmation: {len(trades_1)} trades")
        
        trades_3 = self.strategy_contrarian(signals)
        all_trades.extend(trades_3)
        print(f"  Contrarian: {len(trades_3)} trades")
        
        if all_trades:
            self.execute_paper_trades(all_trades)
        
        signal_ids = [s["id"] for s in signals]
        self.mark_signals_processed(signal_ids)
        
        print(f"\nTotal trades generated: {len(all_trades)}")
    
    def close(self):
        self.conn.close()


def main():
    engine = StrategyEngine(DB_PATH)
    try:
        engine.run()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
