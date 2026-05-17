"""
Phase B3 acceptance tests — Add-On `campaign_id` plan→confirm write-race.

Defect (Sprint-25 Arch audit F3): `/addon SYMBOL …` plans against a specific
open-position row (`telegram_bot.py` `sym_rows.iloc[0]` from
`ec.get_open_positions_campaign`). The pending state stored only `symbol`
(no campaign_id). At confirm, `telegram_callbacks.py` did an unconditional
fresh re-resolution `repo.get_open_campaign_for_symbol(supabase, sym)` and
wrote the Add-On management-notes + addon record to *whatever* that returned —
so if the open campaign for the symbol changed between plan and tap, the
write silently corrupted a *different* campaign's Supabase rows.

Fix (HARDENED mismatch policy, founder-approved):
  * telegram_bot.py — additively persist the planned `campaign_id` (the
    campaign_id of the exact open-position `row` used for entry/stop/qty).
  * telegram_callbacks.py `addon_confirm|YES` — 3 cases:
      (2a) stored cid present + re-resolved == planned -> proceed exactly as
           pre-B3 (byte-identical: identical repo.* calls + identical msgs).
      (2b) HARDENED: stored cid present + re-resolved != planned (the race)
           -> REFUSE: zero Supabase write, explicit Hebrew refusal, clear
           pending.
      (2c) stored cid absent/None (legacy/older in-flight pending) -> fall
           back to re-resolution and proceed exactly as pre-B3
           (byte-identical legacy path).

These tests use a deterministic mock repo / Supabase / bot and an explicit
pre-B3 *oracle* (the unconditional-re-resolution behavior) to PIN that the
normal and legacy cases are byte-identical (same ordered repo.* calls + same
messages), and that ONLY the divergent-cid race path changed (refuse + zero
write). They are strictly additive; no existing test is modified.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for mod in ["telebot", "supabase", "dotenv", "engine_core",
            "adaptive_risk_engine", "telegram_formatters",
            "supabase_repository", "ibkr_sync_runner"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import importlib.util


class _IdentityDecoratorBot:
    """telebot.TeleBot's @bot.callback_query_handler registers AND returns
    the original function unchanged. Replicate that so the isolated
    telegram_callbacks module exposes a callable handle_queries without
    touching the shared bot_core / telegram_callbacks modules other tests
    rely on."""

    def callback_query_handler(self, *a, **k):
        return lambda fn: fn

    def __getattr__(self, name):
        return MagicMock()


def _load_isolated_callbacks():
    _bc = py_types.ModuleType("bot_core")
    _bc.bot        = _IdentityDecoratorBot()
    _bc.supabase   = MagicMock()
    _bc.user_state = {}
    _bc.RTL        = "‏"
    _bc.TOKEN      = ""
    _bc.ADMIN_ID   = ""

    saved_bc = sys.modules.get("bot_core")
    saved_tc = sys.modules.get("telegram_callbacks")
    sys.modules["bot_core"] = _bc
    try:
        path = os.path.join(os.path.dirname(__file__), "..",
                            "telegram_callbacks.py")
        spec = importlib.util.spec_from_file_location("_isolated_tc_b3", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved_bc is not None:
            sys.modules["bot_core"] = saved_bc
        else:
            sys.modules.pop("bot_core", None)
        if saved_tc is not None:
            sys.modules["telegram_callbacks"] = saved_tc


tc = _load_isolated_callbacks()

SYM = "CAT"
ENTRY, STOP, QTY = 910.0, 895.0, 3
# Confirm callback_data shape produced by telegram_bot.py:
#   addon_confirm|YES|SYMBOL|entry|stop|qty
CONFIRM_DATA = f"addon_confirm|YES|{SYM}|{ENTRY}|{STOP}|{QTY}"


def _make_repo(resolved_cid, *, latest_tid="T-LATEST"):
    """Deterministic mock repo. get_open_campaign_for_symbol -> resolved_cid;
    get_latest_buy_trade_id -> latest_tid; the two writers are spies."""
    r = MagicMock(name="repo")
    r.get_open_campaign_for_symbol.return_value = resolved_cid
    r.get_latest_buy_trade_id.return_value = latest_tid
    r.update_management_notes.return_value = None
    r.update_addon_record.return_value = None
    return r


def _make_supabase():
    """Mock Supabase used only by the migration-pending is_addon count
    select. Returns .data == [] so addon_sequence resolves to 1."""
    sb = MagicMock(name="supabase")
    (sb.table.return_value
       .select.return_value
       .eq.return_value
       .eq.return_value
       .execute.return_value).data = []
    return sb


# Frozen timestamp so the time-derived note/message bytes are identical
# between the real B3 run and the pre-B3 oracle (no minute-boundary flake).
_FROZEN = "2026-05-17 12:00"


class _FrozenDatetime:
    @staticmethod
    def now():
        class _N:
            @staticmethod
            def strftime(fmt):
                assert fmt == "%Y-%m-%d %H:%M"
                return _FROZEN
        return _N()


def _run_confirm(pending, resolved_cid):
    """Invoke the REAL (B3) telegram_callbacks.handle_queries for the
    addon_confirm|YES branch with a deterministic mock repo/supabase/bot
    and the given pending state. Returns (fake_bot, repo, state)."""
    fake_bot = MagicMock(name="bot")
    repo = _make_repo(resolved_cid)
    sb = _make_supabase()

    # The addon_confirm|YES branch does NOT lazily import telegram_bot, but
    # other branches of handle_queries do; provide a stub for the duration of
    # the call and restore the prior sys.modules entry so Test 4 (which needs
    # the REAL telegram_bot) is unaffected.
    saved_tb = sys.modules.get("telegram_bot")
    sys.modules["telegram_bot"] = py_types.ModuleType("telegram_bot")

    call = MagicMock()
    call.data = CONFIRM_DATA
    call.id = "cb-b3"
    call.message.chat.id = 7777
    call.message.message_id = 4242

    state = {7777: dict(pending)}
    try:
        with patch.object(tc, 'bot', fake_bot), \
             patch.object(tc, 'repo', repo), \
             patch.object(tc, 'supabase', sb), \
             patch.object(tc, 'datetime', _FrozenDatetime), \
             patch.object(tc, 'user_state', state):
            tc.handle_queries(call)
    finally:
        if saved_tb is not None:
            sys.modules["telegram_bot"] = saved_tb
        else:
            sys.modules.pop("telegram_bot", None)
    return fake_bot, repo, state


# ── Pre-B3 ORACLE ────────────────────────────────────────────────────────────
# A faithful byte-for-byte reproduction of the PRE-B3 addon_confirm|YES body:
# an UNCONDITIONAL `cid = repo.get_open_campaign_for_symbol(supabase, sym)`
# then the original write block, the original "no open campaign" warning,
# the pending-clear, and the original success message — using the SAME RTL
# constant and the SAME frozen timestamp as the real run. Normal+legacy B3
# runs are asserted byte-identical to this (ordered repo.* call shape +
# exact outbound message strings/kwargs).

def _oracle_pre_b3(pending, resolved_cid):
    fake_bot = MagicMock(name="oracle_bot")
    repo = _make_repo(resolved_cid)
    sb = _make_supabase()
    chat_id = 7777
    sym = SYM
    RTL = tc.RTL  # same constant the real module uses

    entry = pending.get("entry", 0)
    stop = pending.get("stop", 0)
    qty = pending.get("qty", 0)
    ts_str = _FROZEN
    note = f"Add-On אושר: כניסה ${entry} | סטופ ${stop} | כמות {qty} ({ts_str})"

    fake_bot.answer_callback_query("cb-b3")
    try:
        fake_bot.edit_message_reply_markup(chat_id, 4242, reply_markup=None)
    except Exception:
        pass
    try:
        cid = repo.get_open_campaign_for_symbol(sb, sym)  # UNCONDITIONAL (pre-B3)
        if cid:
            repo.update_management_notes(sb, cid, note)
            try:
                _tid = repo.get_latest_buy_trade_id(sb, sym, cid)
                if _tid:
                    _seq_res = (sb.table("trades").select("trade_id")
                                .eq("campaign_id", cid)
                                .eq("is_addon", True).execute())
                    _seq = len(_seq_res.data or []) + 1
                    repo.update_addon_record(sb, _tid, cid, _seq)
            except Exception:
                pass
        else:
            fake_bot.send_message(
                chat_id,
                f"{RTL}⚠️ *Add-On נרשם אך לא נמצא קמפיין פתוח ל-{sym}*\nוודא ידנית ב-management\\_notes.",
                parse_mode="Markdown",
            )
    except Exception as exc:  # pragma: no cover - not exercised here
        fake_bot.send_message(
            chat_id,
            f"{RTL}⚠️ *שגיאה בשמירת Add-On ל-Supabase*\n`{type(exc).__name__}: {exc}`\nוודא ידנית.",
            parse_mode="Markdown",
        )
    # pending-clear + success message (pre-B3 unconditional tail)
    fake_bot.send_message(
        chat_id,
        f"{RTL}✅ *Add-On אושר — {sym}*\n{RTL}כניסה: `${entry}` | סטופ: `${stop}` | כמות: `{qty}`\n{RTL}נרשם ב-management\\_notes.",
        parse_mode="Markdown",
    )
    return fake_bot, repo


def _msg_shape(fake_bot):
    """Ordered (chat_id, text, sorted-kwargs-keys, parse_mode) of every
    bot.send_message — the user-facing byte-identity key."""
    shape = []
    for c in fake_bot.send_message.call_args_list:
        shape.append((c.args[0], c.args[1] if len(c.args) > 1 else None,
                      tuple(sorted(c.kwargs)), c.kwargs.get("parse_mode")))
    return shape


def _repo_call_shape(repo):
    """Ordered (method, positional-args-after-supabase) tuple of the three
    Add-On writers/resolvers — the byte-identity oracle key. The supabase
    handle is excluded (it is an injected stub, identical by construction)."""
    shape = []
    for name in ("get_open_campaign_for_symbol", "update_management_notes",
                 "get_latest_buy_trade_id", "update_addon_record"):
        m = getattr(repo, name)
        for c in m.call_args_list:
            # args[0] is the supabase handle (stub) — drop it from the shape.
            shape.append((name, tuple(c.args[1:]), tuple(sorted(c.kwargs))))
    return shape


# ── Test 1 — HARDENED race REFUSED ───────────────────────────────────────────

class TestRaceRefusedHardened:
    def test_divergent_cid_refuses_zero_write_clears_pending(self):
        pending = {"action": "addon_pending", "symbol": SYM,
                   "entry": ENTRY, "stop": STOP, "qty": QTY,
                   "add_type": "tactical", "campaign_id": "CID-PLANNED-X"}
        # The open campaign changed since plan: re-resolution returns Y != X.
        fake_bot, repo, state = _run_confirm(pending, resolved_cid="CID-NEW-Y")

        # ZERO Supabase write of any kind.
        repo.update_management_notes.assert_not_called()
        repo.update_addon_record.assert_not_called()
        # The race was *detected* via a re-resolution call (the only repo call).
        repo.get_open_campaign_for_symbol.assert_called_once()
        repo.get_latest_buy_trade_id.assert_not_called()

        # Pending cleared exactly like the existing cancel/decline path.
        assert 7777 not in state

        # An explicit Hebrew refusal message was sent, telling the user the
        # position changed and to re-run /addon.
        msgs = [c.args[1] for c in fake_bot.send_message.call_args_list]
        assert any(("השתנתה" in m and "addon" in m) for m in msgs), msgs
        # NOT the pre-B3 success message.
        assert not any("Add-On אושר" in m for m in msgs), msgs


# ── Test 2 — NORMAL case byte-identical to pre-B3 oracle ─────────────────────

class TestNormalByteIdentical:
    def test_resolved_equals_planned_is_byte_identical(self):
        pending = {"action": "addon_pending", "symbol": SYM,
                   "entry": ENTRY, "stop": STOP, "qty": QTY,
                   "add_type": "tactical", "campaign_id": "CID-X"}
        # No race: re-resolution returns the SAME campaign as planned.
        fake_bot, repo, state = _run_confirm(pending, resolved_cid="CID-X")
        o_bot, o_repo = _oracle_pre_b3(pending, resolved_cid="CID-X")

        # BYTE-IDENTITY PROOF (normal case): the exact ordered repo.* call
        # shape (incl. the precise note string, frozen ts) AND the exact
        # outbound message shape are equal to the pre-B3 oracle.
        assert _repo_call_shape(repo) == _repo_call_shape(o_repo)
        assert _msg_shape(fake_bot) == _msg_shape(o_bot)
        # Writes target CID-X (planned == resolved campaign).
        repo.update_management_notes.assert_called_once()
        assert repo.update_management_notes.call_args.args[1] == "CID-X"
        repo.update_addon_record.assert_called_once()
        assert repo.update_addon_record.call_args.args[2] == "CID-X"
        # No refusal / no "no campaign" warning; single success message.
        msgs = [c.args[1] for c in fake_bot.send_message.call_args_list]
        assert msgs == [c.args[1]
                        for c in o_bot.send_message.call_args_list]
        assert any("Add-On אושר" in m for m in msgs), msgs
        assert not any("השתנתה" in m for m in msgs), msgs
        # Pending cleared like pre-B3.
        assert 7777 not in state


# ── Test 3 — LEGACY (no stored cid) byte-identical fallback ──────────────────

class TestLegacyFallbackByteIdentical:
    def test_no_campaign_id_key_falls_back_unchanged(self):
        # Older in-flight pending: NO campaign_id key at all.
        pending = {"action": "addon_pending", "symbol": SYM,
                   "entry": ENTRY, "stop": STOP, "qty": QTY,
                   "add_type": "tactical"}
        fake_bot, repo, state = _run_confirm(pending, resolved_cid="CID-LEG")
        o_bot, o_repo = _oracle_pre_b3(pending, resolved_cid="CID-LEG")

        # BYTE-IDENTITY PROOF (legacy path): falls back to
        # get_open_campaign_for_symbol and is byte-identical to pre-B3 —
        # identical repo.* call shape AND identical message shape.
        assert _repo_call_shape(repo) == _repo_call_shape(o_repo)
        assert _msg_shape(fake_bot) == _msg_shape(o_bot)
        repo.update_management_notes.assert_called_once()
        assert repo.update_management_notes.call_args.args[1] == "CID-LEG"
        repo.update_addon_record.assert_called_once()
        assert repo.update_addon_record.call_args.args[2] == "CID-LEG"

        msgs = [c.args[1] for c in fake_bot.send_message.call_args_list]
        assert msgs == [c.args[1]
                        for c in o_bot.send_message.call_args_list]
        assert any("Add-On אושר" in m for m in msgs), msgs
        assert not any("השתנתה" in m for m in msgs), msgs  # NO refusal
        assert 7777 not in state

    def test_explicit_none_campaign_id_also_falls_back(self):
        # Stored campaign_id present but None (planned row had no resolvable
        # cid) — must behave like legacy fallback, never refuse.
        pending = {"action": "addon_pending", "symbol": SYM,
                   "entry": ENTRY, "stop": STOP, "qty": QTY,
                   "add_type": "tactical", "campaign_id": None}
        fake_bot, repo, state = _run_confirm(pending, resolved_cid="CID-Z")
        o_bot, o_repo = _oracle_pre_b3(pending, resolved_cid="CID-Z")

        assert _repo_call_shape(repo) == _repo_call_shape(o_repo)
        assert _msg_shape(fake_bot) == _msg_shape(o_bot)
        repo.update_management_notes.assert_called_once()
        assert repo.update_management_notes.call_args.args[1] == "CID-Z"
        msgs = [c.args[1] for c in fake_bot.send_message.call_args_list]
        assert msgs == [c.args[1]
                        for c in o_bot.send_message.call_args_list]
        assert any("Add-On אושר" in m for m in msgs), msgs
        assert not any("השתנתה" in m for m in msgs), msgs


# ── Test 4 — /addon persists the planned campaign_id ─────────────────────────
# Exercise the real telegram_bot._handle_addon_command pending-state set with
# a deterministic open-positions DataFrame, asserting the persisted
# campaign_id is the campaign_id of the exact resolved row used for
# entry/stop/qty (sym_rows.iloc[0]).

class TestPendingStoresPlannedCid:
    def test_addon_pending_state_carries_resolved_row_campaign_id(self):
        import pandas as pd

        captured = {}

        # Open positions for SYM: the resolved row (iloc[0]) has campaign_id
        # CAMP-PLANNED — that exact id must land in the pending state.
        open_df = pd.DataFrame([{
            "campaign_id": "CAMP-PLANNED", "symbol": SYM, "quantity": 10,
            "base_qty": 10, "base_price": 900.0, "stop_loss": 880.0,
            "initial_stop": 870.0, "price": 905.0, "realized_pnl": 0.0,
            "setup_type": "EP", "entry_date": "2026-05-01",
            "management_state": "full_position",
        }])

        fake_ec = MagicMock(name="ec")
        fake_ec.get_open_positions_campaign.return_value = {
            "ok": True, "error": None, "data": open_df}
        fake_ec.get_live_price.return_value = 905.0
        fake_ec.get_cached_history.return_value = None
        fake_ec.evaluate_position_engine.return_value = {"ok": False}

        fake_addon = MagicMock(name="addon_eng")
        fake_addon.ADDON_TACTICAL = "tactical"
        fake_addon.ADDON_CAMPAIGN = "campaign"
        fake_addon.ADDON_REBUILD = "rebuild"
        fake_addon.compute_campaign_lot_state.return_value = {
            "total_r": 0, "open_r": 0, "locked_profit_usd": 0,
            "open_risk_usd": 0, "original_risk_usd": 28}
        fake_addon.compute_addon_plan.return_value = {"proposed_qty": QTY}

        fake_tf = MagicMock(name="tf")
        fake_tf.fmt_addon_card.return_value = "CARD"

        fake_supabase = MagicMock(name="supabase")
        fake_supabase.table.return_value.select.return_value.execute.\
            return_value.data = open_df.to_dict("records")

        fake_bot = MagicMock(name="bot")

        class _US(dict):
            def __setitem__(self, k, v):
                captured.clear()
                captured.update(v)
                super().__setitem__(k, v)

        # Ensure the REAL telegram_bot module (not a sibling test's stub).
        _stale = sys.modules.get("telegram_bot")
        if _stale is None or not hasattr(_stale, "_handle_addon_command"):
            sys.modules.pop("telegram_bot", None)
        import telegram_bot as tb
        assert hasattr(tb, "_handle_addon_command"), "real telegram_bot expected"
        with patch.object(tb, 'ec', fake_ec), \
             patch.object(tb, 'addon_eng', fake_addon), \
             patch.object(tb, 'tf', fake_tf), \
             patch.object(tb, 'supabase', fake_supabase), \
             patch.object(tb, 'bot', fake_bot), \
             patch.object(tb, 'user_state', _US()):
            tb._handle_addon_command(7777, f"/addon {SYM} {ENTRY} {STOP} {QTY}")

        assert captured.get("action") == "addon_pending"
        assert captured.get("symbol") == SYM
        # The load-bearing assertion: the planned campaign_id is the
        # campaign_id of the resolved open-position row (same row used for
        # entry/stop/qty).
        assert captured.get("campaign_id") == "CAMP-PLANNED"
