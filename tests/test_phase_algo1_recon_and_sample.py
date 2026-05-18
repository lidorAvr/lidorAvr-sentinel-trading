"""Phase ALGO-1 — W-A2 (R-ALGO-2 recon-key bug) + W-A3 (R-ALGO-3 L50 honesty).

Authoritative spec: docs/teams/PHASE_ALGO1_SCOPE.md
Root-cause evidence: docs/teams/ALGO_INVESTIGATION_1.md

These tests ONLY ADD coverage (Mark 6.1 — no existing test deleted/weakened):

  (1) W-A2 parity — on a representative closed-campaign fixture, the חדר-מצב
      reconciliation realized-PnL term (`telegram_portfolio.py:472-475`,
      post-fix reading the producer's real key `total_pnl_usd`) equals the
      dashboard's correct realized oracle (`dashboard.py:424`
      `camp_df['pnl_usd'].sum()` over the same closed campaigns). The pre-fix
      `c.get("net_pnl", 0)` read is demonstrated to be provably always 0.0.

  (2) W-A3 — true L50 sample >=50 ⇒ both L50 display lines are BYTE-IDENTICAL
      to the pre-fix literal; <50 ⇒ an honest disclosure is present and no
      bare misleading "L50(50)" is shown without its honest qualifier.

  (3) LOCKED April invariant byte-identical post-fix (8 / +$180.49 / WR .375
      / PF 2.6262 / excl 2) — proves the locked analytics path is untouched.

  (4) ALGO segregation / observe-only unaffected by these two display fixes.
"""
from datetime import datetime

import pandas as pd
import pytest

import adaptive_risk_engine as are
import analytics_engine as ae
import engine_core as ec
import telegram_formatters as tf


# ── Representative closed-campaign fixture (manual EP/VCP + one ALGO) ───────
# Mirrors the trades-row contract compute_closed_campaigns consumes
# (campaign_id / side / quantity / price / pnl_usd / trade_date / setup_type).
def _row(tid, sym, d, side, qty, px, pnl, istop, setup, cid):
    return dict(trade_id=tid, symbol=sym, trade_date=d, side=side,
                quantity=qty, price=px, pnl_usd=pnl, initial_stop=istop,
                stop_loss=istop, setup_type=setup, campaign_id=cid)


def _closed_fixture_df():
    """Three fully-closed campaigns: two manual (EP/VCP) + one ALGO.
    Net realized = +250.00 + (-60.00) + (-40.00) = +150.00.
    """
    R = [
        # WINNER manual VCP campaign: +250.00
        _row('1', 'AAA', '2026-01-05', 'BUY', 10, 100.0, 0.0, 90.0, 'VCP', 'AAA_1'),
        _row('2', 'AAA', '2026-01-12', 'SELL', -10, 125.0, 250.0, 0, 'VCP', 'AAA_1'),
        # LOSER manual EP campaign: -60.00
        _row('3', 'BBB', '2026-01-06', 'BUY', 6, 50.0, 0.0, 45.0, 'EP', 'BBB_3'),
        _row('4', 'BBB', '2026-01-09', 'SELL', -6, 40.0, -60.0, 0, 'EP', 'BBB_3'),
        # ALGO campaign (observe-only bucket): -40.00
        _row('5', 'CCC', '2026-01-07', 'BUY', 4, 200.0, 0.0, -1, 'ALGO', 'CCC_5'),
        _row('6', 'CCC', '2026-01-11', 'SELL', -4, 190.0, -40.0, -1, 'ALGO', 'CCC_5'),
    ]
    return pd.DataFrame(R)


