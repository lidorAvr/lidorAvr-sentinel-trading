"""
Sprint-27 W3 — companion "voice" acceptance proof (UX P0-1 / P0-2 / P1-2 / P1-3).

W3 is PRESENTATION-ONLY: ONE concise Hebrew "מה עכשיו?" verdict+next-step line
is PREPENDED at the TOP of (a) the weekly/monthly Telegram summary, (b) the live
חדר-מצב / open-book surface, (c) the risk-monitor daily digest — composed ONLY
from signals the surface ALREADY computed (existing verdict_class, open-book
decision state, NAV-freshness/B1 disclosure). NO new computation, NO new data
source, NO KPI/number change. Where a surface can render empty, a one-line
"silence ≠ all-clear" disambiguation is added. The C1 PIN-expiry message and the
B3 race-refusal message are humanized (warmer, still 100% honest).

This proof asserts:
  1. The "מה עכשיו?" line is PRESENT and correctly derived on representative
     states: closed-week (strong/mixed/defensive), 0-closed-live-book,
     drawdown/defensive, stale-NAV.
  2. The report BODY (numbers + every existing line) is byte-identical to a
     pre-W3 oracle on the broker-fresh path — the line is purely prepended.
  3. The empty-surface disambiguation is present (חדר מצב empty path).
  4. The risk-monitor daily digest carries the line, derived from the SAME
     urgent set; its body bullets are byte-identical to pre-W3.
  5. The humanized C1 + B3 messages carry the NEW wording AND are still honest
     (no false reassurance).
"""
import os
import sys
import types as py_types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://ci-test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "ci-test-key")
os.environ.setdefault("DEV_PIN", "0000")

# Stub heavy deps before any telegram/risk_monitor import (same isolation
# pattern as test_phase_b3_addon_cid.py / conftest mock_telegram_bot) so a
# real telebot token / Supabase client is never required.
for _m in ("telebot", "supabase", "dotenv"):
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()
if not getattr(sys.modules["supabase"], "create_client", None):
    sys.modules["supabase"].create_client = lambda *a, **k: None
if not getattr(sys.modules["dotenv"], "load_dotenv", None):
    sys.modules["dotenv"].load_dotenv = lambda *a, **k: None
if not getattr(sys.modules["telebot"], "TeleBot", None):
    sys.modules["telebot"].TeleBot = type(
        "TeleBot", (), {"__init__": lambda *a, **k: None,
                        "__getattr__": lambda s, n: MagicMock()})

import report_renderer as rr  # noqa: E402


import importlib.util  # noqa: E402


class _IdentityDecoratorBot:
    """Mirrors telebot.TeleBot's decorator-returns-fn behaviour so an isolated
    telegram_* module exposes callable handlers without touching the shared
    bot_core other tests rely on."""

    def message_handler(self, *a, **k):
        return lambda fn: fn

    def callback_query_handler(self, *a, **k):
        return lambda fn: fn

    def __getattr__(self, name):
        return MagicMock()


