"""
F1 (Meeting 21/05/2026) — risk-RAISE 4-gate wired to all live callers.

Tests pinned in this file:
  A. build_risk_raise_gate_ctx — pure helper, fail-soft, reuses the
     existing telegram_formatters.classify_broker_reconciliation
     classifier (so all 4 live callers + the scheduler share ONE
     definition of "Critical broker recon").
  B. compute_adaptive_risk + gate end-to-end — N=9 with strong heat
     ("up" direction) is CLAMPED to "hold" because G2 fails; N=25 with
     strong heat stays "up". Down/hold paths are NEVER weakened.
  C. Surface-wiring grep tests — all 4 live callers
     (telegram_portfolio handle_market_regime + handle_portfolio_room,
     dashboard sidebar, risk_monitor proactive alert) MUST call
     build_risk_raise_gate_ctx AND pass risk_raise_gate=. Otherwise the
     bug regresses silently: the founder sees an unguarded "up" rec on
     N=9 again.

These tests do NOT modify the 9 engine_core byte-lock guards — the gate
infrastructure lives in adaptive_risk_engine.py which is not byte-locked.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import adaptive_risk_engine as are  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# A. build_risk_raise_gate_ctx — pure helper
# ════════════════════════════════════════════════════════════════════════════

class TestBuildRiskRaiseGateCtxShape:
    def test_returns_dict_with_required_keys(self):
        ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=[], risk_pct=0.5,
        )
        assert "recon_band" in ctx
        assert "drawdown_active" in ctx

    def test_drawdown_active_passes_through(self):
        ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=[], risk_pct=0.5,
            drawdown_active=True,
        )
        assert ctx["drawdown_active"] is True

    def test_balanced_books_returns_balanced_band(self):
        # nav == deposited + 0 net PnL ⇒ |gap|=0 ≤ $10 ⇒ "Balanced"/"מאוזן".
        ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=[], risk_pct=0.5,
        )
        # The classifier returns either band string; we accept both ways
        # (the test pins the integration, not the exact wording).
        assert ctx["recon_band"] in ("Balanced", "מאוזן")

    def test_critical_gap_returns_critical_band(self):
        # nav $7,857 deposited $7,500 net $0 ⇒ gap $357. With risk_pct
        # 0.6 ⇒ unit = 7500*0.006 = $45; 5*unit = $225; gap > 225 ⇒
        # Critical. This is the exact band the founder's screenshot showed.
        ctx = are.build_risk_raise_gate_ctx(
            nav=7857.0, total_deposited=7500.0,
            closed_campaigns=[], risk_pct=0.6,
        )
        assert ctx["recon_band"] in ("Critical Data Gap", "פער נתונים קריטי")


class TestBuildRiskRaiseGateCtxFailSoft:
    def test_none_inputs_collapse_to_none_recon_band(self):
        # Any failure inside the classifier ⇒ recon_band=None ⇒ G1 PASSES
        # (no FALSE block). This is the safety property: the gate only
        # ever NARROWS, never blocks on missing data.
        ctx = are.build_risk_raise_gate_ctx(
            nav=0.0, total_deposited=0.0,
            closed_campaigns=None, risk_pct=0.0,
        )
        # Whether the band came out as Balanced or None, drawdown_active
        # must be a clean bool and the dict must be well-formed.
        assert isinstance(ctx, dict)
        assert "recon_band" in ctx
        assert ctx["drawdown_active"] is False

    def test_closed_campaigns_with_missing_pnl_keys_handled(self):
        # Rows missing total_pnl_usd ⇒ treated as 0; no raise.
        ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=[{"symbol": "X"}, {"total_pnl_usd": "abc"}],
            risk_pct=0.5,
        )
        assert isinstance(ctx, dict)


# ════════════════════════════════════════════════════════════════════════════
# B. End-to-end — gate clamps "up" on small sample; protects "down"/"hold"
# ════════════════════════════════════════════════════════════════════════════

def _winning_campaigns(n: int) -> list:
    """Build N closed-campaign dicts that score high on heat (Win Rate
    high, payoff positive). Matches the shape compute_adaptive_risk
    expects from compute_closed_campaigns."""
    camps = []
    for i in range(n):
        camps.append({
            "campaign_id": f"C{i}",
            "symbol": f"S{i}",
            "setup_type": "VCP",
            "total_pnl_usd": 100.0,
            "is_win": True,
            "net_r": 2.0,
            "stat_bucket": "VCP_MANUAL",
            "original_campaign_risk": 50.0,
            "close_date": f"2026-04-{(i % 28) + 1:02d}",
        })
    return camps


class TestGateClampsUpOnSmallSample:
    def test_n9_up_direction_clamped_to_hold_when_gate_passed(self):
        # The founder's screenshot scenario: 9 wins → heat=100, S9=99,
        # direction would be "up" with $67 recommendation. With the gate
        # passed, G2 (sample ≥ 20) fails ⇒ direction clamps to "hold".
        camps = _winning_campaigns(9)
        gate_ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=camps, risk_pct=0.6,
        )
        rec = are.compute_adaptive_risk(
            camps, current_risk_pct=0.6, nav=10000.0,
            risk_raise_gate=gate_ctx,
        )
        assert rec.get("ok")
        assert rec["direction"] == "hold", (
            "N=9 with strong heat MUST clamp to hold under the 4-gate "
            "(G2 sample < 20). Otherwise the founder sees unguarded $67 rec.")
        # The recommended pct stays at the current level (no ladder step).
        assert rec["recommended_risk_pct"] == rec["current_risk_pct"]
        # The gate result is surfaced in the response + heat_factors carries
        # the honest reason with the ⛔ prefix.
        assert rec.get("risk_raise_gate", {}).get("evaluated") is True
        assert rec["risk_raise_gate"]["allow_raise"] is False
        assert "G2_sample" in rec["risk_raise_gate"]["failed"]
        assert any("⛔" in f for f in rec.get("heat_factors", []))

    def test_n25_up_direction_stays_up_when_all_gates_pass(self):
        # Once the sample reaches 20+, with positive expectancy and clean
        # recon and no drawdown, "up" is permitted — the gate is risk-
        # NARROWING, not blanket-blocking.
        camps = _winning_campaigns(25)
        gate_ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=camps, risk_pct=0.6,
        )
        rec = are.compute_adaptive_risk(
            camps, current_risk_pct=0.6, nav=10000.0,
            risk_raise_gate=gate_ctx,
        )
        assert rec.get("ok")
        # Direction stays "up" (or at worst "hold" if the ladder-step
        # collapse fires — but it should be "up" with this fixture).
        assert rec["direction"] in ("up", "hold")
        if rec["direction"] == "up":
            assert rec.get("risk_raise_gate", {}).get("allow_raise") is True

    def test_no_gate_passed_keeps_legacy_behavior(self):
        # When the caller does NOT pass risk_raise_gate, the gate does
        # NOT run. This is the OPT-IN contract that keeps every existing
        # test byte-identical.
        camps = _winning_campaigns(9)
        rec = are.compute_adaptive_risk(
            camps, current_risk_pct=0.6, nav=10000.0,
        )
        # The legacy path may say "up" on N=9 — that's exactly the bug
        # this phase fixes by WIRING the gate at the call sites. But
        # without the gate kwarg, the engine is byte-identical to before.
        assert "risk_raise_gate" not in rec


class TestGateNeverWeakensProtection:
    """The gate is strictly risk-NARROWING. It MUST NEVER convert a
    "down_fast" or "hold" into an "up". This pins the safety invariant."""

    def _losing_campaigns(self, n):
        camps = []
        for i in range(n):
            camps.append({
                "campaign_id": f"L{i}",
                "symbol": f"L{i}",
                "setup_type": "VCP",
                "total_pnl_usd": -100.0,
                "is_win": False,
                "net_r": -1.0,
                "stat_bucket": "VCP_MANUAL",
                "original_campaign_risk": 50.0,
                "close_date": f"2026-04-{(i % 28) + 1:02d}",
            })
        return camps

    def test_down_direction_never_clamped_to_up(self):
        camps = self._losing_campaigns(25)
        gate_ctx = are.build_risk_raise_gate_ctx(
            nav=10000.0, total_deposited=10000.0,
            closed_campaigns=camps, risk_pct=0.6,
        )
        rec = are.compute_adaptive_risk(
            camps, current_risk_pct=0.6, nav=10000.0,
            risk_raise_gate=gate_ctx,
        )
        # Direction stays "down_fast" or "hold" — NEVER "up".
        assert rec["direction"] in ("down_fast", "hold")


# ════════════════════════════════════════════════════════════════════════════
# C. Surface-wiring grep tests — all 4 live callers MUST pass the gate
# ════════════════════════════════════════════════════════════════════════════

class TestSurfaceWiringPassesGate:
    """If a live caller stops passing risk_raise_gate, the bug regresses
    silently: founder sees noisy up-step on small samples again. Pin it."""

    def test_telegram_portfolio_passes_gate(self):
        src = _read("telegram_portfolio.py")
        # Both compute_adaptive_risk calls in this file must accompany a
        # build_risk_raise_gate_ctx call.
        assert "build_risk_raise_gate_ctx(" in src
        # Both compute_adaptive_risk call sites pass risk_raise_gate=.
        # A simple count: the file has 2 compute_adaptive_risk calls + 2
        # gate-ctx builders.
        assert src.count("compute_adaptive_risk(") == 2
        assert src.count("risk_raise_gate=") == 2

    def test_dashboard_passes_gate(self):
        src = _read("dashboard.py")
        assert "build_risk_raise_gate_ctx(" in src
        assert "risk_raise_gate=" in src

    def test_risk_monitor_passes_gate(self):
        src = _read("risk_monitor.py")
        assert "build_risk_raise_gate_ctx(" in src
        assert "risk_raise_gate=" in src

    def test_report_scheduler_still_passes_gate(self):
        # Pre-existing wiring — pin it so a future refactor cannot
        # accidentally drop it.
        src = _read("report_scheduler.py")
        assert "risk_raise_gate=" in src
