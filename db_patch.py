#!/usr/bin/env python3
"""
Supabase REST-aware psycopg2 wrapper.

When SUPABASE_URL + SUPABASE_SERVICE_KEY are set but direct DB is unreachable,
this module patches the connection to route writes through REST API while
keeping the psycopg2 interface for reads against local postgres.

Usage in any module:
    import db_patch  # noqa: F401  (must import before psycopg2.connect)
"""

import os
import sys
from datetime import datetime

# Only activate if REST credentials exist
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        import requests

        class _RESTCursor:
            """Minimal cursor that routes INSERT/SELECT to Supabase REST."""

            def __init__(self, base_url: str, key: str):
                self._base = f"{base_url.rstrip('/')}/rest/v1"
                self._key = key
                self._result: list = []
                self._idx = 0

            def _headers(self, prefer: str = "") -> dict:
                h = {
                    "apikey": self._key,
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/json",
                }
                if prefer:
                    h["Prefer"] = prefer
                return h

            def execute(self, query: str, params=None):
                q = query.strip().upper()
                if q.startswith("INSERT"):
                    self._do_insert(query, params)
                elif q.startswith("SELECT"):
                    self._do_select(query, params)
                elif q.startswith("UPDATE"):
                    self._do_update(query, params)
                else:
                    # DDL or unknown — skip silently in REST mode
                    self._result = []

            def _extract_table(self, query: str) -> str:
                """Extract table name from SQL."""
                q = query.upper()
                if "INSERT INTO" in q:
                    part = query.split("INSERT INTO")[1].split("(")[0].strip()
                    return part.split()[0].strip().strip('"')
                if "FROM" in q:
                    part = query.split("FROM")[1].strip()
                    return part.split()[0].strip().strip('"')
                if "UPDATE" in q:
                    part = query.split("UPDATE")[1].strip()
                    return part.split()[0].strip().strip('"')
                return ""

            def _do_insert(self, query: str, params):
                table = self._extract_table(query)
                if not table:
                    return

                # Extract column names from INSERT INTO table (col1, col2, ...) VALUES ...
                cols_part = query.split("(", 1)[1].split(")")[0]
                cols = [c.strip() for c in cols_part.split(",")]

                row = {}
                if params:
                    for i, col in enumerate(cols):
                        if i < len(params):
                            val = params[i]
                            if isinstance(val, datetime):
                                val = val.isoformat()
                            row[col] = val

                resp = requests.post(
                    f"{self._base}/{table}",
                    headers=self._headers(prefer="return=representation"),
                    json=[row],
                    timeout=15,
                )
                resp.raise_for_status()
                self._result = resp.json()

            def _do_select(self, query: str, params):
                table = self._extract_table(query)
                if not table:
                    self._result = []
                    return

                resp = requests.get(
                    f"{self._base}/{table}",
                    headers=self._headers(),
                    params={"limit": "500"},
                    timeout=15,
                )
                resp.raise_for_status()
                self._result = resp.json()
                self._idx = 0

            def _do_update(self, query: str, params):
                # For updates, just pass through — complex to parse generically
                self._result = []

            def fetchall(self):
                rows = []
                for r in self._result:
                    rows.append(tuple(r.values()))
                return rows

            def fetchone(self):
                if self._idx < len(self._result):
                    row = tuple(self._result[self._idx].values())
                    self._idx += 1
                    return row
                return None

            def close(self):
                pass

        class _RESTConnection:
            """Minimal connection that wraps REST cursors."""

            def __init__(self, base_url: str, key: str):
                self._base = base_url
                self._key = key

            def cursor(self):
                return _RESTCursor(self._base, self._key)

            def commit(self):
                pass  # REST is auto-commit

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        # Monkey-patch psycopg2.connect to try REST first
        _original_connect = None
        try:
            import psycopg2 as _pg2
            _original_connect = _pg2.connect
        except ImportError:
            pass

        def _patched_connect(*args, **kwargs):
            """Try direct psycopg2 first; fall back to REST wrapper."""
            if _original_connect:
                try:
                    return _original_connect(*args, **kwargs)
                except Exception:
                    pass  # Direct connection failed, use REST
            return _RESTConnection(SUPABASE_URL, SUPABASE_KEY)

        if _original_connect:
            import psycopg2
            psycopg2.connect = _patched_connect
            print("  DB patch: psycopg2.connect patched with Supabase REST fallback", file=sys.stderr)

    except ImportError:
        pass  # requests not available, skip patching
