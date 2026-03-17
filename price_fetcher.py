#!/usr/bin/env python3
"""
Price Fetcher - Get real-time token prices from onchainos
"""

import json
import subprocess
import sys
from typing import Optional


def run_json(args: list) -> Optional[dict]:
    """Execute command and return JSON output."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def get_token_price(token_address: str, chain: str) -> Optional[float]:
    """
    Get current token price in USD.
    
    Args:
        token_address: Token contract address
        chain: Chain name (solana, xlayer, ethereum, etc.)
    
    Returns:
        Price in USD, or None if failed
    """
    # Use onchainos market price
    data = run_json([
        "onchainos", "market", "price",
        "--address", token_address,
        "--chain", chain
    ])
    
    if not data or not data.get("ok"):
        return None
    
    # Extract price from response
    token_data = data.get("data", [])
    if not token_data:
        return None
    
    price_usd = token_data[0].get("priceUsd")
    if price_usd:
        return float(price_usd)
    
    return None


def get_token_info(token_address: str, chain: str) -> Optional[dict]:
    """
    Get token information including price, volume, market cap.
    
    Returns:
        Dict with token info, or None if failed
    """
    data = run_json([
        "onchainos", "market", "price",
        "--address", token_address,
        "--chain", chain
    ])
    
    if not data or not data.get("ok"):
        return None
    
    token_data = data.get("data", [])
    if not token_data:
        return None
    
    info = token_data[0]
    
    return {
        "symbol": info.get("tokenSymbol", ""),
        "price_usd": float(info.get("priceUsd", 0)),
        "price_change_24h": float(info.get("priceChange24h", 0)),
        "volume_24h": float(info.get("volume24h", 0)),
        "market_cap": float(info.get("marketCap", 0)),
        "liquidity": float(info.get("liquidity", 0))
    }


if __name__ == "__main__":
    # Test
    if len(sys.argv) < 3:
        print("Usage: python3 price_fetcher.py <token_address> <chain>")
        sys.exit(1)
    
    token_addr = sys.argv[1]
    chain = sys.argv[2]
    
    price = get_token_price(token_addr, chain)
    if price:
        print(f"Price: ${price:.8f}")
    else:
        print("Failed to fetch price")
    
    info = get_token_info(token_addr, chain)
    if info:
        print(f"Info: {json.dumps(info, indent=2)}")
