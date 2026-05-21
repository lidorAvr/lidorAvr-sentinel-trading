"""
Portfolio drill-down and analysis flows for Sentinel Trading.

handle_drilldown() — deep technical X-ray for a single symbol.
handle_market_regime() — market pulse + exposure breakdown.
handle_portfolio_room() — open positions overview ("חדר מצב").

Dependencies are passed via module-level singletons from bot_core.
"""
from datetime import datetime
from telebot import types
import pandas as pd
import engine_core as ec
import supabase_repository as repo
import telegram_formatters as tf
import adaptive_risk_engine as are
import position_lifecycle as plc
from bot_core import bot, supabase, user_state, RTL
from bot_helpers import get_account_settings, get_nav_and_risk


def _send_long_message(chat_id, text, reply_markup=None):
    """Send a Telegram message, splitting at 〰️ separator if > 3900 chars."""
    max_len = 3900
    if len(text) <= max_len:
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")
        return
    parts = []
    while len(text) > 0:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_idx = text.rfind('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n', 0, max_len)
        if split_idx == -1:
            split_idx = text.rfind('\n', 0, max_len)
            if split_idx == -1:
                split_idx = max_len
        else:
            split_idx += len('〰️〰️〰️〰️〰️〰️〰️〰️〰️\n')
        parts.append(text[:split_idx])
        text = text[split_idx:]
    for i, part in enumerate(parts):
        try:
            if i == len(parts) - 1:
                bot.send_message(chat_id, part, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, part, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending part {i}: {e}")


def handle_drilldown(chat_id, symbol):
    msg_id = bot.send_message(
        chat_id, f"⏳ שואב נתוני רנטגן (Drill-down) עבור {symbol}...",
        parse_mode="Markdown"
    ).message_id
    try:
        df = pd.DataFrame(repo.get_trades_by_symbol(supabase, symbol))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"] or pos_res["data"].empty:
            bot.edit_message_text(
                f"❌ לא נמצאו פוזיציות פתוחות או קמפיינים פעילים עבור {symbol}.",
                chat_id, msg_id
            )
            return

        # F4 (Meeting 21/05/2026) — wire RISK-1c.1 enrichment for the
        # /trade SYMBOL drilldown surface. Without this, the drilldown
        # showed `avg_price` from row['price'] (could drift on re-sync);
        # the locked anchor stays put. Also resolves the entry display via
        # the same canonical resolver as /portfolio so the two surfaces
        # cannot diverge on the same campaign.
        import position_lock_anchor as _pla
        open_pos = _pla.attach_lock_anchors(pos_res["data"], df).iloc[0]
        _drill_entry = tf.resolve_entry_display(
            price=open_pos['price'],
            locked_entry_price=open_pos.get('locked_entry_price'),
            mode="live",
        )
        entry = _drill_entry['entry']
        qty   = float(open_pos['quantity'])
        sl    = float(open_pos['stop_loss'])
        init_sl    = float(open_pos['initial_stop'])
        setup      = open_pos['setup_type']
        mgt_state  = open_pos.get('management_state', 'full_position')
        entry_date = open_pos['entry_date']
        curr = ec.get_live_price(symbol)
        price_is_fallback = curr is None
        if price_is_fallback:
            curr = entry

        account_settings = get_account_settings()
        acc_size, target_risk_usd, _nav_stale_label = get_nav_and_risk(account_settings)
        weight_pct = ((curr * qty) / acc_size) * 100 if acc_size > 0 else 0
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")

        base_price = open_pos.get('base_price', entry)
        base_qty   = open_pos.get('base_qty', qty)

        # F5 (Wave 2 / Meeting 21/05/2026): drift-resistant base for R math.
        # `base_price` from engine_core is computed off the raw `price`
        # column which can drift on IBKR re-sync. The first-day locked
        # anchor (from position_lock_anchor.attach_lock_anchors) is the
        # immutable equivalent — adopt it when all first-day BUYs are
        # locked, fall back to `base_price` otherwise (unlocked rows or
        # LOCKED-April fixture). For non-drifted locked rows the two
        # values are byte-identical (`locked_entry_price` is a copy of
        # `price` at lock-time); the resistance kicks in only after drift.
        _lbp = open_pos.get('locked_base_price')
        base_price_eff = float(_lbp) if _lbp is not None else float(base_price)

        init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price_eff) else 0
        original_campaign_risk = (base_price_eff - init_sl_clean) * base_qty if init_sl_clean > 0 else 0

        engine_res = ec.evaluate_position_engine(
            symbol=symbol, entry_price=entry, entry_date_str=entry_date,
            current_stop=sl, setup_type=setup, mgt_state=mgt_state,
            weight_pct=weight_pct, total_r=0,
            target_risk_usd=target_risk_usd,
            actual_risk_usd=original_campaign_risk, spy_hist=spy_hist,
        )
        if not engine_res["ok"]:
            bot.edit_message_text(
                f"❌ שגיאת מנוע בחישוב {symbol}: {engine_res['error']}",
                chat_id, msg_id
            )
            return

        data = engine_res["data"]
        feats = data.get("features", {})

        sizing_str = f"ניהול: `{mgt_state}` | חשיפה: `{weight_pct:.1f}%`"
        if str(setup).upper() != "ALGO":
            if original_campaign_risk > 0 and data.get("sizing_status") != "✅ תקין":
                clean_sizing = data.get("sizing_status").replace('⚠️ ', '').replace('📉 ', '')
                sizing_str += f"\n⚖️ סטטוס סיכון: {clean_sizing}"
            elif original_campaign_risk == 0:
                sizing_str += f"\n⚠️ חסר סטופ התחלתי לחישוב בקרת סיכון."

        rep = f"{RTL}🔬 *דו\"ח מודיעין עומק (Drill-down) - {symbol}*\n\n"
        rep += f"*{symbol}* | 🏷️ {setup} | סטטוס: {data['status']}\n{sizing_str}\n〰️〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
        rep += f"{RTL}📊 *פרופיל טכני:*\n"
        if feats.get('dist_12d') is not None:
            rep += f"• ימי פיזור (12 ימים): `{feats['dist_12d']}`\n"
        if feats.get('accum_10d') is not None:
            rep += f"• ימי איסוף (10 ימים): `{feats['accum_10d']}`\n"
        if feats.get('good_closes_10') is not None:
            rep += f"• סגירות חזקות מול חלשות: `{feats['good_closes_10']}` מול `{feats['bad_closes_10']}`\n"

        rep += f"\n{RTL}📈 *מטריצת כוח יחסי (Relative Strength):*\n"
        if feats.get('rs20_market') is not None:
            val = feats['rs20_market'] * 100
            rep += f"• מול השוק (SPY): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"

        sec_bundle = ec.get_sector_bundle(symbol)
        sec_etf = sec_bundle.get('sector_etf')
        if feats.get('rs20_stock_sector') is not None and sec_etf:
            val = feats['rs20_stock_sector'] * 100
            rep += f"• מול הסקטור ({sec_etf}): {'🟢 מובילה' if val > 0 else '🔴 מפגרת'} ({val:+.1f}%)\n"

        rep += f"\n{RTL}🌪️ *משטר תנודתיות (Volatility Regime):*\n"
        if feats.get('atr_regime') is not None:
            reg_val = feats['atr_regime']
            reg_text = "מתרחבת 📈" if reg_val > 1.2 else "מתכווצת 📉" if reg_val < 0.85 else "נורמלית ➖"
            rep += f"• יחס תנודתיות: `{reg_val:.2f}x` ({reg_text})\n"

        if feats.get('stretch_ma20_atr') is not None:
            rep += f"• מתיחות (ממרחק MA20): `{feats['stretch_ma20_atr']:.1f}` יחידות ATR\n"

        if data['issues']:
            rep += f"\n{RTL}⚠️ *אזהרות:* {', '.join(data['issues'])}\n"

        if price_is_fallback:
            # Sprint-12 / Mark §3 — this card's current price / weight / P&L
            # all derive from entry-as-price because ec.get_live_price()
            # returned None. Honest label only (no number recomputed).
            rep += f"\n{RTL}_{tf.PRICE_FALLBACK_LABEL}_\n"

        bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(f"❌ שגיאה בשליפת נתוני עומק: {e}", chat_id, msg_id)