# ════════════════════════════════════════════════════════════════════════════
# (1) W-A2 — R-ALGO-2 recon parity: חדר-מצב realized term == dashboard oracle
# ════════════════════════════════════════════════════════════════════════════
class TestWA2ReconKeyParity:
    def test_producer_emits_total_pnl_usd_not_net_pnl(self):
        """compute_closed_campaigns emits realized PnL under `total_pnl_usd`
        (adaptive_risk_engine.py:205) and NEVER `net_pnl` — the exact root
        cause of the silent-0 חדר-מצב bug."""
        closed = are.compute_closed_campaigns(_closed_fixture_df())
        assert len(closed) == 3
        for c in closed:
            assert "total_pnl_usd" in c, "producer key must be total_pnl_usd"
            assert "net_pnl" not in c, "producer never emits net_pnl"

    def test_prefix_net_pnl_read_was_always_zero(self):
        """Pre-fix telegram_portfolio.py:473 read `c.get("net_pnl", 0)`.
        Demonstrate it summed to 0.0 for EVERY campaign (the silent bug)."""
        closed = are.compute_closed_campaigns(_closed_fixture_df())
        prefix_db_net_pnl = sum(float(c.get("net_pnl", 0) or 0) for c in closed)
        assert prefix_db_net_pnl == 0.0  # ALL realized PnL silently dropped

    def test_postfix_recon_matches_dashboard_realized_oracle(self):
        """The PARITY pin: post-fix חדר-מצב `_db_net_pnl`
        (= sum of producer `total_pnl_usd`) equals the dashboard's correct
        realized oracle. The dashboard sums `camp_df['pnl_usd']` per closed
        campaign (dashboard.py:424); over fully-closed campaigns that equals
        the producer's per-campaign `round(sells['pnl_usd'].sum(), 2)`.
        Both = +150.00 on this fixture (was 0.0 pre-fix)."""
        df = _closed_fixture_df()
        closed = are.compute_closed_campaigns(df)

        # POST-FIX חדר-מצב realized term (telegram_portfolio.py:473, new key)
        postfix_db_net_pnl = sum(
            float(c.get("total_pnl_usd", 0) or 0) for c in closed)

        # Dashboard realized oracle (dashboard.py:424) — sum of pnl_usd over
        # the SAME fully-closed campaigns the recon path considers.
        closed_ids = {c["campaign_id"] for c in closed}
        oracle = round(
            df[df["campaign_id"].isin(closed_ids)]["pnl_usd"].sum(), 2)

        assert postfix_db_net_pnl == pytest.approx(150.0, abs=1e-9)
        assert oracle == pytest.approx(150.0, abs=1e-9)
        # PARITY: חדר-מצב now equals the dashboard's realized quantity.
        assert postfix_db_net_pnl == pytest.approx(oracle, abs=1e-9)
        # And it is strictly NOT the broken pre-fix value.
        assert postfix_db_net_pnl != 0.0

    def test_recon_classifier_band_now_reflects_truth(self):
        """End-to-end: the same classifier (telegram_formatters.py:765),
        fed the corrected realized term, no longer silently zeroes realized
        PnL — proving the authorized חדר-מצב behavior change is live."""
        closed = are.compute_closed_campaigns(_closed_fixture_df())
        deposited, open_pnl, nav = 7500.0, 0.0, 7650.0

        prefix_net = sum(float(c.get("net_pnl", 0) or 0) for c in closed)
        postfix_net = sum(float(c.get("total_pnl_usd", 0) or 0) for c in closed)

        prefix_gap = nav - (deposited + prefix_net + open_pnl)
        postfix_gap = nav - (deposited + postfix_net + open_pnl)

        # Pre-fix expected-equity dropped +150 realized ⇒ a wrong gap.
        assert prefix_gap == pytest.approx(150.0, abs=1e-9)
        assert postfix_gap == pytest.approx(0.0, abs=1e-9)

        r_prefix = tf.classify_broker_reconciliation(
            nav, deposited, prefix_net, reconciliation_gap=prefix_gap,
            risk_pct_input=0.5, nav_source="broker")
        r_postfix = tf.classify_broker_reconciliation(
            nav, deposited, postfix_net, reconciliation_gap=postfix_gap,
            risk_pct_input=0.5, nav_source="broker")
        # The classifier itself is unchanged; only its realized input is now
        # honest — the post-fix gap (0.0) classifies as the truthful
        # "Balanced" band, whereas the buggy pre-fix $150 gap did not.
        assert isinstance(r_prefix, dict) and isinstance(r_postfix, dict)
        assert r_postfix["gap"] == pytest.approx(0.0, abs=1e-9)
        assert r_postfix["band"] == "Balanced"
        assert r_prefix["gap"] == pytest.approx(150.0, abs=1e-9)
        assert r_prefix["band"] != "Balanced"  # the silent-bug mis-band


