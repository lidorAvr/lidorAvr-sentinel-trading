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

Status: todo
Source requirement: REQ-20260509-002
Assigned to: user
Risk: High
Affected services: telegram-bot

Goal:
- Confirm that the production server pulled the latest `main` and that Telegram runs through `telegram_bot_secure_runner.py`.

Plan:
1. Run `git pull` on the Orange Pi server.
2. Rebuild/restart only `telegram-bot`.
3. Inspect logs.
4. Test Telegram commands.

Validation:
- [ ] `docker compose ps` shows telegram-bot running
- [ ] logs show no crash
- [ ] `/portfolio` works
- [ ] `/next` works
- [ ] `/trade CAT` works
- [ ] fast repeated messages trigger rate-limit behavior

Files touched:
- `docker-compose.yml`
- `telegram_bot_secure_runner.py`

Rollback:
- Temporarily revert the Telegram command only if the secure runner fails.

### TASK-20260509-002 — Maintain AI-agent workflow documentation

Status: in_progress
Source requirement: REQ-20260509-003
Assigned to: agent
Risk: Low
Affected services: docs only

Goal:
- Keep repo-level context and workflow docs updated so AI agents can work efficiently.

Progress log:
- 2026-05-09: Created AGENTS.md, CLAUDE.md, all docs/ files.
- 2026-05-09: Updated AGENT_TASKS.md, USER_REQUIREMENTS.md, SYSTEM_STATE.md, DECISIONS.md at session checkpoint.

Validation:
- [x] documentation files added
- [x] AGENT_TASKS.md reflects all work done in session
- [ ] user confirmed workflow is useful

### TASK-20260509-003 — Smart IBKR sync timing and report retention

Status: implemented
Source requirement: REQ-20260509-001
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (main.py only)

Goal:
- Replace naive hourly sync with smart windowed sync.
- Save last 3 IBKR XML reports for debugging.
- Alert via Telegram after 3 failed attempts.

Plan:
1. Define sync window 07:00–11:00 (Asia/Jerusalem, server is already on IDT).
2. Attempt once per hour, not on every 15-min loop tick.
3. Track state in /app/ibkr_sync_state.json (sync_date, fail_count, fail_date, last_attempt_hour, notified_date).
4. Save raw XML to /app/ibkr_reports/ibkr_YYYY-MM-DD_HH-MM.xml, keep last 3 files.
5. Send Telegram alert after MAX_ATTEMPTS_PER_DAY (3) failures.
6. Send success notification when report received.

Progress log:
- 2026-05-09: main.py rewritten (v16.0). Old v15.0 sync replaced.

Validation:
- [ ] Deployed on Orange Pi (git pull + docker compose up -d --build sentinel-bot)
- [ ] /app/ibkr_reports/ directory created on first run
- [ ] /app/ibkr_sync_state.json updated after each loop
- [ ] Report received next morning at 07:xx and saved as XML
- [ ] Success Telegram notification received
- [ ] Failure alert tested by temporarily using wrong token

Rollback:
- git revert on main.py + docker compose up -d --build sentinel-bot

Files touched:
- main.py

### TASK-20260509-004 — Dashboard performance: parallel symbol pre-fetch

Status: implemented
Source requirement: REQ-20260509-004
Assigned to: agent
Risk: Low
Affected services: dashboard

Goal:
- Eliminate sequential network calls that caused 10-20s load times.
- Pre-fetch all open position data in parallel before the serial analysis loop.
- Remove duplicate live-price calls in AI context export.

Plan:
1. Add prefetch_symbols_parallel() using ThreadPoolExecutor (max 8 workers).
2. Call it at the start of compute_live_portfolio_data before the for loop.
3. Fix AI context export to reuse live_df prices instead of re-calling get_live_price().
4. Update spinner message to show symbol count.

Progress log:
- 2026-05-09: dashboard.py updated. No math changes.

Validation:
- [ ] Deployed on Orange Pi
- [ ] Dashboard loads open positions in under 3 seconds (vs previous 10-20s)
- [ ] All position data and calculations identical to before

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

## Completed / validated tasks

Move validated tasks here when done.
