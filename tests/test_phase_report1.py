"""Phase REPORT-1 acceptance suite — T-R1 (monthly Coaching honors the true
dev-score) + F5 closure (on-demand monthly window = last COMPLETE month).

Authoritative spec: docs/teams/PHASE_REPORT1_SCOPE.md (governs).

Confirmed defect (narrow): `report_scheduler._monthly_coaching_insights(a)`
read `dev = a.get("dev_score", 0) or 0`, a key that NEVER exists on the
`analytics` dict — the real composite score lives only in the SEPARATE
`dev_data = compute_trader_development_score(analytics)` dict, consumed
correctly by the scorecard (`dev_score_data=dev_data`). So `dev` was ALWAYS
0 ⇒ the `dev < 50` branch ⇒ the false "ציון פיתוח נמוך (0/100)" line, while
the SAME monthly report's scorecard showed the true "79/100 — מצוין". The
on-demand path (`report_on_demand.py:175`) passed only `analytics` ⇒
identical contradiction. The WEEKLY path never reads a dev score ⇒
structurally immune and MUST stay byte-identical.

T-R1 fix: `_monthly_coaching_insights` gained an optional `dev_score=None`
param read instead of the bogus key (the bogus read DELETED, no shim); both
monthly call sites now pass the SAME `dev_data["score"]` the scorecard
already consumes ⇒ coaching ↔ scorecard consistent by construction.

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). No bug-codifying existing monthly-coaching test was found
(none asserted the OLD false "0/100"/"נמוך" output), so no Mark-6.1
correction was required.
"""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import report_scheduler as sched
import report_on_demand as rod


# ── fixtures ────────────────────────────────────────────────────────────────

def _analytics(**kw):
    """A representative monthly `analytics` dict — note it deliberately has
    NO `dev_score` key (the realistic shape produced by
    compute_period_analytics; the true score lives only in the SEPARATE
    dev_data dict). PF 1.5 / 5 closed ⇒ no PF line either, so any dev line
    that appears must come from the dev_score arg, not a side path.
    """
    base = {
        "win_rate": 0.5, "expectancy_r": 0.3,
        "missing_stop_rate": 0.0, "oversized_rate": 0.0,
        "campaigns_closed": 5, "profit_factor": 1.5,
    }
    base.update(kw)
    return base


_DEV_LINE_SUBSTR = "ציון פיתוח"
_FALSE_LOW_SUBSTR = "0/100"


# ════════════════════════════════════════════════════════════════════════════
# Case 1 — silent band (79): NO dev line, the contradiction simply disappears
# ════════════════════════════════════════════════════════════════════════════

class TestCase1SilentBandNoDevLine:
    def test_score_79_emits_no_dev_score_line_and_no_0_100(self):
        """The observed live case: a real score of 79 sits in the existing
        silent 50≤dev<80 band ⇒ NO "ציון פיתוח" line at all and certainly
        NO false "0/100". The self-contradiction is gone (no new text
        introduced)."""
        out = sched._monthly_coaching_insights(_analytics(), 79)
        joined = " ".join(out)
        assert _DEV_LINE_SUBSTR not in joined
        assert _FALSE_LOW_SUBSTR not in joined

    def test_pf_and_other_lines_unchanged_for_representative_dict(self):
        """The PF block / fallback for a representative analytics dict is
        unchanged by the dev-score parametrization. PF 1.5 (<2.0, not <1.0)
        ⇒ no PF line; benign win_rate/expectancy ⇒ no other branch ⇒ the
        existing 'חודש סביר' fallback is the sole line (byte-identical to
        pre-fix for this input, since pre-fix dev was 0 only via the BUG —
        with the true silent-band score there is correctly no dev line)."""
        out = sched._monthly_coaching_insights(_analytics(), 79)
        assert out == ["חודש סביר — תמשיך לעקוב אחרי הפרמטרים ולשפר בהדרגה."]

    def test_pf_high_line_still_present_with_silent_band_score(self):
        """PF ≥ 2.0 ⇒ the existing exact PF-strong line is still emitted
        (the dev parametrization does not disturb the PF block)."""
        out = sched._monthly_coaching_insights(
            _analytics(profit_factor=2.6262), 79)
        assert ("Profit Factor של 2.63 — המערכת עובדת. "
                "אל תשנה setups שעובדים." in out)
        assert _DEV_LINE_SUBSTR not in " ".join(out)


