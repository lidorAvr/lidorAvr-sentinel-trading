"""test_b1_campaign_target_locked.py — Migration 003 + entry-time snapshot.

Covers the B1 fix from the 2026-05-14 session: the "campaign target"
displayed in /portfolio room must reflect the risk_pct + NAV active when
the trade was OPENED, not the current values that drift every time the
user changes risk.

Three integration layers:
  1. ibkr_trade_importer reads sentinel_config.json and stamps
     risk_pct_at_entry + nav_at_entry on every parsed row.
  2. engine_core.get_open_positions_campaign surfaces those snapshots
     from the campaign's FIRST BUY trade onto each campaign row.
  3. (Verified indirectly via 1+2) telegram_portfolio.handle_portfolio_room
     computes target_risk_usd_at_entry from the snapshot and passes it
     to evaluate_position_engine so sizing_status quotes the locked target.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _mod in ("telebot", "telebot.types", "supabase", "dotenv"):
    sys.modules.setdefault(_mod, MagicMock())
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import ibkr_trade_importer as imp
import engine_core as ec


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _xml_with_one_trade(trade_id="T1", date="20260514", side="BUY",
                        qty=10, price=100.0, symbol="CAT"):
    return (
        f"<FlexQueryResponse><FlexStatements>"
        f"<FlexStatement fromDate='20260414' toDate='20260514'>"
        f"<Trades>"
        f"<Trade tradeID='{trade_id}' symbol='{symbol}' buySell='{side}' "
        f"quantity='{qty}' tradePrice='{price}' tradeDate='{date}' "
        f"fifoPnlRealized='0' />"
        f"</Trades></FlexStatement></FlexStatements></FlexQueryResponse>"
    )


@pytest.fixture
def write_config(tmp_path, monkeypatch):
    """Helper: write a sentinel_config.json snapshot and point the importer at it."""
    def _writer(risk_pct=None, nav=None, total_deposited=None):
        cfg_path = tmp_path / "sentinel_config.json"
        cfg = {}
        if risk_pct is not None:
            cfg["risk_pct_input"] = risk_pct
        if nav is not None:
            cfg["nav"] = nav
        if total_deposited is not None:
            cfg["total_deposited"] = total_deposited
        cfg_path.write_text(json.dumps(cfg))
        monkeypatch.setattr("ibkr_trade_importer._CONFIG_PATH", str(cfg_path))
        return str(cfg_path)
    return _writer


# ════════════════════════════════════════════════════════════════════════════════
# Layer 1 — ibkr_trade_importer stamps snapshot on parsed rows
# ════════════════════════════════════════════════════════════════════════════════

class TestImporterStampsSnapshot:
    def test_writes_snapshot_when_config_present(self, write_config):
        write_config(risk_pct=0.35, nav=7500.0)
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        assert len(rows) == 1
        assert rows[0]["risk_pct_at_entry"] == pytest.approx(0.35)
        assert rows[0]["nav_at_entry"]      == pytest.approx(7500.0)

    def test_uses_total_deposited_when_nav_missing(self, write_config):
        """Pre-IBKR-sync fresh installs only have total_deposited. Use it as
        fallback so the snapshot isn't NULL."""
        write_config(risk_pct=0.5, total_deposited=8000.0)
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        assert rows[0]["nav_at_entry"] == pytest.approx(8000.0)

    def test_nav_takes_priority_over_total_deposited(self, write_config):
        write_config(risk_pct=0.6, nav=9000.0, total_deposited=8000.0)
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        assert rows[0]["nav_at_entry"] == pytest.approx(9000.0)

    def test_missing_config_leaves_columns_null(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ibkr_trade_importer._CONFIG_PATH",
                            str(tmp_path / "does_not_exist.json"))
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        assert rows[0]["risk_pct_at_entry"] is None
        assert rows[0]["nav_at_entry"]      is None

    def test_unparseable_config_does_not_crash(self, tmp_path, monkeypatch):
        bad = tmp_path / "broken.json"
        bad.write_text("{not valid json")
        monkeypatch.setattr("ibkr_trade_importer._CONFIG_PATH", str(bad))
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        # Defensive: bad config → NULL columns, not a raise
        assert rows[0]["risk_pct_at_entry"] is None
        assert rows[0]["nav_at_entry"]      is None

    def test_non_numeric_risk_pct_leaves_null(self, tmp_path, monkeypatch):
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"risk_pct_input": "abc", "nav": 1000}))
        monkeypatch.setattr("ibkr_trade_importer._CONFIG_PATH", str(cfg))
        rows = imp.parse_trades_from_xml(_xml_with_one_trade())
        # nav still gets snapshotted; risk_pct stays NULL
        assert rows[0]["nav_at_entry"] == pytest.approx(1000.0)
        assert rows[0]["risk_pct_at_entry"] is None

    def test_every_row_in_batch_gets_same_snapshot(self, write_config):
        """Importing a multi-trade XML stamps every row with the SAME
        snapshot. Per-trade variability would require knowing each trade's
        historical config, which we don't reconstruct."""
        write_config(risk_pct=0.5, nav=7800.0)
        xml = (
            "<FlexQueryResponse><FlexStatements><FlexStatement "
            "fromDate='20260414' toDate='20260514'><Trades>"
            "<Trade tradeID='A' symbol='CAT' buySell='BUY' quantity='10' "
            "tradePrice='100' tradeDate='20260510' fifoPnlRealized='0' />"
            "<Trade tradeID='B' symbol='MRVL' buySell='BUY' quantity='5' "
            "tradePrice='80' tradeDate='20260511' fifoPnlRealized='0' />"
            "</Trades></FlexStatement></FlexStatements></FlexQueryResponse>"
        )
        rows = imp.parse_trades_from_xml(xml)
        assert len(rows) == 2
        for r in rows:
            assert r["risk_pct_at_entry"] == pytest.approx(0.5)
            assert r["nav_at_entry"]      == pytest.approx(7800.0)


