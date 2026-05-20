"""
F6 (Meeting 21/05/2026) — guard rail against future commission
double-deduction in the realized-PnL math.

The contract (docs/DATA_CONTRACTS.md, "Sprint-25 A2/Data-F6"):
  `pnl_usd` is the authoritative broker-side NET realized PnL (commission
  already deducted). The realized-PnL path
  (`analytics_engine._aggregate_campaigns` → `sells["pnl_usd"].sum()`)
  reads ONLY `pnl_usd`; `commission` is informational/audit-only and MUST
  NOT be subtracted again anywhere in the realized-PnL / R / Net-R /
  Expectancy math — doing so would double-count commission and corrupt
  the LOCKED-April fixture (DEC-019/-020: PF 2.6262 / WR .375 / 8 /
  +$180.49 / +11.01R).

Before this phase, the contract lived ONLY in the docs. A future
agent could trivially write `pnl_usd - commission` thinking they were
"cleaning up the math" and silently destroy reconciliation. These tests
make that mistake impossible without a CI failure.

Two layers of defense:
  A. Source-scan: `commission` MUST NOT appear in analytics_engine.py
     except in explicit doc-only contexts (none expected today).
  B. Behavioral: run `_aggregate_campaigns` with fixture rows carrying
     commission values; assert the campaign's net_pnl equals the raw
     `pnl_usd` sum (NOT pnl_usd minus commission).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


# ════════════════════════════════════════════════════════════════════════════
# A. Source-scan — `commission` MUST NOT appear in the realized-PnL path
# ════════════════════════════════════════════════════════════════════════════

class TestAnalyticsEngineDoesNotReadCommission:
    """The realized-PnL path lives entirely inside analytics_engine.py.
    A future "clean up the math" PR that introduces a commission-aware
    realized-PnL would silently double-count broker fees. Pin the
    absence."""

    def test_commission_word_absent_from_realized_path(self):
        path = os.path.join(ROOT, "analytics_engine.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        # If a future change deliberately needs `commission` for an
        # audit-only display, it must add a clear marker comment first.
        # Today the realized path is commission-free by design.
        assert "commission" not in src, (
            "analytics_engine.py must not reference `commission` in the "
            "realized-PnL path — pnl_usd is already commission-net "
            "(DATA_CONTRACTS Sprint-25 A2/Data-F6). Double-counting "
            "commission corrupts LOCKED-April PF/WR reconciliation."
        )


# ════════════════════════════════════════════════════════════════════════════
# B. Behavioral — _aggregate_campaigns reads ONLY pnl_usd
# ════════════════════════════════════════════════════════════════════════════

class TestAggregateCampaignsIgnoresCommissionColumn:
    """Even when the input frame carries a non-zero `commission` column,
    the aggregation MUST NOT subtract it from pnl_usd. Today this is
    true by code-absence; the test pins it behaviorally."""

    def _fixture(self, *, pnl_usd: float, commission: float):
        # One closed campaign: a BUY then a SELL with the given pnl_usd
        # (already commission-net, per the contract) AND a commission
        # column the aggregation MUST ignore.
        return pd.DataFrame([
            {
                "trade_id": "B1", "campaign_id": "C1", "symbol": "TEST",
                "side": "BUY", "trade_date": "2026-04-01",
                "price": 100.0, "quantity": 10, "stop_loss": 90.0,
                "initial_stop": 90.0, "pnl_usd": 0.0, "commission": commission,
                "setup_type": "VCP", "management_state": "full_position",
            },
            {
                "trade_id": "S1", "campaign_id": "C1", "symbol": "TEST",
                "side": "SELL", "trade_date": "2026-04-10",
                "price": 110.0, "quantity": 10, "stop_loss": 90.0,
                "initial_stop": 90.0, "pnl_usd": pnl_usd, "commission": commission,
                "setup_type": "VCP", "management_state": "full_position",
            },
        ])

    def test_pnl_usd_passes_through_when_commission_zero(self):
        # Baseline: no commission ⇒ net_pnl == pnl_usd.
        import analytics_engine as ae
        df = self._fixture(pnl_usd=100.0, commission=0.0)
        result = ae._aggregate_campaigns(df, target_risk_usd=50.0)
        assert not result.empty
        # The realized-PnL column the campaign carries forward.
        # (column name may differ across versions; check both common names).
        camp = result.iloc[0]
        # _aggregate_campaigns returns the realized PnL in `net_pnl`.
        net = camp.get("net_pnl", camp.get("net_pnl_usd", camp.get("pnl_usd")))
        assert abs(float(net) - 100.0) < 0.01

    def test_pnl_usd_passes_through_when_commission_nonzero(self):
        # The guard: commission $5 is present in the row but MUST be
        # ignored. net_pnl must STILL equal 100.0, not 95.0.
        import analytics_engine as ae
        df = self._fixture(pnl_usd=100.0, commission=5.0)
        result = ae._aggregate_campaigns(df, target_risk_usd=50.0)
        assert not result.empty
        camp = result.iloc[0]
        # _aggregate_campaigns returns the realized PnL in `net_pnl`.
        net = camp.get("net_pnl", camp.get("net_pnl_usd", camp.get("pnl_usd")))
        assert abs(float(net) - 100.0) < 0.01, (
            f"net_pnl was {net} — expected 100.0. If 95.0, commission was "
            f"double-deducted (it's already in pnl_usd from the broker)."
        )

    def test_pnl_usd_passes_through_when_commission_negative(self):
        # Defense in depth: even pathological negative commission (data
        # corruption) must not flow into net_pnl.
        import analytics_engine as ae
        df = self._fixture(pnl_usd=100.0, commission=-3.5)
        result = ae._aggregate_campaigns(df, target_risk_usd=50.0)
        assert not result.empty
        camp = result.iloc[0]
        # _aggregate_campaigns returns the realized PnL in `net_pnl`.
        net = camp.get("net_pnl", camp.get("net_pnl_usd", camp.get("pnl_usd")))
        assert abs(float(net) - 100.0) < 0.01


# ════════════════════════════════════════════════════════════════════════════
# C. Documentation pin — DATA_CONTRACTS must still carry the warning
# ════════════════════════════════════════════════════════════════════════════

class TestDataContractsCarriesTheWarning:
    """The contract that 'commission must not be subtracted again' lives
    in docs/DATA_CONTRACTS.md. The doc-pin guards against silent removal
    of the warning during a doc cleanup."""

    def test_data_contracts_still_warns_against_double_deduction(self):
        path = os.path.join(ROOT, "docs", "DATA_CONTRACTS.md")
        with open(path, encoding="utf-8") as f:
            doc = f.read()
        # The contract phrase may span lines in the markdown — match on the
        # less brittle phrase that appears on its own line.
        # Today: line 110 reads
        #   "ONLY `pnl_usd`; `commission` is **informational/audit-only and MUST NOT be"
        # followed by "subtracted again ..." on the next line.
        # Match the key tokens that survive any reflow.
        assert "informational/audit-only" in doc, (
            "DATA_CONTRACTS.md lost its commission-double-deduction warning "
            "(the 'informational/audit-only' phrase is the canonical marker). "
            "Restore it — the engineering contract depends on it being read."
        )
