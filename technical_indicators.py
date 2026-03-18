#!/usr/bin/env python3
"""
Technical Indicators - Price momentum, volume, volatility analysis
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import db_patch  # noqa: F401, E402 — must import before psycopg2
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class TechnicalIndicators:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
    
    def get_price_history(self, token_address: str, chain: str, hours: int = 24) -> List[Dict]:
        """Get historical price data."""
        try:
            # Use onchainos to get price history
            result = subprocess.run(
                ["onchainos", "market", "price-history", "--address", token_address, "--chain", chain, "--hours", str(hours)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []
            
            prices = data.get("data", [])
            return prices
        
        except Exception as e:
            print(f"Error fetching price history: {e}", file=sys.stderr)
            return []
    
    def calculate_momentum(self, prices: List[Dict]) -> Dict:
        """Calculate price momentum indicators."""
        if len(prices) < 2:
            return {"score": 0.5, "signal": "neutral", "reason": "Insufficient data"}
        
        # Sort by timestamp
        prices = sorted(prices, key=lambda x: x.get("timestamp", 0))
        
        # Calculate returns
        first_price = float(prices[0].get("price", 0))
        last_price = float(prices[-1].get("price", 0))
        
        if first_price == 0:
            return {"score": 0.5, "signal": "neutral", "reason": "Invalid price data"}
        
        total_return = (last_price - first_price) / first_price
        
        # Calculate short-term momentum (last 25% of data)
        split_point = int(len(prices) * 0.75)
        recent_prices = prices[split_point:]
        
        if len(recent_prices) >= 2:
            recent_first = float(recent_prices[0].get("price", 0))
            recent_last = float(recent_prices[-1].get("price", 0))
            
            if recent_first > 0:
                recent_return = (recent_last - recent_first) / recent_first
            else:
                recent_return = 0
        else:
            recent_return = total_return
        
        # Score based on momentum
        if total_return > 0.15 and recent_return > 0.05:
            score = 0.9
            signal = "strong_bullish"
            reason = f"+{total_return*100:.1f}% (24h), +{recent_return*100:.1f}% (recent)"
        elif total_return > 0.05:
            score = 0.7
            signal = "bullish"
            reason = f"+{total_return*100:.1f}% (24h)"
        elif total_return > -0.05:
            score = 0.5
            signal = "neutral"
            reason = f"{total_return*100:.1f}% (24h)"
        elif total_return > -0.15:
            score = 0.3
            signal = "bearish"
            reason = f"{total_return*100:.1f}% (24h)"
        else:
            score = 0.1
            signal = "strong_bearish"
            reason = f"{total_return*100:.1f}% (24h)"
        
        return {
            "score": score,
            "signal": signal,
            "reason": reason,
            "total_return": total_return,
            "recent_return": recent_return
        }
    
    def calculate_volatility(self, prices: List[Dict]) -> Dict:
        """Calculate price volatility."""
        if len(prices) < 5:
            return {"score": 0.5, "volatility": 0, "risk": "unknown"}
        
        # Calculate returns
        returns = []
        for i in range(1, len(prices)):
            prev_price = float(prices[i-1].get("price", 0))
            curr_price = float(prices[i].get("price", 0))
            
            if prev_price > 0:
                ret = (curr_price - prev_price) / prev_price
                returns.append(ret)
        
        if not returns:
            return {"score": 0.5, "volatility": 0, "risk": "unknown"}
        
        # Calculate standard deviation
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5
        
        # Annualized volatility (approximate)
        annualized_vol = volatility * (365 ** 0.5)
        
        # Score based on volatility (lower is better for risk management)
        if annualized_vol > 2.0:
            score = 0.2
            risk = "extreme"
            reason = f"Very high volatility: {annualized_vol*100:.0f}%"
        elif annualized_vol > 1.0:
            score = 0.4
            risk = "high"
            reason = f"High volatility: {annualized_vol*100:.0f}%"
        elif annualized_vol > 0.5:
            score = 0.6
            risk = "medium"
            reason = f"Moderate volatility: {annualized_vol*100:.0f}%"
        else:
            score = 0.8
            risk = "low"
            reason = f"Low volatility: {annualized_vol*100:.0f}%"
        
        return {
            "score": score,
            "volatility": annualized_vol,
            "risk": risk,
            "reason": reason
        }
    
    def calculate_volume_trend(self, prices: List[Dict]) -> Dict:
        """Analyze volume trends."""
        if len(prices) < 5:
            return {"score": 0.5, "signal": "neutral", "reason": "Insufficient data"}
        
        # Extract volumes
        volumes = [float(p.get("volume", 0)) for p in prices]
        
        if not volumes or max(volumes) == 0:
            return {"score": 0.5, "signal": "neutral", "reason": "No volume data"}
        
        # Compare recent vs earlier volume
        split_point = len(volumes) // 2
        early_vol = sum(volumes[:split_point]) / split_point
        recent_vol = sum(volumes[split_point:]) / (len(volumes) - split_point)
        
        if early_vol == 0:
            return {"score": 0.5, "signal": "neutral", "reason": "Invalid volume data"}
        
        volume_change = (recent_vol - early_vol) / early_vol
        
        # Score based on volume trend
        if volume_change > 0.5:
            score = 0.8
            signal = "increasing"
            reason = f"Volume up {volume_change*100:.0f}%"
        elif volume_change > 0.2:
            score = 0.7
            signal = "rising"
            reason = f"Volume up {volume_change*100:.0f}%"
        elif volume_change > -0.2:
            score = 0.5
            signal = "stable"
            reason = "Stable volume"
        else:
            score = 0.3
            signal = "declining"
            reason = f"Volume down {-volume_change*100:.0f}%"
        
        return {
            "score": score,
            "signal": signal,
            "reason": reason,
            "volume_change": volume_change,
            "avg_volume": (early_vol + recent_vol) / 2
        }
    
    def analyze_token(self, token_address: str, chain: str) -> Dict:
        """Complete technical analysis of a token."""
        print(f"Analyzing {token_address}...", file=sys.stderr)
        
        # Get price history
        prices = self.get_price_history(token_address, chain, hours=24)
        
        if not prices:
            return {
                "token_address": token_address,
                "chain": chain,
                "total_score": 0.0,
                "signal": "no_data",
                "reason": "Unable to fetch price data"
            }
        
        # Calculate indicators
        momentum = self.calculate_momentum(prices)
        volatility = self.calculate_volatility(prices)
        volume = self.calculate_volume_trend(prices)
        
        # Combined score (weighted)
        total_score = (
            momentum["score"] * 0.5 +
            volatility["score"] * 0.3 +
            volume["score"] * 0.2
        )
        
        return {
            "token_address": token_address,
            "chain": chain,
            "total_score": total_score,
            "momentum": momentum,
            "volatility": volatility,
            "volume": volume,
            "timestamp": datetime.now()
        }
    
    def save_analysis(self, analysis: Dict):
        """Save technical analysis to database."""
        cur = self.conn.cursor()
        
        cur.execute("""
            INSERT INTO signals (
                source, token_address, chain, signal_score, raw_data, timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "technical",
            analysis["token_address"],
            analysis["chain"],
            analysis["total_score"],
            json.dumps(analysis),
            datetime.now()
        ))
        
        self.conn.commit()
        cur.close()
    
    def monitor_tokens(self, tokens: List[Dict]):
        """Monitor multiple tokens."""
        print(f"=== Technical Indicators Monitor - {datetime.now().isoformat()} ===")
        
        results = []
        for token in tokens:
            token_addr = token["token_address"]
            chain = token.get("chain", "solana")
            
            analysis = self.analyze_token(token_addr, chain)
            results.append(analysis)
            
            # Save to database
            if analysis["total_score"] > 0:
                self.save_analysis(analysis)
        
        print(f"Analyzed {len(results)} tokens")
        return results


def main():
    monitor = TechnicalIndicators()
    
    # Get tokens from recent signals
    cur = monitor.conn.cursor()
    
    since = datetime.now() - timedelta(hours=2)
    cur.execute("""
        SELECT DISTINCT token_address, chain
        FROM signals
        WHERE timestamp >= %s
        LIMIT 20
    """, (since,))
    
    tokens = [{"token_address": row[0], "chain": row[1]} for row in cur.fetchall()]
    cur.close()
    
    if tokens:
        monitor.monitor_tokens(tokens)
    else:
        print("No tokens to analyze")


if __name__ == "__main__":
    main()
