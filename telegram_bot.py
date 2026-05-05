import os, telebot, json, traceback
import pandas as pd
from telebot import types
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime
import xml.etree.ElementTree as ET
import engine_core as ec
import performance_lab as pl
import action_queue_state as aqs
import alert_tasks as at

import post_entry_intake_ui
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
bot = telebot.TeleBot(TOKEN)


post_entry_intake_ui.register(
    bot,
    lambda: globals().get("supabase"),
    lambda: globals().setdefault("user_state", {})
)

# --- Action Queue UI v2: compact queue + working callbacks ---
try:
    import action_queue_ui_v2
    action_queue_ui_v2.register(
        bot,
        lambda: globals().get("supabase"),
        lambda: globals().setdefault("user_state", {})
    )
    print("✅ Action Queue UI v2 registered")
except Exception as _aq_ui_v2_error:
    print(f"⚠️ Action Queue UI v2 registration failed: {_aq_ui_v2_error}")

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

user_state = {}
RTL = "\u200F"

LRM = "\u200E"
SEP = "━━━━━━━━━━━━"

def md_plain(value):
    text = "" if value is None else str(value)
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "'")

def tv(value):
    return "`" + LRM + md_plain(value) + LRM + "`"

def fmt_pct(value, digits=1):
    try:
        return tv(("{:." + str(digits) + "f}%").format(float(value)))
    except:
        return tv(value)

def fmt_r(value, digits=1):
    try:
        return tv(("{:." + str(digits) + "f}R").format(float(value)))
    except:
        return tv(value)

def fmt_usd(value, digits=0):
    try:
        return tv(("$ {:,." + str(digits) + "f}").format(float(value)).replace("$ ", "$"))
    except:
        return tv(value)

def report_section(title):
    return "\n{}*{}*\n{}{}\n".format(RTL, md_plain(title), RTL, SEP)

def report_line(label, value, icon="•"):
    return "{}{} *{}:* {}\n".format(RTL, icon, md_plain(label), value)

def report_note(text, max_chars=260):
    clean = md_plain(text)
    if len(clean) > max_chars:
        clean = clean[:max_chars].rstrip() + "..."
    return "{}_{}_\n".format(RTL, clean)

def gov_mode_he(mode):
    return {
        "EXPANSION": "הרחבה מדודה",
        "NORMAL": "רגיל",
        "SELECTIVE": "סלקטיבי",
        "CAUTION": "זהירות",
        "REDUCED": "מוקטן",
        "PILOT": "פיילוט בלבד",
        "BLOCKED": "חסום",
        "LEARNING": "למידה",
        "UNKNOWN": "לא ידוע",
    }.get(str(mode), str(mode))

def exposure_status_he(status):
    return {
        "BALANCED": "מאוזן",
        "UNDEREXPOSED": "חשיפה נמוכה מדי",
        "LIGHT": "קל מדי",
        "FULL": "מלא",
        "OVEREXPOSED": "חשיפת יתר",
        "CAUTION": "זהירות",
        "BLOCKED": "חסום",
        "CASH_ONLY": "מזומן בלבד",
        "ALGO_OVEREXPOSED": "חשיפת ALGO חריגה",
    }.get(str(status), str(status))

def rtl_wrap_text(text):
    if not isinstance(text, str) or not text:
        return text
    if text.startswith(RTL):
        return text
    return RTL + text

def install_telegram_rtl_guard():
    if getattr(bot, "_sentinel_rtl_guard", False):
        return

    raw_send_message = bot.send_message
    raw_edit_message_text = bot.edit_message_text

    def send_message_rtl(*args, **kwargs):
        args = list(args)
        if len(args) >= 2:
            args[1] = rtl_wrap_text(args[1])
        elif "text" in kwargs:
            kwargs["text"] = rtl_wrap_text(kwargs["text"])
        return raw_send_message(*args, **kwargs)

    def edit_message_text_rtl(*args, **kwargs):
        args = list(args)
        if len(args) >= 1:
            args[0] = rtl_wrap_text(args[0])
        elif "text" in kwargs:
            kwargs["text"] = rtl_wrap_text(kwargs["text"])
        return raw_edit_message_text(*args, **kwargs)

    bot.send_message = send_message_rtl
    bot.edit_message_text = edit_message_text_rtl
    bot._sentinel_rtl_guard = True

install_telegram_rtl_guard()


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

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🎯 תור פעולות"),
        types.KeyboardButton("📊 חדר מצב (פוזיציות)")
    )
    markup.add(
        types.KeyboardButton("🌡️ משטר שוק וסיכונים"),
        types.KeyboardButton("🔬 סקירת מניה")
    )
    markup.add(
        types.KeyboardButton("🔍 סריקת יומן (Backlog)"),
        types.KeyboardButton("🧹 ארכיון עסקאות (Legacy)")
    )
    markup.add(types.KeyboardButton("📈 מעבדת ביצועים"), types.KeyboardButton("❓ פקודות מערכת"))
    markup.add(types.KeyboardButton("🧾 תוכניות ניהול"))
    return markup

