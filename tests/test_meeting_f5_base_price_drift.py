"""
F5 (Meeting 21/05/2026 Wave 2) — drift-resistant `base_price` via the
`locked_base_price` first-day anchor.

Why this exists:
  RISK-1c.1 added a campaign-level lock anchor (`locked_entry_price`)
  to position_lock_anchor.attach_lock_anchors. That clears the
  `⚠️ לא-נעול` banner and stops the displayed entry from drifting.
  But the downstream R math computes `original_campaign_risk` as
  `(base_price - init_sl) * base_qty`, and `base_price` comes from
  engine_core's per-campaign aggregation off the raw `price` column —
  the SAME column that drifts on IBKR re-sync.

  F5 adds a second anchor — `locked_base_price` — computed from the
  qty-weighted average of `locked_entry_price` across FIRST-DAY BUYs
  only (the same scope engine_core uses to compute `base_price`). When
  the column is populated (post-RISK-1c + all first-day BUYs locked),
  consumers adopt it for R math, making `original_campaign_risk`
  drift-resistant.

Byte-identity contract:
  - LOCKED-April fixture (no `locked_entry_price` column in input) ⇒
    every campaign gets `locked_base_price=None` ⇒ consumers fall back
    to `base_price` ⇒ all R / sizing math byte-identical.
  - Currently-unlocked positions (post-RISK-1c.1 banner-flagged) ⇒
    `locked_base_price=None` ⇒ byte-identical to today.
  - Currently-locked positions, no drift yet ⇒ `locked_base_price`
    EQUALS `base_price` byte-identically ⇒ no math change.
  - Currently-locked positions, `price` drifted ⇒ `locked_base_price`
    holds the true at-entry value ⇒ R math is CORRECTED. This is the
    explicit goal.

Tests pinned in this file:
  A. compute_first_day_lock_anchor — pure helper, all branches.
  B. attach_lock_anchors — output frame carries `locked_base_price`
     column with the right values and column-presence guarantees.
  C. Surface-wiring — both display surfaces adopt `locked_base_price`
     in their R-math computation via the `base_price_eff` pattern.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd  # noqa: E402

import position_lock_anchor as pla  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# A. compute_first_day_lock_anchor — pure helper
# ════════════════════════════════════════════════════════════════════════════

class TestComputeFirstDayLockAnchor:
    def _buys(self, rows):
        return pd.DataFrame(rows)

    def test_single_first_day_buy_returns_lock(self):
        buys = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": 87.0, "quantity": 2},
        ])
        assert pla.compute_first_day_lock_anchor(buys) == 87.0

    def test_multiple_first_day_buys_weighted_average(self):
        # Two BUYs on the SAME date — the first day total. (87*2 + 90*2)/4 = 88.5
        buys = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": 87.0, "quantity": 2},
            {"trade_date": "2026-03-05", "locked_entry_price": 90.0, "quantity": 2},
        ])
        assert pla.compute_first_day_lock_anchor(buys) == 88.5

    def test_add_on_on_later_day_does_not_affect_first_day_anchor(self):
        # First-day buy at 87, add-on at 95 on a later date. The first-day
        # anchor MUST stay 87 (mirrors engine_core's `base_price` semantics —
        # base_price is first-day-only, not campaign-wide).
        buys = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": 87.0, "quantity": 2},
            {"trade_date": "2026-03-10", "locked_entry_price": 95.0, "quantity": 1},
        ])
        assert pla.compute_first_day_lock_anchor(buys) == 87.0

    def test_first_day_partial_lock_returns_none(self):
        # First-day BUY missing a lock ⇒ honest "not all first-day locked"
        # ⇒ None ⇒ consumer falls back to base_price. The other-day BUYs
        # being locked or not is irrelevant for the first-day anchor.
        buys = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": None, "quantity": 2},
            {"trade_date": "2026-03-05", "locked_entry_price": 90.0, "quantity": 2},
        ])
        assert pla.compute_first_day_lock_anchor(buys) is None

    def test_missing_column_returns_none_april_path(self):
        # LOCKED-April fixture: the `locked_entry_price` column is absent.
        buys = self._buys([
            {"trade_date": "2026-03-05", "price": 87.0, "quantity": 2},
        ])
        assert pla.compute_first_day_lock_anchor(buys) is None

    def test_missing_trade_date_returns_none(self):
        # Without trade_date the helper cannot identify "first day".
        # Honest disclosure ⇒ None ⇒ fall back.
        buys = self._buys([
            {"locked_entry_price": 87.0, "quantity": 2},
        ])
        assert pla.compute_first_day_lock_anchor(buys) is None

    def test_empty_input_returns_none(self):
        assert pla.compute_first_day_lock_anchor(self._buys([])) is None
        assert pla.compute_first_day_lock_anchor(None) is None

    def test_zero_or_negative_lock_treated_as_unlocked(self):
        # 0 / negative locks are not valid at-entry prices (matches the
        # supabase_repository.set_locked_entry positive-only contract).
        buys_zero = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": 0.0, "quantity": 1},
            {"trade_date": "2026-03-05", "locked_entry_price": 100.0, "quantity": 1},
        ])
        assert pla.compute_first_day_lock_anchor(buys_zero) is None

        buys_neg = self._buys([
            {"trade_date": "2026-03-05", "locked_entry_price": -5.0, "quantity": 1},
        ])
        assert pla.compute_first_day_lock_anchor(buys_neg) is None

    def test_drift_resistance_unit_test(self):
        # THE F5 invariant: the first-day BUY's `price` was overwritten by
        # a re-sync to mark-to-market ($170), but `locked_entry_price`
        # stayed at the original $87. The helper returns $87 — engine
        # math now uses the immutable anchor.
        buys = self._buys([
            {"trade_date": "2026-03-05", "price": 170.0,
             "locked_entry_price": 87.0, "quantity": 1},
        ])
        assert pla.compute_first_day_lock_anchor(buys) == 87.0


# ════════════════════════════════════════════════════════════════════════════
# B. attach_lock_anchors — output frame carries locked_base_price column
# ════════════════════════════════════════════════════════════════════════════

class TestAttachLockAnchorsCarriesBasePrice:
    def _df(self, rows):
        return pd.DataFrame(rows)

    def test_column_added_to_every_row(self):
        open_pos = self._df([
            {"campaign_id": "C1", "symbol": "MRVL"},
            {"campaign_id": "C2", "symbol": "AAPL"},
        ])
        raw = self._df([
            # C1: first day 2026-03-05 has two BUYs.
            {"campaign_id": "C1", "side": "BUY", "trade_date": "2026-03-05",
             "locked_entry_price": 87.0, "quantity": 2},
            {"campaign_id": "C1", "side": "BUY", "trade_date": "2026-03-05",
             "locked_entry_price": 90.0, "quantity": 2},
            # C1 add-on on a later day — must NOT affect the first-day anchor.
            {"campaign_id": "C1", "side": "BUY", "trade_date": "2026-03-10",
             "locked_entry_price": 100.0, "quantity": 1},
            # C2: first-day partial lock ⇒ None.
            {"campaign_id": "C2", "side": "BUY", "trade_date": "2026-04-01",
             "locked_entry_price": 150.0, "quantity": 1},
            {"campaign_id": "C2", "side": "BUY", "trade_date": "2026-04-01",
             "locked_entry_price": None, "quantity": 1},
        ])
        out = pla.attach_lock_anchors(open_pos, raw)
        assert "locked_base_price" in out.columns
        c1_anchor = out[out["campaign_id"] == "C1"]["locked_base_price"].iloc[0]
        c2_anchor = out[out["campaign_id"] == "C2"]["locked_base_price"].iloc[0]
        # C1 first-day weighted avg: (87*2 + 90*2)/4 = 88.5. The add-on at
        # 100 on a later day must NOT contaminate this.
        assert c1_anchor == 88.5
        # C2 has a NaN/None lock on the first day ⇒ honest None.
        assert c2_anchor is None

    def test_empty_open_pos_column_present(self):
        out = pla.attach_lock_anchors(self._df([]), self._df([]))
        assert "locked_base_price" in out.columns

    def test_strictly_additive_existing_columns_preserved(self):
        # The existing `locked_entry_price` column (RISK-1c.1) AND every
        # original column must still be present alongside the new
        # `locked_base_price`.
        open_pos = self._df([
            {"campaign_id": "C1", "symbol": "X", "price": 100.0,
             "base_price": 100.0, "quantity": 1},
        ])
        raw = self._df([
            {"campaign_id": "C1", "side": "BUY", "trade_date": "2026-03-05",
             "locked_entry_price": 100.0, "quantity": 1},
        ])
        out = pla.attach_lock_anchors(open_pos, raw)
        for col in ("campaign_id", "symbol", "price", "base_price",
                    "quantity", "locked_entry_price", "locked_base_price"):
            assert col in out.columns

    def test_missing_raw_columns_returns_none_for_base_anchor(self):
        # If raw lacks campaign_id/side, both anchors fall to None safely.
        open_pos = self._df([{"campaign_id": "C1"}])
        raw_bad = self._df([{"x": 1}])  # missing campaign_id and side
        out = pla.attach_lock_anchors(open_pos, raw_bad)
        assert out["locked_base_price"].iloc[0] is None
        assert out["locked_entry_price"].iloc[0] is None

    def test_dtype_object_preserves_none_round_trip(self):
        # When the result is fed through .to_dict('records') the None must
        # survive (not become np.nan). This pins the dtype=object choice.
        open_pos = self._df([{"campaign_id": "C1"}])
        raw = self._df([{"campaign_id": "C1", "side": "BUY",
                         "trade_date": "2026-03-05",
                         "locked_entry_price": None, "quantity": 1}])
        out = pla.attach_lock_anchors(open_pos, raw)
        rec = out.to_dict("records")[0]
        # Python None — not numpy NaN — for use with `is None` checks.
        assert rec["locked_base_price"] is None


# ════════════════════════════════════════════════════════════════════════════
# C. Surface-wiring — both display surfaces adopt base_price_eff
# ════════════════════════════════════════════════════════════════════════════

class TestSurfaceWiringF5:
    """The two display surfaces (telegram_portfolio + dashboard) must
    adopt `locked_base_price` as the drift-resistant base for the
    `original_campaign_risk` computation. If a future refactor drops the
    `base_price_eff` pattern, the bug regresses silently and `base_price`
    drift leaks back into R math."""

    def test_telegram_portfolio_uses_base_price_eff_pattern(self):
        src = _read("telegram_portfolio.py")
        # The pattern is "base_price_eff = float(_lbp) if _lbp is not None else ..."
        # — pinned for all 3 per-position blocks (drilldown, regime, room).
        assert src.count("base_price_eff") >= 3, (
            "telegram_portfolio.py must use the F5 base_price_eff pattern "
            "in all 3 per-position blocks (drilldown, regime, room). "
            "Anything less leaks base_price drift back into R math."
        )
        assert "locked_base_price" in src

    def test_telegram_portfolio_original_risk_uses_base_price_eff(self):
        src = _read("telegram_portfolio.py")
        # The `original_campaign_risk` (and the regime block's
        # `orig_risk`) MUST be computed off `base_price_eff`, never the
        # raw `base_price`. Grep both names — every occurrence of either
        # must use _eff in the same line.
        for line in src.splitlines():
            stripped = line.strip()
            # Find lines that compute the risk numerator/denominator.
            if "original_campaign_risk = " in stripped or "orig_risk = " in stripped:
                assert "base_price_eff" in stripped, (
                    f"original_campaign_risk computed off raw base_price "
                    f"instead of base_price_eff: {stripped!r}"
                )

    def test_dashboard_uses_base_price_eff_pattern(self):
        src = _read("dashboard.py")
        # Two per-position blocks: live-builder + AI export.
        assert src.count("base_price_eff") >= 2, (
            "dashboard.py must use base_price_eff in both the live builder "
            "and the AI export loop."
        )

    def test_dashboard_original_risk_uses_base_price_eff(self):
        src = _read("dashboard.py")
        # ONLY check lines inside live-position loops; the closed-campaign
        # aggregation (dashboard.py:448 area) intentionally stays on
        # raw `base_price` to preserve LOCKED-April fixture byte-identity.
        # The live-loop assignments are uniquely identified by reading
        # row.get('base_price', entry) — that's the open-positions pattern.
        # We assert the two live-loop original_campaign_risk lines use _eff.
        eff_count = src.count("original_campaign_risk = (base_price_eff")
        assert eff_count >= 2, (
            "dashboard.py: live-loop original_campaign_risk lines must "
            "use base_price_eff (found {eff_count}, need >=2 for the "
            "live builder + AI export blocks)."
        )
