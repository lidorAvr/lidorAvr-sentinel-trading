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
    return json.dumps({
        "status": engine_data["status"],
        "action": engine_data["action"],
        "trigger": engine_data["trigger"],
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

    # Escalation: status worsened → always alert immediately
    if STATUS_RANK.get(current_status, 0) > STATUS_RANK.get(prev_status, 0): return True, now_ts
    # State change: alert content changed → always alert
    if prev_key != current_key: return True, now_ts
    # Repeat cooldown: same status, same content → only during market hours to avoid overnight spam
    if current_status in ["🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו"]:
        if (now_ts - last_alert_ts) > (6 * 3600) and is_during_us_market_hours():
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


def _checkpoint_alert_text(sym, setup, checkpoint_r, open_r, is_algo):
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
    return (
        f"{RTL_M}🏁 *Profit Protection Checkpoint — {checkpoint_r:.0f}R*\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}Open R: `{open_r:.2f}R` חצה סף `{checkpoint_r:.0f}R`\n"
        f"{RTL_M}{action_line}"
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

    # ── Giveback Monitor (only when meaningful profit existed) ────────────
    if peak_open_r >= 1.5 and open_r < peak_open_r:
        gb = ec.compute_giveback_from_peak(peak_open_r, open_r)
        prev_gb_class = prev_state.get("last_giveback_class", "natural")
        prev_gb_ts = prev_state.get("last_giveback_ts", 0)
        alert_classes_to_notify = {"watch", "tighten", "protection_failure"}

        escalated = GIVEBACK_RANK.get(gb["classification"], 0) > GIVEBACK_RANK.get(prev_gb_class, 0)
        cooled_down = (now_ts - prev_gb_ts) > GIVEBACK_COOLDOWN_SEC
        should_fire = gb["classification"] in alert_classes_to_notify and (escalated or cooled_down)

        if should_fire:
            alerts.append(_giveback_alert_text(sym, setup, peak_open_r, open_r, gb, is_algo))
            updates["last_giveback_class"] = gb["classification"]
            updates["last_giveback_ts"] = now_ts
        elif gb["classification"] not in ("na", "natural"):
            updates["last_giveback_class"] = gb["classification"]

    return alerts, updates


def send_telegram(text):
    if not ADMIN_ID: return
    try: bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e: print(f"Telegram send failed: {e}")

def send_telegram_with_keyboard(text, markup):
    if not ADMIN_ID: return
    try: bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e: print(f"Telegram send_keyboard failed: {e}")

def main():
    state = load_state()
    account_settings = get_account_settings()
    ibkr_nav = get_ibkr_nav()
    acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
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
                              "last_giveback_class", "last_giveback_ts", "checkpoints_hit"):
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
        for alert_text in threshold_alerts:
            send_telegram(alert_text)

        new_position_state[campaign_id] = new_pos_entry
        
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
