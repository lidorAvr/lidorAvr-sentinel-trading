"""
telegram_formatters.py
הלפר פורמוט הודעות טלגרם — RTL עברית, אחיד ונקי.
כל הפונקציות מחזירות string מוכן לשליחה ב-parse_mode="Markdown".
"""

RTL = "‏"
SEP = "───────────────"

# Sprint-12 / Mark §3 — the SINGLE canonical honest price-fallback label.
# VERBATIM from MARK_SPRINT12_RULINGS.md §3 (engineering invents no wording).
# Shown ONLY when ec.get_live_price() returned None for that figure and the
# entry/last price was substituted (per-figure, binary on the actual None —
# never a guess). One source, reused at every site (like _SNAPSHOT_LABEL).
PRICE_FALLBACK_LABEL = "‏⚠️ (מחיר לא חי — לפי מחיר כניסה, לא בזמן אמת)"

# ── RISK-1d — single source of truth for at-entry-price display ───────────────
# Sibling of PRICE_FALLBACK_LABEL above (Mark §3), serving the SEPARATE
# at-entry-lock surfacing contract documented in docs/DATA_CONTRACTS.md:70-78.
# Shown ONLY when `locked_entry_price IS NULL` AND mode='live' — the row exists
# but has not yet been locked (RISK-1b forward-capture, RISK-1c backfill, or
# admin /at_entry correction will eventually lock it). For mode='historical'
# (default for byte-locked April / every backwards-compatible caller) the
# label is NEVER shown — `price` is read exactly as before. AGENTS.md #1:
# never silently substitute a fallback value for the real one.
ENTRY_NOT_LOCKED_LABEL = "‏⚠️ (מחיר לא-נעול — עלול לזוז עם re-sync)"


