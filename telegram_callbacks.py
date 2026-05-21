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
import audit_logger
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

    # ── RISK-1c — admin-triggered at-entry-lock backfill confirm/cancel ─────
    # The preview + inline keyboard are emitted by the developer-menu handler
    # in telegram_bot.py (`🔒 נעילה היסטורית (RISK-1c)`). The PIN session
    # check happened there; once the inline buttons are visible, this
    # callback only fires for the operator who initiated the preview (Telegram
    # routes callbacks to the same chat). The orchestration + all per-row +
    # batch-level audit rows live in risk1c_backfill.run_backfill — this
    # callback is thin presentation only.
    if data == "risk1c|cancel":
        bot.answer_callback_query(call.id, text="בוטל.")
        bot.send_message(
            chat_id,
            f"{RTL}❌ *RISK-1c — בוטל*\n"
            f"{RTL}לא בוצע שינוי. החזרה לתפריט מפתח.",
            reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if data == "risk1c|confirm":
        bot.answer_callback_query(call.id, text="מבצע נעילה...")
        bot.send_message(
            chat_id,
            f"{RTL}🔒 *RISK-1c — מבצע נעילה...*\n"
            f"{RTL}_עד דקה לפי גודל ה-backlog. עדכון יגיע בסיום._",
            parse_mode="Markdown")
        try:
            import risk1c_backfill as _r1c
            result = _r1c.run_backfill(supabase, chat_id=chat_id)
            msg = _r1c.format_result(result)
        except Exception as e:
            msg = (f"{RTL}❌ *RISK-1c — שגיאה בריצה:* `{str(e)[:300]}`\n"
                   f"{RTL}_חלק מהשורות אולי ננעלו לפני השגיאה — בדוק את ה-audit log._")
        bot.send_message(
            chat_id, msg,
            reply_markup=get_developer_menu(), parse_mode="Markdown")
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

    # ── Lightweight tap-only stop promotion (UX_TELEGRAM_AUDIT_DAY3 Pain 1) ──
    if data == "promote_open":
        bot.answer_callback_query(call.id)
        _tb.handle_stop_promote_entry(chat_id)
        return

    if data.startswith("promote_pick|"):
        bot.answer_callback_query(call.id)
        try:
            idx = int(data.split("|", 1)[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_stop_promote_pick(chat_id, idx)
        return

    if data == "promote_algo_noop":
        bot.answer_callback_query(
            call.id,
            text="🟠 ALGO מנוהל חיצונית — Sentinel אינה מקדמת סטופ אלגו.",
            show_alert=True,
        )
        return

    # Sprint-12 / Mark §3 — non-tappable honest price-fallback note row.
    if data == "promote_price_fallback_note":
        import telegram_formatters as _tf
        bot.answer_callback_query(
            call.id,
            text=_tf.PRICE_FALLBACK_LABEL,
            show_alert=True,
        )
        return

    # ── Open Tasks (Action-Items) — pull-only view + lifecycle ──────────────
    if data == "task_algo_noop":
        bot.answer_callback_query(
            call.id,
            text="🟠 ALGO מנוהל חיצונית — אין פעולה ב-Sentinel.",
            show_alert=True,
        )
        return

    if data == "task_refresh":
        # #3 / SPRINT11_DESIGN §1.3 — explicit refresh ALWAYS re-derives
        # (discards the cache; the engine is re-consulted as source of truth).
        bot.answer_callback_query(call.id)
        _tb.handle_task_refresh(chat_id)
        return

    if data == "task_algo_panel":
        # #5 / DEC-006 — observation-only consolidated ALGO read-out card.
        # NOT a Task: no done/skip/note, never counted (Mark §2.3).
        bot.answer_callback_query(call.id)
        _tb.handle_algo_panel(chat_id)
        return

    if data == "myactions_refresh":
        # #9 / DEC-008 — re-read the SELECT-only audit surface.
        bot.answer_callback_query(call.id)
        _tb.handle_my_actions(chat_id)
        return

    if data.startswith("task_open|"):
        bot.answer_callback_query(call.id)
        _tb.handle_task_open(chat_id, data.split("|", 1)[1])
        return

    if data.startswith("task_done_confirm|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        try:
            idx = int(parts[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_task_done_confirm(chat_id, idx, parts[2] == "yes")
        return

    if data.startswith("task_skip_confirm|"):
        bot.answer_callback_query(call.id)
        parts = data.split("|")
        try:
            idx = int(parts[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_task_skip_confirm(chat_id, idx, parts[2] == "yes")
        return

    if data.startswith("task_done|"):
        bot.answer_callback_query(call.id)
        try:
            idx = int(data.split("|", 1)[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_task_done(chat_id, idx)
        return

    if data.startswith("task_skip|"):
        bot.answer_callback_query(call.id)
        try:
            idx = int(data.split("|", 1)[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_task_skip(chat_id, idx)
        return

    if data.startswith("task_note|"):
        bot.answer_callback_query(call.id)
        try:
            idx = int(data.split("|", 1)[1])
        except (ValueError, IndexError):
            bot.send_message(chat_id, "❌ בחירה לא תקינה.")
            return
        _tb.handle_task_note(chat_id, idx)
        return

    # ── Ratchet-up loosen confirmation (MARK_DAY3_GUARDRAILS U3/C3) ──────────
    if data.startswith("loosen_confirm|"):
        bot.answer_callback_query(call.id)
        approved = data.split("|", 1)[1] == "yes"
        _tb.finalize_pending_loosen(chat_id, approved)
        return

    # ── /clean defaulted-NO confirmation (Sprint-12 / Mark §2) ──────────────
    if data.startswith("clean_confirm|"):
        bot.answer_callback_query(call.id)
        approved = data.split("|", 1)[1] == "yes"
        _tb.finalize_pending_clean(chat_id, approved)
        return

    if data == "start_trail_flow":
        # Tap-only path: show inline symbol buttons instead of asking the
        # user to TYPE a trade number while scrolling a long message.
        # The typed-index path (action='select_trade_index') is kept as a
        # fallback for anyone still on the old flow, but is no longer the
        # primary interaction.
        if chat_id in user_state and user_state[chat_id].get('temp_positions'):
            positions = user_state[chat_id]['temp_positions']
            kb = _tb.build_stop_promote_keyboard(positions)
            bot.send_message(
                chat_id,
                f"{RTL}🎯 *קידום סטופ — בחר פוזיציה (לחיצה אחת):*",
                reply_markup=kb, parse_mode="Markdown",
            )
        else:
            # No cached positions — open the lightweight list directly
            # instead of forcing a heavy 'חדר מצב' re-run.
            _tb.handle_stop_promote_entry(chat_id)
        bot.answer_callback_query(call.id)

    elif data == "cancel_action":
        bot.send_message(chat_id, "❌ הפעולה בוטלה.", reply_markup=get_main_menu())
        if chat_id in user_state: del user_state[chat_id]
        bot.answer_callback_query(call.id)

    elif data.startswith("backfill_add|"):
        # Engagement Wave-3B B4 — C1-S1 callback to enter reason-collection
        # state. The next text from the founder is the verbatim reason
        # (§X4 honored at storage).
        from telegram_engagement import handle_backfill_add
        entry_ts = data.split("|", 1)[1]
        handle_backfill_add(chat_id, call.message.message_id, entry_ts)
        bot.answer_callback_query(call.id)

    elif data.startswith("backfill_skip|"):
        # Engagement Wave-3B B4 — C1-S1 deliberate-skip callback. Marks
        # the candidate as backfill_skipped=True without fabricating a
        # reason. Mark §3 honesty: silence stays labeled as silence.
        from telegram_engagement import handle_backfill_skip
        entry_ts = data.split("|", 1)[1]
        handle_backfill_skip(chat_id, call.message.message_id, entry_ts)
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
            # B3 (Meeting 21/05/2026 — UX U4 P1 closure): also record on
            # the Supabase audit_log so `/myactions` (telegram_audit_review)
            # surfaces this — log_risk_journal alone is a local JSON file
            # the audit-review reader does not see. Fail-open (the
            # audit_logger never raises) — never block the user's flow.
            audit_logger.log_action(
                supabase, audit_logger.ACTION_RISK_PCT_CHANGE,
                chat_id=chat_id,
                before={"risk_pct": curr_pct},
                after={"risk_pct": rec_pct},
                metadata={"action": "confirmed",
                          "direction": "up" if rec_pct > curr_pct else "down_fast",
                          "nav": nav},
            )
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
                # Phase B3 — guard the Add-On Supabase write against a
                # plan→confirm campaign re-resolution race. The /addon plan
                # persisted the campaign_id of the exact open-position row the
                # user reviewed (telegram_bot.py addon_pending state). Three
                # cases:
                #   (2a) stored cid present: re-resolve to detect the race.
                #        resolved == planned  -> proceed exactly as pre-B3.
                #        resolved != planned  -> HARDENED: refuse, zero write.
                #   (2c) stored cid absent/None (legacy/older in-flight
                #        pending): fall back to re-resolution and proceed
                #        exactly as pre-B3 (byte-identical legacy path).
                planned_cid = pending.get("campaign_id")
                resolved_cid = repo.get_open_campaign_for_symbol(supabase, sym)
                if planned_cid is not None:
                    if resolved_cid != planned_cid:
                        # HARDENED race refusal: the open position for this
                        # symbol changed since the user planned the add-on.
                        # No Supabase write of any kind; clear pending exactly
                        # as the existing cancel/decline path does.
                        if chat_id in user_state:
                            del user_state[chat_id]
                        # Sprint-27 W3 (UX P1-3) — humanized wording ONLY. The
                        # zero-write protective behavior is UNCHANGED (no
                        # Supabase write, pending cleared, return). Reframed as
                        # the system protecting the money (not a rejection) and
                        # says explicitly WHAT changed — still 100% honest, no
                        # false reassurance.
                        bot.send_message(
                            chat_id,
                            f"{RTL}🛡️ *עצרתי את החיזוק — {sym}*\n"
                            f"{RTL}הפוזיציה הפתוחה ב-{sym} התחלפה מאז שתכננת "
                            f"(קמפיין אחר) — לא כתבתי כלום, כדי להגן על הכסף שלך.\n"
                            f"{RTL}הרץ ‎/addon‎ מחדש על המצב הנוכחי.",
                            reply_markup=get_main_menu(),
                            parse_mode="Markdown",
                        )
                        return
                    cid = planned_cid
                else:
                    cid = resolved_cid
                if cid:
                    repo.update_management_notes(supabase, cid, note)
                    # Mark addon fields (requires migration 001_addon_phase2.sql)
                    try:
                        _tid = repo.get_latest_buy_trade_id(supabase, sym, cid)
                        if _tid:
                            _seq_res = supabase.table("trades").select("trade_id").eq("campaign_id", cid).eq("is_addon", True).execute()
                            _seq = len(_seq_res.data or []) + 1
                            repo.update_addon_record(supabase, _tid, cid, _seq)
                    except Exception:
                        pass  # expected until migration 001_addon_phase2.sql is applied
                else:
                    bot.send_message(
                        chat_id,
                        f"{RTL}⚠️ *Add-On נרשם אך לא נמצא קמפיין פתוח ל-{sym}*\nוודא ידנית ב-management\\_notes.",
                        parse_mode="Markdown",
                    )
            except Exception as exc:
                bot.send_message(
                    chat_id,
                    f"{RTL}⚠️ *שגיאה בשמירת Add-On ל-Supabase*\n`{type(exc).__name__}: {exc}`\nוודא ידנית.",
                    parse_mode="Markdown",
                )
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
