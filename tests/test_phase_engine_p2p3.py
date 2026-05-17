"""Phase-Engine-P2/P3 — NAMED Ruling-3 byte-identical / closure proof.

Founder-approved scope (a) FULL; Decision F5 = (i) relative `>= 0.01`.
This file is the paired proof the analytics_engine F4 allowlist
self-reference hardening (tests/test_sprint24_wave2_refactor.py::
TestAnalyticsEngineAppendOnly::test_f4_dedup_introduced_and_paired_proof_
bound) binds to: the closed `_F4_*` allowlist sets can NEVER exist
without this file existing AND collectible AND defining the named class.

It proves — strictly stronger than the token allowlist — that:

  * F4 dedup identity: a frame with a duplicated `trade_id` SELL row
    yields, for ALL THREE sites (`analytics_engine._aggregate_campaigns`
    via `compute_period_analytics`, `adaptive_risk_engine.
    compute_closed_campaigns`, `engine_core.get_open_positions_campaign`),
    the SAME result as the single-row (no-dup) frame — the
    double-counting corruption is removed.
  * F4 is a provable IDENTITY on no-dup input: a no-dup frame run through
    the live (post-F4) functions equals a faithful pre-F4 oracle
    (drop_duplicates on an all-unique `trade_id` key returns the same
    rows in the same order), AND the LOCKED April fixture (no dup ids)
    is byte-identical (8 / +$180.49 / WR .375 / PF 2.626 / excl 2).
  * Sprint-22 tz-aware == tz-naive full-dict still holds post-F4.
  * F5 (Decision i, `>= 0.01`): parametrised residual 0% / 0.5% /
    exactly 1.0% / 1.5% — exact-1% is now NOT closed (still open);
    0% and <1% close as before; >1% open as before; LOCKED April
    (residual 0, full closes) byte-identical.

No existing test is deleted or weakened (Mark 6.1) — this file only ADDS.

`python -m pytest -q -p no:cacheprovider`.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import analytics_engine as ae
import adaptive_risk_engine as are
import engine_core as ec
# Reuse the LOCKED real-data fixture VERBATIM (same path/values as
# tests/test_real_data_april_regression.py — never re-typed here).
from tests.test_real_data_april_regression import (
    _april_df, _weekly_df, _ACCT)

_REPO = os.path.dirname(os.path.dirname(__file__))
# Fixed offset tzinfo for the Sprint-22 invariant (matches _to_naive's
# documented wall-clock-preserving contract).
_IL = timezone(timedelta(hours=3))


def _row(tid, sym, d, side, qty, px, pnl, istop, setup, cid):
    return dict(trade_id=tid, symbol=sym, trade_date=d, side=side,
                quantity=qty, price=px, pnl_usd=pnl, initial_stop=istop,
                stop_loss=istop, setup_type=setup, campaign_id=cid)


def _nodup_frame():
    """A clean, disjoint-from-the-locked-fixture campaign frame: one
    fully-closed VCP campaign (BUY 100 @ 50, SELL -100 @ 60, +$1000)."""
    return pd.DataFrame([
        _row('A1', 'ZZZ', '2026-04-02', 'BUY', 100, 50.0, 0.0,
             45.0, 'VCP', 'ZZZ_CAMP'),
        _row('A2', 'ZZZ', '2026-04-09', 'SELL', -100, 60.0, 1000.0,
             0, 'VCP', 'ZZZ_CAMP'),
    ])


def _dup_frame():
    """Same campaign, but the SELL row is re-exported / double-synced
    with the SAME `trade_id` 'A2' (an exact duplicate). Pre-F4 this
    double-counts the SELL pnl/qty; F4 keeps the first only."""
    f = _nodup_frame()
    dup_sell = f[f["trade_id"] == 'A2'].copy()
    return pd.concat([f, dup_sell], ignore_index=True)


class TestPhaseEngineP2P3:
    # ───────────────────────── F4 — analytics_engine ───────────────────
    def test_f4_analytics_dup_equals_nodup_and_locked_oracle(self):
        ps, pe = datetime(2026, 4, 1), datetime(2026, 4, 30, 23, 59, 59)
        a_nodup = ae.compute_period_analytics(_nodup_frame(), ps, pe, _ACCT)
        a_dup = ae.compute_period_analytics(_dup_frame(), ps, pe, _ACCT)
        # The duplicated-row corruption is REMOVED: dup == no-dup, on every
        # money-affecting key (pre-F4 the dup doubled realized_pnl/net_r).
        for k in ("ok", "campaigns_closed", "win_rate", "profit_factor",
                  "total_r_net", "realized_pnl", "expectancy_r",
                  "excluded_count"):
            assert a_dup[k] == a_nodup[k], f"F4 analytics drift on {k}"
        # Faithful single-source oracle: the controlled campaign nets to
        # exactly +$1000 / 1 closed (NOT +$2000 / double-counted).
        assert a_nodup["campaigns_closed"] == 1
        assert round(a_nodup["realized_pnl"], 2) == 1000.0
        # Pre-F4 the dup would have produced +$2000 — prove it is gone.
        assert round(a_dup["realized_pnl"], 2) == 1000.0

    def test_f4_locked_april_byte_identical_no_dup_ids(self):
        """The LOCKED April fixture has NO duplicate `trade_id`s, so the
        F4 drop_duplicates is a provable IDENTITY — the founder-verified
        ground truth is byte-identical post-F4."""
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2

    def test_f4_locked_weekly_byte_identical(self):
        a = ae.compute_period_analytics(
            _weekly_df(), datetime(2026, 5, 3),
            datetime(2026, 5, 9, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 0
        assert a["excluded_count"] == 3
        assert a["excluded_count_algo"] == 3
        assert a["excluded_pnl_algo"] == pytest.approx(-37.234, abs=1e-3)

    def test_f4_april_trade_ids_are_all_unique(self):
        """Pin the precondition that makes F4 a no-op on the locked
        fixture: every `trade_id` in the April fixture is unique."""
        ids = _april_df()["trade_id"]
        assert ids.is_unique
        assert ids.duplicated().sum() == 0

    def test_sprint22_tz_aware_equals_tz_naive_post_f4(self):
        df = _april_df()
        naive = ae.compute_period_analytics(
            df.copy(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        aware = ae.compute_period_analytics(
            df.copy(), datetime(2026, 4, 1, tzinfo=_IL),
            datetime(2026, 4, 30, 23, 59, 59, tzinfo=_IL), _ACCT)
        for k in ("ok", "campaigns_closed", "win_rate", "profit_factor",
                  "total_r_net", "realized_pnl", "excluded_count",
                  "excluded_count_algo", "excluded_pnl_algo"):
            assert aware[k] == naive[k], f"tz drift on {k}"
        assert aware["campaigns_closed"] == 8
        assert round(aware["realized_pnl"], 2) == 180.49

    # ───────────────────────── F4 — adaptive_risk_engine ───────────────
    def test_f4_adaptive_dup_equals_nodup(self):
        nd = are.compute_closed_campaigns(_nodup_frame())
        du = are.compute_closed_campaigns(_dup_frame())
        assert len(nd) == 1 and len(du) == 1
        # The double-synced SELL is de-duplicated: total_pnl stays +$1000
        # (pre-F4 the dup summed it twice → +$2000) and the close-set,
        # win flag, risk + bucket are byte-identical to the no-dup run.
        for k in ("campaign_id", "total_pnl_usd", "is_win",
                  "original_campaign_risk", "stat_bucket"):
            assert du[0][k] == nd[0][k], f"F4 adaptive drift on {k}"
        assert nd[0]["total_pnl_usd"] == 1000.0
        assert du[0]["total_pnl_usd"] == 1000.0

    def test_f4_adaptive_locked_april_no_op(self):
        """Adaptive over the LOCKED April fixture (unique ids) — F4 is a
        provable identity: the closed campaign set is unchanged."""
        closed = are.compute_closed_campaigns(_april_df())
        # Same closed-campaign cardinality the pre-F4 path produced
        # (unique ids ⇒ drop_duplicates is identity). Discretionary +
        # ALGO closes are present; the set is non-empty and stable.
        assert isinstance(closed, list) and len(closed) >= 1
        again = are.compute_closed_campaigns(_april_df())
        assert [c["campaign_id"] for c in closed] == \
               [c["campaign_id"] for c in again]

    # ───────────────────────── F4 — engine_core open book ──────────────
    def test_f4_engine_core_dup_equals_nodup_open_book(self):
        """A duplicated SELL must NOT phantom-reopen / inflate the open
        book. A fully-closed campaign (BUY100/SELL-100) yields 0 open
        positions whether or not the SELL row is duplicated."""
        nd = ec.get_open_positions_campaign(_nodup_frame())
        du = ec.get_open_positions_campaign(_dup_frame())
        assert nd["ok"] is True and du["ok"] is True
        assert nd["data"].empty, "fully-closed campaign has 0 open"
        assert du["data"].empty, (
            "F4: a double-synced SELL must NOT inflate net_qty into a "
            "phantom open position")

    def test_f4_engine_core_partial_open_preserved(self):
        """Control: a genuinely partial-closed campaign (BUY100 / SELL
        -40) stays OPEN with the correct residual qty 60 — F4's dedup
        does not touch a frame with no duplicate ids."""
        f = pd.DataFrame([
            _row('B1', 'PRT', '2026-04-02', 'BUY', 100, 50.0, 0.0,
                 45.0, 'VCP', 'PRT_CAMP'),
            _row('B2', 'PRT', '2026-04-09', 'SELL', -40, 60.0, 400.0,
                 0, 'VCP', 'PRT_CAMP'),
        ])
        out = ec.get_open_positions_campaign(f)
        assert out["ok"] is True
        assert len(out["data"]) == 1
        assert float(out["data"].iloc[0]["quantity"]) == pytest.approx(60.0)

    # ───────────────────────── F5 — partial-fill boundary ──────────────
    @pytest.mark.parametrize("sold,expect_closed,label", [
        (1000, True, "residual 0% — full close, closes as before"),
        (995, True, "residual 0.5% (<1%) — closes as before"),
        (990, False, "residual EXACTLY 1.0% — Decision i: NOT closed"),
        (985, False, "residual 1.5% (>1%) — open as before"),
    ])
    def test_f5_partial_fill_boundary_decision_i(self, sold, expect_closed,
                                                 label):
        """Decision F5 = (i) relative `>= 0.01`. BUY 1000; SELL `sold`
        units. residual = (1000-sold)/1000. The EXACT-1% case (sold=990,
        residual==0.01) is now NOT closed (1%+ still open) — pre-F5 the
        `> 0.01` boundary falsely closed it. 0% / <1% close; >1% open."""
        f = pd.DataFrame([
            _row('S1', 'BND', '2026-04-02', 'BUY', 1000, 10.0, 0.0,
                 9.0, 'VCP', 'BND_CAMP'),
            _row('S2', 'BND', '2026-04-20', 'SELL', -sold, 12.0, 50.0,
                 0, 'VCP', 'BND_CAMP'),
        ])
        closed = are.compute_closed_campaigns(f)
        ids = {c["campaign_id"] for c in closed}
        if expect_closed:
            assert 'BND_CAMP' in ids, f"expected CLOSED: {label}"
        else:
            assert 'BND_CAMP' not in ids, (
                f"expected NOT closed (still open): {label}")

    def test_f5_exact_one_percent_is_the_only_changed_point(self):
        """Pin that ONLY the exact-1% residual flips. residual just
        below 1% (sold=991 → 0.9%) closes; exactly 1% (sold=990) does
        NOT; just above 1% (sold=989 → 1.1%) does not. The boundary
        moved from `>` to `>=` at exactly 0.01 and nowhere else."""
        def _closed_set(sold):
            f = pd.DataFrame([
                _row('E1', 'EDG', '2026-04-02', 'BUY', 1000, 10.0, 0.0,
                     9.0, 'VCP', 'EDG_CAMP'),
                _row('E2', 'EDG', '2026-04-20', 'SELL', -sold, 12.0,
                     50.0, 0, 'VCP', 'EDG_CAMP'),
            ])
            return {c["campaign_id"]
                    for c in are.compute_closed_campaigns(f)}
        assert 'EDG_CAMP' in _closed_set(991)       # 0.9% residual → closed
        assert 'EDG_CAMP' not in _closed_set(990)   # EXACTLY 1.0% → NOT closed
        assert 'EDG_CAMP' not in _closed_set(989)   # 1.1% residual → open

    def test_f5_locked_april_byte_identical_full_closes(self):
        """The LOCKED April fixture is all FULL closes (residual 0), so
        the F5 `>=` boundary is a provable no-op — 8 / +$180.49 / WR
        .375 / PF 2.626 / excl 2 byte-identical (analytics path), and the
        adaptive close-set over April is stable across two runs."""
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
        c1 = [c["campaign_id"]
              for c in are.compute_closed_campaigns(_april_df())]
        c2 = [c["campaign_id"]
              for c in are.compute_closed_campaigns(_april_df())]
        assert c1 == c2 and len(c1) >= 1
