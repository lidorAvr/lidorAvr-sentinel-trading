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
import json, os, time
from datetime import datetime
import pandas as pd
import engine_core as ec

RISK_LADDER = [0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]
RECOMMENDATIONS_LOG_FILE = "risk_recommendations.json"
RISK_JOURNAL_FILE = "risk_journal.json"
SENTINEL_CONFIG_FILE = "sentinel_config.json"
RISK_SETTLE_HOURS = 48.0  # hours to hold at new risk level before next recommendation fires


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
        old_pct = float(cfg.get("risk_pct_input", new_pct))
        cfg["risk_pct_input"] = round(float(new_pct), 4)
        cfg["risk_changed_ts"] = time.time()
        cfg["risk_changed_dir"] = "up" if new_pct > old_pct else "down_fast"
        with open(SENTINEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_risk_settle_info() -> dict:
    """Returns settle period status. 'active' is True for 48h after a confirmed risk change."""
    try:
        with open(SENTINEL_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        changed_ts = float(cfg.get("risk_changed_ts", 0))
        changed_dir = cfg.get("risk_changed_dir", "")
        changed_pct = float(cfg.get("risk_pct_input", 0))
        if not changed_ts or not changed_dir:
            return {"active": False, "hours_remaining": 0.0, "dir": "", "to_pct": 0.0}
        elapsed = (time.time() - changed_ts) / 3600
        hours_remaining = max(0.0, RISK_SETTLE_HOURS - elapsed)
        return {
            "active": hours_remaining > 0,
            "hours_remaining": round(hours_remaining, 1),
            "dir": changed_dir,
            "to_pct": changed_pct,
        }
    except Exception:
        return {"active": False, "hours_remaining": 0.0, "dir": "", "to_pct": 0.0}


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


def _window_stats(camps: list) -> dict:
    """Compute descriptive stats for a window of closed campaigns (newest-first)."""
    if not camps:
        return {"n": 0, "wr": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "payoff": 0.0, "pf": 0.0, "loss_streak": 0, "win_streak": 0}
    wins   = [c for c in camps if c.get("is_win")]
    losses = [c for c in camps if not c.get("is_win")]
    n   = len(camps)
    wr  = len(wins) / n
    win_pnl  = [float(c.get("total_pnl_usd", 0)) for c in wins   if float(c.get("total_pnl_usd", 0)) > 0]
    loss_pnl = [abs(float(c.get("total_pnl_usd", 0))) for c in losses if float(c.get("total_pnl_usd", 0)) < 0]
    avg_win  = sum(win_pnl)  / len(win_pnl)  if win_pnl  else 0.0
    avg_loss = sum(loss_pnl) / len(loss_pnl) if loss_pnl else 0.0
    payoff = round(avg_win / avg_loss, 2) if avg_loss > 0 and avg_win > 0 else 0.0
    gross_profit = sum(win_pnl)
    gross_loss   = sum(loss_pnl)
    if gross_loss > 0:
        pf = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        pf = 2.0
    else:
        pf = 0.0
    loss_streak = win_streak = 0
    for c in camps:
        if c.get("is_win"):
            if loss_streak > 0: break
            win_streak += 1
        else:
            if win_streak > 0: break
            loss_streak += 1
    return {"n": n, "wr": round(wr, 3), "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
            "payoff": payoff, "pf": pf, "loss_streak": loss_streak, "win_streak": win_streak}


def _window_heat_score(stats: dict) -> float:
    """
    Map window stats to a 0–100 heat score.

    Components:
      base       = Win Rate × 100
      payoff     = +24 at Wizard threshold (≥3.0), graded down to -12 below 0.8
      profit_factor = +12 at PF ≥ 2.5, graded down to -15 below 1.0
      loss_streak = -10/-18 at 2/3+ consecutive losers (Minervini's "cut risk fast")
    """
    if stats["n"] == 0:
        return 50.0
    score = stats["wr"] * 100

    # Payoff (avg_win / avg_loss). Mark targets ≥ 2.0; "wizards" run ≥ 3.0.
    p = stats["payoff"]
    if   p >= 3.0:      score += 24
    elif p >= 2.5:      score += 20
    elif p >= 2.0:      score += 15
    elif p >= 1.5:      score += 8
    elif p >= 1.2:      score += 3
    elif p >= 1.0:      score += 1   # marginal positive
    elif 0 < p < 0.8:   score -= 12  # was -10
    # (0.8 ≤ p < 1.0 stays neutral — sub-1 but not catastrophic)

    pf = stats["pf"]
    if   pf >= 2.5: score += 12
    elif pf >= 2.0: score += 8
    elif pf >= 1.5: score += 4
    elif pf >= 1.0: score += 1   # marginal positive (was 0)
    elif pf < 1.0:  score -= 15

    # Sharper streak penalty — Minervini cuts risk fast on consecutive losers.
    if   stats["loss_streak"] >= 3: score -= 18  # was -15
    elif stats["loss_streak"] >= 2: score -= 10  # was -8
    return min(100.0, max(0.0, score))


def _build_heat_factors(s9: dict, m21: dict, open_r_bonus: float) -> list:
    """Build ordered list of factors explaining the heat score."""
    factors = []
    s9_wr_pct  = s9["wr"]  * 100
    m21_wr_pct = m21["wr"] * 100
    if s9_wr_pct >= 60:
        factors.append(f"▲ Win Rate (S9): {s9_wr_pct:.0f}% — תורם חיובי")
    elif s9_wr_pct < 50 and s9["n"] > 0:
        factors.append(f"▼ Win Rate (S9): {s9_wr_pct:.0f}% — גורר ציון למטה")
    p = s9["payoff"]
    if p >= 1.5:
        factors.append(f"▲ Payoff Ratio (S9): {p:.1f}x — ניצחונות גדולים מהפסדים")
    elif 0 < p < 1.0:
        factors.append(f"▼ Payoff Ratio (S9): {p:.1f}x — הפסד ממוצע גדול מרווח ממוצע")
    pf = s9["pf"]
    if pf >= 2.0:
        factors.append(f"▲ Profit Factor (S9): {pf:.1f}x — תיק שורי")
    elif pf < 1.0:
        factors.append(f"▼ Profit Factor (S9): {pf:.1f}x — הפסדות גדולות מרווחות")
    if s9["loss_streak"] >= 3:
        factors.append(f"▼ רצף הפסד: {s9['loss_streak']} עסקאות ברצף")
    elif s9["win_streak"] >= 3:
        factors.append(f"▲ רצף רווח: {s9['win_streak']} עסקאות ברצף")
    if m21["n"] >= 5 and abs(s9_wr_pct - m21_wr_pct) >= 15:
        if s9_wr_pct > m21_wr_pct:
            factors.append(f"▲ שיפור: S9={s9_wr_pct:.0f}% מעל M21={m21_wr_pct:.0f}%")
        else:
            factors.append(f"▼ ירידה: S9={s9_wr_pct:.0f}% מתחת M21={m21_wr_pct:.0f}%")
    if open_r_bonus > 0:
        factors.append(f"▲ פוזיציות פתוחות: +{open_r_bonus:.0f} נקודות")
    elif open_r_bonus < 0:
        factors.append(f"▼ פוזיציות פתוחות בהפסד: {open_r_bonus:.0f} נקודות")
    return factors[:5]


def _build_what_to_improve(heat_score: float, s9: dict, direction: str,
                            s9_score: float = 50.0) -> list:
    """
    Specific improvements that would lift the heat score to the next level.
    Does NOT prescribe a fixed win-rate target — instead infers the WR needed
    given the trader's current payoff ratio and bonus context.
    """
    items = []
    if direction not in ("down_fast", "hold"):
        return items
    target = 40.0 if direction == "down_fast" else 60.0
    gap = target - heat_score
    items.append(f"ציון חום נדרש: {target:.0f} | כרגע: {heat_score:.0f} | פער: {gap:.0f} נקודות")

    s9_wr = s9["wr"] * 100
    # Infer how much of the current S9 score comes from non-WR factors (payoff, PF, streaks)
    # so we can tell the trader what WR is actually needed at their current payoff level.
    non_wr_component = s9_score - s9_wr  # bonuses/penalties excluding the WR base
    wr_needed = max(0, min(100, round(target - non_wr_component)))
    if s9_wr < wr_needed - 3 and s9["n"] > 0:
        wins_needed = max(1, round((wr_needed - s9_wr) * s9["n"] / 100))
        if s9["payoff"] >= 1.2:
            items.append(
                f"Win Rate S9: {s9_wr:.0f}% | עם Payoff {s9['payoff']:.1f}x נדרש ~{wr_needed:.0f}%"
                f" (עוד {wins_needed} ניצחון)"
            )
        else:
            items.append(
                f"Win Rate S9: {s9_wr:.0f}% — Payoff נמוך ({s9['payoff']:.1f}x) מגביל את הציון"
            )

    if s9["loss_streak"] >= 2:
        items.append(f"רצף הפסד פעיל ({s9['loss_streak']}) — ניצחון אחד יאפס")
    if 0 < s9["payoff"] < 1.2:
        items.append(f"Payoff Ratio: {s9['payoff']:.1f}x | ניצחון גדול יותר מהפסד יוסיף בונוס ציון")
    return items[:4]


def compute_adaptive_risk(
    closed_campaigns: list,
    current_risk_pct: float,
    nav: float,
    open_r_list=None,
    open_positions=None,
) -> dict:
    """
    Compute adaptive risk recommendation using multi-window scoring.

    closed_campaigns: output of compute_closed_campaigns (newest-first)
    current_risk_pct: current risk % from sentinel_config.json
    nav: current NAV in USD
    open_r_list: legacy list of open R floats (positive-only bonus for backward compat)
    open_positions: list of {"open_r": float, "is_algo": bool} — ALGO counted at 0.25x
    """
    if len(closed_campaigns) < 3:
        return {
            "ok": False,
            "error": "not_enough_trades",
            "message": f"רק {len(closed_campaigns)} קמפיינים סגורים — נדרשות לפחות 3 לניתוח",
        }

    def _is_disc(c: dict) -> bool:
        bucket = c.get("stat_bucket")
        if bucket:
            return ec.is_stat_countable(bucket)
        return c.get("setup_type", "").upper() != "ALGO"

    disc_camps = [c for c in closed_campaigns if _is_disc(c)]
    if not disc_camps:
        disc_camps = closed_campaigns[:50]

    # Multi-window scoring on disc-only campaigns (short=50%, medium=30%, long=20%)
    s9_stats  = _window_stats(disc_camps[:9])
    m21_stats = _window_stats(disc_camps[:21])
    l50_stats = _window_stats(disc_camps[:50])

    s9_score  = _window_heat_score(s9_stats)
    m21_score = _window_heat_score(m21_stats)
    l50_score = _window_heat_score(l50_stats)

    base_heat = s9_score * 0.50 + m21_score * 0.30 + l50_score * 0.20

    # Open position adjustment — ALGO positions at 0.25x weight
    disc_open_r = 0.0
    algo_open_r = 0.0

    if open_positions:
        for op in open_positions:
            r = float(op.get("open_r", 0))
            if op.get("is_algo"):
                algo_open_r += r
            else:
                disc_open_r += r
        combined_open_r = disc_open_r + algo_open_r * 0.25
    elif open_r_list:
        # Legacy path: bonus-only (positive R only), no ALGO separation
        combined_open_r = sum(float(r) for r in open_r_list if r > 0)
    else:
        combined_open_r = 0.0

    if   combined_open_r >= 5.0:  open_r_bonus = 10.0
    elif combined_open_r >= 2.0:  open_r_bonus = 5.0
    elif combined_open_r >= 1.0:  open_r_bonus = 2.0
    elif combined_open_r <= -3.0: open_r_bonus = -15.0
    elif combined_open_r <= -1.0: open_r_bonus = -8.0
    elif combined_open_r < 0.0:   open_r_bonus = -3.0
    else:                         open_r_bonus = 0.0

    heat_score = min(100.0, max(0.0, base_heat + open_r_bonus))

    s9_loss_streak = s9_stats["loss_streak"]
    s9_win_streak  = s9_stats["win_streak"]

    if heat_score >= 60 and s9_loss_streak < 2:
        heat_label, heat_color, direction = "חזק", "🔥", "up"
    elif heat_score < 40 or s9_loss_streak >= 3:
        heat_label, heat_color, direction = "חלש", "❄️", "down_fast"
    else:
        heat_label, heat_color, direction = "נייטרל", "➖", "hold"

    curr_idx = _closest_ladder_index(current_risk_pct)
    if direction == "up":
        new_idx   = min(curr_idx + 1, len(RISK_LADDER) - 1)
        step_type = "העלאת סיכון הדרגתית"
    elif direction == "down_fast":
        new_idx   = max(curr_idx - 2, 0)
        step_type = "צמצום סיכון מהיר"
    else:
        new_idx   = curr_idx
        step_type = "שמירה על רמה קיימת"

    # Bug fix: if the ladder index didn't actually move, treat as hold — no alert should fire
    if new_idx == curr_idx and direction != "hold":
        direction = "hold"
        step_type = "שמירה על רמה קיימת"

    rec_pct = RISK_LADDER[new_idx]
    rec_usd = round(nav * rec_pct / 100, 0)
    curr_usd = round(nav * current_risk_pct / 100, 0)

    heat_factors    = _build_heat_factors(s9_stats, m21_stats, open_r_bonus)
    what_to_improve = _build_what_to_improve(heat_score, s9_stats, direction, s9_score=s9_score)

    result = {
        "ok": True,
        "error": None,
        # Backward-compatible keys (mapped from multi-window data)
        "n_trades":    len(disc_camps),
        "n_used_10":   s9_stats["n"],
        "n_used_50":   l50_stats["n"],
        "heat_score":  round(heat_score, 1),
        "heat_label":  heat_label,
        "heat_color":  heat_color,
        "win_streak":  s9_win_streak,
        "loss_streak": s9_loss_streak,
        "recent_10_wr": round(s9_stats["wr"] * 100, 1),
        "all_50_wr":    round(l50_stats["wr"] * 100, 1),
        "payoff_ratio": s9_stats["payoff"],
        "open_r_bonus": round(open_r_bonus, 1),
        "current_risk_pct":     current_risk_pct,
        "current_risk_usd":     curr_usd,
        "recommended_risk_pct": rec_pct,
        "recommended_risk_usd": rec_usd,
        "direction":   direction,
        "step_type":   step_type,
        "generated_at": datetime.now().isoformat(),
        # New multi-window breakdown
        "s9_score":    round(s9_score, 1),
        "m21_score":   round(m21_score, 1),
        "l50_score":   round(l50_score, 1),
        "s9_stats":    s9_stats,
        "m21_stats":   m21_stats,
        "l50_stats":   l50_stats,
        "disc_open_r": round(disc_open_r, 2),
        "algo_open_r": round(algo_open_r, 2),
        "heat_factors":     heat_factors,
        "what_to_improve":  what_to_improve,
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
