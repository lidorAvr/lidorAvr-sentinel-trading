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
import time
from datetime import datetime, timezone

from telebot import types
import pandas as pd

import engine_core as ec
import adaptive_risk_engine as are
import open_tasks
import algo_rules  # Sprint-17 #4/#5 — static §1 known-rule lookup (pure leaf)
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

# #3 / SPRINT11_DESIGN §1.3 — cache staleness TTL. 180s matches the
# engine_core YF_CACHE TTL (DEC-20260509-001 / -003 cadence) so the rendered
# snapshot never out-lives the price layer it was derived from. A cache hit
# serves ONLY lifecycle re-renders; explicit refresh / TTL-exceeded / absent
# cache always re-derives via the full engine pipeline (engine = source of
# truth on every true build).
_TASKS_CACHE_TTL_S = 180

# #2 / Mark §3 — the SINGLE Mark-approved honest snapshot label. Used wherever
# the snapshot value is shown (detail card today; the cached header reuses the
# same one source). States plainly: value at task creation; the live list
# re-derives every open. No "verification pending" (that was the soft
# fallback-as-truth the founder flagged).
_SNAPSHOT_LABEL = "‏(ערך בעת יצירת המשימה — הרשימה מחושבת מחדש בכל פתיחה)"

# #4 / SPRINT11_DESIGN §2.2 — short inline-button tag per task_type (≤14
# RTL chars, Hebrew noun-phrase — NOT the methodology sentence; the full
# recommended_action stays in the detail card only). Methodology-neutral
# display sugar (Mark: confirmed methodology-neutral, SPRINT11_DESIGN §2.1).
_TASK_SHORT_TAG = {
    "EXECUTE_EXIT": "‏סגור עכשיו",
    "PROTECT_RUNNER_PROFIT": "‏הדק (Runner)",
    "TIGHTEN_STOP_PROFIT": "‏הדק 2R+",
    "REVIEW_YELLOW_FLAG": "‏דגל צהוב",
    "TRIM_OR_EXIT_DEAD_MONEY": "‏הון מת",
    "COMPLETE_RISK_DATA": "‏השלם נתונים",
    # T7 / Sprint-12 / Mark §1 — ≤14 RTL chars info-row label for the
    # portfolio drawdown ack (display sugar only; same rule as the tags
    # above — not the methodology sentence).
    open_tasks.TASK_ACK_DRAWDOWN_CUT: "‏אשר ירידת תיק",
}

