#!/usr/bin/env python3
"""
Intelligent Risk Manager - Dynamic position sizing and risk controls
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/chainlens")


class IntelligentRiskManager:
    def __init__(self):
        self.conn = psycopg2.connect(DB_URL)
        
        # Risk parameters
        self.max_position_size = 0.10  # 10% max per position
        self.max_total_exposure = 0.40  # 40% max total
        self.max_daily_loss = 0.05  # 5% daily loss limit
        self.max_drawdown_7d = 0.15  # 15% weekly drawdown limit
        self.max_drawdown_30d = 0.25  # 25% monthly drawdown limit
        
        # Kelly Criterion parameters
        self.kelly_fraction = 0.25  # Conservative Kelly (1/4 Kelly)
        
        # Correlation limits
        self.max_correlated_positions = 3  # Max positions in same sector
    
    def get_current_exposure(self) -> float:
        """Calculate current total exposure."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT COALESCE(SUM(position_size_pct), 0)
            FROM trades
            WHERE status = 'open'
        """)
        
        total_exposure = cur.fetchone()[0] / 100  # Convert to decimal
        cur.close()
        
        return total_exposure
    
    def get_daily_pnl(self) -> float:
        """Get today's PnL."""
        cur = self.conn.cursor()
        
        cur.execute("""
            SELECT COALESCE(SUM(pnl_pct), 0)
            FROM trades
            WHERE status = 'closed'
              AND exit_time >= CURRENT_DATE
        """)
        
        daily_pnl = cur.fetchone()[0] / 100
        cur.close()
        
        return daily_pnl
    
    def get_drawdown(self, days: int) -> float:
        """Calculate drawdown over N days."""
        cur = self.conn.cursor()
        
        since = datetime.now() - timedelta(days=days)
        
        cur.execute("""
            SELECT entry_time, pnl_pct
            FROM trades
            WHERE status = 'closed'
              AND entry_time >= %s
            ORDER BY entry_time ASC
        """, (since,))
        
        trades = cur.fetchall()
        cur.close()
        
        if not trades:
            return 0.0
        
        # Calculate equity curve
        equity = 1.0  # Start at 100%
        peak_equity = 1.0
        max_drawdown = 0.0
        
        for _, pnl_pct in trades:
            equity *= (1 + pnl_pct / 100)
            
            if equity > peak_equity:
                peak_equity = equity
            
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def calculate_kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate optimal position size using Kelly Criterion."""
        if win_rate <= 0 or avg_win <= 0 or avg_loss >= 0:
            return 0.02  # Default 2%
        
        # Kelly formula: f = (p * b - q) / b
        # where p = win rate, q = loss rate, b = avg_win / abs(avg_loss)
        
        loss_rate = 1 - win_rate
        win_loss_ratio = avg_win / abs(avg_loss)
        
        kelly = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        
        # Apply Kelly fraction for safety
        kelly_adjusted = kelly * self.kelly_fraction
        
        # Clamp to reasonable range
        return max(0.01, min(kelly_adjusted, self.max_position_size))
    
    def get_strategy_performance(self, strategy: str, days: int = 30) -> Dict:
        """Get recent performance for a strategy."""
        cur = self.conn.cursor()
        
        since = datetime.now() - timedelta(days=days)
        
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                COUNT(*) as total,
                AVG(pnl_pct) FILTER (WHERE pnl_pct > 0) as avg_win,
                AVG(pnl_pct) FILTER (WHERE pnl_pct <= 0) as avg_loss
            FROM trades
            WHERE strategy = %s
              AND status = 'closed'
              AND entry_time >= %s
        """, (strategy, since))
        
        row = cur.fetchone()
        cur.close()
        
        wins = row[0] or 0
        total = row[1] or 0
        avg_win = row[2] or 0
        avg_loss = row[3] or 0
        
        win_rate = wins / total if total > 0 else 0
        
        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": total
        }
    
    def calculate_dynamic_position_size(
        self,
        strategy: str,
        signal_score: float,
        token_volatility: float = 0.5
    ) -> float:
        """Calculate dynamic position size based on multiple factors."""
        
        # Get strategy performance
        perf = self.get_strategy_performance(strategy, days=30)
        
        if perf["total_trades"] < 10:
            # Not enough data, use conservative sizing
            base_size = 0.02
        else:
            # Use Kelly Criterion
            base_size = self.calculate_kelly_position_size(
                perf["win_rate"],
                perf["avg_win"],
                perf["avg_loss"]
            )
        
        # Adjust for signal strength
        signal_factor = 0.5 + (signal_score - 0.5)  # 0.5-1.5x
        
        # Adjust for volatility (inverse relationship)
        volatility_factor = 1.0 / (1.0 + token_volatility)
        
        # Calculate final size
        position_size = base_size * signal_factor * volatility_factor
        
        # Clamp to limits
        position_size = max(0.01, min(position_size, self.max_position_size))
        
        return position_size
    
    def check_risk_limits(self) -> Dict:
        """Check all risk limits and return status."""
        current_exposure = self.get_current_exposure()
        daily_pnl = self.get_daily_pnl()
        drawdown_7d = self.get_drawdown(7)
        drawdown_30d = self.get_drawdown(30)
        
        violations = []
        warnings = []
        
        # Check exposure
        if current_exposure >= self.max_total_exposure:
            violations.append(f"Total exposure {current_exposure:.1%} >= limit {self.max_total_exposure:.0%}")
        elif current_exposure >= self.max_total_exposure * 0.8:
            warnings.append(f"Total exposure {current_exposure:.1%} approaching limit")
        
        # Check daily loss
        if daily_pnl <= -self.max_daily_loss:
            violations.append(f"Daily loss {daily_pnl:.1%} >= limit {self.max_daily_loss:.0%}")
        elif daily_pnl <= -self.max_daily_loss * 0.8:
            warnings.append(f"Daily loss {daily_pnl:.1%} approaching limit")
        
        # Check 7-day drawdown
        if drawdown_7d >= self.max_drawdown_7d:
            violations.append(f"7-day drawdown {drawdown_7d:.1%} >= limit {self.max_drawdown_7d:.0%}")
        elif drawdown_7d >= self.max_drawdown_7d * 0.8:
            warnings.append(f"7-day drawdown {drawdown_7d:.1%} approaching limit")
        
        # Check 30-day drawdown
        if drawdown_30d >= self.max_drawdown_30d:
            violations.append(f"30-day drawdown {drawdown_30d:.1%} >= limit {self.max_drawdown_30d:.0%}")
        elif drawdown_30d >= self.max_drawdown_30d * 0.8:
            warnings.append(f"30-day drawdown {drawdown_30d:.1%} approaching limit")
        
        # Determine action
        if violations:
            action = "HALT_TRADING"
            status = "CRITICAL"
        elif warnings:
            action = "REDUCE_EXPOSURE"
            status = "WARNING"
        else:
            action = "NORMAL"
            status = "OK"
        
        return {
            "status": status,
            "action": action,
            "current_exposure": current_exposure,
            "daily_pnl": daily_pnl,
            "drawdown_7d": drawdown_7d,
            "drawdown_30d": drawdown_30d,
            "violations": violations,
            "warnings": warnings,
            "timestamp": datetime.now()
        }
    
    def get_available_capital(self) -> float:
        """Calculate available capital for new positions."""
        current_exposure = self.get_current_exposure()
        available = self.max_total_exposure - current_exposure
        
        return max(0, available)
    
    def can_open_position(self, position_size: float) -> tuple[bool, str]:
        """Check if a new position can be opened."""
        risk_status = self.check_risk_limits()
        
        # Check for violations
        if risk_status["status"] == "CRITICAL":
            return False, f"Trading halted: {', '.join(risk_status['violations'])}"
        
        # Check available capital
        available = self.get_available_capital()
        if position_size > available:
            return False, f"Insufficient capital: need {position_size:.1%}, available {available:.1%}"
        
        # Check if we should reduce exposure
        if risk_status["status"] == "WARNING" and position_size > available * 0.5:
            return False, f"Risk warning active: {', '.join(risk_status['warnings'])}"
        
        return True, "OK"
    
    def generate_risk_report(self) -> str:
        """Generate comprehensive risk report."""
        risk_status = self.check_risk_limits()
        
        report = f"""
=== Risk Management Report ===
Generated: {datetime.now().isoformat()}

Status: {risk_status['status']}
Action: {risk_status['action']}

Current Metrics:
- Total Exposure: {risk_status['current_exposure']:.1%} / {self.max_total_exposure:.0%}
- Daily PnL: {risk_status['daily_pnl']:.2%}
- 7-Day Drawdown: {risk_status['drawdown_7d']:.1%} / {self.max_drawdown_7d:.0%}
- 30-Day Drawdown: {risk_status['drawdown_30d']:.1%} / {self.max_drawdown_30d:.0%}
- Available Capital: {self.get_available_capital():.1%}

"""
        
        if risk_status['violations']:
            report += "VIOLATIONS:\n"
            for v in risk_status['violations']:
                report += f"  ❌ {v}\n"
            report += "\n"
        
        if risk_status['warnings']:
            report += "WARNINGS:\n"
            for w in risk_status['warnings']:
                report += f"  ⚠️  {w}\n"
            report += "\n"
        
        if risk_status['status'] == 'OK':
            report += "✅ All risk limits within acceptable range\n"
        
        return report
    
    def close(self):
        self.conn.close()


def main():
    manager = IntelligentRiskManager()
    try:
        print(manager.generate_risk_report())
    finally:
        manager.close()


if __name__ == "__main__":
    main()
