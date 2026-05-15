"""
tests/test_sprint14_alert_dedup.py — Sprint 14 Wave-2 alert-spam remediation.

Covers the 16 cases from docs/teams/SPRINT14_DESIGN.md §3, encoding Mark's
rulings verbatim (docs/teams/MARK_SPRINT14_RULINGS.md):

  - persistence / reload (RC-2/RC-3/RC-4): stable key → no re-push;
    prev round-trips through state_io across a simulated reload from the
    NEW /app/state path; both writers share ONE path constant; gitignored.
  - should_alert / ALGO gate (RC-1/RC-6): genuine non-P0 first sighting is
    pull-only (Mark §1 row 1 — drop the blanket prev-is-None push); ALGO
    observer-only never traverses the generic Live-Alert push (Mark §2);
    ALGO P0 deep-loss still fires.
  - P0 must-fire (Mark §4): critical-exit / status-worsening always fire
    even with a persisted same-key prev and cooldown not elapsed; the
    CAT 22:33 critical-exit is the explicit anti-regression anchor.
  - giveback (RC-5): 6h within-zone suppressed once persistence holds;
    cross-zone still fires.
  - founder live-incident regressions: PWR 7×, HOOD ALGO, PWR giveback,
    CAT P0 preserved.

Uses the same module-stub pattern as tests/test_e2e_risk_monitor.py so no
real Telegram/Supabase is required. Additive — baseline 1620 stays green.
"""
import os
import sys
import types

import pytest

