# ChainLens Signal Quality Hardening Design (2026-03-18)

## Constraints (from owner)
1. 如无必要勿增实体（avoid adding new external systems unless necessary）
2. Prefer free, high-quality tools
3. Use all available automation capabilities

## Chosen approach

### 1) Replace unreliable paid/fragile sources with free reliable sources
- **News**: replace `onchainos news` calls with free RSS feeds:
  - CoinTelegraph
  - CoinDesk
  - Decrypt
  - The Block
- **Price/market cap/liquidity proxy**: replace mock/onchainos-only price logic with **CoinGecko free API**.

Why: zero key, stable, real data, good enough for Phase 1.5 signal quality validation.

### 2) Keep architecture minimal (no new external DB yet)
- Keep current PostgreSQL runtime in GitHub Actions for now (no infra expansion)
- Add **signal health report** step per run to expose real signal counts and avoid “silent success”

Why: fastest path to truth; no new paid infra.

### 3) Fix critical breakages that made metrics fake
- Fix `created_at` → `timestamp` schema mismatch in technical indicators
- Fix strategy engine to use real prices (remove hardcoded `entry_price = 1.0`)
- Remove duplicate sqlite shadow files to reduce maintenance surface

### 4) Add regression guardrails (free)
- Add CI workflow with:
  - ruff (selected core modules)
  - mypy (core typed modules)
  - compileall
  - bandit (high severity)
  - pytest
- Add tests for:
  - input validation
  - data-shape drift handling
  - report filename sanitization
  - price/news parsing logic

## Deferred (explicitly)
- Full historical backtesting engine rewrite
- External persistent DB (Neon/Supabase)
- Twitter paid API integration

Reason: out of scope for this hardening pass; these are Phase 2 items after signal integrity is validated.

## Success criteria for this pass
1. Workflow no longer reports fake “all green” when key modules fail.
2. News and price sources produce non-zero real-world signals/data.
3. Strategy engine can execute with real prices (not placeholders).
4. CI prevents regression on core safety/quality checks.
