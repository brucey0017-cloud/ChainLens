-- ChainLens Trading System Database Schema
-- Based on Jim Simons' quantitative trading principles
-- Version: 2.0 - Added missing fields for live trading

-- 1. Signals Table - Store all incoming signals from multiple sources
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,  -- 'smart_money', 'twitter', 'news'
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    signal_score DECIMAL(5,2),
    raw_data JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_token ON signals(token_address, chain);
CREATE INDEX IF NOT EXISTS idx_signals_processed ON signals(processed);

-- 2. Trades Table - Record all paper and real trades
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,  -- 'triple_confirmation', 'resonance', 'contrarian', 'arbitrage'
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'buy', 'sell'
    entry_price DECIMAL(20,8),
    exit_price DECIMAL(20,8),
    quantity DECIMAL(20,8),
    position_size_usd DECIMAL(12,2),
    position_size_pct DECIMAL(5,2),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    pnl_usd DECIMAL(12,2),
    pnl_pct DECIMAL(8,2),
    tx_hash TEXT,
    status TEXT DEFAULT 'open',  -- 'open', 'closed', 'stopped_out', 'paper', 'pending_approval', 'approved', 'rejected', 'failed'
    is_paper BOOLEAN DEFAULT TRUE,
    -- Signal tracking
    signal_score DECIMAL(5,2),  -- Signal confidence score that triggered this trade
    risk_score DECIMAL(5,2),    -- Token risk assessment score
    -- Approval workflow (for live trading)
    approved_at TIMESTAMPTZ,    -- When trade was approved for execution
    approved_by TEXT,           -- Who approved (manual/auto)
    -- Execution tracking
    executed_at TIMESTAMPTZ,    -- When trade was executed on-chain
    execution_error TEXT,       -- Error message if execution failed
    -- Timestamps
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_signal_score ON trades(signal_score DESC);

-- 3. Portfolio Table - Track current holdings
CREATE TABLE IF NOT EXISTS portfolio (
    id SERIAL PRIMARY KEY,
    trade_id INT REFERENCES trades(id),  -- Link to originating trade
    token_symbol TEXT NOT NULL,
    token_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    quantity DECIMAL(20,8),
    avg_entry_price DECIMAL(20,8),
    current_price DECIMAL(20,8),
    position_size_usd DECIMAL(12,2),     -- USD value at entry
    position_value_usd DECIMAL(12,2),    -- Current USD value
    unrealized_pnl_usd DECIMAL(12,2),
    unrealized_pnl_pct DECIMAL(8,2),
    stop_loss DECIMAL(20,8),             -- Stop loss price
    take_profit DECIMAL(20,8),           -- Take profit price
    status TEXT DEFAULT 'open',          -- 'open', 'closed', 'stopped_out', 'liquidated'
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token_address, chain)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio(status);
CREATE INDEX IF NOT EXISTS idx_portfolio_opened_at ON portfolio(opened_at DESC);

-- 4. Strategy Performance Table - Track strategy metrics
CREATE TABLE IF NOT EXISTS strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,
    period TEXT NOT NULL,  -- 'daily', 'weekly', 'monthly'
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    total_trades INT DEFAULT 0,
    win_trades INT DEFAULT 0,
    loss_trades INT DEFAULT 0,
    win_rate DECIMAL(5,2),
    avg_win_pct DECIMAL(8,2),
    avg_loss_pct DECIMAL(8,2),
    profit_factor DECIMAL(8,2),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown_pct DECIMAL(8,2),
    total_pnl_usd DECIMAL(12,2),
    total_pnl_pct DECIMAL(8,2),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy, period, period_start)
);

CREATE INDEX IF NOT EXISTS idx_strategy_performance ON strategy_performance(strategy, period_start DESC);

-- 5. Account State Table - Track overall account metrics
CREATE TABLE IF NOT EXISTS account_state (
    id SERIAL PRIMARY KEY,
    total_balance_usd DECIMAL(12,2),
    available_balance_usd DECIMAL(12,2),
    total_position_value_usd DECIMAL(12,2),
    total_unrealized_pnl_usd DECIMAL(12,2),
    daily_pnl_usd DECIMAL(12,2),
    daily_pnl_pct DECIMAL(8,2),
    total_pnl_usd DECIMAL(12,2),
    total_pnl_pct DECIMAL(8,2),
    max_drawdown_pct DECIMAL(8,2),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_account_state_timestamp ON account_state(timestamp DESC);

-- 6. Risk Events Table - Log risk management actions
CREATE TABLE IF NOT EXISTS risk_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,  -- 'stop_loss', 'take_profit', 'circuit_breaker', 'position_limit'
    trade_id INT REFERENCES trades(id),
    description TEXT,
    action_taken TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_events_timestamp ON risk_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_trade_id ON risk_events(trade_id);

-- 7. Backtest Results Table - Store historical backtest data
CREATE TABLE IF NOT EXISTS backtest_results (
    id SERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(12,2),
    final_capital DECIMAL(12,2),
    total_return_pct DECIMAL(8,2),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown_pct DECIMAL(8,2),
    win_rate DECIMAL(5,2),
    total_trades INT,
    config JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_results(strategy);

-- 8. Trading Configuration Table - Store strategy parameters
CREATE TABLE IF NOT EXISTS trading_config (
    id SERIAL PRIMARY KEY,
    config_key TEXT NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default configuration
INSERT INTO trading_config (config_key, config_value, description) VALUES
('strategy.triple_confirmation', '{"min_signal_score": 0.6, "min_risk_score": 60, "position_size_pct": [2, 5], "stop_loss_pct": -15, "take_profit_pct": 30}', 'Triple Confirmation strategy parameters'),
('strategy.contrarian', '{"price_drop_threshold": 0.2, "min_risk_score": 60, "position_size_pct": [1, 3], "stop_loss_pct": -10, "take_profit_pct": 25}', 'Contrarian strategy parameters'),
('risk.limits', '{"max_position_size_usd": 50, "max_total_exposure_usd": 200, "daily_loss_limit_usd": 50, "max_position_pct": 0.10}', 'Risk management limits'),
('trading.mode', '{"default": "paper", "require_approval": true}', 'Trading mode settings')
ON CONFLICT (config_key) DO NOTHING;
