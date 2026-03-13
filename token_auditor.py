#!/usr/bin/env python3
"""
ChainLens Token Auditor
Performs deep due diligence on tokens using OKX OnchainOS APIs.
Generates a comprehensive risk assessment report.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

RISK_THRESHOLDS = {
    "top10_holder_high": 50,      # Top 10 holders > 50% = high concentration risk
    "top10_holder_medium": 30,    # Top 10 holders > 30% = medium risk
    "dev_holding_high": 10,       # Dev holding > 10% = high risk
    "dev_holding_medium": 5,      # Dev holding > 5% = medium risk
    "liquidity_low": 10000,       # Liquidity < $10K = very low
    "liquidity_medium": 100000,   # Liquidity < $100K = low
    "rug_pull_threshold": 1,      # Any rug pull history = red flag
    "bundler_high": 20,           # Bundler % > 20% = high risk
    "sniper_high": 15,            # Reserved for future use
    "fresh_wallet_high": 30,      # Fresh wallets > 30% = suspicious
}

CHAIN_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
ADDRESS_RE = re.compile(r"^(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,64}|[A-Za-z0-9_-]{20,128})$")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def validate_inputs(address: str, chain: str) -> None:
    if not CHAIN_RE.fullmatch(chain):
        raise ValueError("Invalid chain format. Allowed: lowercase letters/numbers/_/-, 2-32 chars.")
    if not ADDRESS_RE.fullmatch(address):
        raise ValueError("Invalid token address format.")


def run_cmd(args: list[str], timeout_sec: int = 40) -> dict[str, Any] | None:
    """Execute command safely (no shell) and return parsed JSON."""
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
        print(f"Empty output from command: {' '.join(args)}", file=sys.stderr)
        return None

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc} | command: {' '.join(args)}", file=sys.stderr)
        return None

    if not isinstance(parsed, dict):
        print("Unexpected API response format (expected object).", file=sys.stderr)
        return None

    return parsed


def extract_data_obj(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Extract payload['data'] whether object or first list item."""
    if not payload or "data" not in payload:
        return {}
    data = payload.get("data")
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    return data if isinstance(data, dict) else {}


