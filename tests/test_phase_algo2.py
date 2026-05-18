"""Phase ALGO-2 acceptance suite — T-B1 + T-C1 + T-C2 (ONE coordinated pass).

Authoritative spec: docs/teams/PHASE_ALGO2_SCOPE.md (governs).
Confirmed defects: docs/teams/ALGO_INVESTIGATION_3.md (D1 @ adaptive_risk_engine
:459-460; D2 @ the un-gated heat-only risk-raise + _window_heat_score n==0→50.0).

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). They pin:

  T-B1  empty / all-ALGO disc window ⇒ NO ALGO in the heat base + an explicit
        INSUFFICIENT-DATA state; non-empty disc window ⇒ byte-identical to the
        pre-Phase behavior (the live normal path).
  T-C1  the founder/Mark 4-gate on the risk-RAISE path ONLY: each gate failing
        ⇒ no "up" (parametrised); all-pass + heat≥60 ⇒ "up" preserved; the
        smallest-N-forces-up (N=3 all-win) is now BLOCKED; the cut / "down" /
        "hold" / RISK_LADDER / update_risk_pct paths are byte-identical
        (protection never weakened — strictly risk-narrowing).
  T-C2  the SEPARATE longer rolling manual stat-base feeds S9/M21/L50 + the
        4-gate; the report-period fetch & every report KPI + LOCKED April stay
        byte-identical; the sample line honestly states the true base + N.
"""
import importlib
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import adaptive_risk_engine as are
import engine_core as ec


# ── fixtures ────────────────────────────────────────────────────────────────

def _disc(n, *, win=True, day0=200, bucket="VCP_MANUAL", risk=100.0, pnl=None):
    """Stat-countable MANUAL closed campaigns, newest-first."""
    out = []
    for i in range(n):
        out.append({
            "campaign_id": f"d{i}", "symbol": "AAPL", "setup_type": "VCP",
            "is_win": win,
            "close_date": datetime(2025, 1, 1) + timedelta(days=day0 - i),
            "total_pnl_usd": (pnl if pnl is not None else (300.0 if win else -50.0)),
            "original_campaign_risk": risk,
            "stat_bucket": bucket,
        })
    return out


def _algo(n, *, win=True, day0=200):
    """ALGO_OBSERVED closed campaigns (NEVER stat-countable)."""
    out = []
    for i in range(n):
        out.append({
            "campaign_id": f"a{i}", "symbol": "HOOD", "setup_type": "ALGO",
            "is_win": win,
            "close_date": datetime(2025, 1, 1) + timedelta(days=day0 - i),
            "total_pnl_usd": 500.0 if win else -200.0,
            "original_campaign_risk": 0.0,
            "stat_bucket": ec.STAT_BUCKET_ALGO,
        })
    return out


_GREEN_GATE = {"recon_band": "Balanced", "drawdown_active": False}


# ════════════════════════════════════════════════════════════════════════════
# T-B1 — D1 fix: the empty cold-start fallback must NEVER admit ALGO
# ════════════════════════════════════════════════════════════════════════════

class TestTB1ColdStartNoAlgoContamination:
    def test_all_algo_window_yields_insufficient_state_not_algo_heat(self):
        """Zero stat-countable manual + only ALGO closed ⇒ the engine enters
        an explicit INSUFFICIENT-DATA state; ALGO is NOT fed into S9/M21/L50;
        and it does NOT raise risk (the D1 contamination is closed)."""
        camps = _algo(10, win=True)  # all winners — would have driven "up"
        r = are.compute_adaptive_risk(camps, 0.60, 100_000)
        assert r["ok"] is True
        assert r["insufficient_manual_sample"] is True
        # No ALGO leaked into the disc windows.
        assert r["s9_stats"]["n"] == 0
        assert r["m21_stats"]["n"] == 0
        assert r["l50_stats"]["n"] == 0
        # An all-ALGO winning streak must NOT recommend raising discretionary risk.
        assert r["direction"] != "up"
        assert r["recommended_risk_pct"] <= 0.60

    def test_mixed_window_uses_only_manual_for_heat(self):
        """When manual campaigns exist alongside ALGO, only manual feeds the
        windows and the insufficient flag is False."""
        camps = _disc(6, win=True) + _algo(6, win=False)
        r = are.compute_adaptive_risk(camps, 0.60, 100_000)
        assert r["insufficient_manual_sample"] is False
        assert r["l50_stats"]["n"] == 6  # only the 6 manual

    def test_non_empty_disc_is_byte_identical_to_baseline(self):
        """The live normal path (non-empty disc) is provably byte-identical:
        a frozen copy of the PRE-Phase engine produces the SAME result dict
        on the same input (the additive Phase keys are stripped before the
        equality so the proof is exact)."""
        baseline = _frozen_baseline_compute()
        camps = _disc(8, win=True) + _disc(2, win=False, day0=190)
        before = baseline(camps, 0.50, 10_000)
        after = are.compute_adaptive_risk(camps, 0.50, 10_000)
        _assert_core_identical(before, after)

    @pytest.mark.parametrize("wins,losses", [(8, 2), (5, 5), (1, 9), (9, 1)])
    def test_non_empty_disc_byte_identical_matrix(self, wins, losses):
        baseline = _frozen_baseline_compute()
        camps = _disc(wins, win=True) + _disc(losses, win=False, day0=150)
        _assert_core_identical(
            baseline(camps, 0.85, 50_000),
            are.compute_adaptive_risk(camps, 0.85, 50_000),
        )


