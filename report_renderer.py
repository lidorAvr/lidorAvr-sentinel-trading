"""
report_renderer.py — build HTML from Jinja2 templates and convert to PDF via WeasyPrint.
Falls back to HTML-only if WeasyPrint is unavailable for ANY reason (Sprint 16:
the live incident is an OSError — missing native libs — not an ImportError, so the
WeasyPrint import is loaded lazily and guarded by a broad Exception catch instead
of being a module-top import that can abort every importer).
Charts are generated via chart_generator (Plotly+Kaleido); skipped gracefully if unavailable.
"""
import os
import logging
from datetime import datetime
from typing import Optional

_log = logging.getLogger(__name__)

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    _JINJA2_OK = True
except ImportError:
    _JINJA2_OK = False

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_REPORTS_DIR   = "/app/reports"
_CSS_PATH      = os.path.join(_TEMPLATES_DIR, "report_base.css")

# Sprint-19 §2c (MARK_SPRINT19_RULINGS.md:118-131) — minimum prior same-type
# snapshots before a realized "מול ממוצע" is shown. N=3 (smallest count where
# a mean is not dominated by a single period; matches the
# adaptive_risk_engine ≥3-closed precedent). NEVER a partial mean (#1).
_PERIOD_AVG_MIN_N = 3
# §2b — vs-average column / label wording. {k} = the REAL count averaged
# (state the real N used; never a rounded claim).
_PERIOD_AVG_LABEL = "מול ממוצע {k} {unit}"
# §2c verbatim baseline-pending token (realized vs-average), {k} = real
# available count of same-type prior snapshots. Never a number in its place.
_PERIOD_AVG_BASELINE_PENDING = (
    "📊 מול ממוצע: — · ממתין ל-3 תקופות בסיס (קיימות {k} מתוך 3)"
)
# §2a — the realized vs-previous label MUST read "(ממומש בלבד)" so it is never
# read as including the open book.
_CMP_VS_PREV_LABEL = "מול תקופה קודמת (ממומש בלבד)"

# Sprint-19 §1 — period-honest headline wording (verbatim from
# MARK_SPRINT19_RULINGS.md §1a/§1c). Nothing invented.
_HEADLINE_BADGE_TEXT = "📌 {period_word} ללא סגירות — ספר פתוח פעיל"
_HEADLINE_BADGE_CLASS = "neutral"          # → verdict-neutral (existing class)
_HEADLINE_REALIZED_SUBHEADING = "📉 ביצועים ממומשים (0 קמפיינים נסגרו בתקופה)"
_HEADLINE_REALIZED_PNL_LABEL = "רווח ממומש (0 בתקופה)"
# §1b promoted open-book banner (RTL, ALGO segregated on its own line).
_HEADLINE_BANNER_L1 = (
    '✅ 0 קמפיינים נסגרו בתקופה — אין ביצועים *ממומשים* (זה לא "ללא מסחר").'
)
_HEADLINE_BANNER_L2 = (
    "📌 ספר פתוח (לא ממומש): {n_disc} דיסקרציוני · "
    "צף ${floating_disc:+,.0f} · חשיפה {exposure_disc:.1f}%"
)
_HEADLINE_BANNER_L3_OPENED = "🆕 {n_opened_total} פוזיציות נפתחו בתקופה זו"
_HEADLINE_BANNER_L3_HELD = (
    "↳ כולן מוחזקות מתקופה קודמת (פעילות פתוחה לאורך החלון)"
)
_HEADLINE_BANNER_L4 = "📅 חלון: {period_label} · מקור: {source}"
_HEADLINE_BANNER_ALGO = (
    "🟠 ALGO (פיקוח בלבד · לא הוראה): {n_algo} פוז' · "
    "צף ${floating_algo:+,.0f} · חשיפה {exposure_algo:.1f}% — "
    "מנוהל חיצונית, ללא הוראת Sentinel"
)

# ── Sprint-20 Step-2 — CLOSED-but-excluded (DATA_INCOMPLETE / ALGO) realized
# leg. Honest disclosure of the silent excluded leg already computed at
# analytics_engine.py:57-58,144-145 (excluded_count/excluded_pnl) + the new
# additive manual/ALGO partition. ALL wording is VERBATIM from
# docs/teams/MARK_SPRINT20_RULINGS.md (§1/§2/§4) — nothing invented. NEVER
# summed into realized KPIs; a DISTINCT disclosure block; ALGO segregated
# observation-only (#8 / DEC-20260511-001). Each constant cites its Mark slot.
# §1 — manual-incomplete realized-excluded line (the mandatory "לא-מאומת"
# wording; raw realized $ with NO R/WR/PF attached). MARK_SPRINT20:§1 line.
_EXCL_MANUAL_LINE = (
    "ℹ️ {n} קמפיינים נסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge (חסר stop) — "
    "רווח/הפסד ממומש לא-מאומת: ${x:+,.0f}. השלם entry/stop כדי להיכלל."
)
# §2 — ALGO observation-only line. Carries NO instruction, NO `השלם`, never
# in headline/verdict/edge (DEC-20260511-001). MARK_SPRINT20:§2.2.
_EXCL_ALGO_LINE = (
    "🔭 {n} קמפייני ALGO נסגרו בתקופה — מנוהל חיצונית, פיקוח בלבד · לא הוראה. "
    "ממומש לא-מאומת: ${x:+,.0f} (לא נספר ב-edge)."
)
# §4 — founder-side data-completion note (mirrors bot_health.py:147 honest
# "אינו נספר" tone — a data task, NOT a system error). Shown iff
# excluded_count_manual > 0; NO instruction for the ALGO subset. MARK_SPRINT20:§4.
_EXCL_FOUNDER_NOTE = (
    "📋 {n} קמפיינים נסגרו ללא initial_stop ולכן לא נכנסו לסטטיסטיקת ה-edge. "
    "זו השלמת נתונים — לא תקלת מערכת. השלם entry/stop בכל קמפיין כדי שייספר "
    "ב-WR/Expectancy/PF/Net-R."
)
# Section heading + per-row labels for the PDF disclosure block. Derived from
# the Mark §1/§2 wording (RTL; same Hebrew terms Mark uses verbatim in the
# §1/§2 lines: "הוחרגו מסטטיסטיקת ה-edge", "חסר stop", "ALGO · פיקוח בלבד · לא
# הוראה", "ממומש לא-מאומת").
_EXCL_HEADING = "📕 קמפיינים שנסגרו בתקופה אך הוחרגו מסטטיסטיקת ה-edge"
_EXCL_CAVEAT = (
    "רווח/הפסד ממומש לא-מאומת · חסר initial stop · "
    "לא נספר ב-WR / Expectancy / PF / Net-R (#8 — אין R ללא stop)"
)
_EXCL_ROW_MANUAL = "ידני · חסר stop (DATA_INCOMPLETE)"
_EXCL_ROW_ALGO = "🟠 ALGO · פיקוח בלבד · לא הוראה"
_EXCL_ROW_TOTAL = "סה\"כ מוחרג (לא-מאומת)"
# ── Sprint-21 WS-B — NULL-`campaign_id` honest disclosure line. The wording
# is VERBATIM from docs/teams/MARK_SPRINT21_RULINGS.md §B2 — nothing invented,
# nothing paraphrased. It is STRICTLY separated from countable edge stats
# (WR/Expectancy/PF/Net-R) — never enters them, never the headline; additive
# context only, in the disjoint `unlinked_*` namespace (mirrors the Sprint-20
# `excluded_*` discipline). Shown iff in-window unlinked count > 0; NEVER a
# line when 0 (§B2 — no noise); NEVER silent-zero when >0 (§B3 / #1). The read
# flow NEVER auto-mutates Supabase to "fix" linkage — re-linking is the
# founder-run manual runbook docs/runbooks/SPRINT21_NULL_CAMPAIGN_REPAIR.md
# ONLY (§B3/§B4 / AGENTS.md #4). {N}=count, {X}=Σ stored pnl_usd (signed,2dp).
_UNLINKED_LINE = (
    "⚠️ {n} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · "
    "${x:+,.2f} · דורש קישור"
)
# ALGO observation-only caveat — reuse the canonical Sprint-18 constant
# (report_open_book.ALGO_EXTERNAL_CAVEAT) so the wording is identical.


