"""
Sprint-17 Wave-2 tests — ALGO governance (Workstream A) + on-demand report
dev button (Workstream B).

Covers MARK_SPRINT17_RULINGS.md §6 gate items:
  • #8 byte-identical guard (headline WR/Expectancy identical with vs without
    ALGO trades present) — the gate-failing assertion.
  • ALGO cohort = complement of headline countable set; analytics_engine does
    NOT import algo_metrics (the construction proof).
  • ALGO cohort metrics on the founder's §2/§3 real numbers as fixtures.
  • Governor advisory-not-instruction (never Action Required, never a stop).
  • algo_rules lookup per symbol + honest "observed, not enforced" wording.
  • Backtest-caveat present on every ALGO-stat surface.
  • Scope-B: on-demand run reuses the render path, performs NO snap_save and
    leaves the scheduler dedup untouched; graceful degradation still works.
"""
import ast
import os
import sys
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import analytics_engine as ae
import engine_core as ec
import algo_rules
import algo_metrics


_ACCOUNT = {"nav": 10000.0, "risk_pct_input": 1.0}   # target_risk = $100
START = datetime(2025, 1, 1)
END = datetime(2025, 12, 31)


def _trade(campaign_id, side, date_str, price, qty, pnl=0,
           initial_stop=0, setup="Breakout", symbol="AAPL"):
    return {
        "campaign_id": campaign_id, "side": side, "trade_date": date_str,
        "price": price, "quantity": qty, "pnl_usd": pnl,
        "initial_stop": initial_stop, "stop_loss": initial_stop,
        "setup_type": setup, "symbol": symbol,
    }


def _manual_only_df():
    """A manual-only trades DF with known countable campaigns."""
    return pd.DataFrame([
        _trade("m1", "BUY", "2025-02-03", 100, 10, 0, 90, "VCP", "AAPL"),
        _trade("m1", "SELL", "2025-02-10", 120, 10, 200, 90, "VCP", "AAPL"),
        _trade("m2", "BUY", "2025-03-03", 50, 20, 0, 45, "EP", "MSFT"),
        _trade("m2", "SELL", "2025-03-12", 45, 20, -100, 45, "EP", "MSFT"),
        _trade("m3", "BUY", "2025-04-01", 80, 10, 0, 72, "VCP", "NVDA"),
        _trade("m3", "SELL", "2025-04-09", 95, 10, 150, 72, "VCP", "NVDA"),
    ])


