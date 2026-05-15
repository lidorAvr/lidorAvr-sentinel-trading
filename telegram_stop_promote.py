"""
Lightweight stop-promotion ("קידום סטופ") flow for Sentinel Trading.

Why this module exists
----------------------
Founder pain (UX_TELEGRAM_AUDIT_DAY3, Pain 1): promoting a stop used to
require running the heavy "חדר מצב" portfolio room (a slow, multi-network
report) JUST to populate ``user_state[chat_id]['temp_positions']``, then
*typing* the trade number while scrolling a long message to map number ↔
symbol. Promoting 4 stops meant re-running the heavy room 4 times.

This module provides a fast, tap-only path:

* ``handle_stop_promote_entry`` — fetches open positions with the SAME
  lightweight helpers the rest of the bot uses (``repo.get_all_trades`` +
  ``ec.get_open_positions_campaign`` + ``ec.get_live_price``). It does NOT
  call ``evaluate_position_engine`` and does NOT recompute any campaign /
  R / NAV math beyond the exact open-R formula already used in
  ``telegram_portfolio.handle_portfolio_room``. It only decides how the
  user *selects* a position — never how the stop is computed or written.
* ``build_stop_promote_keyboard`` — one inline button per discretionary
  open position, labelled with symbol + open-R (e.g. ``🎯 CAT  +1.99R``).
  No typing, no scrolling.
* ``handle_stop_promote_pick`` — selects the campaign and hands off to the
  EXISTING ``input_new_sl`` user_state action in telegram_bot.py, whose
  write path (``repo.update_stop_for_campaign``) is byte-identical to the
  legacy flow. A ``promote_batch`` flag tells that handler to return to
  this list after a successful write so the next stop can be promoted
  immediately — no expiry, no heavy re-run.

Red lines respected
--------------------
* No change to stop value math: selection only.
* ALGO campaigns are excluded — Sentinel never instructs ALGO stops
  (DEC-20260511-001 / AGENTS.md). They are shown as non-actionable info.
* Admin guard / anti-spam live in telegram_bot_secure_runner.py and are
  untouched.
"""
from telebot import types
import pandas as pd

import audit_logger
import engine_core as ec
import supabase_repository as repo
from bot_core import bot, supabase, user_state, RTL
from bot_helpers import get_account_settings, get_nav_and_risk
from telegram_menus import get_main_menu, get_portfolio_menu