def compute_period_average(snapshots: Optional[list],
                           n: int = _PERIOD_AVG_MIN_N) -> dict:
    """Sprint-19 §2b — realized "מול ממוצע", PURE presentation helper.

    Arithmetic mean of the SAME stored snapshot KPI floats that
    `report_snapshot_store.save:48-58` already persisted and that
    `compute_period_comparison:207-208` already compares — `win_rate`,
    `expectancy_r`, `profit_factor`, `total_r_net`, `realized_pnl`,
    `missing_stop_rate`, `oversized_rate`, `avg_r_per_day`. It computes **NO**
    R / NAV / campaign / Expectancy / PF math — only `mean()` of values the
    realized engine already produced. `profit_factor` stored as `None`
    (inf-guarded by `_safe_float` on save) is skipped PER-METRIC so the mean
    stays honest.

    `snapshots`: the `report_snapshot_store.load_recent(period_type, ...)`
    list (newest first), READ-ONLY. The current period is NOT yet written when
    this is called (snap_save happens after render), so each is a true prior.

    #1 — returns ``{"available": False, ...}`` when fewer than `n` prior
    snapshots exist (baseline-pending). A partial mean over 1–2 periods is
    NEVER computed or shown — that would present a fabricated/unstable mean as
    "the average". Never raises.
    """
    metrics = ["win_rate", "expectancy_r", "profit_factor", "total_r_net",
               "realized_pnl", "missing_stop_rate", "oversized_rate",
               "avg_r_per_day"]
    try:
        snaps = [s for s in (snapshots or []) if isinstance(s, dict)]
        k = len(snaps)
        if k < n:
            return {"available": False, "n_have": k, "n_need": n,
                    "baseline_pending_text":
                        _PERIOD_AVG_BASELINE_PENDING.format(k=k),
                    "metrics": {}}
        used = snaps[:n]
        kk = len(used)
        out = {}
        for m in metrics:
            vals = []
            for s in used:
                v = s.get(m)
                # profit_factor None (inf-guarded on save) → skip per-metric.
                if v is None:
                    continue
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
            if vals:
                out[m] = round(sum(vals) / len(vals), 4)
        return {"available": True, "n_have": k, "n_need": n,
                "n_used": kk, "baseline_pending_text": "", "metrics": out}
    except Exception as e:
        return {"available": False, "n_have": 0, "n_need": n,
                "baseline_pending_text":
                    _PERIOD_AVG_BASELINE_PENDING.format(k=0),
                "metrics": {}, "error": str(e)}


# ── Public API ─────────────────────────────────────────────────────────────────

def render_weekly(
    analytics: dict,
    account_state: dict,
    period_start: datetime,
    period_end: datetime,
    comparison: Optional[dict] = None,
    dev_score_data: Optional[dict] = None,
    system_health: Optional[dict] = None,
    coaching_insights: Optional[list] = None,
    risk_adherence_rate: Optional[float] = None,
    open_book: Optional[dict] = None,
    mark_delta: Optional[dict] = None,
    period_average: Optional[dict] = None,
    open_book_history: Optional[dict] = None,
) -> str:
    """
    Render weekly PDF report. Returns path to PDF file.
    Raises on critical failures (e.g. Jinja2 not installed).

    Sprint-18: `open_book`/`mark_delta` are ADDITIVE optional dicts (default
    None ⇒ byte-identical for callers/tests not passing them). They surface the
    unrealized open-book via SEPARATE `open_book_*` ctx keys only — the realized
    KPI keys in `_base_ctx` are never touched (realized-byte-identical proof).

    Sprint-19: `period_average`/`open_book_history` ADDITIVE optional (default
    None ⇒ byte-identical). They feed the §1 period-honest headline + §2
    vs-average context via `headline_*`/`cmp_*`/`obcmp_*` keys only — same
    additive-seam pattern; `_base_ctx` realized keys + `compute_verdict`
    untouched.
    """
    from analytics_engine import compute_verdict
    verdict, verdict_class = compute_verdict(analytics)

    output_dir = os.path.join(_REPORTS_DIR, "weekly")
    period_label = _period_label(period_start, period_end)
    charts     = _generate_weekly_charts(analytics, period_label, output_dir)

    ctx = _base_ctx(analytics, account_state, period_start, period_end,
                    verdict, verdict_class, dev_score_data, system_health,
                    risk_adherence_rate)
    ctx.update({
        "comparison":        comparison or {},
        "coaching_insights": coaching_insights or [],
        **charts,
    })
    ctx.update(_open_book_ctx(analytics, open_book, mark_delta, period_label))
    ctx.update(_headline_ctx(analytics, open_book, mark_delta,
                             period_label, period_word="שבוע"))
    ctx.update(_comparison_ctx(comparison, period_average,
                               open_book_history, "weekly"))
    # Sprint-20 Step-2 — additive `excl_*` disclosure ctx (disjoint namespace;
    # gated `excluded_count>0`; realized KPIs byte-identical by construction).
    ctx.update(_excluded_ctx(analytics))
    # Sprint-21 WS-B — additive `unlinked_*` disclosure ctx (disjoint
    # namespace; gated `unlinked_count>0`; realized + open-book figures
    # byte-identical by construction — disclosure only, never silent-zero).
    ctx.update(_unlinked_ctx(analytics))

    filename = f"sentinel_weekly_{period_start.strftime('%Y-%m-%d')}.pdf"
    return _render("weekly_report.html.j2", ctx, output_dir, filename)


