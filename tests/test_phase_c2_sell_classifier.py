"""Phase C2 — SELL/BUY side-first classifier (Engine F1+F2) acceptance.

These are the FIVE separate acceptance tests mandated verbatim by
`docs/teams/PHASE_C2_SCOPE.md` §4 for the founder-gated, Mark-gated
closure-fix of the SELL/BUY side-vs-quantity-sign divergence.

Defect recap (Sprint-25 Engine audit F1+F2): `adaptive_risk_engine`
(`compute_closed_campaigns`) and `engine_core.get_open_positions_campaign`
keyed the SELL/BUY split off the SIGN of `quantity`, while the CORRECT
reference (`analytics_engine.py:399/417`, DATA_CONTRACTS.md:48) keys off
the `side` STRING. On the documented positive-qty-SELL broker export:
  * F1: the closing SELL is misread as a BUY → the campaign silently
    NEVER closes → absent from heat / streak / WR AND from the drawdown
    auto-cut (worst case: raises risk INTO a drawdown).
  * F2: the positive-qty SELL inflates `net_qty` → a CLOSED campaign
    shows as a PHANTOM OPEN position → wrong NAV exposure / open-R.

Fix: one shared pure side-first classifier `engine_core.split_side_first`
(SELL iff `str(side).upper()=="SELL"`, BUY iff `=="BUY"`; quantity is
magnitude-only via `.abs()`), rewired into BOTH callers.
`analytics_engine.py` is NOT touched (already correct + byte-locked).

Byte-identity obligation (Mark Ruling 4): on the currently-correct
inputs (negative-qty SELL / positive-qty BUY — what the LOCKED April
fixture uses) the classifier is a PROVABLE NO-OP, so every pinned number
is byte-identical. Behavior changes ONLY on the positive-qty-SELL input.

`python -m pytest -q -p no:cacheprovider tests/test_phase_c2_sell_classifier.py`
"""
import os
import sys
from datetime import datetime

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adaptive_risk_engine as are
import analytics_engine as ae
import engine_core as ec

# Reuse the LOCKED April fixture VERBATIM (no copy, no edit) so test (4)
# pins the exact bytes the regression locks.
from tests.test_real_data_april_regression import (  # noqa: E402
    _ACCT, _april_df, _r, _weekly_df,
)


def _row(tid, sym, d, side, qty, px, pnl, cid, istop=0.0, setup="VCP"):
    """A trades-row matching the production DataFrame contract."""
    return dict(trade_id=tid, symbol=sym, trade_date=d, side=side,
                quantity=qty, price=px, pnl_usd=pnl, initial_stop=istop,
                stop_loss=istop, setup_type=setup, campaign_id=cid)


# ── 1. Positive-qty SELL now CLOSES in adaptive_risk_engine (F1) ─────────────

