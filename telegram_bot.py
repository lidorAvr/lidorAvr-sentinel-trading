import os, telebot, json, traceback
import pandas as pd
from telebot import types
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime
import xml.etree.ElementTree as ET
import engine_core as ec
import telegram_formatters as tf
import adaptive_risk_engine as are

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
bot = telebot.TeleBot(TOKEN)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

user_state = {}
RTL = "\u200F"

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

def get_main_menu():
    """תפריט ראשי — 4 קטגוריות בלבד, ממנו צוללים לתפריטי תת."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("📊 מצב תיק"), types.KeyboardButton("🔬 ניתוח"))
    markup.add(types.KeyboardButton("📚 יומן"), types.KeyboardButton("❓ עזרה"))
    return markup

def get_portfolio_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("📊 חדר מצב (פוזיציות)"))
    markup.add(types.KeyboardButton("🌡️ משטר שוק וסיכונים"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_analysis_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🔬 סקירת מניה"))
    markup.add(types.KeyboardButton("🧠 ניתוח מינרביני מלא"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup

def get_journal_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🔍 סריקת יומן (Backlog)"))
    markup.add(types.KeyboardButton("🧹 ארכיון עסקאות (Legacy)"))
    markup.add(types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
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
        
        engine_res = ec.evaluate_position_engine(
            symbol=symbol, entry_price=entry, entry_date_str=entry_date, current_stop=sl, 
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=0, 
            target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist
        )
        if not engine_res["ok"]:
            bot.edit_message_text(f"❌ שגיאת מנוע בחישוב {symbol}: {engine_res['error']}", chat_id, msg_id)
            return
        data = engine_res["data"]
        feats = data.get("features", {})
        
        sizing_str = f"ניהול: `{mgt_state}` | חשיפה: `{weight_pct:.1f}%`"
        if str(setup).upper() != "ALGO":
            if original_campaign_risk > 0 and data.get("sizing_status") != "✅ תקין":
                clean_sizing = data.get("sizing_status").replace('⚠️ ', '').replace('📉 ', '')
                sizing_str += f"\n⚖️ סטטוס סיכון: {clean_sizing}"
            elif original_campaign_risk == 0:
                sizing_str += f"\n⚠️ חסר סטופ התחלתי לחישוב בקרת סיכון."
            
        rep = f"{RTL}🔬 *דו\"ח מודיעין עומק (Drill-down) - {symbol}*\n\n"
        rep += f"*{symbol}* | 🏷️ {setup} | סטטוס: {data['status']}\n{sizing_str}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
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

@bot.callback_query_handler(func=lambda call: True)
def handle_queries(call):
    chat_id = call.message.chat.id
    data = call.data
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
    elif data.startswith("risk_confirm|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        action = parts[1]
        rec_pct = float(parts[2])
        curr_pct = float(parts[3])
        account_settings = get_account_settings()
        nav = float(account_settings.get("nav", account_settings.get("total_deposited", 7500.0)))

        if action == "YES":
            success = are.update_risk_pct(rec_pct)
            are.mark_adherence(recommended_pct=rec_pct, actual_pct=rec_pct, followed=True)
            are.log_risk_journal({
                "direction": "up" if rec_pct > curr_pct else "down_fast",
                "current_risk_pct": curr_pct,
                "recommended_risk_pct": rec_pct,
                "action": "confirmed",
                "actual_pct_set": rec_pct,
                "nav": nav,
            })
            status = "✅" if success else "⚠️ שגיאת שמירה"
            try:
                bot.edit_message_text(
                    f"{RTL}{status} *סיכון עודכן ל-{rec_pct:.2f}%*\n"
                    f"{RTL}(${round(nav * rec_pct / 100):,.0f} לעסקה) — נשמר ביומן הסיכון.",
                    chat_id, call.message.message_id, parse_mode="Markdown"
                )
            except Exception:
                bot.send_message(chat_id, f"{status} סיכון עודכן ל-{rec_pct:.2f}%", parse_mode="Markdown")

        elif action == "NO":
            user_state[chat_id] = {
                "action": "risk_reject_reason",
                "rec_pct": rec_pct,
                "curr_pct": curr_pct,
                "original_msg_id": call.message.message_id,
            }
            try:
                bot.edit_message_text(
                    f"{RTL}❌ *דוחה שינוי סיכון*\n{RTL}המלצה: `{rec_pct:.2f}%` ← נדחתה\n\n{RTL}📝 חובה: הסבר את הסיבה (יירשם ביומן):",
                    chat_id, call.message.message_id, parse_mode="Markdown"
                )
            except Exception:
                bot.send_message(chat_id, f"{RTL}📝 *הסבר מדוע דחית:*", parse_mode="Markdown")

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

    # ── טיפול ב-state פעיל ─────────────────────────────────────────────
    active_state = user_state.get(chat_id, {})
    if active_state.get("action") == "risk_reject_reason":
        reason = text.strip()
        rec_pct = active_state["rec_pct"]
        curr_pct = active_state["curr_pct"]
        account_settings = get_account_settings()
        nav = float(account_settings.get("nav", account_settings.get("total_deposited", 7500.0)))
        are.mark_adherence(recommended_pct=rec_pct, actual_pct=curr_pct, followed=False, reason=reason)
        are.log_risk_journal({
            "direction": "up" if rec_pct > curr_pct else "down_fast",
            "current_risk_pct": curr_pct,
            "recommended_risk_pct": rec_pct,
            "action": "rejected",
            "reason": reason,
            "actual_pct_set": curr_pct,
            "nav": nav,
        })
        del user_state[chat_id]
        bot.send_message(
            chat_id,
            f"{RTL}📝 *הדחייה נרשמה ביומן הסיכון*\n{RTL}המלצה `{rec_pct:.2f}%` נדחתה.\n{RTL}סיבה: _{reason}_",
            reply_markup=get_main_menu(), parse_mode="Markdown"
        )
        return

    # ── תפריטים היררכיים ──────────────────────────────────────────────
    if text == "⬅️ חזרה לתפריט ראשי":
        if chat_id in user_state: del user_state[chat_id]
        bot.send_message(chat_id, f"{RTL}🏠 *תפריט ראשי*", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if text == "📊 מצב תיק":
        bot.send_message(chat_id, f"{RTL}📊 *מצב תיק — בחר פעולה:*", reply_markup=get_portfolio_menu(), parse_mode="Markdown")
        return

    if text == "🔬 ניתוח":
        bot.send_message(chat_id, f"{RTL}🔬 *ניתוח — בחר פעולה:*", reply_markup=get_analysis_menu(), parse_mode="Markdown")
        return

    if text == "📚 יומן":
        bot.send_message(chat_id, f"{RTL}📚 *יומן — בחר פעולה:*", reply_markup=get_journal_menu(), parse_mode="Markdown")
        return

    if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]:
        help_txt = (
            f"{RTL}🛡️ *Sentinel — מדריך פקודות*\n"
            f"{RTL}───────────────\n"
            f"{RTL}📊 *מצב תיק* — פוזיציות ומשטר שוק\n"
            f"{RTL}🔬 *ניתוח* — סקירת מניה ו-Trend Template\n"
            f"{RTL}📚 *יומן* — מילוי יומן וארכיון\n"
            f"{RTL}───────────────\n"
            f"{RTL}/portfolio — חדר מצב\n"
            f"{RTL}/trade SYMBOL — ניתוח עומק לפוזיציה\n"
            f"{RTL}/mentor SYMBOL — Trend Template מלא\n"
            f"{RTL}/analyze SYMBOL — ניתוח VCP מינרביני\n"
            f"{RTL}/next — יומן (הבא)\n"
            f"{RTL}/stats — סטטיסטיקת ציות להמלצות סיכון\n"
        )
        return bot.send_message(chat_id, help_txt, reply_markup=get_main_menu(), parse_mode="Markdown")

    if text in ["/stats", "📊 סטטיסטיקת ציות"]:
        stats = are.compute_adherence_stats()
        if not stats.get("ok"):
            bot.send_message(chat_id, f"⚪ {stats.get('message', 'שגיאה')}", parse_mode="Markdown")
            return
        last_str = " ".join(stats.get("last_actions", []))
        msg = (
            f"{RTL}📊 *סטטיסטיקת ציות — המלצות סיכון*\n"
            f"{RTL}───────────────\n"
            f"{RTL}סה\"כ המלצות: `{stats['total_recommendations']}`\n"
            f"{RTL}הוערכו: `{stats['evaluated']}`\n"
            f"{RTL}אושרו ✅: `{stats['followed']}`\n"
            f"{RTL}נדחו ❌: `{stats['not_followed']}`\n"
        )
        if stats["adherence_pct"] is not None:
            msg += f"{RTL}ציות כללי: `{stats['adherence_pct']:.0f}%`\n"
        if last_str:
            msg += f"{RTL}10 האחרונות: {last_str}"
        return bot.send_message(chat_id, msg, parse_mode="Markdown")

    if text == "🧠 ניתוח מינרביני מלא":
        bot.send_message(chat_id, f"{RTL}🧠 *ניתוח Trend Template מלא (8 קריטריונים):*\nהקלד סימול מניה (לדוגמה: AAPL):", parse_mode="Markdown")
        user_state[chat_id] = {'action': 'mentor_symbol'}
        return

    if text.startswith("/mentor ") or text.startswith("/mentor\n"):
        sym_raw = text.split(" ", 1)[-1].strip().upper()
        if sym_raw:
            _loading = bot.send_message(chat_id, f"⏳ מנתח Trend Template עבור {sym_raw}...", parse_mode="Markdown")
            tt_res = ec.compute_trend_template_full(sym_raw)
            report = tf.fmt_minervini_trend_template(sym_raw, tt_res)
            try: bot.delete_message(chat_id, _loading.message_id)
            except: pass
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
        return

    if text.startswith("/analyze "):
        symbol = text.split(" ")[1].upper()
        bot.send_message(chat_id, f"⏳ מנתח נתונים עבור {symbol}...", parse_mode="Markdown")
        report_res = ec.get_minervini_analysis(symbol)
        report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
        bot.send_message(chat_id, report, parse_mode="Markdown")
        return

    if text == "🔬 סקירת מניה":
        bot.send_message(chat_id, "📈 *מנתח Trend Template:*\nאנא הקלד את סימול המניה לסריקה (לדוגמה: AAPL):", parse_mode="Markdown")
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
        return bot.send_message(chat_id, "🛡️ *מערכת הפיקוד (Sentinel Command)*\n\n/trade SYMBOL - צלילת עומק לפוזיציה\n/next - סריקת יומן\n/portfolio - חדר מצב\n/clean - מטאטא ארכיון (מוגן 30 יום)", parse_mode="Markdown")

    if text == "🌡️ משטר שוק וסיכונים":
        msg_id = bot.send_message(chat_id, "⏳ בודק דופק שוק...", parse_mode="Markdown").message_id
        try:
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")
            qqq_hist = ec.get_cached_history("QQQ", "1y", "1d")
            regime = ec.compute_market_regime(spy_hist, qqq_hist)
            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            pos_res = ec.get_open_positions_campaign(df)
            open_pos = pos_res["data"] if pos_res["ok"] else pd.DataFrame()
            account_settings = get_account_settings()
            ibkr_nav = get_ibkr_nav()
            acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
            exp = {"ALGO": 0, "VCP": 0, "EP": 0, "OTHER": 0}
            if not open_pos.empty:
                for _, row in open_pos.iterrows():
                    sym, setup = row["symbol"], str(row["setup_type"]).upper()
                    curr = ec.get_live_price(sym) or float(row["price"])
                    val = curr * float(row["quantity"])
                    if setup in exp: exp[setup] += val
                    else: exp["OTHER"] += val
            total_exp = sum(exp.values())
            total_pct = (total_exp / acc_size) * 100 if acc_size > 0 else 0
            rep = tf.fmt_regime_report(regime, total_pct, exp["ALGO"], exp["VCP"], exp["EP"], acc_size)
            # --- Adaptive Risk Block ---
            try:
                current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
                nav_for_risk = ibkr_nav if ibkr_nav else float(account_settings.get("nav", acc_size))
                closed_camps = are.compute_closed_campaigns(df)
                risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, nav_for_risk)
                rep += tf.fmt_adaptive_risk_block(risk_rec)
            except Exception:
                pass
            bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")
        except Exception as e: bot.edit_message_text(f"❌ תקלה בחישוב משטר שוק: {e}", chat_id, msg_id)
        return

    if text in ["📊 חדר מצב (פוזיציות)", "/portfolio"]:
        loading_msg = bot.send_message(chat_id, "⏳ *שואב נתונים ומרכיב דו\"ח...*", parse_mode="Markdown")
        try:
            res = supabase.table("trades").select("*").execute()
            df = pd.DataFrame(res.data)
            pos_res = ec.get_open_positions_campaign(df)
            if not pos_res["ok"]:
                try: bot.delete_message(chat_id, loading_msg.message_id)
                except: pass
                return bot.send_message(chat_id, f"❌ שגיאת תשתית במשיכת פוזיציות:\n`{pos_res['error']}`")
            open_pos = pos_res["data"]
            if open_pos.empty: 
                try: bot.delete_message(chat_id, loading_msg.message_id)
                except: pass
                return bot.send_message(chat_id, "✅ אין פוזיציות פתוחות במערכת.")

            account_settings = get_account_settings()
            ibkr_nav = get_ibkr_nav()
            acc_size = ibkr_nav if ibkr_nav else float(account_settings.get("total_deposited", 7500.0))
            target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
            target_risk_usd = acc_size * (target_risk_pct / 100)
            spy_hist = ec.get_cached_history("SPY", "1y", "1d")
            
            user_state[chat_id] = {'temp_positions': open_pos.to_dict('records')}
            total_open_pnl = total_disc_pnl = total_algo_pnl = total_risk = total_realized_camp = 0
            total_exposure = total_disc_exposure = total_algo_exposure = 0
            total_locked_profit = total_giveback_risk = 0
            
            algo_count = 0
            active_symbols = []
            
            msg = f"{RTL}🔭 *חדר מצב - דו\"ח ריכוז פוזיציות:*\n\n"
            
            for i, row in enumerate(user_state[chat_id]['temp_positions'], 1):
                sym = row['symbol']
                active_symbols.append(sym)
                entry, sl, init_sl = row['price'], row['stop_loss'], row['initial_stop']
                setup, qty, init_qty = row['setup_type'], row['quantity'], row.get('initial_qty', row['quantity']) 
                realized_pnl, entry_date, mgt_state = row.get('realized_pnl', 0), row['entry_date'], row.get('management_state', 'full_position')
                
                add_on_count = row.get('add_on_count', 0)
                base_price = row.get('base_price', entry)
                base_qty = row.get('base_qty', init_qty)
                
                curr = ec.get_live_price(sym)
                if curr is None: curr = entry
                
                open_pnl_usd = (curr - entry) * qty
                pos_value = curr * qty
                total_pos_profit = open_pnl_usd + realized_pnl
                weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0
                
                init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
                original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
                
                if sl > base_price: 
                    current_open_loss_risk = 0
                    locked_profit_usd = (sl - base_price) * qty
                    giveback_risk_usd = (curr - sl) * qty if curr > sl else 0
                else:
                    current_open_loss_risk = (base_price - sl) * qty if sl > 0 else 0
                    locked_profit_usd = 0
                    giveback_risk_usd = 0
                
                total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
                open_r_val = (open_pnl_usd / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl_usd / original_campaign_risk) if original_campaign_risk > 0 else 0)

                engine_res = ec.evaluate_position_engine(symbol=sym, entry_price=entry, entry_date_str=entry_date, current_stop=sl, setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r, target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist)
                if not engine_res["ok"]: status, action_short, trigger, issues_str, sizing_str, score, stage, suggested_stop, feats = ("❌ שגיאה", "שגיאה", engine_res["error"], "", "✅ תקין", None, "", sl, {})
                else:
                    e_data = engine_res["data"]
                    status, action_short, trigger = e_data['status'], e_data['action'], e_data['trigger']
                    sizing_str = e_data.get('sizing_status', "✅ תקין")
                    issues_str = f": {' | '.join(e_data['issues'])}" if e_data['issues'] else ""
                    score, stage, suggested_stop, feats = e_data['score'], e_data['stage'], e_data['suggested_stop'], e_data.get('features', {})
                
                total_open_pnl += open_pnl_usd
                total_realized_camp += realized_pnl
                total_exposure += pos_value
                total_locked_profit += locked_profit_usd
                total_giveback_risk += giveback_risk_usd
                
                try: days_held = (datetime.now() - pd.to_datetime(entry_date)).days if entry_date else 0
                except: days_held = 0
                pnl_icon = '🟢' if open_pnl_usd >= 0 else '🔴'
                
                qty_text = f"`{qty}`" + (f" (+חיזוק)" if add_on_count > 0 else "")
                entry_text = f"${entry:.2f}" + (f" (בסיס: ${base_price:.2f})" if add_on_count > 0 else "")

                if str(setup).upper() == 'ALGO':
                    algo_count += 1
                    total_algo_pnl += open_pnl_usd
                    total_algo_exposure += pos_value
                    open_r_str = f"`{open_r_val:.1f}R` *(Target Risk Base)*"
                    e_data = engine_res.get("data") or {}
                    risk_basis = e_data.get("risk_basis", "Target")
                    risk_vis = e_data.get("risk_visibility_score", 40)

                    msg += f"{RTL}*{i}. {sym}* | 🏷️ ALGO | 🟠 מנוהל חיצונית\n"
                    msg += f"{RTL}   ▸ ותק: `{days_held}` ימים | כמות: {qty_text}\n"
                    msg += f"{RTL}   ▸ כניסה: {entry_text} | נוכחי: `${curr:.2f}`\n"
                    msg += f"{RTL}   ▸ סטופ: מנוהל חיצונית | בסיס R: `{risk_basis}` | שקיפות סיכון: `{risk_vis}/100`\n"
                    msg += f"{RTL}   ▸ רווח צף: {pnl_icon} `${open_pnl_usd:.2f}` | כולל: `${total_pos_profit:.2f}`\n"
                    msg += f"{RTL}   ▸ חשיפה: `{weight_pct:.1f}%` מקרן הבסיס\n"
                    msg += f"{RTL}   ▸ Open R (צף): {open_r_str}\n"
                    msg += f"{RTL}   ▸ סטטוס שוק: {status}\n"
                    msg += f"{RTL}   ▸ פיקוח: `מידע בלבד — Sentinel אינה מנהלת יציאות אלגו`\n"
                else:
                    total_disc_pnl += open_pnl_usd
                    total_disc_exposure += pos_value
                    total_risk += current_open_loss_risk
                    
                    if original_campaign_risk > 0:
                        open_r_str = f"`{open_r_val:.1f}R`"
                    else:
                        open_r_str = "`N/A` ⚠️ (חסר סטופ התחלתי)"
                        
                    score_text = f" (ציון: `{score}/100`)" if score is not None else ""
                    init_sl_display = f"${init_sl_clean:.2f}" if init_sl_clean > 0 else "חסר/מעל כניסה"
                    
                    msg += f"{RTL}*{i}. {sym}* | 🏷️ {setup}\n"
                    msg += f"{RTL}   ▸ ותק: `{days_held}` ימים ({stage}) | כמות: {qty_text}\n"
                    msg += f"{RTL}   ▸ כניסה: {entry_text} | נוכחי: `${curr:.2f}`\n"
                    msg += f"{RTL}   ▸ סטופ מקורי: `{init_sl_display}` | סטופ נוכחי: `${sl:.2f}`\n"
                    msg += f"{RTL}   ▸ רווח צף: {pnl_icon} `${open_pnl_usd:.2f}` | כולל: `${total_pos_profit:.2f}`\n"
                    msg += f"{RTL}   ▸ Open R (צף): {open_r_str}\n"
                    
                    if current_open_loss_risk > 0:
                        msg += f"{RTL}   ▸ סיכון הון פתוח: `${current_open_loss_risk:.0f}`\n"
                    else:
                        msg += f"{RTL}   ▸ ניהול רווח: מובטח `${locked_profit_usd:.0f}` | ויתור פוטנציאלי `${giveback_risk_usd:.0f}`\n"
                    
                    if original_campaign_risk > 0 and sizing_str != "✅ תקין":
                        clean_sizing = sizing_str.replace('⚠️ ', '').replace('📉 ', '')
                        msg += f"{RTL}   ▸ ⚖️ בקרת קמפיין: {clean_sizing}\n"
                    if total_campaign_r <= -1.25 and original_campaign_risk > 0:
                        msg += f"{RTL}   ▸ 🚨 בקרת ביצוע: חריגה מהסטופ! ({total_campaign_r:.1f}R)\n"
                    
                    msg += f"{RTL}   ▸ סטטוס: {status}{score_text}{issues_str}\n"
                    msg += f"{RTL}   ▸ פעולה: *{action_short}*\n"
                    if trigger: msg += f"{RTL}   ▸ טריגר ניהולי: `{trigger}`\n"

                rs_str = ""
                if feats and feats.get("rs20_market") is not None:
                    rm = feats["rs20_market"] * 100
                    rss = feats.get("rs20_stock_sector")
                    if rss is not None:
                        rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm:+.1f}% | סקטור {rss * 100:+.1f}%\n"
                    else:
                        rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm:+.1f}%\n"
                msg += rs_str + f"{RTL}〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

            total_weight = (total_exposure / acc_size) * 100 if acc_size > 0 else 0
            algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
            total_pnl_icon = '🟢' if total_open_pnl >= 0 else '🔴'
            
            total_secured = total_realized_camp + total_locked_profit

            msg += f"{RTL}📊 *סיכום תיק הפיקוד:*\n"
            msg += f"{RTL}▸ סה\"כ רווח צף: {total_pnl_icon} `${total_open_pnl:,.2f}` (דיסק': `${total_disc_pnl:,.2f}`)\n"
            msg += f"{RTL}▸ סה\"כ סיכון הפסד הון (דיסק'): `${total_risk:,.2f}`\n"
            msg += f"{RTL}▸ רווח שמומש בעסקאות פתוחות: `${total_realized_camp:,.2f}`\n"
            msg += f"{RTL}▸ רווח נעול (Locked) בסטופים: `${total_locked_profit:,.2f}`\n"
            msg += f"{RTL}▸ סך הכל רווח מוגן (Secured): `${total_secured:,.2f}`\n"
            msg += f"{RTL}▸ סיכון ויתור רווח צף (Giveback): `${total_giveback_risk:,.2f}`\n"
            msg += f"{RTL}▸ חשיפה כללית: `{total_weight:.1f}%` מקרן הבסיס\n"
            if algo_count > 0:
                msg += f"\n{RTL}🤖 *בקרת אשכול אלגו:*\n{RTL}▸ חשיפה אלגו: `{algo_cluster_pct:.1f}%` מהקרן\n"

            # שורת coaching מינרביני
            spy_hist_caching = ec.get_cached_history("SPY", "1y", "1d")
            regime_for_coaching = ec.compute_market_regime(spy_hist_caching)
            regime_status_str = regime_for_coaching.get('data', {}).get('status', '') if regime_for_coaching.get('ok') else ''
            try:
                all_res = supabase.table("trades").select("campaign_id,pnl_usd,trade_date").execute()
                camp_all = pd.DataFrame(all_res.data)
                if not camp_all.empty and 'campaign_id' in camp_all.columns:
                    closed_cids = camp_all.groupby('campaign_id')['pnl_usd'].sum()
                    wins_c = (closed_cids > 0).sum()
                    wr_c = wins_c / len(closed_cids) if len(closed_cids) > 0 else 0
                else:
                    wr_c = 0
            except: wr_c = 0
            coaching_insights = ec.generate_minervini_coaching(
                win_rate=wr_c, expectancy_r=0, adj_rr=0,
                oversized_count=0, market_regime_status=regime_status_str,
                streak_losses=0, total_r_net=0
            )
            if coaching_insights:
                msg += f"\n{RTL}🎓 *מינרביני אומר:*\n"
                for ins in coaching_insights[:2]:  # מקסימום 2 insights בטלגרם
                    clean_ins = ins.replace('<b>', '*').replace('</b>', '*')
                    msg += f"{RTL}▸ {clean_ins}\n"

            # --- Adaptive Risk Recommendation ---
            try:
                current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
                nav_for_risk = float(account_settings.get("nav", acc_size))
                closed_camps = are.compute_closed_campaigns(df)
                risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, nav_for_risk)
                msg += tf.fmt_adaptive_risk_block(risk_rec)
            except Exception:
                pass

            try: bot.delete_message(chat_id, loading_msg.message_id)
            except: pass
            
            markup = types.InlineKeyboardMarkup(row_width=3)
            drill_btns = [types.InlineKeyboardButton(text=f"🔍 {s}", callback_data=f"drill|{s}") for s in active_symbols]
            markup.add(*drill_btns)
            markup.add(types.InlineKeyboardButton("🎯 הזן קידום סטופ", callback_data="start_trail_flow"))
            
            send_long_message(chat_id, msg, reply_markup=markup)
            
        except Exception as e:
            err_details = traceback.format_exc()
            b_ticks = "`" * 3
            try: bot.delete_message(chat_id, loading_msg.message_id)
            except: pass
            bot.send_message(chat_id, f"❌ תקלת מערכת בחדר המצב:\n`{e}`\n\n{b_ticks}\n{err_details[-500:]}\n{b_ticks}", parse_mode="Markdown")
            return

    if chat_id in user_state:
        state = user_state[chat_id]
        action = state.get('action')

        if action == 'analyze_symbol':
            symbol = text.strip().upper()
            bot.send_message(chat_id, f"⏳ מושך נתונים טכניים ומנתח את {symbol}...", parse_mode="Markdown")
            report_res = ec.get_minervini_analysis(symbol)
            report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
            del user_state[chat_id]
            return

        if action == 'mentor_symbol':
            symbol = text.strip().upper()
            _loading = bot.send_message(chat_id, f"⏳ מנתח Trend Template מלא עבור {symbol}...", parse_mode="Markdown")
            tt_res = ec.compute_trend_template_full(symbol)
            report = tf.fmt_minervini_trend_template(symbol, tt_res)
            try: bot.delete_message(chat_id, _loading.message_id)
            except: pass
            bot.send_message(chat_id, report, reply_markup=get_analysis_menu(), parse_mode="Markdown")
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
