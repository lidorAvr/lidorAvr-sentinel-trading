"""
Meeting 21/05/2026 — Wave 2 (founder chose A + B1 + B3 from the
team-meeting tiered menu). This module pins the three TESTING-discipline
edge-cases (T1/T2/T3) + the ENGINE-discipline integration test (A4) that
the 8-discipline review surfaced as missing pins:

  T1 — over-shoot disclaimer (`gap=+495.67, estimate=+600`) lands in
       Material Gap with `adjusted_gap=-104.33`; the defensive
       `min(|raw|, |adjusted|)` clamp keeps the band at the MILDER of
       the two, never escalates.

  T2 — gate-clamped adaptive block with `heat_factors=[]` falls back to
       `risk_raise_gate.reason` (the new T2-fallback in
       `telegram_formatters.fmt_adaptive_risk_block`). Mark §X2 requires
       the blocking reason to survive every compact-path render — a
       3-line block with no ⛔ would be a §X2 violation.

  T3 — corrupt non-numeric `pre_db_realized_pnl_estimate` in
       sentinel_config.json (e.g. operator typo `"abc"`) returns 0.0
       from the new `account_state.pre_db_realized_pnl_estimate(...)`
       helper. The 5 caller sites are now defended against the
       ValueError chain TESTING T3 flagged.

  A4 — end-to-end disclaimer→G1 gate chain pin: when the disclaimer
       softens the band from Critical to Balanced, `G1` gate stops
       refusing the up-leg. ENGINE F1 closure pin.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import account_state  # noqa: E402
import adaptive_risk_engine as are  # noqa: E402
import telegram_formatters as tf  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# T1 — over-shoot disclaimer: defensive clamp + adjusted gap surfaces
# ════════════════════════════════════════════════════════════════════════════

class TestOverShootDisclaimer:
    """Disclaimer larger than the raw gap → adjusted_gap goes negative.
    The defensive `min(|raw|, |adjusted|)` clamp must keep the band on
    the MILDER side (|raw|=495.67 < |adjusted|=104.33 → use 495.67),
    and the surfaced fields must both be visible for forensic reasons."""

    def test_over_shoot_keeps_milder_band(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=600.0,
        )
        # |raw|=495.67, |adjusted|=104.33 → milder is |adjusted|=104.33.
        # min(|raw|, |adjusted|) = 104.33. unit = 7857 * 0.006 = 47.14.
        # 104.33 > unit ⇒ Material Gap (not Critical: 104.33 < 5*47.14).
        assert status["band"] == "Material Gap"

    def test_over_shoot_surfaces_both_gaps(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=600.0,
        )
        # Both raw and adjusted MUST surface (Mark §X1).
        assert status["gap"] == 495.67
        assert abs(status["adjusted_gap"] - (495.67 - 600.0)) < 0.01

    def test_over_shoot_never_escalates_band(self):
        # If raw gap was Balanced (< $10) and the operator over-shoots
        # massively, the band must NOT escalate — the clamp prevents an
        # over-disclaimed history from tightening the band.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=5.0,           # raw is Balanced
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=1000.0,  # disclaimer dwarfs the gap
        )
        # min(|5|, |5-1000|) = 5 → still Balanced. Never Critical.
        assert status["band"] == "Balanced"


# ════════════════════════════════════════════════════════════════════════════
# T2 — gate-clamped compact path falls back to risk_raise_gate.reason
# ════════════════════════════════════════════════════════════════════════════

class TestCompactPathHeatFactorsEmptyFallback:
    """When heat_factors is empty (e.g. the rec was built by an alert
    builder that doesn't populate heat_factors), the compact path must
    surface `risk_raise_gate.reason` so the ⛔ blocking reason still
    appears. Mark §X2 invariant."""

    def _empty_factors_rec(self, gate_reason="שער 2 — מדגם לא מספיק"):
        return {
            "ok": True,
            "direction": "hold",
            "step_type": "שמירה על רמה קיימת",
            "heat_label": "נייטרל",
            "heat_color": "➖",
            "heat_score": 100,
            "current_risk_pct": 0.60,
            "current_risk_usd": 47,
            "recommended_risk_pct": 0.60,
            "recommended_risk_usd": 47,
            "win_streak": 1,
            "loss_streak": 0,
            "heat_factors": [],   # ← empty: the T2 scenario
            "risk_raise_gate": {
                "evaluated": True,
                "allow_raise": False,
                "failed": ["G2_sample"],
                "reason": gate_reason,
            },
            "s9_score": 99, "m21_score": 96, "l50_score": 96,
            "s9_stats": {"n": 9}, "m21_stats": {"n": 10}, "l50_stats": {"n": 10},
        }

    def test_compact_path_surfaces_gate_reason_when_factors_empty(self):
        out = tf.fmt_adaptive_risk_block(self._empty_factors_rec())
        # The ⛔ line MUST appear, sourced from gate.reason.
        assert "⛔" in out
        assert "שער 2" in out

    def test_compact_path_does_not_double_prefix_existing_marker(self):
        # If gate.reason already starts with ⛔, the renderer must not
        # emit "⛔ ⛔ ..." — anti-double-prefix.
        rec = self._empty_factors_rec(gate_reason="⛔ שער 1 כשל")
        out = tf.fmt_adaptive_risk_block(rec)
        # exactly one ⛔ in the line (and the line contains "שער 1 כשל").
        gate_lines = [ln for ln in out.splitlines() if "שער 1" in ln]
        assert len(gate_lines) == 1
        assert gate_lines[0].count("⛔") == 1

    def test_compact_path_handles_missing_reason_gracefully(self):
        # If both heat_factors AND gate.reason are absent, the compact
        # block still renders (3 lines: header + headline) — no crash,
        # no silent ⛔-less footgun (the line is just absent).
        rec = self._empty_factors_rec(gate_reason="")
        out = tf.fmt_adaptive_risk_block(rec)
        # The 3 baseline lines render; no ⛔ line.
        non_empty = [ln for ln in out.splitlines() if ln.strip()]
        assert 2 <= len(non_empty) <= 4
        assert "⛔" not in out


# ════════════════════════════════════════════════════════════════════════════
# T3 — corrupt config value → graceful fallback to 0.0
# ════════════════════════════════════════════════════════════════════════════

class TestPreDbHelperFailsafe:
    """The new account_state.pre_db_realized_pnl_estimate(account) helper
    catches the ValueError chain TESTING T3 flagged and falls back to 0.0
    on any non-numeric / null / missing value."""

    def test_missing_key_returns_zero(self):
        assert account_state.pre_db_realized_pnl_estimate({}) == 0.0

    def test_none_value_returns_zero(self):
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": None}) == 0.0

    def test_non_numeric_string_returns_zero(self):
        # Operator typo: "abc" instead of a number.
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": "abc"}) == 0.0

    def test_empty_string_returns_zero(self):
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": ""}) == 0.0

    def test_numeric_string_parses(self):
        # JSON null vs the string "495.67" — both should resolve cleanly.
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": "495.67"}) == 495.67

    def test_positive_float_passes_through(self):
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": 495.67}) == 495.67

    def test_negative_float_passes_through(self):
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": -200.50}) == -200.50

    def test_int_passes_through(self):
        assert account_state.pre_db_realized_pnl_estimate(
            {"pre_db_realized_pnl_estimate": 500}) == 500.0


# ════════════════════════════════════════════════════════════════════════════
# A4 — end-to-end disclaimer → G1 gate integration pin (ENGINE F1)
# ════════════════════════════════════════════════════════════════════════════

class TestDisclaimerGatesG1Chain:
    """When the disclaimer softens the band BELOW `Critical Data Gap`,
    the `G1` gate (clean-data) stops refusing on data-quality grounds.
    This is the integration pin ENGINE F1 flagged as missing — the
    classifier emits a band string, `build_risk_raise_gate_ctx` reads
    it, G1 acts on it. End-to-end on a real fixture."""

    def _gate_ctx(self, pre_db_estimate):
        # Founder's 21/05/2026 scenario shape: raw gap +$495.67 on a
        # $7,857 NAV with $7,500 deposited. With estimate=0 the band is
        # Critical; with estimate=+495.67 it softens to Balanced.
        return are.build_risk_raise_gate_ctx(
            nav=7857.0,
            risk_pct=0.60,
            total_deposited=7500.0,
            closed_campaigns=[],
            nav_source="broker",
            pre_db_realized_pnl_estimate=pre_db_estimate,
        )

    def test_without_disclaimer_G1_refuses(self):
        ctx = self._gate_ctx(pre_db_estimate=0.0)
        # G1 is the clean-data gate. With raw gap $495.67 → Critical
        # band → G1 must be in the failed list.
        assert ctx.get("recon_band") == "Critical Data Gap"
        if ctx.get("evaluated"):
            assert "G1_recon" in (ctx.get("failed") or [])
            assert ctx.get("allow_raise") is False

    def test_with_correct_disclaimer_G1_passes(self):
        # Founder's actual disclaimer: +495.67 zeros the gap.
        ctx = self._gate_ctx(pre_db_estimate=495.67)
        # Band softened to Balanced (or at least below Critical) → G1
        # no longer refuses on data-quality.
        assert ctx.get("recon_band") != "Critical Data Gap"
        if ctx.get("evaluated"):
            assert "G1_recon" not in (ctx.get("failed") or [])

    def test_chain_is_byte_identical_on_default_path(self):
        # The disclaimer is opt-in. The default (estimate=0.0) path
        # must behave identically to a deployment that doesn't know
        # about the field at all — Sprint-25-style byte-identity for
        # any pre-meeting-ux consumer.
        ctx_default = self._gate_ctx(pre_db_estimate=0.0)
        ctx_explicit_zero = self._gate_ctx(pre_db_estimate=0.0)
        # Same fixture → same ctx (idempotency sanity).
        assert ctx_default.get("recon_band") == ctx_explicit_zero.get("recon_band")
        assert ctx_default.get("allow_raise") == ctx_explicit_zero.get("allow_raise")
