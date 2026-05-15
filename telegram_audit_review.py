"""
Telegram UX for the user-facing audit-review surface — `🧾 הפעולות שלי`.

Why this module exists
----------------------
Sprint-11 finding #9 / DEC-20260515-008: there was no bot surface for the
user to review their OWN recorded decisions. `audit_logger` is write-only by
design; DEC-008 adds ONE deliberate additive SELECT-only read path
(`audit_logger.read_recent_actions`) and this thin presentation layer over
it. It mirrors `telegram_tasks` / `telegram_stop_promote` discipline:
additive module, re-exported into `telegram_bot.py`, routed in
`telegram_callbacks.py`. Pull-only — no Telegram push path (G5).

Red lines respected (Mark §4 / DEC-008 / AGENTS.md #1)
------------------------------------------------------
* SELECT-only: the only Supabase touch is `read_recent_actions` (cannot
  insert/update/delete). This module never writes anything.
* No fabricated performance numbers: it shows RECORDED ACTIONS, not computed
  returns. No win-rate / expectancy / PF / PnL / R aggregation is ever
  computed or shown here. No engine import in this surface.
* Honest source + most-recent-first: header states the source explicitly;
  ordering is the audit_log's own `created_at DESC`; a missing timestamp is
  labelled, never invented.
* Surfaces only user-decision action kinds (Mark §4.2 SURFACE list);
  operational/forensic kinds (`dev_pin_*` / `deploy_trigger` /
  `telegram_alert_send`) are omitted. New/unknown kinds default to a generic
  line, never fabricated detail.
* Admin-only via the existing message/callback gate; secure_runner untouched.
"""
from datetime import datetime

from telebot import types

import audit_logger
from bot_core import bot, supabase, RTL
from telegram_menus import get_portfolio_menu

# Mark §4.2 — the ONLY action kinds surfaced (user's own decisions). Anything
# not in this set is omitted (under-showing is honest; over-showing risks
# D3/D4). New constants default to OMIT until explicitly classified here.
_SURFACE_ACTIONS = [
    audit_logger.ACTION_RISK_PCT_CHANGE,
    audit_logger.ACTION_ADDON_CONFIRM,
    audit_logger.ACTION_MANUAL_TRADE,
    audit_logger.ACTION_SETTINGS_CHANGE,  # open-task lifecycle + stop-loosen
]

_DEFAULT_LIMIT = 20


def _fmt_ts(raw) -> str:
    """`DD/MM HH:MM` from the stored `created_at`. Honest: a missing/
    unparseable timestamp is labelled, never invented (Mark §4 D6)."""
    if not raw:
        return "זמן לא רשום"
    s = str(raw)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s.replace("Z", "+0000"), fmt).strftime(
                "%d/%m %H:%M"
            )
        except ValueError:
            continue
    # Last resort: a stable prefix of the stored value, never a fake time.
    try:
        return f"{s[8:10]}/{s[5:7]} {s[11:16]}"
    except Exception:
        return "זמן לא רשום"


def _friendly_line(row: dict) -> str:
    """Map ONE raw audit row → a friendly Hebrew line (SPRINT11_DESIGN §5.3
    table). Shows only the RECORDED action / literal before-after — never an
    aggregated or recomputed number (Mark §4 D3/D4)."""
    action = str(row.get("action", ""))
    meta = row.get("metadata") or {}
    before = row.get("before_state") or {}
    after = row.get("after_state") or {}
    sym = meta.get("symbol") or meta.get("campaign_id") or "—"

    if action == audit_logger.ACTION_RISK_PCT_CHANGE:
        b = before.get("risk_pct")
        a = after.get("risk_pct")
        return f"🎚️ שינוי % סיכון: {b}%→{a}%"

    if action == audit_logger.ACTION_SETTINGS_CHANGE:
        kind = str(meta.get("kind", ""))
        if kind == "stop_loosen_override":
            b = before.get("stop_loss")
            a = after.get("stop_loss")
            return f"🔓 ריפוי סטופ — {sym}: ${b}→${a}"
        if kind == "skipped_critical_exit":
            return f"⏭️ דילוג משימה — {sym}  🛑 P0"
        if kind == "open_task_skipped":
            return f"⏭️ דילוג משימה — {sym}"
        if kind == "open_task_done":
            tt = meta.get("task_type", "")
            return f"✅ משימה בוצעה — {sym} ({tt})"
        if kind == "open_task_note":
            return f"📝 הערה למשימה — {sym}"
        return f"• {action}"

    if action == audit_logger.ACTION_ADDON_CONFIRM:
        return f"➕ אישור Add-On — {sym}"

    if action == audit_logger.ACTION_MANUAL_TRADE:
        return f"🧾 עסקה ידנית — {sym}"

    # Recorded constant we surface but have no friendly mapping for — never
    # invent detail (Mark §4 D3).
    return f"• {action}"


def handle_my_actions(chat_id):
    """`🧾 הפעולות שלי` / `/myactions` — read-only retrospective review.

    Reads via the SELECT-only `audit_logger.read_recent_actions` (this module
    never writes). Most-recent-first, friendly Hebrew, NO fabricated
    performance numbers, honest timestamps & source label."""
    loading = bot.send_message(
        chat_id, f"{RTL}⏳ *טוען את הפעולות שלי...*", parse_mode="Markdown"
    )
    rows = audit_logger.read_recent_actions(
        supabase, chat_id=None, limit=_DEFAULT_LIMIT, actions=_SURFACE_ACTIONS
    )
    try:
        bot.delete_message(chat_id, loading.message_id)
    except Exception:
        pass

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 רענן", callback_data="myactions_refresh"),
        types.InlineKeyboardButton("⬅️ חזרה", callback_data="cancel_action"),
    )

    if rows is None:
        rows = []

    if not rows:
        # Empty ≠ error — never a fake row (Mark §4 D2/D6).
        bot.send_message(
            chat_id,
            f"{RTL}🧾 *הפעולות שלי*\n\n"
            f"{RTL}✅ אין פעולות מתועדות עדיין.",
            reply_markup=markup, parse_mode="Markdown",
        )
        return

    lines = [
        f"{RTL}🧾 *הפעולות שלי — {len(rows)} אחרונות*",
        f"{RTL}מקור: יומן ביקורת (audit_log) · ללא חישובי ביצועים",
        "",
    ]
    for r in rows:
        lines.append(f"{RTL}• {_fmt_ts(r.get('created_at'))}  {_friendly_line(r)}")
    lines.append("")
    lines.append(
        f"{RTL}(רשומות פעולה בלבד — לא ביצועים, לא רווח/הפסד."
    )
    lines.append(f"{RTL} מוצג כפי שנשמר ביומן הביקורת.)")

    bot.send_message(
        chat_id, "\n".join(lines), reply_markup=markup, parse_mode="Markdown"
    )
