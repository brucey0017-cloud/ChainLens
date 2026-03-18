#!/usr/bin/env python3
"""
Multi-Signal Scorer - Combine signals from all sources intelligently
Implements weighted scoring with confidence factors.

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from supabase_client import is_available, select


class MultiSignalScorer:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

        # Signal source weights
        self.weights = {
            "twitter_kol": 0.30,
            "smart_money": 0.25,
            "news": 0.20,
            "onchain": 0.15,
            "technical": 0.10,
        }

        # Minimum scores
        self.min_total_score = 0.70
        self.min_sources = 2  # Require at least 2 sources

    @staticmethod
    def _to_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_ts(v):
        s = str(v or "")
        if not s:
            return datetime.now(timezone.utc)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.now(timezone.utc)

    def get_recent_signals(self, token_address: str, chain: str, hours: int = 2) -> List[Dict]:
        """Get all recent signals for a token."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = select(
            "signals",
            columns="source,signal_score,raw_data,timestamp",
            filters={
                "token_address": f"eq.{token_address}",
                "chain": f"eq.{chain}",
                "timestamp": f"gte.{cutoff}",
            },
            order="timestamp.desc",
            limit=5000,
        )

        signals = []
        for row in rows:
            signals.append(
                {
                    "source": str(row.get("source", "")),
                    "signal_score": self._to_float(row.get("signal_score"), 0.0),
                    "raw_data": row.get("raw_data"),
                    "timestamp": self._parse_ts(row.get("timestamp")),
                }
            )

        return signals

    def calculate_source_score(self, signals: List[Dict], source: str) -> Optional[Dict]:
        """Calculate aggregated score for a specific source."""
        source_signals = [s for s in signals if s["source"] == source]

        if not source_signals:
            return None

        # Get highest score (most bullish signal)
        max_score = max(s["signal_score"] for s in source_signals)

        # Calculate confidence based on signal count and recency
        confidence = min(1.0, len(source_signals) / 5.0)  # Max confidence at 5+ signals

        # Recency factor (newer signals weighted higher)
        now = datetime.now(timezone.utc)
        recency_weights = []
        for sig in source_signals:
            age_hours = max(0.0, (now - sig["timestamp"]).total_seconds() / 3600.0)
            recency = max(0.5, 1.0 - (age_hours / 24.0))  # Decay over 24h
            recency_weights.append(recency)

        avg_recency = sum(recency_weights) / len(recency_weights)

        return {
            "score": max_score,
            "confidence": confidence,
            "recency": avg_recency,
            "count": len(source_signals),
            "adjusted_score": max_score * confidence * avg_recency,
        }

    def calculate_multi_signal_score(self, token_address: str, chain: str) -> Optional[Dict]:
        """Calculate combined score from all signal sources."""
        signals = self.get_recent_signals(token_address, chain, hours=2)

        if not signals:
            return None

        # Calculate scores for each source
        source_scores = {}
        for source in self.weights.keys():
            score_data = self.calculate_source_score(signals, source)
            if score_data:
                source_scores[source] = score_data

        # Check minimum sources requirement
        if len(source_scores) < self.min_sources:
            return None

        # Calculate weighted total score
        total_score = 0.0
        total_weight = 0.0

        for source, weight in self.weights.items():
            if source in source_scores:
                adjusted_score = source_scores[source]["adjusted_score"]
                total_score += adjusted_score * weight
                total_weight += weight

        # Normalize by actual weight used
        final_score = (total_score / total_weight) if total_weight > 0 else 0.0

        # Calculate overall confidence
        confidences = [s["confidence"] for s in source_scores.values()]
        avg_confidence = sum(confidences) / len(confidences)

        return {
            "token_address": token_address,
            "chain": chain,
            "total_score": final_score,
            "confidence": avg_confidence,
            "source_count": len(source_scores),
            "source_scores": source_scores,
            "meets_threshold": final_score >= self.min_total_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_top_tokens(self, chain: str = "solana", limit: int = 10) -> List[Dict]:
        """Get top-scored tokens across all signals."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rows = select(
            "signals",
            columns="token_address,token_symbol",
            filters={
                "chain": f"eq.{chain}",
                "timestamp": f"gte.{cutoff}",
            },
            order="timestamp.desc",
            limit=5000,
        )

        seen = set()
        tokens = []
        for r in rows:
            addr = str(r.get("token_address", "")).strip()
            sym = str(r.get("token_symbol", "")).strip()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            tokens.append((addr, sym))

        # Score each token
        scored_tokens = []
        for token_addr, token_symbol in tokens:
            score_data = self.calculate_multi_signal_score(token_addr, chain)
            if score_data and score_data["meets_threshold"]:
                score_data["token_symbol"] = token_symbol
                scored_tokens.append(score_data)

        # Sort by total score
        scored_tokens.sort(key=lambda x: x["total_score"], reverse=True)

        return scored_tokens[:limit]

    def print_score_report(self, score_data: Dict):
        """Print detailed scoring report."""
        print(f"\n{'=' * 60}")
        print(f"Token: {score_data.get('token_symbol', 'Unknown')} ({score_data['token_address'][:8]}...)")
        print(f"Chain: {score_data['chain']}")
        print(f"{'=' * 60}")
        print(f"Total Score: {score_data['total_score']:.3f} {'✅' if score_data['meets_threshold'] else '❌'}")
        print(f"Confidence: {score_data['confidence']:.2f}")
        print(f"Sources: {score_data['source_count']}")
        print("\nSource Breakdown:")

        for source, data in score_data['source_scores'].items():
            weight = self.weights.get(source, 0)
            print(
                f"  {source:15s} | Score: {data['score']:.2f} | "
                f"Conf: {data['confidence']:.2f} | "
                f"Recency: {data['recency']:.2f} | "
                f"Count: {data['count']:2d} | "
                f"Weight: {weight:.2f}"
            )

        print(f"{'=' * 60}\n")



def main():
    print(f"=== Multi-Signal Scorer - {datetime.now().isoformat()} ===\n")

    scorer = MultiSignalScorer()

    # Get top tokens
    top_tokens = scorer.get_top_tokens(chain="solana", limit=10)

    print(f"Found {len(top_tokens)} tokens meeting threshold (>= {scorer.min_total_score})\n")

    for token_data in top_tokens:
        scorer.print_score_report(token_data)

    if not top_tokens:
        print("No tokens currently meet the multi-signal threshold.")
        print("This is normal if the system just started or during low-activity periods.")


if __name__ == "__main__":
    main()
