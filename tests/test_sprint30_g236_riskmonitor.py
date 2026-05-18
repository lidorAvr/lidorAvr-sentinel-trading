"""
Sprint-30 G2 + G3 + G6 — risk_monitor alert/digest acceptance proof.

Scope (risk_monitor.py ONLY — Sprint-30 SCOPE G2/G3/G6):

  G2 — state-flap re-spam fix. `should_alert` previously fast-pathed ANY rank
       increase straight to a fresh banner; a sub-threshold status oscillation
       (🔥 Power[2] ↔ 🟡 תקין אך במעקב[3] on a <1% price wiggle —
       CAT_9409547470 fired 5× in ~65 lines, 15 byte-identical blocks in the
       real export) flipped DOWN then back UP and the "back UP" bypassed the
       cooldown. Fix: the cooldown/dedup now HOLDS across a status flip that
       is NOT a *material* escalation; a genuine NEW worsening (and every P0)
       still fires immediately. Behaviour-narrowing only (strictly fewer
       duplicate alerts), no new alert type.

  G3 — the existing "🧭 מה עכשיו?" companion voice now also rides the
       high-frequency LIVE alert surface (it was 0× in the 995-msg live
       stream). Same voice the digest/weekly path speaks, derived ONLY from
       THIS alert's already-computed engine `action`. Never a false
       all-clear, never contradicts the body, no new message type.

  G6 — silence ≠ all-clear. When the daily digest renders with NOTHING
       actionable it now emits an explicit Hebrew
       "מערכת פעילה — אין פעולה נדרשת כרגע" line on the EXISTING digest
       message (not a brand-new periodic message).

These tests exercise PURE functions (`should_alert`, `_whatnow_live_companion`,
`_daily_digest_text`) so no real Telegram/Supabase client is touched.
"""
import os
import sys
import types

import pytest

