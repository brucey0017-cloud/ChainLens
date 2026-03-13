#!/usr/bin/env python3
"""
ChainLens Signal Monitor
Monitors Smart Money, KOL, and Whale buy signals on specified chains.
"""

import sys
import json
import subprocess
from datetime import datetime

def run_onchainos_command(cmd):
    """Execute onchainos CLI command and return parsed JSON output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        return None

def monitor_signals(chain, wallet_type=None, min_amount_usd=None):
    """
    Monitor buy signals on a specified chain.
    
    Args:
        chain: Blockchain name (e.g., 'solana', 'ethereum')
        wallet_type: Optional filter for wallet types (1=Smart Money, 2=KOL, 3=Whale)
        min_amount_usd: Optional minimum transaction amount in USD
    """
    cmd = f"onchainos market signal-list {chain}"
    
    if wallet_type:
        cmd += f" --wallet-type {wallet_type}"
    if min_amount_usd:
        cmd += f" --min-amount-usd {min_amount_usd}"
    
    print(f"🔍 Monitoring signals on {chain.upper()}...")
    print(f"Command: {cmd}\n")
    
    data = run_onchainos_command(cmd)
    
    if not data or 'data' not in data:
        print("❌ No signal data received.")
        return
    
    signals = data['data']
    
    if not signals:
        print("✅ No signals found matching the criteria.")
        return
    
    print(f"📊 Found {len(signals)} signal(s):\n")
    
    for idx, signal in enumerate(signals, 1):
        print(f"{'='*60}")
        print(f"Signal #{idx}")
        print(f"{'='*60}")
        print(f"🪙 Token: {signal.get('token', {}).get('symbol', 'N/A')} ({signal.get('token', {}).get('name', 'N/A')})")
        print(f"📍 Address: {signal.get('token', {}).get('tokenAddress', 'N/A')}")
        print(f"💰 Price: ${signal.get('price', 'N/A')}")
        print(f"📈 Market Cap: ${signal.get('token', {}).get('marketCapUsd', 'N/A')}")
        print(f"💧 Liquidity: ${signal.get('token', {}).get('liquidityUsd', 'N/A')}")
        print(f"👥 Holders: {signal.get('token', {}).get('holders', 'N/A')}")
        print(f"🏆 Top 10 Holder %: {signal.get('token', {}).get('top10HolderPercent', 'N/A')}%")
        print(f"\n🎯 Signal Details:")
        print(f"   Type: {signal.get('walletType', 'N/A')}")
        print(f"   Trigger Wallets: {signal.get('triggerWalletCount', 'N/A')}")
        print(f"   Amount (USD): ${signal.get('amountUsd', 'N/A')}")
        print(f"   Sold Ratio: {signal.get('soldRatioPercent', 'N/A')}%")
        print(f"   Timestamp: {datetime.fromtimestamp(int(signal.get('timestamp', 0))/1000).strftime('%Y-%m-%d %H:%M:%S')}")
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python signal_monitor.py <chain> [wallet_type] [min_amount_usd]")
        print("Example: python signal_monitor.py solana 1 5000")
        sys.exit(1)
    
    chain = sys.argv[1]
    wallet_type = sys.argv[2] if len(sys.argv) > 2 else None
    min_amount_usd = sys.argv[3] if len(sys.argv) > 3 else None
    
    monitor_signals(chain, wallet_type, min_amount_usd)