def extract_data_list(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload or "data" not in payload:
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def get_price_info(address: str, chain: str) -> dict[str, Any] | None:
    return run_cmd(["onchainos", "token", "price-info", address, "--chain", chain])


def get_holders(address: str, chain: str) -> dict[str, Any] | None:
    return run_cmd(["onchainos", "token", "holders", address, "--chain", chain])


def get_dev_info(address: str, chain: str) -> dict[str, Any] | None:
    return run_cmd(["onchainos", "market", "memepump-token-dev-info", address, "--chain", chain])


def get_token_details(address: str, chain: str) -> dict[str, Any] | None:
    return run_cmd(["onchainos", "market", "memepump-token-details", address, "--chain", chain])


def get_bundle_info(address: str, chain: str) -> dict[str, Any] | None:
    return run_cmd(["onchainos", "market", "memepump-token-bundle-info", address, "--chain", chain])


def calculate_risk_score(
    price_data: dict[str, Any] | None,
    holders_data: dict[str, Any] | None,
    dev_data: dict[str, Any] | None,
    details_data: dict[str, Any] | None,
    bundle_data: dict[str, Any] | None,
) -> tuple[int, list[str]]:
    """
    Calculate a composite risk score from 0 (safest) to 100 (most dangerous).
    Returns (score, risk_factors[]).
    """
    del holders_data  # Reserved for future scoring extensions.

    score = 0
    factors: list[str] = []

    # --- Price & Market Analysis ---
    pd = extract_data_obj(price_data)
    if pd:
        liquidity = safe_float(pd.get("liquidity"), 0)

        if liquidity < RISK_THRESHOLDS["liquidity_low"]:
            score += 25
            factors.append(f"🔴 CRITICAL: Extremely low liquidity (${liquidity:,.0f})")
        elif liquidity < RISK_THRESHOLDS["liquidity_medium"]:
            score += 15
            factors.append(f"🟡 WARNING: Low liquidity (${liquidity:,.0f})")
        else:
            factors.append(f"🟢 Liquidity OK (${liquidity:,.0f})")

        vol_24h = safe_float(pd.get("volume24H"), 0)
        if liquidity > 0 and vol_24h / liquidity > 10:
            score += 10
            factors.append(f"🟡 WARNING: Volume/Liquidity ratio abnormally high ({vol_24h / liquidity:.1f}x)")

    # --- Holder Concentration ---
    dd = extract_data_obj(details_data)
    if dd:
        tags = dd.get("tags", {}) if isinstance(dd.get("tags"), dict) else {}

        top10 = safe_float(tags.get("top10HoldingsPercent"), 0)
        if top10 > RISK_THRESHOLDS["top10_holder_high"]:
            score += 20
            factors.append(f"🔴 CRITICAL: Top 10 holders control {top10:.1f}%")
        elif top10 > RISK_THRESHOLDS["top10_holder_medium"]:
            score += 10
            factors.append(f"🟡 WARNING: Top 10 holders control {top10:.1f}%")
        else:
            factors.append(f"🟢 Holder distribution OK (top 10: {top10:.1f}%)")

        dev_pct = safe_float(tags.get("devHoldingsPercent"), 0)
        if dev_pct > RISK_THRESHOLDS["dev_holding_high"]:
            score += 15
            factors.append(f"🔴 HIGH: Dev holds {dev_pct:.1f}%")
        elif dev_pct > RISK_THRESHOLDS["dev_holding_medium"]:
            score += 8
            factors.append(f"🟡 WARNING: Dev holds {dev_pct:.1f}%")

        insiders = safe_float(tags.get("insidersPercent"), 0)
        if insiders > 10:
            score += 10
            factors.append(f"🔴 HIGH: Insiders hold {insiders:.1f}%")

        fresh = safe_float(tags.get("freshWalletsPercent"), 0)
        if fresh > RISK_THRESHOLDS["fresh_wallet_high"]:
            score += 10
            factors.append(f"🟡 WARNING: {fresh:.1f}% fresh wallets (possible wash trading)")

        phishing = safe_float(tags.get("suspectedPhishingWalletPercent"), 0)
        if phishing > 1:
            score += 15
            factors.append(f"🔴 CRITICAL: {phishing:.1f}% suspected phishing wallets")

    # --- Developer Reputation ---
    dv = extract_data_obj(dev_data)
    if dv:
        launched = dv.get("devLaunchedInfo", {}) if isinstance(dv.get("devLaunchedInfo"), dict) else {}

        rug_pulls = safe_int(launched.get("rugPullCount"), 0)
        if rug_pulls >= RISK_THRESHOLDS["rug_pull_threshold"]:
            score += 25
            factors.append(f"🔴 CRITICAL: Developer has {rug_pulls} rug pull(s) in history!")

        total_tokens = safe_int(launched.get("totalTokens"), 0)
        migrated = safe_int(launched.get("migratedCount"), 0)
        golden = safe_int(launched.get("goldenGemCount"), 0)

        if total_tokens > 0:
            success_rate = (migrated + golden) / total_tokens * 100
            factors.append(
                f"📊 Dev track record: {total_tokens} tokens, {migrated} migrated, {golden} golden gems ({success_rate:.0f}% success)"
            )
            if success_rate < 10 and total_tokens > 5:
                score += 10
                factors.append("🟡 WARNING: Low dev success rate")

    # --- Bundle/Sniper Analysis ---
    bd = extract_data_obj(bundle_data)
    if bd:
        bundler_pct = safe_float(bd.get("bundlerAthPercent"), 0)
        total_bundlers = safe_int(bd.get("totalBundlers"), 0)

        if bundler_pct > RISK_THRESHOLDS["bundler_high"]:
            score += 15
            factors.append(f"🔴 HIGH: Bundler ATH {bundler_pct:.1f}% ({total_bundlers} bundlers)")
        elif total_bundlers > 5:
            score += 5
            factors.append(f"🟡 WARNING: {total_bundlers} bundlers detected")

    score = min(score, 100)
    return score, factors


def generate_report(
    address: str,
    chain: str,
    price_data: dict[str, Any] | None,
    holders_data: dict[str, Any] | None,
    dev_data: dict[str, Any] | None,
    details_data: dict[str, Any] | None,
    bundle_data: dict[str, Any] | None,
) -> str:
    """Generate a comprehensive audit report."""
    score, factors = calculate_risk_score(price_data, holders_data, dev_data, details_data, bundle_data)

    if score >= 70:
        risk_level = "🔴 EXTREME RISK"
        recommendation = "AVOID — Multiple critical red flags detected."
    elif score >= 50:
        risk_level = "🟠 HIGH RISK"
        recommendation = "CAUTION — Significant risks present. Only invest what you can afford to lose."
    elif score >= 30:
        risk_level = "🟡 MEDIUM RISK"
        recommendation = "MODERATE — Some concerns noted. Do additional research before investing."
    else:
        risk_level = "🟢 LOW RISK"
        recommendation = "RELATIVELY SAFE — Standard risks apply. Always DYOR."

    report: list[str] = []
    report.append("=" * 70)
    report.append("  ChainLens Token Audit Report")
    report.append(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report.append("=" * 70)
    report.append("")

    pd = extract_data_obj(price_data)
    if pd:
        report.append("📋 BASIC INFORMATION")
        report.append(f"   Address: {address}")
        report.append(f"   Chain: {chain}")
        report.append(f"   Price: ${pd.get('price', 'N/A')}")
        report.append(f"   Market Cap: ${safe_float(pd.get('marketCap'), 0):,.0f}")
        report.append(f"   Liquidity: ${safe_float(pd.get('liquidity'), 0):,.0f}")
        report.append(f"   24h Volume: ${safe_float(pd.get('volume24H'), 0):,.0f}")
        report.append(f"   24h Change: {pd.get('priceChange24H', 'N/A')}%")
        report.append(f"   Holders: {pd.get('holders', 'N/A')}")
        report.append("")

    dd = extract_data_obj(details_data)
    if dd:
        report.append("🏷️ TOKEN DETAILS")
        report.append(f"   Name: {dd.get('name', 'N/A')} ({dd.get('symbol', 'N/A')})")
        report.append(f"   Creator: {dd.get('creatorAddress', 'N/A')}")
        report.append(f"   Bonding Curve: {dd.get('bondingPercent', 'N/A')}%")

        social = dd.get("social", {}) if isinstance(dd.get("social"), dict) else {}
        if social:
            report.append(f"   Twitter: {social.get('x', 'N/A')}")
            report.append(f"   Telegram: {social.get('telegram', 'N/A')}")
            report.append(f"   Website: {social.get('website', 'N/A')}")
            report.append(f"   DexScreener Paid: {'Yes' if social.get('dexScreenerPaid') else 'No'}")
        report.append("")

    report.append("⚠️ RISK ASSESSMENT")
    report.append(f"   Overall Score: {score}/100")
    report.append(f"   Risk Level: {risk_level}")
    report.append(f"   Recommendation: {recommendation}")
    report.append("")
    report.append("   Risk Factors:")
    for factor in factors:
        report.append(f"   {factor}")
    report.append("")

    holders_list = extract_data_list(holders_data)
    if holders_list:
        report.append("👥 TOP HOLDERS")
        for i, holder in enumerate(holders_list[:10], 1):
            addr = str(holder.get("holderWalletAddress", "N/A"))
            amount = holder.get("holdAmount", "N/A")
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            report.append(f"   #{i}: {short_addr} — {amount}")
        report.append("")

    dv = extract_data_obj(dev_data)
    if dv:
        launched = dv.get("devLaunchedInfo", {}) if isinstance(dv.get("devLaunchedInfo"), dict) else {}
        holding = dv.get("devHoldingInfo", {}) if isinstance(dv.get("devHoldingInfo"), dict) else {}

        report.append("👨‍💻 DEVELOPER ANALYSIS")
        report.append(f"   Total Tokens Created: {launched.get('totalTokens', 'N/A')}")
        report.append(f"   Rug Pulls: {launched.get('rugPullCount', 'N/A')}")
        report.append(f"   Migrated: {launched.get('migratedCount', 'N/A')}")
        report.append(f"   Golden Gems: {launched.get('goldenGemCount', 'N/A')}")

        if holding:
            report.append(f"   Dev Holding: {holding.get('devHoldingPercent', 'N/A')}%")
            dev_addr = str(holding.get("devAddress", "N/A"))
            if len(dev_addr) > 10:
                dev_addr = f"{dev_addr[:6]}...{dev_addr[-4:]}"
            report.append(f"   Dev Address: {dev_addr}")
        report.append("")

    report.append("=" * 70)
    report.append("  Powered by ChainLens × OKX OnchainOS")
    report.append("  ⚠️ This is not financial advice. Always DYOR.")
    report.append("=" * 70)

    return "\n".join(report)


def audit_token(address: str, chain: str) -> int:
    """Run full audit on a token."""
    print(f"🔍 ChainLens Auditing: {address} on {chain.upper()}")
    print("   Fetching data from OKX OnchainOS...\n")

    price_data = get_price_info(address, chain)
    holders_data = get_holders(address, chain)
    dev_data = get_dev_info(address, chain)
    details_data = get_token_details(address, chain)
    bundle_data = get_bundle_info(address, chain)

    if not any([price_data, holders_data, dev_data, details_data, bundle_data]):
        print("❌ All upstream queries failed. Aborting report generation.", file=sys.stderr)
        return 1

    report = generate_report(address, chain, price_data, holders_data, dev_data, details_data, bundle_data)
    print(report)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_addr = re.sub(r"[^A-Za-z0-9]", "", address)[:12] or "token"
    filename = Path(f"chainlens_report_{chain}_{safe_addr}_{timestamp}.md")
    filename.write_text(report, encoding="utf-8")
    print(f"\n📄 Report saved to: {filename}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Perform token risk audit via OKX OnchainOS.")
    parser.add_argument("address", help="Token contract address")
    parser.add_argument("chain", help="Blockchain name, e.g. solana")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        validate_inputs(args.address, args.chain)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(audit_token(args.address, args.chain))
