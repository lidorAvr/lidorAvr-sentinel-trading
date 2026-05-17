"""
Sprint-27 W4c — telegram_bot.py:872 raw Supabase read → repo parity proof
(Architecture S26-R1).

Before W4c, `_handle_addon_command` did the lone residual direct read:

    res = supabase.table("trades").select("*").execute()
    df  = pd.DataFrame(res.data)

After W4c it routes through the repository layer (the documented S26-R1
micro-phase) — strictly additive, NO wholesale rewrite, C1 guard / admin gate /
B3 logic UNCHANGED:

    df  = pd.DataFrame(repo.get_all_trades(supabase))

`supabase_repository.get_all_trades(sb)` issues `sb.table("trades")
.select("*").execute().data or []` — the byte-identical query, just `... or []`
where the inline read used the raw `res.data`. This proof pins, against a mock
Supabase, that the DataFrame the call site consumes is BYTE-IDENTICAL for every
representative result shape:
  • non-empty list of rows  → identical rows, identical column order
  • empty list `[]`         → empty DataFrame (identical)
  • `None` `.data`          → empty DataFrame (identical: pd.DataFrame(None)
                              == pd.DataFrame([]))
and that the SAME query (`.table("trades").select("*").execute()`) is issued.
"""
import os
import sys
import importlib.util
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _load_real(modname):
    """Load the REAL <modname> from source into a FRESH, throw-away module
    object — WITHOUT touching sys.modules — regardless of whether an earlier
    test polluted sys.modules[modname] with a MagicMock
    (test_phase_b3_addon_cid / test_telegram_backlog / test_telegram_portfolio
    inject MagicMock stubs for supabase_repository / engine_core and never
    restore them — a long-standing collection-order pollution this proof must
    be resilient to so it pins the REAL query, not a MagicMock).

    Called INSIDE each test (function-scoped) and side-effect-free: this proof
    is fully collection-order-independent and never leaks into / out of any
    other suite file (the Sprint self-containment discipline)."""
    path = os.path.join(os.path.dirname(__file__), "..", f"{modname}.py")
    spec = importlib.util.spec_from_file_location(
        f"_real_w4c_{modname}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mock_supabase(data):
    """A mock Supabase whose .table('trades').select('*').execute().data ==
    `data`, recording the exact query chain so we can assert it is unchanged."""
    sb = MagicMock(name="supabase")
    exec_res = MagicMock(name="execute_result")
    exec_res.data = data
    (sb.table.return_value
       .select.return_value
       .execute.return_value) = exec_res
    return sb, exec_res


# Representative `trades` rows (shape the addon call site consumes:
# campaign_id / symbol / price / base_price / base_qty / quantity / stop_loss
# / initial_stop / setup_type — get_open_positions_campaign + the lot-state).
_ROWS = [
    {"campaign_id": "C-1", "symbol": "NVDA", "side": "BUY", "price": 100.0,
     "base_price": 100.0, "base_qty": 10, "quantity": 10, "stop_loss": 95.0,
     "initial_stop": 95.0, "setup_type": "EP", "realized_pnl": 0.0},
    {"campaign_id": "C-2", "symbol": "HOOD", "side": "BUY", "price": 22.0,
     "base_price": 22.0, "base_qty": 50, "quantity": 50, "stop_loss": 20.0,
     "initial_stop": 20.0, "setup_type": "VCP", "realized_pnl": 12.5},
]


@pytest.fixture
def repo():
    """The REAL supabase_repository, loaded fresh per test (immune to the
    pre-existing MagicMock sys.modules pollution; no global side effect)."""
    return _load_real("supabase_repository")


class TestW4cRepoParity:
    """Old raw read vs the new repo call → byte-identical consumed DataFrame."""

    @pytest.mark.parametrize("data", [
        _ROWS,          # the common non-empty case
        [],             # 0 trades
        None,           # Supabase returned .data == None
    ])
    def test_consumed_dataframe_byte_identical(self, repo, data):
        # OLD path (pre-W4c, telegram_bot.py:872 verbatim):
        sb_old, _ = _mock_supabase(data)
        res = sb_old.table("trades").select("*").execute()
        df_old = pd.DataFrame(res.data)

        # NEW path (post-W4c — exactly what telegram_bot.py now runs):
        sb_new, _ = _mock_supabase(data)
        df_new = pd.DataFrame(repo.get_all_trades(sb_new))

        # Byte-identical: same shape, same columns (order), same values.
        assert list(df_new.columns) == list(df_old.columns)
        assert df_new.shape == df_old.shape
        # .equals is True for both the populated and the (0,0) empty frames
        # (pd.DataFrame(None) == pd.DataFrame([]) — proven here too).
        assert df_new.equals(df_old)

    def test_same_query_is_issued(self, repo):
        # The repo issues the byte-identical query the inline read issued:
        # .table("trades").select("*").execute(). Assert the chain + args.
        sb, exec_res = _mock_supabase(_ROWS)
        out = repo.get_all_trades(sb)
        sb.table.assert_called_once_with("trades")
        sb.table.return_value.select.assert_called_once_with("*")
        (sb.table.return_value
           .select.return_value.execute.assert_called_once_with())
        # Repo returns `.data or []`; for a non-empty list that IS `.data`.
        assert out == _ROWS
        assert out is exec_res.data  # non-empty ⇒ `data or []` is `data`

    def test_none_data_yields_empty_list_not_none(self, repo):
        # The ONLY representational delta vs the raw read is `... or []`:
        # raw read passed `None` to pd.DataFrame; the repo passes `[]`.
        # Both yield the SAME empty (0,0) DataFrame — pinned here so the
        # "byte-identical consumed value" claim is explicit.
        sb, _ = _mock_supabase(None)
        assert repo.get_all_trades(sb) == []
        assert pd.DataFrame(None).equals(pd.DataFrame([]))

    def test_downstream_open_positions_identical(self, repo):
        # End-to-end: feed BOTH frames to the SAME downstream the call site
        # uses (engine_core.get_open_positions_campaign) → identical result.
        # Load the REAL engine_core (resilient to the same MagicMock
        # collection-order pollution).
        ec = _load_real("engine_core")
        sb_old, _ = _mock_supabase(_ROWS)
        df_old = pd.DataFrame(sb_old.table("trades").select("*")
                              .execute().data)
        sb_new, _ = _mock_supabase(_ROWS)
        df_new = pd.DataFrame(repo.get_all_trades(sb_new))

        r_old = ec.get_open_positions_campaign(df_old)
        r_new = ec.get_open_positions_campaign(df_new)
        assert r_old["ok"] == r_new["ok"]
        # The consumed open-positions DataFrame is byte-identical.
        assert r_old["data"].equals(r_new["data"])


class TestW4cCallSiteWiring:
    """The swap is the documented additive micro-phase: the call site now uses
    repo.get_all_trades; the raw `.table("trades")` read is gone from
    telegram_bot.py; the C1 guard + B3 logic are untouched (still present)."""

    def _src(self):
        path = os.path.join(os.path.dirname(__file__), "..",
                            "telegram_bot.py")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_no_residual_raw_trades_read_in_telegram_bot(self):
        src = self._src()
        # The S26-R1 residual is gone (the only direct .table("trades") read).
        assert 'supabase.table("trades").select("*").execute()' not in src
        assert "repo.get_all_trades(supabase)" in src

    def test_c1_guard_and_b3_logic_unchanged_present(self):
        src = self._src()
        # C1 fail-closed guard still defined + still gating the addon command
        # is out of W4c scope, but the guard helper must remain intact.
        assert "def _require_active_dev_session(chat_id) -> bool:" in src
        # B3: the planned campaign_id is still persisted into addon_pending.
        assert '"campaign_id": _planned_cid,' in src or \
               '"campaign_id": _planned_cid' in src