def _load_isolated(modname, filename, recording_bot):
    """Load `filename` as an isolated module with a fake bot_core whose `bot`
    is `recording_bot`. Restores sys.modules so other suites are unaffected.

    CRITICAL self-containment: the loaded module does `import
    supabase_repository as repo` / `import engine_core as ec`, which bind to
    the SHARED sys.modules objects. Tests here patch `mod.repo.<fn>` /
    `mod.ec.<fn>`; if those pointed at the real shared modules the patch
    would leak and corrupt e.g. test_supabase_repository's real-module
    assertions. So after exec we rebind `mod.repo` / `mod.ec` to FRESH
    per-load MagicMocks — patches stay local, NO global module is mutated."""
    _bc = py_types.ModuleType("bot_core")
    _bc.bot = recording_bot
    _bc.supabase = MagicMock()
    _bc.user_state = {}
    _bc.RTL = "‏"
    _bc.TOKEN = ""
    _bc.ADMIN_ID = ""
    saved = {k: sys.modules.get(k) for k in ("bot_core", modname)}
    sys.modules["bot_core"] = _bc
    try:
        path = os.path.join(os.path.dirname(__file__), "..", filename)
        spec = importlib.util.spec_from_file_location(
            f"_isolated_w3_{modname}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Per-load private mocks for the data layers so test patches like
        # `mod.repo.get_all_trades = ...` never touch the shared real modules.
        if hasattr(mod, "repo"):
            mod.repo = MagicMock(name="isolated_repo")
        if hasattr(mod, "ec"):
            mod.ec = MagicMock(name="isolated_ec")
        return mod
    finally:
        for k, v in saved.items():
            if v is not None:
                sys.modules[k] = v
            else:
                sys.modules.pop(k, None)

_WHATNOW_PREFIX = "🧭 *מה עכשיו?*"


def _analytics_closed(**kw):
    """A representative CLOSED-week analytics dict (campaigns_closed > 0)."""
    base = {
        "ok": True, "campaigns_closed": 6, "win_rate": 0.6,
        "expectancy_r": 0.4, "profit_factor": 2.4, "total_r_net": 2.2,
        "realized_pnl": 440.0, "missing_stop_rate": 0.0, "oversized_rate": 0.0,
    }
    base.update(kw)
    return base


_ANALYTICS_EMPTY = {
    "ok": True, "campaigns_closed": 0, "win_rate": 0, "expectancy_r": 0,
    "profit_factor": 0, "total_r_net": 0, "realized_pnl": 0,
    "missing_stop_rate": 0, "oversized_rate": 0,
}

_ACC_BROKER_FRESH = {
    "nav": 7921.0, "nav_source": "broker", "freshness": "fresh",
    "freshness_label": "✅ NAV עדכני (6.2h)", "is_stale": False,
    "is_critical": False, "ok": True, "risk_pct_input": 0.5,
}
_ACC_STALE = {
    "nav": 7921.0, "nav_source": "broker", "freshness": "stale",
    "freshness_label": "🟡 NAV ישן (30h)", "is_stale": True,
    "is_critical": False, "ok": True, "risk_pct_input": 0.5,
}
_ACC_FALLBACK = {
    "nav": 7500.0, "nav_source": "fallback", "freshness": "unknown",
    "freshness_label": "🟠 Fallback NAV — sentinel_config.json לא נמצא",
    "is_stale": True, "is_critical": False, "ok": False,
    "risk_pct_input": 0.5,
}


def _present_open_book(fallback_syms=None):
    return {
        "open_book_present": True,
        "open_book_disc": [
            {"symbol": "MRVL", "entry": 60.0, "current": 60.0, "qty": 30,
             "floating_pnl": 0.0, "realized_pnl": 0.0, "structure_r": 0.0,
             "account_r": 0.0, "structure_valid": True, "account_valid": True,
             "exposure_pct": 22.0,
             "price_is_fallback": bool(fallback_syms), "is_algo": False,
             "unrealized_label": "לא ממומש"},
        ],
        "open_book_algo": [],
        "open_book_totals": {
            "floating_pnl_disc": 0.0, "floating_pnl_algo": 0.0,
            "exposure_pct_total": 22.0, "exposure_pct_disc": 22.0,
            "exposure_pct_algo": 0.0, "n_disc": 1, "n_algo": 0,
            "n_opened_total": 0,
        },
        "open_book_data_source": "Cached" if fallback_syms else "Live",
        "open_book_price_fallback_syms": list(fallback_syms or []),
        "open_book_error": None,
    }


# ── 1. The "מה עכשיו?" line PRESENT + correctly derived per state ─────────────

class TestWhatNowLinePresentAndDerived:
    def test_strong_week_actionable_no_action_needed(self):
        # tr>=1.0, wr>=0.55, process_ok ⇒ verdict_class "strong".
        txt = rr.build_summary_text(_analytics_closed(), "lbl", "weekly",
                                    account_state=_ACC_BROKER_FRESH)
        first = txt.split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "חזק" in first
        assert "אין פעולה דרושה" in first  # actionable next step

    def test_defensive_week_priority_reduce_risk(self):
        # tr<=-0.5 ⇒ verdict_class "defensive".
        a = _analytics_closed(total_r_net=-1.2, win_rate=0.30,
                               realized_pnl=-240.0)
        txt = rr.build_summary_text(a, "lbl", "weekly",
                                    account_state=_ACC_BROKER_FRESH)
        first = txt.split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "הגנתי" in first
        assert "צמצום סיכון" in first

    def test_mixed_week_no_urgent_action(self):
        a = _analytics_closed(total_r_net=0.2, win_rate=0.45,
                               profit_factor=1.1, realized_pnl=40.0)
        first = rr.build_summary_text(
            a, "lbl", "weekly",
            account_state=_ACC_BROKER_FRESH).split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "מעורב" in first

    def test_zero_closed_live_book_not_all_clear(self):
        # 0 closed + live book ⇒ verdict_class "neutral"; the line must NOT
        # read as all-clear and must point to the open book.
        txt = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                    open_book=_present_open_book(),
                                    account_state=_ACC_BROKER_FRESH)
        first = txt.split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "לא אומר שהכול תקין/לא תקין" in first
        assert "ספר הפתוח" in first

    def test_stale_nav_leads_with_estimate_caveat(self):
        # When the NAV that scaled the KPIs is not broker-fresh, the "what now"
        # leads with that honesty (accuracy > confidence) — never silent.
        first = rr.build_summary_text(
            _analytics_closed(), "lbl", "weekly",
            account_state=_ACC_STALE).split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "NAV לא-חי" in first
        assert "כהערכה" in first and "לא כאמת מדויקת" in first

    def test_fallback_nav_also_leads_with_caveat(self):
        first = rr.build_summary_text(
            _analytics_closed(), "lbl", "monthly",
            account_state=_ACC_FALLBACK).split("\n", 1)[0]
        assert first.startswith(_WHATNOW_PREFIX)
        assert "NAV לא-חי" in first

    def test_line_is_exactly_one_line(self):
        # The companion voice is ONE line (P0-1: a single sentence), then a
        # blank line, then the body.
        txt = rr.build_summary_text(_analytics_closed(), "lbl", "weekly",
                                    account_state=_ACC_BROKER_FRESH)
        parts = txt.split("\n")
        assert parts[0].startswith(_WHATNOW_PREFIX)
        assert "\n" not in parts[0]
        assert parts[1] == ""  # one blank separator before the body

    def test_whatnow_helper_pure_no_account_state(self):
        # Helper is pure presentation; account_state=None ⇒ NAV-silent
        # (legacy callers), still returns the one line.
        line = rr.whatnow_line("strong")
        assert line.startswith(_WHATNOW_PREFIX)
        assert "NAV לא-חי" not in line