def render_monthly(
    analytics: dict,
    account_state: dict,
    period_start: datetime,
    period_end: datetime,
    comparison: Optional[dict] = None,
    dev_score_data: Optional[dict] = None,
    system_health: Optional[dict] = None,
    coaching_insights: Optional[list] = None,
    risk_adherence_rate: Optional[float] = None,
    weekly_breakdown: Optional[list] = None,
    open_book: Optional[dict] = None,
    mark_delta: Optional[dict] = None,
    period_average: Optional[dict] = None,
    open_book_history: Optional[dict] = None,
) -> str:
    """
    Render monthly PDF report. Returns path to PDF file.

    Sprint-18: `open_book`/`mark_delta` additive optional (default None ⇒
    byte-identical). Same SEPARATE `open_book_*` ctx-key seam as weekly.

    Sprint-19: `period_average`/`open_book_history` additive optional (default
    None ⇒ byte-identical). Feed §1 headline + §2 vs-average via
    `headline_*`/`cmp_*`/`obcmp_*` keys only; `_base_ctx`/`compute_verdict`
    untouched.
    """
    from analytics_engine import compute_verdict
    verdict, verdict_class = compute_verdict(analytics, period_word="חודש")

    output_dir = os.path.join(_REPORTS_DIR, "monthly")
    wb         = weekly_breakdown or []
    period_label = _period_label(period_start, period_end)
    charts     = _generate_monthly_charts(analytics, wb, period_label, output_dir)

    ctx = _base_ctx(analytics, account_state, period_start, period_end,
                    verdict, verdict_class, dev_score_data, system_health,
                    risk_adherence_rate)
    ctx.update({
        "comparison":        comparison or {},
        "coaching_insights": coaching_insights or [],
        "weekly_breakdown":  wb,
        **charts,
    })
    ctx.update(_open_book_ctx(analytics, open_book, mark_delta, period_label))
    ctx.update(_headline_ctx(analytics, open_book, mark_delta,
                             period_label, period_word="חודש"))
    ctx.update(_comparison_ctx(comparison, period_average,
                               open_book_history, "monthly"))
    # Sprint-20 Step-2 — additive `excl_*` disclosure ctx (disjoint namespace;
    # gated `excluded_count>0`; realized KPIs byte-identical by construction).
    ctx.update(_excluded_ctx(analytics))
    # Sprint-21 WS-B — additive `unlinked_*` disclosure ctx (disjoint
    # namespace; gated `unlinked_count>0`; realized + open-book figures
    # byte-identical by construction — disclosure only, never silent-zero).
    ctx.update(_unlinked_ctx(analytics))

    filename = f"sentinel_monthly_{period_start.strftime('%Y-%m')}.pdf"
    return _render("monthly_report.html.j2", ctx, output_dir, filename)


