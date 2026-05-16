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
) -> str:
    """
    Render weekly PDF report. Returns path to PDF file.
    Raises on critical failures (e.g. Jinja2 not installed).
    """
    from analytics_engine import compute_verdict
    verdict, verdict_class = compute_verdict(analytics)

    output_dir = os.path.join(_REPORTS_DIR, "weekly")
    charts     = _generate_weekly_charts(analytics, _period_label(period_start, period_end), output_dir)

    ctx = _base_ctx(analytics, account_state, period_start, period_end,
                    verdict, verdict_class, dev_score_data, system_health,
                    risk_adherence_rate)
    ctx.update({
        "comparison":        comparison or {},
        "coaching_insights": coaching_insights or [],
        **charts,
    })

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
) -> str:
    """
    Render monthly PDF report. Returns path to PDF file.
    """
    from analytics_engine import compute_verdict
    verdict, verdict_class = compute_verdict(analytics)

    output_dir = os.path.join(_REPORTS_DIR, "monthly")
    wb         = weekly_breakdown or []
    charts     = _generate_monthly_charts(analytics, wb, _period_label(period_start, period_end), output_dir)

    ctx = _base_ctx(analytics, account_state, period_start, period_end,
                    verdict, verdict_class, dev_score_data, system_health,
                    risk_adherence_rate)
    ctx.update({
        "comparison":        comparison or {},
        "coaching_insights": coaching_insights or [],
        "weekly_breakdown":  wb,
        **charts,
    })

    filename = f"sentinel_monthly_{period_start.strftime('%Y-%m')}.pdf"
    return _render("monthly_report.html.j2", ctx, output_dir, filename)


def build_summary_text(
    analytics: dict,
    period_label: str,
    period_type: str = "weekly",
    risk_rec: Optional[dict] = None,
) -> str:
    """
    Build the short Telegram summary message sent before the PDF.

    risk_rec: optional adaptive-risk recommendation dict (from
    adaptive_risk_engine.compute_adaptive_risk). When provided, a heat-score
    thermometer with threshold legend is appended after the KPI block so the
    trader sees the same heat visualization in the scheduled summary as in
    the interactive Telegram drilldowns.
    """
    from analytics_engine import compute_verdict
    verdict, _ = compute_verdict(analytics)
    pf     = analytics.get("profit_factor", 0)
    pf_str = f"{pf:.2f}" if pf < 90 else "∞"
    type_heb = "שבועי" if period_type == "weekly" else "חודשי"
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
    _HE_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                  "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.day - 1} ב{_HE_MONTHS[start.month - 1]} {start.year}"
    return (f"{start.day} ב{_HE_MONTHS[start.month - 1]} – "
            f"{end.day - 1} ב{_HE_MONTHS[end.month - 1]} {end.year}")
