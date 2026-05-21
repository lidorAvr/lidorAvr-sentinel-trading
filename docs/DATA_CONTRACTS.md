# Data Contracts

This file defines the data assumptions that future agents must preserve.

## Core principle

The system should show the user the truth, or clearly mark uncertainty.

If a value is computed from fallback data, cached data, default config, or incomplete records, the output must say so.

## Trade row contract

Trade rows are stored in Supabase, usually in a `trades` table.

Common fields observed in the system:

- `trade_id`
- `symbol`
- `trade_date`
- `side`
- `quantity`
- `price`
- `pnl_usd`
- `commission`
- `stop_loss`
- `initial_stop`
- `setup_type`
- `quality`
- `score`
- `image_url`
- `management_notes`
- `campaign_id`
- `parent_trade_id`
- `management_state`
- `management_flags`
- `target_risk_usd`
- `locked_entry_price` *(RISK-1a, migration 006 — NULL until locked)*
- `locked_entry_at` *(RISK-1a, migration 006 — NULL until locked)*
- `lock_source` *(RISK-1a, migration 006 — NULL until locked)*
- `lock_method` *(RISK-1a, migration 006 — NULL until locked)*

Do not assume every field is always populated. Existing code often handles missing values.

### Locked-immutable at-entry price contract (RISK-1a, migration 006)

`locked_entry_price` is the **canonical at-entry anchor** for planned-risk math
going forward — the price the trader committed to at trade-entry, captured
once and never recomputed. The legacy `price` column stays as the broker-fill
record (truth-of-execution); these two diverge by design once the position has
been adjusted, marked-to-market, or partially re-recorded. The drift between
them is exactly the regression that motivated RISK-1 (a live dashboard reading
`price` showed mark-to-market values labelled as entry — e.g. an $87 MRVL
position rendered as $170 once the symbol ran).

| Column                | Type             | Populated by                                                                             |
|-----------------------|------------------|------------------------------------------------------------------------------------------|
| `locked_entry_price`  | `NUMERIC(12,4)`  | RISK-1b wizard (forward) / RISK-1c backfill / RISK-1d.4 `/at_entry_correct` (pending)    |
| `locked_entry_at`     | `TIMESTAMPTZ`    | The same writer, at the moment of the lock (NOT row-insert time)                         |
| `lock_source`         | `TEXT`           | One of: `broker_avg_fill` \| `reuters_open` \| `declared_by_user` \| `unknown`           |
| `lock_method`         | `TEXT`           | One of: `wizard` (RISK-1b) \| `backfill` (RISK-1c) \| `admin_correction` (RISK-1d.4)     |

**NULL is the legitimate "not-yet-locked" sentinel.** Every row that existed
before migration 006 was applied has `locked_entry_price IS NULL` until a
RISK-1b/1c/1d writer touches it. Callers MUST treat NULL as "fall back to the
legacy display path + surface a banner-flagged 'not yet locked' state". Do
NOT silently substitute `price` for `locked_entry_price` — that would
re-introduce the exact display-drift regression RISK-1 exists to fix.

**Read pattern (RISK-1d — LANDED).** `telegram_formatters.resolve_entry_display`
is the **single source of truth** for displaying entry price across all 3
surfaces (Telegram /portfolio card, AI Master Context Export, dashboard
Command-Center expander). Pure / read-only — no Supabase, no engine_core,
no telebot import (DEC-20260510-005). The 3 surfaces each call the resolver
with `mode='live'` (produce-once-consume-thrice) and pass the resolved
`entry` value + `banner` string through to their respective renderers.
`fmt_position_card` gained an `entry_banner: str = ""` kwarg (default →
byte-identical to pre-RISK-1d output, same defaulted-kwarg pattern as
Sprint-12 `price_is_fallback` and Sprint-15 `dual_r_fragment`).

The resolver's `mode` flag:
- `mode='historical'` (default — used by LOCKED-April and every backwards-
  compatible caller): reads `price` exactly as before. NEW lock columns are
  ignored. **April reconciliation is byte-identical by construction** — see
  `tests/_byte_lock_baselines/`. analytics_engine never reads the lock
  columns; the LOCKED-April fixture path is untouched.
