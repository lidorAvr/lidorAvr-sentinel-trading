"""
Phase A — single-user context resolver + tunable-constant source of truth.

In Phase A, every code path has implicit "current user = Mark". This module
centralizes that assumption so Phase B/C can swap the resolution strategy
(per-request context from webhook handler, per-worker context from job
metadata) without touching every call site.

Scope (per docs/teams/HYPERSCALER_PHASE_A_SPEC.md §4.1 + §4.2 and
docs/teams/USER_CONTEXT_INTERFACE_SPEC.md, narrowed by DEC-20260515-002):

  * Phase A is single-user. `get_current_user_id()` is env-var driven and
    falls back to a sentinel UUID with a single logged warning. It never
    returns None and never raises.
  * `MethodologyProfile` has exactly ONE value: `MINERVINI_STRICT`
    (DEC-20260515-002 — the 4-profile model is deferred; a full custom
    profile is permanently rejected).
  * The AGENTS.md / CLAUDE.md Red Lines (`mix_algo_into_wr=False`,
    admin-only Telegram, no DATA_INCOMPLETE in stats, secure_runner
    required, no fallback-as-truth) are MODULE-LEVEL constants in
    `MODULE_LEVEL_INVARIANTS`. They are NOT `UserProfile` fields, NOT in
    `_BUILTIN_DEFAULTS`, and CANNOT be overridden by any profile or by
    passing a `user_id`. Any PR that tries to move one of these into
    `UserProfile` must be rejected on sight (Mark's directive #1).
  * `_BUILTIN_DEFAULTS` mirrors the *current production constants exactly*.
    Every value is cited file:line in a comment. Phase A does NOT yet wire
    the 10 touchpoints to call `get_user_constant()` — that is PR-B1..B10
    (a separate, behaviour-preserving rollout). This module is a leaf with
    no callers in Phase A apart from `bot_core` loading `DEFAULT_USER_ID`.

Hard contract:
  get_current_user_id() ALWAYS returns a valid UUID string. It never returns
  None, never raises. If DEFAULT_USER_ID env var is missing, it logs a single
  warning at first call and returns SENTINEL_USER_ID.
"""
from __future__ import annotations

import copy
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Sentinel UUID ─────────────────────────────────────────────────────────────
# Used in exactly two places (kept in sync by tests/test_user_context.py):
#   1. get_current_user_id() fallback (below).
#   2. migrations/003_*.sql and 004_*.sql DEFAULT clause (same literal).
SENTINEL_USER_ID = "00000000-0000-0000-0000-000000000001"

# Back-compat alias used by the interface spec (§2) — same value.
_DEFAULT_USER_ID = SENTINEL_USER_ID

_warned = False  # one-shot warning latch


def get_current_user_id() -> str:
    """Return the active user_id for the current execution context.

    Phase A: env-var driven, process-wide.
    Phase B: still env-var driven but reads from DB-backed account_profiles.
    Phase C: per-request context from telegram_links / webhook handler.

    Never None, never raises. If DEFAULT_USER_ID is unset, logs a single
    startup warning to stderr and returns SENTINEL_USER_ID — production must
    still run byte-identically if the env var is missed in a deploy.
    """
    global _warned
    val = os.environ.get("DEFAULT_USER_ID", "").strip()
    if val:
        return val
    if not _warned:
        print(
            "[user_context] DEFAULT_USER_ID unset — using sentinel UUID. "
            "Phase A is single-user; this is expected on dev boxes.",
            file=sys.stderr,
            flush=True,
        )
        _warned = True
    return SENTINEL_USER_ID


# ── Layer 1 / Layer 2 enums ───────────────────────────────────────────────────


class CapitalTier(str, Enum):
    MICRO = "micro"      # < $25k
    SMALL = "small"      # $25k - $100k        ← Mark today
    MEDIUM = "medium"    # $100k - $1M
    LARGE = "large"      # > $1M