# ════════════════════════════════════════════════════════════════════════════
# T-C1 — D2 fix: the founder/Mark 4-gate (risk-RAISE path ONLY)
# ════════════════════════════════════════════════════════════════════════════

class TestTC1FourGateRiskRaise:
    def test_window_heat_score_n0_signal_opt_in_only(self):
        """The n==0 → 50.0 pretend-neutral is byte-identical by default; the
        explicit INSUFFICIENT-DATA sentinel is OPT-IN (D2 fix)."""
        empty = {"n": 0, "wr": 0.0, "payoff": 0.0, "pf": 0.0,
                 "loss_streak": 0, "win_streak": 0}
        assert are._window_heat_score(empty) == 50.0  # byte-identical default
        assert (are._window_heat_score(empty, insufficient_signal=True)
                == are.HEAT_INSUFFICIENT_DATA)

    def test_smallest_n_all_win_now_blocked(self):
        """Investigation #3: N=3 all-win mechanically forced direction='up'
        (heat=100, no sample gate). With the 4-gate it is BLOCKED."""
        camps = _disc(3, win=True)
        ungated = are.compute_adaptive_risk(camps, 0.40, 10_000)
        assert ungated["direction"] == "up"  # the as-built D2 defect (unchanged default)
        gated = are.compute_adaptive_risk(camps, 0.40, 10_000,
                                          risk_raise_gate=_GREEN_GATE)
        assert gated["direction"] == "hold"          # clamped
        assert gated["risk_raise_gate"]["allow_raise"] is False
        assert "G2_sample" in gated["risk_raise_gate"]["failed"]
        assert gated["recommended_risk_pct"] == 0.40  # no raise

    def test_all_pass_plus_heat_ge_60_still_raises(self):
        """≥20 manual, clean recon, expectancy ≥0.30R, no drawdown, heat≥60
        ⇒ "up" is PRESERVED (the gate is byte-identical when all green)."""
        camps = _disc(25, win=True)  # 25 manual winners, +3R each
        r = are.compute_adaptive_risk(camps, 0.40, 10_000,
                                      risk_raise_gate=_GREEN_GATE)
        assert r["heat_score"] >= 60
        assert r["risk_raise_gate"]["allow_raise"] is True
        assert r["direction"] == "up"
        assert r["recommended_risk_pct"] > 0.40

    @pytest.mark.parametrize("ctx,failed_id,desc", [
        ({"recon_band": "Critical Data Gap", "drawdown_active": False},
         "G1_recon", "critical broker-recon gap"),
        ({"recon_band": "פער נתונים קריטי", "drawdown_active": False},
         "G1_recon", "critical recon (hebrew band)"),
        ({"recon_band": "Balanced", "drawdown_active": True},
         "G4_drawdown", "active drawdown cut"),
    ])
    def test_each_gate_fail_blocks_up(self, ctx, failed_id, desc):
        """Each gate, failing in isolation on an otherwise-strong (≥20,
        +EV, heat≥60) base ⇒ no "up"."""
        camps = _disc(25, win=True)
        r = are.compute_adaptive_risk(camps, 0.40, 10_000, risk_raise_gate=ctx)
        assert r["direction"] != "up", desc
        assert failed_id in r["risk_raise_gate"]["failed"], desc
        assert r["risk_raise_gate"]["reason"]  # honest Hebrew reason present

    def test_gate2_sample_floor_blocks_below_20(self):
        """19 manual winners (<20 doctrine floor) ⇒ G2 fails ⇒ no raise;
        20 ⇒ G2 passes."""
        below = are.compute_adaptive_risk(_disc(19, win=True), 0.40, 10_000,
                                          risk_raise_gate=_GREEN_GATE)
        assert below["direction"] == "hold"
        assert "G2_sample" in below["risk_raise_gate"]["failed"]
        at = are.compute_adaptive_risk(_disc(20, win=True), 0.40, 10_000,
                                       risk_raise_gate=_GREEN_GATE)
        assert "G2_sample" not in at["risk_raise_gate"]["failed"]

    def test_gate3_expectancy_floor_blocks_low_ev(self):
        """≥20 manual but expectancy < 0.30R ⇒ G3 fails ⇒ no raise.
        Tiny +$ on a large per-campaign risk ⇒ ~0.01R expectancy."""
        camps = _disc(25, win=True, risk=1000.0, pnl=10.0)  # 0.01R each
        r = are.compute_adaptive_risk(camps, 0.40, 10_000,
                                      risk_raise_gate=_GREEN_GATE)
        assert "G3_expectancy" in r["risk_raise_gate"]["failed"]
        assert r["direction"] != "up"

    def test_gate3_expectancy_none_when_no_clean_risk_blocks(self):
        """No campaign carries a positive original risk ⇒ expectancy cannot
        be honestly computed (None) ⇒ G3 fails (clean truth before
        aggressiveness)."""
        camps = _disc(25, win=True, risk=0.0)
        r = are.compute_adaptive_risk(camps, 0.40, 10_000,
                                      risk_raise_gate=_GREEN_GATE)
        assert "G3_expectancy" in r["risk_raise_gate"]["failed"]
        assert r["direction"] != "up"

    def test_insufficient_state_fails_gate2(self):
        """T-B1 ⇄ T-C1 wiring: an all-ALGO insufficient window with the gate
        on ⇒ G2 fails on the insufficient flag, never raises."""
        r = are.compute_adaptive_risk(_algo(12, win=True), 0.40, 10_000,
                                      risk_raise_gate=_GREEN_GATE)
        assert r["insufficient_manual_sample"] is True
        assert r["direction"] != "up"


