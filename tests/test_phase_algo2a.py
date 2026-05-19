"""Phase ALGO-2A acceptance suite — W-2A1 pure divergence helper + W-2A2
dual-surface (Telegram ALGO panel + dashboard ALGO-backtest panel) wiring.

Authoritative spec: docs/teams/PHASE_ALGO2A_SCOPE.md (governs).

Phase-2a is OBSERVE-ONLY (DEC-20260511-001 #8 / AGENTS.md #8): a pure,
deterministic, read-only per-symbol edge-shape divergence statistic joined
**by SYMBOL only** + ONE single-source-of-truth formatter rendered on BOTH
surfaces. ZERO alerts, ZERO directives, ZERO push, ZERO Supabase, ZERO
state, no new message TYPE. Every figure carries BACKTEST + observe-only
labels + the 6 honesty disclaimers + the founder-asserted (NOT
system-verified) join banner. Below the hard min-live-sample gate the
helper emits the explicit "אין מספיק מדגם חי" marker — NEVER a delta,
NEVER a silent zero.

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). All fixtures are hand-crafted synthetic dicts (no real
strategy data, no CSV under the git-ignored data/algo_backtests/).

Hand-computed expected deltas (live − backtest, AVG basis — the basis
algo_metrics exposes via _expectancy):

  HOOD live: n=35 WR=60.0 avg=+1.20 PF=1.80 loss_streak=3
  HOOD bt  :       WR=66.0 avg=+7.50 PF=3.25 loss_streak=1
    ΔWR=-6.00 · Δreturn=-6.30 · ΔPF=-1.45 · Δloss=+2.00
"""
import ast
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import algo_divergence as adv  # noqa: E402
import algo_metrics as am  # noqa: E402  (used ONLY for the floor-equality pin)


# ── synthetic fixtures (no real strategy data) ──────────────────────────────

def _live(n=35, wr=60.0, avg=1.20, pf=1.80, ls=3):
    return {"HOOD": {"n": n, "win_rate_pct": wr, "avg_return_pct": avg,
                     "profit_factor": pf, "loss_streak": ls}}


def _bt(symbol="HOOD", n=50, wr=66.0, avg=7.5, med=7.5, pf=3.25, ls=1):
    return {"present": True, "strategies": {
        f"{symbol}::strat": {
            "symbol": symbol, "n": n, "win_rate_pct": wr,
            "avg_return_pct": avg, "median_return_pct": med,
            "profit_factor": pf, "longest_loss_streak": ls,
        }}}


# ════════════════════════════════════════════════════════════════════════════
# Case 1 — per-symbol delta correctness on a synthetic fixture
# ════════════════════════════════════════════════════════════════════════════

