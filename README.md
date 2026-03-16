# ChainLens Trading System

AI-driven quantitative trading system for onchain intelligence, based on Jim Simons' statistical arbitrage principles.

## 🎯 Core Philosophy

From noise to signal. From signal to profit.

ChainLens extracts weak but repeatable statistical patterns from onchain data, social media, and news sources, then executes automated trades with strict risk management.

## 🏗️ Architecture

### Data Sources
- **Smart Money Signals** - Track whale/KOL/smart money movements via OKX OnchainOS
- **Twitter Sentiment** - Monitor KOL mentions and community sentiment
- **News Events** - AI-rated crypto news with impact scoring
- **Onchain Data** - 8-dimension token risk auditing

### Trading Strategies

1. **Triple Confirmation** - Smart Money + Twitter + Risk Score > 60
   - Win rate target: >55%
   - Position size: 2-5% of capital
   - Stop-loss: -15% | Take-profit: +30%

2. **Resonance** - KOL mention + positive news within 6 hours
   - Win rate target: >60%
   - Position size: 3-7% of capital
   - Stop-loss: -12% | Take-profit: +40%

3. **Contrarian** - Price drop >20% + strong fundamentals + Smart Money buying
   - Win rate target: >50%
   - Position size: 1-3% of capital
   - Stop-loss: -10% | Take-profit: +25%

4. **Arbitrage** - DEX price spread >2% with sufficient liquidity
   - Win rate target: >90%
   - Position size: 10-20% of capital
   - No stop-loss (risk-free arbitrage)

### Risk Management

- **Position Limits:** Max 10% per trade, 40% total exposure
- **Stop-Loss:** Automatic execution at predefined levels
- **Circuit Breaker:** Halt trading if daily loss >5%
- **Kelly Criterion:** Position sizing based on win rate and risk/reward

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or use GitHub Actions service container)
- OKX OnchainOS API access

### Installation

```bash
# Clone repository
git clone https://github.com/brucey0017-cloud/ChainLens.git
cd ChainLens

# Install dependencies
pip install psycopg2-binary python-dotenv web3

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Initialize database
psql $DATABASE_URL -f schema.sql
```

### Configuration

Create `.env` file:

```bash
# Database
DATABASE_URL=postgresql://localhost/chainlens

# Trading Wallet (dedicated small-amount wallet)
WALLET_ADDRESS=0x...
WALLET_PRIVATE_KEY=0x...

# Optional: Notification channels
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### Running Locally

```bash
# Phase 1: Paper Trading (2 weeks)
python3 signal_monitor.py      # Collect signals
python3 strategy_engine.py     # Generate paper trades
python3 position_monitor.py    # Monitor positions
python3 daily_report.py        # Generate report

# Phase 2: Small-amount real trading
# Set is_paper=False in strategy_engine.py after validation
```

### GitHub Actions Automation

The system runs automatically via GitHub Actions:

- **Every 15 minutes:** Signal monitoring + strategy execution + position monitoring
- **Manual trigger:** Backtest or generate reports

See `.github/workflows/trading-system.yml`

## 📊 Dashboard

Live dashboard: https://brucey0017-cloud.github.io/ChainLens/

- Real-time signals
- Open positions
- Strategy performance
- Risk metrics

## 🧪 Phase 1: Paper Trading (Current)

**Goal:** Validate strategies with >55% win rate

**Status:**
- ✅ Database schema
- ✅ Signal monitoring (Smart Money)
- ✅ Strategy engine (Triple Confirmation, Contrarian)
- ✅ Position monitoring (stop-loss/take-profit)
- ✅ Daily reporting
- ⏳ Twitter sentiment integration
- ⏳ News event integration
- ⏳ Backtest system

**Next Steps:**
1. Integrate opentwitter skill for KOL sentiment
2. Integrate opennews skill for news events
3. Implement real price fetching from onchainos
4. Run 2-week paper trading validation
5. Analyze results and tune parameters

## 📈 Expected Performance

Based on Jim Simons' Medallion Fund principles:

- **Monthly Return:** 5-15%
- **Annual Return:** 60-180% (compounded)
- **Win Rate:** 55-65%
- **Profit Factor:** 1.5-2.5
- **Max Drawdown:** 15-25%

## ⚠️ Risk Disclaimer

This is an experimental quantitative trading system. Past performance does not guarantee future results.

**Risks:**
- Strategy failure (market structure changes)
- Black swan events (exchange hacks, regulatory crackdowns)
- Technical failures (API downtime, signing errors)
- Capital limits (strategy capacity constraints)

**Always:**
- Start with paper trading
- Use dedicated small-amount wallets
- Never risk more than you can afford to lose
- Monitor performance continuously

## 🛠️ Development

### Project Structure

```
ChainLens/
├── schema.sql              # Database schema
├── signal_monitor.py       # Collect signals from multiple sources
├── strategy_engine.py      # Execute trading strategies
├── position_monitor.py     # Monitor open positions
├── daily_report.py         # Generate performance reports
├── trade_executor.py       # Sign and broadcast transactions
├── token_auditor.py        # 8-dimension risk scoring
├── .github/workflows/      # GitHub Actions automation
└── docs/                   # Dashboard frontend
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Test with paper trading first
4. Submit a pull request

## 📚 References

- [Jim Simons & Renaissance Technologies](https://en.wikipedia.org/wiki/Renaissance_Technologies)
- [OKX OnchainOS Documentation](https://web3.okx.com/onchainos/dev-docs/home/what-is-onchainos)
- [Kelly Criterion](https://en.wikipedia.org/wiki/Kelly_criterion)
- [Quantitative Trading Strategies](https://www.quantstart.com/)

## 📝 License

Apache License 2.0 - See LICENSE file

## 🤝 Community

- GitHub Issues: [Report bugs / Request features](https://github.com/brucey0017-cloud/ChainLens/issues)
- X Layer AI Hackathon: [Project submission](https://github.com/brucey0017-cloud/ChainLens/blob/main/HACKATHON_SUBMISSION.md)

---

**Built with ❤️ by the ChainLens team**

*"The market is not predictable. But it contains small, repeatable statistical patterns. Find them, validate them, automate them, and manage risk strictly. That's the secret."* - Jim Simons (paraphrased)