class TestTC1ProtectionNeverWeakened:
    """The cut / 'down' / 'hold' / ladder / update_risk_pct paths are
    byte-identical with the gate on AND off — protection is never weakened;
    the gate is strictly risk-NARROWING (only ever blocks a raise)."""

    def test_down_fast_identical_with_and_without_gate(self):
        camps = _disc(3, win=False)  # 3 consecutive losers ⇒ down_fast
        off = are.compute_adaptive_risk(camps, 1.0, 10_000)
        on = are.compute_adaptive_risk(camps, 1.0, 10_000,
                                       risk_raise_gate=_GREEN_GATE)
        assert off["direction"] == "down_fast"
        _assert_core_identical(off, on, ignore=("risk_raise_gate",))

    def test_drawdown_auto_cut_identical_with_and_without_gate(self):
        # heavy realized loss within the last 30d ⇒ drawdown auto-cut fires.
        # (drawdown_auto_cut_recommendation filters close_date to now-30d)
        now = datetime.now()
        camps = [{
            "campaign_id": f"dd{i}", "symbol": "AAPL", "setup_type": "VCP",
            "is_win": False, "close_date": now - timedelta(days=i + 1),
            "total_pnl_usd": -2000.0, "original_campaign_risk": 100.0,
            "stat_bucket": "VCP_MANUAL",
        } for i in range(6)]
        off = are.compute_adaptive_risk(camps, 1.50, 10_000)
        on = are.compute_adaptive_risk(camps, 1.50, 10_000,
                                       risk_raise_gate=_GREEN_GATE)
        assert off.get("override") == "drawdown_auto_cut"
        assert on.get("override") == "drawdown_auto_cut"
        _assert_core_identical(off, on, ignore=("risk_raise_gate",))

    def test_hold_identical_with_and_without_gate(self):
        camps = _disc(5, win=True) + _disc(5, win=False, day0=150)
        off = are.compute_adaptive_risk(camps, 0.60, 10_000)
        on = are.compute_adaptive_risk(camps, 0.60, 10_000,
                                       risk_raise_gate=_GREEN_GATE)
        if off["direction"] == "hold":
            _assert_core_identical(off, on, ignore=("risk_raise_gate",))

    def test_ladder_values_and_cut_constants_untouched(self):
        assert are.RISK_LADDER == [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]
        assert are.DRAWDOWN_TRIGGER_PCT == -8.0
        assert are.DRAWDOWN_CUT_TO_PCT == 0.40

    def test_evaluate_gate_is_pure_and_narrowing(self):
        """The evaluator NEVER returns anything that could ENABLE a raise that
        heat blocked or weaken a cut — it only ever yields allow_raise bool."""
        res = are.evaluate_risk_raise_gate(
            manual_sample_n=5, expectancy_r=0.10, recon_band="Critical Data Gap",
            drawdown_active=True, loss_streak=3)
        assert res["allow_raise"] is False
        assert set(res["failed"]) == {"G1_recon", "G2_sample",
                                      "G3_expectancy", "G4_drawdown"}
        ok = are.evaluate_risk_raise_gate(
            manual_sample_n=30, expectancy_r=0.45, recon_band="Balanced",
            drawdown_active=False, loss_streak=0)
        assert ok["allow_raise"] is True and ok["failed"] == []