# #5 / DEC-006 — the single consolidated ALGO panel callback. NOT a Task,
# no lifecycle, never counted (Mark §2.3 hard rules).
_ALGO_PANEL_CB = "task_algo_panel"


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
            # DEC-20260515-007: the already-stored campaign stop + side, so
            # open_tasks.derive_tasks can compare it against the engine's OWN
            # suggested trail stop (read-only no-op RUNNER suppression). This
            # is the value already fed to the engine — no new math here (G1).
            rec["current_stop"] = sl
            rec["side"] = side
            # #5 / DEC-006 / Mark §2.2 — ALGO observation read-out fields,
            # populated ONLY for an engine-observed ALGO position and ONLY
            # from the engine's already-existing observation (Mark §2.3 hard
            # rule #5: never the discretionary ladder; engine_core.py:457-462
            # returns suggested_stop=None for ALGO and that is respected
            # literally — no Sentinel-originated stop, ever).
            if state_result.get("state") == ec.POSITION_STATE_ALGO_OBSERVED:
                try:
                    risk_basis = ec.classify_risk_basis(
                        sl, entry, setup, target_risk_usd
                    )
                except Exception:
                    risk_basis = "Unknown"
                # External stop: only if ALGO actually exposes one (a real
                # positive stored stop). Else "Unknown" — NEVER $0.00, never
                # a Sentinel suggestion (Mark §2.3 #4 / DECISIONS.md:444-445).
                ext_stop = sl if (isinstance(sl, (int, float)) and sl > 0) else None
                # Sprint-17 #4 — replace the bare "Unknown" with the ALGO's OWN
                # §1 known rule (observed, NOT enforced by Sentinel). Unknown
                # symbol → None, so the panel keeps "Unknown" (never fabricate).
                # Pure static lookup — no I/O, no math, observation-only.
                known_rule = algo_rules.describe_algo_risk_control(sym)
                # Sprint-17 #5 — strategy-adaptive ALGO dead-money = the ALGO's
                # OWN §1 time-exit (QQQ/HOOD/PLTR). TSLA/JPM → None (no ALGO
                # time-exit; the generic 0.75R is NOT applied to ALGO). This is
                # a descriptive note only, never an instruction, never a Task,
                # never counted (#8-safe — open-position observer only).
                time_exit_sig = algo_rules.algo_time_exit_signal(sym)
                rec["_algo_observed"] = {
                    "symbol": sym,
                    # The engine's OWN state label, verbatim
                    # (engine_core.py:1680 / state_result["label"]).
                    "state_label": state_result.get(
                        "label", ec._STATE_LABELS.get(
                            ec.POSITION_STATE_ALGO_OBSERVED, "ALGO")
                    ),
                    "risk_basis": risk_basis,
                    "external_stop": ext_stop,
                    # #4 known-rule descriptor (observed, not enforced).
                    "known_rule": known_rule,
                    # #5 ALGO dead-money signal source (None for TSLA/JPM).
                    "algo_time_exit": time_exit_sig,
                }
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

        # T7 / Sprint-12 / Mark §1 — read-only over the engine's OWN drawdown
        # output. This is the SAME call risk_monitor.py already makes
        # (adaptive_risk_engine.drawdown_auto_cut_recommendation); we add ZERO
        # new R/NAV/PnL/drawdown math (Mark §1.1; G1) and ZERO push (pull-only;
        # risk_monitor untouched — Mark §1.5). If it returns None there is no
        # T7 (never fabricate an ack for a cut that did not happen).
        portfolio_drawdown = None
        risk_settle_active = None
        try:
            from bot_helpers import (
                get_account_settings as _gas,
                get_nav_and_risk as _gnr,
            )
            _acc_s = _gas()
            _nav, _tr, _ = _gnr(_acc_s)
            _cur_risk_pct = float(_acc_s.get("risk_pct_input", 0.5))
            _closed = are.compute_closed_campaigns(df)
            portfolio_drawdown = are.drawdown_auto_cut_recommendation(
                _closed, _cur_risk_pct, _nav
            )
            risk_settle_active = bool(
                are.get_risk_settle_info().get("active", False)
            )
        except Exception:
            # Honest: a failed read-only probe must not blank the list and
            # must not fabricate a T7 (absence ≠ a task; AGENTS.md #1).
            portfolio_drawdown = None
            risk_settle_active = None

        now = datetime.now(timezone.utc)
        tasks = open_tasks.list_tasks(
            supabase, enriched, now=now,
            portfolio_drawdown=portfolio_drawdown,
            risk_settle_active=risk_settle_active,
        )
        # Stash for tap-only addressing (callback carries an index).
        open_only = _grouped_sorted(
            [t for t in tasks if t.status == open_tasks.STATUS_OPEN]
        )
        # Engine ALGO-observed read-out, keyed by campaign_id — carried onto
        # the cached record so handle_algo_panel reads the snapshot, never
        # re-derives (Mark §2.2 / SPRINT11_DESIGN §3.3; G1).
        algo_by_cid = {
            str(r.get("campaign_id", "")): r["_algo_observed"]
            for r in enriched
            if isinstance(r.get("_algo_observed"), dict)
        }
        cached_records = []
        for t in open_only:
            rec = {
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
                # #3 lifecycle-in-place projection fields (default open).
                "status": open_tasks.STATUS_OPEN,
                "closed_local_ts": None,
            }
            if (
                t.task_type == "ALGO_OBSERVE_ONLY"
                and str(t.campaign_id) in algo_by_cid
            ):
                rec["_algo_observed"] = algo_by_cid[str(t.campaign_id)]
            # T7 / Mark §1.4 — carry the current drawdown episode token so the
            # ack records WHICH episode the user acknowledged (append-only on
            # the existing lifecycle row; no schema change).
            if (
                t.task_type == open_tasks.TASK_ACK_DRAWDOWN_CUT
                and t.campaign_id == open_tasks.PORTFOLIO_CID
            ):
                rec["_t7_episode_note"] = open_tasks.t7_episode_note(
                    portfolio_drawdown
                )
            cached_records.append(rec)

        built_ts = time.time()
        built_iso = datetime.now().strftime("%d/%m %H:%M")
        st = user_state.get(chat_id, {})
        # #3 / SPRINT11_DESIGN §1.2 — explicit, invalidatable task cache.
        # `records` replaces today's `task_records` (backward-shaped); the
        # whole derived set is one snapshot keyed by chat_id, exactly like
        # `temp_positions` is one list.
        st["tasks_cache"] = {
            "records": cached_records,
            "enriched": enriched,
            "data_quality": data_quality,
            "built_ts": built_ts,
            "built_iso": built_iso,
        }
        # Back-compat alias: anything still reading task_records sees the
        # same list (no behaviour change for existing callers).
        st["task_records"] = cached_records
        user_state[chat_id] = st
        return open_only, data_quality, None
    except Exception as e:
        return [], "live", f"{type(e).__name__}: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# #3 — cache-and-update-in-place (mirrors telegram_stop_promote temp_positions)