class MethodologyProfile(str, Enum):
    # DEC-20260515-002: single, hardened, validated profile for ALL users.
    # The 4-profile model (minervini_relaxed / oneill_classic /
    # swing_low_risk) is deferred to Sprint 13; a full custom profile is
    # permanently rejected. V1 has exactly ONE enum value.
    MINERVINI_STRICT = "minervini_strict"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"        # ← Mark today
    AGGRESSIVE = "aggressive"


class ExperienceLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERIENCED = "experienced"  # ← Mark today


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SWING_SHORT = "swing_short"      # 2-10d
    SWING_MEDIUM = "swing_medium"    # 10-40d  ← Mark today
    POSITION = "position"            # 40d+


class Universe(str, Enum):
    US_LARGE_CAP = "us_large_cap"
    US_SMALL_CAP = "us_small_cap"
    US_TOTAL = "us_total"            # ← Mark today
    ISRAEL = "israel"
    GLOBAL = "global"


class SectorTilt(str, Enum):
    TECH_HEAVY = "tech_heavy"
    DIVERSIFIED = "diversified"      # ← Mark today
    CYCLICAL = "cyclical"
    DEFENSIVE = "defensive"
    CUSTOM = "custom"


class PositionCountTarget(str, Enum):
    CONCENTRATED = "concentrated"   # 3-5
    BALANCED = "balanced"           # 6-10    ← Mark today
    DIVERSIFIED = "diversified"     # 11-20


@dataclass(frozen=True)
class UserProfile:
    # ── Layer 1 — Identity (set once at onboarding, rarely changes) ──────────
    user_id: str
    display_name: str = "Mark"
    language: str = "he"                       # ISO 639-1; DEC-20260515-003: he-only for V1
    timezone: str = "Asia/Jerusalem"           # IANA TZ string
    capital_tier: CapitalTier = CapitalTier.SMALL
    methodology_profile: MethodologyProfile = MethodologyProfile.MINERVINI_STRICT
    risk_tolerance: RiskTolerance = RiskTolerance.BALANCED
    experience_level: ExperienceLevel = ExperienceLevel.EXPERIENCED

    # ── Layer 2 — Trading style (user-explicit, narrows L1 defaults) ─────────
    time_horizon: TimeHorizon = TimeHorizon.SWING_MEDIUM
    universe: Universe = Universe.US_TOTAL
    sector_tilt: SectorTilt = SectorTilt.DIVERSIFIED
    position_count_target: PositionCountTarget = PositionCountTarget.BALANCED

    # ── Per-user constant overrides ──────────────────────────────────────────
    # Free-form dict for tunables not yet promoted to a typed field.
    # Resolution order: profile.constants[name] > _BUILTIN_DEFAULTS[name].
    # Cannot override anything in MODULE_LEVEL_INVARIANTS.
    # Phase A: ALWAYS {} (single user, no overrides — DEC-20260515-002).
    constants: dict[str, Any] = field(default_factory=dict)

    # ── Phase C — Layer 3 (behavioural learning) ─────────────────────────────
    # Out of scope for V1. Placeholder so the dataclass shape is
    # forward-compatible:
    #   Phase C: behavior: BehavioralProfile | None = None
    #   Phase C: coaching_mute: list[str] = field(default_factory=list)


# ── MODULE_LEVEL_INVARIANTS — Mark's Red Lines ────────────────────────────────
# These are AGENTS.md Red Lines and CLAUDE.md hard constraints. They are NOT
# tunable per user. They are NOT in UserProfile. They cannot be overridden by
# any profile.constants[...] entry. They cannot be reached by passing user_id.
#
# Any PR that tries to move one of these into UserProfile must be rejected on
# sight (Mark's directive #1 in MARK_ALIGNMENT_REVIEW.md §4 / DEC-20260515-002).
MODULE_LEVEL_INVARIANTS: dict[str, Any] = {
    "mix_algo_into_wr":          False,  # AGENTS.md:16 invariant #8 / AGENTS.md:72 Red Line.
                                         # is_stat_countable() at engine_core.py stays a pure
                                         # function with no profile parameter.
    "admin_only_telegram":       True,   # AGENTS.md:11 invariant #3 / AGENTS.md:65 Red Line.
                                         # telegram_bot_secure_runner.py guard stays.
    "data_incomplete_in_stats":  False,  # AGENTS.md:16 invariant #8 — DATA_INCOMPLETE excluded.
    "secure_runner_required":    True,   # CLAUDE.md hard constraint: docker-compose.yml runs
                                         # telegram_bot_secure_runner.py, never raw telegram_bot.py.
    "fallback_data_as_truth":    False,  # AGENTS.md:9 invariant #1 — fallback/cached labelled.
}


