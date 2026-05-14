# IBKR Configuration Reference

**This is the source of truth for IBKR Flex Query setup.** Every required setting that lives outside the repo (IBKR Account Management, `.env` file) is documented here. Failing to follow this exactly is the #1 cause of error 1001 (`Statement could not be generated at this time`).

## Quick verification (no SSH required)

In Telegram → developer menu → 🏥 בדיקת בריאות מערכת. Check that all four IBKR-related rows are ✅:

- `IBKR Sync — <today's date>` (or warn if not synced today)
- `IBKR Token — מוגדר`
- `IBKR Query ID — <your-query-id>` (must show actual ID, NOT "IBKR_QUERY_ID חסר")
- `Flex Period — <N> ימים (<from>→<to>)` (must be ≥ 14 days, ideally 30)

If any of those is 🔴 or ⚠️, fix the corresponding row below.

## Required IBKR Account Management settings

### Flex Query: "Sentinel_Trades"

Navigate: https://www.interactivebrokers.com → Login → Reports → Flex Queries → "Sentinel_Trades" → Edit.

| Field | Required value | Why |
|---|---|---|
| **Query Name** | `Sentinel_Trades` | matches the agreed naming |
| **Format** | `XML` | `ibkr_sync_runner.py` parses XML only |
| **Period** | **`Last 30 Calendar Days`** | dynamic periods (`Month to Date`, `Today`, `YTD`, `QTD`) trigger 1001 in IBKR's post-close batch window |
| **Date Format** | `yyyyMMdd` | Fix 3's `compute_suggested_period` calls `strptime("%Y%m%d")` |
| **Time Format** | `HHmmss` | |
| **Date/Time Separator** | `; (semi-colon)` | |
| **Accounts** | your IBKR account ID (e.g. `U17457096`) | single-account setup |
| **Profit and Loss** | `Default` | |
| **Include Offsetting Trade/Cancel Pairs?** | `No` | |
| **Include Currency Rates?** | `No` | not used by the importer |
| **Include Audit Trail Fields?** | `No` | not used |
| **Display Account Alias?** | `No` | |
| **Breakout by Day?** | `No` | |

### Required sections — `Change in NAV`

Options: `Mark-to-Market`. Minimum required fields (everything else is optional but harmless):

- `Account ID`
- `From Date`
- `To Date`
- `Starting Value`
- `Ending Value` ← **REQUIRED** (read by `ibkr_sync_runner.py:175` → `ChangeInNAV.endingValue` to update `sentinel_config.json`)

The full 58-field list shown in your current config is fine — extra fields are ignored.

### Required sections — `Trades`

Options: `Execution`. Minimum required fields:

| # | Field | Why |
|---|---|---|
| 1 | Asset Class | metadata |
| 2 | Symbol | `ibkr_trade_importer.parse_trades_from_xml` reads this |
| 3 | Trade ID | dedupe key (`get_existing_trade_ids` uses this) |
| 4 | Trade Date | written to `trades.trade_date` |
| 5 | Quantity | sign-flipped by side in `_assign_campaign_ids` |
| 6 | TradePrice | written to `trades.price` |
| 7 | IB Commission | optional |
| 8 | Realized P/L | written to `trades.pnl_usd` |
| 9 | Buy/Sell | drives quantity sign |
| 10 | Order Time | optional |

## Required `.env` variables (on the Pi, in `/home/orangepi/sentinel_trading/.env`)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_ADMIN_ID=<your-chat-id>

# Supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<service-role-or-anon-key>

# IBKR Flex Query
IBKR_TOKEN=<flex-query-token>           # REQUIRED — bot_health turns 🔴 if missing
IBKR_QUERY_ID=<your-query-id>           # REQUIRED — see warning below

