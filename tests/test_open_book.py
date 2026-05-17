"""
Sprint-18 Wave-2 — OPEN BOOK (unrealized) in weekly/monthly report.

Gated by docs/teams/MARK_SPRINT18_RULINGS.md. These tests prove:

  1. Realized-KPI BYTE-IDENTICAL guard — compute_period_analytics returns the
     EXACT same dict with vs without the open-book path executed; the open-book
     dict is id()-distinct and the realized dict is unmutated key-for-key
     (incl. setup_breakdown). (Mark §1 / §5.1, §5.2, §5.3)
  2. Open-book + ALGO segregation — founder command-room positions
     HOOD/MRVL/PLTR/PWR/TSLA/WCC (HOOD/PLTR/TSLA ALGO per ALGO_SYMBOLS;
     MRVL/PWR/WCC discretionary). ALGO rows ONLY in open_book_algo, NEVER in
     open_book_disc, NEVER in any realized total; discretionary floating /
     Structure-R / Account-R == what telegram_portfolio computes from the same
     row (parity, not re-derivation); ALGO Structure-R = "—", never 0.00R.
     (Mark §1 / §3 / §5.4, §5.5, §5.6)
  3. #1 wording — empty-state matrix (both cases), no "ללא עסקאות" with a
     book, data-source + price-fallback honest. (Mark §2 / §5.7, §5.8)

`python -m pytest -q -p no:cacheprovider`.
"""
import os
import sys
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import engine_core as ec
import analytics_engine as ae
import report_open_book as rob


_ACCOUNT = {
    "nav": 7921.0,
    "risk_pct_input": 0.5,          # target_risk = 7921 * 0.005 = $39.605
    "nav_source": "broker",
    "total_deposited": 7500.0,
}

START = datetime(2025, 5, 3)
END   = datetime(2025, 5, 10)


def _buy(campaign_id, date_str, price, qty, *, initial_stop, setup, symbol,
         trade_id):
    return {
        "campaign_id":  campaign_id,
        "side":         "BUY",
        "trade_date":   date_str,
        "trade_id":     trade_id,
        "price":        price,
        "quantity":     qty,
        "pnl_usd":      0,
        "initial_stop": initial_stop,
        "stop_loss":    initial_stop,
        "setup_type":   setup,
        "symbol":       symbol,
    }


def _command_room_df():
    """The founder's live 6-position command-room book.

    HOOD/PLTR/TSLA are in ec.ALGO_SYMBOLS; when setup_type is unknown the
    symbol fallback in is_algo_position makes them ALGO. MRVL/PWR/WCC are
    discretionary (explicit setup, not in ALGO_SYMBOLS).
    """
    rows = [
        # Discretionary — explicit EP/VCP setups with valid initial stops.
        _buy("c-mrvl", "2025-04-20", 60.00, 30, initial_stop=54.00,
             setup="VCP", symbol="MRVL", trade_id="t1"),
        _buy("c-pwr",  "2025-04-21", 95.00, 12, initial_stop=88.00,
             setup="EP",  symbol="PWR",  trade_id="t2"),
        _buy("c-wcc",  "2025-04-22", 150.00, 6, initial_stop=140.00,
             setup="EP",  symbol="WCC",  trade_id="t3"),
        # ALGO — setup unknown ⇒ ALGO_SYMBOLS symbol fallback engages.
        _buy("c-hood", "2025-04-18", 20.00, 50, initial_stop=0,
             setup="Unknown", symbol="HOOD", trade_id="t4"),
        _buy("c-pltr", "2025-04-19", 22.00, 40, initial_stop=0,
             setup="Unknown", symbol="PLTR", trade_id="t5"),
        _buy("c-tsla", "2025-04-15", 240.00, 4, initial_stop=0,
             setup="Unknown", symbol="TSLA", trade_id="t6"),
    ]
    return pd.DataFrame(rows)


# Fixed "live" prices for deterministic floating-PnL parity.
_PRICES = {
    "MRVL": 65.00, "PWR": 98.00, "WCC": 151.00,
    "HOOD": 23.00, "PLTR": 24.00, "TSLA": 250.00,
}


def _fake_live_price(sym):
    return _PRICES.get(sym)


# ── 1. Realized-KPI byte-identical guard ────────────────────────────────────

