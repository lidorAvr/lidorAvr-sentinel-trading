"""
RISK-1d — single-source-of-truth at-entry-price display across the 3 surfaces
(Telegram /portfolio card, AI Master Context Export, Command-Center expander).

Tests pinned in this file:
  A. ``resolve_entry_display`` — all (mode × lock-state × input-type) branches
     of the canonical resolver. Pure / read-only / no I/O.
  B. ``fmt_position_card`` — the new ``entry_banner`` kwarg defaults to ``""``
     so every existing caller stays BYTE-IDENTICAL; passing a non-empty
     banner appends it after the entry price, before the " → נוכחי" arrow.
  C. Surface-wiring grep-tests — the 3 surfaces (telegram_portfolio /
     dashboard live-builder / dashboard AI export / dashboard expander) all
     read the SAME resolver and surface the SAME banner. Anti-drift.

The 4 lock columns are migration-006 / RISK-1a, the wizard forward-capture
is RISK-1b, this phase (RISK-1d) is the display contract. April reconciliation
is byte-identical by construction (analytics_engine never reads the lock
columns; the resolver's mode='historical' default is also byte-identical).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import telegram_formatters as tf  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


# ════════════════════════════════════════════════════════════════════════════
# A. resolve_entry_display — the pure resolver
# ════════════════════════════════════════════════════════════════════════════

class TestResolveEntryDisplayHistoricalMode:
    """mode='historical' is the byte-locked default for April / every
    backwards-compatible caller. It MUST never read the lock columns and MUST
    never emit the banner — that contract is what keeps analytics_engine and
    the LOCKED-April fixture (DEC-019/-020) byte-identical."""

    def test_historical_with_no_lock_returns_price(self):
        r = tf.resolve_entry_display(price=87.0, locked_entry_price=None,
                                     mode="historical")
        assert r["entry"] == 87.0
        assert r["banner"] == ""
        assert r["is_locked"] is False
        assert r["mode"] == "historical"

    def test_historical_ignores_a_set_lock_value(self):
        # Even when the lock column IS populated, historical mode must NOT
        # read it. This is the carve-out that pins April byte-identity.
        r = tf.resolve_entry_display(price=87.0, locked_entry_price=170.0,
                                     mode="historical")
        assert r["entry"] == 87.0  # raw price, not the lock
        assert r["banner"] == ""
        assert r["is_locked"] is False

    def test_historical_with_none_price_returns_zero(self):
        r = tf.resolve_entry_display(price=None, locked_entry_price=None,
                                     mode="historical")
        assert r["entry"] == 0.0
        assert r["banner"] == ""

    def test_historical_with_non_numeric_price_returns_zero(self):
        r = tf.resolve_entry_display(price="abc", locked_entry_price=87.0,
                                     mode="historical")
        assert r["entry"] == 0.0
        assert r["banner"] == ""


class TestResolveEntryDisplayLiveModeLocked:
    """mode='live' + locked_entry_price IS NOT NULL — the canonical
    forward path. Locked value wins, banner is silent (absence = signal)."""

    def test_live_with_positive_lock_returns_lock_silent(self):
        r = tf.resolve_entry_display(price=170.0, locked_entry_price=87.0,
                                     mode="live")
        # This IS the MRVL regression unit-test: legacy `price` drifted to
        # 170 (mark-to-market), the lock pins entry to the real 87.
        assert r["entry"] == 87.0
        assert r["banner"] == ""
        assert r["is_locked"] is True
        assert r["mode"] == "live"

    def test_live_default_mode_is_live(self):
        # Per the docstring contract: when the caller omits ``mode=``, the
        # resolver defaults to 'live'. The 3 display-surface callers MUST
        # rely on this default — flipping it would silently downgrade them
        # to mode='historical' (no banner, no MRVL fix).
        r = tf.resolve_entry_display(price=170.0, locked_entry_price=87.0)
        assert r["mode"] == "live"
        assert r["entry"] == 87.0

    def test_live_lock_takes_precedence_when_price_is_anomalous(self):
        # Even with a 0/None/negative `price` (broker-anomaly), a real lock
        # should still win — the lock IS the canonical at-entry anchor.
        r = tf.resolve_entry_display(price=0.0, locked_entry_price=87.0,
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["is_locked"] is True

    def test_live_lock_handles_numeric_string(self):
        # Supabase JSON sometimes returns NUMERIC as a string. The resolver
        # MUST coerce so the contract doesn't break on the wire format.
        r = tf.resolve_entry_display(price="170.0", locked_entry_price="87.0",
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["is_locked"] is True


class TestResolveEntryDisplayLiveModeUnlocked:
    """mode='live' + locked_entry_price IS NULL / 0 / negative / non-numeric.
    The legacy `price` is still displayed (no silent substitution) AND the
    not-yet-locked banner is emitted so the founder sees the gap."""

    def test_live_with_none_lock_returns_price_plus_banner(self):
        r = tf.resolve_entry_display(price=87.0, locked_entry_price=None,
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["banner"] == tf.ENTRY_NOT_LOCKED_LABEL
        assert r["is_locked"] is False
        assert r["mode"] == "live"

    def test_live_with_zero_lock_treated_as_not_locked(self):
        # 0 is not a valid at-entry price; downgrade to unlocked.
        r = tf.resolve_entry_display(price=87.0, locked_entry_price=0.0,
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["banner"] == tf.ENTRY_NOT_LOCKED_LABEL
        assert r["is_locked"] is False

    def test_live_with_negative_lock_treated_as_not_locked(self):
        r = tf.resolve_entry_display(price=87.0, locked_entry_price=-5.0,
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["banner"] == tf.ENTRY_NOT_LOCKED_LABEL
        assert r["is_locked"] is False

    def test_live_with_non_numeric_lock_treated_as_not_locked(self):
        # Defense-in-depth: anomalous Supabase row (string in numeric column,
        # corrupted JSON, etc.) must NOT crash — degrade to unlocked + banner.
        r = tf.resolve_entry_display(price=87.0, locked_entry_price="abc",
                                     mode="live")
        assert r["entry"] == 87.0
        assert r["banner"] == tf.ENTRY_NOT_LOCKED_LABEL
        assert r["is_locked"] is False

    def test_live_with_non_numeric_price_floors_to_zero(self):
        # Both columns anomalous — entry collapses to 0.0 (the formatter then
        # prints "$0.00", which is the honest "no data" signal).
        r = tf.resolve_entry_display(price=None, locked_entry_price=None,
                                     mode="live")
        assert r["entry"] == 0.0
        assert r["banner"] == tf.ENTRY_NOT_LOCKED_LABEL


class TestEntryNotLockedLabelString:
    """The canonical not-yet-locked label is sourced from the formatter
    module exactly once — every surface reads ``tf.ENTRY_NOT_LOCKED_LABEL``.
    Wording lives here so future edits land in ONE place."""

    def test_label_is_hebrew_with_rtl_marker(self):
        assert "‏" in tf.ENTRY_NOT_LOCKED_LABEL  # RTL marker
        assert "⚠️" in tf.ENTRY_NOT_LOCKED_LABEL
        assert "לא-נעול" in tf.ENTRY_NOT_LOCKED_LABEL

    def test_label_mentions_resync_drift_reason(self):
        # The banner discloses the WHY (re-sync drift) — never a vague warning.
        assert "re-sync" in tf.ENTRY_NOT_LOCKED_LABEL


# ════════════════════════════════════════════════════════════════════════════
# B. fmt_position_card — entry_banner kwarg byte-identity + appending
# ════════════════════════════════════════════════════════════════════════════

class TestFmtPositionCardEntryBannerByteIdentical:
    """Default ``entry_banner=""`` MUST keep every existing caller/test
    byte-identical to the pre-RISK-1d output. Same contract as Sprint-12
    `price_is_fallback` and Sprint-15 `dual_r_fragment`."""

    def _card(self, **kw):
        d = dict(
            i=1, sym="AAPL", setup="VCP", days_held=10,
            curr=155.0, entry=150.0, open_pnl=50.0,
            pos_value=1550.0, weight_pct=5.0,
            total_pos_profit=50.0, total_campaign_r=0.5,
            open_r_val=0.5, status="🟢 Healthy", action_short="Hold",
        )
        d.update(kw)
        return tf.fmt_position_card(**d)

    def test_default_no_banner_no_label(self):
        card = self._card()
        assert tf.ENTRY_NOT_LOCKED_LABEL not in card

    def test_explicit_empty_string_no_label(self):
        card = self._card(entry_banner="")
        assert tf.ENTRY_NOT_LOCKED_LABEL not in card

    def test_default_kwarg_byte_identical_to_empty_string(self):
        # The two callers MUST produce the same bytes (no hidden divergence).
        assert self._card() == self._card(entry_banner="")

    def test_banner_appears_after_entry_before_arrow(self):
        card = self._card(entry_banner=tf.ENTRY_NOT_LOCKED_LABEL)
        assert tf.ENTRY_NOT_LOCKED_LABEL in card
        # Order: entry price → banner → " → נוכחי" arrow. This is the layout
        # the 3 surfaces share; reversing it would split the "not locked"
        # warning from the price it qualifies.
        entry_pos = card.index("$150.00")
        banner_pos = card.index(tf.ENTRY_NOT_LOCKED_LABEL)
        arrow_pos = card.index("נוכחי")
        assert entry_pos < banner_pos < arrow_pos

    def test_banner_appears_exactly_once(self):
        card = self._card(entry_banner=tf.ENTRY_NOT_LOCKED_LABEL)
        assert card.count(tf.ENTRY_NOT_LOCKED_LABEL) == 1

    def test_banner_does_not_affect_price_numbers(self):
        # Label-only: every dollar/R number is byte-identical between the
        # banner-on and banner-off renders. Pure presentation.
        no_banner = self._card(entry_banner="")
        with_banner = self._card(entry_banner=tf.ENTRY_NOT_LOCKED_LABEL)
        # Stripping the banner from the with-banner card must yield bytes
        # identical to the no-banner card.
        assert with_banner.replace(
            f" {tf.ENTRY_NOT_LOCKED_LABEL}", "") == no_banner

    def test_banner_coexists_with_price_fallback_label(self):
        # Both Sprint-12 (live-price fallback) and RISK-1d (entry-lock)
        # can fire on the same card — they target DIFFERENT data points and
        # MUST not collide. Live-price fallback follows " → נוכחי"; entry
        # banner precedes it.
        card = self._card(entry_banner=tf.ENTRY_NOT_LOCKED_LABEL,
                          price_is_fallback=True)
        assert tf.ENTRY_NOT_LOCKED_LABEL in card
        assert tf.PRICE_FALLBACK_LABEL in card
        # Order: entry-banner < arrow < live-price-fallback
        assert (card.index(tf.ENTRY_NOT_LOCKED_LABEL)
                < card.index("נוכחי")
                < card.index(tf.PRICE_FALLBACK_LABEL))


class TestFmtPositionCardSignature:
    """The signature now has ``entry_banner`` as the LAST kwarg with default
    ``""`` — matches the existing Sprint-12 / Sprint-15 evolution pattern."""

    def test_entry_banner_is_a_kwarg_with_default_empty(self):
        import inspect
        sig = inspect.signature(tf.fmt_position_card)
        assert "entry_banner" in sig.parameters
        p = sig.parameters["entry_banner"]
        assert p.default == ""

    def test_pre_risk1d_kwargs_still_present(self):
        # Defensive: no regression on the kwargs the prior phases added.
        import inspect
        sig = inspect.signature(tf.fmt_position_card)
        for name in ("price_is_fallback", "dual_r_fragment",
                     "locked_profit", "giveback_risk", "capital_risk",
                     "add_on_count", "base_price"):
            assert name in sig.parameters


# ════════════════════════════════════════════════════════════════════════════
# C. Surface-wiring grep tests — anti-drift across the 3 display surfaces
# ════════════════════════════════════════════════════════════════════════════

def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


class TestTelegramSurfaceWired:
    """telegram_portfolio.py — Telegram /portfolio card surface."""

    def test_portfolio_calls_resolver(self):
        src = _read("telegram_portfolio.py")
        assert "tf.resolve_entry_display(" in src

    def test_portfolio_reads_locked_column(self):
        src = _read("telegram_portfolio.py")
        assert "row.get('locked_entry_price')" in src \
            or 'row.get("locked_entry_price")' in src

    def test_portfolio_passes_banner_into_fmt_position_card(self):
        src = _read("telegram_portfolio.py")
        assert "entry_banner=_entry_disp['banner']" in src \
            or 'entry_banner=_entry_disp["banner"]' in src


class TestDashboardLiveBuilderWired:
    """dashboard.py / compute_live_portfolio_data — feeds Command-Center +
    AI export + treemap. The bug surface that motivated RISK-1."""

    def test_live_builder_calls_resolver(self):
        src = _read("dashboard.py")
        assert "tf.resolve_entry_display(" in src

    def test_live_df_carries_entry_banner_column(self):
        src = _read("dashboard.py")
        assert "'EntryBanner'" in src
        assert "'IsEntryLocked'" in src


class TestDashboardExpanderWired:
    """dashboard.py / Command-Center expander — surfaces the banner via
    st.caption right under the Data-Quality line."""

    def test_expander_renders_entry_banner(self):
        src = _read("dashboard.py")
        # The expander reads from live_df['EntryBanner'] (not from a fresh
        # resolver call — produce-once-consume-thrice).
        assert "pos.get('EntryBanner'" in src or \
               'pos.get("EntryBanner"' in src
        # Rendered via st.caption (additive — never overwrites another caption).
        assert "st.caption" in src


class TestAIExportWired:
    """dashboard.py / AI Master Context Export — block 2 (per-position)."""

    def test_ai_export_calls_resolver(self):
        src = _read("dashboard.py")
        assert "_entry_disp_ai" in src

    def test_ai_export_appends_banner_after_entry_dollar_value(self):
        src = _read("dashboard.py")
        # The banner is appended AFTER ${entry:.2f} BEFORE the " | Curr:"
        # divider — so when pasted into Claude, the lock status sits with
        # the value it qualifies, not at end-of-line where it could read
        # as a global remark.
        assert "_entry_banner_ai" in src
        assert "Entry: ${entry:.2f}{_entry_banner_ai}" in src


class TestNoSilentSubstitution:
    """The MOST IMPORTANT contract: never silently substitute `price` for
    `locked_entry_price`. If lock is NULL, the user MUST see the banner —
    no surface may strip it. Grep-guards across the 3 surfaces."""

    def test_no_surface_overrides_banner_with_empty_string(self):
        # Defensive scan: no caller should be passing ``entry_banner=""``
        # alongside a real resolve_entry_display call (that would silently
        # mute the banner). Today none do — pin it.
        for path in ("telegram_portfolio.py", "dashboard.py"):
            src = _read(path)
            # If the file calls the resolver, it must also propagate the banner.
            if "tf.resolve_entry_display(" in src:
                assert "['banner']" in src or '["banner"]' in src, (
                    f"{path} resolves entry but never reads ['banner']")


# ════════════════════════════════════════════════════════════════════════════
# D. RISK-1c.1 regression — position_lock_anchor enrichment outside engine_core
# ════════════════════════════════════════════════════════════════════════════
# Bug found in prod 21/05/2026 ~01:40: RISK-1c successfully locked 71 rows in
# Supabase, but /portfolio for MRVL still showed "⚠️ לא-נעול". Root cause:
# engine_core.get_open_positions_campaign builds the per-campaign output dict
# with 14 explicit fields and `locked_entry_price` is not among them, so the
# row that reaches the resolver always carries lock=None ⇒ banner. engine_core
# is BYTE-LOCKED (test_sprint25_byte_lock_redteam + 7 sibling guards) so it
# cannot be modified. The fix is a pure enrichment helper called by the 2
# display surfaces AFTER get_open_positions_campaign.


class TestComputeCampaignLockAnchor:
    """Pin the pure helper that computes one campaign's lock anchor."""

    def _buys(self, rows):
        import pandas as pd
        return pd.DataFrame(rows)

    def test_all_locked_returns_weighted_average(self):
        import position_lock_anchor as pla
        buys = self._buys([
            {"locked_entry_price": 87.0, "quantity": 2},
            {"locked_entry_price": 90.0, "quantity": 2},
        ])
        # (87*2 + 90*2)/4 = 88.5
        assert pla.compute_campaign_lock_anchor(buys) == 88.5

    def test_partial_lock_returns_none(self):
        # Any NaN/None in the column ⇒ honest "not all locked" ⇒ None.
        import position_lock_anchor as pla
        buys = self._buys([
            {"locked_entry_price": 87.0, "quantity": 2},
            {"locked_entry_price": None, "quantity": 2},
        ])
        assert pla.compute_campaign_lock_anchor(buys) is None

    def test_missing_column_returns_none_april_path(self):
        # LOCKED-April fixture: the column does not exist on the input frame.
        import position_lock_anchor as pla
        buys = self._buys([
            {"price": 87.0, "quantity": 2},
        ])
        assert pla.compute_campaign_lock_anchor(buys) is None

    def test_drift_resistance_lock_wins_over_drifted_price(self):
        # THE MRVL regression unit test: `price` drifted to $170 via re-sync,
        # `locked_entry_price` stays at $87. The anchor returns $87 — the
        # drifted price column is never read by this helper.
        import position_lock_anchor as pla
        buys = self._buys([
            {"price": 170.0, "locked_entry_price": 87.0, "quantity": 1},
        ])
        assert pla.compute_campaign_lock_anchor(buys) == 87.0

    def test_zero_or_negative_lock_treated_as_unlocked(self):
        # Defensive: a rogue 0/negative in locked_entry_price (broker-anomaly,
        # corrupted manual write) must NOT be treated as a valid anchor —
        # collapse to None so the banner stays.
        import position_lock_anchor as pla
        buys_zero = self._buys([
            {"locked_entry_price": 0.0, "quantity": 1},
            {"locked_entry_price": 100.0, "quantity": 1},
        ])
        assert pla.compute_campaign_lock_anchor(buys_zero) is None

        buys_neg = self._buys([
            {"locked_entry_price": -5.0, "quantity": 1},
            {"locked_entry_price": 100.0, "quantity": 1},
        ])
        assert pla.compute_campaign_lock_anchor(buys_neg) is None

    def test_empty_dataframe_returns_none(self):
        import position_lock_anchor as pla
        assert pla.compute_campaign_lock_anchor(self._buys([])) is None
        assert pla.compute_campaign_lock_anchor(None) is None

    def test_zero_total_quantity_returns_none(self):
        # Pathological: all rows have qty=0 (shouldn't happen, but defensive).
        import position_lock_anchor as pla
        buys = self._buys([
            {"locked_entry_price": 100.0, "quantity": 0},
        ])
        assert pla.compute_campaign_lock_anchor(buys) is None


