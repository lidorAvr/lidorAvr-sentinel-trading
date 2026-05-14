# `user_context` Module — Interface Specification (V1)

> Branch: `claude/review-system-audit-FBZ2h`
> Author: Adaptive UX Team
> Date: 2026-05-14 (afternoon shift)
> Status: V1 spec — implementation guide. No production code written.
> Companion docs: `docs/teams/PERSONAL_ADAPTIVE_DESIGN.md` (4-layer model + 10 touchpoints), `docs/teams/HYPERSCALER_DESIGN_V0.md` (Phase A/B/C/D plan), `docs/teams/MARK_ALIGNMENT_REVIEW.md` (Red Lines).

---

## 1. Purpose

`user_context.py` is the **single module that resolves "what does this user look like?"** for any caller in the Sentinel codebase.

Today the answer is implicit (Mark is the only user; every constant in the codebase is *his* constant). Tomorrow the answer must be per-`user_id`, sourced from a Supabase row, and the day after that it must absorb behavioural learning. The interface this module exposes **must not change** between those days — every caller speaks to it the same way regardless of where the data lives (env var, JSON file, Supabase table, learned model).

### Design goals

| Goal | Mechanism |
|---|---|
| **Phase A can ship without touching this interface again** | All 10 touchpoints call `get_user_constant(name)` from day one; Phase A backs it with `_BUILTIN_DEFAULTS`. |
| **Phase B can swap the backend with zero caller changes** | `get_user_profile()` returns the same `UserProfile` shape whether built from env vars (Phase A) or read from Supabase (Phase B). |
| **Phase C can add behavioural learning without breaking V1 callers** | Layer 3 data lives in new `UserProfile` fields marked `# Phase C`; `get_user_constant()` consults them additively. |
| **Mark's production is byte-identical until he opts in** | `_DEFAULT_PROFILE` mirrors today's hard-coded values; founder gets it implicitly until a Supabase row exists. |
| **Red Lines stay Red Lines for every profile** | A short list of `MODULE_LEVEL_INVARIANTS` lives in code, not in `UserProfile`. No caller can pass `user_id` to influence them. |

### What this module is NOT

- It is **not** a methodology engine. It returns numbers and enums; it does not decide whether to fire an alert.
- It is **not** a permission layer. Admin gating stays in `telegram_bot_secure_runner.py`.
- It is **not** a feature flag system. `MODULE_LEVEL_INVARIANTS` (see §5) are constants, not flags.
- It is **not** a cache for market data. `YF_CACHE` and `sector_cache.json` are unrelated.

---

## 2. Module structure

```
user_context.py
├── # Public surface
├── UserProfile                          (dataclass, frozen)
├── CapitalTier                          (str Enum)
├── MethodologyProfile                   (str Enum — V1 only "minervini_strict")
├── RiskTolerance                        (str Enum)
├── ExperienceLevel                      (str Enum)
├── TimeHorizon                          (str Enum)
├── Universe                             (str Enum)
├── SectorTilt                            (str Enum)
├── PositionCountTarget                  (str Enum)
│
├── get_current_user_id() -> str         (Phase A: from env var DEFAULT_USER_ID)
├── get_user_profile(user_id: str | None = None) -> UserProfile
├── get_user_constant(name: str, user_id: str | None = None) -> Any
├── effective_profile_dump(user_id: str | None = None) -> dict   (debug helper)
│
├── # Module-level
├── _DEFAULT_USER_ID                     ("00000000-0000-0000-0000-000000000001")
├── _DEFAULT_PROFILE                     (UserProfile)
├── _BUILTIN_DEFAULTS                    (dict[str, Any])
├── MODULE_LEVEL_INVARIANTS              (dict[str, Any] — non-overridable)
│
├── # Internals
├── _CACHE                               (dict[str, tuple[UserProfile, float]])
├── _CACHE_TTL_SEC                       (300)
├── _CACHE_LOCK                          (threading.RLock)
└── _load_profile_from_backend(user_id)  (Phase A: returns _DEFAULT_PROFILE)
```

The module deliberately exposes a **tiny** public surface (one dataclass, six enums, four functions). Anything else is private.

---

## 3. `UserProfile` dataclass

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo


class CapitalTier(str, Enum):
    MICRO  = "micro"    # < $25k
    SMALL  = "small"    # $25k - $100k       ← Mark today
    MEDIUM = "medium"   # $100k - $1M
    LARGE  = "large"    # > $1M


class MethodologyProfile(str, Enum):
    MINERVINI_STRICT  = "minervini_strict"   # ← V1 only (Mark's Red Line — see MARK_ALIGNMENT_REVIEW §4 directive #1)
    # Phase B candidates (NOT in V1):
    # MINERVINI_RELAXED = "minervini_relaxed"
    # ONEILL_CLASSIC    = "oneill_classic"
    # SWING_LOW_RISK    = "swing_low_risk"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED     = "balanced"      # ← Mark today
    AGGRESSIVE   = "aggressive"


class ExperienceLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    EXPERIENCED  = "experienced"   # ← Mark today


class TimeHorizon(str, Enum):
    INTRADAY      = "intraday"
    SWING_SHORT   = "swing_short"     # 2-10d
    SWING_MEDIUM  = "swing_medium"    # 10-40d  ← Mark today
    POSITION      = "position"        # 40d+


class Universe(str, Enum):
    US_LARGE_CAP = "us_large_cap"
    US_SMALL_CAP = "us_small_cap"
    US_TOTAL     = "us_total"         # ← Mark today
    ISRAEL       = "israel"
    GLOBAL       = "global"


class SectorTilt(str, Enum):
    TECH_HEAVY    = "tech_heavy"
    DIVERSIFIED   = "diversified"     # ← Mark today
    CYCLICAL      = "cyclical"
    DEFENSIVE     = "defensive"
    CUSTOM        = "custom"


class PositionCountTarget(str, Enum):
    CONCENTRATED = "concentrated"   # 3-5
    BALANCED     = "balanced"       # 6-10    ← Mark today
    DIVERSIFIED  = "diversified"    # 11-20