def handle_market_regime(chat_id):
    """🌡️ משטר שוק וסיכונים — market pulse + exposure breakdown + adaptive risk."""
    msg_id = bot.send_message(chat_id, "⏳ בודק דופק שוק...", parse_mode="Markdown").message_id
    try:
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")
        qqq_hist = ec.get_cached_history("QQQ", "1y", "1d")
        regime   = ec.compute_market_regime(spy_hist, qqq_hist)

        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        # F4 (Meeting 21/05/2026) — same RISK-1c.1 enrichment for the
        # market-regime flow. Read-only — only used here for exposure totals
        # by setup category, so the lock anchor is informational at this
        # surface but maintains consistency across the file.
        import position_lock_anchor as _pla
        open_pos = (_pla.attach_lock_anchors(pos_res["data"], df)
                    if pos_res["ok"] else pd.DataFrame())

        account_settings = get_account_settings()
        acc_size, _target_risk_usd_regime, nav_stale_label = get_nav_and_risk(account_settings)

        exp = {"ALGO": 0, "VCP": 0, "EP": 0, "OTHER": 0}
        open_r_regime = []
        # Sprint-12 / Mark §3 — symbols whose price fell back because
        # ec.get_live_price() returned None (binary on the ACTUAL None — the
        # legacy `or` also caught a falsy 0, so detect None explicitly).
        regime_fallback_syms = []
        if not open_pos.empty:
            for _, row in open_pos.iterrows():
                sym, setup = row["symbol"], str(row["setup_type"]).upper()
                _live = ec.get_live_price(sym)
                if _live is None:
                    regime_fallback_syms.append(sym)
                curr = _live or float(row["price"])
                val = curr * float(row["quantity"])
                if setup in exp:
                    exp[setup] += val
                else:
                    exp["OTHER"] += val
                open_pnl = (curr - float(row["price"])) * float(row["quantity"])
                init_sl = float(row.get("initial_stop", 0))
                base_price = float(row.get("base_price", row["price"]))
                base_qty = float(row.get("base_qty", row["quantity"]))
                # F5 (Wave 2): drift-resistant base for orig_risk in the
                # regime exposure totals. Falls back to base_price for
                # unlocked / LOCKED-April ⇒ byte-identical.
                _lbp = row.get("locked_base_price")
                base_price_eff = float(_lbp) if _lbp is not None else base_price
                orig_risk = (base_price_eff - init_sl) * base_qty if init_sl > 0 and init_sl < base_price_eff else 0
                if orig_risk > 0:
                    open_r_regime.append(open_pnl / orig_risk)

        total_exp = sum(exp.values())
        total_pct = (total_exp / acc_size) * 100 if acc_size > 0 else 0
        rep = tf.fmt_regime_report(regime, total_pct, exp["ALGO"], exp["VCP"], exp["EP"], acc_size)

        if nav_stale_label:
            rep += f"\n\n⚠️ _{nav_stale_label}_"
        if regime_fallback_syms:
            # Sprint-12 / Mark §3 — honest aggregate notice (label only; the
            # exposure/R numbers above used entry-as-price for these symbols).
            _rfb = ", ".join(sorted(set(regime_fallback_syms)))
            rep += f"\n\n{RTL}{tf.PRICE_FALLBACK_LABEL}\n{RTL}_חל על: {_rfb}_"

        try:
            current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
            closed_camps = are.compute_closed_campaigns(df)
            # F1 (Meeting 21/05/2026) — wire the 4-gate on the risk-RAISE path.
            # Without this, the founder saw "0.85% / $67" on N=9 statistical
            # noise. The gate clamps "up" → "hold" when sample < 20 OR
            # broker-recon is Critical OR expectancy < 0.30R OR loss_streak≥2.
            # Strictly risk-NARROWING: never weakens the cut/hold paths.
            _gate_ctx = are.build_risk_raise_gate_ctx(
                nav=acc_size, risk_pct=current_risk_pct,
                total_deposited=float(account_settings.get("total_deposited", 0) or 0),
                closed_campaigns=closed_camps,
                nav_source=str(account_settings.get("nav_source", "broker") or "broker"),
                pre_db_realized_pnl_estimate=float(account_settings.get("pre_db_realized_pnl_estimate", 0) or 0),
            )
            risk_rec = are.compute_adaptive_risk(
                closed_camps, current_risk_pct, acc_size,
                open_r_list=open_r_regime or None,
                risk_raise_gate=_gate_ctx,
            )
            rep += tf.fmt_adaptive_risk_block(risk_rec, settle_info=are.get_risk_settle_info())
        except Exception:
            pass

        bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(f"❌ תקלה בחישוב משטר שוק: {e}", chat_id, msg_id)