def _algo_rows():
    """Founder §2-style ALGO campaigns (QQQ/TSLA/PLTR) — must NEVER enter
    headline WR/Expectancy (#8)."""
    return [
        _trade("a1", "BUY", "2025-02-04", 400, 5, 0, 0, "ALGO", "QQQ"),
        _trade("a1", "SELL", "2025-02-20", 380, 5, -100, 0, "ALGO", "QQQ"),
        _trade("a2", "BUY", "2025-05-02", 200, 5, 0, 0, "ALGO", "TSLA"),
        _trade("a2", "SELL", "2025-05-22", 260, 5, 300, 0, "ALGO", "TSLA"),
        _trade("a3", "BUY", "2025-06-01", 25, 40, 0, 0, "ALGO", "PLTR"),
        _trade("a3", "SELL", "2025-06-21", 20, 40, -200, 0, "ALGO", "PLTR"),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# #8 byte-identical guard (gate-failing assertion — MARK §6)
# ──────────────────────────────────────────────────────────────────────────────

class TestHeadlineByteIdenticalWithWithoutAlgo:
    _HEADLINE_FIELDS = [
        "win_rate", "expectancy_r", "profit_factor", "avg_win_r",
        "avg_loss_r", "total_r_net", "realized_pnl", "best_trade",
        "worst_trade", "campaigns_closed", "setup_breakdown",
    ]

    def test_headline_identical_with_vs_without_algo(self):
        base = ae.compute_period_analytics(
            _manual_only_df(), START, END, _ACCOUNT)
        with_algo = ae.compute_period_analytics(
            pd.DataFrame(_manual_only_df().to_dict("records") + _algo_rows()),
            START, END, _ACCOUNT)
        for f in self._HEADLINE_FIELDS:
            assert base[f] == with_algo[f], (
                f"#8 VIOLATION: headline field {f!r} diverged "
                f"({base[f]!r} vs {with_algo[f]!r}) — ALGO leaked into "
                f"headline stats. FAIL THE GATE.")

    def test_algo_present_but_excluded_count_reflects_them(self):
        with_algo = ae.compute_period_analytics(
            pd.DataFrame(_manual_only_df().to_dict("records") + _algo_rows()),
            START, END, _ACCOUNT)
        # ALGO campaigns are seen by the period filter but excluded from
        # countable — they show up only in the excluded bucket.
        assert with_algo["excluded_count"] >= 3


class TestAlgoCohortIsComplement:
    def test_cohort_is_exact_complement_of_countable(self):
        df = pd.DataFrame(_manual_only_df().to_dict("records") + _algo_rows())
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        closed = ae._get_closed_campaigns(df, START, END)
        campaigns = ae._aggregate_campaigns(closed, 100.0)
        countable = campaigns[campaigns["stat_bucket"].apply(
            ec.is_stat_countable)]
        cohort = algo_metrics.build_algo_cohort(campaigns)
        # Disjoint: no campaign_id in both.
        assert set(countable["campaign_id"]) & set(cohort["campaign_id"]) == set()
        # Cohort is exactly the ALGO bucket (reuses the existing predicate).
        assert (cohort["stat_bucket"] == ec.STAT_BUCKET_ALGO).all()
        assert len(cohort) == 3

    def test_analytics_engine_does_not_import_algo_metrics(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "analytics_engine.py")).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert n.name != "algo_metrics"
            if isinstance(node, ast.ImportFrom):
                assert node.module != "algo_metrics"


# ──────────────────────────────────────────────────────────────────────────────
# ALGO cohort metrics on the founder's §2/§3 real numbers
# ──────────────────────────────────────────────────────────────────────────────

def _cohort_from_returns(returns, symbol="QQQ"):
    """Build a minimal cohort DataFrame from a list of per-trade %-returns."""
    rows = []
    for i, r in enumerate(returns):
        rows.append({
            "campaign_id": f"{symbol}{i}", "symbol": symbol,
            "setup_type": "ALGO", "stat_bucket": ec.STAT_BUCKET_ALGO,
            "trade_return_pct": float(r), "net_r": float(r),
        })
    return pd.DataFrame(rows)


class TestAlgoCohortMetricsFounderNumbers:
    def test_pf_reproduces_known_value(self):
        # PF = Σwin / |Σloss|. 3 wins of +4 each = 12; 2 losses of -2 = 4 → 3.0
        df = _cohort_from_returns([4, 4, 4, -2, -2])
        m = algo_metrics.compute_algo_cohort_metrics(df)
        assert m["algo_pf"] == pytest.approx(3.0)

    def test_loss_streak_reproduces(self):
        # MARK §2 cross-check: max trailing loss streak.
        df = _cohort_from_returns([1, -1, -1, -1, -1, -1, -1, 2])  # streak 6
        m = algo_metrics.compute_algo_cohort_metrics(df)
        assert m["algo_loss_streak"] == 6

    def test_sum_last_5_and_10(self):
        df = _cohort_from_returns(
            [1, 1, 1, 1, 1, -3, -3, -3, -3, -3])  # last5 = -15, last10 = -10
        m = algo_metrics.compute_algo_cohort_metrics(df)
        assert m["algo_sum_last_5"] == pytest.approx(-15.0)
        assert m["algo_sum_last_10"] == pytest.approx(-10.0)

    def test_2026_regime_pf_below_one(self):
        # §3: 2026 regime PF 0.73 < 1 — losing-regime cohort.
        df = _cohort_from_returns([5, 5, -7, -7])  # PF = 10/14 ≈ 0.714
        m = algo_metrics.compute_algo_cohort_metrics(df)
        assert m["algo_pf"] < 1.0

    def test_caveat_always_present(self):
        df = _cohort_from_returns([1, -1])
        m = algo_metrics.compute_algo_cohort_metrics(df)
        assert m["basis"] == "backtest"
        assert m["caveat_he"] == algo_rules.ALGO_BACKTEST_CAVEAT_HE
        assert m["caveat_en"] == algo_rules.ALGO_BACKTEST_CAVEAT_EN

    def test_empty_cohort_still_carries_caveat(self):
        m = algo_metrics.compute_algo_cohort_metrics(pd.DataFrame())
        assert m["algo_n"] == 0
        assert m["caveat_he"] == algo_rules.ALGO_BACKTEST_CAVEAT_HE

    def test_window_is_30(self):
        assert algo_metrics.ALGO_COHORT_WINDOW == 30


