import os, telebot, json, threading, subprocess
import pandas as pd
from telebot import types
from dotenv import load_dotenv
from datetime import datetime
import engine_core as ec
import telegram_formatters as tf
import adaptive_risk_engine as are
import addon_risk_engine as addon_eng
import supabase_repository as repo
import task_engine as te
import task_state as ts
import setup_performance as sp
from bot_core import bot, supabase, user_state, RTL, ADMIN_ID, TOKEN
from bot_helpers import (_bot_log, _read_last_log_lines, _write_runner_decision,
                         get_account_settings, get_nav_and_risk,
                         _DEV_LOG_FILES, _BOT_LOG_FILE, _BOT_LOG_MAX_LINES, _RM_STATE_FILE)
from telegram_menus import (get_main_menu, get_developer_menu, get_portfolio_menu,
                             get_analysis_menu, get_journal_menu,
                             get_rating_keyboard, get_setup_keyboard)
from ibkr_sync_runner import (run_ibkr_sync, MANUAL_RESULT_FILE,
                               _REPORTS_DIR, _REPORTS_TO_KEEP, _CONFIG_PATH)
from telegram_devops import (_dev_sync_check, _dev_sync_record,
                              _run_manual_sync_thread, _process_uploaded_ibkr_xml,
                              get_ibkr_nav,
                              _DEV_STATE_FILE,
                              _DEV_SYNC_MAX_PER_DAY, _DEV_SYNC_COOLDOWN_HOURS,
                              dev_pin_session_active, dev_pin_activate_session,
                              dev_pin_validate, dev_pin_is_configured,
                              dev_pin_rate_limited, dev_pin_record_failure)

from bot_health import build_health_report as _build_health_report  # noqa: E402



from telegram_backlog import get_next_missing  # noqa: E402 — re-exported for telegram_callbacks lazy import

from telegram_portfolio import handle_drilldown, handle_market_regime, handle_portfolio_room  # noqa: E402 — re-exported for telegram_callbacks lazy import

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    chat_id = message.chat.id
    if user_state.get(chat_id, {}).get('action') != 'awaiting_ibkr_xml':
        return
    del user_state[chat_id]
    _process_uploaded_ibkr_xml(chat_id, message)


# Slash shortcuts (C1 from 2026-05-14 UX feedback — "יותר מדי לחיצות").
# Each maps to the canonical button text the existing dispatcher already
# handles, so this is a pure alias layer — no duplication of business logic.
_SLASH_SHORTCUTS = {
    "/p":     "📊 חדר מצב (פוזיציות)",   # portfolio room
    "/m":     "🌡️ משטר שוק וסיכונים",    # market regime
    "/j":     "/next",                    # journal next
    "/h":     "❓ עזרה",                  # help
    "/d":     "🛠️ מפתח",                 # developer menu
    "/r":     "/stats",                   # risk adherence stats
    "/t":     "📋 סקירת משימות",         # task review (2026-05-14 feature)
    "/s":     "/setup_stats",            # per-setup performance dashboard
    "/home":  "⬅️ חזרה לתפריט ראשי",     # back to main
}


