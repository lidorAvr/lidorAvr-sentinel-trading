"""
Phase 1 — Risk Basis Engine tests.

Tests every new function added to engine_core.py in the Risk Basis Engine
section.  All tests are pure-math (no DB, no yfinance, no mocking needed).
"""

import pytest
from engine_core import (
    # R calculation
    get_campaign_risk_metrics,
    compute_original_campaign_risk,
    compute_frozen_target_risk,
    compute_r_true,
    compute_r_target,
    # Capital + PnL
    compute_capital_at_risk_usd,
    compute_open_pnl_at_stop,
    compute_protected_profit_usd,
    compute_giveback_usd,
    compute_giveback_pct_of_open_profit,
    classify_giveback_severity,
    # Sizing
    compute_sizing_ratio,
    # Data scope
    get_sample_size_context,
    add_data_scope,
    DATA_SCOPE_YTD,
    DATA_SCOPE_SINCE_IMPORT,
    # Thresholds
    GIVEBACK_BUCKET_CONSERVATIVE,
    GIVEBACK_BUCKET_NORMAL,
    GIVEBACK_BUCKET_WIDE,
    _SAMPLE_INITIAL,
    _SAMPLE_SIGNIFICANT,
)


# ──────────────────────────────────────────────────────────────────────────────
# compute_original_campaign_risk
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeOriginalCampaignRisk:
    def test_long_basic(self):
        # (50 - 47) * 100 = $300
        assert compute_original_campaign_risk("BUY", 50, 47, 100) == 300.0

    def test_long_with_fees(self):
        assert compute_original_campaign_risk("BUY", 50, 47, 100, fees=5.0) == 305.0

    def test_short_basic(self):
        # (53 - 50) * 100 = $300
        assert compute_original_campaign_risk("SHORT", 50, 53, 100) == 300.0

    def test_long_alias(self):
        assert compute_original_campaign_risk("LONG", 50, 47, 100) == 300.0

    def test_zero_quantity_returns_zero(self):
        assert compute_original_campaign_risk("BUY", 50, 47, 0) == 0.0

    def test_zero_stop_returns_zero(self):
        assert compute_original_campaign_risk("BUY", 50, 0, 100) == 0.0

    def test_stop_above_entry_long_returns_zero(self):
        # Stop above entry for a long = invalid → returns 0, not negative
        assert compute_original_campaign_risk("BUY", 50, 55, 100) == 0.0

    def test_fractional_shares(self):
        result = compute_original_campaign_risk("BUY", 100.0, 95.0, 0.5)
        assert result == 2.5  # (100-95)*0.5

    def test_rounding_to_cents(self):
        result = compute_original_campaign_risk("BUY", 10.001, 9.998, 1000)
        assert isinstance(result, float)
        assert result == round((10.001 - 9.998) * 1000, 2)


# ──────────────────────────────────────────────────────────────────────────────
# compute_frozen_target_risk
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeFrozenTargetRisk:
    def test_basic(self):
        result = compute_frozen_target_risk(7500, 7934.27, 0.0035)
        assert result["target_risk_base_capital"] == round(7500 * 0.0035, 2)
        assert result["target_risk_current_nav"] == round(7934.27 * 0.0035, 2)

    def test_keys_present(self):
        r = compute_frozen_target_risk(10000, 10000, 0.01)
        assert "target_risk_base_capital" in r
        assert "target_risk_current_nav" in r

    def test_identical_when_nav_equals_base(self):
        r = compute_frozen_target_risk(8000, 8000, 0.005)
        assert r["target_risk_base_capital"] == r["target_risk_current_nav"]


