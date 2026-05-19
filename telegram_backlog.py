"""
Journal backlog scanner for Sentinel Trading.

get_next_missing() drives the step-by-step journal completion flow.
Dependencies are passed via module-level singletons from bot_core.
"""
from telebot import types
import engine_core as ec
import supabase_repository as repo
import telegram_formatters as tf
from bot_core import bot, supabase, user_state
from telegram_menus import get_main_menu, get_setup_keyboard, get_rating_keyboard


def get_next_missing(chat_id):
    try:
        t = None
        for row in repo.get_incomplete_trades(supabase):
            if str(row.get('setup_type')) == 'Legacy':
                continue
            if row.get('side', '').upper() == 'BUY':
                cid = row.get('campaign_id')
                if cid:
                    older_buys_data = repo.get_earlier_buys_for_campaign(supabase, cid, row["trade_date"])
                    if older_buys_data:
                        first_b = older_buys_data[0]
                        upd = {
                            "setup_type": first_b.get("setup_type"),
                            "quality":    first_b.get("quality"),
                            "initial_stop": first_b.get("initial_stop"),
                            "stop_loss":  first_b.get("stop_loss"),
                        }
                        repo.update_trade(supabase, row["trade_id"], upd)
                        continue
                if str(row.get('setup_type')).upper() == 'ALGO':
                    init_sl = row.get('initial_stop')
                    if init_sl is None or init_sl == 0:
                        repo.update_trade(supabase, row["trade_id"], {"initial_stop": -1, "stop_loss": -1})
                        continue
            elif row.get('side', '').upper() == 'SELL':
                # Setup/Quality are entry-time, campaign-level properties answered
                # at open. Mirror the BUY add-on inheritance above so the close
                # journal does not re-ask an already-answered open question.
                cid = row.get('campaign_id')
                if cid:
                    older_buys = repo.get_earlier_buys_for_campaign(supabase, cid, row["trade_date"])
                    if older_buys:
                        first_b = older_buys[0]
                        upd = {}
                        for f in ("setup_type", "quality"):
                            if row.get(f) is None and first_b.get(f) is not None:
                                upd[f] = first_b.get(f)
                        if upd:
                            repo.update_trade(supabase, row["trade_id"], upd)
                            continue
            t = row
            break

        if not t:
            bot.send_message(chat_id, "✅ *היומן מעודכן לחלוטין!*\nאין חוסרים במערכת.",
                             reply_markup=get_main_menu(), parse_mode="Markdown")
            return

        t_id, symbol, side, t_date = t['trade_id'], t['symbol'], t['side'], t['trade_date']
        total_steps = 3 if side.upper() == 'BUY' else 5
        curr_step = 1
        if t.get('setup_type') is not None:
            curr_step += 1
        if t.get('quality') is not None:
            curr_step += 1
        if side.upper() == 'BUY':
            if t.get('initial_stop') not in [None, 0]:
                curr_step += 1
        elif side.upper() == 'SELL':
            if t.get('score') is not None:
                curr_step += 1
            if t.get('image_url') is not None and str(t.get('image_url')) not in ["None", "Skipped"]:
                curr_step += 1

        card = (f"🏷️ *נכס:* {symbol} | {side}\n"
                f"📅 *תאריך:* {t_date}\n"
                f"🆔 *מזהה:* `{t_id}`\n"
                f"⏳ *השלמת יומן - שלב {curr_step}/{total_steps}*\n"
                f"〰️〰️〰️〰️〰️〰️〰️〰️〰️〰️")

        if t.get('setup_type') is None:
            bot.send_message(chat_id, f"{card}\n🎯 *אנא סווג את האסטרטגיה (Setup):*",
                             reply_markup=get_setup_keyboard(t_id), parse_mode="Markdown")
            return

        if t.get('quality') is None:
            if str(t.get('setup_type')).upper() == 'VCP':
                bot.send_message(chat_id, f"⏳ מנתח Trend Template עבור {symbol}...", parse_mode="Markdown")
                report_res = ec.get_minervini_analysis(symbol)
                report = report_res["data"][0] if report_res["ok"] else str(report_res.get("error", "Error")).replace("_", " ")
                bot.send_message(chat_id, f"{card}\n{report}\n\n💎 *מה הציון הסופי שלך? (1-10):*",
                                 reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"{card}\n💎 *מהי איכות הסטאפ בטרייד זה? (1-10):*",
                                 reply_markup=get_rating_keyboard(t_id, 'quality'), parse_mode="Markdown")
            return

        if side.upper() == "BUY":
            init_sl = t.get('initial_stop')
            if init_sl is None or init_sl == 0:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג / ללא סטופ",
                                                       callback_data=f"v|{t_id}|initial_stop|-1"))
                # Sprint-13 / Mark §2 (:54-58, :74-80): the open-position
                # missing-stop surfaces ONLY via this EXISTING journal-backlog
                # prompt, which writes ONLY the founder-typed price or the
                # existing -1 skip sentinel (callback above) — NEVER a
                # fabricated/defaulted value. Mark's VERBATIM Hebrew
                # (tf.MISSING_STOP_BACKLOG_HE) makes the no-fabrication /
                # not-counted-until-complete contract explicit to the founder.
                mark_he = tf.MISSING_STOP_BACKLOG_HE.format(SYMBOL=symbol)
                bot.send_message(chat_id,
                                 f"{card}\n{mark_he}\n"
                                 f"🎯 *מהו הסטופ ההתחלתי? (Initial Stop)*\n"
                                 f"יש להקליד כעת את מחיר הסטופ המקורי (למשל 150.50).",
                                 reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'initial_stop', 't_id': t_id}
                return

        if side.upper() == "SELL":
            if t.get('score') is None:
                bot.send_message(chat_id, f"{card}\n🏆 *כיצד היית מדרג את סגירת העסקה שלך? (1-10):*",
                                 reply_markup=get_rating_keyboard(t_id, 'score'), parse_mode="Markdown")
                return
            if t.get('image_url') is None or t.get('image_url') == "None":
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ דילוג על תמונה",
                                                       callback_data=f"v|{t_id}|image_url|Skipped"))
                bot.send_message(chat_id,
                                 f"{card}\n🔗 *קישור לתמונה נדרש:*\nאנא הדבק קישור מ-TradingView.",
                                 reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'image', 't_id': t_id}
                return
            if t.get('management_notes') is None:
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(text="⏭️ ללא הערה (דילוג)",
                                                       callback_data=f"v|{t_id}|management_notes|Skipped"))
                bot.send_message(chat_id,
                                 f"{card}\n📝 *תובנות ניהול פוזיציה (אופציונלי):*\n"
                                 f"הקלד כעת בהודעה את תובנות הניהול, תחושות או טעויות שביצעת "
                                 f"(יישמר בעמודה ייעודית).",
                                 reply_markup=markup, parse_mode="Markdown")
                user_state[chat_id] = {'action': 'management_notes', 't_id': t_id}
                return

    except Exception as e:
        bot.send_message(chat_id, f"❌ *שגיאת מערכת:* {str(e)}", parse_mode="Markdown")
