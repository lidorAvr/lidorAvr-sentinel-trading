# Adaptive UX Team — "Glove" Design (V0)

> Branch: `claude/review-system-audit-FBZ2h`
> Author: Adaptive UX Team
> Date: 2026-05-14
> Status: V0 design — read-only investigation, no production code changed.

---

## Executive summary

Sentinel today is a single-user, single-locale, single-methodology system with
*one* truly adaptive surface — the heat-score → risk-ladder loop in
`adaptive_risk_engine.py`. Everything else (universe caps, alert cadences,
report schedule, message density, methodology thresholds, language) is hard-coded
for "the average Minervini swing trader" and that trader happens to be the founder.

The founder said: "the system must adapt personally to the user — like a glove
to a hand." Our job, sitting between Hyperscaler (multi-tenancy) and Marketing
(persona segmentation), is to design the model that makes per-user adaptiveness
real without breaking the production behaviour that already serves user #1.

We recommend a **four-layer model**:

1. **Identity profile** — explicit, once at onboarding, rarely changes.
2. **Trading style** — explicit, user-selected, system enforces internal consistency.
3. **Behavioural learning** — implicit, observed silently, used to throttle/shape.
4. **Methodology coaching** — system nudges the user back toward *their own* stated goals.

The change is **additive** — every existing constant becomes a function:
`get_user_constant(user_id, "live_alert_cooldown") -> int`. Layer 0 (current
hard-coded values) becomes the default profile and *cannot* be removed until
the founder's profile has been migrated and verified. No Red Line from
`AGENTS.md` is weakened by any profile (ALGO in WR, admin gate, anti-spam dedup
all stay absolute).

Three deliverables make this real in code:
- a `user_profile` table (Supabase) with a JSON column per layer;
- a thin `user_context.py` module that returns a frozen dict per request;
- backward-compatibility shim: when `TELEGRAM_ADMIN_ID` resolves to user #1
  and `user_profile` is empty, defaults match today's behaviour byte-for-byte.

---

## Phase 1 — Current personalization audit

### 1.1 What IS adaptive today

| Surface | Mechanism | File:line | Per-user data |
|---|---|---|---|
| Risk percentage | 7-step ladder driven by S9/M21/L50 heat score | `adaptive_risk_engine.py:20` (`RISK_LADDER`), `:408` (`compute_adaptive_risk`) | `sentinel_config.json` `risk_pct_input` |
| Drawdown auto-cut | Force-cut to 0.40% when 30d PnL ≤ -8% NAV | `adaptive_risk_engine.py:222` (`drawdown_auto_cut_recommendation`) | derived from trades |
| Risk-change settle | 48h hold after a confirmed risk change | `adaptive_risk_engine.py:33` (`RISK_SETTLE_HOURS`), `:73` (`get_risk_settle_info`) | `sentinel_config.json` `risk_changed_ts` |
| NAV / target risk USD | Pulled from IBKR; falls back to deposited | `account_state.py:39` | `sentinel_config.json` `nav`, `total_deposited` |
| Adherence stats | "Did the user actually follow the recommendation?" | `adaptive_risk_engine.py:602` (`mark_adherence`), `:625` (`compute_adherence_stats`) | `risk_recommendations.json` |
| Risk journal | Per-user historical log of risk decisions | `adaptive_risk_engine.py:95` (`log_risk_journal`) | `risk_journal.json` (500-cap FIFO) |
| Admin gate | `TELEGRAM_ADMIN_ID` per-user lock | `bot_core.py:17`, `telegram_bot_secure_runner.py:30` | env var |
| Output language/tone | Hebrew-first, RTL, opinionated brevity | `telegram_formatters.py` (RTL constant + Hebrew strings throughout) | implicit |
| Position card layout | Compact format with optional fields | `telegram_formatters.py:58` (`fmt_position_card`) | implicit |

### 1.2 What is NOT adaptive (hard-coded for the "average Minervini trader")

