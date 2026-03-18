#!/usr/bin/env python3
"""
Intelligent Risk Manager - Dynamic position sizing and risk controls

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Tuple

from supabase_client import is_available, select


def _to_float(v, default: float = 0.0) -> float:
    try:
        if isinstance(v, Decimal):
            return float(v)
        return float(v)
    except (TypeError, ValueError):
        return default


class IntelligentRiskManager:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

        # Risk parameters
        self.max_position_size = 0.10  # 10% max per position
        self.max_total_exposure = 0.40  # 40% max total
        self.max_daily_loss = 0.05  # 5% daily loss limit
        self.max_drawdown_7d = 0.15  # 15% weekly drawdown limit
        self.max_drawdown_30d = 0.25  # 25% monthly drawdown limit

        # Kelly Criterion parameters
        self.kelly_fraction = 0.25  # Conservative Kelly (1/4 Kelly)

    def get_current_exposure(self) -> float:
        """Calculate current total exposure (sum of position_size_pct for open trades)."""
        rows = select(
            "trades",
            columns="position_size_pct",
            filters={"status": "eq.open"},
            limit=5000,
        )
        total_pct = sum(_to_float(r.get("position_size_pct"), 0.0) for r in rows)
        return total_pct / 100.0

    def get_daily_pnl(self) -> float:
        """Get today's PnL (sum of pnl_pct for closed trades closed today)."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = select(
            "trades",
            columns="pnl_pct",
            filters={"status": "eq.closed", "closed_at": f"gte.{today_start}"},
            limit=5000,
        )
        total = sum(_to_float(r.get("pnl_pct"), 0.0) for r in rows)
        return total / 100.0

    def get_drawdown(self, days: int) -> float:
        """Calculate drawdown over N days using closed_at for windowing."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = select(
            "trades",
            columns="pnl_pct,closed_at",
            filters={"status": "eq.closed", "closed_at": f"gte.{since}"},
            order="closed_at.asc",
            limit=20000,
        )

        if not rows:
            return 0.0

        # Calculate equity curve
        equity = 1.0
        peak_equity = 1.0
        max_drawdown = 0.0

        for r in rows:
            pnl_pct = _to_float(r.get("pnl_pct"), 0.0)
            equity *= 1.0 + pnl_pct / 100.0
            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity
            if dd > max_drawdown:
                max_drawdown = dd

        return max_drawdown

    def calculate_kelly_position_size(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Calculate optimal position size using Kelly Criterion (inputs as floats)."""
        if win_rate <= 0.0 or avg_win <= 0.0 or avg_loss >= 0.0:
            return 0.02

        loss_rate = 1.0 - win_rate
        win_loss_ratio = avg_win / abs(avg_loss)

        kelly = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        kelly_adjusted = kelly * self.kelly_fraction

        return max(0.01, min(kelly_adjusted, self.max_position_size))

    def get_strategy_performance(self, strategy: str, days: int = 30) -> Dict:
        """Get recent performance for a strategy."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = select(
            "trades",
            columns="pnl_pct",
            filters={"strategy": f"eq.{strategy}", "status": "eq.closed", "opened_at": f"gte.{since}"},
            limit=20000,
        )

        wins = 0
        total = 0
        sum_win = 0.0
        sum_loss = 0.0

        for r in rows:
            pnl = _to_float(r.get("pnl_pct"), 0.0)
            total += 1
            if pnl > 0:
                wins += 1
                sum_win += pnl
            else:
                sum_loss += pnl

        win_rate = (wins / total) if total > 0 else 0.0
        avg_win = (sum_win / wins) if wins > 0 else 0.0
        avg_loss = (sum_loss / (total - wins)) if (total - wins) > 0 else 0.0

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": total,
        }

    def calculate_dynamic_position_size(
        self,
        strategy: str,
        signal_score: float,
        token_volatility: float = 0.5,
    ) -> float:
        """Calculate dynamic position size based on multiple factors."""
        perf = self.get_strategy_performance(strategy, days=30)

        if perf["total_trades"] < 10:
            base_size = 0.02
        else:
            base_size = self.calculate_kelly_position_size(
                perf["win_rate"],
                perf["avg_win"],
                perf["avg_loss"],
            )

        # Adjust for signal strength
        signal_factor = 0.5 + (signal_score - 0.5)

        # Adjust for volatility (inverse relationship)
        volatility_factor = 1.0 / (1.0 + token_volatility)

        position_size = base_size * signal_factor * volatility_factor

        return max(0.01, min(position_size, self.max_position_size))

    def check_risk_limits(self) -> Dict:
        """Check all risk limits and return status."""
        current_exposure = self.get_current_exposure()
        daily_pnl = self.get_daily_pnl()
        drawdown_7d = self.get_drawdown(7)
        drawdown_30d = self.get_drawdown(30)

        violations = []
        warnings = []

        if current_exposure >= self.max_total_exposure:
            violations.append(f"Total exposure {current_exposure:.1%} >= limit {self.max_total_exposure:.0%}")
        elif current_exposure >= self.max_total_exposure * 0.8:
            warnings.append(f"Total exposure {current_exposure:.1%} approaching limit")

        if daily_pnl <= -self.max_daily_loss:
            violations.append(f"Daily loss {daily_pnl:.1%} >= limit {self.max_daily_loss:.0%}")
        elif daily_pnl <= -self.max_daily_loss * 0.8:
            warnings.append(f"Daily loss {daily_pnl:.1%} approaching limit")

        if drawdown_7d >= self.max_drawdown_7d:
            violations.append(f"7-day drawdown {drawdown_7d:.1%} >= limit {self.max_drawdown_7d:.0%}")
        elif drawdown_7d >= self.max_drawdown_7d * 0.8:
            warnings.append(f"7-day drawdown {drawdown_7d:.1%} approaching limit")

        if drawdown_30d >= self.max_drawdown_30d:
            violations.append(f"30-day drawdown {drawdown_30d:.1%} >= limit {self.max_drawdown_30d:.0%}")
        elif drawdown_30d >= self.max_drawdown_30d * 0.8:
            warnings.append(f"30-day drawdown {drawdown_30d:.1%} approaching limit")

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_available_capital(self) -> float:
        """Calculate available capital for new positions."""
        return max(0.0, self.max_total_exposure - self.get_current_exposure())

    def can_open_position(self, position_size: float) -> Tuple[bool, str]:
        """Check if a new position can be opened."""
        risk_status = self.check_risk_limits()

        if risk_status["status"] == "CRITICAL":
            return False, f"Trading halted: {', '.join(risk_status['violations'])}"

        available = self.get_available_capital()
        if position_size > available:
            return False, f"Insufficient capital: need {position_size:.1%}, available {available:.1%}"

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



def main():
    manager = IntelligentRiskManager()
    print(manager.generate_risk_report())


if __name__ == "__main__":
    main()
