"""
Sprint 16 Wave-2 — weekly/monthly report resilience when WeasyPrint is dead.

HIGH incident: report_renderer.py had a module-top `from weasyprint import HTML`
guarded only by `except ImportError`. The live failure is an `OSError`
("cannot load library 'libgobject-2.0-0'") raised at import time — NOT an
ImportError — so it leaked and aborted the entire weekly/monthly run before
`build_summary_text` / `deliver_report`, dropping the founder's text summary
(AGENTS.md invariant #1 violation).

These tests prove:
  1. Renderer import guard: forced `from weasyprint import HTML` raising OSError
     (and ImportError) — `import report_renderer` still succeeds and
     `_load_weasyprint()` returns None without raising.
  2. `_render` degrades to the .html path when WeasyPrint is unavailable.
  3. `_render` degrades to .html when `.write_pdf` raises at render time.
  4. `build_summary_text` is byte-identical with/without WeasyPrint present
     (no content/number change).
  5. `_run_weekly`: render forced to raise → text summary STILL built and
     `deliver_report` called with a SAFE falsy pdf_path; degraded honest
     trailer appended; NO `_notify_error` (degraded == SUCCESS, Mark §1).
  6. Degraded summary contains Mark's EXACT Hebrew note (no optimistic wording).
  7. `_run_monthly`: same degraded-success contract as weekly.
  8. Non-degraded regression: WeasyPrint working → .pdf path, no trailer,
     no behaviour change on the happy path.
Plus: os.path.exists(None/"") safety in report_delivery.send_pdf;
      true-failure (creds missing / summary unbuildable) still routes to error.
"""
import builtins
import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub heavy deps before importing modules that pull telebot/supabase/etc.
for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import report_renderer as rr
import report_scheduler as rs
import report_delivery as rd

# Mark's exact binding Hebrew trailer (MARK_SPRINT16_RULINGS.md §1).
EXACT_NOTE = "⚠️ ה-PDF לא נוצר בריצה זו. סיכום הטקסט למעלה הוא הנתון הקובע והמלא."


def _analytics(**kw):
    base = {
        "ok": True, "campaigns_closed": 8, "win_rate": 0.62,
        "total_r_net": 2.4, "realized_pnl": 480.0,
        "expectancy_r": 0.42, "profit_factor": 2.3,
        "missing_stop_rate": 0.0, "oversized_rate": 0.05,
    }
    base.update(kw)
    return base


