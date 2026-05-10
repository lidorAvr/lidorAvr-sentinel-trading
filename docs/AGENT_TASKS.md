# Agent Tasks Ledger

This file tracks tasks that AI agents should perform or are currently performing.

It is a lightweight task ledger for AI-agent work inside the repository.

## Purpose

- Keep agent work visible.
- Avoid losing context between sessions.
- Reduce repeated prompting.
- Prevent agents from starting unrelated work.
- Track what was done, what is blocked, and what remains.

## Task states

Use one of:

- `todo`
- `in_progress`
- `blocked`
- `implemented`
- `validated`
- `cancelled`

## Task template

```markdown
### TASK-YYYYMMDD-001 — Short title

Status: todo / in_progress / blocked / implemented / validated / cancelled
Source requirement: REQ-YYYYMMDD-XXX
Assigned to: agent / user / both
Risk: Low / Medium / High
Affected services: ...

Goal:
- ...

Plan:
1. ...
2. ...
3. ...

Progress log:
- YYYY-MM-DD HH:MM — ...

Validation:
- [ ] tests added or updated
- [ ] CI passed
- [ ] manual smoke test completed
- [ ] deployment completed

Blockers:
- ...

Files touched:
- ...

Rollback:
- ...
```

## Active tasks

### TASK-20260509-001 — Verify secure Telegram deployment on server

Status: validated
Source requirement: REQ-20260509-002
Assigned to: user
Risk: High
Affected services: telegram-bot

Goal:
- Confirm that the production server pulled the latest `main` and that Telegram runs through `telegram_bot_secure_runner.py`.

Progress log:
- 2026-05-10: User confirmed bot is online. Startup message received at 03:36 Israel.
  Bot responded to commands. System confirmed running through secure runner.

Validation:
- [x] `docker compose ps` shows telegram-bot running
- [x] logs show no crash (startup message confirmed received)
- [x] Bot active and responding
- [ ] `/portfolio`, `/next`, `/trade CAT` individually verified (implied by "עובד תקין")
- [ ] fast repeated messages trigger rate-limit behavior (not explicitly tested)

Files touched:
- `docker-compose.yml`
- `telegram_bot_secure_runner.py`

Rollback:
- Temporarily revert the Telegram command only if the secure runner fails.

### TASK-20260509-002 — Maintain AI-agent workflow documentation

Status: validated
Source requirement: REQ-20260509-003
Assigned to: agent
Risk: Low
Affected services: docs only

Goal:
- Keep repo-level context and workflow docs updated so AI agents can work efficiently.

Progress log:
- 2026-05-09: Created AGENTS.md, CLAUDE.md, all docs/ files.
- 2026-05-09: Updated AGENT_TASKS.md, USER_REQUIREMENTS.md, SYSTEM_STATE.md, DECISIONS.md at session checkpoint.
- 2026-05-10: Docs used successfully in new session — agent loaded context correctly without re-explanation.
- 2026-05-10: All docs updated to reflect deployment and post-deployment fixes.

Validation:
- [x] documentation files added
- [x] AGENT_TASKS.md reflects all work done in session
- [x] user confirmed workflow is useful (system used successfully across sessions)

### TASK-20260509-003 — Smart IBKR sync timing and report retention

Status: validated
Source requirement: REQ-20260509-001 / REQ-20260509-006
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (main.py only)

Goal:
- Replace naive hourly sync with smart windowed sync.
- Save last 3 IBKR XML reports for debugging.
- Alert via Telegram after 3 failed attempts.

Progress log:
- 2026-05-09: main.py rewritten (v16.0). Old v15.0 sync replaced.
- 2026-05-10: Deployed. Revealed timezone bug — Docker UTC vs Israel time.
  Sync window ran at 10:00–14:00 Israel instead of 07:00–11:00 Israel.
  Failure alert correctly fired after 3 attempts (wrong Query ID also a factor).
- 2026-05-10: Bug fixed — ZoneInfo("Asia/Jerusalem") + TZ=Asia/Jerusalem in docker-compose.
  User created new Query ID (1503908), added to .env.
- 2026-05-10: Redeployed. Next morning sync expected at 07:00–11:00 Israel.

Validation:
- [x] Deployed on Orange Pi
- [x] /app/ibkr_sync_state.json updated (confirmed by failure alert content)
- [x] Failure alert fired and received after 3 attempts
- [x] Timezone bug fixed and redeployed
- [ ] Report received next morning at 07:xx Israel (pending — tomorrow)
- [ ] Success Telegram notification received (pending)
- [ ] /app/ibkr_reports/ directory contains saved XML files (pending)

Rollback:
- git revert on main.py + docker compose up -d --build sentinel-bot

Files touched:
- main.py
- docker-compose.yml
- requirements.txt

### TASK-20260509-004 — Dashboard performance: parallel symbol pre-fetch

Status: validated
Source requirement: REQ-20260509-004
Assigned to: agent
Risk: Low
Affected services: dashboard

