"""Real-founder-data regression (Sprint-21 RCA, 2026-05-16).

Proves `compute_period_analytics` is CORRECT on the founder's actual
`trades` rows: April-2026 → 8 countable closed campaigns / +$180.49
realized; weekly 03-09/05 → 0 countable but 3 ALGO-excluded (-$37.23).

This LOCKS the finding that the report computation is not the defect:
when the founder's production report shows "0", the cause is data
DELIVERY (`_fetch_trades_df` not receiving these rows at report time),
not the analytics/classification logic. Values are hand-extracted
verbatim from the founder's full DB dump.
"""
from datetime import datetime

import pandas as pd
import pytest

import analytics_engine as ae

_ACCT = {"nav": 7922.19, "risk_pct_input": 0.5}


def _r(tid, sym, d, side, qty, px, pnl, istop, setup, cid):
    return dict(trade_id=tid, symbol=sym, trade_date=d, side=side,
                quantity=qty, price=px, pnl_usd=pnl, initial_stop=istop,
                stop_loss=istop, setup_type=setup, campaign_id=cid)


def _april_df():
    R = [
        _r('9156146580', 'CVX', '2026-03-13', 'BUY', 3, 195.78, 0.0, 184.28, 'VCP', 'CVX_9156146580'),
        _r('9257785640', 'CVX', '2026-04-01', 'SELL', -3, 197.03, -1.25, 0, 'VCP', 'CVX_9156146580'),
        _r('9148472196', 'DAR', '2026-03-12', 'BUY', 1, 55.6, 0.0, 51.02, 'VCP', 'DAR_9148472196'),
        _r('9148472208', 'DAR', '2026-03-12', 'BUY', 7, 55.6, 0.0, 51.02, 'VCP', 'DAR_9148472196'),
        _r('9282495790', 'DAR', '2026-04-08', 'SELL', -8, 59.3, 24.6, 0, 'VCP', 'DAR_9148472196'),
        _r('9307120241', 'RVMD', '2026-04-13', 'BUY', 10, 132.5, 0.0, 127.8, 'EP', 'RVMD_9307120241'),
        _r('9307713252', 'RVMD', '2026-04-13', 'SELL', -1, 128.782, -6.468, 145.4, 'EP', 'RVMD_9307120241'),
        _r('9307742026', 'RVMD', '2026-04-13', 'SELL', -1, 128.36, -6.89, 145.4, 'EP', 'RVMD_9307120241'),
        _r('9307757736', 'RVMD', '2026-04-13', 'SELL', -8, 128.26, -38.42, 145.4, 'EP', 'RVMD_9307120241'),
        _r('9307924911', 'RVMD', '2026-04-13', 'BUY', 13, 130.9, 0.0, 127.8, 'EP', 'RVMD_9307924911'),
        _r('9336142373', 'RVMD', '2026-04-16', 'SELL', -5, 149.3, 88.538462, 145.4, 'EP', 'RVMD_9307924911'),
        _r('9355041897', 'RVMD', '2026-04-21', 'SELL', -8, 145.3, 111.161538, 0, 'EP', 'RVMD_9307924911'),
        _r('9190319665', 'MTZ', '2026-03-19', 'BUY', 1, 315.95, 0.0, 292.7, 'VCP', 'MTZ_9190319665'),
        _r('9408963635', 'MTZ', '2026-04-30', 'SELL', -1, 388.13, 67.18, 0, 'VCP', 'MTZ_9190319665'),
        _r('9376944499', 'NEE', '2026-04-23', 'BUY', 4, 96.6, 0.0, 89.75, 'VCP', 'NEE_9376944499'),
        _r('9392191923', 'NEE', '2026-04-27', 'SELL', -4, 94.96, -11.56, 0, 'VCP', 'NEE_9376944499'),
        _r('9378665300', 'INTC', '2026-04-24', 'BUY', 10, 84.67, 0.0, 82.01, 'EP', 'INTC_9378665300'),
        _r('9379237329', 'INTC', '2026-04-25', 'SELL', -10, 81.81, -33.6, 0, 'Unknown', 'INTC_9378665300'),
        _r('9394908015', 'AXGN', '2026-04-28', 'BUY', 4, 44.65, 0.0, 42.88, 'EP', 'AXGN_9394908015'),
        _r('9397453020', 'AXGN', '2026-04-28', 'SELL', -4, 42.7, -12.8, 0, 'Unknown', 'AXGN_9394908015'),
        # AEHR: stop 68.4 ABOVE entry 60.3 → invalid → DATA_INCOMPLETE (excluded)
        _r('9283303702', 'AEHR', '2026-04-08', 'BUY', 5, 60.3, 0.0, 68.4, 'EP', 'AEHR_9283303702'),
        _r('9320120697', 'AEHR', '2026-04-14', 'SELL', -3, 73.5, 35.6, 68.4, 'EP', 'AEHR_9283303702'),
        _r('9396137314', 'AEHR', '2026-04-28', 'SELL', -2, 78.92, 33.74, 0, 'EP', 'AEHR_9283303702'),
        # TSLA ALGO (stop -1) → ALGO_OBSERVED (excluded)
        _r('9260403195', 'TSLA', '2026-04-01', 'BUY', 3, 380.51, 0.0, -1, 'ALGO', 'TSLA_9260403195'),
        _r('9265665177', 'TSLA', '2026-04-02', 'SELL', -3, 365.875, -48.905, -1, 'ALGO', 'TSLA_9260403195'),
    ]
    return pd.DataFrame(R)


def _weekly_df():
    W = [
        _r('9412172555', 'JPM', '2026-04-30', 'BUY', 1, 312.645, 0.0, -1, 'ALGO', 'JPM_9412172555'),
        _r('9428022411', 'JPM', '2026-05-04', 'SELL', -1, 308.47, -9.175, -1, 'ALGO', 'JPM_9412172555'),
        _r('9443250181', 'JPM', '2026-05-06', 'BUY', 1, 315.095, 0.0, -1, 'ALGO', 'JPM_9443250181'),
        _r('9456685741', 'JPM', '2026-05-07', 'SELL', -1, 310.256, -9.839, -1, 'Unknown', 'JPM_9443250181'),
        _r('9449697599', 'HOOD', '2026-05-06', 'BUY', 4, 78.89, 0.0, -1, 'ALGO', 'HOOD_9449697599'),
        _r('9459447495', 'HOOD', '2026-05-07', 'SELL', -4, 75.585, -18.22, -1, 'Unknown', 'HOOD_9449697599'),
    ]
    return pd.DataFrame(W)


@pytest.mark.unit
class TestRealDataAprilRegression:
    def test_april_eight_countable_closed_180_realized(self):
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8           # NOT 0 — logic is correct
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        # AEHR (invalid stop) + TSLA (ALGO) correctly excluded, split honestly
        assert a["excluded_count"] == 2
        assert a["excluded_count_manual"] == 1
        assert a["excluded_pnl_manual"] == pytest.approx(69.34, abs=1e-2)
        assert a["excluded_count_algo"] == 1
        assert a["excluded_pnl_algo"] == pytest.approx(-48.905, abs=1e-3)

    def test_weekly_three_algo_roundtrips_excluded(self):
        a = ae.compute_period_analytics(
            _weekly_df(), datetime(2026, 5, 3),
            datetime(2026, 5, 9, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 0           # #8-correct (all ALGO)
        assert a["excluded_count"] == 3
        assert a["excluded_count_algo"] == 3
        assert a["excluded_pnl_algo"] == pytest.approx(-37.234, abs=1e-3)
        assert a["excluded_count_manual"] == 0
