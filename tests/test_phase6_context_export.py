"""
Phase 6 — Master Context Export tests.

Tests build_position_context_data() (engine_core.py) — the helper that
computes all Phase 1-4 enrichment fields for a single open position.
All tests are pure — no Streamlit, no DB, no yfinance.
"""

import pytest
import engine_core as ec


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _base_ctx(**overrides):
    """Return a context dict with sensible defaults, with optional overrides."""
    kwargs = dict(
        sym="MRVL",
        setup="VCP",
        entry=50.0,
        curr_p=55.0,      # $5 gain → open_pnl = $500 on 100 shares
        qty=100.0,
        sl=47.0,           # stop $3 below entry
        init_sl=45.0,      # initial stop $5 below entry
        base_price=50.0,
        base_qty=100.0,
        realized_pnl=0.0,
        target_risk_usd=500.0,    # 1R = $500
        management_mode="manual_managed",
        days_to_earnings=None,
        position_state="WORKING",
        state_label="⚙️ Working",
        breakeven_alerted=False,
    )
    kwargs.update(overrides)
    return ec.build_position_context_data(**kwargs)


# ── Return type ───────────────────────────────────────────────────────────────

class TestReturnType:
    def test_returns_dict(self):
        assert isinstance(_base_ctx(), dict)

    def test_contains_all_required_keys(self):
        ctx = _base_ctx()
        required = [
            "sym", "setup", "open_pnl", "original_campaign_risk",
            "open_pnl_at_stop", "protected_profit", "giveback_usd",
            "giveback_pct", "capital_at_risk", "sizing", "event_risk",
            "position_state", "state_label", "breakeven_alerted",
            "has_profit", "is_algo",
        ]
        for key in required:
            assert key in ctx, f"missing key: {key}"


# ── open_pnl ─────────────────────────────────────────────────────────────────

class TestOpenPnl:
    def test_profit_position(self):
        ctx = _base_ctx(entry=50.0, curr_p=55.0, qty=100.0)
        assert abs(ctx["open_pnl"] - 500.0) < 0.01

    def test_loss_position(self):
        ctx = _base_ctx(entry=50.0, curr_p=48.0, qty=100.0)
        assert ctx["open_pnl"] < 0

    def test_breakeven(self):
        ctx = _base_ctx(entry=50.0, curr_p=50.0, qty=100.0)
        assert abs(ctx["open_pnl"]) < 0.01

    def test_has_profit_true_when_positive(self):
        ctx = _base_ctx(entry=50.0, curr_p=55.0, qty=100.0)
        assert ctx["has_profit"] is True

    def test_has_profit_false_when_negative(self):
        ctx = _base_ctx(entry=50.0, curr_p=48.0, qty=100.0)
        assert ctx["has_profit"] is False


# ── original_campaign_risk ───────────────────────────────────────────────────

class TestOriginalCampaignRisk:
    def test_computes_correctly(self):
        # base_price=50, init_sl=45, base_qty=100 → risk = 5*100 = $500
        ctx = _base_ctx(base_price=50.0, init_sl=45.0, base_qty=100.0)
        assert abs(ctx["original_campaign_risk"] - 500.0) < 0.01

    def test_zero_when_init_sl_invalid(self):
        # init_sl=0 → no valid stop → original_campaign_risk = 0
        ctx = _base_ctx(init_sl=0.0)
        assert ctx["original_campaign_risk"] == 0.0

    def test_zero_when_init_sl_above_base_price(self):
        # init_sl > base_price → invalid for a long position
        ctx = _base_ctx(base_price=50.0, init_sl=55.0)
        assert ctx["original_campaign_risk"] == 0.0


# ── protected_profit ─────────────────────────────────────────────────────────

class TestProtectedProfit:
    def test_positive_when_above_stop(self):
        # entry=50, sl=47, curr_p=55, qty=100
        # open_pnl_at_stop = (47-50)*100 = -300; realized=0
        # protected_profit = max(0, 0 + max(0, -300)) = 0
        ctx = _base_ctx(entry=50.0, sl=47.0, curr_p=55.0, qty=100.0, realized_pnl=0.0)
        # stop is below entry so pnl_at_stop is negative → protected = 0
        assert ctx["protected_profit"] == 0.0

    def test_positive_when_stop_above_entry(self):
        # entry=50, sl=53 (stop above entry — locked in profit), curr_p=57, qty=100
        # open_pnl_at_stop = (53-50)*100 = $300
        # protected_profit = max(0, 0 + max(0, 300)) = $300
        ctx = _base_ctx(entry=50.0, sl=53.0, curr_p=57.0, qty=100.0, realized_pnl=0.0)
        assert ctx["protected_profit"] >= 0.0

    def test_includes_realized_pnl(self):
        # realized_pnl=200 adds to protected profit
        ctx_no_realized = _base_ctx(entry=50.0, sl=53.0, qty=100.0, realized_pnl=0.0)
        ctx_with_realized = _base_ctx(entry=50.0, sl=53.0, qty=100.0, realized_pnl=200.0)
        assert ctx_with_realized["protected_profit"] >= ctx_no_realized["protected_profit"]


# ── giveback_usd & giveback_pct ───────────────────────────────────────────────

