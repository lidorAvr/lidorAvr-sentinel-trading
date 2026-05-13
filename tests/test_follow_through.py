"""
Sprint 2 — Follow-Through Score tests.

Pure-math: caller passes a pre-built DataFrame, no yfinance hits.
"""

import pandas as pd
import pytest
from engine_core import compute_follow_through


def _make_hist(entry_dt: str, close_pcts: list, volumes: list | None = None,
               highs: list | None = None, lows: list | None = None) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame indexed by trading days starting at entry."""
    n = len(close_pcts)
    entry = pd.Timestamp(entry_dt)
    idx = pd.bdate_range(entry, periods=n)
    closes = [100.0 * (1 + p / 100) for p in close_pcts]
    df = pd.DataFrame({
        "Open":   closes,
        "High":   highs if highs is not None else [c * 1.01 for c in closes],
        "Low":    lows  if lows  is not None else [c * 0.99 for c in closes],
        "Close":  closes,
        "Volume": volumes if volumes is not None else [1_000_000] * n,
    }, index=idx)
    return df


class TestComputeFollowThrough:
    def test_returns_none_when_history_empty(self):
        r = compute_follow_through("XYZ", "2026-01-01", 100.0,
                                   hist_df=pd.DataFrame())
        assert r is None

    def test_returns_none_when_too_few_bars(self):
        df = _make_hist("2026-01-01", [1, 2, 3])  # only 3 bars, need 5
        r = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert r is None

    def test_returns_none_when_entry_price_invalid(self):
        df = _make_hist("2026-01-01", [1, 2, 3, 4, 5])
        assert compute_follow_through("XYZ", "2026-01-01", 0.0, hist_df=df) is None
        assert compute_follow_through("XYZ", "2026-01-01", -1.0, hist_df=df) is None

    def test_returns_none_when_entry_date_unparseable(self):
        df = _make_hist("2026-01-01", [1, 2, 3, 4, 5])
        assert compute_follow_through("XYZ", "not-a-date", 100.0, hist_df=df) is None

    def test_strong_follow_through_long(self):
        # Price up 12% by day 5, sustained volume on up days
        df = _make_hist("2026-01-01", [2, 5, 8, 10, 12, 11, 10, 11, 12, 13],
                        volumes=[2_000_000, 2_000_000, 2_000_000,
                                 2_000_000, 2_000_000, 500_000, 400_000,
                                 1_500_000, 1_500_000, 1_500_000])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert score is not None
        assert score >= 75.0  # strong follow-through

    def test_weak_follow_through_long(self):
        # Stock stalls — small gains, then fades
        df = _make_hist("2026-01-01", [0.5, 1, 0.5, 0, -0.5, -1, -1.5, -2, -1.5, -1],
                        volumes=[500_000, 500_000, 500_000, 500_000, 500_000,
                                 2_000_000, 2_000_000, 2_000_000, 1_500_000, 1_500_000])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert score is not None
        assert score <= 30.0  # weak follow-through

    def test_neutral_follow_through_long(self):
        # Modest gain, balanced up/down day volume
        df = _make_hist("2026-01-01", [1, 2, 3, 2.5, 3, 2.5, 3, 2.5, 3, 2.5],
                        volumes=[1_000_000] * 10)
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert score is not None
        assert 30.0 <= score <= 85.0

    def test_score_clamped_to_0_100(self):
        # Extreme gain
        df = _make_hist("2026-01-01", [50, 60, 70, 80, 90, 100, 110, 120, 130, 140])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert score is not None
        assert 0 <= score <= 100

    def test_short_follow_through_strong(self):
        # SHORT: price drops 12% — strong follow-through
        df = _make_hist("2026-01-01",
                        [-2, -5, -8, -10, -12, -11, -10, -11, -12, -13],
                        volumes=[2_000_000] * 10)
        score = compute_follow_through("XYZ", "2026-01-01", 100.0,
                                       hist_df=df, side="SHORT")
        assert score is not None
        assert score >= 70.0

    def test_short_follow_through_weak(self):
        # SHORT entry but price rallies — weak follow-through
        df = _make_hist("2026-01-01", [1, 3, 5, 7, 9, 10, 11, 12, 11, 12])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0,
                                       hist_df=df, side="SHORT")
        assert score is not None
        assert score <= 30.0

    def test_no_volume_column_uses_neutral(self):
        # DataFrame without Volume column → vol_score = 12.5 (neutral)
        df = _make_hist("2026-01-01", [3, 5, 7, 9, 10])
        df = df.drop(columns=["Volume"])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=df)
        assert score is not None
        assert score > 0  # peak + new-high components still scored

    def test_history_starts_before_entry_filtered_out(self):
        # Build a series where pre-entry data is much hotter than post.
        # If filtering works, post-entry-only score will be much lower than
        # what the full series would produce.
        before = _make_hist("2025-12-15", [10, 10, 10, 10, 10])
        # Flat post-entry: no gain, no new high, balanced volume
        after  = _make_hist("2026-01-01", [0, 0, 0, 0, 0])
        combined = pd.concat([before, after])
        score = compute_follow_through("XYZ", "2026-01-01", 100.0, hist_df=combined)
        assert score is not None
        # Only the flat post-entry window should count — peak gain 1% (from
        # default High = close*1.01), nh_pct = 1%, neutral volume.
        # Score should be in the lower half.
        assert score < 50.0
