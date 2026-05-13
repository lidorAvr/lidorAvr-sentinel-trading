import os, json, time, telebot
import pandas as pd
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import engine_core as ec
import adaptive_risk_engine as are

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
bot = telebot.TeleBot(TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
RTL = "\u200F"
STATE_FILE = "risk_monitor_state.json"

STATUS_RANK = {
    "⚪ אין דאטה": 0, "🟢 Healthy": 1, "🔥 Power": 2, "⚠️ Climactic": 2,
    "🟡 Yellow Flag": 3, "🟡 תקין אך במעקב": 3, "🟠 Weak": 4, "🔴 Broken": 5, "🚨 קריטי": 6, "🚨 חריגת סיכון אלגו": 6
}

DEVIATION_RANK = {"unknown": 0, "normal": 1, "minor": 2, "moderate": 3, "severe": 4, "system_event": 5}
GIVEBACK_RANK  = {"na": 0, "natural": 1, "watch": 2, "tighten": 3, "protection_failure": 4}
PROFIT_CHECKPOINTS = [2.0, 3.0]  # Fire alert when open_r crosses these thresholds
DEVIATION_COOLDOWN_SEC  = 3 * 3600   # 3h cooldown for same deviation class
GIVEBACK_COOLDOWN_SEC   = 6 * 3600   # 6h cooldown for same giveback class
LIVE_ALERT_REPEAT_COOLDOWN = 45 * 60  # 45 min: prevents oscillation spam on non-escalating action/status changes

# Phase 5 — Anti-Spam: state-transition cooldowns (prevents oscillation re-alerts)
STATE_ALERT_COOLDOWN = {
    "RUNNER":     4 * 3600,   # 4h — price can oscillate around 5R threshold
    "BROKEN":     4 * 3600,   # 4h — price can bounce around stop
    "DEAD_MONEY": 12 * 3600,  # 12h — informational; state is stable but low urgency
}

# Alert priority tiers (reference; governs routing and cooldown expectations)
ALERT_PRIORITY = {
    # P0 — Critical: always fire immediately, no suppression
    "stop_breach":            "P0",
    "algo_cluster_red":       "P0",
    "algo_deep_loss":         "P0",
    "risk_deviation_system":  "P0",
    # P1 — High: fire on transition; re-entry cooldown 4h
    "broken_state":           "P1",
    "runner_state":           "P1",
    "breakeven_protocol":     "P1",
    "risk_deviation_severe":  "P1",
    "algo_loss_streak_orange": "P1",
    # P2 — Medium: 6h standard cooldown
    "profit_checkpoint":         "P2",
    "risk_deviation_moderate":   "P2",
    "giveback_tighten":          "P2",
    "algo_cluster_yellow":       "P2",
    "algo_loss_streak_yellow":   "P2",
    # P3 — Low: market-hours gated, 12–24h cooldown
    "dead_money_state":  "P3",
    "algo_visibility":   "P3",
    "adaptive_risk":     "P3",
    "giveback_watch":    "P3",
}

def _should_fire_state_alert(new_state: str, prev_alerted_type: str,
                              prev_alerted_ts: float, now_ts: float) -> bool:
    """
    Return True if a state-change alert should fire.

    Logic:
      - Always fire if transitioning to a state not seen before in this cycle.
      - For states in STATE_ALERT_COOLDOWN, suppress re-entry alerts for the
        cooldown period to prevent oscillation spam (e.g. price bouncing around
        the RUNNER or BROKEN threshold multiple times per day).
    """
    cooldown = STATE_ALERT_COOLDOWN.get(new_state, 0)
    if cooldown == 0:
        return True
    # Same state re-entered: only fire if cooldown has elapsed
    if new_state == prev_alerted_type:
        return (now_ts - prev_alerted_ts) >= cooldown
    # Different state: always fire (state genuinely changed)
    return True


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"positions": {}, "cluster": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)

def get_ibkr_nav():
    try:
        report_path = "ibkr_raw_report.xml"
        if not os.path.exists(report_path): return None
        tree = ET.parse(report_path)
        root = tree.getroot()
        for elem in root.iter():
            if elem.tag.lower().endswith("changeinnav"):
                ending_val = elem.attrib.get('endingValue')
                if ending_val: return float(ending_val)
        return None
    except: return None

def get_account_settings():
    try:
        with open("sentinel_config.json", "r") as f: return json.load(f)
    except: return {"total_deposited": 7500.0, "risk_pct_input": 0.5}

def build_position_alert_key(pos, engine_data):
    # Exclude 'trigger' — it oscillates intra-day (e.g. MA10 vs trend-follow text) and
    # causes spurious key-change re-alerts without any real state change.
    return json.dumps({
        "status": engine_data["status"],
        "action": engine_data["action"],
        "sizing": engine_data.get("sizing_status", "✅ תקין")
    }, ensure_ascii=False, sort_keys=True)

