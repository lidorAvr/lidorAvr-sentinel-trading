import os, json, time, signal, sys, telebot
import pandas as pd
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
import engine_core as ec
import adaptive_risk_engine as are
import audit_logger
import account_state
import state_io
# Phase Arch-F1 (Sprint-25 F1): single shared sentinel_config.json reader.
# risk_monitor previously kept a byte-identical local get_account_settings
# copy with a bare `except:`. De-duplicated onto bot_helpers' reader
# (`except Exception:`); corrupt-config behavior is byte-identical (a
# JSONDecodeError is an Exception, caught by both) — pure parity-preserving
# polish per Decision A = Honest. See docs/teams/PHASE_ARCHF1_IMPL.md.
from bot_helpers import get_account_settings

_HEARTBEAT_DIR = "/app/state"

def _touch_heartbeat(name: str) -> None:
    """Write current timestamp to /app/state/{name}_last_cycle so healthchecks can verify liveness."""
    try:
        os.makedirs(_HEARTBEAT_DIR, exist_ok=True)
        path = os.path.join(_HEARTBEAT_DIR, f"{name}_last_cycle")
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
bot = telebot.TeleBot(TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
RTL = "\u200F"
# Sprint 14 RC-2/RC-3: anti-spam dedup memory MUST survive `git pull` deploys
# AND container `--force-recreate`. The bare relative name resolved under the
# `.:/app` git bind mount (git-tracked \u2192 reverted by every deploy \u2192 `prev`
# was perpetually None \u2192 should_alert :151 re-pushed every position).
# `/app/state` is the EXISTING `sentinel_state` named volume (already mounted
# on risk-monitor at docker-compose.yml:108, same dir the heartbeat uses) \u2014
# it survives both. No compose change. Single shared constant via state_io so
# the risk-monitor writer and the bot_helpers RMW writer can never drift apart
# onto two different inodes (which would split-brain the fcntl lock + state).
STATE_FILE = state_io.RM_STATE_FILE

STATUS_RANK = {
    "⚪ אין דאטה": 0, "🟢 Healthy": 1, "🔥 Power": 2, "⚠️ Climactic": 2,
    "🟡 Yellow Flag": 3, "🟡 תקין אך במעקב": 3, "🟠 Weak": 4, "🔴 Broken": 5, "🚨 קריטי": 6, "🚨 חריגת סיכון אלגו": 6
}

# Sprint 14 (Mark §4): the P0 / critical-exit status set that MUST fire
# immediately and is NEVER suppressed by any anti-spam change — incl. on a
# genuine first sighting (prev is None). Lifted verbatim from the existing
# critical/broken repeat list (was inline at should_alert) so the first-sight
# gate and the repeat gate can never drift. No status string changed.
CRITICAL_STATUSES = ["🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו"]

DEVIATION_RANK = {"unknown": 0, "normal": 1, "minor": 2, "moderate": 3, "severe": 4, "system_event": 5}
GIVEBACK_RANK  = {"na": 0, "natural": 1, "watch": 2, "tighten": 3, "protection_failure": 4}
PROFIT_CHECKPOINTS = [2.0, 3.0]  # Fire alert when open_r crosses these thresholds
DEVIATION_COOLDOWN_SEC  = 3 * 3600   # 3h cooldown for same deviation class
GIVEBACK_COOLDOWN_SEC   = 6 * 3600   # 6h cooldown for same giveback class
LIVE_ALERT_REPEAT_COOLDOWN = 45 * 60  # 45 min: prevents oscillation spam on non-escalating action/status changes
DAILY_DIGEST_UTC_HOUR_START = 21     # Daily digest window: 21:00 UTC (US market close)
DAILY_DIGEST_UTC_HOUR_END   = 22     # End of window — fires once in this hour per day
SIZING_LEAK_THRESHOLD = 0.65         # < 65% of target risk → Sizing Leak alert (one-time)

# Phase 5 — Anti-Spam: state-transition cooldowns (prevents oscillation re-alerts)
STATE_ALERT_COOLDOWN = {
    "RUNNER":     4 * 3600,   # 4h — price can oscillate around 5R threshold
    "BROKEN":     4 * 3600,   # 4h — price can bounce around stop
    "DEAD_MONEY": 12 * 3600,  # 12h — informational; state is stable but low urgency
}

# Alert priority tiers (reference; governs routing and cooldown expectations)
ALERT_PRIORITY = {
    # P0 — Critical: always fire immediately, no suppression
    "stop_breach":            "P0",
    "algo_cluster_red":       "P0",
    "algo_deep_loss":         "P0",
    "risk_deviation_system":  "P0",
    # P1 — High: fire on transition; re-entry cooldown 4h
    "broken_state":           "P1",
    "runner_state":           "P1",
    "breakeven_protocol":     "P1",
    "risk_deviation_severe":  "P1",
    "algo_loss_streak_orange": "P1",
    # P2 — Medium: 6h standard cooldown
    "profit_checkpoint":         "P2",
    "risk_deviation_moderate":   "P2",
    "giveback_tighten":          "P2",
    "algo_cluster_yellow":       "P2",
    "algo_loss_streak_yellow":   "P2",
    # P3 — Low: market-hours gated, 12–24h cooldown
    "dead_money_state":  "P3",
    "algo_visibility":   "P3",
    "adaptive_risk":     "P3",
    "giveback_watch":    "P3",
}

def _should_fire_state_alert(new_state: str, prev_alerted_type: str,
                              prev_alerted_ts: float, now_ts: float) -> bool:
    """
    Return True if a state-change alert should fire.

    Logic:
      - Always fire if transitioning to a state not seen before in this cycle.
      - For states in STATE_ALERT_COOLDOWN, suppress re-entry alerts for the
        cooldown period to prevent oscillation spam (e.g. price bouncing around
        the RUNNER or BROKEN threshold multiple times per day).
    """
    cooldown = STATE_ALERT_COOLDOWN.get(new_state, 0)
    if cooldown == 0:
        return True
    # Same state re-entered: only fire if cooldown has elapsed
    if new_state == prev_alerted_type:
        return (now_ts - prev_alerted_ts) >= cooldown
    # Different state: always fire (state genuinely changed)
    return True


def load_state():
    return state_io.read_json(STATE_FILE, {"positions": {}, "cluster": {}})

def save_state(state):
    # Locked + atomic: serializes against the telegram-bot RMW in
    # bot_helpers._write_runner_decision so the shared state file is never
    # torn or reset. See state_io / SYSTEM_AUDIT §5.7 (Issue N3).
    # Sprint 14: STATE_FILE now lives under the /app/state named volume.
    # That mountpoint already exists (compose mount + heartbeat), but
    # save_state runs BEFORE _touch_heartbeat in a cycle (:1019 then :1020),
    # so create-if-missing here keeps atomic_write_json's mkstemp(dir=...)
    # safe on a brand-new volume's first post-deploy cycle. No math touched.
    try:
        os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    except Exception:
        pass
    with state_io.file_lock(STATE_FILE):
        state_io.atomic_write_json(STATE_FILE, state)

def get_ibkr_nav():
    try:
        report_path = "ibkr_raw_report.xml"
        if not os.path.exists(report_path): return None
        tree = ET.parse(report_path)
        root = tree.getroot()
        for elem in root.iter():
            if elem.tag.lower().endswith("changeinnav"):
                ending_val = elem.attrib.get('endingValue')
                if ending_val: return float(ending_val)
        return None
    except: return None

def build_position_alert_key(pos, engine_data):
    # Exclude 'trigger' — it oscillates intra-day (e.g. MA10 vs trend-follow text) and
    # causes spurious key-change re-alerts without any real state change.
    return json.dumps({
        "status": engine_data["status"],
        "action": engine_data["action"],
        "sizing": engine_data.get("sizing_status", "✅ תקין")
    }, ensure_ascii=False, sort_keys=True)

def is_during_us_market_hours():
    """True if now is within the US trading day window (pre-market to after-hours).
    Uses UTC check: 11:00–21:00 UTC covers ~14:00–00:00 Israel time on Mon–Fri.
    Repeat cooldown alerts are suppressed outside this window to avoid overnight noise.
    Escalations and first-time alerts always fire regardless of this function."""
    now_utc = datetime.utcnow()
    if now_utc.weekday() >= 5:  # Sat or Sun — US market closed
        return False
    return 11 <= now_utc.hour < 21

def _is_material_escalation(prev, current_status, last_alert_ts, now_ts):
    """Sprint-30 G2 — distinguish a GENUINE worsening from a sub-threshold
    status-flap re-escalation.

    Background (SPRINT29_ARCH S29-1 / UX P0-2, proven in the real export):
    `should_alert` fast-paths ANY rank increase straight to a fresh full
    banner. A campaign straddling a classification boundary (e.g.
    🔥 Power[rank 2] ↔ 🟡 תקין אך במעקב[rank 3] on a <1% price wiggle —
    $898→$903→$899→$901, CAT_9409547470 fired 5× in ~65 lines, 15
    byte-identical blocks) flips DOWN one rank then back UP one rank; the
    "back UP" hits the escalation fast-path and bypasses the
    LIVE_ALERT_REPEAT_COOLDOWN entirely → the SAME alert re-fires every poll.

    This predicate returns True only for a *material* escalation that must
    still fire immediately (escalation semantics PRESERVED):
      • the new status is a P0/CRITICAL status (never suppressed — Mark §4);
      • OR we have climbed to a HIGHER rank than any rank we have ALREADY
        alerted on within the still-active cooldown window (a genuine NEW
        worsening, e.g. Healthy→Weak→Broken — each new high alerts);
      • OR the active cooldown window has elapsed (a re-cross after the
        cooldown is, by the existing LIVE_ALERT_REPEAT_COOLDOWN contract, a
        fresh event and still fires).

    It returns False ONLY for the noise case: a non-critical re-escalation
    back UP to a rank we were ALREADY at (≤ the recent alerted peak) while
    still inside the cooldown window — i.e. the flap. Behaviour-narrowing
    only: strictly fewer duplicate alerts, no new alert type, ALGO
    observe-only path (gated by `_algo_observed` at the call site) unaffected.
    """
    cur_rank = STATUS_RANK.get(current_status, 0)
    # P0/critical worsening is NEVER suppressed (Sprint-14 Mark §4 invariant).
    if current_status in CRITICAL_STATUSES:
        return True
    # The cooldown is no longer active → a re-cross is a fresh event (the
    # existing LIVE_ALERT_REPEAT_COOLDOWN contract). Material.
    if (now_ts - last_alert_ts) > LIVE_ALERT_REPEAT_COOLDOWN:
        return True
    # Within the active cooldown window: a true worsening is one that climbs
    # ABOVE every rank we already alerted on in this window. A flip back UP
    # to a rank ≤ the recent alerted peak is the noise-flap → suppress.
    recent_peak_rank = prev.get("recent_alert_peak_rank")
    if recent_peak_rank is None:
        # No tracked peak (legacy/first escalation) → treat as material so a
        # genuine first escalation is never lost.
        return True
    return cur_rank > recent_peak_rank


def _next_alert_peak_rank(prev, current_status, do_alert, now_ts):
    """Sprint-30 G2 — the `recent_alert_peak_rank` value to persist for the
    NEXT cycle (the worst status rank that has fired an alert while still
    inside the active LIVE_ALERT_REPEAT_COOLDOWN window).

    Kept OUT of `should_alert`'s return so its (do_alert, ts) 2-tuple
    contract — relied on by the LOCKED Sprint-14 dedup tests — is byte-for-
    byte UNCHANGED (Mark 6.1: no existing test weakened). It decays to None
    when the cooldown has elapsed (a re-cross after cooldown is a fresh
    event) so a genuine later worsening is never permanently suppressed.
    Returns None ⇒ caller omits the key (nothing alerted in this window)."""
    if prev is None:
        return STATUS_RANK.get(current_status, 0) if do_alert else None
    last_alert_ts = prev.get("last_alert_ts", 0)
    prev_peak = prev.get("recent_alert_peak_rank")
    cooldown_elapsed = (now_ts - last_alert_ts) > LIVE_ALERT_REPEAT_COOLDOWN
    if do_alert:
        cur_rank = STATUS_RANK.get(current_status, 0)
        # On a fresh fire after the cooldown elapsed the window resets to the
        # just-alerted rank; within an active window it is the running max.
        if cooldown_elapsed or prev_peak is None:
            return cur_rank
        return max(prev_peak, cur_rank)
    # Nothing fired. If the cooldown has elapsed the in-window peak no longer
    # applies (decay). Otherwise it stays sticky across the flap.
    if cooldown_elapsed:
        return None
    return prev_peak


def should_alert(prev, current_status, current_key):
    now_ts = datetime.utcnow().timestamp()
    if prev is None:
        # Sprint 14 (Mark §1 row 1 + §4.4): drop the BLANKET `prev is None`
        # push for NON-P0 status. With persistence fixed (RC-2/RC-3) a None
        # `prev` is now a *genuine* first sighting (no longer the spurious
        # state-loss case). A genuinely-new healthy/held position
        # (🔥 Power / 🟢 Healthy / 🟡 …) is the position working → it belongs
        # on the PULL surface (Open Tasks), NOT a push. A genuine first
        # sighting that is ALREADY a P0/critical status
        # (🚨 קריטי / 🔴 Broken / 🚨 חריגת סיכון אלגו) MUST still push
        # immediately (Mark §4.1/4.3/4.5 — first-ever P0 always fires).
        # State is still recorded by the caller either way, so any later
        # status-worsening escalation fires normally on the next cycle.
        return (current_status in CRITICAL_STATUSES), now_ts

    prev_status = prev.get("status")
    prev_key = prev.get("alert_key")
    last_alert_ts = prev.get("last_alert_ts", 0)

    # Escalation: status worsened. Sprint-30 G2 — only a MATERIAL escalation
    # fast-paths past the cooldown; a sub-threshold flap back UP to a rank we
    # were just at, within the active cooldown window, is the noise-spam and
    # is held (it then falls through to the cooldown-gated key-change branch
    # below, exactly like the symmetric de-escalation already does). The
    # return contract is the SAME (do_alert, new_alert_ts) 2-tuple as before.
    if STATUS_RANK.get(current_status, 0) > STATUS_RANK.get(prev_status, 0):
        if _is_material_escalation(prev, current_status, last_alert_ts, now_ts):
            return True, now_ts
        # noise-flap re-escalation within cooldown → fall through to the
        # cooldown-gated branch (does NOT auto-fire); key may differ so the
        # branch below still allows a fire once the cooldown elapses.

    # Critical/Broken repeat: re-alert after 6h during market hours only
    if current_status in CRITICAL_STATUSES:
        if (now_ts - last_alert_ts) > (6 * 3600) and is_during_us_market_hours():
            return True, now_ts
        return False, last_alert_ts

    # Non-escalating key change (de-escalation or action text oscillation):
    # Apply LIVE_ALERT_REPEAT_COOLDOWN to prevent oscillation spam.
    # Example: Power→Weak fires once; Weak→Power is not an escalation and gets the cooldown.
    if prev_key != current_key:
        if (now_ts - last_alert_ts) > LIVE_ALERT_REPEAT_COOLDOWN:
            return True, now_ts

    return False, last_alert_ts

def _deviation_alert_text(sym, setup, open_r, dev, is_algo):
    RTL_M = "‏"
    if is_algo:
        if dev["alert_level"] == "system":
            heading = f"🚨 *אירוע מערכת — אלגו חורג ממסגרת סיכון*"
        elif dev["alert_level"] == "severe":
            heading = f"🔴 *התרעה חמורה — לבדוק שהאלגו פועל תקין*"
        else:
            heading = f"⚠️ *התרעת ALGO — חריגה מסיכון יעד*"
        action_line = f"{RTL_M}פיקוח: לבדוק שהאלגו מחובר ופעיל. אין המלצת יציאה ידנית."
    else:
        if dev["alert_level"] == "system":
            heading = f"🚨 *אירוע מערכת — חריגה קיצונית מסיכון*"
        elif dev["alert_level"] == "severe":
            heading = f"🔴 *חריגה חמורה מסיכון מתוכנן*"
        else:
            heading = f"⚠️ *חריגת סיכון — מעל סיכון יעד*"
        action_line = f"{RTL_M}פעולה: לבדוק עמידה בסטופ ולהעריך מחדש."

    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    return (
        f"{RTL_M}{heading}\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}חריגה: `{dev['deviation_r']:.2f}R` | סיווג: `{dev['label']}`\n"
        f"{RTL_M}Open R נוכחי: `{open_r:.2f}R`\n"
        f"{RTL_M}{action_line}"
    )


def _giveback_alert_text(sym, setup, peak_r, current_r, gb, is_algo):
    RTL_M = "‏"
    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    if is_algo:
        action_line = f"{RTL_M}פיקוח בלבד — Sentinel אינה מנהלת יציאות אלגו."
    else:
        action_line = f"{RTL_M}פעולה: לשקול הדקת סטופ / מימוש חלקי / מעבר לסטופ עוקב."
    return (
        f"{RTL_M}📉 *Giveback Alert — {gb['label']}*\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}שיא: `{peak_r:.2f}R` → נוכחי: `{current_r:.2f}R`\n"
        f"{RTL_M}ויתור: `{gb['giveback_r']:.2f}R` ({gb['giveback_pct_of_peak']:.0f}% מהשיא)\n"
        f"{RTL_M}{action_line}"
    )


def _checkpoint_alert_text(sym, setup, checkpoint_r, open_r, is_algo,
                            protected_profit=None, giveback_usd=None, giveback_pct=None):
    RTL_M = "‏"
    mode = "ALGO | מנוהל חיצונית" if is_algo else setup
    if is_algo:
        action_line = (
            f"{RTL_M}Sentinel אינה מנהלת יציאות אלגו.\n"
            f"{RTL_M}פיקוח: Profit Protection Checkpoint — מעקב אחרי Giveback מכאן."
        )
    else:
        action_line = (
            f"{RTL_M}פעולה לפי מינרביני: לשקול הגנת רווח — העלאת סטופ, מימוש חלקי, או מעבר ל-Runner."
        )
    extra = ""
    if protected_profit is not None and giveback_usd is not None:
        extra = (f"\n{RTL_M}• רווח מוגן: `${protected_profit:.0f}` "
                 f"| Giveback עד סטופ: `${giveback_usd:.0f}`"
                 + (f" ({giveback_pct:.0f}%)" if giveback_pct is not None else ""))
    return (
        f"{RTL_M}🏁 *Profit Protection Checkpoint — {checkpoint_r:.0f}R*\n"
        f"{RTL_M}סימול: *{sym}* | מצב: `{mode}`\n"
        f"{RTL_M}Open R: `{open_r:.2f}R` חצה סף `{checkpoint_r:.0f}R`{extra}\n"
        f"{RTL_M}{action_line}"
    )


# ── Phase 3 — State-change alert templates ───────────────────────────────────

def _runner_state_alert(sym, setup, open_r, protected_profit, giveback_usd,
                         giveback_pct, current_stop, days_to_earnings,
                         trail_stop: dict | None = None):
    RTL_M = "‏"
    earnings_line = ""
    if days_to_earnings is not None and days_to_earnings <= 30:
        earnings_line = f"\n{RTL_M}• דוחות בעוד: `{days_to_earnings} ימים`"
    trail_line = ""
    if trail_stop and trail_stop.get("basis") != "none" and trail_stop.get("suggested_stop"):
        trail_line = f"\n{RTL_M}• 🎯 *Trailing Stop מוצע:* `${trail_stop['suggested_stop']:.2f}` ({trail_stop['basis']})"
    return (
        f"{RTL_M}🏃 *Runner Mode — {sym}*\n"
        f"{RTL_M}הפוזיציה הגיעה ל-`{open_r:.1f}R` — מצב Runner.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}• Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}• רווח מוגן (לפי סטופ): `${protected_profit:.0f}`\n"
        f"{RTL_M}• Giveback עד סטופ: `${giveback_usd:.0f}` ({giveback_pct:.0f}%)\n"
        f"{RTL_M}• סטופ נוכחי: `${current_stop:.2f}`{trail_line}{earnings_line}\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}✅ להחזיק אם יש Tennis Ball ומחזור יורד בירידות.\n"
        f"{RTL_M}⚠️ Giveback > 40%? — שקל הדקת סטופ.\n"
        f"{RTL_M}🚫 לא להוסיף לפני בסיס חדש."
    )


def _runner_decision_keyboard(sym, campaign_id):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("✅ להחזיק", callback_data=f"runner_decision|hold|{sym}|{campaign_id}"),
        telebot.types.InlineKeyboardButton("🔒 הדק סטופ", callback_data=f"runner_decision|tighten|{sym}|{campaign_id}"),
    )
    markup.add(
        telebot.types.InlineKeyboardButton("📊 מימוש חלקי", callback_data=f"runner_decision|partial|{sym}|{campaign_id}"),
    )
    return markup