class TestAttachLockAnchors:
    """Pin the DataFrame-level enrichment that the 2 surfaces call."""

    def _df(self, rows):
        import pandas as pd
        return pd.DataFrame(rows)

    def test_adds_column_to_every_campaign_row(self):
        import position_lock_anchor as pla
        open_pos = self._df([
            {"campaign_id": "C1", "symbol": "MRVL", "price": 88.5},
            {"campaign_id": "C2", "symbol": "AAPL", "price": 150.0},
        ])
        raw = self._df([
            # C1: both BUYs locked.
            {"campaign_id": "C1", "side": "BUY", "locked_entry_price": 87.0, "quantity": 2},
            {"campaign_id": "C1", "side": "BUY", "locked_entry_price": 90.0, "quantity": 2},
            # C2: one BUY locked, one not ⇒ partial-lock ⇒ None.
            {"campaign_id": "C2", "side": "BUY", "locked_entry_price": 150.0, "quantity": 1},
            {"campaign_id": "C2", "side": "BUY", "locked_entry_price": None, "quantity": 1},
        ])
        out = pla.attach_lock_anchors(open_pos, raw)
        assert "locked_entry_price" in out.columns
        c1_anchor = out[out["campaign_id"] == "C1"]["locked_entry_price"].iloc[0]
        c2_anchor = out[out["campaign_id"] == "C2"]["locked_entry_price"].iloc[0]
        assert c1_anchor == 88.5
        assert c2_anchor is None

    def test_strictly_additive_existing_columns_preserved(self):
        # The fix must NOT mutate or drop any existing column on the
        # open_positions DataFrame — that would break engine_core's contract
        # (which a thousand downstream call sites depend on).
        import position_lock_anchor as pla
        open_pos = self._df([
            {"campaign_id": "C1", "symbol": "X", "price": 100.0,
             "quantity": 1, "stop_loss": 90.0, "setup_type": "VCP"},
        ])
        raw = self._df([
            {"campaign_id": "C1", "side": "BUY", "locked_entry_price": 100.0, "quantity": 1},
        ])
        out = pla.attach_lock_anchors(open_pos, raw)
        for col in ("campaign_id", "symbol", "price", "quantity",
                    "stop_loss", "setup_type"):
            assert col in out.columns

    def test_returns_input_unchanged_when_open_pos_is_none(self):
        import position_lock_anchor as pla
        assert pla.attach_lock_anchors(None, self._df([])) is None

    def test_handles_empty_open_pos(self):
        # Empty open positions ⇒ column gets added (empty) but no rows.
        import position_lock_anchor as pla
        out = pla.attach_lock_anchors(self._df([]), self._df([]))
        assert "locked_entry_price" in out.columns
        assert len(out) == 0

    def test_handles_missing_raw_columns_safely(self):
        # If raw_trades_df is missing `campaign_id` or `side`, fall back to
        # None for every row — never raise.
        import position_lock_anchor as pla
        open_pos = self._df([{"campaign_id": "C1"}])
        raw_no_side = self._df([{"campaign_id": "C1", "locked_entry_price": 100.0}])
        out = pla.attach_lock_anchors(open_pos, raw_no_side)
        assert out["locked_entry_price"].iloc[0] is None

    def test_handles_none_raw_safely(self):
        import position_lock_anchor as pla
        open_pos = self._df([{"campaign_id": "C1"}])
        out = pla.attach_lock_anchors(open_pos, None)
        assert out["locked_entry_price"].iloc[0] is None

    def test_filters_to_buy_rows_ignoring_sells(self):
        # SELL rows must NOT enter the lock anchor computation — a SELL
        # row's `locked_entry_price` is meaningless (the lock anchors the
        # ENTRY, not the exit).
        import position_lock_anchor as pla
        open_pos = self._df([{"campaign_id": "C1", "symbol": "X"}])
        raw = self._df([
            {"campaign_id": "C1", "side": "BUY", "locked_entry_price": 100.0, "quantity": 1},
            # SELL with no lock value — must NOT contaminate the all-locked check.
            {"campaign_id": "C1", "side": "SELL", "locked_entry_price": None, "quantity": -1},
        ])
        out = pla.attach_lock_anchors(open_pos, raw)
        assert out["locked_entry_price"].iloc[0] == 100.0


