#!/usr/bin/env python3
"""Build dashboard JSON data for GitHub Pages.

This script fetches live signal data from onchainos and writes docs/data/latest.json.
It is designed to run locally or in GitHub Actions.
"""

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "latest.json"


def run_json(cmd: str):
    try:
        p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except Exception:
        return None


def chain_signals(chain: str, wallet_type: str = "1", min_usd: int = 1000):
    data = run_json(f"onchainos market signal-list {chain} --wallet-type {wallet_type} --min-amount-usd {min_usd}")
    if not data or not data.get("ok"):
        return []
    return data.get("data", [])[:12]


def to_level(score: int):
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def main():
    # Pull signal snapshots from two chains
    sol = chain_signals("solana", "1", 1000)
    xlayer = chain_signals("xlayer", "3", 1000)

    merged = []
    for s in sol + xlayer:
        token = s.get("token", {})
        level = "medium"
        try:
            top10 = float(token.get("top10HolderPercent", 0) or 0)
            if top10 > 60:
                level = "high"
            elif top10 < 20:
                level = "low"
        except Exception:
            pass

        merged.append({
            "t": datetime.fromtimestamp(int(s.get("timestamp", "0")) / 1000, tz=timezone.utc).strftime("%H:%M UTC"),
            "chain": "solana" if str(s.get("chainIndex")) == "501" else ("xlayer" if str(s.get("chainIndex")) == "196" else str(s.get("chainIndex"))),
            "type": {
                "1": "Smart Money",
                "2": "KOL",
                "3": "Whale"
            }.get(str(s.get("walletType")), str(s.get("walletType"))),
            "token": token.get("symbol", "N/A"),
            "usd": f"{float(s.get('amountUsd', 0) or 0):,.0f}",
            "wallets": int(float(s.get("triggerWalletCount", 0) or 0)),
            "riskLevel": level,
            "finding": f"Top10 holders: {token.get('top10HolderPercent', 'N/A')}%"
        })

    # If live APIs are unavailable in CI (e.g., missing credentials/region limits),
    # keep the previous snapshot instead of overwriting with empty data.
    if not merged and OUT.exists():
        print("No fresh signals; keeping previous dashboard snapshot")
        return

    audits = []
    for row in merged[:6]:
        score = 50
        if row["riskLevel"] == "high":
            score = 72
        elif row["riskLevel"] == "low":
            score = 26
        audits.append({
            "token": row["token"],
            "chain": row["chain"],
            "level": to_level(score),
            "score": score,
            "finding": row["finding"]
        })

    stats = {
        "signals24h": len(merged),
        "topChain": "Solana" if len(sol) >= len(xlayer) else "X Layer",
        "avgRisk": round(sum(a["score"] for a in audits) / len(audits), 1) if audits else 0,
        "criticalAlerts": len([a for a in audits if a["score"] >= 70])
    }

    payload = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stats": stats,
        "audits": audits,
        "signals": merged[:20]
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