# ──────────────────────────────────────────────────────────────────────────────


def _cache_valid(chat_id):
    """True iff a fresh-enough tasks_cache exists for chat_id.

    A cache hit serves ONLY lifecycle re-renders. Invalid (absent / TTL
    exceeded) → the caller must re-derive via the full engine pipeline
    (SPRINT11_DESIGN §1.3 — engine stays the source of truth on every true
    build). Lifecycle actions never invalidate (a status flip changes user
    intent in open_tasks, not engine position state).
    """
    st = user_state.get(chat_id, {})
    cache = st.get("tasks_cache")
    if not cache or not isinstance(cache, dict):
        return False
    built_ts = cache.get("built_ts")
    if not isinstance(built_ts, (int, float)):
        return False
    return (time.time() - built_ts) <= _TASKS_CACHE_TTL_S


def _short_label(rec):
    """#4 / SPRINT11_DESIGN §2.2 — short inline-button text.

    `{glyph} {SYM} — {≤14-char tag}`. The tag is a fixed Hebrew noun-phrase
    keyed by task_type (display sugar, NOT methodology text). Unknown/future
    task_type → a 14-char trim of recommended_action (current behaviour, now
    at 14 not 48). The detail card always carries the FULL recommended_action,
    so truncation never loses information (SPRINT11_DESIGN §2.2).
    """
    tag = _TASK_SHORT_TAG.get(rec.get("task_type"))
    if tag is None:
        ra = str(rec.get("recommended_action", ""))
        tag = ra[:14] if len(ra) <= 14 else ra[:13] + "…"
    icon = _BAND_ICON.get(rec.get("urgency"), "•")
    return f"{icon} {rec.get('symbol')} — {tag}"