# ════════════════════════════════════════════════════════════════════════════
# T-C2 — separate longer rolling manual stat-base (report numbers untouched)
# ════════════════════════════════════════════════════════════════════════════

class TestTC2SeparateStatBase:
    def test_stat_base_draws_the_longer_manual_set(self):
        """A short report-window disc set (<20) that would FAIL Gate-2 is
        rescued by the SEPARATE longer base (≥20 manual) ⇒ S9/M21/L50 + the
        4-gate compute off the longer base."""
        report_window = _disc(6, win=True, day0=60)         # the 8-week slab
        longer = _disc(30, win=True, day0=400)              # the rolling base
        r = are.compute_adaptive_risk(
            report_window, 0.40, 10_000,
            stat_base_campaigns=longer, risk_raise_gate=_GREEN_GATE)
        assert r["stat_base"] == "longer_manual_rolling"
        assert r["l50_stats"]["n"] == 30  # off the longer base, not the 6-slab
        assert r["risk_raise_gate"]["allow_raise"] is True

    def test_stat_base_default_is_report_window_byte_identical(self):
        """No stat_base_campaigns ⇒ provenance is the report window and the
        result is byte-identical to the baseline engine."""
        camps = _disc(9, win=True) + _disc(2, win=False, day0=150)
        r = are.compute_adaptive_risk(camps, 0.50, 10_000)
        assert r["stat_base"] == "report_window"
        baseline = _frozen_baseline_compute()
        _assert_core_identical(baseline(camps, 0.50, 10_000), r)

    def test_all_algo_longer_base_still_insufficient(self):
        """A longer base that is all-ALGO does NOT contaminate (T-B1 holds
        even on the separate base)."""
        r = are.compute_adaptive_risk(
            _disc(4, win=True), 0.40, 10_000,
            stat_base_campaigns=_algo(40, win=True))
        # the all-ALGO longer base has no disc ⇒ falls back to report window
        assert r["stat_base"] == "report_window"
        assert r["l50_stats"]["n"] == 4

    def test_report_period_fetch_untouched_weeks8(self):
        """DEC-20260516-020: _fetch_trades_df still uses an 8-week lookback;
        the separate stat-base read is a DISTINCT function that does not
        touch it."""
        import report_scheduler as rs
        src = importlib.util.find_spec("report_scheduler").origin
        with open(src, "r", encoding="utf-8") as f:
            body = f.read()
        # the report fetch keeps its weeks=8 lookback verbatim
        assert "lookback = period_start - timedelta(weeks=8)" in body
        # the separate stat-base read is a distinct, read-only function
        assert hasattr(rs, "_fetch_stat_base_df")
        assert hasattr(rs, "_compute_risk_rec")

    def test_stat_base_repo_read_is_select_only(self):
        """The T-C2 repository read performs NO Supabase mutation (pure
        SELECT) — recorded via a stub client."""
        import supabase_repository as repo

        class _Q:
            def __init__(s): s.calls = []
            def select(s, *a, **k): s.calls.append("select"); return s
            def gte(s, *a, **k): s.calls.append("gte"); return s
            def order(s, *a, **k): s.calls.append("order"); return s
            def execute(s):
                s.calls.append("execute")
                return type("R", (), {"data": []})()

        class _SB:
            def __init__(s): s.q = _Q()
            def table(s, name):
                assert name == "trades"
                return s.q

        sb = _SB()
        repo.get_trades_since(sb, "2020-01-01")
        # only read verbs were issued — no insert/update/delete/upsert
        forbidden = {"insert", "update", "delete", "upsert"}
        assert not (set(sb.q.calls) & forbidden)
        assert "select" in sb.q.calls and "execute" in sb.q.calls

    def test_sample_line_honestly_states_true_base_and_n(self):
        """The sample-honesty line names the SEPARATE longer manual base when
        it actually fed the windows (T-A1 clarity folded in), and is silent
        about it on the legacy report-window path (byte-identical)."""
        import telegram_formatters as tf
        long_rec = {
            "ok": True, "heat_color": "🟠", "heat_label": "חם",
            "heat_score": 62.0, "s9_score": 70.0, "m21_score": 60.0,
            "l50_score": 55.0, "recent_10_wr": 60.0, "all_50_wr": 50.0,
            "s9_stats": {"n": 9}, "m21_stats": {"n": 21}, "l50_stats": {"n": 30},
            "win_streak": 0, "loss_streak": 0, "heat_factors": [],
            "current_risk_pct": 0.60, "recommended_risk_pct": 0.60,
            "current_risk_usd": 45.0, "recommended_risk_usd": 45.0,
            "direction": "hold", "step_type": "ללא שינוי",
            "stat_base": "longer_manual_rolling",
        }
        out = tf.fmt_adaptive_risk_block(long_rec)
        assert "מדגם נוכחי: 30/50" in out
        assert "היסטוריית מסחר ידנית מתגלגלת" in out
        # legacy report-window path: NO base clause (byte-identical)
        rw = dict(long_rec); rw["stat_base"] = "report_window"
        out2 = tf.fmt_adaptive_risk_block(rw)
        assert "היסטוריית מסחר ידנית מתגלגלת" not in out2
        assert "מדגם נוכחי: 30/50" in out2  # honest N still shown


