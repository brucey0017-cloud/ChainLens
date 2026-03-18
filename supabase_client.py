#!/usr/bin/env python3
"""
Supabase REST client (minimal).

Requirements:
- SUPABASE_URL
- SUPABASE_SERVICE_KEY (service role, not anon)
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE_URL = os.getenv("SUPABASE_URL", "")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def is_available() -> bool:
    """Check if Supabase REST credentials are configured."""
    return bool(BASE_URL and SERVICE_KEY)


def _headers(prefer: str = "") -> Dict[str, str]:
    h = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _build_filters(params: Dict[str, str], filters: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not filters:
        return params
    for k, v in filters.items():
        # PostgREST filter syntax: key=eq.value / gte.value / in.(a,b)
        params[k] = v
    return params


def select(
    table: str,
    columns: str = "*",
    filters: Optional[Dict[str, str]] = None,
    order: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Perform a SELECT query via PostgREST."""
    if not is_available():
        raise RuntimeError("Supabase REST not configured")

    params = {"select": columns}
    params = _build_filters(params, filters)
    if order:
        params["order"] = order
    if limit:
        params["limit"] = str(limit)

    qs = urllib.parse.urlencode(params, safe="*,.()")
    url = f"{BASE_URL}/rest/v1/{table}?{qs}"

    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, list):
        return []
    return data


def insert(table: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert rows and return inserted records."""
    if not is_available():
        raise RuntimeError("Supabase REST not configured")

    if not rows:
        return []

    # Ensure JSON serialization for complex columns; convert Decimal/datetime
    sanitized = []
    for r in rows:
        s = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)):
                s[k] = json.dumps(v)
            elif hasattr(v, "isoformat"):
                s[k] = v.isoformat()
            else:
                s[k] = v
        sanitized.append(s)

    url = f"{BASE_URL}/rest/v1/{table}"
    body = json.dumps(sanitized).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=_headers(prefer="return=representation"),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, list):
        return []
    return data


def update(
    table: str,
    updates: Dict[str, Any],
    filters: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Update rows matching filters and return updated records."""
    if not is_available():
        raise RuntimeError("Supabase REST not configured")

    params: Dict[str, str] = {}
    params = _build_filters(params, filters)

    qs = urllib.parse.urlencode(params, safe="*,.()")
    url = f"{BASE_URL}/rest/v1/{table}?{qs}"

    # Ensure JSON serialization
    payload = {}
    for k, v in updates.items():
        if isinstance(v, (dict, list)):
            payload[k] = json.dumps(v)
        elif hasattr(v, "isoformat"):
            payload[k] = v.isoformat()
        else:
            payload[k] = v

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers=_headers(prefer="return=representation"),
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, list):
        return []
    return data


def delete(table: str, filters: Optional[Dict[str, str]] = None) -> None:
    """Delete rows matching filters."""
    if not is_available():
        raise RuntimeError("Supabase REST not configured")

    params: Dict[str, str] = {}
    params = _build_filters(params, filters)

    qs = urllib.parse.urlencode(params, safe="*,.()")
    url = f"{BASE_URL}/rest/v1/{table}?{qs}"

    req = urllib.request.Request(
        url,
        headers=_headers(prefer="return=representation"),
        method="DELETE",
    )
    urllib.request.urlopen(req, timeout=30)