def build_summary_text(
    analytics: dict,
    period_label: str,
    period_type: str = "weekly",
    risk_rec: Optional[dict] = None,
    open_book: Optional[dict] = None,
    mark_delta: Optional[dict] = None,
    period_average: Optional[dict] = None,
    open_book_history: Optional[dict] = None,
) -> str:
    """
    Build the short Telegram summary message sent before the PDF.

    risk_rec: optional adaptive-risk recommendation dict (from
    adaptive_risk_engine.compute_adaptive_risk). When provided, a heat-score
    thermometer with threshold legend is appended after the KPI block so the
    trader sees the same heat visualization in the scheduled summary as in
    the interactive Telegram drilldowns.

    Sprint-18 (Mark §2 honest empty-state — PRESENTATION switch only, no
    realized-math/`compute_verdict`/920be95-signature change): when
    `analytics.campaigns_closed == 0` the misleading "ללא עסקאות" verdict line
    is REPLACED at the render layer by the honest open-book-aware lines
    (Case A: 0 closed + live book; Case B: truly empty). When campaigns DID
    close, the verdict line is byte-identical and the open-book summary is
    APPENDED after the realized KPI block (never merged into it).
    `open_book`/`mark_delta` default None ⇒ byte-identical for existing callers.
    """
    from analytics_engine import compute_verdict
    verdict, _ = compute_verdict(
        analytics, period_word="חודש" if period_type == "monthly" else "שבוע")
    pf     = analytics.get("profit_factor", 0)
    pf_str = f"{pf:.2f}" if pf < 90 else "∞"
    type_heb = "שבועי" if period_type == "weekly" else "חודשי"

    campaigns_closed = analytics.get("campaigns_closed", 0)
    # Mark §2 presentation switch — applied ONLY when there is no realized
    # data AND a Sprint-18 caller wired an `open_book` (param is not None).
    # `compute_verdict` realized logic, the 920be95 period-aware signature, and
    # `verdict_class` semantics are NOT touched (the switch lives here, not in
    # the verdict). Legacy callers that do NOT pass `open_book` keep the
    # byte-identical pre-Sprint-18 "ללא עסקאות" verdict path (920be95 +
    # Sprint-16 graceful regression intact). Never says "ללא עסקאות" with a
    # live book.
    if campaigns_closed == 0 and open_book is not None:
        import report_open_book as rob
        head = [
            f"🛡️ *Sentinel — דוח {type_heb}*",
            f"📅 תקופה: `{period_label}`",
            f"",
        ]
        head += rob.empty_state_lines(open_book, period_label)
        # Sprint-19 §2 — additive open-book cross-period context (ALGO
        # segregated, baseline-pending honest). Realized vs-average is
        # absent here because campaigns_closed == 0 (no realized to compare).
        ob_cmp = _summary_open_book_cmp_lines(open_book_history)
        if ob_cmp:
            head.append("")
            head.extend(ob_cmp)
        # Sprint-21 WS-B — open-book (BUY-side) NULL-`campaign_id` disclosure
        # in the open-book section (§B2: the line MUST appear in BOTH realized
        # AND open-book whenever in-window N>0). Disclosure only — every
        # open-book figure stays byte-identical (§B3 / guard test).
        ob_unl = _summary_unlinked_open_lines(analytics)
        if ob_unl:
            head.extend(ob_unl)
        # Sprint-20 Step-2 — the founder's exact scenario: campaigns_closed==0
        # because the in-window closes lack a stop (DATA_INCOMPLETE) → they
        # populate excluded_* but were silent. Disclose them honestly here too
        # (realized-but-unverified; NEVER "ללא עסקאות" — Mark §1 hard-rule 3),
        # independent of the open-book lines above.
        excl_lines = _summary_excluded_lines(analytics)
        if excl_lines:
            head.extend(excl_lines)
        # Sprint-21 WS-B — the founder's EXACT scenario: campaigns_closed==0
        # because the in-window SELLs have NULL/blank campaign_id (.dropna()
        # at analytics_engine.py:286 drops them). Disclose them honestly here
        # too (§B2 verbatim; #1 never silent-zero), independent of and
        # additive to the open-book + excluded lines above. The open-book
        # (BUY-side) unlinked line is appended in the open-book section below.
        head.extend(_summary_unlinked_lines(analytics))
        if risk_rec is not None:
            from telegram_formatters import fmt_heat_thermometer
            head.append("")
            head.append(fmt_heat_thermometer(risk_rec, include_legend=True))
        return "\n".join(head)

    lines = [
        f"🛡️ *Sentinel — דוח {type_heb}*",
        f"📅 תקופה: `{period_label}`",
        f"",
        f"{'✅' if analytics.get('total_r_net', 0) > 0 else '🔴'} *{verdict}*",
        f"",
        f"📊 קמפיינים: `{analytics.get('campaigns_closed', 0)}`  |  "
        f"Win%: `{analytics.get('win_rate', 0)*100:.1f}%`",
        f"💰 Realized PnL: `${analytics.get('realized_pnl', 0):+,.0f}`  |  "
        f"Net R: `{analytics.get('total_r_net', 0):+.2f}R`",
        f"🎯 Expectancy: `{analytics.get('expectancy_r', 0):+.2f}R`  |  "
        f"PF: `{pf_str}`",
        f"⚙️ Missing Stop: `{analytics.get('missing_stop_rate', 0)*100:.1f}%`  |  "
        f"Oversized: `{analytics.get('oversized_rate', 0)*100:.1f}%`",
    ]
    # Sprint-19 §2a/§2b: realized vs-previous + vs-average summary line —
    # ADDITIVE, after the realized KPI block, never modifying lines above.
    # Honest baseline-pending until N≥3 (#1 — never a fabricated mean).
    pa = period_average if isinstance(period_average, dict) else {}
    if pa:
        lines.append("")
        if pa.get("available"):
            avg = pa.get("metrics", {})
            unit = "חודשים" if period_type == "monthly" else "שבועות"
            k = pa.get("n_used", pa.get("n_have", 0))
            lines.append(
                f"📊 {_PERIOD_AVG_LABEL.format(k=k, unit=unit)} "
                f"(ממומש בלבד): "
                f"Net R `{avg.get('total_r_net', 0):+.2f}R` · "
                f"Win% `{avg.get('win_rate', 0)*100:.1f}%` · "
                f"Exp `{avg.get('expectancy_r', 0):+.2f}R`")
        else:
            lines.append(f"`{pa.get('baseline_pending_text', '')}`")
    # Sprint-20 Step-2 — CLOSED-but-excluded realized leg, ADDITIVE block
    # appended AFTER the realized KPI + vs-average lines and BEFORE the
    # Sprint-18 open-book append, so realized · excluded · unrealized read in
    # that order. NEVER summed into the realized lines above (Mark §1
    # hard-rule 1); the "לא-מאומת" wording is mandatory (Mark §1 hard-rule 2);
    # ALGO on its OWN observation-only line (Mark §2 / DEC-20260511-001);
    # founder data-completion note mirrors bot_health honest tone (Mark §4).
    lines.extend(_summary_excluded_lines(analytics))
    # Sprint-21 WS-B — NULL-`campaign_id` realized disclosure (§B2 verbatim),
    # ADDITIVE after the excluded block, never summed into the realized lines
    # above (§B3 hard-rule; #1 never silent-zero). [] when count==0 ⇒ existing
    # callers byte-identical.
    lines.extend(_summary_unlinked_lines(analytics))
    # Sprint-18 §1.4: open-book summary APPENDED after the realized KPI block,
    # before the heat thermometer — realized lines above are NOT modified.
    if open_book is not None:
        import report_open_book as rob
        ob_lines = rob.open_book_summary_lines(open_book)
        if ob_lines:
            lines.append("")
            lines.extend(ob_lines)
        if mark_delta is not None and mark_delta.get("text"):
            lines.append(f"`{mark_delta['text']}`")
        # Sprint-19 §2d open-book cross-period context (ALGO segregated).
        ob_cmp = _summary_open_book_cmp_lines(open_book_history)
        if ob_cmp:
            lines.extend(ob_cmp)
        # Sprint-21 WS-B — open-book (BUY-side) NULL-`campaign_id` disclosure
        # in the open-book section (§B2: the line MUST appear in BOTH realized
        # AND open-book whenever in-window N>0; the rows dropped at
        # engine_core.py:479 `.notnull()`). Disclosure only — every open-book
        # figure stays byte-identical (§B3 / guard test).
        ob_unl = _summary_unlinked_open_lines(analytics)
        if ob_unl:
            lines.extend(ob_unl)
    if risk_rec is not None:
        from telegram_formatters import fmt_heat_thermometer
        lines.append("")
        lines.append(fmt_heat_thermometer(risk_rec, include_legend=True))
    return "\n".join(lines)


# ── Chart generation helpers ───────────────────────────────────────────────────

def _generate_weekly_charts(analytics: dict, period_label: str, output_dir: str) -> dict:
    """Generate weekly PNG charts. Returns dict of template context keys → paths (or None)."""
    try:
        import chart_generator as cg
        charts_dir = os.path.join(output_dir, "charts")
        return {
            "chart_campaign_r":    cg.campaign_r_bars(analytics, period_label, charts_dir),
            "chart_setup_perf":    cg.setup_performance_bars(analytics, period_label, charts_dir),
            "chart_equity_curve":  None,
            "chart_win_loss":      None,
        }
    except Exception:
        return _no_charts()