def _force_weasyprint_import_error(exc):
    """Return an import hook that makes `from weasyprint import ...` raise `exc`."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "weasyprint" or name.startswith("weasyprint."):
            raise exc
        return real_import(name, *args, **kwargs)

    return fake_import


# ── 1. Renderer import guard (OSError AND ImportError) ───────────────────────

@pytest.mark.unit
class TestLoadWeasyprintGuard:
    def test_oserror_at_import_returns_none_no_raise(self):
        exc = OSError("cannot load library 'libgobject-2.0-0'")
        with patch("builtins.__import__", _force_weasyprint_import_error(exc)):
            assert rr._load_weasyprint() is None  # broad catch — does NOT raise

    def test_importerror_at_import_returns_none_no_raise(self):
        with patch("builtins.__import__",
                   _force_weasyprint_import_error(ImportError("no module"))):
            assert rr._load_weasyprint() is None

    def test_import_report_renderer_survives_oserror(self):
        """Re-importing report_renderer with weasyprint raising OSError at
        import time must NOT abort — the import is lazy now, not module-top."""
        exc = OSError("cannot load library 'libgobject-2.0-0'")
        with patch("builtins.__import__", _force_weasyprint_import_error(exc)):
            mod = importlib.reload(rr)
            assert mod is not None
            assert mod._load_weasyprint() is None
        importlib.reload(rr)  # restore clean module for other tests


# ── 2 & 3. _render degrades to HTML ──────────────────────────────────────────

@pytest.fixture
def trivial_template(monkeypatch, tmp_path):
    """Point _render at a trivial template dir so we exercise the
    PDF-degradation branch of _render without depending on the heavy
    production Jinja templates (their filters need full analytics context;
    irrelevant to the WeasyPrint fallback logic under test here)."""
    tdir = tmp_path / "tmpl"
    tdir.mkdir()
    (tdir / "t.html.j2").write_text("<h1>{{ title }}</h1>", encoding="utf-8")
    monkeypatch.setattr(rr, "_TEMPLATES_DIR", str(tdir))
    return str(tmp_path)


@pytest.mark.unit
class TestRenderDegrades:
    def test_render_returns_html_when_weasyprint_unavailable(
            self, trivial_template):
        with patch.object(rr, "_load_weasyprint", return_value=None):
            out = rr._render("t.html.j2", {"title": "x"},
                             trivial_template, "x.pdf")
        assert out.endswith(".html")
        assert os.path.exists(out)

    def test_render_returns_html_when_write_pdf_raises(self, trivial_template):
        class BoomHTML:
            def __init__(self, *a, **k):
                pass

            def write_pdf(self, *a, **k):
                raise OSError("cannot load library 'libgobject-2.0-0'")

        with patch.object(rr, "_load_weasyprint", return_value=BoomHTML):
            out = rr._render("t.html.j2", {"title": "x"},
                             trivial_template, "x.pdf")
        assert out.endswith(".html")  # degraded, did NOT raise

    def test_render_returns_pdf_on_happy_path(self, trivial_template):
        class OkHTML:
            def __init__(self, *a, **k):
                pass

            def write_pdf(self, path):
                with open(path, "wb") as f:
                    f.write(b"%PDF-1.4 fake")

        with patch.object(rr, "_load_weasyprint", return_value=OkHTML):
            out = rr._render("t.html.j2", {"title": "x"},
                             trivial_template, "x.pdf")
        assert out.endswith(".pdf")
        assert os.path.exists(out)


# ── 4. build_summary_text unaffected (no content/number change) ──────────────

@pytest.mark.unit
class TestSummaryTextByteIdentical:
    def test_summary_identical_with_and_without_weasyprint(self):
        a = _analytics()
        with patch.object(rr, "_load_weasyprint", return_value=None):
            txt_no_wp = rr.build_summary_text(a, "10/05–16/05/2026", "weekly")
        with patch.object(rr, "_load_weasyprint", return_value=object):
            txt_wp = rr.build_summary_text(a, "10/05–16/05/2026", "weekly")
        assert txt_no_wp == txt_wp
        assert EXACT_NOTE not in txt_no_wp  # build_summary_text never appends it


# ── 5–8. Scheduler degraded-success contract ─────────────────────────────────

def _patch_scheduler_deps(monkeypatch):
    """Stub the data/analytics layer so we can drive _run_weekly/_run_monthly
    deterministically and observe delivery + notify behaviour."""
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    acc_mod = MagicMock()
    acc_mod.load.return_value = {"nav": 100000, "risk_pct_input": 0.5}
    monkeypatch.setitem(sys.modules, "account_state", acc_mod)

    ae = MagicMock()
    ae.compute_period_analytics.return_value = _analytics()
    ae.compute_trader_development_score.return_value = {"score": 70}
    ae.compute_period_comparison.return_value = None
    ae.compute_verdict.return_value = ("ניטרלי", "neutral")
    monkeypatch.setitem(sys.modules, "analytics_engine", ae)

    snap = MagicMock()
    snap.load_previous.return_value = None
    snap.load_recent.return_value = []
    snap.save.return_value = None
    monkeypatch.setitem(sys.modules, "report_snapshot_store", snap)

    monkeypatch.setattr(rs, "_fetch_trades_df", lambda *a, **k: None)
    monkeypatch.setattr(rs, "_compute_risk_rec", lambda *a, **k: {"ok": False})


@pytest.mark.unit
class TestSchedulerDegradedSuccess:
    def test_weekly_render_raises_text_still_sent_no_notify(self, monkeypatch):
        _patch_scheduler_deps(monkeypatch)
        delivered = {}

        def spy_deliver(pdf_path, summary_text, caption, chat_id, token):
            delivered["pdf_path"] = pdf_path
            delivered["summary_text"] = summary_text
            return {"summary_ok": True, "pdf_ok": False}

        notify = MagicMock()
        rr_mock = MagicMock()
        rr_mock.render_weekly.side_effect = OSError(
            "cannot load library 'libgobject-2.0-0'")
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = spy_deliver
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        monkeypatch.setattr(rs, "_notify_error", notify)

        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))

        assert "summary_text" in delivered, "deliver_report must still be called"
        # safe falsy path — never None (os.path.exists(None) would TypeError)
        assert delivered["pdf_path"] == "" and delivered["pdf_path"] is not None
        assert EXACT_NOTE in delivered["summary_text"]
        notify.assert_not_called()  # degraded == SUCCESS, not _notify_error

    def test_weekly_render_returns_html_path_degrades(self, monkeypatch):
        _patch_scheduler_deps(monkeypatch)
        delivered = {}
        rr_mock = MagicMock()
        rr_mock.render_weekly.return_value = "/app/reports/weekly/x.html"
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            delivered.update(pdf_path=p, summary_text=s)
            or {"summary_ok": True, "pdf_ok": False})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        notify = MagicMock()
        monkeypatch.setattr(rs, "_notify_error", notify)

        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))

        assert delivered["pdf_path"] == ""        # non-.pdf → degraded
        assert EXACT_NOTE in delivered["summary_text"]
        notify.assert_not_called()

    def test_monthly_render_raises_text_still_sent_no_notify(self, monkeypatch):
        _patch_scheduler_deps(monkeypatch)
        delivered = {}
        rr_mock = MagicMock()
        rr_mock.render_monthly.side_effect = OSError("native lib missing")
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            delivered.update(pdf_path=p, summary_text=s)
            or {"summary_ok": True, "pdf_ok": False})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        notify = MagicMock()
        monkeypatch.setattr(rs, "_notify_error", notify)

        from datetime import datetime
        rs._run_monthly(datetime(2026, 6, 1, 8, 40))

        assert "summary_text" in delivered
        assert delivered["pdf_path"] == ""
        assert EXACT_NOTE in delivered["summary_text"]
        notify.assert_not_called()

    def test_weekly_happy_path_no_trailer_pdf_sent(self, monkeypatch):
        _patch_scheduler_deps(monkeypatch)
        delivered = {}
        rr_mock = MagicMock()
        rr_mock.render_weekly.return_value = "/app/reports/weekly/x.pdf"
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            delivered.update(pdf_path=p, summary_text=s)
            or {"summary_ok": True, "pdf_ok": True})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        notify = MagicMock()
        monkeypatch.setattr(rs, "_notify_error", notify)

        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))

        assert delivered["pdf_path"].endswith(".pdf")  # PDF preserved
        assert EXACT_NOTE not in delivered["summary_text"]  # no trailer
        notify.assert_not_called()

    def test_weekly_missing_creds_still_real_failure_path(self, monkeypatch):
        """True-failure boundary preserved: creds missing → early return,
        no delivery (NOT a degraded-success silently swallowing the report)."""
        _patch_scheduler_deps(monkeypatch)
        monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        rr_mock = MagicMock()
        rr_mock.render_weekly.return_value = "/app/reports/weekly/x.pdf"
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)

        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))
        rd_mock.deliver_report.assert_not_called()  # creds gate → no delivery


# ── send_pdf falsy/None safety (os.path.exists(None) TypeError guard) ────────

@pytest.mark.unit
class TestSendPdfFalsySafety:
    def test_send_pdf_empty_string_returns_false_no_raise(self):
        assert rd.send_pdf("", "cap", "chat", "tok") is False

    def test_send_pdf_none_returns_false_no_raise(self):
        # Without the guard this is os.path.exists(None) → TypeError.
        assert rd.send_pdf(None, "cap", "chat", "tok") is False

    def test_deliver_report_text_only_no_pdf_crash(self):
        with patch.object(rd, "send_summary", return_value=True):
            res = rd.deliver_report("", "summary", "cap", "chat", "tok")
        assert res == {"summary_ok": True, "pdf_ok": False}


# ── Weekly template real-Jinja regression (on-demand smoke-test catch) ───────
#
# templates/weekly_report.html.j2:116 used the %-style filter with a ','
# thousands separator: {{ "%+,.0f"|format(realized_pnl) }}. '%,' is INVALID
# in %-formatting (str % args) → ValueError("unsupported format character
# ','") raised at template.render(), BEFORE WeasyPrint — so EVERY weekly PDF
# failed (the scheduled Saturday report was PDF-less for weeks); monthly was
# fine ("{:,.0f}".format()). Sprint-16 graceful path masked it (text-only);
# the Sprint-17 on-demand button exposed it (weekly pdf=False vs monthly
# pdf=True side by side). These render the REAL Jinja template (charts
# stubbed, output → tmp) so the regression is caught without WeasyPrint.

@pytest.mark.unit
class TestWeeklyTemplateRealJinjaRegression:
    def _acct(self):
        return {"nav": 7921.0, "risk_pct_input": 0.6,
                "nav_source": "broker", "freshness": "6.2h"}

    def _setup(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rr, "_REPORTS_DIR", str(tmp_path))
        monkeypatch.setattr(rr, "_generate_weekly_charts",
                            lambda *a, **k: {})
        monkeypatch.setattr(rr, "_generate_monthly_charts",
                            lambda *a, **k: {})

    def test_render_weekly_zero_trades_smoke_case_does_not_raise(
            self, monkeypatch, tmp_path):
        # EXACT founder smoke-test scenario: 0 campaigns, on-demand weekly.
        import pandas as pd
        from datetime import datetime
        from analytics_engine import compute_period_analytics
        self._setup(monkeypatch, tmp_path)
        ps, pe = datetime(2026, 5, 3), datetime(2026, 5, 9, 23, 59, 59)
        a = compute_period_analytics(pd.DataFrame(), ps, pe, self._acct())
        # Pre-fix: ValueError at template.render(); post-fix: returns a path.
        path = rr.render_weekly(analytics=a, account_state=self._acct(),
                                period_start=ps, period_end=pe)
        assert isinstance(path, str) and path

    def test_render_weekly_formats_pnl_with_sign_and_thousands(
            self, monkeypatch, tmp_path):
        import pandas as pd
        from datetime import datetime
        from analytics_engine import compute_period_analytics
        self._setup(monkeypatch, tmp_path)
        ps, pe = datetime(2026, 5, 3), datetime(2026, 5, 9, 23, 59, 59)
        a = compute_period_analytics(pd.DataFrame(), ps, pe, self._acct())
        a["realized_pnl"] = 12345.0
        path = rr.render_weekly(analytics=a, account_state=self._acct(),
                                period_start=ps, period_end=pe)
        html = open(path.replace(".pdf", ".html"), encoding="utf-8").read()
        assert "+12,345$" in html        # sign + thousands separator intact


# ── Period-aware verdict (monthly wrongly showed "שבוע ללא עסקאות") ──────────

@pytest.mark.unit
class TestPeriodAwareVerdict:
    def test_default_keeps_weekly_word_byte_identical(self):
        import analytics_engine as ae
        assert ae.compute_verdict(_analytics())[0].startswith("שבוע")
        assert ae.compute_verdict(
            {"ok": True, "campaigns_closed": 0})[0] == "שבוע ללא עסקאות"

    def test_monthly_word_when_requested(self):
        import analytics_engine as ae
        assert ae.compute_verdict(
            _analytics(), period_word="חודש")[0].startswith("חודש")
        assert ae.compute_verdict(
            {"ok": True, "campaigns_closed": 0},
            period_word="חודש")[0] == "חודש ללא עסקאות"

    def test_build_summary_text_period_aware(self):
        txt_m = rr.build_summary_text(
            {"ok": True, "campaigns_closed": 0}, "אפריל 2026", "monthly")
        txt_w = rr.build_summary_text(
            {"ok": True, "campaigns_closed": 0}, "03/05–09/05", "weekly")
        assert "חודש ללא עסקאות" in txt_m
        assert "שבוע ללא עסקאות" in txt_w
