#!/usr/bin/env python3
"""
On-chain Metrics Monitor - Track whale movements and holder patterns.

Uses OKX onchainos token endpoints + Supabase REST only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from supabase_client import insert, is_available, select


class OnchainMonitor:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

        # Thresholds
        self.whale_threshold = 100_000  # $100K+ transactions
        self.min_holders = 100
        self.max_top10_concentration = 0.5  # Top 10 holders < 50%

    def _run_json(self, args: List[str], timeout: int = 30) -> Optional[Dict]:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            return data if isinstance(data, dict) else None
        except Exception as e:
            print(f"Error running command {' '.join(args)}: {e}", file=sys.stderr)
            return None

    @staticmethod
    def _safe_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def get_token_holders(self, token_address: str, chain: str) -> List[Dict]:
        """Get holder distribution for a token."""
        data = self._run_json(["onchainos", "token", "holders", "--address", token_address, "--chain", chain])
        if not data or not data.get("ok"):
            return []
        rows = data.get("data", [])
        return rows if isinstance(rows, list) else []

    def get_large_transactions(self, token_address: str, chain: str, limit: int = 120) -> List[Dict]:
        """Get recent large transactions via token trades."""
        data = self._run_json(
            [
                "onchainos",
                "token",
                "trades",
                "--address",
                token_address,
                "--chain",
                chain,
                "--limit",
                str(limit),
            ]
        )

        if not data or not data.get("ok"):
            return []

        txs = data.get("data", [])
        if not isinstance(txs, list):
            return []

        large = []
        for tx in txs:
            vol = self._safe_float(tx.get("volume"), 0.0)
            if vol >= self.whale_threshold:
                large.append({
                    "type": str(tx.get("type", "")).lower(),
                    "value_usd": vol,
                    "user": tx.get("userAddress", ""),
                    "time": tx.get("time", ""),
                })
        return large

    def analyze_holder_distribution(self, holders: List[Dict]) -> Dict:
        """Analyze holder distribution patterns from top holder rows."""
        total_holders = len(holders)

        if not holders:
            return {
                "score": 0.0,
                "risk": "unknown",
                "reason": "No holder data available",
            }

        # Calculate top 10 concentration from holdPercent
        top10_pct = sum(self._safe_float(h.get("holdPercent"), 0.0) for h in holders[:10]) / 100.0

        # Score based on distribution
        if total_holders < self.min_holders:
            score = 0.3
            risk = "high"
            reason = f"Only {total_holders} holders (min: {self.min_holders})"
        elif top10_pct > self.max_top10_concentration:
            score = 0.4
            risk = "high"
            reason = f"Top 10 hold {top10_pct:.1%} (max: {self.max_top10_concentration:.0%})"
        elif top10_pct > 0.3:
            score = 0.6
            risk = "medium"
            reason = f"Top 10 hold {top10_pct:.1%}"
        else:
            score = 0.8
            risk = "low"
            reason = f"Well distributed: {total_holders} holders, top 10: {top10_pct:.1%}"

        return {
            "score": score,
            "risk": risk,
            "reason": reason,
            "total_holders": total_holders,
            "top10_concentration": top10_pct,
        }

    def analyze_whale_activity(self, transactions: List[Dict]) -> Dict:
        """Analyze whale buying/selling patterns."""
        if not transactions:
            return {
                "score": 0.5,
                "signal": "neutral",
                "reason": "No whale activity",
            }

        # Categorize transactions
        buys = [tx for tx in transactions if tx.get("type") == "buy"]
        sells = [tx for tx in transactions if tx.get("type") == "sell"]

        buy_volume = sum(self._safe_float(tx.get("value_usd"), 0.0) for tx in buys)
        sell_volume = sum(self._safe_float(tx.get("value_usd"), 0.0) for tx in sells)

        # Calculate net flow
        net_flow = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume

        if total_volume == 0:
            return {
                "score": 0.5,
                "signal": "neutral",
                "reason": "No significant volume",
            }

        # Score based on net flow
        flow_ratio = net_flow / total_volume

        if flow_ratio > 0.5:
            score = 0.9
            signal = "strong_buy"
            reason = f"Whales accumulating: ${buy_volume:,.0f} buy vs ${sell_volume:,.0f} sell"
        elif flow_ratio > 0.2:
            score = 0.7
            signal = "buy"
            reason = f"Net buying: ${net_flow:,.0f}"
        elif flow_ratio > -0.2:
            score = 0.5
            signal = "neutral"
            reason = f"Balanced: ${buy_volume:,.0f} / ${sell_volume:,.0f}"
        elif flow_ratio > -0.5:
            score = 0.3
            signal = "sell"
            reason = f"Net selling: ${-net_flow:,.0f}"
        else:
            score = 0.1
            signal = "strong_sell"
            reason = f"Whales dumping: ${sell_volume:,.0f} sell vs ${buy_volume:,.0f} buy"

        return {
            "score": score,
            "signal": signal,
            "reason": reason,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "net_flow": net_flow,
            "transaction_count": len(transactions),
        }

    def monitor_token(self, token_address: str, token_symbol: str, chain: str) -> Optional[Dict]:
        """Comprehensive on-chain analysis for a token."""
        print(f"Analyzing on-chain metrics for {token_symbol}...")

        # Get holder distribution
        holders = self.get_token_holders(token_address, chain)
        distribution_analysis = self.analyze_holder_distribution(holders)

        # Get whale transactions
        transactions = self.get_large_transactions(token_address, chain)
        whale_analysis = self.analyze_whale_activity(transactions)

        # Combined score (60% whale activity, 40% distribution)
        combined_score = (whale_analysis["score"] * 0.6 + distribution_analysis["score"] * 0.4)

        # Save signal to database
        signal_data = {
            "source": "onchain",
            "token_symbol": token_symbol,
            "token_address": token_address,
            "chain": chain,
            "signal_score": round(combined_score, 3),
            "raw_data": {
                "distribution": distribution_analysis,
                "whale_activity": whale_analysis,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": False,
        }

        self.save_signal(signal_data)

        return {
            "token_symbol": token_symbol,
            "token_address": token_address,
            "chain": chain,
            "score": combined_score,
            "distribution": distribution_analysis,
            "whale_activity": whale_analysis,
        }

    def save_signal(self, signal: Dict):
        """Save on-chain signal to database."""
        insert("signals", [signal])

    def monitor_all_active_tokens(self):
        """Monitor all tokens with recent signals."""
        print(f"=== On-chain Monitor - {datetime.now().isoformat()} ===")

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rows = select(
            "signals",
            columns="token_address,token_symbol,chain,source,timestamp",
            filters={"timestamp": f"gte.{cutoff}"},
            order="timestamp.desc",
            limit=1000,
        )

        seen = set()
        tokens = []
        for r in rows:
            source = str(r.get("source", ""))
            addr = str(r.get("token_address", "")).strip()
            sym = str(r.get("token_symbol", "")).strip()
            chain = str(r.get("chain", "")).strip()
            if source == "onchain" or not addr or not chain or chain == "unknown":
                continue
            key = (addr, chain)
            if key in seen:
                continue
            seen.add(key)
            tokens.append((addr, sym, chain))

        print(f"Monitoring {len(tokens)} tokens...")

        results = []
        for token_addr, token_symbol, chain in tokens:
            try:
                result = self.monitor_token(token_addr, token_symbol, chain)
                if result:
                    results.append(result)
                    print(
                        f"  {token_symbol}: score={result['score']:.2f}, "
                        f"whale={result['whale_activity']['signal']}, "
                        f"distribution={result['distribution']['risk']}"
                    )
            except Exception as e:
                print(f"  Error monitoring {token_symbol}: {e}", file=sys.stderr)

        print(f"\nCompleted on-chain analysis for {len(results)} tokens")
        return results


if __name__ == "__main__":
    monitor = OnchainMonitor()
    monitor.monitor_all_active_tokens()