def _generate_monthly_charts(analytics: dict, weekly_breakdown: list,
                              period_label: str, output_dir: str) -> dict:
    """Generate monthly PNG charts."""
    try:
        import chart_generator as cg
        charts_dir = os.path.join(output_dir, "charts")
        return {
            "chart_campaign_r":   None,
            "chart_setup_perf":   cg.setup_performance_bars(analytics, period_label, charts_dir),
            "chart_equity_curve": cg.weekly_equity_curve(weekly_breakdown, period_label, charts_dir),
            "chart_win_loss":     cg.win_loss_donut(analytics, period_label, charts_dir),
        }
    except Exception:
        return _no_charts()


def _no_charts() -> dict:
    return {
        "chart_campaign_r":   None,
        "chart_setup_perf":   None,
        "chart_equity_curve": None,
        "chart_win_loss":     None,
    }


def _summary_open_book_cmp_lines(open_book_history: Optional[dict]) -> list:
    """Sprint-19 §2d — compact open-book cross-period summary lines.

    ADDITIVE; ALWAYS labelled "(לא ממומש)" (via the source strings) so it is
    never read as realized. ALGO on its OWN observation-only line, never
    merged into the disc figure (#8). Returns [] when nothing to show.
    """
    obh = open_book_history if isinstance(open_book_history, dict) else {}
    if not obh:
        return []
    out = []
    if obh.get("available"):
        avg_txt = obh.get("avg_text", "")
        if avg_txt:
            out.append(f"`{avg_txt}`")
        algo_txt = obh.get("avg_algo_text", "")
        if algo_txt:
            out.append(f"`{algo_txt}`")
    else:
        bp = obh.get("baseline_pending_text", "")
        if bp:
            out.append(f"`{bp}`")
    return out


def _summary_excluded_lines(analytics: dict) -> list:
    """Sprint-20 Step-2 — Telegram summary lines for the CLOSED-but-excluded
    realized leg. ADDITIVE; built from `_excluded_ctx` (same disjoint `excl_*`
    namespace; reads ONLY the already-computed `excluded_*` keys). Returns []
    when `excluded_count == 0` ⇒ existing callers byte-identical.

    Renders (Mark §1/§2/§4, all verbatim):
      • manual-incomplete line  — iff `excluded_count_manual > 0`; carries the
        mandatory "לא-מאומת" token + raw realized $ with NO R/WR/PF attached
        + the actionable "השלם entry/stop" hint.
      • ALGO observation-only line — iff `excluded_count_algo > 0`; never
        merged with the manual figure, never an instruction, never in headline
        (DEC-20260511-001 / #8).
      • founder data-completion note — iff `excluded_count_manual > 0`; framed
        as a data task, NOT a system error (bot_health.py:147 honest tone).
    These three are INDEPENDENT (Mark §2.3). NEVER summed into any realized
    KPI line (Mark §1 hard-rule 1) — this is a separate disclosure block.
    """
    ec_ctx = _excluded_ctx(analytics)
    if not ec_ctx.get("excl_present"):
        return []
    out = [""]
    if ec_ctx.get("excl_manual_line"):
        out.append(ec_ctx["excl_manual_line"])
    if ec_ctx.get("excl_algo_line"):
        out.append(ec_ctx["excl_algo_line"])
    if ec_ctx.get("excl_founder_note"):
        out.append(f"`{ec_ctx['excl_founder_note']}`")
    return out


# ── Internals ──────────────────────────────────────────────────────────────────

def _base_ctx(analytics, account_state, period_start, period_end,
              verdict, verdict_class, dev_score_data, system_health,
              risk_adherence_rate) -> dict:
    """Build the common Jinja2 context shared by all report templates."""
    health = system_health or {}
    dev    = dev_score_data or {}
    period_label = _period_label(period_start, period_end)
    return {
        # Period
        "period_label":      period_label,
        "period_start":      period_start.strftime("%Y-%m-%d"),
        "period_end":        period_end.strftime("%Y-%m-%d"),
        "generated_at":      datetime.now().isoformat(),
        # Account
        "nav":               account_state.get("nav", 0),
        "nav_source":        account_state.get("nav_source", "—"),
        "freshness":         account_state.get("freshness", "unknown"),
        "freshness_label":   account_state.get("freshness_label", ""),
        "is_stale":          account_state.get("is_stale", False),
        "nav_freshness_label": account_state.get("freshness_label", "—"),
        # Verdict
        "verdict":           verdict,
        "verdict_class":     verdict_class,
        # KPIs
        "campaigns_closed":  analytics.get("campaigns_closed", 0),
        "win_rate":          analytics.get("win_rate", 0),
        "expectancy_r":      analytics.get("expectancy_r", 0),
        "profit_factor":     analytics.get("profit_factor", 0),
        "avg_win_r":         analytics.get("avg_win_r", 0),
        "avg_loss_r":        analytics.get("avg_loss_r", 0),
        "total_r_net":       analytics.get("total_r_net", 0),
        "realized_pnl":      analytics.get("realized_pnl", 0),
        "best_trade":        analytics.get("best_trade"),
        "worst_trade":       analytics.get("worst_trade"),
        "setup_breakdown":   analytics.get("setup_breakdown", {}),
        "missing_stop_rate": analytics.get("missing_stop_rate", 0),
        "oversized_rate":    analytics.get("oversized_rate", 0),
        "avg_r_per_day":     analytics.get("avg_r_per_day", 0),
        "risk_adherence_rate": risk_adherence_rate,
        # Dev score
        "dev_score":         dev.get("score"),
        "dev_label":         dev.get("label", ""),
        "dev_breakdown":     dev.get("breakdown"),
        # System health
        "sync_status":       health.get("sync_status", "— לא ידוע"),
        "risk_monitor_status": health.get("risk_monitor_status", "— לא ידוע"),
        "report_service_status": health.get("report_service_status", "✅ פעיל"),
        # CSS (inlined for single-file PDF)
        "base_css":          _load_css(),
    }