@dataclass(frozen=True)
class UserProfile:
    # ── Layer 1 — Identity (set once at onboarding, rarely changes) ──────────
    user_id:              str
    display_name:         str                                  = "Mark"
    language:             str                                  = "he"             # ISO 639-1; Phase B may add "en", "ar", "ru", "es"
    timezone:             str                                  = "Asia/Jerusalem" # IANA TZ string
    capital_tier:         CapitalTier                          = CapitalTier.SMALL
    methodology_profile:  MethodologyProfile                   = MethodologyProfile.MINERVINI_STRICT
    risk_tolerance:       RiskTolerance                        = RiskTolerance.BALANCED
    experience_level:     ExperienceLevel                      = ExperienceLevel.EXPERIENCED

    # ── Layer 2 — Trading style (user-explicit, narrows L1 defaults) ─────────
    time_horizon:         TimeHorizon                          = TimeHorizon.SWING_MEDIUM
    universe:             Universe                             = Universe.US_TOTAL
    sector_tilt:          SectorTilt                           = SectorTilt.DIVERSIFIED
    position_count_target: PositionCountTarget                 = PositionCountTarget.BALANCED

    # ── Per-user constant overrides ──────────────────────────────────────────
    # Free-form dict for tunables not yet promoted to a typed field.
    # Resolution order: profile.constants[name] > _BUILTIN_DEFAULTS[name].
    # Cannot override anything in MODULE_LEVEL_INVARIANTS.
    constants:            dict[str, Any]                       = field(default_factory=dict)

    # ── Phase C — Layer 3 (behavioural learning) ──────────────────────────────
    # Out of scope for V1. Placeholder so the dataclass shape is forward-compatible.
    # Phase C: behavior: BehavioralProfile | None = None
    # Phase C: coaching_mute: list[str] = field(default_factory=list)


# Convenience: instance equality used by tests and migration smoke tests.
# All Phase-A profiles must compare equal to _DEFAULT_PROFILE when no override is supplied.
```

### Field-by-field reference

| Field | Type | Default | User-settable? | Allowed values |
|---|---|---|---|---|
| `user_id`              | `str`                  | (required)           | system-set    | UUID string. Mark: `"00000000-0000-0000-0000-000000000001"` |
| `display_name`         | `str`                  | `"Mark"`             | user-settable | Free-form, ≤ 60 chars |
| `language`             | `str` (ISO 639-1)      | `"he"`               | user-settable | V1: `"he"` only. Phase B: `{"he","en","ar","ru","es"}` |
| `timezone`             | `str` (IANA TZ)        | `"Asia/Jerusalem"`   | user-settable | Any valid IANA zone name |
| `capital_tier`         | `CapitalTier`          | `SMALL`              | derived + override | `MICRO`/`SMALL`/`MEDIUM`/`LARGE` |
| `methodology_profile`  | `MethodologyProfile`   | `MINERVINI_STRICT`   | system-set in V1 (per Mark's Red Line) | V1: `MINERVINI_STRICT` only |
| `risk_tolerance`       | `RiskTolerance`        | `BALANCED`           | user-settable | `CONSERVATIVE`/`BALANCED`/`AGGRESSIVE` |
| `experience_level`     | `ExperienceLevel`      | `EXPERIENCED`        | user-settable | `BEGINNER`/`INTERMEDIATE`/`EXPERIENCED` |
| `time_horizon`         | `TimeHorizon`          | `SWING_MEDIUM`       | user-settable | `INTRADAY`/`SWING_SHORT`/`SWING_MEDIUM`/`POSITION` |
| `universe`             | `Universe`             | `US_TOTAL`           | user-settable | enum above |
| `sector_tilt`          | `SectorTilt`           | `DIVERSIFIED`        | user-settable | enum above |
| `position_count_target`| `PositionCountTarget`  | `BALANCED`           | user-settable | enum above |
| `constants`            | `dict[str, Any]`       | `{}`                 | user-settable (advanced) | keys must be in `_BUILTIN_DEFAULTS`; cannot collide with `MODULE_LEVEL_INVARIANTS` |

**Defaults rationale:** every default above produces Mark's **current production behaviour byte-for-byte** when wired through the 10 touchpoints. See §6 migration table.

**Frozen dataclass:** `UserProfile` is `frozen=True` so callers can't mutate it. Profile updates go through `get_user_profile()` → cache invalidation → next read picks up new state. This matches Mark's "no silent changes to Layer 1" anti-pattern (PERSONAL_ADAPTIVE_DESIGN.md Phase 5 #4).

---

## 4. `get_user_constant` — the central function

This function is the **only** way 100+ call sites will look up a tunable value. Every caller calls it exactly the same way. The function does not know or care whether the value comes from env vars, a JSON file, a Supabase row, or a learned model — that's the backend's problem (and the backend is allowed to change between phases).

### Signature

```python
def get_user_constant(name: str, user_id: str | None = None) -> Any:
    """
    Resolve a tunable constant for a user.

    Resolution order:
      1. If `name` is in MODULE_LEVEL_INVARIANTS, return that value
         regardless of user_id (Red Line enforcement — see §5).
      2. Resolve effective user_id (passed in, or get_current_user_id()).
      3. Load the user's profile (cached, see §9).
      4. If profile.constants has `name`, return profile.constants[name].
      5. Otherwise return _BUILTIN_DEFAULTS[name].
      6. If `name` is not in _BUILTIN_DEFAULTS, raise KeyError
         (NOT silent None — fail loud).

    Mutable defaults (lists, dicts) are returned as deep copies so the
    caller cannot accidentally mutate shared state. See open question Q1.
    """