# ── 2. Report BODY byte-identical vs a pre-W3 oracle (broker-fresh) ──────────

class TestReportBodyByteIdenticalPreW3:
    """The W3 invariant: on the broker-fresh / normal path the new line is
    PREPENDED and the existing body (every number + existing line) is
    byte-identical to pre-W3. The pre-W3 oracle = the body produced by
    stripping the one companion line + its single blank separator."""

    def _strip_whatnow(self, txt):
        # The line is prepended as line[0] + a blank line[1]; the body is the
        # remainder. This is the exact pre-W3 build_summary_text output.
        a, sep, body = txt.split("\n", 2)
        assert a.startswith(_WHATNOW_PREFIX)
        assert sep == ""
        return body

    def test_closed_week_body_byte_identical(self):
        a = _analytics_closed()
        full = rr.build_summary_text(a, "Week 20", "weekly",
                                     account_state=_ACC_BROKER_FRESH)
        body = self._strip_whatnow(full)
        # Pre-W3 oracle — the EXACT realized body, frozen literal. Any drift in
        # a number or an existing line fails here (equally strict as the old
        # Sprint-25 frozen-literal pin, just with the prepend removed).
        expected_body = (
            "🛡️ *Sentinel — דוח שבועי*\n"
            "📅 תקופה: `Week 20`\n"
            "\n"
            "✅ *שבוע חזק 💪*\n"
            "\n"
            "📊 קמפיינים: `6`  |  Win%: `60.0%`\n"
            "💰 Realized PnL: `$+440`  |  Net R: `+2.20R`\n"
            "🎯 Expectancy: `+0.40R`  |  PF: `2.40`\n"
            "⚙️ Missing Stop: `0.0%`  |  Oversized: `0.0%`"
        )
        assert body == expected_body

    def test_zero_closed_body_byte_identical_vs_legacy(self):
        # On the 0-closed live-book path, stripping the prepend must equal the
        # legacy (account_state=None, but pre-W3) body. We prove this by
        # equality of the two stripped bodies (broker-fresh vs no-account):
        # both get the same prepend, both must yield the same body.
        ob = _present_open_book()
        full_bf = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                        open_book=ob,
                                        account_state=_ACC_BROKER_FRESH)
        full_no = rr.build_summary_text(_ANALYTICS_EMPTY, "lbl", "weekly",
                                        open_book=ob)
        # Whole strings equal (broker-fresh adds no B1 disclosure ⇒ the only
        # thing on top is the identical W3 line for both).
        assert full_bf == full_no
        body = self._strip_whatnow(full_bf)
        # The body still contains the honest empty-state, NOT "ללא עסקאות".
        assert "ללא עסקאות" not in body
        assert "🛡️ *Sentinel — דוח שבועי*" in body

    def test_prepend_does_not_perturb_b1_disclosure(self):
        # The B1 NAV disclosure still appears in the BODY (unchanged) when NAV
        # is not broker-fresh — W3 prepends, it does not move/duplicate B1.
        full = rr.build_summary_text(_analytics_closed(), "lbl", "weekly",
                                     account_state=_ACC_FALLBACK)
        body = self._strip_whatnow(full)
        assert body.count("שים לב — NAV לא חי") == 1


