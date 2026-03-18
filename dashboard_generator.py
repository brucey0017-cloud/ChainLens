#!/usr/bin/env python3
"""
Real-time Performance Dashboard Generator
Creates HTML dashboard with live metrics
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import db_patch  # noqa: F401, E402 — must import before psycopg2
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class DashboardGenerator:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
    
    def get_system_stats(self) -> Dict:
        """Get overall system statistics."""
        cur = self.conn.cursor()
        
        # Total signals
        cur.execute("SELECT COUNT(*) FROM signals WHERE timestamp >= NOW() - INTERVAL '24 hours'")
        signals_24h = cur.fetchone()[0]
        
        # Total trades
        cur.execute("SELECT COUNT(*) FROM trades WHERE opened_at >= NOW() - INTERVAL '24 hours'")
        trades_24h = cur.fetchone()[0]
        
        # Open positions
        cur.execute("SELECT COUNT(*) FROM trades WHERE status = 'open'")
        open_positions = cur.fetchone()[0]
        
        # Win rate (last 7 days)
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                COUNT(*) as total
            FROM trades
            WHERE status = 'closed'
              AND opened_at >= NOW() - INTERVAL '7 days'
        """)
        row = cur.fetchone()
        wins, total = row[0] or 0, row[1] or 0
        win_rate = (wins / total * 100) if total > 0 else 0
        
        # Total PnL (last 7 days)
        cur.execute("""
            SELECT COALESCE(SUM(pnl_pct), 0)
            FROM trades
            WHERE status = 'closed'
              AND opened_at >= NOW() - INTERVAL '7 days'
        """)
        total_pnl = cur.fetchone()[0]
        
        cur.close()
        
        return {
            "signals_24h": signals_24h,
            "trades_24h": trades_24h,
            "open_positions": open_positions,
            "win_rate_7d": win_rate,
            "total_pnl_7d": total_pnl
        }
    
    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get most recent trades."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT 
                token_symbol, strategy, entry_price, exit_price,
                pnl_pct, status, notes, opened_at, closed_at
            FROM trades
            ORDER BY opened_at DESC
            LIMIT %s
        """, (limit,))
        
        trades = []
        for row in cur.fetchall():
            trades.append({
                "token_symbol": row[0],
                "strategy": row[1],
                "entry_price": float(row[2]) if row[2] else 0,
                "exit_price": float(row[3]) if row[3] else 0,
                "pnl_pct": float(row[4]) if row[4] else 0,
                "status": row[5],
                "notes": row[6],
                "opened_at": row[7].isoformat() if row[7] else "",
                "closed_at": row[8].isoformat() if row[8] else ""
            })
        
        cur.close()
        return trades
    
    def get_signal_breakdown(self) -> Dict:
        """Get signal count by source."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT source, COUNT(*)
            FROM signals
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
            GROUP BY source
        """)
        
        breakdown = {}
        for row in cur.fetchall():
            breakdown[row[0]] = row[1]
        
        cur.close()
        return breakdown
    
    def generate_html(self) -> str:
        """Generate HTML dashboard."""
        stats = self.get_system_stats()
        trades = self.get_recent_trades(20)
        signals = self.get_signal_breakdown()
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChainLens Trading Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .stat-card .label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 8px;
        }}
        
        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }}
        
        .stat-card.positive .value {{
            color: #10b981;
        }}
        
        .stat-card.negative .value {{
            color: #ef4444;
        }}
        
        .section {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            font-size: 1.5em;
            margin-bottom: 20px;
            color: #333;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            background: #f3f4f6;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        tr:hover {{
            background: #f9fafb;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .badge.open {{
            background: #dbeafe;
            color: #1e40af;
        }}
        
        .badge.closed {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .badge.positive {{
            background: #d1fae5;
            color: #065f46;
        }}
        
        .badge.negative {{
            background: #fee2e2;
            color: #991b1b;
        }}
        
        .signal-bar {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
        }}
        
        .signal-bar .label {{
            width: 150px;
            font-weight: 500;
        }}
        
        .signal-bar .bar {{
            flex: 1;
            height: 24px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .signal-bar .fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            padding: 0 8px;
            color: white;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .timestamp {{
            color: #9ca3af;
            font-size: 0.85em;
        }}
        
        .refresh-info {{
            text-align: center;
            color: white;
            margin-top: 20px;
            opacity: 0.8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 ChainLens Trading Dashboard</h1>
            <div class="subtitle">AI-Powered Quantitative Trading System</div>
            <div class="timestamp">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Signals (24h)</div>
                <div class="value">{stats['signals_24h']}</div>
            </div>
            
            <div class="stat-card">
                <div class="label">Trades (24h)</div>
                <div class="value">{stats['trades_24h']}</div>
            </div>
            
            <div class="stat-card">
                <div class="label">Open Positions</div>
                <div class="value">{stats['open_positions']}</div>
            </div>
            
            <div class="stat-card {'positive' if stats['win_rate_7d'] >= 55 else 'negative'}">
                <div class="label">Win Rate (7d)</div>
                <div class="value">{stats['win_rate_7d']:.1f}%</div>
            </div>
            
            <div class="stat-card {'positive' if stats['total_pnl_7d'] > 0 else 'negative'}">
                <div class="label">Total PnL (7d)</div>
                <div class="value">{stats['total_pnl_7d']:+.2f}%</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Signal Sources (24h)</h2>
"""
        
        # Signal breakdown
        if signals:
            total_signals = sum(signals.values())
            for source, count in sorted(signals.items(), key=lambda x: x[1], reverse=True):
                pct = (count / total_signals * 100) if total_signals > 0 else 0
                html += f"""
            <div class="signal-bar">
                <div class="label">{source.replace('_', ' ').title()}</div>
                <div class="bar">
                    <div class="fill" style="width: {pct}%">{count} ({pct:.1f}%)</div>
                </div>
            </div>
"""
        else:
            html += "            <p>No signals in last 24 hours</p>\n"
        
        html += """
        </div>
        
        <div class="section">
            <h2>📈 Recent Trades</h2>
            <table>
                <thead>
                    <tr>
                        <th>Token</th>
                        <th>Strategy</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>PnL</th>
                        <th>Status</th>
                        <th>Reason</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        # Recent trades
        for trade in trades:
            pnl_class = 'positive' if trade['pnl_pct'] > 0 else 'negative'
            status_class = trade['status']
            
            html += f"""
                    <tr>
                        <td><strong>{trade['token_symbol']}</strong></td>
                        <td>{trade['strategy'].replace('_', ' ').title()}</td>
                        <td>${trade['entry_price']:.6f}</td>
                        <td>${trade['exit_price']:.6f}</td>
                        <td><span class="badge {pnl_class}">{trade['pnl_pct']:+.2f}%</span></td>
                        <td><span class="badge {status_class}">{trade['status']}</span></td>
                        <td>{trade['notes'] or '-'}</td>
                        <td class="timestamp">{trade['opened_at'][:16]}</td>
                    </tr>
"""
        
        html += """
                </tbody>
            </table>
        </div>
        
        <div class="refresh-info">
            Auto-refreshes every 15 minutes via GitHub Actions
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def save_dashboard(self, output_path: str = "index.html"):
        """Generate and save dashboard."""
        html = self.generate_html()
        
        with open(output_path, 'w') as f:
            f.write(html)
        
        print(f"Dashboard saved to {output_path}")
    
    def close(self):
        self.conn.close()


def main():
    generator = DashboardGenerator()
    try:
        generator.save_dashboard()
    finally:
        generator.close()


if __name__ == "__main__":
    main()
