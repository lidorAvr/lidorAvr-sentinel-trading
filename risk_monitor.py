import os, json, time, telebot
from telebot import types
import pandas as pd
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import engine_core as ec
import alert_tasks as at
import sentinel_journal as sj

import action_queue_live
import post_entry_intake_push
import live_alert_dedupe
import plan_monitor
live_alert_dedupe.install()
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

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"positions": {}, "cluster": {}}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False, indent=2)

def get_ibkr_nav():
    try:
        import ibkr_nav as navsvc
        return navsvc.load_current_nav()
    except Exception:
        return None

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

def should_alert(prev, current_status, current_key):
    now_ts = datetime.utcnow().timestamp()
    if prev is None: return True, now_ts
    
    prev_status = prev.get("status")
    prev_key = prev.get("alert_key")
    last_alert_ts = prev.get("last_alert_ts", 0)
    
    if STATUS_RANK.get(current_status, 0) > STATUS_RANK.get(prev_status, 0): return True, now_ts
    if prev_key != current_key: return True, now_ts
    if current_status in ["🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו"]:
        if (now_ts - last_alert_ts) > (6 * 3600):
            return True, now_ts
            
    return False, last_alert_ts

def send_telegram(text, reply_markup=None):
    if not ADMIN_ID: return
    try: bot.send_message(ADMIN_ID, text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e: print(f"Telegram send failed: {e}")


def build_alert_reply_markup(task_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(text="✅ בוצע", callback_data=f"at_done|{task_id}"),
        types.InlineKeyboardButton(text="📝 לא בוצע", callback_data=f"at_no|{task_id}")
    )
    return keyboard

def check_alert_task_reminders():
    try:
        for task in at.due_open_tasks():
            task_id = task.get("task_id")
            send_telegram(at.reminder_text(task), reply_markup=build_alert_reply_markup(task_id))
            at.mark_reminded(task_id)
    except Exception as e:
        print(f"Alert task reminder failed: {e}")


def _risk_monitor_main_without_action_queue_live():
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
        
        hist_target_risk = float(row.get("target_risk_usd") or 0)
        effective_target_risk = hist_target_risk if hist_target_risk > 0 else target_risk_usd

        total_campaign_r = (total_pos_profit / effective_target_risk) if str(setup).upper() == 'ALGO' and effective_target_risk > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
        open_r = (open_pnl / effective_target_risk) if str(setup).upper() == 'ALGO' and effective_target_risk > 0 else ((open_pnl / original_campaign_risk) if original_campaign_risk > 0 else 0)
        
        r_str = f"`{open_r:.1f}R`" + (" *(Target Base)*" if str(setup).upper() == "ALGO" else "")
        
        engine_res = ec.evaluate_position_engine(
            symbol=sym, entry_price=entry, entry_date_str=entry_date, current_stop=sl,
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r,
            target_risk_usd=effective_target_risk, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist,
            quantity=qty, initial_quantity=float(row.get("initial_qty") or base_qty or qty)
        )
        
        if not engine_res["ok"]: continue
        engine = engine_res["data"]
        sj.record_position_cycle(
            supabase,
            row,
            engine,
            current_price=curr,
            open_r=open_r,
            total_r=total_campaign_r,
            exposure_pct=weight_pct,
        )
        state_he = engine.get("state_he") or engine.get("position_state")
        violation_count = int(engine.get("violation_count", 0) or 0)
        decision_card = engine.get("decision_card") or {}
        decision_bias = decision_card.get("bias_he") or decision_card.get("bias")
        decision_primary = decision_card.get("primary_action")
        
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
            
            if state_he:
                msg += f"{RTL}מצב ניהולי: *{state_he}* | הפרות: `{violation_count}`\n"
            if decision_primary:
                msg += f"{RTL}כרטיס החלטה: *{decision_bias}* | {decision_primary}\n"
            msg += (
                f"{RTL}Open R: {r_str}\n"
                f"{RTL}סטטוס: *{engine['status']}*{issues}\n"
                f"{RTL}פעולה: *{engine['action']}*\n"
                f"{RTL}טריגר: `{engine['trigger']}`"
            )
            
            if str(setup).upper() != "ALGO" and engine["suggested_stop"] > 0 and engine["suggested_stop"] != sl:
                msg += f"\n{RTL}סטופ מוצע: `${engine['suggested_stop']:.2f}`"
                
            send_telegram(msg)
            
        new_position_state[campaign_id] = {"status": engine["status"], "alert_key": alert_key, "updated_at": datetime.utcnow().isoformat(), "last_alert_ts": new_alert_ts}
        
    algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
    prev_cluster = state.get("cluster", {})
    prev_cluster_status = prev_cluster.get("status", "green")
    last_cluster_alert = prev_cluster.get("last_alert_ts", 0)
    now_ts = datetime.utcnow().timestamp()
    
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
    save_state(state)


def main(*args, **kwargs):
    result = _risk_monitor_main_without_action_queue_live(*args, **kwargs)

    try:
        action_queue_live.push_live_action_queue(globals().get("supabase"))
    except Exception as e:
        print("ActionQueue Live warning: {}".format(e), flush=True)

    return result



# Sentinel Post-Entry Intake live push wrapper.
try:
    _sentinel_main_before_intake_push = main

    def main(*args, **kwargs):
        result = _sentinel_main_before_intake_push(*args, **kwargs)
        try:
            post_entry_intake_push.push_pending_intake(rebuild=True)
        except Exception as e:
            print(f"PostEntry Intake warning: {e}")
        return result
except NameError:
    pass


# Sentinel approved plan monitor wrapper.
try:
    _sentinel_main_before_plan_monitor = main

    def main(*args, **kwargs):
        result = _sentinel_main_before_plan_monitor(*args, **kwargs)
        try:
            plan_monitor.run()
        except Exception as e:
            print(f"PlanMonitor warning: {e}")
        return result
except NameError:
    pass

if __name__ == "__main__":
    print("🛡️ Sentinel Risk Monitor Active")
    while True:
        try:
            main()
            check_alert_task_reminders()
        except Exception as e: print(f"🚨 Risk Monitor Crash: {e}")
        time.sleep(300)