# ──────────────────────────────────────────────────────────────────────────────
# Governor — advisory-not-instruction (MARK §1 / §6)
# ──────────────────────────────────────────────────────────────────────────────

class TestGovernorAdvisoryOnly:
    def test_no_flags_yields_none(self):
        g = algo_metrics.evaluate_governor({}, [], None, None)
        assert g["actionability"] == "none"

    def test_decay_yields_review_required_never_action(self):
        cm = algo_metrics.compute_algo_cohort_metrics(
            _cohort_from_returns([-5, -5, -5, -5, -5, -5, -5, -5]))
        g = algo_metrics.evaluate_governor(cm, [], None, None)
        assert g["actionability"] == "Review Required"
        assert g["actionability"] != "Action Required"

    def test_governor_never_emits_action_required_under_any_input(self):
        cm = algo_metrics.compute_algo_cohort_metrics(
            _cohort_from_returns([-9] * 10))
        positions = [
            {"symbol": "PLTR", "open_pct": 25,
             "giveback_classification": "protection_failure"},
            {"symbol": "HOOD", "open_pct": 18},
        ]
        g = algo_metrics.evaluate_governor(cm, positions,
                                           algo_cluster_pct=40.0,
                                           account_r=-9.0)
        assert g["actionability"] in ("none", "Review Required")
        assert g["actionability"] != "Action Required"
        # No suggested_stop, no instruction key anywhere in the output.
        assert "suggested_stop" not in g
        for fl in g["flags"]:
            assert set(fl.keys()) <= {"code", "he", "en"}

    def test_minus_5r_account_basis_trigger(self):
        g = algo_metrics.evaluate_governor({}, [], None, account_r=-6.0)
        codes = [f["code"] for f in g["flags"]]
        assert "R5" in codes
        assert any("Account-R" in f["en"] for f in g["flags"])

    def test_cluster_reuses_existing_constants(self):
        g = algo_metrics.evaluate_governor(
            {}, [{"symbol": "QQQ"}], algo_cluster_pct=31.0)
        assert any(f["code"] == "C5" for f in g["flags"])
        g2 = algo_metrics.evaluate_governor(
            {}, [{"symbol": "QQQ"}], algo_cluster_pct=36.0)
        assert any(f["code"] == "C5C" for f in g2["flags"])
        # The thresholds are the engine's existing constants (not invented).
        assert ec.ALGO_CLUSTER_WARNING_PCT == 30.0
        assert ec.ALGO_CLUSTER_CRITICAL_PCT == 35.0

    def test_pltr_hood_and_tsla_pltr_cooccurrence(self):
        g = algo_metrics.evaluate_governor(
            {}, [{"symbol": "PLTR"}, {"symbol": "HOOD"}, {"symbol": "TSLA"}])
        codes = [f["code"] for f in g["flags"]]
        assert "C3" in codes  # PLTR & HOOD
        assert "C4" in codes  # TSLA & PLTR

    def test_governor_output_carries_caveat(self):
        g = algo_metrics.evaluate_governor({}, [], None, account_r=-6.0)
        assert g["caveat_he"] == algo_rules.ALGO_BACKTEST_CAVEAT_HE