def _broken_state_alert(sym, setup, open_r, reason):
    RTL_M = "‏"
    return (
        f"{RTL_M}🔴 *טרייד שבור — {sym}*\n"
        f"{RTL_M}הפוזיציה כבר לא עומדת בתוכנית המקורית.\n"
        f"{RTL_M}סיבה: `{reason}`\n"
        f"{RTL_M}Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}• לפעול לפי תוכנית היציאה שהוגדרה מראש.\n"
        f"{RTL_M}• לתעד: האם הייתה חריגת סיכון? נדרש Re-entry Watch?"
    )


def _dead_money_alert(sym, setup, age_days, open_r):
    RTL_M = "‏"
    return (
        f"{RTL_M}⏳ *Dead Money Risk — {sym}*\n"
        f"{RTL_M}הפוזיציה לא שבורה, אבל גם לא מתקדמת.\n"
        f"{RTL_M}• ותק: `{age_days:.0f} ימים` | Open R: `{open_r:.1f}R`\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}✅ להחזיק אם יש Tight action ומחזור יורד.\n"
        f"{RTL_M}↩️ לשקול צמצום אם יש הזדמנות טובה יותר.\n"
        f"{RTL_M}🚫 לא להוסיף עד פריצה/חוזקה חדשה."
    )


def _breakeven_protocol_alert(sym, open_r, capital_at_risk_usd):
    RTL_M = "‏"
    return (
        f"{RTL_M}🧷 *Breakeven Protection Required — {sym}*\n"
        f"{RTL_M}הפוזיציה הגיעה ל-`{open_r:.1f}R`, אבל לפי הסטופ הנוכחי\n"
        f"{RTL_M}עדיין קיים סיכון הון של `${capital_at_risk_usd:.0f}`.\n"
        f"{RTL_M}זה לא מתאים לניהול Risk First.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}1. לקדם סטופ לפחות לאזור כניסה.\n"
        f"{RTL_M}2. לממש חלק ולהשאיר Runner.\n"
        f"{RTL_M}3. להשאיר רק עם סיבה טכנית מתועדת.\n"
        f"{RTL_M}🚫 לא לתת לפוזיציה של 3R להפוך להפסד מלא."
    )


