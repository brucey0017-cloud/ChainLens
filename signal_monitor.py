#!/usr/bin/env python3
"""
ChainLens Signal Monitor
Monitors Smart Money, KOL, and Whale buy signals on specified chains.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

CHAIN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def run_onchainos_command(args: list[str], timeout_sec: int = 30) -> dict[str, Any] | None:
    """Execute onchainos CLI command and return parsed JSON output."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        print(f"Command timed out after {timeout_sec}s: {' '.join(args)}", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as exc:
        print(f"Command failed: {' '.join(args)}", file=sys.stderr)
        stderr = (exc.stderr or "").strip()
        if stderr:
            print(f"stderr: {stderr}", file=sys.stderr)
        return None

    stdout = (result.stdout or "").strip()
    if not stdout:
        print("Command returned empty output.", file=sys.stderr)
        return None

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc}", file=sys.stderr)
        return None

    if not isinstance(parsed, dict):
        print("Unexpected response format (expected JSON object).", file=sys.stderr)
        return None

    return parsed


def format_timestamp_ms(value: Any) -> str:
    """Format millisecond timestamp safely."""
    try:
        ts_ms = int(float(value))
        if ts_ms <= 0:
            return "N/A"
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return "N/A"


def monitor_signals(chain: str, wallet_type: int | None = None, min_amount_usd: float | None = None) -> None:
    """Monitor buy signals on a specified chain."""
    if not CHAIN_RE.fullmatch(chain):
        raise ValueError("Invalid chain format. Allowed: lowercase letters/numbers/_/-, 2-32 chars.")

    cmd = ["onchainos", "market", "signal-list", chain]
    if wallet_type is not None:
        cmd.extend(["--wallet-type", str(wallet_type)])
    if min_amount_usd is not None:
        if min_amount_usd <= 0:
            raise ValueError("min_amount_usd must be > 0")
        cmd.extend(["--min-amount-usd", str(min_amount_usd)])

    print(f"🔍 Monitoring signals on {chain.upper()}...")

    data = run_onchainos_command(cmd)
    if not data or "data" not in data:
        print("❌ No signal data received.")
        return

    signals = data.get("data")
    if not isinstance(signals, list):
        print("❌ Unexpected signal payload format.")
        return

    if not signals:
        print("✅ No signals found matching the criteria.")
        return

    print(f"📊 Found {len(signals)} signal(s):\n")

    for idx, signal in enumerate(signals, 1):
        if not isinstance(signal, dict):
            continue
        token = signal.get("token", {}) if isinstance(signal.get("token"), dict) else {}

        print(f"{'=' * 60}")
        print(f"Signal #{idx}")
        print(f"{'=' * 60}")
        print(f"🪙 Token: {token.get('symbol', 'N/A')} ({token.get('name', 'N/A')})")
        print(f"📍 Address: {token.get('tokenAddress', 'N/A')}")
        print(f"💰 Price: ${signal.get('price', 'N/A')}")
        print(f"📈 Market Cap: ${token.get('marketCapUsd', 'N/A')}")
        print(f"💧 Liquidity: ${token.get('liquidityUsd', 'N/A')}")
        print(f"👥 Holders: {token.get('holders', 'N/A')}")
        print(f"🏆 Top 10 Holder %: {token.get('top10HolderPercent', 'N/A')}%")
        print("\n🎯 Signal Details:")
        print(f"   Type: {signal.get('walletType', 'N/A')}")
        print(f"   Trigger Wallets: {signal.get('triggerWalletCount', 'N/A')}")
        print(f"   Amount (USD): ${signal.get('amountUsd', 'N/A')}")
        print(f"   Sold Ratio: {signal.get('soldRatioPercent', 'N/A')}%")
        print(f"   Timestamp: {format_timestamp_ms(signal.get('timestamp'))}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor Smart Money/KOL/Whale buy signals.")
    parser.add_argument("chain", help="Blockchain name, e.g. solana")
    parser.add_argument(
        "wallet_type",
        nargs="?",
        type=int,
        choices=[1, 2, 3],
        help="1=Smart Money, 2=KOL, 3=Whale",
    )
    parser.add_argument(
        "min_amount_usd",
        nargs="?",
        type=float,
        help="Optional minimum transaction amount in USD (>0)",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        monitor_signals(args.chain, args.wallet_type, args.min_amount_usd)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(2)
