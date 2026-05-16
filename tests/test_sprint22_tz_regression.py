"""Sprint-22 tz-aware == tz-naive regression (DEC-20260516-019).

PROVEN production root cause: production passes tz-AWARE period bounds
(`datetime.now(ISRAEL_TZ)` → `_weekly/_monthly_period`) while
`analytics_engine.py` coerces `trade_date` to a tz-NAIVE Series. The WS-B
unlinked filter + `_get_closed_campaigns` then silently compared tz-naive
Series vs tz-aware scalar → all-False → "0 קמפיינים" in prod (the probe's
own pre-filter RAISED `Invalid comparison` — same defect, different
surface). The Sprint-22 single-point tz-normalization (strip tzinfo,
wall-clock preserved) fixes both at one engine site + the mirrored probe.

This file is ADDITIVE per MARK_SPRINT22_RULINGS.md §2. It REUSES the
LOCKED fixtures `_april_df`/`_weekly_df`/`_ACCT` by import — it does NOT
copy or modify `tests/test_real_data_april_regression.py` (which stays
byte-identical, the tz-naive proof).

Coverage (Mark §2/§3/§5/§6):
  1. tz-aware bounds → EXACTLY the locked tz-naive numbers, key-for-key,
     AND tz_aware_result == tz_naive_result over the full metrics dict.
  2. Probe does NOT raise under tz-aware `now` (the original RAISE
     surface) and stays a faithful witness.
  3. Byte-identical naive-path guard: `_to_naive` is a provable algebraic
     no-op (identity) on already-naive input; locked numbers unchanged.
  4. #1 anti-masking: a genuinely empty/None df under tz-AWARE bounds
     still returns the honest `_empty()` path — DISTINCT from the tz fix,
     never conflated, the empty guard precedes normalization.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import analytics_engine as ae
import period_data_probe as probe
import report_scheduler as sched

# REUSE the LOCKED fixtures — no copy, no modification.
from test_real_data_april_regression import _april_df, _weekly_df, _ACCT

ISRAEL = ZoneInfo("Asia/Jerusalem")

# (start, end) for the LOCKED windows — identical wall-clock to the locked
# tz-naive regression; only tzinfo differs across the parametrization.
_APRIL_BOUNDS = (datetime(2026, 4, 1), datetime(2026, 4, 30, 23, 59, 59))
_WEEKLY_BOUNDS = (datetime(2026, 5, 3), datetime(2026, 5, 9, 23, 59, 59))


def _aware(dt):
    """tz-AWARE Asia/Jerusalem with the SAME wall-clock (no shift)."""
    return dt.replace(tzinfo=ISRAEL)


@pytest.mark.unit
class TestSprint22TzAwareEqualsNaive:
    """§2 — tz-aware bounds MUST yield EXACTLY the locked tz-naive numbers."""

    @pytest.mark.parametrize("tz", [None, "aware"])
    def test_april_locked_numbers_under_both_tz(self, tz):
        s, e = _APRIL_BOUNDS
        if tz == "aware":
            s, e = _aware(s), _aware(e)
        a = ae.compute_period_analytics(_april_df(), s, e, _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
        assert a["excluded_count_manual"] == 1
        assert a["excluded_pnl_manual"] == pytest.approx(69.34, abs=1e-2)
        assert a["excluded_count_algo"] == 1
        assert a["excluded_pnl_algo"] == pytest.approx(-48.905, abs=1e-3)

    @pytest.mark.parametrize("tz", [None, "aware"])
    def test_weekly_locked_numbers_under_both_tz(self, tz):
        s, e = _WEEKLY_BOUNDS
        if tz == "aware":
            s, e = _aware(s), _aware(e)
        a = ae.compute_period_analytics(_weekly_df(), s, e, _ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 0
        assert a["excluded_count"] == 3
        assert a["excluded_count_algo"] == 3
        assert a["excluded_pnl_algo"] == pytest.approx(-37.234, abs=1e-3)
        assert a["excluded_count_manual"] == 0

    def test_april_aware_equals_naive_full_dict(self):
        s, e = _APRIL_BOUNDS
        naive = ae.compute_period_analytics(_april_df(), s, e, _ACCT)
        aware = ae.compute_period_analytics(
            _april_df(), _aware(s), _aware(e), _ACCT)
        # Full-dict equality so ANY future drift on EITHER path fails
        # (Mark §2: not just spot keys). profit_factor here is finite
        # (2.6262) so plain == is exact-safe.
        assert set(aware.keys()) == set(naive.keys())
        assert aware == naive

    def test_weekly_aware_equals_naive_full_dict(self):
        s, e = _WEEKLY_BOUNDS
        naive = ae.compute_period_analytics(_weekly_df(), s, e, _ACCT)
        aware = ae.compute_period_analytics(
            _weekly_df(), _aware(s), _aware(e), _ACCT)
        assert set(aware.keys()) == set(naive.keys())
        assert aware == naive

    def test_scheduler_israel_tz_constant_equals_naive(self):
        # Use the scheduler's OWN ISRAEL_TZ constant (the exact prod tz
        # object) — not just ZoneInfo — to prove the real prod path.
        s, e = _APRIL_BOUNDS
        naive = ae.compute_period_analytics(_april_df(), s, e, _ACCT)
        aware = ae.compute_period_analytics(
            _april_df(),
            s.replace(tzinfo=sched.ISRAEL_TZ),
            e.replace(tzinfo=sched.ISRAEL_TZ),
            _ACCT)
        assert aware["campaigns_closed"] == 8
        assert aware == naive


@pytest.mark.unit
class TestSprint22NoOpProof:
    """§1.5 — normalization is a PROVABLE algebraic no-op on naive input."""

    def test_to_naive_identity_on_naive(self):
        d = datetime(2026, 4, 1)
        # Identity: SAME object returned (not just equal) — zero
        # reassignment for already-naive bounds.
        assert ae._to_naive(d) is d
        d2 = datetime(2026, 4, 30, 23, 59, 59)
        assert ae._to_naive(d2) is d2

    def test_to_naive_strips_tz_wall_clock_preserved(self):
        aware = datetime(2026, 4, 1, 0, 0, 0, tzinfo=ISRAEL)
        out = ae._to_naive(aware)
        assert out.tzinfo is None
        # Wall-clock preserved — NO astimezone shift (Mark §1.1):
        assert out == datetime(2026, 4, 1, 0, 0, 0)
        # A boundary-adjacent value must NOT move by the +2/+3h offset.
        edge = datetime(2026, 4, 30, 23, 59, 59, tzinfo=ISRAEL)
        assert ae._to_naive(edge) == datetime(2026, 4, 30, 23, 59, 59)

    def test_naive_path_byte_identical_to_locked_numbers(self):
        # Sentinel: the entire suite + LOCKED regression stay byte-identical
        # because this is identity on naive input.
        s, e = _APRIL_BOUNDS
        a = ae.compute_period_analytics(_april_df(), s, e, _ACCT)
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
        w = ae.compute_period_analytics(_weekly_df(), *_WEEKLY_BOUNDS, _ACCT)
        assert w["campaigns_closed"] == 0
        assert w["excluded_count"] == 3


@pytest.mark.unit
class TestSprint22AntiMaskingHonestEmpty:
    """§3 — #1: the tz fix must NOT mask a genuinely empty/failed fetch.

    The honest `_empty()` path (`analytics_engine.py` `df is None or
    df.empty` guard) sits BEFORE the §1.2 normalization site, so an
    empty/None fetch short-circuits to the honest branch and NEVER
    interacts with the tz fix. A real non-empty "0 campaigns" (all-ALGO
    weekly) stays an honest zero WITH its excluded disclosure — never
    conflated with an empty/failed fetch.
    """

    def test_empty_df_under_tz_aware_bounds_is_honest_empty(self):
        s, e = _aware(_APRIL_BOUNDS[0]), _aware(_APRIL_BOUNDS[1])
        a = ae.compute_period_analytics(pd.DataFrame(), s, e, _ACCT)
        assert a["campaigns_closed"] == 0
        assert a["ok"] is True
        assert a["unlinked_count"] == 0  # honest-empty, not the tz bug

    def test_none_df_under_tz_aware_bounds_is_honest_empty(self):
        s, e = _aware(_APRIL_BOUNDS[0]), _aware(_APRIL_BOUNDS[1])
        a = ae.compute_period_analytics(None, s, e, _ACCT)
        assert a["campaigns_closed"] == 0
        assert a["ok"] is True

    def test_real_nonempty_zero_stays_honest_zero_with_disclosure(self):
        # The all-ALGO weekly: a LEGITIMATE non-empty "0 campaigns" with
        # excluded disclosure — distinct from an empty/failed fetch.
        s, e = _aware(_WEEKLY_BOUNDS[0]), _aware(_WEEKLY_BOUNDS[1])
        a = ae.compute_period_analytics(_weekly_df(), s, e, _ACCT)
        assert a["campaigns_closed"] == 0
        assert a["excluded_count"] == 3          # disclosed, NOT silent
        assert a["excluded_count_algo"] == 3
        # Distinctness: this is NOT the honest "input ריק/כשל" empty
        # (which has no excluded disclosure); the two never conflate.


@pytest.mark.unit
class TestSprint22ProbeMirrored:
    """§4 — probe no longer RAISES under tz-aware `now`; faithful witness."""

    @pytest.mark.parametrize("period_type", ["weekly", "monthly"])
    def test_probe_no_raise_under_tz_aware_now(self, period_type):
        # The original defect surface: tz-aware `now` made the probe's own
        # pre-filter raise `Invalid comparison`. Must NOT raise now.
        out = probe.build_probe_report(
            period_type, now=datetime.now(sched.ISRAEL_TZ))
        assert isinstance(out, str)
        assert out  # non-empty

    @pytest.mark.parametrize("period_type", ["weekly", "monthly"])
    def test_probe_no_raise_under_fixed_tz_aware_now(self, period_type):
        out = probe.build_probe_report(
            period_type,
            now=datetime(2026, 5, 16, 12, tzinfo=ISRAEL))
        assert isinstance(out, str)
        assert out

    def test_probe_to_naive_helper_is_shared_single_source(self):
        # §4: probe reuses ae._to_naive (single source of truth, no
        # probe-local divergent copy). The probe `import analytics_engine
        # as ae` is function-local, so assert (a) the probe defines no own
        # copy and (b) the probe source delegates to `ae._to_naive`.
        assert not hasattr(probe, "_to_naive")
        import inspect
        src = inspect.getsource(probe._window_block)
        assert "ae._to_naive(period_start)" in src
        assert "ae._to_naive(period_end)" in src