# ── Phase 4 — ALGO Oversight alert templates ─────────────────────────────────

def _algo_deep_loss_alert(sym, open_r):
    RTL_M = "‏"
    return (
        f"{RTL_M}🔴 *ALGO Oversight — הפסד עמוק*\n"
        f"{RTL_M}סימול: *{sym}* | Open R: `{open_r:.2f}R`\n"
        f"{RTL_M}הפוזיציה חצתה ─2R — מגבלת הפסד גבוהה.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}פיקוח: Sentinel לא תציע מכירה ולא תציע שינוי סטופ.\n"
        f"{RTL_M}ℹ️ לוודא שהאלגו עדיין פעיל ועובד לפי הגדרות."
    )


def _algo_loss_streak_alert(sym, open_r, streak_runs, level):
    RTL_M = "‏"
    duration_min = streak_runs * 5
    if level == "orange":
        heading = f"🔴 *ALGO Oversight — ירידה ממושכת*"
    else:
        heading = f"⚠️ *ALGO Oversight — מגמת ירידה*"
    return (
        f"{RTL_M}{heading}\n"
        f"{RTL_M}סימול: *{sym}* | Open R: `{open_r:.2f}R`\n"
        f"{RTL_M}הפוזיציה בהפסד במשך ~{duration_min} דקות ברצף ({streak_runs} ריצות).\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}פיקוח: Sentinel לא מתערבת בניהול אלגו.\n"
        f"{RTL_M}ℹ️ לוודא שהאלגו מחובר ופועל תקין."
    )


def _algo_visibility_alert(visibility_avg, n_positions):
    RTL_M = "‏"
    return (
        f"{RTL_M}⚠️ *ALGO Oversight — נתוני סיכון חסרים*\n"
        f"{RTL_M}ממוצע ניקוד שקיפות: `{visibility_avg:.0f}/100` ({n_positions} פוזיציות)\n"
        f"{RTL_M}ציון 40 = תקין לאלגו (אין סטופ ידוע). ציון 20 = אין target_risk_usd.\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}ℹ️ לבדוק: הוזנו target_risk_usd בפוזיציות האלגו?"
    )


def _sizing_leak_alert(sym, setup, sizing_ratio, target_risk_usd, original_campaign_risk):
    RTL_M = "‏"
    return (
        f"{RTL_M}⚖️ *Sizing Leak — {sym}*\n"
        f"{RTL_M}סטאפ: `{setup}` | נלקח ב-`{sizing_ratio:.2f}x` סיכון יעד\n"
        f"{RTL_M}יעד: `${target_risk_usd:.0f}` | בפועל: `${original_campaign_risk:.0f}`\n"
        f"{RTL_M}─────────────────\n"
        f"{RTL_M}המשמעות: ה-Edge קיים, אבל ההון לא מנוצל מספיק.\n"
        f"{RTL_M}לא לפעול עכשיו — לרשום כלקח לטרייד הבא מאותו Setup."
    )


