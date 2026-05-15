"""
Telegram UX for the Open Tasks (Action-Items) surface — `📋 משימות פתוחות`.

Why this module exists
----------------------
Day-3 audit: the founder asked for a "tasks split by symbol, sorted,
browsable" surface they could not find. The journal walker
(`get_next_missing`) is NOT that. This is — a pull-only, tap-only,
grouped/sorted list of what to do now, with a done/skip/note lifecycle.

It mirrors `telegram_stop_promote.py` exactly (additive module, re-exported
into `telegram_bot.py`, routed in `telegram_callbacks.py`). It is a *view +
lifecycle* over the engine's existing state — it adds **no** Telegram push
path (pull-only — preserves the risk_monitor anti-spam invariant, G5).

Red lines respected
--------------------
* Read-only over engine math: this module runs the EXISTING engine helpers
  to obtain `compute_position_state()` per open position (the same minimal
  data path risk_monitor / telegram_portfolio use) and hands the result to
  the pure `open_tasks.derive_tasks` — it computes no new R/NAV/campaign
  number itself.
* ALGO → info-only non-tappable row (Sentinel never instructs ALGO; mirrors
  `promote_algo_noop`).
* P0 skip requires a typed reason (reuse the `risk_reject_reason` free-text
  capture pattern) — a P0 BROKEN exit is never silently dropped.
* Done/skip use the defaulted-safe inline confirm (mirrors `loosen_confirm`).
* Honest stale/fallback labels (CLAUDE.md / AGENTS.md #1).
* Admin guard / secure runner untouched; `telegram_bot.py` not rewritten.
"""
from datetime import datetime, timezone

from telebot import types
import pandas as pd

import engine_core as ec
import open_tasks
import supabase_repository as repo
from bot_core import bot, supabase, user_state, RTL
from telegram_menus import get_portfolio_menu

# Urgency display bands (UX §2). The underlying tier stays the existing
# ALERT_PRIORITY P0–P3 — this is display mapping only (Mark K4 / G7).
_BAND_ORDER = ["P0", "P1", "P2", "P3", None]
_BAND_HEADER = {
    "P0": "🛑 דחוף",
    "P1": "⚠️ חשוב",
    "P2": "🟡 לתשומת לב",
    "P3": "🔵 מעקב",
    None: "ℹ️ נתונים חסרים",
}
_BAND_ICON = {
    "P0": "🛑",
    "P1": "⚠️",
    "P2": "🟡",
    "P3": "🔵",
    None: "ℹ️",
}


# ──────────────────────────────────────────────────────────────────────────────
# Data path — caller computes state_result (design §1.4), engine stays owner
# ──────────────────────────────────────────────────────────────────────────────


