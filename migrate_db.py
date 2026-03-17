#!/usr/bin/env python3
"""
Database Migration Script
Upgrade ChainLens database from v1.0 to v2.0

This script adds missing fields required for live trading:
- trades.signal_score, risk_score, approved_at, approved_by, executed_at, execution_error
- portfolio.trade_id, position_size_usd, stop_loss, take_profit, status, opened_at, closed_at
- trading_config table
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")

# PostgreSQL migrations
PG_MIGRATIONS = [
    # Add columns to trades table
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS signal_score DECIMAL(5,2);
    """,
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS risk_score DECIMAL(5,2);
    """,
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS approved_by TEXT;
    """,
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ;
    """,
    """
    ALTER TABLE trades 
    ADD COLUMN IF NOT EXISTS execution_error TEXT;
    """,
    # Add columns to portfolio table
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS trade_id INT REFERENCES trades(id);
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS position_size_usd DECIMAL(12,2);
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS stop_loss DECIMAL(20,8);
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS take_profit DECIMAL(20,8);
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open';
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS opened_at TIMESTAMPTZ DEFAULT NOW();
    """,
    """
    ALTER TABLE portfolio 
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
    """,
    # Create trading_config table
    """
    CREATE TABLE IF NOT EXISTS trading_config (
        id SERIAL PRIMARY KEY,
        config_key TEXT NOT NULL UNIQUE,
        config_value JSONB NOT NULL,
        description TEXT,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    # Add indexes
    """
    CREATE INDEX IF NOT EXISTS idx_trades_signal_score ON trades(signal_score DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_portfolio_opened_at ON portfolio(opened_at DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_risk_events_timestamp ON risk_events(timestamp DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_risk_events_trade_id ON risk_events(trade_id);
    """,
    # Insert default config
    """
    INSERT INTO trading_config (config_key, config_value, description) VALUES
    ('strategy.triple_confirmation', '{"min_signal_score": 0.6, "min_risk_score": 60, "position_size_pct": [2, 5], "stop_loss_pct": -15, "take_profit_pct": 30}', 'Triple Confirmation strategy parameters'),
    ('strategy.contrarian', '{"price_drop_threshold": 0.2, "min_risk_score": 60, "position_size_pct": [1, 3], "stop_loss_pct": -10, "take_profit_pct": 25}', 'Contrarian strategy parameters'),
    ('risk.limits', '{"max_position_size_usd": 50, "max_total_exposure_usd": 200, "daily_loss_limit_usd": 50, "max_position_pct": 0.10}', 'Risk management limits'),
    ('trading.mode', '{"default": "paper", "require_approval": true}', 'Trading mode settings')
    ON CONFLICT (config_key) DO NOTHING;
    """,
]

# SQLite migrations
SQLITE_MIGRATIONS = [
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we need to check first
    # These are run with error handling
]


def migrate_postgresql():
    """Run PostgreSQL migrations."""
    import psycopg2
    
    print("Running PostgreSQL migrations...")
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    success_count = 0
    error_count = 0
    
    for i, migration in enumerate(PG_MIGRATIONS, 1):
        try:
            cur.execute(migration)
            conn.commit()
            success_count += 1
            print(f"  [{i:2d}] ✓ Success")
        except Exception as e:
            error_count += 1
            print(f"  [{i:2d}] ✗ Error: {str(e)[:100]}")
            conn.rollback()
    
    cur.close()
    conn.close()
    
    print(f"\nMigration complete: {success_count} successful, {error_count} errors")
    return error_count == 0


def migrate_sqlite(db_path: str):
    """Run SQLite migrations."""
    import sqlite3
    
    print(f"Running SQLite migrations on {db_path}...")
    
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Check and add columns to trades table
    trades_columns = [
        ("signal_score", "REAL"),
        ("risk_score", "REAL"),
        ("approved_at", "DATETIME"),
        ("approved_by", "TEXT"),
        ("executed_at", "DATETIME"),
        ("execution_error", "TEXT"),
    ]
    
    for col_name, col_type in trades_columns:
        try:
            cur.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"  ✓ Added trades.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  - trades.{col_name} already exists")
            else:
                print(f"  ✗ Error adding trades.{col_name}: {e}")
    
    # Check and add columns to portfolio table
    portfolio_columns = [
        ("trade_id", "INTEGER REFERENCES trades(id)"),
        ("position_size_usd", "REAL"),
        ("stop_loss", "REAL"),
        ("take_profit", "REAL"),
        ("status", "TEXT DEFAULT 'open'"),
        ("opened_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
        ("closed_at", "DATETIME"),
    ]
    
    for col_name, col_type in portfolio_columns:
        try:
            cur.execute(f"ALTER TABLE portfolio ADD COLUMN {col_name} {col_type}")
            conn.commit()
            print(f"  ✓ Added portfolio.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  - portfolio.{col_name} already exists")
            else:
                print(f"  ✗ Error adding portfolio.{col_name}: {e}")
    
    # Create trading_config table if not exists
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trading_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_value TEXT NOT NULL,
                description TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("  ✓ Created trading_config table")
    except sqlite3.OperationalError as e:
        print(f"  - trading_config table: {e}")
    
    # Insert default config
    configs = [
        ('strategy.triple_confirmation', '{"min_signal_score": 0.6, "min_risk_score": 60, "position_size_pct": [2, 5], "stop_loss_pct": -15, "take_profit_pct": 30}', 'Triple Confirmation strategy parameters'),
        ('strategy.contrarian', '{"price_drop_threshold": 0.2, "min_risk_score": 60, "position_size_pct": [1, 3], "stop_loss_pct": -10, "take_profit_pct": 25}', 'Contrarian strategy parameters'),
        ('risk.limits', '{"max_position_size_usd": 50, "max_total_exposure_usd": 200, "daily_loss_limit_usd": 50, "max_position_pct": 0.10}', 'Risk management limits'),
        ('trading.mode', '{"default": "paper", "require_approval": true}', 'Trading mode settings'),
    ]
    
    for key, value, desc in configs:
        try:
            cur.execute(
                "INSERT OR IGNORE INTO trading_config (config_key, config_value, description) VALUES (?, ?, ?)",
                (key, value, desc)
            )
            conn.commit()
        except Exception as e:
            print(f"  ✗ Error inserting config {key}: {e}")
    
    cur.close()
    conn.close()
    
    print("\nSQLite migration complete")
    return True


def main():
    print("=" * 60)
    print("ChainLens Database Migration v1.0 → v2.0")
    print("=" * 60)
    print()
    
    if len(sys.argv) > 1:
        # SQLite mode
        db_path = sys.argv[1]
        migrate_sqlite(db_path)
    else:
        # PostgreSQL mode
        if DB_URL.startswith("postgresql://"):
            migrate_postgresql()
        else:
            print("Error: DATABASE_URL must be a PostgreSQL URL")
            print("For SQLite, run: python migrate_db.py <path/to/chainlens.db>")
            sys.exit(1)
    
    print()
    print("Next steps:")
    print("1. Verify the migration: SELECT * FROM trading_config;")
    print("2. Update any existing trades with signal_score if needed")
    print("3. Test the trading system with paper mode")


if __name__ == "__main__":
    main()
