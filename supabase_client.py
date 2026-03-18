#!/usr/bin/env python3
"""
Unified Supabase client for ChainLens.

Routes all DB operations through the Supabase REST API (PostgREST),
bypassing IPv6-only direct connections.

Env vars:
  SUPABASE_URL         – e.g. https://xxx.supabase.co
  SUPABASE_SERVICE_KEY – service_role JWT (full access)
  DATABASE_URL         – fallback: direct psycopg2 connection
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_REST_AVAILABLE = bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(*, prefer: str = "") -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _base() -> str:
    return f"{SUPABASE_URL.rstrip('/')}/rest/v1"


# ── generic CRUD ──────────────────────────────────────────────

def insert(table: str, rows: List[Dict[str, Any]], *, upsert: bool = False) -> List[Dict]:
    """Insert rows via REST API. Returns inserted rows."""
    if not _REST_AVAILABLE:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    prefer = "return=representation"
    if upsert:
        prefer += ",resolution=merge-duplicates"
    resp = requests.post(
        f"{_base()}/{table}",
        headers=_headers(prefer=prefer),
        json=rows,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def select(
    table: str,
    *,
    columns: str = "*",
    filters: Optional[Dict[str, str]] = None,
    order: str = "",
    limit: int = 0,
) -> List[Dict]:
    """Select rows via REST API."""
    if not _REST_AVAILABLE:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    params: Dict[str, str] = {"select": columns}
    if filters:
        params.update(filters)
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)
    resp = requests.get(
        f"{_base()}/{table}",
        headers=_headers(),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def update(
    table: str,
    data: Dict[str, Any],
    *,
    filters: Dict[str, str],
) -> List[Dict]:
    """Update rows matching filters."""
    if not _REST_AVAILABLE:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    resp = requests.patch(
        f"{_base()}/{table}",
        headers=_headers(prefer="return=representation"),
        params=filters,
        json=data,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def rpc(fn: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Call a Postgres function via RPC."""
    if not _REST_AVAILABLE:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    resp = requests.post(
        f"{_base()}/rpc/{fn}",
        headers=_headers(),
        json=params or {},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── convenience helpers ───────────────────────────────────────

def insert_signal(
    source: str,
    token_symbol: str,
    token_address: str,
    chain: str,
    signal_score: float,
    raw_data: Any = None,
) -> Dict:
    """Insert a single signal row."""
    row = {
        "source": source,
        "token_symbol": token_symbol,
        "token_address": token_address,
        "chain": chain,
        "signal_score": round(signal_score, 2),
        "raw_data": json.dumps(raw_data) if raw_data else "{}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = insert("signals", [row])
    return result[0] if result else row


def get_recent_signals(hours: int = 2, source: Optional[str] = None) -> List[Dict]:
    """Get signals from the last N hours."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    filters: Dict[str, str] = {"timestamp": f"gte.{cutoff}"}
    if source:
        filters["source"] = f"eq.{source}"
    return select("signals", order="timestamp.desc", filters=filters, limit=500)


def insert_trade(trade: Dict[str, Any]) -> Dict:
    """Insert a trade row."""
    result = insert("trades", [trade])
    return result[0] if result else trade


def get_open_trades() -> List[Dict]:
    """Get all open trades."""
    return select("trades", filters={"status": "eq.open"}, order="opened_at.desc")


def update_trade(trade_id: int, data: Dict[str, Any]) -> List[Dict]:
    """Update a trade by ID."""
    return update("trades", data, filters={"id": f"eq.{trade_id}"})


def is_available() -> bool:
    """Check if Supabase REST API is configured."""
    return _REST_AVAILABLE
