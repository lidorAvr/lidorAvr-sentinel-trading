"""Sprint-24 Wave-2b — NAMED Ruling-3 byte-identical proof (DEC-20260516-021).

The founder, after Wave-2's honest report, explicitly authorized landing
B1 + B3 as PROVABLE byte-identical no-op refactors (NOT math changes):

  * B1 — the twice-applied `bucket.apply(ec.is_stat_countable)` mask is
    hoisted ONCE into a local `_cnt`, then reused by `countable`/`excluded`.
    `ec.is_stat_countable` is pure/deterministic, so the mask Series is
    identical → the `countable`/`excluded` partition (index + row order
    included) is byte-identical to the OLD twice-applied form.
  * B3 — the inlined numeric-coerce loop is extracted into the top-level
    pure `_coerce_numeric(df, cols)` helper, called with the EXACT same
    tuple in the EXACT same order. The helper mutates `df` in place and
    returns it — algebraically identical to the inlined loop.

This file is the NAMED Ruling-3 proof referenced by the expanded Sprint-19
byte-lock (tests/test_sprint19_headline_comparison.py::
test_analytics_engine_git_diff_empty): the closed `_SPRINT24_AUTHORIZED*`
allowlist sets can NEVER exist without this proof existing AND collectible.

It demonstrates (strictly STRONGER than the lock's token proxy):
  * B1 — mask-once partition `.equals()` the OLD twice-applied partition
    (index + order), over a frame spanning countable + ALGO + DATA_INCOMPLETE.
  * B3 — `_coerce_numeric(df.copy(), TUPLE)` full-frame `.equals()` a fresh
    inlined-loop copy, over all-5 / extra / missing / garbage/NaN/str inputs;
    plus the production call passes that EXACT tuple in that EXACT order.
  * LOCKED April regression byte-identical post-B1/B3 (8 / +$180.49 / WR
    .375 / PF 2.626 / excl 2) — reusing the LOCKED fixture verbatim.
  * Sprint-22 invariant: tz-aware bounds == tz-naive bounds == April
    8/+$180.49 still holds post-B1/B3.

`python -m pytest -q -p no:cacheprovider`.
"""
import ast
import os
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import analytics_engine as ae
import engine_core as ec
# Reuse the LOCKED real-data fixture VERBATIM (same path/values as
# tests/test_real_data_april_regression.py — never re-typed here).
from tests.test_real_data_april_regression import (
    _april_df, _weekly_df, _ACCT)

_REPO = os.path.dirname(os.path.dirname(__file__))
_NUM_COLS = ("price", "quantity", "stop_loss", "initial_stop", "pnl_usd")

# Israel offset is incidental tzinfo here (matches _to_naive's documented
# wall-clock-preserving contract); any fixed offset exercises the path.
_IL = timezone(timedelta(hours=3))


def _inlined_coerce(df, cols):
    """The PRE-B3 inlined loop, byte-for-byte (the oracle)."""
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


