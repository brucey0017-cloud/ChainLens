# Phase 2: Small Capital Live Trading

**Status:** Ready for deployment
**Start Date:** 2026-03-17
**Initial Capital:** $200 USD
**Risk Level:** Conservative

---

## Safety Limits

### Position Limits
- **Max position size:** $50 per trade
- **Max total exposure:** $200 (all positions combined)
- **Max open positions:** 10 concurrent trades

### Risk Limits
- **Daily loss limit:** $50 (circuit breaker)
- **Weekly loss limit:** $100 (reduce positions)
- **Stop loss:** -15% per position
- **Take profit:** +30% or 72h hold

### Signal Quality
- **Min signal score:** 0.7 (higher than paper trading's 0.6)
- **Required confirmations:** 2+ sources (Smart Money + KOL/News)
- **Token risk score:** >60

---

## Approval Workflow

### 1. Signal Detection
- System monitors signals every 15 minutes
- Filters by signal score >= 0.7
- Checks safety limits

### 2. Trade Generation
- Strategy engine creates trade with status `pending_approval`
- Trade includes: token, entry price, position size, stop/take profit
- Stored in database for review

### 3. Manual Approval (Required)
```bash
# List pending trades
python3 live_trading_manager.py list

# Approve a trade
python3 live_trading_manager.py approve <trade_id>

# Reject a trade
python3 live_trading_manager.py reject <trade_id> "reason"
```

### 4. Execution
```bash
# Execute all approved trades
python3 live_trading_manager.py execute

# Dry-run mode (default)
TRADING_MODE=paper python3 live_trading_manager.py execute

# Live mode (requires wallet setup)
TRADING_MODE=live python3 live_trading_manager.py execute
```

---

## Wallet Setup

### 1. Create Trading Wallet
```bash
# Generate new wallet (recommended: use a hardware wallet or MPC)
# For testing, you can use MetaMask or any EVM wallet

# Export private key (NEVER share this!)
# Add to .env file
```

### 2. Fund Wallet
- **Initial capital:** $200 USDT/USDC on X Layer
- **Gas reserve:** $20 OKB for transaction fees
- **Total:** ~$220

### 3. Configure Environment
```bash
# Edit .env file
WALLET_PRIVATE_KEY=0x...  # Your private key (KEEP SECRET!)
WALLET_ADDRESS=0x...      # Your wallet address
TRADING_MODE=paper        # Start with paper mode

# For live trading
TRADING_MODE=live
```

---

## Monitoring

### Real-time Dashboard
- GitHub Pages: https://brucey0017-cloud.github.io/ChainLens/
- Updates every 15 minutes
- Shows: open positions, PnL, win rate, recent trades

### Daily Reports
```bash
# Generate daily report
python3 daily_report.py

# View in terminal or check GitHub Actions logs
```

### Alerts (Optional)
```bash
# Set up Discord webhook
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Set up Telegram bot
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

---

## Phase 2 Goals

### Performance Targets
- **Monthly return:** 5-10% ($10-20 profit on $200)
- **Win rate:** >55%
- **Max drawdown:** <15% ($30 loss)
- **Profit factor:** >1.5

### Duration
- **Minimum:** 30 days
- **Evaluation:** Weekly reviews
- **Graduation criteria:** 
  - 30+ trades executed
  - Win rate >55%
  - Max drawdown <15%
  - No safety limit violations

### Success Criteria
If Phase 2 succeeds:
- **Phase 3:** Increase capital to $1,000
- **Phase 4:** Increase to $5,000
- **Phase 5:** Full production ($10,000+)

---

## Emergency Procedures

### Circuit Breaker Triggers
1. **Daily loss >= $50:** Stop all trading for 24h
2. **3 consecutive losses:** Pause and review strategy
3. **Unusual price movement:** Manual intervention required

### Emergency Actions
```bash
# Close all positions immediately
python3 live_trading_manager.py emergency-close

# Pause trading
python3 live_trading_manager.py pause

# Resume trading
python3 live_trading_manager.py resume
```

---

## Checklist Before Going Live

- [ ] Paper trading results reviewed (胜率 >55%)
- [ ] Wallet created and funded ($220)
- [ ] Private key stored securely
- [ ] .env file configured
- [ ] Safety limits tested
- [ ] Approval workflow tested
- [ ] Emergency procedures understood
- [ ] Monitoring dashboard accessible
- [ ] Daily report automation working

---

## Phase 2 Timeline

**Week 1:** Paper trading validation
- Run system for 7 days
- Collect 50+ paper trades
- Verify win rate >55%

**Week 2:** Live trading preparation
- Set up wallet
- Fund with $200
- Test approval workflow

**Week 3-6:** Live trading execution
- Execute 5-10 trades per week
- Monitor daily
- Weekly performance reviews

**Week 7:** Phase 2 evaluation
- Calculate final metrics
- Decide on Phase 3 graduation

---

## Notes

- **Never invest more than you can afford to lose**
- **This is experimental software**
- **Past performance does not guarantee future results**
- **Always use stop losses**
- **Review every trade manually before approval**

---

**Last Updated:** 2026-03-17
**Status:** Ready for Phase 2 deployment