class TestRealizedKpiByteIdentical:
    def test_open_book_path_does_not_mutate_analytics_dict(self):
        df = _command_room_df()
        # Realized analytics WITHOUT the open-book path.
        a_before = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        a_before_copy = dict(a_before)

        # Run the open-book path on the SAME df.
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            ob = rob.build_open_book(df, _ACCOUNT)

        # Realized analytics AFTER the open-book path.
        a_after = ae.compute_period_analytics(df, START, END, _ACCOUNT)

        # Byte-identical key-for-key (incl. setup_breakdown).
        assert a_after == a_before_copy
        assert a_before == a_before_copy  # original unmutated
        # The open-book dict is a DISTINCT object — never the analytics dict.
        assert id(ob) != id(a_before)
        assert id(ob) != id(a_after)
        assert "win_rate" not in ob and "expectancy_r" not in ob
        assert "open_book_present" in ob

    def test_open_book_module_never_imports_analytics_engine(self):
        """AST proof: no import of analytics_engine and no call to
        compute_period_analytics anywhere in executable code (docstrings,
        which legitimately reference the seam, are excluded)."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(rob))
        imported = set()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Attribute):
                called.add(node.attr)
            elif isinstance(node, ast.Name):
                called.add(node.id)
        assert "analytics_engine" not in imported
        assert "compute_period_analytics" not in called
        # Sanity: it DOES depend only on engine_core (reuse-only).
        assert "engine_core" in imported

    def test_realized_totals_exclude_floating_pnl(self):
        df = _command_room_df()
        a = ae.compute_period_analytics(df, START, END, _ACCOUNT)
        # 0 campaigns closed (all open) ⇒ realized is empty regardless of book.
        assert a["campaigns_closed"] == 0
        assert a["realized_pnl"] == 0
        assert a["total_r_net"] == 0


# ── 2. Open-book + ALGO segregation ─────────────────────────────────────────

class TestOpenBookAlgoSegregation:
    def _book(self):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            return rob.build_open_book(df, _ACCOUNT)

    def test_present_and_counts(self):
        ob = self._book()
        assert ob["open_book_present"] is True
        t = ob["open_book_totals"]
        assert t["n_disc"] == 3
        assert t["n_algo"] == 3

    def test_algo_rows_only_in_algo_list(self):
        ob = self._book()
        disc_syms = {p["symbol"] for p in ob["open_book_disc"]}
        algo_syms = {p["symbol"] for p in ob["open_book_algo"]}
        assert algo_syms == {"HOOD", "PLTR", "TSLA"}
        assert disc_syms == {"MRVL", "PWR", "WCC"}
        # No symbol appears in both lists (strict #8 segregation).
        assert disc_syms.isdisjoint(algo_syms)

    def test_algo_never_in_discretionary_totals(self):
        ob = self._book()
        t = ob["open_book_totals"]
        # Discretionary floating excludes ALGO floating entirely.
        disc_sum = sum(p["floating_pnl"] for p in ob["open_book_disc"])
        algo_sum = sum(p["floating_pnl"] for p in ob["open_book_algo"])
        assert t["floating_pnl_disc"] == pytest.approx(disc_sum)
        assert t["floating_pnl_algo"] == pytest.approx(algo_sum)
        assert algo_sum != 0  # ALGO has real floating, just segregated

    def test_discretionary_floating_parity_with_command_room(self):
        """Discretionary floating == command-room expression
        (curr - entry) * qty (telegram_portfolio.py:285)."""
        ob = self._book()
        by = {p["symbol"]: p for p in ob["open_book_disc"]}
        # MRVL: (65 - 60) * 30 = 150 ; PWR: (98 - 95) * 12 = 36 ;
        # WCC: (151 - 150) * 6 = 6
        assert by["MRVL"]["floating_pnl"] == pytest.approx(150.0)
        assert by["PWR"]["floating_pnl"] == pytest.approx(36.0)
        assert by["WCC"]["floating_pnl"] == pytest.approx(6.0)

    def test_discretionary_dual_r_parity(self):
        """Structure R / Account R == the EXISTING engine functions on the
        same inputs (no re-derivation)."""
        ob = self._book()
        by = {p["symbol"]: p for p in ob["open_book_disc"]}
        # MRVL original risk = (60 - 54) * 30 = 180 ; floating 150
        #   structure_r = compute_r_true(150, 180) = round(0.833..,2) = 0.83
        #   account_r   = compute_r_target(150, 39.605) ≈ 3.79
        target = _ACCOUNT["nav"] * _ACCOUNT["risk_pct_input"] / 100
        assert by["MRVL"]["structure_r"] == ec.compute_r_true(150.0, 180.0)
        assert by["MRVL"]["account_r"] == ec.compute_r_target(150.0, target)
        assert by["MRVL"]["structure_valid"] is True
        assert by["MRVL"]["account_valid"] is True

    def test_algo_structure_r_is_dash_never_zero(self):
        ob = self._book()
        for p in ob["open_book_algo"]:
            assert p["structure_r_token"] == "—"
            assert p["structure_valid"] is False
            # The numeric structure_r must NEVER be presented as 0.00R for ALGO
            assert "0.00R" not in p["structure_r_token"]

    def test_algo_observation_only_and_single_caveat(self):
        ob = self._book()
        for p in ob["open_book_algo"]:
            assert p["observation_label"] == "פיקוח בלבד · לא הוראה"
            assert p["external_caveat"] == \
                "מנוהל חיצונית — פיקוח, ללא הוראת Sentinel"
            # No backtest caveat attaches to the LIVE floating PnL (Mark §3).
            assert "backtest" not in str(p).lower()
            assert "בקטסט" not in str(p)

    def test_unrealized_label_present_on_every_row(self):
        ob = self._book()
        for p in ob["open_book_disc"] + ob["open_book_algo"]:
            assert p["unrealized_label"] == "לא ממומש"

    def test_realized_pnl_separate_from_floating(self):
        ob = self._book()
        for p in ob["open_book_disc"] + ob["open_book_algo"]:
            # realized_pnl is a SEPARATE field; these are all-buy ⇒ 0 realized.
            assert p["realized_pnl"] == 0
            assert p["floating_pnl"] != p["realized_pnl"] or \
                p["floating_pnl"] == 0


# ── 3. #1 honesty — data source + price fallback ────────────────────────────

class TestDataSourceHonesty:
    def test_all_live_source_is_live(self):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            ob = rob.build_open_book(df, _ACCOUNT)
        assert ob["open_book_data_source"] == "Live"
        assert ob["open_book_price_fallback_syms"] == []

    def test_price_fallback_marks_cached_and_records_symbol(self):
        df = _command_room_df()

        def _partial(sym):
            return None if sym == "WCC" else _PRICES.get(sym)

        with patch.object(ec, "get_live_price", side_effect=_partial):
            ob = rob.build_open_book(df, _ACCOUNT)
        assert ob["open_book_data_source"] == "Cached"
        assert "WCC" in ob["open_book_price_fallback_syms"]
        # WCC fell back to entry ⇒ floating = 0 (never a guessed price).
        wcc = next(p for p in ob["open_book_disc"] if p["symbol"] == "WCC")
        assert wcc["price_is_fallback"] is True
        assert wcc["current"] == wcc["entry"]
        assert wcc["floating_pnl"] == pytest.approx(0.0)

    def test_sync_temporary_override_never_fabricated(self):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            ob = rob.build_open_book(df, _ACCOUNT,
                                     data_source_override="Sync זמני")
        assert ob["open_book_data_source"] == "Sync זמני"

    def test_empty_df_returns_not_present_never_raises(self):
        ob = rob.build_open_book(pd.DataFrame(), _ACCOUNT)
        assert ob["open_book_present"] is False
        assert ob["open_book_disc"] == [] and ob["open_book_algo"] == []
        ob2 = rob.build_open_book(None, _ACCOUNT)
        assert ob2["open_book_present"] is False


# ── 3b. Empty-state matrix (#1 wording) ─────────────────────────────────────

class TestEmptyStateWording:
    def _book(self):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            return rob.build_open_book(df, _ACCOUNT)

    def test_case_a_zero_closed_with_live_book(self):
        ob = self._book()
        lines = rob.empty_state_lines(ob, "3–9 במאי 2025")
        text = "\n".join(lines)
        assert "0 קמפיינים נסגרו בתקופה" in text
        assert "אין נתוני ביצועים ממומשים" in text
        assert "ספר פתוח (לא ממומש)" in text
        assert "פוזיציות" in text
        assert "מקור:" in text
        # NEVER the word "ללא עסקאות" while a live book exists.
        assert "ללא עסקאות" not in text

    def test_case_b_truly_empty(self):
        ob = rob.build_open_book(pd.DataFrame(), _ACCOUNT)
        lines = rob.empty_state_lines(ob, "3–9 במאי 2025")
        text = "\n".join(lines)
        assert text == \
            "✅ 0 קמפיינים נסגרו · אין פוזיציות פתוחות. שבוע ללא פעילות מסחר."

    def test_case_a_includes_window_and_source(self):
        ob = self._book()
        lines = rob.empty_state_lines(ob, "3–9 במאי 2025")
        text = "\n".join(lines)
        assert "3–9 במאי 2025" in text
        assert "Live" in text


# ── 3c. Mark-to-market delta — baseline pending (#1, no fabrication) ─────────

class TestMarkDeltaBaselinePending:
    def _book(self):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            return rob.build_open_book(df, _ACCOUNT)

    def test_no_prev_snapshot_is_baseline_pending(self):
        ob = self._book()
        d = rob.compute_mark_delta(ob, None)
        assert d["available"] is False
        assert d["text"] == \
            "Δ שבועי (mark-to-market): — · ממתין לבסיס שבוע קודם"
        assert d["delta_floating_disc"] is None

    def test_old_snapshot_without_open_marks_is_baseline_pending(self):
        ob = self._book()
        old_snap = {"period_start": "2025-04-26", "win_rate": 0.5}
        d = rob.compute_mark_delta(ob, old_snap)
        assert d["available"] is False
        assert "ממתין לבסיס שבוע קודם" in d["text"]

    def test_prior_open_marks_is_pure_subtraction(self):
        ob = self._book()
        prev = {
            "open_marks": {
                "floating_pnl_disc": 100.0,
                "floating_pnl_algo": 50.0,
            }
        }
        d = rob.compute_mark_delta(ob, prev)
        assert d["available"] is True
        cur = ob["open_book_totals"]
        assert d["delta_floating_disc"] == pytest.approx(
            cur["floating_pnl_disc"] - 100.0)
        assert d["delta_floating_algo"] == pytest.approx(
            cur["floating_pnl_algo"] - 50.0)
        # ALGO delta is segregated/observation-only in the text.
        assert "פיקוח בלבד · לא הוראה" in d["text"]
        assert "ללא עסקאות" not in d["text"]


class TestPeriodScopedActivity:
    """Founder binding criterion (SPRINT18_PLAN.md 2026-05-16 14:00):
    the open book must reflect PERIOD-scoped activity — positions opened
    AFTER period_end excluded; opened-in-period vs held-from-before
    attributed; never imply "no trades" when a book spanned the window."""

    def _ob(self, ps=None, pe=None):
        df = _command_room_df()
        with patch.object(ec, "get_live_price", side_effect=_fake_live_price):
            return rob.build_open_book(df, _ACCOUNT,
                                       period_start=ps, period_end=pe)

    # Entry dates: TSLA 04-15, HOOD 04-18, PLTR 04-19, MRVL 04-20,
    # PWR 04-21, WCC 04-22.  Window = 19→21 Apr 2025.
    _PS = datetime(2025, 4, 19)
    _PE = datetime(2025, 4, 21, 23, 59, 59)

    def _syms(self, ob):
        return ({r["symbol"] for r in ob["open_book_disc"]}
                | {r["symbol"] for r in ob["open_book_algo"]})

    def test_opened_after_period_end_excluded(self):
        ob = self._ob(self._PS, self._PE)
        # WCC opened 04-22 (after 04-21) → never existed during the window.
        assert "WCC" not in self._syms(ob)
        assert "MRVL" in self._syms(ob) and "PLTR" in self._syms(ob)

    def test_opened_in_period_attributed(self):
        ob = self._ob(self._PS, self._PE)
        recs = {r["symbol"]: r for r in
                ob["open_book_disc"] + ob["open_book_algo"]}
        for s in ("PLTR", "MRVL", "PWR"):           # 19/20/21 Apr
            assert recs[s]["period_status"] == "opened_in_period"
            assert recs[s]["period_label_he"] == rob.OPENED_IN_PERIOD_LABEL
        for s in ("TSLA", "HOOD"):                  # 15/18 Apr (< start)
            assert recs[s]["period_status"] == "held_from_before"
            assert recs[s]["period_label_he"] == rob.HELD_FROM_BEFORE_LABEL
        assert ob["open_book_totals"]["n_opened_total"] == 3

    def test_no_period_args_is_back_compatible(self):
        ob = self._ob()                              # legacy callers/tests
        assert "WCC" in self._syms(ob)               # nothing excluded
        for r in ob["open_book_disc"] + ob["open_book_algo"]:
            assert r["period_status"] == "" and r["period_label_he"] == ""
        assert ob["open_book_totals"]["n_opened_total"] == 0

    def test_empty_state_states_opened_count_never_no_trades(self):
        ob = self._ob(self._PS, self._PE)
        lines = rob.empty_state_lines(ob, "19/04–21/04/2025")
        joined = " ".join(lines)
        assert "ללא עסקאות" not in joined          # never with a live book
        assert "3" in joined and "נפתחו בתקופה זו" in joined

    def test_summary_lines_surface_opened_in_period(self):
        ob = self._ob(self._PS, self._PE)
        joined = " ".join(rob.open_book_summary_lines(ob))
        assert "נפתחו בתקופה זו" in joined and "3" in joined