| Surface | Today's value | Where | Why this hurts a different user |
|---|---|---|---|
| Position-count cap | **Does not exist** — no cap anywhere in code | (searched all `.py`) | Aggressive concentrators (3-5 names) and diversifiers (11-20) get the same nudges |
| ALGO symbol universe | `{QQQ, TSLA, JPM, PLTR, HOOD}` fixed | `engine_core.py:13` (`ALGO_SYMBOL_LIMITS`) | Israeli equities trader, EU trader, small-cap specialist gets irrelevant caps |
| ALGO per-symbol caps | QQQ 10%, TSLA 7%, etc. | `engine_core.py:13` | Conservative trader wants 5% TSLA; aggressive wants 12% |
| ALGO cluster warnings | warning 30%, critical 35% | `engine_core.py` (referenced in `AI_AGENT_CONTEXT.md`) | Different capital tiers have different cluster tolerance |
| Live-alert cooldown | 45 min, fixed | `risk_monitor.py:42` (`LIVE_ALERT_REPEAT_COOLDOWN`) | Day traders need 5 min; passive position traders prefer 4h |
| Deviation cooldown | 3 h, fixed | `risk_monitor.py:40` (`DEVIATION_COOLDOWN_SEC`) | Same problem |
| Giveback cooldown | 6 h, fixed | `risk_monitor.py:41` (`GIVEBACK_COOLDOWN_SEC`) | Same problem |
| State-alert cooldowns | RUNNER=4h, BROKEN=4h, DEAD_MONEY=12h | `risk_monitor.py:48` (`STATE_ALERT_COOLDOWN`) | Same problem |
| Daily Digest window | 21:00-22:00 UTC, Mon-Fri | `risk_monitor.py:43-44` (`DAILY_DIGEST_UTC_HOUR_*`) | Asian/European trader gets digest at the wrong time |
| Adaptive-risk settle | 48 h, fixed | `adaptive_risk_engine.py:33` (`RISK_SETTLE_HOURS`) | Conservative wants 96h; aggressive wants 24h |
| Drawdown trigger | 30d, -8% NAV → cut to 0.40% | `adaptive_risk_engine.py:27-29` | Aggressive trader's pain threshold is different |
| Risk ladder | `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` | `adaptive_risk_engine.py:20` | Micro-account needs `[0.10..0.50]`; institutional-style needs `[0.25..3.0]` |
| Language | Hebrew-only | `telegram_formatters.py` (every string), `risk_monitor.py` alert text | Non-Hebrew speakers cannot use the system |
| Time zone | Israel TZ for reports; UTC for digest | `report_scheduler.py:15` (`ISRAEL_TZ`), `risk_monitor.py:43` | Reports arrive in the middle of someone else's night |
| Weekly report | Saturday 08:30 Israel TZ | `report_scheduler.py:34-37` | Trader who reviews on Sunday or Monday gets stale data |
| Monthly report | 1st of month 08:40 Israel TZ | `report_scheduler.py:38-40` | Same |
| Trend Template thresholds | Minervini-strict: MA150/200/50 relationships | `engine_core.py:159-162`, `:729-733` | "Generic momentum" user wants relaxed thresholds |
| Distribution window | 12d (DistributionDay), 8d (dist_8d) | `engine_core.py:235-237` | Day-trader wants 3-5d window |
| Accumulation window | 10d (AccumulationDay) | `engine_core.py:236` | Same |
| Trail buffers | 2% MA buffer, ATR factor 0.008, R-thresholds 5R/8R | `engine_core.py:1887-1890` | Volatility-tolerant user wants 4%; tight user wants 1% |
| Add-on size ratio | 40% of original lot | `addon_risk_engine.py:20` (`DEFAULT_SIZE_RATIO`) | Aggressive pyramider wants 60%; conservative wants 25% |
| Add-on min open R | 1.0R | `addon_risk_engine.py:15` (`MIN_OPEN_R_FOR_ADDON`) | Aggressive wants 0.5R; conservative wants 2R |
| Add-on hard floor | -25% of original risk | `addon_risk_engine.py:17` (`HARD_FLOOR_RATIO`) | Conservative wants -10%; aggressive wants -40% |
| Add-on chase limit | 7% above MA10 | `addon_risk_engine.py:21` (`CHASE_EXT_LIMIT`) | Momentum trader wants 12%; mean-reversion wants 3% |
| Menu structure | Fixed 5 categories | `telegram_menus.py:11-17` (`get_main_menu`) | Beginner needs guided flow; expert wants deep links |
| Setup keyboard | `{VCP, ALGO, SWING, EP}` | `telegram_menus.py:8` (`_SETUPS`) | Forex/futures user can't tag setups correctly |
| Message density | Same card for everyone | `telegram_formatters.py:58` (`fmt_position_card`) | Beginner wants explanations; expert wants R only |
| Dashboard tabs | Fixed 5 tabs | `dashboard.py` (Command/Performance/Forensics/Journal/Mentor/DB) | Beginner overwhelmed; expert wants forensics first |

**Bottom line:** the system has one well-tuned dial (`risk_pct`). Everything
else is a fixed constant. The next user — whether a "Minervini-relaxed"
swing trader, a Sephardi small-cap specialist, or a fund analyst stress-testing
the engine — gets the founder's preferences, not their own.

---

## Phase 2 — Four-layer personalization model

### Design principle

Every "constant" today becomes a *function* of user_id. The shim guarantees
that the founder, with no `user_profile` row, sees identical behaviour to
v0. Layers compose top-down: Layer 1 sets defaults, Layer 2 narrows them,
Layer 3 modulates them silently, Layer 4 *coaches without overriding*.

The user is always in charge. The system never silently changes Layer 1 or
Layer 2. Layer 3 changes are reversible via a dashboard toggle. Layer 4 is
advisory only — it nudges, never enforces beyond the configured Red Lines.

---

### Layer 1 — Identity profile (set once at onboarding, rarely changes)

| Field | Type | Source | Reversibility | Maps to today's constant |
|---|---|---|---|---|
| `language` | enum: `he`,`en`,`ar`,`ru`,`es` | user-explicit | yes, anytime | Hebrew-only strings in `telegram_formatters.py` |
| `time_zone` | IANA TZ string | user-explicit (or auto-detect once) | yes | `report_scheduler.ISRAEL_TZ`, `DAILY_DIGEST_UTC_HOUR_*` |
| `capital_tier` | enum: `micro` (<$25k), `small` ($25k-$100k), `mid` ($100k-$1M), `large` ($1M+) | derived from NAV; user can override | yes, but warns | drives `RISK_LADDER` shape, position cap, digest format |
| `methodology_profile` | enum: `minervini_strict`, `minervini_relaxed`, `generic_momentum`, `mean_reversion`, `custom` | user-explicit (coordinate w/ Hyperscaler) | yes, with confirmation | drives Trend Template thresholds, distribution windows, add-on min open R |
| `risk_tolerance` | enum: `conservative`, `balanced`, `aggressive` | user-explicit | yes, anytime (with cooldown — see Phase 5) | drives ladder bias, add-on size ratio, hard floor |
| `experience_level` | enum: `beginner`, `intermediate`, `experienced` | user-explicit | yes, anytime | drives message density, menu depth, coaching verbosity |

**Where the data lives:**
- Supabase table `user_profile` (one row per `telegram_user_id`).
- JSONB column `identity` holds the six fields above.
- Cached in-memory on bot start with a 5-min TTL refresh.
- Read every Telegram message handler entry; written only on `/settings`.

**Read/write cadence:** read on every request (cheap); written only on
explicit user action (`/settings`, `/onboarding`, dashboard form submit).

