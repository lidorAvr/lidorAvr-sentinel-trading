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

        open_pos = pos_res["data"].iloc[0]
        entry = float(open_pos['price'])
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

        init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
        original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0

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
        open_pos = pos_res["data"] if pos_res["ok"] else pd.DataFrame()

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
                orig_risk = (base_price - init_sl) * base_qty if init_sl > 0 and init_sl < base_price else 0
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
            risk_rec = are.compute_adaptive_risk(
                closed_camps, current_risk_pct, acc_size,
                open_r_list=open_r_regime or None,
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

        open_pos = pos_res["data"]
        if open_pos.empty:
            try: bot.delete_message(chat_id, loading_msg.message_id)
            except Exception: pass
            return bot.send_message(chat_id, "✅ אין פוזיציות פתוחות במערכת.")

        account_settings = get_account_settings()
        acc_size, target_risk_usd, nav_stale_label = get_nav_and_risk(account_settings)
        spy_hist = ec.get_cached_history("SPY", "1y", "1d")

        user_state[chat_id] = {'temp_positions': open_pos.to_dict('records')}
        total_open_pnl = total_disc_pnl = total_algo_pnl = total_risk = total_realized_camp = 0
        total_exposure = total_disc_exposure = total_algo_exposure = 0
        total_locked_profit = total_giveback_risk = 0
        algo_count = 0
        active_symbols = []
        open_r_vals = []  # running R for each open position → fed into adaptive risk
        # Sprint-12 / Mark §3 — symbols whose current price fell back to entry
        # because ec.get_live_price() returned None (per-figure, binary on the
        # actual None — never a guess). Drives the honest fallback label.
        price_fallback_syms = []

        msg = f"{RTL}🔭 *חדר מצב - דו\"ח ריכוז פוזיציות:*\n\n"

        for i, row in enumerate(user_state[chat_id]['temp_positions'], 1):
            sym = row['symbol']
            active_symbols.append(sym)
            entry, sl, init_sl = row['price'], row['stop_loss'], row['initial_stop']
            setup, qty = row['setup_type'], row['quantity']
            init_qty = row.get('initial_qty', row['quantity'])
            realized_pnl = row.get('realized_pnl', 0)
            entry_date = row['entry_date']
            mgt_state = row.get('management_state', 'full_position')

            add_on_count = row.get('add_on_count', 0)
            base_price = row.get('base_price', entry)
            base_qty   = row.get('base_qty', init_qty)

            curr = ec.get_live_price(sym)
            price_is_fallback = curr is None
            if price_is_fallback:
                curr = entry
                price_fallback_syms.append(sym)

            open_pnl_usd = (curr - entry) * qty
            pos_value = curr * qty
            total_pos_profit = open_pnl_usd + realized_pnl
            weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0

            init_sl_clean = init_sl if (init_sl > 0 and init_sl < base_price) else 0
            original_campaign_risk = (base_price - init_sl_clean) * base_qty if init_sl_clean > 0 else 0

            if sl > base_price:
                current_open_loss_risk = 0
                locked_profit_usd = (sl - base_price) * qty
                giveback_risk_usd = (curr - sl) * qty if curr > sl else 0
            else:
                current_open_loss_risk = (base_price - sl) * qty if sl > 0 else 0
                locked_profit_usd = 0
                giveback_risk_usd = 0

            total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
            open_r_val = (open_pnl_usd / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl_usd / original_campaign_risk) if original_campaign_risk > 0 else 0)
            open_r_vals.append(open_r_val)

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

            if str(setup).upper() == 'ALGO':
                algo_count += 1
                total_algo_pnl += open_pnl_usd
                total_algo_exposure += pos_value
                open_r_str = f"`{open_r_val:.1f}R` *(Target Risk Base)*"
                e_data = engine_res.get("data") or {}
                risk_basis = e_data.get("risk_basis", "Target")
                risk_vis   = e_data.get("risk_visibility_score", 40)

                msg += f"{RTL}*{i}. {sym}* | 🏷️ ALGO | 🟠 מנוהל חיצונית\n"
                msg += f"{RTL}   ▸ ותק: `{days_held}` ימים | כמות: {qty_text}\n"
                _algo_fb = f" {tf.PRICE_FALLBACK_LABEL}" if price_is_fallback else ""
                msg += f"{RTL}   ▸ כניסה: {entry_text} | נוכחי: `${curr:.2f}`{_algo_fb}\n"
                msg += f"{RTL}   ▸ סטופ: מנוהל חיצונית | בסיס R: `{risk_basis}` | שקיפות סיכון: `{risk_vis}/100`\n"
                msg += f"{RTL}   ▸ רווח צף: {pnl_icon} `${open_pnl_usd:.2f}` | כולל: `${total_pos_profit:.2f}`\n"
                msg += f"{RTL}   ▸ חשיפה: `{weight_pct:.1f}%` מקרן הבסיס\n"
                msg += f"{RTL}   ▸ Open R (צף): {open_r_str}\n"
                msg += f"{RTL}   ▸ סטטוס שוק: {status}\n"
                msg += f"{RTL}   ▸ פיקוח: `מידע בלבד — Sentinel אינה מנהלת יציאות אלגו`\n"
            else:
                total_disc_pnl += open_pnl_usd
                total_disc_exposure += pos_value
                total_risk += current_open_loss_risk

                msg += tf.fmt_position_card(
                    i=i, sym=sym, setup=setup, days_held=days_held,
                    curr=curr, entry=entry, open_pnl=open_pnl_usd,
                    pos_value=pos_value, weight_pct=weight_pct,
                    total_pos_profit=total_pos_profit,
                    total_campaign_r=total_campaign_r,
                    open_r_val=open_r_val, status=status,
                    action_short=action_short,
                    add_on_count=add_on_count, base_price=base_price,
                    locked_profit=locked_profit_usd,
                    giveback_risk=giveback_risk_usd,
                    capital_risk=current_open_loss_risk,
                    price_is_fallback=price_is_fallback,
                ) + "\n"
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
            risk_rec = are.compute_adaptive_risk(
                closed_camps, current_risk_pct, acc_size,
                open_r_list=open_r_vals or None,
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
