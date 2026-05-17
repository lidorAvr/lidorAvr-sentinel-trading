"""
Sprint-18 Wave-2 — open-marks snapshot (additive / back-compat / baseline-
pending) + renderer wiring + on-demand no-snap_save.

Proves (Mark §4 / §5.9, §5.10, §5.11 + design §3, §1.2, §2):

  • report_snapshot_store.save WITHOUT open_book ⇒ snapshot byte-identical to
    pre-Sprint-18 (no `open_marks` key) — no migration, single-user safe.
  • save WITH a present open_book ⇒ additive `open_marks` (_safe_float-guarded,
    ALGO segregated).
  • An old snapshot (no `open_marks`) ⇒ next-run delta = baseline-pending
    token, never a number.
  • render_weekly/render_monthly default (no open_book) ⇒ realized ctx
    byte-identical; passing open_book adds ONLY open_book_* keys.
  • build_summary_text: 0-closed + book ⇒ honest Case-A, NO "ללא עסקאות";
    0-closed + no book ⇒ Case-B (no legacy regression); >0 closed ⇒ realized
    KPI lines byte-identical + open-book appended after them.
  • report_on_demand.run_on_demand builds + renders an open-book yet NEVER
    calls report_snapshot_store.save (Scope-B invariant).
  • 920be95 period-aware verdict + weekly:116 `{:+,.0f}` + bcf32f5 prev_snap
    (no ["analytics"]) regressions intact.

`python -m pytest -q -p no:cacheprovider`.
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import report_snapshot_store as snap
import report_renderer as rr
import report_open_book as rob


START = datetime(2025, 5, 4)
END = datetime(2025, 5, 10)
_ACCOUNT_STATE = {"nav": 7921.0, "nav_source": "broker",
                  "freshness": "fresh", "risk_pct_input": 0.5}

_ANALYTICS_REALIZED = {
    "ok": True, "campaigns_closed": 5, "win_rate": 0.6,
    "expectancy_r": 0.42, "profit_factor": 2.1, "avg_win_r": 1.5,
    "avg_loss_r": -0.8, "total_r_net": 2.4, "realized_pnl": 480.0,
    "missing_stop_rate": 0.05, "oversized_rate": 0.10,
    "avg_r_per_day": 0.06, "setup_breakdown": {"EP": {"count": 3}},
}

_ANALYTICS_EMPTY = {
    "ok": True, "campaigns_closed": 0, "win_rate": 0,
    "expectancy_r": 0, "profit_factor": 0, "total_r_net": 0,
    "realized_pnl": 0, "missing_stop_rate": 0, "oversized_rate": 0,
}


def _present_open_book():
    return {
        "open_book_present": True,
        "open_book_disc": [
            {"symbol": "MRVL", "entry": 60.0, "current": 65.0, "qty": 30,
             "floating_pnl": 150.0, "realized_pnl": 0.0,
             "structure_r": 0.83, "account_r": 3.79,
             "structure_valid": True, "account_valid": True,
             "exposure_pct": 24.6, "price_is_fallback": False,
             "is_algo": False, "unrealized_label": "לא ממומש"},
        ],
        "open_book_algo": [
            {"symbol": "HOOD", "entry": 20.0, "current": 23.0, "qty": 50,
             "floating_pnl": 150.0, "realized_pnl": 0.0,
             "structure_r": 0.0, "account_r": 3.79,
             "structure_valid": False, "account_valid": True,
             "exposure_pct": 14.5, "price_is_fallback": False,
             "is_algo": True, "unrealized_label": "לא ממומש",
             "observation_label": "פיקוח בלבד · לא הוראה",
             "external_caveat": "מנוהל חיצונית — פיקוח, ללא הוראת Sentinel",
             "structure_r_token": "—"},
        ],
        "open_book_totals": {
            "floating_pnl_disc": 150.0, "floating_pnl_algo": 150.0,
            "exposure_pct_total": 39.1, "exposure_pct_disc": 24.6,
            "exposure_pct_algo": 14.5, "n_disc": 1, "n_algo": 1,
        },
        "open_book_data_source": "Live",
        "open_book_price_fallback_syms": [],
        "open_book_error": None,
    }


# ── Snapshot additive / back-compat ─────────────────────────────────────────

class TestSnapshotAdditive:
    def test_save_without_open_book_is_byte_identical(self, tmp_path):
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", START, END, _ANALYTICS_REALIZED,
                      _ACCOUNT_STATE, "/x.pdf")
            p = tmp_path / "weekly" / "2025-05-04.json"
            data = json.loads(p.read_text(encoding="utf-8"))
        # No open_marks key when open_book not supplied — old readers safe.
        assert "open_marks" not in data
        assert data["campaigns_closed"] == 5
        assert data["realized_pnl"] == 480.0

    def test_save_with_open_book_adds_open_marks(self, tmp_path):
        ob = _present_open_book()
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", START, END, _ANALYTICS_REALIZED,
                      _ACCOUNT_STATE, "/x.pdf", open_book=ob)
            data = json.loads(
                (tmp_path / "weekly" / "2025-05-04.json").read_text("utf-8"))
        assert "open_marks" in data
        om = data["open_marks"]
        assert om["n_disc"] == 1 and om["n_algo"] == 1
        assert om["floating_pnl_disc"] == 150.0
        assert om["floating_pnl_algo"] == 150.0
        assert om["open_total_floating"] == 300.0
        assert om["marks_source"] == "Live"
        # Realized keys untouched (additive only).
        assert data["realized_pnl"] == 480.0
        assert data["win_rate"] == 0.6
        # ALGO segregated in per_symbol via is_algo flag.
        algo = [s for s in om["per_symbol"] if s["is_algo"]]
        disc = [s for s in om["per_symbol"] if not s["is_algo"]]
        assert {s["symbol"] for s in algo} == {"HOOD"}
        assert {s["symbol"] for s in disc} == {"MRVL"}

    def test_save_with_absent_open_book_writes_no_open_marks(self, tmp_path):
        ob = {"open_book_present": False, "open_book_totals": {}}
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", START, END, _ANALYTICS_REALIZED,
                      _ACCOUNT_STATE, "", open_book=ob)
            data = json.loads(
                (tmp_path / "weekly" / "2025-05-04.json").read_text("utf-8"))
        assert "open_marks" not in data

    def test_safe_float_guards_inf_nan(self, tmp_path):
        ob = _present_open_book()
        ob["open_book_totals"]["floating_pnl_disc"] = float("inf")
        ob["open_book_disc"][0]["account_r"] = float("nan")
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", START, END, _ANALYTICS_REALIZED,
                      _ACCOUNT_STATE, "", open_book=ob)
            data = json.loads(
                (tmp_path / "weekly" / "2025-05-04.json").read_text("utf-8"))
        # inf/nan serialized as null (None) — never a non-finite JSON token.
        assert data["open_marks"]["floating_pnl_disc"] is None
        assert data["open_marks"]["per_symbol"][0]["account_r"] is None

    def test_old_snapshot_no_open_marks_yields_baseline_pending(self):
        old = {"period_start": "2025-04-27", "win_rate": 0.5}  # no open_marks
        ob = _present_open_book()
        d = rob.compute_mark_delta(ob, old)
        assert d["available"] is False
        assert d["text"] == \
            "Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם"

    def test_round_trip_prior_marks_pure_subtraction(self, tmp_path):
        ob1 = _present_open_book()
        with patch.object(snap, "_BASE_DIR", str(tmp_path)):
            snap.save("weekly", START, END, _ANALYTICS_REALIZED,
                      _ACCOUNT_STATE, "", open_book=ob1)
            prev = snap.load_previous("weekly", datetime(2025, 5, 20))
        assert prev is not None and "open_marks" in prev
        ob2 = _present_open_book()
        ob2["open_book_totals"]["floating_pnl_disc"] = 200.0
        d = rob.compute_mark_delta(ob2, prev)
        assert d["available"] is True
        assert d["delta_floating_disc"] == pytest.approx(200.0 - 150.0)


# ── Renderer wiring — realized ctx byte-identical ───────────────────────────

class TestRendererWiring:
    def test_open_book_ctx_only_adds_namespaced_keys(self):
        ctx_none = rr._open_book_ctx(_ANALYTICS_REALIZED, None, None, "lbl")
        # No realized KPI key leaks into the open-book ctx block.
        for forbidden in ("win_rate", "expectancy_r", "realized_pnl",
                          "total_r_net", "setup_breakdown", "verdict",
                          "verdict_class"):
            assert forbidden not in ctx_none
        assert ctx_none["open_book_present"] is False

    def test_open_book_ctx_present_exposes_lists(self):
        ob = _present_open_book()
        ctx = rr._open_book_ctx(_ANALYTICS_REALIZED, ob, None, "lbl")
        assert ctx["open_book_present"] is True
        assert len(ctx["open_book_disc"]) == 1
        assert len(ctx["open_book_algo"]) == 1
        assert ctx["open_book_algo_observation_label"] == \
            "פיקוח בלבד · לא הוראה"

    def test_empty_state_switch_only_when_zero_closed(self):
        ob = _present_open_book()
        ctx_closed = rr._open_book_ctx(_ANALYTICS_REALIZED, ob, None, "lbl")
        assert ctx_closed["ob_show_empty_state"] is False
        ctx_empty = rr._open_book_ctx(_ANALYTICS_EMPTY, ob, None, "lbl")
        assert ctx_empty["ob_show_empty_state"] is True
        assert any("0 קמפיינים נסגרו" in ln
                   for ln in ctx_empty["ob_empty_state_lines"])
        assert all("ללא עסקאות" not in ln
                   for ln in ctx_empty["ob_empty_state_lines"])


# ── build_summary_text — Mark §2 honest empty-state (presentation switch) ────

class TestBuildSummaryTextHonest:
    def test_zero_closed_with_book_is_case_a_no_legacy_phrase(self):
        ob = _present_open_book()
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "3–9 במאי 2025",
                                    "weekly", open_book=ob)
        assert "0 קמפיינים נסגרו בתקופה" in txt
        assert "ספר פתוח (לא ממומש)" in txt
        # The misleading legacy verdict phrase is REPLACED, never present.
        assert "שבוע ללא עסקאות" not in txt
        assert "ללא עסקאות" not in txt

    def test_zero_closed_no_book_is_case_b(self):
        # Case B = Sprint-18 path active (open_book passed) but EMPTY book.
        empty_ob = rob.build_open_book(pd.DataFrame(), _ACCOUNT_STATE)
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "3–9 במאי 2025",
                                    "weekly", open_book=empty_ob)
        assert "אין פוזיציות פתוחות" in txt
        assert "שבוע ללא פעילות מסחר" in txt

    def test_zero_closed_legacy_caller_no_open_book_byte_identical(self):
        """Legacy caller (open_book NOT passed) keeps the byte-identical
        pre-Sprint-18 920be95 verdict path — no regression."""
        from analytics_engine import compute_verdict
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly")
        verdict, _ = compute_verdict(_ANALYTICS_EMPTY)  # "שבוע ללא עסקאות"
        assert verdict in txt
        assert "ספר פתוח" not in txt

    def test_positive_closed_realized_lines_byte_identical(self):
        """>0 closed: the realized KPI lines must be byte-identical to the
        pre-Sprint-18 output (open-book absent ⇒ no change at all)."""
        base = rr.build_summary_text(_ANALYTICS_REALIZED, "lbl", "weekly")
        with_ob = rr.build_summary_text(_ANALYTICS_REALIZED, "lbl", "weekly",
                                        open_book=_present_open_book())
        # The realized block (first lines, up to the open-book separator) is
        # a strict prefix of the open-book-augmented text.
        assert with_ob.startswith(base)
        # Open-book appended AFTER the realized block (never merged in).
        assert "ספר פתוח (לא ממומש)" in with_ob
        assert "ספר פתוח (לא ממומש)" not in base

    def test_monthly_period_word_preserved_920be95(self):
        # 920be95 period-aware verdict signature unchanged. Sprint-18 monthly
        # caller (open_book passed, empty) ⇒ honest Case-B; legacy monthly
        # caller (no open_book) ⇒ byte-identical "חודש ללא עסקאות".
        empty_ob = rob.build_open_book(pd.DataFrame(), _ACCOUNT_STATE)
        txt_m = rr.build_summary_text(_ANALYTICS_EMPTY, "מאי 2025",
                                      "monthly", open_book=empty_ob)
        assert "שבוע ללא פעילות מסחר" in txt_m  # Case-B sentence (Mark §2)
        from analytics_engine import compute_verdict
        v, c = compute_verdict(_ANALYTICS_REALIZED, period_word="חודש")
        assert "חודש" in v
        v2, _ = compute_verdict(_ANALYTICS_REALIZED)  # default weekly
        assert "שבוע" in v2
        # Legacy monthly caller (no open_book) — 920be95 path byte-identical.
        txt_legacy = rr.build_summary_text(_ANALYTICS_EMPTY, "מאי 2025",
                                           "monthly")
        assert "חודש ללא עסקאות" in txt_legacy


# ── on-demand: builds + renders open-book yet NEVER snap_save (Scope-B) ──────

class TestOnDemandNoSnapSave:
    def test_run_on_demand_never_calls_snap_save(self):
        import report_on_demand as od

        fake_df = pd.DataFrame([{
            "campaign_id": "c1", "side": "BUY", "trade_date": "2025-04-20",
            "trade_id": "t1", "price": 60.0, "quantity": 30, "pnl_usd": 0,
            "initial_stop": 54.0, "stop_loss": 54.0, "setup_type": "VCP",
            "symbol": "MRVL",
        }])

        with patch("report_snapshot_store.save") as spy_save, \
             patch("account_state.load", return_value=_ACCOUNT_STATE), \
             patch("report_scheduler._fetch_trades_df", return_value=fake_df), \
             patch("report_scheduler._build_system_health", return_value={}), \
             patch("report_scheduler._compute_risk_rec", return_value=None), \
             patch("engine_core.get_live_price", return_value=65.0), \
             patch("report_renderer.render_weekly",
                   return_value="/tmp/x.html") as r_weekly, \
             patch("report_delivery.deliver_report",
                   return_value={"summary_ok": True, "pdf_ok": False}):
            res = od.run_on_demand("weekly", now=datetime(2025, 5, 17),
                                   token="tok", chat_id="123")

        assert res["ok"] is True
        # Scope-B HARD invariant (unchanged by Sprint-19): the snapshot store
        # is NEVER written on-demand.
        spy_save.assert_not_called()
        # Yet the open-book WAS built and passed into the render path.
        _, kwargs = r_weekly.call_args
        assert "open_book" in kwargs
        assert kwargs["open_book"]["open_book_present"] is True
        # Sprint-19 §2f: on-demand now reads existing history READ-ONLY and
        # produces mark_delta/period_average/open_book_history (pure
        # load_previous/load_recent reads — NO snap_save, asserted above). The
        # Sprint-18-era `mark_delta is None` was superseded; the delta is the
        # honest baseline-pending token when no prior open-mark exists.
        assert kwargs["mark_delta"] is not None
        assert kwargs["mark_delta"].get("available") is False
        assert "period_average" in kwargs
        assert "open_book_history" in kwargs


# ── bcf32f5 regression — prev_snap passed directly (no ["analytics"]) ────────

class TestBcf32f5Preserved:
    def test_compute_mark_delta_consumes_flat_prev_snap(self):
        """bcf32f5 made prev_snap a FLAT dict (no nested ["analytics"]).
        compute_mark_delta reads prev_snap["open_marks"] directly — never
        prev_snap["analytics"] — so the flat-dict contract is honored."""
        flat_prev = {
            "period_start": "2025-04-27",
            "win_rate": 0.5,
            "open_marks": {"floating_pnl_disc": 10.0,
                           "floating_pnl_algo": 5.0},
        }
        d = rob.compute_mark_delta(_present_open_book(), flat_prev)
        assert d["available"] is True
        # No KeyError on a flat dict (would raise if it expected ["analytics"]).
        assert d["delta_floating_disc"] == pytest.approx(150.0 - 10.0)
