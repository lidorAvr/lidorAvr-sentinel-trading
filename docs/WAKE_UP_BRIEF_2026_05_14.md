# Wake-Up Brief — 2026-05-14
**For: Lidor. Read this first when you wake.**

## TL;DR

The "merge between Pi and main" you asked for is unnecessary. **The Pi backup is a stale subset of main.** Every Pi commit (Phase 4 refactor, IBKR auto-import, Runner Mode buttons, ALGO threshold fix, DNS infra, importer fix) was independently merged to main via PRs at some point. Pi has nothing main lacks.

The team's deliverable is now a **safe deployment path of `origin/main` to the Pi**, with mitigations for 9 risks identified by Mark.

## What's ready for you

Branch: **`claude/integration-pi-and-main-2026-05-14`** — pushed to GitHub.
Contains main + 4 new files (3 docs + 1 helper script). Zero production code changes vs main.

| File | Purpose |
|---|---|
| `docs/WAKE_UP_BRIEF_2026_05_14.md` | This file |
| `docs/DEPLOY_GUIDE_PI_2026_05_14.md` | Step-by-step commands to run on the Pi |
| `docs/BEHAVIOR_DELTA_PI_2026_05_14.md` | Every user-visible change main introduces |
| `docs/MEETING_TRANSCRIPT_2026_05_14.md` | Plan v1 + Mark's review + Plan v2 (audit trail) |
| `scripts/prepare_pi_state_for_deploy.py` | Pre-populates state-file timestamps to prevent alert burst |
| `scripts/test_prepare_pi_state.py` | 6 tests for the helper script (all pass) |

## What you need to decide before deploying

These are user-only decisions. The team won't override them.

1. **RISK_LADDER tightens** from `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` → `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`. Smaller floor (0.25%), no 2.50% top. Your active campaigns may get a different recommendation on the next adaptive cycle. **Are you OK with the new ladder?** If not, override in `sentinel_config.json` after deploy.

2. **Drawdown auto-cut** kicks in at 30d cumulative PnL ≤ -8% NAV (forces risk to 0.40%, overriding heat). **Are you currently in -8% drawdown?** If yes, you'll see this fire on the first cycle. If you don't want it, comment out the call in `adaptive_risk_engine.py:drawdown_auto_cut_recommendation` after deploy.

3. **Daily Digest** is a NEW Telegram message at 21:00–22:00 UTC weekdays (~00:00–01:00 Israel). You haven't seen it before. **Want to keep it?** If not, set `DAILY_DIGEST_UTC_HOUR_END = 0` in `risk_monitor.py` to disable.

4. **dev_pin gate REMOVED** on developer menu. Not a security regression in practice — `telegram_bot_secure_runner.py` still gates the entire bot to your `TELEGRAM_ADMIN_ID`. PIN was 2nd factor; admin-id check is the real gate.

## Pre-flight verified by the team

- ✅ pytest on integration branch: **1321 tests pass, 0 failures, 1 cosmetic warning**
- ✅ pre-populate helper script: **6/6 tests pass**
- ✅ Pi backup contains zero files unique vs main (verified via `comm -13`)
- ✅ `ibkr_trade_importer.py` is byte-identical between main and Pi backup (SHA `d4c7835`)
- ✅ Migration 002 SQL in repo, `verify_migrations.py` ready
- ✅ Rollback target identified: Pi backup tip `6c8288c`

## The deployment in 5 commands (full guide in DEPLOY_GUIDE_PI_2026_05_14.md)

```bash
ssh orangepi@orangepi3-lts
cd ~/sentinel_trading
git fetch origin
git checkout claude/integration-pi-and-main-2026-05-14

# Pre-flight (the helper migrates your state file safely)
python3 scripts/prepare_pi_state_for_deploy.py risk_monitor_state.json
python3 migrations/verify_migrations.py

# Deploy
docker compose down && docker compose up -d --build

# Verify
docker logs --since=2m -f telegram-bot
# Send /portfolio in Telegram
```

## Open question for you

- **Should the team also merge `claude/integration-pi-and-main-2026-05-14` into `main` after you confirm the deploy is healthy?** I haven't done this autonomously. The branch sits next to main; merging it is a docs-only commit (the helper script + 4 docs) and doesn't affect production code. Your call.

## Honest caveats

- The team did not run the deploy itself — only verified the artifacts.
- pytest passed in the sandbox, but the sandbox blocks network (pytest-socket). Live IBKR/Telegram/Supabase paths will only be exercised on the Pi.
- The `BEHAVIOR_DELTA` doc captures every change I could trace from diffs. If a user-flow surfaces something not on the list, treat as a bug to flag.

— Team Lead, on behalf of the Pi-Integration crew