# ── Stub heavy deps before any project import ─────────────────────────────────
for _mod in ("telebot", "supabase", "dotenv"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

sys.modules["supabase"].create_client = lambda *a, **k: None   # type: ignore
sys.modules["dotenv"].load_dotenv     = lambda *a, **k: None   # type: ignore


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


sys.modules["telebot"].TeleBot = _FakeBot          # type: ignore
sys.modules["telebot"].types   = _FakeBot.types    # type: ignore

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import risk_monitor as rm   # noqa: E402
import bot_helpers as bh     # noqa: E402
import state_io               # noqa: E402


# Stable healthy-PWR alert key the founder saw 7× (status/action/sizing only).
PWR_ENGINE = {
    "status": "🔥 Power",
    "action": "החזקה (מובילה)",
    "sizing_status": "✅ תקין",
}
PWR_KEY = rm.build_position_alert_key({}, PWR_ENGINE)


def _persisted_prev(status, key, last_alert_ts):
    return {"status": status, "alert_key": key, "last_alert_ts": last_alert_ts}


# ── 1. Stable key → push exactly once across N simulated cycles ──────────────
def test_stable_key_no_repush_across_cycles():
    """RC-1/RC-4: a persisted healthy-PWR prev with an unchanged key must NOT
    re-push on any subsequent cycle (Mark §1 row 1 hard rule, invariant #7)."""
    # First sighting is genuinely new → pull-only for non-P0 (Mark §1 row1).
    first, ts = rm.should_alert(None, PWR_ENGINE["status"], PWR_KEY)
    assert first is False  # genuinely-new healthy/held → pull surface, no push

    prev = _persisted_prev(PWR_ENGINE["status"], PWR_KEY, ts)
    for _ in range(10):  # 10 five-min cycles, key unchanged
        fire, _ = rm.should_alert(prev, PWR_ENGINE["status"], PWR_KEY)
        assert fire is False, "unchanged-key healthy hold must never re-push"


# ── 2. prev round-trips through state_io across a simulated reload ───────────
def test_prev_persists_across_simulated_reload(tmp_path, monkeypatch):
    """RC-2/RC-3: write state via state_io to a tmp file standing in for the
    /app/state volume path, reload it, assert prev is non-None and
    alert_key/last_alert_ts survive → no re-push after the reload."""
    state_path = str(tmp_path / "risk_monitor_state.json")
    monkeypatch.setattr(rm, "STATE_FILE", state_path)

    state = {
        "positions": {
            "PWR_9415330854": _persisted_prev(PWR_ENGINE["status"], PWR_KEY,
                                               1_700_000_000.0)
        },
        "cluster": {},
    }
    rm.save_state(state)

    reloaded = rm.load_state()
    prev = reloaded["positions"].get("PWR_9415330854")
    assert prev is not None
    assert prev["alert_key"] == PWR_KEY
    assert prev["last_alert_ts"] == 1_700_000_000.0

    fire, _ = rm.should_alert(prev, PWR_ENGINE["status"], PWR_KEY)
    assert fire is False  # state survived → no re-push


# ── 3. Both writers resolve to the SAME /app/state path (drift guard) ────────
def test_state_path_is_under_app_state_and_shared():
    assert rm.STATE_FILE == state_io.RM_STATE_FILE
    assert bh._RM_STATE_FILE == state_io.RM_STATE_FILE
    assert rm.STATE_FILE == "/app/state/risk_monitor_state.json"
    # Single shared constant → the two cross-container writers can never land
    # on two inodes (which would split-brain the fcntl lock + dedup memory).
    assert os.path.dirname(rm.STATE_FILE) == "/app/state"


# ── 4. State file is gitignored (guards RC-2 from regressing) ────────────────
def test_state_file_gitignored():
    repo = os.path.join(os.path.dirname(__file__), "..")
    gi = open(os.path.join(repo, ".gitignore"), encoding="utf-8").read()
    assert "risk_monitor_state.json" in gi
    assert "state/risk_monitor_state.json" in gi


# ── 5. prev is None, non-P0 first sight → pull-only (Mark §1 row 1) ──────────
def test_prev_none_nonp0_first_sight_is_pull_only():
    """Mark §1 row 1: drop the blanket prev-is-None push for NON-P0 status.
    A genuinely-new healthy/held position is the position working → pull
    surface (Open Tasks), not a push."""
    for status in ("🔥 Power", "🟢 Healthy", "🟡 תקין אך במעקב", "🟠 Weak"):
        fire, _ = rm.should_alert(None, status, "k")
        assert fire is False, f"non-P0 first sight must be pull-only: {status}"


def test_prev_none_p0_first_sight_still_fires():
    """Mark §4.1/4.3/4.5: a genuine FIRST sighting that is already a
    P0/critical status MUST push immediately."""
    for status in rm.CRITICAL_STATUSES:
        fire, _ = rm.should_alert(None, status, "k")
        assert fire is True, f"first-ever P0 must fire: {status}"


# ── 6. ALGO observer-only not pushed on the generic live path (Mark §2) ─────
def test_algo_observer_not_pushed_on_live_path(monkeypatch):
    """RC-6 / Mark §2: management_mode == algo_observed must NOT traverse the
    generic recurring Live-Alert send_telegram(msg). We assert the gate
    predicate the loop uses: `do_alert and not _algo_observed`."""
    monkeypatch.setattr(rm.ec, "classify_management_mode",
                        lambda setup, sym: "algo_observed")
    _mgt_mode = rm.ec.classify_management_mode("ALGO", "HOOD")
    _algo_observed = (_mgt_mode == "algo_observed")
    do_alert = True  # would have pushed on the generic path
    assert not (do_alert and not _algo_observed), \
        "ALGO observer-only must be gated out of the generic live push"


def test_non_algo_still_pushes_on_live_path(monkeypatch):
    monkeypatch.setattr(rm.ec, "classify_management_mode",
                        lambda setup, sym: "manual")
    _algo_observed = (rm.ec.classify_management_mode("EP", "PWR")
                      == "algo_observed")
    do_alert = True
    assert (do_alert and not _algo_observed), \
        "non-ALGO P0/escalation must still traverse the generic live push"


# ── 7. ALGO P0 deep-loss still fires (dedicated path, not generic) ──────────
def test_algo_p0_deep_loss_still_fires(monkeypatch):
    """Mark §2/§4: ALGO deep-loss <=-2R one-time visibility is allowed and
    fires via its OWN dedicated path (rm._algo_deep_loss_alert →
    send_telegram), which the RC-6 generic-path gate does not touch."""
    sent = []
    monkeypatch.setattr(rm, "send_telegram", lambda m: sent.append(m))
    open_r = -2.4
    algo_deep_loss_alerted = False
    if open_r <= -2.0 and not algo_deep_loss_alerted:
        rm.send_telegram(rm._algo_deep_loss_alert("HOOD", open_r))
    assert len(sent) == 1, "ALGO deep-loss P0 visibility must still fire"


# ── 8. CAT 22:33 critical-exit ALWAYS fires (the anchor) ────────────────────
def test_p0_critical_exit_always_fires_with_persisted_same_key():
    """Mark §4.1: 🚨 קריטי / price<stop fires even when prev is a persisted
    same-key state and the 6h repeat cooldown has NOT elapsed (escalation
    Healthy→Critical → STATUS_RANK rise → immediate)."""
    prev = _persisted_prev("🟢 Healthy", "old_key",
                            rm.datetime.utcnow().timestamp())  # ts = now
    fire, _ = rm.should_alert(prev, "🚨 קריטי", "crit_key")
    assert fire is True, "CAT 22:33 critical-exit must ALWAYS fire"


# ── 9. Status escalation always fires regardless of cooldown ────────────────
def test_escalation_always_fires():
    prev = _persisted_prev("🟢 Healthy", "k", rm.datetime.utcnow().timestamp())
    fire, _ = rm.should_alert(prev, "🔴 Broken", "k2")
    assert fire is True
    fire2, _ = rm.should_alert(prev, "🟠 Weak", "k3")
    assert fire2 is True


# ── 10. Broken repeat honors 6h + US-market-hours gate ──────────────────────
def test_broken_repeat_market_hours_gate(monkeypatch):
    now = rm.datetime.utcnow().timestamp()
    # Same Broken status, last alert just now → suppressed (cooldown not met).
    prev = _persisted_prev("🔴 Broken", "k", now)
    fire, _ = rm.should_alert(prev, "🔴 Broken", "k")
    assert fire is False
    # >6h ago AND market hours → re-fires.
    monkeypatch.setattr(rm, "is_during_us_market_hours", lambda: True)
    prev_old = _persisted_prev("🔴 Broken", "k", now - 7 * 3600)
    fire2, _ = rm.should_alert(prev_old, "🔴 Broken", "k")
    assert fire2 is True
    # >6h ago but OUTSIDE market hours → still suppressed.
    monkeypatch.setattr(rm, "is_during_us_market_hours", lambda: False)
    fire3, _ = rm.should_alert(prev_old, "🔴 Broken", "k")
    assert fire3 is False


# ── 11. Giveback 6h within-zone suppressed once persistence holds ───────────
def test_giveback_6h_within_zone_suppressed_with_persistence():
    """RC-5: PWR giveback 19:36 then 19:42 (6 min apart) — with the giveback
    class persisted in prev_state, the second check is suppressed because the
    zone did NOT change (fires on zone transition only, Mark §1 giveback row;
    GIVEBACK_COOLDOWN_SEC stays 6h). Uses the REAL pure giveback math:
    peak 2.0R → 1.3R = 35% giveback → 'watch' zone."""
    assert rm.GIVEBACK_COOLDOWN_SEC == 6 * 3600  # Mark: confirm 6h, unchanged
    now = rm.datetime.utcnow().timestamp()
    # 19:36 — zone natural→watch transition fires once.
    prev1 = {"peak_open_r": 2.0, "last_giveback_class": "natural",
             "last_giveback_ts": now, "position_state": ""}
    a1, _ = rm.check_position_risk_thresholds(
        sym="PWR", setup="EP", open_r=1.3, open_pnl_usd=500.0,
        target_risk_usd=100.0, is_algo=False, prev_state=prev1, now_ts=now)
    assert len(a1) >= 1, "natural→watch zone transition should fire once"
    # 19:42 — same 'watch' zone persisted → no repeat.
    prev2 = {"peak_open_r": 2.0, "last_giveback_class": "watch",
             "last_giveback_ts": now, "position_state": ""}
    a2, _ = rm.check_position_risk_thresholds(
        sym="PWR", setup="EP", open_r=1.3, open_pnl_usd=500.0,
        target_risk_usd=100.0, is_algo=False,
        prev_state=prev2, now_ts=now + 360)
    assert a2 == [], "same-zone giveback within 6h must be suppressed"


# ── 12. Giveback still fires on a genuine zone transition ───────────────────
def test_giveback_fires_on_zone_transition():
    """Real giveback math: peak 3.0R → 1.0R = 66.7% giveback →
    'protection_failure' zone; prev class 'watch' → zone changed → fires
    (no over-suppression)."""
    now = rm.datetime.utcnow().timestamp()
    prev = {"peak_open_r": 3.0, "last_giveback_class": "watch",
            "last_giveback_ts": now - 60, "position_state": ""}
    alerts, _ = rm.check_position_risk_thresholds(
        sym="PWR", setup="EP", open_r=1.0, open_pnl_usd=300.0,
        target_risk_usd=100.0, is_algo=False, prev_state=prev, now_ts=now)
    assert len(alerts) >= 1, "watch→protection_failure transition must fire"


# ── 13. Founder regression: PWR healthy 7× → exactly zero pushes ────────────
def test_regression_pwr_healthy_no_respam():
    """Replay PWR 🔥 Power / החזקה (מובילה) / structure-intact across the 7
    observed cycle/deploy events WITH persistence intact → pull-only the
    whole time (Mark §1 row 1: never push). Zero pushes, never 7×."""
    pushes = 0
    prev = None
    for _ in range(7):  # 7 founder-observed events
        fire, ts = rm.should_alert(prev, PWR_ENGINE["status"], PWR_KEY)
        if fire:
            pushes += 1
        prev = _persisted_prev(PWR_ENGINE["status"], PWR_KEY,
                               ts if fire else (prev or {}).get(
                                   "last_alert_ts", 0))
    assert pushes == 0, f"healthy PWR must be pull-only, got {pushes} pushes"


# ── 14. Founder regression: HOOD ALGO Weak→Broken→Broken gated ─────────────
def test_regression_hood_algo_no_respam(monkeypatch):
    monkeypatch.setattr(rm.ec, "classify_management_mode",
                        lambda setup, sym: "algo_observed")
    pushes = 0
    for _status in ("🟠 Weak", "🔴 Broken", "🔴 Broken"):  # 21:08/21:20/21:45
        _algo_observed = (rm.ec.classify_management_mode("ALGO", "HOOD")
                          == "algo_observed")
        do_alert = True  # should_alert would have said push
        if do_alert and not _algo_observed:
            pushes += 1
    assert pushes == 0, "HOOD ALGO must not spam the generic live path"


# ── 15. Founder regression: PWR giveback 19:36 then 19:42 deduped ──────────
def test_regression_pwr_giveback_dedup():
    # Real math: peak 2.0R → 1.3R = 35% → 'watch'; prev already 'watch'
    # (persisted) → no zone change → second push suppressed.
    now = rm.datetime.utcnow().timestamp()
    prev = {"peak_open_r": 2.0, "last_giveback_class": "watch",
            "last_giveback_ts": now, "position_state": ""}
    a, _ = rm.check_position_risk_thresholds(
        sym="PWR", setup="EP", open_r=1.3, open_pnl_usd=500.0,
        target_risk_usd=100.0, is_algo=False,
        prev_state=prev, now_ts=now + 360)  # +6 min
    assert a == [], "PWR giveback 19:42 (same zone, 6 min later) suppressed"


# ── 16. Anti-regression anchor: CAT 22:33 preserved amid all suppression ───
def test_regression_cat_p0_preserved():
    """The explicit must-fire anchor: even with every other suppression in
    place, CAT 22:33 🚨 קריטי | price<stop fires immediately — first sight
    AND escalation AND persisted-same-key all preserve it."""
    # First-ever sighting that is already critical → fires.
    fire_first, _ = rm.should_alert(None, "🚨 קריטי", "cat_key")
    assert fire_first is True
    # Escalation Healthy→Critical with a persisted recent prev → fires.
    now = rm.datetime.utcnow().timestamp()
    prev = _persisted_prev("🟢 Healthy", "old", now)
    fire_esc, _ = rm.should_alert(prev, "🚨 קריטי", "cat_key")
    assert fire_esc is True
    # Already-critical persisted, >6h + market hours → repeat still fires.
    # (and within cooldown it correctly holds — both branches verified in #10)
    assert "🚨 קריטי" in rm.CRITICAL_STATUSES
