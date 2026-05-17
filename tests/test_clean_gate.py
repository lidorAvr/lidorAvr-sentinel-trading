"""
Tests for telegram_clean_gate.py — the Sprint-12 `/clean` defaulted-NO
confirmation gate (Mark §2 / SPRINT12_DESIGN §2).

Verifies the Wave-2 plan cases F–J:
* F. default-NO: `/clean` previews and performs ZERO repo.update_trade before
  a clean_confirm|yes; the keyboard's first/default action is NO.
* G. reject = no-op: clean_confirm|no → zero update_trade, state cleared.
* H. confirm path: clean_confirm|yes → audit row written, then the bulk write
  is BYTE-IDENTICAL to the legacy loop (same upd dicts for the same rows).
* I. protected rows: rows in an open campaign receive ZERO update_trade and
  are counted as protected (M) in the preview.
* J. idempotent: double-tap clean_confirm|yes does not run the bulk write
  twice (pending cleared on first resolve).

Same isolation pattern as test_telegram_stop_promote.py (stub heavy deps,
patch.object on the real module).
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# sys.modules is process-global and this file sorts early alphabetically.
# Stub ONLY the modules that genuinely cannot import in a sandbox (telebot /
# supabase / dotenv) and never overwrite a real module a later test imports
# for real (engine_core / adaptive_risk_engine / ibkr_sync_runner /
# telegram_formatters all import cleanly and several real test files depend
# on the genuine module — stubbing them here poisoned those siblings).
for mod in ["telebot", "supabase", "dotenv"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()


class _FIMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)


class _FIButton:
    def __init__(self, text="", callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""


_tb_mod = sys.modules["telebot"]
_existing = getattr(_tb_mod, "types", None)
if _existing is None or not isinstance(
    getattr(_existing, "InlineKeyboardMarkup", None), type
):
    _tbt = py_types.ModuleType("telebot.types")
    _tbt.InlineKeyboardMarkup = _FIMarkup
    _tbt.InlineKeyboardButton = _FIButton
    _tbt.ReplyKeyboardMarkup = _FIMarkup
    _tbt.KeyboardButton = _FIButton
    _tbt.ReplyKeyboardRemove = _FIMarkup
    _tb_mod.types = _tbt
    sys.modules["telebot.types"] = _tbt

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot = MagicMock()
    _bc.supabase = MagicMock()
    _bc.user_state = {}
    _bc.RTL = "‏"
    _bc.TOKEN = ""
    _bc.ADMIN_ID = ""
    sys.modules["bot_core"] = _bc

import telegram_clean_gate as cg  # noqa: E402


# Old rows (trade_date < cutoff so they're in get_old_trades). Two need an
# update; one is complete (no update); one belongs to an OPEN campaign.
_OLD_ROWS = [
    {"trade_id": 1, "campaign_id": "AAA_1", "side": "BUY",
     "setup_type": None, "quality": None, "initial_stop": 0},
    {"trade_id": 2, "campaign_id": "BBB_2", "side": "SELL",
     "setup_type": "VCP", "quality": 3, "score": None,
     "image_url": None, "management_notes": None},
    {"trade_id": 3, "campaign_id": "CCC_3", "side": "BUY",
     "setup_type": "VCP", "quality": 4, "initial_stop": 88.0},  # complete
    {"trade_id": 4, "campaign_id": "OPEN_9", "side": "BUY",
     "setup_type": None, "quality": None, "initial_stop": 0},  # OPEN campaign
]


def _legacy_upd(t):
    """The pre-gate byte-identical upd-dict logic (telegram_bot.py:382-395),
    reproduced here so the gate write can be golden-compared against it."""
    needs = False
    upd = {}
    if t.get('setup_type') is None: upd['setup_type'] = "Legacy"; needs = True
    if t.get('quality') is None: upd['quality'] = -1; needs = True
    if t.get('side', '').upper() == 'BUY':
        if t.get('initial_stop') in [None, 0]: upd['initial_stop'] = -1; upd['stop_loss'] = -1; needs = True
    if t.get('side', '').upper() == 'SELL':
        if t.get('score') is None: upd['score'] = -1; needs = True
        if t.get('image_url') is None: upd['image_url'] = "Skipped"; needs = True
        if t.get('management_notes') is None: upd['management_notes'] = "Skipped"; needs = True
    return needs, upd


def _patched(open_cids=("OPEN_9",)):
    """Context: repo.get_old_trades → _OLD_ROWS; open-campaign set = open_cids;
    fresh user_state + bot + supabase per test."""
    bot = MagicMock()
    bot.send_message.return_value = MagicMock(message_id=1)
    sb = MagicMock()
    state = {}
    repo = MagicMock()
    repo.get_old_trades = lambda _sb, _bd: list(_OLD_ROWS)

    open_df = pd.DataFrame({"campaign_id": list(open_cids)})
    ec = MagicMock()
    ec.get_open_positions_campaign = lambda _df: {
        "ok": True, "error": None, "data": open_df}

    return patch.multiple(
        cg, bot=bot, supabase=sb, user_state=state, repo=repo, ec=ec
    ), bot, sb, state, repo


class TestDryRunCounts:
    def test_preview_counts_exclude_open_campaign(self):
        ctx, bot, sb, state, repo = _patched()
        with ctx:
            n, m = cg._dry_run_counts("2026-01-01")
        # rows 1,2 need update & not open → n=2; row 4 needs update but OPEN
        # → protected m=1; row 3 complete → neither.
        assert n == 2
        assert m == 1


class TestDefaultNo:
    # F. /clean previews and writes NOTHING before a yes.
    def test_entry_sends_confirm_and_zero_writes(self):
        ctx, bot, sb, state, repo = _patched()
        with ctx:
            cg.handle_clean_entry(123)
        repo.update_trade = getattr(repo, "update_trade")
        assert repo.update_trade.call_count == 0
        assert state[123]["action"] == "clean_pending"
        # default/first button is NO (defaulted-safe; mirrors loosen_confirm).
        confirm_msg = bot.send_message.call_args_list[-1]
        markup = confirm_msg.kwargs["reply_markup"]
        assert markup.buttons[0].callback_data == "clean_confirm|no"
        assert markup.buttons[1].callback_data == "clean_confirm|yes"

    def test_entry_no_candidates_no_confirm_no_write(self):
        ctx, bot, sb, state, repo = _patched()
        repo.get_old_trades = lambda _s, _b: [
            {"trade_id": 9, "campaign_id": "Z_1", "side": "BUY",
             "setup_type": "VCP", "quality": 1, "initial_stop": 5.0}]
        with ctx:
            cg.handle_clean_entry(123)
        assert "clean_pending" not in [
            v.get("action") for v in state.values()] if state else True
        assert repo.update_trade.call_count == 0


class TestRejectIsNoOp:
    # G. clean_confirm|no → zero writes, state cleared, "בוטל".
    def test_reject_writes_nothing(self):
        ctx, bot, sb, state, repo = _patched()
        with ctx:
            cg.handle_clean_entry(55)
            assert state[55]["action"] == "clean_pending"
            with patch.object(cg, "get_next_missing", create=True):
                # finalize lazily imports telegram_bot.get_next_missing; only
                # the confirm path reaches it, so reject never imports it.
                cg.finalize_pending_clean(55, approved=False)
        assert repo.update_trade.call_count == 0
        assert 55 not in state  # pending cleared

    def test_no_pending_is_noop(self):
        ctx, bot, sb, state, repo = _patched()
        with ctx:
            cg.finalize_pending_clean(77, approved=True)
        assert repo.update_trade.call_count == 0


class TestConfirmPath:
    # H. clean_confirm|yes → audit FIRST-class (one row), bulk write
    # byte-identical, open campaign skipped.
    def test_confirm_audit_and_byte_identical_writes(self):
        ctx, bot, sb, state, repo = _patched()
        updates = []
        repo.update_trade = lambda _sb, tid, upd: updates.append((tid, upd))
        audited = {}

        import audit_logger
        orig = audit_logger.log_action

        def _spy(_sb, action, **kw):
            audited["action"] = action
            audited["metadata"] = kw.get("metadata")
            audited["before"] = kw.get("before")
            audited["after"] = kw.get("after")
            return True

        audit_logger.log_action = _spy
        try:
            with ctx, patch("telegram_bot.get_next_missing",
                            MagicMock(), create=True):
                cg.handle_clean_entry(9)
                cg.finalize_pending_clean(9, approved=True)
        finally:
            audit_logger.log_action = orig

        # I. open-campaign row (trade_id 4) is NEVER written.
        written_ids = [tid for tid, _ in updates]
        assert 4 not in written_ids
        # rows 1 & 2 written; row 3 (complete) not written.
        assert sorted(written_ids) == [1, 2]
        # H. byte-identical upd dicts vs the legacy logic.
        for tid, upd in updates:
            row = next(r for r in _OLD_ROWS if r["trade_id"] == tid)
            _needs, legacy = _legacy_upd(row)
            assert upd == legacy

        # one audit row, Mark §2.2 exact kind + counts.
        import audit_logger as al
        assert audited["action"] == al.ACTION_SETTINGS_CHANGE
        md = audited["metadata"]
        assert md["kind"] == "archive_sweep_clean"
        assert md["candidates"] == 2
        assert md["updated"] == 2
        assert md["rows_protected"] == 1
        assert audited["before"] == {"rows_to_update": 2}
        assert audited["after"] == {"rows_updated": 2}


class TestIdempotent:
    # J. double-tap clean_confirm|yes does not run the bulk write twice.
    def test_double_confirm_runs_bulk_once(self):
        ctx, bot, sb, state, repo = _patched()
        calls = []
        repo.update_trade = lambda _sb, tid, upd: calls.append(tid)
        with ctx, patch("telegram_bot.get_next_missing",
                        MagicMock(), create=True):
            cg.handle_clean_entry(42)
            cg.finalize_pending_clean(42, approved=True)
            first = list(calls)
            cg.finalize_pending_clean(42, approved=True)  # double tap
        assert calls == first  # second tap added nothing (pending cleared)


class TestProtectionAbsolute:
    # I. UPDATE-only — the gate adds NO delete path. Assert on actual CODE
    # (AST), not docstring prose: no Supabase `.delete(` attribute call and
    # no repo delete invocation anywhere in the module.
    def test_gate_module_has_no_delete_call(self):
        import ast as _ast
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1]
               / "telegram_clean_gate.py").read_text()
        tree = _ast.parse(src)
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call) and isinstance(
                node.func, _ast.Attribute
            ):
                assert "delete" not in node.func.attr.lower(), (
                    f"unexpected delete-like call: {node.func.attr}"
                )
