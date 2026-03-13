#!/usr/bin/env python3
"""
ChainLens Token Auditor
Performs deep due diligence on tokens using OKX OnchainOS APIs.
Generates a comprehensive risk assessment report.
"""

import sys
import json
import subprocess
from datetime import datetime

RISK_THRESHOLDS = {
    "top10_holder_high": 50,      # Top 10 holders > 50% = high concentration risk
    "top10_holder_medium": 30,    # Top 10 holders > 30% = medium risk
    "dev_holding_high": 10,       # Dev holding > 10% = high risk
    "dev_holding_medium": 5,      # Dev holding > 5% = medium risk
    "liquidity_low": 10000,       # Liquidity < $10K = very low
    "liquidity_medium": 100000,   # Liquidity < $100K = low
    "rug_pull_threshold": 1,      # Any rug pull history = red flag
    "bundler_high": 20,           # Bundler % > 20% = high risk
    "sniper_high": 15,            # Sniper % > 15% = high risk
    "fresh_wallet_high": 30,      # Fresh wallets > 30% = suspicious
}


def run_cmd(cmd):
    """Execute shell command and return parsed JSON."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return None


def get_price_info(address, chain):
    """Get detailed price and market info."""
    return run_cmd(f"onchainos token price-info {address} --chain {chain}")


def get_holders(address, chain):
    """Get top holder distribution."""
    return run_cmd(f"onchainos token holders {address} --chain {chain}")


def get_dev_info(address, chain):
    """Get developer reputation and holding info."""
    return run_cmd(f"onchainos market memepump-token-dev-info {address} --chain {chain}")


def get_token_details(address, chain):
    """Get meme pump token details including audit tags."""
    return run_cmd(f"onchainos market memepump-token-details {address} --chain {chain}")


def get_bundle_info(address, chain):
    """Get bundler/sniper analysis."""
    return run_cmd(f"onchainos market memepump-token-bundle-info {address} --chain {chain}")


def calculate_risk_score(price_data, holders_data, dev_data, details_data, bundle_data):
    """
    Calculate a composite risk score from 0 (safest) to 100 (most dangerous).
    Returns (score, risk_factors[]).
    """
    score = 0
    factors = []

    # --- Price & Market Analysis ---
    if price_data and 'data' in price_data and len(price_data['data']) > 0:
        pd = price_data['data'][0]  # Take first element
        liquidity = float(pd.get('liquidity', 0) or 0)
        
        if liquidity < RISK_THRESHOLDS["liquidity_low"]:
            score += 25
            factors.append(f"🔴 CRITICAL: Extremely low liquidity (${liquidity:,.0f})")
        elif liquidity < RISK_THRESHOLDS["liquidity_medium"]:
            score += 15
            factors.append(f"🟡 WARNING: Low liquidity (${liquidity:,.0f})")
        else:
            factors.append(f"🟢 Liquidity OK (${liquidity:,.0f})")

        # Volume analysis
        vol_24h = float(pd.get('volume24H', 0) or 0)
        if liquidity > 0 and vol_24h / liquidity > 10:
            score += 10
            factors.append(f"🟡 WARNING: Volume/Liquidity ratio abnormally high ({vol_24h/liquidity:.1f}x)")

    # --- Holder Concentration ---
    if details_data and 'data' in details_data:
        dd = details_data['data']
        if isinstance(dd, list) and len(dd) > 0:
            dd = dd[0]
        tags = dd.get('tags', {})
        
        top10 = float(tags.get('top10HoldingsPercent', 0) or 0)
        if top10 > RISK_THRESHOLDS["top10_holder_high"]:
            score += 20
            factors.append(f"🔴 CRITICAL: Top 10 holders control {top10:.1f}%")
        elif top10 > RISK_THRESHOLDS["top10_holder_medium"]:
            score += 10
            factors.append(f"🟡 WARNING: Top 10 holders control {top10:.1f}%")
        else:
            factors.append(f"🟢 Holder distribution OK (top 10: {top10:.1f}%)")

        dev_pct = float(tags.get('devHoldingsPercent', 0) or 0)
        if dev_pct > RISK_THRESHOLDS["dev_holding_high"]:
            score += 15
            factors.append(f"🔴 HIGH: Dev holds {dev_pct:.1f}%")
        elif dev_pct > RISK_THRESHOLDS["dev_holding_medium"]:
            score += 8
            factors.append(f"🟡 WARNING: Dev holds {dev_pct:.1f}%")

        insiders = float(tags.get('insidersPercent', 0) or 0)
        if insiders > 10:
            score += 10
            factors.append(f"🔴 HIGH: Insiders hold {insiders:.1f}%")

        fresh = float(tags.get('freshWalletsPercent', 0) or 0)
        if fresh > RISK_THRESHOLDS["fresh_wallet_high"]:
            score += 10
            factors.append(f"🟡 WARNING: {fresh:.1f}% fresh wallets (possible wash trading)")

        phishing = float(tags.get('suspectedPhishingWalletPercent', 0) or 0)
        if phishing > 1:
            score += 15
            factors.append(f"🔴 CRITICAL: {phishing:.1f}% suspected phishing wallets")

    # --- Developer Reputation ---
    if dev_data and 'data' in dev_data:
        dv = dev_data['data']
        if isinstance(dv, list) and len(dv) > 0:
            dv = dv[0]
        launched = dv.get('devLaunchedInfo', {})
        
        rug_pulls = int(launched.get('rugPullCount', 0) or 0)
        if rug_pulls >= RISK_THRESHOLDS["rug_pull_threshold"]:
            score += 25
            factors.append(f"🔴 CRITICAL: Developer has {rug_pulls} rug pull(s) in history!")
        
        total_tokens = int(launched.get('totalTokens', 0) or 0)
        migrated = int(launched.get('migratedCount', 0) or 0)
        golden = int(launched.get('goldenGemCount', 0) or 0)
        
        if total_tokens > 0:
            success_rate = (migrated + golden) / total_tokens * 100
            factors.append(f"📊 Dev track record: {total_tokens} tokens, {migrated} migrated, {golden} golden gems ({success_rate:.0f}% success)")
            if success_rate < 10 and total_tokens > 5:
                score += 10
                factors.append(f"🟡 WARNING: Low dev success rate")

    # --- Bundle/Sniper Analysis ---
    if bundle_data and 'data' in bundle_data:
        bd = bundle_data['data']
        if isinstance(bd, list) and len(bd) > 0:
            bd = bd[0]
        bundler_pct = float(bd.get('bundlerAthPercent', 0) or 0)
        total_bundlers = int(bd.get('totalBundlers', 0) or 0)
        
        if bundler_pct > RISK_THRESHOLDS["bundler_high"]:
            score += 15
            factors.append(f"🔴 HIGH: Bundler ATH {bundler_pct:.1f}% ({total_bundlers} bundlers)")
        elif total_bundlers > 5:
            score += 5
            factors.append(f"🟡 WARNING: {total_bundlers} bundlers detected")

    # Cap at 100
    score = min(score, 100)
    
    return score, factors


def generate_report(address, chain, price_data, holders_data, dev_data, details_data, bundle_data):
    """Generate a comprehensive audit report."""
    
    score, factors = calculate_risk_score(price_data, holders_data, dev_data, details_data, bundle_data)
    
    # Risk level
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

    report = []
    report.append("=" * 70)
    report.append("  ChainLens Token Audit Report")
    report.append(f"  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report.append("=" * 70)
    report.append("")

    # Basic Info
    if price_data and 'data' in price_data and len(price_data['data']) > 0:
        pd = price_data['data'][0]
        report.append("📋 BASIC INFORMATION")
        report.append(f"   Address: {address}")
        report.append(f"   Chain: {chain}")
        report.append(f"   Price: ${pd.get('price', 'N/A')}")
        report.append(f"   Market Cap: ${float(pd.get('marketCap', 0) or 0):,.0f}")
        report.append(f"   Liquidity: ${float(pd.get('liquidity', 0) or 0):,.0f}")
        report.append(f"   24h Volume: ${float(pd.get('volume24H', 0) or 0):,.0f}")
        report.append(f"   24h Change: {pd.get('priceChange24H', 'N/A')}%")
        report.append(f"   Holders: {pd.get('holders', 'N/A')}")
        report.append("")

    # Token Details (meme pump)
    if details_data and 'data' in details_data:
        dd = details_data['data']
        if isinstance(dd, list) and len(dd) > 0:
            dd = dd[0]
        report.append("🏷️ TOKEN DETAILS")
        report.append(f"   Name: {dd.get('name', 'N/A')} ({dd.get('symbol', 'N/A')})")
        report.append(f"   Creator: {dd.get('creatorAddress', 'N/A')}")
        report.append(f"   Bonding Curve: {dd.get('bondingPercent', 'N/A')}%")
        
        social = dd.get('social', {})
        if social:
            report.append(f"   Twitter: {social.get('x', 'N/A')}")
            report.append(f"   Telegram: {social.get('telegram', 'N/A')}")
            report.append(f"   Website: {social.get('website', 'N/A')}")
            report.append(f"   DexScreener Paid: {'Yes' if social.get('dexScreenerPaid') else 'No'}")
        report.append("")

    # Risk Score
    report.append("⚠️ RISK ASSESSMENT")
    report.append(f"   Overall Score: {score}/100")
    report.append(f"   Risk Level: {risk_level}")
    report.append(f"   Recommendation: {recommendation}")
    report.append("")
    report.append("   Risk Factors:")
    for factor in factors:
        report.append(f"   {factor}")
    report.append("")

    # Top Holders
    if holders_data and 'data' in holders_data:
        report.append("👥 TOP HOLDERS")
        for i, holder in enumerate(holders_data['data'][:10], 1):
            addr = holder.get('holderWalletAddress', 'N/A')
            amount = holder.get('holdAmount', 'N/A')
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            report.append(f"   #{i}: {short_addr} — {amount}")
        report.append("")

    # Developer Info
    if dev_data and 'data' in dev_data:
        dv = dev_data['data']
        if isinstance(dv, list) and len(dv) > 0:
            dv = dv[0]
        launched = dv.get('devLaunchedInfo', {})
        holding = dv.get('devHoldingInfo', {})
        
        report.append("👨‍💻 DEVELOPER ANALYSIS")
        report.append(f"   Total Tokens Created: {launched.get('totalTokens', 'N/A')}")
        report.append(f"   Rug Pulls: {launched.get('rugPullCount', 'N/A')}")
        report.append(f"   Migrated: {launched.get('migratedCount', 'N/A')}")
        report.append(f"   Golden Gems: {launched.get('goldenGemCount', 'N/A')}")
        
        if holding:
            report.append(f"   Dev Holding: {holding.get('devHoldingPercent', 'N/A')}%")
            dev_addr = holding.get('devAddress', 'N/A')
            if dev_addr and len(dev_addr) > 10:
                dev_addr = f"{dev_addr[:6]}...{dev_addr[-4:]}"
            report.append(f"   Dev Address: {dev_addr}")
        report.append("")

    report.append("=" * 70)
    report.append("  Powered by ChainLens × OKX OnchainOS")
    report.append("  ⚠️ This is not financial advice. Always DYOR.")
    report.append("=" * 70)

    return "\n".join(report)


def audit_token(address, chain):
    """Run full audit on a token."""
    print(f"🔍 ChainLens Auditing: {address} on {chain.upper()}")
    print(f"   Fetching data from OKX OnchainOS...\n")

    price_data = get_price_info(address, chain)
    holders_data = get_holders(address, chain)
    dev_data = get_dev_info(address, chain)
    details_data = get_token_details(address, chain)
    bundle_data = get_bundle_info(address, chain)

    report = generate_report(address, chain, price_data, holders_data, dev_data, details_data, bundle_data)
    print(report)
    
    # Save report
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"chainlens_report_{chain}_{address[:8]}_{timestamp}.md"
    with open(filename, 'w') as f:
        f.write(report)
    print(f"\n📄 Report saved to: {filename}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python token_auditor.py <address> <chain>")
        print("Example: python token_auditor.py So11111111111111111111111111111111111111112 solana")
        sys.exit(1)
    
    address = sys.argv[1]
    chain = sys.argv[2]
    audit_token(address, chain)
