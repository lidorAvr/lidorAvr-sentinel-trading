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
import audit_logger
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

from telegram_stop_promote import (handle_stop_promote_entry,  # noqa: E402 — re-exported for telegram_callbacks lazy import
                                    handle_stop_promote_pick,
                                    build_stop_promote_keyboard,
                                    guard_stop_write,
                                    get_campaign_current_stop,
                                    finalize_pending_loosen)

from telegram_tasks import (handle_open_tasks_entry,  # noqa: E402 — re-exported for telegram_callbacks lazy import
                            handle_task_open,
                            handle_task_refresh,
                            handle_algo_panel,
                            handle_task_done,
                            handle_task_done_confirm,
                            handle_task_skip,
                            handle_task_skip_confirm,
                            handle_task_skip_reason,
                            handle_task_note,
                            handle_task_add_note)

from telegram_audit_review import handle_my_actions  # noqa: E402 — re-exported for telegram_callbacks lazy import
from telegram_engagement import handle_gate_receipt, handle_backfill_prompt, handle_backfill_collect_reason  # noqa: E402 — engagement Wave-3B B3+B4

from telegram_clean_gate import (handle_clean_entry,  # noqa: E402 — re-exported for telegram_callbacks lazy import
                                 finalize_pending_clean)

def _send_probe_chunks(chat_id, text):
    """Loss-free, plain-text (NO parse_mode) multi-send for the dev-menu Probe.

    Sprint-23 / DEC-20260516-020 fix for Telegram `Bad Request: message is
    too long` (the probe's ~20-campaign × 2-window output exceeds the 4096
    hard cap). This is the ONLY production caller path that splits
    `period_data_probe.build_probe_report()`'s string; the probe itself is
    byte-identical and still NEVER sends/persists.

    Per Mark's BINDING rulings (docs/teams/MARK_SPRINT23_RULINGS.md):

    * Ruling 1 — chunk, NEVER truncate: every real campaign row is sent;
      no "show first N", no per-window cap, no head/tail trimming.
    * Ruling 3 — plain-text invariant: NO `parse_mode` on ANY part (a
      `campaign_id` `_` under Markdown would italicise / Telegram-400).
      `telegram_portfolio._send_long_message` is NOT reused verbatim
      (it forces `parse_mode="Markdown"`); only its proven SHAPE is mirrored.
    * Ruling 4 — split boundaries: (1) short input (<= LIMIT) → ONE send,
      byte-identical to the pre-Sprint-23 behaviour; (2) else split first
      at the weekly/monthly glue `"\n\n" + _RTL` (period_data_probe.py:328);
      (3) within a window still over budget, split ONLY at `\n` (never
      mid-line / mid-campaign); a single source line > LIMIT is emitted
      whole in its own part (loss-free dominates the size target).
      Every part is independently re-prefixed with the RTL marker
      (U+200F, == bot_core.RTL == period_data_probe._RTL) so each bubble
      renders RTL-correct on its own.
    * Ruling 4 — `reply_markup=get_developer_menu()` on the LAST part ONLY.
    * Mirrors `telegram_portfolio._send_long_message`'s per-part try/except
      shape so one failed part cannot suppress the rest.
    """
    LIMIT = 3900  # ⟨MARK:3900⟩ — mirrors the proven telegram_portfolio.py:23
                  # budget; comfortably under Telegram's 4096 hard cap.

    # Step 1 — short-circuit: byte-for-byte the pre-Sprint-23 single send.
    if len(text) <= LIMIT:
        return bot.send_message(chat_id, text,
                                reply_markup=get_developer_menu())

    import period_data_probe
    _RTL = period_data_probe._RTL  # U+200F — == bot_core.RTL (parity proven)

    # Step 2 — split first at the weekly/monthly glue "\n\n" + _RTL
    # (period_data_probe.py:328). Each resulting segment keeps its own
    # leading _RTL (weekly's head _RTL; monthly's _RTL right after "\n\n").
    glue = "\n\n" + _RTL
    if glue in text:
        head, tail = text.split(glue, 1)
        segments = [head, _RTL + tail]
    else:
        segments = [text]

    # Step 3 — within a segment still over budget, split ONLY at a "\n"
    # line boundary (never mid-line / mid-campaign). The cut is taken
    # AFTER the newline so the "\n" itself is retained at the END of the
    # preceding part — the split is byte loss-free: concatenating the
    # parts (minus the injected per-part _RTL prefixes) reproduces the
    # segment exactly. Each continuation part is re-prefixed with _RTL so
    # every bubble renders RTL on its own (the ONLY injected bytes).
    parts = []
    for seg in segments:
        while len(seg) > LIMIT:
            nl = seg.rfind('\n', 0, LIMIT)
            if nl == -1:
                # No line boundary within budget: a single source line
                # exceeds LIMIT. Loss-free dominates the size target —
                # emit up to the next "\n" (the whole oversized line)
                # WHOLE in its own part; never drop / truncate it.
                nl = seg.find('\n')
                if nl == -1:
                    parts.append(seg)
                    seg = ""
                    break
            split_idx = nl + 1            # keep the "\n" with this part
            parts.append(seg[:split_idx])
            rest = seg[split_idx:]
            seg = rest if rest.startswith(_RTL) else _RTL + rest
        if seg:
            parts.append(seg)

    # Step 4 — send each part plain-text (NO parse_mode); reply_markup on
    # the LAST part ONLY; per-part try/except (mirrors _send_long_message).
    last = None
    for i, part in enumerate(parts):
        try:
            if i == len(parts) - 1:
                last = bot.send_message(chat_id, part,
                                        reply_markup=get_developer_menu())
            else:
                last = bot.send_message(chat_id, part)
        except Exception as e:
            print(f"Error sending Probe part {i}: {e}")
    return last


