"""
report_snapshot_store.py — persist and load period KPI snapshots as JSON.
One file per period at /app/report_state/snapshots/<type>/<YYYY-MM-DD>.json.
Enables WoW / MoM trend comparisons without a database.
"""
import math, os, json
from datetime import datetime
from typing import Optional


def _safe_float(v):
    """Replace non-finite floats (inf/nan) with None for JSON serialization."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v

_BASE_DIR = "/app/report_state/snapshots"


def save(period_type: str, period_start: datetime, period_end: datetime,
         analytics: dict, account_state: dict, report_file_path: str = "",
         open_book: Optional[dict] = None) -> None:
    """Persist a signed period snapshot. Idempotent — overwrites same-period file.

    Sprint-18: `open_book` is an ADDITIVE optional kwarg (default None ⇒ the
    snapshot is byte-identical to today's — old readers, `load_recent`,
    `load_previous` keep working unchanged; NO migration, single-user
    byte-identical per Hyperscaler addendum). When supplied, an additive
    `open_marks` key is written, `_safe_float`-guarded for inf/nan. Old
    snapshots simply lack `open_marks` ⇒ `snap.get("open_marks")` is None ⇒
    next-run delta = baseline-pending token (report_open_book.compute_mark_delta).
    The open-book floating PnL is REUSED verbatim from
    get_open_positions_campaign — no new math is introduced here.
    """
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
        "profit_factor":         _safe_float(analytics.get("profit_factor", 0)),
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
    # Additive open-marks (Sprint-18 §4 / Mark §4) — written ONLY when an
    # open_book is supplied. Pure capture of floats already produced by
    # get_open_positions_campaign; no realized KPI key is affected (the block
    # above is untouched). ALGO segregated and observation-only here too.
    if open_book and open_book.get("open_book_present"):
        t = open_book.get("open_book_totals", {})
        per_symbol = []
        for p in (open_book.get("open_book_disc", [])
                  + open_book.get("open_book_algo", [])):
            per_symbol.append({
                "symbol":       p.get("symbol"),
                "qty":          _safe_float(p.get("qty")),
                "price":        _safe_float(p.get("current")),
                "floating_pnl": _safe_float(p.get("floating_pnl")),
                "structure_r":  _safe_float(p.get("structure_r")),
                "account_r":    _safe_float(p.get("account_r")),
                "is_algo":      bool(p.get("is_algo")),
            })
        snapshot["open_marks"] = {
            "captured_at":         datetime.now().isoformat(),
            "n_disc":              int(t.get("n_disc", 0)),
            "n_algo":              int(t.get("n_algo", 0)),
            "floating_pnl_disc":   _safe_float(t.get("floating_pnl_disc", 0.0)),
            "floating_pnl_algo":   _safe_float(t.get("floating_pnl_algo", 0.0)),
            "open_exposure_pct":   _safe_float(t.get("exposure_pct_total", 0.0)),
            "open_total_floating": _safe_float(
                (t.get("floating_pnl_disc", 0.0) or 0.0)
                + (t.get("floating_pnl_algo", 0.0) or 0.0)
            ),
            "marks_source":        open_book.get("open_book_data_source", ""),
            "per_symbol":          per_symbol,
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
