-- ChainLens Trading System Database Schema (SQLite version)
-- Version: 2.0 - Added missing fields for live trading

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    signal_score REAL,
    raw_data TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_token ON signals(token_address, chain);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON signals(processed);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL,
    exit_price REAL,
    quantity REAL,
    position_size_usd REAL,
    position_size_pct REAL,
    stop_loss REAL,
    take_profit REAL,
    pnl_usd REAL,
    pnl_pct REAL,
    tx_hash TEXT,
    status TEXT DEFAULT 'open',
    is_paper INTEGER DEFAULT 1,
    -- Signal tracking
    signal_score REAL,
    risk_score REAL,
    -- Approval workflow
    approved_at DATETIME,
    approved_by TEXT,
    -- Execution tracking
    executed_at DATETIME,
    execution_error TEXT,
    -- Timestamps
    opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_signal_score ON trades(signal_score DESC);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    quantity REAL,
    avg_entry_price REAL,
    current_price REAL,
    position_size_usd REAL,
    position_value_usd REAL,
    unrealized_pnl_usd REAL,
    unrealized_pnl_pct REAL,
    stop_loss REAL,
    take_profit REAL,
    status TEXT DEFAULT 'open',
    opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(token_address, chain),
    FOREIGN KEY (trade_id) REFERENCES trades(id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio(status);
CREATE INDEX IF NOT EXISTS idx_portfolio_opened_at ON portfolio(opened_at DESC);

CREATE TABLE IF NOT EXISTS strategy_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    period TEXT NOT NULL,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    total_trades INTEGER DEFAULT 0,
    win_trades INTEGER DEFAULT 0,
    loss_trades INTEGER DEFAULT 0,
    win_rate REAL,
    avg_win_pct REAL,
    avg_loss_pct REAL,
    profit_factor REAL,
    sharpe_ratio REAL,
    max_drawdown_pct REAL,
    total_pnl_usd REAL,
    total_pnl_pct REAL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy, period, period_start)
);

CREATE INDEX IF NOT EXISTS idx_strategy_performance ON strategy_performance(strategy, period_start DESC);

CREATE TABLE IF NOT EXISTS account_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_balance_usd REAL,
    available_balance_usd REAL,
    total_position_value_usd REAL,
    total_unrealized_pnl_usd REAL,
    daily_pnl_usd REAL,
    daily_pnl_pct REAL,
    total_pnl_usd REAL,
    total_pnl_pct REAL,
    max_drawdown_pct REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_account_state_timestamp ON account_state(timestamp DESC);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    trade_id INTEGER,
    description TEXT,
    action_taken TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(id)
);

CREATE INDEX IF NOT EXISTS idx_risk_events_timestamp ON risk_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_trade_id ON risk_events(trade_id);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital REAL,
    final_capital REAL,
    total_return_pct REAL,
    sharpe_ratio REAL,
    max_drawdown_pct REAL,
    win_rate REAL,
    total_trades INTEGER,
    config TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy);

CREATE TABLE IF NOT EXISTS trading_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configuration
INSERT OR IGNORE INTO trading_config (config_key, config_value, description) VALUES
('strategy.triple_confirmation', '{"min_signal_score": 0.6, "min_risk_score": 60, "position_size_pct": [2, 5], "stop_loss_pct": -15, "take_profit_pct": 30}', 'Triple Confirmation strategy parameters'),
('strategy.contrarian', '{"price_drop_threshold": 0.2, "min_risk_score": 60, "position_size_pct": [1, 3], "stop_loss_pct": -10, "take_profit_pct": 25}', 'Contrarian strategy parameters'),
('risk.limits', '{"max_position_size_usd": 50, "max_total_exposure_usd": 200, "daily_loss_limit_usd": 50, "max_position_pct": 0.10}', 'Risk management limits'),
('trading.mode', '{"default": "paper", "require_approval": true}', 'Trading mode settings');
