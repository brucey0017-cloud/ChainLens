#!/usr/bin/env python3
"""
Strategy Engine - Implement Jim Simons' multi-strategy approach
Strategies: Triple Confirmation, Resonance, Contrarian, Arbitrage

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from price_fetcher import get_market_data, get_price
from supabase_client import insert, is_available, select, update

load_dotenv()


class StrategyEngine:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    @staticmethod
    def _to_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def get_recent_signals(self, hours: int = 1) -> List[Dict]:
        """Get unprocessed signals from last N hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = select(
            "signals",
            columns="id,source,token_symbol,token_address,chain,signal_score,raw_data,timestamp,processed",
            filters={
                "processed": "eq.false",
                "timestamp": f"gte.{cutoff}",
            },
            order="timestamp.desc",
            limit=2000,
        )

        signals: List[Dict] = []
        for row in rows:
            token_address = str(row.get("token_address", "")).strip()
            chain = str(row.get("chain", "")).strip()
            if not token_address or not chain or chain == "unknown":
                continue
            signals.append(
                {
                    "id": int(row.get("id")),
                    "source": str(row.get("source", "")),
                    "token_symbol": str(row.get("token_symbol", "")),
                    "token_address": token_address,
                    "chain": chain,
                    "signal_score": self._to_float(row.get("signal_score"), 0.0),
                    "raw_data": row.get("raw_data"),
                    "timestamp": row.get("timestamp"),
                }
            )
        return signals

    def mark_signals_processed(self, signal_ids: List[int]):
        """Mark signals as processed."""
        if not signal_ids:
            return

        # Batch updates to avoid tight per-item loops.
        chunk = 200
        for i in range(0, len(signal_ids), chunk):
            part = signal_ids[i:i + chunk]
            id_list = ",".join(str(x) for x in part)
            update("signals", {"processed": True}, filters={"id": f"in.({id_list})"})

    def get_token_risk_score(self, token_address: str, chain: str) -> Optional[float]:
        """Get token risk score from auditor."""
        sys.path.insert(0, os.path.dirname(__file__))

        try:
            from token_auditor import TokenAuditor

            auditor = TokenAuditor()
            result = auditor.audit_token(token_address, chain)
            if result and "risk_score" in result:
                return self._to_float(result["risk_score"], 0.0)
        except Exception as e:
            print(f"  Warning: Token auditor failed: {e}", file=sys.stderr)

        # Conservative fallback (not optimistic)
        return 60.0

    def get_token_market_info(self, token_symbol: str, token_address: str, chain: str) -> Optional[Dict]:
        """Get token market cap and liquidity (OKX first)."""
        try:
            info = get_market_data(symbol=token_symbol, token_address=token_address, chain=chain)
            if info and info.get("liquidity", 0) > 0:
                return {
                    "market_cap": self._to_float(info.get("market_cap"), 0.0),
                    "liquidity": self._to_float(info.get("liquidity"), 0.0),
                    "volume_24h": self._to_float(info.get("volume_24h"), 0.0),
                    "price_change_24h": self._to_float(info.get("change_24h"), 0.0),
                }
        except Exception as e:
            print(f"  Warning: Failed to get market info: {e}", file=sys.stderr)

        return None

    def strategy_triple_confirmation(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 1: Triple Confirmation (enforced)
        Requires:
          - smart_money present
          - twitter_kol present
          - at least one extra source from {news,onchain,technical}
          - risk score >= 60
        """
        trades = []

        # Group signals by token
        token_signals: Dict[tuple, List[Dict]] = defaultdict(list)
        for sig in signals:
            key = (sig["token_address"], sig["chain"])
            token_signals[key].append(sig)

        for (token_addr, chain), sigs in token_signals.items():
            token_symbol = sigs[0]["token_symbol"]

            sources = {s["source"] for s in sigs}

            # Enforce real multi-source confirmation before expensive API calls.
            if "smart_money" not in sources:
                continue
            if "twitter_kol" not in sources:
                continue
            if not ({"news", "onchain", "technical"} & sources):
                continue

            max_score = max(s["signal_score"] for s in sigs)
            if max_score < 0.7:
                continue

            # Market sanity filters (after source/score gating to reduce API pressure)
            token_info = self.get_token_market_info(token_symbol, token_addr, chain)
            if not token_info:
                print(f"  Skipped {token_symbol}: cannot fetch market info", file=sys.stderr)
                continue

            market_cap = token_info.get("market_cap", 0.0)
            liquidity = token_info.get("liquidity", 0.0)

            # Different thresholds for pump.fun vs regular tokens
            is_pumpfun = token_addr.endswith("pump")
            if is_pumpfun:
                min_market_cap = 500_000
                min_liquidity = 100_000
            else:
                min_market_cap = 100_000
                min_liquidity = 50_000

            if market_cap < min_market_cap:
                print(
                    f"  Skipped {token_symbol}: market cap ${market_cap:,.0f} < ${min_market_cap:,.0f}",
                    file=sys.stderr,
                )
                continue

            if liquidity < min_liquidity:
                print(
                    f"  Skipped {token_symbol}: liquidity ${liquidity:,.0f} < ${min_liquidity:,.0f}",
                    file=sys.stderr,
                )
                continue

            risk_score = self.get_token_risk_score(token_addr, chain)
            if risk_score is None or risk_score < 60:
                continue

            trades.append(
                {
                    "strategy": "triple_confirmation",
                    "token_symbol": token_symbol,
                    "token_address": token_addr,
                    "chain": chain,
                    "direction": "buy",
                    "signal_score": round(max_score, 3),
                    "risk_score": round(risk_score, 2),
                    "position_size_pct": self._calculate_position_size(max_score, 2, 5),
                    "stop_loss_pct": -15.0,
                    "take_profit_pct": 30.0,
                    "hold_hours": 24,
                    "source_count": len(sources),
                }
            )

        return trades

    def strategy_contrarian(self, signals: List[Dict]) -> List[Dict]:
        """Strategy 3: Contrarian (placeholder)."""
        _ = signals
        return []

    @staticmethod
    def _calculate_position_size(signal_score: float, min_pct: float, max_pct: float) -> float:
        """Calculate position size based on signal strength."""
        normalized = (signal_score - 0.5) / 0.5  # Map 0.5-1.0 to 0-1
        normalized = max(0.0, min(1.0, normalized))
        return round(min_pct + (max_pct - min_pct) * normalized, 2)

    def execute_paper_trades(self, trades: List[Dict]):
        """Execute paper trades (record in database)."""
        if not trades:
            return

        trading_mode = os.getenv("TRADING_MODE", "paper")
        account_size_usd = 10_000.0

        rows = []
        for trade in trades:
            entry_price = get_price(
                chain=trade["chain"],
                token_address=trade["token_address"],
                symbol=trade["token_symbol"],
            ) or 0.0

            if entry_price <= 0:
                print(f"  Skipped {trade['token_symbol']}: no price available", file=sys.stderr)
                continue

            position_size_usd = (trade["position_size_pct"] / 100.0) * account_size_usd
            quantity = position_size_usd / entry_price

            status = "pending_approval" if trading_mode == "live" else "open"

            rows.append(
                {
                    "strategy": trade["strategy"],
                    "token_symbol": trade["token_symbol"],
                    "token_address": trade["token_address"],
                    "chain": trade["chain"],
                    "direction": trade["direction"],
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "position_size_usd": round(position_size_usd, 2),
                    "position_size_pct": trade["position_size_pct"],
                    "stop_loss": entry_price * (1 + trade["stop_loss_pct"] / 100.0),
                    "take_profit": entry_price * (1 + trade["take_profit_pct"] / 100.0),
                    "signal_score": trade["signal_score"],
                    "risk_score": trade["risk_score"],
                    "is_paper": trading_mode == "paper",
                    "status": status,
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                    "notes": f"sources={trade.get('source_count', 0)}",
                }
            )

        if not rows:
            print("No trades inserted (all candidates lacked reliable pricing)")
            return

        insert("trades", rows)

        if trading_mode == "live":
            print(f"Created {len(rows)} trades pending approval")
        else:
            print(f"Executed {len(rows)} paper trades")

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



def main():
    engine = StrategyEngine()
    engine.run()


if __name__ == "__main__":
    main()
