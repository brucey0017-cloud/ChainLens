#!/usr/bin/env python3
"""
Real-time Performance Dashboard Generator
Creates HTML dashboard with live metrics

Uses Supabase REST as single data plane.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from supabase_client import is_available, select


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class DashboardGenerator:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    def get_system_stats(self) -> Dict:
        """Get overall system statistics."""
        cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        # Signals in last 24h
        sig_rows = select("signals", columns="id", filters={"timestamp": f"gte.{cutoff_24h}"}, limit=10000)
        signals_24h = len(sig_rows)

        # Trades in last 24h
        trade_rows = select("trades", columns="id", filters={"opened_at": f"gte.{cutoff_24h}"}, limit=10000)
        trades_24h = len(trade_rows)

        # Open positions
        open_rows = select("trades", columns="id", filters={"status": "eq.open"}, limit=10000)
        open_positions = len(open_rows)

        # Win rate and PnL (last 7 days, closed trades)
        closed_rows = select(
            "trades",
            columns="pnl_pct",
            filters={"status": "eq.closed", "opened_at": f"gte.{cutoff_7d}"},
            limit=10000,
        )
        total = len(closed_rows)
        wins = sum(1 for r in closed_rows if _to_float(r.get("pnl_pct")) > 0)
        win_rate = (wins / total * 100) if total > 0 else 0
        total_pnl = sum(_to_float(r.get("pnl_pct")) for r in closed_rows)

        return {
            "signals_24h": signals_24h,
            "trades_24h": trades_24h,
            "open_positions": open_positions,
            "win_rate_7d": win_rate,
            "total_pnl_7d": total_pnl,
        }

    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get most recent trades."""
        rows = select(
            "trades",
            columns="token_symbol,strategy,entry_price,exit_price,pnl_pct,status,notes,opened_at,closed_at",
            order="opened_at.desc",
            limit=limit,
        )

        trades = []
        for row in rows:
            trades.append({
                "token_symbol": row.get("token_symbol", ""),
                "strategy": row.get("strategy", ""),
                "entry_price": _to_float(row.get("entry_price")),
                "exit_price": _to_float(row.get("exit_price")),
                "pnl_pct": _to_float(row.get("pnl_pct")),
                "status": row.get("status", ""),
                "notes": row.get("notes", ""),
                "opened_at": row.get("opened_at", ""),
                "closed_at": row.get("closed_at", ""),
            })
        return trades

    def get_signal_breakdown(self) -> Dict:
        """Get signal count by source."""
        cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        rows = select(
            "signals",
            columns="source",
            filters={"timestamp": f"gte.{cutoff_24h}"},
            limit=10000,
        )

        breakdown: Dict[str, int] = {}
        for row in rows:
            src = row.get("source", "unknown")
            breakdown[src] = breakdown.get(src, 0) + 1
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


def main():
    generator = DashboardGenerator()
    generator.save_dashboard()


if __name__ == "__main__":
    main()