```

### Behavioural rules

| Situation                               | Behaviour                                                                |
|-----------------------------------------|--------------------------------------------------------------------------|
| `name` in `MODULE_LEVEL_INVARIANTS`     | Return invariant. Ignore `user_id`. Log nothing.                        |
| `name` in `profile.constants`           | Return override. (Phase A: never — profile.constants is always `{}`.)    |
| `name` in `_BUILTIN_DEFAULTS`           | Return default. Deep-copied if mutable.                                  |
| `name` in neither                       | `raise KeyError(f"Unknown user-constant: {name!r}")`                     |
| `user_id` is `None` and no env set      | `raise RuntimeError("DEFAULT_USER_ID not configured")` from `get_current_user_id()` |
| `user_id` exists but profile load fails | Log warning, return `_DEFAULT_PROFILE` (fail-safe to today's behaviour). |

### `_BUILTIN_DEFAULTS` — the full list

These are the **current production values mirrored from the codebase**. Source file:line in the right column. Every value below was inspected at HEAD on `claude/review-system-audit-FBZ2h`.

```python
_BUILTIN_DEFAULTS: dict[str, Any] = {
    # ─── Touchpoint 1 — Position card density ───────────────────────────────
    "position_card_density":              "default",  # NEW field; "terse"/"default"/"detailed"
                                                      # source: telegram_formatters.py:58 (single card today)
                                                      # maps to experience_level (terse=experienced,
                                                      # default=intermediate, detailed=beginner)

    # ─── Touchpoint 2 — risk_monitor cooldowns ──────────────────────────────
    "live_alert_repeat_cooldown_sec":     45 * 60,    # source: risk_monitor.py:42  (LIVE_ALERT_REPEAT_COOLDOWN)
    "deviation_cooldown_sec":             3 * 3600,   # source: risk_monitor.py:40  (DEVIATION_COOLDOWN_SEC)
    "giveback_cooldown_sec":              6 * 3600,   # source: risk_monitor.py:41  (GIVEBACK_COOLDOWN_SEC)
    "state_alert_cooldown_runner_sec":    4 * 3600,   # source: risk_monitor.py:49  (STATE_ALERT_COOLDOWN["RUNNER"])
    "state_alert_cooldown_broken_sec":    4 * 3600,   # source: risk_monitor.py:50  (STATE_ALERT_COOLDOWN["BROKEN"])
    "state_alert_cooldown_dead_money_sec":12 * 3600,  # source: risk_monitor.py:51  (STATE_ALERT_COOLDOWN["DEAD_MONEY"])
    "sizing_leak_threshold":              0.65,       # source: risk_monitor.py:45  (SIZING_LEAK_THRESHOLD)
    "profit_checkpoints":                 [2.0, 3.0], # source: risk_monitor.py:39  (PROFIT_CHECKPOINTS)

    # ─── Touchpoint 3 — Risk ladder (per Mark — Sprint 9 plan doc is stale) ─
    "risk_ladder":                        [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00],
                                                      # source: adaptive_risk_engine.py:20 (RISK_LADDER)
                                                      # NOTE: docs/SPRINT_9_PLAN.md:206 lists the old 8-step ladder
                                                      # [0.35..2.50] — that doc is STALE. Code wins.

    # ─── Touchpoint 3b — adaptive_risk drawdown ─────────────────────────────
    "drawdown_trigger_pct":               -8.0,       # source: adaptive_risk_engine.py:27 (DRAWDOWN_TRIGGER_PCT)
    "drawdown_cut_to_pct":                0.40,       # source: adaptive_risk_engine.py:28 (DRAWDOWN_CUT_TO_PCT)
    "drawdown_window_days":               30,         # source: adaptive_risk_engine.py:29 (DRAWDOWN_WINDOW_DAYS)

    # ─── Touchpoint 3c — adaptive_risk settle period ────────────────────────
    "risk_settle_hours":                  48.0,       # source: adaptive_risk_engine.py:33 (RISK_SETTLE_HOURS)

    # ─── Touchpoint 4 — Report scheduler ────────────────────────────────────
    "weekly_report_dow":                  5,          # source: report_scheduler.py:35 (_WEEKLY_WEEKDAY ; 5=Sat, Mon-based)
    "weekly_report_hour_il":              8,          # source: report_scheduler.py:36 (_WEEKLY_HOUR)
    "weekly_report_minute_il":            30,         # source: report_scheduler.py:37 (_WEEKLY_MINUTE)
    "weekly_report_tz":                   "Asia/Jerusalem", # source: report_scheduler.py:15 (ISRAEL_TZ)
    "monthly_report_day":                 1,          # source: report_scheduler.py:38 (_MONTHLY_DAY)
    "monthly_report_hour_il":             8,          # source: report_scheduler.py:39 (_MONTHLY_HOUR)
    "monthly_report_minute_il":           40,         # source: report_scheduler.py:40 (_MONTHLY_MINUTE)

    # ─── Touchpoint 5 — ALGO universe + cluster ─────────────────────────────
    "algo_symbol_limits":                 {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0,
                                           "PLTR": 6.0, "HOOD": 6.0},
                                                      # source: engine_core.py:13 (ALGO_SYMBOL_LIMITS)
    "algo_cluster_warning_pct":           30.0,       # source: engine_core.py:15 (ALGO_CLUSTER_WARNING_PCT)
    "algo_cluster_critical_pct":          35.0,       # source: engine_core.py:16 (ALGO_CLUSTER_CRITICAL_PCT)

    # ─── Touchpoint 6 — Telegram menu ───────────────────────────────────────
    "main_menu_buttons":                  [           # source: telegram_menus.py:11-17 (get_main_menu)
        "📊 מצב תיק",
        "🔬 ניתוח",
        "📚 יומן",
        "❓ עזרה",
        "🛠️ מפתח",
    ],
    "setup_universe":                     ["VCP", "ALGO", "SWING", "EP"],
                                                      # source: telegram_menus.py:8 (_SETUPS)
    "developer_menu_visible":             True,       # source: telegram_menus.py:16
                                                      # Beginner profile → False (Phase B);
                                                      # default mirrors today (visible).

    # ─── Touchpoint 7 — Add-on risk engine ──────────────────────────────────
    "addon_default_size_ratio":           0.40,       # source: addon_risk_engine.py:20 (DEFAULT_SIZE_RATIO)
    "addon_min_open_r_for_addon":         1.0,        # source: addon_risk_engine.py:15 (MIN_OPEN_R_FOR_ADDON)
    "addon_hard_floor_ratio":             -0.25,      # source: addon_risk_engine.py:17 (HARD_FLOOR_RATIO)
    "addon_chase_ext_limit":              0.07,       # source: addon_risk_engine.py:21 (CHASE_EXT_LIMIT)
    "addon_max_size_vs_original":         1.0,        # source: addon_risk_engine.py:18 (MAX_SIZE_VS_ORIGINAL)
    "addon_max_size_vs_current":          0.50,       # source: addon_risk_engine.py:19 (MAX_SIZE_VS_CURRENT)
    "addon_min_cushion_ratio":            0.50,       # source: addon_risk_engine.py:16 (MIN_CUSHION_RATIO)

    # ─── Touchpoint 8 — Daily digest window ─────────────────────────────────
    "daily_digest_utc_hour_start":        21,         # source: risk_monitor.py:43 (DAILY_DIGEST_UTC_HOUR_START)
    "daily_digest_utc_hour_end":          22,         # source: risk_monitor.py:44 (DAILY_DIGEST_UTC_HOUR_END)
    "daily_digest_days_of_week":          [0, 1, 2, 3, 4],  # Mon-Fri; source: risk_monitor.py:136-144 weekday gate

    # ─── Touchpoint 9 — Distribution / accumulation windows ─────────────────
    "dist_window_days":                   12,         # source: engine_core.py:235 (dist_12d)
    "accum_window_days":                  10,         # source: engine_core.py:236 (accum_10d)
    "good_closes_window_days":            10,         # source: engine_core.py:237 (good_closes_10)

    # ─── Touchpoint 10 — Trail buffers ──────────────────────────────────────
    "trail_tight_r_threshold":            8.0,        # source: engine_core.py:1889 (_TRAIL_TIGHT_R_THRESHOLD)
    "trail_loose_r_threshold":            5.0,        # source: engine_core.py:1890 (_TRAIL_LOOSE_R_THRESHOLD)
    "trail_ma_buffer_pct":                0.020,      # source: engine_core.py:~1887 (2% MA buffer)
    "trail_atr_factor":                   0.008,      # source: engine_core.py:~1888 (ATR factor)
}
```

### Why fail-loud on unknown name

A typo in `get_user_constant("daily_digest_utc_hour_strat")` must not silently return `None` and quietly produce a digest at midnight. The whole point of moving constants behind a function is to make typos discoverable. Tests in §8 explicitly assert `KeyError` on unknown names.

---

## 5. Hard-coded constants (Mark's Red Lines)

These are **not user-tunable, ever, regardless of profile**. They live as module-level constants in `user_context.py` so that any caller asking for them gets the truth path — but they are deliberately *outside* `UserProfile` and *outside* `_BUILTIN_DEFAULTS` so they can never be shadowed by a misconfigured profile.

```python
# ── MODULE_LEVEL_INVARIANTS ──────────────────────────────────────────────────
# These are AGENTS.md Red Lines and CLAUDE.md hard constraints. They are NOT
# tunable per user. They are NOT in UserProfile. They cannot be overridden by
# any profile.constants[...] entry. They cannot be reached by passing user_id.
#
# Any PR that tries to move one of these into UserProfile must be rejected
# on sight (Mark's directive #1 in MARK_ALIGNMENT_REVIEW.md §4).
MODULE_LEVEL_INVARIANTS: dict[str, Any] = {
    "mix_algo_into_wr":           False,  # AGENTS.md invariant #8 / Red Line "Mix ALGO into WR".
                                          # is_stat_countable() at engine_core.py:1261 stays a
                                          # pure function with no profile parameter.
    "admin_only_telegram":        True,   # AGENTS.md Red Line "Remove admin protection from Telegram".
                                          # telegram_bot_secure_runner.py guard stays.
    "data_incomplete_in_stats":   False,  # AGENTS.md invariant #8 — DATA_INCOMPLETE excluded from stats.
    "secure_runner_required":     True,   # CLAUDE.md hard constraint: docker-compose.yml runs
                                          # telegram_bot_secure_runner.py, never raw telegram_bot.py.
    "fallback_data_as_truth":     False,  # AGENTS.md invariant #1 — fallback/cached data must be labelled.
}


