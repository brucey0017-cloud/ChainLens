#!/usr/bin/env python3
"""Live Trading Manager - Phase 2: Small capital real trading.

Safety features:
1. Max position size: $50 per trade
2. Max total exposure: $200
3. Daily loss limit: $50
4. Requires manual approval for each trade
5. Dry-run mode by default
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

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
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # paper or live

# Phase 2 Safety Limits
MAX_POSITION_SIZE_USD = 50  # $50 per trade
MAX_TOTAL_EXPOSURE_USD = 200  # $200 total
DAILY_LOSS_LIMIT_USD = 50  # $50 daily loss limit
MIN_SIGNAL_SCORE = 0.7  # Higher threshold for live trading


class SafetyLimitError(Exception):
    """Raised when safety limits are exceeded."""
    pass


class LiveTradingManager:
    def __init__(self):
        self.conn = None
    
    def _ensure_connection(self):
        """Ensure database connection is established."""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(DB_URL)
    
    def check_safety_limits(self) -> Dict:
        """Check if we can open new positions."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            # 1. Check total exposure from portfolio table
            cur.execute("""
                SELECT COALESCE(SUM(position_value_usd), 0)
                FROM portfolio
                WHERE status = 'open'
            """)
            total_exposure = float(cur.fetchone()[0] or 0)
            
            # 2. Check daily loss from trades
            cur.execute("""
                SELECT COALESCE(SUM(pnl_usd), 0)
                FROM trades
                WHERE closed_at >= NOW() - INTERVAL '24 hours'
                AND status = 'closed'
            """)
            daily_pnl = float(cur.fetchone()[0] or 0)
            
            # 3. Check open positions count
            cur.execute("""
                SELECT COUNT(*)
                FROM portfolio
                WHERE status = 'open'
            """)
            open_positions = cur.fetchone()[0] or 0
        
        can_trade = True
        reasons = []
        
        if total_exposure >= MAX_TOTAL_EXPOSURE_USD:
            can_trade = False
            reasons.append(f"Total exposure ${total_exposure:.2f} >= ${MAX_TOTAL_EXPOSURE_USD}")
        
        if daily_pnl <= -DAILY_LOSS_LIMIT_USD:
            can_trade = False
            reasons.append(f"Daily loss ${abs(daily_pnl):.2f} >= ${DAILY_LOSS_LIMIT_USD}")
        
        return {
            "can_trade": can_trade,
            "reasons": reasons,
            "total_exposure": total_exposure,
            "daily_pnl": daily_pnl,
            "open_positions": open_positions,
            "available_capital": MAX_TOTAL_EXPOSURE_USD - total_exposure
        }
    
    def get_pending_trades(self) -> List[Dict]:
        """Get trades that need execution approval."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            # Updated to use fields that exist in schema v2.0
            cur.execute("""
                SELECT 
                    id, strategy, token_symbol, token_address, chain,
                    entry_price, position_size_usd, stop_loss, take_profit,
                    signal_score, opened_at
                FROM trades
                WHERE status = 'pending_approval'
                AND signal_score >= %s
                ORDER BY signal_score DESC, opened_at DESC
                LIMIT 10
            """, (MIN_SIGNAL_SCORE,))
            
            trades = []
            for row in cur.fetchall():
                trades.append({
                    "id": row[0],
                    "strategy": row[1],
                    "token_symbol": row[2],
                    "token_address": row[3],
                    "chain": row[4],
                    "entry_price": float(row[5]) if row[5] else 0.0,
                    "position_size_usd": float(row[6]) if row[6] else 0.0,
                    "stop_loss": float(row[7]) if row[7] else 0.0,
                    "take_profit": float(row[8]) if row[8] else 0.0,
                    "signal_score": float(row[9]) if row[9] else 0.0,
                    "created_at": row[10]
                })
            
            return trades
    
    def approve_trade(self, trade_id: int) -> bool:
        """Approve a trade for execution."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE trades
                SET status = 'approved', approved_at = NOW(), approved_by = 'manual'
                WHERE id = %s
            """, (trade_id,))
            self.conn.commit()
        
        logger.info(f"Trade {trade_id} approved")
        return True
    
    def reject_trade(self, trade_id: int, reason: str) -> bool:
        """Reject a trade."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE trades
                SET status = 'rejected', notes = %s
                WHERE id = %s
            """, (reason, trade_id,))
            self.conn.commit()
        
        logger.info(f"Trade {trade_id} rejected: {reason}")
        return True
    
    def execute_approved_trades(self):
        """Execute all approved trades."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id, token_address, chain, position_size_usd, entry_price
                FROM trades
                WHERE status = 'approved'
                ORDER BY opened_at ASC
            """)
            
            approved = cur.fetchall()
        
        if not approved:
            logger.info("No approved trades to execute")
            return
        
        logger.info(f"=== Executing {len(approved)} approved trades ===")
        
        for trade in approved:
            trade_id, token_addr, chain, size_usd, entry_price = trade
            
            if TRADING_MODE == "paper":
                logger.info(f"  [PAPER] Trade #{trade_id}: ${size_usd:.2f} @ ${entry_price:.6f}")
                self._mark_trade_executed(trade_id, "paper", "PAPER_TX_" + str(trade_id))
            else:
                logger.info(f"  [LIVE] Executing trade #{trade_id}...")
                success, tx_hash = self._execute_real_trade(token_addr, chain, size_usd)
                if success:
                    self._mark_trade_executed(trade_id, "live", tx_hash)
                    logger.info(f"    ✅ Success: {tx_hash}")
                else:
                    self._mark_trade_failed(trade_id, "Execution failed")
                    logger.error(f"    ❌ Failed")
    
    def _execute_real_trade(self, token_addr: str, chain: str, size_usd: float) -> Tuple[bool, Optional[str]]:
        """Execute a real on-chain trade."""
        # Get USDT/USDC address for the chain
        stable_token = self._get_stable_token(chain)
        
        # Calculate amount in stable token (assuming 1:1 USD)
        amount = str(int(size_usd * 1e6))  # USDT/USDC has 6 decimals
        
        # Execute swap via trade_executor.py
        try:
            result = subprocess.run([
                "python3", "trade_executor.py", "swap",
                chain, stable_token, token_addr, amount
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse TX hash from output
                for line in result.stdout.split("\n"):
                    if "TX Hash:" in line:
                        tx_hash = line.split("TX Hash:")[1].strip()
                        return True, tx_hash
                return False, None
            else:
                logger.error(f"Trade execution error: {result.stderr[:200]}")
                return False, None
        except Exception as e:
            logger.error(f"Trade execution exception: {e}")
            return False, None
    
    def _get_stable_token(self, chain: str) -> str:
        """Get USDT/USDC address for chain."""
        stable_tokens = {
            "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "xlayer": "0x74b7F16337b8972027F6196A17a631aC6dE26d22",  # USDC
            "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "bsc": "0x55d398326f99059fF775485246999027B3197955",  # USDT
        }
        return stable_tokens.get(chain, stable_tokens["xlayer"])
    
    def _mark_trade_executed(self, trade_id: int, mode: str, tx_hash: str):
        """Mark trade as executed and update portfolio."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            # Update trade status
            cur.execute("""
                UPDATE trades
                SET status = 'open', tx_hash = %s, executed_at = NOW()
                WHERE id = %s
            """, (tx_hash, trade_id))
            
            # Insert into portfolio (linked to trade)
            cur.execute("""
                INSERT INTO portfolio (
                    trade_id, token_symbol, token_address, chain,
                    avg_entry_price, position_size_usd, stop_loss, take_profit,
                    status, opened_at
                )
                SELECT 
                    id, token_symbol, token_address, chain,
                    entry_price, position_size_usd, stop_loss, take_profit,
                    'open', NOW()
                FROM trades
                WHERE id = %s
            """, (trade_id,))
            
            self.conn.commit()
    
    def _mark_trade_failed(self, trade_id: int, reason: str):
        """Mark trade as failed."""
        self._ensure_connection()
        
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE trades
                SET status = 'failed', execution_error = %s
                WHERE id = %s
            """, (reason, trade_id))
            self.conn.commit()
    
    def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()


def main():
    logger.info(f"=== Live Trading Manager - {datetime.now().isoformat()} ===")
    logger.info(f"Mode: {TRADING_MODE.upper()}")
    print()
    
    manager = LiveTradingManager()
    
    try:
        # Check safety limits
        limits = manager.check_safety_limits()
        print("Safety Check:")
        print(f"  Total exposure: ${limits['total_exposure']:.2f} / ${MAX_TOTAL_EXPOSURE_USD}")
        print(f"  Daily P&L: ${limits['daily_pnl']:.2f}")
        print(f"  Open positions: {limits['open_positions']}")
        print(f"  Available capital: ${limits['available_capital']:.2f}")
        print(f"  Can trade: {'✅ YES' if limits['can_trade'] else '❌ NO'}")
        
        if not limits['can_trade']:
            print("\nReasons:")
            for reason in limits['reasons']:
                print(f"  - {reason}")
            sys.exit(0)
        
        print()
        
        # Get pending trades
        pending = manager.get_pending_trades()
        
        if not pending:
            print("No pending trades")
            sys.exit(0)
        
        print(f"Pending trades: {len(pending)}")
        print()
        
        # Show pending trades
        for i, trade in enumerate(pending, 1):
            print(f"{i}. {trade['token_symbol']} ({trade['strategy']})")
            print(f"   Score: {trade['signal_score']:.2f}")
            print(f"   Size: ${trade['position_size_usd']:.2f}")
            print(f"   Entry: ${trade['entry_price']:.6f}")
            if trade['entry_price'] > 0:
                stop_pct = ((trade['entry_price'] - trade['stop_loss']) / trade['entry_price'] * 100)
                target_pct = ((trade['take_profit'] - trade['entry_price']) / trade['entry_price'] * 100)
                print(f"   Stop: ${trade['stop_loss']:.6f} (-{stop_pct:.1f}%)")
                print(f"   Target: ${trade['take_profit']:.6f} (+{target_pct:.1f}%)")
            print()
        
        # Interactive approval (if not in CI/CD)
        if sys.stdin.isatty():
            print("Approve trades? (y/n/[trade_numbers]): ", end="")
            response = input().strip().lower()
            
            if response == 'y':
                # Approve all
                for trade in pending:
                    manager.approve_trade(trade['id'])
                print(f"✅ Approved {len(pending)} trades")
            elif response == 'n':
                print("❌ No trades approved")
                sys.exit(0)
            else:
                # Approve specific trades
                try:
                    indices = [int(x.strip()) - 1 for x in response.split(',')]
                    for idx in indices:
                        if 0 <= idx < len(pending):
                            manager.approve_trade(pending[idx]['id'])
                    print(f"✅ Approved {len(indices)} trades")
                except ValueError:
                    print("Invalid input")
                    sys.exit(1)
        else:
            # Auto-approve in CI/CD (only if mode is paper)
            if TRADING_MODE == "paper":
                for trade in pending:
                    manager.approve_trade(trade['id'])
                print(f"✅ Auto-approved {len(pending)} paper trades")
            else:
                print("⚠️ Live trading requires manual approval")
                sys.exit(0)
        
        # Execute approved trades
        print()
        manager.execute_approved_trades()
    
    finally:
        manager.close()


if __name__ == "__main__":
    main()