- `mode='live'` (opted-in by the 3 display surfaces): reads
  `locked_entry_price` when it is a positive number, falls back to `price`
  with the `ENTRY_NOT_LOCKED_LABEL` banner when NULL / 0 / negative /
  non-numeric. Silent on locked (absence of warning IS the signal).

The banner string (`telegram_formatters.ENTRY_NOT_LOCKED_LABEL` —
"‏⚠️ (מחיר לא-נעול — עלול לזוז עם re-sync)") is sourced exactly once;
wording edits land in one place.

**No SQL CHECK constraint on `lock_source` / `lock_method`.** Validation lives
in the application layer (`supabase_repository.set_locked_entry`). Phase A
intentionally keeps DDL flexible (CLAUDE.md preferred-refactor: gradual
extraction over premature lock-in).

**Audit-log integration.** `set_locked_entry` itself does NOT write an
`audit_log` row — the call sites do, via `audit_logger.log_action`, with
richer before/after context than the helper has. RISK-1b/1c/1d each register
their own action constant.

**`pnl_usd` is the authoritative broker-side NET realized PnL (commission
already deducted).** The DEC-019/-020 raw-Supabase reconciliation
(to the cent: April +$336.14 / +11.01R / PF 4.03) proved production
`pnl_usd` is net of commission. The realized-PnL path
(`analytics_engine._aggregate_campaigns` → `sells["pnl_usd"].sum()`) reads
ONLY `pnl_usd`; `commission` is **informational/audit-only and MUST NOT be
subtracted again** anywhere in the realized-PnL / R / Net-R / Expectancy
math — doing so would double-count commission. (Sprint-25 A2/Data-F6:
this clarifies a documentation gap; no code change — `commission` is
listed above but was never read by the realized path, by design.)

## Side and quantity rules

Current logic assumes:

- buy rows increase campaign quantity
- sell rows reduce campaign quantity
- open campaign exists when net quantity is greater than zero

Be careful: some brokers/export paths may store sell quantity as negative. Before changing quantity logic, inspect real rows.

## Campaign contract

A campaign is one trade idea.

One campaign can include:

- one or more buys
- partial sells
- final sell
- runner state
- management notes

Campaign-level calculations should not treat every row as a separate independent trade.

**Period-boundary / closed-campaign window rule (validated invariant —
do not "fix" without a regression proof).** For a reporting window
`[period_start, period_end)`, a campaign counts as **closed for that
period** if it has **ANY SELL whose `trade_date` falls in
`[period_start, period_end)`** — NOT only if its *last* SELL falls in the
window. This is `analytics_engine._get_closed_campaigns`'s real,
DEC-019/-020-reconciled behaviour (the April `8 / +$180.49 / WR .375 /
PF 2.626 / excl 2` ground truth depends on exactly this any-in-window-SELL
semantics). The in-code `_get_closed_campaigns` docstring historically
said "whose last SELL" — that wording is INACCURATE; the Sprint-24 in-code
CORRECTNESS NOTE and this contract clause are authoritative. A campaign
with a partial SELL inside the window and its final SELL *after*
`period_end` IS counted as closed for the period. Changing this to
match the stale "last SELL" docstring would silently alter the validated
campaign set — a forbidden campaign-aggregation change without tests.
(Sprint-25 A2/Data-F7: doc-only — pins a validated invariant against
future regression; the LOCKED April regression already pins it
numerically.)

## stat_bucket contract

Every campaign is classified into a stat bucket using:

```python
engine_core.classify_stat_bucket(setup_type, original_campaign_risk) → str
```

Valid buckets:

| Bucket            | Meaning                                                    |
|-------------------|------------------------------------------------------------|
| `EP_MANUAL`       | EP setup with known initial stop                           |
| `VCP_MANUAL`      | VCP setup with known initial stop                          |
| `ALGO_OBSERVED`   | ALGO-managed position; Sentinel observes only              |
| `DATA_INCOMPLETE` | Discretionary setup missing initial stop or risk basis     |

