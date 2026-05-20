"""
RISK-1c — admin-triggered retroactive backfill of the `locked_entry_price`
column for every legacy BUY row that the RISK-1b forward-capture wizard
never touched.

Design goals (matches RISK-1a/b safety contract):
  - Idempotent: re-running after a partial batch (or interrupt) safely
    resumes — every per-row lock is itself idempotent
    (supabase_repository.lock_entry_from_trade_price returns False for
    already-locked rows without raising or re-auditing).
  - Fail-soft: a single broker-anomalous row (price None / 0 / negative /
    non-numeric) is logged + skipped; the batch continues.
  - Two-step UI: preview → confirm → run. Never auto-mass-mutates Supabase
    on a single button press (CLAUDE.md Hard Constraint: Supabase
    mutations must be intentional and traceable).
  - Single source of truth: this module reuses
    supabase_repository.lock_entry_from_trade_price (with
    method='backfill') exactly — no second copy of the per-row lock /
    audit logic. The per-row audit rows (ACTION_AT_ENTRY_LOCK /
    ACTION_AT_ENTRY_SKIP) come from there; this module adds ONE
    batch-level audit row (ACTION_AT_ENTRY_BACKFILL_RUN) capturing the
    operator chat_id + summary counts.

Pure / read-only with respect to engine_core, telebot, bot_core — safe to
import from any layer (tests, CLI, the Telegram handler). The ONLY
side-effects are the per-row Supabase UPDATEs that the existing repo
helper performs, plus the one batch-level audit row.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

import audit_logger
import supabase_repository as repo


def _classify_row(row: dict) -> str:
    """Return one of: 'lockable' / 'anomalous_price'.

    Mirrors the validation that lock_entry_from_trade_price will apply
    again at lock-time — duplicated here ONLY for the preview screen, so
    the operator can see ahead of time how many rows will lock vs skip.
    The actual lock decision still happens inside the repo helper; preview
    is advisory.
    """
    price = row.get("price")
    try:
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_f = None
    if price_f is None or price_f <= 0:
        return "anomalous_price"
    return "lockable"


def preview_missing_locks(sb) -> dict:
    """Read-only preview of what RISK-1c would lock if run right now.

    Returns:
      {
        "total":             int,  # all BUY rows where locked_entry_price IS NULL
        "lockable_count":    int,  # rows whose `price` is a positive number
        "anomalous_count":   int,  # rows whose `price` is None/0/negative/non-numeric
        "by_symbol":         {symbol: lockable_count, ...},  # only lockable rows
        "anomalous_symbols": sorted list[str],
      }

    Defensive: when supabase_repository.get_trades_missing_lock raises (e.g.
    Supabase unreachable), returns the zero-shape so the Telegram preview
    can render an honest "אין נתון" state without crashing.
    """
    try:
        rows = repo.get_trades_missing_lock(sb)
    except Exception:
        return {
            "total": 0,
            "lockable_count": 0,
            "anomalous_count": 0,
            "by_symbol": {},
            "anomalous_symbols": [],
            "fetch_error": True,
        }

    by_symbol: dict = defaultdict(int)
    anomalous_symbols: set = set()
    lockable_count = 0
    anomalous_count = 0

    for row in rows:
        cls = _classify_row(row)
        sym = str(row.get("symbol") or "").strip() or "?"
        if cls == "lockable":
            lockable_count += 1
            by_symbol[sym] += 1
        else:
            anomalous_count += 1
            anomalous_symbols.add(sym)

    return {
        "total":             len(rows),
        "lockable_count":    lockable_count,
        "anomalous_count":   anomalous_count,
        "by_symbol":         dict(sorted(by_symbol.items())),
        "anomalous_symbols": sorted(anomalous_symbols),
        "fetch_error":       False,
    }


def run_backfill(sb, *, chat_id: Optional[int] = None) -> dict:
    """Lock every BUY row whose `locked_entry_price` is currently NULL.

    Per-row behaviour delegates to ``repo.lock_entry_from_trade_price`` with
    ``method='backfill'`` — same anomaly handling, same audit-log rows, same
    idempotency contract as the RISK-1b wizard call site. The only
    additions here are batch-level: one ``ACTION_AT_ENTRY_BACKFILL_RUN``
    audit row recording the operator + summary counts.

    Returns:
      {
        "locked":           int,  # newly-locked rows in this batch
        "skipped_anomaly":  int,  # rows skipped on price None/0/neg/non-numeric
        "skipped_other":    int,  # rows where the helper returned False for
                                  # any other reason (already-locked / no row)
        "by_symbol":        {symbol: locked_count, ...},
        "total_processed":  int,
        "fetch_error":      bool,
      }

    Never raises — per-row failures are absorbed by the helper's own
    try/except; a fetch-level failure returns the zero-shape with
    ``fetch_error=True``.
    """
    try:
        rows = repo.get_trades_missing_lock(sb)
    except Exception:
        # Audit the operator's attempt even when the fetch failed — the
        # founder pressed "confirm"; the record matters.
        audit_logger.log_action(
            sb, audit_logger.ACTION_AT_ENTRY_BACKFILL_RUN,
            chat_id=chat_id,
            metadata={
                "outcome": "fetch_error",
                "locked":           0,
                "skipped_anomaly":  0,
                "skipped_other":    0,
                "total_processed":  0,
            },
        )
        return {
            "locked":          0,
            "skipped_anomaly": 0,
            "skipped_other":   0,
            "by_symbol":       {},
            "total_processed": 0,
            "fetch_error":     True,
        }

    locked = 0
    skipped_anomaly = 0
    skipped_other = 0
    by_symbol: dict = defaultdict(int)

    for row in rows:
        trade_id = row.get("trade_id")
        sym = str(row.get("symbol") or "").strip() or "?"
        if not trade_id:
            skipped_other += 1
            continue

        # Pre-classify so the batch summary can distinguish anomalous-price
        # skips from other skip reasons. The helper itself will re-validate
        # and write the canonical ACTION_AT_ENTRY_SKIP audit row.
        pre_class = _classify_row(row)

        success = repo.lock_entry_from_trade_price(
            sb, str(trade_id),
            chat_id=chat_id,
            method="backfill",
        )
        if success:
            locked += 1
            by_symbol[sym] += 1
        elif pre_class == "anomalous_price":
            skipped_anomaly += 1
        else:
            skipped_other += 1

    audit_logger.log_action(
        sb, audit_logger.ACTION_AT_ENTRY_BACKFILL_RUN,
        chat_id=chat_id,
        metadata={
            "outcome":         "success",
            "locked":          locked,
            "skipped_anomaly": skipped_anomaly,
            "skipped_other":   skipped_other,
            "total_processed": len(rows),
        },
    )

    return {
        "locked":          locked,
        "skipped_anomaly": skipped_anomaly,
        "skipped_other":   skipped_other,
        "by_symbol":       dict(sorted(by_symbol.items())),
        "total_processed": len(rows),
        "fetch_error":     False,
    }


# ── Formatters (Hebrew, RTL) ─────────────────────────────────────────────────
# Module-local, NOT in telegram_formatters.py — these are operator-facing
# admin outputs (RISK-1c flow only), not user-facing report formatters.
# Kept here so the orchestration + its operator presentation live together.

RTL = "‏"


def format_preview(preview: dict) -> str:
    """Operator-facing Hebrew preview screen. Shows what the batch will do
    BEFORE the founder confirms. Never invents counts — every number is
    read directly from the preview dict."""
    if preview.get("fetch_error"):
        return (
            f"{RTL}🔒 *RISK-1c — נעילה היסטורית: שגיאה בטעינה*\n"
            f"{RTL}לא הצלחתי לקרוא את רשימת הטריידים מ-Supabase.\n"
            f"{RTL}_אין שינוי בנתונים. נסה שוב או בדוק את הלוגים._"
        )

    total = preview.get("total", 0)
    if total == 0:
        return (
            f"{RTL}🔒 *RISK-1c — נעילה היסטורית*\n"
            f"{RTL}✅ אין טריידים לא-נעולים. כל הקיים כבר נעול."
        )

    lockable = preview.get("lockable_count", 0)
    anomalous = preview.get("anomalous_count", 0)
    by_symbol = preview.get("by_symbol", {})
    anomalous_symbols = preview.get("anomalous_symbols", [])

    lines = [
        f"{RTL}🔒 *RISK-1c — נעילה היסטורית (preview)*",
        f"{RTL}_מציג מה ייקרה אם תאשר. עדיין לא בוצע שינוי._",
        f"",
        f"{RTL}📊 *סך הכל לא-נעולים:* `{total}`",
        f"{RTL}  ▸ ייעלו עכשיו: `{lockable}`",
    ]
    if anomalous:
        lines.append(
            f"{RTL}  ▸ ידולגו (מחיר חריג / חסר): `{anomalous}`"
        )
        if anomalous_symbols:
            sample = ", ".join(anomalous_symbols[:5])
            extra = f" +{len(anomalous_symbols) - 5}" if len(anomalous_symbols) > 5 else ""
            lines.append(f"{RTL}    _דוגמאות:_ `{sample}{extra}`")

    if by_symbol:
        lines.append("")
        lines.append(f"{RTL}📋 *פירוט לפי סימול (ייעלו):*")
        # Sort by count descending, then symbol asc, cap at 12 lines for Telegram readability.
        items = sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))
        for sym, cnt in items[:12]:
            lines.append(f"{RTL}  ▸ `{sym}`: {cnt}")
        if len(items) > 12:
            remaining = sum(c for _, c in items[12:])
            lines.append(f"{RTL}  ▸ _+{len(items) - 12} סימולים נוספים ({remaining} שורות)_")

    lines += [
        "",
        f"{RTL}⚠️ *פעולה בלתי-הפיכה (כמעט).*",
        f"{RTL}_הנעילה משתמשת ב-`price` הקיים כעוגן at-entry. אם רשומה_",
        f"{RTL}_כבר נפגעה מ-re-sync היסטורי, הערך השגוי הוא מה שייעל._",
        f"{RTL}_תיקון פרטני זמין דרך admin correction (RISK-1d.4)._",
    ]
    return "\n".join(lines)


def format_result(result: dict) -> str:
    """Operator-facing Hebrew result screen after run_backfill."""
    if result.get("fetch_error"):
        return (
            f"{RTL}❌ *RISK-1c — שגיאה בטעינה*\n"
            f"{RTL}לא הצלחתי לטעון את רשימת הטריידים מ-Supabase.\n"
            f"{RTL}_אין שינוי בנתונים._"
        )

    locked = result.get("locked", 0)
    skipped_anomaly = result.get("skipped_anomaly", 0)
    skipped_other = result.get("skipped_other", 0)
    by_symbol = result.get("by_symbol", {})

    lines = [
        f"{RTL}✅ *RISK-1c — נעילה היסטורית הושלמה*",
        f"",
        f"{RTL}🔒 *ננעלו:* `{locked}`",
    ]
    if skipped_anomaly > 0:
        lines.append(f"{RTL}⚠️ *דולגו (מחיר חריג):* `{skipped_anomaly}`")
    if skipped_other > 0:
        lines.append(f"{RTL}ℹ️ *דולגו (אחר):* `{skipped_other}`")

    if by_symbol:
        lines.append("")
        lines.append(f"{RTL}📋 *לפי סימול:*")
        items = sorted(by_symbol.items(), key=lambda kv: (-kv[1], kv[0]))
        for sym, cnt in items[:12]:
            lines.append(f"{RTL}  ▸ `{sym}`: {cnt}")
        if len(items) > 12:
            remaining = sum(c for _, c in items[12:])
            lines.append(f"{RTL}  ▸ _+{len(items) - 12} סימולים נוספים ({remaining} ננעלו)_")

    lines += [
        "",
        f"{RTL}_מעכשיו פוזיציות אלו לא יראו `⚠️ לא-נעול` ב-/portfolio._",
        f"{RTL}_re-sync של IBKR כבר לא יחליף את עוגן הכניסה שלהן._",
    ]
    return "\n".join(lines)
