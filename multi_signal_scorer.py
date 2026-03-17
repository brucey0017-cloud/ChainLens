#!/usr/bin/env python3
"""
Multi-Signal Scorer - Combine signals from all sources intelligently
Implements weighted scoring with confidence factors
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class MultiSignalScorer:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
        
        # Signal source weights
        self.weights = {
            "twitter_kol": 0.30,
            "smart_money": 0.25,
            "news": 0.20,
            "onchain": 0.15,
            "technical": 0.10
        }
        
        # Minimum scores
        self.min_total_score = 0.70
        self.min_sources = 2  # Require at least 2 sources
    
    def get_recent_signals(self, token_address: str, chain: str, hours: int = 1) -> List[Dict]:
        """Get all recent signals for a token."""
        cur = self.conn.cursor()
        
        since = datetime.now() - timedelta(hours=hours)
        
        cur.execute("""
            SELECT source, signal_score, raw_data, timestamp
            FROM signals
            WHERE token_address = %s
              AND chain = %s
              AND timestamp >= %s
            ORDER BY timestamp DESC
        """, (token_address, chain, since))
        
        signals = []
        for row in cur.fetchall():
            signals.append({
                "source": row[0],
                "signal_score": float(row[1]),
                "raw_data": row[2],
                "timestamp": row[3]
            })
        
        cur.close()
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
        now = datetime.now()
        recency_weights = []
        for sig in source_signals:
            age_hours = (now - sig["timestamp"]).total_seconds() / 3600
            recency = max(0.5, 1.0 - (age_hours / 24))  # Decay over 24h
            recency_weights.append(recency)
        
        avg_recency = sum(recency_weights) / len(recency_weights)
        
        return {
            "score": max_score,
            "confidence": confidence,
            "recency": avg_recency,
            "count": len(source_signals),
            "adjusted_score": max_score * confidence * avg_recency
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
        if total_weight > 0:
            final_score = total_score / total_weight
        else:
            final_score = 0.0
        
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
            "timestamp": datetime.now()
        }
    
    def get_top_tokens(self, chain: str = "solana", limit: int = 10) -> List[Dict]:
        """Get top-scored tokens across all signals."""
        cur = self.conn.cursor()
        
        # Get unique tokens from recent signals
        since = datetime.now() - timedelta(hours=2)
        
        cur.execute("""
            SELECT DISTINCT token_address, token_symbol
            FROM signals
            WHERE chain = %s
              AND timestamp >= %s
        """, (chain, since))
        
        tokens = cur.fetchall()
        cur.close()
        
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
        print(f"\n{'='*60}")
        print(f"Token: {score_data.get('token_symbol', 'Unknown')} ({score_data['token_address'][:8]}...)")
        print(f"Chain: {score_data['chain']}")
        print(f"{'='*60}")
        print(f"Total Score: {score_data['total_score']:.3f} {'✅' if score_data['meets_threshold'] else '❌'}")
        print(f"Confidence: {score_data['confidence']:.2f}")
        print(f"Sources: {score_data['source_count']}")
        print(f"\nSource Breakdown:")
        
        for source, data in score_data['source_scores'].items():
            weight = self.weights.get(source, 0)
            print(f"  {source:15s} | Score: {data['score']:.2f} | "
                  f"Conf: {data['confidence']:.2f} | "
                  f"Recency: {data['recency']:.2f} | "
                  f"Count: {data['count']:2d} | "
                  f"Weight: {weight:.2f}")
        
        print(f"{'='*60}\n")


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