def is_during_us_market_hours():
    """True if now is within the US trading day window (pre-market to after-hours).
    Uses UTC check: 11:00–21:00 UTC covers ~14:00–00:00 Israel time on Mon–Fri.
    Repeat cooldown alerts are suppressed outside this window to avoid overnight noise.
    Escalations and first-time alerts always fire regardless of this function."""
    now_utc = datetime.utcnow()
    if now_utc.weekday() >= 5:  # Sat or Sun — US market closed
        return False
    return 11 <= now_utc.hour < 21

def should_alert(prev, current_status, current_key):
    now_ts = datetime.utcnow().timestamp()
    if prev is None: return True, now_ts

    prev_status = prev.get("status")
    prev_key = prev.get("alert_key")
    last_alert_ts = prev.get("last_alert_ts", 0)

    # Escalation: status worsened → always alert immediately (e.g. Healthy→Broken)
    if STATUS_RANK.get(current_status, 0) > STATUS_RANK.get(prev_status, 0): return True, now_ts

    # Critical/Broken repeat: re-alert after 6h during market hours only
    if current_status in ["🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו"]:
        if (now_ts - last_alert_ts) > (6 * 3600) and is_during_us_market_hours():
            return True, now_ts
        return False, last_alert_ts

    # Non-escalating key change (de-escalation or action text oscillation):
    # Apply LIVE_ALERT_REPEAT_COOLDOWN to prevent oscillation spam.
    # Example: Power→Weak fires once; Weak→Power is not an escalation and gets the cooldown.
    if prev_key != current_key:
        if (now_ts - last_alert_ts) > LIVE_ALERT_REPEAT_COOLDOWN:
            return True, now_ts

    return False, last_alert_ts

def _deviation_alert_text(sym, setup, open_r, dev, is_algo):
    RTL_M = "‏"
    if is_algo:
        if dev["alert_level"] == "system":
            heading = f"🚨 *אירוע מערכת — אלגו חורג ממסגרת סיכון*"
        elif dev["alert_level"] == "severe":
            heading = f"🔴 *התרעה חמורה — לבדוק שהאלגו פועל תקין*"
        else:
            heading = f"⚠️ *התרעת ALGO — חריגה מסיכון יעד*"
        action_line = f"{RTL_M}פיקוח: לבדוק שהאלגו מחובר ופעיל. אין המלצת יציאה ידנית."
    else:
        if dev["alert_level"] == "system":
            heading = f"🚨 *אירוע מערכת — חריגה קיצונית מסיכון*"
        elif dev["alert_level"] == "severe":
            heading = f"🔴 *חריגה חמורה מסיכון מתוכנן*"
        else:
            heading = f"⚠️ *חריגת סיכון — מעל סיכון יעד*"
        action_line = f"{RTL_M}פעולה: לבדוק עמידה בסטופ ולהעריך מחדש."

    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    return (
        f"{RTL_M}{heading}\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}חריגה: `{dev['deviation_r']:.2f}R` | סיווג: `{dev['label']}`\n"
        f"{RTL_M}Open R נוכחי: `{open_r:.2f}R`\n"
        f"{RTL_M}{action_line}"
    )


def _giveback_alert_text(sym, setup, peak_r, current_r, gb, is_algo):
    RTL_M = "‏"
    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    if is_algo:
        action_line = f"{RTL_M}פיקוח בלבד — Sentinel אינה מנהלת יציאות אלגו."
    else:
        action_line = f"{RTL_M}פעולה: לשקול הדקת סטופ / מימוש חלקי / מעבר לסטופ עוקב."
    return (
        f"{RTL_M}📉 *Giveback Alert — {gb['label']}*\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}שיא: `{peak_r:.2f}R` → נוכחי: `{current_r:.2f}R`\n"
        f"{RTL_M}ויתור: `{gb['giveback_r']:.2f}R` ({gb['giveback_pct_of_peak']:.0f}% מהשיא)\n"
        f"{RTL_M}{action_line}"
    )


def _checkpoint_alert_text(sym, setup, checkpoint_r, open_r, is_algo,
                            protected_profit=None, giveback_usd=None, giveback_pct=None):
    RTL_M = "‏"
    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    if is_algo:
        action_line = (
            f"{RTL_M}Sentinel אינה מנהלת יציאות אלגו.\n"
            f"{RTL_M}פיקוח: Profit Protection Checkpoint — מעקב אחרי Giveback מכאן."
        )
    else:
        action_line = (
            f"{RTL_M}פעולה לפי מינרביני: לשקול הגנת רווח — העלאת סטופ, מימוש חלקי, או מעבר ל-Runner."
        )
    extra = ""
    if protected_profit is not None and giveback_usd is not None:
        extra = (f"\n{RTL_M}• רווח מוגן: `${protected_profit:.0f}` "
                 f"| Giveback עד סטופ: `${giveback_usd:.0f}`"
                 + (f" ({giveback_pct:.0f}%)" if giveback_pct is not None else ""))
    return (
        f"{RTL_M}🏁 *Profit Protection Checkpoint — {checkpoint_r:.0f}R*\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}Open R: `{open_r:.2f}R` חצה סף `{checkpoint_r:.0f}R`{extra}\n"
        f"{RTL_M}{action_line}"
    )