@bot.message_handler(func=lambda m: True, content_types=['text', 'photo'])
def handle_all_messages(message):
    chat_id = message.chat.id
    text = message.text if message.text else ""

    # Slash shortcut → canonical button — applied before any other dispatch
    # so power users can /p, /m, /r, /j, /h, /d without navigating menus.
    if text in _SLASH_SHORTCUTS:
        text = _SLASH_SHORTCUTS[text]

    if text in ["ביטול", "cancel", "/cancel", "❌ ביטול"]:
        if chat_id in user_state: del user_state[chat_id]
        bot.send_message(chat_id, "❌ הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=get_main_menu())
        return

    # ── טיפול ב-state פעיל ─────────────────────────────────────────────
    active_state = user_state.get(chat_id, {})

    # Task Review manual-edit text input — must run BEFORE the dev PIN
    # branch so the user can type a numeric value without colliding with
    # other input modes.
    if active_state.get("action") == "task_edit_value":
        import telegram_tasks as _tasks
        _tasks.apply_manual_edit_value(chat_id, text, user_state)
        return

    if active_state.get("action") == "awaiting_dev_pin":
        del user_state[chat_id]
        if dev_pin_rate_limited(chat_id):
            bot.send_message(chat_id, f"{RTL}🔒 *יותר מדי ניסיונות — נסה שוב בעוד 5 דקות*", reply_markup=get_main_menu(), parse_mode="Markdown")
        elif dev_pin_validate(text):
            dev_pin_activate_session(chat_id)
            bot.send_message(chat_id, f"{RTL}✅ *PIN מאומת — פגישה פעילה ל-30 דקות*", parse_mode="Markdown")
            bot.send_message(chat_id, f"{RTL}🛠️ *תפריט מפתח — כלי פיתוח ודיבאג*", reply_markup=get_developer_menu(), parse_mode="Markdown")
        else:
            dev_pin_record_failure(chat_id)
            bot.send_message(chat_id, f"{RTL}⛔ *PIN שגוי — גישה נדחתה*", reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    if active_state.get("action") == "risk_reject_reason":
        reason = text.strip()
        rec_pct = active_state["rec_pct"]
        curr_pct = active_state["curr_pct"]
        account_settings = get_account_settings()
        nav, _, _ = get_nav_and_risk(account_settings)
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

    if text == "🛠️ מפתח":
        if dev_pin_is_configured() and not dev_pin_session_active(chat_id):
            user_state[chat_id] = {"action": "awaiting_dev_pin"}
            bot.send_message(chat_id, f"{RTL}🔐 *תפריט מפתח — דרוש PIN*\nהזן את ה-PIN:", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, f"{RTL}🛠️ *תפריט מפתח — כלי פיתוח ודיבאג*", reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    # ── Developer menu handlers ────────────────────────────────────────────────

    if text == "📡 IBKR Sync ידני":
        allowed, reason, state_dict = _dev_sync_check()
        if not allowed:
            bot.send_message(chat_id, f"{RTL}⛔ *Sync נחסם:*\n{RTL}{reason}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
            return
        _dev_sync_record(state_dict)
        bot.send_message(
            chat_id,
            f"{RTL}📡 *IBKR Manual Sync — מתחיל...*\n"
            f"{RTL}תקבל עדכון ב-Telegram כשהסנכרון יסתיים (עד ~3 דקות).",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )
        _bot_log(f"Manual IBKR sync triggered by {chat_id}")
        threading.Thread(target=_run_manual_sync_thread, args=(chat_id,), daemon=True).start()
        return

    if text == "📤 העלה דוח XML":
        user_state[chat_id] = {'action': 'awaiting_ibkr_xml'}
        bot.send_message(
            chat_id,
            f"{RTL}📤 *העלה דוח IBKR XML*\n"
            f"{RTL}שלח את קובץ ה-XML שהורדת מ-IBKR (Flex Query → Activity Flex Query → XML).\n\n"
            f"{RTL}לביטול שלח *ביטול*",
            reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown",
        )
        return

    if text == "📊 תוצאת Sync אחרון":
        try:
            if not os.path.exists(MANUAL_RESULT_FILE):
                bot.send_message(chat_id, f"{RTL}⚪ אין תוצאת סנכרון ידני שמורה.",
                                 reply_markup=get_developer_menu(), parse_mode="Markdown")
                return
            r = json.load(open(MANUAL_RESULT_FILE))
            status   = r.get("status", "?")
            message  = r.get("message", "—")
            nav      = r.get("nav")
            ts       = r.get("triggered_at", "—")[:19]
            emoji    = "✅" if status == "success" else ("🚨" if status == "fatal" else "⚠️")
            nav_line = f"\n{RTL}NAV: `${nav:,.0f}`" if nav else ""
            bot.send_message(
                chat_id,
                f"{RTL}{emoji} *תוצאת Sync אחרון*\n"
                f"{RTL}סטטוס: `{status}`\n"
                f"{RTL}הודעה: {message}{nav_line}\n"
                f"{RTL}בוצע: `{ts}`",
                reply_markup=get_developer_menu(), parse_mode="Markdown",
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה בקריאת תוצאה: {e}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "📋 לוגים":
        # Inline keyboard to choose service
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in _DEV_LOG_FILES:
            kb.add(types.InlineKeyboardButton(f"📋 {name}", callback_data=f"devlog|{name}"))
        bot.send_message(chat_id, f"{RTL}📋 *לוגים — בחר שירות:*",
                         reply_markup=kb, parse_mode="Markdown")
        return

    if text == "🔄 Git Pull + Deploy":
        bot.send_message(chat_id, f"{RTL}🔄 *Git Pull — מריץ...*",
                         reply_markup=get_developer_menu(), parse_mode="Markdown")
        _bot_log(f"Git pull triggered by {chat_id}")
        _TRIGGER_FILE = "/app/deploy_trigger"
        try:
            result = subprocess.run(
                ["git", "-C", "/app", "pull"],
                capture_output=True, text=True, timeout=60,
            )
            stdout = result.stdout.strip()[-800:] or "(ריק)"
            stderr = result.stderr.strip()[-400:] or ""
            rc     = result.returncode
            status_icon = "✅" if rc == 0 else "❌"
            msg = (
                f"{RTL}{status_icon} *Git Pull — {'הצליח' if rc == 0 else 'נכשל'} (rc={rc})*\n"
                f"{RTL}```\n{stdout}\n```"
            )
            if stderr:
                msg += f"\n{RTL}⚠️ stderr:\n```\n{stderr}\n```"
            if rc == 0:
                # Write deploy trigger — deploy_watcher.sh on the host picks this up
                # and runs: git pull && docker compose up -d --build
                try:
                    import time as _time
                    with open(_TRIGGER_FILE, "w") as _tf:
                        _tf.write(str(_time.time()))
                    msg += f"\n\n{RTL}🚀 *trigger נכתב* — deploy_watcher יאסוף ויפעיל docker compose תוך ~5 שניות"
                    _bot_log("Deploy trigger file written")
                except Exception as te:
                    msg += f"\n\n{RTL}⚠️ לא הצלחתי לכתוב trigger file: {te}\nהרץ ידנית: `docker compose up -d --build`"
            else:
                msg += f"\n\n{RTL}⚠️ Git pull נכשל — trigger לא נכתב. בדוק שגיאות למעלה."
            _bot_log(f"Git pull rc={rc}: {stdout[:200]}")
        except FileNotFoundError:
            msg = (
                f"{RTL}⚠️ *git לא מותקן בקונטיינר זה.*\n"
                f"{RTL}כדי לפרוס עדכון, הרץ על Orange Pi:\n"
                f"`cd ~/sentinel_trading && git pull && docker compose up -d --build`"
            )
        except subprocess.TimeoutExpired:
            msg = f"{RTL}⏳ *Git pull פג timeout (60s).*"
        except Exception as e:
            msg = f"❌ שגיאה: {e}"
        bot.send_message(chat_id, msg, reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "⚙️ הצג Config":
        try:
            cfg_paths = ["/app/sentinel_config.json", "sentinel_config.json"]
            cfg = None
            for p in cfg_paths:
                if os.path.exists(p):
                    cfg = json.load(open(p))
                    break
            if cfg is None:
                bot.send_message(chat_id, f"{RTL}⚠️ sentinel_config.json לא נמצא.",
                                 reply_markup=get_developer_menu(), parse_mode="Markdown")
                return
            # Mask any token-like values for safety
            safe_cfg = {}
            for k, v in cfg.items():
                if any(s in k.lower() for s in ("token", "key", "secret", "password")):
                    safe_cfg[k] = "***"
                else:
                    safe_cfg[k] = v
            cfg_text = json.dumps(safe_cfg, indent=2, ensure_ascii=False)
            bot.send_message(
                chat_id,
                f"{RTL}⚙️ *sentinel_config.json:*\n```\n{cfg_text[:3000]}\n```",
                reply_markup=get_developer_menu(), parse_mode="Markdown",
            )
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה: {e}",
                             reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "🏥 בריאות מערכת":
        return bot.send_message(chat_id, _build_health_report(),
                                reply_markup=get_developer_menu())

    if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]:
        help_txt = (
            f"{RTL}🛡️ *Sentinel — מדריך פקודות*\n"
            f"{RTL}───────────────\n"
            f"{RTL}⚡ *קיצורי דרך* (טייפ אחד):\n"
            f"{RTL}  `/p` — חדר מצב (פוזיציות)\n"
            f"{RTL}  `/m` — משטר שוק וסיכונים\n"
            f"{RTL}  `/r` — סטטיסטיקת ציות לסיכון\n"
            f"{RTL}  `/j` — יומן הבא (Backlog)\n"
            f"{RTL}  `/d` — תפריט מפתח\n"
            f"{RTL}  `/s` — ביצועי setup (VCP/EP/SWING breakdown)\n"
            f"{RTL}  `/h` — מדריך זה\n"
            f"{RTL}  `/home` — חזרה לתפריט ראשי\n"
            f"{RTL}───────────────\n"
            f"{RTL}🔍 *פקודות מתקדמות:*\n"
            f"{RTL}  /portfolio — חדר מצב (גרסה ארוכה)\n"
            f"{RTL}  /trade SYMBOL — ניתוח עומק לפוזיציה\n"
            f"{RTL}  /mentor SYMBOL — Trend Template מלא\n"
            f"{RTL}  /analyze SYMBOL — ניתוח VCP מינרביני\n"
            f"{RTL}  /next — יומן (הבא)\n"
            f"{RTL}  /stats — סטטיסטיקת ציות להמלצות סיכון\n"
            f"{RTL}───────────────\n"
            f"{RTL}📂 *תפריטים* — לחיצה על כפתור:\n"
            f"{RTL}  📊 מצב תיק | 🔬 ניתוח | 📚 יומן | 🛠️ מפתח\n"
        )
        return bot.send_message(chat_id, help_txt, reply_markup=get_main_menu(), parse_mode="Markdown")

    if text in ["/stats", "📊 סטטיסטיקת ציות"]:
        stats = are.compute_adherence_stats()
        if not stats.get("ok"):
            bot.send_message(chat_id, f"⚪ {stats.get('message', 'שגיאה')}", parse_mode="Markdown")
            return
        last_str = " ".join(stats.get("last_actions", []))
        total      = stats['total_recommendations']
        evaluated  = stats['evaluated']
        pending    = max(0, total - evaluated)
        followed   = stats['followed']
        not_followed = stats['not_followed']
        msg = (
            f"{RTL}📊 *ציות להמלצות סיכון אדפטיבי*\n"
            f"{RTL}───────────────\n"
            f"{RTL}המערכת המליצה לשנות סיכון *{total}* פעמים מאז התחלת המעקב.\n"
            f"{RTL}מתוכן ענית (אישר/דחה) על *{evaluated}* בלבד; שאר *{pending}* פגו ללא תגובה.\n"
        )
        if evaluated > 0:
            msg += (
                f"{RTL}\n"
                f"{RTL}מתוך *{evaluated}* שהשבת:\n"
                f"{RTL}  ✅ אושרו: `{followed}`\n"
                f"{RTL}  ❌ נדחו: `{not_followed}`\n"
            )
            if stats["adherence_pct"] is not None:
                msg += f"{RTL}  → ציות: `{stats['adherence_pct']:.0f}%`\n"
        if last_str:
            msg += (
                f"{RTL}\n"
                f"{RTL}10 ההמלצות האחרונות:\n"
                f"{RTL}  {last_str}\n"
                f"{RTL}  _(⏳ ממתינה ל-/risk · ✅ אושר · ❌ נדחה)_"
            )
        return bot.send_message(chat_id, msg, parse_mode="Markdown")

    if text in ["/health", "🏥 בריאות מערכת"]:
        return bot.send_message(chat_id, _build_health_report())

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

    if text.startswith("/addon"):
        _handle_addon_command(chat_id, text)
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
            count = 0
            for t in repo.get_old_trades(supabase, thirty_days_ago):
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
                    repo.update_trade(supabase, t['trade_id'], upd)
                    count += 1
            bot.send_message(chat_id, f"✅ ארכיון נקי! {count} עסקאות ישנות טופלו בהצלחה.", parse_mode="Markdown")
        except Exception as e:
            bot.send_message(chat_id, f"❌ שגיאה בניקוי הארכיון: {e}")
        return get_next_missing(chat_id)

    if text in ["❓ פקודות מערכת", "/help"]:
        return bot.send_message(chat_id, "🛡️ *מערכת הפיקוד (Sentinel Command)*\n\n/trade SYMBOL - צלילת עומק לפוזיציה\n/next - סריקת יומן\n/portfolio - חדר מצב\n/clean - מטאטא ארכיון (מוגן 30 יום)", parse_mode="Markdown")

    if text == "🌡️ משטר שוק וסיכונים":
        handle_market_regime(chat_id)
        return

    if text in ["📊 חדר מצב (פוזיציות)", "/portfolio"]:
        handle_portfolio_room(chat_id)
        return

    if text in ["📋 סקירת משימות", "/tasks"]:
        handle_tasks_review(chat_id)
        return

    if text in ["📊 ביצועי Setup", "/setup_stats"]:
        try:
            trades = repo.get_all_trades(supabase)
            df = pd.DataFrame(trades)
            if df.empty:
                bot.send_message(chat_id, f"{RTL}📊 אין נתונים להצגה.",
                                 reply_markup=get_main_menu(), parse_mode="Markdown")
                return
            closed = are.compute_closed_campaigns(df)
            breakdown = sp.compute_setup_breakdown(closed)
            text_out = sp.render_breakdown(breakdown)
            bot.send_message(chat_id, text_out,
                             reply_markup=get_main_menu(), parse_mode="Markdown")
        except Exception as _e:
            bot.send_message(chat_id, f"{RTL}❌ שגיאה: `{_e}`",
                             reply_markup=get_main_menu(), parse_mode="Markdown")
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

        elif action == 'tighten_stop':
            try:
                new_sl = float(text)
                sym_ts  = state.get('sym', '')
                cid_ts  = state.get('campaign_id', '')
                if cid_ts:
                    repo.update_stop_for_campaign(supabase, cid_ts, new_sl)
                    bot.send_message(chat_id, f"{RTL}🔒 *סטופ עודכן — {sym_ts}*\nסטופ חדש: `${new_sl:.2f}`", reply_markup=get_main_menu(), parse_mode="Markdown")
                else:
                    bot.send_message(chat_id, "❌ תקלת מערכת: לא נמצא campaign_id.")
                del user_state[chat_id]
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר (למשל 150.50).")
            return

        elif action == 'initial_stop':
            try:
                new_sl = float(text)
                trade_id = state.get('t_id')
                if trade_id:
                    repo.update_trade(supabase, trade_id, {"initial_stop": new_sl, "stop_loss": new_sl})
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
                    repo.update_stop_for_campaign(supabase, cid, new_sl)
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
            repo.update_trade(supabase, t_id, {"image_url": text.strip()})
            bot.send_message(chat_id, "✅ תמונה נשמרה.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

        if action == 'management_notes' and t_id:
            if message.content_type != 'text':
                bot.send_message(chat_id, "🚨 שגיאה: יש לשלוח הערת טקסט בלבד.", parse_mode="Markdown")
                return
            repo.update_trade(supabase, t_id, {"management_notes": text.strip()})
            bot.send_message(chat_id, "✅ תובנות הניהול נשמרו ביומן המערכת.", parse_mode="Markdown")
            del user_state[chat_id]
            get_next_missing(chat_id)
            return

    bot.send_message(chat_id, "🎯 *Sentinel Standby*\nמערכת מוכנה לפעולה. בחר מהתפריט למטה:", reply_markup=get_main_menu(), parse_mode="Markdown")


def _handle_addon_command(chat_id: int, text: str):
    """
    /addon SYMBOL [entry] [stop] [qty] [type]
    Examples:
      /addon CAT               → interactive: asks for entry/stop
      /addon CAT 910 895       → auto-sizes, tactical
      /addon CAT 910 895 3     → specific qty, tactical
      /addon CAT 910 895 3 campaign → specific qty, campaign add
    """
    parts = text.strip().split()
    if len(parts) < 2:
        bot.send_message(
            chat_id,
            f"{RTL}📌 *Add-On Planner*\n\n"
            f"{RTL}שימוש: `/addon SYMBOL כניסה סטופ [כמות] [סוג]`\n"
            f"{RTL}דוגמה: `/addon CAT 910 895 3 tactical`\n\n"
            f"{RTL}סוגים: `tactical` | `campaign` | `rebuild`\n"
            f"{RTL}ללא כמות — המערכת תחשב אוטומטית.",
            parse_mode="Markdown",
        )
        return

    symbol = parts[1].upper()
    loading = bot.send_message(chat_id, f"⏳ בודק נתוני חיזוק עבור *{symbol}*...", parse_mode="Markdown")

    try:
        # Parse optional args
        add_entry = float(parts[2]) if len(parts) > 2 else None
        add_stop  = float(parts[3]) if len(parts) > 3 else None
        qty_arg   = int(parts[4])   if len(parts) > 4 else None
        type_arg  = parts[5].lower() if len(parts) > 5 else "tactical"

        add_type_map = {
            "campaign": addon_eng.ADDON_CAMPAIGN,
            "tactical":  addon_eng.ADDON_TACTICAL,
            "rebuild":   addon_eng.ADDON_REBUILD,
        }
        add_type = add_type_map.get(type_arg, addon_eng.ADDON_TACTICAL)

        # Load open position for symbol
        res = supabase.table("trades").select("*").execute()
        df  = pd.DataFrame(res.data)
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"] or pos_res["data"].empty:
            try: bot.delete_message(chat_id, loading.message_id)
            except: pass
            bot.send_message(chat_id, f"❌ אין פוזיציה פתוחה עבור {symbol}.")
            return

        open_pos = pos_res["data"]
        sym_rows = open_pos[open_pos["symbol"].str.upper() == symbol]
        if sym_rows.empty:
            try: bot.delete_message(chat_id, loading.message_id)
            except: pass
            bot.send_message(chat_id, f"❌ אין פוזיציה פתוחה עבור {symbol}.")
            return

        row = sym_rows.iloc[0]
        curr_price = ec.get_live_price(symbol) or float(row["price"])

        lot_state = addon_eng.compute_campaign_lot_state(
            base_price       = float(row["base_price"]),
            base_qty         = float(row["base_qty"]),
            current_qty      = float(row["quantity"]),
            stop_loss        = float(row["stop_loss"]) if float(row.get("stop_loss", 0)) > 0 else float(row["base_price"]),
            initial_stop     = float(row["initial_stop"]) if float(row.get("initial_stop", 0)) > 0 else 0,
            realized_pnl_usd = float(row.get("realized_pnl", 0)),
            current_price    = curr_price,
            setup_type       = str(row.get("setup_type", "EP")),
        )

        # Gather market features from engine_core
        market_features = None
        try:
            hist = ec.get_cached_history(symbol, "6mo", "1d")
            feats = ec.evaluate_position_engine(
                symbol=symbol, entry_price=float(row["base_price"]),
                entry_date_str=str(row.get("entry_date", "")),
                current_stop=float(row.get("stop_loss", 0)),
                setup_type=str(row.get("setup_type", "EP")),
                mgt_state="full_position", weight_pct=5.0,
                total_r=lot_state.get("total_r") or 0,
                target_risk_usd=28, actual_risk_usd=lot_state["original_risk_usd"],
                spy_hist=ec.get_cached_history("SPY", "6mo", "1d"),
            )
            if feats.get("ok"):
                f = feats["data"].get("features", {})
                market_features = {
                    "ext10":          f.get("ext10", 0),
                    "ext20":          f.get("ext20", 0),
                    "close_below_ma20": f.get("close_below_ma20", False),
                    "regime_ok":      True,
                    "rs_spy_ok":      f.get("rs_pct_spy", 0) > 0,
                }
        except Exception:
            pass

        # If no entry/stop provided, just show eligibility status
        if add_entry is None or add_stop is None:
            elig = addon_eng.check_addon_eligibility(lot_state, market_features=market_features)
            status_emoji = {"APPROVED": "✅ מאושר לתכנון", "WATCH": "👁 צפייה", "BLOCKED": "🚫 חסום", "MANUAL_REVIEW_REQUIRED": "⚠️ בדיקה ידנית"}.get(elig["status"], elig["status"])
            msg = (
                f"{RTL}📌 *Add-On Eligibility — {symbol}*\n"
                f"{RTL}סטטוס: *{status_emoji}*\n\n"
                f"{RTL}Open R: `{lot_state.get('open_r', 'N/A')}R` | רווח נעול: `${lot_state['locked_profit_usd']:.0f}`\n"
                f"{RTL}סיכון פתוח: `${lot_state['open_risk_usd']:.0f}` | סיכון מקורי: `${lot_state['original_risk_usd']:.0f}`\n\n"
            )
            for r in elig["reasons"][:3]: msg += f"{RTL}  {r}\n"
            for b in elig["blocks"][:3]:  msg += f"{RTL}  {b}\n"
            for w in elig["warnings"][:2]: msg += f"{RTL}  {w}\n"
            msg += f"\n{RTL}לתכנון מלא: `/addon {symbol} כניסה סטופ [כמות]`"
            try: bot.delete_message(chat_id, loading.message_id)
            except: pass
            bot.send_message(chat_id, msg, parse_mode="Markdown")
            return

        # Full plan
        plan = addon_eng.compute_addon_plan(
            lot_state=lot_state,
            add_entry=add_entry,
            add_stop=add_stop,
            add_type=add_type,
            quantity=qty_arg,
            market_features=market_features,
        )
        card = tf.fmt_addon_card(plan, symbol=symbol)
        try: bot.delete_message(chat_id, loading.message_id)
        except: pass

        # Store plan for confirmation step
        import json as _json
        user_state[chat_id] = {
            "action":   "addon_pending",
            "symbol":   symbol,
            "entry":    add_entry,
            "stop":     add_stop,
            "qty":      plan.get("proposed_qty", qty_arg),
            "add_type": type_arg,
        }

        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton(
                "✅ אשר כניסה",
                callback_data=f"addon_confirm|YES|{symbol}|{add_entry}|{add_stop}|{plan.get('proposed_qty', qty_arg or 0)}",
            ),
            telebot.types.InlineKeyboardButton("❌ בטל", callback_data="cancel_action"),
        )
        bot.send_message(chat_id, card, parse_mode="Markdown", reply_markup=markup)

    except (IndexError, ValueError) as e:
        try: bot.delete_message(chat_id, loading.message_id)
        except: pass
        bot.send_message(
            chat_id,
            f"❌ פורמט שגוי: `{e}`\nשימוש: `/addon {symbol} כניסה סטופ [כמות] [סוג]`",
            parse_mode="Markdown",
        )
    except Exception as e:
        try: bot.delete_message(chat_id, loading.message_id)
        except: pass
        bot.send_message(chat_id, f"❌ שגיאת מערכת: {e}")


import telegram_callbacks  # registers @bot.callback_query_handler

if __name__ == "__main__":
    _bot_log("Sentinel Telegram Bot — started")
    if ADMIN_ID:
        try:
            bot.send_message(
                ADMIN_ID,
                "🛡️ *Sentinel Monitoring: ONLINE*\n"
                "v3.7 — תפריט מפתח פעיל (🛠️ מפתח).",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )
        except:
            pass
    bot.infinity_polling()