def resolve_entry_display(price, locked_entry_price=None, *,
                          mode: str = "live") -> dict:
    """Single canonical resolver — given (price, locked_entry_price, mode)
    decide WHICH number to display as the at-entry anchor and WHETHER the
    not-yet-locked banner is appended.

    Consumed by THREE surfaces (Telegram /portfolio card, AI Master Context
    Export, and the dashboard's Command-Center expander) so the same row
    cannot show different entry numbers across surfaces (anti-drift, the
    direct fix for the MRVL $87-vs-$170 regression that motivated RISK-1).

    Pure / read-only: no Supabase, no engine_core, no telebot import.
    Defensive on every input type — non-numeric / None / 0 / negative
    locked_entry_price all collapse to "not locked" and fall back to price.

    Returns: {"entry": float, "banner": str, "is_locked": bool, "mode": str}
      • mode='historical' (default for byte-locked April + every legacy
        caller): always {entry=price, banner="", is_locked=False}. The new
        lock columns are IGNORED — `price` is read exactly as before, so
        analytics_engine / the LOCKED-April fixture stay byte-identical.
      • mode='live' (opt-in by the 3 display surfaces): when
        locked_entry_price is a positive number → {entry=locked_entry_price,
        banner="", is_locked=True} (silent on-locked, by design — the
        absence of warning IS the signal). When locked_entry_price is NULL /
        0 / negative / non-numeric → {entry=price, banner=
        ENTRY_NOT_LOCKED_LABEL, is_locked=False} (the legacy `price` is
        still shown — the banner discloses it is not the canonical at-entry
        anchor, never a silent substitution).
    """
    def _coerce_float(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    if mode == "historical":
        return {
            "entry": _coerce_float(price) or 0.0,
            "banner": "",
            "is_locked": False,
            "mode": "historical",
        }

    locked_f = _coerce_float(locked_entry_price)
    if locked_f is not None and locked_f > 0:
        return {
            "entry": locked_f,
            "banner": "",
            "is_locked": True,
            "mode": "live",
        }
    return {
        "entry": _coerce_float(price) or 0.0,
        "banner": ENTRY_NOT_LOCKED_LABEL,
        "is_locked": False,
        "mode": "live",
    }

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


# ── R-ALGO-3 (Phase ALGO-1 W-A3 / HONESTY-FIX, presentation-only) ──────────
# The L50 window brands its score "L50(50)" / "L50" even when the real sample
# is <50 (e.g. 9 closed campaigns ⇒ "L50(50)" — false confidence feeding a
# risk-raise read-out). The honest helper engine_core.get_sample_size_context
# ALREADY exists (engine_core.py:1205) and is reused here VERBATIM (CALLED,
# never modified — engine_core.py stays 0-diff). CLAUDE.md #1.
_L50_TARGET_SAMPLE = 50  # the L50 window's nominal size (adaptive_risk_engine [:50])


def _l50_true_sample(risk_rec: dict) -> int:
    """The TRUE L50 sample size actually used (closed campaigns in the L50
    window), not the hardcoded literal 50. Mirrors the same source the Win-Rate
    sub-lines already read (l50_stats['n']), falling back to n_used_50/n_trades.
    """
    try:
        l50 = risk_rec.get("l50_stats")
        if l50 and l50.get("n") is not None:
            return int(l50["n"])
    except Exception:
        pass
    try:
        return int(risk_rec.get("n_used_50", risk_rec.get("n_trades", 0)) or 0)
    except Exception:
        return 0


# ── R-ALGO-3 finish (Sprint-30 G5 / HONESTY-FIX, presentation-only) ─────────
# The adaptive score line still printed the HARDCODED window literal
# "S9(9)=… | M21(21)=… | L50(50)=…" directly ABOVE the honest
# "מדגם נוכחי: N/50" caveat W-A3 added — an on-screen self-contradiction
# (literal claims 50 while its own caveat one line down says e.g. 9/50).
# The parentheticals are the window's NOMINAL size, not the TRUE sample
# actually in each window. adaptive_risk_engine builds the windows as
# disc_camps[:9]/[:21]/[:50] and _window_stats(...)['n'] == len(window) ==
# min(window_size, len(disc_camps)) (adaptive_risk_engine.py:283-314,
# 463-465,561-563). So when the book is small all three collapse to the
# same true N (no contradiction with the caveat); when there ARE ≥50
# closed campaigns the true Ns are exactly (9,21,50) ⇒ the line is
# BYTE-IDENTICAL to today. ZERO math/KPI change; engine_core 0-diff
# (true Ns are read from the SAME s9/m21/l50_stats['n'] the Win-Rate
# sub-line already consumes — CALLED/consumed only). CLAUDE.md #1.
_SCORE_WINDOW_NOMINALS = (9, 21, 50)  # S9 / M21 / L50 nominal window sizes


def _score_line_window_labels(risk_rec: dict) -> tuple:
    """Return the (S9, M21, L50) parenthetical sizes for the score line.

    Returns the TRUE per-window sample sizes (the same s9/m21/l50_stats['n']
    the Win-Rate sub-line already reads) ONLY when ALL THREE window-stat
    dicts carry an int `n` — otherwise returns the unchanged nominal literal
    (9, 21, 50) so the line stays BYTE-IDENTICAL whenever the true sample is
    not fully known (and so legacy/synthetic risk_recs that omit a window
    stat — e.g. the W-A3 fixture without m21_stats — keep today's literal,
    no existing pin weakened). Whenever there ARE ≥50 closed campaigns the
    three true Ns are exactly (9, 21, 50) ⇒ byte-identical by construction.
    """
    try:
        s9 = risk_rec.get("s9_stats")
        m21 = risk_rec.get("m21_stats")
        l50 = risk_rec.get("l50_stats")
        if (s9 and m21 and l50
                and s9.get("n") is not None
                and m21.get("n") is not None
                and l50.get("n") is not None):
            return (int(s9["n"]), int(m21["n"]), int(l50["n"]))
    except Exception:
        pass
    return _SCORE_WINDOW_NOMINALS


def _l50_sample_honesty_line(n_l50: int, stat_base: str | None = None) -> str | None:
    """When the real L50 sample is <50, return an honest disclosure line using
    engine_core.get_sample_size_context's OWN wording/contract (no invented
    UX). When >=50, return None so the existing "L50(50)"/"L50" literal stays
    BYTE-IDENTICAL (zero math/KPI change). Lazy import keeps this module
    dependency-light and avoids any import cycle.

    Phase ALGO-2 T-A1/T-C2: `stat_base` is OPT-IN and defaults to None so the
    line is BYTE-IDENTICAL for every existing caller. When the SEPARATE
    longer-rolling manual base actually fed the windows
    (`stat_base == "longer_manual_rolling"`) the line honestly names the true
    base so the founder is never told "8-week window" when it is the long
    base, nor vice-versa. The legacy report-window base ⇒ no extra clause
    (byte-identical).
    """
    if n_l50 >= _L50_TARGET_SAMPLE:
        return None
    try:
        import engine_core as _ec
        ctx = _ec.get_sample_size_context(n_l50)
        label = ctx.get("label", "")
    except Exception:
        label = ""
    suffix = f" — {label}" if label else ""
    base_clause = ""
    if stat_base == "longer_manual_rolling":
        base_clause = f"{RTL}  ℹ️ הבסיס: היסטוריית מסחר ידנית מתגלגלת (לא חלון הדיווח)\n"
    return (f"{base_clause}{RTL}  ⚠️ L50 מבוסס מדגם חלקי — "
            f"מדגם נוכחי: {n_l50}/{_L50_TARGET_SAMPLE}{suffix}")


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
                      capital_risk: float = 0,
                      price_is_fallback: bool = False,
                      dual_r_fragment: str | None = None,
                      entry_banner: str = "") -> str:
    """כרטיס פוזיציה אחד — קומפקטי וברור.

    ``price_is_fallback`` (Sprint-12 / Mark §3): default ``False`` keeps every
    existing caller/test BYTE-IDENTICAL. When the CALLER detected that
    ``ec.get_live_price()`` returned ``None`` for this position and fell back
    to ``entry`` as ``curr``, it passes ``True`` and the card appends the
    single canonical honest label after the price (label only — no number is
    recomputed or restated; this is a pure formatter, DEC-20260510-005, so the
    fallback DETECTION stays in the caller).

    ``dual_r_fragment`` (Sprint-15 / Mark §1, DEC-20260515-011): default
    ``None`` keeps every existing caller/test BYTE-IDENTICAL. When the CALLER
    builds the canonical ``fmt_dual_r(...)`` fragment (Structure R via the
    EXISTING ``compute_r_true``, Account R via the EXISTING ``compute_r_target``)
    it is passed in and REPLACES the silent ``(צף x.xxR)`` open fragment. The
    primary campaign-R number (``total_campaign_r``) stays byte-identical — only
    the open-R sub-fragment is correctly relabelled with the dual metric.

    ``entry_banner`` (RISK-1d): default ``""`` keeps every existing caller/test
    BYTE-IDENTICAL. When the CALLER built the not-yet-locked banner via
    ``resolve_entry_display(mode='live')`` and got back a non-empty string, it
    is appended after the entry price on the same line. Pure rendering — the
    formatter never decides locked-vs-not-locked; the resolver upstream does.
    """
    pnl_icon = '🟢' if open_pnl >= 0 else '🔴'
    addon_tag = f" +(+{add_on_count})" if add_on_count > 0 else ""
    base_tag = f" _(בסיס ${base_price:.2f})_" if add_on_count > 0 and base_price > 0 else ""

    if dual_r_fragment is not None:
        r_str = f"`{total_campaign_r:+.2f}R` ({dual_r_fragment})"
    else:
        r_str = f"`{total_campaign_r:+.2f}R` (צף `{open_r_val:+.2f}R`)"
    if total_campaign_r == 0 and open_r_val == 0 and capital_risk == 0 and locked_profit == 0:
        r_str = "`N/A` ⚠️ חסר סטופ התחלתי"

    curr_line = f"{RTL}  ▸ כניסה: `${entry:.2f}`{base_tag}"
    if entry_banner:
        curr_line += f" {entry_banner}"
    curr_line += f" → נוכחי: `${curr:.2f}`"
    if price_is_fallback:
        curr_line += f" {PRICE_FALLBACK_LABEL}"
    lines = [
        f"{RTL}*{i}. {sym}*{addon_tag} | 🏷️ {setup} | {days_held}d",
        curr_line,
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
        # G5: window parentheticals reflect the TRUE per-window sample so the
        # score line no longer contradicts the "מדגם נוכחי: N/50" caveat
        # below it. When the true sample is unknown or there are ≥50 closed
        # campaigns the labels are exactly (9,21,50) ⇒ BYTE-IDENTICAL.
        _wS9, _wM21, _wL50 = _score_line_window_labels(risk_rec)
        lines.append(f"{RTL}  ▸ ציון (0-100) לפי טווח: S9({_wS9})=`{s9_sc:.0f}` | M21({_wM21})=`{m21_sc:.0f}` | L50({_wL50})=`{l50_sc:.0f}`")
        # R-ALGO-3 / W-A3: honest disclosure when the TRUE L50 sample is <50.
        # >=50 ⇒ helper returns None ⇒ the line above is byte-identical.
        _l50_honesty = _l50_sample_honesty_line(
            _l50_true_sample(risk_rec), stat_base=risk_rec.get("stat_base"))
        if _l50_honesty is not None:
            lines.append(_l50_honesty)

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


def fmt_heat_thermometer(risk_rec: dict, include_legend: bool = False) -> str:
    """
    Visual heat thermometer for Telegram — S9 / M21 / L50 window breakdown.

    include_legend: append a threshold legend (useful in scheduled reports
    where the user sees the thermometer infrequently and needs the scale
    reminded).

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
        # R-ALGO-3 / W-A3: this block previously showed NO N for L50. Append an
        # honest disclosure when the TRUE L50 sample is <50; >=50 ⇒ helper
        # returns None ⇒ the three score lines above stay byte-identical.
        _l50_honesty = _l50_sample_honesty_line(
            _l50_true_sample(risk_rec), stat_base=risk_rec.get("stat_base"))
        if _l50_honesty is not None:
            lines.append(_l50_honesty)

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

    if include_legend:
        lines.append(f"\n{RTL}_סולם:_ 🔥 ≥80 חם מאוד | 🟠 60-79 חם | 🟡 40-59 מתון | 🔵 20-39 קר | ❄️ <20 קר מאוד")

    return "\n".join(lines)


# ── Sprint-13 / Mark §2 — missing-stops split-label (READ-ONLY, pure) ───────
# Mark MARK_SPRINT13_RULINGS.md §2 (:50-67): split the existing 55 detected
# missing-stop rows by lifecycle — never fabricate a stop, never a stat.
#
#   • OPEN position missing a stop  = real risk gap (urgent). Routes to the
#     EXISTING journal-backlog (telegram_backlog.py:86-97), which prompts the
#     founder for the *true* initial stop and writes ONLY what the founder
#     types (or the existing -1 skip sentinel) — NEVER a default/fabricated
#     value. These rows stay out of WR/Expectancy/PF until completed
#     (AGENTS.md #8; open_tasks.py:271-281 COMPLETE_RISK_DATA, urgency=None,
#     never counted) — this helper adds NO new ruleset key / §6 entry, so
#     test_ruleset_matches_methodology_spec stays green.
#   • CLOSED / archived row missing a stop = hygiene only. Handled by the
#     already-gated /clean (telegram_clean_gate.py — defaulted-NO, open
#     campaigns excluded, 30-day absolute window). The bot_health.py:92-98
#     Sprint-12 notice text stays VERBATIM for this subset (Mark §2 :71-72).
#
# This function is the approved-surface label only. It performs ZERO trade /
# campaign / R / NAV math: the caller passes in the rows it already detected
# AND the open-campaign id set it already derived (engine's existing
# net-qty>0.001 rule, engine_core.get_open_positions_campaign:473-514). The
# helper is referentially transparent: same inputs → same output, no I/O,
# no Supabase, no fabricated stop number, no $/R, no stat.

# VERBATIM from MARK_SPRINT13_RULINGS.md §2 (:76-80). Engineering invents no
# wording. {SYMBOL} is the only substitution (the row's own symbol — never a
# price). Used by the journal-backlog open-position stop-completion prompt.
MISSING_STOP_BACKLOG_HE = (
    "‏🛡️ פוזיציה פתוחה ללא סטופ — {SYMBOL}\n"
    "‏הזן את הסטופ ההתחלתי האמיתי (לדוגמה 150.50).\n"
    "‏לא יומצא ערך. עד להשלמה — לא נכלל בסטטיסטיקה."
)


def classify_missing_stops(missing_rows, open_campaign_ids):
    """Split detected missing-stop rows into open (urgent) vs closed (hygiene).

    Pure / read-only (Mark §2). No fabricated stop, no $/R, no stat.

    Parameters
    ----------
    missing_rows : iterable of mapping
        The rows the caller ALREADY detected as missing-stop (BUY, qty>0,
        stop_loss<=0). Each needs ``symbol`` and ``campaign_id`` keys. This
        function does NOT re-detect or re-query — it only labels.
    open_campaign_ids : set/iterable
        The campaign_ids the caller ALREADY derived as OPEN via the engine's
        existing net-qty>0.001 rule (engine_core.get_open_positions_campaign).
        This helper performs NO campaign math itself.

    Returns
    -------
    dict with:
        ``open_count``     int  — rows on an OPEN campaign (real risk gap)
        ``open_symbols``   sorted unique list[str]
        ``legacy_count``   int  — rows on a closed/archived/no campaign
        ``legacy_symbols`` sorted unique list[str]
        ``total``          int  — == open_count + legacy_count == len(rows)
    Invariant: ``open_count + legacy_count == total`` (every row lands in
    exactly one bucket; no row is dropped, none duplicated). No key in the
    return is ever a stop price, an R value, or a money figure.
    """
    open_ids = set(open_campaign_ids or [])
    open_syms: set = set()
    legacy_syms: set = set()
    open_count = 0
    legacy_count = 0

    for row in (missing_rows or []):
        sym = str(row.get("symbol", "")).strip() or "?"
        cid = row.get("campaign_id")
        # OPEN iff the row's campaign is in the caller-derived open set.
        # No campaign_id, or a campaign not in the open set → closed/archived
        # (hygiene). Net-quantity already decided membership upstream.
        if cid is not None and cid in open_ids:
            open_count += 1
            open_syms.add(sym)
        else:
            legacy_count += 1
            legacy_syms.add(sym)

    return {
        "open_count": open_count,
        "open_symbols": sorted(open_syms),
        "legacy_count": legacy_count,
        "legacy_symbols": sorted(legacy_syms),
        "total": open_count + legacy_count,
    }


def fmt_missing_stops_split_label(split):
    """Non-numeric Hebrew split-label line(s) for the /health notice.

    Consumes ``classify_missing_stops`` output. States the OPEN subset is an
    actionable journal-backlog item (real risk gap) and the CLOSED subset is
    hygiene via the gated /clean — count + symbols only, NEVER a stop price,
    $/R, or a stat (Mark §2 :69-72; AGENTS.md #1/#8). Returns ``""`` when
    nothing is missing (caller appends nothing).
    """
    if not split or split.get("total", 0) <= 0:
        return ""
    parts = []
    oc = split.get("open_count", 0)
    lc = split.get("legacy_count", 0)
    if oc > 0:
        osy = ", ".join(split.get("open_symbols", [])[:5])
        parts.append(
            f"{RTL}‏🛡️ פוזיציות פתוחות ללא סטופ: {oc} ({osy}) — "
            f"השלם בגיבוי היומן (ערך אמיתי בלבד, לא יומצא; "
            f"עד להשלמה לא נכלל בסטטיסטיקה)."
        )
    if lc > 0:
        lsy = ", ".join(split.get("legacy_symbols", [])[:5])
        parts.append(
            f"{RTL}‏🧹 רשומות סגורות/ארכיון ללא סטופ: {lc} ({lsy}) — "
            f"היגיינה בלבד דרך /clean (אינו משימה, אינו נספר)."
        )
    return "\n".join(parts)


# ── Sprint-15 / Mark §1-§3 — Report R-Integrity surfacing (READ-ONLY, pure) ──
#
# DEC-20260515-011 (Dual R), -012 (Risk Capital Basis label), -013 (Broker
# Reconciliation Status). These helpers are import-pure (DEC-20260510-005: no
# engine_core / supabase / telebot import). The CALLER computes the two R
# numbers via the EXISTING engine functions and passes them in — no new R / NAV
# / campaign math is introduced anywhere. Every label/threshold string below is
# VERBATIM from MARK_SPRINT15_RULINGS.md; engineering invents none.

# Mark §1 — exact label strings (verbatim).
_STRUCTURE_R_LABEL_HE = "‏R מבנה"
_ACCOUNT_R_LABEL_HE   = "‏R חשבון"
_STRUCTURE_R_LABEL_EN = "Structure R"
_ACCOUNT_R_LABEL_EN   = "Account R"
# Mark §1 — ALGO / missing-stop tokens (NEVER print 0.00R as if real).
_ALGO_NA_DISPLAY      = "—"
_ALGO_NA_NOTE_HE      = "‏(אין סטופ אמיתי)"
_ALGO_NA_AICOPY       = "N/A"
_ALGO_NA_NOTE_EN      = "(no real stop)"
_MISSING_STOP_NOTE_HE = "‏(חסר סטופ התחלתי)"
_MISSING_STOP_NOTE_EN = "(missing initial stop)"
_R_UNAVAILABLE_HE     = "‏R לא זמין"
_R_UNAVAILABLE_EN     = "R unavailable"


def dual_r_basis(*, original_campaign_risk: float,
                 frozen_target_risk_usd: float,
                 is_algo: bool) -> dict:
    """Canonical basis producer — reports WHICH of the two existing functions
    produced a valid number, so the label can no longer contradict the value.

    Performs NO division and NO R math (design §2.3). The guards mirror the
    EXISTING engine guards verbatim:
      structure_valid = original_campaign_risk > 0  (compute_r_true:999)
      account_valid   = frozen_target_risk_usd > 0  (compute_r_target:1006)
    ALGO ⇒ structure_valid forced False (no real stop) — DEC-011 / Mark §1.
    """
    structure_valid = (not is_algo) and (original_campaign_risk or 0) > 0
    account_valid = (frozen_target_risk_usd or 0) > 0
    if is_algo:
        primary_basis_label = "account"
    elif structure_valid:
        primary_basis_label = "structure"
    elif account_valid:
        primary_basis_label = "account"
    else:
        primary_basis_label = "none"
    return {
        "structure_valid": structure_valid,
        "account_valid": account_valid,
        "is_algo": bool(is_algo),
        "primary_basis_label": primary_basis_label,
    }


def fmt_dual_r(structure_r, account_r, *,
               structure_valid: bool, account_valid: bool,
               is_algo: bool, ai_copy: bool = False) -> str:
    """Single canonical dual-R fragment consumed by ALL THREE surfaces
    (produce-once, consume-thrice — anti-drift, design §2.2).

    The caller computes ``structure_r = ec.compute_r_true(...)`` and
    ``account_r = ec.compute_r_target(...)`` with the SAME inputs the inline
    expression uses today, so the primary (Structure for manual / Account for
    ALGO) number is byte-identical. This helper performs NO R math — it only
    formats two pre-computed values with Mark's verbatim labels.

    Mark §1: Structure first (= today's primary number), Account second.
    ALGO / invalid original risk ⇒ Structure token = ``—``/``N/A`` (never
    ``0.00R``); Account R only. Both unavailable ⇒ ``R unavailable``.
    """
    s_lbl = _STRUCTURE_R_LABEL_EN if ai_copy else _STRUCTURE_R_LABEL_HE
    a_lbl = _ACCOUNT_R_LABEL_EN if ai_copy else _ACCOUNT_R_LABEL_HE
    na_tok = _ALGO_NA_AICOPY if ai_copy else _ALGO_NA_DISPLAY

    # Structure side
    if structure_valid:
        s_part = f"{s_lbl}: {structure_r:.2f}R"
    elif is_algo:
        note = _ALGO_NA_NOTE_EN if ai_copy else _ALGO_NA_NOTE_HE
        s_part = f"{s_lbl}: {na_tok} {note}"
    else:
        note = _MISSING_STOP_NOTE_EN if ai_copy else _MISSING_STOP_NOTE_HE
        s_part = f"{s_lbl}: {na_tok} {note}"

    # Account side
    if account_valid:
        a_part = f"{a_lbl}: {account_r:.2f}R"
    else:
        a_part = None

    if not structure_valid and not account_valid:
        return _R_UNAVAILABLE_EN if ai_copy else _R_UNAVAILABLE_HE

    parts = [s_part]
    if a_part is not None:
        parts.append(a_part)
    return " | ".join(parts)


# Mark §2 — Risk Capital Basis declaration strings (verbatim).
def fmt_risk_capital_basis(nav: float, target_risk_usd: float, *,
                           nav_source: str = "broker",
                           ai_copy: bool = False) -> str:
    """Declaration string stating target risk is derived from NAV (Mark §2).
    Labelling ONLY — the engine still uses ``nav * risk_pct/100``
    (account_state.py:61); DEC-012 declares, does not change, the basis.

    When ``nav_source != "broker"`` the "NAV" shown is actually the
    fallback/deposited figure — disclosed honestly (AGENTS.md #1).
    """
    if ai_copy:
        base = (f"Risk Capital Basis: NAV (${nav:,.0f}) — "
                f"target risk ${target_risk_usd:.2f}")
        if nav_source != "broker":
            base += f" [NAV source: {nav_source} — not live broker NAV]"
    else:
        base = (f"{RTL}בסיס הון לסיכון: NAV (${nav:,.0f}) — "
                f"סיכון יעד ${target_risk_usd:.2f}")
        if nav_source != "broker":
            base += f" ‏⚠️ (מקור NAV: {nav_source} — לא NAV חי מהברוקר)"
    return base


# Mark §3 — Broker Reconciliation bands (thresholds = multiples of EXISTING
# constants; none invented). $10 is the verbatim production constant at
# dashboard.py:411 (adopted, not changed).
_RECON_EQ_THRESHOLD = 10.0


def classify_broker_reconciliation(nav: float, base_capital: float,
                                   db_net_pnl: float, *,
                                   reconciliation_gap: float,
                                   risk_pct_input: float,
                                   nav_source: str = "broker",
                                   max_open_campaign_risk: float = 0.0) -> dict:
    """Read-only derived reconciliation status (DEC-013 / Mark §3).

    ``reconciliation_gap`` is the ALREADY-computed gap from dashboard.py:404-405
    (`current_acc_size - (total_deposited + total_pnl_net + total_open_pnl)`),
    passed in — this helper does NOT recompute it (invariant #8). No Supabase,
    no financial math: it only classifies the existing number into Mark's 4
    bands and emits Mark's verbatim non-asserting wording.

    Bands (Mark §3 — multiples of existing constants):
      unit = base_capital * risk_pct_input / 100  (one target-risk unit)
      Balanced        : |gap| <= 10.0            (dashboard.py:411 constant)
      Minor Difference: 10.0 < |gap| <= unit
      Material Gap    : unit < |gap| <= 1.25*unit (±25% sizing band)
      Critical Data Gap: |gap| > 5*unit  OR  |gap| > max open-campaign orig risk
    """
    gap = float(reconciliation_gap)
    agap = abs(gap)
    unit = base_capital * (risk_pct_input or 0) / 100.0   # one target-risk unit
    crit_anchor = 5.0 * unit                              # Mark §3 5R anchor

    # Mark §3 (verbatim band conditions; thresholds = multiples of EXISTING
    # constants — $10 production constant, risk_pct_input unit, 5R anchor):
    #   Balanced         : |gap| <= $10
    #   Minor Difference  : $10 < |gap| <= 1 unit
    #   Material Gap      : |gap| > 1 unit  (and not Critical)
    #   Critical Data Gap : |gap| > 5*unit  OR  |gap| > any single open-campaign
    #                       original risk
    # Critical is checked FIRST so its explicit condition wins over Material.
    is_critical = (agap > crit_anchor) or (
        bool(max_open_campaign_risk) and agap > max_open_campaign_risk)

    if is_critical:
        band, band_he = "Critical Data Gap", "פער נתונים קריטי"
    elif agap <= _RECON_EQ_THRESHOLD:
        band, band_he = "Balanced", "מאוזן"
    elif agap <= unit:
        band, band_he = "Minor Difference", "הפרש מינורי"
    else:
        band, band_he = "Material Gap", "פער מהותי"

    caveat = ""
    if nav_source != "broker":
        caveat = (f"NAV side is itself {nav_source} (not live broker NAV) — "
                  f"reconciliation is provisional")

    return {
        "band": band,
        "band_he": band_he,
        "gap": round(gap, 2),
        "abs_gap": round(agap, 2),
        "unit": round(unit, 2),
        "nav_source": nav_source,
        "caveat": caveat,
    }


def fmt_broker_reconciliation(status: dict, *, ai_copy: bool = False) -> str:
    """Mark §3 verbatim honesty wording — NEVER asserts a single cause.
    Consumes ``classify_broker_reconciliation`` output (produce-once)."""
    band = status["band"]
    gap = status["gap"]
    if ai_copy:
        line = (f"Broker Reconciliation Status: {band}. Gap ${gap:,.2f}. "
                f"Cause unverified — possible deposits/withdrawals/open "
                f"positions/fees/YTD report window. Manual verification "
                f"required.")
        if status.get("caveat"):
            line += f" [{status['caveat']}]"
    else:
        line = (f"{RTL}מצב התאמה מול ברוקר: {status['band_he']}. "
                f"פער ${gap:,.2f}. הסיבה לא אומתה — ייתכן "
                f"הפקדות/משיכות/פוזיציות פתוחות/עמלות/חלון דיווח YTD. "
                f"דורש אימות ידני.")
        if status.get("caveat"):
            line += (f" ‏⚠️ (צד ה-NAV עצמו {status['nav_source']} — "
                     f"לא NAV חי; ההתאמה זמנית)")
    return line


# ── Sprint-15 / Mark §5 — BLOCKED #4/#5 framework ONLY (NO ALGO threshold) ───
# Mark §5: contract SHAPE only so the founder's forthcoming ALGO rules slot in
# without rework. Populated EXCLUSIVELY from existing engine fields
# (management_mode / risk_basis / risk_visibility_score). NO threshold defined
# here; the predicate's `rules` is supplied later by the founder. The ALGO
# Oversight Gate is NOT built (PROPOSED only). The manual dead-money path
# (_DEAD_MONEY_MAX_R=0.75) is NOT touched.

def algo_data_quality(*, management_mode: str, risk_basis: str,
                      risk_visibility_score, init_stop=None,
                      curr_stop=None) -> dict:
    """Additive derived data-quality dict for an ALGO position (Mark §5 #4).
    Populated ONLY from existing engine fields — derives no new number,
    defines no threshold. ``missing_fields`` lists which inputs are absent."""
    missing = []
    if init_stop in (None, 0, 0.0):
        missing.append("init_stop")
    if curr_stop in (None, 0, 0.0):
        missing.append("curr_stop")
    if risk_visibility_score is None:
        missing.append("risk_visibility_score")
    return {
        "state": management_mode,
        "init_stop": init_stop,
        "curr_stop": curr_stop,
        "risk_basis": risk_basis,
        "visibility": risk_visibility_score,
        "missing_fields": missing,
    }


def algo_quality_ok(quality: dict, rules=None) -> bool:
    """Pluggable predicate (Mark §5 #4). ``rules`` is supplied LATER by the
    founder — NO threshold is defined here. With no rules the contract is
    inert: returns True (no gate applied). The ALGO Oversight Gate remains
    PROPOSED / NOT built this sprint."""
    if not rules:
        return True
    # Founder-supplied rules slot in here without reworking the call sites.
    return bool(rules(quality)) if callable(rules) else True


def algo_dead_money_rule(*args, **kwargs):
    """Mark §5 #5 named stub. The manual dead-money path keeps
    ``_DEAD_MONEY_MAX_R = 0.75`` byte-identical (engine_core.py untouched).
    The ALGO branch is a stub returning a pending sentinel until the founder
    supplies the rule — NO ALGO dead-money number invented."""
    return "pending founder rule"
