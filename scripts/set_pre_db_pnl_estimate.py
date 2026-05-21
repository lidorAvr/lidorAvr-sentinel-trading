#!/usr/bin/env python3
"""
F-YTD calibration helper — set or display the `pre_db_realized_pnl_estimate`
field in sentinel_config.json.

Why this exists:
  Sentinel's Supabase `trades` table only carries trades from the
  deployment date forward. Pre-deploy closed campaigns have no row,
  so the raw reconciliation gap (NAV − deposits − DB-realized − open)
  is overstated by the missing pre-deploy realized PnL. The founder
  manually estimates that missing PnL and sets it here once; the
  classifier subtracts it from the raw gap before banding, so future
  /portfolio refreshes report the RESIDUAL gap — any new growth is a
  genuine drift worth investigating.

  See docs/DATA_CONTRACTS.md "Data history scope (YTD-bound)" for
  the full contract.

Usage:
  python3 scripts/set_pre_db_pnl_estimate.py --show
      Display current value + last-known config snapshot.
  python3 scripts/set_pre_db_pnl_estimate.py <value>
      Set the field to <value>. Signed: positive = pre-deploy GAINS;
      negative = pre-deploy LOSSES.
      Example to neutralise the 21/05/2026 founder's screenshot gap:
        python3 scripts/set_pre_db_pnl_estimate.py 495.67
  python3 scripts/set_pre_db_pnl_estimate.py --clear
      Remove the field entirely (returns to default-0 behaviour).

Safety:
  - Loads the JSON, validates structure, writes back atomically (temp +
    rename) so a crash mid-write cannot corrupt the file.
  - Preserves existing indentation + key ordering as far as json.dump
    allows.
  - Refuses to run if sentinel_config.json doesn't exist (no
    auto-create — the file is part of the deployment setup).
  - Prints a before/after diff so the operator sees exactly what
    changed.

Where the file lives:
  Default: `./sentinel_config.json` in the current working directory.
  Override via env var: SENTINEL_CONFIG_PATH=/app/sentinel_config.json
  (handy for `docker exec` invocations from a different CWD).

Exit codes:
  0  success
  1  file not found / malformed JSON / write failure
  2  invalid value argument (non-numeric)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_FIELD_NAME = "pre_db_realized_pnl_estimate"
_DEFAULT_PATH = "sentinel_config.json"
_ENV_OVERRIDE = "SENTINEL_CONFIG_PATH"


def _resolve_config_path() -> Path:
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    return Path(_DEFAULT_PATH)


def _load(path: Path) -> dict:
    if not path.exists():
        print(f"❌ Config file not found: {path}", file=sys.stderr)
        print(
            f"   Set {_ENV_OVERRIDE} env var if the file lives elsewhere "
            f"(e.g. inside a docker container).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ Malformed JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON via temp-file-and-rename so a crash mid-write cannot
    corrupt sentinel_config.json. The rename is atomic on POSIX
    filesystems (same directory)."""
    parent = path.parent.resolve()
    fd, tmp_name = tempfile.mkstemp(prefix=".sentinel_config_", suffix=".tmp",
                                    dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup of the temp file before re-raising.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _fmt_value(v: Any) -> str:
    if v is None:
        return "(unset — defaults to 0.0)"
    try:
        return f"${float(v):+,.2f}"
    except (TypeError, ValueError):
        return repr(v)


def _show(path: Path) -> int:
    data = _load(path)
    current = data.get(_FIELD_NAME)
    print(f"Config: {path}")
    print(f"  {_FIELD_NAME}: {_fmt_value(current)}")
    print()
    print("Reference fields (read-only):")
    for k in ("total_deposited", "risk_pct_input", "nav_source"):
        if k in data:
            print(f"  {k}: {data[k]}")
    print()
    print("To set a value (e.g. neutralise a $495.67 gap):")
    print(f"  python3 {sys.argv[0]} 495.67")
    print()
    print("To clear:")
    print(f"  python3 {sys.argv[0]} --clear")
    return 0


def _parse_value(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        print(f"❌ Invalid value: {raw!r} — must be a number "
              f"(e.g. 495.67 or -200.0).", file=sys.stderr)
        sys.exit(2)


def _set(path: Path, value: float) -> int:
    data = _load(path)
    before = data.get(_FIELD_NAME)
    data[_FIELD_NAME] = round(float(value), 2)
    _atomic_write(path, data)
    print(f"✅ Updated {path}")
    print(f"   Before: {_fmt_value(before)}")
    print(f"   After:  {_fmt_value(data[_FIELD_NAME])}")
    print()
    print("Next /portfolio refresh will show the band softened by the new "
          "disclaimer. The raw gap stays visible in the breakdown for "
          "forensic comparison.")
    return 0


def _clear(path: Path) -> int:
    data = _load(path)
    if _FIELD_NAME not in data:
        print(f"ℹ️  {_FIELD_NAME} already absent — nothing to clear.")
        return 0
    before = data.pop(_FIELD_NAME)
    _atomic_write(path, data)
    print(f"✅ Cleared {_FIELD_NAME} (was: {_fmt_value(before)})")
    print("   Behaviour returns to byte-identical default-0.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set/show/clear pre_db_realized_pnl_estimate in "
                    "sentinel_config.json.",
        epilog="See docs/DATA_CONTRACTS.md 'Data history scope' for "
               "the full contract.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true",
                       help="Display current value + reference fields.")
    group.add_argument("--clear", action="store_true",
                       help="Remove the field (returns to default-0).")
    group.add_argument("value", nargs="?", type=str, default=None,
                       help="Numeric value (signed: positive = "
                            "pre-deploy gains; negative = losses).")

    args = parser.parse_args()
    path = _resolve_config_path()

    if args.show:
        return _show(path)
    if args.clear:
        return _clear(path)
    if args.value is None:
        # argparse should have caught this via mutually_exclusive required.
        parser.print_help()
        return 1
    return _set(path, _parse_value(args.value))


if __name__ == "__main__":
    sys.exit(main())