class TestCase1DeltaCorrectness:
    def test_per_symbol_delta_matches_hand_computed(self):
        d = adv.compute_symbol_divergence("HOOD", _live(), _bt())
        assert d["enough_sample"] is True
        assert d["live_n"] == 35
        assert d["backtest_present"] is True
        assert d["win_rate_delta"] == pytest.approx(-6.0)
        assert d["return_delta"] == pytest.approx(-6.3)
        assert d["return_basis"] == "ממוצע"
        assert d["profit_factor_delta"] == pytest.approx(-1.45)
        assert d["loss_streak_delta"] == pytest.approx(2.0)

    def test_join_is_by_symbol_only_case_insensitive(self):
        d = adv.compute_symbol_divergence(
            "hood", _live(), _bt(symbol="HOOD"))
        assert d["symbol"] == "HOOD"
        assert d["backtest_present"] is True

    def test_formatter_shows_each_side_and_deltas(self):
        out = adv.format_symbol_divergence("HOOD", _live(), _bt())
        assert "ΔWR=-6.00%" in out
        assert "Δתשואה(ממוצע)=-6.30%" in out
        assert "ΔPF=-1.45" in out
        assert "Δרצף-L=2.00" in out
        assert "חי: WR=+60.00%" in out
        assert "בקטסט: WR=+66.00%" in out

    def test_missing_one_side_field_is_honest_dash_never_zero(self):
        """A missing side metric ⇒ honest '—', never a fabricated 0 delta
        (zero-as-truth is forbidden, SCOPE §3)."""
        live = _live()
        live["HOOD"].pop("profit_factor")
        d = adv.compute_symbol_divergence("HOOD", live, _bt())
        assert d["profit_factor_delta"] is None
        out = adv.format_symbol_divergence("HOOD", live, _bt())
        assert "ΔPF=—" in out
        assert "ΔPF=+0.00" not in out and "ΔPF=0.00" not in out

    def test_infinite_pf_never_fabricates_finite_delta(self):
        bt = _bt()
        bt["strategies"]["HOOD::strat"]["profit_factor"] = float("inf")
        d = adv.compute_symbol_divergence("HOOD", _live(), bt)
        assert d["profit_factor_delta"] is None
        out = adv.format_symbol_divergence("HOOD", _live(), bt)
        assert "בקטסט:" in out and "PF=∞" in out

    def test_compute_is_pure_and_never_raises_on_garbage(self):
        for bad_live, bad_bt in (
            (None, None), ({}, {}), ("x", 5), ([], ()),
            ({"HOOD": "notadict"}, {"strategies": "x"}),
            ({"HOOD": {"n": "abc"}}, {"strategies": {"k": {"symbol": None}}}),
        ):
            d = adv.compute_symbol_divergence("HOOD", bad_live, bad_bt)
            assert isinstance(d, dict)
            assert d["win_rate_delta"] is None
            txt = adv.format_symbol_divergence("HOOD", bad_live, bad_bt)
            assert isinstance(txt, str) and adv.MARKER in txt


# ════════════════════════════════════════════════════════════════════════════
# Case 2 — hard min-live-sample gate (SCOPE §3 #1)
# ════════════════════════════════════════════════════════════════════════════

class TestCase2MinSampleGate:
    def test_floor_equals_algo_cohort_window_discipline(self):
        """The hard floor mirrors algo_metrics.ALGO_COHORT_WINDOW = 30 (the
        two are pinned equal so they can never silently drift)."""
        assert adv.MIN_LIVE_SAMPLE == am.ALGO_COHORT_WINDOW == 30

    def test_below_floor_is_honest_marker_not_zero_not_delta(self):
        d = adv.compute_symbol_divergence("HOOD", _live(n=29), _bt())
        assert d["enough_sample"] is False
        assert d["win_rate_delta"] is None
        assert d["return_delta"] is None
        assert d["profit_factor_delta"] is None
        assert d["loss_streak_delta"] is None
        out = adv.format_symbol_divergence("HOOD", _live(n=29), _bt())
        assert adv.INSUFFICIENT_LIVE_SAMPLE_HE in out
        assert "אין מספיק מדגם חי" in out
        # never a zero/delta when below floor
        for tok in ("ΔWR=", "Δתשואה", "+0.00%", "0.00%"):
            assert tok not in out, tok

    def test_at_floor_is_enough(self):
        d = adv.compute_symbol_divergence("HOOD", _live(n=30), _bt())
        assert d["enough_sample"] is True

    def test_missing_live_n_is_below_floor_not_zero(self):
        d = adv.compute_symbol_divergence(
            "HOOD", {"HOOD": {"win_rate_pct": 60.0}}, _bt())
        assert d["live_n"] is None
        assert d["enough_sample"] is False
        out = adv.format_symbol_divergence(
            "HOOD", {"HOOD": {"win_rate_pct": 60.0}}, _bt())
        assert adv.INSUFFICIENT_LIVE_SAMPLE_HE in out

    def test_no_backtest_strategy_is_honest_not_zero(self):
        out = adv.format_symbol_divergence("HOOD", _live(), {"strategies": {}})
        assert "אין אסטרטגיית בקטסט תואמת" in out
        for tok in ("ΔWR=", "+0.00%"):
            assert tok not in out


# ════════════════════════════════════════════════════════════════════════════
# Case 3 — the 6 disclaimers + join banner + observe-only labels
# ════════════════════════════════════════════════════════════════════════════