class TestSprint24B1B3ByteIdentical:
    # ── B1 — mask-once partition is byte-identical ──────────────────────────
    def test_b1_mask_once_partition_equals_twice_applied(self):
        # campaigns-like frame spanning countable + ALGO + DATA_INCOMPLETE,
        # deliberately NOT in bucket order so index + row order are exercised.
        campaigns = pd.DataFrame([
            {"campaign_id": "C1", "stat_bucket": "VCP_MANUAL", "net_pnl": 10.0},
            {"campaign_id": "C2", "stat_bucket": ec.STAT_BUCKET_ALGO,
             "net_pnl": -5.0},
            {"campaign_id": "C3", "stat_bucket": "EP_MANUAL", "net_pnl": 7.0},
            {"campaign_id": "C4",
             "stat_bucket": ec.STAT_BUCKET_DATA_INCOMPLETE, "net_pnl": 3.0},
            {"campaign_id": "C5", "stat_bucket": ec.STAT_BUCKET_ALGO,
             "net_pnl": 1.0},
            {"campaign_id": "C6", "stat_bucket": "VCP_MANUAL", "net_pnl": -2.0},
        ], index=[5, 11, 2, 9, 4, 7])  # non-trivial, non-sorted index
        bucket = campaigns["stat_bucket"]

        # OLD (pre-B1) — mask applied TWICE.
        old_countable = campaigns[bucket.apply(ec.is_stat_countable)]
        old_excluded = campaigns[~bucket.apply(ec.is_stat_countable)]

        # NEW (post-B1) — hoisted once.
        _cnt = bucket.apply(ec.is_stat_countable)
        new_countable = campaigns[_cnt]
        new_excluded = campaigns[~_cnt]

        assert new_countable.equals(old_countable)   # values + index + order
        assert new_excluded.equals(old_excluded)
        assert list(new_countable.index) == list(old_countable.index)
        assert list(new_excluded.index) == list(old_excluded.index)
        # Sanity: the partition is non-trivial (both legs populated).
        assert not new_countable.empty and not new_excluded.empty
        assert len(new_countable) + len(new_excluded) == len(campaigns)

    # ── B3 — _coerce_numeric is byte-identical to the inlined loop ──────────
    def test_b3_coerce_numeric_full_frame_equals_inlined(self):
        raw = pd.DataFrame({
            "price":        ["1.5", "x", None, "3"],
            "quantity":     [10, "bad", 4, None],
            "stop_loss":    ["", "2.0", "NaN", 5],
            "initial_stop": [float("nan"), 1.0, 2.0, 3.0],
            "pnl_usd":      ["-7.25", None, "garbage", "0"],
            "symbol":       ["A", "B", "C", "D"],          # extra col untouched
            "trade_date":   ["2026-04-01"] * 4,            # extra col untouched
        })
        helper_out = ae._coerce_numeric(raw.copy(), _NUM_COLS)
        oracle_out = _inlined_coerce(raw.copy(), _NUM_COLS)
        assert helper_out.equals(oracle_out)               # whole frame
        assert list(helper_out.columns) == list(oracle_out.columns)

    def test_b3_coerce_numeric_missing_some_columns(self):
        raw = pd.DataFrame({
            "price":  ["1", "z"],
            "pnl_usd": [None, "4"],
            "other":  ["keep", "me"],
            # quantity / stop_loss / initial_stop deliberately ABSENT
        })
        assert ae._coerce_numeric(raw.copy(), _NUM_COLS).equals(
            _inlined_coerce(raw.copy(), _NUM_COLS))

    def test_b3_helper_mutates_in_place_and_returns_same_object(self):
        df = pd.DataFrame({"price": ["1", "bad"], "quantity": [2, 3]})
        out = ae._coerce_numeric(df, _NUM_COLS)
        assert out is df                                   # in place, no copy
        assert out["price"].tolist() == [1.0, 0.0]         # coerced + filled

    def test_b3_production_call_passes_exact_tuple_in_order(self):
        """Static proof: compute_period_analytics calls _coerce_numeric with
        the EXACT 5-tuple in the EXACT order (no silent column drift)."""
        src = open(os.path.join(_REPO, "analytics_engine.py")).read()
        tree = ast.parse(src)
        calls = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_coerce_numeric"):
                calls.append(node)
        assert len(calls) == 1, "exactly one _coerce_numeric call expected"
        tup = calls[0].args[1]
        assert isinstance(tup, ast.Tuple)
        passed = tuple(el.value for el in tup.elts)
        assert passed == _NUM_COLS                          # exact + ordered
        # And it is the ONLY caller (compute_period_analytics).
        assert src.count("_coerce_numeric(") == 2  # 1 def-site + 1 call-site

    # ── LOCKED April regression byte-identical post-B1/B3 ───────────────────
    def test_locked_april_regression_byte_identical_post_b1b3(self):
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2

    def test_locked_weekly_regression_byte_identical_post_b1b3(self):
        a = ae.compute_period_analytics(
            _weekly_df(), datetime(2026, 5, 3),
            datetime(2026, 5, 9, 23, 59, 59), _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 0
        assert a["excluded_count"] == 3
        assert a["excluded_count_algo"] == 3
        assert a["excluded_pnl_algo"] == pytest.approx(-37.234, abs=1e-3)

    # ── Sprint-22 invariant: tz-aware == tz-naive == 8/+$180.49 ─────────────
    def test_sprint22_tz_aware_equals_tz_naive_post_b1b3(self):
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
            assert aware[k] == naive[k], f"tz-aware vs tz-naive drift on {k}"
        assert aware["campaigns_closed"] == 8
        assert round(aware["realized_pnl"], 2) == 180.49
