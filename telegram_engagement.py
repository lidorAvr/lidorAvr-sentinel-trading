"""
telegram_engagement.py — engagement-phase pull surfaces.

Engagement-meeting Wave-3B (21/05/2026). New shippable surfaces that
build on the Wave-3A foundation (engagement_suppression, audit
constants, gate_result logging, fmt_adaptive_risk_block routing).

Surfaces currently exposed:
  - `/gate_receipt` → C4-S1 Gate Receipt (Mark §C4 binding,
    count-only Phase-1; symmetric framing reserved for Phase-2 D11).

Module discipline (mirrors `telegram_audit_review.py`):
  - SELECT-only: this module never writes to Supabase.
  - Admin-gated via the existing telegram_bot message/callback gate;
    secure_runner untouched.
  - No fabricated numbers (Mark §3 / §X1). When the underlying engine
    function returns ``total_clamps=0`` the formatter returns ""; this
    handler then emits an HONEST empty-state line, never a fake
    "great work" celebration (§C4 R1).
  - Pull-only — no push path here. §X5 silence-as-surface honored.
"""
import pandas as pd
from telebot import types

from bot_core import bot, supabase, user_state, RTL

import audit_logger
import adaptive_risk_engine as are
import engagement_suppression as es
import supabase_repository as repo
import telegram_formatters as tf


def handle_backfill_prompt(chat_id):
    """`/backfill_prompt` — C1-S1 Phase-1 pull surface.

    Finds the oldest null-reason rejection ≥14 days old (Mark §C1
    binding), surfaces it as `fmt_backfill_prompt`, and offers two
    inline-keyboard choices:
        ✏️ הוסף סיבה  — sets user_state to collect the typed reason
        🙈 דלג         — marks the entry as deliberately skipped

    §X5 silence-as-surface: if no candidate exists (no null-reason
    rejection in window), emit an honest empty-state line — never a
    "great work, your journal is full" celebration.
    """
    candidate = are.find_backfill_candidate()
    if not candidate:
        bot.send_message(
            chat_id,
            f"{RTL}📖 *הספר*\n"
            f"{RTL}אין דחיות חסרות-נימוק מתוך 14 הימים האחרונים. "
            f"כל הדחיות מתועדות עם סיבה.",
            parse_mode="Markdown",
        )
        return
    body = tf.fmt_backfill_prompt(candidate)
    ts = str(candidate.get("ts") or "")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "✏️ הוסף סיבה",
            callback_data=f"backfill_add|{ts}",
        ),
        types.InlineKeyboardButton(
            "🙈 דלג",
            callback_data=f"backfill_skip|{ts}",
        ),
    )
    bot.send_message(chat_id, body, reply_markup=markup, parse_mode="Markdown")


def handle_backfill_add(chat_id, message_id, entry_ts):
    """Callback for `backfill_add|{ts}` — enter the reason-collection
    state. The next text from the founder is captured as the
    rejection's verbatim reason (§X4)."""
    user_state[chat_id] = {
        "action": "backfill_collect_reason",
        "entry_ts": entry_ts,
        "original_msg_id": message_id,
    }
    try:
        bot.edit_message_text(
            f"{RTL}📖 *הספר ממתין*\n"
            f"{RTL}כתוב במשפט אחד את הסיבה לדחייה. הטקסט יישמר verbatim — "
            f"זאת המילה שלך, לא ניסוח שלי.",
            chat_id, message_id, parse_mode="Markdown",
        )
    except Exception:
        bot.send_message(
            chat_id,
            f"{RTL}📖 כתוב במשפט אחד את הסיבה לדחייה.",
            parse_mode="Markdown",
        )


def handle_backfill_skip(chat_id, message_id, entry_ts):
    """Callback for `backfill_skip|{ts}` — mark the candidate as
    deliberately skipped and confirm. Honest semantics: the rejection
    stays reason="" in the journal; the new `backfill_skipped=True`
    flag means "the founder chose silence here". No reason fabricated.
    """
    ok = are.mark_backfill_skipped(entry_ts)
    audit_logger.log_action(
        supabase, audit_logger.ACTION_SETTINGS_CHANGE,
        chat_id=chat_id,
        before={"backfill_status": "candidate"},
        after={"backfill_status": "skipped"},
        metadata={
            "kind": "backfill_skipped",
            "entry_ts": entry_ts,
        },
    )
    msg = (
        f"{RTL}📖 *הספר רושם — דלגת על הסבר*\n"
        f"{RTL}הדחייה נשארת ללא ניסוח. הספר לא ימציא לך אחד."
        if ok else
        f"{RTL}📖 לא הצלחתי למצוא את הרשומה. ייתכן שכבר עודכנה."
    )
    try:
        bot.edit_message_text(msg, chat_id, message_id, parse_mode="Markdown")
    except Exception:
        bot.send_message(chat_id, msg, parse_mode="Markdown")


