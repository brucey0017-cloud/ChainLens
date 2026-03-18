#!/usr/bin/env python3
"""
Signal Monitor - Collect Smart Money signals via onchainos CLI.

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from supabase_client import insert, is_available

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Config:
    """Configuration for signal monitoring."""

    CHAINS = ["solana"]
    KOL_WALLET_TYPE = "2"
    WHALE_WALLET_TYPE = "3"
    SMART_MONEY_WALLET_TYPE = "1"


class SignalMonitor:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    @staticmethod
    def _safe_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(v, default: int = 0) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def run_json(self, args: List[str], timeout_sec: int = 40) -> Optional[Dict]:
        """Run a command and return parsed JSON output."""
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
            if result.returncode != 0:
                logger.warning(f"Command failed (rc={result.returncode}): {' '.join(args)}")
                return None
            payload = json.loads(result.stdout)
            return payload if isinstance(payload, dict) else None
        except Exception as e:
            logger.error(f"Command error: {e}")
            return None

    def calculate_signal_score(self, signal: Dict) -> float:
        """Calculate a normalized signal score from raw signal fields."""
        source = str(signal.get("source", "")).lower()

        if source == "smart_money":
            amount_score = min(self._safe_float(signal.get("amount_usd"), 0.0) / 10000.0, 1.0) * 0.4
            wallet_score = min(self._safe_int(signal.get("wallet_count"), 0) / 5, 1.0) * 0.3
            base_score = 0.3
            return amount_score + wallet_score + base_score

        if source == "kol":
            amount_score = min(self._safe_float(signal.get("amount_usd"), 0.0) / 30000.0, 1.0) * 0.3
            wallet_score = min(self._safe_int(signal.get("wallet_count"), 0) / 5, 1.0) * 0.3
            base_score = 0.4  # KOLs have higher influence
            return amount_score + wallet_score + base_score

        if source == "whale":
            amount_score = min(self._safe_float(signal.get("amount_usd"), 0.0) / 50000.0, 1.0) * 0.5
            wallet_score = min(self._safe_int(signal.get("wallet_count"), 0) / 3, 1.0) * 0.2
            base_score = 0.3
            return amount_score + wallet_score + base_score

        if source in ("twitter", "news"):
            return 0.5

        return 0.0

    def store_signals(self, signals: List[Dict]):
        """Store signals in Supabase."""
        if not signals:
            return

        rows = []
        for sig in signals:
            score = self.calculate_signal_score(sig)
            rows.append(
                {
                    "source": sig["source"],
                    "token_symbol": sig["token_symbol"],
                    "token_address": sig["token_address"],
                    "chain": sig["chain"],
                    "signal_score": round(score, 3),
                    "raw_data": sig.get("raw_data", {}),
                    "timestamp": sig.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                    "processed": False,
                }
            )

        insert("signals", rows)
        logger.info(f"Stored {len(rows)} signals via Supabase REST")

    def fetch_kol_signals(self, chain: str = "solana") -> List[Dict]:
        """Fetch KOL signals from onchainos."""
        logger.info(f"Fetching KOL signals for {chain}...")

        data = self.run_json(
            [
                "onchainos",
                "signal",
                "list",
                "--chain",
                chain,
                "--wallet-type",
                Config.KOL_WALLET_TYPE,
            ]
        )

        if not data or not data.get("ok"):
            return []

        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append(
                {
                    "source": "kol",
                    "token_symbol": token.get("symbol", ""),
                    "token_address": token.get("tokenAddress", ""),
                    "chain": chain,
                    "amount_usd": self._safe_float(sig.get("amountUsd", 0), 0.0),
                    "wallet_count": self._safe_int(sig.get("triggerWalletCount", 0), 0),
                    "timestamp": sig.get("timestamp", ""),
                    "raw_data": sig,
                }
            )

        logger.info(f"  Found {len(signals)} KOL signals")
        return signals

    def fetch_whale_signals(self, chain: str = "solana") -> List[Dict]:
        """Fetch Whale signals from onchainos."""
        logger.info(f"Fetching Whale signals for {chain}...")

        data = self.run_json(
            [
                "onchainos",
                "signal",
                "list",
                "--chain",
                chain,
                "--wallet-type",
                Config.WHALE_WALLET_TYPE,
            ]
        )

        if not data or not data.get("ok"):
            return []

        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append(
                {
                    "source": "whale",
                    "token_symbol": token.get("symbol", ""),
                    "token_address": token.get("tokenAddress", ""),
                    "chain": chain,
                    "amount_usd": self._safe_float(sig.get("amountUsd", 0), 0.0),
                    "wallet_count": self._safe_int(sig.get("triggerWalletCount", 0), 0),
                    "timestamp": sig.get("timestamp", ""),
                    "raw_data": sig,
                }
            )

        logger.info(f"  Found {len(signals)} Whale signals")
        return signals

    def fetch_smart_money_signals(self, chain: str = "solana") -> List[Dict]:
        """Fetch Smart Money signals from onchainos."""
        logger.info(f"Fetching Smart Money signals for {chain}...")

        data = self.run_json(
            [
                "onchainos",
                "signal",
                "list",
                "--chain",
                chain,
                "--wallet-type",
                Config.SMART_MONEY_WALLET_TYPE,
            ]
        )

        if not data or not data.get("ok"):
            return []

        signals = []
        for sig in data.get("data", []):
            token = sig.get("token", {})
            signals.append(
                {
                    "source": "smart_money",
                    "token_symbol": token.get("symbol", ""),
                    "token_address": token.get("tokenAddress", ""),
                    "chain": chain,
                    "amount_usd": self._safe_float(sig.get("amountUsd", 0), 0.0),
                    "wallet_count": self._safe_int(sig.get("triggerWalletCount", 0), 0),
                    "timestamp": sig.get("timestamp", ""),
                    "raw_data": sig,
                }
            )

        logger.info(f"  Found {len(signals)} Smart Money signals")
        return signals

    def run(self):
        """Main execution loop."""
        logger.info(f"=== Signal Monitor - {datetime.now().isoformat()} ===")

        # Fetch signals from all sources
        all_signals: List[Dict] = []

        for chain in Config.CHAINS:
            sm_signals = self.fetch_smart_money_signals(chain)
            all_signals.extend(sm_signals)

            kol_signals = self.fetch_kol_signals(chain)
            all_signals.extend(kol_signals)

            whale_signals = self.fetch_whale_signals(chain)
            all_signals.extend(whale_signals)

        logger.info(f"Total signals collected: {len(all_signals)}")

        # Store signals
        if all_signals:
            self.store_signals(all_signals)
        else:
            logger.info("No signals to store")



def main():
    monitor = SignalMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
