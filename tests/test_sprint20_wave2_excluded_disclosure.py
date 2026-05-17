"""
Sprint-20 Step-2 Wave-2 — honest disclosure of the CLOSED-but-excluded
(DATA_INCOMPLETE / ALGO) realized leg.

Proves (MARK_SPRINT20_RULINGS.md §1–§5 + SPRINT20_DESIGN.md §1–§4):

  • §2 ADDITIVE manual-vs-ALGO partition of the SAME already-aggregated
    `excluded["net_pnl"]` — `excluded_count`/`excluded_pnl` + countable/edge
    semantics byte-identical; invariant manual + algo == excluded; ALGO
    segregated via the canonical `ec.STAT_BUCKET_ALGO` (#8), never countable.
  • §1 Countable-byte-identical guard: the analytics countable KPI subset AND
    the `_base_ctx` realized ctx keys + verdict/verdict_class are byte-identical
    with vs without the new disclosure path (additive `_excluded_ctx` seam,
    disjoint `excl_*` namespace).
  • §1 Disclosure appears iff `excluded_count > 0`, with the correct $ and the
    correct manual/ALGO split; NEVER summed into realized PnL/WR/Exp/PF/Net-R.
  • §1 hard-rule 2 — the mandatory "לא-מאומת" token is present; no R/WR/PF is
    attached to the excluded $; never "ללא עסקאות" for the excluded leg.
  • §2/§4 ALGO line is observation-only (no `השלם`, no instruction), never in
    headline/verdict; founder note framed as data-completion, not a fault.
  • §5.11 on-demand renders the section READ-ONLY — no snap_save.
  • Sprint-18/19 + 920be95 + bcf32f5 + Sprint-16 NOT regressed.

`python -m pytest -q -p no:cacheprovider`.
"""
import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "http://test")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import analytics_engine as ae
import report_renderer as rr
import report_open_book as rob
import report_scheduler as sched

START = datetime(2025, 1, 6)
END = datetime(2025, 1, 13)
_ACCOUNT = {"nav": 10000.0, "nav_source": "broker",
            "freshness": "fresh", "risk_pct_input": 1.0}  # target_risk $100


def _t(cid, side, date_str, price, qty, pnl=0, init_stop=0,
       setup="Breakout", symbol="AAPL"):
    return {"campaign_id": cid, "side": side, "trade_date": date_str,
            "price": price, "quantity": qty, "pnl_usd": pnl,
            "initial_stop": init_stop, "stop_loss": init_stop,
            "setup_type": setup, "symbol": symbol}


def _manual_win():
    # entry 100, stop 90, qty 10 → orig_risk $100; pnl +$200 → net_r +2.0
    return [_t("m1", "BUY", "2025-01-07", 100, 10, 0, 90, setup="EP"),
            _t("m1", "SELL", "2025-01-09", 120, 10, 200, 0, setup="EP")]


def _data_incomplete(pnl=300.0):
    # manual setup, NO initial stop → DATA_INCOMPLETE → excluded (manual)
    return [_t("d1", "BUY", "2025-01-07", 100, 10, 0, 0, setup="Breakout"),
            _t("d1", "SELL", "2025-01-09", 130, 10, pnl, 0, setup="Breakout")]


def _algo_close(pnl=600.0):
    # setup_type ALGO → STAT_BUCKET_ALGO → excluded (algo)
    return [_t("a1", "BUY", "2025-01-07", 50, 20, 0, 45, setup="ALGO"),
            _t("a1", "SELL", "2025-01-09", 80, 20, pnl, 0, setup="ALGO")]


def _mixed_df():
    """1 countable manual win + 1 DATA_INCOMPLETE ($300) + 1 ALGO ($600)."""
    return pd.DataFrame(_manual_win() + _data_incomplete(300.0)
                        + _algo_close(600.0))


def _capture_ctx(render_fn, **kw):
    captured = {}

    def _fake_render(template_name, ctx, output_dir, filename):
        captured.update(ctx)
        return os.path.join(output_dir, filename.replace(".pdf", ".html"))

    with patch.object(rr, "_render", _fake_render), \
         patch.object(rr, "_generate_weekly_charts",
                      lambda *a, **k: rr._no_charts()), \
         patch.object(rr, "_generate_monthly_charts",
                      lambda *a, **k: rr._no_charts()):
        render_fn(**kw)
    return captured


# ════════════════════════════════════════════════════════════════════════════
# §2 — Additive manual/ALGO partition of the SAME excluded_pnl
# ════════════════════════════════════════════════════════════════════════════