def get_user_constant(name: str, user_id: str | None = None) -> Any:
    if name in MODULE_LEVEL_INVARIANTS:
        return MODULE_LEVEL_INVARIANTS[name]
    # ... resolution chain continues
```

### Why module-level, not in UserProfile

If `mix_algo_into_wr` were a `UserProfile` field, a misconfigured profile (typo in a migration, malicious user, drift in defaults across Phase A→B→C) could flip it to `True`. By keeping it as a module-level dict that *no profile can shadow*:

- Static analysis can grep for the constant name and prove it's never reassigned.
- Tests can assert `get_user_constant("mix_algo_into_wr", user_id=ANY)` returns `False`.
- Code review can hard-block any PR that proposes moving these into `UserProfile`.

### Caller pattern

```python
# Correct: caller does not need user_id; the answer is universal.
from user_context import get_user_constant
if get_user_constant("mix_algo_into_wr"):
    raise AssertionError("Red Line violation — see AGENTS.md invariant #8")

# Also correct: the user_id is accepted but ignored.
assert get_user_constant("mix_algo_into_wr", user_id="any-uuid") is False
```

---

## 6. Migration path (Phase A → Phase B → Phase C)

The interface defined above must not change between phases. Only the **backend** changes.

### Phase A (Sprint 10) — env-var backend, single user

- `get_current_user_id()` returns `os.getenv("DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000001")`.
- `get_user_profile(user_id)` always returns `_DEFAULT_PROFILE` (regardless of `user_id`).
- `_DEFAULT_PROFILE.constants == {}`.
- Every `get_user_constant("X")` resolves via `_BUILTIN_DEFAULTS["X"]`.
- **All 10 touchpoints in §7 can adopt `get_user_constant()` with no behaviour change.**

```python
# Phase A implementation sketch
_DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000001")

_DEFAULT_PROFILE = UserProfile(
    user_id=_DEFAULT_USER_ID,
    display_name="Mark",
    # all other fields use dataclass defaults (Mark's current values)
)

def _load_profile_from_backend(user_id: str) -> UserProfile:
    # Phase A: always returns the default profile.
    return _DEFAULT_PROFILE
```

**Exit criteria for Phase A:** every touchpoint in §7 has switched to `get_user_constant()`. `pytest -q` passes. Mark's heat score, risk ladder, alert timing, weekly/monthly reports are byte-identical to pre-Phase-A `main`.

### Phase B (Sprint 11-13) — Supabase backend

- A new `user_profiles` Supabase table (schema in HYPERSCALER_DESIGN_V0.md §2).
- `_load_profile_from_backend(user_id)` reads from the table.
- On DB error (timeout, RLS misconfig, missing row), log warning and return `_DEFAULT_PROFILE` (fail-safe).
- Cache layer (§9) absorbs the latency.
- `methodology_profile` enum gains `MINERVINI_RELAXED`, `ONEILL_CLASSIC`, `SWING_LOW_RISK`.
- `language` enum gains `"en"` etc.
- **Callers still call `get_user_constant("X")` the same way.** Nothing in §7 changes.

**Exit criteria for Phase B:** second user (test) can sign up, get a Supabase row, and have their own ladder/cooldowns/menu. Mark's row in the DB has values byte-identical to `_DEFAULT_PROFILE`.

### Phase C (Sprint 14+) — Behavioural learning

- `UserProfile` gains a `behavior: BehavioralProfile` field (currently commented out in §3).
- `get_user_constant()` for keys like `live_alert_repeat_cooldown_sec` consults learned multipliers (see PERSONAL_ADAPTIVE_DESIGN.md Phase 3 #2 for the formula).
- A nightly cron aggregates `user_telemetry` into `user_profile.behavior`.
- **Callers still call `get_user_constant("X")` the same way.** The math behind the answer changes; the interface does not.

---

## 7. 10 touchpoint migration plan

For each touchpoint, the **exact old line** and the **exact new pattern**. Reference: PERSONAL_ADAPTIVE_DESIGN.md Phase 3.

### Touchpoint 1 — `telegram_formatters.fmt_position_card` (density)

```python
# telegram_formatters.py:58  — BEFORE
def fmt_position_card(i, sym, setup, days_held, curr, entry, open_pnl,
                      pos_value, weight_pct, total_pos_profit, total_campaign_r,
                      open_r_val, status, action_short,
                      add_on_count=0, base_price=0, locked_profit=0,
                      giveback_risk=0, capital_risk=0) -> str:
    # ... single dense Hebrew card
