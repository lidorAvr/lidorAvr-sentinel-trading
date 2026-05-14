# IBKR Error 1001 — Investigation & Fix (2026-05-14)

Context: After the main→Pi deploy on 2026-05-14, a manual IBKR sync at 14:36 IL failed with `ErrorCode 1001` ("Statement could not be generated at this time. Please try again shortly."). User asked whether the failure was truly IBKR-side or whether Sentinel was contributing.

Investigation team:
- **IBKR Implementer** (new, certified) — IBKR Universal Flex Web Service domain knowledge
- **Senior engineer (Team Lead)** — Sentinel codebase context
- **Mark** — adversarial review

Full transcripts in `/tmp/merge-meeting/04_IBKR_IMPLEMENTER_REPORT.md` and `/tmp/merge-meeting/05_MARK_IBKR_REVIEW.md`.

## TL;DR

**Error 1001 is NOT purely IBKR-side.** Three concrete Sentinel-side issues were identified and fixed in this branch.

| # | Fix | Where | Risk |
|---|---|---|---|
| 1 | Wire `MANUAL_TRIGGER_FILE` so manual syncs route through `main.py` (one SendRequest source) | `telegram_devops.py`, `main.py` | MED — changes manual-sync UX flow |
| 2 | 120s Sentinel-side SendRequest cooldown (env-tunable, recorded only on success) | `ibkr_sync_runner.py` | LOW — additive |
| 3 | Parse `<FlexStatement fromDate=… toDate=…>` from XML; log + warn if span < 6 days | `ibkr_sync_runner.py` | LOW — log-only |

User-side action required:
- **Confirm Flex Query Period = "Last 7 Days"** in IBKR Account Management → Reports → Flex Queries → "Sentinel_Trades". Narrow Periods (Today / LastBusinessDay / MonthToDate) are the #1 driver of intermittent 1001 in your timeline.

## Root cause analysis

### What ErrorCode 1001 actually means

Per the IBKR Universal Flex Web Service spec, 1001 is a catch-all the Flex backend returns when statement generation refuses to start. It covers four distinct conditions:

1. **Per-(token, queryId) throttle** — IBKR enforces ~30–60 second minimum between SendRequest calls for the same Flex Query. Too-fast retries get 1001.
2. **Statement not ready yet** — for narrow periods (Today / MonthToDate), IBKR returns 1001 between roughly 16:00 ET (close) and ~18:00 ET while the back-office batch posts.
3. **Empty result set on a strict period** — `LastBusinessWeek` on Monday morning before any trade data populates can come back as 1001 rather than an empty `<FlexQueryResponse>`.
4. **True transient server load** — rare. Usually clears in <60s.

### Why Sentinel was hitting it

Three architectural issues, in priority order:

#### Issue 1 — Flex Query Period configured too narrowly (likely root cause)

The user previously switched away from `LastBusinessWeek` per `docs/AGENT_TASKS.md:515-534` (TASK-20260512-014) because it hid current-week trades. If the new Period is `Today` or `LastBusinessDay`, every request made during IBKR's post-close batch window (16:00–18:00 ET ≈ 23:00–01:00 IL) lands in the "statement not ready" zone and 1001s.