def get_rating_keyboard(t_id, field):
    keyboard = types.InlineKeyboardMarkup(row_width=5)
    btns = [types.InlineKeyboardButton(text=str(i), callback_data=f"v|{t_id}|{field}|{i}") for i in range(1, 11)]
    keyboard.add(*btns)
    keyboard.add(types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|{field}|-1"))
    return keyboard

def get_setup_keyboard(t_id):
    setups = ["VCP", "ALGO", "SWING", "EP"]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for s in setups: keyboard.add(types.InlineKeyboardButton(text=s, callback_data=f"v|{t_id}|setup_type|{s}"))
    keyboard.add(types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|setup_type|Skipped"))
    return keyboard


POSITION_STATE_LABELS = {
    "New Entry": "כניסה חדשה",
    "Working": "עובד תקין",
    "Tennis Ball": "התאוששות חזקה",
    "Squat Watch": "פריצה בלי המשכיות",
    "Violation": "הפרות ניהול",
    "Breakeven Protect": "הגנת איזון",
    "Profit Protect": "הגנת רווח",
    "Climactic": "מהלך מתוח",
    "Dead Money": "הון תקוע",
    "Broken": "הטרייד נכשל",
    "ALGO Guard": "בקרת אלגו",
}

def format_position_state_line(data):
    if not data:
        return ""
    state = data.get("state_he") or POSITION_STATE_LABELS.get(data.get("position_state"), data.get("position_state"))
    if not state:
        return ""
    count = int(data.get("violation_count", 0) or 0)
    priority = data.get("decision_priority", "")
    preferred = data.get("preferred_action", "")
    line = f"{RTL}• מצב ניהולי: {state} | הפרות: `{count}`"
    if priority:
        line += f" | עדיפות: {priority}"
    line += "\n"
    if preferred:
        line += f"{RTL}• החלטה מועדפת: {preferred}\n"
    return line

def format_position_state_block(data):
    if not data:
        return ""
    state = data.get("state_he") or POSITION_STATE_LABELS.get(data.get("position_state"), data.get("position_state"))
    if not state:
        return ""
    violations = data.get("violations") or []
    summary = data.get("decision_summary") or ""
    preferred = data.get("preferred_action") or ""
    priority = data.get("decision_priority") or ""
    txt = f"{RTL}🧭 *מצב ניהולי:*\n"
    txt += f"• מצב: *{state}*"
    if priority:
        txt += f" | עדיפות: `{priority}`"
    txt += "\n"
    txt += f"• הפרות: `{len(violations)}`"
    if violations:
        txt += " | " + ", ".join(violations[:4])
    txt += "\n"
    if preferred:
        txt += f"• פעולה מועדפת: *{preferred}*\n"
    if summary:
        txt += f"• סיכום: {summary}\n"
    return txt



def format_decision_card_line(data):
    card = (data or {}).get("decision_card") or {}
    if not card:
        return ""
    bias = card.get("bias_he") or card.get("bias") or "החלטה"
    action = card.get("primary_action") or ""
    urgency = card.get("urgency") or ""
    txt = f"{RTL}• כרטיס החלטה: *{bias}*"
    if urgency:
        txt += f" | דחיפות: `{urgency}`"
    txt += "\n"
    if action:
        txt += f"{RTL}• פעולה לפי הכללים: {action}\n"
    reasons = card.get("reasons") or []
    if reasons:
        txt += f"{RTL}• למה: " + " | ".join(reasons[:3]) + "\n"
    return txt

def format_decision_card_block(data):
    card = (data or {}).get("decision_card") or {}
    if not card:
        return ""
    bias = card.get("bias_he") or card.get("bias") or "החלטה"
    action = card.get("primary_action") or ""
    urgency = card.get("urgency") or ""
    reasons = card.get("reasons") or []
    alternatives = card.get("alternatives") or []
    consequence = card.get("consequence") or ""

    txt = f"{RTL}🎯 *כרטיס החלטה: {bias}*\n"
    if urgency:
        txt += f"• דחיפות: `{urgency}`\n"
    if action:
        txt += f"• פעולה מועדפת: *{action}*\n"
    if reasons:
        txt += "• בסיס ההחלטה: " + " | ".join(reasons[:4]) + "\n"
    if alternatives:
        txt += "• אפשרויות: " + " | ".join(alternatives[:3]) + "\n"
    if consequence:
        txt += f"• אם לא פועלים: {consequence}\n"
    return txt


def send_long_message(chat_id, text, reply_markup=None):
    max_len = 3900
    if len(text) <= max_len:
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        return
    parts = []
    while len(text) > 0:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_idx = text.rfind('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n', 0, max_len)
        if split_idx == -1:
            split_idx = text.rfind('\n', 0, max_len)
            if split_idx == -1: split_idx = max_len
        else: split_idx += len('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n')
        parts.append(text[:split_idx])
        text = text[split_idx:]
    for i, part in enumerate(parts):
        try:
            if i == len(parts) - 1: bot.send_message(chat_id, part, reply_markup=reply_markup, parse_mode="Markdown")
            else: bot.send_message(chat_id, part, parse_mode="Markdown")
        except Exception as e: print(f"Error sending part {i}: {e}")

def get_next_missing(chat_id):
    try:
        query_or = "setup_type.is.null,quality.is.null,and(side.eq.BUY,initial_stop.is.null),and(side.eq.BUY,initial_stop.eq.0),and(side.eq.SELL,score.is.null),and(side.eq.SELL,image_url.is.null),and(side.eq.SELL,management_notes.is.null)"
        res = supabase.table("trades").select("*").or_(query_or).order("trade_date", desc=False).order("trade_id", desc=False).limit(100).execute()
        t = None
        for row in res.data:
            if str(row.get('setup_type')) == 'Legacy': continue
            if row.get('side', '').upper() == 'BUY':
                cid = row.get('campaign_id')
                if cid:
                    older_buys = supabase.table("trades").select("*").eq("campaign_id", cid).eq("side", "BUY").lt("trade_date", row["trade_date"]).execute()
                    if older_buys.data:
                        first_b = older_buys.data[0]
                        upd = {"setup_type": first_b.get("setup_type"), "quality": first_b.get("quality"), "initial_stop": first_b.get("initial_stop"), "stop_loss": first_b.get("stop_loss")}
                        supabase.table("trades").update(upd).eq("trade_id", row["trade_id"]).execute()
                        continue
                if str(row.get('setup_type')).upper() == 'ALGO':
                    init_sl = row.get('initial_stop')
                    if init_sl is None or init_sl == 0:
                        supabase.table("trades").update({"initial_stop": -1, "stop_loss": -1}).eq("trade_id", row["trade_id"]).execute()
                        continue 
            t = row
            break
        if not t:
            bot.send_message(chat_id, "✅ *היומן מעודכן לחלוטין!*\nאין חוסרים במערכת.", reply_markup=get_main_menu(), parse_mode="Markdown")
            return
        t_id, symbol, side, t_date = t['trade_id'], t['symbol'], t['side'], t['trade_date']
        total_steps = 3 if side.upper() == 'BUY' else 5
        curr_step = 1
        if t.get('setup_type') is not None: curr_step += 1
        if t.get('quality') is not None: curr_step += 1
        if side.upper() == 'BUY':
            if t.get('initial_stop') not in [None, 0]: curr_step += 1
        elif side.upper() == 'SELL':
            if t.get('score') is not None: curr_step += 1
            if t.get('image_url') is not None and str(t.get('image_url')) not in ["None", "Skipped"]: curr_step += 1
        card = f"🏷️ *נכס:* {symbol} | {side}\n📅 *תאריך:* {t_date}\n🆔 *מזהה:* `{t_id}`\n⏳ *השלמת יומן - שלב {curr_step}/{total_steps}*\n〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️"
        if t.get('setup_type') is None:
            bot.send_message(chat_id, f"{card}\n🎯 *אנא סווג את האסטרטגיה (Setup):*", reply_markup=get_setup_keyboard(t_id), parse_mode="Markdown")
            return
        if t.get('quality') is None:
            if str(t.get('setup_type')).upper() == 'VCP':
                bot.send_message(chat_id, f"⏳ מנתח Trend Template עבור {symbol}...", parse_mode="Markdown")
                report_res = ec.get_minervini_analysis(symbol)
                report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
                bot.send_message(chat_id, f"{card}\n{report}\n\n💎 *מה הציון הסופי שלך? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"{card}\n💎 *מהי איכות הסטאפ בטרייד זה? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            return
        if side.upper() == "BUY":
            init_sl = t.get('initial_stop')
            if init_sl is None or init_sl == 0:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג / ללא סטופ", callback_data=f"v|{t_id}|initial_stop|-1"))
                bot.send_message(chat_id, f"{card}\n🎯 *מהו הסטופ ההתחלתי? (Initial Stop)*\nיש להקליד כעת את מחיר הסטופ המקורי (למשל 150.50).", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'initial_stop', 't_id': t_id}
                return
        if side.upper() == "SELL":
            if t.get('score') is None:
                bot.send_message(chat_id, f"{card}\n🏆 *כיצד היית מדרג את סגירת העסקה שלך? (1-10):*", reply_markup=get_rating_keyboard(t_id, 'score'), parse_mode="Markdown")
                return
            if t.get('image_url') is None or t.get('image_url') == "None":
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג על תמונה", callback_data=f"v|{t_id}|image_url|Skipped"))
                bot.send_message(chat_id, f"{card}\n🔗 *קישור לתמונה נדרש:*\nאנא הדבק קישור מ-TradingView.", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'image', 't_id': t_id}
                return
            if t.get('management_notes') is None:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ ללא הערה (דילוג)", callback_data=f"v|{t_id}|management_notes|Skipped"))
                bot.send_message(chat_id, f"{card}\n📝 *תובנות ניהול פוזיציה (אופציונלי):*\nהקלד כעת בהודעה את תובנות הניהול, תחושות או טעויות שביצעת (יישמר בעמודה ייעודית).", reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'management_notes', 't_id': t_id}
                return
    except Exception as e: bot.send_message(chat_id, f"❌ *שגיאת מערכת:* {str(e)}", parse_mode="Markdown")

def handle_drilldown(chat_id, symbol):
    msg_id = bot.send_message(chat_id, f"⏳ שואב נתוני רנטגן (Drill-down) עבור {symbol}...", parse_mode="Markdown").message_id
    try:
        res = supabase.table("trades").select("*").eq("symbol", symbol).execute()
        df = pd.DataFrame(res.data)
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"] or pos_res["data"].empty:
            bot.edit_message_text(f"❌ לא נמצאו פוזיציות פתוחות או קמפיינים פעילים עבור {symbol}.", chat_id, msg_id)
            return
        open_pos = pos_res["data"].iloc[0]
        entry, qty, sl = float(open_pos['price']), float(open_pos['quantity']), float(open_pos['stop_loss'])
        init_sl = float(open_pos['initial_stop'])
        realized_pnl = float(open_pos.get('realized_pnl') or 0)
        setup, mgt_state, entry_date = open_pos['setup_type'], open_pos.get('management_state', 'full_position'), open_pos['entry_date']
        curr = ec.get_live_price(symbol)
        if curr is None: curr = entry
        
        account_settings = get_account_settings()
        ibkr_nav = get_ibkr_nav()
        acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
        target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
        target_risk_usd = acc_size * (target_risk_pct / 100)
        
        weight_pct = ((curr * qty) / acc_size) * 100 if acc_size > 0 else 0
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")
        
        base_price = open_pos.get('base_price', entry)
        base_qty = open_pos.get('base_qty', qty)
        
        init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0

        open_pnl_usd = (curr - entry) * qty
        total_pos_profit = open_pnl_usd + realized_pnl
        hist_target_risk = float(open_pos.get("target_risk_usd") or 0)
        effective_target_risk = hist_target_risk if hist_target_risk > 0 else target_risk_usd
        if str(setup).upper() == "ALGO":
            total_campaign_r = total_pos_profit / effective_target_risk if effective_target_risk > 0 else 0
        else:
            total_campaign_r = total_pos_profit / original_campaign_risk if original_campaign_risk > 0 else 0
        
        engine_res = ec.evaluate_position_engine(
            symbol=symbol, entry_price=entry, entry_date_str=entry_date, current_stop=sl, 
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r, 
            target_risk_usd=effective_target_risk, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist,
            quantity=qty, initial_quantity=float(open_pos.get("initial_qty") or base_qty or qty)
        )
        if not engine_res["ok"]:
            state_line = ""
            decision_line = ""
            bot.edit_message_text(f"❌ שגיאת מנוע בחישוב {symbol}: {engine_res['error']}", chat_id, msg_id)
            return
        data = engine_res["data"]
        feats = data.get("features", {})
        state_block = format_position_state_block(data)
        decision_block = format_decision_card_block(data)
        
        sizing_str = f"ניהול: `{mgt_state}` | חשיפה: `{weight_pct:.1f}%`"
        if str(setup).upper() != "ALGO":
            if original_campaign_risk > 0 and data.get("sizing_status") != "✅ תקין":
                clean_sizing = data.get("sizing_status").replace('⚠️ ', '').replace('📉 ', '')
                sizing_str += f"\n⚖️ סטטוס סיכון: {clean_sizing}"
            elif original_campaign_risk == 0:
                sizing_str += f"\n⚠️ חסר סטופ התחלתי לחישוב בקרת סיכון."
            
        rep = f"{RTL}🔬 *דו\"ח מודיעין עומק (Drill-down) - {symbol}*\n\n"
        rep += f"*{symbol}* | 🏷️ {setup} | סטטוס: {data['status']}\n{sizing_str}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
        if state_block:
            rep += state_block + "\n"
        if decision_block:
            rep += decision_block + "\n"
        rep += f"{RTL}📊 *פרופיל טכני:*\n"
        if feats.get('dist_12d') is not None: rep += f"• ימי פיזור (12 ימים): `{feats['dist_12d']}`\n"
        if feats.get('accum_10d') is not None: rep += f"• ימי איסוף (10 ימים): `{feats['accum_10d']}`\n"
        if feats.get('good_closes_10') is not None: rep += f"• סגירות חזקות מול חלשות: `{feats['good_closes_10']}` מול `{feats['bad_closes_10']}`\n"
        rep += f"\n{RTL}📈 *מטריצת כוח יחסי (Relative Strength):*\n"
        if feats.get('rs20_market') is not None:
            val = feats['rs20_market'] * 100
            rep += f"• מול השוק (SPY): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"
        sec_bundle = ec.get_sector_bundle(symbol)
        sec_etf = sec_bundle.get('sector_etf')
        if feats.get('rs20_stock_sector') is not None and sec_etf:
            val = feats['rs20_stock_sector'] * 100
            rep += f"• מול הסקטור ({sec_etf}): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"
        rep += f"\n{RTL}🌪️ *משטר תנודתיות (Volatility Regime):*\n"
        if feats.get('atr_regime') is not None:
            reg_val = feats['atr_regime']
            reg_text = "מתרחבת 📈" if reg_val > 1.2 else "מתכווצת 📉" if reg_val < 0.85 else "נורמלית ➖"
            rep += f"• יחס תנודתיות: `{reg_val:.2f}x` ({reg_text})\n"
        if feats.get('stretch_ma20_atr') is not None: rep += f"• מתיחות (ממרחק MA20): `{feats['stretch_ma20_atr']:.1f}` יחידות ATR\n"
        if data['issues']: rep += f"\n{RTL}⚠️ *אזהרות:* {', '.join(data['issues'])}\n"
        bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")
    except Exception as e: bot.edit_message_text(f"❌ שגיאה בשליפת נתוני עומק: {e}", chat_id, msg_id)


def append_alert_task_to_trade(task, action_label, user_note=None):
    try:
        trade_id = task.get("trade_id")
        if not trade_id:
            return
        alert_type = str(task.get("alert_type", "")).replace("_", " ")
        symbol = task.get("symbol", "")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        line = f"[{stamp}] Alert Task {alert_type} {symbol}: {action_label}"
        if user_note:
            line += f" | Note: {user_note}"

        res = supabase.table("trades").select("notes").eq("trade_id", trade_id).limit(1).execute()
        old = ""
        if res.data:
            old = res.data[0].get("notes") or ""
        new_notes = (old + " | " if old else "") + line
        supabase.table("trades").update({"notes": new_notes}).eq("trade_id", trade_id).execute()
    except Exception as e:
        print(f"append_alert_task_to_trade failed: {e}")

def build_alert_reply_markup(task_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(text="✅ בוצע", callback_data=f"at_done|{task_id}"),
        types.InlineKeyboardButton(text="📝 לא בוצע", callback_data=f"at_no|{task_id}")
    )
    return keyboard



def _aq_rank(row):
    status = str(row.get("status") or "")
    state = str(row.get("position_state") or "")
    state_he = str(row.get("state_he") or "")
    bias = str(row.get("decision_bias") or "")
    violations = int(row.get("violation_count") or 0)

    if "קריטי" in status or state == "Broken" or "נכשל" in state_he:
        return 100
    if "מכירה לחולשה" in bias:
        return 90
    if violations >= 3:
        return 85
    if "מכירה לחוזק" in bias:
        return 75
    if "הגנת רווח" in state_he or state == "Profit Protect":
        return 70
    if "הגנת איזון" in state_he or state == "Breakeven Protect":
        return 60
    if violations > 0:
        return 50
    return 20

def _aq_priority_label(rank):
    if rank >= 95:
        return "קריטי"
    if rank >= 80:
        return "גבוה"
    if rank >= 60:
        return "בינוני"
    return "נמוך"

def _aq_short_money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return "$0"

def _aq_short_r(v):
    try:
        return f"{float(v):.1f}R"
    except Exception:
        return "N/A"


def log_action_queue_decision(task, action_status, note=None):
    try:
        campaign_id = task.get("campaign_id")
        symbol = task.get("symbol")
        dedupe = "{}|{}|{}|{}".format(campaign_id, symbol, action_status, datetime.now().strftime("%Y%m%d%H%M"))

        payload = {
            "dedupe_key": dedupe,
            "campaign_id": campaign_id,
            "trade_id": task.get("trade_id"),
            "symbol": symbol,
            "status": task.get("status"),
            "position_state": task.get("position_state"),
            "decision_bias": task.get("decision_bias"),
            "primary_action": "{}{}".format(action_status, (" | " + note) if note else ""),
            "urgency": task.get("priority"),
            "violation_count": int(task.get("violation_count") or 0),
            "reasons": task.get("reasons") or [],
            "decision_card": {
                "source": "action_queue",
                "action_status": action_status,
                "note": note,
                "suggested_action": task.get("suggested_action"),
                "decision_bias": task.get("decision_bias"),
            },
        }
        supabase.table("decision_journal").upsert(payload, on_conflict="dedupe_key").execute()
    except Exception as e:
        print(f"Action Queue journal write failed: {e}")

def load_latest_action_queue_item(campaign_id):
    try:
        res = (
            supabase.table("position_snapshots")
            .select("*")
            .eq("campaign_id", campaign_id)
            .order("snapshot_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"load_latest_action_queue_item failed: {e}")
    return None


def handle_action_queue(chat_id):
    try:
        res = (
            supabase.table("position_snapshots")
            .select("*")
            .order("snapshot_at", desc=True)
            .limit(100)
            .execute()
        )
        rows = res.data or []

        latest = {}
        for row in rows:
            cid = row.get("campaign_id") or row.get("symbol")
            if cid and cid not in latest:
                latest[cid] = row

        items = list(latest.values())
        if not items:
            bot.send_message(
                chat_id,
                f"{RTL}🎯 *תור פעולות*\n━━━━━━━━━━━━\nאין עדיין נתוני Journal. הרץ Risk Monitor או המתן למחזור הבא.",
                reply_markup=get_main_menu(),
                parse_mode="Markdown",
            )
            return

        ranked = []
        for row in items:
            rank = _aq_rank(row)
            row["_rank"] = rank
            ranked.append(row)

        ranked.sort(key=lambda r: r.get("_rank", 0), reverse=True)

        msg = f"{RTL}🎯 *תור פעולות - Sentinel*\n{RTL}━━━━━━━━━━━━\n"
        msg += f"{RTL}מסודר לפי דחיפות. מציג רק החלטה מעשית, לא כל הדאטה.\n\n"

        actionable = 0
        for row in ranked[:10]:
            rank = row.get("_rank", 0)
            if rank < 50:
                continue
            if aqs.is_hidden(row):
                continue

            actionable += 1
            sym = row.get("symbol") or "?"
            setup = row.get("setup_type") or ""
            status = row.get("status") or ""
            state_he = row.get("state_he") or row.get("position_state") or ""
            bias = row.get("decision_bias") or "מעקב"
            action = row.get("suggested_action") or ""
            violations = int(row.get("violation_count") or 0)
            open_r = _aq_short_r(row.get("open_r"))
            total_r = _aq_short_r(row.get("total_r"))
            locked = _aq_short_money(row.get("locked_profit"))
            giveback = _aq_short_money(row.get("giveback_risk"))
            priority = _aq_priority_label(rank)

            msg += f"{RTL}*{actionable}. {sym}*  `{setup}`\n"
            msg += f"{RTL}━━━━━━━━━━━━\n"
            msg += f"{RTL}• עדיפות: *{priority}* | מצב: {status}\n"
            msg += f"{RTL}• מצב ניהולי: {state_he} | הפרות: `{violations}`\n"
            msg += f"{RTL}• החלטה: *{bias}*\n"
            if action:
                msg += f"{RTL}• פעולה: {action}\n"
            msg += f"{RTL}• R: פתוח `{open_r}` | כולל `{total_r}`\n"
            msg += f"{RTL}• רווח מוגן: `{locked}` | ויתור: `{giveback}`\n\n"

        if actionable == 0:
            msg += f"{RTL}אין פעולות דחופות כרגע. הפוזיציות במעקב רגיל.\n"

        msg += f"{RTL}פעולות שסומנו כבוצעו מוסתרות עד שינוי מהותי במצב."
        keyboard = None
        if actionable > 0:
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            added_symbols = set()
            for row in ranked[:10]:
                if row.get("_rank", 0) < 50:
                    continue
                sym_btn = row.get("symbol")
                if not sym_btn or sym_btn in added_symbols:
                    continue
                added_symbols.add(sym_btn)
                cid_btn = row.get("campaign_id") or sym_btn
                keyboard.add(types.InlineKeyboardButton(text=f"⚙️ ניהול {sym_btn}", callback_data=f"aq_menu|{cid_btn}"))
            keyboard.add(types.InlineKeyboardButton(text="🔄 רענון תור פעולות", callback_data="aq_refresh"))

        send_long_message(chat_id, msg, reply_markup=keyboard if keyboard else get_main_menu())

    except Exception as e:
        bot.send_message(chat_id, f"{RTL}❌ תקלה בבניית תור הפעולות: `{e}`", reply_markup=get_main_menu(), parse_mode="Markdown")




def _perf_lrm(s):
    return LRM + str(s) + LRM

def _perf_fmt_r(v):
    try:
        x = float(v)
        sign = "+" if x > 0 else ""
        return _perf_lrm(f"{sign}{x:.2f}R")
    except Exception:
        return _perf_lrm("0.00R")

def _perf_fmt_pct(v):
    try:
        return _perf_lrm(f"{float(v):.0f}%")
    except Exception:
        return _perf_lrm("0%")

def _perf_fmt_num(v, digits=2):
    try:
        return _perf_lrm(f"{float(v):.{digits}f}")
    except Exception:
        return _perf_lrm("0")

def _perf_quality_label(m):
    exp = float(m.get("expectancy", 0) or 0)
    pf = float(m.get("profit_factor", 0) or 0)
    streak = int(m.get("current_loss_streak", m.get("loss_streak", 0)) or 0)
    dd = float(m.get("max_drawdown_r", m.get("max_dd", 0)) or 0)

    if exp > 0.5 and pf >= 1.5 and streak <= 1:
        return "חיובי, אבל תנודתי" if dd <= -6 else "בריא"
    if exp > 0 and pf >= 1.1:
        return "חיובי אך לא נקי"
    if exp < 0:
        return "שלילי"
    return "מעורב"

def _perf_window_line(label, m):
    return (
        f"{RTL}• {label}: "
        f"תוחלת {_perf_fmt_r(m.get('expectancy'))} | "
        f"הצלחה {_perf_fmt_pct(m.get('win_rate'))} | "
        f"DD {_perf_fmt_r(m.get('max_drawdown_r'))}"
    )

def handle_performance_lab(chat_id):
    try:
        res = supabase.table("trades").select("*").execute()
        df = pd.DataFrame(res.data or [])

        account_settings = get_account_settings()
        ibkr_nav = get_ibkr_nav()
        acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
        risk_pct = float(account_settings.get("risk_pct_input", 0.5))
        fallback_risk = acc_size * (risk_pct / 100) if acc_size > 0 else 37.5

        summary = pl.summarize_performance(df, fallback_risk=fallback_risk)
        if not summary.get("ok"):
            bot.send_message(
                chat_id,
                f"{RTL}📈 *מעבדת ביצועים*\n{RTL}━━━━━━━━━━━━\n{RTL}אין עדיין מספיק קמפיינים סגורים לחישוב.",
                reply_markup=get_main_menu(),
                parse_mode="Markdown",
            )
            return

        w10 = summary["windows"]["10"]
        w20 = summary["windows"]["20"]
        w50 = summary["windows"]["50"]
        allm = summary["all"]
        quality = _perf_quality_label(w20)

        win20 = int(w20.get("win_count", 0) or 0)
        loss20 = int(w20.get("loss_count", 0) or 0)
        current_streak = int(w20.get("current_loss_streak", w20.get("loss_streak", 0)) or 0)

        lines = [
            f"{RTL}📈 *מעבדת ביצועים - Sentinel*",
            f"{RTL}━━━━━━━━━━━━",
            f"{RTL}מדידה לפי קמפיינים סגורים בלבד. R ראשי = סיכון בפועל; באלגו = Target R.",
            "",
            f"{RTL}*שורה תחתונה*",
            f"{RTL}• מצב 20 אחרונים: *{quality}*",
            f"{RTL}• קמפיינים סגורים: {_perf_lrm(allm.get('count', 0))}",
            f"{RTL}• תוחלת 20: {_perf_fmt_r(w20.get('expectancy'))}",
            f"{RTL}• הצלחה 20: {_perf_fmt_pct(w20.get('win_rate'))} ({_perf_lrm(win20)} מנצחות / {_perf_lrm(loss20)} מפסידות)",
            f"{RTL}• רצף הפסדים נוכחי: {_perf_lrm(current_streak)}",
            f"{RTL}• MaxDD ב־20: {_perf_fmt_r(w20.get('max_drawdown_r'))}",
            "",
            f"{RTL}*איכות רווח/הפסד*",
            f"{RTL}• רווח ממוצע: {_perf_fmt_r(w20.get('avg_win_r'))}",
            f"{RTL}• הפסד ממוצע: {_perf_fmt_r(w20.get('avg_loss_r'))}",
            f"{RTL}• יחס רווח/הפסד: {_perf_fmt_num(w20.get('payoff'))}",
            f"{RTL}• פקטור רווח: {_perf_fmt_num(w20.get('profit_factor'))}",
            "",
            f"{RTL}*חלונות ביצוע*",
            _perf_window_line("10 אחרונים", w10),
            _perf_window_line("20 אחרונים", w20),
            _perf_window_line("50 אחרונים", w50),
            "",
            f"{RTL}*לפי אסטרטגיה*",
        ]

        for row in summary.get("setup_stats", [])[:6]:
            lines.append(
                f"{RTL}• {md_plain(row.get('setup_type'))}: "
                f"{_perf_lrm(row.get('count', 0))} | "
                f"תוחלת {_perf_fmt_r(row.get('expectancy'))} | "
                f"הצלחה {_perf_fmt_pct(row.get('win_rate'))} | "
                f"PF {_perf_fmt_num(row.get('profit_factor'))}"
            )

        lines += ["", f"{RTL}*קמפיינים אחרונים*"]
        for r in summary.get("recent", [])[:6]:
            rv = float(r.get("r", 0) or 0)
            icon = "🟢" if rv > 0 else "🔴" if rv < 0 else "⚪"
            pnl = float(r.get("pnl_usd", r.get("pnl", 0)) or 0)
            target_r = r.get("target_r")
            target_txt = ""
            if target_r is not None and abs(float(target_r) - rv) > 0.05:
                target_txt = f" | Target {_perf_fmt_r(target_r)}"
            lines.append(
                f"{RTL}• {icon} {md_plain(r.get('symbol'))} {md_plain(r.get('setup_type'))} | "
                f"R {_perf_fmt_r(rv)}{target_txt} | "
                f"{_perf_lrm('$' + format(pnl, '.0f'))}"
            )

        lines.append("")
        if float(w20.get("expectancy", 0) or 0) > 0 and float(w20.get("max_drawdown_r", 0) or 0) <= -6:
            lines.append(f"{RTL}🧭 *פירוש:* התוחלת חיובית, אבל היה Drawdown עמוק בתוך 20 האחרונות. לא מגדילים סיכון אוטומטית; נותנים ל־Risk Governor להחליט.")
        elif float(w20.get("expectancy", 0) or 0) > 0 and current_streak <= 1:
            lines.append(f"{RTL}🧭 *פירוש:* התוחלת חיובית ואין רצף הפסדים נוכחי חריג.")
        elif float(w20.get("expectancy", 0) or 0) < 0:
            lines.append(f"{RTL}🧭 *פירוש:* התוחלת שלילית. לא מעלים סיכון עד שיפור מוכח.")
        else:
            lines.append(f"{RTL}🧭 *פירוש:* התמונה מעורבת. שומרים על סיכון שמרני.")

        send_long_message(chat_id, chr(10).join(lines), reply_markup=get_main_menu())

    except Exception as e:
        bot.send_message(chat_id, f"{RTL}❌ תקלה במעבדת הביצועים: `{md_plain(e)}`", reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_queries(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("at_done|"):
        task_id = data.split("|", 1)[1]
        task = at.close_task(task_id, "done")
        if task:
            append_alert_task_to_trade(task, "בוצע")
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "תועד כבוצע")
        bot.send_message(chat_id, f"{RTL}✅ הפעולה סומנה כבוצעה ותועדה ביומן.", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if data.startswith("at_no|"):
        task_id = data.split("|", 1)[1]
        task = at.get_task(task_id)
        if not task:
            bot.answer_callback_query(call.id, "המשימה לא נמצאה")
            return
        user_state[chat_id] = {"action": "alert_not_done_note", "task_id": task_id}
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"{RTL}📝 רשום בקצרה למה הפעולה לא בוצעה. ההערה תישמר ביומן.", parse_mode="Markdown")
        return

    if data == "aq_refresh":
        bot.answer_callback_query(call.id)
        return handle_action_queue(chat_id)

    if data.startswith("aq_menu|"):
        campaign_id = data.split("|", 1)[1]
        task = load_latest_action_queue_item(campaign_id)
        if not task:
            bot.answer_callback_query(call.id, "לא נמצאה פעולה")
            return

        sym = task.get("symbol") or "?"
        bias = task.get("decision_bias") or "מעקב"
        action = task.get("suggested_action") or "אין פעולה מוגדרת"
        priority = _aq_priority_label(_aq_rank(task))

        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(types.InlineKeyboardButton(text=f"🔬 Drill-down {sym}", callback_data=f"drill|{sym}"))
        keyboard.add(types.InlineKeyboardButton(text="✅ בוצע / השתק עד שינוי", callback_data=f"aq_done|{campaign_id}"))
        keyboard.add(types.InlineKeyboardButton(text="📝 לא בוצע - הוסף הערה", callback_data=f"aq_no|{campaign_id}"))

        txt = (
            f"{RTL}⚙️ *ניהול פעולה - {sym}*\n"
            f"{RTL}━━━━━━━━━━━━\n"
            f"{RTL}• עדיפות: *{priority}*\n"
            f"{RTL}• החלטה: *{bias}*\n"
            f"{RTL}• פעולה: {action}\n\n"
            f"{RTL}סימון `בוצע` יסתיר את אותה החלטה עד שהמצב ישתנה."
        )
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, txt, reply_markup=keyboard, parse_mode="Markdown")
        return

    if data.startswith("aq_done|"):
        campaign_id = data.split("|", 1)[1]
        task = load_latest_action_queue_item(campaign_id)
        if not task:
            bot.answer_callback_query(call.id, "לא נמצאה פעולה")
            return
        log_action_queue_decision(task, "בוצע")
        aqs.mark(task, "done")
        bot.answer_callback_query(call.id, "תועד כבוצע")
        bot.send_message(chat_id, f"{RTL}✅ הפעולה סומנה כבוצעה ונשמרה ביומן.", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if data.startswith("aq_no|"):
        campaign_id = data.split("|", 1)[1]
        task = load_latest_action_queue_item(campaign_id)
        if not task:
            bot.answer_callback_query(call.id, "לא נמצאה פעולה")
            return
        user_state[chat_id] = {
            "action": "action_queue_not_done_note",
            "campaign_id": campaign_id,
            "task": task,
        }
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"{RTL}📝 למה הפעולה לא בוצעה? כתוב הערה קצרה והיא תישמר ביומן.", parse_mode="Markdown")
        return

    if data.startswith("drill|"):
        symbol = data.split("|")[1]
        bot.answer_callback_query(call.id)
        handle_drilldown(chat_id, symbol)
        return
    if data == "start_trail_flow":
        if chat_id in user_state and 'temp_positions' in user_state[chat_id]:
            count = len(user_state[chat_id]['temp_positions'])
            bot.send_message(chat_id, f"🎯 *קידום סטופ:*\nהקלד את מספר הטרייד מהרשימה (1-{count}):\n(או שלח 'ביטול')", parse_mode="Markdown")
            user_state[chat_id]['action'] = 'select_trade_index'
        else: bot.send_message(chat_id, "⚠️ המידע פג תוקף. לחץ שוב על 'חדר מצב'.")
        bot.answer_callback_query(call.id)
    elif data == "cancel_action":
        bot.send_message(chat_id, "❌ הפעולה בוטלה.", reply_markup=get_main_menu())
        if chat_id in user_state: del user_state[chat_id]
        bot.answer_callback_query(call.id)
    elif data.startswith("v|"):
        bot.answer_callback_query(call.id)
        parts = data.split('|')
        try:
            t_id, field, val = parts[1], parts[2], parts[3]
            if field in ['quality', 'score']:
                supabase.table("trades").update({field: int(val)}).eq("trade_id", t_id).execute()
            elif field == 'initial_stop':
                supabase.table("trades").update({"initial_stop": float(val), "stop_loss": float(val)}).eq("trade_id", t_id).execute()
            elif field == 'stop_loss':
                supabase.table("trades").update({field: float(val)}).eq("trade_id", t_id).execute()
            else:
                save_val = "Skipped" if val == 'Skipped' else val
                supabase.table("trades").update({field: save_val}).eq("trade_id", t_id).execute()
            
            bot.delete_message(chat_id, call.message.message_id)
            get_next_missing(chat_id)
        except Exception as e: bot.send_message(chat_id, f"❌ *תקלה בעדכון:* {str(e)}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text', 'photo'])
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text if message.text else ""

    if text in ["ביטול", "cancel", "/cancel", "❌ ביטול"]:
        if chat_id in user_state: del user_state[chat_id]
        bot.send_message(chat_id, "❌ הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=get_main_menu())
        return

    if text in ["📈 מעבדת ביצועים", "/performance", "/perf"]:
        return handle_performance_lab(chat_id)

    if text in ["🎯 תור פעולות", "/actions", "Action Queue", "action queue"]:
        return handle_action_queue(chat_id)

    if chat_id in user_state and user_state[chat_id].get("action") == "action_queue_not_done_note":
        note = text.strip()
        task = user_state[chat_id].get("task") or {}
        log_action_queue_decision(task, "לא בוצע", note=note)
        aqs.mark(task, "not_done", note=note, snooze_hours=6)
        del user_state[chat_id]
        bot.send_message(chat_id, f"{RTL}✅ ההערה נשמרה ביומן ההחלטות.", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if text.startswith("/analyze "):
        symbol = text.split(" ")[1].upper()
        bot.send_message(chat_id, f"⏳ מושך מודיעין מניה עבור {symbol}...", parse_mode="Markdown")
        report_res = ec.get_minervini_analysis(symbol)
        report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
        bot.send_message(chat_id, report, parse_mode="Markdown")
        return

    if text == "🔬 סקירת מניה":
        bot.send_message(chat_id, "🔬 *מודיעין מניה:*\nאנא הקלד את סימול המניה לסריקה (לדוגמה: AAPL):", parse_mode="Markdown")
        user_state[chat_id] = {'action': 'analyze_symbol'}
        return

    if text in ["🔍 סריקת יומן (Backlog)", "/next", "📚 ניהול יומן (Backlog)"]: return get_next_missing(chat_id)

    if text in ["🧹 ארכיון עסקאות (Legacy)", "/clean"]:
        bot.send_message(chat_id, "🧹 *מבצע ניקוי היסטוריה (עסקאות מעל 30 יום בלבד)...*", parse_mode="Markdown")
        try:
            thirty_days_ago = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
            res = supabase.table("trades").select("*").lt("trade_date", thirty_days_ago).execute()
            count = 0
            for t in res.data:
                needs_update = False
                upd = {}
                if t.get('setup_type') is None: upd['setup_type'] = "Legacy"; needs_update = True
                if t.get('quality') is None: upd['quality'] = -1; needs_update = True
                if t.get('side', '').upper() == 'BUY':
                    if t.get('initial_stop') in [None, 0]: upd['initial_stop'] = -1; upd['stop_loss'] = -1; needs_update = True
                if t.get('side', '').upper() == 'SELL':
                    if t.get('score') is None: upd['score'] = -1; needs_update = True
                    if t.get('image_url') is None: upd['image_url'] = "Skipped"; needs_update = True
                    if t.get('management_notes') is None: upd['management_notes'] = "Skipped"; needs_update = True
                if needs_update:
                    supabase.table("trades").update(upd).eq("trade_id", t['trade_id']).execute()
                    count += 1
            bot.send_message(chat_id, f"✅ ארכיון נקי! {count} עסקאות ישנות טופלו בהצלחה.", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה בניקוי הארכיון: {e}")
        return get_next_missing(chat_id)

    if text in ["❓ פקודות מערכת", "/help"]:
        help_text = (
            f"{RTL}🛡️ *מערכת הפיקוד (Sentinel Command)*\n"
            "━━━━━━━━━━━━\n\n"
            "/actions - תור פעולות\n/intake - תוכניות ניהול לאחר כניסה\n"
            "/portfolio - חדר מצב\n"
            "/risk - משטר שוק וסיכונים\n"
            "/trade SYMBOL - צלילת עומק לפוזיציה\n"
            "/next - סריקת יומן\n"
            "/clean - ארכיון עסקאות ישנות"
        )
        return bot.send_message(chat_id, help_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    if text in ["🌡️ משטר שוק וסיכונים", "/risk", "/market"]:
        msg_id = bot.send_message(chat_id, "{}⏳ בודק משטר שוק וסיכון...".format(RTL), parse_mode="Markdown").message_id
        try:
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")
            qqq_hist = ec.get_cached_history("QQQ", "1y", "1d")
            regime = ec.compute_market_regime(spy_hist, qqq_hist)

            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            perf_summary = pl.summarize_performance(df, fallback_risk=target_risk_usd if 'target_risk_usd' in locals() else 37.5)

            pos_res = ec.get_open_positions_campaign(df)
            open_pos = pos_res["data"] if pos_res["ok"] else pd.DataFrame()

            account_settings = get_account_settings()
            ibkr_nav = get_ibkr_nav()
            acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
            target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))

            perf_fallback_risk = acc_size * (target_risk_pct / 100) if acc_size > 0 else 37.5
            perf_summary_risk = pl.summarize_performance(df, fallback_risk=perf_fallback_risk)
            gov_res = ec.compute_risk_governor(df, regime, acc_size, target_risk_pct)
            gov_res = ec.enrich_risk_governor_with_performance(gov_res, perf_summary_risk)
            exp_gov_res = ec.compute_exposure_governor(df, regime, gov_res, acc_size)

            exp = {"ALGO": 0.0, "VCP": 0.0, "EP": 0.0, "OTHER": 0.0}
            if not open_pos.empty:
                for _, row in open_pos.iterrows():
                    sym = row["symbol"]
                    setup = str(row["setup_type"]).upper()
                    curr = ec.get_live_price(sym) or float(row["price"])
                    val = curr * float(row["quantity"])
                    if setup in exp:
                        exp[setup] += val
                    else:
                        exp["OTHER"] += val

            total_exp = sum(exp.values())
            total_pct = (total_exp / acc_size) * 100 if acc_size > 0 else 0

            rep = "{}🌡️ *משטר שוק וסיכונים*\n{}{}\n".format(RTL, RTL, SEP)

            rep += report_section("שוק")
            if regime["ok"]:
                rd = regime["data"]
                rep += report_line("מצב", "{} {}".format(rd["color"], tv(rd["status"])))
                rep += report_line("הנחיה", md_plain(rd["text"]))
                basis_lines = rd.get("basis", [])[:4]
                if basis_lines:
                    rep += report_line("בדיקה", "")
                    for b in basis_lines:
                        rep += "{}  - {}\n".format(RTL, md_plain(b))
            else:
                rep += report_line("מצב", "⚪ {}".format(tv("לא ידוע")))
                rep += report_line("שגיאה", tv(regime.get("error")))

            rep += report_section("בקרת סיכון")
            if gov_res["ok"]:
                gd = gov_res["data"]
                rep += report_line("מצב עבודה", tv(gov_mode_he(gd["trade_mode"])))
                rep += report_line("סיכון מותר לעסקה", fmt_pct(gd["allowed_risk_pct"], 2))
                rep += report_line("חשיפה מותרת", fmt_pct(gd["allowed_exposure_pct"], 0))
                rep += report_line("תוחלת 20 עסקאות", fmt_r(gd["rolling_expectancy_20"], 2))
                rep += report_line("רצף הפסדים", tv(gd["loss_streak"]))
                rep += report_line("DD נוכחי / מקסימום 20", "{} / {}".format(fmt_r(gd["personal_drawdown_r"], 1), fmt_r(gd.get("recent_max_drawdown_r", 0), 1)))
                rep += report_line("פתוחות משוקללות", "{} מתוך {}".format(fmt_r(gd.get("open_portfolio_r_weighted", 0), 1), fmt_r(gd.get("open_portfolio_r", 0), 1)))
                rep += report_line("החלטה", report_note(gd["reason"]).strip())
            else:
                rep += report_line("מצב", "לא זמין")
                rep += report_line("שגיאה", tv(gov_res.get("error")))

            try:
                pb = gd.get("performance_bridge") if "gd" in locals() else {}
                if pb:
                    rep += report_section("מדדי ביצוע שהשפיעו")
                    for line in pb.get("lines", [])[:4]:
                        rep += report_line("בדיקה", md_plain(line))
                    rep += report_line("דירוג ביצוע", tv(pb.get("grade")))
                    rep += report_line("מגמה", tv(pb.get("trend")))
            except Exception:
                pass

            rep += report_section("בקרת חשיפה")
            if exp_gov_res["ok"]:
                ed = exp_gov_res["data"]
                rep += report_line("מצב חשיפה", tv(exposure_status_he(ed["status"])))
                rep += report_line("חשיפה בפועל / מותרת", "{} / {}".format(fmt_pct(ed["total_exposure_pct"], 1), fmt_pct(ed["allowed_exposure_pct"], 0)))
                rep += report_line("ניצול חשיפה", fmt_pct(ed["utilization_pct"], 0))
                rep += report_line("מזומן", fmt_pct(ed["cash_pct"], 1))
                rep += report_line("חשיפת ALGO", fmt_pct(ed["algo_exposure_pct"], 1))
                if ed.get("issues"):
                    rep += report_line("אזהרות", md_plain(", ".join(ed["issues"])))
                rep += report_line("פעולה", report_note(ed["action"]).strip())
            else:
                rep += report_line("מצב", "לא זמין")
                rep += report_line("שגיאה", tv(exp_gov_res.get("error")))

            rep += report_section("חשיפה לפי אסטרטגיה")
            rep += report_line("סה״כ תיק", fmt_pct(total_pct, 1))
            if acc_size > 0:
                rep += report_line("ALGO", fmt_pct((exp["ALGO"] / acc_size) * 100, 1))
                rep += report_line("VCP", fmt_pct((exp["VCP"] / acc_size) * 100, 1))
                rep += report_line("EP", fmt_pct((exp["EP"] / acc_size) * 100, 1))
                if exp["OTHER"] > 0:
                    rep += report_line("אחר", fmt_pct((exp["OTHER"] / acc_size) * 100, 1))

            bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")
        except Exception as e:
            bot.edit_message_text("{}❌ תקלה בחישוב משטר שוק: {}".format(RTL, md_plain(e)), chat_id, msg_id)
        return
    if text in ["📊 חדר מצב (פוזיציות)", "/portfolio"]:
        loading_msg = bot.send_message(chat_id, "{}⏳ מרכיב חדר מצב...".format(RTL), parse_mode="Markdown")
        try:
            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            pos_res = ec.get_open_positions_campaign(df)

            if not pos_res["ok"]:
                try:
                    bot.delete_message(chat_id, loading_msg.message_id)
                except:
                    pass
                return bot.send_message(chat_id, "{}❌ שגיאה במשיכת פוזיציות: {}".format(RTL, tv(pos_res["error"])), parse_mode="Markdown")

            open_pos = pos_res["data"]
            if open_pos.empty:
                try:
                    bot.delete_message(chat_id, loading_msg.message_id)
                except:
                    pass
                return bot.send_message(chat_id, "{}✅ אין פוזיציות פתוחות במערכת.".format(RTL), reply_markup=get_main_menu(), parse_mode="Markdown")

            account_settings = get_account_settings()
            ibkr_nav = get_ibkr_nav()
            acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
            target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
            target_risk_usd = acc_size * (target_risk_pct / 100)
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")

            user_state[chat_id] = {"temp_positions": open_pos.to_dict("records")}

            total_open_pnl = 0.0
            total_disc_pnl = 0.0
            total_realized_camp = 0.0
            total_exposure = 0.0
            total_risk = 0.0
            total_locked_profit = 0.0
            total_giveback_risk = 0.0
            total_algo_exposure = 0.0
            active_symbols = []

            msg = "{}🔭 *חדר מצב - פוזיציות פתוחות*\n{}{}\n".format(RTL, RTL, SEP)

            for i, row in enumerate(user_state[chat_id]["temp_positions"], 1):
                sym = row["symbol"]
                active_symbols.append(sym)

                entry = float(row.get("price") or 0)
                qty = float(row.get("quantity") or 0)
                sl = float(row.get("stop_loss") or 0)
                init_sl = float(row.get("initial_stop") or 0)
                setup = str(row.get("setup_type") or "Unknown").upper()
                realized_pnl = float(row.get("realized_pnl") or 0)
                entry_date = row.get("entry_date")
                mgt_state = row.get("management_state", "full_position")
                base_price = float(row.get("base_price") or entry)
                base_qty = float(row.get("base_qty") or qty)
                add_on_count = int(row.get("add_on_count") or 0)

                curr = ec.get_live_price(sym)
                if curr is None:
                    curr = entry

                open_pnl_usd = (curr - entry) * qty
                total_pos_profit = open_pnl_usd + realized_pnl
                pos_value = curr * qty
                weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0

                init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
                original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0

                if sl > base_price:
                    current_open_loss_risk = 0.0
                    locked_profit_usd = (sl - base_price) * qty
                    giveback_risk_usd = (curr - sl) * qty if curr > sl else 0.0
                else:
                    current_open_loss_risk = (base_price - sl) * qty if sl > 0 else 0.0
                    locked_profit_usd = 0.0
                    giveback_risk_usd = 0.0

                hist_target_risk = float(row.get("target_risk_usd") or 0)
                effective_target_risk = hist_target_risk if hist_target_risk > 0 else target_risk_usd

                if setup == "ALGO":
                    total_campaign_r = total_pos_profit / effective_target_risk if effective_target_risk > 0 else 0
                    open_r_val = open_pnl_usd / effective_target_risk if effective_target_risk > 0 else 0
                else:
                    total_campaign_r = total_pos_profit / original_campaign_risk if original_campaign_risk > 0 else 0
                    open_r_val = open_pnl_usd / original_campaign_risk if original_campaign_risk > 0 else 0

                engine_res = ec.evaluate_position_engine(
                    symbol=sym,
                    entry_price=entry,
                    entry_date_str=entry_date,
                    current_stop=sl,
                    setup_type=setup,
                    mgt_state=mgt_state,
                    weight_pct=weight_pct,
                    total_r=total_campaign_r,
                    target_risk_usd=effective_target_risk,
                    actual_risk_usd=original_campaign_risk,
                    spy_hist=spy_hist,
                    quantity=qty,
                    initial_quantity=float(row.get("initial_qty") or base_qty or qty)
                )

                if engine_res["ok"]:
                    e_data = engine_res["data"]
                    status = e_data.get("status", "לא ידוע")
                    action_short = e_data.get("action", "מעקב")
                    trigger = e_data.get("trigger", "")
                    issues = e_data.get("issues", [])
                    score = e_data.get("score")
                    stage = e_data.get("stage", "")
                    feats = e_data.get("features", {})
                    sizing_str = e_data.get("sizing_status", "✅ תקין")
                else:
                    status = "❌ שגיאה"
                    action_short = "בדיקה ידנית"
                    trigger = engine_res.get("error", "")
                    issues = []
                    score = None
                    stage = ""
                    feats = {}
                    sizing_str = "לא ידוע"

                total_open_pnl += open_pnl_usd
                total_realized_camp += realized_pnl
                total_exposure += pos_value
                total_locked_profit += locked_profit_usd
                total_giveback_risk += giveback_risk_usd

                if setup == "ALGO":
                    total_algo_exposure += pos_value
                else:
                    total_disc_pnl += open_pnl_usd
                    total_risk += current_open_loss_risk

                try:
                    days_held = (datetime.now() - pd.to_datetime(entry_date)).days if entry_date else 0
                except:
                    days_held = 0

                pnl_icon = "🟢" if open_pnl_usd >= 0 else "🔴"
                score_text = ""
                if score is not None and not pd.isna(score):
                    score_text = " | ציון {}".format(tv(str(int(score)) + "/100"))
                issues_text = " | {}".format(md_plain(" | ".join(issues[:2]))) if issues else ""

                msg += "\n{}*{}. {}*  {}\n{}{}\n".format(RTL, i, md_plain(sym), tv(setup), RTL, SEP)
                msg += report_line("מצב", "{}{}{}".format(md_plain(status), score_text, issues_text))
                msg += report_line("פעולה", "*{}*".format(md_plain(action_short)))
                if trigger:
                    msg += report_line("טריגר", md_plain(trigger))

                qty_label = "{}".format(qty)
                if add_on_count > 0:
                    qty_label += " + חיזוק"

                msg += report_line("פוזיציה", "כמות {} | ותק {} | ניהול {}".format(tv(qty_label), tv(str(days_held) + " ימים"), tv(mgt_state)))
                msg += report_line("מחיר", "כניסה {} | נוכחי {}".format(fmt_usd(entry, 2), fmt_usd(curr, 2)))
                msg += report_line("רווח", "{} צף {} | כולל {} | {}".format(pnl_icon, fmt_usd(open_pnl_usd, 2), fmt_usd(total_pos_profit, 2), fmt_r(open_r_val, 1)))
                msg += report_line("חשיפה", fmt_pct(weight_pct, 1))

                if setup == "ALGO":
                    msg += report_line("סטופים", tv("אלגו"))
                else:
                    init_display = fmt_usd(init_sl_clean, 2) if init_sl_clean > 0 else tv("חסר")
                    msg += report_line("סטופים", "מקורי {} | נוכחי {}".format(init_display, fmt_usd(sl, 2)))
                    if sizing_str != "✅ תקין" and original_campaign_risk > 0:
                        msg += report_line("בקרת סיכון", md_plain(sizing_str))

                if current_open_loss_risk > 0:
                    msg += report_line("סיכון פתוח", fmt_usd(current_open_loss_risk, 0))
                else:
                    msg += report_line("הגנת רווח", "מובטח {} | ויתור {}".format(fmt_usd(locked_profit_usd, 0), fmt_usd(giveback_risk_usd, 0)))

                if feats and feats.get("rs20_market") is not None:
                    rs_m = feats["rs20_market"] * 100
                    rs_s = feats.get("rs20_stock_sector")
                    if rs_s is not None:
                        msg += report_line("כוח יחסי", "שוק {} | סקטור {}".format(fmt_pct(rs_m, 1), fmt_pct(rs_s * 100, 1)))
                    else:
                        msg += report_line("כוח יחסי", "שוק {}".format(fmt_pct(rs_m, 1)))

            total_weight = (total_exposure / acc_size) * 100 if acc_size > 0 else 0
            algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
            total_pnl_icon = "🟢" if total_open_pnl >= 0 else "🔴"
            total_secured = total_realized_camp + total_locked_profit

            msg += report_section("סיכום תיק")
            msg += report_line("רווח צף", "{} {}".format(total_pnl_icon, fmt_usd(total_open_pnl, 2)))
            msg += report_line("רווח שמומש בפתוחות", fmt_usd(total_realized_camp, 2))
            msg += report_line("רווח מוגן", fmt_usd(total_secured, 2))
            msg += report_line("סיכון ויתור", fmt_usd(total_giveback_risk, 2))
            msg += report_line("סיכון הפסד הון", fmt_usd(total_risk, 2))
            msg += report_line("חשיפה כללית", fmt_pct(total_weight, 1))
            msg += report_line("חשיפת ALGO", fmt_pct(algo_cluster_pct, 1))

            try:
                bot.delete_message(chat_id, loading_msg.message_id)
            except:
                pass

            markup = types.InlineKeyboardMarkup(row_width=3)
            drill_btns = [types.InlineKeyboardButton(text="🔍 {}".format(s), callback_data="drill|{}".format(s)) for s in active_symbols]
            if drill_btns:
                markup.add(*drill_btns)
            markup.add(types.InlineKeyboardButton("🎯 הזן קידום סטופ", callback_data="start_trail_flow"))

            send_long_message(chat_id, msg, reply_markup=markup)
            return

        except Exception as e:
            err_details = traceback.format_exc()
            try:
                bot.delete_message(chat_id, loading_msg.message_id)
            except:
                pass
            bot.send_message(chat_id, "{}❌ תקלת מערכת בחדר המצב:\n{}\n\n{}".format(RTL, tv(e), tv(err_details[-500:])), parse_mode="Markdown")
            return
    if chat_id in user_state:
        state = user_state[chat_id]
        action = state.get('action')

        if action == 'analyze_symbol':
            symbol = text.strip().upper()
            bot.send_message(chat_id, f"⏳ מושך נתונים טכניים ומנתח את {symbol}...", parse_mode="Markdown")
            report_res = ec.get_minervini_analysis(symbol)
            report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
            bot.send_message(chat_id, report, parse_mode="Markdown")
            del user_state[chat_id]
            return

        if action == 'select_trade_index':
            try:
                idx = int(text) - 1
                positions = state['temp_positions']
                if 0 <= idx < len(positions):
                    selected = positions[idx]
                    state['selected_trade'] = selected
                    state['action'] = 'input_new_sl'
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("❌ ביטול", callback_data="cancel_action"))
                    bot.send_message(chat_id, f"✅ בחרת ב-*{selected['symbol']}*.\nמחיר כניסה: `${selected['price']:.2f}`\nסטופ נוכחי: `${selected['stop_loss']:.2f}`\n\n*הקלד את מחיר הסטופ החדש:*", reply_markup=markup, parse_mode="Markdown")
                else: bot.send_message(chat_id, f"❌ מספר לא תקין. בחר בין 1 ל-{len(positions)}.")
            except: bot.send_message(chat_id, "❌ נא להזין מספר בלבד.")
            return

        elif action == 'initial_stop':
            try:
                new_sl = float(text)
                trade_id = state.get('t_id')
                if trade_id:
                    supabase.table("trades").update({"initial_stop": new_sl, "stop_loss": new_sl}).eq("trade_id", trade_id).execute()
                    bot.send_message(chat_id, f"🚀 *הסטופ ההתחלתי נשמר במערכת: ${new_sl:.2f}*", parse_mode="Markdown")
                del user_state[chat_id]
                get_next_missing(chat_id)
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר בלבד (למשל 150.50).")
            return

        elif action == 'input_new_sl':
            try:
                new_sl = float(text)
                trade = state['selected_trade']
                cid = trade.get('campaign_id')
                if cid:
                    supabase.table("trades").update({"stop_loss": new_sl}).eq("campaign_id", cid).eq("side", "BUY").execute()
                    bot.send_message(chat_id, f"🚀 *הסטופ עודכן בהצלחה!*\nנכס: `{trade['symbol']}`\nסטופ מעודכן ל: `${new_sl:.2f}`\nפקודות הקנייה בקמפיין עודכנו.", reply_markup=get_main_menu(), parse_mode="Markdown")
                else: bot.send_message(chat_id, "❌ תקלת מערכת: לא נמצא מזהה קמפיין לעסקה זו.")
                del user_state[chat_id]
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר.")
            return

        t_id = state.get('t_id')
        if action == 'image' and t_id:
            if message.content_type == 'photo':
                bot.send_message(chat_id, "🚨 *שגיאה:* יש לשלוח לינק מ-TradingView, לא העלאת תמונה.", parse_mode="Markdown")
                return
            supabase.table("trades").update({"image_url": text.strip()}).eq("trade_id", t_id).execute()
            bot.send_message(chat_id, "✅ תמונה נשמרה.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

        if action == 'management_notes' and t_id:
            if message.content_type != 'text':
                bot.send_message(chat_id, "🚨 שגיאה: יש לשלוח הערת טקסט בלבד.", parse_mode="Markdown")
                return
            supabase.table("trades").update({"management_notes": text.strip()}).eq("trade_id", t_id).execute()
            bot.send_message(chat_id, "✅ תובנות הניהול נשמרו ביומן המערכת.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

    bot.send_message(chat_id, "🎯 *Sentinel Standby*\nמערכת מוכנה לפעולה. בחר מהתפריט למטה:", reply_markup=get_main_menu(), parse_mode="Markdown")

if __name__ == "__main__":
    if ADMIN_ID:
        try: bot.send_message(ADMIN_ID, "🛡️ *Sentinel Monitoring: ONLINE*\nשדרוג נתוני כניסה (v3.6 - Master Final Polish).", reply_markup=get_main_menu(), parse_mode="Markdown")
        except: pass
    bot.infinity_polling()