# ── Phase 3 — State-change alert templates ───────────────────────────────────

def _runner_state_alert(sym, setup, open_r, protected_profit, giveback_usd,
                         giveback_pct, current_stop, days_to_earnings):
    RTL_M = "‏"
    earnings_line = ""
    if days_to_earnings is not None and days_to_earnings <= 30:
        earnings_line = f"\n{RTL_M}• דוחות בעוד: `{days_to_earnings} ימים`"
    return (
        f"{RTL_M}🏃 *Runner Mode — {sym}*\n"
        f"{RTL_M}הפוזיציה הגיעה ל-`{open_r:.1f}R` — מצב Runner.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}• Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}• רווח מוגן (לפי סטופ): `${protected_profit:.0f}`\n"
        f"{RTL_M}• Giveback עד סטופ: `${giveback_usd:.0f}` ({giveback_pct:.0f}%)\n"
        f"{RTL_M}• סטופ נוכחי: `${current_stop:.2f}`{earnings_line}\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}✅ להחזיק אם יש Tennis Ball ומחזור יורד בירידות.\n"
        f"{RTL_M}⚠️ Giveback > 40%? — שקל הדקת סטופ.\n"
        f"{RTL_M}🚫 לא להוסיף לפני בסיס חדש."
    )


def _runner_decision_keyboard(sym, campaign_id):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("✅ להחזיק", callback_data=f"runner_decision|hold|{sym}|{campaign_id}"),
        telebot.types.InlineKeyboardButton("🔒 הדק סטופ", callback_data=f"runner_decision|tighten|{sym}|{campaign_id}"),
    )
    markup.add(
        telebot.types.InlineKeyboardButton("📊 מימוש חלקי", callback_data=f"runner_decision|partial|{sym}|{campaign_id}"),
    )
    return markup


def _broken_state_alert(sym, setup, open_r, reason):
    RTL_M = "‏"
    return (
        f"{RTL_M}🔴 *טרייד שבור — {sym}*\n"
        f"{RTL_M}הפוזיציה כבר לא עומדת בתוכנית המקורית.\n"
        f"{RTL_M}סיבה: `{reason}`\n"
        f"{RTL_M}Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}• לפעול לפי תוכנית היציאה שהוגדרה מראש.\n"
        f"{RTL_M}• לתעד: האם הייתה חריגת סיכון? נדרש Re-entry Watch?"
    )


def _dead_money_alert(sym, setup, age_days, open_r):
    RTL_M = "‏"
    return (
        f"{RTL_M}⏳ *Dead Money Risk — {sym}*\n"
        f"{RTL_M}הפוזיציה לא שבורה, אבל גם לא מתקדמת.\n"
        f"{RTL_M}• ותק: `{age_days:.0f} ימים` | Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}✅ להחזיק אם יש Tight action ומחזור יורד.\n"
        f"{RTL_M}↩️ לשקול צמצום אם יש הזדמנות טובה יותר.\n"
        f"{RTL_M}🚫 לא להוסיף עד פריצה/חוזקה חדשה."
    )


def _breakeven_protocol_alert(sym, open_r, capital_at_risk_usd):
    RTL_M = "‏"
    return (
        f"{RTL_M}🧷 *Breakeven Protection Required — {sym}*\n"
        f"{RTL_M}הפוזיציה הגיעה ל-`{open_r:.1f}R`, אבל לפי הסטופ הנוכחי\n"
        f"{RTL_M}עדיין קיים סיכון הון של `${capital_at_risk_usd:.0f}`.\n"
        f"{RTL_M}זה לא מתאים לניהול Risk First.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}1. לקדם סטופ לפחות לאזור כניסה.\n"
        f"{RTL_M}2. לממש חלק ולהשאיר Runner.\n"
        f"{RTL_M}3. להשאיר רק עם סיבה טכנית מתועדת.\n"
        f"{RTL_M}🚫 לא לתת לפוזיציה של 3R להפוך להפסד מלא."
    )


# ── Phase 4 — ALGO Oversight alert templates ─────────────────────────────────

def _algo_deep_loss_alert(sym, open_r):
    RTL_M = "‏"
    return (
        f"{RTL_M}🔴 *ALGO Oversight — הפסד עמוק*\n"
        f"{RTL_M}סימול: *{sym}* | Open R: `{open_r:.2f}R`\n"
        f"{RTL_M}הפוזיציה חצתה ─2R — מגבלת הפסד גבוהה.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}פיקוח: Sentinel לא תציע מכירה ולא תציע שינוי סטופ.\n"
        f"{RTL_M}ℹ️ לוודא שהאלגו עדיין פעיל ועובד לפי הגדרות."
    )