# ── _BUILTIN_DEFAULTS — current production values, mirrored exactly ───────────
# Every value below was inspected at HEAD. The right-hand comment cites the
# exact source file:line so drift is auditable. Phase A does NOT yet route the
# touchpoints through this dict (that is PR-B1..B10); it exists so the leaf
# module + its tests can prove the values match production.
_BUILTIN_DEFAULTS: dict[str, Any] = {
    # ─── Touchpoint 1 — Position card density ───────────────────────────────
    "position_card_density":               "default",   # NEW field; "terse"/"default"/"detailed".
                                                         # source: telegram_formatters.py:58
                                                         # (fmt_position_card — single card today)

    # ─── Touchpoint 2 — risk_monitor cooldowns ──────────────────────────────
    "live_alert_repeat_cooldown_sec":      45 * 60,      # source: risk_monitor.py:43 (LIVE_ALERT_REPEAT_COOLDOWN)
    "deviation_cooldown_sec":              3 * 3600,     # source: risk_monitor.py:41 (DEVIATION_COOLDOWN_SEC)
    "giveback_cooldown_sec":               6 * 3600,     # source: risk_monitor.py:42 (GIVEBACK_COOLDOWN_SEC)
    "state_alert_cooldown_runner_sec":     4 * 3600,     # source: risk_monitor.py:50 (STATE_ALERT_COOLDOWN["RUNNER"])
    "state_alert_cooldown_broken_sec":     4 * 3600,     # source: risk_monitor.py:51 (STATE_ALERT_COOLDOWN["BROKEN"])
    "state_alert_cooldown_dead_money_sec": 12 * 3600,    # source: risk_monitor.py:52 (STATE_ALERT_COOLDOWN["DEAD_MONEY"])
    "sizing_leak_threshold":               0.65,         # source: risk_monitor.py:46 (SIZING_LEAK_THRESHOLD)
    "profit_checkpoints":                  [2.0, 3.0],   # source: risk_monitor.py:40 (PROFIT_CHECKPOINTS)

    # ─── Touchpoint 3 — Risk ladder (code wins; SPRINT_9_PLAN.md is stale) ───
    "risk_ladder":                         [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00],
                                                         # source: adaptive_risk_engine.py:20 (RISK_LADDER)

    # ─── Touchpoint 3b — adaptive_risk drawdown ─────────────────────────────
    "drawdown_trigger_pct":                -8.0,         # source: adaptive_risk_engine.py:27 (DRAWDOWN_TRIGGER_PCT)
    "drawdown_cut_to_pct":                 0.40,         # source: adaptive_risk_engine.py:28 (DRAWDOWN_CUT_TO_PCT)
    "drawdown_window_days":                30,           # source: adaptive_risk_engine.py:29 (DRAWDOWN_WINDOW_DAYS)

    # ─── Touchpoint 3c — adaptive_risk settle period ────────────────────────
    "risk_settle_hours":                   48.0,         # source: adaptive_risk_engine.py:33 (RISK_SETTLE_HOURS)

    # ─── Touchpoint 4 — Report scheduler ────────────────────────────────────
    "weekly_report_dow":                   5,            # source: report_scheduler.py:35 (_WEEKLY_WEEKDAY; 5=Sat, Mon-based)
    "weekly_report_hour_il":               8,            # source: report_scheduler.py:36 (_WEEKLY_HOUR)
    "weekly_report_minute_il":             30,           # source: report_scheduler.py:37 (_WEEKLY_MINUTE)
    "weekly_report_tz":                    "Asia/Jerusalem",  # source: report_scheduler.py:15 (ISRAEL_TZ)
    "monthly_report_day":                  1,            # source: report_scheduler.py:38 (_MONTHLY_DAY)
    "monthly_report_hour_il":              8,            # source: report_scheduler.py:39 (_MONTHLY_HOUR)
    "monthly_report_minute_il":            40,           # source: report_scheduler.py:40 (_MONTHLY_MINUTE)

    # ─── Touchpoint 5 — ALGO universe + cluster ─────────────────────────────
    "algo_symbol_limits":                  {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0,
                                            "PLTR": 6.0, "HOOD": 6.0},
                                                         # source: engine_core.py:13 (ALGO_SYMBOL_LIMITS)
    "algo_cluster_warning_pct":            30.0,         # source: engine_core.py:15 (ALGO_CLUSTER_WARNING_PCT)
    "algo_cluster_critical_pct":           35.0,         # source: engine_core.py:16 (ALGO_CLUSTER_CRITICAL_PCT)

    # ─── Touchpoint 6 — Telegram menu ───────────────────────────────────────
    "main_menu_buttons":                   [             # source: telegram_menus.py:14-16 (get_main_menu)
        "📊 מצב תיק",
        "🔬 ניתוח",
        "📚 יומן",
        "❓ עזרה",
        "🛠️ מפתח",
    ],
    "setup_universe":                      ["VCP", "ALGO", "SWING", "EP"],
                                                         # source: telegram_menus.py:8 (_SETUPS)
    "developer_menu_visible":              True,         # source: telegram_menus.py:16 (🛠️ מפתח always added today)

    # ─── Touchpoint 7 — Add-on risk engine ──────────────────────────────────
    "addon_default_size_ratio":            0.40,         # source: addon_risk_engine.py:20 (DEFAULT_SIZE_RATIO)
    "addon_min_open_r_for_addon":          1.0,          # source: addon_risk_engine.py:15 (MIN_OPEN_R_FOR_ADDON)
    "addon_hard_floor_ratio":              -0.25,        # source: addon_risk_engine.py:17 (HARD_FLOOR_RATIO)
    "addon_chase_ext_limit":               0.07,         # source: addon_risk_engine.py:21 (CHASE_EXT_LIMIT)
    "addon_max_size_vs_original":          1.0,          # source: addon_risk_engine.py:18 (MAX_SIZE_VS_ORIGINAL)
    "addon_max_size_vs_current":           0.50,         # source: addon_risk_engine.py:19 (MAX_SIZE_VS_CURRENT)
    "addon_min_cushion_ratio":             0.50,         # source: addon_risk_engine.py:16 (MIN_CUSHION_RATIO)

    # ─── Touchpoint 8 — Daily digest window ─────────────────────────────────
    "daily_digest_utc_hour_start":         21,           # source: risk_monitor.py:44 (DAILY_DIGEST_UTC_HOUR_START)
    "daily_digest_utc_hour_end":           22,           # source: risk_monitor.py:45 (DAILY_DIGEST_UTC_HOUR_END)
    "daily_digest_days_of_week":           [0, 1, 2, 3, 4],  # Mon-Fri; source: risk_monitor.py weekday gate

    # ─── Touchpoint 9 — Distribution / accumulation windows ─────────────────
    "dist_window_days":                    12,           # source: engine_core.py:236 (dist_12d)
    "accum_window_days":                   10,           # source: engine_core.py:237 (accum_10d)
    "good_closes_window_days":             10,           # source: engine_core.py:238 (good_closes_10)

    # ─── Touchpoint 10 — Trail buffers ──────────────────────────────────────
    "trail_tight_r_threshold":             8.0,          # source: engine_core.py:1889 (_TRAIL_TIGHT_R_THRESHOLD)
    "trail_loose_r_threshold":             5.0,          # source: engine_core.py:1890 (_TRAIL_LOOSE_R_THRESHOLD)
    "trail_ma_buffer_pct":                 0.02,         # source: engine_core.py:1887 (_TRAIL_MA_BUFFER_PCT)
    "trail_atr_factor":                    0.008,        # source: engine_core.py:1888 (_TRAIL_ATR_BUFFER_FACTOR)
}