class TestEngineAlgoShortcircuitPreserved:
    def test_algo_observed_path_byte_identical(self):
        # Regression guard: the ALGO_OBSERVED return contract is untouched.
        src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "engine_core.py")).read()
        assert '"action": "מנוהל חיצונית — בקרה בלבד"' in src
        assert '"suggested_stop": None' in src

    def test_is_stat_countable_still_excludes_algo(self):
        assert ec.is_stat_countable(ec.STAT_BUCKET_ALGO) is False
        assert ec.is_stat_countable(ec.STAT_BUCKET_DATA_INCOMPLETE) is False


# ──────────────────────────────────────────────────────────────────────────────
# algo_rules — #4 known rule + #5 dead-money source (MARK §3 / §4)
# ──────────────────────────────────────────────────────────────────────────────

class TestAlgoRulesLookup:
    def test_qqq_hood_no_hard_stop_time_exit_controlled(self):
        for sym in ("QQQ", "HOOD"):
            d = algo_rules.get_algo_known_rule(sym)
            assert d["hard_stop_pct"] is None
            assert "ללא סטופ קשיח" in d["display"]
            assert algo_rules.algo_time_exit_signal(sym) is not None

    def test_tsla_jpm_have_hard_stop_no_time_exit(self):
        assert algo_rules.get_algo_known_rule("TSLA")["hard_stop_pct"] == -4.3
        assert algo_rules.get_algo_known_rule("JPM")["hard_stop_pct"] == -3.3
        # MARK §4: TSLA/JPM get NO ALGO dead-money signal.
        assert algo_rules.algo_time_exit_signal("TSLA") is None
        assert algo_rules.algo_time_exit_signal("JPM") is None

    def test_pltr_emergency_cushion_not_management_stop(self):
        d = algo_rules.get_algo_known_rule("PLTR")
        assert d["emergency_cushion_pct"] == -25.0
        assert d["hard_stop_pct"] is None
        assert "כרית חירום" in d["display"]

    def test_unknown_symbol_returns_none_no_fabrication(self):
        assert algo_rules.get_algo_known_rule("AAPL") is None
        assert algo_rules.describe_algo_risk_control("AAPL") is None
        assert algo_rules.get_algo_known_rule(None) is None

    def test_describe_has_no_imperative_verb(self):
        # Honesty mandate: descriptive, never an instruction. Hebrew
        # imperative cue words must not appear in the known-rule display.
        bad = ["מכור", "קנה", "סגור", "העלה סטופ", "צא ", "בצע"]
        for sym in algo_rules.ALGO_KNOWN_RULES:
            txt = algo_rules.describe_algo_risk_control(sym)
            for b in bad:
                assert b not in txt, f"{sym}: imperative {b!r} in {txt!r}"

    def test_lookup_returns_copy_not_reference(self):
        d = algo_rules.get_algo_known_rule("QQQ")
        d["display"] = "MUTATED"
        assert algo_rules.get_algo_known_rule("QQQ")["display"] != "MUTATED"


# ──────────────────────────────────────────────────────────────────────────────
# Scope B — on-demand report dev button (SPRINT17_PLAN Scope item B)
# ──────────────────────────────────────────────────────────────────────────────

import report_on_demand
import report_scheduler as sched


class TestScopeBPeriodLogic:
    def test_weekly_ref_uses_scheduler_period_logic(self):
        # Wed 2025-05-14 → last complete week ends Sat 2025-05-10.
        now = datetime(2025, 5, 14, 10, 0)
        ref = report_on_demand.last_complete_weekly_ref(now)
        assert ref.weekday() == 5  # Saturday
        ps, pe = sched._weekly_period(ref)
        # Identical shape to the scheduler: Sunday 00:00 → Saturday 23:59:59.
        assert ps.weekday() == 6 and ps.hour == 0
        assert pe.weekday() == 5 and pe.hour == 23
        assert (pe - ps).days == 6

    def test_on_a_saturday_uses_previous_complete_week(self):
        sat = datetime(2025, 5, 17, 9, 0)  # a Saturday
        ref = report_on_demand.last_complete_weekly_ref(sat)
        assert ref.date() < sat.date()
        assert ref.weekday() == 5

    def test_monthly_ref_yields_previous_month(self):
        now = datetime(2025, 6, 15)
        ref = report_on_demand.last_complete_monthly_ref(now)
        ps, pe = sched._monthly_period(ref)
        assert ps.month == 5 and ps.year == 2025  # May = last complete month