# IBKR throttle tuning (optional, defaults shown)
# IBKR_SENDREQ_COOLDOWN_SEC=120         # Sentinel-side cooldown between SendRequests
```

### ⚠️ Critical — `IBKR_QUERY_ID`

If `IBKR_QUERY_ID` is **absent** from `.env`, the code falls back to a hardcoded default `1501352` (in `ibkr_sync_runner.py`). **This default does NOT belong to your account** — leaving it in place means every sync queries the wrong Flex Query (or fails immediately with `1014 Query ID invalid`).

Verification options:

1. **No SSH** — Telegram → 🏥 בדיקת בריאות מערכת. Look at the "IBKR Query ID" row.
   - ✅ `IBKR Query ID — 1446152` → set correctly
   - 🔴 `IBKR Query ID — IBKR_QUERY_ID חסר ב-.env!` → fix `.env`

2. **SSH** — `docker exec sentinel-bot printenv IBKR_QUERY_ID` should print your actual Query ID.

3. **Logs** — every sync writes a config line:
   ```
   IBKR Sync — config: query_id=1446152, token=...4Bxc
   ```
   If you see `query_id=1501352 (DEFAULT — set IBKR_QUERY_ID env)` instead — the env var is missing.

## What the code does at sync time

1. Reads `IBKR_TOKEN` and `IBKR_QUERY_ID` from env (with the hardcoded fallback noted above).
2. Logs the effective config (Query ID + last-4 of token).
3. Checks the Sentinel-side SendRequest cooldown (default 120s). If we issued a successful SendRequest less than `IBKR_SENDREQ_COOLDOWN_SEC` ago, refuses to touch IBKR.
4. POSTs `SendRequest?t=$token&q=$query_id&v=3` to `interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest`.
5. On `ErrorCode` in response: returns `{"status": <class>, "code": <code>, "message": <hebrew>}` and does NOT consume the cooldown.
6. On success (valid `<ReferenceCode>`): records the cooldown timestamp, waits 15s, then polls `GetStatement` up to 3 times with 60s between retries.
7. Writes the XML to `/app/ibkr_reports/`, parses `<ChangeInNAV endingValue>` into `sentinel_config.json`, parses `<Trade>` elements for the trade importer.
8. Logs the Flex Query period from `<FlexStatement fromDate=... toDate=...>` and warns if span < 6 days.

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Every sync returns `1001 (temporary)` | `Period` set to `Month to Date` / `YTD` / `QTD` / `Today` | Change to `Last 30 Calendar Days` |
| Every sync returns `1014 fatal (Query ID לא תקין)` | `IBKR_QUERY_ID` missing from `.env` → uses default 1501352 | Add `IBKR_QUERY_ID=<yours>` to `.env`, restart containers |
| Every sync returns `1015 fatal (Token לא תקין)` | `IBKR_TOKEN` missing or expired | Regenerate token in IBKR Account Management, update `.env` |
| Every sync returns `1013 fatal (הגבלת IP)` | Token is configured for fixed IP and the Pi's external IP changed | Update Token IP whitelist in IBKR or remove restriction |
| Sync works manually but auto-sync at 07:00 fails | Auto-sync attempted before market open + Period is "Today" → empty result | Same as #1 — switch to fixed period |
| 409 conflict in Telegram bot, not IBKR-related | Another bot instance using the same `TELEGRAM_BOT_TOKEN` | Stop the duplicate (see Pi-deploy session 2026-05-14) |

## Architecture: how manual vs auto sync flow

Both run through `ibkr_sync_runner.run_ibkr_sync()`. Two entry points:

```
auto sync (every hour, 07:00-11:00 IL)
  └─ main.py loop @ scheduled block (line ~217)
       └─ run_ibkr_sync(log_fn=log)
            └─ writes /app/logs/sentinel_main.log

manual sync (Telegram developer menu)
  └─ telegram_bot.py callback handler
       └─ telegram_devops._run_manual_sync_thread (telegram-bot container)
            ├─ writes /app/ibkr_manual_trigger (atomic via tmp+rename)
            └─ polls /app/ibkr_last_sync_result.json (5min timeout)
                 ▲
                 │ written by:
                 │
  main.py loop @ trigger handler (line ~133)
       └─ run_ibkr_sync(log_fn=log)
            └─ writes /app/ibkr_last_sync_result.json (atomic)
            └─ bumps state.last_attempt_hour to prevent self-race
```

**Single SendRequest source**: both paths route through `main.py` in the `sentinel-bot` container. The cross-container race that caused intermittent 1001 (before commit 73af2da) is eliminated.

## Tests covering this contract

- `tests/test_ibkr_sync_full.py` — full SendRequest → GetStatement → NAV pipeline
- `tests/test_ibkr_1001_fixes.py` — cooldown, period detection, trigger handoff (27 tests)
- `tests/test_ibkr_config_visibility.py` — startup log surfaces Query ID + bot_health checks
- `tests/test_bot_health.py` — health check shape and individual check correctness
- `tests/test_ibkr_trade_importer.py` — XML field mapping + dedupe + campaign assignment

## Changelog

- 2026-05-14: Initial creation. Authors: IBKR Implementer + Senior + Mark. Triggered by 1001 investigation (commit 73af2da) and Lidor's request for spec+tests after Period mismatch surfaced via screenshot.
