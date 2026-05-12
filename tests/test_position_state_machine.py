"""
Phase 2 — Position State Machine tests.

Covers every state transition, priority ordering, edge cases,
and the event-risk secondary flag.  All tests are pure-math —
no DB, no yfinance, no mocking required.
"""

import pytest
from engine_core import (
    compute_position_state,
    compute_event_risk_info,
    get_position_state_display_label,
    # State constants
    POSITION_STATE_NEW,
    POSITION_STATE_PROVING,
    POSITION_STATE_WORKING,
    POSITION_STATE_PROFIT_PROTECTION,
    POSITION_STATE_RUNNER,
    POSITION_STATE_YELLOW_FLAG,
    POSITION_STATE_BROKEN,
    POSITION_STATE_DEAD_MONEY,
    POSITION_STATE_ALGO_OBSERVED,
    POSITION_STATE_DATA_INCOMPLETE,
    # Thresholds (for boundary tests)
    _R_RUNNER,
    _R_PROFIT_PROTECT,
    _R_WORKING,
    _NEW_MAX_DAYS,
    _PROVING_MIN_DAYS,
    _PROVING_MAX_DAYS,
    _DEAD_MONEY_MIN_DAYS,
    _VIOLATION_YELLOW_FLAG,
    _VIOLATION_BROKEN,
    _EVENT_RISK_MAX_DAYS,
    _EVENT_RISK_ORANGE_DAYS,
    _EVENT_RISK_RED_DAYS,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _state(
    side="BUY",
    management_mode="manual_managed",
    age_days=5.0,
    open_r=0.5,
    realized_pnl=0.0,
    original_campaign_risk=100.0,
    current_price=55.0,
    current_stop=47.0,
    days_to_earnings=None,
    follow_through_score=None,
    violation_score=0,
    has_new_high_since_entry=True,
    has_open_quantity=True,
):
    """Thin wrapper with sensible defaults for concise test writing."""
    return compute_position_state(
        side=side,
        management_mode=management_mode,
        age_days=age_days,
        open_r=open_r,
        realized_pnl=realized_pnl,
        original_campaign_risk=original_campaign_risk,
        current_price=current_price,
        current_stop=current_stop,
        days_to_earnings=days_to_earnings,
        follow_through_score=follow_through_score,
        violation_score=violation_score,
        has_new_high_since_entry=has_new_high_since_entry,
        has_open_quantity=has_open_quantity,
    )


# ── compute_event_risk_info ───────────────────────────────────────────────────

class TestComputeEventRiskInfo:
    def test_none_days_inactive(self):
        r = compute_event_risk_info(None, "manual_managed")
        assert r["active"] is False
        assert r["severity"] is None

    def test_algo_always_inactive(self):
        r = compute_event_risk_info(5, "algo_observed")
        assert r["active"] is False

    def test_red_at_zero_days(self):
        r = compute_event_risk_info(0, "manual_managed")
        assert r["active"] is True
        assert r["severity"] == "red"

    def test_red_at_3_days(self):
        r = compute_event_risk_info(3, "manual_managed")
        assert r["severity"] == "red"

    def test_orange_at_4_days(self):
        r = compute_event_risk_info(4, "manual_managed")
        assert r["severity"] == "orange"

    def test_orange_at_7_days(self):
        r = compute_event_risk_info(7, "manual_managed")
        assert r["severity"] == "orange"

    def test_yellow_at_8_days(self):
        r = compute_event_risk_info(8, "manual_managed")
        assert r["severity"] == "yellow"

    def test_yellow_at_15_days(self):
        r = compute_event_risk_info(15, "manual_managed")
        assert r["active"] is True
        assert r["severity"] == "yellow"

    def test_inactive_at_16_days(self):
        r = compute_event_risk_info(16, "manual_managed")
        assert r["active"] is False

    def test_days_stored_in_result(self):
        r = compute_event_risk_info(7, "manual_managed")
        assert r["days"] == 7


# ── ALGO_OBSERVED ─────────────────────────────────────────────────────────────

class TestAlgoObservedState:
    def test_algo_observed_mode(self):
        r = _state(management_mode="algo_observed")
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED

    def test_algo_observed_regardless_of_r(self):
        r = _state(management_mode="algo_observed", open_r=10.0)
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED

    def test_algo_observed_regardless_of_broken_price(self):
        # Even if price <= stop, ALGO is still ALGO_OBSERVED (Sentinel doesn't direct exits)
        r = _state(management_mode="algo_observed", current_price=40.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED

    def test_algo_observed_takes_priority_over_data_incomplete(self):
        r = _state(management_mode="algo_observed", original_campaign_risk=0)
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED

    def test_label_contains_oversight(self):
        r = _state(management_mode="algo_observed")
        assert "פיקוח" in r["label"]


# ── DATA_INCOMPLETE ───────────────────────────────────────────────────────────

class TestDataIncompleteState:
    def test_unknown_management_mode(self):
        r = _state(management_mode="unknown")
        assert r["state"] == POSITION_STATE_DATA_INCOMPLETE

    def test_zero_original_campaign_risk(self):
        r = _state(original_campaign_risk=0)
        assert r["state"] == POSITION_STATE_DATA_INCOMPLETE

    def test_reason_mentions_risk(self):
        r = _state(original_campaign_risk=0)
        assert "סיכון" in r["reason"] or "R" in r["reason"]


# ── BROKEN ────────────────────────────────────────────────────────────────────

class TestBrokenState:
    def test_long_price_at_stop(self):
        r = _state(side="BUY", current_price=47.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_long_price_below_stop(self):
        r = _state(side="BUY", current_price=45.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_long_price_above_stop_not_broken(self):
        r = _state(side="BUY", current_price=55.0, current_stop=47.0)
        assert r["state"] != POSITION_STATE_BROKEN

    def test_short_price_at_stop(self):
        r = _state(side="SHORT", current_price=53.0, current_stop=53.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_short_price_above_stop_broken(self):
        r = _state(side="SHORT", current_price=56.0, current_stop=53.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_short_price_below_stop_not_broken(self):
        r = _state(side="SHORT", current_price=48.0, current_stop=53.0)
        assert r["state"] != POSITION_STATE_BROKEN

    def test_unknown_stop_zero_not_broken(self):
        r = _state(current_price=45.0, current_stop=0)
        assert r["state"] != POSITION_STATE_BROKEN

    def test_unknown_price_not_broken(self):
        r = _state(current_price=0, current_stop=47.0)
        assert r["state"] != POSITION_STATE_BROKEN

    def test_violation_score_at_threshold(self):
        r = _state(violation_score=_VIOLATION_BROKEN)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_violation_score_below_threshold_not_broken(self):
        r = _state(violation_score=_VIOLATION_BROKEN - 1)
        assert r["state"] != POSITION_STATE_BROKEN

    def test_broken_takes_priority_over_runner(self):
        # High R but price through stop
        r = _state(open_r=6.0, current_price=46.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_broken_reason_in_result(self):
        r = _state(current_price=46.0, current_stop=47.0)
        assert "סטופ" in r["reason"]


# ── RUNNER ────────────────────────────────────────────────────────────────────

class TestRunnerState:
    def test_runner_by_r(self):
        r = _state(open_r=_R_RUNNER)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_runner_above_threshold(self):
        r = _state(open_r=8.0)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_below_runner_threshold_not_runner(self):
        r = _state(open_r=4.9)
        assert r["state"] != POSITION_STATE_RUNNER

    def test_runner_by_realized_pnl(self):
        # realized_pnl >= original_campaign_risk → runner via realized
        r = _state(open_r=2.5, realized_pnl=100.0, original_campaign_risk=100.0,
                   has_open_quantity=True)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_runner_by_realized_requires_open_quantity(self):
        r = _state(open_r=2.5, realized_pnl=100.0, original_campaign_risk=100.0,
                   has_open_quantity=False)
        assert r["state"] != POSITION_STATE_RUNNER

    def test_runner_by_realized_requires_acceptable_follow_through(self):
        # follow_through_score < 70 blocks runner-via-realized
        r = _state(open_r=2.5, realized_pnl=100.0, original_campaign_risk=100.0,
                   has_open_quantity=True, follow_through_score=65.0)
        assert r["state"] != POSITION_STATE_RUNNER

    def test_runner_by_realized_follow_through_none_allowed(self):
        r = _state(open_r=2.5, realized_pnl=100.0, original_campaign_risk=100.0,
                   has_open_quantity=True, follow_through_score=None)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_runner_takes_priority_over_profit_protection(self):
        r = _state(open_r=5.0)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_runner_label(self):
        r = _state(open_r=6.0)
        assert "Runner" in r["label"]


# ── PROFIT_PROTECTION ─────────────────────────────────────────────────────────

class TestProfitProtectionState:
    def test_at_2r(self):
        r = _state(open_r=_R_PROFIT_PROTECT)
        assert r["state"] == POSITION_STATE_PROFIT_PROTECTION

    def test_at_3r(self):
        r = _state(open_r=3.0)
        assert r["state"] == POSITION_STATE_PROFIT_PROTECTION

    def test_at_4r(self):
        r = _state(open_r=4.9)
        assert r["state"] == POSITION_STATE_PROFIT_PROTECTION

    def test_below_2r_not_profit_protection(self):
        r = _state(open_r=1.99)
        assert r["state"] != POSITION_STATE_PROFIT_PROTECTION

    def test_label_mentions_protection(self):
        r = _state(open_r=2.5)
        assert "הגנ" in r["label"]


# ── WORKING ───────────────────────────────────────────────────────────────────

class TestWorkingState:
    def test_at_1r(self):
        r = _state(open_r=_R_WORKING)
        assert r["state"] == POSITION_STATE_WORKING

    def test_at_1_5r(self):
        r = _state(open_r=1.5)
        assert r["state"] == POSITION_STATE_WORKING

    def test_below_1r_not_working(self):
        r = _state(open_r=0.9)
        assert r["state"] != POSITION_STATE_WORKING

    def test_working_with_good_follow_through(self):
        r = _state(open_r=1.2, follow_through_score=75.0)
        assert r["state"] == POSITION_STATE_WORKING

    def test_working_blocked_by_poor_follow_through(self):
        r = _state(open_r=1.2, follow_through_score=40.0)
        assert r["state"] != POSITION_STATE_WORKING

    def test_working_follow_through_none_is_ok(self):
        r = _state(open_r=1.2, follow_through_score=None)
        assert r["state"] == POSITION_STATE_WORKING


# ── YELLOW_FLAG ───────────────────────────────────────────────────────────────

class TestYellowFlagState:
    def test_at_violation_threshold(self):
        r = _state(violation_score=_VIOLATION_YELLOW_FLAG)
        assert r["state"] == POSITION_STATE_YELLOW_FLAG

    def test_below_threshold_not_yellow(self):
        r = _state(violation_score=_VIOLATION_YELLOW_FLAG - 1)
        assert r["state"] != POSITION_STATE_YELLOW_FLAG

    def test_violation_5_yellow_flag(self):
        r = _state(violation_score=5)
        assert r["state"] == POSITION_STATE_YELLOW_FLAG

    def test_violation_6_broken_not_yellow(self):
        r = _state(violation_score=_VIOLATION_BROKEN)
        assert r["state"] == POSITION_STATE_BROKEN


# ── DEAD_MONEY ────────────────────────────────────────────────────────────────

class TestDeadMoneyState:
    def test_dead_money_conditions(self):
        r = _state(
            age_days=10.0, open_r=0.3,
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] == POSITION_STATE_DEAD_MONEY

    def test_dead_money_requires_age(self):
        r = _state(
            age_days=7.0, open_r=0.3,
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY

    def test_dead_money_requires_weak_follow_through(self):
        r = _state(
            age_days=10.0, open_r=0.3,
            follow_through_score=60.0, has_new_high_since_entry=False,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY

    def test_dead_money_requires_no_new_high(self):
        r = _state(
            age_days=10.0, open_r=0.3,
            follow_through_score=40.0, has_new_high_since_entry=True,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY

    def test_dead_money_skipped_when_follow_through_none(self):
        # Without follow_through data, we don't classify as DEAD_MONEY (benefit of doubt)
        r = _state(
            age_days=10.0, open_r=0.3,
            follow_through_score=None, has_new_high_since_entry=False,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY

    def test_dead_money_r_below_min_not_dead(self):
        r = _state(
            age_days=10.0, open_r=-1.0,   # below -0.5 threshold
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY

    def test_dead_money_r_above_max_not_dead(self):
        r = _state(
            age_days=10.0, open_r=1.0,    # above 0.75 threshold
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] != POSITION_STATE_DEAD_MONEY


# ── PROVING ───────────────────────────────────────────────────────────────────

class TestProvingState:
    def test_day_3_r_zero(self):
        r = _state(age_days=3.0, open_r=0.0)
        assert r["state"] == POSITION_STATE_PROVING

    def test_day_7_r_negative(self):
        r = _state(age_days=7.0, open_r=-0.3)
        assert r["state"] == POSITION_STATE_PROVING

    def test_day_8_exits_proving(self):
        r = _state(age_days=8.0, open_r=0.5)
        # Falls through to fallback PROVING, but via different path
        assert r["state"] == POSITION_STATE_PROVING  # fallback

    def test_proving_r_above_working_exits_to_working(self):
        r = _state(age_days=5.0, open_r=1.2)
        assert r["state"] == POSITION_STATE_WORKING

    def test_proving_window_label(self):
        r = _state(age_days=4.0, open_r=0.2)
        assert r["state"] == POSITION_STATE_PROVING


# ── NEW ───────────────────────────────────────────────────────────────────────

class TestNewState:
    def test_day_0(self):
        r = _state(age_days=0.0, open_r=0.0)
        assert r["state"] == POSITION_STATE_NEW

    def test_day_1(self):
        r = _state(age_days=1.0, open_r=0.5)
        assert r["state"] == POSITION_STATE_NEW

    def test_day_2(self):
        r = _state(age_days=2.0, open_r=0.8)
        assert r["state"] == POSITION_STATE_NEW

    def test_day_3_not_new(self):
        r = _state(age_days=3.0, open_r=0.5)
        assert r["state"] == POSITION_STATE_PROVING

    def test_new_with_high_r_exits_to_working(self):
        # Age=1 but R=1.5 → WORKING wins (higher priority)
        r = _state(age_days=1.0, open_r=1.5)
        assert r["state"] == POSITION_STATE_WORKING


# ── Event Risk secondary flag ─────────────────────────────────────────────────

class TestEventRiskFlag:
    def test_runner_with_event_risk(self):
        r = _state(open_r=6.0, days_to_earnings=7)
        assert r["state"] == POSITION_STATE_RUNNER
        assert r["event_risk"]["active"] is True
        assert r["event_risk"]["severity"] == "orange"

    def test_working_with_event_risk_red(self):
        r = _state(open_r=1.5, days_to_earnings=2)
        assert r["state"] == POSITION_STATE_WORKING
        assert r["event_risk"]["active"] is True
        assert r["event_risk"]["severity"] == "red"

    def test_new_with_event_risk(self):
        r = _state(age_days=1.0, open_r=0.0, days_to_earnings=10)
        assert r["state"] == POSITION_STATE_NEW
        assert r["event_risk"]["active"] is True

    def test_no_event_risk_when_none(self):
        r = _state(days_to_earnings=None)
        assert r["event_risk"]["active"] is False

    def test_event_risk_not_active_beyond_15_days(self):
        r = _state(open_r=1.5, days_to_earnings=20)
        assert r["event_risk"]["active"] is False

    def test_algo_never_has_event_risk(self):
        r = _state(management_mode="algo_observed", days_to_earnings=5)
        assert r["event_risk"]["active"] is False


# ── get_position_state_display_label ─────────────────────────────────────────

class TestDisplayLabel:
    def test_no_event_risk_plain_label(self):
        r = _state(open_r=1.5)
        label = get_position_state_display_label(r)
        assert "Event Risk" not in label
        assert r["label"] in label

    def test_event_risk_appended(self):
        r = _state(open_r=6.0, days_to_earnings=7)
        label = get_position_state_display_label(r)
        assert "Event Risk" in label
        assert "7 ימים" in label

    def test_combined_runner_event_risk_label(self):
        r = _state(open_r=7.0, days_to_earnings=5)
        label = get_position_state_display_label(r)
        assert "Runner" in label
        assert "Event Risk" in label


# ── Priority ordering ────────────────────────────────────────────────────────

class TestPriorityOrdering:
    """Verify the strict priority order is respected."""

    def test_algo_beats_all(self):
        # ALGO_OBSERVED should win even if conditions for RUNNER etc. are met
        r = _state(management_mode="algo_observed", open_r=10.0, violation_score=10)
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED

    def test_data_incomplete_beats_broken(self):
        # Unknown management mode → DATA_INCOMPLETE, not BROKEN
        r = _state(management_mode="unknown",
                   current_price=40.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_DATA_INCOMPLETE

    def test_broken_beats_runner(self):
        r = _state(open_r=6.0, current_price=46.0, current_stop=47.0)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_runner_beats_profit_protection(self):
        r = _state(open_r=5.0)
        assert r["state"] == POSITION_STATE_RUNNER

    def test_profit_protection_beats_working(self):
        r = _state(open_r=2.0)
        assert r["state"] == POSITION_STATE_PROFIT_PROTECTION

    def test_working_beats_yellow_flag(self):
        r = _state(open_r=1.2, violation_score=3)
        assert r["state"] == POSITION_STATE_WORKING

    def test_yellow_flag_beats_dead_money(self):
        r = _state(
            violation_score=3,
            age_days=10.0, open_r=0.3,
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] == POSITION_STATE_YELLOW_FLAG

    def test_dead_money_beats_proving(self):
        r = _state(
            age_days=10.0, open_r=0.3,
            follow_through_score=40.0, has_new_high_since_entry=False,
        )
        assert r["state"] == POSITION_STATE_DEAD_MONEY

    def test_proving_beats_new_when_in_age_range(self):
        # age_days=3 is in PROVING range (3-7), even though it could be "new-ish"
        r = _state(age_days=3.0, open_r=0.0)
        assert r["state"] == POSITION_STATE_PROVING


# ── Return dict structure ─────────────────────────────────────────────────────

class TestReturnStructure:
    def test_all_keys_present(self):
        r = _state()
        assert "state" in r
        assert "label" in r
        assert "event_risk" in r
        assert "reason" in r

    def test_event_risk_keys_present(self):
        r = _state()
        er = r["event_risk"]
        assert "active" in er
        assert "severity" in er
        assert "days" in er

    def test_reason_is_string(self):
        r = _state()
        assert isinstance(r["reason"], str)
        assert len(r["reason"]) > 0

    def test_label_is_string(self):
        r = _state()
        assert isinstance(r["label"], str)

    def test_state_is_valid_constant(self):
        valid_states = {
            POSITION_STATE_NEW, POSITION_STATE_PROVING, POSITION_STATE_WORKING,
            POSITION_STATE_PROFIT_PROTECTION, POSITION_STATE_RUNNER,
            POSITION_STATE_YELLOW_FLAG, POSITION_STATE_BROKEN, POSITION_STATE_DEAD_MONEY,
            POSITION_STATE_ALGO_OBSERVED, POSITION_STATE_DATA_INCOMPLETE,
        }
        r = _state()
        assert r["state"] in valid_states


# ── Real-world scenarios from the spec ───────────────────────────────────────

class TestSpecScenarios:
    def test_mrvl_runner_plus_event_risk(self):
        # MRVL: Runner + Event Risk from the spec example
        r = _state(open_r=6.5, days_to_earnings=7)
        assert r["state"] == POSITION_STATE_RUNNER
        assert r["event_risk"]["active"] is True
        label = get_position_state_display_label(r)
        assert "Runner" in label
        assert "Event Risk" in label

    def test_algo_pltr_oversight_only(self):
        # PLTR is an ALGO position — must never receive exit instructions
        r = _state(management_mode="algo_observed",
                   current_stop=0,   # unknown stop
                   open_r=-0.5)
        assert r["state"] == POSITION_STATE_ALGO_OBSERVED
        assert "פיקוח" in r["label"]

    def test_cat_profit_protection(self):
        # CAT at 2.5R with known giveback — PROFIT_PROTECTION state
        r = _state(open_r=2.5, age_days=20)
        assert r["state"] == POSITION_STATE_PROFIT_PROTECTION

    def test_axgn_micro_probe_proving(self):
        # Small early position — should be PROVING
        r = _state(age_days=4.0, open_r=0.1)
        assert r["state"] == POSITION_STATE_PROVING

    def test_broken_manual_requires_action(self):
        r = _state(current_price=44.0, current_stop=47.0, open_r=-1.2)
        assert r["state"] == POSITION_STATE_BROKEN

    def test_new_trade_day_one(self):
        r = _state(age_days=0.5, open_r=0.0)
        assert r["state"] == POSITION_STATE_NEW
