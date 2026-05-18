"""Phase ALGO-3 acceptance suite — T-B-1 (classifier honors `stop_loss` fallback).

Authoritative spec: docs/teams/PHASE_ALGO3_SCOPE.md (governs).
Confirmed defect: docs/teams/ALGO_INVESTIGATION_4.md — `compute_closed_campaigns`
derived `original_campaign_risk` from `initial_stop` ONLY; when that field is
absent / <=0 / >= base_price it set risk=0 ⇒ DATA_INCOMPLETE ⇒ the campaign was
silently dropped from S9/M21/L50/WR/Expectancy/Heat/the 4-gate, EVEN WHEN the
documented `stop_loss` field (DATA_CONTRACTS.md:25) carried a perfectly valid
stop (the live AXGN_9394908015 class).

T-B-1 fix (additive, precedence-preserving): `initial_stop` stays the FIRST,
UNCHANGED source; `stop_loss` is a documented FALLBACK used ONLY when
`initial_stop` does not yield a valid basis, under the IDENTICAL validity guard
(`> 0 and < base_price`) so a garbage/invalid `stop_loss` can never fabricate a
fake risk basis.

These tests ONLY ADD coverage — no existing test is deleted or weakened
(Mark 6.1). They pin EXACTLY the scope §"Separate acceptance tests":

  1. initial_stop-valid ⇒ risk basis + bucket byte-identical to pre-fix, and a
     supplied stop_loss does NOT change it (the PRECEDENCE proof).
  2. initial_stop invalid/absent + a VALID stop_loss ⇒ now countable
     (the AXGN-class recovery; was DATA_INCOMPLETE).
  3. no valid stop anywhere ⇒ still DATA_INCOMPLETE (the 6-class; no false
     recovery).
  4. garbage stop_loss (<=0 / >= base_price) with invalid initial_stop ⇒
     rejected, still DATA_INCOMPLETE.
  5. an ALGO campaign with initial_stop == -1 + any stop_loss ⇒ still
     ALGO_OBSERVED / excluded (the -1 sentinel fails the >0 guard; ALGO is
     bucket/setup filtered regardless) — no recovery into a manual stat.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import adaptive_risk_engine as are
import engine_core as ec


# ── fixtures ────────────────────────────────────────────────────────────────

def _campaign_df(*, cid="c1", symbol="AXGN", setup_type="VCP",
                 base_price=100.0, qty=10.0,
                 initial_stop=None, stop_loss=None):
    """A minimal fully-closed single-day campaign (one BUY then one SELL of
    the full quantity). `initial_stop` / `stop_loss` are attached to the BUY
    row only when provided (absent column ⇒ `.get(..., 0)` default path).

    The side split keys ONLY on the `side` string (engine_core.split_side_first
    / DATA_CONTRACTS.md:48); `quantity` is magnitude-only. SELL pnl is +1.0 so
    the campaign is a win (irrelevant to the risk-basis assertions but keeps
    is_win deterministic).
    """
    buy = {
        "campaign_id": cid, "symbol": symbol, "setup_type": setup_type,
        "side": "BUY", "trade_date": "2026-03-01",
        "quantity": qty, "price": base_price, "pnl_usd": 0.0,
    }
    sell = {
        "campaign_id": cid, "symbol": symbol, "setup_type": setup_type,
        "side": "SELL", "trade_date": "2026-03-05",
        "quantity": qty, "price": base_price + 5.0, "pnl_usd": 50.0,
    }
    if initial_stop is not None:
        buy["initial_stop"] = initial_stop
    if stop_loss is not None:
        buy["stop_loss"] = stop_loss
    return pd.DataFrame([buy, sell])


def _only(trades_df):
    """compute_closed_campaigns on a single-campaign df ⇒ the one dict."""
    closed = are.compute_closed_campaigns(trades_df)
    assert len(closed) == 1, f"expected exactly 1 closed campaign, got {closed}"
    return closed[0]


# ════════════════════════════════════════════════════════════════════════════
# Case 1 — PRECEDENCE proof: initial_stop is FIRST and UNCHANGED
# ════════════════════════════════════════════════════════════════════════════

class TestCase1InitialStopPrecedenceByteIdentical:
    def test_initial_stop_valid_yields_exact_prefix_risk_and_bucket(self):
        """A valid `initial_stop` campaign produces EXACTLY the pre-fix risk
        `(base_price - initial_stop) * qty` and a stat-countable bucket — the
        fallback branch is never reached."""
        c = _only(_campaign_df(base_price=100.0, qty=10.0, initial_stop=90.0))
        # pre-fix math, unchanged: (100 - 90) * 10 = 100.0
        assert c["original_campaign_risk"] == 100.0
        assert c["stat_bucket"] == "VCP_MANUAL"
        assert ec.is_stat_countable(c["stat_bucket"]) is True

    def test_valid_initial_stop_ignores_any_stop_loss_value(self):
        """Precedence: when `initial_stop` is valid, the risk basis is
        IDENTICAL regardless of ANY `stop_loss` value supplied (a different
        valid one, a garbage one, or none) — the fallback never fires."""
        base = _only(_campaign_df(base_price=100.0, qty=10.0,
                                  initial_stop=90.0))
        for sl in (50.0, 95.0, 0.0, -1.0, 100.0, 200.0):
            c = _only(_campaign_df(base_price=100.0, qty=10.0,
                                   initial_stop=90.0, stop_loss=sl))
            assert c["original_campaign_risk"] == base["original_campaign_risk"]
            assert c["original_campaign_risk"] == 100.0
            assert c["stat_bucket"] == base["stat_bucket"] == "VCP_MANUAL"


# ════════════════════════════════════════════════════════════════════════════
# Case 2 — AXGN-class recovery: invalid/absent initial_stop + valid stop_loss
# ════════════════════════════════════════════════════════════════════════════

class TestCase2StopLossFallbackRecovery:
    def test_absent_initial_stop_valid_stop_loss_now_countable(self):
        """No `initial_stop` column at all + a valid `stop_loss` ⇒ the
        documented fallback produces a positive risk and the campaign becomes
        stat-countable (was DATA_INCOMPLETE before T-B-1)."""
        c = _only(_campaign_df(base_price=100.0, qty=10.0,
                               initial_stop=None, stop_loss=92.0))
        # fallback math: (100 - 92) * 10 = 80.0
        assert c["original_campaign_risk"] == 80.0
        assert c["stat_bucket"] == "VCP_MANUAL"
        assert ec.is_stat_countable(c["stat_bucket"]) is True

    def test_invalid_initial_stop_valid_stop_loss_now_countable(self):
        """`initial_stop` present but invalid (>= base_price) + valid
        `stop_loss` ⇒ fallback recovers a positive risk ⇒ countable."""
        c = _only(_campaign_df(base_price=100.0, qty=10.0,
                               initial_stop=150.0, stop_loss=92.0))
        assert c["original_campaign_risk"] == 80.0
        assert c["stat_bucket"] == "VCP_MANUAL"
        assert ec.is_stat_countable(c["stat_bucket"]) is True

    def test_zero_initial_stop_valid_stop_loss_now_countable(self):
        """`initial_stop == 0` (the common 'not recorded' sentinel) + valid
        `stop_loss` ⇒ AXGN-class recovery."""
        c = _only(_campaign_df(base_price=50.0, qty=20.0,
                               initial_stop=0.0, stop_loss=45.0))
        # (50 - 45) * 20 = 100.0
        assert c["original_campaign_risk"] == 100.0
        assert ec.is_stat_countable(c["stat_bucket"]) is True


# ════════════════════════════════════════════════════════════════════════════
# Case 3 — no valid stop anywhere ⇒ still DATA_INCOMPLETE (no false recovery)
# ════════════════════════════════════════════════════════════════════════════

class TestCase3NoStopStaysDataIncomplete:
    def test_no_initial_stop_no_stop_loss_stays_data_incomplete(self):
        """Neither field present (the genuinely-stopless 6-class) ⇒ risk 0.0
        ⇒ DATA_INCOMPLETE ⇒ NOT stat-countable. No false recovery."""
        c = _only(_campaign_df(base_price=100.0, qty=10.0,
                               initial_stop=None, stop_loss=None))
        assert c["original_campaign_risk"] == 0.0
        assert c["stat_bucket"] == ec.STAT_BUCKET_DATA_INCOMPLETE
        assert ec.is_stat_countable(c["stat_bucket"]) is False

    def test_both_fields_zero_stays_data_incomplete(self):
        """Both fields present but zero (no stop logged in either) ⇒ still
        DATA_INCOMPLETE — the fallback guard rejects 0."""
        c = _only(_campaign_df(base_price=100.0, qty=10.0,
                               initial_stop=0.0, stop_loss=0.0))
        assert c["original_campaign_risk"] == 0.0
        assert c["stat_bucket"] == ec.STAT_BUCKET_DATA_INCOMPLETE
        assert ec.is_stat_countable(c["stat_bucket"]) is False


# ════════════════════════════════════════════════════════════════════════════
# Case 4 — garbage stop_loss is rejected by the IDENTICAL validity guard
# ════════════════════════════════════════════════════════════════════════════

class TestCase4GarbageStopLossRejected:
    def test_stop_loss_at_or_above_base_price_rejected(self):
        """Invalid `initial_stop` + a `stop_loss` >= base_price (would imply
        a non-positive / inverted risk) ⇒ the IDENTICAL guard rejects it ⇒
        risk 0.0 ⇒ still DATA_INCOMPLETE. A garbage stop never fabricates a
        fake basis."""
        for bad_sl in (100.0, 150.0):  # == base_price, > base_price
            c = _only(_campaign_df(base_price=100.0, qty=10.0,
                                   initial_stop=0.0, stop_loss=bad_sl))
            assert c["original_campaign_risk"] == 0.0
            assert c["stat_bucket"] == ec.STAT_BUCKET_DATA_INCOMPLETE
            assert ec.is_stat_countable(c["stat_bucket"]) is False

    def test_non_positive_stop_loss_rejected(self):
        """Invalid `initial_stop` + a `stop_loss` <= 0 ⇒ rejected by the
        `> 0` half of the guard ⇒ still DATA_INCOMPLETE."""
        for bad_sl in (0.0, -1.0, -25.0):
            c = _only(_campaign_df(base_price=100.0, qty=10.0,
                                   initial_stop=150.0, stop_loss=bad_sl))
            assert c["original_campaign_risk"] == 0.0
            assert c["stat_bucket"] == ec.STAT_BUCKET_DATA_INCOMPLETE
            assert ec.is_stat_countable(c["stat_bucket"]) is False


# ════════════════════════════════════════════════════════════════════════════
# Case 5 — ALGO -1 sentinel + any stop_loss ⇒ still ALGO_OBSERVED / excluded
# ════════════════════════════════════════════════════════════════════════════

class TestCase5AlgoSentinelNotRecovered:
    def test_algo_initial_stop_minus_one_any_stop_loss_stays_algo_observed(self):
        """An ALGO campaign with `initial_stop == -1` (the ALGO sentinel)
        plus ANY `stop_loss` value MUST stay ALGO_OBSERVED and excluded:
          * the -1 sentinel fails the `> 0` guard for `initial_stop`;
          * AND ALGO is bucket/setup filtered in classify_stat_bucket
            (is_algo_position) BEFORE risk is consulted, so it can never
            become a countable manual stat campaign regardless of the
            fallback.
        """
        for sl in (None, 0.0, -1.0, 92.0, 95.0, 200.0):
            c = _only(_campaign_df(symbol="HOOD", setup_type="ALGO",
                                   base_price=100.0, qty=10.0,
                                   initial_stop=-1.0, stop_loss=sl))
            assert c["stat_bucket"] == ec.STAT_BUCKET_ALGO
            assert ec.is_stat_countable(c["stat_bucket"]) is False
            assert c["setup_type"] == "ALGO"

    def test_manual_initial_stop_minus_one_falls_back_to_stop_loss(self):
        """Defensive precedence detail: a MANUAL campaign with
        `initial_stop == -1` (fails the `> 0` guard) + a VALID `stop_loss`
        DOES recover via the fallback (this is correct — only the ALGO
        SENTINEL must stay excluded, and that exclusion is enforced by the
        ALGO setup filter, not by the -1 value)."""
        c = _only(_campaign_df(symbol="AXGN", setup_type="VCP",
                               base_price=100.0, qty=10.0,
                               initial_stop=-1.0, stop_loss=92.0))
        assert c["original_campaign_risk"] == 80.0
        assert c["stat_bucket"] == "VCP_MANUAL"
        assert ec.is_stat_countable(c["stat_bucket"]) is True