def _enrich_positions(records, *, target_risk_usd):
    """Attach `state_result` / `open_r` / `age_days` / `trail_stop` to each
    open-position record using the EXISTING engine helpers.

    This is the "callers compute data and pass it in" contract: open_tasks
    itself never calls the engine. The R/age numbers are the engine's own
    (get_campaign_risk_metrics / compute_position_state) — nothing recomputed
    here beyond the exact open-R formula already used across the bot.

    Returns (enriched_list, data_quality) where data_quality is one of
    "live" / "stale" (any price fell back to entry).
    """
    enriched = []
    data_quality = "live"
    for row in records:
        try:
            sym = row.get("symbol")
            entry = float(row.get("price", 0) or 0)
            qty = float(row.get("quantity", 0) or 0)
            sl = float(row.get("stop_loss", 0) or 0)
            setup = str(row.get("setup_type", "")).upper()
            side = "BUY"

            curr = ec.get_live_price(sym)
            if curr is None:
                curr = entry
                data_quality = "stale"

            metrics = ec.get_campaign_risk_metrics(dict(row))
            original_campaign_risk = metrics.get("original_risk", 0.0)

            open_pnl = (curr - entry) * qty
            if setup == "ALGO" and target_risk_usd > 0:
                open_r = open_pnl / target_risk_usd
            elif original_campaign_risk > 0:
                open_r = open_pnl / original_campaign_risk
            else:
                open_r = None

            try:
                _entry_dt = pd.to_datetime(
                    row.get("entry_date")
                ).to_pydatetime().replace(tzinfo=None)
                age_days = max(0.0, float((datetime.utcnow() - _entry_dt).days))
            except Exception:
                age_days = 0.0

            mgt_mode = ec.classify_management_mode(setup, sym)

            state_result = ec.compute_position_state(
                side=side,
                management_mode=mgt_mode,
                age_days=age_days,
                open_r=(open_r if open_r is not None else 0.0),
                realized_pnl=float(row.get("realized_pnl", 0) or 0),
                original_campaign_risk=original_campaign_risk,
                current_price=curr,
                current_stop=sl,
                days_to_earnings=None,
                follow_through_score=None,
                violation_score=0,
                has_new_high_since_entry=True,
                has_open_quantity=(qty > 0),
            )

            # RUNNER action embeds the engine's OWN suggested trail stop
            # verbatim — never a stop this module computes (G4).
            trail_stop = None
            if state_result.get("state") == ec.POSITION_STATE_RUNNER:
                try:
                    ma = ec.get_ma_levels(sym)
                    trail_stop = ec.compute_suggested_trail_stop(
                        side=side, current_price=curr,
                        ma21=ma.get("ma21"), ma50=ma.get("ma50"),
                        open_r=(open_r if open_r is not None else 0.0),
                        entry_price=entry,
                    )
                except Exception:
                    trail_stop = None

            rec = dict(row)
            rec["state_result"] = state_result
            rec["open_r"] = open_r
            rec["age_days"] = age_days
            rec["trail_stop"] = trail_stop
            rec["_data_quality"] = "stale" if curr == entry and ec.get_live_price(sym) is None else "live"
            enriched.append(rec)
        except Exception:
            # A single bad row must not blank the whole list (honesty: better
            # to show the rest than fake completeness).
            continue
    return enriched, data_quality


def _grouped_sorted(tasks):
    """Sort contract (UX §2): group by urgency (P0→P1→P2→P3→None), then
    symbol A→Z, then created_ts ascending (oldest unattended first)."""
    def key(t):
        try:
            band = _BAND_ORDER.index(t.urgency)
        except ValueError:
            band = len(_BAND_ORDER)
        return (band, str(t.symbol), str(t.created_ts))
    return sorted(tasks, key=key)


def _load_tasks(chat_id):
    """Load + derive + lifecycle-overlay the open tasks. Returns
    (tasks_sorted, data_quality, error_str|None). Lightweight — no heavy
    'חדר מצב' room, mirrors handle_stop_promote_entry."""
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"]:
            return [], "live", str(pos_res.get("error", "unknown"))
        open_pos = pos_res["data"]
        if open_pos.empty:
            return [], "live", None
        records = open_pos.to_dict("records")

        # Open-R for ALGO uses Target Risk base — read it the same lightweight
        # way the rest of the bot does (no NAV recompute here).
        target_risk_usd = 0.0
        try:
            from bot_helpers import get_account_settings, get_nav_and_risk
            _acc, target_risk_usd, _stale = get_nav_and_risk(get_account_settings())
        except Exception:
            target_risk_usd = 0.0

        enriched, data_quality = _enrich_positions(
            records, target_risk_usd=target_risk_usd
        )

        now = datetime.now(timezone.utc)
        tasks = open_tasks.list_tasks(supabase, enriched, now=now)
        # Stash for tap-only addressing (callback carries an index).
        open_only = [t for t in tasks if t.status == open_tasks.STATUS_OPEN]
        st = user_state.get(chat_id, {})
        st["task_records"] = [
            {
                "campaign_id": t.campaign_id,
                "task_type": t.task_type,
                "symbol": t.symbol,
                "urgency": t.urgency,
                "info_only": t.info_only,
                "recommended_action": t.recommended_action,
                "state": t.trigger_snapshot.state,
                "open_r": t.trigger_snapshot.open_r,
                "age_days": t.trigger_snapshot.age_days,
                "reason": t.trigger_snapshot.reason,
            }
            for t in _grouped_sorted(open_only)
        ]
        user_state[chat_id] = st
        return _grouped_sorted(open_only), data_quality, None
    except Exception as e:
        return [], "live", f"{type(e).__name__}: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# Keyboards