def _algo_loss_streak_alert(sym, open_r, streak_runs, level):
    RTL_M = "‏"
    duration_min = streak_runs * 5
    if level == "orange":
        heading = f"🔴 *ALGO Oversight — ירידה ממושכת*"
    else:
        heading = f"⚠️ *ALGO Oversight — מגמת ירידה*"
    return (
        f"{RTL_M}{heading}\n"
        f"{RTL_M}סימול: *{sym}* | Open R: `{open_r:.2f}R`\n"
        f"{RTL_M}הפוזיציה בהפסד במשך ~{duration_min} דקות ברצף ({streak_runs} ריצות).\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}פיקוח: Sentinel לא מתערבת בניהול אלגו.\n"
        f"{RTL_M}ℹ️ לוודא שהאלגו מחובר ופועל תקין."
    )


def _algo_visibility_alert(visibility_avg, n_positions):
    RTL_M = "‏"
    return (
        f"{RTL_M}⚠️ *ALGO Oversight — נתוני סיכון חסרים*\n"
        f"{RTL_M}ממוצע ניקוד שקיפות: `{visibility_avg:.0f}/100` ({n_positions} פוזיציות)\n"
        f"{RTL_M}ציון 40 = תקין לאלגו (אין סטופ ידוע). ציון 20 = אין target_risk_usd.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}ℹ️ לבדוק: הוזנו target_risk_usd בפוזיציות האלגו?"
    )


def check_position_risk_thresholds(sym, setup, open_r, open_pnl_usd, target_risk_usd,
                                    is_algo, prev_state, now_ts):
    """
    Check risk deviation, giveback, and profit protection checkpoints for one position.
    Returns (alerts_list, state_updates_dict).
    alerts_list: list of strings to send via Telegram.
    state_updates_dict: fields to merge into the position's state dict.
    """
    alerts = []
    updates = {}

    peak_open_r = max(prev_state.get("peak_open_r", 0.0), open_r if open_r > 0 else 0.0)
    updates["peak_open_r"] = peak_open_r

    # ── Risk Deviation (losses only) ──────────────────────────────────────
    if open_pnl_usd < 0 and target_risk_usd > 0:
        dev = ec.compute_risk_deviation(open_pnl_usd, target_risk_usd)
        prev_dev_class = prev_state.get("last_deviation_class", "normal")
        prev_dev_ts = prev_state.get("last_deviation_ts", 0)
        alert_levels_to_notify = {"moderate", "severe", "system_event"}

        escalated = DEVIATION_RANK.get(dev["classification"], 0) > DEVIATION_RANK.get(prev_dev_class, 0)
        cooled_down = (now_ts - prev_dev_ts) > DEVIATION_COOLDOWN_SEC
        should_fire = dev["classification"] in alert_levels_to_notify and (escalated or cooled_down)

        if should_fire:
            alerts.append(_deviation_alert_text(sym, setup, open_r, dev, is_algo))
            updates["last_deviation_class"] = dev["classification"]
            updates["last_deviation_ts"] = now_ts
        elif dev["classification"] not in ("normal", "minor"):
            # Track class even without alert
            updates["last_deviation_class"] = dev["classification"]

    # ── Profit Protection Checkpoints ─────────────────────────────────────
    checkpoints_hit = set(prev_state.get("checkpoints_hit", []))
    for cp in PROFIT_CHECKPOINTS:
        if open_r >= cp and cp not in checkpoints_hit:
            alerts.append(_checkpoint_alert_text(sym, setup, cp, open_r, is_algo))
            checkpoints_hit.add(cp)
    updates["checkpoints_hit"] = list(checkpoints_hit)

    # ── Giveback Monitor (only when meaningful profit existed, not after BROKEN) ─
    _pos_state = prev_state.get("position_state", "")
    if peak_open_r >= 1.5 and open_r < peak_open_r and _pos_state != ec.POSITION_STATE_BROKEN:
        gb = ec.compute_giveback_from_peak(peak_open_r, open_r)
        prev_gb_class = prev_state.get("last_giveback_class", "natural")
        prev_gb_ts = prev_state.get("last_giveback_ts", 0)
        alert_classes_to_notify = {"watch", "tighten", "protection_failure"}

        zone_changed = gb["classification"] != prev_gb_class
        # Fire only on zone transition (entering OR leaving an alert zone).
        # No repeat-after-cooldown within the same zone — that caused the spam.
        is_alert_current = gb["classification"] in alert_classes_to_notify
        is_alert_prev = prev_gb_class in alert_classes_to_notify
        should_fire = zone_changed and (is_alert_current or is_alert_prev)

        if should_fire:
            alerts.append(_giveback_alert_text(sym, setup, peak_open_r, open_r, gb, is_algo))
        updates["last_giveback_class"] = gb["classification"]
        if should_fire:
            updates["last_giveback_ts"] = now_ts

    return alerts, updates


