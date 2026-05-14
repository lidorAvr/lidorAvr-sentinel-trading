# Deploy Guide — main → Orange Pi (2026-05-14)

Operator-facing. Step-by-step.

## Why

Pi has been running stale code (Pi-backup tip = `6c8288c`, 2026-05-12). Main has all that Pi has + Sprint 6/7/8 (audit_logger, ATR trail buffer, drawdown auto-cut, mgmt_notes APPEND, heat-bar emoji, healthchecks, autoheal, daily digest, sizing-leak alert, 1321 tests). See `BEHAVIOR_DELTA_PI_2026_05_14.md` for the full user-visible change list.

## Recommended deploy window

Outside US market hours: weekday after 21:00 UTC (00:00 Israel) or any weekend hour. State-file mitigation eliminates the alert-burst risk, but a quiet window still gives a calmer cutover.

## Pre-flight (on the Pi, while containers still running)

```bash
ssh orangepi@orangepi3-lts
cd ~/sentinel_trading
```

### 1. Stash any local runtime modifications

```bash
git status
# expected modifications: risk_monitor_state.json, sentinel_config.json (runtime state)

git stash push -m "pre-deploy-2026-05-14" risk_monitor_state.json sentinel_config.json
# (we will restore them after checkout)
```

### 2. Fetch and checkout the integration branch

```bash
git fetch origin
git checkout claude/integration-pi-and-main-2026-05-14
git log --oneline -3
# expect to see the integration commit on top of main
```

### 3. Restore stashed state files

```bash
git stash pop
# you should now be on the integration branch with your state files in place
```

### 4. Backup state files (rollback insurance)

```bash
cp risk_monitor_state.json risk_monitor_state.json.pre-deploy.$(date +%Y%m%d-%H%M)
cp sentinel_config.json   sentinel_config.json.pre-deploy.$(date +%Y%m%d-%H%M)
ls -la *.pre-deploy.*
```

### 5. Pre-populate state-file timestamps (mitigates alert burst)

```bash
python3 scripts/prepare_pi_state_for_deploy.py risk_monitor_state.json
# expect: "Backed up original to risk_monitor_state.json.pre-mitigation.<ts>"
# expect: "Seeded N positions with missing keys (M keys total). Wrote risk_monitor_state.json."
```

### 6. Verify migration 002 is applied to Supabase

```bash
python3 migrations/verify_migrations.py
# expect: "audit_log: ✅ exists" (or similar)
```

If `audit_log` does not exist:
1. Open Supabase SQL editor.
2. Paste contents of `migrations/002_audit_log.sql`.
3. Execute.
4. Re-run `python3 migrations/verify_migrations.py`.

If you skip this step: the bot will not crash (`audit_logger.log_action` is fail-open) but compliance trail will be silently absent. **Recommended: apply before deploy.**

### 7. Confirm autoheal sidecar (optional, for healthcheck-driven restart)

```bash
docker ps -a | grep autoheal
# if no row: container restarts on health-fail will not happen automatically.
# this is acceptable; you can add the autoheal sidecar later.
```

## Deploy

### 8. Stop everything cleanly (avoids 409 Telegram conflict from container overlap)

```bash
docker compose down
```

### 9. Build and start with the integration branch checked out

```bash
docker compose up -d --build
```

Build takes ~5 minutes on the Pi (multi-stage builds for 5 services).

### 10. Tail logs for first 5 minutes

```bash
docker logs --since=5m -f telegram-bot
# Ctrl+C, then:
docker logs --since=5m risk-monitor 2>&1 | head -60
docker logs --since=5m sentinel-bot 2>&1 | head -30
docker logs --since=5m dashboard 2>&1 | head -30
docker logs --since=5m reporting-service 2>&1 | head -30
```

## Verification — do these in order

### V1. Telegram bot responsiveness (within 1 min of start)

In Telegram, send: `/portfolio`

Expected: a portfolio report within 5 seconds. Hebrew, RTL, includes heat-bar emoji squares (🟢⚪).

If no response:
```bash
docker logs --since=2m telegram-bot 2>&1 | grep -E "409|Conflict|Error" | tail
```
If 409: another bot instance is running with the same token (see earlier troubleshooting session about ma-alerts — different token, not the cause).

### V2. No state-file alert burst

```bash
docker logs --since=5m risk-monitor 2>&1 | grep -cE "📢|🚨|⚠️"
# expect: 0–3 (only true escalations should fire)
```

If > 5: the pre-populate helper may have failed. Check `risk_monitor_state.json` — every position should have `last_state_alert_ts` set to a recent timestamp.

### V3. Healthchecks reporting

```bash
docker ps
# expect: "(healthy)" annotation next to each service after ~30 sec
```

If "(unhealthy)": check `docker inspect <container> --format '{{.State.Health.Log}}'`.

### V4. audit_log writes (only if you applied migration 002)

Trigger one addon confirm via Telegram (e.g., `/addon` flow). Then in Supabase SQL editor:

```sql
SELECT count(*) FROM audit_log WHERE created_at > now() - interval '5 min';
```

Expected: `>= 1`.

### V5. New RISK_LADDER values present

In Telegram: `/portfolio` → look at the recommended `risk_pct`. It should be a value in `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (not 0.35 or 2.50).

### V6. IBKR sync still works (if you have time)

In Telegram: developer menu → manual sync. Watch logs:
```bash
docker logs --since=2m sentinel-bot 2>&1 | tail -30
```
Expected: no `NameResolutionError` (DNS fix is in main), trades imported message ("נמצאו N טריידים חדשים") if there are new trades.

## Rollback

**Trigger any of:**
- Telegram bot doesn't respond to `/portfolio` for 10 min
- Alert burst > 5 in first 5 min (state mitigation failed)
- Healthchecks consistently red for 10 min
- Any user-visible regression you don't want to debug live

**Procedure:**
```bash
cd ~/sentinel_trading
docker compose down

# Restore Pi-backup tip
git checkout 6c8288c

# Restore state files from your pre-deploy backup
ls -la *.pre-deploy.*
cp risk_monitor_state.json.pre-deploy.YYYYMMDD-HHMM risk_monitor_state.json
cp sentinel_config.json.pre-deploy.YYYYMMDD-HHMM sentinel_config.json

# Rebuild old code
docker compose up -d --build

# Verify
docker logs --since=2m -f telegram-bot
```

**Notes**:
- Migration 002 is non-reversible. The `audit_log` table is write-only and harmless if Pi-backup code never reads it.
- `mgmt_notes` rows that received APPEND `[YYYY-MM-DD HH:MM]` blobs are read by Pi-backup code as opaque strings — no break.

## After successful deploy — optional follow-ups

1. **Merge integration branch into main** (docs-only; harmless):
   ```bash
   # locally:
   gh pr create --base main --head claude/integration-pi-and-main-2026-05-14 \
       --title "docs+helper: Pi deploy guide & state-file mitigation" \
       --body "Adds deploy guide + state pre-population script. No production code changes."
   ```
2. **Delete the Pi backup branch** (only after a few weeks of stable main run):
   ```bash
   git push origin --delete backup/pi-production-2026-05-13
   ```
   (or keep it as a museum piece — it's small.)
3. **Document the new daily digest behavior** for yourself so the 21:00 UTC Telegram message isn't a surprise next time.

## Total expected time

| Phase | Time |
|---|---|
| Pre-flight | 5–10 min |
| Build | 5 min |
| Verification | 10 min |
| **Total** | **~25 min** |