# ──────────────────────────────────────────────────────────────────────────────
# compute_r_true / compute_r_target
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeRValues:
    def test_r_true_win(self):
        # $300 profit on $100 risk = 3R
        assert compute_r_true(300, 100) == 3.0

    def test_r_true_loss(self):
        # -$100 on $100 risk = -1R
        assert compute_r_true(-100, 100) == -1.0

    def test_r_true_zero_risk(self):
        assert compute_r_true(100, 0) == 0.0

    def test_r_target_basic(self):
        assert compute_r_target(55.54, 27.77) == round(55.54 / 27.77, 2)

    def test_r_target_zero_target(self):
        assert compute_r_target(100, 0) == 0.0

    def test_r_rounding(self):
        # Should round to 2 decimal places
        r = compute_r_true(100, 3)
        assert r == round(100 / 3, 2)


# ──────────────────────────────────────────────────────────────────────────────
# compute_capital_at_risk_usd
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeCapitalAtRisk:
    def test_long_stop_below_entry(self):
        # entry=50, stop=47, qty=100 → $300 at risk
        assert compute_capital_at_risk_usd("BUY", 50, 47, 100) == 300.0

    def test_long_stop_above_entry_zero(self):
        # Stop moved above entry → no capital at risk
        assert compute_capital_at_risk_usd("BUY", 50, 52, 100) == 0.0

    def test_short_stop_above_entry(self):
        # entry=50, stop=53, qty=100 → $300 at risk
        assert compute_capital_at_risk_usd("SHORT", 50, 53, 100) == 300.0

    def test_zero_quantity(self):
        assert compute_capital_at_risk_usd("BUY", 50, 47, 0) == 0.0

    def test_breakeven_stop_zero_risk(self):
        assert compute_capital_at_risk_usd("BUY", 50, 50, 100) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# compute_open_pnl_at_stop
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeOpenPnlAtStop:
    def test_long_stop_below_entry_loss(self):
        # entry=50, stop=47, qty=100 → PnL at stop = (47-50)*100 = -$300
        assert compute_open_pnl_at_stop("BUY", 50, 47, 100) == -300.0

    def test_long_stop_above_entry_profit(self):
        # entry=50, stop=55, qty=100 → PnL at stop = (55-50)*100 = +$500
        assert compute_open_pnl_at_stop("BUY", 50, 55, 100) == 500.0

    def test_with_fees(self):
        # entry=50, stop=55, qty=100, fees=10 → 500 - 10 = $490
        assert compute_open_pnl_at_stop("BUY", 50, 55, 100, estimated_exit_fees=10) == 490.0

    def test_short_stop_above_entry(self):
        # entry=50, stop=47, qty=100 → PnL at stop = (50-47)*100 = +$300
        assert compute_open_pnl_at_stop("SHORT", 50, 47, 100) == 300.0

    def test_zero_quantity(self):
        assert compute_open_pnl_at_stop("BUY", 50, 55, 0) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# compute_protected_profit_usd
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeProtectedProfit:
    def test_partial_realized_plus_stop_profit(self):
        # Realized $200, stop locks in $300 more → $500 protected
        assert compute_protected_profit_usd(200, 300) == 500.0

    def test_stop_below_entry_only_realized_counts(self):
        # Stop below entry: open_pnl_at_stop = -$100 → floor to 0
        assert compute_protected_profit_usd(200, -100) == 200.0

    def test_no_realized_only_stop_profit(self):
        assert compute_protected_profit_usd(0, 400) == 400.0

    def test_both_zero(self):
        assert compute_protected_profit_usd(0, 0) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# compute_giveback_usd / compute_giveback_pct_of_open_profit
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeGivebackUsd:
    def test_positive_open_pnl_with_giveback(self):
        # Open P&L = $500, PnL at stop = $300 → giveback = $200
        assert compute_giveback_usd(500, 300) == 200.0

    def test_underwater_position_zero_giveback(self):
        assert compute_giveback_usd(-100, -200) == 0.0

    def test_stop_above_entry_no_giveback(self):
        # Stop locks in full profit — giveback = 0
        assert compute_giveback_usd(500, 600) == 0.0

    def test_giveback_pct_basic(self):
        # Giveback $200 of $500 open profit = 40%
        assert compute_giveback_pct_of_open_profit(200, 500) == 40.0

    def test_giveback_pct_zero_open_profit(self):
        assert compute_giveback_pct_of_open_profit(100, 0) == 0.0

    def test_giveback_pct_full_giveback(self):
        # All open profit would be given back
        assert compute_giveback_pct_of_open_profit(500, 500) == 100.0