def handle_portfolio_room(chat_id):
    """📊 חדר מצב — open positions overview report with drill-down keyboard."""
    loading_msg = bot.send_message(chat_id, "⏳ *שואב נתונים ומרכיב דו\"ח...*", parse_mode="Markdown")
    try:
        df = pd.DataFrame(repo.get_all_trades(supabase))
        pos_res = ec.get_open_positions_campaign(df)
        if not pos_res["ok"]:
            try: bot.delete_message(chat_id, loading_msg.message_id)
            except Exception: pass
            return bot.send_message(chat_id, f"❌ שגיאת תשתית במשיכת פוזיציות:\n`{pos_res['error']}`")

        # RISK-1c.1 — engine_core is byte-locked, so it does not propagate
        # the `locked_entry_price` column into its per-campaign output dict.
        # The pure enrichment helper computes the campaign-level lock anchor
        # from the raw BUY rows in `df` (which DOES carry the column from
        # the select("*") fetch). See position_lock_anchor.py for semantics.
        import position_lock_anchor as _pla
        open_pos = _pla.attach_lock_anchors(pos_res["data"], df)
        if open_pos.empty:
            try: bot.delete_message(chat_id, loading_msg.message_id)
            except Exception: pass
            # Sprint-27 W3 (UX P0-2) — an empty open-book is ambiguous: it can
            # mean no positions OR upstream data did not load. Disambiguate so
            # silence is never read as "all-clear". PURE presentation; the
            # already-asserted `open_pos.empty` is the only signal used.
            return bot.send_message(
                chat_id,
                f"{RTL}📭 *אין פוזיציות פתוחות כרגע.*\n"
                f"{RTL}_זה לא אומר שהכול תקין/לא תקין — רק שאין כעת מה לנהל. "
                f"אם פתחת עסקה ולא מופיעה, בדוק סנכרון נתונים._")

        account_settings = get_account_settings()
        acc_size, target_risk_usd, nav_stale_label = get_nav_and_risk(account_settings)
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")

        user_state[chat_id] = {'temp_positions': open_pos.to_dict('records')}

        # Phase REPORT-2 (W-R2-2) — read-only per-campaign raw-leg lookup for
        # the additive units-lifecycle line. NO new data source / NO Supabase
        # / NO network: it slices the SAME `df` already fetched above
        # (`repo.get_all_trades` is byte-identical, used read-only). The leg
        # split + honest-empty + reconciliation decision live entirely inside
        # the pure `position_lifecycle` helper — this only hands it the raw
        # rows and the engine's OWN authoritative `quantity`. The existing
        # `quantity`/`כמות` card number is NEVER touched (strictly additive).
        _camp_legs = {}
        if not df.empty and 'campaign_id' in df.columns:
            _lc_cols = [c for c in ('side', 'quantity', 'trade_id')
                        if c in df.columns]
            for _cid, _grp in df[df['campaign_id'].notnull()].groupby(
                    'campaign_id'):
                _camp_legs[_cid] = _grp[_lc_cols].to_dict('records')

        total_open_pnl = total_disc_pnl = total_algo_pnl = total_risk = total_realized_camp = 0
        total_exposure = total_disc_exposure = total_algo_exposure = 0
        total_locked_profit = total_giveback_risk = 0
        # R-ALGO-2 (Sprint-30 G1 / CLOSURE-FIX): the max single open-campaign
        # original risk — the SAME quantity the dashboard recon oracle passes
        # as `max_open_campaign_risk` (dashboard.py:452 `live_df["OriginalRisk"]
        # .max()`, fed to the classifier at dashboard.py:460). Accumulated from
        # the per-position `original_campaign_risk` already computed in the loop
        # below (telegram_portfolio.py:307) — NO new data source, NO new math.
        # Previously this surface OMITTED the argument ⇒ the classifier's
        # `bool(max_open_campaign_risk)` Critical branch was DEAD here, so the
        # same gap the dashboard banded "פער נתונים קריטי" was banded the
        # softer "פער מהותי" on the phone — a two-surface band divergence
        # directly above a risk-raise rec. Mirroring the oracle's input makes
        # both surfaces emit the SAME band for the SAME state.
        _max_open_campaign_risk = 0.0
        algo_count = 0
        active_symbols = []
        # Sprint-27 W3 (UX P0-1) — symbols whose ALREADY-computed engine
        # `status` is a critical/decision state (the EXACT string the position
        # card prints in "סטטוס שוק"; the same set risk_monitor.CRITICAL_STATUSES
        # uses). Collected during the existing loop — NO new computation, NO new
        # data source — so the ONE companion "מה עכשיו?" line can lead the
        # surface (today the lede is buried under position cards).
        _WHATNOW_CRITICAL = ("🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו")
        decision_syms = []
        open_r_vals = []  # running R for each open position → fed into adaptive risk
        # Sprint-12 / Mark §3 — symbols whose current price fell back to entry
        # because ec.get_live_price() returned None (per-figure, binary on the
        # actual None — never a guess). Drives the honest fallback label.
        price_fallback_syms = []

        msg = f"{RTL}🔭 *חדר מצב - דו\"ח ריכוז פוזיציות:*\n\n"

        for i, row in enumerate(user_state[chat_id]['temp_positions'], 1):
            sym = row['symbol']
            active_symbols.append(sym)
            # RISK-1d: single-source-of-truth at-entry resolver. mode='live'
            # prefers `locked_entry_price` (RISK-1a immutable column populated
            # by the RISK-1b wizard / RISK-1c backfill) over the raw `price`
            # column, which can drift via IBKR re-sync (the MRVL $87→$170
            # regression that motivated RISK-1). NULL lock ⇒ falls back to
            # `price` with the not-yet-locked banner. Byte-identical to the
            # legacy path for any row where locked_entry_price IS NULL
            # (resolver returns price + banner; the entry NUMBER is unchanged).
            _entry_disp = tf.resolve_entry_display(
                price=row['price'],
                locked_entry_price=row.get('locked_entry_price'),
                mode="live",
            )
            entry, sl, init_sl = _entry_disp['entry'], row['stop_loss'], row['initial_stop']
            setup, qty = row['setup_type'], row['quantity']
            init_qty = row.get('initial_qty', row['quantity'])
            realized_pnl = row.get('realized_pnl', 0)
            entry_date = row['entry_date']
            mgt_state = row.get('management_state', 'full_position')

            add_on_count = row.get('add_on_count', 0)
            base_price = row.get('base_price', entry)
            base_qty   = row.get('base_qty', init_qty)

            # F5 (Wave 2): drift-resistant first-day-locked base for R math
            # (see telegram_portfolio.py:97-105 for the canonical comment).
            _lbp = row.get('locked_base_price')
            base_price_eff = float(_lbp) if _lbp is not None else float(base_price)

            curr = ec.get_live_price(sym)
            price_is_fallback = curr is None
            if price_is_fallback:
                curr = entry
                price_fallback_syms.append(sym)

            open_pnl_usd = (curr - entry) * qty
            pos_value = curr * qty
            total_pos_profit = open_pnl_usd + realized_pnl
            weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0

            init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price_eff) else 0
            original_campaign_risk = (base_price_eff - init_sl_clean) * base_qty if init_sl_clean > 0 else 0
            # R-ALGO-2 (Sprint-30 G1): mirror dashboard.py:452's
            # `live_df["OriginalRisk"].max()` — the exact same per-open-position
            # `original_campaign_risk` quantity, max-reduced for the recon
            # classifier's Critical-by-open-risk branch. Read-only, no recompute.
            if original_campaign_risk > _max_open_campaign_risk:
                _max_open_campaign_risk = float(original_campaign_risk)

            if sl > base_price_eff:
                current_open_loss_risk = 0
                locked_profit_usd = (sl - base_price_eff) * qty
                giveback_risk_usd = (curr - sl) * qty if curr > sl else 0
            else:
                current_open_loss_risk = (base_price_eff - sl) * qty if sl > 0 else 0
                locked_profit_usd = 0
                giveback_risk_usd = 0

            total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
            open_r_val = (open_pnl_usd / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl_usd / original_campaign_risk) if original_campaign_risk > 0 else 0)
            open_r_vals.append(open_r_val)

            # Sprint-15 / DEC-20260515-011 — dual-R via the EXISTING engine
            # functions called with the SAME inputs as the inline expression
            # above (no new R math). Structure R (manual primary, byte-identical
            # to today's open_r_val) and Account R, formatted via the single
            # canonical helper (produce-once, consume-thrice).
            _is_algo_pos = str(setup).upper() == 'ALGO'
            _structure_r = ec.compute_r_true(open_pnl_usd, original_campaign_risk)
            _account_r   = ec.compute_r_target(open_pnl_usd, target_risk_usd)
            _r_basis = tf.dual_r_basis(
                original_campaign_risk=original_campaign_risk,
                frozen_target_risk_usd=target_risk_usd,
                is_algo=_is_algo_pos,
            )
            _dual_r_frag = tf.fmt_dual_r(
                _structure_r, _account_r,
                structure_valid=_r_basis["structure_valid"],
                account_valid=_r_basis["account_valid"],
                is_algo=_is_algo_pos,
            )

            engine_res = ec.evaluate_position_engine(
                symbol=sym, entry_price=entry, entry_date_str=entry_date,
                current_stop=sl, setup_type=setup, mgt_state=mgt_state,
                weight_pct=weight_pct, total_r=total_campaign_r,
                target_risk_usd=target_risk_usd,
                actual_risk_usd=original_campaign_risk, spy_hist=spy_hist
            )
            if not engine_res["ok"]:
                status, action_short, trigger = "❌ שגיאה", "שגיאה", engine_res["error"]
                sizing_str, score, stage, suggested_stop, feats = "✅ תקין", None, "", sl, {}
            else:
                e_data = engine_res["data"]
                status, action_short, trigger = e_data['status'], e_data['action'], e_data['trigger']
                sizing_str = e_data.get('sizing_status', "✅ תקין")
                score, stage = e_data['score'], e_data['stage']
                suggested_stop, feats = e_data['suggested_stop'], e_data.get('features', {})

            # Sprint-27 W3 — record (do NOT alter) the symbol if its
            # already-computed `status` is a decision state. Read-only on the
            # value the card prints below; no number/flow changed.
            if status in _WHATNOW_CRITICAL:
                decision_syms.append(sym)

            total_open_pnl += open_pnl_usd
            total_realized_camp += realized_pnl
            total_exposure += pos_value
            total_locked_profit += locked_profit_usd
            total_giveback_risk += giveback_risk_usd

            try:
                days_held = (datetime.now() - pd.to_datetime(entry_date)).days if entry_date else 0
            except Exception:
                days_held = 0
            pnl_icon = '🟢' if open_pnl_usd >= 0 else '🔴'

            qty_text   = f"`{qty}`" + (f" (+חיזוק)" if add_on_count > 0 else "")
            entry_text = f"${entry:.2f}" + (f" (בסיס: ${base_price:.2f})" if add_on_count > 0 else "")

            # Phase REPORT-2 (W-R2-1/2) — units lifecycle, read-only & honest.
            # The pure helper re-derives Σ|BUY|/Σ|SELL|/net from the SAME raw
            # legs the engine splits, gated by the engine's OWN authoritative
            # `quantity` (`row['quantity']` == engine_core.py:560 net_qty).
            # Missing/ambiguous/non-reconciling ⇒ honest `—` + `לא ניתן לאמת`
            # (never a fabricated number, AGENTS.md #1). `format_units_lifecycle`
            # is THE single source of truth — the dashboard calls the SAME
            # function for cross-surface byte-identity (anti-drift, SCOPE §5).
            _lc = plc.compute_units_lifecycle(
                _camp_legs.get(row.get('campaign_id')),
                engine_net_qty=qty,
            )
            _lc_line = plc.format_units_lifecycle(_lc)

            if str(setup).upper() == 'ALGO':
                algo_count += 1
                total_algo_pnl += open_pnl_usd
                total_algo_exposure += pos_value
                # Sprint-15 / Mark §1: the conflated single Open-R + standalone
                # `בסיס R` display token is replaced by the canonical dual-R
                # fragment (ALGO ⇒ Structure R = `—` "no real stop", Account R
                # only — never 0.00R). `risk_basis` stays an internal field.
                open_r_str = _dual_r_frag
                e_data = engine_res.get("data") or {}
                risk_basis = e_data.get("risk_basis", "Target")
                risk_vis   = e_data.get("risk_visibility_score", 40)

                msg += f"{RTL}*{i}. {sym}* | 🏷️ ALGO | 🟠 מנוהל חיצונית\n"
                msg += f"{RTL}   ▸ ותק: `{days_held}` ימים | כמות: {qty_text}\n"
                _algo_fb = f" {tf.PRICE_FALLBACK_LABEL}" if price_is_fallback else ""
                msg += f"{RTL}   ▸ כניסה: {entry_text} | נוכחי: `${curr:.2f}`{_algo_fb}\n"
                msg += f"{RTL}   ▸ סטופ: מנוהל חיצונית | שקיפות סיכון: `{risk_vis}/100`\n"
                msg += f"{RTL}   ▸ רווח צף: {pnl_icon} `${open_pnl_usd:.2f}` | כולל: `${total_pos_profit:.2f}`\n"
                msg += f"{RTL}   ▸ חשיפה: `{weight_pct:.1f}%` מקרן הבסיס\n"
                msg += f"{RTL}   ▸ Open R (צף): {open_r_str}\n"
                msg += f"{RTL}   ▸ סטטוס שוק: {status}\n"
                msg += f"{RTL}   ▸ פיקוח: `מידע בלבד — Sentinel אינה מנהלת יציאות אלגו`\n"
            else:
                total_disc_pnl += open_pnl_usd
                total_disc_exposure += pos_value
                total_risk += current_open_loss_risk

                # Phase REPORT-2 (W-R2-3) — SUPPRESSIVE-ONLY decision-awareness,
                # the 4 HARD FENCES (SCOPE §4 — INVIOLABLE):
                #  (a) ALGO carve-out: this is the NON-ALGO branch only; the
                #      ALGO branch above is git-diff-untouched by this softening
                #      (observe-only, AGENTS.md #8 / DEC-20260511-001).
                #  (b) ZERO risk-math change: operates ONLY on the ALREADY-
                #      computed display string `action_short`; never re-enters
                #      the engine, never alters R/NAV/exposure/heat.
                #  (c) NO new directive / TYPE / callback / push: it only
                #      REPLACES a redundant realize/trim/Runner-tighten voice
                #      with a neutral honest note when units were already
                #      partially realized.
                #  (d) Ambiguity ⇒ EXISTING behaviour: fires ONLY when the
                #      lifecycle is `ok=True` AND realized-units > 0; on
                #      `ok=False` the existing `action_short` renders verbatim.
                #  A BROKEN / stop-breach / critical status+action is NEVER
                #  suppressed (those engine branches stay verbatim).
                _action_short_eff = action_short
                _SOFTENABLE = (
                    "שקול מימוש חלקי",
                    "שקול מימוש נוסף",
                    "הידוק ל-Runner",
                    "הידוק אגרסיבי ל-Runner",
                    "קדם סטופ ל-Runner",
                    "Runner חופשי - שקול מימוש",
                    "Runner חופשי - שקול מימוש נוסף בשבירת MA10",
                    "Runner חופשי - שקול מימוש בשבירת MA10",
                )
                _CRITICAL_STATUS = ("🚨 קריטי", "🔴 Broken",
                                    "🚨 חריגת סיכון אלגו")
                _NEVER_SUPPRESS_ACTION = (
                    "יציאה מיידית 🚨",
                    "יציאה / הידוק מידי",
                    "מימוש יתרה / יציאה לפי תוכנית",
                    "שקול סגירת יתרת Runner",
                    "להפחית חשיפה",
                )
                if (
                    _lc.get("ok")
                    and (_lc.get("realized") or 0) > 0
                    and status not in _CRITICAL_STATUS
                    and action_short not in _NEVER_SUPPRESS_ACTION
                    and any(t in str(action_short) for t in _SOFTENABLE)
                ):
                    _action_short_eff = (
                        "כבר מומש חלקית — אין צורך לממש שוב כרגע"
                    )

                msg += tf.fmt_position_card(
                    i=i, sym=sym, setup=setup, days_held=days_held,
                    curr=curr, entry=entry, open_pnl=open_pnl_usd,
                    pos_value=pos_value, weight_pct=weight_pct,
                    total_pos_profit=total_pos_profit,
                    total_campaign_r=total_campaign_r,
                    open_r_val=open_r_val, status=status,
                    action_short=_action_short_eff,
                    add_on_count=add_on_count, base_price=base_price,
                    locked_profit=locked_profit_usd,
                    giveback_risk=giveback_risk_usd,
                    capital_risk=current_open_loss_risk,
                    price_is_fallback=price_is_fallback,
                    dual_r_fragment=_dual_r_frag,
                    entry_banner=_entry_disp['banner'],
                ) + "\n"
                # Phase REPORT-2 (W-R2-1/2) — ONE additive units-lifecycle line
                # from THE single formatter. Strictly additive: every existing
                # card number/string above is byte-identical; this line never
                # replaces `quantity`/`כמות`.
                msg += f"{RTL}   ▸ {_lc_line}\n"
                if original_campaign_risk > 0 and sizing_str != "✅ תקין":
                    clean_sizing = sizing_str.replace('⚠️ ', '').replace('📉 ', '')
                    msg += f"{RTL}   ▸ ⚖️ בקרת קמפיין: {clean_sizing}\n"
                if total_campaign_r <= -1.25 and original_campaign_risk > 0:
                    msg += f"{RTL}   ▸ 🚨 בקרת ביצוע: חריגה מהסטופ! ({total_campaign_r:.1f}R)\n"
                if trigger:
                    msg += f"{RTL}   ▸ טריגר ניהולי: `{trigger}`\n"

            rs_str = ""
            if feats and feats.get("rs20_market") is not None:
                rm_val = feats["rs20_market"] * 100
                rss = feats.get("rs20_stock_sector")
                if rss is not None:
                    rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm_val:+.1f}% | סקטור {rss * 100:+.1f}%\n"
                else:
                    rs_str = f"{RTL}   ▸ כוח יחסי (RS): שוק {rm_val:+.1f}%\n"
            msg += rs_str + f"{RTL}〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"

        total_weight = (total_exposure / acc_size) * 100 if acc_size > 0 else 0
        algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
        total_pnl_icon = '🟢' if total_open_pnl >= 0 else '🔴'
        total_secured = total_realized_camp + total_locked_profit

        msg += f"{RTL}📊 *סיכום תיק הפיקוד:*\n"
        msg += f"{RTL}▸ סה\"כ רווח צף: {total_pnl_icon} `${total_open_pnl:,.2f}` (דיסק': `${total_disc_pnl:,.2f}`)\n"
        msg += f"{RTL}▸ סה\"כ סיכון הפסד הון (דיסק'): `${total_risk:,.2f}`\n"
        msg += f"{RTL}▸ רווח שמומש בעסקאות פתוחות: `${total_realized_camp:,.2f}`\n"
        msg += f"{RTL}▸ רווח נעול (Locked) בסטופים: `${total_locked_profit:,.2f}`\n"
        msg += f"{RTL}▸ סך הכל רווח מוגן (Secured): `${total_secured:,.2f}`\n"
        msg += f"{RTL}▸ סיכון ויתור רווח צף (Giveback): `${total_giveback_risk:,.2f}`\n"
        msg += f"{RTL}▸ חשיפה כללית: `{total_weight:.1f}%` מקרן הבסיס\n"
        if algo_count > 0:
            msg += f"\n{RTL}🤖 *בקרת אשכול אלגו:*\n{RTL}▸ חשיפה אלגו: `{algo_cluster_pct:.1f}%` מהקרן\n"

        # Sprint-15 / DEC-20260515-012 — Risk Capital Basis declaration
        # (labelling only; engine still uses nav*risk_pct/100). NAV source
        # disclosed honestly (AGENTS.md #1) when not a live broker NAV.
        _nav_src = str(account_settings.get("nav_source")
                       or ("broker" if "nav" in account_settings else "deposited"))
        msg += f"\n{tf.fmt_risk_capital_basis(acc_size, target_risk_usd, nav_source=_nav_src)}\n"

        # Sprint-15 / DEC-20260515-013 — Broker Reconciliation Status.
        # Reuses the SAME gap expression as dashboard.py:404-405
        # (NAV − (total_deposited + DB net PnL + open PnL)); read-only, no
        # Supabase write, no recompute of any financial number. The 4 bands
        # are multiples of EXISTING constants (Mark §3) — none invented.
        try:
            _total_deposited = float(account_settings.get("total_deposited", 7500.0))
            _risk_pct_in = float(account_settings.get("risk_pct_input", 0.5))
            _closed_for_rec = are.compute_closed_campaigns(df) if not df.empty else []
            # R-ALGO-2 (Phase ALGO-1 W-A2 / CLOSURE-FIX): compute_closed_campaigns
            # emits realized closed-campaign PnL under "total_pnl_usd"
            # (adaptive_risk_engine.py:205) — it NEVER emits "net_pnl". The prior
            # c.get("net_pnl", 0) matched no key ⇒ _db_net_pnl was silently
            # always 0.0, dropping ALL realized PnL and diverging from the
            # dashboard oracle camp_df['pnl_usd'].sum() (dashboard.py:424).
            # Reading the correct producer key makes חדר-מצב's recon realized-PnL
            # term equal the dashboard's realized quantity. One-site key fix only.
            _db_net_pnl = sum(float(c.get("total_pnl_usd", 0) or 0) for c in _closed_for_rec)
            _db_equity_expected = _total_deposited + _db_net_pnl + total_open_pnl
            _recon_gap = acc_size - _db_equity_expected
            # R-ALGO-2 (Sprint-30 G1 / CLOSURE-FIX): pass the SAME
            # `max_open_campaign_risk` the dashboard recon oracle passes
            # (dashboard.py:460). Omitting it here defaulted it to 0.0 ⇒ the
            # classifier's `bool(max_open_campaign_risk) and agap > …` Critical
            # branch (telegram_formatters.py:799-800) was DEAD on this surface,
            # so a gap the dashboard classifies "פער נתונים קריטי" was
            # mis-classified the softer "פער מהותי" on the phone — the
            # post-deploy two-surface band divergence (tg_report_2 L1239 vs
            # the dashboard oracle), sitting directly above a risk-raise rec.
            # Same classifier, same inputs ⇒ both surfaces emit the SAME band.
            # The dashboard oracle (dashboard.py:455-461) remains the reference.
            # YTD-history adjustment (founder note 21/05/2026): when the
            # founder set `pre_db_realized_pnl_estimate` in
            # sentinel_config.json, the classifier subtracts it from the
            # raw gap so the band reflects the TRUE residual after
            # disclaiming pre-DB closed-campaign PnL. Defaults to 0 ⇒
            # byte-identical behaviour for any deployment that doesn't
            # opt in. See docs/DATA_CONTRACTS.md "Data history scope".
            _pre_db_est = float(account_settings.get(
                "pre_db_realized_pnl_estimate", 0) or 0)
            _recon = tf.classify_broker_reconciliation(
                acc_size, _total_deposited, _db_net_pnl,
                reconciliation_gap=_recon_gap,
                risk_pct_input=_risk_pct_in,
                nav_source=_nav_src,
                max_open_campaign_risk=_max_open_campaign_risk,
                pre_db_realized_pnl_estimate=_pre_db_est,
            )
            msg += f"{tf.fmt_broker_reconciliation(_recon)}\n"
            # F2 (Wave 2): the per-component breakdown is now RESTRICTED to the
            # AI Master Context Export (dashboard.py). Founder feedback
            # 21/05/2026 ~02:30 — the 7-line breakdown was too verbose for
            # /portfolio (חדר מצב). The Mark §3 single-line summary above
            # stays; the founder pastes the AI export when investigating.
        except Exception:
            pass

        spy_hist_caching = ec.get_cached_history("SPY", "1y", "1d")
        regime_for_coaching = ec.compute_market_regime(spy_hist_caching)
        regime_status_str = regime_for_coaching.get('data', {}).get('status', '') if regime_for_coaching.get('ok') else ''
        # Win rate from countable closed campaigns (matches dashboard: excludes ALGO + DATA_INCOMPLETE).
        try:
            wr_c = 0
            countable = [c for c in are.compute_closed_campaigns(df)
                         if ec.is_stat_countable(c.get("stat_bucket", ""))]
            if countable:
                wr_c = sum(1 for c in countable if c.get("is_win")) / len(countable)
        except Exception:
            wr_c = 0
        coaching_insights = ec.generate_minervini_coaching(
            win_rate=wr_c, expectancy_r=0, adj_rr=0,
            oversized_count=0, market_regime_status=regime_status_str,
            streak_losses=0, total_r_net=0
        )
        if coaching_insights:
            msg += f"\n{RTL}🎓 *מינרביני אומר:*\n"
            for ins in coaching_insights[:2]:
                clean_ins = ins.replace('<b>', '*').replace('</b>', '*')
                msg += f"{RTL}▸ {clean_ins}\n"

        try:
            current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
            closed_camps = are.compute_closed_campaigns(df)
            # F1 (Meeting 21/05/2026) — same 4-gate wiring as handle_market_regime
            # above. /portfolio is the surface where the founder saw the noisy
            # "0.85% / $67" recommendation; this is the primary fix point.
            _gate_ctx = are.build_risk_raise_gate_ctx(
                nav=acc_size, risk_pct=current_risk_pct,
                total_deposited=float(account_settings.get("total_deposited", 0) or 0),
                closed_campaigns=closed_camps,
                nav_source=str(account_settings.get("nav_source", "broker") or "broker"),
                pre_db_realized_pnl_estimate=float(account_settings.get("pre_db_realized_pnl_estimate", 0) or 0),
            )
            risk_rec = are.compute_adaptive_risk(
                closed_camps, current_risk_pct, acc_size,
                open_r_list=open_r_vals or None,
                risk_raise_gate=_gate_ctx,
            )
            msg += tf.fmt_adaptive_risk_block(risk_rec, settle_info=are.get_risk_settle_info())
        except Exception:
            pass

        if nav_stale_label:
            msg += f"\n\n{RTL}⚠️ _{nav_stale_label}_"
        if price_fallback_syms:
            # Sprint-12 / Mark §3 — honest aggregate notice: at least one
            # position's price fell back to entry (label only; no number
            # recomputed). Same footer region as nav_stale_label.
            _fb_list = ", ".join(sorted(set(price_fallback_syms)))
            msg += (
                f"\n\n{RTL}{tf.PRICE_FALLBACK_LABEL}"
                f"\n{RTL}_חל על: {_fb_list}_"
            )

        # Sprint-27 W3 (UX P0-1) — the ONE companion "מה עכשיו?" line,
        # PREPENDED above the existing header. Composed ONLY from signals the
        # surface ALREADY computed in the loop above: the decision-state
        # symbols (already-computed engine `status`), the position count, and
        # the existing NAV-stale / price-fallback honesty flags. NO new
        # computation, NO new data source, NO number changed — the entire
        # `msg` body built above stays byte-identical; this line is prepended.
        _pos_n = len(active_symbols)
        if decision_syms:
            _wn_body = (f"{len(decision_syms)} פוז' דורשות החלטה: "
                        f"{', '.join(decision_syms)} — ראה כרטיסים למטה.")
        else:
            _wn_body = (f"{_pos_n} פוז' במעקב, אין מצב קריטי — "
                        f"עבור על הכרטיסים, אין פעולה דחופה.")
        if nav_stale_label:
            # NAV that scales R/exposure is not live → lead with that honesty
            # (accuracy > confidence). Uses ONLY the existing nav_stale_label
            # flag the footer already prints; no new field, no math.
            _wn_body = ("שים לב — NAV לא חי (ראה הערה למטה), קרא R/חשיפה "
                        "כהערכה. " + _wn_body)
        msg = f"{RTL}🧭 *מה עכשיו?* {_wn_body}\n\n" + msg

        try: bot.delete_message(chat_id, loading_msg.message_id)
        except Exception: pass

        markup = types.InlineKeyboardMarkup(row_width=3)
        drill_btns = [types.InlineKeyboardButton(text=f"🔍 {s}", callback_data=f"drill|{s}") for s in active_symbols]
        markup.add(*drill_btns)
        markup.add(types.InlineKeyboardButton("🎯 הזן קידום סטופ", callback_data="start_trail_flow"))

        _send_long_message(chat_id, msg, reply_markup=markup)

    except Exception as e:
        import traceback
        err_details = traceback.format_exc()
        b_ticks = "`" * 3
        try: bot.delete_message(chat_id, loading_msg.message_id)
        except Exception: pass
        bot.send_message(
            chat_id,
            f"❌ תקלת מערכת בחדר המצב:\n`{e}`\n\n{b_ticks}\n{err_details[-500:]}\n{b_ticks}",
            parse_mode="Markdown"
        )
