# ChainLens 🔍

**AI-Powered On-Chain Intelligence Agent built on OKX OnchainOS**

ChainLens is an autonomous AI agent that aggregates on-chain signals, performs deep token due diligence, and generates actionable research reports — all powered by OKX OnchainOS.

## What It Does

1. **Signal Monitoring** — Tracks Smart Money, KOL, and Whale buy signals across multiple chains
2. **Token Audit** — Deep due diligence with risk scoring (0-100) covering:
   - Liquidity depth analysis
   - Holder concentration risk
   - Developer reputation & rug pull history
   - Bundler/sniper detection
   - Fresh wallet & phishing wallet analysis
3. **Risk Assessment** — Composite risk score with actionable recommendations
4. **Report Generation** — Structured audit reports in Markdown format

## Architecture

```
User Request
    │
    ▼
┌─────────────────────┐
│   OpenClaw Agent     │  ← ChainLens SKILL.md defines behavior
│   (Claude Opus)      │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
┌────────┐ ┌────────┐
│ Signal │ │ Token  │
│Monitor │ │Auditor │
└───┬────┘ └───┬────┘
    │          │
    ▼          ▼
┌─────────────────────┐
│  OKX OnchainOS CLI  │  ← onchainos commands
│  (okx-dex-market,   │
│   okx-dex-token,    │
│   okx-dex-swap,     │
│   okx-wallet-       │
│   portfolio)        │
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  On-Chain Data       │
│  (X Layer, Solana,   │
│   Ethereum, BSC...) │
└─────────────────────┘
```

## Quick Start

### Prerequisites

- [OpenClaw](https://github.com/openclaw/openclaw) installed and configured
- OKX OnchainOS CLI (`onchainos`) installed and available in `PATH`.
  - Prefer official installation docs/managed package channels.
  - If using a script installer, review script contents before execution.

### Installation

1. Clone this repo:
   ```bash
   git clone https://github.com/brucey0017-cloud/ChainLens.git
   ```

2. Copy skill to OpenClaw skills directory:
   ```bash
   cp -r ChainLens ~/.openclaw/skills/chainlens
   ```

3. Start using with your OpenClaw agent:
   ```
   "Monitor Smart Money signals on Solana"
   "Audit token 0x123...abc on Ethereum"
   ```

### Standalone Usage

```bash
# Monitor signals
python signal_monitor.py solana
python signal_monitor.py ethereum 1 5000  # Smart Money only, min $5K

# Audit a token
python token_auditor.py <token_address> solana
```

## Signal Monitor

Monitors three types of on-chain buy signals:

| Signal Type | Description |
|---|---|
| Smart Money (1) | Wallets with consistently profitable trading history |
| KOL/Influencer (2) | Known crypto influencer wallets |
| Whale (3) | Large-balance wallets making significant moves |

### Filters

- `wallet_type` (positional, optional): signal source (`1`, `2`, `3`)
- `min_amount_usd` (positional, optional): minimum transaction amount in USD

## Token Auditor

Performs comprehensive due diligence across 8 risk dimensions:

| Dimension | Weight | Data Source |
|---|---|---|
| Liquidity Depth | High | `onchainos token price-info` |
| Holder Concentration | High | `onchainos market memepump-token-details` |
| Developer Reputation | Critical | `onchainos market memepump-token-dev-info` |
| Rug Pull History | Critical | `onchainos market memepump-token-dev-info` |
| Bundler Activity | Medium | `onchainos market memepump-token-bundle-info` |
| Fresh Wallet % | Medium | `onchainos market memepump-token-details` |
| Phishing Wallet % | High | `onchainos market memepump-token-details` |
| Volume/Liquidity Ratio | Medium | `onchainos token price-info` |

### Risk Scoring

| Score | Level | Recommendation |
|---|---|---|
| 0-29 | 🟢 LOW | Relatively safe. Standard risks apply. |
| 30-49 | 🟡 MEDIUM | Some concerns. Do additional research. |
| 50-69 | 🟠 HIGH | Significant risks. Only invest what you can lose. |
| 70-100 | 🔴 EXTREME | AVOID. Multiple critical red flags. |

## Example Report

```
======================================================================
  ChainLens Token Audit Report
  Generated: 2026-03-13 02:30:00 UTC
======================================================================

📋 BASIC INFORMATION
   Address: DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
   Chain: solana
   Price: $0.00001234
   Market Cap: $1,234,567
   Liquidity: $456,789
   24h Volume: $2,345,678
   Holders: 12,345

⚠️ RISK ASSESSMENT
   Overall Score: 35/100
   Risk Level: 🟡 MEDIUM RISK
   Recommendation: MODERATE — Some concerns noted.

   Risk Factors:
   🟢 Liquidity OK ($456,789)
   🟡 WARNING: Top 10 holders control 35.2%
   🟢 Dev has 0 rug pulls
   📊 Dev track record: 3 tokens, 2 migrated, 1 golden gem (100% success)

======================================================================
  Powered by ChainLens × OKX OnchainOS
  ⚠️ This is not financial advice. Always DYOR.
======================================================================
```

## Supported Chains

| Chain | Signal Monitor | Token Audit |
|---|---|---|
| X Layer | ✅ | ✅ |
| Solana | ✅ | ✅ |
| Ethereum | ✅ | ✅ |
| Base | ✅ | ✅ |
| BSC | ✅ | ✅ |
| Arbitrum | — | ✅ |
| Polygon | — | ✅ |

## Tech Stack

- **Agent Framework**: OpenClaw
- **AI Model**: Claude Opus 4.6
- **On-Chain Data**: OKX OnchainOS (onchainos CLI)
- **Language**: Python 3
- **Output**: Markdown reports

## Live Dashboard (Free)

A static dashboard is now included and deployable for free via GitHub Pages:

- URL (after Pages build): `https://brucey0017-cloud.github.io/ChainLens/`
- Source: `docs/index.html`
- Live data JSON: `docs/data/latest.json`
- Auto-refresh: `.github/workflows/dashboard-data.yml` (every 30 minutes)

## Real-time / Push Plans (Free-first)

1. **GitHub Pages + GitHub Actions (already implemented)**
   - Cost: **$0**
   - User action: only GitHub account verification
   - Best for: low-maintenance public dashboard + periodic updates

2. **Cloudflare Pages + Worker + Telegram Bot push**
   - Cost: **$0** (free tier)
   - User action: one-time Cloudflare login + Telegram bot token
   - Best for: near real-time push alerts and API proxying

3. **Railway/Render free backend + SSE/WebSocket + static frontend**
   - Cost: **$0** (free tier limits)
   - User action: one-time platform auth
   - Best for: full realtime UX, more moving parts

## Roadmap

- [x] Signal monitoring (Smart Money / KOL / Whale)
- [x] Token audit with risk scoring
- [x] Structured report generation
- [ ] Real-time alert system (WebSocket integration)
- [ ] Cross-chain correlation analysis
- [ ] Historical signal backtesting
- [ ] X Layer native deployment for Hackathon
- [ ] Web dashboard

## License

Apache-2.0

## Disclaimer

ChainLens is an informational tool only. It does not constitute financial advice. Always do your own research (DYOR) before making any investment decisions. The risk scores and recommendations are algorithmic assessments and may not capture all relevant factors.

---

Built with ❤️ using [OpenClaw](https://github.com/openclaw/openclaw) × [OKX OnchainOS](https://web3.okx.com)