def _require_active_dev_session(chat_id) -> bool:
    """Sprint-25 C1 (Security S-1/S-2/S-3) — fail-CLOSED privileged-action gate.

    The dev menu is a *persistent* ReplyKeyboardMarkup of literal Hebrew
    strings. Before C1 the ONLY dev-PIN check was on the `🛠️ מפתח`
    menu-OPEN button (the gate at telegram_bot.py — the
    `dev_pin_is_configured()`/`dev_pin_session_active(chat_id)` check).
    Every privileged dev handler then dispatched purely on `text ==
    "<button>"` with NO session re-check, so the admin could type/tap a
    button (or use a still-visible keyboard from an EXPIRED session) and
    reach `git pull` (subprocess), IBKR sync, the XML upload→Supabase
    insert + NAV overwrite, config/log dump, or on-demand reports with
    NO active 30-minute PIN session (S-1). With `DEV_PIN` unset,
    `dev_pin_is_configured()` is False and the old menu-open gate
    short-circuited OPEN (S-2, fail-open); the XML write path inherited
    this (S-3).

    This shared guard, called at the TOP of every privileged dev handler,
    re-asserts an active PIN session and is **fail-CLOSED**: an
    unconfigured (empty/unset) `DEV_PIN` DENIES every privileged action.
    It performs the action ONLY when a valid, non-expired session exists.
    On refusal it replies in the existing Hebrew refusal style and
    returns False — the caller must `return` without performing the
    action. It does NOT weaken the constant-time PIN compare or the
    session expiry (telegram_devops); it only ENFORCES them at the
    privileged call sites. It does NOT change the outer admin (chat-id)
    gate in telegram_bot_secure_runner.py, which stays the outer check.
    """
    if not dev_pin_is_configured():
        # S-2: an unconfigured dev-PIN must DENY (never open) — production
        # with no DEV_PIN is now safe-by-default.
        bot.send_message(
            chat_id,
            f"{RTL}⛔ *גישת מפתח חסומה — DEV_PIN לא מוגדר*\n"
            f"{RTL}פעולות מפתח מושבתות עד שמוגדר PIN.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
        return False
    if not dev_pin_session_active(chat_id):
        # S-1/S-3: no active (or expired) PIN session — refuse and route
        # back to PIN entry, mirroring the menu-open gate's behaviour.
        user_state[chat_id] = {"action": "awaiting_dev_pin"}
        # Sprint-27 W3 (UX P1-2) — humanized wording ONLY. The fail-closed
        # security behavior is UNCHANGED (still routes back to PIN entry, still
        # returns False, no TTL/compare touched): warmer + still 100% honest —
        # it states plainly the session is not active (no false reassurance)
        # and frames the re-entry as a quick resume, not a rejection.
        bot.send_message(
            chat_id,
            f"{RTL}🔐 *צריך PIN פעיל לפעולת מפתח*\n"
            f"{RTL}הפגישה שלך פגה (תוקף 30 דק' לאבטחתך) — לא בוצעה שום פעולה.\n"
            f"{RTL}הזן את ה-PIN ונמשיך מכאן:",
            parse_mode="Markdown",
        )
        return False
    return True


@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    chat_id = message.chat.id
    if user_state.get(chat_id, {}).get('action') != 'awaiting_ibkr_xml':
        return
    # Sprint-25 C1 (Security S-3): the XML upload writes sentinel_config.json
    # NAV + inserts trades into Supabase. Re-assert an active dev-PIN session
    # at the actual write entry (defence-in-depth: even though arming
    # `awaiting_ibkr_xml` now requires the gated XML handler, a stale/expired
    # session must not be able to complete a real-money NAV/Supabase write).
    if not _require_active_dev_session(chat_id):
        del user_state[chat_id]
        return
    del user_state[chat_id]
    _process_uploaded_ibkr_xml(chat_id, message)


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

    if active_state.get("action") == "task_skip_reason":
        # P0 Open-Task skip: typed reason is mandatory (spec §3 / G8).
        handle_task_skip_reason(chat_id, text)
        return

    if active_state.get("action") == "task_add_note":
        handle_task_add_note(chat_id, text)
        return

    if active_state.get("action") == "backfill_collect_reason":
        # Engagement Wave-3B B4 — C1-S1 reason capture. §X4 verbatim
        # storage; render-safe via render_journal_text in the handler.
        handle_backfill_collect_reason(chat_id, text)
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
        # B3 (Meeting 21/05/2026 — UX U4 P1 closure) + Engagement Wave-3A
        # U4 full-closure: mirror the rejection to Supabase audit_log via the
        # DISTINCT ACTION_RISK_REJECT constant (not ACTION_RISK_PCT_CHANGE)
        # so `/myactions` renders the dismissal with the operator's reason
        # text rather than the misleading "0.60%→0.60%" line a same-pct row
        # would produce. Fail-open: audit_logger never raises.
        audit_logger.log_action(
            supabase, audit_logger.ACTION_RISK_REJECT,
            chat_id=chat_id,
            before={"risk_pct": curr_pct},
            after={"risk_pct": curr_pct},  # no actual change — rejected
            metadata={"recommended_pct": rec_pct,
                      "direction": "up" if rec_pct > curr_pct else "down_fast",
                      "reason": reason,
                      "nav": nav},
        )
        del user_state[chat_id]
        # S-ENGAGE-1 closure: escape Markdown specials in the operator-typed
        # reason before rendering inside the Markdown envelope. Bytes on
        # disk stay verbatim (§X4); escape lives at the render boundary.
        from telegram_formatters import render_journal_text
        _reason_render = render_journal_text(reason)
        bot.send_message(
            chat_id,
            f"{RTL}📝 *הדחייה נרשמה ביומן הסיכון*\n{RTL}המלצה `{rec_pct:.2f}%` נדחתה.\n{RTL}סיבה: _{_reason_render}_",
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
        if not dev_pin_is_configured():
            # Sprint-25 C1 (Security S-2) — fail-CLOSED: an unconfigured
            # (unset/empty) DEV_PIN must DENY the dev menu, never open it.
            # Before C1 this branch fell through to `else` and opened the
            # menu with ZERO PIN. CI sets DEV_PIN=0000 so configured
            # paths/tests are unaffected; production with no DEV_PIN is
            # now safe-by-default.
            bot.send_message(
                chat_id,
                f"{RTL}⛔ *תפריט מפתח חסום — DEV_PIN לא מוגדר*\n"
                f"{RTL}פעולות מפתח מושבתות עד שמוגדר PIN.",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )
        elif not dev_pin_session_active(chat_id):
            user_state[chat_id] = {"action": "awaiting_dev_pin"}
            bot.send_message(chat_id, f"{RTL}🔐 *תפריט מפתח — דרוש PIN*\nהזן את ה-PIN:", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, f"{RTL}🛠️ *תפריט מפתח — כלי פיתוח ודיבאג*", reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    # ── Developer menu handlers ────────────────────────────────────────────────

    if text == "📡 IBKR Sync ידני":
        if not _require_active_dev_session(chat_id):
            return
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
        if not _require_active_dev_session(chat_id):
            return
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
        if not _require_active_dev_session(chat_id):
            return
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
        if not _require_active_dev_session(chat_id):
            return
        # Inline keyboard to choose service
        kb = types.InlineKeyboardMarkup(row_width=1)
        for name in _DEV_LOG_FILES:
            kb.add(types.InlineKeyboardButton(f"📋 {name}", callback_data=f"devlog|{name}"))
        bot.send_message(chat_id, f"{RTL}📋 *לוגים — בחר שירות:*",
                         reply_markup=kb, parse_mode="Markdown")
        return

    if text == "🔄 Git Pull + Deploy":
        if not _require_active_dev_session(chat_id):
            return
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
                    msg += (
                        f"\n\n{RTL}ℹ️ git נמשך *בתוך הקונטיינר בלבד* — זה לא deploy."
                        f"\n{RTL}deploy-watcher אינו מותקן (DEC-20260515-010)."
                        f"\n{RTL}כדי לפרוס בפועל, הרץ ב-Orange Pi:\n"
                        f"`cd ~/sentinel_trading && ./deploy.sh`"
                    )
                    _bot_log("Deploy trigger file written (no watcher installed — informational)")
                except Exception as te:
                    msg += f"\n\n{RTL}⚠️ trigger לא נכתב: {te}\nהרץ ב-Orange Pi: `cd ~/sentinel_trading && ./deploy.sh`"
            else:
                msg += f"\n\n{RTL}⚠️ Git pull נכשל — trigger לא נכתב. בדוק שגיאות למעלה."
            _bot_log(f"Git pull rc={rc}: {stdout[:200]}")
        except FileNotFoundError:
            msg = (
                f"{RTL}⚠️ *git לא מותקן בקונטיינר זה.*\n"
                f"{RTL}כדי לפרוס עדכון, הרץ על Orange Pi:\n"
                f"`cd ~/sentinel_trading && ./deploy.sh`"
            )
        except subprocess.TimeoutExpired:
            msg = f"{RTL}⏳ *Git pull פג timeout (60s).*"
        except Exception as e:
            msg = f"❌ שגיאה: {e}"
        bot.send_message(chat_id, msg, reply_markup=get_developer_menu(), parse_mode="Markdown")
        return

    if text == "⚙️ הצג Config":
        if not _require_active_dev_session(chat_id):
            return
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
        if not _require_active_dev_session(chat_id):
            return
        return bot.send_message(chat_id, _build_health_report(),
                                reply_markup=get_developer_menu())

    # ── Sprint-21 WS-A — live PURE READ-ONLY data-delivery probe ────────────
    # Re-runs the EXACT scheduler `_fetch_trades_df` for BOTH on-demand
    # windows read-only and reports, honestly, what the real pipeline yields
    # (distinguishing "input ריק/כשל" from "0 closes"; no secrets — only the
    # JWT role word). NO write/snap_save/state-mutation (AST-proven). Admin-
    # gated by construction: this branch is in the developer-menu region,
    # reachable ONLY inside an authenticated dev-PIN session (the EXISTING
    # gate at telegram_bot.py:241-247 — the `🛠️ מפתח` menu-open
    # `dev_pin_is_configured()`/`dev_pin_session_active(chat_id)` check;
    # Sprint-25 A2/S-4 corrected anchor — the old "147-153" cite was
    # WRONG, those lines are the `_send_probe_chunks` message-split loop,
    # not a gate; unchanged, not bypassed). Mirrors the synchronous
    # `🏥 בריאות מערכת` handler exactly.
    if text == "🔬 בדיקת נתוני תקופה (Probe)":
        if not _require_active_dev_session(chat_id):
            return
        try:
            import period_data_probe
            txt = period_data_probe.build_probe_report()
            return _send_probe_chunks(chat_id, txt)
        except Exception as e:
            return bot.send_message(
                chat_id, f"{RTL}❌ שגיאת Probe: `{str(e)[:300]}`",
                reply_markup=get_developer_menu(), parse_mode="Markdown")

    # ── Sprint-17 Scope item B — on-demand report (dev/testing only) ─────────
    # Generates the weekly/monthly report for the LAST COMPLETE period using
    # the SAME scheduler period logic + render/deliver path (Sprint-16 graceful
    # degradation intact). HARD: never snap_save into the real snapshot store,
    # never touch the scheduler period-dedup (report_on_demand is read-only
    # w.r.t. that state). Admin-gated by this dev-menu/PIN path already.
    if text in ("📈 דוח שבועי עכשיו", "📆 דוח חודשי עכשיו"):
        if not _require_active_dev_session(chat_id):
            return
        period_type = "weekly" if text == "📈 דוח שבועי עכשיו" else "monthly"
        kind_he = "שבועי" if period_type == "weekly" else "חודשי"
        bot.send_message(
            chat_id,
            f"{RTL}📊 *מפיק דוח {kind_he} (On-Demand) — לתקופה השלמה האחרונה...*\n"
            f"{RTL}ריצת בדיקה בלבד — לא נשמר ל-snapshot ולא משפיע על הדוח המתוזמן.",
            reply_markup=get_developer_menu(), parse_mode="Markdown",
        )
        _bot_log(f"On-demand {period_type} report triggered by {chat_id}")

        def _run_on_demand_report_thread(_pt, _kind, _cid):
            try:
                import report_on_demand
                # This thread runs in the telegram-bot process — pass ITS
                # working bot creds (bot_core TOKEN + the requesting admin
                # chat); the scheduler's TELEGRAM_TOKEN/TELEGRAM_CHAT_ID env
                # convention is not set in this container.
                res = report_on_demand.run_on_demand(
                    _pt, token=TOKEN, chat_id=str(_cid))
                if res.get("ok"):
                    deg = " (PDF דרדור — טקסט מלא נשלח)" if res.get("pdf_degraded") else ""
                    bot.send_message(
                        _cid,
                        f"{RTL}✅ *דוח {_kind} (On-Demand) נשלח*{deg}\n"
                        f"{RTL}תקופה: `{res.get('period_label', '—')}`\n"
                        f"{RTL}summary={res.get('summary_ok')} · pdf={res.get('pdf_ok')}",
                        reply_markup=get_developer_menu(), parse_mode="Markdown",
                    )
                else:
                    bot.send_message(
                        _cid,
                        f"{RTL}❌ *דוח {_kind} (On-Demand) נכשל*\n"
                        f"{RTL}שגיאה: `{str(res.get('error'))[:300]}`",
                        reply_markup=get_developer_menu(), parse_mode="Markdown",
                    )
            except Exception as e:
                bot.send_message(
                    _cid, f"{RTL}❌ שגיאה בדוח On-Demand: `{str(e)[:300]}`",
                    reply_markup=get_developer_menu(), parse_mode="Markdown",
                )

        threading.Thread(
            target=_run_on_demand_report_thread,
            args=(period_type, kind_he, chat_id), daemon=True,
        ).start()
        return

    # ── RISK-1c — admin-triggered at-entry-lock backfill ────────────────────
    # Two-step flow: this button shows the preview + inline confirm/cancel
    # keyboard; the actual run happens in the `risk1c|confirm` callback
    # registered in telegram_callbacks.py. Admin-gated through the existing
    # dev-PIN session check (`_require_active_dev_session`). All Supabase
    # mutations + per-row audit rows live inside `risk1c_backfill.run_backfill`;
    # this surface is thin presentation only. CLAUDE.md "do not rewrite
    # telegram_bot.py wholesale" — this is the minimum-possible touch.
    if text == "🔒 נעילה היסטורית (RISK-1c)":
        if not _require_active_dev_session(chat_id):
            return
        try:
            import risk1c_backfill as _r1c
            preview = _r1c.preview_missing_locks(supabase)
            preview_msg = _r1c.format_preview(preview)
        except Exception as e:
            bot.send_message(
                chat_id,
                f"{RTL}❌ *RISK-1c — שגיאה בהכנת preview:* `{str(e)[:200]}`",
                reply_markup=get_developer_menu(), parse_mode="Markdown")
            return

        # No rows to lock → no inline keyboard, just an honest "all clean"
        # message back into the dev menu. fetch_error → same shape (the
        # preview already disclosed it in the body).
        if preview.get("fetch_error") or preview.get("total", 0) == 0 \
                or preview.get("lockable_count", 0) == 0:
            return bot.send_message(
                chat_id, preview_msg,
                reply_markup=get_developer_menu(), parse_mode="Markdown")

        # Real preview → inline confirm/cancel. The callback IDs are scoped
        # under `risk1c|` so they cannot collide with other surfaces.
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ אשר ונעל",
                                       callback_data="risk1c|confirm"),
            types.InlineKeyboardButton("❌ ביטול",
                                       callback_data="risk1c|cancel"),
        )
        return bot.send_message(
            chat_id, preview_msg,
            reply_markup=kb, parse_mode="Markdown")

    if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]:
        help_txt = (
            f"{RTL}🛡️ *Sentinel — מדריך פקודות*\n"
            f"{RTL}───────────────\n"
            f"{RTL}📊 *מצב תיק* — פוזיציות ומשטר שוק\n"
            f"{RTL}🔬 *ניתוח* — סקירת מניה ו-Trend Template\n"
            f"{RTL}📚 *יומן* — מילוי יומן וארכיון\n"
            f"{RTL}───────────────\n"
            f"{RTL}/portfolio — חדר מצב\n"
            f"{RTL}/tasks — משימות פתוחות (Action-Items)\n"
            f"{RTL}/myactions — הפעולות שלי (יומן ביקורת)\n"
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

    if text in ["🔍 השלמת יומן — הפריט הבא", "🔍 סריקת יומן (Backlog)",
                "/next", "📚 ניהול יומן (Backlog)"]:
        return get_next_missing(chat_id)

    if text in ["🧹 ארכיון עסקאות (Legacy)", "/clean"]:
        # Sprint-12 / Mark §2 — `/clean` no longer writes on a single tap. It
        # runs a read-only dry-run preview and a defaulted-NO inline confirm
        # (reuses the proven guard_stop_write / finalize_pending_loosen
        # pattern). The bulk-write body is relocated BYTE-IDENTICAL behind the
        # gate in telegram_clean_gate.finalize_pending_clean. Additive routing
        # only (CLAUDE.md — no telegram_bot.py wholesale rewrite).
        handle_clean_entry(chat_id)
        return

    # Sprint-25 A2 (Arch F5) — removed a provably-UNREACHABLE duplicate
    # `/help` block here. The earlier handler at the top of this dispatcher
    # `if text in ["❓ עזרה", "❓ פקודות מערכת", "/help"]:` UNCONDITIONALLY
    # `return bot.send_message(...)` for ALL THREE of those literals; its
    # literal set is a strict SUPERSET of this block's `["❓ פקודות מערכת",
    # "/help"]`, and `text` is assigned exactly once at handler entry and
    # NEVER reassigned in between → control flow could never reach this
    # branch (it always returned earlier). It rendered a second, stale
    # help string that can never ship. Pure dead-code removal: no
    # behavior change (the live `/help` is the earlier block).

    if text == "🌡️ משטר שוק וסיכונים":
        handle_market_regime(chat_id)
        return

    if text in ["📊 חדר מצב (פוזיציות)", "/portfolio"]:
        handle_portfolio_room(chat_id)
        return

    if text in ["📋 משימות פתוחות", "/tasks"]:
        handle_open_tasks_entry(chat_id)
        return

    if text in ["🧾 הפעולות שלי", "/myactions"]:
        handle_my_actions(chat_id)
        return

    if text == "/gate_receipt":
        # Engagement Wave-3B B3 — C4-S1 Gate Receipt count-only Phase-1.
        # Slash-only (no menu button) — advanced pull surface; the
        # founder discovers it via the docs. Phase-2 (D11 dollar-value
        # saved) will graduate to a menu entry once symmetric framing
        # data is available.
        handle_gate_receipt(chat_id)
        return

    if text == "/backfill_prompt":
        # Engagement Wave-3B B4 — C1-S1 backfill prompt pull surface.
        # Finds the oldest null-reason rejection ≥14 days old and
        # invites the founder to add a verbatim reason (§X4) OR mark
        # it deliberately skipped. The corpus this builds is the raw
        # material for the day-60 Callback (C1-S2, Phase-3).
        handle_backfill_prompt(chat_id)
        return

    if text in ["🎯 קידום סטופ", "/promote"]:
        handle_stop_promote_entry(chat_id)
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
                    if guard_stop_write(chat_id, cid=cid_ts, sym=sym_ts,
                                        new_sl=new_sl,
                                        current_stop=get_campaign_current_stop(cid_ts),
                                        resume={'batch': False}):
                        return  # loosen — confirmation pending, do not write
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
                    # RISK-1b — forward-capture wizard lock. Idempotent + fail-soft:
                    # locks the at-entry price from the trade's existing broker-imported
                    # `price` field. No-op on already-locked / missing-row / anomalous-price.
                    # Never raises (logged via audit). Banner for unlocked rows arrives
                    # in RISK-1d's formatter.
                    repo.lock_entry_from_trade_price(supabase, trade_id, chat_id=chat_id)
                    bot.send_message(chat_id, f"🚀 *הסטופ ההתחלתי נשמר במערכת: ${new_sl:.2f}*", parse_mode="Markdown")
                del user_state[chat_id]
                get_next_missing(chat_id)
            except: bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר בלבד (למשל 150.50).")
            return

        elif action == 'input_new_sl':
            # NOTE: stop-write logic below is byte-identical to the legacy
            # flow (repo.update_stop_for_campaign). Only the post-write
            # navigation differs: batch flow re-opens the position list so
            # the user can promote the next stop without a heavy re-run.
            batch_mode = state.get('promote_batch', False)
            try:
                new_sl = float(text)
                trade = state['selected_trade']
                cid = trade.get('campaign_id')
                if cid:
                    if guard_stop_write(chat_id, cid=cid,
                                        sym=trade.get('symbol', ''),
                                        new_sl=new_sl,
                                        current_stop=trade.get('stop_loss'),
                                        resume={'batch': batch_mode}):
                        return  # loosen — confirmation pending, do not write
                    repo.update_stop_for_campaign(supabase, cid, new_sl)
                    if batch_mode:
                        bot.send_message(
                            chat_id,
                            f"{RTL}🚀 *הסטופ עודכן — {trade['symbol']}*\n"
                            f"{RTL}סטופ חדש: `${new_sl:.2f}` | פקודות הקנייה בקמפיין עודכנו.\n"
                            f"{RTL}בחר פוזיציה נוספת לקידום, או '❌ סגור':",
                            parse_mode="Markdown",
                        )
                    else:
                        bot.send_message(chat_id, f"🚀 *הסטופ עודכן בהצלחה!*\nנכס: `{trade['symbol']}`\nסטופ מעודכן ל: `${new_sl:.2f}`\nפקודות הקנייה בקמפיין עודכנו.", reply_markup=get_main_menu(), parse_mode="Markdown")
                else:
                    bot.send_message(chat_id, "❌ תקלת מערכת: לא נמצא מזהה קמפיין לעסקה זו.")
                    batch_mode = False
                if batch_mode and cid:
                    # Stay in the batch list: clear the per-pick action but
                    # keep temp_positions so the next tap works with no
                    # expiry and no heavy 'חדר מצב' re-run.
                    positions = state.get('temp_positions')
                    user_state[chat_id] = {'temp_positions': positions} if positions else {}
                    if positions:
                        bot.send_message(
                            chat_id,
                            f"{RTL}🎯 *קידום סטופ — בחר פוזיציה הבאה:*",
                            reply_markup=build_stop_promote_keyboard(positions),
                            parse_mode="Markdown",
                        )
                else:
                    del user_state[chat_id]
            except Exception:
                bot.send_message(chat_id, "❌ מחיר לא תקין. נא להזין מספר.")
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

        # Load open position for symbol.
        # Sprint-27 W4c (Arch S26-R1): route the lone residual raw
        # `supabase.table("trades").select("*")` read through the repository
        # layer (`supabase_repository.get_all_trades`, which issues the
        # byte-identical query). Read-only, byte-identical result — the repo
        # returns `... .data or []`, so non-empty rows are passed through
        # unchanged and an empty/None result yields an empty DataFrame exactly
        # as `pd.DataFrame(res.data)` did. C1 `_require_active_dev_session`
        # guard + admin gate + B3 plan/confirm logic UNCHANGED.
        df  = pd.DataFrame(repo.get_all_trades(supabase))
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

        # Store plan for confirmation step.
        # Phase B3: persist the planned campaign_id — the campaign_id of the
        # exact open-position row this /addon was planned against (same `row`
        # used above for entry/stop/qty). At confirm we verify the open
        # campaign for the symbol has not changed since the plan, so the
        # Add-On write can never silently land on a different campaign's
        # Supabase rows than the one the user reviewed. If for some reason the
        # planned row has no resolvable campaign_id, store None so confirm
        # falls back to the legacy (pre-B3) re-resolution behavior.
        _planned_cid = row.get("campaign_id")
        if pd.isna(_planned_cid):
            _planned_cid = None
        user_state[chat_id] = {
            "action":      "addon_pending",
            "symbol":      symbol,
            "entry":       add_entry,
            "stop":        add_stop,
            "qty":         plan.get("proposed_qty", qty_arg),
            "add_type":    type_arg,
            "campaign_id": _planned_cid,
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