# ──────────────────────────────────────────────────────────────────────────────
# classify_giveback_severity
# ──────────────────────────────────────────────────────────────────────────────

class TestClassifyGivebackSeverity:
    def test_conservative(self):
        assert classify_giveback_severity(10.0) == "conservative"

    def test_at_conservative_boundary(self):
        assert classify_giveback_severity(25.0) == "conservative"

    def test_normal(self):
        assert classify_giveback_severity(35.0) == "normal"

    def test_wide(self):
        assert classify_giveback_severity(55.0) == "wide"

    def test_excessive(self):
        assert classify_giveback_severity(75.0) == "excessive"

    def test_zero_is_conservative(self):
        assert classify_giveback_severity(0.0) == "conservative"

    def test_exactly_60_is_wide(self):
        assert classify_giveback_severity(60.0) == "wide"

    def test_above_60_is_excessive(self):
        assert classify_giveback_severity(60.1) == "excessive"


# ──────────────────────────────────────────────────────────────────────────────
# compute_sizing_ratio
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeSizingRatio:
    """
    Sizing tiers (from spec):
      < 0.35    Micro Probe     score=30   not countable
      0.35–0.60 Probe           score=50   not countable (optional)
      0.60–0.85 Undersized      score=70   countable
      0.85–1.15 Ideal           score=100  countable
      1.15–1.30 Slight Oversize score=80   countable  yellow
      1.30–1.50 Oversized       score=55   countable  orange
      >  1.50   Critical Oversize score=20 countable  red
    """

    def _ratio(self, original_risk, target_risk):
        return compute_sizing_ratio(original_risk, target_risk)

    def test_micro_probe(self):
        r = self._ratio(7.08, 27.77)  # ratio ≈ 0.255 — spec example AXGN
        assert r["classification"] == "Micro Probe"
        assert r["score"] == 30
        assert r["countable_for_main_stats"] is False
        assert r["alert_level"] is None

    def test_probe(self):
        r = self._ratio(14.0, 27.77)  # ratio ≈ 0.504
        assert r["classification"] == "Probe"
        assert r["countable_for_main_stats"] is False

    def test_undersized(self):
        r = self._ratio(19.0, 27.77)  # ratio ≈ 0.684
        assert r["classification"] == "Undersized"
        assert r["countable_for_main_stats"] is True

    def test_ideal(self):
        r = self._ratio(27.77, 27.77)  # ratio = 1.0
        assert r["classification"] == "Ideal"
        assert r["score"] == 100
        assert r["alert_level"] is None

    def test_slight_oversize(self):
        r = self._ratio(33.0, 27.77)  # ratio ≈ 1.19
        assert r["classification"] == "Slight Oversize"
        assert r["alert_level"] == "yellow"

    def test_oversized(self):
        r = self._ratio(38.0, 27.77)  # ratio ≈ 1.37
        assert r["classification"] == "Oversized"
        assert r["alert_level"] == "orange"

    def test_critical_oversize(self):
        r = self._ratio(47.0, 27.77)  # ratio ≈ 1.69 — spec example RVMD
        assert r["classification"] == "Critical Oversize"
        assert r["score"] == 20
        assert r["alert_level"] == "red"
        assert r["countable_for_main_stats"] is True

    def test_zero_target_returns_unknown(self):
        r = compute_sizing_ratio(100, 0)
        assert r["classification"] == "Unknown"
        assert r["score"] == 0

    def test_zero_original_returns_unknown(self):
        r = compute_sizing_ratio(0, 27.77)
        assert r["classification"] == "Unknown"

    def test_sizing_ratio_value_stored(self):
        r = self._ratio(47, 27.77)
        assert r["sizing_ratio"] == round(47 / 27.77, 2)

    def test_ideal_boundary_lower(self):
        # Exactly 0.85 → Ideal (0.85 is first ratio that is NOT < 0.85)
        r = self._ratio(0.85 * 27.77, 27.77)
        assert r["classification"] == "Ideal"

    def test_ideal_boundary_upper(self):
        # Just below 1.15 → Ideal
        r = self._ratio(1.149 * 27.77, 27.77)
        assert r["classification"] == "Ideal"