# Sprint-27 W3 / Sprint-30 G3 — the SINGLE source of the "🧭 מה עכשיו?"
# companion derivation in the risk-monitor domain. The exact urgent-state set
# the digest already used (BROKEN / RUNNER / PROFIT_PROTECTION) is hoisted into
# a named constant so the digest line and the new live-alert companion line are
# provably the SAME derivation — no new wording, no new logic, no new data.
_WHATNOW_URGENT_STATES = (
    ec.POSITION_STATE_BROKEN,
    ec.POSITION_STATE_RUNNER,
    ec.POSITION_STATE_PROFIT_PROTECTION,
)


def _whatnow_live_companion(status: str, action: str) -> str:
    """Sprint-30 G3 — surface the existing "🧭 מה עכשיו?" companion voice on
    the high-frequency LIVE alert surface (the alert/חדר-מצב path the trader
    actually lives), where it appeared 0× in the 995-msg live stream.

    PURE presentation, ZERO math, NO new message type: it ONLY restates the
    ALREADY-computed engine `status` + `action` of THIS alert as one short
    Hebrew next-step line, using the SAME `🧭 *מה עכשיו?*` voice the
    on-demand weekly/monthly + daily-digest path already speak. It can NEVER
    be a false all-clear (it is only ever appended to a fired alert about a
    flagged position) and it never contradicts the body — it is the body's
    own `action`, verbatim, framed as the one next step. `status`/`action`
    are the exact strings already printed two lines above it.
    """
    act = (action or "").strip()
    if act:
        return f"{RTL}🧭 *מה עכשיו?* {act} — ראה הפירוט למעלה."
    # Defensive: an empty action is never a green light — point at the body.
    return f"{RTL}🧭 *מה עכשיו?* יש לבחון את הפוזיציה לפי הפירוט למעלה."


def _daily_digest_text(rows: list, date_str: str) -> str:
    RTL_M = "‏"
    _state_emoji = {
        ec.POSITION_STATE_RUNNER:            "🏃",
        ec.POSITION_STATE_BROKEN:            "🔴",
        ec.POSITION_STATE_DEAD_MONEY:        "⏳",
        ec.POSITION_STATE_YELLOW_FLAG:       "🟡",
        ec.POSITION_STATE_PROFIT_PROTECTION: "🛡️",
        ec.POSITION_STATE_WORKING:           "✅",
        ec.POSITION_STATE_PROVING:           "🔍",
    }
    _action_map = {
        ec.POSITION_STATE_RUNNER:            "הגן על רווח",
        ec.POSITION_STATE_BROKEN:            "בצע יציאה",
        ec.POSITION_STATE_DEAD_MONEY:        "שקול צמצום",
        ec.POSITION_STATE_YELLOW_FLAG:       "מעקב צמוד",
        ec.POSITION_STATE_PROFIT_PROTECTION: "שקול הדקת סטופ",
        ec.POSITION_STATE_WORKING:           "עקוב",
        ec.POSITION_STATE_PROVING:           "בדוק follow-through",
    }
    # Sprint-27 W3 (UX P0-1) — derive `urgent` FIRST (same classification the
    # body uses below, byte-identical set) so the ONE companion "מה עכשיו?"
    # line can lead the digest. PURE presentation: it summarizes the
    # ALREADY-computed per-row `state` into one actionable Hebrew sentence;
    # NO new computation, NO new data source, NO number touched. The Sprint-26
    # UX review (P0-1): the digest opens with a divider then a flat bullet
    # list — the human must reconstruct "do I need to act?" himself.
    # Sprint-30 G3: the urgent set is now read from the shared
    # `_WHATNOW_URGENT_STATES` constant — the SAME tuple (same three states,
    # same order) the live-alert companion derivation uses. Provably
    # byte-identical to the prior inline literal (BROKEN, RUNNER,
    # PROFIT_PROTECTION) — pure de-duplication, no behaviour change. Pinned by
    # the existing test_digest_body_bullets_byte_identical.
    urgent = [r["sym"] for r in rows if r["state"] in _WHATNOW_URGENT_STATES]
    if urgent:
        _whatnow = (f"{RTL_M}🧭 *מה עכשיו?* {len(urgent)} פוז' דורשות החלטה: "
                    f"{', '.join(urgent)} — ראה פירוט למטה.")
    else:
        _whatnow = (f"{RTL_M}🧭 *מה עכשיו?* {len(rows)} פוז' תחת מעקב, "
                    f"אין פעולה דחופה — עקוב לפי הפירוט.")
    lines = [
        f"{RTL_M}📋 *Sentinel — סיכום יומי | {date_str}*",
        _whatnow,
        f"{RTL_M}───────────────────",
    ]
    for r in rows:
        emoji = _state_emoji.get(r["state"], "⚪")
        action = _action_map.get(r["state"], "עקוב")
        tag = " `[ALGO]`" if r["is_algo"] else ""
        r_str = f"`{r['open_r']:+.1f}R`"
        lines.append(f"{RTL_M}• *{r['sym']}*{tag} {emoji} {r_str} — {action}")
    if urgent:
        lines.append(f"{RTL_M}───────────────────")
        lines.append(f"{RTL_M}⚡ *נדרשת החלטה:* {', '.join(urgent)}")
    else:
        # Sprint-30 G6 — silence ≠ all-clear. When the digest renders with
        # NOTHING actionable it previously ended on the flat bullet list +
        # the dashboard footer; an idle monitor and a calm one looked
        # identical (0 positive-heartbeat in the 1,425-msg real export). Add
        # ONE explicit Hebrew alive line to the EXISTING digest message (NOT
        # a new periodic message): the monitor ran, it is active, and
        # nothing needs action right now — honest, additive, ZERO math.
        lines.append(f"{RTL_M}───────────────────")
        lines.append(f"{RTL_M}✅ *מערכת פעילה — אין פעולה נדרשת כרגע.*")
    lines.append(f"{RTL_M}───────────────────")
    lines.append(f"{RTL_M}_(ללא פעולה נוספת? הדאשבורד עדכני)_")
    return "\n".join(lines)


def _send_daily_digest_if_due(state: dict, rows: list, now_ts: float) -> None:
    """Send one daily digest at US market close (21:00–22:00 UTC), Mon–Fri only."""
    now_utc = datetime.utcnow()
    if now_utc.weekday() >= 5:  # Sat/Sun — market closed
        return
    if not (DAILY_DIGEST_UTC_HOUR_START <= now_utc.hour < DAILY_DIGEST_UTC_HOUR_END):
        return
    today_str = now_utc.strftime("%Y-%m-%d")
    if state.get("last_digest_date") == today_str:
        return
    if not rows:
        return
    send_telegram(_daily_digest_text(rows, now_utc.strftime("%d/%m/%Y")))
    state["last_digest_date"] = today_str