class TestTC2ReportKPIsAndLockedAprilByteIdentical:
    def test_locked_april_regression_still_passes_untouched(self):
        """The LOCKED April ground truth (8 / +$180.49 / WR .375 / PF 2.6262
        / excl 2) is produced by analytics_engine, NOT the adaptive risk
        engine — Phase ALGO-2 does not touch it. Re-run its exact invariant
        through the LOCKED fixture's own df + the unchanged analytics API."""
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

    def test_byte_locked_files_unmodified(self):
        """engine_core / analytics_engine / period_data_probe / LOCKED April
        fixture are byte-identical to their committed baselines (Phase ALGO-2
        touched NONE of them)."""
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)


# ── byte-identical proof harness ────────────────────────────────────────────

# The PRE-Phase additive keys that Phase ALGO-2 introduces. Stripping them
# makes the "non-empty disc ⇒ byte-identical" proof EXACT against a frozen
# copy of the engine logic (no Phase key changes any pre-existing value).
_PHASE_KEYS = ("insufficient_manual_sample", "stat_base", "risk_raise_gate")


def _strip(d, ignore=()):
    out = {k: v for k, v in d.items()
           if k not in _PHASE_KEYS and k not in ignore}
    out.pop("generated_at", None)  # timestamp — non-deterministic in both
    return out


def _assert_core_identical(before, after, ignore=()):
    """Every pre-existing key/value is identical; only the additive Phase
    keys may differ. heat_factors may carry an extra gate reason ONLY when a
    raise was blocked — excluded from the strict compare in that case via the
    ignore arg passed by the protection tests (which assert direction parity
    separately)."""
    b, a = _strip(before, ignore), _strip(after, ignore)
    assert b == a, (
        "core result diverged (NOT byte-identical):\n"
        f"only-in-before={{k: b[k] for k in b if b.get(k) != a.get(k)}}\n"
        f"only-in-after={{k: a[k] for k in a if a.get(k) != b.get(k)}}")