# ──────────────────────────────────────────────────────────────────────────────
# get_sample_size_context
# ──────────────────────────────────────────────────────────────────────────────

class TestGetSampleSizeContext:
    def test_zero_trades_warning(self):
        r = get_sample_size_context(0)
        assert r["warning"] is True
        assert r["usable"] is False
        assert r["significant"] is False

    def test_9_trades_preliminary(self):
        r = get_sample_size_context(9)
        assert r["warning"] is True
        assert "ראשונית" in r["label"]

    def test_exactly_30_usable(self):
        r = get_sample_size_context(30)
        assert r["usable"] is True
        assert r["warning"] is False
        assert r["significant"] is False

    def test_50_trades_usable_not_significant(self):
        r = get_sample_size_context(50)
        assert r["usable"] is True
        assert r["significant"] is False

    def test_100_trades_significant(self):
        r = get_sample_size_context(100)
        assert r["significant"] is True

    def test_countable_trades_field(self):
        r = get_sample_size_context(42)
        assert r["countable_trades"] == 42


# ──────────────────────────────────────────────────────────────────────────────
# add_data_scope
# ──────────────────────────────────────────────────────────────────────────────

class TestAddDataScope:
    def test_basic_with_countable_trades(self):
        r = add_data_scope(0.444, DATA_SCOPE_YTD, countable_trades=9)
        assert r["value"] == 0.444
        assert r["scope"] == DATA_SCOPE_YTD
        assert r["countable_trades"] == 9
        assert r["sample_warning"] is True

    def test_without_countable_trades(self):
        r = add_data_scope(-585.03, DATA_SCOPE_SINCE_IMPORT)
        assert r["value"] == -585.03
        assert r["scope"] == DATA_SCOPE_SINCE_IMPORT
        assert "countable_trades" not in r
        assert "sample_warning" not in r

    def test_30_trades_no_warning(self):
        r = add_data_scope(0.71, DATA_SCOPE_YTD, countable_trades=30)
        assert r["sample_warning"] is False

    def test_works_with_non_numeric_value(self):
        r = add_data_scope("44.4%", DATA_SCOPE_YTD, countable_trades=9)
        assert r["value"] == "44.4%"


# ──────────────────────────────────────────────────────────────────────────────
# Integration — spec scenario from the document
# ──────────────────────────────────────────────────────────────────────────────