class TestF1PositiveQtySellNowCloses:
    """A campaign whose closing SELL has `quantity > 0` AND `side=="SELL"`
    must now be correctly CLOSED (enters heat/streak/WR; the drawdown-cut
    sees it). Pre-fix oracle (sign-of-quantity split): it did NOT close.
    """

    def _pos_qty_sell_df(self):
        # 10 bought, 10 sold — but the broker export stored the SELL
        # quantity as POSITIVE (the DATA_CONTRACTS.md:48 case).
        return pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 10, 150.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", 10, 165.0, 150.0, "C1"),
        ])

    def test_positive_qty_sell_campaign_now_closes(self):
        closed = are.compute_closed_campaigns(self._pos_qty_sell_df())
        assert len(closed) == 1, (
            "post-C2 a positive-qty SELL must close the campaign (side-"
            f"string classifier); got {closed!r}")
        c = closed[0]
        assert c["campaign_id"] == "C1"
        assert c["is_win"] is True
        assert round(c["total_pnl_usd"], 2) == 150.0

    def test_pre_fix_oracle_did_not_close(self):
        """Pin the documented pre-fix behavior: the OLD sign-of-quantity
        split (`buys=qty>0`, `sells=qty<0`) on this same input found NO
        SELL leg (qty is +10) → `sells.empty` → campaign never closed.
        This makes test 1 a genuine before/after closure proof."""
        df = self._pos_qty_sell_df().copy()
        for col in ["quantity", "price", "pnl_usd"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        grp = df[df["campaign_id"] == "C1"]
        old_buys = grp[grp["quantity"] > 0]
        old_sells = grp[grp["quantity"] < 0]
        old_buys_qty = old_buys["quantity"].sum()
        old_sells_qty = old_sells["quantity"].abs().sum()
        # Old logic: sells empty AND net never ≈0 → `continue` → not closed.
        assert old_sells.empty
        assert (old_buys_qty - old_sells_qty) / old_buys_qty > 0.01


# ── 2. Positive-qty SELL NOT phantom-open in engine_core (F2) ────────────────

class TestF2PositiveQtySellNotPhantomOpen:
    """`engine_core.get_open_positions_campaign` must NOT list a fully-
    closed positive-qty-SELL campaign as open; `net_qty` (now
    buys_qty − sells_qty by side string) excludes the SELL leg."""

    def _df(self):
        return pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 100, 150.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", 100, 165.0, 1500.0, "C1"),
        ])

    def test_closed_positive_qty_sell_not_open(self):
        res = ec.get_open_positions_campaign(self._df())
        assert res["ok"] is True
        df = res["data"]
        # Fully closed → no open rows (pre-fix: phantom OPEN qty 200).
        assert df.empty or "AAPL" not in list(df.get("symbol", [])), (
            f"closed positive-qty-SELL campaign phantom-opened: {df!r}")

    def test_pre_fix_oracle_net_qty_inflated(self):
        """Pin the pre-fix defect: OLD `net_qty = quantity.sum()` summed
        the +100 SELL as if a BUY → 200 (a phantom open position)."""
        old_net = self._df()["quantity"].astype(float).sum()
        assert old_net == 200.0
        # New side-first net excludes the SELL leg → 0.
        _, _, bq, sq = ec.split_side_first(self._df())
        assert bq - sq == 0.0

    def test_still_open_partial_positive_qty_sell(self):
        """A genuinely-open campaign (BUY 100, positive-qty SELL 40) must
        still be reported open with the correct residual net_qty 60."""
        df = pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 100, 150.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", 40, 165.0, 600.0, "C1"),
        ])
        res = ec.get_open_positions_campaign(df)
        assert res["ok"] is True
        d = res["data"]
        assert not d.empty
        row = d[d["symbol"] == "AAPL"].iloc[0]
        assert float(row["quantity"]) == pytest.approx(60.0)


# ── 3. Negative-qty SELL byte-identical before/after (no regression) ─────────