def check_position_risk_thresholds(sym, setup, open_r, open_pnl_usd, target_risk_usd,
                                    is_algo, prev_state, now_ts):
    """
    Check risk deviation, giveback, and profit protection checkpoints for one position.
    Returns (alerts_list, state_updates_dict).
    alerts_list: list of strings to send via Telegram.
    state_updates_dict: fields to merge into the position's state dict.
    """
    alerts = []
    updates = {}

    peak_open_r = max(prev_state.get("peak_open_r", 0.0), open_r if open_r > 0 else 0.0)
    updates["peak_open_r"] = peak_open_r

    # ── Risk Deviation (losses only) ──────────────────────────────────────
    if open_pnl_usd < 0 and target_risk_usd > 0:
        dev = ec.compute_risk_deviation(open_pnl_usd, target_risk_usd)
        prev_dev_class = prev_state.get("last_deviation_class", "normal")
        prev_dev_ts = prev_state.get("last_deviation_ts", 0)
        alert_levels_to_notify = {"moderate", "severe", "system_event"}

        escalated = DEVIATION_RANK.get(dev["classification"], 0) > DEVIATION_RANK.get(prev_dev_class, 0)
        cooled_down = (now_ts - prev_dev_ts) > DEVIATION_COOLDOWN_SEC
        should_fire = dev["classification"] in alert_levels_to_notify and (escalated or cooled_down)

        if should_fire:
            alerts.append(_deviation_alert_text(sym, setup, open_r, dev, is_algo))
            updates["last_deviation_class"] = dev["classification"]
            updates["last_deviation_ts"] = now_ts
        elif dev["classification"] not in ("normal", "minor"):
            # Track class even without alert
            updates["last_deviation_class"] = dev["classification"]

    # ── Profit Protection Checkpoints ─────────────────────────────────────
    checkpoints_hit = set(prev_state.get("checkpoints_hit", []))
    for cp in PROFIT_CHECKPOINTS:
        if open_r >= cp and cp not in checkpoints_hit:
            alerts.append(_checkpoint_alert_text(sym, setup, cp, open_r, is_algo))
            checkpoints_hit.add(cp)
    updates["checkpoints_hit"] = list(checkpoints_hit)

    # ── Giveback Monitor (only when meaningful profit existed, not after BROKEN) ─
    _pos_state = prev_state.get("position_state", "")
    if peak_open_r >= 1.5 and open_r < peak_open_r and _pos_state != ec.POSITION_STATE_BROKEN:
        gb = ec.compute_giveback_from_peak(peak_open_r, open_r)
        prev_gb_class = prev_state.get("last_giveback_class", "natural")
        prev_gb_ts = prev_state.get("last_giveback_ts", 0)
        alert_classes_to_notify = {"watch", "tighten", "protection_failure"}

        zone_changed = gb["classification"] != prev_gb_class
        # Fire only on zone transition (entering OR leaving an alert zone).
        # No repeat-after-cooldown within the same zone — that caused the spam.
        is_alert_current = gb["classification"] in alert_classes_to_notify
        is_alert_prev = prev_gb_class in alert_classes_to_notify
        should_fire = zone_changed and (is_alert_current or is_alert_prev)

        if should_fire:
            alerts.append(_giveback_alert_text(sym, setup, peak_open_r, open_r, gb, is_algo))
        updates["last_giveback_class"] = gb["classification"]
        if should_fire:
            updates["last_giveback_ts"] = now_ts

    return alerts, updates


def _audit_telegram_send_failure(helper_name: str, text: str, exc: Exception) -> None:
    """F8 (Meeting 21/05/2026 Wave 2) — deadletter audit on Telegram send
    failure. Writes ONE audit_log row capturing helper origin + error
    + a SHORT preview of the failed text (first 80 chars; full message
    is NOT logged to avoid leaking sensitive content / market positions
    into the audit trail).

    Never raises — audit_logger.log_action is fail-open, this wrapper is
    just defense in depth so the catch site stays clean.
    """
    try:
        audit_logger.log_action(
            supabase, audit_logger.ACTION_TELEGRAM_SEND_FAILED,
            metadata={
                "helper":        helper_name,
                "error_type":    type(exc).__name__,
                "error_message": str(exc)[:200],
                # Preview only — full message could contain symbol/PnL data
                # that the audit log doesn't need a permanent copy of.
                "text_preview":  (text or "")[:80],
            },
        )
    except Exception:
        pass  # Audit must NEVER block business logic.


def send_telegram(text):
    if not ADMIN_ID: return
    try:
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Telegram send failed: {e}")
        _audit_telegram_send_failure("send_telegram", text, e)

def send_telegram_with_keyboard(text, markup):
    if not ADMIN_ID: return
    try:
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(f"Telegram send_keyboard failed: {e}")
        _audit_telegram_send_failure("send_telegram_with_keyboard", text, e)

_KNOWN_RISK_PCT_KEY = "last_known_risk_pct"


def check_manual_risk_override(state: dict) -> None:
    """
    Detect when risk_pct_input in sentinel_config.json was changed outside of
    the Telegram flow (i.e. manually edited or by a script). When detected,
    log it via mark_adherence and send a Telegram alert.
    """
    try:
        cfg = get_account_settings()
        current_pct = float(cfg.get("risk_pct_input", 0.5))
        last_known = state.get(_KNOWN_RISK_PCT_KEY)

        if last_known is not None and abs(current_pct - float(last_known)) > 0.001:
            # Suppress alert if the change originated from the Telegram bot (within 2 minutes)
            via_bot_ts = float(cfg.get("risk_changed_ts", 0))
            is_bot_change = (time.time() - via_bot_ts) < 120

            if not is_bot_change:
                delta = current_pct - float(last_known)
                direction = "⬆️" if delta > 0 else "⬇️"
                are.mark_adherence(
                    recommended_pct=float(last_known),
                    actual_pct=current_pct,
                    followed=False,
                    reason="Manual override detected by risk monitor",
                )
                are.log_risk_journal({
                    "direction": "up" if delta > 0 else "down_fast",
                    "current_risk_pct": float(last_known),
                    "recommended_risk_pct": float(last_known),
                    "action": "manual_override",
                    "actual_pct_set": current_pct,
                    "nav": ec.get_nav_with_freshness()["nav"],
                })
                alert = (
                    f"{RTL}⚠️ *זוהתה שינוי ידנית בסיכון*\n"
                    f"{RTL}risk\\_pct שונה מחוץ לטלגרם\n"
                    f"{RTL}{direction} `{float(last_known):.2f}%` → `{current_pct:.2f}%`\n"
                    f"{RTL}נרשם ביומן הסיכון כ-manual override."
                )
                send_telegram(alert)

        state[_KNOWN_RISK_PCT_KEY] = current_pct
    except Exception as e:
        print(f"check_manual_risk_override error: {e}")