def _compute_open_r(row, target_risk_usd):
    """Open-R for one open-position dict.

    This is the SAME formula already used in
    telegram_portfolio.handle_portfolio_room (ALGO → Target Risk base;
    discretionary → original campaign risk). It is duplicated here only
    for the button label — the authoritative report still computes it
    itself; this never feeds back into any write.

    Returns ``(open_r, curr, price_is_fallback)``. ``price_is_fallback``
    (Sprint-12 / Mark §3) is a PURE bool of ``ec.get_live_price() is None``
    — NO math change (the open-R formula and ``curr`` are byte-identical to
    before); it only lets the keyboard render the honest fallback label.
    """
    try:
        entry = float(row.get("price", 0) or 0)
        qty = float(row.get("quantity", 0) or 0)
        init_sl = float(row.get("initial_stop", 0) or 0)
        base_price = float(row.get("base_price", entry) or entry)
        base_qty = float(row.get("base_qty", qty) or qty)
        setup = str(row.get("setup_type", "")).upper()

        curr = ec.get_live_price(row.get("symbol"))
        price_is_fallback = curr is None
        if price_is_fallback:
            curr = entry
        open_pnl_usd = (curr - entry) * qty

        if setup == "ALGO" and target_risk_usd > 0:
            return open_pnl_usd / target_risk_usd, curr, price_is_fallback
        init_sl_clean = init_sl if (0 < init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
        if original_campaign_risk > 0:
            return open_pnl_usd / original_campaign_risk, curr, price_is_fallback
        return None, curr, price_is_fallback
    except Exception:
        return None, None, False


def build_stop_promote_keyboard(positions):
    """Inline keyboard: one symbol-labelled button per discretionary position.

    positions: list of open-position dicts (the ``temp_positions`` records).
    Returns an InlineKeyboardMarkup. ALGO positions are skipped entirely
    (Sprint-11 #7) — Sentinel never manages ALGO stops, so an ALGO row in
    a stop-promotion list is pure noise (no button, no dead-end popup).
    """
    account_settings = get_account_settings()
    _acc, target_risk_usd, _stale = get_nav_and_risk(account_settings)

    markup = types.InlineKeyboardMarkup(row_width=1)
    any_fallback = False
    for idx, row in enumerate(positions):
        sym = row.get("symbol", "?")
        setup = str(row.get("setup_type", "")).upper()
        if setup == "ALGO":
            # #7 / SPRINT11_DESIGN §4.1 — Sentinel never manages ALGO stops;
            # ALGO rows are pure noise in this discretionary-only flow. Skip
            # them entirely (no info button, no promote_algo_noop dead-end).
            continue
        open_r, _curr, price_is_fallback = _compute_open_r(row, target_risk_usd)
        if open_r is None:
            r_label = "R N/A"
        else:
            r_label = f"{open_r:+.2f}R"
        # Sprint-12 / Mark §3 — when this row's open-R was computed off
        # entry-as-price because ec.get_live_price() returned None, the button
        # carries an honest short marker (the canonical label is shown in full
        # below; the button is space-constrained). No number changes.
        fb_mark = " ‏⚠️" if price_is_fallback else ""
        any_fallback = any_fallback or price_is_fallback
        markup.add(types.InlineKeyboardButton(
            f"🎯 {sym}  {r_label}{fb_mark}",
            callback_data=f"promote_pick|{idx}",
        ))
    if any_fallback:
        # Sprint-12 / Mark §3 — surface the EXACT canonical label (the
        # space-constrained buttons only carry a ⚠️ marker). Non-tappable
        # info row (same pattern as the ALGO no-op rows); tapping it just
        # echoes the honest label, never an action.
        import telegram_formatters as _tf
        markup.add(types.InlineKeyboardButton(
            _tf.PRICE_FALLBACK_LABEL,
            callback_data="promote_price_fallback_note",
        ))
    markup.add(types.InlineKeyboardButton("❌ סגור", callback_data="cancel_action"))
    return markup


def handle_stop_promote_entry(chat_id):
    """Lightweight entry point — list open positions WITHOUT the heavy room.

    Reuses repo.get_all_trades + ec.get_open_positions_campaign only
    (no evaluate_position_engine, no market regime, no coaching). Stores
    the records in user_state['temp_positions'] so both this flow and the
    legacy typed-index flow keep working from the same data.
    """
    loading = bot.send_message(chat_id, f"{RTL}⏳ *טוען פוזיציות לקידום סטופ...*",
                               parse_mode="Markdown")
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"]:
            try:
                bot.delete_message(chat_id, loading.message_id)
            except Exception:
                pass
            bot.send_message(chat_id, f"{RTL}❌ שגיאת תשתית: `{pos_res['error']}`",
                             reply_markup=get_portfolio_menu(), parse_mode="Markdown")
            return

        open_pos = pos_res["data"]
        if open_pos.empty:
            try:
                bot.delete_message(chat_id, loading.message_id)
            except Exception:
                pass
            bot.send_message(chat_id, f"{RTL}✅ אין פוזיציות פתוחות לקידום סטופ.",
                             reply_markup=get_portfolio_menu(), parse_mode="Markdown")
            return

        records = open_pos.to_dict("records")
        # Keep the same key the legacy typed-index flow reads, so both paths
        # stay consistent and the typed fallback still works.
        st = user_state.get(chat_id, {})
        st["temp_positions"] = records
        user_state[chat_id] = st

        disc = [r for r in records if str(r.get("setup_type", "")).upper() != "ALGO"]
        algo_n = len(records) - len(disc)

        # #7 / SPRINT11_DESIGN §4.2 — with ALGO rows no longer rendered, the
        # all-ALGO case must be an explicit early empty-state (the keyboard
        # would otherwise be just "❌ סגור"). Mirrors this module's own
        # "אין פוזיציות פתוחות" early-return path.
        if not disc:
            try:
                bot.delete_message(chat_id, loading.message_id)
            except Exception:
                pass
            bot.send_message(
                chat_id,
                f"{RTL}🎯 *קידום סטופ*\n"
                f"{RTL}אין פוזיציות דיסקרציוניות לקידום סטופ.\n"
                f"{RTL}כל הפוזיציות הפתוחות מנוהלות חיצונית (ALGO) — "
                f"Sentinel אינה מנהלת סטופים של אלגו.",
                reply_markup=get_portfolio_menu(), parse_mode="Markdown",
            )
            return

        header = (
            f"{RTL}🎯 *קידום סטופ — בחר פוזיציה*\n"
            f"{RTL}לחיצה אחת בוחרת קמפיין. אין צורך להקליד מספר.\n"
        )
        if algo_n:
            # Mixed case: ALGO buttons are gone, so the note is reworded
            # (SPRINT11_DESIGN §4.2 — pure UX, methodology-neutral).
            header += f"{RTL}_(פוזיציות ALGO אינן מוצגות — מנוהל חיצונית.)_"

        try:
            bot.delete_message(chat_id, loading.message_id)
        except Exception:
            pass
        bot.send_message(chat_id, header,
                         reply_markup=build_stop_promote_keyboard(records),
                         parse_mode="Markdown")
    except Exception as e:
        try:
            bot.delete_message(chat_id, loading.message_id)
        except Exception:
            pass
        bot.send_message(chat_id, f"{RTL}❌ תקלה בטעינת פוזיציות: `{e}`",
                         reply_markup=get_portfolio_menu(), parse_mode="Markdown")


def handle_stop_promote_pick(chat_id, idx):
    """User tapped a position button — select it and ask for the new stop.

    Hands off to the EXISTING ``input_new_sl`` user_state action handled in
    telegram_bot.py (byte-identical write via repo.update_stop_for_campaign).
    Sets ``promote_batch`` so that handler re-opens this list afterwards.
    """
    st = user_state.get(chat_id, {})
    positions = st.get("temp_positions")
    if not positions:
        bot.send_message(
            chat_id,
            f"{RTL}⚠️ הרשימה פגה. פותח מחדש...",
            parse_mode="Markdown",
        )
        handle_stop_promote_entry(chat_id)
        return

    if not (0 <= idx < len(positions)):
        bot.send_message(chat_id, f"{RTL}❌ בחירה לא תקינה.", parse_mode="Markdown")
        handle_stop_promote_entry(chat_id)
        return

    selected = positions[idx]
    if str(selected.get("setup_type", "")).upper() == "ALGO":
        bot.send_message(
            chat_id,
            f"{RTL}🟠 *{selected.get('symbol')}* מנוהל חיצונית (ALGO).\n"
            f"{RTL}Sentinel אינה מנהלת סטופים של אלגו — לבחור פוזיציה אחרת.",
            parse_mode="Markdown",
        )
        return

    st["selected_trade"] = selected
    st["action"] = "input_new_sl"
    st["promote_batch"] = True  # tells input_new_sl handler to return here
    user_state[chat_id] = st

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ ביטול", callback_data="cancel_action"))
    try:
        entry_p = float(selected.get("price", 0) or 0)
        stop_p = float(selected.get("stop_loss", 0) or 0)
    except Exception:
        entry_p = stop_p = 0
    bot.send_message(
        chat_id,
        f"{RTL}✅ נבחר *{selected.get('symbol')}*\n"
        f"{RTL}מחיר כניסה: `${entry_p:.2f}` | סטופ נוכחי: `${stop_p:.2f}`\n\n"
        f"{RTL}*הקלד את מחיר הסטופ החדש:*",
        reply_markup=markup, parse_mode="Markdown",
    )


# ── Ratchet-up guard (MARK_DAY3_GUARDRAILS U3/C3; DEC: founder chose ──────────
#    "explicit confirmation + audit"). Minervini rule: a long position's stop
#    only ever moves UP. Lowering it ("loosening") is the single most
#    methodology-violating action the bot can permit, so it requires an
#    explicit, defaulted-NO confirmation and a write-only audit_log entry.
#
#    This module is the ONLY place the rule lives; both stop-write paths
#    (input_new_sl, tighten_stop in telegram_bot.py) call guard_stop_write
#    immediately before repo.update_stop_for_campaign. The stop *value* math
#    is unchanged — this only gates whether the byte-identical write happens.
_LOOSEN_EPS = 0.005  # ignore sub-cent float noise; stops are 2-dp dollar prices


def _is_loosen(current_stop, new_sl) -> bool:
    """True only when we can POSITIVELY determine new_sl loosens the stop.

    Long-only assumption (this is a Minervini long-momentum system; no shorts
    in the data model): loosening = moving the stop DOWN, i.e.
    ``new_sl < current_stop``. Unknown / non-positive current stop (e.g. the
    very first stop being set) → False, so legitimate first-time stop entry
    and all tightening proceed byte-identically with zero added friction and
    zero false positives.
    """
    try:
        if current_stop is None:
            return False
        c = float(current_stop)
        n = float(new_sl)
        if c <= 0:
            return False
        return n < c - _LOOSEN_EPS
    except (TypeError, ValueError):
        return False


def get_campaign_current_stop(campaign_id):
    """Best-effort current stop for a campaign; None if not resolvable.

    Used by the tighten_stop path, whose user_state carries only sym +
    campaign_id (no stop). Uses the SAME data path as the position list
    (repo.get_all_trades + ec.get_open_positions_campaign). If it cannot be
    resolved the guard proceeds (does not block a runner-alert tighten we
    cannot verify) — documented limitation; the high-value input_new_sl path
    always has the current stop in state and is fully covered.
    """
    if not campaign_id:
        return None
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"]:
            return None
        for rec in pos_res["data"].to_dict("records"):
            if str(rec.get("campaign_id")) == str(campaign_id):
                sl = rec.get("stop_loss")
                if sl in (None, ""):
                    return None
                return float(sl)
    except Exception:
        return None
    return None


def guard_stop_write(chat_id, *, cid, sym, new_sl, current_stop, resume) -> bool:
    """Ratchet-up gate. Call immediately before repo.update_stop_for_campaign.

    Returns True if the write was INTERCEPTED (a loosen): the caller MUST NOT
    write and MUST return — a defaulted-NO confirmation has been sent and the
    pending write stashed in user_state. Returns False to proceed
    byte-identically (tighten / equal / unknown current stop).

    resume: dict carried to finalize_pending_loosen, e.g. {'batch': bool}.
    """
    if not _is_loosen(current_stop, new_sl):
        return False
    cur = float(current_stop)
    new = float(new_sl)
    diff = cur - new
    user_state[chat_id] = {
        "action": "loosen_pending",
        "pending": {
            "cid": cid,
            "sym": sym,
            "new_sl": new,
            "current_stop": cur,
            "resume": resume or {},
        },
    }
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "⚠️ כן, לרופף את הסטופ (יירשם ביומן הביקורת)",
        callback_data="loosen_confirm|yes"))
    markup.add(types.InlineKeyboardButton(
        "✅ לא — השאר את הסטופ הקיים",
        callback_data="loosen_confirm|no"))
    bot.send_message(
        chat_id,
        f"{RTL}🛑 *אזהרת ריפוי סטופ — {sym}*\n"
        f"{RTL}סטופ נוכחי: `${cur:.2f}`\n"
        f"{RTL}סטופ מבוקש: `${new:.2f}`  (ירידה של `${diff:.2f}`)\n\n"
        f"{RTL}הורדת סטופ מנוגדת לכלל ה-Ratchet של Minervini — "
        f"סטופ של פוזיציית long רק עולה, לעולם לא יורד.\n"
        f"{RTL}ברירת המחדל היא *לא לשנות*. אישור מפורש יירשם ביומן הביקורת.",
        reply_markup=markup, parse_mode="Markdown",
    )
    return True


