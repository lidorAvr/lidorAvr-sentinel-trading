#!/usr/bin/env python3
"""
Sprint 7 #4 — verify that all migrations/*.sql have been applied to Supabase.

Operator script. Run manually after a deploy:

    SUPABASE_URL=... SUPABASE_KEY=... python3 migrations/verify_migrations.py

Exits 0 if all expected columns/tables are present, 1 otherwise.
Designed to be safe to run repeatedly — it only reads schema metadata.

This is the fix for the Sprint 6 "audit_logger merged but migration 002 not
applied" silent gap that Compliance flagged in Meeting 7. The bot_health
check #14 (audit_log accessible) surfaces the same gap to the trader at
runtime; this script gives operators a clean pre-deploy check.

# How extensions register here

Each migration in this directory describes a table or columns it adds.
For now we hard-code the post-conditions in MIGRATIONS below. If we add
many more migrations, switch to a per-migration manifest file — but with
only two migrations today, that's over-engineering.
"""
from __future__ import annotations
import os
import sys


# Each entry: (migration filename, table, expected columns or None for "table exists")
MIGRATIONS: list[tuple[str, str, list[str] | None]] = [
    (
        "001_addon_phase2.sql",
        "trades",
        ["is_addon", "base_campaign_lot_id", "addon_sequence"],
    ),
    (
        "002_audit_log.sql",
        "audit_log",
        None,  # whole table is new — existence is the test
    ),
    (
        "003_add_user_id_to_trades.sql",
        "trades",
        ["user_id"],  # Phase A — additive user_id column
    ),
    (
        "004_add_user_id_to_audit_log.sql",
        "audit_log",
        ["user_id"],  # Phase A — additive user_id column
    ),
    (
        "005_create_open_tasks.sql",
        "open_tasks",
        None,  # whole table is new — existence is the test
    ),
]


def _connect():
    """Return a Supabase client built from SUPABASE_URL/SUPABASE_KEY env vars."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: `supabase` package not installed. "
              "Run `pip install -r requirements.txt`.", file=sys.stderr)
        sys.exit(2)

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set.",
              file=sys.stderr)
        sys.exit(2)
    return create_client(url, key)


def _check_table(sb, table: str) -> tuple[bool, str]:
    """Return (ok, message). The probe SELECT(id) LIMIT 0 doesn't read data,
    just exercises the schema."""
    try:
        sb.table(table).select("*").limit(1).execute()
        return True, f"table `{table}` exists"
    except Exception as e:
        return False, f"table `{table}` MISSING — {type(e).__name__}: {str(e)[:80]}"


def _check_column(sb, table: str, col: str) -> tuple[bool, str]:
    """Verify a column exists by selecting it. PostgREST returns a clear
    'column does not exist' error if missing."""
    try:
        sb.table(table).select(col).limit(1).execute()
        return True, f"  {table}.{col} ✓"
    except Exception as e:
        return False, f"  {table}.{col} MISSING — {str(e)[:80]}"


def main() -> int:
    sb = _connect()
    print("=== verify_migrations ===")
    all_ok = True

    for filename, table, cols in MIGRATIONS:
        print(f"\n[{filename}]")
        ok, msg = _check_table(sb, table)
        print(("✓ " if ok else "✗ ") + msg)
        if not ok:
            all_ok = False
            print(f"  → Apply migrations/{filename} in Supabase SQL Editor.")
            continue
        if cols:
            for c in cols:
                col_ok, col_msg = _check_column(sb, table, c)
                print(col_msg)
                if not col_ok:
                    all_ok = False

    print()
    if all_ok:
        print("✅ All migrations applied.")
        return 0
    print("🔴 Some migrations are missing — see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