def _open_book_ctx(analytics: dict, open_book: Optional[dict],
                   mark_delta: Optional[dict], period_label: str) -> dict:
    """Build the SEPARATE `open_book_*` template ctx keys (Sprint-18).

    This is a strictly ADDITIVE seam: it returns ONLY `open_book_*` /
    `ob_*`-namespaced keys plus the §2 empty-state flags. It does NOT read or
    write any realized KPI key produced by `_base_ctx` — the realized ctx is
    byte-identical with vs without this path (proof by construction; guard
    test asserts `_base_ctx` unmutated key-for-key).

    `campaigns_closed == 0` ⇒ presentation-layer empty-state switch (Mark §2):
      • book present ⇒ honest "0 closed + live book" banner (Case A).
      • book absent  ⇒ legacy truly-empty sentence (Case B). The legacy
        920be95 verdict path / `verdict_class` is unchanged; the template
        merely supplements it with the honest banner — it never regresses.
    """
    import report_open_book as rob

    ob = open_book or {}
    present = bool(ob.get("open_book_present"))
    campaigns_closed = analytics.get("campaigns_closed", 0)

    empty_state_lines = []
    show_empty_state = False
    if campaigns_closed == 0 and open_book is not None:
        # Mark §2 — supplement (never replace) the verdict block with the
        # honest banner, ONLY for Sprint-18 callers that wired an open_book.
        # Legacy callers (open_book is None) keep the unchanged 920be95
        # verdict-badge path — no regression. Case A (book) vs Case B (truly
        # empty) both honest; never the word "ללא עסקאות" while a book exists.
        empty_state_lines = rob.empty_state_lines(open_book, period_label)
        show_empty_state = True

    delta = mark_delta or {}
    return {
        "open_book_present":             present,
        "open_book_heading":             rob.OPEN_BOOK_HEADING,
        "open_book_unrealized_label":    rob.OPEN_BOOK_UNREALIZED_LABEL,
        "open_book_disc":                ob.get("open_book_disc", []),
        "open_book_algo":                ob.get("open_book_algo", []),
        "open_book_totals":              ob.get("open_book_totals", {}),
        "open_book_data_source":         ob.get("open_book_data_source", ""),
        "open_book_price_fallback_syms": ob.get("open_book_price_fallback_syms", []),
        "open_book_algo_observation_label": rob.ALGO_OBSERVATION_LABEL,
        "open_book_algo_external_caveat":   rob.ALGO_EXTERNAL_CAVEAT,
        # §2 empty-state (presentation only; verdict/verdict_class untouched)
        "ob_show_empty_state":           show_empty_state,
        "ob_empty_state_lines":          empty_state_lines,
        # §4 mark-to-market delta (baseline-pending honest token by default)
        "open_book_mark_delta_text":     delta.get("text", rob.DELTA_BASELINE_PENDING)
        if (mark_delta is not None or present) else "",
        "open_book_mark_delta_available": bool(delta.get("available")),
    }


def _headline_ctx(analytics: dict, open_book: Optional[dict],
                  mark_delta: Optional[dict], period_label: str,
                  period_word: str = "שבוע") -> dict:
    """Sprint-19 §1 — period-honest headline. STRICTLY ADDITIVE seam.

    Returns ONLY `headline_*`-namespaced keys; never reads or writes a
    `_base_ctx` realized key. `compute_verdict` is still called unchanged in
    `render_*`; its `verdict`/`verdict_class` stay in ctx byte-identical. The
    TEMPLATE merely chooses which to show under the trigger condition (§1a):
    `analytics.campaigns_closed == 0` AND `open_book is not None` AND
    `open_book["open_book_present"] == True` (Sprint-18 wired-caller path;
    legacy `open_book is None` callers keep the byte-identical 920be95 path —
    NO regression). Realized KPI cards stay numerically byte-identical, only
    reframed/demoted (§1c). ALGO is NEVER in the headline badge or the disc
    figures (#8 / DEC-20260511-001) — it is on its OWN segregated line only.
    """
    import report_open_book as rob

    campaigns_closed = analytics.get("campaigns_closed", 0)
    ob = open_book or {}
    present = bool(ob.get("open_book_present"))
    # §1 trigger: 0 closed AND a Sprint-18-wired live book spanned the period.
    mode = (campaigns_closed == 0) and (open_book is not None) and present

    if not mode:
        # Off ⇒ legacy badge path (truly-empty §1d or non-zero campaigns).
        return {
            "headline_open_book_mode": False,
            "headline_badge_text": "",
            "headline_badge_class": "",
            "headline_banner_lines": [],
            "headline_realized_subheading": "",
            "headline_realized_pnl_label": "",
        }

    t = ob.get("open_book_totals", {})
    src = ob.get("open_book_data_source", rob.DATA_SOURCE_LIVE)
    n_disc = int(t.get("n_disc", 0))
    n_algo = int(t.get("n_algo", 0))
    floating_disc = float(t.get("floating_pnl_disc", 0.0) or 0.0)
    floating_algo = float(t.get("floating_pnl_algo", 0.0) or 0.0)
    exposure_disc = float(t.get("exposure_pct_disc", 0.0) or 0.0)
    exposure_algo = float(t.get("exposure_pct_algo", 0.0) or 0.0)
    n_opened_total = int(t.get("n_opened_total", 0))

    # §1b promoted banner — disc only (ALGO NEVER summed into disc figures).
    lines = [
        _HEADLINE_BANNER_L1,
        _HEADLINE_BANNER_L2.format(
            n_disc=n_disc, floating_disc=floating_disc,
            exposure_disc=exposure_disc),
    ]
    if n_opened_total > 0:
        lines.append(_HEADLINE_BANNER_L3_OPENED.format(
            n_opened_total=n_opened_total))
    else:
        lines.append(_HEADLINE_BANNER_L3_HELD)
    lines.append(_HEADLINE_BANNER_L4.format(
        period_label=period_label, source=src))
    # ALGO on its OWN segregated, observation-only line (never in headline #).
    if n_algo > 0:
        lines.append(_HEADLINE_BANNER_ALGO.format(
            n_algo=n_algo, floating_algo=floating_algo,
            exposure_algo=exposure_algo))
    # §2 mark-to-market Δ appended ONLY per the baseline-pending token.
    md = mark_delta or {}
    md_text = md.get("text") if md else None
    if md_text:
        lines.append(md_text)

    return {
        "headline_open_book_mode": True,
        "headline_badge_text": _HEADLINE_BADGE_TEXT.format(
            period_word=period_word),
        "headline_badge_class": _HEADLINE_BADGE_CLASS,
        "headline_banner_lines": lines,
        "headline_realized_subheading": _HEADLINE_REALIZED_SUBHEADING,
        "headline_realized_pnl_label": _HEADLINE_REALIZED_PNL_LABEL,
    }


