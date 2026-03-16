#!/usr/bin/env python3
"""
Signal Monitor - SQLite version for local testing
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Use SQLite for local testing
DB_PATH = os.path.join(os.path.dirname(__file__), "chainlens.db")


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


def fetch_smart_money_signals(chain: str = "solana", min_amount: int = 1000) -> List[Dict]:
    """Fetch Smart Money signals from onchainos."""
    print(f"Fetching Smart Money signals for {chain}...")
    
    data = run_json([
        "onchainos", "signal", "list",
        "--chain", chain,
        "--wallet-type", "1",  # Smart Money
        "--min-amount-usd", str(min_amount)
    ])
    
    if not data or not data.get("ok"):
        return []
    
    signals = []
    for item in data.get("data", []):
        for sig in item.get("signalList", []):
            signals.append({
                "source": "smart_money",
                "token_symbol": sig.get("tokenSymbol", ""),
                "token_address": sig.get("tokenContractAddress", ""),
                "chain": chain,
                "amount_usd": float(sig.get("amountUsd", 0)),
                "wallet_count": int(sig.get("triggerWalletCount", 0)),
                "timestamp": sig.get("time", ""),
                "raw_data": sig
            })
    
    print(f"  Found {len(signals)} Smart Money signals")
    return signals


def calculate_signal_score(signal: Dict) -> float:
    """Calculate signal score based on multiple factors."""
    source = signal["source"]
    
    if source == "smart_money":
        amount_score = min(signal.get("amount_usd", 0) / 10000, 1.0) * 0.4
        wallet_score = min(signal.get("wallet_count", 0) / 10, 1.0) * 0.3
        base_score = 0.3
        return amount_score + wallet_score + base_score
    
    return 0.5


def store_signals(signals: List[Dict]):
    """Store signals in SQLite database."""
    if not signals:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for sig in signals:
        score = calculate_signal_score(sig)
        
        cur.execute("""
            INSERT INTO signals (source, token_symbol, token_address, chain, signal_score, raw_data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            sig["source"],
            sig["token_symbol"],
            sig["token_address"],
            sig["chain"],
            score,
            json.dumps(sig.get("raw_data", {}))
        ))
    
    conn.commit()
    conn.close()
    
    print(f"Stored {len(signals)} signals in database")


def main():
    print(f"=== Signal Monitor - {datetime.now().isoformat()} ===")
    
    all_signals = []
    
    # Fetch Smart Money signals
    sm_signals = fetch_smart_money_signals("solana", min_amount=1000)
    all_signals.extend(sm_signals)
    
    # Store in database
    if all_signals:
        store_signals(all_signals)
        print(f"\nTotal signals collected: {len(all_signals)}")
    else:
        print("\nNo signals collected")


if __name__ == "__main__":
    main()