def handle_backfill_collect_reason(chat_id, text):
    """Text-collection handler invoked when user_state.action ==
    'backfill_collect_reason'. Writes the typed reason §X4 verbatim
    to the original risk_journal.json entry + an audit row, then
    confirms."""
    state = user_state.get(chat_id, {}) or {}
    entry_ts = str(state.get("entry_ts") or "")
    if not entry_ts:
        bot.send_message(
            chat_id,
            f"{RTL}📖 הקשר אבד. נסה שוב מ-/backfill_prompt.",
            parse_mode="Markdown",
        )
        user_state.pop(chat_id, None)
        return
    reason_text = (text or "").strip()
    if not reason_text:
        bot.send_message(
            chat_id,
            f"{RTL}📖 שורה ריקה אינה ניסוח. כתוב משפט אחד או בטל.",
            parse_mode="Markdown",
        )
        return
    ok = are.apply_backfill_reason(entry_ts, reason_text)
    audit_logger.log_action(
        supabase, audit_logger.ACTION_SETTINGS_CHANGE,
        chat_id=chat_id,
        before={"reason": ""},
        after={"reason": reason_text},  # §X4 verbatim
        metadata={
            "kind": "backfill_reason_added",
            "entry_ts": entry_ts,
        },
    )
    user_state.pop(chat_id, None)
    # S-ENGAGE-1 boundary: escape Markdown specials in the rendered
    # reason. Stored bytes stay verbatim (§X4); only the render is
    # escaped.
    safe_reason = tf.render_journal_text(reason_text)
    msg = (
        f"{RTL}📖 *הספר רשם*\n"
        f"{RTL}\"_{safe_reason}_\"\n"
        f"{RTL}נשמר verbatim על הדחייה מ-{entry_ts[:10]}."
        if ok else
        f"{RTL}📖 לא הצלחתי למצוא את הרשומה. ייתכן שכבר עודכנה."
    )
    bot.send_message(chat_id, msg, parse_mode="Markdown")


def handle_eod_check(chat_id):
    """`/eod_check` — B5 EOD verdict pull surface.

    Computes today's closed R (calendar day in IL time) + checks §X5
    suppression rules (TWO_R_DOWN / SETTLE) for the FRAMING. Renders
    via fmt_eod_verdict.

    Mark §3 honesty: if Supabase is unreachable / no trades data, the
    surface honestly says "לא נסגרו עסקאות היום" — never invent an R.
    """
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
    except Exception:
        df = pd.DataFrame()
    closed = are.compute_closed_campaigns(df) if not df.empty else []
    todays = are.compute_todays_R_summary(closed)
    settle = are.get_risk_settle_info() if hasattr(are, "get_risk_settle_info") else {}
    # Only check the suppression's frame when there IS a real R for
    # today (todays_R when n_trades==0 is meaningless for the rule).
    sup_todays_R = todays["total_R"] if todays.get("n_trades", 0) > 0 else None
    sup = es.should_suppress_engagement(
        todays_R=sup_todays_R,
        settle_info=settle,
    )
    body = tf.fmt_eod_verdict(todays, sup).lstrip("\n")
    bot.send_message(chat_id, body, parse_mode="Markdown")


def handle_gate_receipt(chat_id, n_days: int = 90):
    """`/gate_receipt` — C4-S1 Phase-1 pull surface.

    Reads `risk_recommendations.json` via `compute_gate_clamp_summary`,
    renders via `fmt_gate_receipt`. Honest empty-state when no clamps
    in the window (§C4 R1 — never invent a celebration). Mark §X6 —
    self-data only; no market commentary.
    """
    summary = are.compute_gate_clamp_summary(n_days=n_days)
    body = tf.fmt_gate_receipt(summary)
    if not body:
        # Honest empty-state. NOT a celebration line. The founder may
        # genuinely have zero in-window clamps and that is fine — we
        # surface the fact, no spin.
        text = (
            f"{RTL}🛡️ *קבלה מהשער*\n"
            f"{RTL}אין חסימות סיכון מתועדות ב-`{int(n_days)}` הימים האחרונים."
        )
    else:
        text = body.lstrip("\n")
    bot.send_message(chat_id, text, parse_mode="Markdown")