# ──────────────────────────────────────────────────────────────────────────────


def build_tasks_keyboard(tasks):
    """One tap-only inline row per task (reuse build_stop_promote_keyboard's
    one-button-per-row pattern). ALGO/info-only rows are non-tappable info
    buttons (callback task_algo_noop), exactly like promote_algo_noop."""
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, t in enumerate(tasks):
        icon = _BAND_ICON.get(t.urgency, "•")
        short = t.recommended_action
        if len(short) > 48:
            short = short[:47] + "…"
        if t.info_only:
            markup.add(types.InlineKeyboardButton(
                f"🟠 {t.symbol} — {short}",
                callback_data="task_algo_noop",
            ))
            continue
        markup.add(types.InlineKeyboardButton(
            f"{icon} {t.symbol} — {short}",
            callback_data=f"task_open|{idx}",
        ))
    markup.add(types.InlineKeyboardButton("🔄 רענן", callback_data="task_refresh"))
    markup.add(types.InlineKeyboardButton("❌ סגור", callback_data="cancel_action"))
    return markup


def _detail_keyboard(idx, urgency, info_only):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if info_only:
        markup.add(types.InlineKeyboardButton(
            "⬅️ חזרה לרשימה", callback_data="task_open|list"))
        return markup
    markup.add(
        types.InlineKeyboardButton("✅ בוצע", callback_data=f"task_done|{idx}"),
        types.InlineKeyboardButton("⏭️ דלג", callback_data=f"task_skip|{idx}"),
    )
    markup.add(types.InlineKeyboardButton(
        "📝 הוסף הערה", callback_data=f"task_note|{idx}"))
    markup.add(types.InlineKeyboardButton(
        "⬅️ חזרה לרשימה", callback_data="task_open|list"))
    return markup