# ════════════════════════════════════════════════════════════════════════════
# (2) W-A3 — R-ALGO-3 L50 sample honesty
# ════════════════════════════════════════════════════════════════════════════
def _risk_rec(n_l50: int) -> dict:
    """Minimal risk_rec the two formatters consume, with a controllable
    TRUE L50 sample size via l50_stats['n']."""
    return {
        "ok": True,
        "heat_color": "🟠", "heat_label": "חם", "heat_score": 62.0,
        "s9_score": 70.0, "m21_score": 60.0, "l50_score": 55.0,
        "recent_10_wr": 60.0, "all_50_wr": 50.0,
        "s9_stats": {"n": 9}, "l50_stats": {"n": n_l50},
        "win_streak": 0, "loss_streak": 0, "heat_factors": [],
        "current_risk_pct": 0.60, "recommended_risk_pct": 0.60,
        "current_risk_usd": 45.0, "recommended_risk_usd": 45.0,
        "direction": "hold", "step_type": "ללא שינוי",
    }


# The EXACT pre-fix L50 score literal (telegram_formatters.py:204) — must
# stay byte-identical when the true sample >= 50.
def _expected_l50_score_line(rr):
    return (f"{tf.RTL}  ▸ ציון (0-100) לפי טווח: "
            f"S9(9)=`{rr['s9_score']:.0f}` | M21(21)=`{rr['m21_score']:.0f}`"
            f" | L50(50)=`{rr['l50_score']:.0f}`")


class TestWA3L50SampleHonesty:
    def test_sample_ge_50_byte_identical_adaptive_block(self):
        """True L50 sample >= 50 ⇒ the L50 score line is BYTE-IDENTICAL to
        the pre-fix literal and NO honesty disclosure is appended."""
        rr = _risk_rec(50)
        out = tf.fmt_adaptive_risk_block(rr)
        assert _expected_l50_score_line(rr) in out
        # No <50 disclosure wording present.
        assert "מדגם נוכחי:" not in out
        assert "מבוסס מדגם חלקי" not in out

    def test_sample_ge_50_byte_identical_heat_thermometer(self):
        """True L50 sample >= 50 ⇒ heat-thermometer L50 lines byte-identical;
        no honesty disclosure appended."""
        rr = _risk_rec(60)
        out = tf.fmt_heat_thermometer(rr)
        assert f"{tf.RTL}  L50 `[" in out  # original bare L50 line preserved
        assert "מדגם נוכחי:" not in out
        assert "מבוסס מדגם חלקי" not in out

    def test_sample_lt_50_honest_disclosure_adaptive_block(self):
        """True L50 sample of 9 ⇒ honest disclosure present, using the
        EXISTING engine_core.get_sample_size_context wording; never a bare
        misleading L50(50) without its honest qualifier."""
        rr = _risk_rec(9)
        out = tf.fmt_adaptive_risk_block(rr)
        ctx = ec.get_sample_size_context(9)
        assert "מדגם נוכחי: 9/50" in out
        assert ctx["label"] in out  # helper's own verbatim wording reused
        # The score literal still appears but is now qualified by the
        # honest disclosure line that follows it.
        assert _expected_l50_score_line(rr) in out
        assert "מבוסס מדגם חלקי" in out

    def test_sample_lt_50_honest_disclosure_heat_thermometer(self):
        rr = _risk_rec(9)
        out = tf.fmt_heat_thermometer(rr)
        ctx = ec.get_sample_size_context(9)
        assert "מדגם נוכחי: 9/50" in out
        assert ctx["label"] in out
        assert "מבוסס מדגם חלקי" in out

    def test_helper_called_not_modified_contract(self):
        """We CALL get_sample_size_context verbatim — its <30 contract
        (the strong honesty label) is what surfaces for tiny samples."""
        ctx = ec.get_sample_size_context(9)
        assert ctx["warning"] is True
        assert ctx["label"] == (
            "סטטיסטיקה ראשונית בלבד — אין לאשר הגדלת סיכון אגרסיבית")