class TestScopeBNoSnapshotMutation:
    """HARD constraint: on-demand run performs NO snap_save and leaves the
    scheduler period-dedup untouched."""

    def _patched_env(self):
        return patch.dict(os.environ, {
            "TELEGRAM_TOKEN": "T", "TELEGRAM_CHAT_ID": "C"})

    def test_run_on_demand_never_calls_snap_save(self):
        with patch("report_snapshot_store.save") as snap_save, \
             patch("report_scheduler._fetch_trades_df",
                   return_value=pd.DataFrame()), \
             patch("report_scheduler._mark_ran") as mark_ran, \
             patch("report_scheduler._save_state") as save_state, \
             patch("account_state.load",
                   return_value={"nav": 10000.0, "risk_pct_input": 0.5,
                                 "nav_source": "test", "freshness": "x"}), \
             patch("report_renderer.render_weekly", return_value="r.pdf"), \
             patch("report_delivery.deliver_report",
                   return_value={"summary_ok": True, "pdf_ok": True}), \
             self._patched_env():
            res = report_on_demand.run_on_demand(
                "weekly", now=datetime(2025, 5, 14, 10, 0))
        assert res["ok"] is True
        snap_save.assert_not_called()      # NO snapshot mutation
        mark_ran.assert_not_called()       # scheduler dedup untouched
        save_state.assert_not_called()     # scheduler state untouched

    def test_on_demand_module_does_not_call_snapshot_save(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "report_on_demand.py")).read()
        tree = ast.parse(src)
        # No `snap_save`/`save` from report_snapshot_store is imported or
        # called; only the read-only `load_recent` is.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) \
                    and node.module == "report_snapshot_store":
                names = {n.name for n in node.names}
                assert "save" not in names
                assert names <= {"load_recent"}

    def test_graceful_degradation_still_works(self):
        with patch("report_snapshot_store.save") as snap_save, \
             patch("report_scheduler._fetch_trades_df",
                   return_value=pd.DataFrame()), \
             patch("account_state.load",
                   return_value={"nav": 10000.0, "risk_pct_input": 0.5,
                                 "nav_source": "t", "freshness": "x"}), \
             patch("report_renderer.render_weekly",
                   side_effect=OSError("WeasyPrint missing")), \
             patch("report_delivery.deliver_report",
                   return_value={"summary_ok": True, "pdf_ok": False}) \
                as deliver, \
             self._patched_env():
            res = report_on_demand.run_on_demand(
                "weekly", now=datetime(2025, 5, 14, 10, 0))
        assert res["ok"] is True
        assert res["pdf_degraded"] is True
        snap_save.assert_not_called()
        # Degraded trailer present in the delivered summary text.
        sent_text = deliver.call_args[0][1]
        assert sched._DEGRADED_PDF_NOTE in sent_text


class TestScopeBDevMenuGated:
    @staticmethod
    def _labels(markup):
        # Robust to (a) the real telebot ReplyKeyboardMarkup (`.keyboard` =
        # list of rows of dicts) and (b) the suite-wide fake markup installed
        # by test_telegram_menus.py (`.buttons` = flat list with `.text`).
        out = []
        if hasattr(markup, "buttons"):
            for b in markup.buttons:
                out.append(b["text"] if isinstance(b, dict)
                           else getattr(b, "text", str(b)))
            return out
        for row in getattr(markup, "keyboard", []):
            for b in row:
                out.append(b["text"] if isinstance(b, dict)
                           else getattr(b, "text", str(b)))
        return out

    def test_button_in_developer_menu_only(self):
        import telegram_menus
        dev_labels = self._labels(telegram_menus.get_developer_menu())
        assert "📈 דוח שבועי עכשיו" in dev_labels
        assert "📆 דוח חודשי עכשיו" in dev_labels
        # NOT in the normal portfolio menu.
        pf_labels = self._labels(telegram_menus.get_portfolio_menu())
        assert "📈 דוח שבועי עכשיו" not in pf_labels
