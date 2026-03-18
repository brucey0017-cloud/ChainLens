#!/usr/bin/env python3
"""
Database adapter for ChainLens.

Priority:
  1. Supabase REST API (SUPABASE_URL + SUPABASE_SERVICE_KEY) — works everywhere
  2. Direct psycopg2 (DATABASE_URL) — needs IPv4 or IPv6 connectivity

All modules should import from here instead of using psycopg2 directly.
"""

import os

# Try Supabase REST first
try:
    from supabase_client import is_available as _rest_ok
    SUPABASE_REST = _rest_ok()
except ImportError:
    SUPABASE_REST = False

# Try psycopg2 fallback
try:
    import psycopg2
    DB_URL = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    PSYCOPG2_OK = bool(DB_URL)
except ImportError:
    PSYCOPG2_OK = False
    DB_URL = ""


def get_mode() -> str:
    """Return current DB mode: 'rest', 'psycopg2', or 'none'."""
    if SUPABASE_REST:
        return "rest"
    if PSYCOPG2_OK:
        return "psycopg2"
    return "none"


def get_connection():
    """Get a psycopg2 connection (only for legacy code paths)."""
    if not PSYCOPG2_OK:
        raise RuntimeError("No DATABASE_URL configured and Supabase REST not available")
    return psycopg2.connect(DB_URL)


def print_status():
    """Print DB connectivity status."""
    mode = get_mode()
    if mode == "rest":
        url = os.getenv("SUPABASE_URL", "")
        print(f"  DB mode: Supabase REST API ({url[:40]}...)")
    elif mode == "psycopg2":
        # Mask password in URL
        safe = DB_URL.split("@")[-1] if "@" in DB_URL else DB_URL[:40]
        print(f"  DB mode: psycopg2 direct ({safe})")
    else:
        print("  DB mode: NONE — no database configured!")
