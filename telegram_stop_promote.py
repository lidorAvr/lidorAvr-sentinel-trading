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

import engine_core as ec
import supabase_repository as repo
from bot_core import bot, supabase, user_state, RTL
from bot_helpers import get_account_settings, get_nav_and_risk
from telegram_menus import get_portfolio_menu


def _compute_open_r(row, target_risk_usd):
    """Open-R for one open-position dict.

    This is the SAME formula already used in
    telegram_portfolio.handle_portfolio_room (ALGO → Target Risk base;
    discretionary → original campaign risk). It is duplicated here only
    for the button label — the authoritative report still computes it
    itself; this never feeds back into any write.
    """
    try:
        entry = float(row.get("price", 0) or 0)
        qty = float(row.get("quantity", 0) or 0)
        init_sl = float(row.get("initial_stop", 0) or 0)
        base_price = float(row.get("base_price", entry) or entry)
        base_qty = float(row.get("base_qty", qty) or qty)
        setup = str(row.get("setup_type", "")).upper()

        curr = ec.get_live_price(row.get("symbol"))
        if curr is None:
            curr = entry
        open_pnl_usd = (curr - entry) * qty

        if setup == "ALGO" and target_risk_usd > 0:
            return open_pnl_usd / target_risk_usd, curr
        init_sl_clean = init_sl if (0 < init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
        if original_campaign_risk > 0:
            return open_pnl_usd / original_campaign_risk, curr
        return None, curr
    except Exception:
        return None, None


def build_stop_promote_keyboard(positions):
    """Inline keyboard: one symbol-labelled button per discretionary position.

    positions: list of open-position dicts (the ``temp_positions`` records).
    Returns an InlineKeyboardMarkup. ALGO positions get a disabled-style
    info button (callback ``promote_algo_noop``) so the user understands
    why they cannot promote them — Sentinel does not manage ALGO stops.
    """
    account_settings = get_account_settings()
    _acc, target_risk_usd, _stale = get_nav_and_risk(account_settings)

    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, row in enumerate(positions):
        sym = row.get("symbol", "?")
        setup = str(row.get("setup_type", "")).upper()
        open_r, _curr = _compute_open_r(row, target_risk_usd)
        if setup == "ALGO":
            markup.add(types.InlineKeyboardButton(
                f"🟠 {sym} — מנוהל חיצונית (ALGO)",
                callback_data="promote_algo_noop",
            ))
            continue
        if open_r is None:
            r_label = "R N/A"
        else:
            r_label = f"{open_r:+.2f}R"
        markup.add(types.InlineKeyboardButton(
            f"🎯 {sym}  {r_label}",
            callback_data=f"promote_pick|{idx}",
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

        header = (
            f"{RTL}🎯 *קידום סטופ — בחר פוזיציה*\n"
            f"{RTL}לחיצה אחת בוחרת קמפיין. אין צורך להקליד מספר.\n"
        )
        if not disc:
            header += f"{RTL}\n⚠️ כל הפוזיציות הפתוחות הן ALGO — Sentinel אינה מנהלת סטופים של אלגו."
        elif algo_n:
            header += f"{RTL}_(פוזיציות ALGO מסומנות 🟠 ואינן ניתנות לקידום — מנוהל חיצונית.)_"

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
