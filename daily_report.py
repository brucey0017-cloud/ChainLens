#!/usr/bin/env python3
"""
Daily Report Generator - Generate performance summary
Based on Jim Simons' emphasis on continuous monitoring and feedback
"""

import os
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
        """Get statistics for the last 24 hours."""
        cur = self.conn.cursor()
        
        # Total signals
        cur.execute("""
            SELECT COUNT(*) FROM signals
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        total_signals = cur.fetchone()[0]
        
        # Trades opened
        cur.execute("""
            SELECT COUNT(*) FROM trades
            WHERE opened_at > NOW() - INTERVAL '24 hours'
        """)
        trades_opened = cur.fetchone()[0]
        
        # Trades closed
        cur.execute("""
            SELECT COUNT(*), SUM(pnl_usd), AVG(pnl_pct)
            FROM trades
            WHERE closed_at > NOW() - INTERVAL '24 hours'
              AND status = 'closed'
        """)
        row = cur.fetchone()
        trades_closed = row[0] or 0
        total_pnl = float(row[1]) if row[1] else 0.0
        avg_pnl_pct = float(row[2]) if row[2] else 0.0
        
        # Win rate
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                COUNT(*) as total
            FROM trades
            WHERE closed_at > NOW() - INTERVAL '24 hours'
              AND status = 'closed'
        """)
        row = cur.fetchone()
        wins = row[0] or 0
        total = row[1] or 0
        win_rate = (wins / total * 100) if total > 0 else 0.0
        
        # Open positions
        cur.execute("""
            SELECT COUNT(*) FROM trades WHERE status = 'open'
        """)
        open_positions = cur.fetchone()[0]
        
        cur.close()
        
        return {
            "total_signals": total_signals,
            "trades_opened": trades_opened,
            "trades_closed": trades_closed,
            "total_pnl": total_pnl,
            "avg_pnl_pct": avg_pnl_pct,
            "win_rate": win_rate,
            "open_positions": open_positions
        }
    
    def get_strategy_performance(self) -> List[Dict]:
        """Get performance by strategy."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT 
                strategy,
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE pnl_usd > 0) as wins,
                AVG(pnl_pct) as avg_pnl_pct,
                SUM(pnl_usd) as total_pnl
            FROM trades
            WHERE closed_at > NOW() - INTERVAL '7 days'
              AND status = 'closed'
            GROUP BY strategy
            ORDER BY total_pnl DESC
        """)
        
        strategies = []
        for row in cur.fetchall():
            total = row[1]
            wins = row[2] or 0
            strategies.append({
                "strategy": row[0],
                "total_trades": total,
                "win_rate": (wins / total * 100) if total > 0 else 0.0,
                "avg_pnl_pct": float(row[3]) if row[3] else 0.0,
                "total_pnl": float(row[4]) if row[4] else 0.0
            })
        
        cur.close()
        return strategies
    
    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get recent closed trades."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT token_symbol, strategy, pnl_pct, pnl_usd, closed_at, notes
            FROM trades
            WHERE status = 'closed'
            ORDER BY closed_at DESC
            LIMIT %s
        """, (limit,))
        
        trades = []
        for row in cur.fetchall():
            trades.append({
                "token": row[0],
                "strategy": row[1],
                "pnl_pct": float(row[2]) if row[2] else 0.0,
                "pnl_usd": float(row[3]) if row[3] else 0.0,
                "closed_at": row[4],
                "reason": row[5] or "unknown"
            })
        
        cur.close()
        return trades
    
    def generate_report(self) -> str:
        """Generate markdown report."""
        stats = self.get_daily_stats()
        strategies = self.get_strategy_performance()
        recent_trades = self.get_recent_trades(10)
        
        report = f"""# ChainLens Daily Report
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

## 📊 24-Hour Summary

- **Signals Collected:** {stats['total_signals']}
- **Trades Opened:** {stats['trades_opened']}
- **Trades Closed:** {stats['trades_closed']}
- **Total P&L:** ${stats['total_pnl']:.2f} ({stats['avg_pnl_pct']:+.2f}% avg)
- **Win Rate:** {stats['win_rate']:.1f}%
- **Open Positions:** {stats['open_positions']}

## 📈 Strategy Performance (7 Days)

"""
        
        for strat in strategies:
            report += f"""### {strat['strategy']}
- Trades: {strat['total_trades']}
- Win Rate: {strat['win_rate']:.1f}%
- Avg P&L: {strat['avg_pnl_pct']:+.2f}%
- Total P&L: ${strat['total_pnl']:.2f}

"""
        
        report += "## 🔄 Recent Trades\n\n"
        report += "| Token | Strategy | P&L % | P&L $ | Closed | Reason |\n"
        report += "|-------|----------|-------|-------|--------|--------|\n"
        
        for trade in recent_trades:
            pnl_emoji = "🟢" if trade['pnl_pct'] > 0 else "🔴"
            report += f"| {trade['token']} | {trade['strategy']} | {pnl_emoji} {trade['pnl_pct']:+.2f}% | ${trade['pnl_usd']:.2f} | {trade['closed_at'].strftime('%m-%d %H:%M')} | {trade['reason']} |\n"
        
        report += "\n---\n*Powered by ChainLens - AI-driven onchain intelligence*\n"
        
        return report
    
    def close(self):
        self.conn.close()


def main():
    print("Generating daily report...")
    
    generator = ReportGenerator(DB_URL)
    try:
        report = generator.generate_report()
        print(report)
        
        # Save to file
        with open("DAILY_REPORT.md", "w") as f:
            f.write(report)
        
        print("\nReport saved to DAILY_REPORT.md")
    finally:
        generator.close()


if __name__ == "__main__":
    main()