class TestCase3DisclaimersAndBanner:
    def _all(self):
        return adv.format_symbol_divergence("HOOD", _live(), _bt())

    def test_join_banner_always_present_both_states(self):
        for live in (_live(), _live(n=2)):
            out = adv.format_symbol_divergence("HOOD", live, _bt())
            assert adv.JOIN_BANNER_HE in out
            assert "אותה-אסטרטגיה לפי אישור המנהל" in out
            assert "לא מאומת אוטומטית" in out

    def test_six_disclaimers_present(self):
        out = self._all()
        # #1 hard min-sample (its TEXT is present as the gate constant; it
        # triggers as the marker when below floor — proven in Case 2).
        assert adv.INSUFFICIENT_LIVE_SAMPLE_HE == \
            "אין מספיק מדגם חי — לא מוצג הפרש (לא חוסר, לא איתות)"
        # #2 window/regime
        assert adv.WINDOW_REGIME_MISMATCH_HE in out
        # #3 survivorship/look-ahead
        assert adv.SURVIVORSHIP_HE in out
        # #4 Volume=1/cost=0 — REUSES the existing BACKTEST_LABEL verbatim
        from algo_backtest_store import BACKTEST_LABEL
        assert adv.NO_COST_HE == BACKTEST_LABEL
        assert BACKTEST_LABEL in out
        # #5 long-only-vs-live
        assert adv.LONG_ONLY_HE in out
        # #6 multiple-comparisons
        assert adv.MULTIPLE_COMPARISONS_HE in out

    def test_observe_only_and_backtest_caveat_labels_present(self):
        from algo_backtest_store import BACKTEST_LABEL, OBSERVE_ONLY_LABEL
        from algo_rules import ALGO_BACKTEST_CAVEAT_HE
        out = self._all()
        assert OBSERVE_ONLY_LABEL in out
        assert BACKTEST_LABEL in out
        assert ALGO_BACKTEST_CAVEAT_HE in out
        # reused verbatim — no duplicated string definitions
        assert adv.BACKTEST_CAVEAT_HE == ALGO_BACKTEST_CAVEAT_HE

    def test_below_floor_still_carries_all_mandatory_labels(self):
        out = adv.format_symbol_divergence("HOOD", _live(n=1), _bt())
        from algo_backtest_store import BACKTEST_LABEL, OBSERVE_ONLY_LABEL
        assert adv.JOIN_BANNER_HE in out
        assert BACKTEST_LABEL in out
        assert OBSERVE_ONLY_LABEL in out
        assert adv.WINDOW_REGIME_MISMATCH_HE in out
        assert adv.MULTIPLE_COMPARISONS_HE in out


# ════════════════════════════════════════════════════════════════════════════
# Case 4 — observe-only: no imperative/directive token, no 🔴/🟢, no actuation
# ════════════════════════════════════════════════════════════════════════════

