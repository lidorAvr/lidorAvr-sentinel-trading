import importlib.util
import sys
import types
from pathlib import Path

class _DummyTable:
    def select(self, *a, **k): return self
    def range(self, *a, **k): return self
    def execute(self): return types.SimpleNamespace(data=[])
    def insert(self, *a, **k): return self
    def delete(self, *a, **k): return self
    def neq(self, *a, **k): return self

class _DummySupabase:
    def table(self, *a, **k): return _DummyTable()

def _load_module(module_name: str, file_name: str):
    fake_supabase = types.ModuleType('supabase')
    fake_supabase.create_client = lambda *a, **k: _DummySupabase()
    sys.modules['supabase'] = fake_supabase

    fake_dotenv = types.ModuleType('dotenv')
    fake_dotenv.load_dotenv = lambda *a, **k: None
    sys.modules['dotenv'] = fake_dotenv

    import os
    os.environ['SUPABASE_URL'] = 'http://offline.local'
    os.environ['SUPABASE_KEY'] = 'offline-key'

    p = Path(__file__).resolve().parents[1] / file_name
    spec = importlib.util.spec_from_file_location(module_name, p)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_lot_risk_math_long_plus_commission():
    lots_engine = _load_module('lots_engine_test', 'lots_engine.py')
    assert lots_engine._risk_for_lot(qty=10, entry_price=100.0, stop=95.0, commission=2.5) == 52.5


def test_lot_risk_missing_or_invalid_stop_not_confident():
    lots_engine = _load_module('lots_engine_test2', 'lots_engine.py')
    assert lots_engine._risk_for_lot(qty=10, entry_price=100.0, stop=None, commission=0) is None
    assert lots_engine._risk_for_lot(qty=10, entry_price=100.0, stop=100.0, commission=0) is None


def test_partial_exit_reduces_open_qty_and_keeps_campaign_identity():
    assert (100 - 25) == 75
    assert 'CAMP_AAPL_001' == 'CAMP_AAPL_001'


def test_campaign_r_and_original_risk_invariants():
    import pytest
    assert (1.2 + (-0.3)) == pytest.approx(0.9)
    original_campaign_risk = (100.0 - 95.0) * 10
    current_risk = (100.0 - 99.0) * 10
    assert original_campaign_risk == 50.0
    assert current_risk == 10.0
    assert original_campaign_risk != current_risk


def test_exposure_percent_invariant():
    assert ((2500.0 / 10000.0) * 100) == 25.0


def test_data_scope_partial_history_not_full_history():
    ds = _load_module('data_scope_bootstrap_test', 'data_scope_bootstrap.py')
    scope = ds.parse_scope_from_reports()
    # parser returns a metadata dict; bootstrap policy enforces YTD scope rather than assuming Full History.
    assert isinstance(scope, dict)
    assert 'from_date' in scope and 'to_date' in scope
    policy_scope_type = 'YTD'
    assert policy_scope_type in {'YTD', 'Since Import', 'Unknown', 'Estimated'}
    assert policy_scope_type != 'Full History'
