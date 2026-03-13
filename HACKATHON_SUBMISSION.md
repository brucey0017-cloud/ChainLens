# X Layer OnchainOS AI Hackathon — Submission Draft

Form: https://forms.gle/BgBD4SuvJ7936FU97
Project: ChainLens
Repo: https://github.com/brucey0017-cloud/ChainLens

## Prefilled Answers

### Project Name / 项目名称
ChainLens

### Project Description / 项目描述 (<=300 chars)
ChainLens is an AI onchain intelligence agent built on OKX OnchainOS. It monitors Smart Money/KOL/Whale signals, audits token risk across 8 dimensions, flags rug-pull patterns, and outputs actionable research reports for faster crypto due diligence on X Layer.

### Primary Track / 主赛道
Onchain Data Analysis / 链上数据分析

### Project X (Twitter) Handle / 项目 X 账号
`@________` (official project account required)

### Personal Telegram Handle / 个人 Telegram
`@________`

### Team members & X accounts / 核心成员与X账户
- Commander (agent) — implementation lead
- Maker (agent) — code audit lead
- Human operator: @________

### Project X Post URL / 项目官方 X 推文链接
`https://x.com/________/status/________`

### Additional Demo Screenshots or Video URL / 额外演示
- Demo script: https://github.com/brucey0017-cloud/ChainLens/blob/main/DEMO.md
- Dashboard: https://brucey0017-cloud.github.io/ChainLens/
- Repo screenshots/video: `________`

### GitHub Repository URL / 仓库链接
https://github.com/brucey0017-cloud/ChainLens

### X Layer Transaction Hash / X Layer 交易 Hash
`0x________`

(Need at least one mainnet tx hash proving real onchain activity)

### X Layer Contract or Wallet Address / 合约或钱包地址
`0x________`

### OnchainOS capabilities used / 使用的功能
- [x] Market API
- [x] Trade API (quote/swap flow support in architecture)
- [x] Wallet API (portfolio integration path)
- [ ] x402 Payments (planned)
- [ ] DApp Wallet Connect (planned)

### AI Model & Version Used / 模型版本
Claude Opus 4.6 (via OpenClaw runtime)

### Prompt Design Overview / 提示词设计概述 (<=600 chars)
ChainLens uses a structured agent prompt: detect user intent (signal discovery vs token audit), call the minimal required OnchainOS commands, normalize outputs, score risk with explicit thresholds (liquidity, holder concentration, dev rug history, bundlers, phishing wallets), and produce concise actionable reports with no key/secret exposure. The agent is constrained to read-only market intelligence flows unless explicit trade execution is requested.

### Anything else / 其他说明
- Security hardening applied (input validation, shell execution safeguards)
- GitHub Pages dashboard included with automated data refresh
- Designed for low-friction public deployment and operator-safe workflows

---

## Submission Checklist

- [ ] Official project X account set
- [ ] Official X demo post published
- [ ] Valid X Layer mainnet tx hash added
- [ ] Wallet/contract address added
- [ ] Demo video or screenshot URL added
- [ ] Form submitted
