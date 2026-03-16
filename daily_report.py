#!/usr/bin/env python3
"""
Daily Report Generator - Generate trading performance reports
Send to Discord/Telegram
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class ReportGenerator:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.conn = psycopg2.connect(db_url)
    
    def get_daily_stats(self) -> Dict:
        """Get yesterday's trading statistics."""
        cur = self.conn.cursor()
        
        # Get trades from yesterday
        cur.execute("""
            SELECT 
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl_usd > 0) as win_trades,
                COUNT(*) FILTER (WHERE pnl_usd < 0) as loss_trades,
                COALESCE(SUM(pnl_usd), 0) as total_pnl_usd,
                COALESCE(AVG(pnl_pct) FILTER (WHERE pnl_usd > 0), 0) as avg_win_pct,
                COALESCE(AVG(pnl_pct) FILTER (WHERE pnl_usd < 0), 0) as avg_loss_pct
            FROM trades
            WHERE closed_at >= CURRENT_DATE - INTERVAL '1 day'
              AND closed_at < CURRENT_DATE
              AND status = 'closed'
        """)
        
        row = cur.fetchone()
        
        total_trades = row[0] or 0
        win_trades = row[1] or 0
        loss_trades = row[2] or 0
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0
        
        stats = {
            "total_trades": total_trades,
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "win_rate": win_rate,
            "total_pnl_usd": float(row[3] or 0),
            "avg_win_pct": float(row[4] or 0),
            "avg_loss_pct": float(row[5] or 0)
        }
        
        cur.close()
        return stats
    
    def get_open_positions(self) -> List[Dict]:
        """Get current open positions."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT token_symbol, entry_price, quantity, opened_at
            FROM trades
            WHERE status = 'open'
            ORDER BY opened_at DESC
            LIMIT 10
        """)
        
        positions = []
        for row in cur.fetchall():
            positions.append({
                "token_symbol": row[0],
                "entry_price": float(row[1]),
                "quantity": float(row[2]),
                "opened_at": row[3].strftime("%Y-%m-%d %H:%M")
            })
        
        cur.close()
        return positions
    
    def get_strategy_performance(self) -> List[Dict]:
        """Get performance by strategy."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT 
                strategy,
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl_usd > 0) as win_trades,
                COALESCE(SUM(pnl_usd), 0) as total_pnl_usd
            FROM trades
            WHERE closed_at >= CURRENT_DATE - INTERVAL '7 days'
              AND status = 'closed'
            GROUP BY strategy
            ORDER BY total_pnl_usd DESC
        """)
        
        strategies = []
        for row in cur.fetchall():
            total = row[1]
            wins = row[2]
            win_rate = (wins / total * 100) if total > 0 else 0
            
            strategies.append({
                "strategy": row[0],
                "total_trades": total,
                "win_rate": win_rate,
                "total_pnl_usd": float(row[3])
            })
        
        cur.close()
        return strategies
    
    def get_recent_trades(self, limit: int = 5) -> List[Dict]:
        """Get recent closed trades."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT token_symbol, strategy, entry_price, exit_price, pnl_pct, closed_at
            FROM trades
            WHERE status = 'closed'
              AND closed_at >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY closed_at DESC
            LIMIT %s
        """, (limit,))
        
        trades = []
        for row in cur.fetchall():
            trades.append({
                "token_symbol": row[0],
                "strategy": row[1],
                "entry_price": float(row[2]),
                "exit_price": float(row[3]),
                "pnl_pct": float(row[4]),
                "closed_at": row[5].strftime("%Y-%m-%d %H:%M")
            })
        
        cur.close()
        return trades
    
    def generate_report(self) -> str:
        """Generate markdown report."""
        stats = self.get_daily_stats()
        positions = self.get_open_positions()
        strategies = self.get_strategy_performance()
        recent_trades = self.get_recent_trades()
        
        report = f"""# ChainLens Daily Report
**Date:** {datetime.now().strftime("%Y-%m-%d")}

## Yesterday's Performance

- **Total Trades:** {stats['total_trades']}
- **Win Rate:** {stats['win_rate']:.1f}% ({stats['win_trades']}W / {stats['loss_trades']}L)
- **Total P&L:** ${stats['total_pnl_usd']:.2f}
- **Avg Win:** {stats['avg_win_pct']:.2f}%
- **Avg Loss:** {stats['avg_loss_pct']:.2f}%

## Strategy Performance (Last 7 Days)

"""
        
        for strat in strategies:
            report += f"- **{strat['strategy']}:** {strat['total_trades']} trades, {strat['win_rate']:.1f}% win rate, ${strat['total_pnl_usd']:.2f} P&L\n"
        
        if not strategies:
            report += "_No trades in the last 7 days_\n"
        
        report += "\n## Recent Trades\n\n"
        
        for trade in recent_trades:
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            report += f"{emoji} **{trade['token_symbol']}** ({trade['strategy']}): {trade['pnl_pct']:+.2f}% @ {trade['closed_at']}\n"
        
        if not recent_trades:
            report += "_No trades closed yesterday_\n"
        
        report += "\n## Open Positions\n\n"
        
        for pos in positions:
            report += f"- **{pos['token_symbol']}:** Entry ${pos['entry_price']:.4f}, Qty {pos['quantity']:.2f} @ {pos['opened_at']}\n"
        
        if not positions:
            report += "_No open positions_\n"
        
        report += f"\n---\n_Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}_"
        
        return report
    
    def close(self):
        self.conn.close()


def main():
    print(f"=== Daily Report Generator - {datetime.now().isoformat()} ===\n")
    
    generator = ReportGenerator(DB_URL)
    try:
        report = generator.generate_report()
        print(report)
        
        # Save to file
        report_file = f"reports/daily_report_{datetime.now().strftime('%Y%m%d')}.md"
        os.makedirs("reports", exist_ok=True)
        with open(report_file, "w") as f:
            f.write(report)
        print(f"\nReport saved to {report_file}")
        
    finally:
        generator.close()


if __name__ == "__main__":
    main()