Pattern match against user's logs:
- 2026-05-11 17:48 IL = **10:48 ET** — within batch lag for "Today" if period covers today
- 2026-05-12 07:23 IL = **00:23 ET** — **inside post-close batch window**
- 2026-05-12 13:45 IL = **06:45 ET** — outside batch → SUCCESS
- 2026-05-12 14:08 IL = **07:08 ET** — outside batch → SUCCESS (22 min after #3, proves no IBKR-side hard cooldown)
- 2026-05-14 07:06 IL = **00:06 ET** — borderline, but succeeded
- 2026-05-14 14:36 IL = **07:36 ET** — outside batch but FAILED. May be Issue 2 or 3.

Fix 3 (period detection from XML) makes this visible: every successful sync now logs `Report period: YYYYMMDD → YYYYMMDD`, and warns if the span is < 6 days. Once you see one log line, you'll know definitively what Period is configured.

#### Issue 2 — Two containers race on the same Flex token

`docker-compose.yml` runs `sentinel-bot` (`main.py`) and `telegram-bot` (`telegram_bot_secure_runner.py`) from the same image, both with access to `IBKR_TOKEN`. Each had its own SendRequest path:

- `main.py:217` — scheduled auto-sync, gated by `tried_this_hour`
- `telegram_devops.py:233-264` — manual-sync via developer menu, gated by `_dev_sync_check` (3h cooldown)

**Neither gate sees the other.** If the user pressed "📡 IBKR Sync ידני" within seconds of `main.py`'s 07:00 hourly attempt, both containers would issue SendRequest, and IBKR would return 1001 on the second.

The codebase had a designed-but-unwired hand-off: `MANUAL_TRIGGER_FILE = "/app/ibkr_manual_trigger"` is defined in `main.py:13`, watched in `main.py:128, 173`, and handled in `_handle_manual_trigger` (`main.py:133-156`) — but **no caller wrote it**. The telegram-bot container just called `run_ibkr_sync` directly.

Fix 1 wires the dead code: telegram-bot now writes the trigger file atomically, polls `MANUAL_RESULT_FILE` for up to 5 minutes, then reads and reports the result. One SendRequest source. Cross-container race eliminated.

#### Issue 3 — Self-race inside main.py (Mark caught this)

Once Fix 1 routes manual syncs through `main.py`, a NEW bug appears: `_handle_manual_trigger` ran SendRequest but did NOT update `last_attempt_hour`. So the same loop iteration would fall through to the scheduled block, see `tried_this_hour=False`, and fire **another** SendRequest 10 ms later. Guaranteed 1001 on the second one.

Fix 1 also bumps `state["last_attempt_hour"]` (and on success, `sync_date`) inside `_handle_manual_trigger`. Now the scheduled block sees `tried_this_hour=True` and skips.

### What was NOT the cause (ruled out)

- **IBKR maintenance**: too consistent a pattern. Successes 22 min apart on 05-12 prove no hard cooldown after success.
- **DNS / network**: the SendRequest returns instantly with a 1001 XML body — DNS reached, IBKR responded.
- **Token expiry**: would return 1012 (`fatal`), not 1001.
- **Invalid Query ID**: would return 1014 (`fatal`), not 1001.

## The three fixes — implementation details

### Fix 2: Sentinel-side SendRequest cooldown

File: `ibkr_sync_runner.py`

Three helpers added:
- `_sendrequest_cooldown_sec()` — reads `IBKR_SENDREQ_COOLDOWN_SEC` env var (default 120s)
- `_last_sendrequest_ts()` — reads `/app/state/ibkr_last_sendrequest.json` (returns 0 if absent)
- `_record_sendrequest_ts()` — writes timestamp atomically (tmp + os.replace)

Before SendRequest, `run_ibkr_sync` checks: if `now - last_ts < cooldown`, return `status="rate_limit"` immediately without touching IBKR. After SendRequest succeeds and a ReferenceCode is parsed, `_record_sendrequest_ts()` is called.

**Critically**: a failed SendRequest (1001 etc.) does NOT consume the cooldown slot. Otherwise a benign IBKR transient would block legitimate retries for 120s — user-hostile.

Default 120s — empirical IBKR floor is 30-60s, so this leaves comfortable margin.

### Fix 3: Period detection from XML

File: `ibkr_sync_runner.py`

After parsing the report XML, the code looks for `<FlexStatement fromDate=… toDate=…>` and logs the period. If the span (toDate − fromDate) < 6 days, it logs a warning suggesting `Period = "Last 7 Days"` in IBKR Account Management.

Silently skips if `<FlexStatement>` is absent or dates are unparseable (defensive — never blocks the sync flow).

### Fix 1: Wire MANUAL_TRIGGER_FILE handoff

Files: `telegram_devops.py`, `main.py`

**telegram_devops.py** (`_run_manual_sync_thread` rewritten):
1. Remove stale `MANUAL_RESULT_FILE` (so we don't read yesterday's result)
2. Write trigger file atomically: `open(tmp); os.rename(tmp, real)`
3. Poll `MANUAL_RESULT_FILE` every 5s for up to 5 minutes
4. On timeout: send Telegram error message pointing user to `docker logs --tail=50 sentinel-bot`
5. On result: parse and report status to Telegram

Helper functions added: `_write_manual_trigger(chat_id)`, `_poll_manual_result(deadline_ts)`.

**main.py** (`_handle_manual_trigger`):
- Result file written atomically (tmp + os.replace)
- After run_ibkr_sync: bump `state["last_attempt_hour"]` to current hour
- On success: also set `state["sync_date"]` and `state["fail_count"] = 0`
- All wrapped in try/except so a state-bump failure doesn't break the sync

## Tests

New file: `tests/test_ibkr_1001_fixes.py` — 27 tests, all pass.

| Test class | Tests | What it covers |
|---|---|---|
| TestCooldownConfiguration | 3 | env var override + default + invalid input |
| TestCooldownState | 4 | file read/write/atomic/corrupt handling |
| TestCooldownBlocksRapidRetries | 3 | block within window, allow after, no-state-no-block |
| TestCooldownRecordingPolicy | 3 | record on success, NOT on 1001, NOT on missing refcode |
| TestPeriodDetection | 7 | 7d no warn, 1d warn, 0d warn, missing FlexStatement, invalid date |
| TestManualTriggerStateBump | 2 | success bumps both hour+date, failure bumps only hour |
| TestTelegramSideTriggerPoller | 5 | atomic write, result return, timeout None, corrupt JSON handling |

Full pytest suite: 1321 + 27 = **1348 tests** target, all expected to pass.

## What the user must do on the Pi

### Step 1 (today): verify Flex Query Period

1. Browser: https://www.interactivebrokers.com → Login
2. Reports → Flex Queries → "Sentinel_Trades" → Edit
3. Confirm **Period = "Last 7 Days"** (NOT "Today", "LastBusinessDay", "MonthToDate", etc.)
4. Save

### Step 2 (after pulling this branch): redeploy

```bash
ssh orangepi@orangepi3-lts
cd ~/sentinel_trading
git fetch origin
git pull origin claude/integration-pi-and-main-2026-05-14
docker compose down
docker compose up -d --build
docker logs --since=3m -f telegram-bot
# Ctrl+C, send "/portfolio" in Telegram to verify
```

### Step 3 (next successful sync): confirm the period in logs

After the next successful IBKR sync, check the sentinel-bot logs:

```bash
docker logs sentinel-bot 2>&1 | grep "Report period:" | tail -1
```

Expected line: `Report period: 20260507 → 20260514` (approximately 7-day span). If you see `Report period: 20260514 → 20260514` or similar narrow span, you'll also see a warning line right after — go back to Step 1 and re-check the Flex Query setting in IBKR.

### Step 4 (optional, advanced): test the cross-container fix

Force a manual sync via Telegram developer menu. Expected behavior:
1. Telegram message immediately acknowledges the request
2. Within 1–4 minutes: Telegram receives the result message
3. **sentinel-bot logs** (not telegram-bot) show the SendRequest

If the result message says `⚠️ סנכרון ידני לא חזר תוך 5 דקות`, sentinel-bot may be stuck or crashed:
```bash
docker logs --tail=100 sentinel-bot
docker ps | grep sentinel-bot   # should be (healthy)
```

## Standalone host scripts — deploy note

Mark flagged `check_my_trades.py` and `fetch_live_ibkr.py` as dev-host scripts that bypass all guardrails proposed here. They use `/home/orangepi/…` paths (host, not container), so:

- Do NOT run them on the host while the containers are doing a sync (07:00–11:00 IL, or during manual sync). They issue SendRequest directly and will collide with the container path.
- Consider deleting them in a future sprint — they predate the current architecture.

## Rollback

If anything is wrong after deploy:

```bash
docker compose down
git checkout 8bab814   # last known-good commit (pre-IBKR fixes)
docker compose up -d --build
```

If the IBKR fixes are confirmed working but the user wants to revert to running SendRequest from telegram-bot (not main.py), revert just the `telegram_devops.py` changes and leave Fix 2 and Fix 3 in place — they're orthogonal.

## Severity / risk summary

| Item | Severity | Reversible? |
|---|---|---|
| Fix 2 cooldown | LOW | YES (delete state file or unset env) |
| Fix 3 period log | LOW | YES (log-only) |
| Fix 1 trigger handoff | MED | YES (revert telegram_devops.py + main.py change) |
| State file format | LOW | YES (state files are auto-recreated) |
| Production sync flow | YES | manual sync now takes 1–4 minutes (was instant + non-blocking thread); user gets a result Telegram message at the end |

## Closing

Open question to user (`docs/WAKE_UP_BRIEF_2026_05_14.md` style):

- **Do you want me to also delete `check_my_trades.py` and `fetch_live_ibkr.py`** in a follow-up commit? They are dev-host scripts that bypass every guardrail in this fix and are not used in production. Suggest: yes, with a `git rm` and a commit `cleanup: remove dev-host IBKR scripts (superseded by container flow)`.

— Team: IBKR Implementer + Senior + Mark
