---
name: chainlens
description: "ChainLens - An AI-powered on-chain intelligence agent built on OKX OnchainOS. It aggregates market signals, performs deep token due diligence (DD), assesses risks, and generates actionable research reports. Use this skill to identify alpha opportunities, audit new tokens, and get comprehensive market insights. Perfect for participating in the X Layer AI Hackathon."
license: Apache-2.0
metadata:
  author: Commander
  version: "0.1.0"
  homepage: "https://github.com/CommanderAI/ChainLens" # Placeholder
---

# ChainLens - AI On-Chain Intelligence Agent

ChainLens is designed to provide comprehensive on-chain intelligence by leveraging OKX OnchainOS capabilities.

## Commands

### 1. `chainlens monitor-signals <chain>`

Monitors Smart Money, KOL, and Whale buy signals on a specified chain.

**Parameters:**
- `<chain>`: Required. The blockchain name (e.g., `solana`, `ethereum`, `xlayer`).

**Example Usage:**
`chainlens monitor-signals solana`

### 2. `chainlens audit-token <address> --chain <chain>`

Performs a deep due diligence audit on a given token contract address, including price info, holder distribution, and developer reputation.

**Parameters:**
- `<address>`: Required. The token contract address.
- `--chain`: Required. The blockchain name.

**Example Usage:**
`chainlens audit-token 0x123...abc --chain ethereum`

## Operation Flow

### Intent Mapping

- To discover alpha signals: `chainlens monitor-signals`
- To research a specific token: `chainlens audit-token`

### Data Flow

- `monitor-signals` calls `okx-dex-market`'s `signal-list` command.
- `audit-token` calls `okx-dex-token`'s `price-info`, `holders` and `okx-dex-market`'s `memepump-token-dev-info`.

## Pre-flight Checks (inherited from OnchainOS skills)

Ensure `onchainos` CLI is installed and up-to-date.
```bash
which onchainos || curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh
curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh # Check for updates
```

## Internal Workflow for `audit-token`

1.  **Basic Info & Market Data**: Calls `onchainos token price-info <address> --chain <chain>`
2.  **Holder Distribution**: Calls `onchainos token holders <address> --chain <chain>`
3.  **Developer Reputation**: Calls `onchainos market memepump-token-dev-info <address> --chain <chain>`
4.  **AI Analysis (future)**: Integrates with Claude Code to analyze the collected data and generate a risk score/recommendation.

---
This `SKILL.md` is designed to be self-explanatory and guide the AI in utilizing its capabilities effectively.
