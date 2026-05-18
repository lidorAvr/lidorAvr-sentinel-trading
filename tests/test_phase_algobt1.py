"""Phase ALGO-BT-1 acceptance suite — ALGO backtest baseline (ingest +
per-strategy statistics + additive read-only surface).

Authoritative spec: docs/teams/PHASE_ALGOBT1_SCOPE.md (governs).

Phase-1 is OBSERVE-ONLY (DEC-20260511-001 #8 / AGENTS.md #8): a pure,
deterministic, read-only loader (`algo_backtest_store`) + computed-on-load
per-strategy BACKTEST statistics + an additive read-only dashboard panel.
Zero alerts, zero directives, zero migration, zero Supabase, zero write,
no new message TYPE. The figures are TrendSpider edge-shape percentages
(Volume=1, Trade cost=0%) — NOT account P&L and NOT a forward promise;
every surface carries an explicit BACKTEST + observe-only label.

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). The synthetic fixture under `tests/_fixtures/algo_backtests/`
is hand-crafted in the exact 22-col schema with NO real strategy data; it
is tracked because it lives under `tests/`, NOT under the git-ignored
`data/algo_backtests/`.

Hand-computed expected values (fixture is deliberately verifiable by hand):

  HOOD::hood_21x9_ema_2h — closed Return%: +10,+20,-5,+30,-15,+5
    (a 7th row Closed?=no is filtered; an 8th 1-field row is malformed;
     TSLA/bad_schema.csv has the wrong header ⇒ skipped-with-note)
    N=6 · wins[10,20,30,5]→WR 4/6=66.667% · losses[-5,-15] Σ=-20
    sum=45 · avg=7.5 · sorted[-15,-5,5,10,20,30] median=(5+10)/2=7.5
    PF = 65/|-20| = 3.25 · expectancy = mean = 7.5
    Max Drawdown vs Entry %: -2.5,-8,-12,-1,-20,-3 ⇒ min = -20.0
    Length: 4,6,3,8,5,2 ⇒ avg=28/6, max=8
    exit mix: TP=3, SL=2, time(x_candles_passed)=1, signal=0
    sign run [+,+,-,+,-,+] ⇒ longest win=2, longest loss=1
    entry span 29 Jan 2024 (IST) → 03 Apr 2024 (IDT)
  TSLA::tsla_6x34_sma_2h — closed Return%: +12,+8,+25 (all wins)
    N=3 · WR=100% · sum=45 · avg=15 · median=12
    no losses ⇒ PF = math.inf, label "∞" · streaks W=3, L=0
    exit mix: TP=2, signal(Zulu)=1
"""
import importlib
import math
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import algo_backtest_store as s  # noqa: E402

_FIX = os.path.join(os.path.dirname(__file__), "_fixtures", "algo_backtests")
_HOOD = "HOOD::hood_21x9_ema_2h"
_TSLA = "TSLA::tsla_6x34_sma_2h"


def _stats(base=_FIX):
    return s.compute_algo_backtest_stats(s.load_algo_backtests(base))


# ════════════════════════════════════════════════════════════════════════════
# Case 1 — parser correctness (schema, Closed? filter, UTF-8/Hebrew folder,
#          IST/IDT timestamps, malformed-row & bad-schema-file skip-not-crash)
# ════════════════════════════════════════════════════════════════════════════

