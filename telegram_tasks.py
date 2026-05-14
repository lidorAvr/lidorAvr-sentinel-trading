"""telegram_tasks.py — UI handlers for the 📋 סקירת משימות feature.

Three screens, two callback flows:
  1. handle_tasks_review(chat_id)           — list of symbols with task counts
  2. show_symbol_tasks(chat_id, sym)        — list of tasks for one symbol
  3. show_task_detail(chat_id, cid, kind)   — detail + action buttons
  4. confirm_approve(chat_id, cid, kind)    — secondary confirm dialog
  5. (manual edit path)                     — handled by handle_all_messages text input

Callback data scheme:
  task|sym|<SYM>                       — open a symbol's task list
  task|view|<campaign_id>|<kind>       — open a single task detail
  task|approve|<campaign_id>|<kind>    — show confirm dialog
  task|confirm|<campaign_id>|<kind>|<v> — apply the suggested level v
  task|edit|<campaign_id>|<kind>       — switch to manual-input mode
  task|snooze|<campaign_id>|<kind>     — 24h snooze
  task|dismiss|<campaign_id>|<kind>    — 30d snooze
  task|cancel                          — cancel the current dialog
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

import telebot
import pandas as pd

import engine_core as ec
import supabase_repository as repo
import audit_logger
import task_engine as te
import task_state as ts
from bot_core import bot, supabase, RTL
from bot_helpers import get_account_settings, get_nav_and_risk
from telegram_menus import get_main_menu


SEP = "───────────────"


# ────────────────────────────────────────────────────────────────────────────────
# Data preparation — turn raw position rows into the dict shape task_engine needs.
# ────────────────────────────────────────────────────────────────────────────────

def _build_task_input(df: pd.DataFrame, acc_size: float) -> list[dict]:
    """For each open campaign row, compute the derived fields task_engine needs:
    current_price, open_r, days_held, ma21 (optional). ALGO rows are kept;
    task_engine itself filters them out (single point of truth)."""
    pos_res = ec.get_open_positions_campaign(df)
    if not pos_res.get("ok") or pos_res["data"].empty:
        return []
    out = []
    for row in pos_res["data"].to_dict("records"):
        try:
            sym       = row.get("symbol")
            entry     = float(row.get("price") or 0)
            qty       = float(row.get("quantity") or 0)
            sl        = float(row.get("stop_loss") or 0)
            init_sl   = float(row.get("initial_stop") or 0)
            base_qty  = float(row.get("base_qty", qty) or qty)
            base_pr   = float(row.get("base_price", entry) or entry)
            entry_dt  = row.get("entry_date")

            curr = ec.get_live_price(sym) or entry
            try:
                days_held = (datetime.now() - pd.to_datetime(entry_dt)).days if entry_dt else 0
            except Exception:
                days_held = 0

            # Original campaign risk in $ — needed for open_r in R-multiples.
            init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_pr) else 0
            original_risk = (base_pr - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
            open_pnl = (curr - entry) * qty
            open_r   = (open_pnl / original_risk) if original_risk > 0 else 0

            # ma21 — optional, best-effort. None means tighten_to_ma21 won't fire.
            ma21 = None
            try:
                lvl = ec.get_ma_levels(sym)
                ma21 = float(lvl.get("ma21")) if lvl and lvl.get("ma21") else None
            except Exception:
                pass

            out.append({
                "campaign_id":   row.get("campaign_id"),
                "symbol":        sym,
                "setup_type":    row.get("setup_type"),
                "current_price": curr,
                "entry_price":   entry,
                "stop_loss":     sl,
                "initial_stop":  init_sl_clean,
                "open_r":        open_r,
                "days_held":     days_held,
                "ma21":          ma21,
            })
        except Exception:
            continue
    return out


# ────────────────────────────────────────────────────────────────────────────────
# Screen 1 — list of symbols with task counts
# ────────────────────────────────────────────────────────────────────────────────

def handle_tasks_review(chat_id: int):
    """Entry point — list of symbols with open tasks. If none, simple OK."""
    try:
        trades = repo.get_all_trades(supabase)
        df     = pd.DataFrame(trades)
        if df.empty:
            return bot.send_message(chat_id, f"{RTL}📋 *סקירת משימות*\n{RTL}אין פוזיציות פתוחות.",
                                     reply_markup=get_main_menu(), parse_mode="Markdown")

        account_settings = get_account_settings()
        acc_size, _, _ = get_nav_and_risk(account_settings)
        positions = _build_task_input(df, acc_size)
        snoozed   = ts.get_snoozes()
        tasks     = te.compute_open_tasks(positions, snoozed=snoozed)

        if not tasks:
            return bot.send_message(
                chat_id,
                f"{RTL}📋 *סקירת משימות*\n{RTL}{SEP}\n"
                f"{RTL}✅ *אין משימות פתוחות.* כל הפוזיציות בניהול תקין.\n",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )

        grouped = te.group_by_symbol(tasks)
        lines = [
            f"{RTL}📋 *סקירת משימות* — `{len(tasks)}` משימות פתוחות",
            f"{RTL}{SEP}",
            f"{RTL}בחר סימול כדי לראות את המשימות שלו:",
        ]
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        # Show symbols grouped by count, sorted by highest urgency first
        sym_summary = []
        for sym in grouped:
            max_urg = max(t.urgency for t in grouped[sym])
            sym_summary.append((max_urg, len(grouped[sym]), sym))
        sym_summary.sort(reverse=True)
        for _urg, n_tasks, sym in sym_summary:
            label = f"{sym} ({n_tasks})"
            markup.add(telebot.types.InlineKeyboardButton(
                label, callback_data=f"task|sym|{sym}"))
        bot.send_message(chat_id, "\n".join(lines),
                         reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"{RTL}❌ שגיאה בסקירת משימות:\n`{e}`",
                         reply_markup=get_main_menu(), parse_mode="Markdown")


# ────────────────────────────────────────────────────────────────────────────────
# Screen 2 — tasks for one symbol
# ────────────────────────────────────────────────────────────────────────────────

def show_symbol_tasks(chat_id: int, sym: str):
    """List all open tasks for a given symbol."""
    try:
        trades = repo.get_all_trades(supabase)
        df     = pd.DataFrame(trades)
        account_settings = get_account_settings()
        acc_size, _, _ = get_nav_and_risk(account_settings)
        positions = _build_task_input(df, acc_size)
        snoozed   = ts.get_snoozes()
        all_tasks = te.compute_open_tasks(positions, snoozed=snoozed)
        sym_tasks = [t for t in all_tasks if t.symbol == sym]
        if not sym_tasks:
            return bot.send_message(
                chat_id,
                f"{RTL}📋 *{sym}* — אין משימות פתוחות.",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )

        lines = [
            f"{RTL}📋 *משימות — {sym}* ({len(sym_tasks)})",
            f"{RTL}{SEP}",
        ]
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        for t in sym_tasks:
            markup.add(telebot.types.InlineKeyboardButton(
                te.render_task_line(t),
                callback_data=f"task|view|{t.campaign_id}|{t.kind}",
            ))
        markup.add(telebot.types.InlineKeyboardButton(
            "⬅️ חזרה לסקירה", callback_data="task|back"))
        bot.send_message(chat_id, "\n".join(lines),
                         reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"{RTL}❌ שגיאה: `{e}`",
                         reply_markup=get_main_menu(), parse_mode="Markdown")


# ────────────────────────────────────────────────────────────────────────────────
# Screen 3 — detail + action buttons
# ────────────────────────────────────────────────────────────────────────────────

def _find_task(campaign_id: str, kind: str):
    """Re-evaluate tasks and locate the one matching (campaign_id, kind).
    Returns None if the task no longer fires (state changed) or position
    closed — caller should tell the user 'no longer relevant'."""
    trades = repo.get_all_trades(supabase)
    df     = pd.DataFrame(trades)
    account_settings = get_account_settings()
    acc_size, _, _ = get_nav_and_risk(account_settings)
    positions = _build_task_input(df, acc_size)
    snoozed   = ts.get_snoozes()
    all_tasks = te.compute_open_tasks(positions, snoozed=snoozed)
    for t in all_tasks:
        if t.campaign_id == campaign_id and t.kind == kind:
            return t
    return None


def show_task_detail(chat_id: int, campaign_id: str, kind: str):
    t = _find_task(campaign_id, kind)
    if t is None:
        return bot.send_message(
            chat_id,
            f"{RTL}ℹ️ המשימה כבר לא רלוונטית (ייתכן שעודכן הסטופ או הפוזיציה נסגרה).",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
    detail = te.render_task_detail(t)
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    if t.suggested_action == "update_stop" and t.suggested_level is not None:
        markup.add(
            telebot.types.InlineKeyboardButton(
                f"✅ אשר (${t.suggested_level:.2f})",
                callback_data=f"task|approve|{campaign_id}|{kind}"),
            telebot.types.InlineKeyboardButton(
                "✏️ ערוך ערך",
                callback_data=f"task|edit|{campaign_id}|{kind}"),
        )
    elif t.suggested_action == "exit":
        markup.add(telebot.types.InlineKeyboardButton(
            "✅ סמן כבוצע (סגור ב-IBKR ידנית)",
            callback_data=f"task|approve|{campaign_id}|{kind}"))
    markup.add(
        telebot.types.InlineKeyboardButton("⏰ דחה 24ש",
            callback_data=f"task|snooze|{campaign_id}|{kind}"),
        telebot.types.InlineKeyboardButton("❌ דלג 30 יום",
            callback_data=f"task|dismiss|{campaign_id}|{kind}"),
    )
    markup.add(telebot.types.InlineKeyboardButton(
        "⬅️ חזרה לסימול",
        callback_data=f"task|sym|{t.symbol}"))
    bot.send_message(chat_id, f"{RTL}{detail}",
                     reply_markup=markup, parse_mode="Markdown")


# ────────────────────────────────────────────────────────────────────────────────
# Approve flow — confirmation dialog
# ────────────────────────────────────────────────────────────────────────────────

def show_approve_confirm(chat_id: int, campaign_id: str, kind: str):
    """User tapped ✅ אשר → show 2-step confirm dialog with the exact
    level that will be written to Supabase, plus an option to edit it."""
    t = _find_task(campaign_id, kind)
    if t is None:
        return bot.send_message(
            chat_id,
            f"{RTL}ℹ️ המשימה כבר לא רלוונטית.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
    if t.suggested_action == "exit":
        # No price to confirm — just record acknowledgement
        return _apply_approve(chat_id, t, new_stop=None)

    lvl = t.suggested_level if t.suggested_level is not None else 0.0
    text = (
        f"{RTL}*אישור פעולה — {t.symbol}*\n"
        f"{RTL}{SEP}\n"
        f"{RTL}{t.title}\n"
        f"{RTL}\n"
        f"{RTL}האם להגדיר סטופ ל-`${lvl:.2f}`?\n"
    )
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    markup.add(telebot.types.InlineKeyboardButton(
        f"✅ כן, עדכן ל-${lvl:.2f}",
        callback_data=f"task|confirm|{campaign_id}|{kind}|{lvl:.2f}",
    ))
    markup.add(telebot.types.InlineKeyboardButton(
        "✏️ ערוך ערך אחר",
        callback_data=f"task|edit|{campaign_id}|{kind}",
    ))
    markup.add(telebot.types.InlineKeyboardButton(
        "❌ ביטול", callback_data=f"task|view|{campaign_id}|{kind}",
    ))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


def _apply_approve(chat_id: int, task, new_stop: Optional[float]):
    """Apply the approved task. Writes to Supabase (stop_loss for the
    campaign) when applicable, records audit_log + task_state."""
    dedup = task.dedup_key
    before = task.suggested_level  # for audit context (best-effort)
    after  = new_stop

    if task.suggested_action == "update_stop" and new_stop is not None:
        try:
            repo.update_stop_for_campaign(supabase, task.campaign_id, new_stop)
        except Exception as e:
            bot.send_message(
                chat_id,
                f"{RTL}⚠️ *שגיאה בעדכון Supabase:* `{e}`\n"
                f"{RTL}המשימה לא נסגרה. נסה שוב מאוחר יותר.",
                reply_markup=get_main_menu(), parse_mode="Markdown",
            )
            return
        try:
            audit_logger.log_action(
                supabase, "stop_update_via_task",
                chat_id=chat_id,
                before={"stop_loss": before},
                after={"stop_loss": after},
                metadata={"campaign_id": task.campaign_id,
                          "task_kind": task.kind,
                          "symbol": task.symbol},
            )
        except Exception:
            pass  # audit is fail-open by design
        ts.approve_task(dedup, before=before, after=after)
        bot.send_message(
            chat_id,
            f"{RTL}✅ *סטופ עודכן — {task.symbol}*\n"
            f"{RTL}סטופ חדש: `${new_stop:.2f}`\n"
            f"{RTL}נרשם ב-audit_log.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
    else:
        # Exit-type tasks: no Supabase write; just record acknowledgement.
        ts.approve_task(dedup, before=None, after=None)
        try:
            audit_logger.log_action(
                supabase, "task_acknowledged",
                chat_id=chat_id,
                metadata={"campaign_id": task.campaign_id,
                          "task_kind": task.kind,
                          "symbol": task.symbol},
            )
        except Exception:
            pass
        bot.send_message(
            chat_id,
            f"{RTL}✅ *סומן כבוצע — {task.symbol}*\n"
            f"{RTL}{task.title}\n"
            f"{RTL}בצע את הפעולה ב-IBKR ועדכן ידנית במערכת לאחר ביצוע.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )


def apply_confirmed_value(chat_id: int, campaign_id: str, kind: str, value: float):
    """User clicked '✅ כן, עדכן ל-$X' — apply that exact value."""
    t = _find_task(campaign_id, kind)
    if t is None:
        return bot.send_message(
            chat_id, f"{RTL}ℹ️ המשימה כבר לא רלוונטית.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
    _apply_approve(chat_id, t, new_stop=value)


# ────────────────────────────────────────────────────────────────────────────────
# Manual edit — text input flow
# ────────────────────────────────────────────────────────────────────────────────

def start_manual_edit(chat_id: int, campaign_id: str, kind: str, user_state: dict):
    """Switch the user into 'task_edit_value' state. handle_all_messages
    will route their next text message to apply_manual_edit_value."""
    t = _find_task(campaign_id, kind)
    if t is None:
        return bot.send_message(
            chat_id, f"{RTL}ℹ️ המשימה כבר לא רלוונטית.",
            reply_markup=get_main_menu(), parse_mode="Markdown",
        )
    user_state[chat_id] = {
        "action":      "task_edit_value",
        "campaign_id": campaign_id,
        "kind":        kind,
        "symbol":      t.symbol,
    }
    sugg = f"${t.suggested_level:.2f}" if t.suggested_level else "—"
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton(
        "❌ ביטול", callback_data="cancel_action"))
    bot.send_message(
        chat_id,
        f"{RTL}✏️ *ערוך ערך סטופ — {t.symbol}*\n"
        f"{RTL}{SEP}\n"
        f"{RTL}המלצה מקורית: {sugg}\n"
        f"{RTL}הקלד ערך חדש בדולרים (לדוגמה: `875.00`).",
        reply_markup=markup, parse_mode="Markdown",
    )


def apply_manual_edit_value(chat_id: int, value_text: str, user_state: dict):
    """Called from handle_all_messages when the user is in 'task_edit_value'
    mode. Validates the input as a positive float and applies it."""
    pending = user_state.get(chat_id, {})
    if pending.get("action") != "task_edit_value":
        return False
    try:
        new_val = float(value_text.replace("$", "").replace(",", "").strip())
        if new_val <= 0:
            raise ValueError("non-positive")
    except (ValueError, TypeError):
        bot.send_message(
            chat_id,
            f"{RTL}⚠️ ערך לא תקין. הקלד מספר חיובי (לדוגמה: `880.50`) או שלח 'ביטול'.",
            parse_mode="Markdown",
        )
        return True  # handled (stayed in state)
    cid  = pending["campaign_id"]
    kind = pending["kind"]
    user_state.pop(chat_id, None)
    apply_confirmed_value(chat_id, cid, kind, new_val)
    return True


# ────────────────────────────────────────────────────────────────────────────────
# Snooze / Dismiss
# ────────────────────────────────────────────────────────────────────────────────

def snooze_short(chat_id: int, campaign_id: str, kind: str):
    """24h snooze (⏰)."""
    dedup = f"{campaign_id}|{kind}"
    ts.snooze_task(dedup, ts.SNOOZE_SHORT)
    bot.send_message(
        chat_id,
        f"{RTL}⏰ נדחתה ל-24 שעות. תופיע שוב מחר אם המצב עדיין רלוונטי.",
        reply_markup=get_main_menu(), parse_mode="Markdown",
    )


def dismiss_long(chat_id: int, campaign_id: str, kind: str):
    """30-day dismiss (❌ דלג)."""
    dedup = f"{campaign_id}|{kind}"
    ts.dismiss_task(dedup)
    bot.send_message(
        chat_id,
        f"{RTL}❌ דולגה ל-30 יום. תוכל לראות אותה שוב באמצעות 'איפוס משימות' בעתיד.",
        reply_markup=get_main_menu(), parse_mode="Markdown",
    )