```

```python
# telegram_formatters.py  — AFTER
from user_context import get_user_constant

def fmt_position_card(i, sym, setup, days_held, ...,
                      capital_risk=0, density: str | None = None) -> str:
    if density is None:
        density = get_user_constant("position_card_density")
    # density ∈ {"terse", "default", "detailed"} — branches render variants.
    # "default" is byte-identical to today.
```

Backward-compat: signature is preserved (`density` is keyword-only with default `None`); existing tests in `tests/test_telegram_formatters.py` still pass.

### Touchpoint 2 — `risk_monitor.LIVE_ALERT_REPEAT_COOLDOWN`

```python
# risk_monitor.py:42  — BEFORE
LIVE_ALERT_REPEAT_COOLDOWN = 45 * 60  # 45 min
# ... and at line 167:
if (now_ts - last_alert_ts) > LIVE_ALERT_REPEAT_COOLDOWN:
```

```python
# risk_monitor.py  — AFTER
# (LIVE_ALERT_REPEAT_COOLDOWN constant deleted)
from user_context import get_user_constant
# ... and at the same call site:
cooldown_sec = get_user_constant("live_alert_repeat_cooldown_sec")
if (now_ts - last_alert_ts) > cooldown_sec:
```

Also migrate (same file): `DEVIATION_COOLDOWN_SEC`, `GIVEBACK_COOLDOWN_SEC`, `SIZING_LEAK_THRESHOLD`, `PROFIT_CHECKPOINTS`, the three entries in `STATE_ALERT_COOLDOWN`.

### Touchpoint 3 — `adaptive_risk_engine.RISK_LADDER` + `RISK_SETTLE_HOURS`

```python
# adaptive_risk_engine.py:20  — BEFORE
RISK_LADDER = [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]
# adaptive_risk_engine.py:33
RISK_SETTLE_HOURS = 48.0
```

```python
# adaptive_risk_engine.py  — AFTER
from user_context import get_user_constant
# (module-level constants deleted)
# At every call site that used RISK_LADDER:
ladder = get_user_constant("risk_ladder")
# At every call site that used RISK_SETTLE_HOURS:
settle_hours = get_user_constant("risk_settle_hours")
```

Also migrate (same file): `DRAWDOWN_TRIGGER_PCT`, `DRAWDOWN_CUT_TO_PCT`, `DRAWDOWN_WINDOW_DAYS`.

**Test note (Mark's directive #2):** add `tests/test_methodology_profile_default.py` proving WR/Expectancy/PF byte-identical pre/post migration.

### Touchpoint 4 — `report_scheduler` weekly/monthly schedule

```python
# report_scheduler.py:35-40  — BEFORE
_WEEKLY_WEEKDAY = 5
_WEEKLY_HOUR    = 8
_WEEKLY_MINUTE  = 30
_MONTHLY_DAY    = 1
_MONTHLY_HOUR   = 8
_MONTHLY_MINUTE = 40
```

```python
# report_scheduler.py  — AFTER
from user_context import get_user_constant
# (module-level constants deleted)
def _next_weekly_fire(profile_user_id):
    weekday = get_user_constant("weekly_report_dow", profile_user_id)
    hour    = get_user_constant("weekly_report_hour_il", profile_user_id)
    minute  = get_user_constant("weekly_report_minute_il", profile_user_id)
    tz_name = get_user_constant("weekly_report_tz", profile_user_id)
    return _compute_fire_dt(weekday, hour, minute, ZoneInfo(tz_name))
```

**Phase A note:** the scheduler loop still has one user (`get_current_user_id()`); Phase C iterates all active users.

### Touchpoint 5 — `engine_core.ALGO_SYMBOL_LIMITS`

```python
# engine_core.py:13-16  — BEFORE
ALGO_SYMBOL_LIMITS = {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0, "PLTR": 6.0, "HOOD": 6.0}
ALGO_SYMBOLS = set(ALGO_SYMBOL_LIMITS.keys())
ALGO_CLUSTER_WARNING_PCT = 30.0
ALGO_CLUSTER_CRITICAL_PCT = 35.0
```

```python
# engine_core.py  — AFTER
from user_context import get_user_constant

def _algo_symbol_limits() -> dict[str, float]:
    return get_user_constant("algo_symbol_limits")

def _algo_symbols() -> set[str]:
    return set(_algo_symbol_limits().keys())

# At call sites (engine_core.py:309, 1387):
limit = _algo_symbol_limits().get(symbol, 100.0)
```

**Risk:** this touches `evaluate_position_engine`, sector cluster warnings, ALGO classification. Mark's directive #2 requires the methodology-default smoke test pass.

### Touchpoint 6 — `telegram_menus.get_main_menu` + `_SETUPS`

```python
# telegram_menus.py:8-17  — BEFORE
_SETUPS = ["VCP", "ALGO", "SWING", "EP"]

def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(telebot.types.KeyboardButton("📊 מצב תיק"),
               telebot.types.KeyboardButton("🔬 ניתוח"))
    markup.add(telebot.types.KeyboardButton("📚 יומן"),
               telebot.types.KeyboardButton("❓ עזרה"))
    markup.add(telebot.types.KeyboardButton("🛠️ מפתח"))
    return markup
```

```python
# telegram_menus.py  — AFTER
from user_context import get_user_constant

def get_main_menu():
    labels = get_user_constant("main_menu_buttons")
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for chunk in _row_pairs(labels):
        markup.add(*[telebot.types.KeyboardButton(t) for t in chunk])
    return markup

def get_setup_keyboard(t_id):
    setups = get_user_constant("setup_universe")
    # ... iterate setups
```

### Touchpoint 7 — `addon_risk_engine.DEFAULT_SIZE_RATIO` + cohort

```python
# addon_risk_engine.py:15-21  — BEFORE
MIN_OPEN_R_FOR_ADDON  = 1.0
MIN_CUSHION_RATIO     = 0.50
HARD_FLOOR_RATIO      = -0.25
MAX_SIZE_VS_ORIGINAL  = 1.0
MAX_SIZE_VS_CURRENT   = 0.50
DEFAULT_SIZE_RATIO    = 0.40
CHASE_EXT_LIMIT       = 0.07
```

```python
# addon_risk_engine.py  — AFTER
from user_context import get_user_constant
# (module-level constants deleted)
# Helper:
def _addon_constants() -> dict:
    return {
        "min_open_r":   get_user_constant("addon_min_open_r_for_addon"),
        "cushion":      get_user_constant("addon_min_cushion_ratio"),
        "floor":        get_user_constant("addon_hard_floor_ratio"),
        "max_vs_orig":  get_user_constant("addon_max_size_vs_original"),
        "max_vs_curr":  get_user_constant("addon_max_size_vs_current"),
        "size_ratio":   get_user_constant("addon_default_size_ratio"),
        "chase_ext":    get_user_constant("addon_chase_ext_limit"),
    }
