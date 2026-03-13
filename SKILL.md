---
name: chainlens
description: "ChainLens - AI-powered on-chain intelligence agent on OKX OnchainOS. Aggregates market signals, audits tokens with multi-factor risk scoring, and outputs actionable research reports."
license: Apache-2.0
metadata:
  author: Bruce Team
  version: "0.1.1"
  homepage: "https://github.com/brucey0017-cloud/ChainLens"
---

# ChainLens - AI On-Chain Intelligence Agent

ChainLens provides on-chain intelligence using OKX OnchainOS APIs.

## Security Rules (must-follow)

- Never store or print private keys, seed phrases, or exchange/API secrets.
- Never paste credentials into command args, code, logs, issues, or reports.
- Use environment variables for credentials when needed.
- Redact sensitive fields before sharing outputs.

## Commands

### 1) `chainlens monitor-signals <chain> [wallet_type] [min_amount_usd]`

Monitors Smart Money, KOL, and Whale buy signals on a specified chain.

- `chain`: required, e.g. `solana`, `ethereum`, `xlayer`
- `wallet_type`: optional (`1`=Smart Money, `2`=KOL, `3`=Whale)
- `min_amount_usd`: optional minimum signal amount

Example:

```bash
chainlens monitor-signals solana 1 5000
```

### 2) `chainlens audit-token <address> --chain <chain>`

Performs deep DD audit for a token address, including market data, holder concentration, dev history, and bundle/sniper signals.

Example:

```bash
chainlens audit-token 0x123...abc --chain ethereum
```

## Data Flow

- `monitor-signals` -> `onchainos market signal-list`
- `audit-token` ->
  - `onchainos token price-info`
  - `onchainos token holders`
  - `onchainos market memepump-token-dev-info`
  - `onchainos market memepump-token-details`
  - `onchainos market memepump-token-bundle-info`

## Pre-flight Checks

Ensure `onchainos` CLI is installed and reachable before execution.

```bash
which onchainos
onchainos --version
```

## Audit Output

`audit-token` generates:

- Composite risk score (0-100)
- Risk factor breakdown
- Recommendation tier (low/medium/high/extreme)
- Markdown report file for handoff
