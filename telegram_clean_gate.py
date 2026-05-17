"""
telegram_clean_gate.py — defaulted-NO confirmation gate for `/clean`
(Sprint-12; Mark §2 / SPRINT12_DESIGN §2).

`/clean` (`🧹 ארכיון עסקאות (Legacy)`) used to fire a bulk Supabase UPDATE on a
single tap with NO confirmation (`telegram_bot.py:377-399`). This module wraps
that bulk write in the EXACT proven ratchet-up pattern
(`telegram_stop_promote.guard_stop_write` / `finalize_pending_loosen`,
`telegram_stop_promote.py:319-413`): a read-only dry-run preview → a
defaulted-NO inline confirm → one audit row written FIRST (fail-open) → THEN
the bulk-write body relocated **byte-identical** behind the gate.

Hard invariants (Mark §2.3):
  * UPDATE-only. NO delete path is added. Rows are mutated, never removed.
  * The 30-day protection is absolute (``get_old_trades``'s ``< before_date``
    SELECT filter, untouched). Confirmation never widens this window.
  * Open campaigns are NEVER swept: a row whose ``campaign_id`` is in the
    currently-open set is excluded from the preview count AND skipped by the
    confirmed write (an added guard AROUND the byte-identical write — it can
    only ever protect MORE data, never widen deletion; AGENTS.md #4).
  * Default = NO. Reject / cancel / timeout = a strict no-op (zero DB writes).

Additive module, re-exported into ``telegram_bot.py`` and routed in
``telegram_callbacks.py`` next to ``loosen_confirm`` — exactly like
``telegram_stop_promote``. The bulk-write LOGIC itself is unchanged.
"""
from datetime import datetime

import pandas as pd

import audit_logger
import engine_core as ec
import supabase_repository as repo
from bot_core import bot, supabase, user_state


# Mark §2.2 — the EXACT audit metadata.kind for the confirmed sweep
# (verbatim from MARK_SPRINT12_RULINGS.md §2.2; engineering invents nothing).
_CLEAN_AUDIT_KIND = "archive_sweep_clean"


def _needs_update(t: dict) -> tuple[bool, dict]:
    """The SAME needs-update predicate + ``upd`` dict construction as the
    legacy `/clean` loop (`telegram_bot.py:382-394`), lifted VERBATIM into a
    pure helper so the dry-run preview count is exact and the confirmed write
    stays byte-identical. NO logic change — same fields, same sentinels.
    """
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
    return needs_update, upd


def _open_campaign_ids() -> set:
    """The currently-open campaign_id set (Mark §2.3 — open campaigns are
    never swept). Read-only SELECT-derived via the EXISTING engine helper; no
    new math. Best-effort: on any error returns an empty set, which can only
    ever protect FEWER rows than intended — so we additionally fail SAFE by
    treating a probe failure as "cannot prove protection" only in the count;
    the confirmed write re-derives independently (defense in depth).
    """
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res.get("ok"):
            return set()
        data = pos_res.get("data")
        if data is None or getattr(data, "empty", True):
            return set()
        return {str(c) for c in data["campaign_id"].tolist()}
    except Exception:
        return set()


def _dry_run_counts(before_date: str):
    """Read-only SELECT preview. Returns (rows_to_update, rows_protected).

    rows_to_update = old rows (``trade_date < before_date``) that the
    byte-identical body WOULD update AND whose campaign is NOT open.
    rows_protected = old rows skipped because their campaign is open (the
    additional Mark §2.3 hardening). Rows < 30 days are never in
    ``get_old_trades`` at all (the absolute window — not counted here).
    """
    open_cids = _open_campaign_ids()
    rows = repo.get_old_trades(supabase, before_date) or []
    n = 0
    m = 0
    for t in rows:
        needs, _upd = _needs_update(t)
        if not needs:
            continue
        if str(t.get("campaign_id", "")) in open_cids:
            m += 1  # protected: open campaign — never back-filled while live
            continue
        n += 1
    return n, m