```

### Touchpoint 8 — `risk_monitor.DAILY_DIGEST_UTC_HOUR_*`

```python
# risk_monitor.py:43-44  — BEFORE
DAILY_DIGEST_UTC_HOUR_START = 21
DAILY_DIGEST_UTC_HOUR_END   = 22
# ... and at line 424:
if not (DAILY_DIGEST_UTC_HOUR_START <= now_utc.hour < DAILY_DIGEST_UTC_HOUR_END):
```

```python
# risk_monitor.py  — AFTER
from user_context import get_user_constant
# (module-level constants deleted)
start = get_user_constant("daily_digest_utc_hour_start")
end   = get_user_constant("daily_digest_utc_hour_end")
if not (start <= now_utc.hour < end):
    ...
```

**Phase C note:** when behavioural learning ships, Layer 3 may shift `start`/`end` based on `behavior.peak_attention_hour_utc`. Interface doesn't change.

### Touchpoint 9 — `engine_core` distribution / accumulation windows

```python
# engine_core.py:235-237  — BEFORE
# (windows currently inlined; see compute_distribution_days etc.)
# Example call:
dist_12d = compute_distribution_days(symbol, window=12)
accum_10d = compute_accumulation_days(symbol, window=10)
```

```python
# engine_core.py  — AFTER
from user_context import get_user_constant
dist_window = get_user_constant("dist_window_days")
accum_window = get_user_constant("accum_window_days")
dist_12d  = compute_distribution_days(symbol, window=dist_window)
accum_10d = compute_accumulation_days(symbol, window=accum_window)
```

**Risk:** `evaluate_hard_rules` and `score_position` consume these. AGENTS.md Red Line — full regression in `tests/test_calculations_comprehensive.py` required.

### Touchpoint 10 — `engine_core._TRAIL_TIGHT_R_THRESHOLD` / `_TRAIL_LOOSE_R_THRESHOLD`

```python
# engine_core.py:1889-1890  — BEFORE
_TRAIL_TIGHT_R_THRESHOLD = 8.0
_TRAIL_LOOSE_R_THRESHOLD = 5.0
```

```python
# engine_core.py  — AFTER
from user_context import get_user_constant
# (module-level constants deleted)
def _trail_thresholds() -> tuple[float, float]:
    return (
        get_user_constant("trail_tight_r_threshold"),
        get_user_constant("trail_loose_r_threshold"),
    )
```

### Touchpoint migration summary

| # | File | Lines touched | Constants migrated |
|---|---|---|---|
| 1 | `telegram_formatters.py` | 58-89                                | `position_card_density` (new) |
| 2 | `risk_monitor.py`        | 39-51                                | 6 cooldowns + sizing leak + profit checkpoints |
| 3 | `adaptive_risk_engine.py`| 20, 27-29, 33                        | `risk_ladder`, drawdown trio, `risk_settle_hours` |
| 4 | `report_scheduler.py`    | 15, 35-40                            | weekly + monthly schedule (7 values) |
| 5 | `engine_core.py`         | 13-16                                | algo limits + cluster pct |
| 6 | `telegram_menus.py`      | 8, 11-17                             | main menu buttons + setup universe |
| 7 | `addon_risk_engine.py`   | 15-21                                | 7 add-on constants |
| 8 | `risk_monitor.py`        | 43-44 (overlap with #2)              | digest UTC window |
| 9 | `engine_core.py`         | 235-237 (call sites)                 | dist / accum / good-closes windows |
| 10| `engine_core.py`         | 1887-1890                            | trail thresholds + MA buffer + ATR factor |

---

## 8. Test plan

Two test layers: per-module unit tests, and an integration "founder behaviour is byte-identical" test.

### Unit tests — `tests/test_user_context.py`

```python
# 1. Default resolution
def test_get_user_constant_returns_builtin_default_when_no_override():
    assert get_user_constant("live_alert_repeat_cooldown_sec") == 45 * 60
    assert get_user_constant("risk_ladder") == [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]
    assert get_user_constant("addon_default_size_ratio") == 0.40
    assert get_user_constant("risk_settle_hours") == 48.0

# 2. Profile override path (Phase B preview — uses a hand-built profile)
def test_get_user_constant_returns_profile_override_when_set():
    custom = UserProfile(user_id="u-test",
                         constants={"live_alert_repeat_cooldown_sec": 1800})
    monkeypatch_load_profile(custom)
    assert get_user_constant("live_alert_repeat_cooldown_sec", user_id="u-test") == 1800

# 3. Fail-loud on unknown name
def test_get_user_constant_raises_keyerror_on_unknown():
    with pytest.raises(KeyError):
        get_user_constant("not_a_real_constant")

# 4. Module-level invariants cannot be overridden
def test_invariants_cannot_be_overridden_by_profile():
    malicious = UserProfile(user_id="u-malicious",
                            constants={"mix_algo_into_wr": True})
    monkeypatch_load_profile(malicious)
    assert get_user_constant("mix_algo_into_wr", user_id="u-malicious") is False
    assert get_user_constant("admin_only_telegram", user_id="u-malicious") is True
    assert get_user_constant("data_incomplete_in_stats", user_id="u-malicious") is False
    assert get_user_constant("secure_runner_required", user_id="u-malicious") is True

# 5. Mutable default isolation
def test_mutable_default_is_deep_copied():
    ladder_a = get_user_constant("risk_ladder")
    ladder_a.append(99.0)
    ladder_b = get_user_constant("risk_ladder")
    assert ladder_b == [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]
    assert 99.0 not in ladder_b

# 6. Cache TTL behaviour
def test_cache_serves_within_ttl_and_refreshes_after():
    # ... see §9

# 7. Thread-safety smoke test
def test_concurrent_reads_do_not_corrupt_cache():
    # spawn 20 threads, each calling get_user_constant 1000x; no exceptions, all return same value
