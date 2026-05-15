"""
Tests for the Minervini ratchet-up guard (MARK_DAY3_GUARDRAILS U3/C3).

Founder decision: a long position's stop only moves UP. Lowering it
("loosening") requires an explicit, defaulted-NO confirmation and a
write-only audit_log row. The stop *value* math is unchanged — the guard
only gates whether the byte-identical repo.update_stop_for_campaign runs.

Covers:
* _is_loosen edge matrix (None / 0 / tighten / within-eps / loosen)
* guard_stop_write: tighten → passthrough; loosen → intercept + confirm UI
  + pending state; unknown current stop → passthrough (documented limit)
* finalize_pending_loosen: no-pending; reject (default, no write/no audit);
  approve (audit BEFORE write, correct args, state cleared); batch resume
* get_campaign_current_stop: match / no-match / repo-not-ok / exception

Same stubbing pattern as test_telegram_stop_promote.py so it is robust to
sibling Telegram test modules polluting global sys.modules.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch, call
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod in ["telebot", "supabase", "dotenv", "engine_core", "adaptive_risk_engine",
            "telegram_formatters", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

_tb_mod = sys.modules["telebot"]


class _FIMarkup:
    def __init__(self, *a, **k): self.buttons = []
    def add(self, *btns): self.buttons.extend(btns)


class _FIButton:
    def __init__(self, text="", callback_data=None, *a, **k):
        self.text = text
        self.callback_data = callback_data or ""


_existing = getattr(_tb_mod, "types", None)
if _existing is None or not isinstance(
    getattr(_existing, "InlineKeyboardMarkup", None), type
):
    _tbt2 = py_types.ModuleType("telebot.types")
    _tbt2.InlineKeyboardMarkup = _FIMarkup
    _tbt2.InlineKeyboardButton = _FIButton
    _tbt2.ReplyKeyboardMarkup  = _FIMarkup
    _tbt2.KeyboardButton       = _FIButton
    _tbt2.ReplyKeyboardRemove  = _FIMarkup
    _tb_mod.types = _tbt2
    sys.modules["telebot.types"] = _tbt2

if "bot_core" not in sys.modules:
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = MagicMock()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""
    sys.modules["bot_core"] = _bc

import telegram_stop_promote as sp  # noqa


class _StubTypes:
    InlineKeyboardMarkup = _FIMarkup
    InlineKeyboardButton = _FIButton
    ReplyKeyboardMarkup  = _FIMarkup
    KeyboardButton       = _FIButton
    ReplyKeyboardRemove  = _FIMarkup


# ── _is_loosen edge matrix ─────────────────────────────────────────────────────

class TestIsLoosen:
    def test_none_current_is_not_loosen(self):
        assert sp._is_loosen(None, 95.0) is False

    def test_zero_or_negative_current_is_not_loosen(self):
        # first-time stop entry (no prior stop) must pass through
        assert sp._is_loosen(0, 95.0) is False
        assert sp._is_loosen(-1, 95.0) is False

    def test_tightening_is_not_loosen(self):
        assert sp._is_loosen(90.0, 95.0) is False   # stop UP

    def test_equal_is_not_loosen(self):
        assert sp._is_loosen(95.0, 95.0) is False

    def test_within_epsilon_is_not_loosen(self):
        assert sp._is_loosen(95.0, 94.999) is False  # sub-cent noise

    def test_clear_loosen_is_detected(self):
        assert sp._is_loosen(95.0, 90.0) is True     # stop DOWN

    def test_bad_input_is_not_loosen(self):
        assert sp._is_loosen("abc", 90.0) is False
        assert sp._is_loosen(95.0, None) is False


# ── guard_stop_write ───────────────────────────────────────────────────────────

class TestGuardStopWrite:
    def _run(self, current, new, state):
        fake_bot = MagicMock()
        with patch.object(sp, 'types', _StubTypes), \
             patch.object(sp, 'bot', fake_bot), \
             patch.object(sp, 'user_state', state):
            intercepted = sp.guard_stop_write(
                123, cid="CAT_1", sym="CAT",
                new_sl=new, current_stop=current,
                resume={'batch': True})
        return intercepted, fake_bot, state

    def test_tighten_sends_nothing(self):
        state = {}
        intercepted, fake_bot, st = self._run(90.0, 95.0, state)
        assert intercepted is False
        fake_bot.send_message.assert_not_called()
        assert st == {}

    def test_unknown_current_passes_through(self):
        state = {}
        intercepted, fake_bot, st = self._run(None, 90.0, state)
        assert intercepted is False
        fake_bot.send_message.assert_not_called()

    def test_loosen_intercepts_and_stashes_pending(self):
        state = {}
        intercepted, fake_bot, st = self._run(95.0, 90.0, state)
        assert intercepted is True
        assert st[123]["action"] == "loosen_pending"
        p = st[123]["pending"]
        assert p["cid"] == "CAT_1"
        assert p["sym"] == "CAT"
        assert p["new_sl"] == 90.0
        assert p["current_stop"] == 95.0
        assert p["resume"] == {'batch': True}

    def test_loosen_sends_defaulted_no_confirmation(self):
        state = {}
        intercepted, fake_bot, st = self._run(95.0, 90.0, state)
        assert fake_bot.send_message.called
        _args, kwargs = fake_bot.send_message.call_args
        markup = kwargs["reply_markup"]
        cbs = [b.callback_data for b in markup.buttons]
        assert "loosen_confirm|yes" in cbs
        assert "loosen_confirm|no" in cbs
        # yes button text must carry the audit warning; no must be present
        yes_btn = next(b for b in markup.buttons if b.callback_data == "loosen_confirm|yes")
        assert "יומן" in yes_btn.text  # "logged to the audit journal"


# ── finalize_pending_loosen ────────────────────────────────────────────────────

class TestFinalize:
    def _ctx(self, state):
        fake_bot = MagicMock()
        fake_sb = MagicMock()
        fake_repo = MagicMock()
        fake_audit = MagicMock()
        cm = patch.multiple(
            sp,
            bot=fake_bot, supabase=fake_sb, repo=fake_repo,
            audit_logger=fake_audit, user_state=state,
            get_main_menu=lambda: "MAIN",
        )
        return cm, fake_bot, fake_sb, fake_repo, fake_audit

    def test_no_pending_is_safe_noop(self):
        state = {}
        cm, fbot, fsb, frepo, faud = self._ctx(state)
        with cm:
            sp.finalize_pending_loosen(123, True)
        frepo.update_stop_for_campaign.assert_not_called()
        faud.log_action.assert_not_called()
        assert fbot.send_message.called

    def test_reject_does_not_write_or_audit(self):
        state = {123: {"action": "loosen_pending", "pending": {
            "cid": "CAT_1", "sym": "CAT", "new_sl": 90.0,
            "current_stop": 95.0, "resume": {}}}}
        cm, fbot, fsb, frepo, faud = self._ctx(state)
        with cm:
            sp.finalize_pending_loosen(123, False)
        frepo.update_stop_for_campaign.assert_not_called()
        faud.log_action.assert_not_called()
        assert 123 not in state  # pending cleared
        _a, kw = fbot.send_message.call_args
        assert "בוטל" in _a[1] or "בוטל" in _a[0]

    def test_approve_audits_before_write_with_correct_args(self):
        state = {123: {"action": "loosen_pending", "pending": {
            "cid": "CAT_1", "sym": "CAT", "new_sl": 90.0,
            "current_stop": 95.0, "resume": {}}}}
        cm, fbot, fsb, frepo, faud = self._ctx(state)
        faud.ACTION_SETTINGS_CHANGE = "settings_change"
        order = []
        faud.log_action.side_effect = lambda *a, **k: order.append("audit")
        frepo.update_stop_for_campaign.side_effect = lambda *a, **k: order.append("write")
        with cm:
            sp.finalize_pending_loosen(123, True)
        # audit happens BEFORE the write (fail-open compliance trail)
        assert order == ["audit", "write"]
        # write args byte-identical to the legacy path: (sb, cid, new_sl)
        frepo.update_stop_for_campaign.assert_called_once_with(fsb, "CAT_1", 90.0)
        # audit carries before/after stop + the override metadata
        _a, kw = faud.log_action.call_args
        assert kw["before"] == {"stop_loss": 95.0}
        assert kw["after"] == {"stop_loss": 90.0}
        assert kw["metadata"]["kind"] == "stop_loosen_override"
        assert kw["metadata"]["symbol"] == "CAT"
        assert 123 not in state

    def test_approve_with_batch_resume_reopens_list(self):
        state = {123: {"action": "loosen_pending", "pending": {
            "cid": "CAT_1", "sym": "CAT", "new_sl": 90.0,
            "current_stop": 95.0, "resume": {"batch": True}}}}
        cm, fbot, fsb, frepo, faud = self._ctx(state)
        with cm, patch.object(sp, 'handle_stop_promote_entry') as hse:
            sp.finalize_pending_loosen(123, True)
        hse.assert_called_once_with(123)

    def test_approve_without_batch_does_not_reopen_list(self):
        state = {123: {"action": "loosen_pending", "pending": {
            "cid": "CAT_1", "sym": "CAT", "new_sl": 90.0,
            "current_stop": 95.0, "resume": {}}}}
        cm, fbot, fsb, frepo, faud = self._ctx(state)
        with cm, patch.object(sp, 'handle_stop_promote_entry') as hse:
            sp.finalize_pending_loosen(123, True)
        hse.assert_not_called()


# ── get_campaign_current_stop ──────────────────────────────────────────────────

class TestGetCampaignCurrentStop:
    def _ec(self, ok=True, rows=None):
        m = MagicMock()
        if rows is None:
            rows = [{"campaign_id": "CAT_1", "stop_loss": 95.0}]
        m.get_open_positions_campaign.return_value = {
            "ok": ok, "data": pd.DataFrame(rows), "error": "boom"}
        return m

    def test_resolves_matching_campaign_stop(self):
        frepo = MagicMock()
        frepo.get_all_trades.return_value = [{"campaign_id": "CAT_1"}]
        with patch.object(sp, 'repo', frepo), \
             patch.object(sp, 'ec', self._ec(rows=[
                 {"campaign_id": "MSFT_1", "stop_loss": 10.0},
                 {"campaign_id": "CAT_1", "stop_loss": 95.0}])):
            assert sp.get_campaign_current_stop("CAT_1") == 95.0

    def test_no_match_returns_none(self):
        frepo = MagicMock()
        frepo.get_all_trades.return_value = []
        with patch.object(sp, 'repo', frepo), \
             patch.object(sp, 'ec', self._ec(rows=[{"campaign_id": "X", "stop_loss": 1.0}])):
            assert sp.get_campaign_current_stop("CAT_1") is None

    def test_repo_not_ok_returns_none(self):
        frepo = MagicMock()
        frepo.get_all_trades.return_value = []
        with patch.object(sp, 'repo', frepo), \
             patch.object(sp, 'ec', self._ec(ok=False)):
            assert sp.get_campaign_current_stop("CAT_1") is None

    def test_empty_campaign_id_returns_none(self):
        assert sp.get_campaign_current_stop("") is None
        assert sp.get_campaign_current_stop(None) is None

    def test_exception_returns_none(self):
        frepo = MagicMock()
        frepo.get_all_trades.side_effect = RuntimeError("db down")
        with patch.object(sp, 'repo', frepo):
            assert sp.get_campaign_current_stop("CAT_1") is None
