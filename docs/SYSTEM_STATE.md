# Current System State

## Changes — 2026-05-10 (session 2: dashboard + telegram upgrade)

### dashboard.py
- `get_cached_market_regime()` new function: wraps SPY/QQQ fetch + compute_market_regime in `@st.cache_data(ttl=600)`. Prevents re-computation on every Streamlit re-run.
- `_warm_symbol_cache`: period changed from "6mo" to "1y". Fixes cache miss for MAE/MFE (`compute_mfe_mae` needs "1y") and for Trend Template (`compute_trend_template_full` needs "1y").
- `compute_live_portfolio_data`: SPY + QQQ added to parallel prefetch. TTL raised 180→300s. campaign_id added to live_positions dict.
- Campaign buy records lookup built after `actual_open_trades` for Add-on quality analysis.
- Command Center expander: expanded from 3 to 4 columns. Column 4: Trend Template 8 criteria + Add-on quality per position.
- New "🧠 Minervini Mentor" tab (tabs[4]): avg TT score, win/loss streak, strengths, weaknesses, dynamic coaching insights.
- Visual Journal: days held + R-per-day + actual vs planned risk metrics added per closed campaign.
- DB Manager moved from tabs[4] to tabs[5].
- Tabs definition updated to 6 tabs.

### engine_core.py (additive only)
- `generate_minervini_coaching(win_rate, expectancy_r, adj_rr, oversized_count, market_regime_status, streak_losses, total_r_net)`: returns list of Hebrew coaching insights based on Minervini methodology. Used by dashboard Mentor tab and Telegram /portfolio.

### telegram_bot.py
- Import: `import telegram_formatters as tf` added.
- `get_main_menu()` redesigned: 4 category buttons only (מצב תיק / ניתוח / יומן / עזרה).
- New functions: `get_portfolio_menu()`, `get_analysis_menu()`, `get_journal_menu()`.
- New handlers: "📊 מצב תיק", "🔬 ניתוח", "📚 יומן", "❓ עזרה", "⬅️ חזרה לתפריט ראשי", "🧠 ניתוח מינרביני מלא".
- `/mentor SYMBOL` command: calls `compute_trend_template_full()` and formats via `tf.fmt_minervini_trend_template()`.
- `mentor_symbol` user_state action: prompts for symbol then runs /mentor flow.
- Regime report: now uses `tf.fmt_regime_report()`.
- `/portfolio`: appends top 2 Minervini coaching insights at summary.
- All `analyze_symbol` responses now return `get_analysis_menu()` keyboard.

### telegram_formatters.py (NEW FILE)
- RTL formatting helpers for consistent, readable Hebrew Telegram messages.
- `fmt_position_card()`: unified position card for /portfolio.
- `fmt_summary_footer()`: portfolio summary block.
- `fmt_regime_report()`: market regime report.
- `fmt_minervini_trend_template()`: 8-criteria Trend Template output.
- Formatting rules: RTL markers, `▸` field prefix, em-dash separators, backtick numbers.



This file is a concise source of truth for the current repo state.

Update it after meaningful architecture, deployment, or workflow changes.

## Current date context

Last updated: 2026-05-10

## Production wiring

Docker Compose services (unchanged):

- `sentinel-bot` runs `python3 main.py`
- `telegram-bot` runs `python3 telegram_bot_secure_runner.py`
- `dashboard` runs `streamlit run dashboard.py`
- `risk-monitor` runs `python risk_monitor.py`

## Code state vs deployed state

**Session 1 changes (2026-05-09/10): deployed to Orange Pi.**
**Session 2 changes (2026-05-10): pushed to main (commit ad2d5c1) — NOT YET DEPLOYED.**

