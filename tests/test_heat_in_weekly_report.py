"""
Sprint 6 #5 — fmt_heat_thermometer wired into the weekly/monthly report summary.

Covers:
  - fmt_heat_thermometer baseline output (no prior coverage in test suite).
  - include_legend flag adds threshold legend; default keeps the message compact.
  - build_summary_text remains backwards-compatible when risk_rec is omitted.
  - When risk_rec is supplied, the thermometer block is appended after KPIs
    and the threshold legend is included (weekly summary use case).
  - When risk_rec.ok is False, a graceful fallback line appears (no thermometer).
"""
import sys, os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub heavy deps before importing modules that pull telebot/supabase/etc.
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import telegram_formatters as tf
import report_renderer as rr


def _analytics(**kw):
    base = {
        "ok": True, "campaigns_closed": 8, "win_rate": 0.62,
        "total_r_net": 2.4, "realized_pnl": 480.0,
        "expectancy_r": 0.42, "profit_factor": 2.3,
        "missing_stop_rate": 0.0, "oversized_rate": 0.05,
    }
    base.update(kw)
    return base


def _risk_rec_ok(**kw):
    base = {
        "ok": True,
        "heat_score": 72,
        "s9_score": 78,
        "m21_score": 65,
        "l50_score": 60,
        "recent_10_wr": 70,
        "all_50_wr": 58,
        "s9_stats": {"n": 9},
        "l50_stats": {"n": 27},
        "current_risk_pct": 0.6,
        "recommended_risk_pct": 0.85,
        "direction": "up",
    }
    base.update(kw)
    return base


# ── fmt_heat_thermometer — direct ────────────────────────────────────────────

@pytest.mark.unit
class TestFmtHeatThermometer:
    def test_ok_rec_contains_heat_header(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok())
        assert "מד חום מסחר" in out

    def test_ok_rec_renders_score_number(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok(heat_score=83))
        assert "83" in out

    def test_ok_rec_shows_window_breakdown(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok())
        assert "S9" in out and "M21" in out and "L50" in out

    def test_ok_rec_shows_win_rate_with_sample_size(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok())
        assert "Win Rate" in out
        # Sample sizes from s9_stats/l50_stats appear in parentheses
        assert "(9)" in out and "(27)" in out

    def test_not_ok_rec_shows_fallback(self):
        out = tf.fmt_heat_thermometer({"ok": False, "message": "אין מספיק נתונים"})
        assert "מד החום" in out
        assert "אין מספיק נתונים" in out
        assert "מד חום מסחר" not in out  # the full thermometer header is skipped

    def test_legend_excluded_by_default(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok())
        assert "סולם" not in out

    def test_legend_included_when_flag_set(self):
        out = tf.fmt_heat_thermometer(_risk_rec_ok(), include_legend=True)
        assert "סולם" in out
        # All five label tiers should appear in the legend
        for emoji in ("🔥", "🟠", "🟡", "🔵", "❄️"):
            assert emoji in out

    def test_legend_not_added_to_fallback(self):
        out = tf.fmt_heat_thermometer({"ok": False}, include_legend=True)
        assert "סולם" not in out  # fallback short-circuits before legend logic


# ── build_summary_text — backwards compatibility + new path ──────────────────

@pytest.mark.unit
class TestBuildSummaryWithHeat:

    def test_backwards_compatible_no_risk_rec(self):
        """Existing callers that omit risk_rec must keep working unchanged."""
        text = rr.build_summary_text(_analytics(), "05/01–11/01", "weekly")
        assert "Sentinel" in text
        assert "מד חום" not in text  # no thermometer when risk_rec omitted

    def test_risk_rec_none_explicit(self):
        text = rr.build_summary_text(_analytics(), "05/01–11/01", "weekly", risk_rec=None)
        assert "מד חום" not in text

    def test_risk_rec_ok_appends_thermometer(self):
        text = rr.build_summary_text(
            _analytics(), "05/01–11/01", "weekly", risk_rec=_risk_rec_ok()
        )
        assert "מד חום מסחר" in text
        # Heat score and one of the window labels must appear
        assert "72" in text
        assert "S9" in text

    def test_weekly_summary_includes_legend(self):
        text = rr.build_summary_text(
            _analytics(), "05/01–11/01", "weekly", risk_rec=_risk_rec_ok()
        )
        assert "סולם" in text

    def test_monthly_summary_also_includes_thermometer(self):
        text = rr.build_summary_text(
            _analytics(), "ינואר 2026", "monthly", risk_rec=_risk_rec_ok()
        )
        assert "חודשי" in text
        assert "מד חום" in text

    def test_risk_rec_not_ok_shows_fallback(self):
        text = rr.build_summary_text(
            _analytics(), "05/01–11/01", "weekly",
            risk_rec={"ok": False, "message": "פחות מ-3 קמפיינים סגורים"}
        )
        assert "מד החום" in text
        assert "פחות מ-3 קמפיינים" in text
        assert "מד חום מסחר" not in text  # no full thermometer block

    def test_thermometer_placed_after_kpis(self):
        """KPIs (Win%, Expectancy) must precede the heat section."""
        text = rr.build_summary_text(
            _analytics(), "05/01–11/01", "weekly", risk_rec=_risk_rec_ok()
        )
        win_pos  = text.find("Win")
        heat_pos = text.find("מד חום מסחר")
        assert 0 < win_pos < heat_pos
