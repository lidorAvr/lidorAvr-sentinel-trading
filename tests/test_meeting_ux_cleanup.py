"""
UX cleanup landing (founder feedback 21/05/2026 ~03:30):

The founder saw the /portfolio output after F-YTD and pointed out:
  "עכשיו זה מבלבל וארוך"
    1. The recon line contradicts itself: says "מאוזן" but then
       "הסיבה לא אומתה — דורש אימות ידני" (Mark §3 verbatim wording
       designed for an UN-explained gap). Once the user explicitly
       disclaimed history, those phrases no longer apply.
    2. The 14-line adaptive-risk verbose breakdown was firing even
       when direction='hold' because the gate clamped — so the user
       saw a forest of stats explaining "no change recommended",
       which is the OPPOSITE of glance-able.

This phase fixes BOTH without weakening any safety guarantee:
  - When the disclaimer softened the band BELOW Critical, the recon
    line renders the SHORT clean variant (no contradictory preamble).
    Critical residual still gets the Mark §3 verbatim wording.
  - When the 4-gate explicitly clamped an "up" to "hold", the adaptive
    block renders the COMPACT variant (5 lines instead of 14). Natural
    "hold" (no gate evaluation) keeps the verbose path so existing
    fixture-based tests stay green.

Tests pinned:
  A. Recon line — softened-band variant + Critical-residual variant.
  B. Adaptive block — compact-on-gate-clamp + verbose-on-natural-hold.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import telegram_formatters as tf  # noqa: E402


def _status_softened(raw_gap=495.67, estimate=495.67, deposited=7500.0,
                     nav=7857.0):
    """Recon status with adjustment applied + soft band (Balanced)."""
    return tf.classify_broker_reconciliation(
        nav, deposited, 0.0,
        reconciliation_gap=raw_gap,
        risk_pct_input=0.6,
        pre_db_realized_pnl_estimate=estimate,
    )


# ════════════════════════════════════════════════════════════════════════════
# A. Recon line — softened-band variant
# ════════════════════════════════════════════════════════════════════════════

class TestReconLineSoftenedVariant:
    def test_softened_line_omits_unverified_preamble(self):
        # When adjustment softened the band, the Mark §3 "cause unverified
        # / manual verification required" preamble is contradictory — it
        # MUST NOT appear in the rendered line.
        status = _status_softened()
        assert status["band"] == "Balanced"
        line = tf.fmt_broker_reconciliation(status)
        # The verbose preamble is GONE.
        assert "הסיבה לא אומתה" not in line
        assert "דורש אימות ידני" not in line
        # The disclaimer disclosure stays — that's the actionable info.
        assert "הצהרת היסטוריה לפני-DB" in line
        # Raw and adjusted gaps both surface for forensic clarity.
        assert "גולמי" in line
        assert "מותאם" in line

    def test_softened_line_ai_copy_also_clean(self):
        # The AI-copy mirror also drops the preamble.
        status = _status_softened()
        line = tf.fmt_broker_reconciliation(status, ai_copy=True)
        assert "Cause unverified" not in line
        assert "Manual verification" not in line
        assert "pre-DB history" in line.lower() or "pre-DB" in line


class TestReconLineCriticalResidualKeepsMarkWording:
    def test_huge_residual_still_critical_keeps_full_preamble(self):
        # If the disclaimer over-shoots or the raw gap is so big that
        # the residual is STILL Critical, the Mark §3 wording must
        # remain — manual verification IS still needed for the residual.
        status = tf.classify_broker_reconciliation(
            10000.0, 7500.0, 0.0,
            reconciliation_gap=2500.0,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=100.0,  # tiny disclaimer
        )
        assert status["band"] == "Critical Data Gap"
        line = tf.fmt_broker_reconciliation(status)
        # The full Mark §3 preamble survives.
        assert "הסיבה לא אומתה" in line
        assert "דורש אימות ידני" in line
        # Disclaimer note still appended (operator should see it).
        assert "הצהרה" in line or "שארית" in line


class TestReconLineNoAdjustmentByteIdentical:
    def test_no_adjustment_keeps_original_mark_wording(self):
        # Default path (no estimate set) MUST be byte-identical to the
        # pre-F-YTD line. The cleanup never touched the default path.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
        )
        line = tf.fmt_broker_reconciliation(status)
        # All original Mark §3 phrases present.
        assert "הסיבה לא אומתה" in line
        assert "דורש אימות ידני" in line
        # No adjustment disclosure (none was applied).
        assert "הצהרת היסטוריה" not in line


# ════════════════════════════════════════════════════════════════════════════
# B. Adaptive block — compact-on-gate-clamp + verbose-on-natural-hold
# ════════════════════════════════════════════════════════════════════════════

class TestAdaptiveBlockCompactOnGateClamp:
    def _gate_clamped_rec(self):
        # The exact founder-scenario shape: gate clamped to hold + the
        # heat_factors[0] carries the ⛔ reason.
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
            "heat_factors": [
                "⛔ שער 2 (מדגם מספיק) נכשל — נדרשות ≥20 עסקאות "
                "ידניות נספרות (יש 10)",
                "▲ Win Rate (S9): 67% — תורם חיובי",
            ],
            "what_to_improve": ["ציון חום נדרש: 60 | כרגע: 100"],
            "risk_raise_gate": {
                "evaluated": True,
                "allow_raise": False,
                "failed": ["G2_sample"],
                "reason": "שער 2 ...",
            },
            "s9_score": 99, "m21_score": 96, "l50_score": 96,
            "s9_stats": {"n": 9}, "m21_stats": {"n": 10}, "l50_stats": {"n": 10},
        }

    def test_compact_path_omits_score_breakdown(self):
        out = tf.fmt_adaptive_risk_block(self._gate_clamped_rec())
        # The verbose multi-window line MUST NOT appear.
        assert "ציון (0-100) לפי טווח" not in out
        # Nor the per-window win rate breakdown.
        assert "Win Rate — S9" not in out
        # Nor the "🔼 לשיפור" line — meaningless when score is 100 and
        # the system says "hold".
        assert "לשיפור" not in out
        # Nor the L50 partial-sample warning (it's not actionable on hold).
        assert "L50 מבוסס מדגם חלקי" not in out

    def test_compact_path_keeps_blocking_reason(self):
        # The ⛔ gate reason MUST survive — that's the actionable info.
        out = tf.fmt_adaptive_risk_block(self._gate_clamped_rec())
        assert "⛔" in out
        assert "שער 2" in out

    def test_compact_path_keeps_current_recommendation(self):
        # Founder needs to see the current/recommended on a glance.
        out = tf.fmt_adaptive_risk_block(self._gate_clamped_rec())
        assert "0.60%" in out
        assert "47" in out

    def test_compact_path_omits_positive_heat_factors(self):
        # The "▲ Win Rate ... — תורם חיובי" line is noise when no raise is
        # happening. Only ⛔ entries survive.
        out = tf.fmt_adaptive_risk_block(self._gate_clamped_rec())
        assert "תורם חיובי" not in out

    def test_compact_path_is_short(self):
        # Line count must be small — the WHOLE point. <= 6 non-empty
        # lines for the founder's scenario (title + headline + ⛔ reason).
        out = tf.fmt_adaptive_risk_block(self._gate_clamped_rec())
        non_empty = [l for l in out.splitlines() if l.strip()]
        assert len(non_empty) <= 6, f"compact block has {len(non_empty)} lines: {non_empty}"


class TestAdaptiveBlockVerboseOnNaturalHold:
    """Natural hold (no gate evaluation OR gate allowed but other reason
    held) keeps the verbose path so the existing fixture-based tests
    (W-A3 / G5 / Sprint-30) stay green."""

    def _natural_hold_rec(self):
        # Same shape as the gate-clamped fixture but WITHOUT a
        # risk_raise_gate.evaluated flag — represents the legacy "hold
        # because heat is neutral" path.
        return {
            "ok": True,
            "direction": "hold",
            "step_type": "שמירה על רמה קיימת",
            "heat_label": "נייטרל",
            "heat_color": "➖",
            "heat_score": 50,
            "current_risk_pct": 0.60,
            "current_risk_usd": 47,
            "recommended_risk_pct": 0.60,
            "recommended_risk_usd": 47,
            "win_streak": 0,
            "loss_streak": 0,
            "heat_factors": [],
            "s9_score": 50, "m21_score": 50, "l50_score": 50,
            "s9_stats": {"n": 9}, "m21_stats": {"n": 21}, "l50_stats": {"n": 50},
        }

    def test_verbose_path_includes_score_line(self):
        # No gate clamp ⇒ verbose path ⇒ score breakdown survives.
        out = tf.fmt_adaptive_risk_block(self._natural_hold_rec())
        assert "ציון (0-100) לפי טווח" in out

    def test_verbose_path_includes_win_rate_breakdown(self):
        out = tf.fmt_adaptive_risk_block(self._natural_hold_rec())
        assert "Win Rate" in out or "שיעור הצלחה" in out


class TestAdaptiveBlockUpDirectionStaysVerbose:
    def test_up_direction_keeps_verbose(self):
        rec = {
            "ok": True,
            "direction": "up",
            "step_type": "העלאת סיכון הדרגתית",
            "heat_label": "חזק",
            "heat_color": "🔥",
            "heat_score": 80,
            "current_risk_pct": 0.60,
            "current_risk_usd": 47,
            "recommended_risk_pct": 0.85,
            "recommended_risk_usd": 67,
            "win_streak": 3,
            "loss_streak": 0,
            "heat_factors": ["▲ Win Rate"],
            "s9_score": 80, "m21_score": 80, "l50_score": 80,
            "s9_stats": {"n": 25}, "m21_stats": {"n": 25}, "l50_stats": {"n": 25},
        }
        out = tf.fmt_adaptive_risk_block(rec)
        # Verbose path: score line + heat label appear.
        assert "ציון (0-100) לפי טווח" in out
        assert "0.85%" in out  # the proposed pct surfaces
