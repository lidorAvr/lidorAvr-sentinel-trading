"""
telegram_formatters.py
הלפר פורמוט הודעות טלגרם — RTL עברית, אחיד ונקי.
כל הפונקציות מחזירות string מוכן לשליחה ב-parse_mode="Markdown".
"""

RTL = "‏"
SEP = "───────────────"

# ── Actionability Layer ────────────────────────────────────────────────────
# Every alert must declare what the user should do with it.
ACTIONABILITY_LABELS = {
    "action_required": "🔴 פעולה נדרשת",
    "review_required": "🟡 לבדוק",
    "observation_only": "⚪ מידע בלבד",
    "system_health":   "🔧 בריאות מערכת",
    "external_managed": "🟠 מנוהל חיצונית — Sentinel בפיקוח בלבד",
}


def fmt_actionability(level: str) -> str:
    """Return a formatted actionability line for any Telegram message."""
    label = ACTIONABILITY_LABELS.get(level, f"⚪ {level}")
    return f"{RTL}▸ סוג התרעה: *{label}*"


def fmt_data_quality_badge(primary: str, risk_badge: str, label: str) -> str:
    """Return a compact badge string for inline display."""
    parts = [primary]
    if risk_badge:
        parts.append(risk_badge)
    parts.append(f"`{label}`")
    return " ".join(parts)