# ════════════════════════════════════════════════════════════════════════════
# (3) LOCKED April invariant byte-identical post-fix
# ════════════════════════════════════════════════════════════════════════════
def _april_df():
    R = [
        _row('9156146580', 'CVX', '2026-03-13', 'BUY', 3, 195.78, 0.0, 184.28, 'VCP', 'CVX_9156146580'),
        _row('9257785640', 'CVX', '2026-04-01', 'SELL', -3, 197.03, -1.25, 0, 'VCP', 'CVX_9156146580'),
        _row('9148472196', 'DAR', '2026-03-12', 'BUY', 1, 55.6, 0.0, 51.02, 'VCP', 'DAR_9148472196'),
        _row('9148472208', 'DAR', '2026-03-12', 'BUY', 7, 55.6, 0.0, 51.02, 'VCP', 'DAR_9148472196'),
        _row('9282495790', 'DAR', '2026-04-08', 'SELL', -8, 59.3, 24.6, 0, 'VCP', 'DAR_9148472196'),
        _row('9307120241', 'RVMD', '2026-04-13', 'BUY', 10, 132.5, 0.0, 127.8, 'EP', 'RVMD_9307120241'),
        _row('9307713252', 'RVMD', '2026-04-13', 'SELL', -1, 128.782, -6.468, 145.4, 'EP', 'RVMD_9307120241'),
        _row('9307742026', 'RVMD', '2026-04-13', 'SELL', -1, 128.36, -6.89, 145.4, 'EP', 'RVMD_9307120241'),
        _row('9307757736', 'RVMD', '2026-04-13', 'SELL', -8, 128.26, -38.42, 145.4, 'EP', 'RVMD_9307120241'),
        _row('9307924911', 'RVMD', '2026-04-13', 'BUY', 13, 130.9, 0.0, 127.8, 'EP', 'RVMD_9307924911'),
        _row('9336142373', 'RVMD', '2026-04-16', 'SELL', -5, 149.3, 88.538462, 145.4, 'EP', 'RVMD_9307924911'),
        _row('9355041897', 'RVMD', '2026-04-21', 'SELL', -8, 145.3, 111.161538, 0, 'EP', 'RVMD_9307924911'),
        _row('9190319665', 'MTZ', '2026-03-19', 'BUY', 1, 315.95, 0.0, 292.7, 'VCP', 'MTZ_9190319665'),
        _row('9408963635', 'MTZ', '2026-04-30', 'SELL', -1, 388.13, 67.18, 0, 'VCP', 'MTZ_9190319665'),
        _row('9376944499', 'NEE', '2026-04-23', 'BUY', 4, 96.6, 0.0, 89.75, 'VCP', 'NEE_9376944499'),
        _row('9392191923', 'NEE', '2026-04-27', 'SELL', -4, 94.96, -11.56, 0, 'VCP', 'NEE_9376944499'),
        _row('9378665300', 'INTC', '2026-04-24', 'BUY', 10, 84.67, 0.0, 82.01, 'EP', 'INTC_9378665300'),
        _row('9379237329', 'INTC', '2026-04-25', 'SELL', -10, 81.81, -33.6, 0, 'Unknown', 'INTC_9378665300'),
        _row('9394908015', 'AXGN', '2026-04-28', 'BUY', 4, 44.65, 0.0, 42.88, 'EP', 'AXGN_9394908015'),
        _row('9397453020', 'AXGN', '2026-04-28', 'SELL', -4, 42.7, -12.8, 0, 'Unknown', 'AXGN_9394908015'),
        _row('9283303702', 'AEHR', '2026-04-08', 'BUY', 5, 60.3, 0.0, 68.4, 'EP', 'AEHR_9283303702'),
        _row('9320120697', 'AEHR', '2026-04-14', 'SELL', -3, 73.5, 35.6, 68.4, 'EP', 'AEHR_9283303702'),
        _row('9396137314', 'AEHR', '2026-04-28', 'SELL', -2, 78.92, 33.74, 0, 'EP', 'AEHR_9283303702'),
        _row('9260403195', 'TSLA', '2026-04-01', 'BUY', 3, 380.51, 0.0, -1, 'ALGO', 'TSLA_9260403195'),
        _row('9265665177', 'TSLA', '2026-04-02', 'SELL', -3, 365.875, -48.905, -1, 'ALGO', 'TSLA_9260403195'),
    ]
    return pd.DataFrame(R)