```

### Per-touchpoint tests

For each touchpoint, two tests:

| Touchpoint | Default-equivalent test | Override test |
|---|---|---|
| 1 — fmt_position_card     | Identical output for default density vs no `density` arg | "terse" density produces shorter string |
| 2 — risk_monitor cooldown | Default 45min: `should_alert()` mirrors today | Override 10min: alert fires 10min after previous |
| 3 — RISK_LADDER           | `compute_adaptive_risk` returns same values as pre-migration | Custom ladder snaps to override |
| 4 — report_scheduler      | Saturday 08:30 Israel TZ fires (today's behaviour)| Sunday 19:00 UTC fires for a Layer-2 user |
| 5 — ALGO_SYMBOL_LIMITS    | `evaluate_position_engine` produces today's caps | Custom dict adds NVDA cap |
| 6 — get_main_menu         | 5 buttons identical to today | Beginner profile shows 3 |
| 7 — addon size ratio      | `validate_addon` math identical to today | Conservative profile shows 0.25 |
| 8 — daily digest window   | 21-22 UTC Mon-Fri fires today | TZ-shifted window fires for non-IL user |
| 9 — dist/accum windows    | `score_position` returns today's values | Custom 5/5 window changes signal |
| 10 — trail thresholds     | RUNNER trip at 5R / tight at 8R today | Conservative trips at 3R / 5R |

### Integration test — `tests/test_byte_identical_founder.py`

The single most important test in this whole migration.

```python
def test_founder_behaviour_is_byte_identical_to_pre_migration():
    """
    Mark's directive #2 (MARK_ALIGNMENT_REVIEW.md §4):
    'All Hyperscaler migrations must include a single-user identity smoke test.
    Same fixture, same numbers, byte-for-byte. If any number moves, the
    migration is rejected.'
    """
    from tests.fixtures.founder_trades_2026_05 import FOUNDER_FIXTURE

    pre  = json.load(open("tests/fixtures/founder_baseline.json"))    # captured pre-migration
    post = run_full_engine(FOUNDER_FIXTURE)                           # uses user_context everywhere

    for key in ["wr", "expectancy", "pf", "total_r", "heat_score",
                "risk_pct_recommendation", "weekly_report_dt",
                "next_digest_dt", "active_alerts_count"]:
        assert pre[key] == post[key], f"Behaviour drift on {key}: {pre[key]} != {post[key]}"
```

If any number moves, the migration is rejected.

---

## 9. Caching & threading

### Cache shape

- **Per-process in-memory cache**, dict keyed by `user_id`, value is `(UserProfile, loaded_at_unix_ts)`.
- **TTL: 5 minutes.** Same number Hyperscaler picked for `methodology_profiles` (HYPERSCALER_DESIGN_V0.md §"Where the data lives").
- **Cache is process-local.** Each Docker container (sentinel-bot, telegram-bot, risk-monitor, dashboard, reporting-service) has its own dict. No Redis in Phase A. This is fine because each container only ever asks about one user (Mark) in Phase A.
- **Phase B cross-process invalidation:** when Phase B writes a profile change via `/settings`, it publishes a tiny Supabase Realtime notification (`channel: user_profiles, payload: {user_id}`); each container's cache subscribes and invalidates that key. Lazy users not signed in to Realtime fall back to TTL.

### Implementation sketch

```python
import threading, time
_CACHE: dict[str, tuple[UserProfile, float]] = {}
_CACHE_TTL_SEC = 300
_CACHE_LOCK = threading.RLock()

def get_user_profile(user_id: str | None = None) -> UserProfile:
    uid = user_id or get_current_user_id()
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(uid)
        if cached and (now - cached[1]) < _CACHE_TTL_SEC:
            return cached[0]
        profile = _load_profile_from_backend(uid)
        _CACHE[uid] = (profile, now)
        return profile


def invalidate_user_cache(user_id: str) -> None:
    """Phase B: called by Supabase Realtime listener on profile change."""
    with _CACHE_LOCK:
        _CACHE.pop(user_id, None)
