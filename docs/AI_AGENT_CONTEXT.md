# AI Agent Context — Sentinel Trading

## What this system is

Sentinel Trading is a personal trading operations system. It connects trade records, portfolio/risk analysis, Telegram workflows, market data, and monitoring into one decision-support stack.

The system is not just a dashboard. It is used to support real trading decisions, so correctness and clarity are more important than cleverness.

The system direction is: **from "displays data" to "coaches in real time"** — without spam, without drama, and without giving obvious instructions.

## User goals

The system should help the user:

1. Track open and closed trading campaigns accurately.
2. Manage EP, VCP, ALGO, and other setup types completely separately in statistics.
3. Understand position health, risk, exposure, and R-multiple clearly.
4. Avoid stale or misleading data.
5. Get concise Telegram reports in Hebrew that are easy to act on.
6. Automate repetitive journal/backlog work without corrupting trade data.
7. Keep improving the system safely over time.
8. Receive one daily summary instead of repeated intra-day alerts.
9. Get one-time coaching alerts per position (Sizing Leak, Breakeven Protocol) — never repeated.

## Stat scope separation

All Win Rate, Expectancy, Avg Win R, Avg Loss R, and Profit Factor statistics must be scoped:

- **Discretionary (disc)** = EP_MANUAL + VCP_MANUAL + other `_MANUAL` buckets. All have known initial stops.
- **EP** = EP_MANUAL campaigns only.
- **VCP** = VCP_MANUAL campaigns only.
- **ALGO** = ALGO_OBSERVED. Measured by Net PnL and Net R (Target Base) only. Not counted in Win Rate.
- **DATA_INCOMPLETE** = manual setups missing initial stop. Excluded from all quality statistics.
- **Combined (countable)** = disc only (excludes ALGO and DATA_INCOMPLETE).

The functions enforcing this:
- `engine_core.classify_stat_bucket(setup_type, original_campaign_risk)` → bucket string
- `engine_core.is_stat_countable(bucket)` → True for disc buckets, False for ALGO/DATA_INCOMPLETE
- `engine_core.is_discretionary_bucket(bucket)` → True if bucket ends with `_MANUAL`
- `adaptive_risk_engine.compute_closed_campaigns(df)` → each campaign dict includes `stat_bucket`

## Alert tiers

`risk_monitor.py` sends alerts in three tiers only:

**Tier 1 — Immediate (always fire):**
- Status escalation (position worsens to higher STATUS_RANK)
- First-time state transitions: RUNNER, BROKEN, DEAD_MONEY
- Stop breach, ALGO deep loss, risk deviation severe/system
- Giveback zone transition (entering or leaving an alert zone)

**Tier 2 — Throttled (once per threshold/event):**
- Profit Protection Checkpoints (2R, 3R) — one-time per campaign
- Breakeven Protocol — one-time per campaign
- Sizing Leak — one-time per campaign when original_campaign_risk / target_risk_usd < 0.65
- Adaptive Risk direction change — once per 24h per direction

**Tier 3 — Daily Digest (once per day):**
- Fires once at 21:00–22:00 UTC (US market close), Mon–Fri only
- Lists all open positions with state emoji, Open R, and required action
- Highlights symbols needing a decision (BROKEN / RUNNER / PROFIT_PROTECTION)
- Tracked by `last_digest_date` in `risk_monitor_state.json`

**Suppressed:**
- Live Alert re-fires within 45 min unless status truly escalated
- Giveback re-fires within the same zone (no cooldown re-fire)
- Any alert after BROKEN state on that position (Giveback suppressed)
- Sizing warning repeated in every Live Alert cycle

## Main strategies and concepts

### EP

Episodic Pivot / event-driven trade. Usually catalyst-driven, often around earnings or strong news. Management focuses on follow-through, power, weakness, stops, and partials.

### VCP

Volatility Contraction Pattern. Management often references Minervini-style trend template, relative strength, distribution days, and base quality.

### ALGO

Algorithmic or system-managed positions. ALGO has specific exposure caps and should not be treated like discretionary EP/VCP risk.

Known ALGO symbol caps live in `engine_core.py`:

- QQQ: 10 percent
- TSLA: 7 percent
- JPM: 7 percent
- PLTR: 6 percent
- HOOD: 6 percent

Cluster warnings:

- warning around 30 percent ALGO exposure
- critical around 35 percent ALGO exposure

## Important design principle

Campaign-level truth matters more than raw transaction rows.

A campaign is one trade idea that can include:

- initial buy
- add-on buys
- partial sells
- final sell
- runner mode

Do not count partial sells as new trades. Do not create fake campaigns. Do not recalculate R using the wrong stop or wrong quantity.

## Current service architecture

`docker-compose.yml` defines these services:

- `sentinel-bot`: runs `main.py`
- `telegram-bot`: runs `telegram_bot_secure_runner.py`
- `dashboard`: runs `dashboard.py`
- `risk-monitor`: runs `risk_monitor.py`
- `reporting-service`: runs `report_scheduler.py`

The Telegram service intentionally runs through `telegram_bot_secure_runner.py` instead of directly through `telegram_bot.py`.

## Why the secure runner exists

`telegram_bot.py` is a long working file with many flows. Rewriting it all at once is risky.

`telegram_bot_secure_runner.py` wraps the existing bot at runtime and adds:

- admin-only access control
- rate-limit / anti-spam behavior
- cooldown after bursts
- data-source disclosure on user-facing reports

Future refactor may move this logic directly into smaller Telegram modules, but do not remove it until equivalent protections are explicit and tested.

## Data reliability rule

If a live price, NAV, or external data point is unavailable and the code falls back to a cached/default/entry value, user-facing output must clearly say that the value is estimated or fallback.

Never let a fallback value look like exact truth.

## Language and UX

Telegram messages should be:

- Hebrew-first
- RTL-friendly
- not too long
- direct and actionable
- structured with clear sections
- careful with English technical terms

Avoid dense wall-of-text reports. The bot should help the user decide what to do next, not overwhelm them.

## Change philosophy

When modifying the repo:

1. Prefer small changes.
2. Add tests around math and safety logic.
3. Avoid broad rewrites of long files.
4. Document assumptions.
5. Keep rollback simple.

## Mark rulings

Code comments often cite Mark rulings: `# Sprint-12 / Mark §3 ...`,
`# MARK_SPRINT15_RULINGS.md §1`. The ruling files live at
`docs/teams/MARK_SPRINT<N>_RULINGS.md`. The discoverable index is
`docs/markings/INDEX.md` (F12, Meeting 21/05/2026 — added so a future
agent can answer "what did Mark already rule on?" without grep-guessing
sprint numbers).
