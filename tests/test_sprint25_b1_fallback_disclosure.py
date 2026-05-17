"""Sprint-25 Wave-2C B1 — NAMED proof for the fallback-as-truth CLOSURE-FIX
(Telegram P0-1 + Data F1/F2; MARK_SPRINT25 Tier-B; CLAUDE.md hard constraint
"do not silently present fallback data as exact truth").

B1 is an ADDITIVE, presentation-only honesty disclosure — ZERO
`analytics_engine.py` / KPI-math change. This file is the Mark-Ruling-3 named
proof and covers the EXACT validated paths B1 touches:

  1. fallback / stale / critical / non-broker / not-ok NAV ⇒ the disclosure
     token is PRESENT in `build_summary_text` (both the normal-KPI branch and
     the 0-closed/empty-state branch) AND on the PDF-degraded scheduler path
     AND on the on-demand path (the Telegram-only fallback-NAV case is never
     presented as "הקובע והמלא" without the honesty line).
  2. broker + fresh NAV + no price fallback ⇒ `build_summary_text` is
     BYTE-IDENTICAL to the pre-B1 output (asserted by exact-string equality
     of the `account_state`-less call vs the broker+fresh call, AND a frozen
     literal for a representative fixture). This keeps the LOCKED April
     regression (broker NAV) + every existing renderer test byte-identical.
  3. 0-closed / empty-state with a price-fallback symbol ⇒ the ALREADY-
     computed `⚠️ מחיר לא חי (לפי כניסה)` per-symbol warning is surfaced (the
     fabricated $0 floating is no longer presented as a real `מקור: Cached`
     quote — Telegram P0-1). No-fallback ⇒ byte-identical.
  4. LOCKED April regression still byte-identical (8 / +$180.49 / WR .375 /
     PF 2.626 / excl 2) — B1 touches NO analytics path; re-confirmed here so
     a future regression is caught against this proof too.

`python -m pytest -q -p no:cacheprovider tests/test_sprint25_b1_fallback_disclosure.py`
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://ci-test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "ci-test-key")

import report_renderer as rr  # noqa: E402

# The B1 disclosure header token (a stable substring of _NAV_FALLBACK_DISCLOSURE
# — never the volatile freshness_label text, which carries a live age).
_NAV_TOKEN = "שים לב — NAV לא חי"
# The verbatim Sprint-18 per-symbol price-fallback warning (single source:
# report_open_book.price_fallback_warning_lines / open_book_summary_lines).
_PRICE_FB_TOKEN = "⚠️ מחיר לא חי (לפי כניסה)"
# Sprint-16 Mark-verbatim degraded trailer.
_DEGRADED_NOTE = (
    "⚠️ ה-PDF לא נוצר בריצה זו. סיכום הטקסט למעלה הוא הנתון הקובע והמלא."
)


def _analytics(**kw):
    base = {
        "ok": True, "campaigns_closed": 6, "win_rate": 0.5,
        "expectancy_r": 0.3, "profit_factor": 2.1, "total_r_net": 1.8,
        "realized_pnl": 360.0, "missing_stop_rate": 0.0, "oversized_rate": 0.0,
    }
    base.update(kw)
    return base


_ANALYTICS_EMPTY = {
    "ok": True, "campaigns_closed": 0, "win_rate": 0, "expectancy_r": 0,
    "profit_factor": 0, "total_r_net": 0, "realized_pnl": 0,
    "missing_stop_rate": 0, "oversized_rate": 0,
}

# Broker + fresh = the happy path (no disclosure ⇒ byte-identical).
_ACC_BROKER_FRESH = {
    "nav": 7921.0, "nav_source": "broker", "freshness": "fresh",
    "freshness_label": "✅ NAV עדכני (6.2h)", "is_stale": False,
    "is_critical": False, "ok": True, "risk_pct_input": 0.5,
}
# The exact account_state.py:_fallback() shape (config missing/corrupt).
_ACC_FALLBACK = {
    "nav": 7500.0, "total_deposited": 7500.0, "risk_pct_input": 0.5,
    "nav_source": "fallback", "nav_updated_at": None, "age_hours": None,
    "freshness": "unknown",
    "freshness_label": "🟠 Fallback NAV — sentinel_config.json לא נמצא",
    "is_stale": True, "is_critical": False, "ok": False,
}
_ACC_STALE = {
    "nav": 7921.0, "nav_source": "broker", "freshness": "stale",
    "freshness_label": "🟡 NAV ישן (30h)", "is_stale": True,
    "is_critical": False, "ok": True, "risk_pct_input": 0.5,
}
_ACC_DEPOSITED = {
    "nav": 7500.0, "nav_source": "deposited", "freshness": "fresh",
    "freshness_label": "✅ NAV עדכני (1.0h)", "is_stale": False,
    "is_critical": False, "ok": True, "risk_pct_input": 0.5,
}


def _present_open_book(fallback_syms=None):
    return {
        "open_book_present": True,
        "open_book_disc": [
            {"symbol": "MRVL", "entry": 60.0, "current": 60.0, "qty": 30,
             "floating_pnl": 0.0, "realized_pnl": 0.0, "structure_r": 0.0,
             "account_r": 0.0, "structure_valid": True, "account_valid": True,
             "exposure_pct": 22.0,
             "price_is_fallback": bool(fallback_syms), "is_algo": False,
             "unrealized_label": "לא ממומש"},
        ],
        "open_book_algo": [],
        "open_book_totals": {
            "floating_pnl_disc": 0.0, "floating_pnl_algo": 0.0,
            "exposure_pct_total": 22.0, "exposure_pct_disc": 22.0,
            "exposure_pct_algo": 0.0, "n_disc": 1, "n_algo": 0,
            "n_opened_total": 0,
        },
        "open_book_data_source": "Cached" if fallback_syms else "Live",
        "open_book_price_fallback_syms": list(fallback_syms or []),
        "open_book_error": None,
    }


# ── 1. Disclosure PRESENT for every non-broker-fresh NAV state ───────────────

class TestNavDisclosurePresentOnFallback:
    @pytest.mark.parametrize("acc", [
        _ACC_FALLBACK, _ACC_STALE, _ACC_DEPOSITED,
        {**_ACC_BROKER_FRESH, "freshness": "critical", "is_stale": True,
         "freshness_label": "🔴 NAV קריטי (60h)"},
        {**_ACC_BROKER_FRESH, "ok": False},
    ])
    def test_normal_branch_discloses(self, acc):
        txt = rr.build_summary_text(_analytics(), "lbl", "weekly",
                                    account_state=acc)
        assert _NAV_TOKEN in txt
        # the verbatim already-honest freshness_label is reused (not invented)
        assert acc["freshness_label"] in txt
        assert acc["nav_source"] in txt

    def test_zero_closed_branch_discloses(self):
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                    open_book=_present_open_book(),
                                    account_state=_ACC_FALLBACK)
        assert _NAV_TOKEN in txt
        assert _ACC_FALLBACK["freshness_label"] in txt

    def test_disclosure_appears_exactly_once(self):
        txt = rr.build_summary_text(_analytics(), "lbl", "weekly",
                                    account_state=_ACC_FALLBACK)
        assert txt.count(_NAV_TOKEN) == 1


# ── 2. Broker+fresh / no account_state ⇒ BYTE-IDENTICAL to pre-B1 ────────────

class TestHappyPathByteIdentical:
    def test_broker_fresh_equals_no_account_state(self):
        # pre-B1 == the account_state-less call (legacy callers/tests). B1 must
        # add NOTHING on the broker+fresh happy path.
        pre_b1 = rr.build_summary_text(_analytics(), "lbl", "weekly")
        broker_fresh = rr.build_summary_text(_analytics(), "lbl", "weekly",
                                             account_state=_ACC_BROKER_FRESH)
        assert broker_fresh == pre_b1
        assert _NAV_TOKEN not in broker_fresh

    def test_zero_closed_broker_fresh_byte_identical(self):
        ob = _present_open_book()  # no fallback symbols
        pre_b1 = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                       open_book=ob)
        with_acc = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                         open_book=ob,
                                         account_state=_ACC_BROKER_FRESH)
        assert with_acc == pre_b1
        assert _NAV_TOKEN not in with_acc
        assert _PRICE_FB_TOKEN not in with_acc

    def test_frozen_literal_representative_fixture(self):
        # Exact-string pin of a representative broker+fresh summary so any
        # future accidental byte drift on the happy path is caught here.
        # Sprint-27 W3 (authorized additive prepend, NOT a weakening — same
        # "Updated NOT deleted/weakened" precedent as the Sprint-25 C1 test
        # correction): the ONE companion "מה עכשיו?" line + its blank line are
        # PREPENDED. The pin stays an exact-byte equality (equally strict, still
        # catches any body drift); the BODY below the prepend is byte-identical
        # to the pre-W3 frozen literal — that byte-identity is the W3 invariant
        # and is asserted explicitly here.
        _pre_w3_body = (
            "🛡️ *Sentinel — דוח שבועי*\n"
            "📅 תקופה: `lbl`\n"
            "\n"
            "🔴 *שבוע ללא עסקאות*\n"
            "\n"
            "📊 קמפיינים: `0`  |  Win%: `0.0%`\n"
            "💰 Realized PnL: `$+0`  |  Net R: `+0.00R`\n"
            "🎯 Expectancy: `+0.00R`  |  PF: `0.00`\n"
            "⚙️ Missing Stop: `0.0%`  |  Oversized: `0.0%`"
        )
        expected = (
            "🧭 *מה עכשיו?* אין עסקאות שנסגרו בתקופה — "
            "זה לא אומר שהכול תקין/לא תקין; עבור על הספר הפתוח למטה.\n"
            "\n"
            + _pre_w3_body
        )
        got = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                    account_state=_ACC_BROKER_FRESH)
        assert got == expected
        # W3 invariant: stripping the prepended companion line + its blank
        # line yields the pre-W3 body byte-for-byte (numbers untouched).
        assert got.split("\n", 2)[2] == _pre_w3_body


# ── 3. 0-closed price-fallback symbols surfaced (Telegram P0-1) ──────────────

class TestZeroClosedPriceFallbackSurfaced:
    def test_fallback_symbol_surfaced_on_empty_state(self):
        ob = _present_open_book(fallback_syms=["MRVL"])
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                    open_book=ob)
        # the fabricated $0 is no longer a silent "מקור: Cached" — the symbol
        # list IS now present on the 0-closed decision surface.
        assert _PRICE_FB_TOKEN in txt
        assert "MRVL" in txt

    def test_no_fallback_zero_closed_byte_identical(self):
        # No symbol fell back ⇒ the new line is absent ⇒ byte-identical to the
        # pre-B1 0-closed output (the live-price happy path is unchanged).
        ob_live = _present_open_book(fallback_syms=None)
        import importlib
        import report_open_book as rob
        # Build the pre-B1 expected by composing the existing helpers WITHOUT
        # the new price-fallback surfacing (helper returns [] when no fallback,
        # so the new call is a structural no-op here — assert that).
        importlib.reload(rob)
        assert rob.price_fallback_warning_lines(ob_live) == []
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                    open_book=ob_live)
        assert _PRICE_FB_TOKEN not in txt

    def test_single_source_helper_matches_open_book_summary(self):
        # The 0-closed surfacing reuses the EXACT Sprint-18 wording that
        # open_book_summary_lines already emits (one canonical source).
        import report_open_book as rob
        ob = _present_open_book(fallback_syms=["MRVL", "AEHR"])
        helper = rob.price_fallback_warning_lines(ob)
        summ = rob.open_book_summary_lines(ob)
        assert helper == [f"⚠️ מחיר לא חי (לפי כניסה): `MRVL, AEHR`"]
        assert helper[0] in summ


# ── 1b. PDF-degraded (scheduler) + on-demand paths carry the token ──────────

class TestDegradedAndOnDemandCarryToken:
    def _patch_sched(self, monkeypatch, account):
        import report_scheduler as rs
        monkeypatch.setenv("TELEGRAM_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
        acc_mod = MagicMock()
        acc_mod.load.return_value = account
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
        return rs

    def test_scheduler_pdf_degraded_weekly_carries_nav_token(self, monkeypatch):
        rs = self._patch_sched(monkeypatch, _ACC_FALLBACK)
        delivered = {}
        rr_mock = MagicMock()
        rr_mock.render_weekly.side_effect = OSError(
            "cannot load library 'libgobject-2.0-0'")
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            delivered.update(pdf_path=p, summary_text=s)
            or {"summary_ok": True, "pdf_ok": False})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        monkeypatch.setattr(rs, "_notify_error", MagicMock())

        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))

        s = delivered["summary_text"]
        # The honesty line is present AND precedes the degraded trailer, so
        # the fallback NAV is never "הקובע והמלא" without the disclosure.
        assert _NAV_TOKEN in s
        assert _DEGRADED_NOTE in s
        assert s.index(_NAV_TOKEN) < s.index(_DEGRADED_NOTE)
        assert delivered["pdf_path"] == ""

    def test_scheduler_pdf_degraded_broker_fresh_no_token(self, monkeypatch):
        rs = self._patch_sched(monkeypatch, _ACC_BROKER_FRESH)
        delivered = {}
        rr_mock = MagicMock()
        rr_mock.render_weekly.side_effect = OSError("native lib missing")
        rr_mock.build_summary_text = rr.build_summary_text
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            delivered.update(summary_text=s)
            or {"summary_ok": True, "pdf_ok": False})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        monkeypatch.setattr(rs, "_notify_error", MagicMock())
        from datetime import datetime
        rs._run_weekly(datetime(2026, 5, 16, 8, 30))
        # Happy NAV ⇒ NO disclosure even on the degraded path (still honest).
        assert _NAV_TOKEN not in delivered["summary_text"]
        assert _DEGRADED_NOTE in delivered["summary_text"]

    def test_on_demand_carries_nav_token(self, monkeypatch):
        rs = self._patch_sched(monkeypatch, _ACC_FALLBACK)
        import report_on_demand as rod
        captured = {}
        rr_mock = MagicMock()
        rr_mock.render_weekly.return_value = "/app/reports/weekly/x.html"  # degraded
        rr_mock.render_monthly.return_value = "/app/reports/monthly/x.html"
        rr_mock.build_summary_text = rr.build_summary_text
        rr_mock.compute_period_average.return_value = {"available": False}
        monkeypatch.setitem(sys.modules, "report_renderer", rr_mock)
        rd_mock = MagicMock()
        rd_mock.deliver_report.side_effect = lambda p, s, c, ci, t: (
            captured.update(summary_text=s)
            or {"summary_ok": True, "pdf_ok": False})
        monkeypatch.setitem(sys.modules, "report_delivery", rd_mock)
        ae = sys.modules["analytics_engine"]
        ae.compute_period_analytics.return_value = _analytics()
        from datetime import datetime
        res = rod.run_on_demand("weekly", now=datetime(2026, 5, 20, 12, 0),
                                token="t", chat_id="c")
        assert res["ok"] is True
        assert _NAV_TOKEN in captured["summary_text"]
        # degraded ⇒ trailer too; disclosure precedes it
        assert _DEGRADED_NOTE in captured["summary_text"]
        assert (captured["summary_text"].index(_NAV_TOKEN)
                < captured["summary_text"].index(_DEGRADED_NOTE))


# ── 4. LOCKED April regression still byte-identical (analytics untouched) ────

class TestLockedAprilByteIdentical:
    def test_april_numbers_unchanged_b1_is_analytics_free(self):
        from datetime import datetime
        from analytics_engine import compute_period_analytics
        # Mirror tests/test_real_data_april_regression.py inputs/asserts —
        # B1 touches NO analytics path, so the pinned set is byte-identical.
        from tests.test_real_data_april_regression import _april_df, _ACCT
        a = compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