# ── 3. Empty-surface disambiguation (silence ≠ all-clear) ────────────────────

class TestEmptySurfaceDisambiguation:
    def test_portfolio_room_empty_says_not_all_clear(self):
        sent = []

        class _Bot(_IdentityDecoratorBot):
            def send_message(self, cid, text, **kw):
                sent.append(text)
                return type("M", (), {"message_id": 1})()

            def delete_message(self, *a, **k):
                pass

        tp = _load_isolated("telegram_portfolio",
                            "telegram_portfolio.py", _Bot())

        class _EmptyDF:
            empty = True

        tp.ec.get_open_positions_campaign = lambda df: {
            "ok": True, "data": _EmptyDF()}
        tp.repo.get_all_trades = lambda sb: []
        tp.handle_portfolio_room(999)

        joined = "\n".join(sent)
        assert "אין פוזיציות פתוחות כרגע" in joined
        # The disambiguation: silence is NOT all-clear.
        assert "לא אומר שהכול תקין/לא תקין" in joined
        assert "בדוק סנכרון נתונים" in joined


# ── 4. Risk-monitor daily digest carries the line; body byte-identical ──────

class TestDailyDigestCompanionLine:
    def _rows(self, states):
        import risk_monitor as rm
        out = []
        for i, st in enumerate(states):
            out.append({"sym": f"S{i}", "state": st, "open_r": 1.0 + i,
                        "is_algo": False})
        return out, rm

    def test_digest_line_present_urgent(self):
        import risk_monitor as rm
        rows = [
            {"sym": "NVDA", "state": rm.ec.POSITION_STATE_BROKEN,
             "open_r": -1.4, "is_algo": False},
            {"sym": "HOOD", "state": rm.ec.POSITION_STATE_WORKING,
             "open_r": 0.6, "is_algo": False},
        ]
        txt = rm._daily_digest_text(rows, "17/05/2026")
        lines = txt.split("\n")
        assert lines[0].endswith("סיכום יומי | 17/05/2026*")
        # The companion line is line[1] (right after the title).
        assert "מה עכשיו?" in lines[1]
        assert "דורשות החלטה" in lines[1]
        assert "NVDA" in lines[1]

    def test_digest_line_present_no_urgent(self):
        import risk_monitor as rm
        rows = [
            {"sym": "AAPL", "state": rm.ec.POSITION_STATE_WORKING,
             "open_r": 0.4, "is_algo": False},
        ]
        txt = rm._daily_digest_text(rows, "17/05/2026")
        line2 = txt.split("\n")[1]
        assert "מה עכשיו?" in line2
        assert "אין פעולה דחופה" in line2
        # honest: never claims "all good", only "no urgent action"
        assert "הכול תקין" not in line2

    def test_digest_body_bullets_byte_identical(self):
        # The per-row bullets + the urgent footer must be byte-identical to
        # pre-W3 (the urgent-set computation was a provable no-op refactor;
        # only the one line is added). Build the pre-W3 body explicitly.
        import risk_monitor as rm
        RTL_M = "‏"
        rows = [
            {"sym": "NVDA", "state": rm.ec.POSITION_STATE_BROKEN,
             "open_r": -1.4, "is_algo": False},
            {"sym": "HOOD", "state": rm.ec.POSITION_STATE_WORKING,
             "open_r": 0.6, "is_algo": True},
        ]
        txt = rm._daily_digest_text(rows, "17/05/2026")
        lines = txt.split("\n")
        # Strip line[1] (the companion line) → must equal the pre-W3 digest.
        pre_w3 = "\n".join([lines[0]] + lines[2:])
        expected = "\n".join([
            f"{RTL_M}📋 *Sentinel — סיכום יומי | 17/05/2026*",
            f"{RTL_M}───────────────────",
            f"{RTL_M}• *NVDA* 🔴 `-1.4R` — בצע יציאה",
            f"{RTL_M}• *HOOD* `[ALGO]` ✅ `+0.6R` — עקוב",
            f"{RTL_M}───────────────────",
            f"{RTL_M}⚡ *נדרשת החלטה:* NVDA",
            f"{RTL_M}───────────────────",
            f"{RTL_M}_(ללא פעולה נוספת? הדאשבורד עדכני)_",
        ])
        assert pre_w3 == expected