def send_telegram(text):
    if not ADMIN_ID: return
    try: bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e: print(f"Telegram send failed: {e}")

def send_telegram_with_keyboard(text, markup):
    if not ADMIN_ID: return
    try: bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e: print(f"Telegram send_keyboard failed: {e}")

_KNOWN_RISK_PCT_KEY = "last_known_risk_pct"


def check_manual_risk_override(state: dict) -> None:
    """
    Detect when risk_pct_input in sentinel_config.json was changed outside of
    the Telegram flow (i.e. manually edited or by a script). When detected,
    log it via mark_adherence and send a Telegram alert.
    """
    try:
        cfg = get_account_settings()
        current_pct = float(cfg.get("risk_pct_input", 0.5))
        last_known = state.get(_KNOWN_RISK_PCT_KEY)

        if last_known is not None and abs(current_pct - float(last_known)) > 0.001:
            delta = current_pct - float(last_known)
            direction = "⬆️" if delta > 0 else "⬇️"
            are.mark_adherence(
                recommended_pct=float(last_known),
                actual_pct=current_pct,
                followed=False,
                reason="Manual override detected by risk monitor",
            )
            are.log_risk_journal({
                "direction": "up" if delta > 0 else "down_fast",
                "current_risk_pct": float(last_known),
                "recommended_risk_pct": float(last_known),
                "action": "manual_override",
                "actual_pct_set": current_pct,
                "nav": ec.get_nav_with_freshness()["nav"],
            })
            alert = (
                f"{RTL}⚠️ *זוהתה שינוי ידנית בסיכון*\n"
                f"{RTL}risk\\_pct שונה מחוץ לטלגרם\n"
                f"{RTL}{direction} `{float(last_known):.2f}%` → `{current_pct:.2f}%`\n"
                f"{RTL}נרשם ביומן הסיכון כ-manual override."
            )
            send_telegram(alert)

        state[_KNOWN_RISK_PCT_KEY] = current_pct
    except Exception as e:
        print(f"check_manual_risk_override error: {e}")