def main():
    state = load_state()
    check_manual_risk_override(state)

    account_settings = get_account_settings()
    nav_info = ec.get_nav_with_freshness()
    acc_size = nav_info["nav"] if nav_info["ok"] else float(account_settings.get("total_deposited", 7500.0))
    target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
    target_risk_usd = acc_size * (target_risk_pct / 100)

    # Settle state — used to suppress Sizing Leak during 48h after a risk raise
    settle_state = are.get_risk_settle_info()
    
    res = supabase.table("trades").select("*").execute()
    df = pd.DataFrame(res.data)
    if df.empty: return
    
    pos_res = ec.get_open_positions_campaign(df)
    if not pos_res["ok"] or pos_res["data"].empty: return
    open_pos = pos_res["data"]
    
    spy_hist = ec.get_cached_history("SPY", "1y", "1d")
    total_algo_exposure = 0.0
    algo_oversight_positions = []
    new_position_state = {}
    daily_digest_rows = []
    open_positions_for_risk = []
    now_ts = datetime.utcnow().timestamp()

    for _, row in open_pos.iterrows():
        sym, setup, entry = row["symbol"], row["setup_type"], float(row["price"])
        qty, sl, init_sl = float(row["quantity"]), float(row["stop_loss"]), float(row["initial_stop"])
        realized_pnl, entry_date = float(row["realized_pnl"]), row["entry_date"]
        campaign_id, mgt_state = row["campaign_id"], row.get("management_state", "full_position")
        
        curr = ec.get_live_price(sym)
        if curr is None:
            send_telegram(
                f"{RTL}⚠️ *Sentinel — מחיר חי חסר*\n"
                f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
                f"{RTL}לא נמצא מחיר חי — משתמש במחיר כניסה `${entry:.2f}` כ-fallback.\n"
                f"{RTL}_בדוק את החיבור ל-yfinance / market data_"
            )
            curr = entry

        open_pnl = (curr - entry) * qty
        pos_value = curr * qty
        weight_pct = (pos_value / acc_size) * 100 if acc_size > 0 else 0
        if str(setup).upper() == "ALGO": total_algo_exposure += pos_value

        # Single source of truth: ec.get_campaign_risk_metrics() via engine_core
        _risk_metrics = ec.get_campaign_risk_metrics(dict(row))
        original_campaign_risk = _risk_metrics["original_risk"]
        if not _risk_metrics["valid"] and str(setup).upper() != "ALGO":
            send_telegram(
                f"{RTL}⚠️ *Sentinel — סטופ מקורי חסר*\n"
                f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
                f"{RTL}לא ניתן לחשב 1R: {_risk_metrics['reason']}\n"
                f"{RTL}_עדכן initial\\_stop בסופאבייס_"
            )

        total_pos_profit = open_pnl + realized_pnl

        total_campaign_r = (total_pos_profit / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((total_pos_profit / original_campaign_risk) if original_campaign_risk > 0 else 0)
        open_r = (open_pnl / target_risk_usd) if str(setup).upper() == 'ALGO' and target_risk_usd > 0 else ((open_pnl / original_campaign_risk) if original_campaign_risk > 0 else 0)

        r_str = f"`{open_r:.1f}R`" + (" *(Target Base)*" if str(setup).upper() == "ALGO" else "")

        engine_res = ec.evaluate_position_engine(
            symbol=sym, entry_price=entry, entry_date_str=entry_date, current_stop=sl,
            setup_type=setup, mgt_state=mgt_state, weight_pct=weight_pct, total_r=total_campaign_r,
            target_risk_usd=target_risk_usd, actual_risk_usd=original_campaign_risk, spy_hist=spy_hist
        )

        if not engine_res["ok"]:
            send_telegram(
                f"{RTL}🚨 *Sentinel — שגיאה בהערכת פוזיציה*\n"
                f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
                f"{RTL}evaluate\\_position\\_engine נכשל: `{engine_res.get('error', 'unknown')}`\n"
                f"{RTL}_הפוזיציה דולגה בסבב זה_"
            )
            continue
        engine = engine_res["data"]
        
        alert_key = build_position_alert_key(row, engine)
        prev = state["positions"].get(campaign_id)

        do_alert, new_alert_ts = should_alert(prev, engine["status"], alert_key)
        # Sprint-30 G2: the recent-alerted-peak rank to persist for the next
        # cycle (kept out of should_alert's 2-tuple so the LOCKED Sprint-14
        # dedup tests' (fire, ts) unpack is byte-for-byte unchanged).
        _now_for_peak = datetime.utcnow().timestamp()
        _alert_peak_rank = _next_alert_peak_rank(
            prev, engine["status"], do_alert, _now_for_peak)

        # Sprint 14 RC-6 (Mark §2 / DEC-20260511-001 / invariant #8): ALGO is
        # observer-only and MUST NEVER push a management action. This generic
        # recurring Live-Alert status push is exactly the path that spammed
        # HOOD Weak→Broken→Broken once `prev` was lost. Classify management
        # mode HERE (pure read, no math) and gate the generic push for
        # algo_observed positions. ALGO's allowed observer-framed visibility
        # (deep-loss one-time :849, loss-streak one-shot, deviation,
        # 24h portfolio note) keeps firing via its OWN dedicated paths below
        # — those are NOT this generic msg, so no ALGO P0 is suppressed.
        _mgt_mode = ec.classify_management_mode(setup, sym)
        _algo_observed = (_mgt_mode == "algo_observed")

        if do_alert and not _algo_observed:
            issues = f" | {' | '.join(engine['issues'])}" if engine["issues"] else ""
            sizing_str = engine.get("sizing_status", "✅ תקין")
            
            msg = (
                f"{RTL}🚨 *Sentinel Live Alert*\n"
                f"{RTL}סימול: *{sym}* | קמפיין: `{campaign_id}`\n"
                f"{RTL}סטאפ: `{setup}` | ניהול: `{mgt_state}`\n"
                f"{RTL}מחיר ממוצע: `${curr:.2f}` | חשיפה: `{weight_pct:.1f}%`\n"
            )
            if str(setup).upper() != "ALGO":
                msg += f"{RTL}סיכון מקורי (קמפיין): `${original_campaign_risk:.0f}` (יעד: `${target_risk_usd:.0f}`)\n"
                if sizing_str != "✅ תקין":
                    if "גבוה" in sizing_str: msg += f"{RTL}⚠️ *Sizing:* סיכון כניסה גבוה מדי!\n"
                    elif "נמוך" in sizing_str: msg += f"{RTL}📉 *Sizing:* סיכון כניסה נמוך מדי!\n"
                
                if total_campaign_r <= -1.25 and original_campaign_risk > 0:
                    msg += f"{RTL}🚨 *Execution:* חריגה חמורה מהסטופ ({total_campaign_r:.1f}R)\n"
            
            msg += (
                f"{RTL}Open R: {r_str}\n"
                f"{RTL}סטטוס: *{engine['status']}*{issues}\n"
                f"{RTL}פעולה: *{engine['action']}*\n"
                f"{RTL}טריגר: `{engine['trigger']}`"
            )

            if str(setup).upper() != "ALGO" and engine["suggested_stop"] > 0 and engine["suggested_stop"] != sl:
                msg += f"\n{RTL}סטופ מוצע: `${engine['suggested_stop']:.2f}`"

            # Sprint-30 G3 — append the existing "🧭 מה עכשיו?" companion
            # voice onto the LIVE alert (the high-frequency surface the
            # trader actually lives — it was 0× in the 995-msg live stream).
            # PURE presentation, ZERO math, NO new message type: it restates
            # THIS alert's ALREADY-computed engine `action` as the one next
            # step, in the SAME companion voice the weekly/digest path
            # speaks. It is appended to an already-fired alert about a
            # flagged position, so it can never be a false all-clear, and it
            # echoes the body's own `action` so it can never contradict it.
            msg += "\n" + _whatnow_live_companion(
                engine["status"], engine["action"])

            send_telegram(msg)
            
        new_pos_entry = {
            "status": engine["status"], "alert_key": alert_key,
            "updated_at": datetime.utcnow().isoformat(), "last_alert_ts": new_alert_ts,
        }
        # Sprint-30 G2: persist the recent in-window alerted-peak rank so the
        # next cycle can tell a genuine NEW worsening apart from a noise-flap
        # re-escalation back to a rank we were just at. None ⇒ omit the key
        # entirely (cooldown decayed / nothing alerted yet) so a later
        # genuine escalation is never permanently suppressed.
        if _alert_peak_rank is not None:
            new_pos_entry["recent_alert_peak_rank"] = _alert_peak_rank
        # Carry over threshold-tracking fields from previous state
        if prev:
            for carry_key in ("peak_open_r", "last_deviation_class", "last_deviation_ts",
                              "last_giveback_class", "last_giveback_ts", "checkpoints_hit",
                              "position_state", "state_label", "breakeven_alerted",
                              "algo_loss_streak", "algo_streak_alerted_yellow",
                              "algo_streak_alerted_orange", "algo_deep_loss_alerted",
                              "last_state_alert_ts", "last_state_alert_type",
                              "runner_decision", "runner_decision_ts",
                              "sizing_leak_alerted"):
                if carry_key in prev:
                    new_pos_entry[carry_key] = prev[carry_key]

        # Risk Deviation / Giveback / Profit Protection Checkpoints
        is_algo = ec.is_algo_position(setup, sym)
        open_positions_for_risk.append({"open_r": open_r, "is_algo": is_algo})
        threshold_alerts, threshold_updates = check_position_risk_thresholds(
            sym=sym, setup=setup, open_r=open_r, open_pnl_usd=open_pnl,
            target_risk_usd=target_risk_usd, is_algo=is_algo,
            prev_state=new_pos_entry, now_ts=now_ts,
        )
        new_pos_entry.update(threshold_updates)

        # Enrich checkpoint alerts with Phase 1 protected-profit / giveback values
        _side_pos = "BUY"
        _open_pnl_at_stop = ec.compute_open_pnl_at_stop(_side_pos, entry, sl, qty)
        _protected_profit  = ec.compute_protected_profit_usd(realized_pnl, _open_pnl_at_stop)
        _giveback_usd      = ec.compute_giveback_usd(open_pnl, _open_pnl_at_stop)
        _giveback_pct      = ec.compute_giveback_pct_of_open_profit(_giveback_usd, open_pnl)
        _capital_at_risk   = ec.compute_capital_at_risk_usd(_side_pos, entry, sl, qty)

        for alert_text in threshold_alerts:
            send_telegram(alert_text)

        # ── Phase 3: Position State Machine ──────────────────────────────────
        # Age in days since campaign entry
        try:
            _entry_dt = pd.to_datetime(entry_date).to_pydatetime().replace(tzinfo=None)
            _age_days = max(0.0, float((datetime.utcnow() - _entry_dt).days))
        except Exception:
            _age_days = 0.0

        # Earnings window (cached, non-blocking)
        _days_to_earnings = None
        try:
            _earn = ec.fetch_next_earnings_date(sym)
            if _earn.get("ok") and _earn.get("days_to_event") is not None:
                _days_to_earnings = int(_earn["days_to_event"])
        except Exception:
            pass

        # _mgt_mode already classified above (pure read, hoisted for the
        # RC-6 ALGO live-alert gate); reuse it — value is identical, the
        # downstream :771/:789/:837/:846 guards are unchanged.

        # Follow-through score — None for ALGO (different management) or when
        # the position is too young / history unavailable.
        _ft_score = None
        if _mgt_mode != "algo_observed":
            try:
                _ft_score = ec.compute_follow_through(
                    symbol=sym, entry_date_str=entry_date,
                    entry_price=entry, side=_side_pos,
                )
            except Exception as e:
                print(f"follow-through error for {sym}: {e}")

        _state_result = ec.compute_position_state(
            side=_side_pos,
            management_mode=_mgt_mode,
            age_days=_age_days,
            open_r=open_r,
            realized_pnl=realized_pnl,
            original_campaign_risk=original_campaign_risk,
            current_price=curr,
            current_stop=sl,
            days_to_earnings=_days_to_earnings,
            follow_through_score=_ft_score,
            violation_score=0,
            has_new_high_since_entry=True,
            has_open_quantity=(qty > 0),
        )

        _new_state  = _state_result["state"]
        _prev_state = new_pos_entry.get("position_state", "")

        # F7 (Meeting 21/05/2026) — audit-log every position state transition,
        # INCLUDING ALGO positions whose Telegram alerts are intentionally
        # suppressed below (`_mgt_mode != "algo_observed"` gate). Before F7
        # the CEO had no chronological record of when ALGO went Broken — only
        # the state_label visible in /portfolio at the moment. The audit row
        # answers "when did PLTR go to Broken?" in one Supabase query.
        # Fail-soft per audit_logger contract: never raises into the monitor.
        if _new_state != _prev_state:
            _is_algo_state = (_mgt_mode == "algo_observed")
            audit_logger.log_action(
                supabase, audit_logger.ACTION_POSITION_STATE_TRANSITION,
                metadata={
                    "symbol":             sym,
                    "campaign_id":        campaign_id,
                    "setup":              setup,
                    "prev_state":         _prev_state,
                    "new_state":          _new_state,
                    "is_algo":            _is_algo_state,
                    "telegram_suppressed": _is_algo_state,
                    "suppression_reason": "algo_observed" if _is_algo_state else None,
                    "open_r":             round(float(open_r or 0), 2),
                },
            )

        # Phase 5: state-change alerts with oscillation-safe cooldown
        if _new_state != _prev_state and _mgt_mode != "algo_observed":
            _last_sa_type = new_pos_entry.get("last_state_alert_type", "")
            _last_sa_ts   = new_pos_entry.get("last_state_alert_ts", 0.0)
            _fire = _should_fire_state_alert(_new_state, _last_sa_type,
                                             _last_sa_ts, now_ts)
            if _fire:
                if _new_state == ec.POSITION_STATE_RUNNER:
                    _dec     = new_pos_entry.get("runner_decision", "")
                    _dec_ts  = new_pos_entry.get("runner_decision_ts", 0.0)
                    if _dec == "hold" and (now_ts - _dec_ts) < 24 * 3600:
                        _fire = False  # user decided to hold — suppress for 24h
                    else:
                        _ma_lvls = {}
                        try:
                            _ma_lvls = ec.get_ma_levels(sym)
                        except Exception:
                            pass
                        # Pass ATR so the buffer scales with volatility (Sprint 8 #6).
                        # atr_pct is in the engine_res features dict — high-ATR
                        # names get a wider buffer, preventing whipsaws.
                        _atr_pct = (engine.get("features") or {}).get("atr_pct")
                        _trail = ec.compute_suggested_trail_stop(
                            side=_side_pos, current_price=curr,
                            ma21=_ma_lvls.get("ma21"), ma50=_ma_lvls.get("ma50"),
                            open_r=open_r, entry_price=entry,
                            atr_pct=_atr_pct,
                        )
                        send_telegram_with_keyboard(
                            _runner_state_alert(sym, setup, open_r,
                                                _protected_profit, _giveback_usd, _giveback_pct,
                                                sl, _days_to_earnings, trail_stop=_trail),
                            _runner_decision_keyboard(sym, campaign_id),
                        )
                elif _new_state == ec.POSITION_STATE_BROKEN:
                    send_telegram(_broken_state_alert(sym, setup, open_r,
                                                       _state_result["reason"]))
                elif _new_state == ec.POSITION_STATE_DEAD_MONEY:
                    send_telegram(_dead_money_alert(sym, setup, _age_days, open_r))
                else:
                    _fire = False  # no alert for this state — don't update ts
            if _fire:
                new_pos_entry["last_state_alert_type"] = _new_state
                new_pos_entry["last_state_alert_ts"]   = now_ts

        # Break-even Protocol: 3R+ but capital still at risk (one-time alert)
        if (open_r >= 3.0
                and _capital_at_risk > 0
                and not new_pos_entry.get("breakeven_alerted", False)
                and _mgt_mode != "algo_observed"):
            send_telegram(_breakeven_protocol_alert(sym, open_r, _capital_at_risk))
            new_pos_entry["breakeven_alerted"] = True

        new_pos_entry["position_state"] = _new_state
        new_pos_entry["state_label"]    = _state_result["label"]
        # ─────────────────────────────────────────────────────────────────────

        # ── Phase 4: ALGO Oversight per-position ─────────────────────────────
        if _mgt_mode == "algo_observed":
            # Consecutive loss streak (one run = ~5 min)
            _prev_streak = new_pos_entry.get("algo_loss_streak", 0)
            _new_streak = _prev_streak + 1 if open_r < 0 else 0
            new_pos_entry["algo_loss_streak"] = _new_streak

            _alerted_yellow = new_pos_entry.get("algo_streak_alerted_yellow", False)
            _alerted_orange = new_pos_entry.get("algo_streak_alerted_orange", False)

            if _new_streak >= 5 and not _alerted_orange:
                send_telegram(_algo_loss_streak_alert(sym, open_r, _new_streak, "orange"))
                new_pos_entry["algo_streak_alerted_orange"] = True
            elif _new_streak >= 3 and not _alerted_yellow:
                send_telegram(_algo_loss_streak_alert(sym, open_r, _new_streak, "yellow"))
                new_pos_entry["algo_streak_alerted_yellow"] = True

            if _new_streak == 0:  # Position recovered — reset streak flags
                new_pos_entry["algo_streak_alerted_yellow"] = False
                new_pos_entry["algo_streak_alerted_orange"] = False

            # Single deep-loss alert (open_r ≤ −2R)
            if open_r <= -2.0 and not new_pos_entry.get("algo_deep_loss_alerted", False):
                send_telegram(_algo_deep_loss_alert(sym, open_r))
                new_pos_entry["algo_deep_loss_alerted"] = True
            if open_r > -1.0:  # Significant recovery — allow re-alert if it dips again
                new_pos_entry["algo_deep_loss_alerted"] = False

            # Collect for portfolio-level summary check
            _oversight_score = engine.get("risk_visibility_score", 0)
            algo_oversight_positions.append({
                "symbol": sym, "pos_value": pos_value,
                "oversight_score": _oversight_score, "open_r": open_r,
                "campaign_id": campaign_id,
            })
        # ─────────────────────────────────────────────────────────────────────

        # ── Sizing Leak: one-time alert when position is undersized vs target ─
        # Suppressed during the 48h settle period after a risk raise — positions
        # that were correctly sized for the old (lower) target should not be
        # retroactively flagged because the user raised their risk level.
        _in_post_raise_settle = settle_state.get("active") and settle_state.get("dir") == "up"
        if (not is_algo and original_campaign_risk > 0 and target_risk_usd > 0
                and not new_pos_entry.get("sizing_leak_alerted", False)
                and not _in_post_raise_settle):
            _sizing_ratio = original_campaign_risk / target_risk_usd
            if _sizing_ratio < SIZING_LEAK_THRESHOLD:
                send_telegram(_sizing_leak_alert(sym, setup, _sizing_ratio,
                                                 target_risk_usd, original_campaign_risk))
                new_pos_entry["sizing_leak_alerted"] = True

        # ── Collect row for daily digest ──────────────────────────────────────
        daily_digest_rows.append({
            "sym": sym, "setup": setup, "open_r": open_r,
            "state": new_pos_entry.get("position_state", ""),
            "is_algo": is_algo,
        })

        new_position_state[campaign_id] = new_pos_entry
        
    # ── Phase 4: ALGO Oversight — portfolio-level visibility check ───────────
    if algo_oversight_positions:
        _algo_summary = ec.compute_algo_oversight_summary(algo_oversight_positions, acc_size)
        if _algo_summary["visibility_below_threshold"]:
            _prev_vis_ts = state.get("algo_visibility_alerted_ts", 0)
            if (now_ts - _prev_vis_ts) > 24 * 3600:
                send_telegram(_algo_visibility_alert(
                    _algo_summary["visibility_avg"],
                    _algo_summary["n_positions"],
                ))
                state["algo_visibility_alerted_ts"] = now_ts

    algo_cluster_pct = (total_algo_exposure / acc_size) * 100 if acc_size > 0 else 0
    prev_cluster = state.get("cluster", {})
    prev_cluster_status = prev_cluster.get("status", "green")
    last_cluster_alert = prev_cluster.get("last_alert_ts", 0)
    
    if algo_cluster_pct > ec.ALGO_CLUSTER_CRITICAL_PCT: # 35.0
        cluster_status = "red"
    elif algo_cluster_pct > ec.ALGO_CLUSTER_WARNING_PCT: # 30.0
        if prev_cluster_status == "red" and algo_cluster_pct > 34.0: cluster_status = "red"
        else: cluster_status = "yellow"
    else:
        if prev_cluster_status == "yellow" and algo_cluster_pct > 29.0: cluster_status = "yellow"
        else: cluster_status = "green"
    
    alert_cluster = False
    if cluster_status != prev_cluster_status:
        alert_cluster = True
        last_cluster_alert = now_ts
    elif cluster_status in ["red", "yellow"] and (now_ts - last_cluster_alert) > (6 * 3600):
        alert_cluster = True
        last_cluster_alert = now_ts
        
    if alert_cluster:
        if cluster_status == "red": send_telegram(f"{RTL}🚨 *חריגת אדום באשכול ALGO*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן\n{RTL}פעולה: *חסום כניסות חדשות והפחת חשיפה מהפוזיציות הגדולות ביותר*")
        elif cluster_status == "yellow": send_telegram(f"{RTL}⚠️ *התראת אשכול ALGO*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן\n{RTL}פעולה: *עצור כניסות חדשות עד חזרה לאזור בטוח*")
        elif cluster_status == "green" and prev_cluster.get("status") in ("yellow", "red"): send_telegram(f"{RTL}✅ *אשכול ALGO חזר לאזור תקין*\n{RTL}חשיפת ALGO: `{algo_cluster_pct:.1f}%` מהקרן")
            
    state["positions"] = new_position_state
    state["cluster"] = {"status": cluster_status, "algo_cluster_pct": round(algo_cluster_pct, 2), "updated_at": datetime.utcnow().isoformat(), "last_alert_ts": last_cluster_alert}
    # Checkpoint: persist position alerts before the slower global checks run.
    # A crash in the sections below won't lose per-position alert state.
    save_state(state)

    # ── Daily Digest (US market close, once per day) ──────────────────────────
    try:
        _send_daily_digest_if_due(state, daily_digest_rows, now_ts)
    except Exception as e:
        print(f"Daily digest error: {e}")

    # --- Adaptive Risk Proactive Alert ---
    try:
        current_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
        nav_for_risk = float(account_settings.get("nav", acc_size))
        closed_camps = are.compute_closed_campaigns(df)
        # F1 (Meeting 21/05/2026) — 4-gate on the risk-RAISE path. The
        # risk-monitor proactive alert previously fired "up" recommendations
        # to Telegram without the gate, mismatching the Telegram /portfolio
        # surface after F1 wired the bot. Now all 4 live callers (Telegram x2,
        # dashboard, risk-monitor) share the SAME gated recommendation.
        _gate_ctx_rm = are.build_risk_raise_gate_ctx(
            nav=nav_for_risk, risk_pct=current_risk_pct,
            total_deposited=float(account_settings.get("total_deposited", 0) or 0),
            closed_campaigns=closed_camps,
            nav_source=str(account_settings.get("nav_source", "broker") or "broker"),
            pre_db_realized_pnl_estimate=account_state.pre_db_realized_pnl_estimate(account_settings),
        )
        risk_rec = are.compute_adaptive_risk(closed_camps, current_risk_pct, nav_for_risk,
                                             open_positions=open_positions_for_risk,
                                             risk_raise_gate=_gate_ctx_rm)

        if risk_rec.get("ok") and risk_rec["direction"] != "hold":
            prev_alert = state.get("risk_alert", {})
            last_risk_ts = prev_alert.get("ts", 0)
            last_direction = prev_alert.get("direction", "")

            same_direction_recently = (
                last_direction == risk_rec["direction"]
                and (now_ts - last_risk_ts) < 24 * 3600
            )

            # Settle gate: skip alert for 48h after user confirmed a risk change
            settle = are.get_risk_settle_info()
            in_settle = settle["active"] and settle["dir"] == risk_rec["direction"]
            if in_settle:
                print(f"Adaptive risk: in settle period ({settle['hours_remaining']:.1f}h remaining), skipping alert")

            if not same_direction_recently and not in_settle:
                rec_pct = risk_rec["recommended_risk_pct"]
                curr_pct = risk_rec["current_risk_pct"]
                curr_usd = risk_rec["current_risk_usd"]
                rec_usd = risk_rec["recommended_risk_usd"]
                arrow = "⬆️" if risk_rec["direction"] == "up" else "⬇️⬇️"
                heat  = risk_rec["heat_score"]
                step  = risk_rec["step_type"]
                s9_sc  = risk_rec.get("s9_score",  heat)
                m21_sc = risk_rec.get("m21_score", heat)
                l50_sc = risk_rec.get("l50_score", heat)

                alert_text = (
                    f"{RTL}🎯 *התראת סיכון אדפטיבי*\n"
                    f"{RTL}───────────────\n"
                    f"{RTL}חום מסחר: {risk_rec['heat_color']} `{heat:.0f}/100` | {step}\n"
                    f"{RTL}  ▸ ציון (0-100) לפי טווח: S9(9 עסקאות)=`{s9_sc:.0f}` | M21(21)=`{m21_sc:.0f}` | L50(50)=`{l50_sc:.0f}`\n"
                )
                factors = risk_rec.get("heat_factors", [])
                if factors:
                    alert_text += f"{RTL}\n{RTL}📊 גורמים מרכזיים:\n"
                    for f_line in factors[:3]:
                        alert_text += f"{RTL}  {f_line}\n"
                if rec_pct == curr_pct:
                    alert_text += f"{RTL}\n{RTL}סיכון נוכחי: `{curr_pct:.2f}%` (`${curr_usd:,.0f}` לעסקה) — *ללא שינוי*\n"
                else:
                    alert_text += (
                        f"{RTL}\n{RTL}סיכון נוכחי: `{curr_pct:.2f}%` (`${curr_usd:,.0f}` לעסקה)\n"
                        f"{RTL}{arrow} *סיכון מוצע:* `{rec_pct:.2f}%` (`${rec_usd:,.0f}` לעסקה)\n"
                    )
                improve = risk_rec.get("what_to_improve", [])
                if improve:
                    alert_text += f"{RTL}\n{RTL}🔼 לשיפור:\n"
                    for imp in improve[:3]:
                        alert_text += f"{RTL}  → {imp}\n"
                alert_text += f"\n{RTL}האם לאשר שינוי סיכון?"
                markup = telebot.types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    telebot.types.InlineKeyboardButton(
                        "✅ מאשר שינוי",
                        callback_data=f"risk_confirm|YES|{rec_pct}|{curr_pct}"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "❌ דוחה (חובה: הסבר)",
                        callback_data=f"risk_confirm|NO|{rec_pct}|{curr_pct}"
                    )
                )
                send_telegram_with_keyboard(alert_text, markup)
                state["risk_alert"] = {
                    "direction": risk_rec["direction"],
                    "ts": now_ts,
                    "rec_pct": rec_pct,
                    "curr_pct": curr_pct,
                }
    except Exception as e:
        print(f"Risk alert error: {e}")

    save_state(state)
    _touch_heartbeat("risk_monitor")


