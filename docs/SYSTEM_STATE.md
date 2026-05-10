# Current System State

## Changes — 2026-05-10 (session 3: adaptive risk engine + proactive alerts)

### adaptive_risk_engine.py (NEW FILE)
- RISK_LADDER: `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` (min 0.35%, max 2.50%)
- `compute_closed_campaigns(df)`: extracts closed campaigns (net_qty ≈ 0) from trades DataFrame, sorted newest→oldest.
- `compute_adaptive_risk(closed_camps, current_risk_pct, nav)`: weighted win rate algorithm, streak detection, step-up/step-down logic, returns full recommendation dict.
- `update_risk_pct(new_pct)`: reads/writes `sentinel_config.json` atomically.
- `log_risk_journal(entry)`: appends decisions to `risk_journal.json` (500 entries).
- `mark_adherence(rec_pct, actual_pct, followed, reason="")`: updates latest entry in `risk_recommendations.json`.
- `compute_adherence_stats()`: returns total/evaluated/followed/not_followed/adherence_pct + last 10 icons.
- `_log_recommendation(rec)`: auto-called by `compute_adaptive_risk`, logs to `risk_recommendations.json` (200 entries).

### engine_core.py
- `compute_market_regime`: now returns raw `signals` dict inside `data` key: spy_close, spy_ma20, spy_ma50, qqq_close, qqq_ma20, four boolean flags, score, max_score. Backward compatible.

### telegram_formatters.py
- `fmt_regime_report`: now renders raw SPY/QQQ signals with ✅/❌ and actual $ values under "📐 בסיס ציון N/4".
- `fmt_adaptive_risk_block` (new): renders adaptive risk recommendation block (heat score, streaks, win rates, directional recommendation with % and $).

### risk_monitor.py
- `import adaptive_risk_engine as are` added.
- `send_telegram_with_keyboard(text, markup)` helper added.
- Proactive adaptive risk alert at end of `main()`: computes recommendation, skips if direction=="hold", throttles to once per 24h per direction, sends InlineKeyboard with `risk_confirm|YES|{rec_pct}|{curr_pct}` and `risk_confirm|NO|{rec_pct}|{curr_pct}` callbacks. State saved in `risk_monitor_state.json["risk_alert"]`.

### telegram_bot.py
- `import adaptive_risk_engine as are` added.
- `risk_confirm|YES` callback: calls `are.update_risk_pct`, `are.mark_adherence(followed=True)`, `are.log_risk_journal`, edits original message to show confirmation.
- `risk_confirm|NO` callback: sets `user_state[chat_id]["action"] = "risk_reject_reason"`, edits message to prompt for reason.
- `risk_reject_reason` state handler: collects reason, calls `are.mark_adherence(followed=False, reason=...)`, `are.log_risk_journal`, confirms to user.
- `/stats` command: calls `are.compute_adherence_stats()`, displays formatted adherence report.
- `/help` text updated to include `/stats`.
- Adaptive risk block appended to both `🌡️ משטר שוק` and `📊 חדר מצב` handlers.

### Runtime files (auto-created, not committed to git)
- `risk_recommendations.json` — recommendation log, last 200 entries, `followed` field updated by callbacks.
- `risk_journal.json` — full decision journal, last 500 entries, written on YES/NO response.

---

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
**Session 3 changes (2026-05-10): committed locally (5f85069) — NOT YET PUSHED OR DEPLOYED.**

| Service | Code version | Deployed | Status |
|---------|-------------|---------|--------|
| sentinel-bot | v16.0 + ZoneInfo timezone fix | ✅ deployed | pending morning sync validation |
| dashboard | parallel pre-fetch + Minervini metrics + Mentor tab + performance fixes | ⚠️ NOT deployed | requires: docker compose up -d --build dashboard |
| engine_core | +5 Minervini functions + coaching + regime signals | ⚠️ NOT deployed | bundled with dashboard rebuild |
| telegram-bot | hierarchical menus + /mentor + formatters + adaptive risk + /stats | ⚠️ NOT deployed | requires: docker compose restart telegram-bot |
| risk-monitor | market-hours cooldown + TZ fix + proactive risk alerts | ⚠️ NOT deployed | requires: docker compose restart risk-monitor |

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

1. **Deploy sessions 2+3**: `git push` then on Orange Pi: `git pull && docker compose up -d --build dashboard && docker compose restart telegram-bot risk-monitor`
2. Wire `mark_adherence` to sentinel_config.json change detection (detect manual risk_pct edits outside Telegram).
3. Dashboard integration: show algorithm-suggested risk % vs actual + deviation alert.
4. fmt_position_card() in /portfolio loop (Phase 4 Telegram refactor — medium risk).
5. analyze_addon_quality() in Visual Journal (closed campaigns).
6. Add target_price field to Supabase schema for true planned R:R (HIGH risk — separate task).
7. "Weekly mentor review" automated Telegram message (future feature).
8. Improve market regime with breadth indicators (% stocks above MA50, A/D line).
9. Per-closed-campaign Trend Template retrospective.

## Deployment instructions (sessions 2 + 3 combined)

Run on Windows first:
```bash
git push origin main
```

Then on Orange Pi:
```bash
cd ~/sentinel_trading
git pull
docker compose up -d --build dashboard
docker compose restart telegram-bot risk-monitor
docker compose logs telegram-bot --tail=20
docker compose logs risk-monitor --tail=20
```

`sentinel-bot` does NOT need restart (no changes to main.py).

Smoke tests after deployment:
- `🌡️ משטר שוק` in Telegram → should show ✅/❌ per SPY/QQQ criterion + adaptive risk block
- `📊 חדר מצב` → should show adaptive risk block at bottom
- `/stats` → should return adherence report (empty is fine initially)
- Open dashboard → verify Minervini Mentor tab renders, positions load faster
- Verify /mentor AAPL returns 8-criteria output
- Run `pytest -q` on server to confirm 24/24 pass

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