def main():
    state = load_state()
    check_manual_risk_override(state)

    account_settings = get_account_settings()
    nav_info = ec.get_nav_with_freshness()
    acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited", 7500.0))
    target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
    target_risk_usd = acc_size * (target_risk_pct / 100)
    
    res = supabase.table("trades").select("*").execute()
    df = pd.DataFrame(res.data)
    if df.empty: return
    
    pos_res = ec.get_open_positions_campaign(df)
    if not pos_res["ok"] or pos_res["data"].empty: return
    open_pos = pos_res["data"]
    
    spy_hist = ec.get_cached_history("SPY", "1y", "1d")
    total_algo_exposure = 0.0
    algo_oversight_positions = []
    new_position_state = {}
    now_ts = datetime.utcnow().timestamp()

    for _, row in open_pos.iterrows():
        sym, setup, entry = row["symbol"], row["setup_type"], float(row["price"])
        qty, sl, init_sl = float(row["quantity"]), float(row["stop_loss"]), float(row["initial_stop"])
        realized_pnl, entry_date = float(row["realized_pnl"]), row["entry_date"]
        campaign_id, mgt_state = row["campaign_id"], row.get("management_state", "full_position")
        
        curr = ec.get_live_price(sym)
        if curr is None: curr = entry
        
        open_pnl = (curr - entry) * qty
        pos_value = curr * qty
        weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0
        if str(setup).upper() == "ALGO": total_algo_exposure += pos_value
        
        base_price = row.get('base_price', entry)
        base_qty = row.get('base_qty', qty)
        
        init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
        total_pos_profit = open_pnl + realized_pnl
        
        total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
        open_r = (open_pnl / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl / original_campaign_risk) if original_campaign_risk > 0 else 0)
        
        r_str = f"`{open_r:.1f}R`" + (" *(Target Base)*" if str(setup).upper() == "ALGO" else "")
        
        engine_res = ec.evaluate_position_engine(
            symbol=sym, entry_price=entry, entry_date_str=entry_date, current_stop=sl,
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r,
            target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist
        )
        
        if not engine_res["ok"]: continue
        engine = engine_res["data"]
        
        alert_key = build_position_alert_key(row, engine)
        prev = state["positions"].get(campaign_id)
        
        do_alert, new_alert_ts = should_alert(prev, engine["status"], alert_key)
        
        if do_alert:
            issues = f" | {' | '.join(engine['issues'])}" if engine["issues"] else ""
            sizing_str = engine.get("sizing_status", "✅ תקין")
            
            msg = (
                f"{RTL}🚨 *Sentinel Live Alert*\n"
                f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
                f"{RTL}סטאפ: `{setup}` | ניהול: `{mgt_state}`\n"
                f"{RTL}מחיר ממוצע: `${curr:.2f}` | חשיפה: `{weight_pct:.1f}%`\n"
            )
            if str(setup).upper() != "ALGO":
                msg += f"{RTL}סיכון מקורי (קמפיין): `${original_campaign_risk:.0f}` (יעד: `${target_risk_usd:.0f}`)\n"
                if sizing_str != "✅ תקין":
                    if "גבוה" in sizing_str: msg += f"{RTL}⚠️ *Sizing:* סיכון כניסה גבוה מדי!\n"
                    elif "נמוך" in sizing_str: msg += f"{RTL}📉 *Sizing:* סיכון כניסה נמוך מדי!\n"
                
                if total_campaign_r <= -1.25 and original_campaign_risk > 0:
                    msg += f"{RTL}🚨 *Execution:* חריגה חמורה מהסטופ ({total_campaign_r:.1f}R)\n"
            
            msg += (
                f"{RTL}Open R: {r_str}\n"
                f"{RTL}סטטוס: *{engine['status']}*{issues}\n"
                f"{RTL}פעולה: *{engine['action']}*\n"
                f"{RTL}טריגר: `{engine['trigger']}`"
            )
            
            if str(setup).upper() != "ALGO" and engine["suggested_stop"] > 0 and engine["suggested_stop"] != sl:
                msg += f"\n{RTL}סטופ מוצע: `${engine['suggested_stop']:.2f}`"
                
            send_telegram(msg)
            
        new_pos_entry = {
            "status": engine["status"], "alert_key": alert_key,
            "updated_at": datetime.utcnow().isoformat(), "last_alert_ts": new_alert_ts,
        }
        # Carry over threshold-tracking fields from previous state
        if prev:
            for carry_key in ("peak_open_r", "last_deviation_class", "last_deviation_ts",
                              "last_giveback_class", "last_giveback_ts", "checkpoints_hit",
                              "position_state", "state_label", "breakeven_alerted",
                              "algo_loss_streak", "algo_streak_alerted_yellow",
                              "algo_streak_alerted_orange", "algo_deep_loss_alerted",
                              "last_state_alert_ts", "last_state_alert_type",
                              "runner_decision", "runner_decision_ts"):
                if carry_key in prev:
                    new_pos_entry[carry_key] = prev[carry_key]

        # Risk Deviation / Giveback / Profit Protection Checkpoints
        is_algo = ec.is_algo_position(setup, sym)
        threshold_alerts, threshold_updates = check_position_risk_thresholds(
            sym=sym, setup=setup, open_r=open_r, open_pnl_usd=open_pnl,
            target_risk_usd=target_risk_usd, is_algo=is_algo,
            prev_state=new_pos_entry, now_ts=now_ts,
        )
        new_pos_entry.update(threshold_updates)

        # Enrich checkpoint alerts with Phase 1 protected-profit / giveback values
        _side_pos = "BUY"
        _open_pnl_at_stop = ec.compute_open_pnl_at_stop(_side_pos, entry, sl, qty)
        _protected_profit  = ec.compute_protected_profit_usd(realized_pnl, _open_pnl_at_stop)
        _giveback_usd      = ec.compute_giveback_usd(open_pnl, _open_pnl_at_stop)
        _giveback_pct      = ec.compute_giveback_pct_of_open_profit(_giveback_usd, open_pnl)
        _capital_at_risk   = ec.compute_capital_at_risk_usd(_side_pos, entry, sl, qty)

        for alert_text in threshold_alerts:
            send_telegram(alert_text)

        # ── Phase 3: Position State Machine ──────────────────────────────────
        # Age in days since campaign entry
        try:
            _entry_dt = pd.to_datetime(entry_date).to_pydatetime().replace(tzinfo=None)
            _age_days = max(0.0, float((datetime.utcnow() - _entry_dt).days))
        except Exception:
            _age_days = 0.0

        # Earnings window (cached, non-blocking)
        _days_to_earnings = None
        try:
            _earn = ec.fetch_next_earnings_date(sym)
            if _earn.get("ok") and _earn.get("days_to_event") is not None:
                _days_to_earnings = int(_earn["days_to_event"])
        except Exception:
            pass

        _mgt_mode = ec.classify_management_mode(setup, sym)

        _state_result = ec.compute_position_state(
            side=_side_pos,
            management_mode=_mgt_mode,
            age_days=_age_days,
            open_r=open_r,
            realized_pnl=realized_pnl,
            original_campaign_risk=original_campaign_risk,
            current_price=curr,
            current_stop=sl,
            days_to_earnings=_days_to_earnings,
            follow_through_score=None,
            violation_score=0,
            has_new_high_since_entry=True,
            has_open_quantity=(qty > 0),
        )

        _new_state  = _state_result["state"]
        _prev_state = new_pos_entry.get("position_state", "")

        # Phase 5: state-change alerts with oscillation-safe cooldown
        if _new_state != _prev_state and _mgt_mode != "algo_observed":
            _last_sa_type = new_pos_entry.get("last_state_alert_type", "")
            _last_sa_ts   = new_pos_entry.get("last_state_alert_ts", 0.0)
            _fire = _should_fire_state_alert(_new_state, _last_sa_type,
                                             _last_sa_ts, now_ts)
            if _fire:
                if _new_state == ec.POSITION_STATE_RUNNER:
                    _dec     = new_pos_entry.get("runner_decision", "")
                    _dec_ts  = new_pos_entry.get("runner_decision_ts", 0.0)
                    if _dec == "hold" and (now_ts - _dec_ts) < 24 * 3600:
                        _fire = False  # user decided to hold — suppress for 24h
                    else:
                        send_telegram_with_keyboard(
                            _runner_state_alert(sym, setup, open_r,
                                                _protected_profit, _giveback_usd, _giveback_pct,
                                                sl, _days_to_earnings),
                            _runner_decision_keyboard(sym, campaign_id),
                        )
                elif _new_state == ec.POSITION_STATE_BROKEN:
                    send_telegram(_broken_state_alert(sym, setup, open_r,
                                                       _state_result["reason"]))
                elif _new_state == ec.POSITION_STATE_DEAD_MONEY:
                    send_telegram(_dead_money_alert(sym, setup, _age_days, open_r))
                else:
                    _fire = False  # no alert for this state — don't update ts
            if _fire:
                new_pos_entry["last_state_alert_type"] = _new_state
                new_pos_entry["last_state_alert_ts"]   = now_ts

        # Break-even Protocol: 3R+ but capital still at risk (one-time alert)
        if (open_r >= 3.0
                and _capital_at_risk > 0
                and not new_pos_entry.get("breakeven_alerted", False)
                and _mgt_mode != "algo_observed"):
            send_telegram(_breakeven_protocol_alert(sym, open_r, _capital_at_risk))
            new_pos_entry["breakeven_alerted"] = True

        new_pos_entry["position_state"] = _new_state
        new_pos_entry["state_label"]    = _state_result["label"]
        # ─────────────────────────────────────────────────────────────────────

        # ── Phase 4: ALGO Oversight per-position ─────────────────────────────
        if _mgt_mode == "algo_observed":
            # Consecutive loss streak (one run = ~5 min)
            _prev_streak = new_pos_entry.get("algo_loss_streak", 0)
            _new_streak = _prev_streak + 1 if open_r < 0 else 0
            new_pos_entry["algo_loss_streak"] = _new_streak

            _alerted_yellow = new_pos_entry.get("algo_streak_alerted_yellow", False)
            _alerted_orange = new_pos_entry.get("algo_streak_alerted_orange", False)

            if _new_streak >= 5 and not _alerted_orange:
                send_telegram(_algo_loss_streak_alert(sym, open_r, _new_streak, "orange"))
                new_pos_entry["algo_streak_alerted_orange"] = True
            elif _new_streak >= 3 and not _alerted_yellow:
                send_telegram(_algo_loss_streak_alert(sym, open_r, _new_streak, "yellow"))
                new_pos_entry["algo_streak_alerted_yellow"] = True

            if _new_streak == 0:  # Position recovered — reset streak flags
                new_pos_entry["algo_streak_alerted_yellow"] = False
                new_pos_entry["algo_streak_alerted_orange"] = False

            # Single deep-loss alert (open_r ≤ −2R)
            if open_r <= -2.0 and not new_pos_entry.get("algo_deep_loss_alerted", False):
                send_telegram(_algo_deep_loss_alert(sym, open_r))
                new_pos_entry["algo_deep_loss_alerted"] = True
            if open_r > -1.0:  # Significant recovery — allow re-alert if it dips again
                new_pos_entry["algo_deep_loss_alerted"] = False

            # Collect for portfolio-level summary check
            _oversight_score = engine.get("risk_visibility_score", 0)
            algo_oversight_positions.append({
                "symbol": sym, "pos_value": pos_value,
                "oversight_score": _oversight_score, "open_r": open_r,
                "campaign_id": campaign_id,
            })
        # ─────────────────────────────────────────────────────────────────────

        new_position_state[campaign_id] = new_pos_entry
        
    # ── Phase 4: ALGO Oversight — portfolio-level visibility check ───────────
    if algo_oversight_positions:
        _algo_summary = ec.compute_algo_oversight_summary(algo_oversight_positions, acc_size)
        if _algo_summary["visibility_below_threshold"]:
            _prev_vis_ts = state.get("algo_visibility_alerted_ts", 0)
            if (now_ts - _prev_vis_ts) > 24 * 3600:
                send_telegram(_algo_visibility_alert(
                    _algo_summary["visibility_avg"],
                    _algo_summary["n_positions"],
                ))
                state["algo_visibility_alerted_ts"] = now_ts

    algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
    prev_cluster = state.get("cluster", {})
    prev_cluster_status = prev_cluster.get("status", "green")
    last_cluster_alert = prev_cluster.get("last_alert_ts", 0)
    
    if algo_cluster_pct > ec.ALGO_CLUSTER_CRITICAL_PCT: # 35.0
        cluster_status = "red"
    elif algo_cluster_pct > ec.ALGO_CLUSTER_WARNING_PCT: # 30.0
        if prev_cluster_status == "red" and algo_cluster_pct > 34.0: cluster_status = "red"
        else: cluster_status = "yellow"
    else:
        if prev_cluster_status == "yellow" and algo_cluster_pct > 29.0: cluster_status = "yellow"
        else: cluster_status = "green"
    
    alert_cluster = False
    if cluster_status != prev_cluster_status:
        alert_cluster = True
        last_cluster_alert = now_ts
    elif cluster_status in ["red", "yellow"] and (now_ts - last_cluster_alert) > (6 * 3600):
        alert_cluster = True
        last_cluster_alert = now_ts
        
    if alert_cluster:
        if cluster_status == "red": send_telegram(f"{RTL}🚨 *חריגת אדום באשכול ALGO*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן\n{RTL}פעולה: *חסום כניסות חדשות והפחת חשיפה מהפוזיציות הגדולות ביותר*")
        elif cluster_status == "yellow": send_telegram(f"{RTL}⚠️ *התראת אשכול ALGO*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן\n{RTL}פעולה: *עצור כניסות חדשות עד חזרה לאזור בטוח*")
        elif cluster_status == "green" and prev_cluster.get("status") in ("yellow", "red"): send_telegram(f"{RTL}✅ *אשכול ALGO חזר לאזור תקין*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן")
            
    state["positions"] = new_position_state
    state["cluster"] = {"status": cluster_status, "algo_cluster_pct": round(algo_cluster_pct, 2), "updated_at": datetime.utcnow().isoformat(), "last_alert_ts": last_cluster_alert}

    # --- Adaptive Risk Proactive Alert ---
    try:
        current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
        nav_for_risk = float(account_settings.get("nav", acc_size))
        closed_camps = are.compute_closed_campaigns(df)
        risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, nav_for_risk)

        if risk_rec.get("ok") and risk_rec["direction"] != "hold":
            prev_alert = state.get("risk_alert", {})
            last_risk_ts = prev_alert.get("ts", 0)
            last_direction = prev_alert.get("direction", "")

            same_direction_recently = (
                last_direction == risk_rec["direction"]
                and (now_ts - last_risk_ts) < 24 * 3600
            )

            if not same_direction_recently:
                rec_pct = risk_rec["recommended_risk_pct"]
                curr_pct = risk_rec["current_risk_pct"]
                curr_usd = risk_rec["current_risk_usd"]
                rec_usd = risk_rec["recommended_risk_usd"]
                arrow = "⬆️" if risk_rec["direction"] == "up" else "⬇️⬇️"
                heat = risk_rec["heat_score"]
                step = risk_rec["step_type"]

                alert_text = (
                    f"{RTL}🎯 *התראת סיכון אדפטיבי*\n"
                    f"{RTL}───────────────\n"
                    f"{RTL}חום מסחר: {risk_rec['heat_color']} `{heat:.0f}%` | {step}\n"
                    f"{RTL}רמה נוכחית: `{curr_pct:.2f}%` (`${curr_usd:,.0f}` לעסקה)\n"
                    f"{RTL}{arrow} המלצה: `{rec_pct:.2f}%` (`${rec_usd:,.0f}` לעסקה)\n\n"
                    f"{RTL}האם לאשר שינוי סיכון?"
                )
                markup = telebot.types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    telebot.types.InlineKeyboardButton(
                        "✅ מאשר שינוי",
                        callback_data=f"risk_confirm|YES|{rec_pct}|{curr_pct}"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "❌ דוחה (חובה: הסבר)",
                        callback_data=f"risk_confirm|NO|{rec_pct}|{curr_pct}"
                    )
                )
                send_telegram_with_keyboard(alert_text, markup)
                state["risk_alert"] = {
                    "direction": risk_rec["direction"],
                    "ts": now_ts,
                    "rec_pct": rec_pct,
                    "curr_pct": curr_pct,
                }
    except Exception as e:
        print(f"Risk alert error: {e}")

    save_state(state)

if __name__ == "__main__":
    print("🛡️ Sentinel Risk Monitor Active")
    while True:
        try: main()
        except Exception as e: print(f"🚨 Risk Monitor Crash: {e}")
        time.sleep(300)
