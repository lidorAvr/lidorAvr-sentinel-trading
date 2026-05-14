# Data Contracts

This file defines the data assumptions that future agents must preserve.

## Core principle

The system should show the user the truth, or clearly mark uncertainty.

If a value is computed from fallback data, cached data, default config, or incomplete records, the output must say so.

## Trade row contract

Trade rows are stored in Supabase, in the `trades` table.

### Core fields (always populated by importer)

- `trade_id` (PK, IBKR `tradeID`)
- `symbol`
- `trade_date` (`YYYY-MM-DD`)
- `side` (`BUY` / `SELL`)
- `quantity` (signed: BUY positive, SELL negative)
- `price` (`tradePrice` from IBKR)
- `pnl_usd` (from IBKR `fifoPnlRealized` on SELL rows)
- `campaign_id` (format `{SYMBOL}_{tradeID of first BUY}`)

### Fields populated by user via backlog/dashboard

- `setup_type` (`VCP` / `EP` / `SWING` / `ALGO`)
- `quality` (1–10 score)
- `score` (1–10 score)
- `stop_loss` (current stop, may be updated via Task Review)
- `initial_stop` (entry-time stop, locked)
- `image_url`
- `management_notes` (APPEND not REPLACE per Sprint 8 — every confirm prepends `[YYYY-MM-DD HH:MM]`)

### Migration 001 — addon Phase 2 (Sprint 5)

- `is_addon` (bool)
- `base_campaign_lot_id`
- `addon_sequence` (int)

### Migration 003 — entry snapshots (Sprint 11, 2026-05-14)

- `risk_pct_at_entry` (numeric, nullable) — `risk_pct_input` from sentinel_config at insert time
- `nav_at_entry` (numeric, nullable) — `nav` (or `total_deposited` fallback) from sentinel_config at insert time

These let the portfolio display compute the ORIGINAL campaign target
(the one in effect when the trade was opened), not the moving CURRENT
target that drifts every time the user changes their adaptive risk.
Existing trades (pre-Sprint 11) have NULL → fallback to current target
silently. `ibkr_trade_importer._load_entry_snapshot()` stamps the
snapshot once per import batch.

Surfaced via `engine_core.get_open_positions_campaign` — each campaign
row inherits the snapshot from its FIRST BUY trade.

### Runtime / advisory fields (computed or stored, not always populated)

- `parent_trade_id`
- `management_state`
- `management_flags`
- `target_risk_usd`

Do not assume every field is always populated. Existing code often handles missing values.

### Apply migration 003

```sql
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS risk_pct_at_entry numeric,
    ADD COLUMN IF NOT EXISTS nav_at_entry      numeric;
```

Verify with `python3 migrations/verify_migrations.py`.

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

## Initial risk contract

For discretionary trades such as EP/VCP:

- initial risk should usually be based on first-day buy price/quantity and initial stop
- partial sells should not rewrite the original campaign risk
- R calculations must be based on the correct original risk basis

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

## task_state.json contract (Sprint 10)

Persistent state for the 📋 Task Review feature. Located at
`/app/task_state.json` (override via `task_state.TASK_STATE_FILE` —
resolved at call time, NOT as default argument).

```json
{
  "snoozed": {
    "<campaign_id>|<kind>": <unix_ts_until_active_again>
  },
  "last_action": {
    "<campaign_id>|<kind>": {
      "action": "approve" | "snooze" | "dismiss",
      "ts": <unix>,
      "before": <value_or_null>,
      "after":  <value_or_null>,
      "duration_sec": <only_for_snooze>
    }
  }
}
```

Dedup key: `f"{campaign_id}|{kind}"` where kind ∈ {`stop_breach`,
`dead_money`, `break_even_2r`, `trail_up_3r`, `loose_stop`,
`tighten_to_ma21`}.

Snooze durations:
- `SNOOZE_SHORT = 24h` — user pressed ⏰ דחה
- `SNOOZE_LONG = 30d` — user pressed ❌ דלג
- `1h grace` — auto, after every approve (prevents re-fire before
  Supabase write propagates)

All writes are atomic (tmp + os.replace). Never raises — returns
False / empty skeleton on failure.

---

## ibkr_last_sendrequest.json contract (Sprint 11 IBKR fix)

Sentinel-side SendRequest cooldown state. Located at
`/app/state/ibkr_last_sendrequest.json`.

```json
{"last_ts": <unix_seconds>}
```

Read by `ibkr_sync_runner._last_sendrequest_ts()`. Written by
`_record_sendrequest_ts()` ONLY when SendRequest produced a valid
`<ReferenceCode>` — failed requests (1001, etc.) do NOT consume the
cooldown slot.

Cooldown: `IBKR_SENDREQ_COOLDOWN_SEC` env var (default 120s).

---

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

## Schema change protocol

If adding/removing/changing a field:

1. Document it here.
2. Update all modules that read/write it.
3. Add tests or migration notes.
4. Confirm backward compatibility with existing rows.
