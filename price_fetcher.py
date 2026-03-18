#!/usr/bin/env python3
"""
Price Fetcher - Uses CoinGecko free API (no key required).
Rate limit: ~10-30 req/min on free tier. We batch where possible.
Falls back to onchainos CLI for tokens not on CoinGecko.
"""

import json
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Cache: symbol -> coingecko_id (populated lazily)
_SYMBOL_TO_ID: Dict[str, str] = {}
_LAST_FETCH_TIME = 0.0
_MIN_INTERVAL = 2.0  # seconds between CoinGecko calls


def _rate_limit():
    """Simple rate limiter for CoinGecko free tier."""
    global _LAST_FETCH_TIME
    elapsed = time.time() - _LAST_FETCH_TIME
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_FETCH_TIME = time.time()


def _get(path: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
    """GET from CoinGecko with rate limiting."""
    _rate_limit()
    url = f"{COINGECKO_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChainLens/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  CoinGecko error ({path}): {e}", file=sys.stderr)
        return None


def resolve_coingecko_id(symbol: str) -> Optional[str]:
    """Resolve a token symbol to a CoinGecko coin ID."""
    sym = symbol.upper()
    if sym in _SYMBOL_TO_ID:
        return _SYMBOL_TO_ID[sym]

    data = _get("/search", {"query": symbol.lower()})
    if not data:
        return None

    for coin in data.get("coins", []):
        if coin.get("symbol", "").upper() == sym:
            _SYMBOL_TO_ID[sym] = coin["id"]
            return coin["id"]
    return None


def get_price(symbol: str) -> Optional[float]:
    """Get current USD price for a token symbol."""
    cg_id = resolve_coingecko_id(symbol)
    if not cg_id:
        return _fallback_onchainos_price(symbol)

    data = _get("/simple/price", {"ids": cg_id, "vs_currencies": "usd"})
    if data and cg_id in data:
        return data[cg_id].get("usd")
    return _fallback_onchainos_price(symbol)


def get_prices_batch(symbols: List[str]) -> Dict[str, float]:
    """Batch price fetch — resolves IDs then does one call."""
    id_map = {}
    for sym in symbols:
        cg_id = resolve_coingecko_id(sym)
        if cg_id:
            id_map[cg_id] = sym

    if not id_map:
        return {}

    ids_str = ",".join(id_map.keys())
    data = _get("/simple/price", {"ids": ids_str, "vs_currencies": "usd"})
    if not data:
        return {}

    result = {}
    for cg_id, sym in id_map.items():
        if cg_id in data and "usd" in data[cg_id]:
            result[sym] = data[cg_id]["usd"]
    return result


def get_market_data(symbol: str) -> Optional[Dict]:
    """Get detailed market data: price, market_cap, volume, 24h change."""
    cg_id = resolve_coingecko_id(symbol)
    if not cg_id:
        return None

    data = _get(
        "/simple/price",
        {
            "ids": cg_id,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        },
    )
    if not data or cg_id not in data:
        return None

    d = data[cg_id]
    return {
        "price": d.get("usd", 0),
        "market_cap": d.get("usd_market_cap", 0),
        "volume_24h": d.get("usd_24h_vol", 0),
        "change_24h": d.get("usd_24h_change", 0),
    }


def get_trending() -> List[Dict]:
    """Get CoinGecko trending coins (free, no key)."""
    data = _get("/search/trending")
    if not data:
        return []
    coins = []
    for item in data.get("coins", []):
        c = item.get("item", {})
        coins.append({
            "symbol": c.get("symbol", ""),
            "name": c.get("name", ""),
            "market_cap_rank": c.get("market_cap_rank"),
            "price_btc": c.get("price_btc", 0),
        })
    return coins


def _fallback_onchainos_price(symbol: str) -> Optional[float]:
    """Fallback: try onchainos CLI for price."""
    try:
        result = subprocess.run(
            ["onchainos", "market", "price", "--symbol", symbol],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("data", {}).get("price") or data.get("data", {}).get("priceUsd") or 0) or None
    except Exception:
        pass
    return None


if __name__ == "__main__":
    # Quick self-test
    print("Testing CoinGecko price fetcher...")
    for sym in ["SOL", "ETH", "BONK"]:
        p = get_price(sym)
        print(f"  {sym}: ${p}" if p else f"  {sym}: unavailable")

    print("\nTrending coins:")
    for c in get_trending()[:5]:
        print(f"  {c['symbol']:8s} rank={c['market_cap_rank']}")
