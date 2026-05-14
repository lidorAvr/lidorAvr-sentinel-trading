"""test_market_ftd.py — Sprint 11 P3 HIGH 6.

Minervini / IBD Follow-Through Day market signal (compute_market_ftd
in engine_core.py). Different from the existing per-position
compute_follow_through.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import engine_core as ec


def _build_spy_hist(prices, volumes=None):
    """Build a SPY-like DataFrame from a price + volume series."""
    if volumes is None:
        volumes = [1_000_000] * len(prices)
    df = pd.DataFrame({
        "Open":   prices,
        "High":   [p * 1.005 for p in prices],
        "Low":    [p * 0.995 for p in prices],
        "Close":  prices,
        "Volume": volumes,
    }, index=pd.bdate_range("2026-01-01", periods=len(prices)))
    return df


class TestComputeMarketFTD:
    def test_insufficient_history_returns_not_ok(self):
        df = _build_spy_hist([100.0] * 20)  # too short
        out = ec.compute_market_ftd(df)
        assert out["ok"] is False
        assert out["ftd_today"] is False

    def test_flat_market_no_correction(self):
        """A flat market (no decline) → not in correction → no FTD signal."""
        # 100-row flat history above MA50
        df = _build_spy_hist([100.0] * 100)
        out = ec.compute_market_ftd(df)
        assert out["ok"] is True
        assert out["is_correction"] is False

    def test_active_correction_no_ftd_yet(self):
        """Long downtrend, low recent, day-1 just happened but no big up
        day yet."""
        # Build: 50 days at 100, then 25 days declining from 100 to 85,
        # then 1 small up day
        prices = ([100.0] * 50
                  + [100.0 - (i * 0.6) for i in range(1, 26)]
                  + [85.5])  # day 1 (tiny bounce)
        df = _build_spy_hist(prices)
        out = ec.compute_market_ftd(df)
        # Should be: in correction, no FTD
        assert out["is_correction"] is True
        assert out["ftd_today"] is False

    def test_ftd_today_detected(self):
        """Construct: correction, day-1 several days ago, today is a
        +2% day on higher volume → FTD today."""
        # 50 flat + decline to a low + 4 small ups + today big up
        prices = ([100.0] * 50)
        # decline
        for i in range(20):
            prices.append(100.0 - i * 0.4)
        # day 1 + small ups
        prices.extend([92.5, 92.6, 92.7, 92.8])
        # today: +2% day
        prices.append(prices[-1] * 1.022)
        volumes = [1_000_000] * (len(prices) - 1) + [1_500_000]  # higher vol today
        df = _build_spy_hist(prices, volumes)
        out = ec.compute_market_ftd(df)
        assert out["ok"] is True
        # The function should detect today's FTD (last row up 2% on higher vol)
        assert out["ftd_today"] is True
        assert out["ftd_recent"] is True

    def test_ftd_recent_but_not_today(self):
        """FTD fired 2-3 sessions ago, today is quiet."""
        prices = ([100.0] * 50)
        for i in range(20):
            prices.append(100.0 - i * 0.4)
        # day 1 + small ups
        prices.extend([92.5, 92.6, 92.7])
        # FTD day: +2%
        prices.append(prices[-1] * 1.022)
        # 2 quiet days after FTD
        prices.extend([prices[-1] * 1.001, prices[-1] * 1.001 * 0.999])
        volumes = ([1_000_000] * (len(prices) - 3) + [1_500_000] +
                   [1_100_000, 1_000_000])
        df = _build_spy_hist(prices, volumes)
        out = ec.compute_market_ftd(df)
        assert out["ok"] is True
        assert out["ftd_recent"] is True
        assert out["ftd_today"] is False

    def test_summary_contains_hebrew(self):
        """Summary is Hebrew; should mention FTD or correction state."""
        prices = ([100.0] * 50)
        for i in range(20):
            prices.append(100.0 - i * 0.4)
        prices.extend([92.5, 92.6, 92.7, 92.8])
        prices.append(prices[-1] * 1.022)
        volumes = [1_000_000] * (len(prices) - 1) + [1_500_000]
        df = _build_spy_hist(prices, volumes)
        out = ec.compute_market_ftd(df)
        if out["ftd_today"]:
            assert "Follow-Through" in out["summary"] or "FTD" in out["summary"]

    def test_returns_safe_defaults_on_bad_input(self):
        """Empty DataFrame / None inputs return ok=False, no exception."""
        out = ec.compute_market_ftd(None)
        assert out["ok"] is False
        assert out["ftd_today"] is False
        assert out["ftd_recent"] is False
        # Verify no KeyError accessing optional fields
        assert "summary" in out