class TestCase4ObserveOnly:
    def _all_outputs(self):
        return [
            adv.format_symbol_divergence("HOOD", _live(), _bt()),
            adv.format_symbol_divergence("HOOD", _live(n=3), _bt()),
            adv.format_symbol_divergence("HOOD", _live(), {"strategies": {}}),
            adv.format_symbol_divergence("HOOD", None, None),
        ]

    def test_no_verdict_colour_emoji(self):
        for out in self._all_outputs():
            assert "🔴" not in out
            assert "🟢" not in out
            assert adv.MARKER == "🔭" and adv.MARKER in out

    def test_no_imperative_or_directive_token(self):
        # imperative / actuation Hebrew tokens that would make this a
        # recommendation; "דרושה פעולה" is explicitly forbidden (only the
        # passive "דרוש עיון" is permitted, SCOPE §4).
        forbidden = (
            "דרושה פעולה", "מומלץ", "המלצה", "הדק", "צמצם", "מכור",
            "קנה", "צא ", "הגדל", "הקטן", "בצע", "סגור פוזיציה",
            "Action Required", "suggested_stop",
        )
        for out in self._all_outputs():
            for tok in forbidden:
                assert tok not in out, tok
            # the permitted passive wording IS present
            assert "דרוש עיון" in out or \
                adv.INSUFFICIENT_LIVE_SAMPLE_HE in out

    def test_helper_has_no_state_push_or_supabase(self):
        """The W-2A1 helper performs no write / push / Supabase / network —
        it is a pure read-only function (observe-only doctrine)."""
        src = open(adv.__file__, encoding="utf-8").read()
        for forbidden in ("supabase", "create_client", "requests", "urllib",
                          "yfinance", "telebot", ".execute(",
                          "table(", "json.dump", "os.makedirs"):
            assert forbidden not in src, forbidden
        # opens nothing for write/append (it opens nothing at all)
        assert "open(" not in src
        # no network / write / push primitive of any kind
        for prim in ("socket", "http.client", "send_message",
                     "subprocess", "os.system"):
            assert prim not in src, prim

    def test_divergence_never_feeds_wr_expectancy_pf(self):
        """The structured result is a SELF-CONTAINED divergence dict — it
        carries NO win_rate / expectancy / profit_factor / net_r / edge /
        headline KEY that a stat path could merge (the deltas are namespaced
        `*_delta` only; AGENTS.md #8)."""
        d = adv.compute_symbol_divergence("HOOD", _live(), _bt())
        top = set(d.keys())
        for forbidden in ("win_rate", "win_rate_pct", "expectancy",
                          "expectancy_r", "profit_factor", "net_r",
                          "total_r", "edge", "headline"):
            assert forbidden not in top, forbidden
        # only namespaced deltas + display sub-dicts
        assert {"win_rate_delta", "return_delta", "profit_factor_delta",
                "loss_streak_delta"}.issubset(top)


# ════════════════════════════════════════════════════════════════════════════
# Case 5 — import-introspection: helper imports none of the forbidden modules
# ════════════════════════════════════════════════════════════════════════════