def _rec_view(t):
    """Normalize a Task OR a cached record dict into the dict shape the
    render path expects (so the cache hit and the fresh-build path render
    identically; existing Task-returning callers/tests stay green)."""
    if isinstance(t, dict):
        return t
    return {
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
        "status": getattr(t, "status", open_tasks.STATUS_OPEN),
        "closed_local_ts": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Keyboards
# ──────────────────────────────────────────────────────────────────────────────


def build_tasks_keyboard(tasks):
    """One tap-only inline row per task. #4: short label
    `{glyph} {SYM} — {tag}` (full text only in the detail card). #5/DEC-006:
    all ALGO_OBSERVE_ONLY info-only items collapse into ONE consolidated
    `task_algo_panel` entry (NOT a Task, never counted) — the per-row
    task_algo_noop dead-end popup is removed. Accepts Task objects OR cached
    record dicts (duck-typed via _rec_view)."""
    markup = types.InlineKeyboardMarkup(row_width=1)
    views = [_rec_view(t) for t in tasks]
    algo_count = 0
    for idx, rec in enumerate(views):
        if rec.get("info_only") and rec.get("task_type") == "ALGO_OBSERVE_ONLY":
            # #5 / DEC-006 / Mark §2.3 #1 — never a per-row tappable Task;
            # consolidated into one panel entry below. No task_algo_noop.
            algo_count += 1
            continue
        if rec.get("info_only"):
            # Non-ALGO info-only (e.g. DATA_INCOMPLETE) keeps the existing
            # non-tappable info row pattern.
            markup.add(types.InlineKeyboardButton(
                f"🟠 {rec.get('symbol')} — {_short_label(rec)}",
                callback_data="task_algo_noop",
            ))
            continue
        markup.add(types.InlineKeyboardButton(
            _short_label(rec),
            callback_data=f"task_open|{idx}",
        ))
    if algo_count:
        # #5 / DEC-006 — ONE consolidated, non-Task ALGO control. It carries
        # no index (it is the whole ALGO set), opens a read-out card via
        # handle_algo_panel (observation-only; Mark §2.2/§2.3).
        markup.add(types.InlineKeyboardButton(
            f"🤖 ALGO ({algo_count}) — בקרה",
            callback_data=_ALGO_PANEL_CB,
        ))
    markup.add(types.InlineKeyboardButton("🔄 רענן", callback_data="task_refresh"))
    markup.add(types.InlineKeyboardButton("❌ סגור", callback_data="cancel_action"))
    return markup


def _detail_keyboard(idx, urgency, info_only, task_type=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if info_only:
        markup.add(types.InlineKeyboardButton(
            "⬅️ חזרה לרשימה", callback_data="task_open|list"))
        return markup
    if task_type == open_tasks.TASK_ACK_DRAWDOWN_CUT:
        # T7 / Mark §1.4 + SPRINT12_DESIGN §1.4 — ACK-ONLY. It is an
        # acknowledgement, not a decision with alternatives: ONE explicit
        # "✅ הבנתי" affordance routed through the EXISTING task_done|{idx}
        # path (unchanged authoritative write + fail-open audit). NO skip,
        # NO note (⟨MARK: confirm T7 is ack-only — acknowledge, never
        # skip/note⟩ — Mark §1.4 "Requires explicit user 'done'").
        markup.add(types.InlineKeyboardButton(
            "✅ הבנתי", callback_data=f"task_done|{idx}"))
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


def _open_views_from_cache(chat_id):
    """Open (non-closed) cached record dicts for re-render. Drops rows the
    user already acted on locally (status != open) so a done/skip row leaves
    the list immediately (SPRINT11_DESIGN §1.2 step 3)."""
    cache = user_state.get(chat_id, {}).get("tasks_cache") or {}
    recs = cache.get("records") or []
    return [
        r for r in recs
        if r.get("status", open_tasks.STATUS_OPEN) == open_tasks.STATUS_OPEN
    ]


def _render_tasks_list(chat_id, tasks, data_quality):
    """Render the list message + keyboard from a normalized task collection
    (Task objects on a fresh build OR cached dict records on a cache hit —
    one render path, identical output)."""
    if not tasks:
        bot.send_message(
            chat_id,
            f"{RTL}📋 *משימות פתוחות*\n\n"
            f"{RTL}✅ אין משימות פתוחות.\n"
            f"{RTL}התיק תחת שליטה — אין פעולה נדרשת כרגע.",
            reply_markup=get_portfolio_menu(), parse_mode="Markdown",
        )
        return

    views = [_rec_view(t) for t in tasks]
    actionable = [v for v in views if not v.get("info_only")]
    info_only = [v for v in views if v.get("info_only")]
    symbols = sorted({v.get("symbol") for v in views})
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
            f"{RTL}📋 *משימות פתוחות — {len(views)} משימות "
            f"({len(symbols)} סימולים)*\n"
            f"{RTL}מעודכן: {ts_str} · נתונים: {_data_label(data_quality)}\n"
            # #2 — single Mark-approved honest snapshot label (one source).
            f"{RTL}{_SNAPSHOT_LABEL}\n"
        )
        if data_quality != "live":
            header += (
                f"{RTL}⚠️ נתונים חלקיים — אמת מול IBKR לפני פעולה. "
                f"P0 לא נטען כוודאי על נתון מאוחסן.\n"
            )

    bot.send_message(chat_id, header,
                     reply_markup=build_tasks_keyboard(views),
                     parse_mode="Markdown")


def handle_open_tasks_entry(chat_id):
    """`📋 משימות פתוחות` / `/tasks` entry — lightweight, pull-only.

    #3: serves from the cached snapshot when it is still fresh (≤TTL); a true
    re-derive (full engine pipeline) runs only on cache-absent / TTL-exceeded
    (the engine stays the single source of truth on every true build). The
    explicit 🔄 רענן button always re-derives (handle_task_refresh)."""
    if _cache_valid(chat_id):
        cache = user_state[chat_id]["tasks_cache"]
        _render_tasks_list(
            chat_id, _open_views_from_cache(chat_id), cache.get("data_quality"))
        return

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

    _render_tasks_list(chat_id, tasks, data_quality)


def handle_task_refresh(chat_id):
    """Explicit 🔄 רענן — ALWAYS discards the cache and re-derives via the
    full engine pipeline (SPRINT11_DESIGN §1.3 — the user-facing "engine is
    the source of truth" lever; the cached status flip never survives a
    refresh the DB overlay contradicts)."""
    st = user_state.get(chat_id, {})
    st.pop("tasks_cache", None)
    st.pop("task_records", None)
    user_state[chat_id] = st
    handle_open_tasks_entry(chat_id)


def _get_record(chat_id, idx):
    st = user_state.get(chat_id, {})
    recs = st.get("task_records") or []
    if not (0 <= idx < len(recs)):
        return None
    return recs[idx]


def _apply_local_status(chat_id, idx, status):
    """#3 / SPRINT11_DESIGN §1.2 — in-place lifecycle mutate + re-render.

    The authoritative Supabase write is STILL done by the caller via
    open_tasks.mark_done/skip_task (unchanged, audited) — only the *re-render*
    is served from the cache. This mutates ONLY the acted row's status (other
    rows + `enriched` untouched), drops it from the visible list, and
    re-renders straight from the cached records: zero engine call, zero
    network, header counts recomputed from the cached list.

    Cache-miss is always safe: fall back to a full re-derive (never a hard
    error; SPRINT11_DESIGN §1.2 step 1)."""
    st = user_state.get(chat_id, {})
    cache = st.get("tasks_cache")
    if not cache or not isinstance(cache, dict) or not cache.get("records"):
        handle_open_tasks_entry(chat_id)
        return
    recs = cache["records"]
    if 0 <= idx < len(recs):
        recs[idx]["status"] = status
        recs[idx]["closed_local_ts"] = datetime.now().strftime("%d/%m %H:%M")
    user_state[chat_id] = st
    _render_tasks_list(
        chat_id, _open_views_from_cache(chat_id), cache.get("data_quality"))


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
        f"{RTL}• Open-R: `{r_str}` _{_SNAPSHOT_LABEL}_\n"
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
        reply_markup=_detail_keyboard(
            idx, rec.get("urgency"), rec.get("info_only"),
            task_type=rec.get("task_type"),
        ),
        parse_mode="Markdown",
    )