# Phase A default profile — every field uses Mark's current production value.
# All Phase-A profiles compare equal to this (single user, no overrides).
_DEFAULT_PROFILE = UserProfile(
    user_id=SENTINEL_USER_ID,
    display_name="Mark",
    # all other fields use the dataclass defaults (Mark's current values)
)


# ── Cache (process-local) ─────────────────────────────────────────────────────
_CACHE: dict[str, tuple[UserProfile, float]] = {}
_CACHE_TTL_SEC = 300
_CACHE_LOCK = threading.RLock()


def _load_profile_from_backend(user_id: str) -> UserProfile:
    """Phase A backend: always returns the single default profile.

    Phase B swaps this body to read the `user_profiles` Supabase table.
    The public interface (get_user_profile / get_user_constant) does not
    change between phases.
    """
    return _DEFAULT_PROFILE


def get_user_profile(user_id: str | None = None) -> UserProfile:
    """Return the (cached) UserProfile for a user.

    Phase A: always the default profile regardless of user_id. Cached with a
    5-minute TTL behind a reentrant lock so concurrent risk_monitor /
    dashboard threads cannot corrupt the cache.
    """
    uid = user_id or get_current_user_id()
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(uid)
        if cached and (now - cached[1]) < _CACHE_TTL_SEC:
            return cached[0]
        profile = _load_profile_from_backend(uid)
        _CACHE[uid] = (profile, now)
        return profile


