"""
Tests for addon_risk_engine.py — Add-On / Pyramid Risk Validation Engine
Test cases 1-8 as specified in the Add-On / Pyramid Risk Engine Specification.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import addon_risk_engine as are

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_lot_state(
    base_price=100.0, base_qty=10.0, current_qty=10.0,
    stop_loss=104.0,   # raised stop → locks profit
    initial_stop=96.0, realized_pnl=0.0, current_price=110.0,
    setup_type="EP",
) -> dict:
    return are.compute_campaign_lot_state(
        base_price=base_price, base_qty=base_qty, current_qty=current_qty,
        stop_loss=stop_loss, initial_stop=initial_stop,
        realized_pnl_usd=realized_pnl, current_price=current_price,
        setup_type=setup_type,
    )


# ── Test Case 1: Approved — small add, stop leaves campaign profitable ─────────

class TestCase1ApprovedSmallAdd:
    """
    Original: 10 shares at $100, initial stop $96, original risk $40.
    Current stop raised to $104, locking $40 profit.
    Proposed add: 5 shares at $110, stop at $104.
    Add risk: 5 * $6 = $30. Campaign result if stopped: $40 - $30 = +$10.
    Expected: APPROVED.
    """
    def setup_method(self):
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96, current_price=110,
        )
        self.plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=110, add_stop=104,
            add_type=are.ADDON_TACTICAL, quantity=5,
            add_reason="PULLBACK_TO_MA10",
        )

    def test_status_approved(self):
        assert self.plan["status"] == are.APPROVED

    def test_result_if_stopped_positive(self):
        # locked = (104-100)*10 = $40, add risk = 5*(110-104) = $30
        # result = $40 - $30 = +$10
        assert self.plan["result_if_stopped"] > 0

    def test_no_blocking_reasons(self):
        assert len(self.plan["blocks"]) == 0

    def test_add_qty_accepted(self):
        assert self.plan["proposed_qty"] == 5

    def test_open_r_computed(self):
        # open_r = (110 - 100) * 10 / 40 = 2.5R
        assert self.lot_state["open_r"] == pytest.approx(2.5)


# ── Test Case 2: Blocked — add too large, stop creates campaign loss ───────────

class TestCase2BlockedLargeAdd:
    """
    Same original position (locked $40 profit).
    Proposed bad add: 10 shares at $110, stop at $104.
    Add risk: 10 * $6 = $60. Campaign result: $40 - $60 = -$20.
    -$20 < -25% of original risk ($40) = -$10 → BLOCKED.
    Expected: BLOCKED.
    """
    def setup_method(self):
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96, current_price=110,
        )
        self.plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=110, add_stop=104,
            add_type=are.ADDON_TACTICAL, quantity=10,
        )

    def test_status_blocked(self):
        assert self.plan["status"] == are.BLOCKED

    def test_result_if_stopped_below_hard_floor(self):
        # result = $40 - $60 = -$20, hard floor = -25% * $40 = -$10
        assert self.plan["result_if_stopped"] < self.plan["hard_floor_usd"]

    def test_blocking_reason_present(self):
        assert len(self.plan["blocks"]) > 0

    def test_max_qty_lower_than_10(self):
        sizing = are.compute_addon_sizing(self.lot_state, 110, 104)
        # available = $40, risk_per = $6, raw_max = floor(40/6) = 6
        # BUT safety cap: 50% of current_qty = floor(10*0.5) = 5
        # max_qty = min(6, 10, 5) = 5
        assert sizing["max_qty"] == 5


# ── Test Case 3: Tactical stop hit — close add-on only ────────────────────────

class TestCase3TacticalStopHit:
    """
    Runner position with tactical add. Tactical add stop is hit.
    Expected: close add-on only, keep original if runner stop intact.
    This tests stop mode selection.
    """
    def setup_method(self):
        # Runner: stop already well above entry, lots of locked profit
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=5,  # partial sell done
            stop_loss=118, initial_stop=96, realized_pnl=150.0,
            current_price=130,
        )

    def test_tactical_add_gets_layered_stop(self):
        stop_mode = are.recommend_stop_mode(are.ADDON_TACTICAL, self.lot_state)
        assert stop_mode["mode"] == are.STOP_LAYERED

    def test_layered_stop_closes_addon_only(self):
        stop_mode = are.recommend_stop_mode(are.ADDON_TACTICAL, self.lot_state)
        assert "הוספה בלבד" in stop_mode["description"] or "ההוספה" in stop_mode["description"]

    def test_plan_shows_layered_stop(self):
        plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=130, add_stop=120,
            add_type=are.ADDON_TACTICAL, quantity=2,
        )
        assert plan["stop_mode"] == are.STOP_LAYERED


# ── Test Case 4: Campaign stop hit — close all lots ───────────────────────────

class TestCase4CampaignStopHit:
    """
    Campaign (not tactical) add-on. Campaign stop is hit.
    Expected: close all lots message (unified stop mode).
    """
    def setup_method(self):
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96, current_price=112,
        )

    def test_campaign_add_gets_unified_stop(self):
        stop_mode = are.recommend_stop_mode(are.ADDON_CAMPAIGN, self.lot_state)
        assert stop_mode["mode"] == are.STOP_UNIFIED

    def test_plan_shows_unified_stop(self):
        plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=112, add_stop=105,
            add_type=are.ADDON_CAMPAIGN, quantity=3,
        )
        assert plan["stop_mode"] == are.STOP_UNIFIED


# ── Test Case 5: Missing initial_stop → MANUAL_REVIEW_REQUIRED ───────────────

class TestCase5MissingStop:
    """
    Position with initial_stop = 0 (not set in Supabase).
    Expected: MANUAL_REVIEW_REQUIRED — cannot compute campaign risk.
    """
    def setup_method(self):
        # initial_stop = 0 → data_complete = False
        self.lot_state = are.compute_campaign_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=0,  # missing!
            realized_pnl_usd=0, current_price=112,
        )

    def test_data_not_complete(self):
        assert self.lot_state["data_complete"] is False

    def test_original_risk_zero(self):
        assert self.lot_state["original_risk_usd"] == 0.0

    def test_eligibility_returns_manual_review(self):
        result = are.check_addon_eligibility(self.lot_state)
        assert result["status"] == are.MANUAL_REVIEW

    def test_plan_returns_manual_review(self):
        plan = are.compute_addon_plan(self.lot_state, add_entry=112, add_stop=105)
        assert plan.get("status") == are.MANUAL_REVIEW or not plan["ok"]


# ── Test Case 6: ALGO position → no manual add-on ─────────────────────────────

class TestCase6AlgoBlocked:
    """
    ALGO-managed position. No manual add-on should be recommended.
    Expected: BLOCKED with clear reason.
    """
    def setup_method(self):
        self.lot_state = are.compute_campaign_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96,
            realized_pnl_usd=0, current_price=112,
            setup_type="ALGO",
        )

    def test_is_algo_flagged(self):
        assert self.lot_state["is_algo"] is True

    def test_eligibility_blocked(self):
        result = are.check_addon_eligibility(self.lot_state)
        assert result["status"] == are.BLOCKED

    def test_block_reason_mentions_algo(self):
        result = are.check_addon_eligibility(self.lot_state)
        assert any("ALGO" in b or "אלגו" in b.lower() for b in result["blocks"])

    def test_plan_blocked_for_algo(self):
        plan = are.compute_addon_plan(self.lot_state, add_entry=112, add_stop=105)
        assert plan["status"] == are.BLOCKED


# ── Test Case 7: Chase warning — extended above MA10 by >7% ───────────────────

class TestCase7ChaseWarning:
    """
    Position profitable, but stock extended >7% above MA10.
    Expected: BLOCKED or WATCH due to chase risk.
    """
    def setup_method(self):
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96, current_price=120,
        )
        # ext10 = 8% (above the 7% CHASE_EXT_LIMIT)
        self.market_features = {
            "ext10": 8.0,
            "ext20": 12.0,
            "close_below_ma20": False,
            "regime_ok": True,
            "rs_spy_ok": True,
        }

    def test_chase_causes_block(self):
        result = are.check_addon_eligibility(
            self.lot_state,
            add_reason="MANUAL",
            market_features=self.market_features,
        )
        assert result["status"] in (are.BLOCKED, are.WATCH)

    def test_chase_block_reason_present(self):
        result = are.check_addon_eligibility(
            self.lot_state,
            add_reason="MANUAL",
            market_features=self.market_features,
        )
        assert any("MA10" in b or "Chase" in b or "מורחב" in b for b in result["blocks"])

    def test_plan_blocked_when_extended(self):
        plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=120, add_stop=110,
            market_features=self.market_features,
        )
        assert plan["status"] == are.BLOCKED


# ── Test Case 8: Add-on must be a lot, not a separate trade ───────────────────

class TestCase8AddOnNotSeparateTrade:
    """
    Verifies that add-on quantity is associated with the same campaign.
    The engine should flag when the add is larger than original (treated as new trade).
    """
    def setup_method(self):
        self.lot_state = make_lot_state(
            base_price=100, base_qty=10, current_qty=10,
            stop_loss=104, initial_stop=96, current_price=110,
        )

    def test_add_larger_than_original_is_capped(self):
        """Add-on quantity > original quantity is blocked by sizing cap."""
        sizing = are.compute_addon_sizing(self.lot_state, add_entry=110, add_stop=104)
        # max_qty capped at min(original_qty=10, 50% current=5, available/risk)
        # available = $40, risk/share = $6 → raw_max = 6; cap_current = 5
        assert sizing["max_qty"] <= 5

    def test_plan_blocks_quantity_exceeding_max(self):
        """If user requests 20 shares (2x original), plan must block it."""
        plan = are.compute_addon_plan(
            self.lot_state,
            add_entry=110, add_stop=104,
            add_type=are.ADDON_TACTICAL, quantity=20,
        )
        assert plan["status"] == are.BLOCKED
        assert any("חורגת" in b or "מקסימום" in b for b in plan["blocks"])


# ── Additional unit tests for compute_campaign_lot_state ─────────────────────

class TestLotStateComputation:
    def test_locked_profit_when_stop_above_entry(self):
        state = make_lot_state(base_price=100, stop_loss=108, current_price=115)
        # locked = (108 - 100) * 10 = $80
        assert state["locked_profit_usd"] == pytest.approx(80.0)

    def test_open_risk_when_stop_below_entry(self):
        state = make_lot_state(base_price=100, stop_loss=94, current_price=110)
        # open_risk = (100 - 94) * 10 = $60
        assert state["open_risk_usd"] == pytest.approx(60.0)

    def test_net_result_if_stop_hit_breakeven(self):
        # stop = entry → no gain no loss, no realized pnl
        state = make_lot_state(base_price=100, stop_loss=100, current_price=110)
        assert state["net_result_if_stop_hit"] == pytest.approx(0.0)

    def test_net_result_includes_realized(self):
        state = make_lot_state(
            base_price=100, stop_loss=104, current_price=110,
            realized_pnl=50.0,
        )
        # net = 50 + (104-100)*10 = 50 + 40 = $90
        assert state["net_result_if_stop_hit"] == pytest.approx(90.0)

    def test_original_risk_correct(self):
        state = make_lot_state(base_price=100, base_qty=10, initial_stop=96)
        # (100 - 96) * 10 = $40
        assert state["original_risk_usd"] == pytest.approx(40.0)

    def test_open_r_correct(self):
        # open_pnl = (110 - 100) * 10 = $100, orig_risk = $40
        state = make_lot_state(base_price=100, initial_stop=96, current_price=110)
        assert state["open_r"] == pytest.approx(2.5)


# ── Additional unit tests for compute_addon_sizing ────────────────────────────

class TestAddonSizing:
    def test_sizing_formula_basic(self):
        lot_state = make_lot_state(
            base_price=100, base_qty=10, stop_loss=104, initial_stop=96,
            realized_pnl=0, current_price=110,
        )
        sizing = are.compute_addon_sizing(lot_state, add_entry=110, add_stop=104)
        # available = locked(40) + realized(0) - buffer(0) = 40
        # risk_per_share = 6, raw_max = floor(40/6) = 6
        # cap_current = floor(10 * 0.5) = 5
        # max_qty = min(6, 10, 5) = 5
        assert sizing["available_risk"] == pytest.approx(40.0)
        assert sizing["max_qty"] == 5

    def test_sizing_with_desired_buffer(self):
        lot_state = make_lot_state(
            base_price=100, base_qty=10, stop_loss=104, initial_stop=96,
            current_price=110,
        )
        sizing = are.compute_addon_sizing(lot_state, add_entry=110, add_stop=104,
                                          desired_buffer_usd=20.0)
        # available = 40 - 20 = 20, risk_per = 6, raw_max = 3
        assert sizing["available_risk"] == pytest.approx(20.0)
        assert sizing["max_qty"] == 3

    def test_zero_available_gives_zero_qty(self):
        # No locked profit, no realized
        lot_state = make_lot_state(
            base_price=100, stop_loss=96, initial_stop=96,  # stop at entry, no lock
            current_price=108,
        )
        sizing = are.compute_addon_sizing(lot_state, add_entry=108, add_stop=100)
        assert sizing["max_qty"] == 0

    def test_invalid_entry_stop_raises(self):
        lot_state = make_lot_state()
        result = are.compute_addon_sizing(lot_state, add_entry=100, add_stop=110)
        assert "error" in result
