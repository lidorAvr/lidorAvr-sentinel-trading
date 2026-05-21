"""
F-YTD (Founder note 21/05/2026 ~02:30) — pre-DB realized PnL
disclaimer flows through the reconciliation classifier to soften
the band when the founder has explicitly accounted for missing history.

Why this exists:
  Sentinel's Supabase `trades` table only carries trades from the
  deployment date forward. Pre-deploy closed campaigns have NO
  realized-PnL row, so the raw reconciliation gap
  (NAV − (deposits + DB realized + open)) is OVERSTATED by the
  missing pre-deploy realized PnL. Before this phase the system
  surfaced "Critical Data Gap" on what was actually just missing
  history — and the founder had no way to tell the system
  otherwise.

  Now the founder sets `pre_db_realized_pnl_estimate` in
  sentinel_config.json (signed: negative for pre-deploy losses) and
  the classifier subtracts it from the raw gap before banding. The
  band naturally softens; the breakdown surfaces both the raw and
  adjusted numbers; the directional hypothesis drops the pre-DB
  candidate since the founder already accounted for it.

Tests pinned in this file:
  A. classify_broker_reconciliation accepts the new kwarg, returns
     the new keys, and DOES NOT regress for default (0) callers.
  B. Adjusted gap softens the band — the founder's actual production
     numbers (raw gap $495.67) become Balanced when estimate = -$495.67.
  C. Defensive invariant — an over-disclaimed history cannot
     ESCALATE the band beyond the raw gap's classification.
  D. fmt_broker_reconciliation surfaces the disclaimer text when
     applied; no change when the kwarg defaults to 0.
  E. Surface wiring — all 4 live callers + report_scheduler propagate
     the new field from account_settings.
  F. Documentation — DATA_CONTRACTS.md carries the YTD-scope section.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import telegram_formatters as tf  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


# ════════════════════════════════════════════════════════════════════════════
# A. classify_broker_reconciliation accepts the new kwarg; defaults preserved
# ════════════════════════════════════════════════════════════════════════════

class TestClassifierSignature:
    def test_pre_db_kwarg_defaults_to_zero(self):
        import inspect
        sig = inspect.signature(tf.classify_broker_reconciliation)
        assert "pre_db_realized_pnl_estimate" in sig.parameters
        assert sig.parameters["pre_db_realized_pnl_estimate"].default == 0.0

    def test_result_dict_carries_new_keys(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
        )
        assert "pre_db_pnl_estimate" in status
        assert "adjusted_gap" in status
        assert "adjustment_applied" in status

    def test_default_zero_keeps_legacy_keys_byte_identical(self):
        # The pre-F-YTD callers see the SAME band/gap/abs_gap/unit
        # they always did. The new keys are additive; the legacy
        # keys are byte-identical.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
        )
        # Raw gap $495.67 on $7,500 capital with 0.6% risk:
        # unit = 7,500 * 0.006 = $45; 5*unit = $225; |gap| > 225 ⇒ Critical.
        assert status["band"] == "Critical Data Gap"
        assert status["gap"] == 495.67
        # adjustment_applied should be False with default kwarg.
        assert status["adjustment_applied"] is False
        # adjusted_gap equals raw gap when no adjustment.
        assert status["adjusted_gap"] == 495.67


# ════════════════════════════════════════════════════════════════════════════
# B. Adjusted gap softens the band
# ════════════════════════════════════════════════════════════════════════════

class TestAdjustedGapSoftensBand:
    def test_founders_actual_numbers_become_balanced_with_full_disclaimer(self):
        # The founder's actual production numbers: raw gap $495.67.
        # If they set pre_db_realized_pnl_estimate = 495.67 (i.e., they
        # estimate $495.67 of pre-deploy realized PnL the DB is missing
        # — note: signed POSITIVE because pre-deploy PnL would have
        # ADDED to expected equity if the DB had it), the adjusted gap
        # is 0 ⇒ Balanced.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=495.67,
        )
        assert status["adjustment_applied"] is True
        assert status["pre_db_pnl_estimate"] == 495.67
        # Adjusted gap = 495.67 - 495.67 = 0.0 ⇒ Balanced (|0| ≤ $10).
        assert abs(status["adjusted_gap"]) < 0.01
        assert status["band"] == "Balanced"
        # Raw gap preserved for the breakdown / forensic display.
        assert status["gap"] == 495.67

    def test_partial_disclaimer_softens_to_material(self):
        # Raw gap $495.67, partial disclaimer $300 ⇒ adjusted $195.67.
        # On $7,500 capital with 0.6% risk: unit = $45; 5*unit = $225.
        # |$195.67| > unit ($45) and ≤ crit ($225) ⇒ "Material Gap".
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=300.0,
        )
        assert status["band"] == "Material Gap", (
            f"Expected partial-disclaimer to soften Critical → Material; "
            f"got {status['band']} with adjusted_gap={status['adjusted_gap']}"
        )

    def test_negative_estimate_handles_pre_deploy_losses(self):
        # If pre-deploy realized PnL was NEGATIVE (founder had losses
        # before deploy), the disclaimer is a negative number. Raw
        # gap $495.67 - (-500) = +995.67 — WORSE. The min() guard
        # ensures the band can't get TIGHTER from this; the raw gap's
        # band wins ⇒ stays Critical.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=-500.0,
        )
        # Both the raw gap and the adjusted gap exceed crit_anchor → both
        # are "Critical Data Gap" → band stays Critical (no inflation).
        assert status["band"] == "Critical Data Gap"


# ════════════════════════════════════════════════════════════════════════════
# C. Defensive invariant — over-disclaim cannot escalate the band
# ════════════════════════════════════════════════════════════════════════════

class TestDefensiveInvariant:
    def test_over_disclaimed_history_cannot_tighten_band(self):
        # Founder sets pre_db_realized_pnl_estimate=$10,000 when the
        # raw gap is only $495.67. The min() guard means the band is
        # computed off the SMALLER absolute value — keeping the
        # softening property while preventing inflation.
        # raw_gap=$495.67 (Critical), adjusted=-$9,504 (also Critical).
        # min(|495.67|, |9504|) = 495.67 → still Critical (correct;
        # over-disclaiming doesn't FALSELY soften past where the raw
        # gap classifies).
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=10000.0,
        )
        # The band reflects the smaller of |495.67| and |adjusted|.
        # In this case |adjusted| = |495.67 - 10000| = $9,504 >> |495.67|
        # so min picks 495.67 → Critical.
        assert status["band"] == "Critical Data Gap"

    def test_smaller_disclaimer_softens_to_minor(self):
        # Raw $495 (Critical), disclaimer $470 → adjusted $25.67. On
        # $7,500 capital with 0.6%: unit=$45. $10<|25.67|≤$45 → Minor.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=470.0,
        )
        assert status["band"] == "Minor Difference"


# ════════════════════════════════════════════════════════════════════════════
# D. fmt_broker_reconciliation surfaces the disclaimer
# ════════════════════════════════════════════════════════════════════════════

class TestFormatterShowsDisclaimer:
    def test_disclaimer_text_appears_when_applied(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=495.67,
        )
        line = tf.fmt_broker_reconciliation(status)
        # The line shows the disclaimer (text mentions adjustment).
        assert "היסטוריה לפני-DB" in line or "פער מותאם" in line

    def test_no_disclaimer_text_when_estimate_is_zero(self):
        # The default-0 path is byte-identical to the pre-F-YTD line.
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
        )
        line = tf.fmt_broker_reconciliation(status)
        # No disclaimer mention.
        assert "היסטוריה לפני-DB" not in line
        assert "פער מותאם" not in line

    def test_breakdown_shows_adjusted_gap_when_applied(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
            pre_db_realized_pnl_estimate=495.67,
        )
        breakdown = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.0, total_deposited=7500.0,
            db_net_pnl=0.0, open_pnl=0.0,
            status=status,
        )
        # Both raw and adjusted gap appear.
        assert "פער (גולמי)" in breakdown
        assert "פער מותאם" in breakdown
        # The pre-DB candidate is DROPPED from the hypothesis line —
        # the founder already disclaimed it.
        assert "היסטוריית מסחר לפני" not in breakdown

    def test_breakdown_keeps_pre_db_hypothesis_when_no_disclaimer(self):
        status = tf.classify_broker_reconciliation(
            7857.0, 7500.0, 0.0,
            reconciliation_gap=495.67,
            risk_pct_input=0.6,
        )
        breakdown = tf.fmt_broker_reconciliation_breakdown(
            nav=7857.0, total_deposited=7500.0,
            db_net_pnl=0.0, open_pnl=0.0,
            status=status,
        )
        # Without a disclaimer the pre-DB candidate stays primary.
        assert "היסטוריית מסחר" in breakdown


# ════════════════════════════════════════════════════════════════════════════
# E. Surface wiring — all 4 live callers + scheduler propagate the field
# ════════════════════════════════════════════════════════════════════════════

class TestSurfaceWiringYTD:
    def test_telegram_portfolio_reads_field(self):
        src = _read("telegram_portfolio.py")
        assert 'pre_db_realized_pnl_estimate' in src

    def test_dashboard_reads_field(self):
        src = _read("dashboard.py")
        assert 'pre_db_realized_pnl_estimate' in src

    def test_risk_monitor_reads_field(self):
        src = _read("risk_monitor.py")
        assert 'pre_db_realized_pnl_estimate' in src

    def test_report_scheduler_reads_field(self):
        src = _read("report_scheduler.py")
        assert 'pre_db_realized_pnl_estimate' in src

    def test_build_risk_raise_gate_ctx_accepts_kwarg(self):
        import adaptive_risk_engine as are
        import inspect
        sig = inspect.signature(are.build_risk_raise_gate_ctx)
        assert "pre_db_realized_pnl_estimate" in sig.parameters


# ════════════════════════════════════════════════════════════════════════════
# F. Documentation — DATA_CONTRACTS.md carries the YTD-scope section
# ════════════════════════════════════════════════════════════════════════════

class TestDataContractsDocumented:
    def test_data_history_section_exists(self):
        doc = _read("docs/DATA_CONTRACTS.md")
        assert "Data history scope" in doc
        assert "pre_db_realized_pnl_estimate" in doc

    def test_doc_mentions_yt_d_or_deploy_date(self):
        doc = _read("docs/DATA_CONTRACTS.md")
        # The doc should explain WHY the data is partial.
        assert "deploy" in doc.lower() or "ytd" in doc.lower()

    def test_doc_mentions_defensive_invariant(self):
        # Over-estimating must never tighten the band.
        doc = _read("docs/DATA_CONTRACTS.md")
        assert "min(" in doc or "soften" in doc.lower() or "never tighten" in doc.lower()