class TestCase1ParserCorrectness:
    def test_loads_both_strategies_under_hebrew_and_ascii_parents(self):
        """A Hebrew-named parent folder (`איתותים/HOOD/...`) and an ASCII
        one (`TSLA/...`) are both walked UTF-8-safely; the strategy id is
        derived from filename + Symbol."""
        loaded = s.load_algo_backtests(_FIX)
        assert loaded["present"] is True
        assert set(loaded["strategies"].keys()) == {_HOOD, _TSLA}
        assert loaded["strategies"][_HOOD]["symbol"] == "HOOD"
        assert loaded["strategies"][_TSLA]["symbol"] == "TSLA"

    def test_closed_no_row_is_filtered_out(self):
        """Only `Closed? == yes` rows are kept — the 7th HOOD row
        (Closed?=no) is excluded ⇒ exactly 6 HOOD trades."""
        loaded = s.load_algo_backtests(_FIX)
        assert len(loaded["strategies"][_HOOD]["trades"]) == 6
        rets = sorted(t["return_pct"]
                      for t in loaded["strategies"][_HOOD]["trades"])
        assert rets == [-15.0, -5.0, 5.0, 10.0, 20.0, 30.0]

    def test_ist_and_idt_timestamps_parse(self):
        """`29 Jan 2024 … IST` and `03 Apr 2024 … IDT` both parse ⇒ the
        entry date-span is first→last across the DST boundary."""
        span = _stats()["strategies"][_HOOD]["date_span"]
        assert span["first"] == "29 Jan 2024"
        assert span["last"] == "03 Apr 2024"

    def test_malformed_short_row_skipped_with_note_not_crash(self):
        """The trailing 1-field HOOD row is skipped with an honest note —
        the loader never raises."""
        loaded = s.load_algo_backtests(_FIX)
        assert any("שורה פגומה" in n for n in loaded["notes"])

    def test_wrong_schema_file_skipped_with_note_not_crash(self):
        """`TSLA/bad_schema.csv` (3-col header) is skipped wholesale with an
        honest schema note; its rows never pollute the TSLA strategy."""
        loaded = s.load_algo_backtests(_FIX)
        assert any("סכימה לא תואמת" in n for n in loaded["notes"])
        assert len(loaded["strategies"][_TSLA]["trades"]) == 3

    def test_expected_schema_is_exactly_22_columns(self):
        assert len(s.EXPECTED_COLUMNS) == 22
        assert s.EXPECTED_COLUMNS[0] == "Symbol"
        assert s.EXPECTED_COLUMNS[-1] == "Max Drawdown vs Entry After Candles"


# ════════════════════════════════════════════════════════════════════════════
# Case 2 — statistics vs hand-computed values
# ════════════════════════════════════════════════════════════════════════════

class TestCase2StatsHandComputed:
    def test_hood_stats_match_hand_computed(self):
        h = _stats()["strategies"][_HOOD]
        assert h["n"] == 6
        assert h["win_rate_pct"] == pytest.approx(66.6666667, abs=1e-4)
        assert h["avg_return_pct"] == pytest.approx(7.5)
        assert h["median_return_pct"] == pytest.approx(7.5)
        assert h["sum_return_pct"] == pytest.approx(45.0)
        assert h["profit_factor"] == pytest.approx(3.25)        # 65/20
        assert h["profit_factor_label"] == "3.25"
        assert h["expectancy_pct"] == pytest.approx(7.5)
        assert h["max_trade_drawdown_pct"] == pytest.approx(-20.0)
        assert h["avg_length_candles"] == pytest.approx(28.0 / 6.0)
        assert h["max_length_candles"] == pytest.approx(8.0)
        assert h["exit_reason_mix"] == {
            "take_profit": 3, "stop_loss": 2, "time_stop": 1, "signal": 0}
        assert h["longest_win_streak"] == 2
        assert h["longest_loss_streak"] == 1

    def test_tsla_all_wins_profit_factor_is_infinite(self):
        """No losing trade ⇒ profit_factor == math.inf, labelled '∞'
        (per scope: no losses → inf; the divide-by-zero is honestly
        represented, never a crash)."""
        t = _stats()["strategies"][_TSLA]
        assert t["n"] == 3
        assert t["win_rate_pct"] == pytest.approx(100.0)
        assert t["sum_return_pct"] == pytest.approx(45.0)
        assert t["avg_return_pct"] == pytest.approx(15.0)
        assert t["median_return_pct"] == pytest.approx(12.0)
        assert t["profit_factor"] == math.inf
        assert t["profit_factor_label"] == "∞"
        assert t["longest_win_streak"] == 3
        assert t["longest_loss_streak"] == 0
        assert t["exit_reason_mix"]["take_profit"] == 2
        assert t["exit_reason_mix"]["signal"] == 1

    def test_no_r_nav_or_account_keys_present(self):
        """Observe-only: the stats expose ONLY edge-shape % figures — there
        is NO R-multiple / NAV / exposure / account / pnl key anywhere (no
        live coupling). Every numeric key is a `_pct` / count / label, never
        an account-money key."""
        h = _stats()["strategies"][_HOOD]
        keys = {k.lower() for k in h.keys()}
        for forbidden in ("nav", "total_r", "structure_r", "account_r",
                          "exposure", "exposure_pct", "account_size",
                          "pnl_usd", "realized_pnl", "risk_usd"):
            assert forbidden not in keys
        # the only money-shaped quantities are explicitly BACKTEST %.
        assert "win_rate_pct" in keys and "avg_return_pct" in keys


# ════════════════════════════════════════════════════════════════════════════
# Case 3 — idempotency (pure function of the files present, no accumulation)
# ════════════════════════════════════════════════════════════════════════════

