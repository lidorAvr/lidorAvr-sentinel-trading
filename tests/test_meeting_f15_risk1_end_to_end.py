"""
F15 (Meeting 21/05/2026 Wave 2) — end-to-end integration test stitching
all RISK-1 components together.

The RISK-1 series spans many modules:
  RISK-1a   migration 006 added 4 lock columns
  RISK-1b   forward-capture wizard writes the columns at trade-entry
  RISK-1c   admin backfill writes the columns retroactively
  RISK-1c.1 position_lock_anchor enriches engine_core's stripped output
  RISK-1d   resolver + formatter banner across 3 surfaces

Each phase has its own unit tests. But until F15 there was no test
proving the FULL CONTRACT — that a trade row inserted into Supabase,
then locked, then aggregated via engine_core, then enriched by
position_lock_anchor, then resolved by telegram_formatters → produces
the right entry value + empty banner.

If a future refactor breaks the wiring at any layer (e.g. someone
renames a column, changes a dict key, drops the enrichment step), unit
tests for the touched layer might still pass while the overall flow
silently breaks. This integration test catches that.

Approach: real engine_core (byte-locked, untouched), real
position_lock_anchor (pure), real telegram_formatters (pure). Supabase
is MagicMock-ed at the boundary, but the trade DataFrame fed downstream
is the same shape Supabase returns.

The test does NOT exercise telegram_bot.py or risk_monitor.py
(those need TELEGRAM_TOKEN at import). The flow tested is the data
contract from raw row → display number.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd  # noqa: E402

import engine_core as ec  # noqa: E402 (byte-locked, untouched)
import position_lock_anchor as pla  # noqa: E402
import telegram_formatters as tf  # noqa: E402


def _trade_rows(*, with_lock: bool, drifted: bool = False):
    """Build the raw rows shape Supabase returns. ``with_lock`` toggles
    whether locked_entry_price is populated (post-RISK-1b/1c).
    ``drifted`` simulates the MRVL bug: `price` was overwritten by a
    re-sync to mark-to-market while locked_entry_price stayed at the
    original entry."""
    lock_val = 87.0 if with_lock else None
    return [
        {
            "trade_id": "B1", "campaign_id": "MRVL_1", "symbol": "MRVL",
            "side": "BUY", "trade_date": "2026-03-05",
            "price": 170.0 if drifted else 87.0,
            "locked_entry_price": lock_val,
            "quantity": 4, "stop_loss": 80.0, "initial_stop": 80.0,
            "pnl_usd": 0, "setup_type": "EP",
            "management_state": "full_position", "base_price": 87.0,
        },
    ]


def _flow(rows):
    """Stitch the full read path: raw rows → DataFrame → engine
    aggregation → position_lock_anchor enrichment → per-row dict →
    resolver output."""
    df = pd.DataFrame(rows)
    pos_res = ec.get_open_positions_campaign(df)
    assert pos_res["ok"], f"engine failure: {pos_res.get('error')}"
    # The enrichment layer is the F15 stitch — without it the rest of
    # the flow would silently regress to the pre-RISK-1c.1 bug.
    enriched = pla.attach_lock_anchors(pos_res["data"], df)
    row = enriched.to_dict("records")[0]
    resolved = tf.resolve_entry_display(
        price=row["price"],
        locked_entry_price=row.get("locked_entry_price"),
        mode="live",
    )
    return row, resolved


# ════════════════════════════════════════════════════════════════════════════
# A. Unlocked trade path — full RISK-1 contract preserves legacy display
# ════════════════════════════════════════════════════════════════════════════

class TestUnlockedTradePath:
    """A trade that has NOT been locked yet flows through the entire
    pipeline unchanged: engine sees `price`, enrichment sets lock columns
    to None, resolver returns price + the not-yet-locked banner. This
    pins the byte-identity contract for the 71 historical rows that
    weren't yet locked (or any future row pre-RISK-1b wizard)."""

    def test_unlocked_trade_resolver_returns_price_with_banner(self):
        row, resolved = _flow(_trade_rows(with_lock=False))
        # Resolver got price (since locked_entry_price is None).
        assert resolved["entry"] == 87.0
        assert resolved["is_locked"] is False
        # The not-yet-locked banner fires.
        assert resolved["banner"] == tf.ENTRY_NOT_LOCKED_LABEL
        # The aggregated row carries None for both lock anchors.
        assert row["locked_entry_price"] is None
        assert row["locked_base_price"] is None