def _comparison_ctx(comparison: Optional[dict],
                    period_average: Optional[dict],
                    open_book_history: Optional[dict],
                    period_type: str) -> dict:
    """Sprint-19 §2 — period-over-period + vs-average. ADDITIVE seam.

    Emits ONLY `cmp_*` / `obcmp_*` namespaced keys; never mutates `comparison`
    (which stays the unchanged `compute_period_comparison` dict) and never a
    realized KPI key. `period_average` is the `compute_period_average` dict
    (baseline-pending honest until N≥3 — #1). `open_book_history` is the
    `report_open_book.compute_open_book_history` dict (ALGO segregated).
    """
    pa = period_average or {}
    obh = open_book_history or {}
    unit = "חודשים" if period_type == "monthly" else "שבועות"
    avg_metrics = pa.get("metrics", {}) if pa.get("available") else {}
    k_have = pa.get("n_have", 0)
    return {
        # §2a realized vs-previous — label only; the table still consumes the
        # unchanged `comparison` dict. "(ממומש בלבד)" so it is never read as
        # including the open book.
        "cmp_vs_prev_label": _CMP_VS_PREV_LABEL,
        # §2b/§2c realized vs-average.
        "cmp_vs_avg_available": bool(pa.get("available")),
        "cmp_vs_avg_label": _PERIOD_AVG_LABEL.format(
            k=pa.get("n_used", k_have), unit=unit),
        "cmp_vs_avg": avg_metrics,
        "cmp_vs_avg_baseline_pending": pa.get(
            "baseline_pending_text", ""),
        "cmp_avg_n_have": k_have,
        "cmp_avg_n_need": pa.get("n_need", _PERIOD_AVG_MIN_N),
        # §2d open-book period-over-period + vs-average (ALGO segregated).
        "obcmp_available": bool(obh.get("available")),
        "obcmp_prev_delta_text": (obh.get("prev_delta") or {}).get("text", ""),
        "obcmp_avg_text": obh.get("avg_text", ""),
        "obcmp_avg_algo_text": obh.get("avg_algo_text", ""),
        "obcmp_baseline_pending": obh.get("baseline_pending_text", ""),
    }


def _excluded_ctx(analytics: dict) -> dict:
    """Sprint-20 Step-2 — CLOSED-but-excluded realized leg. STRICTLY ADDITIVE
    seam (same disjoint-namespace discipline as `_headline_ctx`/
    `_comparison_ctx`).

    Returns ONLY `excl_*`-namespaced keys; it NEVER reads or writes a
    `_base_ctx` realized KPI key, `_headline_ctx`/`_comparison_ctx`/
    `_open_book_ctx` key, `compute_verdict`, or `analytics`'s number path. It
    merely re-presents the ALREADY-computed `excluded_count`/`excluded_pnl`
    (`analytics_engine.py:57-58,144-145`) plus the additive
    `excluded_*_manual`/`excluded_*_algo` partition — ZERO R/NAV/campaign/
    Expectancy math (proof by construction; guard test asserts `_base_ctx`
    dict identical with vs without this call + key-set disjointness).

    Gate: the whole block is shown **iff** `excluded_count > 0` (Mark §1) —
    exactly the founder scenario (real linked closes with no `initial_stop`).
    `excluded_pnl` is NEVER summed into `realized_pnl`/`total_r_net`/
    `win_rate`/`expectancy_r`/`profit_factor` (Mark §1 hard-rule 1); the
    Sprint-19 "0 בתקופה" framing (countable 0) coexists with no contradiction
    — countable 0 AND excluded N are both true (Mark §1 hard-rule 3).

    The manual line / ALGO line / founder note are INDEPENDENT: manual line +
    founder note shown iff `excluded_count_manual > 0`; ALGO line shown iff
    `excluded_count_algo > 0` (Mark §2.3). ALGO is observation-only — carries
    NO instruction, NEVER in headline/verdict/edge (DEC-20260511-001 / #8).
    """
    import report_open_book as rob

    n          = int(analytics.get("excluded_count", 0) or 0)
    pnl        = float(analytics.get("excluded_pnl", 0.0) or 0.0)
    n_manual   = int(analytics.get("excluded_count_manual", 0) or 0)
    pnl_manual = float(analytics.get("excluded_pnl_manual", 0.0) or 0.0)
    n_algo     = int(analytics.get("excluded_count_algo", 0) or 0)
    pnl_algo   = float(analytics.get("excluded_pnl_algo", 0.0) or 0.0)
    present    = n > 0

    return {
        "excl_present":      present,
        "excl_count":        n,
        "excl_pnl":          pnl,
        "excl_count_manual": n_manual,
        "excl_pnl_manual":   pnl_manual,
        "excl_count_algo":   n_algo,
        "excl_pnl_algo":     pnl_algo,
        "excl_heading":      _EXCL_HEADING,
        "excl_caveat":       _EXCL_CAVEAT,
        "excl_row_manual":   _EXCL_ROW_MANUAL,
        "excl_row_algo":     _EXCL_ROW_ALGO,
        "excl_row_total":    _EXCL_ROW_TOTAL,
        # §1 manual-incomplete line ("לא-מאומת" mandatory; raw $ no R/WR/PF) —
        # only meaningful when n_manual>0 (template/summary gate on it).
        "excl_manual_line":  _EXCL_MANUAL_LINE.format(n=n_manual, x=pnl_manual)
        if n_manual > 0 else "",
        # §2 ALGO observation-only line — only when n_algo>0; no instruction.
        "excl_algo_line":    _EXCL_ALGO_LINE.format(n=n_algo, x=pnl_algo)
        if n_algo > 0 else "",
        # §4 founder data-completion note — only when n_manual>0 (no note for
        # the ALGO subset; DEC-20260511-001).
        "excl_founder_note": _EXCL_FOUNDER_NOTE.format(n=n_manual)
        if n_manual > 0 else "",
        # ALGO observation-only caveat — canonical Sprint-18 constant reused.
        "excl_algo_caveat":  rob.ALGO_EXTERNAL_CAVEAT,
    }


