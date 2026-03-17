#!/bin/bash
# Phase 2 Pre-flight Check
# Run this before starting live trading

set -e

echo "=== ChainLens Phase 2 Pre-flight Check ==="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 1. Check Python dependencies
echo "1. Checking Python dependencies..."
if python3 -c "import psycopg2, web3, eth_account" 2>/dev/null; then
    check_pass "Python dependencies installed"
else
    check_fail "Missing Python dependencies. Run: pip install psycopg2-binary web3 eth-account"
fi

# 2. Check onchainos CLI
echo ""
echo "2. Checking onchainos CLI..."
if command -v onchainos &> /dev/null; then
    VERSION=$(onchainos --version 2>&1 | head -1)
    check_pass "onchainos CLI installed: $VERSION"
else
    check_fail "onchainos CLI not found. Install from: https://github.com/okx/onchainos-skills"
fi

# 3. Check .env file
echo ""
echo "3. Checking .env configuration..."
if [ -f .env ]; then
    check_pass ".env file exists"
    
    # Check required variables
    if grep -q "DATABASE_URL=" .env; then
        check_pass "DATABASE_URL configured"
    else
        check_fail "DATABASE_URL not set in .env"
    fi
    
    if grep -q "TRADING_MODE=" .env; then
        MODE=$(grep "TRADING_MODE=" .env | cut -d'=' -f2)
        if [ "$MODE" = "paper" ]; then
            check_pass "TRADING_MODE=paper (safe for testing)"
        elif [ "$MODE" = "live" ]; then
            check_warn "TRADING_MODE=live (REAL MONEY!)"
        fi
    else
        check_pass "TRADING_MODE not set (defaults to paper)"
    fi
    
    if grep -q "WALLET_PRIVATE_KEY=" .env; then
        if grep -q "WALLET_PRIVATE_KEY=0x" .env; then
            check_warn "WALLET_PRIVATE_KEY configured (keep it secret!)"
        else
            check_fail "WALLET_PRIVATE_KEY is empty"
        fi
    else
        check_warn "WALLET_PRIVATE_KEY not set (required for live trading)"
    fi
    
    if grep -q "WALLET_ADDRESS=" .env; then
        check_pass "WALLET_ADDRESS configured"
    else
        check_warn "WALLET_ADDRESS not set (required for live trading)"
    fi
else
    check_fail ".env file not found. Copy from .env.example"
fi

# 4. Check database connection
echo ""
echo "4. Checking database connection..."
if python3 -c "import os; import psycopg2; from dotenv import load_dotenv; load_dotenv(); psycopg2.connect(os.getenv('DATABASE_URL'))" 2>/dev/null; then
    check_pass "Database connection successful"
else
    check_fail "Cannot connect to database"
fi

# 5. Check paper trading results
echo ""
echo "5. Checking paper trading results..."
PAPER_TRADES=$(python3 -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM trades WHERE is_paper = TRUE')
print(cur.fetchone()[0])
" 2>/dev/null || echo "0")

if [ "$PAPER_TRADES" -gt 30 ]; then
    check_pass "Paper trading: $PAPER_TRADES trades (>30 required)"
else
    check_warn "Paper trading: $PAPER_TRADES trades (<30, need more data)"
fi

# Calculate win rate
WIN_RATE=$(python3 -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute(\"\"\"
    SELECT 
        COUNT(*) FILTER (WHERE pnl_pct > 0) * 100.0 / NULLIF(COUNT(*), 0)
    FROM trades 
    WHERE is_paper = TRUE AND status = 'closed'
\"\"\")
result = cur.fetchone()[0]
print(f'{result:.1f}' if result else '0.0')
" 2>/dev/null || echo "0.0")

if (( $(echo "$WIN_RATE >= 55" | bc -l) )); then
    check_pass "Win rate: ${WIN_RATE}% (>55% required)"
else
    check_warn "Win rate: ${WIN_RATE}% (<55%, need improvement)"
fi

# 6. Check safety limits
echo ""
echo "6. Checking safety limits..."
if python3 -c "from live_trading_manager import LiveTradingManager; m = LiveTradingManager(); print(m.check_safety_limits())" 2>/dev/null; then
    check_pass "Safety limits module working"
else
    check_fail "Safety limits module error"
fi

# 7. Check wallet balance (if configured)
echo ""
echo "7. Checking wallet balance..."
if grep -q "WALLET_ADDRESS=0x" .env 2>/dev/null; then
    WALLET_ADDR=$(grep "WALLET_ADDRESS=" .env | cut -d'=' -f2)
    echo "   Wallet: $WALLET_ADDR"
    check_warn "Manual check required: Ensure wallet has $200 USDT + $20 gas"
else
    check_warn "Wallet not configured (skip for paper trading)"
fi

# Summary
echo ""
echo "==================================="
echo "Summary:"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    if [ "$WIN_RATE" != "0.0" ] && (( $(echo "$WIN_RATE >= 55" | bc -l) )) && [ "$PAPER_TRADES" -gt 30 ]; then
        echo -e "${GREEN}✓ Ready for Phase 2 live trading!${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Review PHASE2.md"
        echo "  2. Set TRADING_MODE=live in .env"
        echo "  3. Fund wallet with $220 ($200 capital + $20 gas)"
        echo "  4. Run: python3 live_trading_manager.py list"
        echo "  5. Approve trades manually"
        echo "  6. Run: python3 live_trading_manager.py execute"
    else
        echo -e "${YELLOW}⚠ System ready, but need more paper trading data${NC}"
        echo ""
        echo "Recommendations:"
        echo "  - Run paper trading for 7+ days"
        echo "  - Collect 30+ trades"
        echo "  - Achieve 55%+ win rate"
        echo "  - Then proceed to live trading"
    fi
else
    echo -e "${RED}✗ Not ready for live trading${NC}"
    echo ""
    echo "Fix the failed checks above before proceeding."
fi

echo ""
