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
import engine_core as ec

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
        buys = group[group["quantity"] > 0]
        sells = group[group["quantity"] < 0]
        buys_qty = buys["quantity"].sum()
        sells_qty = sells["quantity"].abs().sum()
        if buys_qty <= 0:
            continue
        if (buys_qty - sells_qty) / buys_qty > 0.01:
            continue
        if sells.empty:
            continue

        total_pnl = sells["pnl_usd"].sum()

        close_date_raw = sells["trade_date"].max()
        try:
            close_date = pd.to_datetime(close_date_raw)
        except Exception:
            close_date = datetime.now()

        # Original campaign risk from first BUY day (matches dashboard logic).
        try:
            first_date = buys["trade_date"].min()
            first_day = buys[buys["trade_date"] == first_date]
            base_qty = float(first_day["quantity"].sum())
            base_price = (
                float((first_day["price"] * first_day["quantity"]).sum() / base_qty)
                if base_qty > 0 else 0.0
            )
            init_sl_raw = first_day.iloc[0].get("initial_stop", 0)
            init_sl = float(init_sl_raw) if init_sl_raw and not pd.isna(init_sl_raw) else 0.0
            if init_sl > 0 and init_sl < base_price:
                original_campaign_risk = round((base_price - init_sl) * base_qty, 2)
            else:
                original_campaign_risk = 0.0
        except Exception:
            original_campaign_risk = 0.0

        setup_type = str(group.iloc[0].get("setup_type", "") or "")
        stat_bucket = ec.classify_stat_bucket(setup_type, original_campaign_risk)

        closed.append({
            "campaign_id": cid,
            "symbol": str(group.iloc[0].get("symbol", "")),
            "setup_type": setup_type,
            "total_pnl_usd": round(float(total_pnl), 2),
            "close_date": close_date,
            "is_win": float(total_pnl) > 0,
            "original_campaign_risk": original_campaign_risk,
            "stat_bucket": stat_bucket,
        })

    closed.sort(key=lambda x: x["close_date"], reverse=True)
    return closed


def compute_adaptive_risk(
    closed_campaigns: list[dict],
    current_risk_pct: float,
    nav: float,
    open_r_list: list[float] | None = None,
) -> dict:
    """
    מחשב המלצת סיכון אדפטיבית.

    closed_campaigns: פלט של compute_closed_campaigns (ממוין חדש→ישן)
    current_risk_pct: אחוז סיכון נוכחי מ-sentinel_config.json (למשל 0.5)
    nav: NAV נוכחי בדולרים
    open_r_list: רשימת R צף לכל פוזיציה פתוחה (חיובי = רווח, שלילי = הפסד)
    """
    if len(closed_campaigns) < 3:
        return {
            "ok": False,
            "error": "not_enough_trades",
            "message": f"רק {len(closed_campaigns)} קמפיינים סגורים — נדרשות לפחות 3 לניתוח",
        }

    recent_50 = closed_campaigns[:50]
    recent_10 = closed_campaigns[:10]

    # Discretionary = countable (excludes ALGO + DATA_INCOMPLETE so WR matches dashboard).
    # Falls back to setup_type filter on legacy dicts without stat_bucket.
    def _is_disc(c: dict) -> bool:
        bucket = c.get("stat_bucket")
        if bucket:
            return ec.is_stat_countable(bucket)
        return c.get("setup_type", "").upper() != "ALGO"

    disc_camps = [c for c in closed_campaigns if _is_disc(c)]
    if disc_camps:
        actual_recent_10 = disc_camps[:10]
        actual_recent_50 = disc_camps[:50]
    else:
        actual_recent_10 = recent_10
        actual_recent_50 = recent_50

    # Weighted Win Rate: last 10 weight=2, rest weight=1; ALGO at 0.25x (observer only)
    weighted_wins = 0.0
    weighted_total = 0.0
    for i, c in enumerate(recent_50):
        is_algo = c.get("setup_type", "").upper() == "ALGO"
        base_w = 2.0 if i < 10 else 1.0
        w = base_w * (0.25 if is_algo else 1.0)
        weighted_wins += w * (1 if c.get("is_win") else 0)
        weighted_total += w

    weighted_wr = weighted_wins / weighted_total if weighted_total > 0 else 0.0

    # Win rates shown to user — from discretionary only (no ALGO noise)
    recent_10_wr = (
        sum(1 for c in actual_recent_10 if c.get("is_win")) / len(actual_recent_10)
    ) if actual_recent_10 else 0.0
    all_50_wr = (
        sum(1 for c in actual_recent_50 if c.get("is_win")) / len(actual_recent_50)
    ) if actual_recent_50 else 0.0

    # Streak Detection: discretionary only — ALGO losses should not penalise the trader
    streak_source = disc_camps[:50] if disc_camps else recent_50
    win_streak = 0
    loss_streak = 0
    for c in streak_source:
        if c.get("is_win"):
            if loss_streak > 0:
                break
            win_streak += 1
        else:
            if win_streak > 0:
                break
            loss_streak += 1

    heat_score = weighted_wr * 100  # 0–100

    # Payoff quality factor: are recent wins bigger than historical wins?
    wins_10 = [c["total_pnl_usd"] for c in actual_recent_10 if c.get("is_win") and c.get("total_pnl_usd", 0) > 0]
    wins_50 = [c["total_pnl_usd"] for c in actual_recent_50 if c.get("is_win") and c.get("total_pnl_usd", 0) > 0]
    avg_win_10 = sum(wins_10) / len(wins_10) if wins_10 else 0.0
    avg_win_50 = sum(wins_50) / len(wins_50) if wins_50 else 0.0
    payoff_ratio = avg_win_10 / avg_win_50 if avg_win_50 > 0 and avg_win_10 > 0 else 1.0

    payoff_delta = 0.0
    if len(wins_10) >= 2:
        if payoff_ratio >= 1.5:
            payoff_delta = 10.0   # Recent wins 50%+ above historical → hot streak
        elif payoff_ratio >= 1.2:
            payoff_delta = 5.0
        elif payoff_ratio < 0.6:
            payoff_delta = -10.0  # Recent wins shrinking → cooling off

    # Open position bonus: running winners are strong evidence of a hot period
    open_r_bonus = 0.0
    if open_r_list:
        running_r = sum(r for r in open_r_list if r > 0)
        if running_r >= 5.0:
            open_r_bonus = 10.0
        elif running_r >= 2.0:
            open_r_bonus = 5.0
        elif running_r >= 1.0:
            open_r_bonus = 2.0

    heat_score = min(100.0, max(0.0, heat_score + payoff_delta + open_r_bonus))

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
        "n_used_10": len(actual_recent_10),
        "n_used_50": len(actual_recent_50),
        "heat_score": round(heat_score, 1),
        "heat_label": heat_label,
        "heat_color": heat_color,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "recent_10_wr": round(recent_10_wr * 100, 1),
        "all_50_wr": round(all_50_wr * 100, 1),
        "payoff_ratio": round(payoff_ratio, 2),
        "open_r_bonus": round(open_r_bonus, 1),
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
