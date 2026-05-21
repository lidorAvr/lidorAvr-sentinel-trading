"""
F2 (Meeting 21/05/2026 Wave 2) — broker-reconciliation per-component
breakdown.

Before F2 the founder saw "פער נתונים קריטי $495.67" with no actionable
diagnosis. The Mark §3 line listed 5 possible causes generically. F2
adds a SIBLING formatter (`fmt_broker_reconciliation_breakdown`) that:
  - Shows the arithmetic split: NAV, deposits, realized PnL, open PnL,
    expected equity, actual gap.
  - Narrows the hypothesis list by the gap's SIGN — gap > 0 lists
    causes that INCREASE NAV; gap < 0 lists causes that DECREASE NAV.
  - Stays honest: hypotheses are framed "ייתכן ..." (Mark §3 contract).

Tests pinned in this file:
  A. Arithmetic — the breakdown's gap = nav - (deposits + realized +
     open). Pinned for the founder's $7,857 / $7,500 / $0 / $184 inputs
     (the actual production numbers from the 21/05/2026 screenshot).
  B. Directional hypotheses — gap > 0 surfaces "NAV גבוה מהצפי"
     wording; gap < 0 surfaces "NAV נמוך"; |gap| ≤ $10 surfaces no
     hypothesis line (balanced).
  C. Honesty — every hypothesis line carries "ייתכן" / "Possible
     causes (unverified)" framing. No single cause is asserted.
  D. Surface wiring — telegram_portfolio + dashboard both call the new
     formatter alongside (NOT instead of) fmt_broker_reconciliation.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import telegram_formatters as tf  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _status(band="Critical Data Gap"):
    return {"band": band, "band_he": "פער נתונים קריטי",
            "gap": 0.0, "abs_gap": 0.0, "unit": 0.0,
            "nav_source": "broker", "caveat": ""}


# ════════════════════════════════════════════════════════════════════════════
# A. Arithmetic — the breakdown's numbers
# ════════════════════════════════════════════════════════════════════════════

class TestArithmetic:
    def test_founders_actual_production_numbers(self):
        # The 21/05/2026 screenshot showed: NAV $7,857, gap $495.67.
        # If total_deposited=$7,500, realized=$0, open=$184.72 → expected
        # = $7,684.72; gap = $7,857 - $7,684.72 = $172.28. Doesn't match
        # the reported $495.67 exactly because the founder's actual
        # deposited number is unknown — but the FORMULA must be correct.
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=184.72,
            status=_status(),
        )
        # Every input number appears in the output (formatted).
        assert "7,857" in result
        assert "7,500" in result
        # +0.00 for realized, +184.72 for open
        assert "184.72" in result
        # Expected = 7,500 + 0 + 184.72 = 7,684.72
        assert "7,684.72" in result
        # Gap = 7,857.00 - 7,684.72 = 172.28
        assert "172.28" in result

    def test_negative_gap_arithmetic(self):
        # NAV $7,000 vs expected $7,500 = gap -$500.
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7000.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
        )
        # Negative gap renders with a minus sign.
        assert "-500" in result

    def test_balanced_arithmetic(self):
        # |gap| ≤ $10 — exact balance.
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7500.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(band="Balanced"),
        )
        assert "7,500.00" in result  # both NAV and deposited

    def test_realized_pnl_negative_arithmetic(self):
        # Realized loss flows through correctly.
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7400.00, total_deposited=7500.00,
            db_net_pnl=-100.0, open_pnl=0.0,
            status=_status(band="Balanced"),
        )
        # Expected = 7,500 + (-100) + 0 = 7,400 ⇒ gap 0 ⇒ Balanced.
        assert "-100" in result
        assert "7,400" in result


# ════════════════════════════════════════════════════════════════════════════
# B. Directional hypotheses
# ════════════════════════════════════════════════════════════════════════════

class TestDirectionalHypotheses:
    def test_positive_gap_surfaces_nav_higher_hypothesis(self):
        # gap = 7857 - 7500 = $357 > 0 ⇒ "NAV גבוה מהצפי".
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
        )
        assert "גבוה" in result
        # Causes that INCREASE NAV listed — none of the DECREASE causes.
        assert "דיבידנד" in result or "הפקדה" in result
        assert "משיכה" not in result  # NOT in the positive-gap list

    def test_negative_gap_surfaces_nav_lower_hypothesis(self):
        # gap = 7000 - 7500 = -$500 < 0 ⇒ "NAV נמוך מהצפי".
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7000.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
        )
        assert "נמוך" in result
        assert "עמלה" in result or "משיכה" in result
        # The hypothesis line should NOT mention deposits/dividends here.
        assert "דיבידנד" not in result

    def test_balanced_omits_hypothesis_line(self):
        # |gap| ≤ $10 ⇒ no hypothesis line emitted (no false direction).
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7505.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(band="Balanced"),
        )
        assert "גבוה" not in result
        assert "נמוך" not in result

    def test_ai_copy_uses_english_hypotheses(self):
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
            ai_copy=True,
        )
        assert "NAV exceeds expected" in result
        assert "Reconciliation Breakdown" in result


# ════════════════════════════════════════════════════════════════════════════
# C. Honesty — Mark §3 contract preserved
# ════════════════════════════════════════════════════════════════════════════

class TestHonestyContract:
    def test_positive_gap_uses_yittachen_framing(self):
        # The hypothesis MUST be framed "ייתכן ..." (possible/conjectural),
        # never asserted. This preserves Mark §3's no-single-cause rule.
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
        )
        assert "ייתכן" in result
        # NEVER asserts: no "הסיבה היא ..." or "האשם ...".
        assert "הסיבה היא" not in result
        assert "האשם" not in result

    def test_negative_gap_uses_yittachen_framing(self):
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7000.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
        )
        assert "ייתכן" in result
        assert "לא מאומת" in result

    def test_ai_copy_disclaims_unverified(self):
        result = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.00, total_deposited=7500.00,
            db_net_pnl=0.0, open_pnl=0.0,
            status=_status(),
            ai_copy=True,
        )
        # English equivalent of "ייתכן" — "Possible causes (unverified)".
        assert "unverified" in result.lower()


# ════════════════════════════════════════════════════════════════════════════
# D. Surface wiring — both surfaces call the new formatter alongside the old
# ════════════════════════════════════════════════════════════════════════════

class TestSurfaceWiringF2:
    def test_telegram_portfolio_calls_breakdown(self):
        src = _read("telegram_portfolio.py")
        assert "fmt_broker_reconciliation_breakdown(" in src
        # Both old and new MUST be called (breakdown complements, never replaces).
        assert "fmt_broker_reconciliation(" in src

    def test_dashboard_calls_breakdown_in_ai_export(self):
        src = _read("dashboard.py")
        assert "fmt_broker_reconciliation_breakdown(" in src
        assert "fmt_broker_reconciliation(" in src