def _frozen_baseline_compute():
    """A frozen reimplementation of the PRE-Phase compute_adaptive_risk core
    (the exact pre-T-B1 disc/fallback + heat + direction + ladder + drawdown
    math) used purely as the byte-identical ORACLE. It deliberately keeps the
    OLD unsafe `disc_camps = closed_campaigns[:50]` fallback so the proof
    shows the non-empty path is unchanged while ONLY the empty path differs.
    """
    def _baseline(closed_campaigns, current_risk_pct, nav):
        if len(closed_campaigns) < 3:
            return {"ok": False, "error": "not_enough_trades",
                    "message": f"רק {len(closed_campaigns)} קמפיינים סגורים — נדרשות לפחות 3 לניתוח"}

        def _is_disc(c):
            bucket = c.get("stat_bucket")
            if bucket:
                return ec.is_stat_countable(bucket)
            return c.get("setup_type", "").upper() != "ALGO"

        disc_camps = [c for c in closed_campaigns if _is_disc(c)]
        if not disc_camps:
            disc_camps = closed_campaigns[:50]  # OLD unsafe fallback (oracle)

        s9 = are._window_stats(disc_camps[:9])
        m21 = are._window_stats(disc_camps[:21])
        l50 = are._window_stats(disc_camps[:50])
        s9s = are._window_heat_score(s9)
        m21s = are._window_heat_score(m21)
        l50s = are._window_heat_score(l50)
        base_heat = s9s * 0.50 + m21s * 0.30 + l50s * 0.20
        heat = min(100.0, max(0.0, base_heat + 0.0))
        ls, ws = s9["loss_streak"], s9["win_streak"]
        if heat >= 60 and ls < 2:
            lbl, col, d = "חזק", "🔥", "up"
        elif heat < 40 or ls >= 3:
            lbl, col, d = "חלש", "❄️", "down_fast"
        else:
            lbl, col, d = "נייטרל", "➖", "hold"
        ci = are._closest_ladder_index(current_risk_pct)
        if d == "up":
            ni, st = min(ci + 1, len(are.RISK_LADDER) - 1), "העלאת סיכון הדרגתית"
        elif d == "down_fast":
            ni, st = max(ci - 2, 0), "צמצום סיכון מהיר"
        else:
            ni, st = ci, "שמירה על רמה קיימת"
        if ni == ci and d != "hold":
            d, st = "hold", "שמירה על רמה קיימת"
        rec_pct = are.RISK_LADDER[ni]
        res = {
            "ok": True, "error": None, "n_trades": len(disc_camps),
            "n_used_10": s9["n"], "n_used_50": l50["n"],
            "heat_score": round(heat, 1), "heat_label": lbl, "heat_color": col,
            "win_streak": ws, "loss_streak": ls,
            "recent_10_wr": round(s9["wr"] * 100, 1),
            "all_50_wr": round(l50["wr"] * 100, 1),
            "payoff_ratio": s9["payoff"], "open_r_bonus": 0.0,
            "current_risk_pct": current_risk_pct,
            "current_risk_usd": round(nav * current_risk_pct / 100, 0),
            "recommended_risk_pct": rec_pct,
            "recommended_risk_usd": round(nav * rec_pct / 100, 0),
            "direction": d, "step_type": st,
            "s9_score": round(s9s, 1), "m21_score": round(m21s, 1),
            "l50_score": round(l50s, 1),
            "s9_stats": s9, "m21_stats": m21, "l50_stats": l50,
            "disc_open_r": 0.0, "algo_open_r": 0.0,
            "heat_factors": are._build_heat_factors(s9, m21, 0.0),
            "what_to_improve": are._build_what_to_improve(
                heat, s9, d, s9_score=s9s),
        }
        dd = are.drawdown_auto_cut_recommendation(
            closed_campaigns, current_risk_pct, nav)
        if dd is not None:
            res["override"] = "drawdown_auto_cut"
            res["drawdown_pct"] = dd["drawdown_pct"]
            res["drawdown_pnl_usd"] = dd["pnl_30d_usd"]
            res["drawdown_n_trades"] = dd["n_trades"]
            res["drawdown_window_days"] = dd["window_days"]
            res["recommended_risk_pct"] = dd["force_cut_to_pct"]
            res["recommended_risk_usd"] = round(
                nav * dd["force_cut_to_pct"] / 100, 0)
            res["direction"] = "down_fast"
            res["step_type"] = "🚨 Drawdown auto-cut — קיצוץ מחויב"
            res["heat_factors"] = [f"⛔ {dd['reason']}"] + (
                res["heat_factors"] or [])
            res["what_to_improve"] = [
                f"Drawdown 30d: {dd['drawdown_pct']:.1f}% "
                f"(${dd['pnl_30d_usd']:.0f}) — "
                f"מתחת לסף -8% של NAV. הרצה עם "
                f"{dd['force_cut_to_pct']:.2f}% עד שהDD יחזור מעל -5%.",
            ] + (res["what_to_improve"] or [])
        return res

    return _baseline