| Service | Code version | Deployed | Status |
|---------|-------------|---------|--------|
| sentinel-bot | v16.0 + ZoneInfo timezone fix | ✅ deployed | pending morning sync validation |
| dashboard | parallel pre-fetch + Minervini metrics + Mentor tab + performance fixes | ⚠️ NOT deployed | requires: docker compose up -d --build dashboard |
| engine_core | +5 Minervini functions + generate_minervini_coaching() | ⚠️ NOT deployed | bundled with dashboard rebuild |
| telegram-bot | hierarchical menus + /mentor + formatters | ⚠️ NOT deployed | requires: docker compose up -d --build telegram-bot |
| risk-monitor | market-hours cooldown + TZ fix | ✅ deployed | overnight spam fixed |

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

## Pending validation (next deploy)

1. Confirm IBKR sync fires at 07:xx Israel time (first real test of timezone fix).
2. Confirm /app/ibkr_reports/ directory created and XML file saved.
3. Confirm NAV updated in sentinel_config.json after morning sync.
4. Confirm no overnight alert spam from risk_monitor (market-hours gate working).
5. Verify Minervini Mentor tab renders correctly (after dashboard deploy).
6. Verify /mentor AAPL returns 8-criteria output (after telegram-bot deploy).
7. Verify hierarchical Telegram menus work end-to-end.
8. Measure dashboard load time on second interaction on Orange Pi.

## Pending follow-up items (not started)

1. Deploy session 2 changes: `docker compose up -d --build dashboard telegram-bot` on Orange Pi.
2. fmt_position_card() in /portfolio loop (Phase 4 Telegram refactor — medium risk).
3. analyze_addon_quality() in Visual Journal (closed campaigns).
4. Add target_price field to Supabase schema for true planned R:R (HIGH risk — separate task).
5. "Weekly mentor review" automated Telegram message (future feature).
6. Improve market regime with breadth indicators (% stocks above MA50, A/D line).
7. Per-closed-campaign Trend Template retrospective.

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

## Changes — 2026-05-10 (post-deployment fixes)

### Timezone fix (main.py + docker-compose.yml)
- Docker containers default to UTC. `datetime.now()` was returning UTC, not Israel time.
- Sync window ran at 10:00–14:00 Israel instead of the intended 07:00–11:00 Israel.
- Fix: added `TZ=Asia/Jerusalem` env to sentinel-bot and risk-monitor in docker-compose.yml.
- Fix: main.py now uses `ZoneInfo("Asia/Jerusalem")` explicitly.
- Fix: added `tzdata` to requirements.txt so ZoneInfo works on slim Docker images.

### Alert spam fix (risk_monitor.py)
- "Broken" status repeat alerts fired every 6 hours including overnight when market is closed.
- Fix: added `is_during_us_market_hours()` — repeat cooldown alerts (same status, same key)
  only fire during 11:00–21:00 UTC (≈ 14:00–00:00 Israel, Mon–Fri).
- Escalations and first-time alerts are unaffected and fire at any hour.

### Deployment instructions (immediate)
```bash
cd ~/sentinel_trading
git pull
docker compose up -d --build sentinel-bot risk-monitor
# Optional: force one-time sync today with new Query ID
rm ibkr_sync_state.json
docker compose restart sentinel-bot
```

## Quality audit — 2026-05-10

Full audit performed on all 2026-05-09 session changes.

Results:
- pytest: 24/24 passing — zero regressions
- engine_core.py new functions: logic verified correct
- main.py v16.0: state machine verified correct (window guard, per-hour guard, fail count, Telegram alerts)
- dashboard.py: parallel prefetch verified correct
- Bug fixed: `_warm_symbol_cache` now wraps calls in try/except to be truly exception-safe
  (previously the comment said exceptions were absorbed but `f.result()` would have re-raised them)

Code is production-ready pending server deployment.

## Rollback paths

| Service | Rollback command |
|---------|-----------------|
| sentinel-bot | `git revert <commit>` + `docker compose up -d --build sentinel-bot` |
| dashboard | `git revert <commit>` + `docker compose up -d --build dashboard` |
| engine_core | Revert is safe — no existing functions changed |
| Supabase | No schema changes made — no DB rollback needed |
