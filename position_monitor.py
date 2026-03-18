#!/usr/bin/env python3
"""
Position Monitor - Monitor open positions and execute stop-loss/take-profit
Based on Jim Simons' strict risk management principles.

Uses Supabase REST as single data plane.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from dotenv import load_dotenv
from price_fetcher import get_price
from supabase_client import insert, is_available, select, update

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Config:
    """Position monitoring configuration."""

    MAX_HOLDING_HOURS = 72  # Maximum time to hold a position
    MAX_PRICE_RETRIES = 3


class PositionMonitor:
    def __init__(self):
        if not is_available():
            raise RuntimeError("Supabase REST not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    @staticmethod
    def _to_float(v, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_ts(v):
        if isinstance(v, datetime):
            return v
        s = str(v or "")
        if not s:
            return datetime.now(timezone.utc)
        # PostgREST may return trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.now(timezone.utc)

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions."""
        rows = select(
            "trades",
            columns="id,strategy,token_symbol,token_address,chain,entry_price,quantity,stop_loss,take_profit,opened_at,is_paper",
            filters={"status": "eq.open"},
            order="opened_at.desc",
            limit=1000,
        )

        positions = []
        for row in rows:
            positions.append(
                {
                    "id": int(row.get("id")),
                    "strategy": row.get("strategy", ""),
                    "token_symbol": row.get("token_symbol", ""),
                    "token_address": row.get("token_address", ""),
                    "chain": row.get("chain", ""),
                    "entry_price": self._to_float(row.get("entry_price"), 0.0),
                    "quantity": self._to_float(row.get("quantity"), 0.0),
                    "stop_loss": self._to_float(row.get("stop_loss"), 0.0),
                    "take_profit": self._to_float(row.get("take_profit"), 0.0),
                    "opened_at": self._parse_ts(row.get("opened_at")),
                    "is_paper": bool(row.get("is_paper", True)),
                }
            )

        return positions

    def get_current_price(self, token_symbol: str, token_address: str, chain: str) -> float:
        """
        Get current token price from OKX first.

        Raises:
            RuntimeError: If price cannot be fetched
        """
        for attempt in range(Config.MAX_PRICE_RETRIES):
            price = get_price(chain=chain, token_address=token_address, symbol=token_symbol)
            if price and price > 0:
                return float(price)

            logger.warning(f"Price fetch attempt {attempt + 1} failed, retrying...")

        raise RuntimeError(
            f"Cannot fetch price for {token_symbol} after {Config.MAX_PRICE_RETRIES} attempts. "
            "Manual intervention required."
        )

    @staticmethod
    def check_stop_loss(position: Dict, current_price: float) -> bool:
        """Check if stop-loss is triggered."""
        return current_price <= position["stop_loss"]

    @staticmethod
    def check_take_profit(position: Dict, current_price: float) -> bool:
        """Check if take-profit is triggered."""
        return current_price >= position["take_profit"]

    @staticmethod
    def check_time_stop(position: Dict, max_hours: int = None) -> bool:
        """Check if position should be closed due to time limit."""
        if max_hours is None:
            max_hours = Config.MAX_HOLDING_HOURS

        now = datetime.now(timezone.utc)
        opened_at = position["opened_at"]

        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        age = now - opened_at
        return age > timedelta(hours=max_hours)

    def close_position(self, position: Dict, exit_price: float, reason: str):
        """Close a position and record P&L."""
        entry_price = position["entry_price"]
        quantity = position["quantity"]

        pnl_usd = (exit_price - entry_price) * quantity
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0

        update(
            "trades",
            {
                "exit_price": exit_price,
                "pnl_usd": pnl_usd,
                "pnl_pct": pnl_pct,
                "status": "closed",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "notes": reason,
            },
            filters={"id": f"eq.{position['id']}"},
        )

        insert(
            "risk_events",
            [
                {
                    "event_type": reason,
                    "trade_id": position["id"],
                    "description": f"Position closed: {reason}",
                    "action_taken": f"Exit at {exit_price}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

        logger.info(f"Closed {position['token_symbol']}: {pnl_pct:+.2f}% ({reason})")

    def monitor_positions(self):
        """Main monitoring loop."""
        positions = self.get_open_positions()

        if not positions:
            logger.info("No open positions")
            return

        logger.info(f"Monitoring {len(positions)} open positions...")

        for pos in positions:
            try:
                current_price = self.get_current_price(pos["token_symbol"], pos["token_address"], pos["chain"])
            except RuntimeError as e:
                logger.error(f"Cannot monitor {pos['token_symbol']}: {e}")
                continue

            if self.check_stop_loss(pos, current_price):
                self.close_position(pos, current_price, "stop_loss")
                continue

            if self.check_take_profit(pos, current_price):
                self.close_position(pos, current_price, "take_profit")
                continue

            if self.check_time_stop(pos):
                self.close_position(pos, current_price, "time_stop")
                continue

            pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100 if pos["entry_price"] > 0 else 0.0
            status = "paper" if pos["is_paper"] else "live"
            logger.info(f"  {pos['token_symbol']} [{status}]: {pnl_pct:+.2f}% (open)")


def main():
    logger.info(f"=== Position Monitor - {datetime.now().isoformat()} ===")

    monitor = PositionMonitor()
    monitor.monitor_positions()


if __name__ == "__main__":
    main()