def finalize_pending_loosen(chat_id, approved: bool):
    """Resolve a pending loosen confirmation (called from the callback router).

    Approved → write an audit_log row FIRST (fail-open), then the
    byte-identical repo.update_stop_for_campaign, then resume the original
    flow. Rejected (default) → leave the stop untouched.
    """
    st = user_state.get(chat_id, {})
    pending = st.get("pending") if st.get("action") == "loosen_pending" else None
    if not pending:
        bot.send_message(chat_id, f"{RTL}⚠️ אין פעולת סטופ ממתינה.",
                          reply_markup=get_main_menu())
        return
    user_state.pop(chat_id, None)
    cid = pending["cid"]
    sym = pending["sym"]
    new_sl = pending["new_sl"]
    cur = pending["current_stop"]
    resume = pending.get("resume", {})

    if not approved:
        bot.send_message(
            chat_id,
            f"{RTL}✅ *בוטל — הסטופ לא שונה* ({sym})\n"
            f"{RTL}הסטופ נשאר `${cur:.2f}`.",
            reply_markup=get_main_menu(), parse_mode="Markdown")
        return

    audit_logger.log_action(
        supabase, audit_logger.ACTION_SETTINGS_CHANGE,
        chat_id=chat_id,
        before={"stop_loss": cur},
        after={"stop_loss": new_sl},
        metadata={
            "kind": "stop_loosen_override",
            "symbol": sym,
            "campaign_id": cid,
            "loosen_usd": round(cur - new_sl, 4),
        },
    )
    repo.update_stop_for_campaign(supabase, cid, new_sl)
    bot.send_message(
        chat_id,
        f"{RTL}⚠️ *סטופ רופף ועודכן — {sym}*\n"
        f"{RTL}סטופ חדש: `${new_sl:.2f}` (היה `${cur:.2f}`).\n"
        f"{RTL}הפעולה נרשמה ביומן הביקורת.",
        reply_markup=get_main_menu(), parse_mode="Markdown")
    if resume.get("batch"):
        handle_stop_promote_entry(chat_id)
