"""
Phase 5 — Anti-Spam / Alert State Table tests.

Tests _should_fire_state_alert(), STATE_ALERT_COOLDOWN, and ALERT_PRIORITY.
All tests are pure logic tests — no Telegram, no DB, no yfinance.
"""

import sys
import types
import pytest

# ── Stub heavy dependencies before importing risk_monitor ────────────────────
for mod_name in ["telebot", "supabase", "dotenv"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules["supabase"].create_client = lambda *a, **k: None  # type: ignore
sys.modules["dotenv"].load_dotenv = lambda *a, **k: None  # type: ignore

class _FakeBot:
    def __init__(self, *a, **k): pass
sys.modules["telebot"].TeleBot = _FakeBot  # type: ignore

import risk_monitor as rm

NOW = 1_700_000_000.0  # arbitrary fixed timestamp for testing


# ── _should_fire_state_alert ──────────────────────────────────────────────────

class TestShouldFireStateAlertNoCooldown:
    """States with no cooldown defined should always fire."""

    def test_new_state_fires_first_time(self):
        assert rm._should_fire_state_alert("WORKING", "", 0.0, NOW) is True

    def test_proving_no_cooldown_always_fires(self):
        # PROVING has no entry in STATE_ALERT_COOLDOWN
        assert rm._should_fire_state_alert("PROVING", "PROVING", NOW - 60, NOW) is True

    def test_profit_protection_no_cooldown_always_fires(self):
        assert rm._should_fire_state_alert("PROFIT_PROTECTION", "PROFIT_PROTECTION",
                                           NOW - 100, NOW) is True

    def test_algo_observed_no_cooldown(self):
        assert rm._should_fire_state_alert("ALGO_OBSERVED", "ALGO_OBSERVED",
                                           NOW - 30, NOW) is True


class TestShouldFireStateAlertRunnerCooldown:
    """RUNNER has 4h cooldown — re-entry within window is suppressed."""

    COOLDOWN = 4 * 3600

    def test_runner_first_entry_fires(self):
        assert rm._should_fire_state_alert("RUNNER", "", 0.0, NOW) is True

    def test_runner_from_different_prev_always_fires(self):
        # WORKING → RUNNER: different state type, always fires
        assert rm._should_fire_state_alert("RUNNER", "WORKING", NOW - 60, NOW) is True

    def test_runner_reentry_within_cooldown_suppressed(self):
        # RUNNER → WORKING → RUNNER within 3h: should NOT fire
        last_ts = NOW - (3 * 3600)  # 3h ago
        assert rm._should_fire_state_alert("RUNNER", "RUNNER", last_ts, NOW) is False

    def test_runner_reentry_after_cooldown_fires(self):
        # Same-type re-entry after 5h: should fire
        last_ts = NOW - (5 * 3600)  # 5h ago
        assert rm._should_fire_state_alert("RUNNER", "RUNNER", last_ts, NOW) is True

    def test_runner_reentry_at_exact_cooldown_fires(self):
        # Exactly at the cooldown boundary: >= cooldown → fires
        last_ts = NOW - self.COOLDOWN
        assert rm._should_fire_state_alert("RUNNER", "RUNNER", last_ts, NOW) is True

    def test_runner_reentry_one_second_before_cooldown_suppressed(self):
        last_ts = NOW - (self.COOLDOWN - 1)
        assert rm._should_fire_state_alert("RUNNER", "RUNNER", last_ts, NOW) is False


class TestShouldFireStateAlertBrokenCooldown:
    """BROKEN has 4h cooldown — prevents stop-bounce spam."""

    COOLDOWN = 4 * 3600

    def test_broken_first_entry_fires(self):
        assert rm._should_fire_state_alert("BROKEN", "", 0.0, NOW) is True

    def test_broken_from_working_fires(self):
        assert rm._should_fire_state_alert("BROKEN", "WORKING", NOW - 60, NOW) is True

    def test_broken_reentry_within_cooldown_suppressed(self):
        last_ts = NOW - (1 * 3600)
        assert rm._should_fire_state_alert("BROKEN", "BROKEN", last_ts, NOW) is False

    def test_broken_reentry_after_cooldown_fires(self):
        last_ts = NOW - (5 * 3600)
        assert rm._should_fire_state_alert("BROKEN", "BROKEN", last_ts, NOW) is True


class TestShouldFireStateAlertDeadMoneyCooldown:
    """DEAD_MONEY has 12h cooldown."""

    COOLDOWN = 12 * 3600

    def test_dead_money_first_entry_fires(self):
        assert rm._should_fire_state_alert("DEAD_MONEY", "", 0.0, NOW) is True

    def test_dead_money_reentry_within_12h_suppressed(self):
        last_ts = NOW - (6 * 3600)
        assert rm._should_fire_state_alert("DEAD_MONEY", "DEAD_MONEY", last_ts, NOW) is False

    def test_dead_money_reentry_after_12h_fires(self):
        last_ts = NOW - (13 * 3600)
        assert rm._should_fire_state_alert("DEAD_MONEY", "DEAD_MONEY", last_ts, NOW) is True

    def test_dead_money_from_broken_fires(self):
        # Different previous state always fires regardless of cooldown
        assert rm._should_fire_state_alert("DEAD_MONEY", "BROKEN", NOW - 60, NOW) is True


# ── STATE_ALERT_COOLDOWN ──────────────────────────────────────────────────────

class TestStateAlertCooldownConstants:
    def test_runner_has_4h_cooldown(self):
        assert rm.STATE_ALERT_COOLDOWN["RUNNER"] == 4 * 3600

    def test_broken_has_4h_cooldown(self):
        assert rm.STATE_ALERT_COOLDOWN["BROKEN"] == 4 * 3600

    def test_dead_money_has_12h_cooldown(self):
        assert rm.STATE_ALERT_COOLDOWN["DEAD_MONEY"] == 12 * 3600

    def test_p0_states_not_in_cooldown_table(self):
        # P0 states should never have cooldown suppression
        for state in ("ALGO_OBSERVED", "DATA_INCOMPLETE", "NEW", "PROVING",
                      "WORKING", "PROFIT_PROTECTION", "YELLOW_FLAG"):
            assert state not in rm.STATE_ALERT_COOLDOWN, \
                f"{state} unexpectedly has a cooldown"


# ── ALERT_PRIORITY ────────────────────────────────────────────────────────────

class TestAlertPriorityConstants:
    def test_p0_types_present(self):
        p0 = {k for k, v in rm.ALERT_PRIORITY.items() if v == "P0"}
        assert "stop_breach" in p0
        assert "algo_cluster_red" in p0
        assert "algo_deep_loss" in p0
        assert "risk_deviation_system" in p0

    def test_p1_types_present(self):
        p1 = {k for k, v in rm.ALERT_PRIORITY.items() if v == "P1"}
        assert "broken_state" in p1
        assert "runner_state" in p1
        assert "breakeven_protocol" in p1

    def test_p2_types_present(self):
        p2 = {k for k, v in rm.ALERT_PRIORITY.items() if v == "P2"}
        assert "profit_checkpoint" in p2
        assert "giveback_tighten" in p2

    def test_p3_types_present(self):
        p3 = {k for k, v in rm.ALERT_PRIORITY.items() if v == "P3"}
        assert "dead_money_state" in p3
        assert "algo_visibility" in p3
        assert "adaptive_risk" in p3

    def test_all_values_are_valid_priority(self):
        valid = {"P0", "P1", "P2", "P3"}
        for key, val in rm.ALERT_PRIORITY.items():
            assert val in valid, f"{key} has invalid priority {val}"

    def test_runner_state_is_p1(self):
        assert rm.ALERT_PRIORITY["runner_state"] == "P1"

    def test_broken_state_is_p1(self):
        assert rm.ALERT_PRIORITY["broken_state"] == "P1"

    def test_dead_money_is_p3(self):
        assert rm.ALERT_PRIORITY["dead_money_state"] == "P3"


# ── Integration: oscillation scenario ────────────────────────────────────────

class TestOscillationScenario:
    """Simulate a price that oscillates between RUNNER and WORKING states."""

    def test_runner_working_runner_cycle_within_4h_fires_once(self):
        """
        Cycle: first RUNNER entry fires.
        Then WORKING (different state) would fire (not tested here — that state
        has no cooldown and is a different type).
        Then RUNNER re-entry within 4h: SUPPRESSED.
        """
        t0 = NOW
        # 1st RUNNER entry (fresh position, no prev alert)
        assert rm._should_fire_state_alert("RUNNER", "", 0.0, t0) is True

        # 2h later: position dips to WORKING, re-enters RUNNER
        t1 = t0 + 2 * 3600
        # "RUNNER" re-entered — prev_type was RUNNER from 2h ago
        assert rm._should_fire_state_alert("RUNNER", "RUNNER", t0, t1) is False

    def test_broken_bounce_scenario(self):
        """Price crosses stop, bounces above, crosses again within 2h — second alert suppressed."""
        t0 = NOW
        # First BROKEN entry
        assert rm._should_fire_state_alert("BROKEN", "WORKING", t0 - 60, t0) is True

        # 2h later: price bounced above stop (WORKING), then drops below again
        t1 = t0 + 2 * 3600
        assert rm._should_fire_state_alert("BROKEN", "BROKEN", t0, t1) is False

    def test_broken_fires_again_after_full_day(self):
        """If position recovers for >4h and breaks down again, should re-alert."""
        t0 = NOW
        t1 = t0 + 5 * 3600  # 5h later
        assert rm._should_fire_state_alert("BROKEN", "BROKEN", t0, t1) is True