```

### Thread-safety

`threading.RLock` is used because:

- Multiple threads can hit `risk_monitor.should_alert()` concurrently (one per active symbol).
- `dashboard.py` uses Streamlit's session model which sometimes spawns threads.
- The lock is **reentrant** so `_load_profile_from_backend()` can itself call `get_user_constant()` for some bootstrapping value without deadlocking.

The lock protects cache mutations (`_CACHE[uid] = ...`, `_CACHE.pop`). Reads are also under the lock for consistency (a partial-write read of a dict key is undefined in CPython 3.10 under some race conditions; the lock is cheap).

### What the cache does NOT do

- Does not cache `_BUILTIN_DEFAULTS` — those are module-level constants, already in memory.
- Does not cache `MODULE_LEVEL_INVARIANTS` — same.
- Does not cache the deep-copy of mutable defaults — each call to `get_user_constant("risk_ladder")` produces a fresh copy. See open question Q1.

---

## 10. Open questions

These are the items where reasonable engineers might disagree. Resolve before implementation kickoff (PR-B in the rollout plan).

**Q1 — Deep copy of mutable values.**
Should `get_user_constant("risk_ladder")` return `list.copy()` or the same list every call? Recommendation: **deep copy.** It costs ~200ns per call and protects against the kind of accidental mutation bug that has bitten us before (e.g., a caller doing `ladder = get_user_constant("risk_ladder"); ladder.sort()` would otherwise corrupt the module-level default). Override decision needed from the lead engineer before §8 test #5 lands.

**Q2 — Precedence of `profile.constants` vs methodology profile defaults.**
In Phase B, `methodology_profile=minervini_strict` brings its own defaults from the `methodology_profiles` Supabase table. If the user *also* sets `profile.constants["risk_ladder"] = [...]`, who wins? Recommendation: **explicit `constants` override always wins**, because the user explicitly set it via `/settings` (audit-logged). The methodology profile is the *baseline*; `constants` is the *override*. Document this precedence in `docs/DATA_CONTRACTS.md`.

**Q3 — CLI dump tool for debugging.**
Should Phase A include a CLI: `python -m user_context dump <user_id>` that prints the effective `UserProfile` + every `_BUILTIN_DEFAULTS` value resolved through the cache? Recommendation: **yes, include in Phase A.** Implementation is ~30 lines using `effective_profile_dump()`. Costs nothing, enormously useful for debugging "why is Mark's digest firing at the wrong time?" without spinning up the full stack.

**Q4 — KeyError vs custom exception.**
`get_user_constant("typo")` raises `KeyError`. Should it raise a custom `UnknownUserConstant(name)` instead so tests can catch it without catching every dict-access bug? Recommendation: **custom exception** — also gives a better error message ("Did you mean: live_alert_repeat_cooldown_sec?") via SequenceMatcher.

**Q5 — Concurrent profile updates.**
If user A's `/settings` runs at the same moment as risk_monitor's read in another container, who wins? Recommendation: **DB wins (Phase B+), cache eventually consistent.** TTL of 5min is acceptable lag for a settings change; the user gets immediate feedback in the dashboard, and the risk monitor picks up the new value within 5 minutes. Tighter consistency is a Phase C concern (Realtime invalidation, see §9).

**Q6 — Where does `MODULE_LEVEL_INVARIANTS` actually get enforced?**
The invariant `mix_algo_into_wr=False` is enforced today by `engine_core.is_stat_countable()` returning False for ALGO. Putting it in `MODULE_LEVEL_INVARIANTS` is **belt-and-suspenders** — if some future PR proposes a sketchy `is_stat_countable(bucket, profile)` change, the test in §8 catches it. Recommendation: keep the invariant + keep the existing pure function, and **add a test that asserts the invariant matches `is_stat_countable("ALGO_OBSERVED")`'s return value.** Two checks, one truth.

**Q7 — Phase A scope: env-var fallback for `language` / `timezone`?**
Should Phase A allow `LANGUAGE=he`, `TZ=Asia/Jerusalem` env vars to override `_DEFAULT_PROFILE`? Recommendation: **no, defer to Phase B.** Phase A is "single user, byte-identical to today" — env-var overrides invite drift between containers (one container reads `TZ` from env, another doesn't). Phase B reads everything from Supabase and the question disappears.

---

## Appendix A — Source-of-truth references

All paths absolute under `/home/user/lidorAvr-sentinel-trading`.

### Touchpoint constants in production code

| Touchpoint | File | Lines |
|---|---|---|
| 1  | `telegram_formatters.py`    | 58-89 (`fmt_position_card`) |
| 2  | `risk_monitor.py`           | 39-51 (cooldowns, profit checkpoints, sizing leak, state cooldowns) |
| 3  | `adaptive_risk_engine.py`   | 20 (RISK_LADDER), 27-29 (drawdown trio), 33 (RISK_SETTLE_HOURS) |
| 4  | `report_scheduler.py`       | 15 (ISRAEL_TZ), 35-40 (_WEEKLY_* / _MONTHLY_*) |
| 5  | `engine_core.py`            | 13-16 (ALGO_SYMBOL_LIMITS, ALGO_CLUSTER_*) |
| 6  | `telegram_menus.py`         | 8 (_SETUPS), 11-17 (get_main_menu) |
| 7  | `addon_risk_engine.py`      | 15-21 (MIN_OPEN_R_FOR_ADDON, MIN_CUSHION_RATIO, HARD_FLOOR_RATIO, MAX_SIZE_VS_ORIGINAL, MAX_SIZE_VS_CURRENT, DEFAULT_SIZE_RATIO, CHASE_EXT_LIMIT) |
| 8  | `risk_monitor.py`           | 43-44 (DAILY_DIGEST_UTC_HOUR_*), 136-144 (US market weekday gate) |
| 9  | `engine_core.py`            | 235-237 (dist_12d, accum_10d, good_closes_10) |
| 10 | `engine_core.py`            | 1887-1890 (_TRAIL_*_R_THRESHOLD, MA buffer pct, ATR factor) |

### Red Line sources

| Invariant | Source |
|---|---|
| `mix_algo_into_wr`         | `AGENTS.md:16` (invariant #8), `AGENTS.md:72` (Red Line "Mix ALGO into WR"), `engine_core.py:1261` (`is_stat_countable`) |
| `admin_only_telegram`      | `AGENTS.md:11` (invariant #3), `AGENTS.md:65` (Red Line), `telegram_bot_secure_runner.py:30, 42-44` |
| `data_incomplete_in_stats` | `AGENTS.md:16` (invariant #8), `engine_core.py:1261` |
| `secure_runner_required`   | `CLAUDE.md:21-24` (hard constraints), `docker-compose.yml` (telegram-bot service command) |
| `fallback_data_as_truth`   | `AGENTS.md:9` (invariant #1), `CLAUDE.md` ("clear about fallback/cached data") |

### Companion docs consumed

- `/home/user/lidorAvr-sentinel-trading/docs/teams/PERSONAL_ADAPTIVE_DESIGN.md` — 4-layer model + 10 touchpoints (morning shift)
- `/home/user/lidorAvr-sentinel-trading/docs/teams/HYPERSCALER_DESIGN_V0.md` — Phase A/B/C/D plan + `user_context` reference
- `/home/user/lidorAvr-sentinel-trading/docs/teams/MARK_ALIGNMENT_REVIEW.md` — Mark's hard constants list + Sprint 10 directives
- `/home/user/lidorAvr-sentinel-trading/docs/teams/DAY1_MIDDAY_STANDUP.md` — cross-team conflict resolution log

### Sprint 10 directives this spec satisfies

- Mark's directive #1 (MARK_ALIGNMENT_REVIEW.md §4): `mix_algo_into_wr` is a Python module-level constant, **never a profile field** — see §5.
- Mark's directive #2: byte-identical single-user smoke test — see §8 integration test.
- DAY1 standup, Sprint 10 P2: "UX `user_context` module skeleton (shim layer only)" — this spec is the design input for that PR.

---

## Appendix B — Implementation rollout (sub-PRs)

This spec defines the **interface**. The actual rollout is 11 sub-PRs over Sprint 10-11:

| PR | Scope | Estimated LOC | Risk |
|---|---|---|---|
| PR-B0 | `user_context.py` skeleton + `_BUILTIN_DEFAULTS` + `MODULE_LEVEL_INVARIANTS` + unit tests | ~250 | Low |
| PR-B1 | Touchpoint 2 (risk_monitor cooldowns) + tests | ~120 | Medium |
| PR-B2 | Touchpoint 3 (RISK_LADDER + RISK_SETTLE_HOURS + drawdown trio) + tests | ~150 | High — math |
| PR-B3 | Touchpoint 5 (ALGO_SYMBOL_LIMITS) + tests | ~180 | High — touches scoring |
| PR-B4 | Touchpoint 8 (daily digest window) + tests | ~80  | Low |
| PR-B5 | Touchpoint 7 (addon defaults) + tests | ~120 | Medium |
| PR-B6 | Touchpoint 4 (report_scheduler weekly/monthly) + tests | ~150 | Medium |
| PR-B7 | Touchpoint 1 (fmt_position_card density) + tests | ~100 | Low |
| PR-B8 | Touchpoint 6 (telegram menus) + tests | ~80  | Low |
| PR-B9 | Touchpoint 9 (dist/accum windows) + tests | ~120 | High — methodology |
| PR-B10| Touchpoint 10 (trail thresholds) + tests | ~80  | Medium |

**Total estimated effort:** ~1430 LOC of new code, ~14 dev-days. Every PR is independently revertable. The byte-identical smoke test (§8) runs in CI on every PR.

**End of spec.**