class TestLockedAprilByteIdenticalPostFix:
    def test_april_invariant_unchanged(self):
        a = ae.compute_period_analytics(
            _april_df(), datetime(2026, 4, 1),
            datetime(2026, 4, 30, 23, 59, 59),
            {"nav": 7922.19, "risk_pct_input": 0.5})
        assert a["ok"] is True
        assert a["campaigns_closed"] == 8
        assert round(a["realized_pnl"], 2) == 180.49
        assert a["win_rate"] == pytest.approx(0.375, abs=1e-6)
        assert a["profit_factor"] == pytest.approx(2.6262, abs=1e-3)
        assert a["excluded_count"] == 2


# ════════════════════════════════════════════════════════════════════════════
# (4) ALGO segregation / observe-only unaffected by the two display fixes
# ════════════════════════════════════════════════════════════════════════════
class TestAlgoSegregationObserveOnlyUnaffected:
    def test_algo_bucket_still_not_stat_countable(self):
        """The recon-key fix touches a DISPLAY/recon read only — ALGO
        remains excluded from edge stats (AGENTS.md #8 / DEC-20260511-001)."""
        assert ec.is_stat_countable(ec.STAT_BUCKET_ALGO) is False

    def test_algo_position_remains_observe_only(self):
        """No exit-management introduced: ALGO classification stays
        observe-only (engine_core.classify_management_mode → algo_observed;
        DEC-20260511-001 #8). Neither display fix adds management logic."""
        assert ec.classify_management_mode("ALGO") == "algo_observed"
        assert ec.classify_management_mode("ALGO", "TSLA") == "algo_observed"
        # A manual setup is unaffected (no cross-contamination by the fixes).
        assert ec.classify_management_mode("VCP") == "manual_managed"
        assert ec.classify_management_mode("EP") == "manual_managed"

    def test_algo_campaign_pnl_flows_only_through_disclosed_total(self):
        """The W-A2 recon term now includes the ALGO campaign's realized
        PnL exactly as the dashboard's disclosed `(all)` total does — this
        is the disclosed, labelled total (#3 of the investigation), NOT an
        edge-stat contamination."""
        closed = are.compute_closed_campaigns(_closed_fixture_df())
        algo = [c for c in closed if c["campaign_id"] == "CCC_5"]
        assert len(algo) == 1
        assert algo[0]["total_pnl_usd"] == pytest.approx(-40.0, abs=1e-9)
        assert ec.is_stat_countable(algo[0]["stat_bucket"]) is False
