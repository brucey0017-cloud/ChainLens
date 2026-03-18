#!/usr/bin/env python3
"""Quick Supabase connectivity test for CI."""
import os, sys
try:
    import psycopg2
except ImportError:
    print("psycopg2 not installed, skipping")
    sys.exit(0)

db_url = os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")
if not db_url:
    print("No SUPABASE_DATABASE_URL set, skipping")
    sys.exit(0)

try:
    conn = psycopg2.connect(db_url, connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT version()")
    print(f"Connected: {cur.fetchone()[0][:60]}")
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"Public tables ({len(tables)}): {tables}")
    conn.close()
    print("OK")
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)
