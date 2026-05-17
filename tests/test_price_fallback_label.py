"""
Tests for the Sprint-12 price-fallback honest label (Mark §3 /
SPRINT12_DESIGN §3).

Wave-2 plan cases:
* K. the label appears ONLY when ec.get_live_price() returned None and the
  caller fell back; on the live path it is ABSENT; the displayed numbers are
  unchanged between the two runs (label-only, no math).
* L. fmt_position_card without the new kwarg is BYTE-IDENTICAL to today
  (the defaulted kwarg keeps every existing caller/test green).

Covers F1 (telegram_stop_promote._compute_open_r 3rd return flag +
build_stop_promote_keyboard) and F5 (telegram_formatters.fmt_position_card
defaulted kwarg) directly + the canonical single-source label string.
"""
import sys, os, types as py_types
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# sys.modules is process-global; this file sorts early alphabetically. Stub
# ONLY the unimportable-in-sandbox deps; never overwrite a real module that a
# later real test imports (engine_core / adaptive_risk_engine /
# ibkr_sync_runner import cleanly — stubbing them poisoned siblings).
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

import telegram_formatters as tf  # noqa: E402
import telegram_stop_promote as sp  # noqa: E402

_LABEL = "‏⚠️ (מחיר לא חי — לפי מחיר כניסה, לא בזמן אמת)"


class TestCanonicalLabelString:
    def test_label_is_mark_verbatim_single_source(self):
        # VERBATIM from MARK_SPRINT12_RULINGS.md §3 — engineering invents no
        # wording; one canonical source reused everywhere.
        assert tf.PRICE_FALLBACK_LABEL == _LABEL


class TestFmtPositionCardDefaultByteIdentical:
    def _card(self, **kw):
        d = dict(
            i=1, sym="AAPL", setup="VCP", days_held=10,
            curr=155.0, entry=150.0, open_pnl=50.0,
            pos_value=1550.0, weight_pct=5.0,
            total_pos_profit=50.0, total_campaign_r=0.5,
            open_r_val=0.5, status="🟢 Healthy", action_short="Hold",
        )
        d.update(kw)
        return tf.fmt_position_card(**d)

    # L. default kwarg → byte-identical to pre-Sprint-12 (no label).
    def test_default_has_no_label(self):
        card = self._card()
        assert _LABEL not in card

    def test_explicit_false_has_no_label(self):
        assert _LABEL not in self._card(price_is_fallback=False)

    # K. label present ONLY when the caller flags fallback.
    def test_fallback_true_appends_label_after_price(self):
        card = self._card(price_is_fallback=True)
        assert _LABEL in card
        # label-only: every other number unchanged vs the no-label card.
        plain = self._card(price_is_fallback=False)
        assert card.replace(f" {_LABEL}", "") == plain

    def test_label_appears_exactly_once(self):
        assert self._card(price_is_fallback=True).count(_LABEL) == 1


class TestComputeOpenRFallbackFlag:
    def _row(self, **ov):
        base = {"symbol": "CAT", "price": 100.0, "quantity": 10,
                "initial_stop": 90.0, "base_price": 100.0, "base_qty": 10,
                "setup_type": "VCP", "campaign_id": "CAT_1"}
        base.update(ov)
        return base

    def test_live_price_no_fallback_flag(self):
        with patch.object(sp.ec, "get_live_price", return_value=120.0):
            open_r, curr, fb = sp._compute_open_r(self._row(), 50.0)
        assert fb is False
        assert curr == 120.0  # live price used

    def test_none_price_sets_fallback_flag_and_uses_entry(self):
        with patch.object(sp.ec, "get_live_price", return_value=None):
            open_r, curr, fb = sp._compute_open_r(self._row(), 50.0)
        assert fb is True
        assert curr == 100.0  # entry substituted (unchanged behaviour)

    def test_open_r_value_unchanged_between_live_equalprice_runs(self):
        # If the live price equals entry, the OPEN-R number is identical
        # whether it came live or via fallback (label-only; no math change).
        row = self._row()
        with patch.object(sp.ec, "get_live_price", return_value=100.0):
            r_live, c_live, fb_live = sp._compute_open_r(row, 50.0)
        with patch.object(sp.ec, "get_live_price", return_value=None):
            r_fb, c_fb, fb_fb = sp._compute_open_r(row, 50.0)
        assert r_live == r_fb
        assert c_live == c_fb
        assert fb_live is False and fb_fb is True


class TestStopPromoteKeyboardLabel:
    def _row(self, **ov):
        base = {"symbol": "CAT", "price": 100.0, "quantity": 10,
                "stop_loss": 95.0, "initial_stop": 90.0,
                "base_price": 100.0, "base_qty": 10,
                "setup_type": "VCP", "campaign_id": "CAT_1"}
        base.update(ov)
        return base

    def _kb(self, positions):
        class _ST:
            InlineKeyboardMarkup = _FIMarkup
            InlineKeyboardButton = _FIButton
        with patch.object(sp, "types", _ST), \
             patch.object(sp, "get_account_settings",
                          lambda: {"risk_pct_input": 0.5}), \
             patch.object(sp, "get_nav_and_risk", lambda s=None: (1e4, 50.0, None)):
            return sp.build_stop_promote_keyboard(positions)

    # K. live → no canonical label row anywhere.
    def test_live_price_no_fallback_row(self):
        with patch.object(sp.ec, "get_live_price", return_value=120.0):
            kb = self._kb([self._row()])
        assert all(_LABEL not in b.text for b in kb.buttons)
        assert all(b.callback_data != "promote_price_fallback_note"
                   for b in kb.buttons)

    # K. None → exactly one canonical-label info row + the ⚠️ button marker.
    def test_none_price_adds_fallback_note_row(self):
        with patch.object(sp.ec, "get_live_price", return_value=None):
            kb = self._kb([self._row()])
        note_rows = [b for b in kb.buttons
                     if b.callback_data == "promote_price_fallback_note"]
        assert len(note_rows) == 1
        assert note_rows[0].text == _LABEL
        pick = [b for b in kb.buttons
                if b.callback_data == "promote_pick|0"][0]
        assert "‏⚠️" in pick.text  # per-row honest marker
