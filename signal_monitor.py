#!/usr/bin/env python3
"""
Signal Monitor - Collect signals from multiple sources
Based on Jim Simons' multi-source data fusion approach
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


def run_json(args: List[str]) -> Optional[Dict]:
    """Execute command and return JSON output."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            print(f"Command failed: {' '.join(args)}", file=sys.stderr)
            print(f"Error: {p.stderr[:200]}", file=sys.stderr)
            return None
        return json.loads(p.stdout)
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)
        return None


def fetch_smart_money_signals(chain: str = "solana", min_amount: int = 100) -> List[Dict]:
    """Fetch Smart Money signals from onchainos."""
    print(f"Fetching Smart Money signals for {chain} (min ${min_amount})...")
    
    data = run_json([
        "onchainos", "signal", "list",
        "--chain", chain,
        "--wallet-type", "1",  # Smart Money
        "--min-amount-usd", str(min_amount)
    ])
    
    if not data or not data.get("ok"):
        return []
    
    signals = []
    for sig in data.get("data", []):
        token = sig.get("token", {})
        signals.append({
            "source": "smart_money",
            "token_symbol": token.get("symbol", ""),
            "token_address": token.get("tokenAddress", ""),
            "chain": chain,
            "amount_usd": float(sig.get("amountUsd", 0)),
            "wallet_count": int(sig.get("triggerWalletCount", 0)),
            "timestamp": sig.get("timestamp", ""),
            "raw_data": sig
        })
    
    print(f"  Found {len(signals)} Smart Money signals")
    return signals


def calculate_signal_score(signal: Dict) -> float:
    """Calculate signal score based on multiple factors."""
    source = signal["source"]
    
    if source == "smart_money":
        # Smart Money scoring
        amount_score = min(signal.get("amount_usd", 0) / 10000, 1.0) * 0.4
        wallet_score = min(signal.get("wallet_count", 0) / 10, 1.0) * 0.3
        # TODO: Add historical win rate when available
        base_score = 0.3
        return amount_score + wallet_score + base_score
    
    elif source == "kol":
        # KOL scoring (higher base score due to influence)
        amount_score = min(signal.get("amount_usd", 0) / 5000, 1.0) * 0.3
        wallet_score = min(signal.get("wallet_count", 0) / 5, 1.0) * 0.3
        base_score = 0.4  # KOLs have higher influence
        return amount_score + wallet_score + base_score
    
    elif source == "whale":
        # Whale scoring (focus on amount)
        amount_score = min(signal.get("amount_usd", 0) / 50000, 1.0) * 0.5
        wallet_score = min(signal.get("wallet_count", 0) / 3, 1.0) * 0.2
        base_score = 0.3
        return amount_score + wallet_score + base_score
    
    elif source == "twitter":
        # Twitter scoring (placeholder)
        return 0.5
    
    elif source == "news":
        # News scoring (placeholder)
        return 0.5
    
    return 0.0


def store_signals(signals: List[Dict]):
    """Store signals in database."""
    if not signals:
        return
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    for sig in signals:
        score = calculate_signal_score(sig)
        
        cur.execute("""
            INSERT INTO signals (source, token_symbol, token_address, chain, signal_score, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            sig["source"],
            sig["token_symbol"],
            sig["token_address"],
            sig["chain"],
            score,
            json.dumps(sig.get("raw_data", {}))
        ))
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Stored {len(signals)} signals in database")


def fetch_kol_signals(chain: str = "solana") -> List[Dict]:
    """Fetch KOL signals from onchainos."""
    print(f"Fetching KOL signals for {chain}...")
    
    data = run_json([
        "onchainos", "signal", "list",
        "--chain", chain,
        "--wallet-type", "2"  # KOL
    ])
    
    if not data or not data.get("ok"):
        return []
    
    signals = []
    for sig in data.get("data", []):
        token = sig.get("token", {})
        signals.append({
            "source": "kol",
            "token_symbol": token.get("symbol", ""),
            "token_address": token.get("tokenAddress", ""),
            "chain": chain,
            "amount_usd": float(sig.get("amountUsd", 0)),
            "wallet_count": int(sig.get("triggerWalletCount", 0)),
            "timestamp": sig.get("timestamp", ""),
            "raw_data": sig
        })
    
    print(f"  Found {len(signals)} KOL signals")
    return signals


def fetch_whale_signals(chain: str = "solana") -> List[Dict]:
    """Fetch Whale signals from onchainos."""
    print(f"Fetching Whale signals for {chain}...")
    
    data = run_json([
        "onchainos", "signal", "list",
        "--chain", chain,
        "--wallet-type", "3"  # Whale
    ])
    
    if not data or not data.get("ok"):
        return []
    
    signals = []
    for sig in data.get("data", []):
        token = sig.get("token", {})
        signals.append({
            "source": "whale",
            "token_symbol": token.get("symbol", ""),
            "token_address": token.get("tokenAddress", ""),
            "chain": chain,
            "amount_usd": float(sig.get("amountUsd", 0)),
            "wallet_count": int(sig.get("triggerWalletCount", 0)),
            "timestamp": sig.get("timestamp", ""),
            "raw_data": sig
        })
    
    print(f"  Found {len(signals)} Whale signals")
    return signals


def main():
    print(f"=== Signal Monitor - {datetime.now().isoformat()} ===")
    
    # Fetch signals from all sources
    all_signals = []
    
    # 1. Solana signals
    sm_signals_sol = fetch_smart_money_signals("solana", min_amount=100)
    all_signals.extend(sm_signals_sol)
    
    kol_signals_sol = fetch_kol_signals("solana")
    all_signals.extend(kol_signals_sol)
    
    whale_signals_sol = fetch_whale_signals("solana")
    all_signals.extend(whale_signals_sol)
    
    # 2. X Layer signals
    sm_signals_xlayer = fetch_smart_money_signals("xlayer", min_amount=100)
    all_signals.extend(sm_signals_xlayer)
    
    kol_signals_xlayer = fetch_kol_signals("xlayer")
    all_signals.extend(kol_signals_xlayer)
    
    whale_signals_xlayer = fetch_whale_signals("xlayer")
    all_signals.extend(whale_signals_xlayer)
    
    # TODO: Add Twitter signals (opentwitter skill)
    # TODO: Add News signals (opennews skill)
    
    # Store in database
    if all_signals:
        store_signals(all_signals)
        print(f"\nTotal signals collected: {len(all_signals)}")
        print(f"  Solana - Smart Money: {len(sm_signals_sol)}, KOL: {len(kol_signals_sol)}, Whale: {len(whale_signals_sol)}")
        print(f"  X Layer - Smart Money: {len(sm_signals_xlayer)}, KOL: {len(kol_signals_xlayer)}, Whale: {len(whale_signals_xlayer)}")
    else:
        print("\nNo signals collected")


if __name__ == "__main__":
    main()