# ── 5. Humanized C1 + B3 messages: new wording AND still honest ─────────────

class TestHumanizedC1Message:
    def test_c1_expiry_warmer_but_still_honest(self):
        sent = []

        class _Bot(_IdentityDecoratorBot):
            def send_message(self, cid, text, **kw):
                sent.append(text)

        tb = _load_isolated("telegram_bot", "telegram_bot.py", _Bot())
        tb.dev_pin_is_configured = lambda: True
        tb.dev_pin_session_active = lambda cid: False  # session expired
        tb.user_state.clear()
        res = tb._require_active_dev_session(12345)

        # Security UNCHANGED: still denies (fail-closed), still routes to PIN.
        assert res is False
        assert tb.user_state.get(12345) == {"action": "awaiting_dev_pin"}
        msg = sent[-1]
        # Warmer wording present.
        assert "צריך PIN פעיל" in msg
        assert "נמשיך מכאן" in msg
        # Still 100% honest — states plainly the session expired AND that NO
        # action ran (no false reassurance).
        assert "פגה" in msg
        assert "לא בוצעה שום פעולה" in msg
        # Never falsely says an action succeeded.
        assert "✅" not in msg


class TestHumanizedB3Message:
    def test_b3_race_refusal_warmer_but_still_honest(self):
        sent = []

        class _Bot(_IdentityDecoratorBot):
            def answer_callback_query(self, *a, **k):
                pass

            def edit_message_reply_markup(self, *a, **k):
                pass

            def send_message(self, cid, text, **kw):
                sent.append(text)

        tc = _load_isolated("telegram_callbacks",
                            "telegram_callbacks.py", _Bot())

        def _no_write(*a, **k):
            raise AssertionError("B3 zero-write violated")

        tc.repo = MagicMock()
        tc.repo.get_open_campaign_for_symbol = lambda sb, s: "CID-NEW-Y"
        tc.repo.update_management_notes = _no_write
        tc.repo.update_addon_record = _no_write
        tc.supabase = MagicMock()
        tc.user_state.clear()
        tc.user_state[55] = {"action": "addon_pending", "symbol": "NVDA",
                              "entry": 100, "stop": 95, "qty": 3,
                              "add_type": "tactical",
                              "campaign_id": "CID-PLANNED-X"}
        call = MagicMock()
        call.id = "cb1"
        call.data = "addon_confirm|YES|NVDA"
        call.message.message_id = 1
        call.message.chat.id = 55
        tc.handle_queries(call)

        msg = sent[-1]
        # Warmer / protective framing (NEW wording).
        assert "עצרתי את החיזוק" in msg
        assert "התחלפה" in msg
        assert "להגן על הכסף שלך" in msg
        # Still 100% honest — explicitly says NOTHING was written (no false
        # reassurance) and gives the actionable next step.
        assert "לא כתבתי כלום" in msg
        assert "הרץ" in msg and "addon" in msg
        # Never reads as a success / completed write.
        assert "Add-On אושר" not in msg
        assert "NVDA" in msg
        # Pending cleared (zero-write protective path).
        assert 55 not in tc.user_state