# ── Stub heavy deps before any project import (same pattern as
#    test_e2e_risk_monitor.py / conftest) ──────────────────────────────────────
for _mod in ("telebot", "supabase", "dotenv"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

if not getattr(sys.modules["supabase"], "create_client", None):
    sys.modules["supabase"].create_client = lambda *a, **k: None  # type: ignore
if not getattr(sys.modules["dotenv"], "load_dotenv", None):
    sys.modules["dotenv"].load_dotenv = lambda *a, **k: None       # type: ignore


class _FakeBot:
    def __init__(self, *a, **k):
        pass

    class types:
        class InlineKeyboardMarkup:
            def __init__(self, **k):
                self.buttons = []

            def add(self, *b):
                self.buttons.extend(b)

        class InlineKeyboardButton:
            def __init__(self, text="", callback_data=""):
                pass


if not getattr(sys.modules["telebot"], "TeleBot", None):
    sys.modules["telebot"].TeleBot = _FakeBot          # type: ignore
if not getattr(sys.modules["telebot"], "types", None):
    sys.modules["telebot"].types = _FakeBot.types      # type: ignore

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://ci-test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "ci-test-key")
os.environ.setdefault("DEV_PIN", "0000")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import risk_monitor as rm  # noqa: E402
import engine_core as ec   # noqa: E402

pytestmark = pytest.mark.unit

_YELLOW = "🟡 תקין אך במעקב"   # STATUS_RANK 3
_POWER = "🔥 Power"             # STATUS_RANK 2
_WEAK = "🟠 Weak"               # STATUS_RANK 4
_BROKEN = "🔴 Broken"           # STATUS_RANK 5  (CRITICAL_STATUSES, P0)
_HEALTHY = "🟢 Healthy"         # STATUS_RANK 1


def _key(status):
    """A representative alert_key that changes with status (mirrors the real
    build_position_alert_key — status is one of its components)."""
    return f'{{"status":"{status}"}}'


def _step(prev, status, at_ts):
    """Drive ONE risk-monitor cycle exactly as `main()` does: call
    should_alert (the LOCKED 2-tuple contract) with a pinned 'now', then
    compute the next persisted recent-alert-peak via the dedicated helper.
    Returns (do_alert, new_alert_ts, next_state_dict)."""
    do, ts = rm.should_alert(prev, status, _key(status))
    peak = rm._next_alert_peak_rank(prev, status, do, at_ts)
    nxt = {
        "status": status,
        "alert_key": _key(status),
        "last_alert_ts": ts,
    }
    if peak is not None:
        nxt["recent_alert_peak_rank"] = peak
    return do, ts, nxt


def _at(prev, status, at_ts):
    """Run _step with `now` pinned to at_ts (should_alert + the peak helper
    both read datetime.utcnow()/timestamps)."""
    import datetime as _dt

    class _FixedDT(_dt.datetime):
        @classmethod
        def utcnow(cls):
            return _dt.datetime.utcfromtimestamp(at_ts)

    orig = rm.datetime
    rm.datetime = _FixedDT
    try:
        return _step(prev, status, at_ts)
    finally:
        rm.datetime = orig


# ════════════════════════════════════════════════════════════════════════════
# G2 — state-flap re-spam fix
# ════════════════════════════════════════════════════════════════════════════

class TestG2StateFlapSuppressed:
    """The CAT_9409547470 signature: 🟡[3] alerted, flips DOWN to 🔥[2], then
    back UP to 🟡[3] within the 45-min cooldown. The 'back UP' must NOT
    re-fire (it previously bypassed the cooldown via the escalation
    fast-path)."""

    def _first_alert_state(self, status, now):
        """The persisted state after a first 🟡 alert fired (rank tracked)."""
        return {
            "status": status,
            "alert_key": _key(status),
            "last_alert_ts": now,
            "recent_alert_peak_rank": rm.STATUS_RANK[status],
        }

    def test_flap_back_up_within_cooldown_is_suppressed(self):
        now = 1_000_000.0
        # State after a 🟡 (rank 3) alert just fired.
        st_yellow = self._first_alert_state(_YELLOW, now)

        # +5min: 🟡 → 🔥 (rank 3 → 2, a de-escalation). Already cooldown-gated
        # by the pre-existing key-change branch — no fire.
        do1, ts1, st_power = _at(st_yellow, _POWER, now + 5 * 60)
        assert do1 is False

        # +10min: 🔥 → 🟡 (rank 2 → 3, an ESCALATION). This is the bug path:
        # pre-fix it hit the escalation fast-path and re-fired, bypassing the
        # cooldown. Post-fix: it is NOT a material escalation (we are flapping
        # back to a rank we were just at, inside the active cooldown) → HELD.
        do2, ts2, st2 = _at(st_power, _YELLOW, now + 10 * 60)
        assert do2 is False, "G2: noise-flap re-escalation must be suppressed"
        # The in-window alerted peak stays sticky at 3 so subsequent flaps
        # are also recognised as noise.
        assert st2["recent_alert_peak_rank"] == 3

    def test_flap_still_suppressed_on_third_oscillation(self):
        now = 2_000_000.0
        st = self._first_alert_state(_YELLOW, now)
        # 🟡→🔥 (+5m), 🔥→🟡 (+10m), 🟡→🔥 (+15m), 🔥→🟡 (+20m): every flip
        # is inside the 45-min cooldown ⇒ none fire.
        for status, mins in [(_POWER, 5), (_YELLOW, 10),
                             (_POWER, 15), (_YELLOW, 20)]:
            do, ts, st = _at(st, status, now + mins * 60)
            assert do is False, f"flap to {status} at +{mins}m must be held"


class TestG2GenuineEscalationStillFires:
    """Escalation semantics PRESERVED — a real worsening still alerts."""

    def test_new_higher_tier_within_cooldown_still_fires(self):
        now = 3_000_000.0
        # 🟡 (rank 3) alerted, peak=3. Now genuinely worsens to 🟠 Weak
        # (rank 4) — a NEW high we have NOT alerted on in this window.
        st = {
            "status": _YELLOW, "alert_key": _key(_YELLOW),
            "last_alert_ts": now, "recent_alert_peak_rank": 3,
        }
        do, ts, nxt = _at(st, _WEAK, now + 8 * 60)
        assert do is True, "G2: genuine NEW worsening must still fire"
        assert ts == now + 8 * 60
        assert nxt["recent_alert_peak_rank"] == 4  # peak advances to new high

    def test_p0_critical_escalation_never_suppressed(self):
        now = 4_000_000.0
        # Even inside the cooldown, a worsening into a P0/CRITICAL status
        # (🔴 Broken) must ALWAYS fire (Sprint-14 Mark §4 invariant).
        st = {
            "status": _YELLOW, "alert_key": _key(_YELLOW),
            "last_alert_ts": now, "recent_alert_peak_rank": 3,
        }
        do, ts, nxt = _at(st, _BROKEN, now + 2 * 60)
        assert do is True, "G2: P0/critical worsening must never be suppressed"

    def test_first_sight_critical_still_pushes(self):
        # prev is None + already-critical status ⇒ MUST push (unchanged
        # Sprint-14 — and the 2-tuple return contract is byte-identical).
        res = rm.should_alert(None, _BROKEN, _key(_BROKEN))
        assert len(res) == 2  # LOCKED 2-tuple — Sprint-14 dedup tests rely on it
        do, ts = res
        assert do is True
        # The persisted peak is computed by the dedicated helper, not returned.
        assert rm._next_alert_peak_rank(None, _BROKEN, do, ts) == \
            rm.STATUS_RANK[_BROKEN]

    def test_first_sight_non_critical_does_not_push(self):
        # prev is None + healthy/working ⇒ no push (unchanged Sprint-14).
        do, ts = rm.should_alert(None, _HEALTHY, _key(_HEALTHY))
        assert do is False
        assert rm._next_alert_peak_rank(None, _HEALTHY, do, ts) is None

    def test_escalation_after_cooldown_elapsed_still_fires(self):
        now = 5_000_000.0
        st = {
            "status": _POWER, "alert_key": _key(_POWER),
            "last_alert_ts": now, "recent_alert_peak_rank": 3,
        }
        # 🔥 → 🟡 escalation but the 45-min cooldown has ELAPSED — a re-cross
        # after cooldown is a fresh event by the existing contract.
        do, ts, nxt = _at(st, _YELLOW, now + 46 * 60)
        assert do is True
        assert ts == now + 46 * 60

    def test_behaviour_narrowing_only_no_new_alert_type(self):
        # The fix never INTRODUCES an alert; it only ever returns the same
        # do_alert=True cases as before or fewer. Sanity: a clean genuine
        # escalation with NO prior peak still fires (legacy/no-track path).
        now = 6_000_000.0
        st = {
            "status": _HEALTHY, "alert_key": _key(_HEALTHY),
            "last_alert_ts": now - 10 * 60,
        }  # no recent_alert_peak_rank tracked
        do, ts, nxt = _at(st, _WEAK, now)
        assert do is True, "no-track first escalation must never be lost"

    def test_should_alert_return_contract_unchanged_2_tuple(self):
        # Mark 6.1 — the LOCKED Sprint-14 dedup tests unpack `should_alert`
        # as `(fire, ts)`. The G2 fix must NOT change that contract.
        st = {"status": _YELLOW, "alert_key": _key(_YELLOW),
              "last_alert_ts": 0}
        assert len(rm.should_alert(st, _POWER, _key(_POWER))) == 2
        assert len(rm.should_alert(None, _HEALTHY, _key(_HEALTHY))) == 2


# ════════════════════════════════════════════════════════════════════════════
# G3 — companion "🧭 מה עכשיו?" line on the LIVE surface
# ════════════════════════════════════════════════════════════════════════════

class TestG3CompanionLineOnLiveSurface:
    def test_live_companion_uses_existing_whatnow_voice(self):
        line = rm._whatnow_live_companion("🟡 תקין אך במעקב",
                                          "לא להוסיף. שקול צמצום")
        # Same companion voice token as the digest / weekly path.
        assert line.startswith("‏🧭 *מה עכשיו?*")
        # It restates THIS alert's already-computed action verbatim.
        assert "לא להוסיף. שקול צמצום" in line
        # Points back at the body it sits under — never contradicts it.
        assert "ראה הפירוט למעלה" in line

    def test_live_companion_never_false_all_clear(self):
        # Even with an EMPTY action it never emits an all-clear / "הכול תקין"
        # / green-light wording — it points at the body for a decision.
        line = rm._whatnow_live_companion("🔴 Broken", "")
        assert "הכול תקין" not in line
        assert "אין פעולה" not in line  # never a digest-style all-clear here
        assert "לבחון את הפוזיציה" in line
        assert line.startswith("‏🧭 *מה עכשיו?*")

    def test_live_companion_echoes_body_action_no_contradiction(self):
        # The line carries the EXACT body `action` string, so it can never
        # disagree with the "פעולה:" line two rows above it.
        for act in ("בצע יציאה", "הגן על רווח", "החזקה (מובילה)"):
            line = rm._whatnow_live_companion("🔴 Broken", act)
            assert act in line

    def test_live_companion_is_single_line(self):
        line = rm._whatnow_live_companion("🟠 Weak", "צמצם חשיפה")
        assert "\n" not in line

    def test_live_alert_path_appends_companion(self):
        # Source-level proof the LIVE alert builder appends the companion via
        # the shared helper (presentation-additive on the EXISTING message,
        # not a new message type).
        import inspect
        src = inspect.getsource(rm.main)
        assert "_whatnow_live_companion(" in src
        # It is appended to the SAME `msg` that send_telegram sends — i.e.
        # the existing Sentinel Live Alert surface, no new send call/type.
        assert 'msg += "\\n" + _whatnow_live_companion(' in src

    def test_shared_urgent_states_constant_is_byte_identical_set(self):
        # G3 de-duped the digest's inline urgent tuple onto the shared
        # constant the live derivation reuses — provably the SAME set/order.
        assert rm._WHATNOW_URGENT_STATES == (
            ec.POSITION_STATE_BROKEN,
            ec.POSITION_STATE_RUNNER,
            ec.POSITION_STATE_PROFIT_PROTECTION,
        )


# ════════════════════════════════════════════════════════════════════════════
# G6 — silence ≠ all-clear on the daily digest
# ════════════════════════════════════════════════════════════════════════════

class TestG6DigestAliveLine:
    def test_empty_actionable_digest_emits_explicit_alive_line(self):
        rows = [
            {"sym": "AAPL", "state": ec.POSITION_STATE_WORKING,
             "open_r": 0.4, "is_algo": False},
            {"sym": "MSFT", "state": ec.POSITION_STATE_PROVING,
             "open_r": 0.1, "is_algo": False},
        ]
        txt = rm._daily_digest_text(rows, "18/05/2026")
        # The explicit Hebrew alive line is present on the EXISTING digest.
        assert "מערכת פעילה — אין פעולה נדרשת כרגע" in txt
        # Honest: it does NOT claim "all good", only that nothing needs
        # action right now (the dashboard footer caveat still follows).
        assert "הכול תקין" not in txt
        assert "_(ללא פעולה נוספת? הדאשבורד עדכני)_" in txt

    def test_urgent_digest_does_not_show_alive_line(self):
        # When there IS something actionable the alive line must NOT appear
        # (the urgent footer leads instead) — additive, not a replacement.
        rows = [
            {"sym": "NVDA", "state": ec.POSITION_STATE_BROKEN,
             "open_r": -1.4, "is_algo": False},
        ]
        txt = rm._daily_digest_text(rows, "18/05/2026")
        assert "מערכת פעילה — אין פעולה נדרשת כרגע" not in txt
        assert "⚡ *נדרשת החלטה:* NVDA" in txt

    def test_digest_urgent_body_byte_identical_post_g6(self):
        # G6 only ADDS an else-branch line; the urgent path's body + footer
        # must remain byte-identical (same as the Sprint-27 W3 pin).
        RTL_M = "‏"
        rows = [
            {"sym": "NVDA", "state": ec.POSITION_STATE_BROKEN,
             "open_r": -1.4, "is_algo": False},
            {"sym": "HOOD", "state": ec.POSITION_STATE_WORKING,
             "open_r": 0.6, "is_algo": True},
        ]
        txt = rm._daily_digest_text(rows, "17/05/2026")
        lines = txt.split("\n")
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

    def test_companion_line_still_present_on_empty_digest(self):
        # G3/W3 companion line still leads even on the calm digest (the
        # "no urgent action" voice), and the G6 alive line follows in body.
        rows = [
            {"sym": "AAPL", "state": ec.POSITION_STATE_WORKING,
             "open_r": 0.4, "is_algo": False},
        ]
        txt = rm._daily_digest_text(rows, "18/05/2026")
        line2 = txt.split("\n")[1]
        assert "מה עכשיו?" in line2
        assert "אין פעולה דחופה" in line2
        assert "מערכת פעילה — אין פעולה נדרשת כרגע" in txt