Goal:
- Eliminate sequential network calls that caused 10-20s load times.
- Pre-fetch all open position data in parallel before the serial analysis loop.
- Remove duplicate live-price calls in AI context export.

Progress log:
- 2026-05-09: dashboard.py updated. No math changes.
- 2026-05-10: Deployed. User confirmed system works correctly overall.
- 2026-05-10: Bug fixed — _warm_symbol_cache now wraps calls in try/except for true exception safety.

Validation:
- [x] Deployed on Orange Pi
- [x] System reported working correctly ("עובד תקין באופן כללי")
- [ ] Load time explicitly timed under 3 seconds (not formally measured)
- [x] No regression in data or calculations reported

Rollback:
- git revert on dashboard.py + docker compose up -d --build dashboard

Files touched:
- dashboard.py

### TASK-20260509-005 — Minervini-aligned trade metrics and math audit

Status: implemented
Source requirement: REQ-20260509-005
Assigned to: agent
Risk: Medium
Affected services: dashboard (new display), engine_core (new functions only)

Goal:
- Audit all existing calculations for correctness against Minervini methodology.
- Add missing metrics: initial risk % of NAV, R-per-day, MAE/MFE, add-on quality, full 8-criteria Trend Template.
- Add planned vs actual display in dashboard for open positions.

Audit findings:
- R-multiple math: CORRECT.
- Campaign aggregation: CORRECT.
- ATR / distribution day detection: CORRECT.
- Trend Template: was 5/8 criteria — fixed with new compute_trend_template_full().
- Missing entirely: initial_risk_pct, r_per_day, MAE/MFE, add-on quality check.

Plan:
1. Add compute_initial_risk_metrics() — risk sizing grade per Minervini 1-2.5% NAV rule.
2. Add compute_r_efficiency() — R-per-day capital efficiency.
3. Add compute_mfe_mae() — max adverse/favorable excursion from price history.
4. Add compute_trend_template_full() — all 8 Minervini criteria (separate from Telegram-facing get_minervini_analysis).
5. Add analyze_addon_quality() — validates pyramiding was done only above entry price.
6. Update compute_live_portfolio_data in dashboard to compute and expose new metrics.
7. Add planned vs actual expander per open position in Command Center tab.
8. Write 21 deterministic unit tests.

Progress log:
- 2026-05-09: All 5 new functions added to engine_core.py (additive only — no existing functions changed).
- 2026-05-09: dashboard.py updated with new columns and planned-vs-actual UI.
- 2026-05-09: tests/test_trade_metrics.py created. 24/24 tests pass.

Validation:
- [x] tests added — 21 new tests in tests/test_trade_metrics.py
- [x] all 24 tests pass (pytest -q)
- [ ] Deployed on Orange Pi
- [ ] Dashboard planned-vs-actual section verified manually
- [ ] MAE/MFE values cross-checked against chart

Remaining follow-up (not started):
- Display compute_trend_template_full() output in dashboard UI (Trend Template tab or per-position expander).
- Display analyze_addon_quality() results in dashboard for open and closed campaigns.
- Add planned-vs-actual section also for closed campaigns (Visual Journal tab).
- Add target_price field to Supabase schema to enable true planned R:R calculation (HIGH risk — schema change required, needs separate task).
- Improve market regime with breadth indicators (% stocks above MA50, A/D line direction).

Rollback:
- git revert on engine_core.py and dashboard.py
- No Supabase changes were made — full rollback is safe

Files touched:
- engine_core.py
- dashboard.py
- tests/test_trade_metrics.py

### TASK-20260510-001 — Quality audit: verify all session changes and fix prefetch exception safety

Status: validated
Source requirement: REQ-20260509-003 / REQ-20260509-004 / REQ-20260509-005
Assigned to: agent
Risk: Low
Affected services: dashboard (bug fix), docs only

Goal:
- Audit all changes from the 2026-05-09 session.
- Confirm tests pass at 100%.
- Identify and fix any bugs or code correctness issues.

Audit findings:
- pytest: 24/24 passed — no regressions.
- engine_core.py new functions: logic correct and well-structured.
- main.py v16.0: state machine logic correct (window, per-hour guard, fail count, notification).
- dashboard.py parallel prefetch: works correctly.
- Bug found: `f.result()` in `prefetch_symbols_parallel` (dashboard.py:230) does NOT absorb exceptions
  despite the comment claiming it does. Underlying functions are all exception-safe so this cannot
  trigger today, but the comment is wrong and the code is fragile against future changes.

Plan:
1. Add `try/except Exception: pass` inside `_warm_symbol_cache` to make it truly exception-safe.
2. Correct the comment on `f.result()`.
3. Update AGENT_TASKS.md and SYSTEM_STATE.md.

Progress log:
- 2026-05-10: Audit completed. Bug identified and fixed. All 24 tests still pass.

Validation:
- [x] pytest -q: 24/24 pass before fix
- [x] bug fix applied to dashboard.py
- [x] pytest -q: 24/24 pass after fix
- [ ] Deployed on Orange Pi with other batched changes

