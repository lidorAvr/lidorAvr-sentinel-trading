"""
Portfolio drill-down and analysis flows for Sentinel Trading.

handle_drilldown() — deep technical X-ray for a single symbol.
Dependencies are passed via module-level singletons from bot_core.
"""
import pandas as pd
import engine_core as ec
import supabase_repository as repo
from bot_core import bot, supabase, RTL
from bot_helpers import get_account_settings, get_nav_and_risk


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
        if curr is None:
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

        bot.edit_message_text(rep, chat_id, msg_id, parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(f"❌ שגיאה בשליפת נתוני עומק: {e}", chat_id, msg_id)