# ──────────────────────────────────────────────────────────────────────────────
# #5 / DEC-006 — consolidated ALGO observation panel (NOT a Task)
# ──────────────────────────────────────────────────────────────────────────────

# Mark §2.2 — risk_basis surfaced descriptively (engine's own
# classify_risk_basis output; no instruction, no Sentinel computation).
_RISK_BASIS_HE = {
    "True": "אמיתי",
    "Target": "Target (יעד)",
    "Unknown": "לא ידוע",
}


def handle_algo_panel(chat_id):
    """#5 / DEC-006 — ONE consolidated, observation-only ALGO read-out card.

    Hard invariants (Mark §2.3): it is NOT a Task — no task_type/urgency, no
    done/skip/note/lifecycle, never counted in WR/Expectancy/PF/total_r. It
    surfaces ONLY the engine's already-existing observation fields
    (ALGO_OBSERVED state label, risk_basis, an external stop ONLY if ALGO
    exposes one) — never a Sentinel-synthesized recommendation or stop
    (engine_core.py:457-462 returns suggested_stop=None and that is respected
    literally). Read from the CACHE (no engine call; consistent with #3);
    cache absent → safe full re-derive first.
    """
    if not _cache_valid(chat_id):
        # Safe: build the cache (engine = source of truth) before reading it.
        _load_tasks(chat_id)
    cache = user_state.get(chat_id, {}).get("tasks_cache") or {}
    recs = cache.get("records") or []
    algo = [
        r.get("_algo_observed")
        for r in recs
        if r.get("task_type") == "ALGO_OBSERVE_ONLY"
        and isinstance(r.get("_algo_observed"), dict)
    ]

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "⬅️ חזרה לרשימה", callback_data="task_open|list"))

    if not algo:
        # Empty ALGO set — nothing to read out (the entry would not have been
        # rendered; this is the defensive path).
        bot.send_message(
            chat_id,
            f"{RTL}🤖 *ALGO — מנוהל חיצונית*\n"
            f"{RTL}אין כרגע פוזיציות ALGO תחת בקרה.",
            reply_markup=markup, parse_mode="Markdown",
        )
        return

    # Header disclaimer — MANDATORY and FIRST (Mark §2.2, verbatim;
    # descriptive, non-binding, no imperative).
    body = (
        f"{RTL}🤖 ALGO — מנוהל חיצונית. בקרה בלבד.\n"
        f"{RTL}Sentinel אינו מנהל, אינו ממליץ, ואינו נספר בסטטיסטיקה.\n"
        f"{RTL}המידע למטה הוא מה ש-Sentinel *רואה* — לא הוראת פעולה.\n\n"
    )
    # Per-position purely descriptive observation line (Mark §2.2 exact
    # shape — no imperative verb, no Sentinel stop number).
    for a in algo:
        sym = a.get("symbol", "?")
        state_label = a.get("state_label") or "🤖 ALGO — פיקוח בלבד"
        rb = _RISK_BASIS_HE.get(a.get("risk_basis"), "לא ידוע")
        ext = a.get("external_stop")
        # Sprint-17 #4 — when the external stop is "Unknown", surface the
        # ALGO's OWN §1 known rule instead of a bare "Unknown" (observed, NOT
        # enforced by Sentinel). A real broker stop, if exposed, still wins.
        if isinstance(ext, (int, float)) and ext > 0:
            ext_he = f"${float(ext):.2f}"
        elif a.get("known_rule"):
            ext_he = f"חוק ALGO ידוע (נצפה, לא נאכף): {a['known_rule']}"
        else:
            ext_he = "לא ידוע"
        body += (
            f"{RTL}• {sym}: מצב נצפה — {state_label}.\n"
            f"{RTL}  בסיס סיכון: {rb}. סטופ חיצוני: {ext_he}.\n"
        )
        # Sprint-17 #5 — ALGO dead-money = the ALGO's OWN §1 time-exit window
        # (QQQ/HOOD/PLTR only; TSLA/JPM have none → no line). Descriptive
        # observer note, never an instruction, never a Task, never counted.
        te = a.get("algo_time_exit")
        if te:
            body += (
                f"{RTL}  ⏳ ALGO {sym} קרוב לחלון יציאת-הזמן שלו "
                f"({te}) — לוודא שהאלגו מחובר ופועל. תיאור, לא הוראה.\n"
            )
    # Backtest-caveat — MANDATORY on any surface that shows ALGO data derived
    # from the founder backtest dataset (MARK §5; AGENTS.md #1). Non-suppressible.
    body += f"\n{RTL}{algo_rules.ALGO_BACKTEST_CAVEAT_HE}\n"
    # Honest source label (same vocabulary the list uses).
    body += (
        f"\n{RTL}נתונים: {_data_label(cache.get('data_quality'))} · "
        f"מעודכן: {cache.get('built_iso', '—')}\n"
        f"{RTL}{_SNAPSHOT_LABEL}"
    )
    bot.send_message(chat_id, body, reply_markup=markup, parse_mode="Markdown")


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
    # T7 / Mark §1.4 — record WHICH drawdown episode the user acked so a later
    # NEW episode is not masked by this ack (append-only on the existing
    # lifecycle row; no schema change). Other tasks: note stays None.
    _ack_note = None
    if (
        rec.get("task_type") == open_tasks.TASK_ACK_DRAWDOWN_CUT
        and rec.get("campaign_id") == open_tasks.PORTFOLIO_CID
    ):
        _ep = rec.get("_t7_episode_note")
        _ack_note = _ep if _ep else None
    ok = open_tasks.mark_done(
        supabase, rec["campaign_id"], rec["task_type"], note=_ack_note,
    )
    status = "✅ סומן כבוצע" if ok else "⚠️ שמירה נכשלה (נסה שוב)"
    bot.send_message(
        chat_id,
        f"{RTL}{status} — {rec.get('symbol')}.",
        parse_mode="Markdown",
    )
    # #3 — re-render from the cache (no engine, no network); the Supabase
    # write above is unchanged/authoritative.
    _apply_local_status(chat_id, idx, open_tasks.STATUS_DONE)


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
    # #3 — re-render from the cache (no engine, no network).
    _apply_local_status(chat_id, idx, open_tasks.STATUS_SKIPPED)


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
    # Clear only the in-progress free-text capture keys; PRESERVE tasks_cache
    # so the post-skip re-render is served in-place (#3) instead of paying a
    # full re-derive for a single P0 status flip.
    st.pop("action", None)
    st.pop("task_idx", None)
    user_state[chat_id] = st
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
    # #3 — re-render from cache (cache-miss → safe full re-derive).
    _apply_local_status(chat_id, idx, open_tasks.STATUS_SKIPPED)


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
