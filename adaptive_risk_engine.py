"""
adaptive_risk_engine.py
מנוע סיכון אדפטיבי — מנתח ביצועי מסחר אחרונים וממליץ על אחוז סיכון מתאים.

אלגוריתם:
- מנתח עד 50 קמפיינים סגורים אחרונים.
- 10 האחרונים מקבלים משקל כפול (עדיפות לנסיון עדכני).
- מחשב "ציון חום" (0–100%) = Weighted Win Rate.
- ממפה לרמת סיכון על סולם קבוע.
- בתקופה חזקה: מעלה שלב אחד.
- בתקופה חלשה (ציון < 40% או 3+ הפסדים ברצף): מוריד שני שלבים.
"""

from __future__ import annotations
import json, os
from datetime import datetime
import pandas as pd

RISK_LADDER = [0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]
RECOMMENDATIONS_LOG_FILE = "risk_recommendations.json"
RISK_JOURNAL_FILE = "risk_journal.json"
SENTINEL_CONFIG_FILE = "sentinel_config.json"


def _closest_ladder_index(pct: float) -> int:
    diffs = [abs(pct - r) for r in RISK_LADDER]
    return diffs.index(min(diffs))


def update_risk_pct(new_pct: float) -> bool:
    """מעדכן את risk_pct_input ב-sentinel_config.json. מחזיר True בהצלחה."""
    try:
        cfg = {}
        if os.path.exists(SENTINEL_CONFIG_FILE):
            with open(SENTINEL_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["risk_pct_input"] = round(float(new_pct), 4)
        with open(SENTINEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def log_risk_journal(entry: dict) -> None:
    """
    רושם החלטת סיכון ביומן הסיכון (risk_journal.json).
    entry צריך לכלול: direction, current_risk_pct, recommended_risk_pct,
                      action ('confirmed'/'rejected'), reason (אופציונלי), actual_pct_set.
    """
    log = []
    if os.path.exists(RISK_JOURNAL_FILE):
        try:
            with open(RISK_JOURNAL_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []

    full_entry = {"ts": datetime.now().isoformat()}
    full_entry.update(entry)
    log.insert(0, full_entry)
    log = log[:500]
    try:
        with open(RISK_JOURNAL_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def compute_closed_campaigns(trades_df: pd.DataFrame) -> list[dict]:
    """
    מחלץ קמפיינים סגורים מ-DataFrame של עסקאות.
    קמפיין סגור = כל הכמות נמכרה (net_qty ≈ 0).
    מחזיר רשימה ממוינת מהחדש לישן לפי תאריך סגירה.
    """
    if trades_df is None or trades_df.empty or "campaign_id" not in trades_df.columns:
        return []

    df = trades_df.copy()
    for col in ["quantity", "price", "pnl_usd"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    closed = []
    for cid, group in df.groupby("campaign_id"):
        if pd.isna(cid):
            continue
        buys_qty = group[group["quantity"] > 0]["quantity"].sum()
        sells_qty = group[group["quantity"] < 0]["quantity"].abs().sum()
        if buys_qty <= 0:
            continue
        if (buys_qty - sells_qty) / buys_qty > 0.01:
            continue

        total_pnl = group[group["quantity"] < 0]["pnl_usd"].sum()
        sell_rows = group[group["quantity"] < 0]
        if sell_rows.empty:
            continue

        close_date_raw = sell_rows["trade_date"].max()
        try:
            close_date = pd.to_datetime(close_date_raw)
        except Exception:
            close_date = datetime.now()

        closed.append({
            "campaign_id": cid,
            "symbol": str(group.iloc[0].get("symbol", "")),
            "total_pnl_usd": round(float(total_pnl), 2),
            "close_date": close_date,
            "is_win": float(total_pnl) > 0,
        })

    closed.sort(key=lambda x: x["close_date"], reverse=True)
    return closed


def compute_adaptive_risk(
    closed_campaigns: list[dict],
    current_risk_pct: float,
    nav: float,
) -> dict:
    """
    מחשב המלצת סיכון אדפטיבית.

    closed_campaigns: פלט של compute_closed_campaigns (ממוין חדש→ישן)
    current_risk_pct: אחוז סיכון נוכחי מ-sentinel_config.json (למשל 0.5)
    nav: NAV נוכחי בדולרים
    """
    if len(closed_campaigns) < 3:
        return {
            "ok": False,
            "error": "not_enough_trades",
            "message": f"רק {len(closed_campaigns)} קמפיינים סגורים — נדרשות לפחות 3 לניתוח",
        }

    recent_50 = closed_campaigns[:50]
    recent_10 = closed_campaigns[:10]

    # Weighted Win Rate: last 10 weight=2, rest weight=1
    weighted_wins = 0
    weighted_total = 0
    for i, c in enumerate(recent_50):
        w = 2 if i < 10 else 1
        weighted_wins += w * (1 if c["is_win"] else 0)
        weighted_total += w

    weighted_wr = weighted_wins / weighted_total if weighted_total > 0 else 0.0
    recent_10_wr = (sum(1 for c in recent_10 if c["is_win"]) / len(recent_10)) if recent_10 else 0.0
    all_50_wr = (sum(1 for c in recent_50 if c["is_win"]) / len(recent_50)) if recent_50 else 0.0

    # Streak Detection (newest first)
    win_streak = 0
    loss_streak = 0
    for c in recent_50:
        if c["is_win"]:
            if loss_streak > 0:
                break
            win_streak += 1
        else:
            if win_streak > 0:
                break
            loss_streak += 1

    heat_score = weighted_wr * 100  # 0–100

    if heat_score >= 60 and loss_streak < 3:
        heat_label, heat_color, direction = "חזק", "🔥", "up"
    elif heat_score < 40 or loss_streak >= 3:
        heat_label, heat_color, direction = "חלש", "❄️", "down_fast"
    else:
        heat_label, heat_color, direction = "נייטרל", "➖", "hold"

    curr_idx = _closest_ladder_index(current_risk_pct)
    if direction == "up":
        new_idx = min(curr_idx + 1, len(RISK_LADDER) - 1)
        step_type = "העלאת סיכון הדרגתית"
    elif direction == "down_fast":
        new_idx = max(curr_idx - 2, 0)
        step_type = "צמצום סיכון מהיר"
    else:
        new_idx = curr_idx
        step_type = "שמירה על רמה קיימת"

    rec_pct = RISK_LADDER[new_idx]
    rec_usd = round(nav * rec_pct / 100, 0)
    curr_usd = round(nav * current_risk_pct / 100, 0)

    result = {
        "ok": True,
        "error": None,
        "n_trades": len(recent_50),
        "heat_score": round(heat_score, 1),
        "heat_label": heat_label,
        "heat_color": heat_color,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "recent_10_wr": round(recent_10_wr * 100, 1),
        "all_50_wr": round(all_50_wr * 100, 1),
        "current_risk_pct": current_risk_pct,
        "current_risk_usd": curr_usd,
        "recommended_risk_pct": rec_pct,
        "recommended_risk_usd": rec_usd,
        "direction": direction,
        "step_type": step_type,
        "generated_at": datetime.now().isoformat(),
    }
    _log_recommendation(result)
    return result


def _log_recommendation(rec: dict) -> None:
    """שומר המלצה ל-risk_recommendations.json לצורך מעקב ציות."""
    log = []
    if os.path.exists(RECOMMENDATIONS_LOG_FILE):
        try:
            with open(RECOMMENDATIONS_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []

    entry = {
        "ts": rec.get("generated_at"),
        "heat_score": rec.get("heat_score"),
        "direction": rec.get("direction"),
        "current_risk_pct": rec.get("current_risk_pct"),
        "recommended_risk_pct": rec.get("recommended_risk_pct"),
        "followed": None,
        "reason": None,
    }
    log.insert(0, entry)
    log = log[:200]
    try:
        with open(RECOMMENDATIONS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def mark_adherence(recommended_pct: float, actual_pct: float,
                   followed: bool, reason: str = "") -> None:
    """
    מסמן האם ההמלצה האחרונה יושמה.
    followed: True אם המשתמש אישר, False אם דחה.
    reason: הסבר לדחייה (חובה בדחייה, ריק באישור).
    """
    if not os.path.exists(RECOMMENDATIONS_LOG_FILE):
        return
    try:
        with open(RECOMMENDATIONS_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
        if log and log[0].get("followed") is None:
            log[0]["followed"] = followed
            log[0]["actual_risk_pct"] = actual_pct
            if reason:
                log[0]["reason"] = reason
            with open(RECOMMENDATIONS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def compute_adherence_stats() -> dict:
    """מחשב סטטיסטיקת ציות להמלצות סיכון."""
    if not os.path.exists(RECOMMENDATIONS_LOG_FILE):
        return {"ok": False, "message": "אין היסטוריית המלצות עדיין"}

    try:
        with open(RECOMMENDATIONS_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return {"ok": False, "message": "שגיאה בקריאת היסטוריה"}

    total = len(log)
    if total == 0:
        return {"ok": False, "message": "אין נתוני ציות עדיין"}

    evaluated = [r for r in log if r.get("followed") is not None]
    followed = sum(1 for r in evaluated if r["followed"])
    not_followed = len(evaluated) - followed

    # Last 10 actions
    last_actions = []
    for r in log[:10]:
        if r.get("followed") is True:
            last_actions.append("✅")
        elif r.get("followed") is False:
            last_actions.append("❌")
        else:
            last_actions.append("⏳")

    return {
        "ok": True,
        "total_recommendations": total,
        "evaluated": len(evaluated),
        "followed": followed,
        "not_followed": not_followed,
        "adherence_pct": round(followed / len(evaluated) * 100, 1) if evaluated else None,
        "last_actions": last_actions,
    }