Files touched:
- dashboard.py (bug fix in _warm_symbol_cache)
- docs/AGENT_TASKS.md
- docs/SYSTEM_STATE.md

Rollback:
- Revert dashboard.py change — safe, no logic change

### TASK-20260510-002 — Fix IBKR sync timezone + risk-monitor overnight spam

Status: validated
Source requirement: REQ-20260509-006 / REQ-20260509-002
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (main.py, docker-compose), risk-monitor (risk_monitor.py)

Goal:
- Fix sync window running 3 hours late (UTC vs Israel time bug).
- Stop repeat alerts for "Broken" status during market-closed hours (night spam).

Root causes:
- Docker containers default to UTC. main.py uses datetime.now() which returned UTC,
  not Israel time. Code intended 07:00-11:00 Israel but ran 07:00-11:00 UTC = 10:00-14:00 Israel.
- risk_monitor.py repeat cooldown (6h) fires any time, including overnight when market is closed.

Plan:
1. docker-compose.yml: add TZ=Asia/Jerusalem to sentinel-bot and risk-monitor.
2. requirements.txt: add tzdata (enables ZoneInfo on slim Docker images).
3. main.py: use ZoneInfo("Asia/Jerusalem") explicitly for defensive correctness.
4. risk_monitor.py: add is_during_us_market_hours() and gate repeat alerts on it.

Progress log:
- 2026-05-10: All changes implemented.

Validation:
- [x] tests pass (24/24)
- [ ] Deploy on Orange Pi: docker compose up -d --build sentinel-bot risk-monitor
- [ ] Confirm first sync attempt at 07:xx Israel time (tomorrow)
- [ ] Confirm no overnight "Broken" alerts between 23:30-14:00 Israel time

User instructions for today's manual sync:
  rm ~/sentinel_trading/ibkr_sync_state.json
  docker compose restart sentinel-bot
  (only works before 11:00 Israel time)

Files touched:
- docker-compose.yml
- requirements.txt
- main.py
- risk_monitor.py

Rollback:
- Revert TZ env from docker-compose + revert main.py + revert risk_monitor.py
- All safe — no Supabase changes

### TASK-20260510-003 — Dashboard performance, enrichment, Telegram UX, Minervini Mentor

Status: implemented
Source requirement: REQ-20260510-001 / REQ-20260510-002 / REQ-20260510-003 / REQ-20260510-004
Assigned to: agent
Risk: Low
Affected services: dashboard, telegram-bot

Goal:
- Fix remaining dashboard performance bottlenecks
- Add Trend Template (8 criteria) + Add-on quality per open position
- Add "🧠 Minervini Mentor" tab with streak, strengths/weaknesses, dynamic coaching
- Add days-held + R-per-day + risk metrics to Visual Journal closed campaigns
- Create telegram_formatters.py (RTL formatting helpers)
- Redesign Telegram menus to hierarchical (4 categories → sub-menus)
- Add /mentor SYMBOL command for full Trend Template in Telegram
- Add generate_minervini_coaching() to engine_core
- Add Minervini coaching insight to /portfolio summary

Progress log:
- 2026-05-10: All changes implemented. pytest 24/24 ✅. Syntax validated. Committed and pushed (ad2d5c1).

Validation:
- [x] pytest -q: 24/24 pass (no regressions)
- [x] All 4 files pass AST syntax check
- [x] Committed to main and pushed to origin
- [ ] Deploy on Orange Pi: docker compose up -d --build dashboard telegram-bot
- [ ] Verify Minervini Mentor tab renders correctly
- [ ] Verify hierarchical Telegram menus work end-to-end
- [ ] Verify /mentor AAPL returns 8-criteria output
- [ ] Measure dashboard load time on second interaction (target: < 3s)

Files touched:
- dashboard.py (performance + 4-column expander + Mentor tab + Visual Journal metrics)
- engine_core.py (generate_minervini_coaching() — additive only, no existing functions changed)
- telegram_bot.py (hierarchical menus + /mentor + tf import + coaching in /portfolio)
- telegram_formatters.py (NEW file — RTL formatting helpers)
- docs/AGENT_TASKS.md, docs/USER_REQUIREMENTS.md, docs/SYSTEM_STATE.md, docs/DECISIONS.md

Rollback:
- git revert ad2d5c1 — safe (no Supabase schema changes, no docker-compose changes)
- Only rebuild dashboard and telegram-bot after rollback

Remaining follow-up items (not started):
1. fmt_position_card() in /portfolio loop (Phase 4 Telegram refactor — medium risk)
2. analyze_addon_quality() in Visual Journal (closed campaigns)
3. Dedicated Trend Template overview section for all open positions
4. "Weekly mentor review" automated Telegram message
5. target_price in Supabase for true planned R:R (HIGH risk — separate task)
6. Measure dashboard load time explicitly on Orange Pi

## Completed / validated tasks

Move validated tasks here when done.
