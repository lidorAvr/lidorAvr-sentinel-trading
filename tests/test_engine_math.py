import math
import pandas as pd

import engine_core as ec


def test_classify_trade_stage_thresholds():
    assert ec.classify_trade_stage(-0.1, 1) == "underwater"
    assert ec.classify_trade_stage(0.0, 1) == "early"
    assert ec.classify_trade_stage(1.0, 3) == "developing"
    assert ec.classify_trade_stage(2.5, 10) == "advanced"
    assert ec.classify_trade_stage(4.0, 30) == "runner"


def test_time_efficiency_dead_money_and_slow():
    assert ec.map_time_efficiency(8, 0.49) == "dead_money"
    assert ec.map_time_efficiency(15, 0.99) == "slow"
    assert ec.map_time_efficiency(7, 0.49) == "ok"
    assert ec.map_time_efficiency(15, 1.0) == "ok"


def test_safe_return_uses_current_and_lookback_points():
    series = pd.Series([100, 110, 121])
    assert math.isclose(ec.safe_return(series, 2), 0.10, rel_tol=1e-9)
    assert ec.safe_return(series, 5) is None
    assert ec.safe_return(pd.Series([0, 1]), 2) is None


def test_atr_series_known_values():
    hist = pd.DataFrame(
        {
            "High": [11, 13, 14],
            "Low": [9, 10, 12],
            "Close": [10, 12, 13],
        }
    )
    atr = ec.calculate_atr_series(hist, window=2)
    # True ranges: 2, 3, 2. ATR(2): NaN, 2.5, 2.5
    assert math.isnan(atr.iloc[0])
    assert math.isclose(atr.iloc[1], 2.5, rel_tol=1e-9)
    assert math.isclose(atr.iloc[2], 2.5, rel_tol=1e-9)


def test_open_positions_campaign_uses_initial_buy_risk_and_remaining_quantity():
    df = pd.DataFrame(
        [
            {
                "trade_id": "1",
                "campaign_id": "CAT_1",
                "symbol": "CAT",
                "trade_date": "2026-05-01",
                "side": "BUY",
                "quantity": 2,
                "price": 100.0,
                "stop_loss": 90.0,
                "initial_stop": 90.0,
                "pnl_usd": 0.0,
                "setup_type": "EP",
                "management_state": "full_position",
            },
            {
                "trade_id": "2",
                "campaign_id": "CAT_1",
                "symbol": "CAT",
                "trade_date": "2026-05-03",
                "side": "SELL",
                "quantity": -1,
                "price": 120.0,
                "stop_loss": 90.0,
                "initial_stop": 90.0,
                "pnl_usd": 20.0,
                "setup_type": "EP",
                "management_state": "runner_mode",
            },
        ]
    )
    result = ec.get_open_positions_campaign(df)
    assert result["ok"] is True
    open_pos = result["data"]
    assert len(open_pos) == 1
    row = open_pos.iloc[0]
    assert row["symbol"] == "CAT"
    assert math.isclose(float(row["quantity"]), 1.0, rel_tol=1e-9)
    assert math.isclose(float(row["base_price"]), 100.0, rel_tol=1e-9)
    assert math.isclose(float(row["initial_stop"]), 90.0, rel_tol=1e-9)
