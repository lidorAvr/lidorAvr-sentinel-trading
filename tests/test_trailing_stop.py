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
