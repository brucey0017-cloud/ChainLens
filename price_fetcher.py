#!/usr/bin/env python3
"""
Price Fetcher

Priority:
1) OKX onchainos (address+chain, free)
2) CoinGecko free API (symbol fallback)
"""

from __future__ import annotations

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


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


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


def _run_onchainos(args: List[str], timeout: int = 20) -> Optional[Dict]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        payload = json.loads(p.stdout)
        return payload if isinstance(payload, dict) else None
    except Exception:
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


def get_price(chain: str = "", token_address: str = "", symbol: str = "") -> Optional[float]:
    """
    Get current USD price.

    Priority:
    - onchainos by (chain, token_address)
    - CoinGecko by symbol
    """
    if chain and token_address:
        p = get_okx_price(chain, token_address)
        if p and p > 0:
            return p

    if symbol:
        return _coingecko_price(symbol)

    return None


def get_okx_price(chain: str, token_address: str) -> Optional[float]:
    data = _run_onchainos(
        ["onchainos", "market", "price", "--chain", chain, "--address", token_address],
        timeout=20,
    )
    if not data or not data.get("ok"):
        return None

    rows = data.get("data", [])
    if isinstance(rows, list) and rows:
        return _safe_float(rows[0].get("price"), 0.0) or None
    if isinstance(rows, dict):
        return _safe_float(rows.get("price"), 0.0) or None
    return None


def _coingecko_price(symbol: str) -> Optional[float]:
    cg_id = resolve_coingecko_id(symbol)
    if not cg_id:
        return None

    data = _get("/simple/price", {"ids": cg_id, "vs_currencies": "usd"})
    if data and cg_id in data:
        return data[cg_id].get("usd")
    return None


def get_prices_batch(symbols: List[str]) -> Dict[str, float]:
    """Batch price fetch from CoinGecko (symbol fallback path)."""
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


def get_market_data(symbol: str = "", token_address: str = "", chain: str = "") -> Optional[Dict]:
    """
    Get detailed market data: price, market_cap, liquidity, volume, 24h change.

    Priority:
    - onchainos token price-info by (address, chain)
    - CoinGecko by symbol
    """
    if chain and token_address:
        okx = _run_onchainos(
            ["onchainos", "token", "price-info", "--chain", chain, "--address", token_address],
            timeout=25,
        )
        if okx and okx.get("ok"):
            rows = okx.get("data", [])
            row = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else None)
            if isinstance(row, dict):
                return {
                    "price": _safe_float(row.get("price"), 0.0),
                    "market_cap": _safe_float(row.get("marketCap"), 0.0),
                    "liquidity": _safe_float(row.get("liquidity"), 0.0),
                    "volume_24h": _safe_float(row.get("volume24H"), 0.0),
                    "change_24h": _safe_float(row.get("priceChange24H"), 0.0),
                }

    if not symbol:
        return None

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
        "liquidity": d.get("usd_24h_vol", 0),
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


if __name__ == "__main__":
    # Quick self-test
    print("Testing price fetcher...")
    p = get_price(chain="solana", token_address="So11111111111111111111111111111111111111112")
    print(f"  wSOL(Solana): ${p}" if p else "  wSOL(Solana): unavailable")

    for sym in ["SOL", "ETH", "BONK"]:
        p = get_price(symbol=sym)
        print(f"  {sym}: ${p}" if p else f"  {sym}: unavailable")
