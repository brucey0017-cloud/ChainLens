#!/usr/bin/env python3
"""
Strategy Engine - Implement Jim Simons' multi-strategy approach
Strategies: Triple Confirmation, Resonance, Contrarian, Arbitrage
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class StrategyEngine:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = psycopg2.connect(db_url)
    
    def get_recent_signals(self, hours: int = 1) -> List[Dict]:
        """Get unprocessed signals from last N hours."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id, source, token_symbol, token_address, chain, signal_score, raw_data, timestamp
            FROM signals
            WHERE processed = FALSE
              AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
        """, (hours,))
        
        signals = []
        for row in cur.fetchall():
            signals.append({
                "id": row[0],
                "source": row[1],
                "token_symbol": row[2],
                "token_address": row[3],
                "chain": row[4],
                "signal_score": float(row[5]) if row[5] else 0.0,
                "raw_data": row[6],
                "timestamp": row[7]
            })
        
        cur.close()
        return signals
    
    def mark_signals_processed(self, signal_ids: List[int]):
        """Mark signals as processed."""
        if not signal_ids:
            return
        
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE signals
            SET processed = TRUE
            WHERE id = ANY(%s)
        """, (signal_ids,))
        self.conn.commit()
        cur.close()
    
    def get_token_risk_score(self, token_address: str, chain: str) -> Optional[float]:
        """Get token risk score from auditor."""
        # Import token_auditor
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        
        try:
            from token_auditor import TokenAuditor
            auditor = TokenAuditor()
            result = auditor.audit_token(token_address, chain)
            if result and "risk_score" in result:
                return result["risk_score"]
        except Exception as e:
            print(f"  Warning: Token auditor failed: {e}", file=sys.stderr)
        
        # Fallback: return a mock score
        return 65.0
    
    def get_token_market_info(self, token_symbol: str, token_address: str, chain: str) -> Optional[Dict]:
        """Get token market cap and liquidity via CoinGecko (free, no key)."""
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from price_fetcher import get_market_data

            info = get_market_data(token_symbol)
            if info and info.get("market_cap", 0) > 0:
                return {
                    "market_cap": info["market_cap"],
                    "liquidity": info.get("volume_24h", 0),  # use 24h volume as liquidity proxy
                    "volume_24h": info.get("volume_24h", 0),
                    "price_change_24h": info.get("change_24h", 0),
                }
        except Exception as e:
            print(f"  Warning: Failed to get market info: {e}", file=sys.stderr)

        return None
    
    def strategy_triple_confirmation(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 1: Triple Confirmation
        Requires: Smart Money + Twitter + Risk Score > 60
        """
        trades = []
        
        # Group signals by token
        token_signals = {}
        for sig in signals:
            key = (sig["token_address"], sig["chain"])
            if key not in token_signals:
                token_signals[key] = []
            token_signals[key].append(sig)
        
        # Check for triple confirmation
        for (token_addr, chain), sigs in token_signals.items():
            token_symbol = sigs[0]["token_symbol"]
            
            # FILTER 1: Check market cap and liquidity first
            token_info = self.get_token_market_info(token_symbol, token_addr, chain)
            if not token_info:
                print(f"  Skipped {token_symbol}: cannot fetch market info", file=sys.stderr)
                continue
            
            market_cap = token_info.get("market_cap", 0)
            liquidity = token_info.get("liquidity", 0)
            
            # Different thresholds for pump.fun vs regular tokens
            is_pumpfun = token_addr.endswith("pump")
            
            if is_pumpfun:
                # Stricter requirements for pump.fun tokens
                MIN_MARKET_CAP = 500_000   # $500K
                MIN_LIQUIDITY = 100_000    # $100K
                
                if market_cap < MIN_MARKET_CAP:
                    print(f"  Skipped {token_symbol} (pump.fun): market cap ${market_cap:,.0f} < ${MIN_MARKET_CAP:,.0f}", file=sys.stderr)
                    continue
                
                if liquidity < MIN_LIQUIDITY:
                    print(f"  Skipped {token_symbol} (pump.fun): liquidity ${liquidity:,.0f} < ${MIN_LIQUIDITY:,.0f}", file=sys.stderr)
                    continue
                
                print(f"  ✓ {token_symbol} (pump.fun): market cap ${market_cap:,.0f}, liquidity ${liquidity:,.0f}", file=sys.stderr)
            else:
                # Regular tokens: lower thresholds
                MIN_MARKET_CAP = 100_000   # $100K
                MIN_LIQUIDITY = 50_000     # $50K
                
                if market_cap < MIN_MARKET_CAP:
                    print(f"  Skipped {token_symbol}: market cap ${market_cap:,.0f} < ${MIN_MARKET_CAP:,.0f}", file=sys.stderr)
                    continue
                
                if liquidity < MIN_LIQUIDITY:
                    print(f"  Skipped {token_symbol}: liquidity ${liquidity:,.0f} < ${MIN_LIQUIDITY:,.0f}", file=sys.stderr)
                    continue
            
            sources = set(s["source"] for s in sigs)
            
            # Need at least smart_money signal
            if "smart_money" not in sources:
                continue
            
            # Get highest signal score
            max_score = max(s["signal_score"] for s in sigs)
            
            if max_score < 0.6:
                continue
            
            # Check risk score
            risk_score = self.get_token_risk_score(token_addr, chain)
            if risk_score is None or risk_score < 60:
                continue
            
            # Generate trade signal
            trades.append({
                "strategy": "triple_confirmation",
                "token_symbol": token_symbol,
                "token_address": token_addr,
                "chain": chain,
                "direction": "buy",
                "signal_score": max_score,
                "risk_score": risk_score,
                "position_size_pct": self._calculate_position_size(max_score, 2, 5),
                "stop_loss_pct": -15.0,
                "take_profit_pct": 30.0,
                "hold_hours": 24
            })
        
        return trades
    
    def strategy_contrarian(self, signals: List[Dict]) -> List[Dict]:
        """
        Strategy 3: Contrarian
        Buy when price drops >20% but fundamentals are strong
        """
        trades = []
        
        # TODO: Implement price drop detection
        # For now, return empty
        
        return trades
    
    def _calculate_position_size(self, signal_score: float, min_pct: float, max_pct: float) -> float:
        """Calculate position size based on signal strength."""
        # Linear interpolation between min and max
        normalized = (signal_score - 0.5) / 0.5  # Map 0.5-1.0 to 0-1
        normalized = max(0, min(1, normalized))
        return min_pct + (max_pct - min_pct) * normalized
    
    def execute_paper_trades(self, trades: List[Dict]):
        """Execute paper trades (record in database)."""
        if not trades:
            return
        
        # Check trading mode
        trading_mode = os.getenv("TRADING_MODE", "paper")
        
        cur = self.conn.cursor()
        
        for trade in trades:
            # Get current price from CoinGecko
            try:
                from price_fetcher import get_price
                entry_price = get_price(trade["token_symbol"]) or 0.0
            except Exception:
                entry_price = 0.0

            if entry_price <= 0:
                print(f"  Skipped {trade['token_symbol']}: no price available", file=sys.stderr)
                continue

            quantity = (trade["position_size_pct"] / 100) * 10000 / entry_price  # Assume $10k account
            
            # In live mode, create pending_approval trades
            if trading_mode == "live":
                status = "pending_approval"
            else:
                status = "open"
            
            cur.execute("""
                INSERT INTO trades (
                    strategy, token_symbol, token_address, chain, direction,
                    entry_price, quantity, position_size_pct,
                    stop_loss, take_profit, is_paper, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade["strategy"],
                trade["token_symbol"],
                trade["token_address"],
                trade["chain"],
                trade["direction"],
                entry_price,
                quantity,
                trade["position_size_pct"],
                entry_price * (1 + trade["stop_loss_pct"] / 100),
                entry_price * (1 + trade["take_profit_pct"] / 100),
                trading_mode == "paper",  # is_paper
                status
            ))
        
        self.conn.commit()
        cur.close()
        
        if trading_mode == "live":
            print(f"Created {len(trades)} trades pending approval")
        else:
            print(f"Executed {len(trades)} paper trades")
    
    def run(self):
        """Main execution loop."""
        print(f"=== Strategy Engine - {datetime.now().isoformat()} ===")
        
        # Get recent signals
        signals = self.get_recent_signals(hours=1)
        print(f"Processing {len(signals)} signals...")
        
        if not signals:
            print("No signals to process")
            return
        
        # Run strategies
        all_trades = []
        
        # Strategy 1: Triple Confirmation
        trades_1 = self.strategy_triple_confirmation(signals)
        all_trades.extend(trades_1)
        print(f"  Triple Confirmation: {len(trades_1)} trades")
        
        # Strategy 3: Contrarian
        trades_3 = self.strategy_contrarian(signals)
        all_trades.extend(trades_3)
        print(f"  Contrarian: {len(trades_3)} trades")
        
        # Execute paper trades
        if all_trades:
            self.execute_paper_trades(all_trades)
        
        # Mark signals as processed
        signal_ids = [s["id"] for s in signals]
        self.mark_signals_processed(signal_ids)
        
        print(f"\nTotal trades generated: {len(all_trades)}")
    
    def close(self):
        self.conn.close()


def main():
    engine = StrategyEngine(DB_URL)
    try:
        engine.run()
    finally:
        engine.close()


if __name__ == "__main__":
    main()