# ════════════════════════════════════════════════════════════════════════════
# B. Locked + non-drifted trade — silent on lock, byte-identical numbers
# ════════════════════════════════════════════════════════════════════════════

class TestLockedNonDriftedTradePath:
    """The post-RISK-1c steady state: every BUY's locked_entry_price was
    copied from `price` at lock-time, and no re-sync has drifted `price`.
    The resolver returns the lock value (same as price), no banner. F15
    pins that the displayed entry is byte-identical to the pre-lock
    display — only the banner clears."""

    def test_locked_trade_resolver_returns_lock_no_banner(self):
        row, resolved = _flow(_trade_rows(with_lock=True, drifted=False))
        # Both columns equal 87.0 (no drift) → entry = 87.0, banner = "".
        assert resolved["entry"] == 87.0
        assert resolved["is_locked"] is True
        assert resolved["banner"] == ""
        # The enrichment populated both anchors (campaign-level + first-day).
        assert row["locked_entry_price"] == 87.0
        assert row["locked_base_price"] == 87.0


# ════════════════════════════════════════════════════════════════════════════
# C. Locked + drifted trade — THE MRVL regression unit test
# ════════════════════════════════════════════════════════════════════════════

class TestLockedDriftedTradePath:
    """The exact MRVL $87 → $170 regression that motivated RISK-1: IBKR
    re-sync overwrote `price` to mark-to-market ($170), but
    locked_entry_price stays at the immutable $87 from lock-time. The
    pipeline MUST return $87 — the locked value wins over the drifted
    price column."""

    def test_drift_does_not_corrupt_displayed_entry(self):
        row, resolved = _flow(_trade_rows(with_lock=True, drifted=True))
        # `price` column was overwritten to 170 (drifted).
        assert row["price"] == 170.0
        # But the resolver returns the immutable lock anchor.
        assert resolved["entry"] == 87.0
        assert resolved["is_locked"] is True
        assert resolved["banner"] == ""

    def test_first_day_lock_anchor_resists_drift_for_R_math(self):
        # F5's drift-resistant base — the SAME pipeline that fixes the
        # display ALSO fixes the R-math input downstream.
        row, _ = _flow(_trade_rows(with_lock=True, drifted=True))
        # locked_base_price stays at 87 even when base_price (from raw
        # `price` column) might have drifted.
        assert row["locked_base_price"] == 87.0


# ════════════════════════════════════════════════════════════════════════════
# D. April-fixture path — engine output stays byte-identical when no lock
# ════════════════════════════════════════════════════════════════════════════

class TestAprilFixturePath:
    """The LOCKED-April fixture predates the lock columns. Its rows do
    NOT carry locked_entry_price at all. F15 verifies that this path
    produces locked_entry_price=None and locked_base_price=None on the
    enriched row, which means every downstream consumer falls back to
    `price` / `base_price` byte-identically. This is what keeps the
    9 byte-lock guards green."""

    def _april_rows(self):
        # Note: NO locked_entry_price column on these rows — same shape
        # as the LOCKED-April fixture.
        return [
            {
                "trade_id": "B1", "campaign_id": "LEGACY_1", "symbol": "LEGACY",
                "side": "BUY", "trade_date": "2026-04-01",
                "price": 50.0, "quantity": 10,
                "stop_loss": 45.0, "initial_stop": 45.0, "pnl_usd": 0,
                "setup_type": "VCP", "management_state": "full_position",
                "base_price": 50.0,
            },
        ]

    def test_no_lock_column_produces_none_anchors(self):
        df = pd.DataFrame(self._april_rows())
        pos_res = ec.get_open_positions_campaign(df)
        assert pos_res["ok"]
        enriched = pla.attach_lock_anchors(pos_res["data"], df)
        row = enriched.to_dict("records")[0]
        # The fixture has no lock column ⇒ both anchors None.
        assert row["locked_entry_price"] is None
        assert row["locked_base_price"] is None
        # The price column passes through unchanged ⇒ April fixtures
        # consuming this path see exactly today's behaviour.
        assert row["price"] == 50.0