class TestCase3Idempotency:
    def test_load_twice_is_deep_equal(self):
        a = s.load_algo_backtests(_FIX)
        b = s.load_algo_backtests(_FIX)
        assert a == b
        assert s.compute_algo_backtest_stats(a) == \
            s.compute_algo_backtest_stats(b)

    def test_add_then_remove_a_file_adds_then_removes_exactly_it(self, tmp_path):
        """A pure function of the files PRESENT: copying the fixture, then
        adding one strategy file ⇒ exactly that strategy appears (others
        byte-identical); removing it ⇒ it is gone, no accumulation, no
        stale stateful store."""
        base = tmp_path / "abt"
        shutil.copytree(_FIX, base)
        before = s.compute_algo_backtest_stats(s.load_algo_backtests(str(base)))
        assert set(before["strategies"]) == {_HOOD, _TSLA}

        extra_dir = base / "QQQ"
        extra_dir.mkdir()
        src = os.path.join(_FIX, "TSLA", "tsla_6x34_sma_2h.csv")
        with open(src, encoding="utf-8") as fh:
            content = fh.read().replace("TSLA,long", "QQQ,long")
        extra = extra_dir / "qqq_6x30_sma_2h.csv"
        extra.write_text(content, encoding="utf-8")

        after_add = s.compute_algo_backtest_stats(
            s.load_algo_backtests(str(base)))
        added = set(after_add["strategies"]) - set(before["strategies"])
        assert len(added) == 1 and next(iter(added)).startswith("QQQ::")
        # the untouched strategies are byte-identical (no accumulation).
        assert after_add["strategies"][_HOOD] == before["strategies"][_HOOD]
        assert after_add["strategies"][_TSLA] == before["strategies"][_TSLA]

        os.remove(extra)
        after_rm = s.compute_algo_backtest_stats(
            s.load_algo_backtests(str(base)))
        assert set(after_rm["strategies"]) == set(before["strategies"])
        assert after_rm == before

    def test_replacing_a_file_replaces_only_that_strategy(self, tmp_path):
        """Replacing a strategy's CSV reflects ONLY-current — the prior
        rows do not accumulate (idempotent re-ingest)."""
        base = tmp_path / "abt"
        shutil.copytree(_FIX, base)
        tsla = base / "TSLA" / "tsla_6x34_sma_2h.csv"
        header = s.EXPECTED_COLUMNS
        new = (",".join(header) + "\n" +
               "TSLA,long,1,01 Jan 2024 20:30 IST,01 Jan 2024 20:30 IST,"
               "1,100,0%,02 Jan 2024 20:30 IST,02 Jan 2024 20:30 IST,2,150,"
               "yes,Romeo,take_profit,5,50.00,55,-1,3,-1,1\n")
        tsla.write_text(new, encoding="utf-8")
        st = s.compute_algo_backtest_stats(s.load_algo_backtests(str(base)))
        assert st["strategies"][_TSLA]["n"] == 1                 # not 3+1
        assert st["strategies"][_TSLA]["sum_return_pct"] == pytest.approx(50.0)
        # HOOD untouched.
        assert st["strategies"][_HOOD]["n"] == 6


# ════════════════════════════════════════════════════════════════════════════
# Case 4 — graceful missing/empty dir (no raise, honest empty)
# ════════════════════════════════════════════════════════════════════════════

