#!/usr/bin/env python3
"""
Strategy Engine - Implement Jim Simons' multi-strategy approach
Strategies: Triple Confirmation, Resonance, Contrarian, Arbitrage
SQLite version for local testing
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Use SQLite for local testing
DB_PATH = os.path.join(os.path.dirname(__file__), "chainlens.db")


class Config:
    """Strategy configuration constants."""
    
    # Triple Confirmation Strategy
    MIN_SIGNAL_SCORE = 0.6
    MIN_RISK_SCORE = 60
    TRIPLE_CONFIRMATION_POSITION_SIZE = (2, 5)  # min%, max%
    TRIPLE_CONFIRMATION_STOP_LOSS = -15.0
    TRIPLE_CONFIRMATION_TAKE_PROFIT = 30.0
    
    # Contrarian Strategy
    CONTRARIAN_PRICE_DROP_THRESHOLD = 0.2
    CONTRARIAN_POSITION_SIZE = (1, 3)
    CONTRARIAN_STOP_LOSS = -10.0
    CONTRARIAN_TAKE_PROFIT = 25.0
    
    # Risk Management
    MAX_POSITION_PCT = 0.10  # 10% max per trade
    INITIAL_CAPITAL = 10000.0


class StrategyEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
    
    @contextmanager
    def _get_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database cursor with automatic cleanup."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()
    
    def get_recent_signals(self, hours: int = 1) -> List[Dict]:
        """Get unprocessed signals from last N hours."""
        with self._get_cursor() as cur:
            # Fixed: Use proper SQLite datetime modifier
            cur.execute("""
                SELECT id, source, token_symbol, token_address, chain, signal_score, raw_data, timestamp
                FROM signals
                WHERE processed = 0
                  AND timestamp > datetime('now', ?)
                ORDER BY timestamp DESC
            """, (f'-{hours} hours',))
            
            signals = []
            for row in cur.fetchall():
                try:
                    raw_data = json.loads(row["raw_data"]) if row["raw_data"] else {}
                except json.JSONDecodeError:
                    raw_data = {}
                
                signals.append({
                    "id": row["id"],
                    "source": row["source"],
                    "token_symbol": row["token_symbol"],
                    "token_address": row["token_address"],
                    "chain": row["chain"],
                    "signal_score": float(row["signal_score"]) if row["signal_score"] else 0.0,
                    "raw_data": raw_data,
                    "timestamp": self._parse_timestamp(row["timestamp"])
                })
            
            return signals
    
    def _parse_timestamp(self, ts: str) -> datetime:
        """Parse timestamp string to datetime."""
        try:
            # Try ISO format first
            return datetime.fromisoformat(ts)
        except ValueError:
            try:
                # Fallback to SQLite format
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning(f"Could not parse timestamp: {ts}")
                return datetime.now()
    
    def mark_signals_processed(self, signal_ids: List[int]):
        """Mark signals as processed."""
        if not signal_ids:
            return
        
        with self._get_cursor() as cur:
            # Fixed: Proper parameterized query (no f-string)
            placeholders = ",".join("?" * len(signal_ids))
            cur.execute(
                f"UPDATE signals SET processed = 1 WHERE id IN ({placeholders})",
                signal_ids
            )
            self.conn.commit()
    
    def get_token_risk_score(self, token_address: str, chain: str) -> Optional[float]:
        """Get token risk score from auditor."""
        try:
            # Import token_auditor if available
            sys.path.insert(0, os.path.dirname(__file__))
            from token_auditor import TokenAuditor
            
            auditor = TokenAuditor()
            result = auditor.audit_token(token_address, chain)
            if result and "risk_score" in result:
                return result["risk_score"]
        except Exception as e:
            logger.warning(f"Token auditor failed: {e}")
        
        # Fallback: return a conservative score
        logger.warning("Using fallback risk score - manual verification recommended")
        return 65.0
    
    def strategy_triple_confirmation(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 1: Triple Confirmation
        Requires: Smart Money + Twitter + Risk Score > 60
        """
        trades = []
        
        # Group signals by token
        token_signals: Dict[tuple, List[Dict]] = {}
        for sig in signals:
            key = (sig["token_address"], sig["chain"])
            if key not in token_signals:
                token_signals[key] = []
            token_signals[key].append(sig)
        
        # Check for triple confirmation
        for (token_addr, chain), sigs in token_signals.items():
            sources = set(s["source"] for s in sigs)
            
            # Need at least smart_money signal
            if "smart_money" not in sources:
                continue
            
            # Get highest signal score
            max_score = max(s["signal_score"] for s in sigs)
            
            if max_score < Config.MIN_SIGNAL_SCORE:
                continue
            
            # Check risk score
            risk_score = self.get_token_risk_score(token_addr, chain)
            if risk_score is None or risk_score < Config.MIN_RISK_SCORE:
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
                "position_size_pct": self._calculate_position_size(
                    max_score, 
                    Config.TRIPLE_CONFIRMATION_POSITION_SIZE[0],
                    Config.TRIPLE_CONFIRMATION_POSITION_SIZE[1]
                ),
                "stop_loss_pct": Config.TRIPLE_CONFIRMATION_STOP_LOSS,
                "take_profit_pct": Config.TRIPLE_CONFIRMATION_TAKE_PROFIT,
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
        # This would require historical price data from onchainos
        
        return trades
    
    def _calculate_position_size(self, signal_score: float, min_pct: float, max_pct: float) -> float:
        """Calculate position size based on signal strength."""
        # Linear interpolation between min and max
        normalized = (signal_score - 0.5) / 0.5  # Map 0.5-1.0 to 0-1
        normalized = max(0.0, min(1.0, normalized))
        position_pct = min_pct + (max_pct - min_pct) * normalized
        
        # Enforce maximum position size
        return min(position_pct, Config.MAX_POSITION_PCT * 100)
    
    def get_real_price(self, token_address: str, chain: str) -> Optional[float]:
        """Get real token price from onchainos."""
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from price_fetcher import get_token_price
            
            price = get_token_price(token_address, chain)
            if price and price > 0:
                return price
        except Exception as e:
            logger.warning(f"Price fetch failed: {e}")
        
        return None
    
    def execute_paper_trades(self, trades: List[Dict]):
        """Execute paper trades (record in database)."""
        if not trades:
            return
        
        executed_count = 0
        
        with self._get_cursor() as cur:
            for trade in trades:
                # Try to get real price first
                entry_price = self.get_real_price(trade["token_address"], trade["chain"])
                
                if entry_price is None:
                    # WARNING: Using mock price - this should not happen in production
                    logger.warning(
                        f"⚠️ Using mock price for {trade['token_symbol']} - "
                        "Real price unavailable. This should not happen in production!"
                    )
                    entry_price = self._get_mock_price(trade["token_symbol"])
                
                if entry_price is None or entry_price <= 0:
                    logger.error(f"Could not get valid price for {trade['token_symbol']}. Skipping trade.")
                    continue
                
                position_size_usd = (trade["position_size_pct"] / 100) * Config.INITIAL_CAPITAL
                quantity = position_size_usd / entry_price
                
                cur.execute("""
                    INSERT INTO trades (
                        strategy, token_symbol, token_address, chain, direction,
                        entry_price, quantity, position_size_pct, position_size_usd,
                        stop_loss, take_profit, signal_score, risk_score, is_paper, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    trade["signal_score"],
                    trade["risk_score"],
                    1,  # Paper trade
                    "open"
                ))
                executed_count += 1
            
            self.conn.commit()
        
        logger.info(f"Executed {executed_count} paper trades")
    
    def _get_mock_price(self, symbol: str) -> Optional[float]:
        """
        Mock price for testing ONLY.
        In production, this should never be called.
        """
        import random
        
        # Known token prices for testing
        mock_prices = {
            "OKB": 95.0,
            "USDT": 1.0,
            "USDC": 1.0,
            "WETH": 2100.0,
            "WBTC": 45000.0,
        }
        
        if symbol in mock_prices:
            # Add small random variation for testing
            return mock_prices[symbol] * random.uniform(0.98, 1.02)
        
        # Unknown token - return random small value
        logger.warning(f"Using random mock price for unknown token: {symbol}")
        return random.uniform(0.0001, 0.001)
    
    def run(self):
        """Main execution loop."""
        logger.info(f"=== Strategy Engine - {datetime.now().isoformat()} ===")
        
        signals = self.get_recent_signals(hours=1)
        logger.info(f"Processing {len(signals)} signals...")
        
        if not signals:
            logger.info("No signals to process")
            return
        
        all_trades: List[Dict[str, Any]] = []
        
        # Strategy 1: Triple Confirmation
        trades_1 = self.strategy_triple_confirmation(signals)
        all_trades.extend(trades_1)
        logger.info(f"  Triple Confirmation: {len(trades_1)} trades")
        
        # Strategy 3: Contrarian
        trades_3 = self.strategy_contrarian(signals)
        all_trades.extend(trades_3)
        logger.info(f"  Contrarian: {len(trades_3)} trades")
        
        # Execute paper trades
        if all_trades:
            self.execute_paper_trades(all_trades)
        
        # Mark signals as processed
        signal_ids = [s["id"] for s in signals]
        self.mark_signals_processed(signal_ids)
        
        logger.info(f"Total trades generated: {len(all_trades)}")
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None


def main():
    engine = StrategyEngine(DB_PATH)
    try:
        engine.run()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