def _require_env() -> None:
    """Fail fast at startup when a critical env var is missing."""
    required = {
        "TELEGRAM_BOT_TOKEN": TOKEN,
        "TELEGRAM_ADMIN_ID":  ADMIN_ID,
        "SUPABASE_URL":       SUPABASE_URL,
        "SUPABASE_KEY":       SUPABASE_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(
            f"🚨 Risk Monitor cannot start — missing env vars: {', '.join(missing)}"
        )


_SHUTTING_DOWN = False


def _graceful_shutdown(signum, frame):
    """Save last-known state before container/process exit.

    Triggered by docker compose down (SIGTERM) and Ctrl+C (SIGINT).
    We rely on the most-recent state file written during the main loop; no
    re-computation here to avoid touching Supabase mid-shutdown.
    """
    global _SHUTTING_DOWN
    if _SHUTTING_DOWN:
        return
    _SHUTTING_DOWN = True
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"🛑 Risk Monitor received {sig_name} — checkpoint and exit")
    try:
        if os.path.exists(STATE_FILE):
            state = load_state()
            state["shutdown_at"] = datetime.utcnow().isoformat()
            state["shutdown_signal"] = sig_name
            save_state(state)
    except Exception as e:
        print(f"shutdown checkpoint failed: {e}")
    sys.exit(0)


if __name__ == "__main__":
    _require_env()
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT,  _graceful_shutdown)
    print("🛡️ Sentinel Risk Monitor Active")
    while True:
        try: main()
        except Exception as e: print(f"🚨 Risk Monitor Crash: {e}")
        time.sleep(300)
