# Current System State

This file is a concise source of truth for the current repo state.

Update it after meaningful architecture, deployment, or workflow changes.

## Current date context

Last updated: 2026-05-09

## Production wiring

Docker Compose services (unchanged):

- `sentinel-bot` runs `python3 main.py`
- `telegram-bot` runs `python3 telegram_bot_secure_runner.py`
- `dashboard` runs `streamlit run dashboard.py`
- `risk-monitor` runs `python risk_monitor.py`

## Code state vs deployed state

**Important: all changes below are committed and pushed to `main` but NOT yet deployed to the Orange Pi server.**

The user has chosen to batch all changes before a single deployment.

| Service | Code version | Deployed version | Gap |
|---------|-------------|-----------------|-----|
| sentinel-bot | v16.0 (smart sync) | v15.0 (old sync) | main.py fully rewritten |
| dashboard | parallel pre-fetch + Minervini metrics | old sequential | dashboard.py updated |
| engine_core | +5 new Minervini functions | old | engine_core.py additive only |
| telegram-bot | unchanged | unchanged | none |
| risk-monitor | unchanged | unchanged | none |

## What changed in this session (2026-05-09)

### main.py — v16.0

- Sync window: 07:00–11:00 Asia/Jerusalem only (was: hour >= 6 always)
- One attempt per clock-hour (was: retry every 15 min with no limit)
- State in /app/ibkr_sync_state.json (was: plain text date file)
- XML reports saved to /app/ibkr_reports/, last 3 kept (was: discarded after parse)
- Telegram success notification + per-attempt failure warnings
- Telegram alert after 3 failed attempts

### dashboard.py

- prefetch_symbols_parallel(): all symbols fetched in parallel via ThreadPoolExecutor
- compute_live_portfolio_data now returns Minervini metrics per position:
  InitRisk_USD, InitRisk_Pct, SizingGrade, DaysHeld, R_per_Day, EfficiencyLabel,
  EfficiencyColor, MFE_R, MAE_R, MFE_Pct, MAE_Pct
- Planned vs Actual expander in Command Center tab (per open position)
- AI context export no longer re-calls get_live_price() (uses live_df cache)

### engine_core.py — additive only, no existing functions changed

- compute_initial_risk_metrics(): risk sizing grade per Minervini 1-2.5% NAV rule
- compute_r_efficiency(): R-per-day capital efficiency label and color
- compute_mfe_mae(): Max Adverse/Favorable Excursion from 1y price history
- compute_trend_template_full(): complete 8-criteria Minervini Trend Template
- analyze_addon_quality(): validates pyramiding was done above entry price only

### tests/

- tests/test_trade_metrics.py: 21 new deterministic unit tests
- Full test suite: 24/24 passing

## Telegram hardening status

Status: implemented in code, pending server deployment verification.

Protection layer: `telegram_bot_secure_runner.py`

- admin-only access through TELEGRAM_ADMIN_ID
- rate limiting and cooldown
- data-source disclosure note for sensitive reports

Open validation:
- Pull latest `main` on Orange Pi server.
- Rebuild/restart `telegram-bot`.
- Test Telegram commands and rate limiting.

## Known high-risk areas (unchanged)

1. `telegram_bot.py` is long and should not be rewritten wholesale.
2. NAV/config path consistency must be validated on the server after deployment.
3. Campaign/R calculations are protected by tests — do not change without test coverage.
4. Supabase write flows must remain explicit and traceable.
5. Telegram output must remain Hebrew-friendly and not too verbose.

## Pending follow-up items (not started)

1. Wire compute_trend_template_full() output into dashboard UI.
2. Wire analyze_addon_quality() results into dashboard (open + closed campaigns).
3. Add planned-vs-actual section to Visual Journal tab (closed campaigns).
4. Add target_price field to Supabase schema for true planned R:R (HIGH risk — separate task).
5. Improve market regime with breadth indicators (% stocks above MA50, A/D line).
6. NAV auto-update verification: confirm IBKR XML ChangeInNAV node correctly updates sentinel_config.json.

## Deployment instructions (when ready)

Run on Orange Pi:

```bash
cd ~/sentinel_trading
git pull
docker compose up -d --build sentinel-bot dashboard
docker compose logs -f sentinel-bot
docker compose logs -f dashboard
```

Only rebuild affected services. `telegram-bot` and `risk-monitor` are unchanged.

Smoke tests after deployment:
- Check /app/ibkr_sync_state.json exists and updates
- Check /app/ibkr_reports/ directory is created
- Open dashboard and verify positions load faster
- Verify planned-vs-actual section appears for open positions
- Run pytest -q on server to confirm tests pass

## Rollback paths

| Service | Rollback command |
|---------|-----------------|
| sentinel-bot | `git revert <commit>` + `docker compose up -d --build sentinel-bot` |
| dashboard | `git revert <commit>` + `docker compose up -d --build dashboard` |
| engine_core | Revert is safe — no existing functions changed |
| Supabase | No schema changes made — no DB rollback needed |