Rules:

- `engine_core.is_stat_countable(bucket)` → True **only** for `_MANUAL` buckets (EP_MANUAL, VCP_MANUAL).
- `engine_core.is_discretionary_bucket(bucket)` → True if bucket ends with `_MANUAL`.
- `DATA_INCOMPLETE` and `ALGO_OBSERVED` must **never** appear in Win Rate, Expectancy, Avg Win R, Avg Loss R, or Profit Factor.
- `ALGO_OBSERVED` campaigns are measured by Net PnL and Net R (Target Base) only.
- `original_campaign_risk = 0` triggers `DATA_INCOMPLETE` classification even if setup_type is EP or VCP.

The `adaptive_risk_engine.compute_closed_campaigns(df)` function attaches `stat_bucket` to each campaign dict. All downstream stats must read from that field.

**F6 — two intentional Profit-Factor conventions; do NOT "unify" one side (Sprint-25 audit).**
There are deliberately **two** PF conventions in the codebase and they must stay separate:

- `analytics_engine` profit-factor uses **raw `math.inf`** for a countable set with wins
  and zero losses (`gross_profit / 0 → math.inf`). DEC-20260516-021 lists this `math.inf`
  branch as **intentional / DO-NOT-TOUCH**. It is clamped everywhere checked
  (`compute_trader_development_score`, verdict, renderer); the residual risk is only future
  serialization / period-delta math, not a current headline.
- The **`99.0` sentinel** lives **only** in the dashboard `_bucket_stats` (a display cap),
  NOT in `analytics_engine`.

A future edit must NOT "unify" these — replacing the `analytics_engine` `math.inf` with the
dashboard `99.0` (or vice-versa) would change the locked April PF `2.6262` path / the
serialized PF and is a reconciliation trap. The divergence is by design; document, do not fix.