**Migration:** the founder gets a one-time row populated by a migration
script that mirrors today's defaults:
`{language:"he", time_zone:"Asia/Jerusalem", capital_tier:"small",
methodology_profile:"minervini_strict", risk_tolerance:"balanced",
experience_level:"experienced"}`.

---

### Layer 2 — Trading style (user picks, system enforces consistency)

| Field | Type | Source | Reversibility | Maps to today's constant |
|---|---|---|---|---|
| `time_horizon` | enum: `intraday`, `swing_short` (2-10d), `swing_medium` (10-40d), `position` (40d+) | user-explicit | yes | distribution window, trail buffer R-thresholds, dead-money age |
| `universe` | enum: `us_large_cap`, `us_small_cap`, `us_total`, `israel`, `global` | user-explicit | yes | `ALGO_SYMBOL_LIMITS` keys, sector mapping |
| `sector_tilt` | enum: `tech_heavy`, `diversified`, `cyclical`, `defensive`, `custom` | user-explicit | yes | sector cluster warnings, exposure flags |
| `position_count_target` | enum: `concentrated` (3-5), `balanced` (6-10), `diversified` (11-20) | user-explicit | yes | NEW — feeds a new "exposure spread" warning |
| `setup_universe` | set: subset of `{EP, VCP, SWING, ALGO, BREAKOUT, MEAN_REVERSION}` | user-explicit | yes | `_SETUPS` in `telegram_menus.py:8` |

**Where the data lives:** `user_profile.style` JSONB.

**Read/write cadence:** read on every Telegram menu render and every
risk_monitor cycle entry. Written only on `/settings/trading-style`.