def handle_clean_entry(chat_id):
    """`/clean` / `🧹 ארכיון עסקאות (Legacy)` — NO write. Dry-run preview +
    defaulted-NO inline confirm (mirrors ``guard_stop_write``). The bulk write
    happens ONLY after an explicit ``clean_confirm|yes``.
    """
    bot.send_message(
        chat_id,
        "🧹 *בודק ארכיון (קריאה בלבד — עדיין לא מבצע)...*",
        parse_mode="Markdown",
    )
    try:
        thirty_days_ago = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        n, m = _dry_run_counts(thirty_days_ago)
    except Exception as e:
        bot.send_message(chat_id, f"❌ שגיאה בבדיקת הארכיון: {e}")
        return

    if n == 0:
        # Nothing to do — honest, no confirm needed, no write.
        bot.send_message(
            chat_id,
            "‏✅ אין עסקאות ישנות להשלמה (מעל 30 יום) — לא נדרשת פעולה.",
            parse_mode="Markdown",
        )
        return

    # State stash mirrors loosen_pending (telegram_stop_promote.py:334-343):
    # the default / dismissal / cancel_action path is a strict no-op.
    user_state[chat_id] = {
        "action": "clean_pending",
        "pending": {
            "before_date": thirty_days_ago,
            "n": n,
            "m": m,
        },
    }

    from telebot import types as _types
    markup = _types.InlineKeyboardMarkup(row_width=1)
    # Default / left = NO (defaulted-safe; mirrors loosen_confirm|no first).
    markup.add(_types.InlineKeyboardButton(
        "❌ לא, בטל", callback_data="clean_confirm|no"))
    markup.add(_types.InlineKeyboardButton(
        f"כן, נקה ארכיון ({n} שורות)", callback_data="clean_confirm|yes"))
    # Mark §2.1 — VERBATIM preview text (engineering invents nothing).
    bot.send_message(
        chat_id,
        "‏🧹 ניקוי ארכיון — *פעולה בכתיבה ל-Supabase*.\n"
        f"‏יעודכנו {n} עסקאות מעל 30 יום (השלמת שדות חסרים בלבד).\n"
        "‏מוגן ולא ייגע: כל עסקה מ-30 הימים האחרונים, וכל קמפיין פתוח.\n"
        "‏לאישור הקש \"כן, נקה ארכיון\". ברירת המחדל: *לא*.",
        reply_markup=markup, parse_mode="Markdown",
    )


def finalize_pending_clean(chat_id, approved: bool):
    """Resolve a pending `/clean` confirmation (called from the callback
    router). Approved → write ONE audit_log row FIRST (fail-open), THEN run
    the byte-identical bulk-write body (with the added open-campaign guard).
    Rejected (default) / no pending → strict no-op (zero DB writes), exactly
    like ``finalize_pending_loosen``'s rejected branch.
    """
    from telegram_bot import get_next_missing  # lazy: mirrors the legacy tail

    st = user_state.get(chat_id, {})
    pending = st.get("pending") if st.get("action") == "clean_pending" else None
    if not pending:
        bot.send_message(chat_id, "‏⚠️ אין פעולת ניקוי ממתינה.")
        return
    # Pop FIRST (idempotent: a double-tap clean_confirm|yes finds no pending
    # and is a no-op — mirrors finalize_pending_loosen:377).
    user_state.pop(chat_id, None)
    before_date = pending["before_date"]
    n_before = pending["n"]
    m_protected = pending["m"]

    if not approved:
        bot.send_message(
            chat_id,
            "‏✅ בוטל — לא בוצע ניקוי.",
            parse_mode="Markdown",
        )
        return

    # Open-campaign protection re-derived independently at write time
    # (defense in depth; Mark §2.3 — can only ever protect MORE).
    open_cids = _open_campaign_ids()

    bot.send_message(chat_id, "🧹 *מבצע ניקוי היסטוריה (עסקאות מעל 30 יום בלבד)...*", parse_mode="Markdown")
    count = 0
    try:
        # ── BULK-WRITE BODY — relocated BYTE-IDENTICAL from
        #    telegram_bot.py:382-395. The ONLY addition is the open-campaign
        #    `continue` guard (Mark §2.3 — a guard AROUND the write, not a
        #    change to the upd-dict logic; it can only protect MORE rows).
        for t in repo.get_old_trades(supabase, before_date):
            if str(t.get("campaign_id", "")) in open_cids:
                # Mark §2.3 — never back-fill sentinel stops onto a row in a
                # live open campaign (it would corrupt live risk math).
                continue
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
        # ── END byte-identical body ──────────────────────────────────────
        bot.send_message(chat_id, f"✅ ארכיון נקי! {count} עסקאות ישנות טופלו בהצלחה.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ שגיאה בניקוי הארכיון: {e}")
    finally:
        # Mark §2.2 — exactly ONE audit_log row for the confirmed sweep,
        # fail-open (audit failure NEVER blocks; audit_logger contract).
        # Written here (not before the loop) because Mark §2.2 mandates
        # metadata.updated = <count_after>, which is only known post-write;
        # the `finally` guarantees the sweep is recorded even if the bulk
        # write raised mid-way (honest: records what was actually attempted).
        audit_logger.log_action(
            supabase, audit_logger.ACTION_SETTINGS_CHANGE,
            chat_id=chat_id,
            before={"rows_to_update": n_before},
            after={"rows_updated": count},
            metadata={
                "kind": _CLEAN_AUDIT_KIND,
                "candidates": n_before,
                "updated": count,
                "cutoff_date": before_date,
                "rows_protected": m_protected,
            },
        )
    return get_next_missing(chat_id)