**F4 — exact-`trade_id` dedup before per-campaign aggregation (Phase-Engine-P2/P3).**
`_aggregate_campaigns` (analytics_engine), `compute_closed_campaigns` (adaptive_risk_engine)
and `get_open_positions_campaign` (engine_core) drop EXACT-`trade_id`-duplicate rows
(`keep="first"`, guarded on the column's presence — absent ⇒ no-op) BEFORE the side
split / `pnl_usd` sum, so a re-exported / double-synced SELL is not counted twice. On
inputs with no duplicate `trade_id` (the LOCKED April fixture + current prod per DEC-019)
this is a provable identity (drop_duplicates on an all-unique key returns the same rows in
the same order). Behavior changes ONLY on the duplicated-row input.

**F9 — out-of-order rows floor `days_held=1`, inflating `avg_r_per_day` / dev-score (display/score only).**
`_aggregate_campaigns` computes `days_held = max(1, (last_sell - entry).days)`. If a SELL
row's date precedes its BUY (out-of-order export), the difference is ≤ 0 and `days_held`
floors to **1**, so `avg_r_per_day = (net_r / days_held).mean()` and the trader-development
"execution efficiency" / Minervini R-per-day reward a data-ordering artifact. **R itself is
correct** — only `avg_r_per_day` and the dev-score are affected, and the `max(1, ...)`
div-by-zero guard is itself correct. The LOCKED fixture has ordered rows so it is
byte-identical. Documented (not money-affecting); no code change.

## Initial risk contract

For discretionary trades such as EP/VCP:

- initial risk should usually be based on first-day buy price/quantity and initial stop
- partial sells should not rewrite the original campaign risk
- R calculations must be based on the correct original risk basis

**F7 — the 1R denominator is deliberately cent-rounded (Sprint-25 audit, DO NOT "clean up").**
`engine_core.compute_original_campaign_risk` returns `round(max(0.0, risk*qty+fees), 2)`,
and that cent-rounded value is the **denominator** of every `net_r = net_pnl / orig_risk`
(`analytics_engine`). So every R carries a deliberate sub-cent basis rounding (e.g. raw
`4.6533 → 4.66`). This is **intentional and load-bearing**: the LOCKED April regression
(PF `2.6262`, WR `.375`, 8 / +$180.49) was computed *with* this rounding. Removing the
`round(..., 2)` would shift every R and BREAK the locked fixture — do NOT "clean it up".

For ALGO trades:

- ALGO can use different risk interpretation
- symbol exposure caps are more important than discretionary initial-stop sizing
- `current_stop` of 0 for ALGO is expected — display as "External / Unknown", never as `$0.00`
- R is calculated using `target_risk_usd` as denominator, labeled as "Target Risk Base"

## management_mode contract (runtime-derived, not stored in Supabase)

Computed by `engine_core.classify_management_mode(setup_type, symbol)`.

Values:
- `manual_managed`: discretionary EP/VCP position managed by the user
- `algo_observed`: externally managed by ALGO system; Sentinel observes only
- `unknown`: insufficient data to classify; exclude from quality statistics

Rules:
- Sentinel must NEVER issue stop-raise or exit instructions to `algo_observed` positions.
- `algo_observed` positions are excluded from EP/VCP execution discipline scoring.
- `unknown` positions are excluded from Expectancy and Win Rate statistics.

## risk_basis contract (runtime-derived)

Computed by `engine_core.classify_risk_basis(stop, base_price, setup_type, target_risk_usd)`.

Values:
- `True`: real known stop exists; enters all quality statistics
- `Target`: uses `target_risk_usd` as R denominator (ALGO or missing stop)
- `Unknown`: no basis available; excluded from statistics

## risk_visibility_score contract (runtime-derived)

Computed by `engine_core.compute_risk_visibility_score(setup_type, stop, base_price, target_risk_usd)`.

Range 0–100:
- 100: stop known, risk known (True Risk basis)
- 60: Target Risk basis only
- 40: ALGO external, target risk available
- 20: ALGO external, no target risk; or no stop and no target
- 0: broken data

## NAV / account-size contract

NAV/account size can affect:

- risk per trade
- exposure percent
- target risk in dollars
- sizing status
- portfolio-level warnings

Rules:

1. There must be one clear source of truth for NAV/account-size.
2. If IBKR NAV is unavailable and the system falls back to deposited capital/default value, the report must say so.
3. Do not silently mix host paths and container paths.
4. If modifying config paths, update Docker Compose, docs, and tests together.

> **Divergence flag (Phase Arch-F1 / Sprint-25 F1 — DEFERRED, founder-gated).**
> Rule 1 ("one clear source of truth") is NOT yet fully met. Two
> blessed NAV contracts coexist behind the SAME risk math:
> `account_state.load()` (report pipeline — shape A, honest fallback,
> `ok=False` only on fallback) and `engine_core.get_nav_with_freshness()`
> (bot + risk-monitor `:607-609` — different shape `source`/`updated_at`,
> different fallback `is_critical=True`/different label/`ok=False`). A future
> edit to one fallback silently desyncs Telegram risk sizing, the
> risk-monitor Sizing-Leak threshold, and the weekly/monthly report
> target-risk. Unifying them is money-affecting (changes which
> fallback/freshness a path sees) → **OUT of Arch-F1, a deferred
> founder-gated decision**. Arch-F1 only de-duplicated the
> `sentinel_config.json` *reader* (one shared
> `bot_helpers.get_account_settings`, bare-`except:` removed); the
> `risk_monitor.py:607-609` math + `engine_core.py` + `account_state.py` are
> byte-unchanged.

Known deployment detail:

- Docker services mount the repo into `/app`.
- `docker-compose.yml` currently runs Telegram through `telegram_bot_secure_runner.py`.

## Market data contract

`engine_core.py` retrieves data through yfinance and fallback scraping/cached history.

Rules:

- Live price may be unavailable.
- Cached price may be stale.
- Historical close is not the same as live price.
- Any report using fallback price must identify the uncertainty.

## Telegram report contract

Telegram output should include enough information to act safely, but not overload the user.

Required properties:

- Hebrew-friendly layout
- short sections
- clear action/trigger/status
- no misleading precision
- source/fallback disclosure for risk-sensitive reports
- long reports split below Telegram limits

## Supabase write contract

Supabase writes happen in user workflows, especially backlog/journal completion.

Rules:

- Do not write to Supabase from a read-only report flow unless explicitly required.
- Do not auto-fill missing values unless the rule is deterministic and documented.
- When inheriting values from older campaign rows, keep the logic transparent.
- Any new mutation path should be isolated and testable.

## Status contract

Common position statuses include:

- Power
- Healthy
- Yellow Flag
- Weak
- Broken
- Climactic

Do not change status names lightly because user-facing reports and mental models rely on them.

## Alert key contract

`risk_monitor.py` builds a per-position alert key for deduplication via `build_position_alert_key()`.

The alert key includes:

- `status`: current position status string
- `action`: recommended action string
- `sizing_status`: sizing label (default "✅ תקין")

The alert key does **NOT** include `trigger` — removing trigger prevents re-fires when the trigger text cycles without a real state change.

`should_alert()` logic:

1. Status escalation (higher `STATUS_RANK`) → always fires immediately.
2. Critical/Broken status → fires at most once per 6 h during US market hours.
3. Key change (non-escalating) → fires only if ≥ 45 min since last alert (`LIVE_ALERT_REPEAT_COOLDOWN`).
4. No change → never fires.

## Giveback zone contract

`risk_monitor.py` fires a Giveback alert only when the zone classification **changes**.

Zone-change logic:

```python
alert_classes = {"watch", "tighten", "protection_failure"}
zone_changed = gb["classification"] != prev_gb_class
is_alert_current = gb["classification"] in alert_classes
is_alert_prev    = prev_gb_class in alert_classes
should_fire = zone_changed and (is_alert_current or is_alert_prev)
```

Rules:

- No cooldown-based re-fire within the same zone.
- BROKEN position state gates the entire Giveback check — no Giveback alert on an already-broken position.
- `last_giveback_class` is always updated after each cycle (even if no alert fires) to track zone for next comparison.

## risk_monitor_state.json contract

`risk_monitor_state.json` is the anti-spam / deduplication state store.

Per-position keys (nested under symbol key):

| Key                          | Type      | Purpose                                                   |
|------------------------------|-----------|-----------------------------------------------------------|
| `peak_open_r`                | float     | Highest Open R seen; used for Giveback watermark          |
| `last_deviation_class`       | str       | Last risk-deviation classification seen                   |
| `last_deviation_ts`          | float     | Timestamp of last deviation alert                         |
| `last_giveback_class`        | str       | Last Giveback zone classification (for zone-change check) |
| `last_giveback_ts`           | float     | Timestamp of last Giveback alert fire                     |
| `checkpoints_hit`            | list[str] | Profit protection checkpoints already fired (2R, 3R)      |
| `position_state`             | str       | Last known position state (RUNNER, BROKEN, etc.)          |
| `state_label`                | str       | Display label of position state                           |
| `breakeven_alerted`          | bool      | True after Breakeven Protocol alert fires (one-time)      |
| `algo_loss_streak`           | int       | Running ALGO consecutive-loss count                       |
| `algo_streak_alerted_yellow` | bool      | One-time streak alert at yellow threshold                 |
| `algo_streak_alerted_orange` | bool      | One-time streak alert at orange threshold                 |
| `algo_deep_loss_alerted`     | bool      | One-time deep-loss alert for ALGO positions               |
| `last_state_alert_ts`        | float     | Timestamp of last position-state alert                    |
| `last_state_alert_type`      | str       | State type of last state alert                            |
| `runner_decision`            | str       | Runner mode decision recorded                             |
| `runner_decision_ts`         | float     | Timestamp of runner decision                              |
| `sizing_leak_alerted`        | bool      | True after Sizing Leak alert fires (one-time per campaign) |

Top-level (global) keys:

| Key                | Type | Purpose                                              |
|--------------------|------|------------------------------------------------------|
| `last_digest_date` | str  | ISO date string of last Daily Digest send (YYYY-MM-DD) |

Rules:

- `sizing_leak_alerted` is **one-time per campaign**. Once True, sizing leak never fires again for that position.
- `last_digest_date` prevents the digest from firing more than once per calendar day.
- All keys must be carried over between monitor cycles via the carry-over key list.
- Adding a new one-time alert requires adding its dedup key here and to the carry-over list in `risk_monitor.py`.

## Sizing Leak contract

Sizing Leak fires when:

```
original_campaign_risk / target_risk_usd < SIZING_LEAK_THRESHOLD (0.65)
```

Rules:

- Applies only to discretionary (non-ALGO) positions.
- Fires only once per campaign (`sizing_leak_alerted` flag).
- Does not repeat in Live Alert cycle.
- `original_campaign_risk` and `target_risk_usd` must both be > 0 for the check to run.

## Daily Digest contract

Daily Digest sends one summary message per trading day.

Timing: once between `DAILY_DIGEST_UTC_HOUR_START` (21:00) and `DAILY_DIGEST_UTC_HOUR_END` (22:00) UTC, Monday–Friday only.

Content per position row: symbol + setup + state emoji + Open R + action.

Deduplication: checked via `last_digest_date` in `risk_monitor_state.json`. If today's date already matches, digest is skipped.

## Risk language contract

The user expects direct language. Avoid vague output.

Good:

- `לא להוסיף. להחזיק ולעקוב אחרי שבירת MA20.`
- `הנתון משוער כי מחיר חי לא זמין.`

Bad:

- `נראה בסדר כנראה.`
- `המערכת מעריכה מצב חיובי` without evidence.

## Data history scope (YTD-bound / founder note 21/05/2026)

**The Supabase `trades` table only carries trades from the date Sentinel
was deployed forward.** Closed campaigns that ran BEFORE the deployment
date have no row in `trades` at all — neither BUYs nor SELLs nor
realized PnL.

This affects every "all-time" calculation:
- **Realized PnL** (`SUM(sells.pnl_usd)`) covers only post-deploy
  campaigns. Pre-deploy realized PnL is structurally absent.
- **Broker reconciliation gap** (`NAV - (deposits + realized + open)`)
  is therefore OVERSTATED by the missing pre-deploy realized PnL.
  A founder seeing a $495 gap on $7.5K capital should suspect this
  before assuming a true data corruption.
- **Win Rate / Expectancy / Profit Factor / Adaptive Risk windows**
  (S9/M21/L50) are all evaluated on the post-deploy set. The "L50
  partial sample" honest-disclosure line already discloses this for
  the heat windows; the reconciliation gap was the surfacing-gap
  before this section was added.

**Operator workflow.** When the founder reconciles manually with
the broker, they can SET the following field in `sentinel_config.json`:

```json
{
  "total_deposited": 7500.0,
  "risk_pct_input": 0.5,
  "pre_db_realized_pnl_estimate": -495.67
}
```

The value is the **founder's manual estimate** of pre-deploy realized
PnL (signed: positive = pre-deploy gains, negative = pre-deploy losses).
`classify_broker_reconciliation` subtracts this from the raw gap before
banding, so the surfaced band reflects the residual after the
disclaimer. The classifier never asserts a cause — it only relaxes the
band when the founder has explicitly disclaimed history.

**Defensive invariant.** The classifier uses
`min(|raw_gap|, |adjusted_gap|)` for band classification, so an
over-estimated history can only ever SOFTEN the band, never tighten
it. If the founder writes `pre_db_realized_pnl_estimate: -10000` when
the true pre-deploy PnL was only -$500, the system will not falsely
escalate a non-existent gap into Critical.

**Future improvement.** A full per-trade pre-deploy backfill would
eliminate the estimate altogether (every closed campaign would have a
real row). Until then, the manual estimate is the bridge.

## Schema change protocol

If adding/removing/changing a field:

1. Document it here.
2. Update all modules that read/write it.
3. Add tests or migration notes.
4. Confirm backward compatibility with existing rows.
