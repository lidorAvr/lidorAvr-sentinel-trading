"""
report_snapshot_store.py — persist and load period KPI snapshots as JSON.
One file per period at /app/report_state/snapshots/<type>/<YYYY-MM-DD>.json.
Enables WoW / MoM trend comparisons without a database.
"""
import os, json
from datetime import datetime
from typing import Optional

_BASE_DIR = "/app/report_state/snapshots"


def save(period_type: str, period_start: datetime, period_end: datetime,
         analytics: dict, account_state: dict, report_file_path: str = "") -> None:
    """Persist a signed period snapshot. Idempotent — overwrites same-period file."""
    path = _snapshot_path(period_type, period_start)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    snapshot = {
        "period_type":           period_type,
        "period_start":          period_start.isoformat(),
        "period_end":            period_end.isoformat(),
        "generated_at":          datetime.now().isoformat(),
        "nav_start":             account_state.get("nav"),
        "nav_source":            account_state.get("nav_source"),
        "freshness":             account_state.get("freshness"),
        "risk_pct_input":        account_state.get("risk_pct_input"),
        "report_file_path":      report_file_path,
        # KPIs
        "campaigns_closed":      analytics.get("campaigns_closed", 0),
        "win_rate":              analytics.get("win_rate", 0),
        "expectancy_r":          analytics.get("expectancy_r", 0),
        "profit_factor":         analytics.get("profit_factor", 0),
        "avg_win_r":             analytics.get("avg_win_r", 0),
        "avg_loss_r":            analytics.get("avg_loss_r", 0),
        "total_r_net":           analytics.get("total_r_net", 0),
        "realized_pnl":          analytics.get("realized_pnl", 0),
        "missing_stop_rate":     analytics.get("missing_stop_rate", 0),
        "oversized_rate":        analytics.get("oversized_rate", 0),
        "avg_r_per_day":         analytics.get("avg_r_per_day", 0),
        "risk_adherence_rate":   analytics.get("risk_adherence_rate"),
        "dev_score":             analytics.get("dev_score"),
        "setup_breakdown":       analytics.get("setup_breakdown", {}),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def load_recent(period_type: str, n: int = 4) -> list:
    """
    Load the n most recent snapshots for period_type ("weekly" or "monthly").
    Returns list of dicts, newest first. Returns [] if none found.
    """
    folder = _folder(period_type)
    if not os.path.isdir(folder):
        return []
    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".json")],
        reverse=True,
    )[:n]
    result = []
    for fname in files:
        try:
            with open(os.path.join(folder, fname), encoding="utf-8") as f:
                result.append(json.load(f))
        except Exception:
            pass
    return result


def load_previous(period_type: str, period_start: datetime) -> Optional[dict]:
    """Load the snapshot immediately before period_start (for WoW/MoM comparison)."""
    recent = load_recent(period_type, n=10)
    key = period_start.isoformat()
    for snap in recent:
        if snap.get("period_start") < key:
            return snap
    return None


# ── internals ──────────────────────────────────────────────────────────────────

def _folder(period_type: str) -> str:
    return os.path.join(_BASE_DIR, period_type)


def _snapshot_path(period_type: str, period_start: datetime) -> str:
    date_str = period_start.strftime("%Y-%m-%d")
    return os.path.join(_folder(period_type), f"{date_str}.json")
