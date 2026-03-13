# ChainLens Demo Script

## Setup
```bash
# Install ChainLens
git clone https://github.com/brucey0017-cloud/ChainLens.git
cp -r ChainLens ~/.openclaw/skills/chainlens
```

## Demo 1: Signal Monitoring

**Scenario:** Discover what Smart Money is buying on Solana right now.

```bash
python signal_monitor.py solana 1 5000
```

**Expected Output:**
- List of tokens with Smart Money buy signals
- Minimum $5K transaction amount
- Token details: price, market cap, holders
- Signal metadata: wallet count, amount, timestamp

**Key Insight:** Found 100+ signals in real-time. Example: XPD token with 3 Smart Money wallets buying $1.2K worth.

## Demo 2: Token Audit (Safe Token)

**Scenario:** Audit a relatively safe token.

```bash
python token_auditor.py So11111111111111111111111111111111111111112 solana
```

**Expected Output:**
- Risk Score: ~20-30 (LOW RISK)
- Liquidity: High
- Developer: No rug pull history
- Holder distribution: Decentralized

## Demo 3: Token Audit (Risky Token)

**Scenario:** Audit a suspicious meme token.

```bash
python token_auditor.py 26HijyQRPisA96er6xWLh32TSMAHLvivTnmcmu7bpump solana
```

**Expected Output:**
- Risk Score: 55/100 (HIGH RISK)
- 🔴 Developer has 7 rug pulls in history
- 🟡 Low liquidity ($32K)
- 🟡 8 bundlers detected
- Recommendation: CAUTION

**Key Insight:** ChainLens automatically flags multiple red flags that would take hours to research manually.

## Demo 4: OpenClaw Integration

**Scenario:** Use ChainLens through natural language with OpenClaw agent.

```
User: "Monitor Smart Money signals on Solana"
Agent: [Calls chainlens signal_monitor.py]
Agent: "Found 100 signals. Top signal: XPD token with 3 Smart Money wallets..."

User: "Audit the XPD token"
Agent: [Calls chainlens token_auditor.py]
Agent: "Risk Score: 55/100 (HIGH RISK). Developer has 7 rug pulls..."
```

## Key Features Demonstrated

1. **Real-time Signal Aggregation** — 100+ signals in seconds
2. **Multi-dimensional Risk Scoring** — 8 risk factors analyzed
3. **Developer Reputation Tracking** — Rug pull history exposed
4. **Bundler/Sniper Detection** — Identifies suspicious wallet activity
5. **Structured Reports** — Markdown format, easy to share
6. **OpenClaw Integration** — Natural language interface

## Technical Highlights

- **Data Source:** OKX OnchainOS (onchainos CLI)
- **Chains Supported:** Solana, Ethereum, X Layer, Base, BSC
- **AI Model:** Claude Opus 4.6 (via OpenClaw)
- **Output:** Structured Markdown reports
- **Performance:** <5 seconds per audit

## Use Cases

1. **Alpha Discovery** — Find tokens before they pump
2. **Risk Assessment** — Avoid rug pulls and scams
3. **Portfolio Research** — Due diligence on holdings
4. **Market Intelligence** — Track Smart Money movements
5. **Automated Alerts** — (Future) Real-time notifications

---

**Built for X Layer AI Hackathon**
Track: Onchain Data Analysis
Prize Pool: 200,000 USDT