class TestSpecScenarios:
    """
    End-to-end scenario checks using values from the spec document.
    base_capital = 7500, NAV = 7934.27, target_risk_pct = 0.0035
    """

    def test_frozen_target_risk_at_nav(self):
        r = compute_frozen_target_risk(7500, 7934.27, 0.0035)
        assert r["target_risk_base_capital"] == round(7500 * 0.0035, 2)   # 26.25
        assert r["target_risk_current_nav"]  == round(7934.27 * 0.0035, 2)  # 27.77

    def test_axgn_micro_probe(self):
        # AXGN: original_campaign_risk = $7.08, frozen_target = $27.77
        r = compute_sizing_ratio(7.08, 27.77)
        assert r["classification"] == "Micro Probe"
        assert r["countable_for_main_stats"] is False

    def test_rvmd_critical_oversize(self):
        # RVMD: risk $47 vs target $27.77
        r = compute_sizing_ratio(47, 27.77)
        assert r["classification"] == "Critical Oversize"
        assert r["alert_level"] == "red"

    def test_manual_win_rate_scope(self):
        # Win Rate 44.4%, 9 manual trades, YTD
        r = add_data_scope(0.444, DATA_SCOPE_YTD, countable_trades=9)
        assert r["sample_warning"] is True  # 9 < 30

    def test_algo_net_pnl_scope(self):
        # ALGO Net PnL -$585.03, Since Import scope
        r = add_data_scope(-585.03, DATA_SCOPE_SINCE_IMPORT)
        assert r["scope"] == DATA_SCOPE_SINCE_IMPORT

    def test_profit_protection_scenario(self):
        # Position at 2R: entry=50, stop raised to 55 (above entry), qty=100
        # Realized=$0, open P&L = (current_price - 50)*100
        # Suppose current_price = 60 → open_pnl = $1000
        open_pnl_at_stop = compute_open_pnl_at_stop("BUY", 50, 55, 100)
        assert open_pnl_at_stop == 500.0  # stop above entry = profit

        protected = compute_protected_profit_usd(0, 500.0)
        assert protected == 500.0

        cap_at_risk = compute_capital_at_risk_usd("BUY", 50, 55, 100)
        assert cap_at_risk == 0.0  # stop above entry, no capital at risk

    def test_giveback_scenario(self):
        # open_pnl=$1000, pnl_at_stop=$500 → giveback=$500
        gb_usd = compute_giveback_usd(1000, 500)
        assert gb_usd == 500.0
        gb_pct = compute_giveback_pct_of_open_profit(500, 1000)
        assert gb_pct == 50.0
        assert classify_giveback_severity(50.0) == "wide"


# ──────────────────────────────────────────────────────────────────────────────
# get_campaign_risk_metrics — single source of truth wrapper
# ──────────────────────────────────────────────────────────────────────────────
class TestGetCampaignRiskMetrics:
    def _row(self, **overrides):
        base = {
            "base_price": 50.0, "base_qty": 100.0,
            "initial_stop": 47.0, "side": "BUY",
        }
        base.update(overrides)
        return base

    def test_valid_long(self):
        r = get_campaign_risk_metrics(self._row())
        assert r["valid"] is True
        assert r["original_risk"] == 300.0
        assert r["reason"] == ""

    def test_falls_back_to_price_when_base_price_missing(self):
        # No base_price — falls back to "price"
        row = {"price": 50.0, "base_qty": 100.0, "initial_stop": 47.0, "side": "BUY"}
        r = get_campaign_risk_metrics(row)
        assert r["valid"] is True
        assert r["original_risk"] == 300.0

    def test_falls_back_to_quantity_when_base_qty_missing(self):
        row = {"base_price": 50.0, "quantity": 100.0, "initial_stop": 47.0, "side": "BUY"}
        r = get_campaign_risk_metrics(row)
        assert r["valid"] is True
        assert r["original_risk"] == 300.0

    def test_missing_initial_stop(self):
        r = get_campaign_risk_metrics(self._row(initial_stop=0))
        assert r["valid"] is False
        assert "initial_stop" in r["reason"]

    def test_stop_above_price_invalid(self):
        r = get_campaign_risk_metrics(self._row(initial_stop=55.0))
        assert r["valid"] is False
        assert "initial_stop" in r["reason"]

    def test_missing_base_price(self):
        r = get_campaign_risk_metrics({"base_qty": 100.0, "initial_stop": 47.0, "side": "BUY"})
        assert r["valid"] is False
        assert "base_price" in r["reason"]

    def test_missing_base_qty(self):
        r = get_campaign_risk_metrics({"base_price": 50.0, "initial_stop": 47.0, "side": "BUY"})
        assert r["valid"] is False

    def test_short_side(self):
        # SHORT: stop above entry
        r = get_campaign_risk_metrics({
            "base_price": 50.0, "base_qty": 100.0,
            "initial_stop": 53.0, "side": "SHORT",
        })
        assert r["valid"] is True
        assert r["original_risk"] == 300.0

    def test_none_initial_stop_treated_as_missing(self):
        r = get_campaign_risk_metrics(self._row(initial_stop=None))
        assert r["valid"] is False