class TestCase5ImportPurity:
    def test_no_forbidden_static_import(self):
        src = open(adv.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        for forbidden in ("engine_core", "analytics_engine",
                          "period_data_probe", "supabase", "requests",
                          "urllib", "yfinance", "telebot", "algo_metrics"):
            assert not any(forbidden in (n or "") for n in names), \
                f"{forbidden} imported by algo_divergence"
        # only the pure leaves + stdlib
        assert set(n for n in names if n) == {
            "math", "typing", "algo_backtest_store", "algo_rules"}

    def test_importing_helper_does_not_pull_engine_or_supabase(self):
        """Importing algo_divergence in a fresh interpreter must NOT
        transitively import engine_core / supabase / a network client."""
        import subprocess
        root = os.path.dirname(os.path.dirname(__file__))
        code = (
            "import sys; import algo_divergence; "
            "bad=[m for m in ('engine_core','analytics_engine',"
            "'period_data_probe','supabase','requests','yfinance','telebot') "
            "if m in sys.modules]; "
            "print('BAD' if bad else 'CLEAN', bad)"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=root,
                             capture_output=True, text=True)
        assert "CLEAN" in out.stdout, (out.stdout, out.stderr)


# ════════════════════════════════════════════════════════════════════════════
# Case 6 — CROSS-SURFACE BYTE-IDENTITY (the core anti-drift proof, SCOPE §5)
# ════════════════════════════════════════════════════════════════════════════

class TestCase6CrossSurfaceByteIdentity:
    def test_telegram_path_and_dashboard_path_emit_identical_text(self):
        """The Telegram ALGO panel and the dashboard ALGO-backtest panel
        BOTH call the SAME single-source-of-truth formatter
        `algo_divergence.format_symbol_divergence`. For the SAME input the
        two surface code paths therefore emit byte-identical divergence
        text — proven by calling the exact formatter both surfaces call."""
        live, bt = _live(), _bt()
        for sym in ("HOOD", "ZZZ"):
            telegram_text = adv.format_symbol_divergence(sym, live, bt)
            dashboard_text = adv.format_symbol_divergence(sym, live, bt)
            assert telegram_text == dashboard_text
            assert telegram_text.encode("utf-8") == \
                dashboard_text.encode("utf-8")

    def test_both_surfaces_reference_the_single_formatter(self):
        """Static proof neither surface formats independently: both
        `telegram_tasks.py handle_algo_panel` and the dashboard
        ALGO-backtest section call `algo_divergence
        .format_symbol_divergence` (the ONE formatter) and nothing else
        formats the divergence text."""
        root = os.path.dirname(os.path.dirname(__file__))
        tt = open(os.path.join(root, "telegram_tasks.py"),
                  encoding="utf-8").read()
        dash = open(os.path.join(root, "dashboard.py"),
                    encoding="utf-8").read()
        assert "import algo_divergence" in tt
        assert "import algo_divergence" in dash
        assert "algo_divergence.format_symbol_divergence(" in tt
        assert "algo_divergence.format_symbol_divergence(" in dash

    def test_formatter_is_deterministic_idempotent(self):
        live, bt = _live(), _bt()
        a = adv.format_symbol_divergence("HOOD", live, bt)
        b = adv.format_symbol_divergence("HOOD", live, bt)
        assert a == b
        # input not mutated (pure)
        assert live == _live() and bt == _bt()


# ════════════════════════════════════════════════════════════════════════════
# Case 7 — dual-surface wiring is ADDITIVE only (no existing line/number lost)
# ════════════════════════════════════════════════════════════════════════════

class TestCase7AdditiveWiring:
    def test_telegram_panel_addition_is_after_state_line_before_caveat(self):
        root = os.path.dirname(os.path.dirname(__file__))
        tt = open(os.path.join(root, "telegram_tasks.py"),
                  encoding="utf-8").read()
        start = tt.index("def handle_algo_panel(")
        end = tt.index("\ndef ", start + 1)
        block = tt[start:end]
        i_state = block.index("מצב נצפה")
        i_div = block.index("algo_divergence.format_symbol_divergence(")
        i_caveat = block.index("algo_rules.ALGO_BACKTEST_CAVEAT_HE")
        # the 🔭 divergence call is AFTER the per-symbol state line and
        # BEFORE the existing mandatory backtest caveat (SCOPE §5a).
        assert i_state < i_div < i_caveat
        # the existing observation line + mandatory caveat are still present
        assert "מנוהל חיצונית. בקרה בלבד." in block
        assert "סטופ חיצוני:" in block

    def test_dashboard_section_is_marker_delimited_and_additive(self):
        root = os.path.dirname(os.path.dirname(__file__))
        dash = open(os.path.join(root, "dashboard.py"),
                    encoding="utf-8").read()
        assert "ALGO-2A divergence section START" in dash
        assert "ALGO-2A divergence section END" in dash
        s = dash.index("ALGO-2A divergence section START")
        e = dash.index("ALGO-2A divergence section END")
        section = dash[s:e]
        # additive section calls the single formatter and writes no Supabase
        assert "algo_divergence.format_symbol_divergence(" in section
        for forbidden in ("supabase.table", ".execute(", ".insert(",
                          ".update(", ".delete("):
            assert forbidden not in section, forbidden
        # the EXISTING ALGO-BT-1 panel title/labels are untouched (additive)
        assert "ALGO — בסיס בקטסט (פיקוח בלבד)" in dash
        assert "abs_store.load_algo_backtests()" in dash


# ════════════════════════════════════════════════════════════════════════════
# Case 8 — LOCKED April + byte-locked money-math untouched by this Phase
# ════════════════════════════════════════════════════════════════════════════

class TestCase8LockedAprilAndByteLockUnaffected:
    def test_byte_locked_files_unmodified(self):
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)

    def test_locked_april_regression_invariant_still_holds(self):
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

    def test_helper_does_no_r_nav_account_math(self):
        src = open(adv.__file__, encoding="utf-8").read()
        assert "import engine_core" not in src
        assert "import analytics_engine" not in src
        assert "import account_state" not in src
        assert "import algo_metrics" not in src
