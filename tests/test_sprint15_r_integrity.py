"""
Sprint-15 Wave-2 — Report R-Integrity tests (DEC-20260515-011/-012/-013).

Covers:
* Dual R via the EXISTING engine functions ONLY (compute_r_true →
  Structure R, compute_r_target → Account R) — no new R formula.
  Fixtures from the founder finding: MRVL 9.22R/3.73R, PWR 1.34R/0.89R,
  WCC 0.26R/0.11R; ALGO ⇒ Structure R = "—"/"N/A" (never 0.00R), Account
  R only.
* The pre-existing primary displayed R number is BYTE-IDENTICAL (the
  critical guard — any drift = math changed = FAIL).
* Risk Capital Basis label = NAV (Mark §2 verbatim); honest nav_source
  disclosure (AGENTS.md #1); no $ figure changed.
* Broker Reconciliation 4 bands keyed off EXISTING constants (Mark §3),
  the live $741.31 → Critical; non-asserting "cause unverified" wording.
* Mark §5 framework-only stubs define NO threshold.

All numbers asserted are produced by the two existing engine functions —
the tests fail loudly if engine_core R math is touched.
"""
import sys, os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _mod in ["telebot", "supabase", "dotenv"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import engine_core as ec
import telegram_formatters as tf


# ── Fixtures (exact, from the founder finding / SPRINT15_DESIGN §5.1) ────────
# target risk ≈ $47.53 (NAV 7921 × 0.5%). Each open_pnl / original_risk pair
# is chosen so the EXISTING compute_r_true / compute_r_target reproduce the
# founder's reported Structure / Account R exactly.
TARGET_RISK = 47.53
MRVL = {"open_pnl": 177.34, "orig_risk": 19.23, "struct": 9.22, "acct": 3.73}
PWR  = {"open_pnl": 42.30,  "orig_risk": 31.5672, "struct": 1.34, "acct": 0.89}
WCC  = {"open_pnl": 5.23,   "orig_risk": 20.1154, "struct": 0.26, "acct": 0.11}


# ── 1. Dual R produced ONLY by the two existing engine functions ────────────

def _assert_dual(fix):
    s = ec.compute_r_true(fix["open_pnl"], fix["orig_risk"])
    a = ec.compute_r_target(fix["open_pnl"], TARGET_RISK)
    assert s == fix["struct"], (s, fix)
    assert a == fix["acct"], (a, fix)
    return s, a


def test_dual_r_mrvl_structure_9_22_account_3_73():
    s, a = _assert_dual(MRVL)
    assert s == 9.22 and a == 3.73


def test_dual_r_pwr_structure_1_34_account_0_89():
    s, a = _assert_dual(PWR)
    assert s == 1.34 and a == 0.89


def test_dual_r_wcc_structure_0_26_account_0_11():
    s, a = _assert_dual(WCC)
    assert s == 0.26 and a == 0.11


def test_fmt_dual_r_uses_marks_verbatim_labels_manual():
    s, a = _assert_dual(MRVL)
    basis = tf.dual_r_basis(original_campaign_risk=MRVL["orig_risk"],
                            frozen_target_risk_usd=TARGET_RISK,
                            is_algo=False)
    assert basis["structure_valid"] and basis["account_valid"]
    assert basis["primary_basis_label"] == "structure"
    frag = tf.fmt_dual_r(s, a, structure_valid=True, account_valid=True,
                         is_algo=False)
    # Mark §1 he labels, Structure first.
    assert frag == "‏R מבנה: 9.22R | ‏R חשבון: 3.73R"
    frag_ai = tf.fmt_dual_r(s, a, structure_valid=True, account_valid=True,
                            is_algo=False, ai_copy=True)
    assert frag_ai == "Structure R: 9.22R | Account R: 3.73R"


def test_algo_structure_r_is_na_account_only_never_0_00R():
    # ALGO: no real stop ⇒ Structure R = "—"/"N/A", Account R only.
    open_pnl = 100.0
    s = ec.compute_r_true(open_pnl, 0)            # invalid orig risk → 0.0
    a = ec.compute_r_target(open_pnl, TARGET_RISK)
    basis = tf.dual_r_basis(original_campaign_risk=0,
                            frozen_target_risk_usd=TARGET_RISK,
                            is_algo=True)
    assert basis["structure_valid"] is False
    assert basis["account_valid"] is True
    assert basis["primary_basis_label"] == "account"
    frag = tf.fmt_dual_r(s, a, structure_valid=False, account_valid=True,
                         is_algo=True)
    assert "—" in frag and "אין סטופ אמיתי" in frag
    assert "0.00R" not in frag           # never present 0.0 as if real
    assert "‏R חשבון: 2.10R" in frag      # Account R still shown
    frag_ai = tf.fmt_dual_r(s, a, structure_valid=False, account_valid=True,
                            is_algo=True, ai_copy=True)
    assert "Structure R: N/A (no real stop)" in frag_ai
    assert "0.00R" not in frag_ai


def test_manual_missing_original_risk_no_silent_basis_swap():
    # Manual, missing initial stop ⇒ Structure R = "—" + reason, NOT
    # silently swapped to Account basis.
    open_pnl = 60.0
    basis = tf.dual_r_basis(original_campaign_risk=0,
                            frozen_target_risk_usd=TARGET_RISK,
                            is_algo=False)
    assert basis["structure_valid"] is False
    frag = tf.fmt_dual_r(0.0, ec.compute_r_target(open_pnl, TARGET_RISK),
                         structure_valid=False, account_valid=True,
                         is_algo=False)
    assert "חסר סטופ התחלתי" in frag
    assert "0.00R" not in frag


def test_both_unavailable_returns_r_unavailable():
    frag = tf.fmt_dual_r(0.0, 0.0, structure_valid=False,
                         account_valid=False, is_algo=False)
    assert frag == "‏R לא זמין"
    frag_ai = tf.fmt_dual_r(0.0, 0.0, structure_valid=False,
                            account_valid=False, is_algo=False,
                            ai_copy=True)
    assert frag_ai == "R unavailable"


# ── 2. Byte-identical guard (THE critical one — drift = math changed) ────────

def test_primary_open_r_byte_identical_to_pre_change_formula():
    """The primary displayed number must equal the pre-change inline
    expression. Manual primary = open_pnl/original_campaign_risk (==
    compute_r_true); ALGO primary = open_pnl/target_risk (== compute_r_target).
    Any divergence here = engine_core math edited = FAIL the gate."""
    for fix in (MRVL, PWR, WCC):
        pre_change_manual = round(fix["open_pnl"] / fix["orig_risk"], 2)
        assert ec.compute_r_true(fix["open_pnl"], fix["orig_risk"]) == pre_change_manual
    pre_change_algo = round(100.0 / TARGET_RISK, 2)
    assert ec.compute_r_target(100.0, TARGET_RISK) == pre_change_algo


def test_engine_r_functions_unchanged_contract():
    # compute_r_true/compute_r_target guards must still return 0.0 on invalid
    # (the display layer maps that to "—", never 0.00R).
    assert ec.compute_r_true(100.0, 0) == 0.0
    assert ec.compute_r_true(100.0, -5) == 0.0
    assert ec.compute_r_target(100.0, 0) == 0.0
    assert ec.compute_r_target(100.0, -5) == 0.0


def test_fmt_position_card_byte_identical_without_dual_r_kwarg():
    """Default dual_r_fragment=None ⇒ card is byte-identical to pre-change
    (the new kwarg must not perturb any existing caller)."""
    base_kwargs = dict(i=1, sym="MRVL", setup="VCP", days_held=5,
                       curr=80.0, entry=70.0, open_pnl=177.34,
                       pos_value=8000.0, weight_pct=12.3,
                       total_pos_profit=200.0, total_campaign_r=9.22,
                       open_r_val=9.22, status="🟢 OK", action_short="HOLD")
    no_kwarg = tf.fmt_position_card(**base_kwargs)
    explicit_none = tf.fmt_position_card(**base_kwargs, dual_r_fragment=None)
    assert no_kwarg == explicit_none
    assert "(צף `+9.22R`)" in no_kwarg          # pre-change open fragment kept
    # With a dual fragment the PRIMARY campaign-R token is byte-identical;
    # only the open sub-fragment is replaced.
    with_dual = tf.fmt_position_card(**base_kwargs,
                                     dual_r_fragment="‏R מבנה: 9.22R | ‏R חשבון: 3.73R")
    assert "`+9.22R`" in with_dual               # primary token unchanged
    assert "‏R מבנה: 9.22R | ‏R חשבון: 3.73R" in with_dual
    assert "(צף `+9.22R`)" not in with_dual      # silent fragment replaced


# ── 3. Risk Capital Basis label (Mark §2 verbatim, no $ change) ─────────────

def test_basis_label_is_nav_when_nav_source_broker():
    line = tf.fmt_risk_capital_basis(7921.0, 47.53, nav_source="broker")
    assert line == "‏בסיס הון לסיכון: NAV ($7,921) — סיכון יעד $47.53"
    ai = tf.fmt_risk_capital_basis(7921.0, 47.53, nav_source="broker",
                                   ai_copy=True)
    assert ai == "Risk Capital Basis: NAV ($7,921) — target risk $47.53"


def test_basis_label_discloses_fallback_when_nav_source_not_broker():
    line = tf.fmt_risk_capital_basis(7500.0, 37.50, nav_source="fallback")
    assert "NAV ($7,500)" in line
    assert "מקור NAV: fallback" in line          # honest disclosure (AGENTS #1)
    ai = tf.fmt_risk_capital_basis(7500.0, 37.50, nav_source="deposited",
                                   ai_copy=True)
    assert "NAV source: deposited — not live broker NAV" in ai


def test_basis_label_changes_no_dollar_figure():
    # The label only restates the inputs; it never recomputes them.
    nav, tr = 7921.08, 47.5265
    line = tf.fmt_risk_capital_basis(nav, tr, nav_source="broker", ai_copy=True)
    assert f"${nav:,.0f}" in line and f"${tr:.2f}" in line


# ── 4. Broker Reconciliation bands (Mark §3, no invented numbers) ──────────

def test_recon_live_founder_case_is_critical():
    # 7921.08 − (7500 + (−320.23) + 0) = 741.31  → Critical
    gap = 7921.08 - (7500.0 + (-320.23) + 0.0)
    assert round(gap, 2) == 741.31
    st = tf.classify_broker_reconciliation(
        7921.08, 7500.0, -320.23, reconciliation_gap=gap,
        risk_pct_input=0.5, nav_source="broker")
    assert st["band"] == "Critical Data Gap"
    assert st["gap"] == 741.31


def test_recon_band_boundaries_keyed_off_existing_constants():
    # unit = 7500 * 0.5/100 = 37.50 (one target-risk unit); 5*unit = 187.50
    f = lambda g: tf.classify_broker_reconciliation(
        7921.0, 7500.0, 0.0, reconciliation_gap=g, risk_pct_input=0.5,
        nav_source="broker")["band"]
    assert f(10.0) == "Balanced"                 # $10 production constant
    assert f(10.01) == "Minor Difference"
    assert f(37.50) == "Minor Difference"        # exactly one unit
    assert f(37.51) == "Material Gap"
    assert f(187.50) == "Material Gap"           # exactly 5*unit
    assert f(187.51) == "Critical Data Gap"      # > 5R anchor


def test_recon_critical_when_gap_exceeds_open_campaign_risk():
    # Inside the 5R anchor but > a single open-campaign original risk ⇒ Critical
    st = tf.classify_broker_reconciliation(
        7921.0, 7500.0, 0.0, reconciliation_gap=50.0, risk_pct_input=0.5,
        nav_source="broker", max_open_campaign_risk=19.23)
    assert st["band"] == "Critical Data Gap"


def test_recon_states_cause_unverified_never_asserts_single_cause():
    st = tf.classify_broker_reconciliation(
        7921.08, 7500.0, -320.23, reconciliation_gap=741.31,
        risk_pct_input=0.5, nav_source="broker")
    he = tf.fmt_broker_reconciliation(st)
    ai = tf.fmt_broker_reconciliation(st, ai_copy=True)
    # Mark §3 verbatim non-asserting wording.
    assert "הסיבה לא אומתה" in he and "דורש אימות ידני" in he
    assert "חלון דיווח YTD" in he
    assert "Cause unverified" in ai and "Manual verification required" in ai
    assert "YTD report window" in ai
    # The forbidden asserted-cause phrasing must NOT appear.
    assert "Unrecorded Legacy PnL" not in he and "Unrecorded Legacy PnL" not in ai
    assert "עסקאות/הפקדות ישנות" not in he


def test_recon_caveat_when_nav_not_broker():
    st = tf.classify_broker_reconciliation(
        7500.0, 7500.0, 0.0, reconciliation_gap=5.0, risk_pct_input=0.5,
        nav_source="fallback")
    assert st["caveat"]
    he = tf.fmt_broker_reconciliation(st)
    assert "צד ה-NAV עצמו fallback" in he
    ai = tf.fmt_broker_reconciliation(st, ai_copy=True)
    assert "NAV side is itself fallback" in ai


def test_recon_reuses_passed_gap_does_not_recompute():
    # The helper must trust the passed-in gap (dashboard.py:404-405 reuse),
    # NOT derive its own from nav/base/pnl. nav=999999 would yield a huge
    # derived gap; the passed gap=5.0 must win and band must reflect it.
    st = tf.classify_broker_reconciliation(
        999999.0, 7500.0, 0.0, reconciliation_gap=5.0, risk_pct_input=0.5,
        nav_source="broker")
    assert st["gap"] == 5.0 and st["band"] == "Balanced"


# ── 5. Mark §5 framework-only — NO threshold defined ────────────────────────

def test_algo_data_quality_populated_only_from_existing_fields():
    q = tf.algo_data_quality(management_mode="algo_observed",
                             risk_basis="Target", risk_visibility_score=40,
                             init_stop=None, curr_stop=None)
    assert q["state"] == "algo_observed"
    assert q["visibility"] == 40
    assert "init_stop" in q["missing_fields"]
    assert "curr_stop" in q["missing_fields"]


def test_algo_quality_ok_is_inert_without_rules_no_threshold():
    q = tf.algo_data_quality(management_mode="algo_observed",
                             risk_basis="Target", risk_visibility_score=40)
    # No rules supplied ⇒ inert (no gate, no invented threshold).
    assert tf.algo_quality_ok(q) is True
    assert tf.algo_quality_ok(q, rules=None) is True
    # A founder-supplied rule slots in without reworking call sites.
    assert tf.algo_quality_ok(q, rules=lambda x: x["visibility"] >= 70) is False


def test_algo_dead_money_rule_is_pending_stub():
    assert tf.algo_dead_money_rule() == "pending founder rule"
    # Manual constant untouched.
    assert ec._DEAD_MONEY_MAX_R == 0.75


def test_no_invented_constants_changed():
    """Guard: the system's own constants the design pins must be unchanged."""
    assert ec._DEAD_MONEY_MAX_R == 0.75
    assert tf._RECON_EQ_THRESHOLD == 10.0        # adopted dashboard.py:411 const
    # ALGO visibility cap 40 (compute_risk_visibility_score) unchanged.
    assert ec.compute_risk_visibility_score("ALGO", 0, 100, target_risk_usd=50) == 40