class TestNegativeQtySellByteIdenticalNoOp:
    """The classifier is a PROVABLE NO-OP on the currently-correct
    convention (negative-qty SELL / positive-qty BUY). We reconstruct the
    EXACT pre-C2 split inline and assert the live classifier returns the
    identical row-sets and magnitude sums — for BOTH callers' shapes."""

    def _neg_qty_df(self):
        return pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 10, 150.0, 0.0, "C1"),
            _row("b2", "AAPL", "2026-04-02", "BUY", 5, 152.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", -15, 165.0, 210.0, "C1"),
            _row("b3", "MSFT", "2026-04-03", "BUY", 8, 300.0, 0.0, "C2"),
            _row("s2", "MSFT", "2026-04-09", "SELL", -8, 290.0, -80.0, "C2"),
        ])

    def test_classifier_is_noop_on_negative_qty_convention(self):
        df = self._neg_qty_df()
        for col in ["quantity", "price", "pnl_usd"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        for cid, grp in df.groupby("campaign_id"):
            # OLD adaptive split (sign of quantity):
            old_buys = grp[grp["quantity"] > 0]
            old_sells = grp[grp["quantity"] < 0]
            old_buys_qty = float(old_buys["quantity"].sum())
            old_sells_qty = float(old_sells["quantity"].abs().sum())
            # NEW shared side-first classifier:
            nb, ns, nbq, nsq = ec.split_side_first(grp)
            assert list(nb["trade_id"]) == list(old_buys["trade_id"])
            assert list(ns["trade_id"]) == list(old_sells["trade_id"])
            assert nbq == old_buys_qty
            assert nsq == old_sells_qty

    def test_adaptive_negative_qty_oracle_unchanged(self):
        closed = are.compute_closed_campaigns(self._neg_qty_df())
        by = {c["campaign_id"]: c for c in closed}
        assert set(by) == {"C1", "C2"}
        assert round(by["C1"]["total_pnl_usd"], 2) == 210.0
        assert by["C1"]["is_win"] is True
        assert round(by["C2"]["total_pnl_usd"], 2) == -80.0
        assert by["C2"]["is_win"] is False

    def test_open_book_negative_qty_oracle_unchanged(self):
        # Partially open (BUY 15, SELL -5) under the correct convention →
        # behaves exactly as before (net_qty 10, side-string == sign here).
        df = pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 15, 150.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", -5, 165.0, 75.0, "C1"),
        ])
        res = ec.get_open_positions_campaign(df)
        assert res["ok"] is True
        row = res["data"].iloc[0]
        assert float(row["quantity"]) == pytest.approx(10.0)
        assert float(row["realized_pnl"]) == pytest.approx(75.0)


# ── 4. LOCKED April byte-identical post-C2 (reuse the LOCKED fixture) ────────

class TestLockedAprilByteIdenticalPostC2:
    """The LOCKED April regression fixture uses NEGATIVE-qty SELLs, so the
    side-first classifier is a provable no-op on it. Re-running the EXACT
    locked numbers through analytics (the path the regression locks) and
    through the C2-rewired adaptive engine must yield byte-identical
    results: 8 / +$180.49 / WR .375 / PF 2.626 / excl 2."""

    def test_analytics_april_locked_numbers_byte_identical(self):
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2

    def test_adaptive_april_locked_fixture_noop(self):
        """The C2-rewired `compute_closed_campaigns` on the LOCKED April
        rows (all negative-qty SELLs) closes exactly the discretionary
        round-trip campaigns it always did — the classifier no-op."""
        closed = are.compute_closed_campaigns(_april_df())
        ids = {c["campaign_id"] for c in closed}
        # Every fully round-tripped campaign in the locked fixture
        # (each has matching BUY qty and a negative-qty SELL leg).
        assert ids == {
            "CVX_9156146580", "DAR_9148472196", "RVMD_9307120241",
            "RVMD_9307924911", "MTZ_9190319665", "NEE_9376944499",
            "INTC_9378665300", "AXGN_9394908015", "AEHR_9283303702",
            "TSLA_9260403195",
        }
        # Realized PnL per campaign is the sum of its SELL pnl_usd —
        # byte-identical to pre-C2 (negative-qty SELLs unchanged).
        by = {c["campaign_id"]: round(c["total_pnl_usd"], 2) for c in closed}
        assert by["DAR_9148472196"] == 24.6
        assert by["CVX_9156146580"] == -1.25
        assert by["INTC_9378665300"] == -33.6

    def test_weekly_algo_fixture_noop(self):
        """Sprint-22/locked weekly ALGO round-trips: analytics still
        excludes all 3 ALGO; the adaptive no-op closes them by side
        string exactly as the negative-qty sign did."""
        a = ae.compute_period_analytics(
            _weekly_df(), datetime(2026, 5, 3),
            datetime(2026, 5, 9, 23, 59, 59), _ACCT)
        assert a["campaigns_closed"] == 0
        assert a["excluded_count_algo"] == 3
        closed = are.compute_closed_campaigns(_weekly_df())
        assert {c["campaign_id"] for c in closed} == {
            "JPM_9412172555", "JPM_9443250181", "HOOD_9449697599"}