def _confirm_keyboard(kind, idx):
    """Defaulted-safe inline confirm (mirrors loosen_confirm|yes/no)."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    if kind == "done":
        markup.add(
            types.InlineKeyboardButton(
                "✅ כן, בוצע", callback_data=f"task_done_confirm|{idx}|yes"),
            types.InlineKeyboardButton(
                "↩️ עוד לא", callback_data=f"task_done_confirm|{idx}|no"),
        )
    else:  # skip (P1–P3)
        markup.add(
            types.InlineKeyboardButton(
                "⏭️ דלג", callback_data=f"task_skip_confirm|{idx}|yes"),
            types.InlineKeyboardButton(
                "↩️ ביטול", callback_data=f"task_skip_confirm|{idx}|no"),
        )
    return markup


# ──────────────────────────────────────────────────────────────────────────────
# Entry + list
# ──────────────────────────────────────────────────────────────────────────────


def _data_label(data_quality):
    return {"live": "חי 🟢", "stale": "מאוחסן ⚠️"}.get(data_quality, "מוערך ⛔")


def handle_open_tasks_entry(chat_id):
    """`📋 משימות פתוחות` / `/tasks` entry — lightweight, pull-only."""
    loading = bot.send_message(chat_id, f"{RTL}⏳ *טוען משימות פתוחות...*",
                               parse_mode="Markdown")
    tasks, data_quality, error = _load_tasks(chat_id)

    try:
        bot.delete_message(chat_id, loading.message_id)
    except Exception:
        pass

    if error is not None:
        # Honest infra-error: absence of list ≠ absence of tasks (CLAUDE.md;
        # mirrors handle_stop_promote_entry's infra-error message).
        bot.send_message(
            chat_id,
            f"{RTL}📋 *משימות פתוחות*\n"
            f"{RTL}❌ לא ניתן לטעון משימות כרגע (שגיאת תשתית).\n"
            f"{RTL}לא מוצגות משימות — זה *לא* אומר שאין.\n"
            f"{RTL}פרטים: `{error}`\n"
            f"{RTL}נסה שוב, או בדוק /health.",
            reply_markup=get_portfolio_menu(), parse_mode="Markdown",
        )
        return

    if not tasks:
        bot.send_message(
            chat_id,
            f"{RTL}📋 *משימות פתוחות*\n\n"
            f"{RTL}✅ אין משימות פתוחות.\n"
            f"{RTL}התיק תחת שליטה — אין פעולה נדרשת כרגע.",
            reply_markup=get_portfolio_menu(), parse_mode="Markdown",
        )
        return

    actionable = [t for t in tasks if not t.info_only]
    info_only = [t for t in tasks if t.info_only]
    symbols = sorted({t.symbol for t in tasks})
    ts_str = datetime.now().strftime("%d/%m %H:%M")

    if not actionable and info_only:
        # ALGO-only / data-incomplete-only → info-only screen (UX §5b).
        header = (
            f"{RTL}📋 *משימות פתוחות*\n\n"
            f"{RTL}🟠 כל הפוזיציות הפתוחות מנוהלות חיצונית/חסרות נתונים.\n"
            f"{RTL}Sentinel אינו מנפיק משימות פעולה — מעקב בלבד:\n"
        )
    else:
        header = (
            f"{RTL}📋 *משימות פתוחות — {len(tasks)} משימות "
            f"({len(symbols)} סימולים)*\n"
            f"{RTL}מעודכן: {ts_str} · נתונים: {_data_label(data_quality)}\n"
        )
        if data_quality != "live":
            header += (
                f"{RTL}⚠️ נתונים חלקיים — אמת מול IBKR לפני פעולה. "
                f"P0 לא נטען כוודאי על נתון מאוחסן.\n"
            )

    bot.send_message(chat_id, header,
                     reply_markup=build_tasks_keyboard(tasks),
                     parse_mode="Markdown")


def _get_record(chat_id, idx):
    st = user_state.get(chat_id, {})
    recs = st.get("task_records") or []
    if not (0 <= idx < len(recs)):
        return None
    return recs[idx]


def handle_task_open(chat_id, raw_idx):
    """Tapping a row → detail card (or 'list' → re-render the list)."""
    if raw_idx == "list":
        handle_open_tasks_entry(chat_id)
        return
    try:
        idx = int(raw_idx)
    except (TypeError, ValueError):
        bot.send_message(chat_id, f"{RTL}❌ בחירה לא תקינה.", parse_mode="Markdown")
        return
    rec = _get_record(chat_id, idx)
    if rec is None:
        bot.send_message(chat_id, f"{RTL}⚠️ הרשימה פגה. פותח מחדש...",
                         parse_mode="Markdown")
        handle_open_tasks_entry(chat_id)
        return

    open_r = rec.get("open_r")
    age_days = rec.get("age_days")
    r_str = f"{open_r:+.2f}R" if isinstance(open_r, (int, float)) else "לא זמין (חסר סיכון מקורי)"
    age_str = f"{age_days:.0f} ימים" if isinstance(age_days, (int, float)) else "לא זמין"

    body = (
        f"{RTL}{_BAND_ICON.get(rec.get('urgency'), '•')} *{rec.get('symbol')} — משימה*\n\n"
        f"{RTL}🔎 *מה קרה:*\n"
        f"{RTL}• מצב: `{rec.get('state')}`\n"
        f"{RTL}• Open-R: `{r_str}` _(snapshot — לא מאומת כעת)_\n"
        f"{RTL}• בקמפיין: {age_str}\n"
        f"{RTL}• סיבת מנוע: _{rec.get('reason') or '—'}_\n\n"
        f"{RTL}🎯 *פעולה מומלצת:*\n"
        f"{RTL}{rec.get('recommended_action')}\n\n"
    )
    if rec.get("info_only"):
        body += f"{RTL}(מידע בלבד — Sentinel אינו מבצע ואינו ממליץ פעולה כאן.)"
    else:
        body += (
            f"{RTL}(המלצה בלבד. Sentinel לא מבצע מסחר —\n"
            f"{RTL} בצע ב-IBKR ואז סמן כאן ✅ בוצע.)"
        )
    bot.send_message(
        chat_id, body,
        reply_markup=_detail_keyboard(idx, rec.get("urgency"), rec.get("info_only")),
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Done / Skip / Note
# ──────────────────────────────────────────────────────────────────────────────


def handle_task_done(chat_id, idx):
    """Step 1 of done — defaulted-safe confirm (mirrors guard_stop_write)."""
    rec = _get_record(chat_id, idx)
    if rec is None:
        handle_open_tasks_entry(chat_id)
        return
    bot.send_message(
        chat_id,
        f"{RTL}✅ *לסמן בוצע? — {rec.get('symbol')}*\n"
        f"{RTL}\"{rec.get('recommended_action')}\"\n\n"
        f"{RTL}האם ביצעת את הפעולה?",
        reply_markup=_confirm_keyboard("done", idx), parse_mode="Markdown",
    )


def handle_task_done_confirm(chat_id, idx, approved):
    rec = _get_record(chat_id, idx)
    if rec is None:
        handle_open_tasks_entry(chat_id)
        return
    if not approved:
        bot.send_message(chat_id, f"{RTL}↩️ ללא שינוי.", parse_mode="Markdown")
        handle_task_open(chat_id, idx)
        return
    ok = open_tasks.mark_done(
        supabase, rec["campaign_id"], rec["task_type"],
    )
    status = "✅ סומן כבוצע" if ok else "⚠️ שמירה נכשלה (נסה שוב)"
    bot.send_message(
        chat_id,
        f"{RTL}{status} — {rec.get('symbol')}.",
        parse_mode="Markdown",
    )
    handle_open_tasks_entry(chat_id)


def handle_task_skip(chat_id, idx):
    """Skip. P0 requires a TYPED reason (reuse risk_reject_reason free-text
    capture). P1–P3 → defaulted-safe confirm."""
    rec = _get_record(chat_id, idx)
    if rec is None:
        handle_open_tasks_entry(chat_id)
        return
    if rec.get("urgency") == "P0":
        # P0 skip is the highest-methodology-risk action — a confirm is NOT
        # enough; an explicit logged reason is mandatory (spec §3 / G8).
        user_state.setdefault(chat_id, {})
        user_state[chat_id]["action"] = "task_skip_reason"
        user_state[chat_id]["task_idx"] = idx
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ ביטול דילוג", callback_data="cancel_action"))
        bot.send_message(
            chat_id,
            f"{RTL}🛑 *דילוג על P0 — {rec.get('symbol')}*\n"
            f"{RTL}דילוג על משימה דחופה דורש סיבה מפורשת\n"
            f"{RTL}(תירשם ביומן השיטה).\n\n"
            f"{RTL}📝 כתוב מדוע אתה מדלג:",
            reply_markup=markup, parse_mode="Markdown",
        )
        return
    bot.send_message(
        chat_id,
        f"{RTL}⏭️ *לדלג על המשימה? — {rec.get('symbol')}*\n"
        f"{RTL}\"{rec.get('recommended_action')}\"",
        reply_markup=_confirm_keyboard("skip", idx), parse_mode="Markdown",
    )


def handle_task_skip_confirm(chat_id, idx, approved):
    rec = _get_record(chat_id, idx)
    if rec is None:
        handle_open_tasks_entry(chat_id)
        return
    if not approved:
        bot.send_message(chat_id, f"{RTL}↩️ הדילוג בוטל.", parse_mode="Markdown")
        handle_task_open(chat_id, idx)
        return
    ok = open_tasks.skip_task(
        supabase, rec["campaign_id"], rec["task_type"],
        urgency=rec.get("urgency"),
    )
    status = "⏭️ המשימה דולגה ונרשמה" if ok else "⚠️ שמירה נכשלה"
    bot.send_message(chat_id, f"{RTL}{status} — {rec.get('symbol')}.",
                     parse_mode="Markdown")
    handle_open_tasks_entry(chat_id)


def handle_task_skip_reason(chat_id, reason):
    """Top-of-handler branch (telegram_bot.py) calls this with the typed P0
    skip reason. Empty/blank → re-prompt (cannot silently bypass a P0
    guardrail — spec §3.b.4 / G8)."""
    st = user_state.get(chat_id, {})
    idx = st.get("task_idx")
    rec = _get_record(chat_id, idx) if idx is not None else None
    if rec is None:
        user_state.pop(chat_id, None)
        bot.send_message(chat_id, f"{RTL}⚠️ המשימה כבר אינה זמינה.",
                         reply_markup=get_portfolio_menu(), parse_mode="Markdown")
        return
    if not reason or not reason.strip():
        # Re-prompt; do NOT skip.
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "↩️ ביטול דילוג", callback_data="cancel_action"))
        bot.send_message(
            chat_id,
            f"{RTL}🛑 סיבה ריקה אינה מתקבלת.\n"
            f"{RTL}📝 כתוב מדוע אתה מדלג (חובה ל-P0):",
            reply_markup=markup, parse_mode="Markdown",
        )
        return
    user_state.pop(chat_id, None)
    open_tasks.skip_task(
        supabase, rec["campaign_id"], rec["task_type"],
        note=reason.strip(), urgency="P0",
    )
    bot.send_message(
        chat_id,
        f"{RTL}📝 *הדילוג נרשם — {rec.get('symbol')}*\n"
        f"{RTL}סיבה: _{reason.strip()}_\n"
        f"{RTL}(נרשם כ-skipped\\_critical\\_exit ביומן הביקורת.)",
        reply_markup=get_portfolio_menu(), parse_mode="Markdown",
    )
    handle_open_tasks_entry(chat_id)


def handle_task_note(chat_id, idx):
    """Add-note → free-text capture (same pattern as risk_reject_reason)."""
    rec = _get_record(chat_id, idx)
    if rec is None:
        handle_open_tasks_entry(chat_id)
        return
    user_state.setdefault(chat_id, {})
    user_state[chat_id]["action"] = "task_add_note"
    user_state[chat_id]["task_idx"] = idx
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("↩️ ביטול", callback_data="cancel_action"))
    bot.send_message(
        chat_id,
        f"{RTL}📝 כתוב הערה למשימה ({rec.get('symbol')}):",
        reply_markup=markup, parse_mode="Markdown",
    )


def handle_task_add_note(chat_id, note):
    """Top-of-handler branch (telegram_bot.py) calls this with typed note."""
    st = user_state.get(chat_id, {})
    idx = st.get("task_idx")
    rec = _get_record(chat_id, idx) if idx is not None else None
    user_state.pop(chat_id, None)
    if rec is None:
        bot.send_message(chat_id, f"{RTL}⚠️ המשימה כבר אינה זמינה.",
                         reply_markup=get_portfolio_menu(), parse_mode="Markdown")
        return
    if not note or not note.strip():
        bot.send_message(chat_id, f"{RTL}⚠️ הערה ריקה — לא נשמרה.",
                         reply_markup=get_portfolio_menu(), parse_mode="Markdown")
        return
    ok = open_tasks.add_note(
        supabase, rec["campaign_id"], rec["task_type"], note.strip(),
    )
    status = "✅ ההערה נשמרה" if ok else "⚠️ שמירה נכשלה"
    bot.send_message(chat_id, f"{RTL}{status} — {rec.get('symbol')}.",
                     parse_mode="Markdown")
    handle_task_open(chat_id, idx)
