# Behavior Delta — what changes on the Pi after deploying main (2026-05-14)

Every user-visible change in `origin/main` vs Pi-backup tip `6c8288c`.
Sources: diffs on `risk_monitor.py`, `adaptive_risk_engine.py`, `engine_core.py`, `supabase_repository.py`, `telegram_formatters.py`, `docker-compose.yml`, `audit_logger.py`, plus Sprint 6/7/8 lessons docs.

## Severity legend

- 🔴 **HIGH** — Affects real money (R, NAV, exposure, position sizing) or compliance.
- 🟡 **MED** — User-perceptible UX change. May surprise but not damage.
- 🟢 **LOW** — Cosmetic or invisible (logs, internal state).

---

## 🔴 RISK_LADDER tightened

**What changed**:
- Pi-backup: `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` (8 rungs, top 2.50%, floor 0.35%)
- Main:      `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (7 rungs, top 2.00%, floor 0.25%)

**File**: `adaptive_risk_engine.py`

**Impact**: On the next adaptive cycle (Friday close → weekend recompute), every active campaign's recommended risk_pct may map to a different rung. The 2.50% top is gone — if you were ever recommended 2.50%, the new ceiling is 2.00%. The 0.25% floor is new — small accounts can now be recommended below 0.35%.

**To revert (after deploy)**: edit `adaptive_risk_engine.py`, change `RISK_LADDER` back to the 8-rung list. Restart `risk-monitor` container.

---

## 🔴 Drawdown auto-cut (NEW)

**What changed**: Main adds `drawdown_auto_cut_recommendation()`. When 30-day cumulative PnL ≤ -8% NAV, the engine **forces** risk_pct to 0.40%, overriding any heat-based recommendation.

**File**: `adaptive_risk_engine.py:drawdown_auto_cut_recommendation`

**Impact**: If you are currently in a -8% (or worse) 30-day drawdown, the next adaptive cycle will set your risk to 0.40%. The recommended risk display will show this as an explicit override.

**Pre-deploy check**: Compute your last 30 days of realized PnL as a percentage of current NAV. If ≤ -8%, expect the auto-cut to fire on first cycle.

**To revert**: edit `adaptive_risk_engine.py`, comment out the `drawdown_auto_cut_recommendation()` call (search for the function call site). Restart `risk-monitor`.

---

## 🔴 Mgmt-notes APPEND not REPLACE

**What changed**: `update_management_notes()` now prepends `[YYYY-MM-DD HH:MM] ` and appends to existing notes, rather than overwriting.

**File**: `supabase_repository.py:update_management_notes` + `audit_logger.log_action(ACTION_ADDON_CONFIRM)` call

**Impact**: Every addon confirm grows the `management_notes` column over time. Old code reads the column as opaque string — no break. Dashboard SQL that does exact-string match on the column will see longer strings.

**Audit side-effect**: Each call also writes a row to `audit_log` (compliance trail). Requires migration 002 applied.

**No revert needed** — append behavior is non-destructive.

---

## 🔴 ATR-based trail buffer

**What changed**: `compute_suggested_trail_stop()` now uses ATR % of price as the trail buffer, instead of a fixed buffer.

**File**: `engine_core.py:compute_suggested_trail_stop`, `risk_monitor.py:790`

**Impact**: When a position becomes a RUNNER and the bot suggests a trail stop, the suggested stop is wider for high-volatility names (high ATR%) and tighter for low-vol names. Reduces whipsaws on volatile names. The numerical suggested-stop value will differ from what Pi-backup would have suggested.

---

## 🔴 Follow-through scoring (Minervini wizard)

**What changed**: `compute_follow_through()` adds a wizard-pattern signal scored on the daily chart.

**File**: `engine_core.py:compute_follow_through`

**Impact**: The "follow_through" field in position assessments now reflects a more sophisticated signal. Visible in detailed `/trade <SYM>` reports.

---

## 🟡 Daily Digest — NEW Telegram message

**What changed**: Once per weekday between 21:00–22:00 UTC (~00:00–01:00 Israel time), `risk-monitor` sends a daily summary via Telegram.

**File**: `risk_monitor.py:_daily_digest_text`, `_send_daily_digest_if_due`

**Impact**: You will receive a new daily Telegram message you've never seen before. One per day, weekdays only.

**To disable**: edit `risk_monitor.py`, set `DAILY_DIGEST_UTC_HOUR_END = 0`. Restart `risk-monitor`.

---

## 🟡 LIVE_ALERT_REPEAT_COOLDOWN = 45 min

**What changed**: Non-escalating state changes (e.g., status oscillating Power → Weak → Power) now respect a 45-minute cooldown before re-alerting.

**File**: `risk_monitor.py:should_alert`

**Impact**: Fewer Telegram alerts for noisy positions. You may notice the bot is "quieter" than before for certain stocks. Critical/Broken status escalations still alert immediately and re-fire after 6h during market hours.

---

## 🟡 Sizing Leak alert — NEW (one-time per position)

**What changed**: When a position's actual risk drops below 65% of `target_risk_usd`, the bot fires a one-time Telegram alert per position.

**File**: `risk_monitor.py:_sizing_leak_alert`, threshold `SIZING_LEAK_THRESHOLD = 0.65`

**Impact**: New alert type. Alerts you to positions where the actual stop placement leaves you risking less than planned. Persistent flag (`sizing_leak_alerted: True`) prevents re-fire.

---

## 🟡 ALGO visibility threshold change (already in main)

**What changed**: ALGO oversight alert fires only when avg visibility score < 30 (was < 60). This is already the behavior on Pi via the `ebbd38f` commit, but the new code path is slightly cleaner.

**File**: `engine_core.py:1403`, `risk_monitor.py:_algo_visibility_alert`

**Impact**: No change vs Pi-backup behavior. ALGO portfolios will still alert only when there are positions with no `target_risk_usd` (visibility = 20).

---

## 🟡 Heat-bar emoji squares

**What changed**: Risk recommendation reports now show a 10-block emoji bar (`🟢🟢🟢🟢🟢⚪⚪⚪⚪⚪`) instead of a `%.0f%` number for the heat score.

**File**: `telegram_formatters.py:_score_to_bar`, `_HEAT_FILLED`, `_HEAT_EMPTY`

**Impact**: Reports look different. Tested for RTL on iOS Telegram. Cosmetic only.

---

## 🟡 Heartbeat writes to `/app/state/`

**What changed**: Each container writes `<service>_last_cycle` timestamp file every loop iteration. Healthchecks read these files via the `sentinel_state` named volume.

**File**: `main.py:_touch_heartbeat`, `risk_monitor.py:_touch_heartbeat`, `docker-compose.yml`

**Impact**: Filesystem writes. Healthchecks become real (vs Pi-backup which had no liveness check).

---

## 🟡 dev_pin gate REMOVED

**What changed**: The 6-digit PIN that gated developer menu access is gone. Developer menu opens on first click.

**File**: `telegram_devops.py` (dev_pin functions retained for backward compat but not enforced)

**Impact**: Slightly less friction in dev menu access. **NOT a real security regression** — `telegram_bot_secure_runner.py` still rejects messages from any chat_id ≠ `TELEGRAM_ADMIN_ID`. PIN was a 2nd factor; admin-id check is the real gate.

---

## 🟢 Healthchecks + autoheal labels

**What changed**: `docker-compose.yml` adds `healthcheck:` blocks per service with custom intervals (telegram-bot 180s, sentinel-bot 1980s, dashboard via curl, risk-monitor 720s) and `autoheal=true` labels.

**Impact**: If you run an `autoheal` sidecar container, it will restart unhealthy services automatically. Without the sidecar, healthchecks are just informational (visible in `docker ps` output).

---

## 🟢 Memory limits + log rotation

**What changed**: `docker-compose.yml` adds `mem_limit: 1200m` per service and `logging.driver: json-file` with `max-size: 10m, max-file: 5`.

**Impact**: Each service capped at 1.2 GB RAM. Logs auto-rotate at 10 MB × 5 files. Reduces risk of one runaway service taking down the Pi.

---

## 🟢 pytest-socket in test suite

**What changed**: `tests/conftest.py` blocks all network calls during tests. Auto-applies markers (`unit`/`integration`/`slow`) based on test file naming.

**Impact**: Invisible at runtime. Tests can no longer accidentally hit Telegram/IBKR/Supabase during CI. 1321 tests pass under this constraint.

---

## 🟢 audit_logger module + migration 002

**What changed**: New `audit_logger.py` module. 4 wired call sites (`adaptive_risk_engine`, `supabase_repository`, `telegram_devops`, `audit_logger` self-test). Migration `002_audit_log.sql` creates the `audit_log` table.

**Impact**: Compliance trail of risk_pct changes, addon confirms, dev_pin events. Fail-open — never blocks user actions even if Supabase is down.

**Without migration 002**: writes silently fail (logged to stderr). Bot keeps working. Apply migration to start collecting the trail.

---

## Summary table

| Severity | Count | Categories |
|---|---|---|
| 🔴 HIGH | 5 | RISK_LADDER, drawdown auto-cut, mgmt-notes APPEND, ATR trail, follow-through |
| 🟡 MED | 7 | Daily digest, alert cooldown, sizing leak, ALGO threshold, heat-bar, heartbeats, dev_pin removal |
| 🟢 LOW | 4 | Healthchecks, mem limits, pytest-socket, audit_logger |

## What is NOT changing

- Telegram admin gate (`TELEGRAM_ADMIN_ID` check in `telegram_bot_secure_runner.py`)
- Supabase read paths
- IBKR XML parser (`ibkr_trade_importer.py` — byte-identical)
- Engine math for entry/stop validation
- Campaign aggregation logic (`engine_core.get_open_positions_campaign`)
- NAV computation