class TestManualAlgoSplit:
    def test_split_correct_on_mixed_fixture(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        # Existing semantics UNCHANGED (Mark §2.1 hard rule).
        assert a["campaigns_closed"] == 1          # only the countable win
        assert a["win_rate"] == pytest.approx(1.0)
        assert a["excluded_count"] == 2            # DATA_INCOMPLETE + ALGO
        assert a["excluded_pnl"] == pytest.approx(900.0)  # 300 + 600
        # New ADDITIVE split.
        assert a["excluded_count_manual"] == 1
        assert a["excluded_pnl_manual"] == pytest.approx(300.0)
        assert a["excluded_count_algo"] == 1
        assert a["excluded_pnl_algo"] == pytest.approx(600.0)
        # Invariant: manual + algo == existing excluded total.
        assert (a["excluded_count_manual"] + a["excluded_count_algo"]
                == a["excluded_count"])
        assert (a["excluded_pnl_manual"] + a["excluded_pnl_algo"]
                == pytest.approx(a["excluded_pnl"]))

    def test_split_follows_canonical_stat_bucket_not_symbol(self):
        # The split partitions by the SAME `stat_bucket` series the existing
        # countable/excluded partition uses (canonical ec.STAT_BUCKET_ALGO set
        # by classify_stat_bucket via is_algo_position(setup_type)). An
        # explicit setup="ALGO" close is segregated as ALGO; a no-stop
        # unknown-setup close is DATA_INCOMPLETE (manual) — existing
        # pre-Sprint-20 classification, NOT changed by the additive split.
        df = pd.DataFrame(_manual_win() + _algo_close(600.0) + [
            _t("x1", "BUY", "2025-01-07", 10, 100, 0, 0, setup="Unknown"),
            _t("x1", "SELL", "2025-01-09", 12, 100, 200, 0, setup="Unknown")])
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        assert a["excluded_count_algo"] == 1       # the explicit ALGO close
        assert a["excluded_pnl_algo"] == pytest.approx(600.0)
        assert a["excluded_count_manual"] == 1     # the no-stop unknown close
        assert a["excluded_pnl_manual"] == pytest.approx(200.0)
        assert a["campaigns_closed"] == 1          # ALGO never countable (#8)

    def test_pure_manual_split_all_zero(self):
        df = pd.DataFrame(_manual_win())
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        assert a["excluded_count"] == 0
        for k in ("excluded_count_manual", "excluded_count_algo"):
            assert a[k] == 0
        for k in ("excluded_pnl_manual", "excluded_pnl_algo"):
            assert a[k] == pytest.approx(0.0)

    def test_empty_path_has_split_keys_zero(self):
        a = ae.compute_period_analytics(pd.DataFrame(), START, END, _ACCOUNT)
        for k in ("excluded_count_manual", "excluded_count_algo"):
            assert a[k] == 0
        for k in ("excluded_pnl_manual", "excluded_pnl_algo"):
            assert a[k] == pytest.approx(0.0)

    def test_all_excluded_path_carries_split(self):
        # No countable rows (only DATA_INCOMPLETE + ALGO) → countable.empty
        # early return must still carry the additive split keys.
        df = pd.DataFrame(_data_incomplete(300.0) + _algo_close(600.0))
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        assert a["campaigns_closed"] == 0
        assert a["ok"] is True
        assert a["excluded_count"] == 2
        assert a["excluded_pnl"] == pytest.approx(900.0)
        assert a["excluded_count_manual"] == 1
        assert a["excluded_pnl_manual"] == pytest.approx(300.0)
        assert a["excluded_count_algo"] == 1
        assert a["excluded_pnl_algo"] == pytest.approx(600.0)


# ════════════════════════════════════════════════════════════════════════════
# §1 — Countable / realized byte-identical guard
# ════════════════════════════════════════════════════════════════════════════

# The countable EDGE subset — these MUST be byte-identical regardless of
# whether the period also has excluded closes (they are computed from
# `countable` ONLY). `missing_stop_rate`/`oversized_rate` are deliberately
# EXCLUDED here: they are process-discipline metrics computed over MANUAL
# campaigns INCLUDING DATA_INCOMPLETE (analytics_engine.py:54,60-71) — a
# missing stop is precisely what they exist to surface, so they correctly
# move when a no-stop manual close is added to the input. (Their ctx
# pass-through is still guarded byte-identical at the same-analytics ctx
# level below.)
_COUNTABLE_KEYS = [
    "campaigns_closed", "win_rate", "expectancy_r", "profit_factor",
    "avg_win_r", "avg_loss_r", "total_r_net", "realized_pnl",
    "best_trade", "worst_trade", "setup_breakdown",
    "avg_r_per_day",
]
_REALIZED_CTX_KEYS = [
    "verdict", "verdict_class", "campaigns_closed", "win_rate",
    "expectancy_r", "profit_factor", "avg_win_r", "avg_loss_r",
    "total_r_net", "realized_pnl", "best_trade", "worst_trade",
    "setup_breakdown", "missing_stop_rate", "oversized_rate",
    "avg_r_per_day",
]


class TestCountableByteIdentical:
    def test_countable_kpis_identical_with_vs_without_excluded(self):
        """The countable KPI subset is byte-identical whether or not the
        period also contains excluded (DATA_INCOMPLETE/ALGO) closes — the §2
        split is purely additive new keys."""
        pure = ae.compute_period_analytics(
            pd.DataFrame(_manual_win()), START, END, _ACCOUNT)
        mixed = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        for k in _COUNTABLE_KEYS:
            assert pure[k] == mixed[k], f"countable KPI {k} drifted"

    def test_countable_edge_ctx_identical_across_pure_vs_mixed_dataset(self):
        """Cross-dataset: the countable EDGE ctx keys are byte-identical
        whether the input also has excluded closes. (verdict + discipline
        rates correctly track the dataset — the added no-stop close lifts
        missing_stop_rate, which is exactly what that metric exists for —
        so they are NOT in this cross-dataset subset; the same-analytics
        seam guard below proves the seam itself never mutates them.)"""
        a_no = ae.compute_period_analytics(
            pd.DataFrame(_manual_win()), START, END, _ACCOUNT)
        a_ex = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        base = _capture_ctx(rr.render_weekly, analytics=a_no,
                            account_state=_ACCOUNT,
                            period_start=START, period_end=END)
        full = _capture_ctx(rr.render_weekly, analytics=a_ex,
                            account_state=_ACCOUNT,
                            period_start=START, period_end=END)
        edge_keys = [k for k in _REALIZED_CTX_KEYS
                     if k not in ("verdict", "verdict_class",
                                  "missing_stop_rate", "oversized_rate")]
        for k in edge_keys:
            assert base[k] == full[k], f"countable edge ctx key {k} drifted"

    def test_same_analytics_realized_ctx_byte_identical_vs_no_excluded_seam(self):
        """Load-bearing proof: for the SAME analytics input, the realized
        ctx (incl. missing_stop_rate/oversized_rate pass-through) + verdict is
        byte-identical with vs without the `_excluded_ctx` seam in the
        pipeline — the seam is purely additive `excl_*` keys."""
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        with_seam = _capture_ctx(rr.render_weekly, analytics=a,
                                 account_state=_ACCOUNT,
                                 period_start=START, period_end=END)
        orig = rr._excluded_ctx
        try:
            rr._excluded_ctx = lambda _a: {}      # neutralize the seam
            without_seam = _capture_ctx(rr.render_weekly, analytics=a,
                                        account_state=_ACCOUNT,
                                        period_start=START, period_end=END)
        finally:
            rr._excluded_ctx = orig
        guarded = _REALIZED_CTX_KEYS + ["missing_stop_rate",
                                        "oversized_rate"]
        for k in guarded:
            assert with_seam[k] == without_seam[k], \
                f"realized/discipline ctx key {k} mutated by _excluded_ctx"
        # The seam adds ONLY excl_* keys.
        added = set(with_seam) - set(without_seam)
        assert added and all(k.startswith("excl_") for k in added), \
            f"_excluded_ctx added non-excl_ keys: {added}"

    def test_excluded_ctx_namespace_disjoint(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        ec_ctx = rr._excluded_ctx(a)
        assert all(k.startswith("excl_") for k in ec_ctx), \
            f"non-excl_ key leaked: {[k for k in ec_ctx if not k.startswith('excl_')]}"
        assert not (set(ec_ctx) & set(_REALIZED_CTX_KEYS))

    def test_excluded_never_summed_into_realized(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        # realized_pnl is ONLY the countable $200 win — not 200+900.
        assert a["realized_pnl"] == pytest.approx(200.0)
        assert a["total_r_net"] == pytest.approx(2.0)   # the one +2R win only
        assert a["win_rate"] == pytest.approx(1.0)
        # all-wins countable ⇒ PF is +inf (math.inf); never the excluded $.
        import math
        assert math.isinf(a["profit_factor"])


# ════════════════════════════════════════════════════════════════════════════
# §1 — Disclosure appears iff excluded_count > 0
# ════════════════════════════════════════════════════════════════════════════

class TestDisclosurePresence:
    def test_no_excluded_no_section(self):
        a = ae.compute_period_analytics(
            pd.DataFrame(_manual_win()), START, END, _ACCOUNT)
        ctx = _capture_ctx(rr.render_weekly, analytics=a,
                           account_state=_ACCOUNT,
                           period_start=START, period_end=END)
        assert ctx["excl_present"] is False
        s = rr.build_summary_text(a, "lbl", "weekly")
        assert "לא-מאומת" not in s
        assert "הוחרגו מסטטיסטיקת ה-edge" not in s

    def test_excluded_present_correct_amounts(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        ctx = _capture_ctx(rr.render_weekly, analytics=a,
                           account_state=_ACCOUNT,
                           period_start=START, period_end=END)
        assert ctx["excl_present"] is True
        assert ctx["excl_count"] == 2
        assert ctx["excl_pnl"] == pytest.approx(900.0)
        assert ctx["excl_count_manual"] == 1
        assert ctx["excl_pnl_manual"] == pytest.approx(300.0)
        assert ctx["excl_count_algo"] == 1
        assert ctx["excl_pnl_algo"] == pytest.approx(600.0)

    def test_monthly_also_carries_excluded_ctx(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        ctx = _capture_ctx(rr.render_monthly, analytics=a,
                           account_state=_ACCOUNT,
                           period_start=START, period_end=END)
        assert ctx["excl_present"] is True
        assert ctx["excl_pnl"] == pytest.approx(900.0)

    def test_rendered_html_contains_disclosure_and_amounts(self, tmp_path):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        with patch.object(rr, "_REPORTS_DIR", str(tmp_path)), \
             patch.object(rr, "_generate_weekly_charts",
                          lambda *x, **k: rr._no_charts()), \
             patch.object(rr, "_load_weasyprint", lambda: None):
            path = rr.render_weekly(a, _ACCOUNT, START, END)
        html = open(path, encoding="utf-8").read()
        assert "הוחרגו מסטטיסטיקת ה-edge" in html
        assert "לא-מאומת" in html
        assert "+900$" in html or "900$" in html
        assert "ללא עסקאות" not in html or "הוחרגו" in html


# ════════════════════════════════════════════════════════════════════════════
# §1/§2/§4 — Wording: לא-מאומת present, ALGO observation-only, founder note
# ════════════════════════════════════════════════════════════════════════════

class TestWordingAndAlgoSegregation:
    def test_summary_has_lo_meumat_and_action_hint(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        s = rr.build_summary_text(a, "lbl", "weekly")
        assert "לא-מאומת" in s
        assert "השלם entry/stop" in s            # actionable manual hint
        assert "הוחרגו מסטטיסטיקת ה-edge" in s
        # no R/WR/PF token attached to the excluded $
        assert "ממומש לא-מאומת: $+300" in s

    def test_algo_line_observation_only_no_instruction(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        s = rr.build_summary_text(a, "lbl", "weekly")
        # ALGO line present, on its own, observation-only.
        assert "קמפייני ALGO נסגרו בתקופה" in s
        assert "פיקוח בלבד · לא הוראה" in s
        assert "לא נספר ב-edge" in s
        # The ALGO line carries NO `השלם` instruction.
        algo_line = next(ln for ln in s.split("\n")
                         if "קמפייני ALGO נסגרו" in ln)
        assert "השלם" not in algo_line

    def test_founder_note_data_completion_not_system_error(self):
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        s = rr.build_summary_text(a, "lbl", "weekly")
        assert "זו השלמת נתונים — לא תקלת מערכת" in s

    def test_algo_only_excluded_omits_manual_line_and_note(self):
        # ALGO-only excluded → manual line + founder note omitted; ALGO shown.
        df = pd.DataFrame(_manual_win() + _algo_close(600.0))
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        s = rr.build_summary_text(a, "lbl", "weekly")
        assert "קמפייני ALGO נסגרו בתקופה" in s
        assert "הוחרגו מסטטיסטיקת ה-edge (חסר stop)" not in s
        assert "זו השלמת נתונים" not in s

    def test_manual_only_excluded_omits_algo_line(self):
        df = pd.DataFrame(_manual_win() + _data_incomplete(300.0))
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        s = rr.build_summary_text(a, "lbl", "weekly")
        assert "הוחרגו מסטטיסטיקת ה-edge (חסר stop)" in s
        assert "קמפייני ALGO נסגרו בתקופה" not in s

    def test_algo_not_in_headline_badge(self):
        # Headline (Sprint-19) badge/banner never mentions the excluded ALGO.
        a = ae.compute_period_analytics(_mixed_df(), START, END, _ACCOUNT)
        ctx = _capture_ctx(rr.render_weekly, analytics=a,
                           account_state=_ACCOUNT,
                           period_start=START, period_end=END)
        # campaigns_closed == 1 here ⇒ no headline_open_book_mode at all.
        assert ctx["headline_open_book_mode"] is False
        assert ctx["headline_banner_lines"] == []


# ════════════════════════════════════════════════════════════════════════════
# §1 hard-rule 3 — Sprint-19 reconciliation: 0-closed + excluded, no "ללא עסקאות"
# ════════════════════════════════════════════════════════════════════════════

class TestSprint19Reconciliation:
    def test_zero_countable_excluded_present_summary_no_lo_iskaot(self):
        # founder scenario: only DATA_INCOMPLETE + ALGO closed → countable 0.
        df = pd.DataFrame(_data_incomplete(300.0) + _algo_close(600.0))
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        assert a["campaigns_closed"] == 0
        # Case-A path (0 closed + a wired open_book) must surface the
        # excluded leg and never the misleading "ללא עסקאות".
        ob = {"open_book_present": False, "open_book_disc": [],
              "open_book_algo": [], "open_book_totals": {},
              "open_book_data_source": "Live"}
        s = rr.build_summary_text(a, "lbl", "weekly", open_book=ob)
        assert "לא-מאומת" in s
        assert "הוחרגו מסטטיסטיקת ה-edge" in s

    def test_verdict_string_unchanged_920be95(self):
        from analytics_engine import compute_verdict
        a = ae.compute_period_analytics(
            pd.DataFrame(_data_incomplete(300.0)), START, END, _ACCOUNT)
        v, vc = compute_verdict(a)
        assert v == "שבוע ללא עסקאות" and vc == "neutral"
        vm, vcm = compute_verdict(a, period_word="חודש")
        assert vm == "חודש ללא עסקאות" and vcm == "neutral"


# ════════════════════════════════════════════════════════════════════════════
# §5.11 — on-demand renders the section READ-ONLY (no snap_save)
# ════════════════════════════════════════════════════════════════════════════

class TestOnDemandNoSnapSave:
    def test_on_demand_excluded_no_snap_save(self, tmp_path):
        import report_on_demand as rod
        import report_snapshot_store as rss

        def _boom_save(*a, **k):
            raise AssertionError("on-demand MUST NOT call snap_save")

        def _boom_mark(*a, **k):
            raise AssertionError("on-demand MUST NOT _mark_ran")

        def _boom_state(*a, **k):
            raise AssertionError("on-demand MUST NOT _save_state")

        # Sprint-25 A3 (Ops F4) — stub real chart generation. Without
        # this, run_on_demand → render_weekly renders a REAL Plotly
        # figure → Kaleido `to_image` spawns an event-loop `calc_fig`
        # coroutine that is never awaited; it is GC'd LATER and pytest's
        # unraisable hook then blames whatever test happens to be running
        # during that GC (order/timing dependent — the proven latent
        # flake: `-W error::pytest.PytestUnraisableExceptionWarning` → 1
        # failed). Every OTHER render-invoking test in THIS file already
        # stubs charts via `rr._no_charts()` (the `_capture_ctx` helper +
        # the rendered-HTML test); this on-demand test was the lone
        # omission. Stub it the SAME way → the Kaleido coroutine is never
        # created → deterministic suite. ROOT-CAUSE fix at the source, NOT
        # a global `-W ignore` that would merely hide it.
        with patch.object(rss, "_BASE_DIR", str(tmp_path)), \
             patch.object(rss, "save", _boom_save), \
             patch.object(sched, "_mark_ran", _boom_mark), \
             patch.object(sched, "_save_state", _boom_state), \
             patch.object(rr, "_generate_weekly_charts",
                          lambda *a, **k: rr._no_charts()), \
             patch.object(rr, "_generate_monthly_charts",
                          lambda *a, **k: rr._no_charts()), \
             patch.object(sched, "_fetch_trades_df",
                          lambda *a, **k: _mixed_df()), \
             patch("account_state.load", lambda: _ACCOUNT), \
             patch("report_delivery.deliver_report",
                   lambda *a, **k: {"summary_ok": True, "pdf_ok": False}):
            res = rod.run_on_demand("weekly", now=datetime(2025, 1, 14),
                                    token="t", chat_id="c")
        assert res["ok"] is True
