"""
tests/test_trailing_stop.py — unit tests for compute_suggested_trail_stop()
and get_ma_levels() (pure-math paths only — no I/O).
"""
import pytest
import engine_core as ec


@pytest.mark.unit
class TestComputeSuggestedTrailStop:
    def test_long_8r_uses_ma21(self):
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
        )
        assert result["basis"] == "MA21"
        # stop = MA21 * (1 - 0.02) = 180 * 0.98 = 176.40
        assert result["suggested_stop"] == pytest.approx(176.40, abs=0.01)
        assert "MA21" in result["note"]

    def test_long_5r_uses_ma50_when_no_tight_r(self):
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=6.0, entry_price=100.0,
        )
        assert result["basis"] == "MA50"
        # stop = MA50 * (1 - 0.02) = 170 * 0.98 = 166.60
        assert result["suggested_stop"] == pytest.approx(166.60, abs=0.01)

    def test_long_fallback_to_breakeven_when_no_ma(self):
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=None, ma50=None,
            open_r=7.0, entry_price=120.0,
        )
        assert result["basis"] == "breakeven"
        assert result["suggested_stop"] == pytest.approx(120.0)

    def test_short_8r_uses_ma21_above(self):
        result = ec.compute_suggested_trail_stop(
            side="SELL", current_price=80.0,
            ma21=100.0, ma50=110.0,
            open_r=8.5, entry_price=150.0,
        )
        assert result["basis"] == "MA21"
        # stop = MA21 * (1 + 0.02) = 100 * 1.02 = 102.0
        assert result["suggested_stop"] == pytest.approx(102.0, abs=0.01)

    def test_none_returned_when_no_data_at_all(self):
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=None, ma50=None,
            open_r=6.0, entry_price=0.0,
        )
        assert result["basis"] == "none"
        assert result["suggested_stop"] is None

    def test_long_8r_ma21_takes_priority_over_ma50(self):
        """When open_r >= 8, MA21 must win even if MA50 is also available."""
        result = ec.compute_suggested_trail_stop(
            side="LONG", current_price=300.0,
            ma21=250.0, ma50=230.0,
            open_r=10.0, entry_price=100.0,
        )
        assert result["basis"] == "MA21"
        assert result["suggested_stop"] < 250.0  # below MA21


# Sprint 8 #6: ATR-aware buffer (Sarah/Daria spec from Meeting 5).
@pytest.mark.unit
class TestATRBuffer:
    """
    buffer = max(2%, 0.008 × atr_pct), where atr_pct is in percentage points.

    Examples Sarah modelled in Meeting 5:
      atr_pct=2.5 (NVDA-class)  → max(0.02, 0.020) = 2.00% (floor wins)
      atr_pct=4.2 (MNST-class)  → max(0.02, 0.0336) = 3.36% (ATR wins)
      atr_pct=None              → 0.02 (legacy fallback)
    """

    def test_default_buffer_when_atr_pct_none(self):
        """Backwards compat: omitting atr_pct must give the original 2% buffer."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
        )
        # ma21 * (1 - 0.02) = 176.40 — matches the legacy test
        assert result["suggested_stop"] == pytest.approx(176.40, abs=0.01)

    def test_low_atr_keeps_floor(self):
        """NVDA-class (ATR ≈ 2.5%) — 0.008 × 2.5 = 0.020, equal to floor.
        Buffer stays at the 2% floor."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
            atr_pct=2.5,
        )
        # max(0.02, 0.008 * 2.5 = 0.020) = 0.02 → stop = 180 * 0.98 = 176.40
        assert result["suggested_stop"] == pytest.approx(176.40, abs=0.01)

    def test_high_atr_widens_buffer(self):
        """MNST-class (ATR ≈ 4.2%) — buffer = 0.008 × 4.2 = 0.0336 (3.36%).
        Stop is wider, preventing whipsaws on a volatile name."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
            atr_pct=4.2,
        )
        # buffer = 0.008 × 4.2 = 0.0336 → stop = 180 × (1 - 0.0336) = 173.952
        assert result["suggested_stop"] == pytest.approx(173.95, abs=0.01)

    def test_extreme_atr_widens_further(self):
        """ATR=10% (MARA-class meme stock) — buffer = 0.08 (8%)."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
            atr_pct=10.0,
        )
        # buffer = 0.008 × 10 = 0.08 → stop = 180 × 0.92 = 165.60
        assert result["suggested_stop"] == pytest.approx(165.60, abs=0.01)

    def test_short_atr_buffer_widens_above(self):
        """SHORT positions — buffer applied above MA, same scaling logic."""
        result = ec.compute_suggested_trail_stop(
            side="SELL", current_price=80.0,
            ma21=100.0, ma50=110.0,
            open_r=8.5, entry_price=150.0,
            atr_pct=5.0,
        )
        # buffer = 0.008 × 5 = 0.04 → stop = 100 × 1.04 = 104.0
        assert result["suggested_stop"] == pytest.approx(104.0, abs=0.01)

    def test_atr_zero_falls_back_to_default(self):
        """ATR=0 is degenerate (e.g. yfinance returned NaN); use the default floor."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
            atr_pct=0.0,
        )
        assert result["suggested_stop"] == pytest.approx(176.40, abs=0.01)

    def test_atr_negative_falls_back_to_default(self):
        """Defensive: negative ATR should be treated as missing."""
        result = ec.compute_suggested_trail_stop(
            side="BUY", current_price=200.0,
            ma21=180.0, ma50=170.0,
            open_r=9.0, entry_price=100.0,
            atr_pct=-1.0,
        )
        assert result["suggested_stop"] == pytest.approx(176.40, abs=0.01)


@pytest.mark.unit
class TestTrailBufferHelper:
    """Direct unit tests for the _trail_buffer helper — the math core."""

    def test_none_returns_default(self):
        assert ec._trail_buffer(None) == 0.02

    def test_zero_returns_default(self):
        assert ec._trail_buffer(0) == 0.02

    def test_negative_returns_default(self):
        assert ec._trail_buffer(-1.5) == 0.02

    def test_low_atr_returns_floor(self):
        # 0.008 × 2.0 = 0.016 < 0.02 → floor wins
        assert ec._trail_buffer(2.0) == 0.02

    def test_threshold_atr_is_exactly_floor(self):
        # 0.008 × 2.5 = 0.020 → tied with floor
        assert ec._trail_buffer(2.5) == pytest.approx(0.02, abs=1e-6)

    def test_high_atr_returns_atr_value(self):
        # 0.008 × 4.2 = 0.0336 > 0.02
        assert ec._trail_buffer(4.2) == pytest.approx(0.0336, abs=1e-6)