**Consistency enforcement:** if `methodology_profile == minervini_strict` and
the user picks `time_horizon == intraday`, the dashboard shows a soft
warning ("Mark's methodology assumes multi-day holds — your style is
inconsistent with your methodology profile. Proceed?"). Never blocked,
always logged.

---

### Layer 3 — Behavioural learning (system observes, adjusts silently)

| Signal | What's observed | How adjustment shows up | Reversibility |
|---|---|---|---|
| **Check-in pattern** | Telegram message timestamps, dashboard load times, last 30d | Daily Digest scheduled in the 2h window where the user is most active 60%+ of days | toggle in `/settings/learning` (off = use Layer 1 timezone defaults) |
| **Alert responsiveness** | Time between alert sent and next user action on same symbol (drill-down, stop change, dismiss) | Low-priority alerts throttled (e.g. cooldown 45min→90min) for users who consistently ignore for >6h; tightened for fast actors | toggle |
| **Revenge-trading pattern** | Trades opened within 24h of a >1R loss | Settle period dynamically extended from 48h→96h after a loss-cluster; Phase 5 anti-pattern about consent applies | toggle |
| **Tone preference** | Average tokens of user replies; whether user uses /verbose or /short commands | Position card switches between "compact" (today's format) and "rich" (adds explanation lines) | toggle |
| **Time-of-day attention** | Telegram interaction histogram | Live alerts during low-attention hours are downgraded to digest-only | toggle |

**Where the data lives:**
- `user_telemetry` table (write-heavy, append-only).
- Aggregated nightly into `user_profile.behavior` JSONB (read-cheap).

**Read/write cadence:**
- Write: every Telegram event (~10-200 per day), `risk_monitor` alerts (~5-20 per day).
- Aggregate read: once at risk_monitor cycle start, once at digest dispatch.
- Aggregation: nightly cron at 03:00 user TZ.

**Who sets it:** purely system-inferred. User cannot directly edit; can only
toggle the entire learning loop off via `/settings/learning off`.

**Privacy:** all behavioural data stays in the user's own Supabase row.
Coordinate with Hyperscaler to make sure multi-tenant isolation is enforced
in `supabase_repository.py`.

---

### Layer 4 — Methodology coaching (nudge toward stated goals)

| Trigger | Condition | Nudge | Hard enforcement? |
|---|---|---|---|
| **Stop discipline drift** | `methodology_profile=minervini_strict` AND last 5 disc trades have avg open_r at stop < -1.0R (i.e. wider than 8% effective) | Telegram coaching message: "המקצוען מאבד 1R או פחות. 3 מתוך 5 העסקאות האחרונות עברו את הסף." | NO — coaching only |
| **Profit factor decay** | `pf` over L50 drops below user's stated target (default 1.5 for balanced) | Heat-score weighting shifts +5 points toward defensive (loss-streak penalty); user is told why | YES — but transparent: dashboard shows "Coaching adjustment: +5 toward defensive due to PF 1.3 < target 1.5" |
| **Sizing inflation** | User repeatedly sets risk_pct above adaptive recommendation despite cold heat | After 3 rejections in 14d, the adaptive recommendation gates: "Sentinel will not raise the ladder again until win-rate recovers to 50%." | YES — temporary lock, expires when condition clears |
| **Setup drift** | Selecting `setup=SWING` while `setup_universe` excludes SWING | Soft dialog: "אתה מתעד SWING אבל אסטרטגיית התיק שלך לא כוללת אותו. לעדכן את האסטרטגיה או לתקן את הטעגינג?" | NO |
| **Concentration violation** | Open positions > `position_count_target` upper bound for 7+ days | Weekly report includes a section: "you targeted 6-10, you're at 14 for 9 days. Consider trimming or updating target." | NO |

**Where the data lives:** computed on the fly from existing tables; no new
storage other than a `coaching_log` (append-only) for transparency.

**Read/write cadence:** evaluated in `risk_monitor.py` cycle (every 5 min)
for the gating cases and in `report_scheduler.py` for the weekly cases.

**Reversibility:** every coaching message has a "❌ הפסק לחנוך כאן" inline
button that adds the rule to `user_profile.coaching_mute`.

---

## Phase 3 — Concrete code touchpoints

### Overview table

| # | File:function | Today | Adaptive proposal | Per-user data needed | Backward-compat shim |
|---|---|---|---|---|---|
| 1 | `telegram_formatters.py:fmt_position_card` | Single dense Hebrew card | Three density modes (compact/balanced/rich) × language map | `identity.language`, `identity.experience_level` | If both missing → today's format |
| 2 | `risk_monitor.py:LIVE_ALERT_REPEAT_COOLDOWN` | 45 min fixed | Function of behavioural responsiveness + risk_tolerance | `behavior.alert_response_p50`, `identity.risk_tolerance` | Default returns 45 min |
| 3 | `adaptive_risk_engine.py:RISK_LADDER` | `[0.25..2.00]` shared | Per-tier ladders | `identity.capital_tier`, `identity.risk_tolerance` | `small + balanced` → current ladder |
| 4 | `report_scheduler.py:_WEEKLY_*`, `_MONTHLY_*` | Sat 08:30 / 1st 08:40 Israel TZ | Per-user weekday + hour + TZ | `identity.time_zone`, `style.weekly_review_day`, `style.preferred_briefing_hour` | Missing → Sat 08:30 Asia/Jerusalem |
| 5 | `engine_core.py:ALGO_SYMBOL_LIMITS` | `{QQQ,TSLA,JPM,PLTR,HOOD}` fixed | Per-user dict overlaid on default | `style.algo_overrides`, `style.universe` | Missing → today's dict |
| 6 | `telegram_menus.py:get_main_menu` | Fixed 5 buttons | Filtered by `experience_level` and `setup_universe` | `identity.experience_level`, `style.setup_universe` | Empty profile → today's 5 buttons |
| 7 | `addon_risk_engine.py:DEFAULT_SIZE_RATIO` | `0.40` fixed | Function of `risk_tolerance` | `identity.risk_tolerance` | balanced → 0.40 |
| 8 | `risk_monitor.py:DAILY_DIGEST_UTC_HOUR_*` | 21:00-22:00 UTC | User-local 30min window inferred from check-in pattern (Layer 3) | `behavior.peak_attention_hour_utc` or `identity.time_zone` | Missing → 21:00 UTC |
| 9 | `engine_core.py:dist_12d / accum_10d` windows | 12d / 10d hardcoded | Per `methodology_profile` + `time_horizon` | `identity.methodology_profile`, `style.time_horizon` | strict + swing_medium → 12/10 |
| 10 | `engine_core.py:_TRAIL_TIGHT_R_THRESHOLD / _TRAIL_LOOSE_R_THRESHOLD` | 8R / 5R | Per `risk_tolerance` | `identity.risk_tolerance` | balanced → 8/5 |

### Per-item detail

#### 1. `telegram_formatters.py:fmt_position_card`

- **Today:** lines 58-89. Single compact card, Hebrew-only, RTL-friendly.
- **Adaptive:** wrap with a renderer that:
  - Picks string table by `identity.language`.
  - Switches density:
    - `compact` (experienced): exactly today's 6 base lines.
    - `balanced` (intermediate): 6 lines + one "why" line per non-trivial flag (`giveback_risk`, `capital_risk`).
    - `rich` (beginner): adds inline tooltips ("R = רווח/הפסד יחסית לסיכון הראשוני") for first occurrences in a session.
- **Per-user data:** `identity.language`, `identity.experience_level`.
- **Shim:** when both missing → today's format. Existing tests in
  `tests/test_telegram_formatters.py` continue to pass because the public
  signature does not change; an additional `user_ctx=None` kwarg defaults to None.

#### 2. `risk_monitor.py:LIVE_ALERT_REPEAT_COOLDOWN` (line 42)

- **Today:** 45 min, hardcoded module constant. Used inside `should_alert()`.
- **Adaptive:** read `user_ctx.live_alert_cooldown_sec`. Computed as:
  ```
  base = {conservative:90min, balanced:45min, aggressive:20min}[risk_tolerance]
  if behavior.alert_response_p50 < 5min: multiplier = 0.5    # fast actor
  if behavior.alert_response_p50 > 6h:  multiplier = 2.0     # ignorer
  return clamp(base * multiplier, 10min, 4h)
  ```
- **Per-user data:** `identity.risk_tolerance`, `behavior.alert_response_p50`.
- **Shim:** if profile missing → return 45 min (today's value).
- **Test:** add `test_user_adaptive_cooldown.py` to verify clamp + fallback path.

#### 3. `adaptive_risk_engine.py:RISK_LADDER` (line 20)

- **Today:** `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`.
- **Adaptive:** matrix:

| capital_tier × risk_tolerance | conservative | balanced | aggressive |
|---|---|---|---|
| micro | [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.65] | [0.15, 0.25, 0.35, 0.50, 0.70, 0.90, 1.10] | [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00] |
| small | [0.15, 0.25, 0.35, 0.50, 0.65, 0.85, 1.10] | **[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]** (today) | [0.40, 0.60, 0.85, 1.15, 1.50, 2.00, 2.75] |
| mid | [0.20, 0.30, 0.40, 0.55, 0.75, 1.00, 1.30] | [0.30, 0.50, 0.70, 0.95, 1.25, 1.65, 2.20] | [0.50, 0.75, 1.00, 1.30, 1.65, 2.20, 2.85] |
| large | [0.15, 0.25, 0.35, 0.50, 0.70, 0.95, 1.25] | [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00] | [0.40, 0.60, 0.85, 1.15, 1.50, 2.00, 2.50] |

- **Per-user data:** `identity.capital_tier`, `identity.risk_tolerance`.
- **Shim:** founder maps to `small × balanced` → identical ladder. The
  `_closest_ladder_index()` helper already operates on whatever ladder is
  passed in.
- **Test:** existing `tests/test_adaptive_risk_engine.py` continues to use the
  default ladder; add fixtures for two non-default tiers.

#### 4. `report_scheduler.py:_WEEKLY_WEEKDAY/_HOUR/_MINUTE` (lines 34-40)

- **Today:** Saturday 08:30 Israel TZ; 1st of month 08:40 Israel TZ.
- **Adaptive:** scheduler loop iterates over all active users, computes "next
  fire time" in each user's TZ. Defaults are read from
  `style.weekly_review_day` (default 5=Sat) and `style.weekly_review_hour`
  (default 8). `_LOOP_SEC=60` stays.
- **Per-user data:** `identity.time_zone`, `style.weekly_review_day`,
  `style.weekly_review_hour`, `style.weekly_review_minute`.
- **Shim:** for any user with empty profile → use today's constants and Israel TZ.
- **Caution:** Phase 5 anti-pattern about scheduler-cost growth applies — do
  not iterate over thousands of users naively. Use a min-heap keyed on next-fire.

#### 5. `engine_core.py:ALGO_SYMBOL_LIMITS` (line 13)

- **Today:** `{"QQQ":10.0, "TSLA":7.0, "JPM":7.0, "PLTR":6.0, "HOOD":6.0}`.
- **Adaptive:** the constant becomes `_DEFAULT_ALGO_SYMBOL_LIMITS`; the engine
  takes per-call `algo_symbol_limits` parameter or reads from `user_ctx`.
  Per-user override merged on top:
  - `style.algo_overrides = {"NVDA": 8.0, "QQQ": 12.0}` → effective dict
    has QQQ at 12.0, NVDA added at 8.0, rest from default.
  - `style.universe == "israel"` → swap to Israeli ETF set (coordinate w/
    Hyperscaler — they own the universe maps).
- **Per-user data:** `style.algo_overrides`, `style.universe`.
- **Shim:** empty overrides + universe `us_total` → today's dict.
- **Risk:** changing this dict affects `evaluate_position_engine`, sector
  cluster warnings, ALGO classification scoring. Test coverage in
  `tests/test_algo_observer.py` must be extended.

#### 6. `telegram_menus.py:get_main_menu` (line 11)

- **Today:** fixed 5 buttons: portfolio, analysis, journal, help, developer.
- **Adaptive:**
  - `experience_level=beginner` → 3 buttons (portfolio, analysis, help). No
    developer menu. Journal hidden until first trade logged.
  - `experience_level=intermediate` → 4 buttons (today's first 4).
  - `experience_level=experienced` → today's 5.
  - `setup_universe` filters `_SETUPS` for the rating keyboard
    (`get_setup_keyboard`, line 62).
- **Per-user data:** `identity.experience_level`, `style.setup_universe`.
- **Shim:** missing → today's 5 buttons + `{VCP,ALGO,SWING,EP}` setup list.

#### 7. `addon_risk_engine.py:DEFAULT_SIZE_RATIO` (line 20) + related constants

- **Today:** `DEFAULT_SIZE_RATIO=0.40`, `MIN_OPEN_R_FOR_ADDON=1.0`,
  `HARD_FLOOR_RATIO=-0.25`, `CHASE_EXT_LIMIT=0.07`.
- **Adaptive:** matrix by `risk_tolerance`:

| risk_tolerance | size_ratio | min_open_r | hard_floor | chase_ext |
|---|---|---|---|---|
| conservative | 0.25 | 2.0 | -0.10 | 0.04 |
| balanced (today) | 0.40 | 1.0 | -0.25 | 0.07 |
| aggressive | 0.60 | 0.5 | -0.40 | 0.12 |

- **Per-user data:** `identity.risk_tolerance`.
- **Shim:** balanced → today's values.
- **Test:** `test_addon_risk_engine` must be extended with fixtures per tolerance.

#### 8. `risk_monitor.py:DAILY_DIGEST_UTC_HOUR_*` (lines 43-44)

- **Today:** 21:00-22:00 UTC, Mon-Fri only.
- **Adaptive:**
  - **Layer 1 default:** convert `identity.time_zone` to the equivalent of
    21:00 New York time (so US market close translates locally).
  - **Layer 3 override:** if behavioural data shows the user opens Telegram
    consistently in a 2h window, shift digest to land 30min before that
    window.
- **Per-user data:** `identity.time_zone`, `behavior.peak_attention_hour_utc`.
- **Shim:** missing profile → 21:00 UTC.
- **Caveat:** the `last_digest_date` dedup key in
  `risk_monitor_state.json` becomes per-user. Coordinate w/ Hyperscaler
  on the schema.

#### 9. `engine_core.py:dist_12d / accum_10d / good_closes_10` (lines 235-237)

- **Today:** 12d distribution, 10d accumulation, 10d good/bad close windows.
- **Adaptive:**

| methodology × time_horizon | dist window | accum window | close window |
|---|---|---|---|
| minervini_strict × swing_medium (today) | 12 | 10 | 10 |
| minervini_strict × position | 21 | 21 | 21 |
| minervini_relaxed × swing_short | 8 | 8 | 8 |
| generic_momentum × swing_short | 5 | 5 | 5 |
| mean_reversion × swing_short | 5 | 10 | 5 |

- **Per-user data:** `identity.methodology_profile`, `style.time_horizon`.
- **Shim:** strict × swing_medium → today's 12/10/10.
- **Risk:** `evaluate_hard_rules` and `score_position` consume these. Any
  change here is high-risk per `AGENTS.md` Red Line #5 — needs full
  regression in `tests/test_calculations_comprehensive.py`.

#### 10. `engine_core.py:_TRAIL_TIGHT_R_THRESHOLD / _TRAIL_LOOSE_R_THRESHOLD` (lines 1889-1890)

- **Today:** 8R for tight (MA21), 5R for loose (MA50).
- **Adaptive:**

| risk_tolerance | tight_r | loose_r | MA buffer pct |
|---|---|---|---|
| conservative | 5R | 3R | 0.015 |
| balanced (today) | 8R | 5R | 0.020 |
| aggressive | 12R | 7R | 0.030 |

- **Per-user data:** `identity.risk_tolerance`.
- **Shim:** balanced → today's values.

---

## Phase 4 — Onboarding flow (10-minute walkthrough)

The shortest path from `/start` to a tailored morning briefing.

### Step 1 — `/start` (≤30 sec)

```
> /start

🛡️ ברוך הבא ל-Sentinel. אני המאמן האישי שלך לסיכון.

לפני שאני מתחיל לעקוב, אני צריך 5-7 תשובות קצרות (2-3 דקות).
תוכל לדלג על כל אחת — אני אנחש ברירת מחדל ואתקן בהמשך.

[התחל] [דמו ראשון]
```

- **Captures:** Telegram user_id, language preference (detected from Telegram client locale, confirmed).
- **Optional:** "Demo first" path injects 30 days of synthetic disc + ALGO trades so the user sees the system populated. Real onboarding can continue after.
- **Infers:** TZ from Telegram client (`Asia/Jerusalem` if Hebrew default).

### Step 2 — Identity Profile (5-7 questions, ≤4 min)

Each question is a single inline keyboard, ≤6 options, with a "אני לא יודע — תבחר לי" button.

**Q1: Language** — auto-detected; confirm.
> "🇮🇱 עברית" | "🇺🇸 English" | "🇸🇦 العربية" | ...

**Q2: Capital tier**
> "מתחת ל-$25k" | "$25k-$100k" | "$100k-$1M" | "$1M+" | "תבחר לי"

We **do not** ask the dollar amount; tier is enough until they connect a broker.

**Q3: Methodology profile** (coordinate with Hyperscaler — they own the canonical list)
> "Minervini-strict (8% stop, Trend Template)" | "Minervini-relaxed" | "מומנטום כללי" | "Mean reversion" | "אחר / מותאם"

**Q4: Risk tolerance**
> "שמרני" | "מאוזן" | "אגרסיבי" | "תבחר לי"

Coupled visualisation: "מאוזן ⇒ סיכון ראשוני 0.5% מהקרן" so the user has anchored intuition.

**Q5: Experience**
> "מתחיל" | "ביניים" | "מנוסה"

This drives message density. Optionally we infer from past Telegram interactions if the user already used Sentinel.

**Q6: Time horizon** (Layer 2 starts here — optional, skippable)
> "אינטראדיי" | "סווינג קצר (2-10 ימים)" | "סווינג בינוני (10-40 ימים)" | "פוזיציה (40+ ימים)" | "תבחר לי"

**Q7: Position-count target**
> "ריכוז (3-5)" | "מאוזן (6-10)" | "פיזור (11-20)" | "אין לי דעה"

At the end of Q7:
- Total elapsed: 3-4 min.
- Layers 1+2 captured.
- We tell the user: "אפשר להמשיך — אני אלמד הרגלים תוך כדי שימוש (Layer 3)."

### Step 3 — Broker link or demo mode (≤2 min)

Two paths:

**Path A — IBKR link:**
> "כדי לראות את התיק שלך, אני צריך טוקן Flex Query של IBKR. תוכל לעשות זאת בהמשך — בינתיים אעבוד עם דמו."

We link to a 90-second video. If skipped, fall to Path B.

**Path B — Demo mode:**
> Pre-loads `demo_user_id` Supabase rows: 30 days × 12 closed campaigns
> (8 EP, 3 VCP, 1 ALGO), mix of wins/losses giving WR ≈ 55%, average payoff
> 1.8x. Enough to populate adaptive_risk_engine. Synthetic data is clearly
> tagged with `is_demo=true` and excluded from any real-money math.

### Step 4 — First morning briefing tailored to choices (≤3 min)

Generated *immediately* after onboarding, formatted by user's choices:

- Language: chosen at Q1.
- Density: from Q5 experience level.
- Risk ladder: from Q2 + Q4 → e.g. small × balanced → today's ladder.
- Distribution window: from Q3 + Q6.
- Setup universe filter: from Q6 (intraday hides VCP, etc.).

Sample (Hebrew × intermediate × balanced × swing_medium):

```
🛡️ סנטינל — בריפינג ראשון

הפרופיל שלך:
• אסטרטגיה: Minervini-relaxed
• אופק: סווינג בינוני (10-40 ימים)
• סיכון: מאוזן | קרן: $25k-$100k
• יעד: 6-10 פוזיציות

מה תראה ממני:
🟢 סיכון אדפטיבי לפי סולם של 7 שלבים (כרגע 0.50%).
🟢 התרעות פוזיציה — לא יותר מאחת ל-45 דקות לסימול.
🟢 סיכום יומי בערב (21:30 שעון ת"א).
🟢 דוח שבועי שבת 08:30.

📍 מצב נוכחי (דמו):
WR 55% | Payoff 1.8x | Heat 62/100 🟠 חם

הצעדים הבאים:
1. /portfolio — לראות פוזיציות דמו
2. /settings — לעדכן כל בחירה
3. /onboard_real — לחבר IBKR
```

### What we capture vs. infer vs. defer

| Field | Onboarding capture | Inferred at start | Captured later |
|---|---|---|---|
| language | yes (Q1) | from TG locale (Q1 prefill) | — |
| time_zone | — | from TG client | yes via /settings |
| capital_tier | yes (Q2) | — | refined when IBKR links |
| methodology | yes (Q3) | — | — |
| risk_tolerance | yes (Q4) | — | revisited every 90 days |
| experience | yes (Q5) | — | system suggests upgrade after N actions |
| time_horizon | yes (Q6) optional | swing_medium default | yes |
| position_count_target | yes (Q7) optional | balanced default | yes |
| universe | — | us_total default | yes via /settings |
| sector_tilt | — | diversified default | yes |
| behavior.* | — | starts empty | builds over 30 days of use |

---

## Phase 5 — Anti-patterns

Things the personalisation layer must **NEVER** do.

1. **Don't ask 30 onboarding questions.** Hard cap: 7 mandatory + 0-3
   optional. Anything more and the user drops off. Hyperscaler can ask
   additional fields *after* trust is built (post first 30d of usage).

2. **Don't auto-change methodology_profile without consent.** If Layer 4
   detects sustained drift (e.g. user is opening Mean-Reversion setups while
   profile says Minervini-strict), the system asks once. Never silently
   updates Layer 1.

3. **Don't violate `AGENTS.md` Red Lines for ANY profile.** Specifically:
   no ALGO campaigns in Win Rate ever, no removal of admin gate, no
   silent fallback presented as truth, no recurring alert without dedup,
   no skip of the secure-runner wrapper. These are universal — there is
   no `risk_tolerance=yolo` that unlocks them.

4. **Don't let Layer 3 silently override an explicit Layer 1/2 choice.**
   Example: user said `live_alert_cooldown=45min` (today's default). Layer 3
   sees they ignore alerts; it may *propose* extending to 90 min, but only
   surfaces the change as a prompt: "תרצה שאדחה התרעות אם אתה לא מגיב תוך 6 שעות?"

5. **Don't show coaching messages more than once per condition per week.**
   `coaching_log` enforces a per-rule cooldown. No spam.

6. **Don't migrate the founder's data unless the migration is reversible.**
   The v0 ship of this design must include a `rollback_user_profile.sql`
   that restores empty profile (→ shim returns defaults → behaviour
   unchanged). Run on staging first.

7. **Don't break determinism in tests.** Per-user functions must be
   pure given a `user_ctx` dict. Existing fixture-based tests
   (e.g. `test_adaptive_risk_engine.py`) pass an explicit `user_ctx=None`
   that resolves to today's defaults.

8. **Don't tier-shift the user without warning.** Capital tier auto-derived
   from NAV → if the NAV grows to a new tier, *prompt* the user before
   switching ladders. A 10% NAV jump should not silently double the risk
   ladder step size.

---

## Phase 6 — Tensions with Mark's methodology

Mark Minervini's published methodology is prescriptive: 7-8% max stops,
Trend Template gating, distribution-day rules, position-sizing math.
Per-user adaptiveness creates several real tensions. Below are the six
we identified plus the recommended resolution.

### Tension 1: 7-8% stop vs. `risk_tolerance=aggressive`

- **Mark:** "Cut losses at 7-8% — no exceptions."
- **User:** picks `aggressive`, expects 12-15% stops on volatile names.
- **Resolution:** **enforce a methodology floor**, not a tolerance ceiling.
  When `methodology_profile in (minervini_strict, minervini_relaxed)`, the
  hard floor for stop distance is 10% (relaxed) or 8% (strict), regardless
  of `risk_tolerance`. The aggressive tolerance only widens *position-sizing
  appetite* (risk_pct ladder), not the stop discipline.
- **Code:** `engine_core.evaluate_hard_rules` adds a new "stop too wide
  for methodology" hard-rule warning. Coaching message in Telegram.

### Tension 2: Trend Template (8/8 passes) vs. `methodology_profile=generic_momentum`

- **Mark:** Trend Template is non-negotiable for entries.
- **User:** picks `generic_momentum`; they trust their own pattern recognition.
- **Resolution:** Trend Template **score** still computed, but the
  *gating* effect on hard rules is per-profile:
  - strict: <5/8 → "broken trend, do not add" hard block.
  - relaxed: <5/8 → warning, not block.
  - generic_momentum: <5/8 → informational only.
- **Code:** `engine_core.evaluate_hard_rules` and the add-on validator
  read `methodology_profile` and gate accordingly.

### Tension 3: 12-day distribution window vs. `time_horizon=intraday`

- **Mark:** 12d distribution day cluster = unhealthy market.
- **User:** intraday; 12d is meaningless to them.
- **Resolution:** the *concept* maps cleanly; the *window* should
  scale. Phase 3 #9 already proposes per-profile windows. The Trend
  Template criteria stay; they're just evaluated over a horizon-appropriate
  window. We **do not silently weaken** the concept — we adapt the
  measurement scale.

### Tension 4: Heat-score "ladder up" vs. `risk_tolerance=conservative`

- **Mark/today:** Hot streak → +1 step on the ladder.
- **User:** conservative; doesn't want auto-raises.
- **Resolution:** ladder *exists* regardless, but `risk_tolerance` modulates
  the *speed*:
  - conservative: only auto-raises if heat ≥ 75 (vs today's 60).
  - balanced: today's 60.
  - aggressive: 50.
  The system **always** auto-cuts on cold heat or drawdown — that's the
  Red Line. Tolerance never disables the cut.

### Tension 5: ALGO observer-only vs. user wants Sentinel to act on ALGO

- **Mark:** N/A — Mark doesn't run automated systems.
- **User:** has an external ALGO; wants Sentinel to also stop-raise it.
- **Resolution:** **non-negotiable.** AGENTS.md and DATA_CONTRACTS.md
  state Sentinel never instructs ALGO exits. This is a Red Line for ALL
  profiles. We will, however, allow `style.algo_visibility_alerts = on`
  to make the visibility/cluster/streak alerts more verbose — but Sentinel
  still never sends a stop-raise instruction.

### Tension 6: Single weekly report on Saturday vs. user in a country where Saturday is a workday

- **Mark:** "Review weekly, after the close."
- **User:** Western Europe / US; Saturday morning is fine but Sunday evening
  would also work; some users prefer Friday after-market.
- **Resolution:** purely scheduling. Phase 3 #4 already lets the user pick.
  No methodology conflict — Mark's principle is "weekly review" not "Saturday".
  Default stays Saturday for the founder.

---

## Appendix — Code references

### Files inspected (read-only)

- `/home/user/lidorAvr-sentinel-trading/AGENTS.md`
- `/home/user/lidorAvr-sentinel-trading/CLAUDE.md`
- `/home/user/lidorAvr-sentinel-trading/README.md`
- `/home/user/lidorAvr-sentinel-trading/docs/AI_AGENT_CONTEXT.md`
- `/home/user/lidorAvr-sentinel-trading/docs/MODULE_MAP.md`
- `/home/user/lidorAvr-sentinel-trading/docs/DATA_CONTRACTS.md`
- `/home/user/lidorAvr-sentinel-trading/adaptive_risk_engine.py`
- `/home/user/lidorAvr-sentinel-trading/addon_risk_engine.py`
- `/home/user/lidorAvr-sentinel-trading/account_state.py`
- `/home/user/lidorAvr-sentinel-trading/sentinel_config.json`
- `/home/user/lidorAvr-sentinel-trading/telegram_formatters.py`
- `/home/user/lidorAvr-sentinel-trading/telegram_portfolio.py`
- `/home/user/lidorAvr-sentinel-trading/telegram_menus.py`
- `/home/user/lidorAvr-sentinel-trading/report_scheduler.py`
- `/home/user/lidorAvr-sentinel-trading/risk_monitor.py`
- `/home/user/lidorAvr-sentinel-trading/engine_core.py`
- `/home/user/lidorAvr-sentinel-trading/bot_core.py`

### Key line references

#### Layer 1 (Identity) touchpoints
- Hebrew RTL constant: `telegram_formatters.py:7`
- Israel TZ: `report_scheduler.py:15`
- Admin gate: `bot_core.py:17-23`, `telegram_bot_secure_runner.py:30,43`
- NAV / risk_pct config: `account_state.py:39-47`, `sentinel_config.json:1`
- Single-user risk ladder: `adaptive_risk_engine.py:20`

#### Layer 2 (Trading style) touchpoints
- ALGO universe: `engine_core.py:13` (`ALGO_SYMBOL_LIMITS`)
- ALGO per-symbol caps: `engine_core.py:13`, `:309`, `:1387`
- Setup keyboard universe: `telegram_menus.py:8` (`_SETUPS`)
- Distribution / accumulation windows: `engine_core.py:235-239`
- Trail buffer thresholds: `engine_core.py:1887-1890`
- Add-on size ratio / floor / chase / min_open_r: `addon_risk_engine.py:15-21`

#### Layer 3 (Behavioural) touchpoints
- Live alert cooldown: `risk_monitor.py:42` (`LIVE_ALERT_REPEAT_COOLDOWN`)
- Deviation cooldown: `risk_monitor.py:40` (`DEVIATION_COOLDOWN_SEC`)
- Giveback cooldown: `risk_monitor.py:41` (`GIVEBACK_COOLDOWN_SEC`)
- State alert cooldowns: `risk_monitor.py:48` (`STATE_ALERT_COOLDOWN`)
- Daily Digest window: `risk_monitor.py:43-44`
- Adaptive risk settle: `adaptive_risk_engine.py:33` (`RISK_SETTLE_HOURS`)

#### Layer 4 (Coaching) touchpoints
- Heat-score direction logic: `adaptive_risk_engine.py:483-505`
- Drawdown auto-cut: `adaptive_risk_engine.py:27-29`, `:222-259`
- Adherence stats: `adaptive_risk_engine.py:602-662`
- Coaching insight generator: `engine_core.py:generate_minervini_coaching`
  (called from `telegram_portfolio.py:395`)
- Heat factors / what-to-improve: `adaptive_risk_engine.py:334-405`

#### Critical invariants (must not be weakened by ANY profile)
- Win Rate excludes ALGO + DATA_INCOMPLETE: `adaptive_risk_engine.py:431-435`
  (`_is_disc`), `engine_core.is_stat_countable`
- Admin-only Telegram: `telegram_bot_secure_runner.py:43`
- Per-position dedup state: `risk_monitor.py:48,127,146-170`
- Secure runner: `docker-compose.yml` Telegram service entrypoint
- Fallback NAV labelled: `account_state.py:89-102`

### Suggested next-step PRs (each small, additive, reversible)

1. **PR-A: data layer** — Supabase migration adding `user_profile` table with
   `identity`, `style`, `behavior`, `coaching_mute` JSONB columns; one row
   for the founder mirroring defaults; verify migrations script updated.
2. **PR-B: user_context module** — `user_context.py` with `get_user_ctx(user_id) → dict`;
   tests verifying the founder's user_id returns today's constants exactly.
3. **PR-C: Phase 3 touchpoint #2** — replace `LIVE_ALERT_REPEAT_COOLDOWN`
   constant access with `user_ctx.live_alert_cooldown_sec`; verify
   `risk_monitor` tests still pass; add new test for non-default profile.
4. **PR-D: Phase 3 touchpoint #1** — `fmt_position_card` accepts optional
   `user_ctx`; density modes; new test fixtures.
5. **PR-E onwards:** one touchpoint per PR. Each ships with a coverage
   ratchet, a tier-specific test fixture, and an `AGENTS.md`-style
   rollback note.

Estimated total: 12-15 PRs over a sprint, no Red Line ever broken,
founder's experience byte-identical until they opt into a new profile via
`/settings`.
