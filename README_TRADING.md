# ChainLens Trading System

AI-powered onchain intelligence and automated trading system based on Jim Simons' quantitative trading principles.

## Features

- **Multi-Source Signal Aggregation**: Smart Money, KOL, Whale tracking
- **8-Dimension Risk Scoring**: Comprehensive token safety analysis
- **Automated Trading**: Paper trading and live execution
- **Multi-Strategy Engine**: Triple Confirmation, Resonance, Contrarian, Arbitrage
- **Strict Risk Management**: Stop-loss, take-profit, position sizing
- **Real-time Dashboard**: GitHub Pages hosted
- **Automated Reporting**: Daily performance summaries

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Signal Sources                          │
├─────────────────────────────────────────────────────────────┤
│  Smart Money  │  Twitter/X  │  Crypto News  │  On-chain    │
│  (onchainos)  │ (opentwitter)│  (opennews)  │   Data       │
└────────┬────────────┬─────────────┬──────────────┬──────────┘
         │            │             │              │
         └────────────┴─────────────┴──────────────┘
                      │
         ┌────────────▼────────────┐
         │   Signal Monitor        │
         │  (signal_monitor.py)    │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │   Strategy Engine       │
         │ (strategy_engine.py)    │
         │  - Triple Confirmation  │
         │  - Resonance            │
         │  - Contrarian           │
         │  - Arbitrage            │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │   Risk Manager          │
         │  - Position Sizing      │
         │  - Stop Loss/Take Profit│
         │  - Circuit Breaker      │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │   Trade Executor        │
         │  (trade_executor.py)    │
         │  - Paper Trading        │
         │  - Live Trading         │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │   Position Monitor      │
         │ (position_monitor.py)   │
         └─────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (or SQLite for local testing)
- onchainos CLI
- web3.py

### Setup

```bash
# Clone repository
git clone https://github.com/brucey0017-cloud/ChainLens.git
cd ChainLens

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Initialize database
psql $DATABASE_URL -f schema.sql

# Test signal monitoring
python3 signal_monitor.py
```

## Usage

### Paper Trading (Recommended for testing)

```bash
# Run signal monitor
python3 signal_monitor.py

# Run strategy engine (generates paper trades)
python3 strategy_engine.py

# Monitor positions
python3 position_monitor.py

# Generate daily report
python3 daily_report.py
```

### Live Trading (Use with caution)

```bash
# Set up wallet private key in .env
WALLET_PRIVATE_KEY=0x...
WALLET_ADDRESS=0x...

# Run with live trading enabled
python3 strategy_engine.py --live
```

## Strategies

### 1. Triple Confirmation
- **Trigger**: Smart Money signal + Twitter sentiment + Risk score >60
- **Position Size**: 2-5% of account
- **Stop Loss**: -15%
- **Take Profit**: +30% or 24h hold
- **Target Win Rate**: >55%

### 2. Resonance
- **Trigger**: KOL tweet + Positive news within 6h
- **Position Size**: 3-7% of account
- **Stop Loss**: -12%
- **Take Profit**: +40% or 48h hold
- **Target Win Rate**: >60%

### 3. Contrarian
- **Trigger**: -20% price drop + Risk score >70 + No negative news + Smart Money buying
- **Position Size**: 1-3% of account
- **Stop Loss**: -10%
- **Take Profit**: +25% or 72h hold
- **Target Win Rate**: >50%

### 4. Arbitrage
- **Trigger**: >2% price difference across DEXs
- **Position Size**: 10-20% of account
- **Stop Loss**: Execution failure
- **Take Profit**: Immediate
- **Target Win Rate**: >90%

## Risk Management

- **Max Position Size**: 10% per trade
- **Max Total Exposure**: 40% of account
- **Daily Loss Limit**: -5% (circuit breaker)
- **Weekly Drawdown Limit**: -15% (reduce positions)
- **Monthly Drawdown Limit**: -25% (stop trading)

## Automation

### GitHub Actions

The system runs automatically via GitHub Actions:

- **Signal Monitoring**: Every 15 minutes
- **Position Monitoring**: Every 5 minutes
- **Daily Report**: Every day at 8 AM UTC

See `.github/workflows/trading-system.yml` for configuration.

## Database Schema

- `signals`: Incoming signals from all sources
- `trades`: All paper and live trades
- `portfolio`: Current holdings
- `strategy_performance`: Strategy metrics by period
- `account_state`: Overall account metrics
- `risk_events`: Risk management actions
- `backtest_results`: Historical backtest data

## Performance Targets

Based on Jim Simons' Medallion Fund principles:

- **Monthly Return**: 5-15%
- **Annual Return**: 60-180% (compounded)
- **Max Drawdown**: 15-25%
- **Win Rate**: 55-65%
- **Profit Factor**: 1.5-2.5

## Security

- Private keys stored in `.env` (never committed)
- All sensitive data excluded via `.gitignore`
- Paper trading by default
- Strict risk limits and circuit breakers

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

Apache 2.0

## Disclaimer

This is experimental software for educational purposes. Use at your own risk. Never invest more than you can afford to lose.

## Acknowledgments

- Inspired by Jim Simons and Renaissance Technologies
- Built on OKX OnchainOS
- Powered by OpenClaw

---

**"Don't try to predict the market. Find small, repeatable statistical patterns, verify them, automate them, and manage risk strictly."** — Jim Simons
