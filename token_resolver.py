#!/usr/bin/env python3
"""
Token resolver using OKX OnchainOS token search.

Goal: normalize symbol-only signals (news/twitter) into (token_address, chain)
so multi-source aggregation can happen on a stable identity.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Dict, Optional, Tuple

# Small in-process cache for one run
_CACHE: Dict[Tuple[str, str], Optional[Dict[str, str]]] = {}

CHAIN_INDEX_TO_NAME = {
    "1": "ethereum",
    "56": "bsc",
    "137": "polygon",
    "196": "xlayer",
    "42161": "arbitrum",
    "8453": "base",
    "501": "solana",
}

DEFAULT_CHAINS = "solana,ethereum,base,bsc,arbitrum,polygon,xlayer"


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _run_search(symbol: str, chains: str) -> list:
    try:
        proc = subprocess.run(
            [
                "onchainos",
                "token",
                "search",
                "--query",
                symbol,
                "--chains",
                chains,
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if proc.returncode != 0:
            return []
        payload = json.loads(proc.stdout)
        if not payload.get("ok"):
            return []
        data = payload.get("data", [])
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"token_resolver search failed for {symbol}: {e}", file=sys.stderr)
        return []


def resolve_symbol(symbol: str, chains: str = DEFAULT_CHAINS) -> Optional[Dict[str, str]]:
    """
    Resolve symbol to best candidate token identity.

    Returns:
      {"token_symbol", "token_address", "chain"} or None.
    """
    raw = (symbol or "").strip()
    if not raw:
        return None

    normalized = raw.lstrip("$#").upper()
    key = (normalized, chains)
    if key in _CACHE:
        return _CACHE[key]

    rows = _run_search(normalized, chains)
    if not rows:
        _CACHE[key] = None
        return None

    # Keep exact symbol matches first (case-insensitive).
    exact = [
        r for r in rows
        if str(r.get("tokenSymbol", "")).upper() == normalized
           and str(r.get("tokenContractAddress", "")).strip()
    ]

    # If no exact symbol match, we reject (avoid fuzzy mis-routing).
    if not exact:
        _CACHE[key] = None
        return None

    def rank(row: dict):
        tag = row.get("tagList") or {}
        recognized = 1 if bool(tag.get("communityRecognized")) else 0
        market_cap = _safe_float(row.get("marketCap"), 0.0)
        liquidity = _safe_float(row.get("liquidity"), 0.0)

        # Prefer chain by priority (solana first for this strategy)
        chain_name = CHAIN_INDEX_TO_NAME.get(str(row.get("chainIndex", "")), "")
        chain_priority = {
            "solana": 7,
            "xlayer": 6,
            "ethereum": 5,
            "base": 4,
            "bsc": 3,
            "arbitrum": 2,
            "polygon": 1,
        }.get(chain_name, 0)

        return (recognized, chain_priority, market_cap, liquidity)

    best = sorted(exact, key=rank, reverse=True)[0]
    chain = CHAIN_INDEX_TO_NAME.get(str(best.get("chainIndex", "")), "unknown")

    result = {
        "token_symbol": str(best.get("tokenSymbol") or normalized).upper(),
        "token_address": str(best.get("tokenContractAddress", "")).strip(),
        "chain": chain,
    }

    if not result["token_address"] or result["chain"] == "unknown":
        _CACHE[key] = None
        return None

    _CACHE[key] = result
    return result