# ════════════════════════════════════════════════════════════════════════════════
# Layer 2 — engine_core surfaces snapshot on each campaign row
# ════════════════════════════════════════════════════════════════════════════════

class TestEngineSurfacesSnapshot:
    def _make_df(self, rows):
        import pandas as pd
        return pd.DataFrame(rows)

    def test_surfaces_snapshot_from_first_buy(self):
        df = self._make_df([
            {"trade_id": "T1", "symbol": "CAT", "campaign_id": "CAT_T1",
             "side": "BUY", "quantity": 10, "price": 100.0, "stop_loss": 90.0,
             "initial_stop": 90.0, "pnl_usd": 0, "trade_date": "2026-05-10",
             "setup_type": "EP", "management_state": "full_position",
             "risk_pct_at_entry": 0.35, "nav_at_entry": 7500.0},
        ])
        result = ec.get_open_positions_campaign(df)
        assert result["ok"]
        camps = result["data"]
        assert not camps.empty
        row = camps.iloc[0]
        assert row["risk_pct_at_entry"] == pytest.approx(0.35)
        assert row["nav_at_entry"]      == pytest.approx(7500.0)

    def test_addon_after_rate_change_keeps_first_buy_snapshot(self):
        """Add-on trade was imported at a different rate. Campaign target
        must lock to the FIRST BUY's rate, not the add-on's."""
        df = self._make_df([
            {"trade_id": "T1", "symbol": "CAT", "campaign_id": "CAT_T1",
             "side": "BUY", "quantity": 10, "price": 100.0, "stop_loss": 90.0,
             "initial_stop": 90.0, "pnl_usd": 0, "trade_date": "2026-05-01",
             "setup_type": "EP", "management_state": "full_position",
             "risk_pct_at_entry": 0.35, "nav_at_entry": 7500.0},
            {"trade_id": "T2", "symbol": "CAT", "campaign_id": "CAT_T1",
             "side": "BUY", "quantity": 5, "price": 110.0, "stop_loss": 90.0,
             "initial_stop": 90.0, "pnl_usd": 0, "trade_date": "2026-05-14",
             "setup_type": "EP", "management_state": "full_position",
             "risk_pct_at_entry": 0.60, "nav_at_entry": 8000.0},
        ])
        result = ec.get_open_positions_campaign(df)
        row = result["data"].iloc[0]
        # First buy was at 0.35% / $7500 — that's what locks
        assert row["risk_pct_at_entry"] == pytest.approx(0.35)
        assert row["nav_at_entry"]      == pytest.approx(7500.0)

    def test_null_snapshot_legacy_trades(self):
        """Pre-migration trades have NULL snapshot. The aggregation must
        surface None, not crash."""
        df = self._make_df([
            {"trade_id": "T1", "symbol": "OLD", "campaign_id": "OLD_T1",
             "side": "BUY", "quantity": 10, "price": 50.0, "stop_loss": 45.0,
             "initial_stop": 45.0, "pnl_usd": 0, "trade_date": "2026-04-01",
             "setup_type": "EP", "management_state": "full_position",
             "risk_pct_at_entry": None, "nav_at_entry": None},
        ])
        result = ec.get_open_positions_campaign(df)
        assert result["ok"]
        row = result["data"].iloc[0]
        assert row["risk_pct_at_entry"] is None
        assert row["nav_at_entry"]      is None

    def test_works_without_snapshot_columns_at_all(self):
        """Bullet-proofing: very-old data without the columns at all should
        still aggregate (the engine should NOT KeyError)."""
        df = self._make_df([
            {"trade_id": "T1", "symbol": "OLD", "campaign_id": "OLD_T1",
             "side": "BUY", "quantity": 10, "price": 50.0, "stop_loss": 45.0,
             "initial_stop": 45.0, "pnl_usd": 0, "trade_date": "2026-04-01",
             "setup_type": "EP", "management_state": "full_position"},
        ])
        result = ec.get_open_positions_campaign(df)
        assert result["ok"]
        row = result["data"].iloc[0]
        # Missing columns surface as None (via .get())
        assert row.get("risk_pct_at_entry") in (None, float("nan")) or \
               row["risk_pct_at_entry"] != row["risk_pct_at_entry"]  # NaN check


# ════════════════════════════════════════════════════════════════════════════════
# Migration 003 contract — verify_migrations.py knows about it
# ════════════════════════════════════════════════════════════════════════════════

class TestMigration003Registered:
    def test_verify_script_lists_003(self):
        # Import the manifest list
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_verify",
            os.path.join(os.path.dirname(__file__), "..", "migrations",
                         "verify_migrations.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        filenames = [m[0] for m in mod.MIGRATIONS]
        assert "003_trade_entry_snapshots.sql" in filenames

        # Entry has the two new columns
        m003 = next(m for m in mod.MIGRATIONS
                    if m[0] == "003_trade_entry_snapshots.sql")
        assert m003[1] == "trades"
        assert "risk_pct_at_entry" in m003[2]
        assert "nav_at_entry"      in m003[2]

    def test_migration_sql_exists_and_is_idempotent(self):
        path = os.path.join(os.path.dirname(__file__), "..", "migrations",
                            "003_trade_entry_snapshots.sql")
        assert os.path.exists(path), "migration file missing"
        sql = open(path).read()
        assert "IF NOT EXISTS" in sql, "migration must be idempotent (re-runnable)"
        assert "risk_pct_at_entry" in sql
        assert "nav_at_entry"      in sql
        assert "ALTER TABLE trades" in sql