def invalidate_user_cache(user_id: str | None = None) -> None:
    """Drop a user's cached profile (Phase B: called by a Realtime listener).

    Passing None clears the entire cache (used by tests for isolation).
    """
    with _CACHE_LOCK:
        if user_id is None:
            _CACHE.clear()
        else:
            _CACHE.pop(user_id, None)


def get_user_constant(name: str, user_id: str | None = None) -> Any:
    """Resolve a tunable constant for a user.

    Resolution order:
      1. If `name` is in MODULE_LEVEL_INVARIANTS, return that value
         regardless of user_id (Red Line enforcement — cannot be shadowed).
      2. Resolve effective user_id (passed in, or get_current_user_id()).
      3. Load the user's profile (cached).
      4. If profile.constants has `name`, return that override (deep-copied
         if mutable). Phase A: never — profile.constants is always {}.
      5. Otherwise return _BUILTIN_DEFAULTS[name] (deep-copied if mutable).
      6. If `name` is in neither, raise KeyError (NOT silent None — fail
         loud so typos are discoverable).
    """
    if name in MODULE_LEVEL_INVARIANTS:
        return MODULE_LEVEL_INVARIANTS[name]

    profile = get_user_profile(user_id)

    if name in profile.constants:
        return copy.deepcopy(profile.constants[name])

    if name in _BUILTIN_DEFAULTS:
        return copy.deepcopy(_BUILTIN_DEFAULTS[name])

    raise KeyError(f"Unknown user-constant: {name!r}")


def effective_profile_dump(user_id: str | None = None) -> dict[str, Any]:
    """Debug helper: the resolved profile + every constant a caller can read.

    Useful for answering "why is Mark's digest firing at the wrong time?"
    without spinning up the full stack.
    """
    profile = get_user_profile(user_id)
    profile_view: dict[str, Any] = {}
    for fname, val in profile.__dict__.items():
        profile_view[fname] = val.value if isinstance(val, Enum) else val

    constants_view: dict[str, Any] = {}
    for key in sorted(_BUILTIN_DEFAULTS):
        constants_view[key] = get_user_constant(key, user_id=user_id)

    return {
        "user_id": profile.user_id,
        "profile": profile_view,
        "invariants": dict(MODULE_LEVEL_INVARIANTS),
        "constants": constants_view,
    }