# ── 5. Mixed / edge: blank/NaN side, sign-conflicting, ALGO ─────────────────

class TestEdgeBlankNaNConflictingAlgo:
    """Deterministic, segregation-preserving behavior on the awkward
    inputs. The classifier keys ONLY off the `side` string; a row whose
    `side` is blank/NaN/garbage is NEITHER a BUY nor a SELL (excluded
    from both legs) — honest, never silently coerced into a side."""

    def test_blank_and_nan_side_excluded_from_both_legs(self):
        grp = pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", 10, 150.0, 0.0, "C1"),
            _row("x1", "AAPL", "2026-04-02", "", 5, 151.0, 0.0, "C1"),
            _row("x2", "AAPL", "2026-04-03", None, 5, 151.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", -10, 165.0, 150.0, "C1"),
        ])
        buys, sells, bq, sq = ec.split_side_first(grp)
        assert set(buys["trade_id"]) == {"b1"}
        assert set(sells["trade_id"]) == {"s1"}
        assert bq == 10.0 and sq == 10.0  # blank/None rows in NEITHER leg

    def test_side_set_but_qty_sign_conflicting_uses_side_string(self):
        """`side` is authoritative: a SELL with POSITIVE qty is a SELL; a
        BUY with NEGATIVE qty is a BUY. Quantity is magnitude-only."""
        grp = pd.DataFrame([
            _row("b1", "AAPL", "2026-04-01", "BUY", -10, 150.0, 0.0, "C1"),
            _row("s1", "AAPL", "2026-04-10", "SELL", 10, 165.0, 150.0, "C1"),
        ])
        buys, sells, bq, sq = ec.split_side_first(grp)
        assert set(buys["trade_id"]) == {"b1"}
        assert set(sells["trade_id"]) == {"s1"}
        assert bq == 10.0 and sq == 10.0   # magnitudes, sign ignored

    def test_algo_rows_segregation_preserved(self):
        """ALGO segregation is unaffected: the classifier only splits
        BUY/SELL; ALGO exclusion (stat_bucket / management_mode) is
        downstream and unchanged. An ALGO round-trip closes structurally
        but stays ALGO-classified (excluded from WR/Expectancy)."""
        df = pd.DataFrame([
            _r("a1", "TSLA", "2026-04-01", "BUY", 3, 380.51, 0.0, -1,
               "ALGO", "TSLA_A1"),
            _r("a2", "TSLA", "2026-04-02", "SELL", -3, 365.875, -48.905,
               -1, "ALGO", "TSLA_A1"),
        ])
        closed = are.compute_closed_campaigns(df)
        assert len(closed) == 1
        assert closed[0]["campaign_id"] == "TSLA_A1"
        # ALGO stat-bucket preserved (segregation intact, #8).
        assert closed[0]["stat_bucket"] == ec.STAT_BUCKET_ALGO

    def test_algo_positive_qty_sell_also_closes(self):
        """The closure-fix also applies to ALGO: a positive-qty-SELL ALGO
        round-trip now closes (structurally) AND remains ALGO-segregated
        — deterministic, no leakage into discretionary WR."""
        df = pd.DataFrame([
            _r("a1", "JPM", "2026-04-30", "BUY", 1, 312.645, 0.0, -1,
               "ALGO", "JPM_A1"),
            _r("a2", "JPM", "2026-05-04", "SELL", 1, 308.47, -9.175, -1,
               "ALGO", "JPM_A1"),
        ])
        closed = are.compute_closed_campaigns(df)
        assert len(closed) == 1
        assert closed[0]["stat_bucket"] == ec.STAT_BUCKET_ALGO