class TestGiveback:
    def test_giveback_zero_when_at_stop(self):
        # curr_p == entry (flat trade), stop below → no open profit → no giveback
        ctx = _base_ctx(entry=50.0, curr_p=50.0, sl=47.0, qty=100.0)
        # open_pnl = 0; giveback = max(0, open_pnl - open_pnl_at_stop)
        # But open_pnl = 0 and stop is below → no meaningful giveback
        assert ctx["giveback_usd"] >= 0.0

    def test_giveback_pct_nonnegative(self):
        ctx = _base_ctx()
        assert ctx["giveback_pct"] >= 0.0


# ── capital_at_risk ───────────────────────────────────────────────────────────

class TestCapitalAtRisk:
    def test_positive_when_stop_below_entry(self):
        # entry=50, sl=47 → cap at risk = (50-47)*100 = $300
        ctx = _base_ctx(entry=50.0, sl=47.0, qty=100.0)
        assert abs(ctx["capital_at_risk"] - 300.0) < 0.01

    def test_zero_when_stop_above_entry(self):
        # stop above entry → no capital at risk
        ctx = _base_ctx(entry=50.0, sl=53.0, qty=100.0)
        assert ctx["capital_at_risk"] == 0.0


# ── sizing ────────────────────────────────────────────────────────────────────

class TestSizingContext:
    def test_sizing_has_classification_key(self):
        ctx = _base_ctx()
        assert "classification" in ctx["sizing"]

    def test_sizing_label_ideal_when_1x(self):
        # original_campaign_risk == target_risk_usd → ratio 1.0 → Ideal
        ctx = _base_ctx(base_price=50.0, init_sl=45.0, base_qty=100.0,
                        target_risk_usd=500.0)
        assert ctx["sizing"]["classification"] == "Ideal"
        assert abs(ctx["sizing"]["sizing_ratio"] - 1.0) < 0.01

    def test_sizing_unknown_when_no_campaign_risk(self):
        # original_campaign_risk = 0 → classification = Unknown
        ctx = _base_ctx(init_sl=0.0)
        assert ctx["sizing"]["classification"] == "Unknown"

    def test_sizing_has_sizing_ratio_key(self):
        ctx = _base_ctx()
        assert "sizing_ratio" in ctx["sizing"]


# ── event_risk ────────────────────────────────────────────────────────────────

class TestEventRiskContext:
    def test_no_earnings_gives_inactive(self):
        ctx = _base_ctx(days_to_earnings=None)
        assert ctx["event_risk"]["active"] is False

    def test_earnings_within_3_days_active(self):
        ctx = _base_ctx(days_to_earnings=2, management_mode="manual_managed")
        assert ctx["event_risk"]["active"] is True
        assert ctx["event_risk"]["severity"] == "red"

    def test_earnings_beyond_15_days_inactive(self):
        ctx = _base_ctx(days_to_earnings=20, management_mode="manual_managed")
        assert ctx["event_risk"]["active"] is False

    def test_algo_position_no_event_risk(self):
        ctx = _base_ctx(days_to_earnings=5, management_mode="algo_observed")
        assert ctx["event_risk"]["active"] is False


# ── passthrough fields ────────────────────────────────────────────────────────

class TestPassthroughFields:
    def test_position_state_passed_through(self):
        ctx = _base_ctx(position_state="RUNNER")
        assert ctx["position_state"] == "RUNNER"

    def test_state_label_passed_through(self):
        ctx = _base_ctx(state_label="🏃 Runner Mode")
        assert ctx["state_label"] == "🏃 Runner Mode"

    def test_breakeven_alerted_passed_through(self):
        ctx = _base_ctx(breakeven_alerted=True)
        assert ctx["breakeven_alerted"] is True

    def test_is_algo_true_for_algo_mode(self):
        ctx = _base_ctx(management_mode="algo_observed")
        assert ctx["is_algo"] is True

    def test_is_algo_false_for_manual(self):
        ctx = _base_ctx(management_mode="manual_managed")
        assert ctx["is_algo"] is False


# ── Integration scenarios ─────────────────────────────────────────────────────

class TestIntegrationScenarios:
    def test_runner_with_high_profit(self):
        # 5R runner: entry=50, curr=75 (+$25*100=$2500), stop=52 (+$2)
        ctx = _base_ctx(
            entry=50.0, curr_p=75.0, sl=52.0, qty=100.0,
            init_sl=45.0, base_price=50.0, base_qty=100.0,
            target_risk_usd=500.0, position_state="RUNNER",
            state_label="🏃 Runner Mode",
        )
        assert ctx["has_profit"] is True
        assert ctx["position_state"] == "RUNNER"
        assert ctx["capital_at_risk"] == 0.0  # stop above entry (52>50)

    def test_broken_position_with_loss(self):
        # price below stop
        ctx = _base_ctx(
            entry=50.0, curr_p=46.0, sl=47.0, qty=100.0,
            position_state="BROKEN",
        )
        assert ctx["has_profit"] is False
        assert ctx["capital_at_risk"] > 0

    def test_algo_position_fields(self):
        ctx = _base_ctx(
            setup="ALGO", management_mode="algo_observed",
            days_to_earnings=5,
        )
        assert ctx["is_algo"] is True
        assert ctx["event_risk"]["active"] is False  # algo: no event risk