# ════════════════════════════════════════════════════════════════════════════
# Case 2 — ≥80 and <50: the EXISTING exact lines, with the REAL score
# ════════════════════════════════════════════════════════════════════════════

class TestCase2HonestHighAndLowLines:
    def test_score_85_emits_exact_excellent_line(self):
        """Real score ≥ 80 ⇒ the EXISTING byte-identical excellent line with
        the real score interpolated."""
        out = sched._monthly_coaching_insights(_analytics(), 85)
        assert ("ציון פיתוח מעולה (85/100) — "
                "אתה פועל בעקביות ברמה גבוהה." in out)
        assert _FALSE_LOW_SUBSTR not in " ".join(out)

    def test_score_40_emits_exact_low_line_genuinely_low_stays_honest(self):
        """A genuinely-low real score (< 50) is STILL honestly flagged with
        the EXISTING byte-identical low line — the fix removes the FALSE
        0/100, never the honest low warning for a real low score."""
        out = sched._monthly_coaching_insights(_analytics(), 40)
        assert (
            "ציון פיתוח נמוך (40/100) — יש לשפר משמעת תהליך ואיכות ה-edge. "
            "קרא שוב את כללי ה-Minervini ויישם." in out
        )

    def test_boundary_80_is_excellent_49_is_low(self):
        """Boundary integrity preserved: 80 ⇒ excellent, 49 ⇒ low (the
        existing ≥80 / <50 thresholds, unchanged)."""
        hi = sched._monthly_coaching_insights(_analytics(), 80)
        assert "ציון פיתוח מעולה (80/100)" in " ".join(hi)
        lo = sched._monthly_coaching_insights(_analytics(), 49)
        assert "ציון פיתוח נמוך (49/100)" in " ".join(lo)


# ════════════════════════════════════════════════════════════════════════════
# Case 3 — score None / omitted ⇒ NO dev line (never the false low line)
# ════════════════════════════════════════════════════════════════════════════

class TestCase3InsufficientScoreNoLine:
    def test_score_none_emits_no_dev_line(self):
        """`compute_trader_development_score` returns {"score": None,…} on
        insufficient data ⇒ NO dev-score line at all, NEVER the false
        "נמוך (0/100)"."""
        out = sched._monthly_coaching_insights(_analytics(), None)
        joined = " ".join(out)
        assert _DEV_LINE_SUBSTR not in joined
        assert _FALSE_LOW_SUBSTR not in joined

    def test_score_arg_omitted_defaults_to_none_no_dev_line(self):
        """Calling WITHOUT the score arg (default None) ⇒ identical
        behavior: no dev line, no false "0/100" (the bogus a.get default
        path is fully deleted, not shimmed)."""
        out = sched._monthly_coaching_insights(_analytics())
        joined = " ".join(out)
        assert _DEV_LINE_SUBSTR not in joined
        assert _FALSE_LOW_SUBSTR not in joined


# ════════════════════════════════════════════════════════════════════════════
# Case 4 — bug-regression: the realistic monthly wiring, pre/post contrast
# ════════════════════════════════════════════════════════════════════════════