def fmt_algo_risk_note(symbol: str, open_r: float, exposure_pct: float,
                       reason: str, risk_basis: str = "Target",
                       risk_vis: int = 40) -> str:
    """
    Structured ALGO Observer risk note for Telegram.
    Actionability is always Review Required — Sentinel never issues exit instructions.
    """
    return "\n".join([
        f"{RTL}🧠 *Sentinel Risk Note*",
        f"{RTL}{SEP}",
        f"{RTL}סימול: *{symbol}* | אסטרטגיה: `ALGO` | מצב: 🟠 מנוהל חיצונית",
        f"{RTL}Open R: `{open_r:.2f}R` ({risk_basis} Risk Base) | חשיפה: `{exposure_pct:.1f}%`",
        f"{RTL}שקיפות סיכון: `{risk_vis}/100`",
        f"{RTL}{SEP}",
        f"{RTL}מה קרה: {reason}",
        f"{RTL}{SEP}",
        fmt_actionability("review_required"),
        f"{RTL}▸ לוודא שהאלגו פעיל ומחובר.",
        f"{RTL}▸ אין המלצת יציאה ידנית מ-Sentinel.",
    ])


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

    r_str = f"`{total_campaign_r:+.2f}R` (צף `{open_r_val:+.2f}R`)"
    if total_campaign_r == 0 and open_r_val == 0 and capital_risk == 0 and locked_profit == 0:
        r_str = "`N/A` ⚠️ חסר סטופ התחלתי"

    lines = [
        f"{RTL}*{i}. {sym}*{addon_tag} | 🏷️ {setup} | {days_held}d",
        f"{RTL}  ▸ כניסה: `${entry:.2f}`{base_tag} → נוכחי: `${curr:.2f}`",
        f"{RTL}  ▸ רווח צף: {pnl_icon} `${open_pnl:+.2f}` | סה״כ: `${total_pos_profit:+.2f}`",
        f"{RTL}  ▸ R: {r_str}",
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
    if disc_count == 0 and algo_count == 0:
        lines.append(f"{RTL}  ▸ ⚠️ אין פוזיציות מזוהות (בדוק setup_type)")
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
    """דוח משטר שוק — עם נתוני בסיס שקופים."""
    lines = [f"{RTL}🌡️ *דו\"ח משטר שוק*\n{RTL}{SEP}\n"]
    if regime.get('ok'):
        rd = regime['data']
        lines.append(f"{RTL}*שוק:* {rd['color']} {rd['status']}")
        lines.append(f"{RTL}_המלצה: {rd['text']}_")
        sig = rd.get('signals', {})
        if sig:
            chk = lambda v: "✅" if v else "❌"
            na = lambda v: "—" if v is None else f"${v:,.2f}"
            score = sig.get('score', '?')
            max_score = sig.get('max_score', 4)
            lines.append(f"\n{RTL}📐 *בסיס ציון {score}/{max_score}:*")
            lines.append(f"{RTL}  {chk(sig.get('spy_above_ma20'))} SPY `{na(sig.get('spy_close'))}` מעל MA20 `{na(sig.get('spy_ma20'))}`")
            lines.append(f"{RTL}  {chk(sig.get('spy_above_ma50'))} SPY מעל MA50 `{na(sig.get('spy_ma50'))}`")
            lines.append(f"{RTL}  {chk(sig.get('spy_ma20_above_ma50'))} MA20 מעל MA50 (מגמה)")
            if sig.get('qqq_above_ma20') is not None:
                lines.append(f"{RTL}  {chk(sig.get('qqq_above_ma20'))} QQQ `{na(sig.get('qqq_close'))}` מעל MA20 `{na(sig.get('qqq_ma20'))}`")
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
    lines.append(f"\n{fmt_actionability('observation_only')}")
    return "\n".join(lines)


def fmt_adaptive_risk_block(risk_rec: dict, settle_info: dict | None = None) -> str:
    """בלוק המלצת סיכון אדפטיבי — מוצג בדוח משטר שוק ובסיכום תיק."""
    if not risk_rec.get('ok'):
        msg = risk_rec.get('message', 'אין מספיק נתונים')
        return f"\n{RTL}{SEP}\n{RTL}🎯 *סיכון אדפטיבי:* ⚪ {msg}"
    lines = [f"\n{RTL}{SEP}", f"{RTL}🎯 *המלצת סיכון אדפטיבי*",
             fmt_actionability("review_required")]
    lines.append(f"{RTL}חום מסחר: {risk_rec['heat_color']} *{risk_rec['heat_label']}* (ציון: `{risk_rec['heat_score']:.0f}/100`)")

    # Multi-window breakdown (new fields — shown if present)
    s9_sc  = risk_rec.get("s9_score")
    m21_sc = risk_rec.get("m21_score")
    l50_sc = risk_rec.get("l50_score")
    if s9_sc is not None:
        lines.append(f"{RTL}  ▸ ציון (0-100) לפי טווח: S9(9)=`{s9_sc:.0f}` | M21(21)=`{m21_sc:.0f}` | L50(50)=`{l50_sc:.0f}`")

    # Win rate per window
    s9_wr  = risk_rec.get("recent_10_wr", 0)  # backward-compat: mapped from S9
    l50_wr = risk_rec.get("all_50_wr", 0)
    n50 = risk_rec.get('n_used_50', risk_rec.get('n_trades', 0))
    if risk_rec.get("s9_stats") and risk_rec.get("l50_stats"):
        n9  = risk_rec["s9_stats"]["n"]
        n50 = risk_rec["l50_stats"]["n"]
        lines.append(f"{RTL}  ▸ Win Rate — S9 ({n9}): `{s9_wr:.0f}%` | L50 ({n50}): `{l50_wr:.0f}%`")
    else:
        n10 = risk_rec.get('n_used_10', min(10, risk_rec.get('n_trades', 10)))
        lines.append(f"{RTL}  ▸ שיעור הצלחה ({n10} אחרונות): `{s9_wr:.0f}%`")

    # Streak
    if risk_rec['win_streak'] > 0:
        lines.append(f"{RTL}  ▸ רצף רווחים: `{risk_rec['win_streak']}` עסקאות")
    elif risk_rec['loss_streak'] > 0:
        lines.append(f"{RTL}  ▸ ⚠️ רצף הפסדים: `{risk_rec['loss_streak']}` עסקאות")

    # Heat factors — includes open position adjustment if nonzero (no separate display needed)
    factors = risk_rec.get("heat_factors", [])
    for f_line in factors[:4]:
        lines.append(f"{RTL}  ▸ {f_line}")

    curr_pct = risk_rec['current_risk_pct']
    rec_pct  = risk_rec['recommended_risk_pct']
    curr_usd = risk_rec['current_risk_usd']
    rec_usd  = risk_rec['recommended_risk_usd']
    direction = risk_rec['direction']
    arrow = "⬆️" if direction == 'up' else ("⬇️⬇️" if direction == 'down_fast' else "➡️")
    lines.append(f"\n{RTL}{arrow} *{risk_rec['step_type']}*")
    lines.append(f"{RTL}  סיכון נוכחי: `{curr_pct:.2f}%` (`${curr_usd:,.0f}` לעסקה)")
    if rec_pct == curr_pct:
        lines.append(f"{RTL}  סיכון מוצע: `{rec_pct:.2f}%` — *ללא שינוי*")
    else:
        lines.append(f"{RTL}  סיכון מוצע: `{rec_pct:.2f}%` (`${rec_usd:,.0f}` לעסקה)")

    # Settle period note — shown when user just confirmed a raise/cut within 48h
    if settle_info and settle_info.get("active") and settle_info.get("dir") == direction:
        hrs = settle_info["hours_remaining"]
        lines.append(
            f"{RTL}📌 *תקופת התבססות:* שינוי בוצע לאחרונה — "
            f"עוד `{hrs:.0f}ש` לפני שהמלצה הבאה תישלח"
        )

    # What to improve (new field)
    improve = risk_rec.get("what_to_improve", [])
    if improve:
        lines.append(f"\n{RTL}🔼 לשיפור:")
        for imp in improve[:3]:
            lines.append(f"{RTL}  → {imp}")

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


# ── Add-On Risk Card ──────────────────────────────────────────────────────────

def fmt_addon_card(plan: dict, symbol: str = "") -> str:
    """
    Format the Add-On Risk Card for Telegram.
    Always shows: campaign state, proposed add, result-if-stopped, decision, stop mode.
    """
    import addon_risk_engine as are

    if not plan.get("ok"):
        msg = plan.get("message") or plan.get("error", "שגיאת חישוב")
        return f"\n{RTL}{SEP}\n{RTL}📌 *חיזוק — {symbol}*\n{RTL}⚠️ {msg}"

    status = plan["status"]
    status_emoji = {
        are.APPROVED:      "✅ מאושר",
        are.WATCH:         "👁 צפייה",
        are.BLOCKED:       "🚫 חסום",
        are.MANUAL_REVIEW: "⚠️ בדיקה ידנית",
    }.get(status, status)

    ls   = plan["lot_state"]
    lines = [
        f"\n{RTL}{SEP}",
        f"{RTL}📌 *Add-On Planner{f': {symbol}' if symbol else ''}*",
        f"{RTL}סטטוס: *{status_emoji}*",
        f"\n{RTL}📊 *מצב קמפיין נוכחי:*",
        f"{RTL}  ▸ Open R: `{ls['open_r']:.1f}R`" if ls.get("open_r") is not None else f"{RTL}  ▸ Open R: לא זמין",
        f"{RTL}  ▸ סיכון מקורי: `${ls['original_risk_usd']:.0f}`",
        f"{RTL}  ▸ רווח נעול בסטופ: `${ls['locked_profit_usd']:.0f}`",
        f"{RTL}  ▸ סיכון פתוח: `${ls['open_risk_usd']:.0f}`",
        f"{RTL}  ▸ רווח ממומש: `${ls['realized_pnl_usd']:.0f}`",
        f"{RTL}  ▸ תוצאה אם הסטופ הנוכחי נפגע: `${ls['net_result_if_stop_hit']:.0f}`",
    ]

    lines += [
        f"\n{RTL}🔢 *הוספה מוצעת:*",
        f"{RTL}  ▸ כניסה: `${plan['add_entry']:.2f}` | סטופ: `${plan['add_stop']:.2f}`",
        f"{RTL}  ▸ סיכון למניה: `${plan['risk_per_share']:.2f}`",
        f"{RTL}  ▸ כמות מוצעת: `{plan['proposed_qty']}` מניות",
        f"{RTL}  ▸ סיכון ההוספה: `${plan['addon_risk_usd']:.0f}`",
        f"{RTL}  ▸ מקסימום מותר: `{plan['max_qty']}` מניות",
    ]

    # Result if stopped
    result = plan["result_if_stopped"]
    result_emoji = "🟢" if result > 0 else ("🟡" if result >= plan["hard_floor_usd"] else "🔴")
    r_str = f" ({plan['result_r']:.1f}R)" if plan.get("result_r") is not None else ""
    lines += [
        f"\n{RTL}📉 *תוצאה אם הסטופ נפגע:*",
        f"{RTL}  {result_emoji} `${result:.0f}`{r_str}",
        f"{RTL}  ▸ רצפה: `${plan['hard_floor_usd']:.0f}` (-25% סיכון מקורי)",
    ]

    # Stop mode
    lines += [
        f"\n{RTL}🔒 *מצב סטופ מומלץ:* `{plan['stop_mode']}`",
        f"{RTL}  ▸ {plan['stop_mode_desc']}",
    ]

    # Reasons / Blocks / Warnings
    if plan.get("reasons"):
        lines.append(f"\n{RTL}✅ *אישורים:*")
        for r in plan["reasons"][:3]:
            lines.append(f"{RTL}  {r}")
    if plan.get("blocks"):
        lines.append(f"\n{RTL}🚫 *חסימות:*")
        for b in plan["blocks"][:3]:
            lines.append(f"{RTL}  {b}")
    if plan.get("warnings"):
        lines.append(f"\n{RTL}⚠️ *אזהרות:*")
        for w in plan["warnings"][:2]:
            lines.append(f"{RTL}  {w}")

    return "\n".join(lines)


# ── Heat Thermometer ──────────────────────────────────────────────────────────

# Sprint 8 #10 (Mobile UX from Sarah, Meeting 6 backlog #28).
# Block characters (█░) are bidirectional in Hebrew RTL contexts and visually
# flip on iOS Telegram, so a 70%-filled bar can read as 30%-filled. Coloured
# emoji circles render left-to-right inside RTL lines on every Telegram client
# (iOS, Android, web, desktop) — verified by Sarah on iPhone 14 + Pixel 7.
_HEAT_FILLED  = "🟢"
_HEAT_EMPTY   = "⚪"
_HEAT_BLOCKS  = 10

_HEAT_LABEL_MAP = [
    (80, "🔥 חם מאוד"),
    (60, "🟠 חם"),
    (40, "🟡 מתון"),
    (20, "🔵 קר"),
    (0,  "❄️ קר מאוד"),
]


def _score_to_bar(score: float, blocks: int = _HEAT_BLOCKS) -> str:
    filled = round(max(0, min(score, 100)) / 100 * blocks)
    return _HEAT_FILLED * filled + _HEAT_EMPTY * (blocks - filled)


def _heat_label(score: float) -> str:
    for threshold, label in _HEAT_LABEL_MAP:
        if score >= threshold:
            return label
    return "❄️ קר מאוד"


def fmt_heat_thermometer(risk_rec: dict) -> str:
    """
    Visual heat thermometer for Telegram — S9 / M21 / L50 window breakdown.

    Returns a ready-to-send Markdown string.
    """
    if not risk_rec.get("ok"):
        msg = risk_rec.get("message", "אין מספיק נתונים")
        return f"{RTL}🌡️ *מד החום:* ⚪ {msg}"

    score = risk_rec.get("heat_score", 0)
    bar   = _score_to_bar(score)
    label = _heat_label(score)

    lines = [
        f"{RTL}{SEP}",
        f"{RTL}🌡️ *מד חום מסחר*",
        f"{RTL}`[{bar}]` *{score:.0f}/100* — {label}",
    ]

    s9_sc  = risk_rec.get("s9_score")
    m21_sc = risk_rec.get("m21_score")
    l50_sc = risk_rec.get("l50_score")

    if s9_sc is not None and m21_sc is not None and l50_sc is not None:
        lines += [
            f"\n{RTL}📊 *פירוט לפי טווח:*",
            f"{RTL}  S9  `[{_score_to_bar(s9_sc, 5)}]` `{s9_sc:.0f}`",
            f"{RTL}  M21 `[{_score_to_bar(m21_sc, 5)}]` `{m21_sc:.0f}`",
            f"{RTL}  L50 `[{_score_to_bar(l50_sc, 5)}]` `{l50_sc:.0f}`",
        ]

    s9_wr  = risk_rec.get("recent_10_wr", 0)
    l50_wr = risk_rec.get("all_50_wr", 0)
    if risk_rec.get("s9_stats") and risk_rec.get("l50_stats"):
        n9  = risk_rec["s9_stats"]["n"]
        n50 = risk_rec["l50_stats"]["n"]
        lines.append(f"{RTL}  Win Rate — S9 ({n9}): `{s9_wr:.0f}%` | L50 ({n50}): `{l50_wr:.0f}%`")

    curr_pct  = risk_rec.get("current_risk_pct", 0)
    rec_pct   = risk_rec.get("recommended_risk_pct", 0)
    direction = risk_rec.get("direction", "hold")
    arrow = "⬆️" if direction == "up" else ("⬇️" if direction in ("down", "down_fast") else "➡️")
    change = f" (כרגע: `{curr_pct:.2f}%`)" if rec_pct != curr_pct else " ← ללא שינוי"
    lines.append(f"\n{RTL}{arrow} סיכון מומלץ: `{rec_pct:.2f}%`{change}")

    return "\n".join(lines)
