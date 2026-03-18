#!/usr/bin/env python3
"""
Live Trading Manager - Approval workflow for live trades.

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List

from supabase_client import is_available, select, update

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Risk limits (must match risk manager)
MAX_POSITION_SIZE_USD = 50.0
MAX_TOTAL_EXPOSURE_USD = 200.0
DAILY_LOSS_LIMIT_USD = 50.0
MIN_SIGNAL_SCORE = 0.7


class LiveTradingManager:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    @staticmethod
    def _to_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def check_risk_limits(self) -> Dict:
        """Check if trading is allowed under current risk conditions."""
        open_positions = select(
            "trades",
            columns="position_size_usd",
            filters={"status": "eq.open"},
            limit=5000,
        )
        total_exposure = sum(self._to_float(r.get("position_size_usd"), 0.0) for r in open_positions)

        # Daily PnL: sum pnl_usd for closed trades today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        closed_rows = select(
            "trades",
            columns="pnl_usd",
            filters={"status": "eq.closed", "closed_at": f"gte.{today_start}"},
            limit=5000,
        )
        daily_pnl = sum(self._to_float(r.get("pnl_usd"), 0.0) for r in closed_rows)

        can_trade = True
        reasons: List[str] = []

        if total_exposure >= MAX_TOTAL_EXPOSURE_USD:
            can_trade = False
            reasons.append(f"Total exposure ${total_exposure:.2f} >= ${MAX_TOTAL_EXPOSURE_USD}")

        if daily_pnl <= -DAILY_LOSS_LIMIT_USD:
            can_trade = False
            reasons.append(f"Daily loss ${abs(daily_pnl):.2f} >= ${DAILY_LOSS_LIMIT_USD}")

        return {
            "can_trade": can_trade,
            "reasons": reasons,
            "total_exposure": total_exposure,
            "daily_pnl": daily_pnl,
            "open_positions": len(open_positions),
            "available_capital": MAX_TOTAL_EXPOSURE_USD - total_exposure,
        }

    def get_pending_trades(self) -> List[Dict]:
        """Get trades that need execution approval."""
        rows = select(
            "trades",
            columns="id,strategy,token_symbol,token_address,chain,entry_price,position_size_usd,stop_loss,take_profit,signal_score,opened_at",
            filters={"status": "eq.pending_approval"},
            order="signal_score.desc,opened_at.desc",
            limit=20,
        )

        trades = []
        for row in rows:
            score = self._to_float(row.get("signal_score"), 0.0)
            if score < MIN_SIGNAL_SCORE:
                continue
            trades.append(
                {
                    "id": int(row.get("id")),
                    "strategy": row.get("strategy", ""),
                    "token_symbol": row.get("token_symbol", ""),
                    "token_address": row.get("token_address", ""),
                    "chain": row.get("chain", ""),
                    "entry_price": self._to_float(row.get("entry_price"), 0.0),
                    "position_size_usd": self._to_float(row.get("position_size_usd"), 0.0),
                    "stop_loss": self._to_float(row.get("stop_loss"), 0.0),
                    "take_profit": self._to_float(row.get("take_profit"), 0.0),
                    "signal_score": score,
                    "opened_at": row.get("opened_at"),
                }
            )
        return trades

    def approve_trade(self, trade_id: int) -> bool:
        """Approve a trade for execution."""
        update(
            "trades",
            {"status": "approved", "approved_at": datetime.now(timezone.utc).isoformat(), "approved_by": "manual"},
            filters={"id": f"eq.{trade_id}"},
        )
        logger.info(f"Trade {trade_id} approved")
        return True

    def reject_trade(self, trade_id: int, reason: str) -> bool:
        """Reject a trade."""
        update("trades", {"status": "rejected", "notes": reason}, filters={"id": f"eq.{trade_id}"})
        logger.info(f"Trade {trade_id} rejected: {reason}")
        return True

    def execute_approved_trades(self):
        """Execute all approved trades (placeholder for OKX swap integration)."""
        rows = select(
            "trades",
            columns="id,token_address,chain,position_size_usd,entry_price",
            filters={"status": "eq.approved"},
            order="opened_at.asc",
            limit=20,
        )

        if not rows:
            logger.info("No approved trades to execute")
            return

        logger.warning("OKX swap execution not implemented yet. Marking as failed for now.")
        for r in rows:
            tid = int(r.get("id"))
            update(
                "trades",
                {"status": "failed", "execution_error": "swap not implemented"},
                filters={"id": f"eq.{tid}"},
            )



def main():
    logger.info(f"=== Live Trading Manager - {datetime.now().isoformat()} ===")

    manager = LiveTradingManager()

    risk = manager.check_risk_limits()
    if not risk["can_trade"]:
        logger.warning(f"Risk limits violated: {', '.join(risk['reasons'])}")
        return

    pending = manager.get_pending_trades()
    logger.info(f"Pending trades: {len(pending)}")

    manager.execute_approved_trades()


if __name__ == "__main__":
    main()
