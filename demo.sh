#!/bin/bash
# ChainLens Trading System - Local Test Demo
# Demonstrates the complete trading pipeline

set -e

echo "=== ChainLens Trading System Demo ==="
echo ""

# Initialize database
echo "1. Initializing database..."
rm -f chainlens.db
sqlite3 chainlens.db < schema_sqlite.sql
echo "   ✓ Database created"
echo ""

# Insert test signals
echo "2. Inserting test signals..."
sqlite3 chainlens.db << 'SQL'
INSERT INTO signals (source, token_symbol, token_address, chain, signal_score, raw_data, processed)
VALUES 
  ('smart_money', 'SOL', 'So11111111111111111111111111111111111111112', 'solana', 0.75, '{"amount_usd": 5000, "wallet_count": 5}', 0),
  ('smart_money', 'BONK', '0xbonk1111111111111111111111111111111111111', 'solana', 0.68, '{"amount_usd": 3500, "wallet_count": 4}', 0),
  ('smart_money', 'JUP', '0xjup11111111111111111111111111111111111111', 'solana', 0.62, '{"amount_usd": 2800, "wallet_count": 3}', 0);
SQL
echo "   ✓ 3 test signals inserted"
echo ""

# Run signal monitor (would fetch real signals in production)
echo "3. Running signal monitor..."
python3 signal_monitor_sqlite.py
echo ""

# Run strategy engine
echo "4. Running strategy engine..."
python3 strategy_engine_sqlite.py
echo ""

# Show trades
echo "5. Current trades:"
sqlite3 chainlens.db << 'SQL'
SELECT 
  id, 
  strategy, 
  token_symbol, 
  direction,
  ROUND(position_size_pct, 1) || '%' as position,
  status
FROM trades
ORDER BY id;
SQL
echo ""

# Run position monitor
echo "6. Running position monitor..."
python3 position_monitor_sqlite.py
echo ""

# Show final state
echo "7. Final state:"
sqlite3 chainlens.db << 'SQL'
SELECT 
  token_symbol,
  status,
  CASE 
    WHEN pnl_pct IS NOT NULL THEN ROUND(pnl_pct, 2) || '%'
    ELSE 'N/A'
  END as pnl,
  notes
FROM trades
ORDER BY id;
SQL
echo ""

echo "=== Demo Complete ==="
echo ""
echo "Next steps:"
echo "  - Integrate real data sources (opentwitter, opennews)"
echo "  - Run 2-week paper trading validation"
echo "  - Deploy to GitHub Actions for automation"
echo ""