class TestCase4BugRegressionMonthlyWiring:
    def test_fixed_monthly_wiring_emits_no_false_low_line(self):
        """Reproduce the EXACT fixed monthly wiring: an `analytics` dict
        WITHOUT a `dev_score` key + a separate `dev_data` whose score is 79
        (the live silent-band case), called exactly as the fixed call sites
        do: `_monthly_coaching_insights(analytics, dev_data.get("score"))`.
        Result: NO false low line, NO "0/100" — coaching no longer
        contradicts the scorecard."""
        analytics = _analytics()
        assert "dev_score" not in analytics  # realistic shape (never merged)
        dev_data = {"score": 79, "label": "מצוין 🟢", "breakdown": {}}

        out = sched._monthly_coaching_insights(
            analytics, dev_data.get("score"))
        joined = " ".join(out)
        assert _DEV_LINE_SUBSTR not in joined
        assert _FALSE_LOW_SUBSTR not in joined

        # PRE-FIX CONTRADICTION DEMONSTRATED: the old call form passed ONLY
        # `analytics` (no score). With the FIXED signature that means
        # dev_score defaults to None ⇒ correctly no line. The defect was
        # that the OLD body did `dev = a.get("dev_score", 0) or 0` ⇒ since
        # `analytics` has NO "dev_score" key, dev was ALWAYS 0 ⇒ the
        # `dev < 50` branch ⇒ the false "ציון פיתוח נמוך (0/100)" line —
        # while dev_data["score"] was 79. We reproduce ONLY that buggy
        # expression here (not by editing prod) to PROVE the contradiction
        # the fix removed:
        buggy_dev = analytics.get("dev_score", 0) or 0
        assert buggy_dev == 0, (
            "the realistic analytics dict has no dev_score key ⇒ the OLD "
            "code's a.get('dev_score',0) was always 0")
        false_pre_fix_line = (
            f"ציון פיתוח נמוך ({buggy_dev}/100) — יש לשפר משמעת תהליך "
            "ואיכות ה-edge. קרא שוב את כללי ה-Minervini ויישם."
        )
        assert _FALSE_LOW_SUBSTR in false_pre_fix_line  # the bug's "0/100"
        # ... and that exact false line is NOT in the fixed output (the
        # contradiction with the true 79 scorecard score is gone).
        assert false_pre_fix_line not in out

    def test_on_demand_helper_is_the_same_scheduler_function(self):
        """report_on_demand calls `sched._monthly_coaching_insights` — the
        SAME function — so the on-demand monthly path is fixed by the same
        change (no separate copy to drift)."""
        assert rod.sched._monthly_coaching_insights is \
            sched._monthly_coaching_insights


# ════════════════════════════════════════════════════════════════════════════
# Case 5 — weekly coaching byte-identical (never a dev-score line, ever)
# ════════════════════════════════════════════════════════════════════════════

class TestCase5WeeklyCoachingByteIdentical:
    def test_weekly_representative_output_unchanged_and_no_dev_line(self):
        """`_weekly_coaching_insights` is structurally immune (never reads a
        dev score) and was NOT touched. For a representative analytics dict
        its output is the exact existing benign-path line and contains NO
        "ציון פיתוח" / dev-score text."""
        out = sched._weekly_coaching_insights(_analytics())
        assert out == ["התהליך השבועי תקין — המשך לפעול לפי הפרוטוקול."]
        assert _DEV_LINE_SUBSTR not in " ".join(out)

    def test_weekly_signature_unchanged_single_arg(self):
        """The weekly helper signature is unchanged (single `a` param) — it
        gained NO dev_score param; weekly call sites are untouched."""
        import inspect
        params = list(
            inspect.signature(sched._weekly_coaching_insights).parameters)
        assert params == ["a"]

    def test_weekly_negative_expectancy_line_byte_identical(self):
        """A representative weekly branch (negative expectancy) still emits
        its exact existing line — no dev-score contamination on weekly."""
        out = sched._weekly_coaching_insights(
            _analytics(expectancy_r=-0.5))
        assert any("Expectancy שלילי (-0.50R)" in i for i in out)
        assert _DEV_LINE_SUBSTR not in " ".join(out)


# ════════════════════════════════════════════════════════════════════════════
# Case 6 — F5 closure pin: on-demand monthly window = LAST COMPLETE month
# ════════════════════════════════════════════════════════════════════════════

