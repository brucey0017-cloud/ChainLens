#!/usr/bin/env python3
"""
Technical Indicators - Price momentum, volume, volatility analysis

Uses OKX K-line data + Supabase REST.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from supabase_client import insert, is_available, select


class TechnicalIndicators:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    @staticmethod
    def _safe_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def get_price_history(self, token_address: str, chain: str, points: int = 48) -> List[Dict]:
        """Get historical kline data (1H bars)."""
        try:
            result = subprocess.run(
                [
                    "onchainos",
                    "market",
                    "kline",
                    "--address",
                    token_address,
                    "--chain",
                    chain,
                    "--bar",
                    "1H",
                    "--limit",
                    str(points),
                ],
                capture_output=True,
                text=True,
                timeout=35,
            )

            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            if not data.get("ok"):
                return []

            # API returns list of arrays: [ts, open, high, low, close, volume, quoteVol, flag]
            rows = data.get("data", [])
            out = []
            for r in rows:
                if not isinstance(r, list) or len(r) < 6:
                    continue
                out.append(
                    {
                        "timestamp": int(r[0]),
                        "price": self._safe_float(r[4], 0.0),  # close
                        "volume": self._safe_float(r[5], 0.0),
                    }
                )
            return out

        except Exception as e:
            print(f"Error fetching price history: {e}", file=sys.stderr)
            return []

    def calculate_momentum(self, prices: List[Dict]) -> Dict:
        """Calculate price momentum indicators."""
        if len(prices) < 2:
            return {"score": 0.5, "signal": "neutral", "reason": "Insufficient data"}

        prices = sorted(prices, key=lambda x: x.get("timestamp", 0))

        first_price = self._safe_float(prices[0].get("price"), 0.0)
        last_price = self._safe_float(prices[-1].get("price"), 0.0)

        if first_price <= 0:
            return {"score": 0.5, "signal": "neutral", "reason": "Invalid price data"}

        total_return = (last_price - first_price) / first_price

        split_point = int(len(prices) * 0.75)
        recent_prices = prices[split_point:]

        if len(recent_prices) >= 2:
            recent_first = self._safe_float(recent_prices[0].get("price"), 0.0)
            recent_last = self._safe_float(recent_prices[-1].get("price"), 0.0)

            if recent_first > 0:
                recent_return = (recent_last - recent_first) / recent_first
            else:
                recent_return = 0.0
        else:
            recent_return = total_return

        if total_return > 0.15 and recent_return > 0.05:
            score = 0.9
            signal = "strong_bullish"
            reason = f"+{total_return * 100:.1f}% (24h), +{recent_return * 100:.1f}% (recent)"
        elif total_return > 0.05:
            score = 0.7
            signal = "bullish"
            reason = f"+{total_return * 100:.1f}% (24h)"
        elif total_return > -0.05:
            score = 0.5
            signal = "neutral"
            reason = f"{total_return * 100:.1f}% (24h)"
        elif total_return > -0.15:
            score = 0.3
            signal = "bearish"
            reason = f"{total_return * 100:.1f}% (24h)"
        else:
            score = 0.1
            signal = "strong_bearish"
            reason = f"{total_return * 100:.1f}% (24h)"

        return {
            "score": score,
            "signal": signal,
            "reason": reason,
            "total_return": total_return,
            "recent_return": recent_return,
        }

    def calculate_volatility(self, prices: List[Dict]) -> Dict:
        """Calculate price volatility."""
        if len(prices) < 5:
            return {"score": 0.5, "volatility": 0.0, "risk": "unknown"}

        returns = []
        for i in range(1, len(prices)):
            prev_price = self._safe_float(prices[i - 1].get("price"), 0.0)
            curr_price = self._safe_float(prices[i].get("price"), 0.0)

            if prev_price > 0:
                returns.append((curr_price - prev_price) / prev_price)

        if not returns:
            return {"score": 0.5, "volatility": 0.0, "risk": "unknown"}

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5

        # Hourly bars => annualization sqrt(24*365)
        annualized_vol = volatility * ((24 * 365) ** 0.5)

        if annualized_vol > 2.0:
            score = 0.2
            risk = "extreme"
            reason = f"Very high volatility: {annualized_vol * 100:.0f}%"
        elif annualized_vol > 1.0:
            score = 0.4
            risk = "high"
            reason = f"High volatility: {annualized_vol * 100:.0f}%"
        elif annualized_vol > 0.5:
            score = 0.6
            risk = "medium"
            reason = f"Moderate volatility: {annualized_vol * 100:.0f}%"
        else:
            score = 0.8
            risk = "low"
            reason = f"Low volatility: {annualized_vol * 100:.0f}%"

        return {
            "score": score,
            "volatility": annualized_vol,
            "risk": risk,
            "reason": reason,
        }

    def calculate_volume_trend(self, prices: List[Dict]) -> Dict:
        """Analyze volume trends."""
        if len(prices) < 5:
            return {"score": 0.5, "signal": "neutral", "reason": "Insufficient data"}

        volumes = [self._safe_float(p.get("volume"), 0.0) for p in prices]

        if not volumes or max(volumes) == 0:
            return {"score": 0.5, "signal": "neutral", "reason": "No volume data"}

        split_point = len(volumes) // 2
        early_vol = sum(volumes[:split_point]) / max(split_point, 1)
        recent_vol = sum(volumes[split_point:]) / max(len(volumes) - split_point, 1)

        if early_vol == 0:
            return {"score": 0.5, "signal": "neutral", "reason": "Invalid volume data"}

        volume_change = (recent_vol - early_vol) / early_vol

        if volume_change > 0.5:
            score = 0.8
            signal = "increasing"
            reason = f"Volume up {volume_change * 100:.0f}%"
        elif volume_change > 0.2:
            score = 0.7
            signal = "rising"
            reason = f"Volume up {volume_change * 100:.0f}%"
        elif volume_change > -0.2:
            score = 0.5
            signal = "stable"
            reason = "Stable volume"
        else:
            score = 0.3
            signal = "declining"
            reason = f"Volume down {-volume_change * 100:.0f}%"

        return {
            "score": score,
            "signal": signal,
            "reason": reason,
            "volume_change": volume_change,
            "avg_volume": (early_vol + recent_vol) / 2,
        }

    def analyze_token(self, token_address: str, chain: str) -> Dict:
        """Complete technical analysis of a token."""
        print(f"Analyzing {token_address}...", file=sys.stderr)

        prices = self.get_price_history(token_address, chain, points=48)

        if not prices:
            return {
                "token_address": token_address,
                "chain": chain,
                "total_score": 0.0,
                "signal": "no_data",
                "reason": "Unable to fetch price data",
            }

        momentum = self.calculate_momentum(prices)
        volatility = self.calculate_volatility(prices)
        volume = self.calculate_volume_trend(prices)

        total_score = momentum["score"] * 0.5 + volatility["score"] * 0.3 + volume["score"] * 0.2

        return {
            "token_address": token_address,
            "chain": chain,
            "total_score": round(total_score, 3),
            "momentum": momentum,
            "volatility": volatility,
            "volume": volume,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save_analysis(self, analysis: Dict):
        """Save technical analysis to database."""
        row = {
            "source": "technical",
            "token_symbol": "",
            "token_address": analysis["token_address"],
            "chain": analysis["chain"],
            "signal_score": analysis["total_score"],
            "raw_data": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": False,
        }
        insert("signals", [row])

    def monitor_tokens(self, tokens: List[Dict]):
        """Monitor multiple tokens."""
        print(f"=== Technical Indicators Monitor - {datetime.now().isoformat()} ===")

        results = []
        for token in tokens:
            token_addr = token["token_address"]
            chain = token.get("chain", "solana")

            analysis = self.analyze_token(token_addr, chain)
            results.append(analysis)

            if analysis["total_score"] > 0:
                self.save_analysis(analysis)

        print(f"Analyzed {len(results)} tokens")
        return results


def main():
    monitor = TechnicalIndicators()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    rows = select(
        "signals",
        columns="token_address,chain,timestamp",
        filters={"timestamp": f"gte.{cutoff}"},
        order="timestamp.desc",
        limit=500,
    )

    seen = set()
    tokens = []
    for r in rows:
        addr = str(r.get("token_address", "")).strip()
        chain = str(r.get("chain", "")).strip()
        if not addr or chain == "unknown" or not chain:
            continue
        key = (addr, chain)
        if key in seen:
            continue
        seen.add(key)
        tokens.append({"token_address": addr, "chain": chain})
        if len(tokens) >= 20:
            break

    if tokens:
        monitor.monitor_tokens(tokens)
    else:
        print("No tokens to analyze")


if __name__ == "__main__":
    main()
