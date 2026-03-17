#!/usr/bin/env python3
"""
On-chain Metrics Monitor - Track whale movements and holder patterns
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class OnchainMonitor:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
        
        # Thresholds
        self.whale_threshold = 100_000  # $100K+ transactions
        self.min_holders = 100
        self.max_top10_concentration = 0.5  # Top 10 holders < 50%
    
    def get_token_holders(self, token_address: str, chain: str) -> Optional[Dict]:
        """Get holder distribution for a token."""
        try:
            result = subprocess.run(
                ["onchainos", "market", "holders", "--address", token_address, "--chain", chain],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return None
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return None
            
            holder_data = data.get("data", {})
            return holder_data
        
        except Exception as e:
            print(f"Error fetching holders: {e}", file=sys.stderr)
            return None
    
    def get_large_transactions(self, token_address: str, chain: str, limit: int = 20) -> List[Dict]:
        """Get recent large transactions."""
        try:
            result = subprocess.run(
                ["onchainos", "market", "transactions", "--address", token_address, "--chain", chain, "--limit", str(limit)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            txs = data.get("data", [])
            
            # Filter for large transactions
            large_txs = [tx for tx in txs if tx.get("value_usd", 0) >= self.whale_threshold]
            
            return large_txs
        
        except Exception as e:
            print(f"Error fetching transactions: {e}", file=sys.stderr)
            return []
    
    def analyze_holder_distribution(self, holder_data: Dict) -> Dict:
        """Analyze holder distribution patterns."""
        total_holders = holder_data.get("holder_count", 0)
        top_holders = holder_data.get("top_holders", [])
        
        if not top_holders:
            return {
                "score": 0.0,
                "risk": "unknown",
                "reason": "No holder data available"
            }
        
        # Calculate top 10 concentration
        top10_pct = sum(h.get("percentage", 0) for h in top_holders[:10])
        
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
            "top10_concentration": top10_pct
        }
    
    def analyze_whale_activity(self, transactions: List[Dict]) -> Dict:
        """Analyze whale buying/selling patterns."""
        if not transactions:
            return {
                "score": 0.5,
                "signal": "neutral",
                "reason": "No whale activity"
            }
        
        # Categorize transactions
        buys = [tx for tx in transactions if tx.get("type") == "buy"]
        sells = [tx for tx in transactions if tx.get("type") == "sell"]
        
        buy_volume = sum(tx.get("value_usd", 0) for tx in buys)
        sell_volume = sum(tx.get("value_usd", 0) for tx in sells)
        
        # Calculate net flow
        net_flow = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return {
                "score": 0.5,
                "signal": "neutral",
                "reason": "No significant volume"
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
            "transaction_count": len(transactions)
        }
    
    def monitor_token(self, token_address: str, token_symbol: str, chain: str) -> Optional[Dict]:
        """Comprehensive on-chain analysis for a token."""
        print(f"Analyzing on-chain metrics for {token_symbol}...")
        
        # Get holder distribution
        holder_data = self.get_token_holders(token_address, chain)
        if holder_data:
            distribution_analysis = self.analyze_holder_distribution(holder_data)
        else:
            distribution_analysis = {"score": 0.5, "risk": "unknown", "reason": "No data"}
        
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
            "signal_score": combined_score,
            "raw_data": json.dumps({
                "distribution": distribution_analysis,
                "whale_activity": whale_analysis
            })
        }
        
        self.save_signal(signal_data)
        
        return {
            "token_symbol": token_symbol,
            "token_address": token_address,
            "chain": chain,
            "score": combined_score,
            "distribution": distribution_analysis,
            "whale_activity": whale_analysis
        }
    
    def save_signal(self, signal: Dict):
        """Save on-chain signal to database."""
        cur = self.conn.cursor()
        
        cur.execute("""
            INSERT INTO signals (
                source, token_symbol, token_address, chain,
                signal_score, raw_data, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            signal["source"],
            signal["token_symbol"],
            signal["token_address"],
            signal["chain"],
            signal["signal_score"],
            signal["raw_data"],
            datetime.now()
        ))
        
        self.conn.commit()
        cur.close()
    
    def monitor_all_active_tokens(self):
        """Monitor all tokens with recent signals."""
        print(f"=== On-chain Monitor - {datetime.now().isoformat()} ===")
        
        cur = self.conn.cursor()
        
        # Get unique tokens from recent signals
        cur.execute("""
            SELECT DISTINCT token_address, token_symbol, chain
            FROM signals
            WHERE created_at >= NOW() - INTERVAL '2 hours'
              AND source != 'onchain'
        """)
        
        tokens = cur.fetchall()
        cur.close()
        
        print(f"Monitoring {len(tokens)} tokens...")
        
        results = []
        for token_addr, token_symbol, chain in tokens:
            try:
                result = self.monitor_token(token_addr, token_symbol, chain)
                if result:
                    results.append(result)
                    print(f"  {token_symbol}: score={result['score']:.2f}, "
                          f"whale={result['whale_activity']['signal']}, "
                          f"distribution={result['distribution']['risk']}")
            except Exception as e:
                print(f"  Error monitoring {token_symbol}: {e}", file=sys.stderr)
        
        print(f"\nCompleted on-chain analysis for {len(results)} tokens")
        return results


if __name__ == "__main__":
    monitor = OnchainMonitor()
    monitor.monitor_all_active_tokens()
