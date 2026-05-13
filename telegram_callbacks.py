"""
Telegram callback query handler for Sentinel Trading.

Separated from telegram_bot.py to isolate callback routing.
bot/supabase instances come from bot_core; helpers from bot_helpers.

handle_drilldown and get_next_missing are lazy-imported from telegram_bot
to avoid circular dependency (they use bot/supabase defined in bot_core).
"""
import telebot
from datetime import datetime
import adaptive_risk_engine as are
import supabase_repository as repo
from bot_core import bot, supabase, user_state, RTL
from bot_helpers import (_DEV_LOG_FILES, _read_last_log_lines,
                         _write_runner_decision, get_account_settings, get_nav_and_risk)
from telegram_menus import get_main_menu, get_developer_menu


@bot.callback_query_handler(func=lambda call: True)
def handle_queries(call):
    # lazy import — telegram_bot is fully defined by the time any callback fires
    import telegram_bot as _tb

    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("devlog|"):
        bot.answer_callback_query(call.id)
        service_name = data.split("|", 1)[1]
        log_path = _DEV_LOG_FILES.get(service_name, "")
        lines = _read_last_log_lines(log_path, 50)
        header = f"{RTL}📋 *לוגים — {service_name} (50 שורות אחרונות):*\n"
        body   = f"```\n{lines[-3600:]}\n```"
        try:
            bot.send_message(chat_id, header + body,
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, header + lines[-3000:],
                             reply_markup=get_developer_menu())
        return

    if data.startswith("drill|"):
        symbol = data.split("|")[1]
        bot.answer_callback_query(call.id)
        _tb.handle_drilldown(chat_id, symbol)
        return

    if data == "open_backlog":
        bot.answer_callback_query(call.id)
        _tb.get_next_missing(chat_id)
        return

    if data == "start_trail_flow":
        if chat_id in user_state and 'temp_positions' in user_state[chat_id]:
            count = len(user_state[chat_id]['temp_positions'])
            bot.send_message(chat_id, f"🎯 *קידום סטופ:*\nהקלד את מספר הטרייד מהרשימה (1-{count}):\n(או שלח 'ביטול')", parse_mode="Markdown")
            user_state[chat_id]['action'] = 'select_trade_index'
        else:
            bot.send_message(chat_id, "⚠️ המידע פג תוקף. לחץ שוב על 'חדר מצב'.")
        bot.answer_callback_query(call.id)

    elif data == "cancel_action":
        bot.send_message(chat_id, "❌ הפעולה בוטלה.", reply_markup=get_main_menu())
        if chat_id in user_state: del user_state[chat_id]
        bot.answer_callback_query(call.id)

    elif data.startswith("risk_confirm|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        action  = parts[1]
        rec_pct = float(parts[2])
        curr_pct = float(parts[3])
        account_settings = get_account_settings()
        nav, _, _ = get_nav_and_risk(account_settings)

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

    elif data.startswith("runner_decision|"):
        bot.answer_callback_query(call.id)
        parts  = data.split("|")
        action = parts[1] if len(parts) > 1 else ""
        sym    = parts[2] if len(parts) > 2 else ""
        cid    = parts[3] if len(parts) > 3 else ""
        try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception: pass

        if action == "hold":
            _write_runner_decision(cid, "hold")
            if cid:
                try:
                    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    repo.update_management_notes(supabase, cid, f"Runner: להחזיק ({ts_str})")
                except Exception: pass
            bot.send_message(chat_id, f"{RTL}✅ *{sym} — להחזיק*\nההחלטה נרשמה. Sentinel לא ישלח התראות Runner ל-24 שעות.", parse_mode="Markdown")

        elif action == "tighten":
            user_state[chat_id] = {"action": "tighten_stop", "sym": sym, "campaign_id": cid}
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("❌ ביטול", callback_data="cancel_action"))
            bot.send_message(chat_id, f"{RTL}🔒 *{sym} — הדקת סטופ*\nהזן את מחיר הסטופ החדש:", reply_markup=markup, parse_mode="Markdown")

        elif action == "partial":
            if cid:
                try:
                    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    repo.update_management_notes(supabase, cid, f"Runner: כוונת מימוש חלקי ({ts_str})")
                except Exception: pass
            bot.send_message(chat_id, f"{RTL}📊 *{sym} — מימוש חלקי*\nהכוונה נרשמה. בצע את הפקודה ב-IBKR ועדכן במערכת לאחר ביצוע.", parse_mode="Markdown")

    elif data.startswith("addon_confirm|"):
        bot.answer_callback_query(call.id)
        parts  = data.split("|")
        action = parts[1] if len(parts) > 1 else ""
        sym    = parts[2] if len(parts) > 2 else ""
        try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
        except Exception: pass

        if action == "YES":
            pending = user_state.get(chat_id, {})
            entry   = pending.get("entry", 0)
            stop    = pending.get("stop", 0)
            qty     = pending.get("qty", 0)
            ts_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
            note    = f"Add-On אושר: כניסה ${entry} | סטופ ${stop} | כמות {qty} ({ts_str})"
            try:
                # record confirmation in management_notes of the open campaign
                res = supabase.table("trades").select("campaign_id").eq("symbol", sym).execute()
                cid = res.data[0]["campaign_id"] if res.data else None
                if cid:
                    repo.update_management_notes(supabase, cid, note)
            except Exception:
                pass
            if chat_id in user_state:
                del user_state[chat_id]
            bot.send_message(
                chat_id,
                f"{RTL}✅ *Add-On אושר — {sym}*\n{RTL}כניסה: `${entry}` | סטופ: `${stop}` | כמות: `{qty}`\n{RTL}נרשם ב-management\\_notes.",
                parse_mode="Markdown",
            )
        else:
            if chat_id in user_state:
                del user_state[chat_id]
            bot.send_message(chat_id, f"{RTL}❌ Add-On בוטל.", reply_markup=get_main_menu())

    elif data.startswith("v|"):
        bot.answer_callback_query(call.id)
        parts = data.split('|')
        try:
            t_id, field, val = parts[1], parts[2], parts[3]
            if field in ['quality', 'score']:
                repo.update_trade(supabase, t_id, {field: int(val)})
            elif field == 'initial_stop':
                repo.update_trade(supabase, t_id, {"initial_stop": float(val), "stop_loss": float(val)})
            elif field == 'stop_loss':
                repo.update_trade(supabase, t_id, {field: float(val)})
            else:
                save_val = "Skipped" if val == 'Skipped' else val
                repo.update_trade(supabase, t_id, {field: save_val})
            bot.delete_message(chat_id, call.message.message_id)
            _tb.get_next_missing(chat_id)
        except Exception as e:
            bot.send_message(chat_id, f"❌ *תקלה בעדכון:* {str(e)}", parse_mode="Markdown")