def _unlinked_ctx(analytics: dict) -> dict:
    """Sprint-21 WS-B — NULL-`campaign_id` honest-disclosure seam. STRICTLY
    ADDITIVE, same disjoint-namespace discipline as `_excluded_ctx:750`
    (Sprint-20) / `_headline_ctx`.

    Returns ONLY `unlinked_*`-namespaced keys; it reads ONLY the four additive
    analytics keys `unlinked_count`/`unlinked_pnl`/`unlinked_count_buy`/
    `unlinked_pnl_buy` (analytics_engine §WS-B). It NEVER reads or writes a
    `_base_ctx`/`_headline_ctx`/`_comparison_ctx`/`_open_book_ctx`/`_excluded_
    ctx` key, `compute_verdict`, or any realized/open-book number — ZERO
    R/NAV/campaign/Expectancy math (proof by construction; guard test asserts
    the `_base_ctx`/countable dict is identical with vs without this call and
    that the key-set is disjoint).

    Gate (MARK_SPRINT21_RULINGS.md §B2): the block is shown **iff**
    `unlinked_count > 0` (realized) / `unlinked_count_buy > 0` (open-book) —
    NEVER silent-zero when >0 (#1 / §B3), NEVER a line when 0 (no noise). The
    read flow NEVER auto-mutates Supabase — re-linking is the founder-run
    manual runbook ONLY (§B3/§B4).
    """
    n          = int(analytics.get("unlinked_count", 0) or 0)
    pnl        = float(analytics.get("unlinked_pnl", 0.0) or 0.0)
    n_buy      = int(analytics.get("unlinked_count_buy", 0) or 0)
    pnl_buy    = float(analytics.get("unlinked_pnl_buy", 0.0) or 0.0)

    return {
        "unlinked_present":      n > 0,
        "unlinked_count":        n,
        "unlinked_pnl":          pnl,
        "unlinked_present_buy":  n_buy > 0,
        "unlinked_count_buy":    n_buy,
        "unlinked_pnl_buy":      pnl_buy,
        # Verbatim §B2 realized line — only meaningful when n>0 (template/
        # summary gate on `unlinked_present`).
        "unlinked_line":         _UNLINKED_LINE.format(n=n, x=pnl)
        if n > 0 else "",
        # Verbatim §B2 line for the open-book (BUY-side) — same wording,
        # gated on the BUY-side count so unlinked OPEN trades dropped at
        # engine_core.py:479 are not silently absent either.
        "unlinked_line_buy":     _UNLINKED_LINE.format(n=n_buy, x=pnl_buy)
        if n_buy > 0 else "",
    }


def _summary_unlinked_lines(analytics: dict) -> list:
    """Sprint-21 WS-B — Telegram summary lines for the NULL-`campaign_id`
    silent-drop disclosure (realized leg). ADDITIVE; built from
    `_unlinked_ctx` (same disjoint `unlinked_*` namespace; reads ONLY the four
    additive analytics keys). Returns [] when `unlinked_count == 0` ⇒ existing
    callers byte-identical (§B2 — no line when 0).

    Renders the §B2 verbatim line; NEVER summed into any realized KPI line
    (§B3 hard-rule); never the headline. Open-book BUY-side line is emitted by
    `_summary_unlinked_open_lines` in the open-book section.
    """
    uc = _unlinked_ctx(analytics)
    if not uc.get("unlinked_present"):
        return []
    return ["", uc["unlinked_line"]]


def _summary_unlinked_open_lines(analytics: dict) -> list:
    """Sprint-21 WS-B — open-book (BUY-side) NULL-`campaign_id` disclosure
    line. ADDITIVE; same verbatim §B2 wording, gated on
    `unlinked_count_buy > 0` so unlinked OPEN trades silently dropped at
    `engine_core.py:479` (`.notnull()`) are honestly surfaced too. The
    open-book figures themselves are NEVER altered (disclosure only — §B3;
    `get_open_positions_campaign` and every open-book number byte-identical,
    guard test §B). Returns [] when count == 0."""
    uc = _unlinked_ctx(analytics)
    if not uc.get("unlinked_present_buy"):
        return []
    return [uc["unlinked_line_buy"]]


def _load_weasyprint():
    """
    Lazily import WeasyPrint's HTML class.

    Returns the ``HTML`` class on success, or ``None`` if WeasyPrint cannot be
    loaded for ANY reason. The catch is intentionally a broad ``Exception``
    (NOT just ``ImportError``): the live Sprint-16 incident is
    ``OSError: cannot load library 'libgobject-2.0-0'`` raised at import time
    from ``weasyprint/text/ffi.py``, which is not an ``ImportError``. Catching
    only ``ImportError`` (the old module-top behaviour) let that ``OSError``
    leak and abort the entire weekly/monthly run. No global side effects.
    """
    try:
        from weasyprint import HTML as WeasyHTML
        return WeasyHTML
    except Exception as e:
        _log.warning(
            "WeasyPrint unavailable (%s: %s) — reports will degrade to text/HTML-only",
            type(e).__name__, str(e)[:200],
        )
        return None


def _render(template_name: str, ctx: dict, output_dir: str, filename: str) -> str:
    """Render HTML template → PDF. Returns output path.

    On any PDF failure (WeasyPrint missing / native-lib OSError / render-time
    exception) this falls back to returning the ``.html`` path — the existing
    dev-fallback contract — instead of raising, so the scheduler can still send
    the text summary to the founder.
    """
    if not _JINJA2_OK:
        raise RuntimeError("jinja2 is not installed — cannot render reports")

    env      = Environment(loader=FileSystemLoader(_TEMPLATES_DIR),
                           autoescape=select_autoescape(["html"]))
    template = env.get_template(template_name)
    html_str = template.render(**ctx)

    os.makedirs(output_dir, exist_ok=True)
    html_path = os.path.join(output_dir, filename.replace(".pdf", ".html"))
    pdf_path  = os.path.join(output_dir, filename)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_str)

    WeasyHTML = _load_weasyprint()
    if WeasyHTML is None:
        return html_path
    try:
        WeasyHTML(string=html_str, base_url=_TEMPLATES_DIR).write_pdf(pdf_path)
        return pdf_path
    except Exception as e:
        _log.warning(
            "PDF render failed (%s: %s) — falling back to HTML-only for %s",
            type(e).__name__, str(e)[:200], filename,
        )
        return html_path


def _load_css() -> str:
    try:
        with open(_CSS_PATH, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _period_label(start: datetime, end: datetime) -> str:
    # Sprint-19 §3b (MARK_SPRINT19_RULINGS.md:195-206): `period_end` from
    # _weekly_period (Saturday 23:59:59) AND _monthly_period (last_of_prev =
    # 23:59:59 of the final day) is the INCLUSIVE last instant of the final
    # day — `.day` is ALREADY the correct calendar day. The historic
    # `end.day - 1` assumed an EXCLUSIVE end and under-counted by one in BOTH
    # branches: monthly April rendered "1–29 באפריל" (April has 30 days),
    # weekly under-counted symmetrically (masked, never reported). Ruling:
    # render the inclusive end day itself — no `- 1` in either branch.
    # Arithmetic-only; _weekly_period/_monthly_period definitions unchanged.
    _HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                  "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day} ב{_HE_MONTHS[start.month - 1]} {start.year}"
    return (f"{start.day} ב{_HE_MONTHS[start.month - 1]} – "
            f"{end.day} ב{_HE_MONTHS[end.month - 1]} {end.year}")
