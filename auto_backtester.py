#!/usr/bin/env python3
"""
Automated Backtesting System - Validate strategies with historical data
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import db_patch  # noqa: F401, E402 — must import before psycopg2
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class AutoBacktester:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
        self.initial_capital = 10000  # $10K
    
    def get_closed_trades(self, days: int = 7) -> List[Dict]:
        """Get all closed trades from last N days."""
        cur = self.conn.cursor()
        
        since = datetime.now() - timedelta(days=days)
        
        cur.execute("""
            SELECT 
                id, strategy, token_symbol, token_address, chain,
                entry_price, exit_price, quantity, position_size_pct,
                opened_at, closed_at, pnl_pct, notes
            FROM trades
            WHERE status = 'closed'
              AND opened_at >= %s
            ORDER BY opened_at ASC
        """, (since,))
        
        trades = []
        for row in cur.fetchall():
            trades.append({
                "id": row[0],
                "strategy": row[1],
                "token_symbol": row[2],
                "token_address": row[3],
                "chain": row[4],
                "entry_price": float(row[5]) if row[5] else 0,
                "exit_price": float(row[6]) if row[6] else 0,
                "quantity": float(row[7]) if row[7] else 0,
                "position_size_pct": float(row[8]) if row[8] else 0,
                "opened_at": row[9],
                "closed_at": row[10],
                "pnl_pct": float(row[11]) if row[11] else 0,
                "notes": row[12]
            })
        
        cur.close()
        return trades
    
    def calculate_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "max_drawdown": 0,
                "sharpe_ratio": 0
            }
        
        # Basic stats
        total_trades = len(trades)
        winning_trades = [t for t in trades if t["pnl_pct"] > 0]
        losing_trades = [t for t in trades if t["pnl_pct"] <= 0]
        
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_rate = win_count / total_trades if total_trades > 0 else 0
        
        # PnL stats
        total_pnl = sum(t["pnl_pct"] for t in trades)
        
        if winning_trades:
            avg_win = sum(t["pnl_pct"] for t in winning_trades) / len(winning_trades)
            total_wins = sum(t["pnl_pct"] for t in winning_trades)
        else:
            avg_win = 0
            total_wins = 0
        
        if losing_trades:
            avg_loss = sum(t["pnl_pct"] for t in losing_trades) / len(losing_trades)
            total_losses = abs(sum(t["pnl_pct"] for t in losing_trades))
        else:
            avg_loss = 0
            total_losses = 0
        
        # Profit factor
        if total_losses > 0:
            profit_factor = total_wins / total_losses
        else:
            profit_factor = float('inf') if total_wins > 0 else 0
        
        # Drawdown calculation
        equity_curve = [self.initial_capital]
        for trade in trades:
            position_value = equity_curve[-1] * (trade["position_size_pct"] / 100)
            pnl = position_value * (trade["pnl_pct"] / 100)
            new_equity = equity_curve[-1] + pnl
            equity_curve.append(new_equity)
        
        max_equity = equity_curve[0]
        max_drawdown = 0
        
        for equity in equity_curve:
            if equity > max_equity:
                max_equity = equity
            drawdown = (max_equity - equity) / max_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Sharpe ratio (simplified)
        if len(trades) > 1:
            returns = [t["pnl_pct"] for t in trades]
            avg_return = sum(returns) / len(returns)
            variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** 0.5
            
            if std_dev > 0:
                sharpe_ratio = (avg_return / std_dev) * (252 ** 0.5)  # Annualized
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_pnl_pct": total_pnl,
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "max_drawdown_pct": max_drawdown * 100,
            "sharpe_ratio": sharpe_ratio,
            "final_equity": equity_curve[-1] if equity_curve else self.initial_capital,
            "total_return_pct": ((equity_curve[-1] - self.initial_capital) / self.initial_capital * 100) if equity_curve else 0
        }
    
    def analyze_by_strategy(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Break down metrics by strategy."""
        strategies = {}
        
        for trade in trades:
            strategy = trade["strategy"]
            if strategy not in strategies:
                strategies[strategy] = []
            strategies[strategy].append(trade)
        
        results = {}
        for strategy, strategy_trades in strategies.items():
            results[strategy] = self.calculate_metrics(strategy_trades)
        
        return results
    
    def analyze_by_notes(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Break down metrics by exit reason."""
        reasons = {}
        
        for trade in trades:
            reason = trade["notes"] or "unknown"
            if reason not in reasons:
                reasons[reason] = []
            reasons[reason].append(trade)
        
        results = {}
        for reason, reason_trades in reasons.items():
            results[reason] = {
                "count": len(reason_trades),
                "avg_pnl_pct": sum(t["pnl_pct"] for t in reason_trades) / len(reason_trades)
            }
        
        return results
    
    def save_backtest_results(self, metrics: Dict, period_days: int):
        """Save backtest results to database."""
        cur = self.conn.cursor()
        
        cur.execute("""
            INSERT INTO backtest_results (
                period_start, period_end, total_trades, win_rate,
                profit_factor, total_return_pct, max_drawdown_pct,
                sharpe_ratio, metrics_json
            ) VALUES (
                NOW() - INTERVAL '%s days',
                NOW(),
                %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            period_days,
            metrics["total_trades"],
            metrics["win_rate"],
            metrics["profit_factor"],
            metrics["total_return_pct"],
            metrics["max_drawdown_pct"],
            metrics["sharpe_ratio"],
            json.dumps(metrics)
        ))
        
        self.conn.commit()
        cur.close()
    
    def generate_report(self, days: int = 7):
        """Generate comprehensive backtest report."""
        print(f"\n{'='*70}")
        print(f"BACKTEST REPORT - Last {days} Days")
        print(f"{'='*70}\n")
        
        trades = self.get_closed_trades(days=days)
        
        if not trades:
            print("No closed trades in this period.")
            return
        
        # Overall metrics
        overall = self.calculate_metrics(trades)
        
        print("OVERALL PERFORMANCE")
        print(f"{'─'*70}")
        print(f"Total Trades:        {overall['total_trades']}")
        print(f"Win Rate:            {overall['win_rate']*100:.1f}% ({overall['win_count']}W / {overall['loss_count']}L)")
        print(f"Profit Factor:       {overall['profit_factor']:.2f}")
        print(f"Total Return:        {overall['total_return_pct']:.2f}%")
        print(f"Average Win:         +{overall['avg_win_pct']:.2f}%")
        print(f"Average Loss:        {overall['avg_loss_pct']:.2f}%")
        print(f"Max Drawdown:        {overall['max_drawdown_pct']:.2f}%")
        print(f"Sharpe Ratio:        {overall['sharpe_ratio']:.2f}")
        print(f"Final Equity:        ${overall['final_equity']:,.2f}")
        print()
        
        # By strategy
        by_strategy = self.analyze_by_strategy(trades)
        
        print("PERFORMANCE BY STRATEGY")
        print(f"{'─'*70}")
        for strategy, metrics in by_strategy.items():
            print(f"\n{strategy.upper()}:")
            print(f"  Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']*100:.1f}%")
            print(f"  Profit Factor: {metrics['profit_factor']:.2f} | Return: {metrics['total_return_pct']:.2f}%")
        print()
        
        # By exit reason
        by_reason = self.analyze_by_notes(trades)
        
        print("PERFORMANCE BY EXIT REASON")
        print(f"{'─'*70}")
        for reason, stats in by_reason.items():
            print(f"{reason:20s}: {stats['count']:3d} trades | Avg PnL: {stats['avg_pnl_pct']:+.2f}%")
        print()
        
        # Save results
        self.save_backtest_results(overall, days)
        
        # Assessment
        print("ASSESSMENT")
        print(f"{'─'*70}")
        
        if overall['win_rate'] >= 0.55 and overall['profit_factor'] >= 1.5:
            print("✅ PASS - System meets Phase 2 criteria")
            print("   Ready for live trading consideration")
        elif overall['win_rate'] >= 0.50:
            print("⚠️  MARGINAL - Close to target but needs improvement")
            print("   Continue paper trading and optimization")
        else:
            print("❌ FAIL - System does not meet criteria")
            print("   Significant improvements needed before live trading")
        
        print(f"{'='*70}\n")
    
    def close(self):
        self.conn.close()


def main():
    backtester = AutoBacktester()
    try:
        # Generate reports for different periods
        backtester.generate_report(days=7)   # Weekly
        # backtester.generate_report(days=30)  # Monthly (uncomment when enough data)
    finally:
        backtester.close()


if __name__ == "__main__":
    main()