class TestSurfaceWiringRiskC1:
    """The 2 display surfaces MUST call attach_lock_anchors right after
    get_open_positions_campaign — otherwise the bug regresses silently."""

    def test_telegram_portfolio_wires_attach_lock_anchors(self):
        # F4 (Meeting 21/05/2026) — ALL THREE telegram_portfolio call sites
        # of get_open_positions_campaign must call attach_lock_anchors:
        #   1. handle_drilldown (`/trade SYMBOL`)
        #   2. handle_market_regime
        #   3. handle_portfolio_room (`/portfolio`)
        # Before F4 only #3 was wired (RISK-1c.1) so the same campaign
        # could show a drifted entry on /trade and a locked entry on
        # /portfolio. Pin all three so the bug cannot regress silently.
        src = _read("telegram_portfolio.py")
        # Each call site is an `attach_lock_anchors(` invocation.
        call_count = src.count("attach_lock_anchors(")
        assert call_count >= 3, (
            f"Expected >=3 attach_lock_anchors() calls in telegram_portfolio.py "
            f"(one per get_open_positions_campaign call site); found {call_count}. "
            f"F4 wiring may have regressed."
        )

    def test_dashboard_wires_attach_lock_anchors(self):
        src = _read("dashboard.py")
        assert "attach_lock_anchors" in src

    def test_position_lock_anchor_imports_no_engine_core(self):
        # Pure helper — must not import engine_core (the byte-locked module
        # whose limitation this helper exists to work around).
        src = _read("position_lock_anchor.py")
        assert "import engine_core" not in src
        assert "from engine_core" not in src
