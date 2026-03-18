#!/usr/bin/env python3
"""
Signal Monitor - Collect signals from multiple sources
Based on Jim Simons' multi-source data fusion approach
"""

import json
import logging
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

import db_patch  # noqa: F401, E402 — must import before psycopg2
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
    """Signal monitoring configuration."""
    
    CHAINS = ["solana", "xlayer"]
    MIN_AMOUNT_USD = 100
    COMMAND_TIMEOUT = 30


class SignalMonitor:
    """Monitor and collect signals from multiple on-chain sources."""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = None
    
    @contextmanager
    def _get_connection(self) -> Generator:
        """Context manager for database connection with automatic cleanup."""
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            yield conn
        finally:
            if conn:
                conn.close()
    
    def run_json(self, args: List[str]) -> Optional[Dict[str, Any]]:
        """Execute command and return JSON output."""
        try:
            p = subprocess.run(
                args, 
                capture_output=True, 
                text=True, 
                timeout=Config.COMMAND_TIMEOUT
            )
            if p.returncode != 0:
                logger.error(f"Command failed: {' '.join(args)}")
                logger.error(f"Error: {p.stderr[:200]}")
                return None
            return json.loads(p.stdout)
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(args)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error running command: {e}")
            return None
    
    def fetch_smart_money_signals(self, chain: str = "solana", min_amount: int = None) -> List[Dict]:
        """Fetch Smart Money signals from onchainos."""
        if min_amount is None:
            min_amount = Config.MIN_AMOUNT_USD
        
        logger.info(f"Fetching Smart Money signals for {chain} (min ${min_amount})...")
        
        data = self.run_json([
            "onchainos", "signal", "list",
            "--chain", chain,
            "--wallet-type", "1",  # Smart Money
            "--min-amount-usd", str(min_amount)
        ])
        
        if not data or not data.get("ok"):
            return []
        
        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append({
                "source": "smart_money",
                "token_symbol": token.get("symbol", ""),
                "token_address": token.get("tokenAddress", ""),
                "chain": chain,
                "amount_usd": float(sig.get("amountUsd", 0)),
                "wallet_count": int(sig.get("triggerWalletCount", 0)),
                "timestamp": sig.get("timestamp", ""),
                "raw_data": sig
            })
        
        logger.info(f"  Found {len(signals)} Smart Money signals")
        return signals
    
    def calculate_signal_score(self, signal: Dict) -> float:
        """Calculate signal score based on multiple factors."""
        source = signal["source"]
        
        if source == "smart_money":
            # Smart Money scoring
            amount_score = min(signal.get("amount_usd", 0) / 10000, 1.0) * 0.4
            wallet_score = min(signal.get("wallet_count", 0) / 10, 1.0) * 0.3
            # TODO: Add historical win rate when available
            base_score = 0.3
            return amount_score + wallet_score + base_score
        
        elif source == "kol":
            # KOL scoring (higher base score due to influence)
            amount_score = min(signal.get("amount_usd", 0) / 5000, 1.0) * 0.3
            wallet_score = min(signal.get("wallet_count", 0) / 5, 1.0) * 0.3
            base_score = 0.4  # KOLs have higher influence
            return amount_score + wallet_score + base_score
        
        elif source == "whale":
            # Whale scoring (focus on amount)
            amount_score = min(signal.get("amount_usd", 0) / 50000, 1.0) * 0.5
            wallet_score = min(signal.get("wallet_count", 0) / 3, 1.0) * 0.2
            base_score = 0.3
            return amount_score + wallet_score + base_score
        
        elif source == "twitter":
            # Twitter scoring (placeholder)
            return 0.5
        
        elif source == "news":
            # News scoring (placeholder)
            return 0.5
        
        return 0.0
    
    def store_signals(self, signals: List[Dict]):
        """Store signals in database (Supabase REST preferred, psycopg2 fallback)."""
        if not signals:
            return

        rows = []
        for sig in signals:
            score = self.calculate_signal_score(sig)
            rows.append({
                "source": sig["source"],
                "token_symbol": sig["token_symbol"],
                "token_address": sig["token_address"],
                "chain": sig["chain"],
                "signal_score": round(score, 2),
                "raw_data": json.dumps(sig.get("raw_data", {})),
            })

        # Try Supabase REST first
        try:
            from supabase_client import insert, is_available
            if is_available():
                insert("signals", rows)
                logger.info(f"Stored {len(rows)} signals via Supabase REST")
                return
        except Exception as e:
            logger.warning(f"Supabase REST insert failed: {e}, falling back to psycopg2")

        # Fallback: psycopg2
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute("""
                        INSERT INTO signals (source, token_symbol, token_address, chain, signal_score, raw_data)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (row["source"], row["token_symbol"], row["token_address"],
                          row["chain"], row["signal_score"], row["raw_data"]))
                conn.commit()

        logger.info(f"Stored {len(rows)} signals via psycopg2")
    
    def fetch_kol_signals(self, chain: str = "solana") -> List[Dict]:
        """Fetch KOL signals from onchainos."""
        logger.info(f"Fetching KOL signals for {chain}...")
        
        data = self.run_json([
            "onchainos", "signal", "list",
            "--chain", chain,
            "--wallet-type", "2"  # KOL
        ])
        
        if not data or not data.get("ok"):
            return []
        
        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append({
                "source": "kol",
                "token_symbol": token.get("symbol", ""),
                "token_address": token.get("tokenAddress", ""),
                "chain": chain,
                "amount_usd": float(sig.get("amountUsd", 0)),
                "wallet_count": int(sig.get("triggerWalletCount", 0)),
                "timestamp": sig.get("timestamp", ""),
                "raw_data": sig
            })
        
        logger.info(f"  Found {len(signals)} KOL signals")
        return signals
    
    def fetch_whale_signals(self, chain: str = "solana") -> List[Dict]:
        """Fetch Whale signals from onchainos."""
        logger.info(f"Fetching Whale signals for {chain}...")
        
        data = self.run_json([
            "onchainos", "signal", "list",
            "--chain", chain,
            "--wallet-type", "3"  # Whale
        ])
        
        if not data or not data.get("ok"):
            return []
        
        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append({
                "source": "whale",
                "token_symbol": token.get("symbol", ""),
                "token_address": token.get("tokenAddress", ""),
                "chain": chain,
                "amount_usd": float(sig.get("amountUsd", 0)),
                "wallet_count": int(sig.get("triggerWalletCount", 0)),
                "timestamp": sig.get("timestamp", ""),
                "raw_data": sig
            })
        
        logger.info(f"  Found {len(signals)} Whale signals")
        return signals
    
    def run(self):
        """Main execution loop."""
        logger.info(f"=== Signal Monitor - {datetime.now().isoformat()} ===")
        
        # Fetch signals from all sources
        all_signals = []
        
        for chain in Config.CHAINS:
            # Smart Money
            sm_signals = self.fetch_smart_money_signals(chain)
            all_signals.extend(sm_signals)
            
            # KOL
            kol_signals = self.fetch_kol_signals(chain)
            all_signals.extend(kol_signals)
            
            # Whale
            whale_signals = self.fetch_whale_signals(chain)
            all_signals.extend(whale_signals)
        
        # TODO: Add Twitter signals (opentwitter skill)
        # TODO: Add News signals (opennews skill)
        
        # Store in database
        if all_signals:
            self.store_signals(all_signals)
            logger.info(f"\nTotal signals collected: {len(all_signals)}")
            
            # Summary by chain
            for chain in Config.CHAINS:
                chain_signals = [s for s in all_signals if s["chain"] == chain]
                sm = len([s for s in chain_signals if s["source"] == "smart_money"])
                kol = len([s for s in chain_signals if s["source"] == "kol"])
                whale = len([s for s in chain_signals if s["source"] == "whale"])
                logger.info(f"  {chain} - Smart Money: {sm}, KOL: {kol}, Whale: {whale}")
        else:
            logger.info("\nNo signals collected")


def main():
    monitor = SignalMonitor(DB_URL)
    monitor.run()


if __name__ == "__main__":
    main()
