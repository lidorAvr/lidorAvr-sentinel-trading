"""
telegram_formatters.py
הלפר פורמוט הודעות טלגרם — RTL עברית, אחיד ונקי.
כל הפונקציות מחזירות string מוכן לשליחה ב-parse_mode="Markdown".
"""

RTL = "‏"
SEP = "───────────────"


def fmt_position_card(i: int, sym: str, setup: str, days_held: int,
                      curr: float, entry: float, open_pnl: float,
                      pos_value: float, weight_pct: float,
                      total_pos_profit: float, total_campaign_r: float,
                      open_r_val: float, status: str, action_short: str,
                      add_on_count: int = 0, base_price: float = 0,
                      locked_profit: float = 0, giveback_risk: float = 0,
                      capital_risk: float = 0) -> str:
    """כרטיס פוזיציה אחד — קומפקטי וברור."""
    pnl_icon = '🟢' if open_pnl >= 0 else '🔴'
    addon_tag = f" +(+{add_on_count})" if add_on_count > 0 else ""
    base_tag = f" _(בסיס ${base_price:.2f})_" if add_on_count > 0 and base_price > 0 else ""

    lines = [
        f"{RTL}*{i}. {sym}*{addon_tag} | 🏷️ {setup} | {days_held}d",
        f"{RTL}  ▸ כניסה: `${entry:.2f}`{base_tag} → נוכחי: `${curr:.2f}`",
        f"{RTL}  ▸ רווח צף: {pnl_icon} `${open_pnl:+.2f}` | סה״כ: `${total_pos_profit:+.2f}`",
        f"{RTL}  ▸ R: `{total_campaign_r:+.2f}R` (צף `{open_r_val:+.2f}R`)",
        f"{RTL}  ▸ חשיפה: `{weight_pct:.1f}%` (${pos_value:,.0f})",
        f"{RTL}  ▸ סטטוס: {status} | פעולה: *{action_short}*",
    ]
    if locked_profit > 0:
        lines.append(f"{RTL}  ▸ 🔒 רווח נעול: `${locked_profit:,.0f}`")
    if giveback_risk > 0:
        lines.append(f"{RTL}  ▸ ⚡ Giveback: `${giveback_risk:,.0f}`")
    if capital_risk > 0:
        lines.append(f"{RTL}  ▸ ⚠️ סיכון הון פתוח: `${capital_risk:,.0f}`")
    return "\n".join(lines)


def fmt_summary_footer(total_open_pnl: float, total_disc_pnl: float,
                       total_algo_pnl: float, total_exposure: float,
                       acc_size: float, total_locked_profit: float,
                       total_giveback_risk: float, total_risk: float,
                       total_realized_camp: float,
                       disc_count: int, algo_count: int) -> str:
    """סיכום תיק — שורה תחתונה."""
    exp_pct = (total_exposure / acc_size * 100) if acc_size > 0 else 0
    lines = [
        f"\n{RTL}{SEP}",
        f"{RTL}📊 *סיכום תיק:*",
        f"{RTL}  ▸ חשיפה כוללת: `{exp_pct:.1f}%` (${total_exposure:,.0f})",
        f"{RTL}  ▸ רווח צף: `${total_open_pnl:+,.2f}`",
    ]
    if disc_count > 0:
        lines.append(f"{RTL}  ▸ דיסקרשן ({disc_count}): `${total_disc_pnl:+,.2f}`")
    if algo_count > 0:
        lines.append(f"{RTL}  ▸ אלגו ({algo_count}): `${total_algo_pnl:+,.2f}`")
    if total_realized_camp != 0:
        lines.append(f"{RTL}  ▸ ממומש בקמפיין: `${total_realized_camp:+,.2f}`")
    if total_locked_profit > 0:
        lines.append(f"{RTL}  ▸ 🔒 רווח נעול: `${total_locked_profit:,.0f}`")
    if total_giveback_risk > 0:
        lines.append(f"{RTL}  ▸ ⚡ Giveback סה״כ: `${total_giveback_risk:,.0f}`")
    if total_risk > 0:
        lines.append(f"{RTL}  ▸ סיכון הון פתוח: `${total_risk:,.0f}`")
    return "\n".join(lines)


def fmt_regime_report(regime: dict, exposure_pct: float,
                      exp_algo: float, exp_vcp: float, exp_ep: float,
                      acc_size: float) -> str:
    """דוח משטר שוק קומפקטי."""
    lines = [f"{RTL}🌡️ *דו\"ח משטר שוק*\n{RTL}{SEP}\n"]
    if regime.get('ok'):
        rd = regime['data']
        lines.append(f"{RTL}*שוק:* {rd['color']} {rd['status']}")
        lines.append(f"{RTL}_המלצה: {rd['text']}_")
    else:
        lines.append(f"{RTL}*שוק:* ⚪ לא ידוע")
    lines.append(f"\n{RTL}📊 *חשיפה קיימת:* `{exposure_pct:.1f}%`")
    if acc_size > 0:
        if exp_algo > 0:
            lines.append(f"{RTL}  ▸ אלגו: `{exp_algo/acc_size*100:.1f}%`")
        if exp_vcp > 0:
            lines.append(f"{RTL}  ▸ VCP: `{exp_vcp/acc_size*100:.1f}%`")
        if exp_ep > 0:
            lines.append(f"{RTL}  ▸ EP: `{exp_ep/acc_size*100:.1f}%`")
    return "\n".join(lines)


def fmt_minervini_trend_template(symbol: str, tt_result: dict) -> str:
    """פלט Trend Template מלא — 8 קריטריונים."""
    cmap = {True: "✅", False: "❌", None: "➖"}
    labels = [
        "מחיר > MA150/MA200",
        "MA150 > MA200",
        "MA200 בעלייה (חודש)",
        "MA50 > MA150/MA200",
        "מחיר > MA50",
        "30%+ מעל שפל שנה",
        "25%- מהשיא שנה",
        "RS חזקה מ-SPY (12M)",
    ]
    if not tt_result.get('ok'):
        return f"{RTL}🧠 *Trend Template — {symbol}*\n{RTL}{SEP}\n❌ אין מספיק נתונים"

    d = tt_result['data']
    passed = d['passed']
    score_emoji = "🟢" if passed >= 7 else ("🟡" if passed >= 5 else "🔴")
    lines = [
        f"{RTL}🧠 *ניתוח Trend Template — {symbol}*",
        f"{RTL}{SEP}",
    ]
    for lbl, val in zip(labels, d['criteria'].values()):
        lines.append(f"{RTL}{cmap[val]} {lbl}")
    lines += [
        f"{RTL}{SEP}",
        f"{RTL}ציון: *{passed}/8* {score_emoji}",
        f"{RTL}_{('מניה בטרנד מלא ✅' if passed >= 7 else 'תבנית חלקית' if passed >= 5 else 'לא עומדת בתבנית ❌')}_",
    ]
    return "\n".join(lines)