class TestCase6F5MonthlyWindowLastCompleteMonth:
    """F5 ("on-demand April monthly renders 0/$0") is RESOLVED by
    correct-by-design relative-window timing, not a code bug. This pins the
    contract so a future silent window-shift regression is caught. Uses the
    REAL functions (`report_on_demand.last_complete_monthly_ref` →
    `report_scheduler._monthly_period`), not a reimplementation.

    Contract read from report_scheduler.py:199-204:
      _monthly_period(ref) → (first_of_prev, last_of_prev) where
      first_of_this = ref.replace(day=1, 00:00:00),
      last_of_prev  = first_of_this - 1 second,
      first_of_prev = last_of_prev.replace(day=1, 00:00:00).
    So for ANY day in May 2026 the window is
      [2026-04-01 00:00:00, 2026-04-30 23:59:59]  (inclusive second-before-May end).
    last_complete_monthly_ref(now) returns `now` itself (report_on_demand.py:63).
    """

    def test_may_reference_resolves_to_april_window(self):
        now = datetime(2026, 5, 18, 14, 30, 0)  # any day in May 2026
        ref = rod.last_complete_monthly_ref(now)
        period_start, period_end = sched._monthly_period(ref)

        # last COMPLETE calendar month = April 2026
        assert period_start == datetime(2026, 4, 1, 0, 0, 0)
        assert period_start.year == 2026 and period_start.month == 4
        assert period_start.day == 1
        # end is the last instant of April (1 second before May 1) per the
        # actual implementation's inclusive contract.
        assert period_end == datetime(2026, 4, 30, 23, 59, 59)
        assert period_end.month == 4
        # the first instant of the NEXT month is exactly 1 second after end.
        assert (period_end + __import__("datetime").timedelta(seconds=1)
                == datetime(2026, 5, 1, 0, 0, 0))

    def test_window_independent_of_day_within_reference_month(self):
        """Any day in May 2026 (1st, mid, last) resolves to the SAME April
        window — the on-demand ref is `now` and _monthly_period keys only on
        the month, so the F5 timing contract is day-stable."""
        windows = {
            sched._monthly_period(rod.last_complete_monthly_ref(
                datetime(2026, 5, d, h, 0, 0)))
            for d, h in ((1, 0), (18, 14), (31, 23))
        }
        assert windows == {
            (datetime(2026, 4, 1, 0, 0, 0),
             datetime(2026, 4, 30, 23, 59, 59))
        }

    def test_pre_april_reference_would_resolve_to_march_the_f5_root(self):
        """Root-cause pin: invoked while *now* was still IN April, the
        on-demand monthly correctly resolved to MARCH (last complete month)
        ⇒ April closes filtered out ⇒ the deferred 0/$0 — a correct-by-
        design timing artifact, NOT a code bug. Post-April it resolves to
        April (this is exactly why F5 is closed, not fixed)."""
        ref_in_april = rod.last_complete_monthly_ref(
            datetime(2026, 4, 20, 9, 0, 0))
        ps, pe = sched._monthly_period(ref_in_april)
        assert ps == datetime(2026, 3, 1, 0, 0, 0)
        assert pe == datetime(2026, 3, 31, 23, 59, 59)


# ════════════════════════════════════════════════════════════════════════════
# Case 7 — LOCKED April unaffected: coaching is narrative, not KPI math
# ════════════════════════════════════════════════════════════════════════════

class TestCase7LockedAprilNarrativeIndependent:
    """LOCKED April (8 / +$180.49 / WR .375 / PF 2.6262 / excl 2) is
    produced by analytics_engine — NOT by the coaching narrative. This
    Phase touches ONLY the monthly *coaching narrative* score-line; it
    imports/alters NO KPI / R / NAV / PF / count math. (The full suite's
    own LOCKED-April regression + every _byte_lock_* test remain the
    authoritative byte-identity proof; this is a lightweight independence
    assertion.)
    """

    def test_monthly_coaching_returns_list_of_strings_no_kpi_mutation(self):
        """`_monthly_coaching_insights` returns a plain list[str] of
        narrative lines and performs no numeric KPI mutation on the input
        analytics dict (it only .get()s and string-formats)."""
        analytics = _analytics(profit_factor=2.6262, campaigns_closed=8)
        snapshot = dict(analytics)
        out = sched._monthly_coaching_insights(analytics, 79)
        assert isinstance(out, list) and out
        assert all(isinstance(s, str) and s for s in out)
        # the analytics dict is not mutated by the coaching helper
        assert analytics == snapshot

    def test_byte_locked_kpi_files_unmodified(self):
        """engine_core / analytics_engine / period_data_probe / the LOCKED
        April fixture are byte-identical to their committed baselines —
        Phase REPORT-1 touched NONE of them (only report_scheduler.py +
        report_on_demand.py changed)."""
        from tests._byte_lock_baseline import assert_byte_identical
        for rel in (
            "engine_core.py",
            "analytics_engine.py",
            "period_data_probe.py",
            "tests/test_real_data_april_regression.py",
        ):
            assert_byte_identical(rel)

    def test_locked_april_regression_invariant_still_holds(self):
        """Re-run the LOCKED April ground truth through the unchanged
        analytics API on the LOCKED fixture's own df — narrative-independent,
        still exact post-fix."""
        import importlib
        mod = importlib.import_module(
            "tests.test_real_data_april_regression")
        import analytics_engine as ae
        a = ae.compute_period_analytics(
            mod._april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59), mod._ACCT)
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2