class TestCase4GracefulEmpty:
    def test_missing_dir_no_raise_honest_empty(self):
        loaded = s.load_algo_backtests("tests/_fixtures/__definitely_absent__")
        st = s.compute_algo_backtest_stats(loaded)
        assert loaded["present"] is False
        assert st["present"] is False
        assert st["strategies"] == {}
        assert s.EMPTY_STATE_TEXT in loaded["notes"]

    def test_none_and_empty_base_dir_no_raise(self):
        for bad in (None, "", "   "):
            loaded = s.load_algo_backtests(bad)
            assert loaded["present"] is False
            assert s.EMPTY_STATE_TEXT in loaded["notes"]

    def test_empty_dir_no_csv_honest_empty(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        loaded = s.load_algo_backtests(str(d))
        assert loaded["present"] is False
        assert s.EMPTY_STATE_TEXT in loaded["notes"]


# ════════════════════════════════════════════════════════════════════════════
# Case 5 — BACKTEST + observe-only labels present in the formatter
# ════════════════════════════════════════════════════════════════════════════

class TestCase5FormatterLabels:
    def test_formatter_carries_backtest_and_observe_only_labels(self):
        out = s.format_algo_backtest_summary(_stats())
        assert s.BACKTEST_LABEL in out
        assert s.OBSERVE_ONLY_LABEL in out
        # honest edge-shape figures present, not presented as live truth.
        assert "WR=66.7%" in out
        assert "PF=∞" in out          # the all-wins strategy honestly shown

    def test_formatter_empty_state_is_honest(self):
        out = s.format_algo_backtest_summary(
            s.compute_algo_backtest_stats(
                s.load_algo_backtests("tests/_fixtures/__absent__")))
        assert s.EMPTY_STATE_TEXT in out
        assert s.BACKTEST_LABEL in out
        assert s.OBSERVE_ONLY_LABEL in out

    def test_formatter_is_pure_text_no_side_effect(self):
        st = _stats()
        snap = s.format_algo_backtest_summary(st)
        again = s.format_algo_backtest_summary(st)
        assert isinstance(snap, str) and snap == again


# ════════════════════════════════════════════════════════════════════════════
# Case 6 — the additive dashboard panel is read-only (no live ALGO/Supabase)
# ════════════════════════════════════════════════════════════════════════════

class TestCase6DashboardPanelReadOnly:
    def test_store_module_imports_no_network_or_supabase(self):
        """The store underpinning the panel imports NOTHING that could read
        live ALGO / Supabase / the network and performs no write."""
        src = open(s.__file__, encoding="utf-8").read()
        for forbidden in ("import supabase", "create_client", "requests",
                          "urllib", "import telebot", "yfinance",
                          ".execute(", "open(", "os.makedirs", "json.dump"):
            if forbidden == "open(":
                # the loader DOES open() CSVs read-only; assert no write mode.
                assert "\"w\"" not in src and "'w'" not in src and \
                    "\"a\"" not in src and "'a'" not in src
                continue
            assert forbidden not in src, f"unexpected `{forbidden}` in store"

    def test_dashboard_wires_panel_additively_via_store_only(self):
        """`dashboard.py` references the store for the additive panel and
        the panel's title/labels — without importing anything new that
        touches live ALGO state for it (the store is the only data path)."""
        root = os.path.dirname(os.path.dirname(__file__))
        dash = open(os.path.join(root, "dashboard.py"), encoding="utf-8").read()
        assert "import algo_backtest_store as abs_store" in dash
        assert "ALGO — בסיס בקטסט (פיקוח בלבד)" in dash
        assert "abs_store.load_algo_backtests()" in dash
        assert "abs_store.compute_algo_backtest_stats(" in dash
        # the panel renders the store result; it must NOT feed Supabase/live
        # ALGO data into the backtest panel.
        assert "supabase" not in _panel_block(dash)

    def test_panel_block_does_not_mutate_or_read_supabase(self):
        """The additive panel block contains no Supabase call and no write
        — it is display-only (observe-only doctrine)."""
        root = os.path.dirname(os.path.dirname(__file__))
        dash = open(os.path.join(root, "dashboard.py"), encoding="utf-8").read()
        block = _panel_block(dash)
        for forbidden in ("supabase.table", ".execute(", ".update(",
                          ".insert(", ".delete("):
            assert forbidden not in block


def _panel_block(dash_src: str) -> str:
    """The additive ALGO-BT-1 panel block in dashboard.py (marker-delimited)."""
    start = dash_src.index("Phase ALGO-BT-1 W-BT4 — ADDITIVE")
    end = dash_src.index("with tabs[3]:", start)
    return dash_src[start:end]


# ════════════════════════════════════════════════════════════════════════════
# Case 7 — LOCKED April + every _byte_lock_* unaffected by this Phase
# ════════════════════════════════════════════════════════════════════════════

class TestCase7LockedAprilAndByteLockUnaffected:
    def test_byte_locked_files_unmodified(self):
        """Phase ALGO-BT-1 touched NONE of the byte-locked money-math files
        (only new modules + an additive dashboard panel + new tests + the
        .gitignore + the scaffold)."""
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)

    def test_locked_april_regression_invariant_still_holds(self):
        """The LOCKED April ground truth is produced by analytics_engine,
        which this Phase does not import or alter — still exact."""
        from datetime import datetime
        mod = importlib.import_module("tests.test_real_data_april_regression")
        import analytics_engine as ae
        a = ae.compute_period_analytics(
            mod._april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), mod._ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2

    def test_store_does_no_r_nav_account_math(self):
        """The store is independent of the money-math layer: it neither
        imports engine_core/analytics_engine nor computes R/NAV — it is a
        pure CSV→stats function (observe-only, no live coupling)."""
        src = open(s.__file__, encoding="utf-8").read()
        assert "import engine_core" not in src
        assert "import analytics_engine" not in src
        assert "import account_state" not in src
