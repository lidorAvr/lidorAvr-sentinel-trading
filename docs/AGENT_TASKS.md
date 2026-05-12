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

### TASK-20260512-007 — Fix ALGO visibility alert threshold (always-fires bug)

Status: validated
Risk: Low
Affected services: risk_monitor

Problem discovered in production (2026-05-12):
- `compute_risk_visibility_score()` caps ALGO positions at **40/100** max (expected — no real stop known).
- `_algo_visibility_alert()` fires when avg < **60**, so it fires for EVERY ALGO position always.
- Alert message is misleading: "שקיפות נמוכה" when 40 is the normal/healthy ALGO score.

Fix applied (2026-05-12):
1. `engine_core.py → compute_algo_oversight_summary()`: threshold changed `vis_avg < 60.0` → `< 30.0`.
   - < 30 means ALGO positions lack even target_risk_usd (score = 20) — truly blind.
   - 40 = ALGO with target_risk_usd → acceptable, no alert needed.
2. `risk_monitor.py → _algo_visibility_alert()`: text updated — explains 40=normal, 20=missing target_risk_usd.
3. `tests/test_phase4_algo_oversight.py`: updated + 1 new test (score=40 must NOT alert).

Secondary question to investigate:
- Why does risk_monitor see only **2 ALGO positions** when user has more?
  - Likely: others are closed (pnl recorded) or `setup_type` casing differs (e.g. `algo` vs `ALGO`).
  - Check: `SELECT campaign_id, setup_type, quantity FROM trades WHERE setup_type ILIKE 'algo' AND quantity > 0`.

Files touched:
- `engine_core.py`
- `risk_monitor.py`
- `tests/test_phase4_algo_oversight.py`

Validation:
- [x] tests updated and passing (926 tests, 0 failures)
- [x] alert no longer fires for ALGO positions with normal 40/100 score
- [x] alert still fires for positions scoring 20 (no target_risk_usd)

---

### TASK-20260512-008 — Runner Mode: inline decision buttons + decision tracking

Status: proposed
Risk: Medium
Affected services: risk_monitor, telegram_bot

User request (2026-05-12):
- Alert text action items ("✅ להחזיק", "🚫 לא להוסיף") should become Telegram inline keyboard buttons.
- User clicks a button → system records the decision + timestamp.
- Risk monitor reads the stored decision on the next cycle and adjusts monitoring accordingly.
- "Not leaving things in the air."

Proposed buttons for Runner Mode alert:
1. ✅ להחזיק — Tennis Ball  → records `runner_decision: hold`
2. 🔒 הדק סטופ             → prompts user to enter new stop price
3. 📊 מימוש חלקי           → records `runner_decision: partial_exit` + asks qty
4. 📝 הערה ידנית           → opens free-text input

Implementation plan:
1. `risk_monitor.py`: replace `send_telegram(_runner_state_alert(...))` with
   `send_telegram_with_keyboard(text, _runner_decision_keyboard(sym, campaign_id))`.
2. `telegram_bot.py`: add `@bot.callback_query_handler` for `runner_decision|*` callbacks.
   - Hold → ACK message + save to `management_notes` in Supabase.
   - Tighten stop → reply "הזן מחיר סטופ חדש:" then await next message (multi-step flow).
   - Partial exit → save intent, next message asks qty.
3. `risk_monitor_state.json`: add `runner_decision` + `runner_decision_ts` per campaign.
4. Risk monitor: when `runner_decision = hold` → suppress repeated Runner alerts for 24h.

Files to touch:
- `risk_monitor.py`
- `telegram_bot.py`
- Tests: `tests/test_phase3_state_alerts.py` (keyboard structure)

Blockers:
- Needs multi-step conversation state in `telegram_bot.py` (user response to bot prompt).
  Existing pattern: check how tighten-stop flow works elsewhere in the bot.

---

---

## Completed tasks (session 8 — 2026-05-12)

### TASK-20260512-001 — Phase 1: Risk Basis Engine

Status: implemented
Risk: Low
Affected services: engine_core (no runtime change — new pure functions)

Done:
- `compute_original_campaign_risk()`, `compute_frozen_target_risk()`, R_true / R_target
- `compute_capital_at_risk_usd()`, `compute_open_pnl_at_stop()`, `compute_protected_profit_usd()`
- `compute_giveback_usd/pct()`, `classify_giveback_severity()`
- `compute_sizing_ratio()` with 7 tiers
- `get_sample_size_context()`, `add_data_scope()`, data scope constants
- 75 tests in `tests/test_risk_basis_engine.py`

---

### TASK-20260512-002 — Phase 2: Position State Machine

Status: implemented
Risk: Low
Affected services: engine_core

Done:
- 10 state constants + `compute_position_state()` with priority ordering
- `compute_event_risk_info()`: earnings-window risk (RED ≤ 3d / ORANGE ≤ 7d / YELLOW ≤ 15d, manual only)
- `get_position_state_display_label()`: merged label
- 100 tests in `tests/test_position_state_machine.py`

---

### TASK-20260512-003 — Phase 3: State Machine wiring in risk_monitor.py

Status: implemented
Risk: Medium
Affected services: risk_monitor

Done:
- Enriched `_checkpoint_alert_text()` with Phase 1 values
- 4 new state-change alert functions (Runner / Broken / Dead Money / Breakeven Protocol)
- Main loop: state compute per position, one-time/transition alerts, state persistence
- 40 tests in `tests/test_phase3_state_alerts.py`

---

### TASK-20260512-004 — Phase 4: ALGO Oversight

Status: implemented
Risk: Low
Affected services: risk_monitor, engine_core

Done:
- `compute_algo_oversight_summary()`: portfolio visibility, cap breaches, deep loss
- 3 ALGO oversight alert functions (deep loss / streak / visibility)
- Per-position streak tracking + one-time deep loss gate with recovery reset
- Post-loop portfolio visibility check (24h cooldown)
- 48 tests in `tests/test_phase4_algo_oversight.py`

---

### TASK-20260512-005 — Phase 5: Anti-Spam / Alert State Table

Status: implemented
Risk: Low
Affected services: risk_monitor

Done:
- `STATE_ALERT_COOLDOWN` dict (RUNNER/BROKEN 4h, DEAD_MONEY 12h)
- `ALERT_PRIORITY` dict: P0–P3 for all 14 alert types
- `_should_fire_state_alert()`: oscillation-safe gate
- `last_state_alert_ts` / `last_state_alert_type` in state JSON
- 33 tests in `tests/test_phase5_anti_spam.py`

---

### TASK-20260512-006 — Phase 6: Master Context Export

Status: implemented
Risk: Low
Affected services: dashboard, engine_core

Done:
- `build_position_context_data()` in engine_core.py
- Dashboard Section 2 enriched: State / Sizing / EventRisk / Protected Profit / Breakeven
- Dashboard Section 4 enriched: BROKEN/DEAD_MONEY context, Event Risk <7d, Sizing warning
- State loaded from `risk_monitor_state.json`
- 33 tests in `tests/test_phase6_context_export.py`

---

## Completed tasks

### TASK-20260511-012 — Manual IBKR XML upload via developer menu

Status: validated
Assigned to: agent
Risk: Low
Affected services: telegram-bot

Goal:
- Fallback when IBKR API is throttled: user downloads XML from IBKR website and uploads it directly in Telegram.

Done:
- `📤 העלה דוח XML` button in developer menu.
- `_process_uploaded_ibkr_xml()`: validates extension, parses NAV + trades, saves report, updates config, writes result file.
- `handle_document_upload()` handler for `content_types=['document']`.
- 8 new tests in `test_developer_menu.py`.

Validation:
- [x] 8 new tests pass (596 total)
- [x] Confirmed working on Orange Pi: 27 trades, NAV $7,934.27 loaded 2026-05-11 21:07
- [x] PR #11 merged to main
- [x] Deployed: `docker compose restart telegram-bot`

Files touched:
- `telegram_bot.py`
- `tests/test_developer_menu.py`

---

### TASK-20260511-013 — Fix 6 production bugs (IBKR pipeline + dashboard)

Status: validated
Assigned to: agent
Risk: Medium
Affected services: telegram-bot, dashboard

Goal:
- Diagnose and fix all production errors after session 5 deploy.

Done (PRs #5–#10, #12):
1. Telegram health report Markdown crash on IBKR filenames (underscores) → removed `parse_mode="Markdown"` (PR #5)
2. Dashboard `background_gradient` matplotlib ImportError → removed cosmetic call (PR #6)
3. IBKR sync diagnostic: log raw SendRequest response (PR #7)
4. Manual sync logs invisible: pass `log_fn=_bot_log` (PR #8)
5. IBKR ReferenceCode PascalCase: `root.find(".//ReferenceCode")` + explicit `is None` check (PR #9)
6. GetStatement URL: extract `<Url>` from SendRequest, default to `gdcdyn.interactivebrokers.com` (PR #10)
7. Dashboard NAV key: `"current_nav"` → `"nav"`, fix `save_settings` to merge config (PR #12)

Validation:
- [x] 596 tests pass
- [x] All PRs merged to main and deployed
- [x] Dashboard confirmed: Live IBKR NAV $7,934.27, All-Time Return +5.8%

---

### TASK-20260511-011 — Clean up scripts/archive and root-level clutter

Status: validated
Assigned to: agent
Risk: Low
Affected services: none

Goal:
- Archived 26 orphaned one-shot fix scripts to `scripts/archive/`.
- Verify `test_infra.py` and `test_xml_ibkr.py` (archived) are no longer needed.
- Add `scripts/archive/README.md` with inventory.

Progress log:
- 2026-05-11: 26 files moved to scripts/archive/.

Validation:
- [x] All orphaned scripts moved to scripts/archive/
- [x] scripts/archive/README.md written
- [x] pytest -q still passes (596 passed)

---

### TASK-20260511-010 — Comprehensive test suite: security, calculations, data validation, UX

Status: validated
Assigned to: agent
Risk: Low
Affected services: tests only

Goal:
- 587 tests covering functionality, security, UX, data validation, and math at highest precision.

Done:
- `tests/test_security.py` (30 tests): token masking, rate limiting, secrets not in logs, retry boundary.
- `tests/test_calculations_comprehensive.py` (45 tests): R-multiples, profit factor, expectancy, dev score, adaptive risk math, NAV freshness.
- `tests/test_data_validation.py` (50 tests): malformed input, edge cases, corrupt files, account state.
- `tests/test_ux_formatting_comprehensive.py` (40 tests): Hebrew months, Markdown validity, verdict, coaching.
- `tests/test_adaptive_risk_engine.py` (55 tests): RISK_LADDER, all directions, heat score, streaks, adherence.
- `tests/test_ibkr_sync_full.py` (35 tests): all 17 error codes, retry logic, full pipeline.
- 3 production bugs fixed: `adaptive_risk_engine.py` (3× `c["is_win"]` → `.get()`), `account_state.py` (non-dict JSON guard).

Validation:
- [x] 587 tests pass, 0 failures
- [x] Committed and pushed to claude/review-dev-roadmap-6K19V

---

### TASK-20260511-009 — PDF weekly/monthly report service (Phase 1 + Phase 2)

Status: validated
Assigned to: agent
Risk: Low
Affected services: report-scheduler (new Docker service)

Goal:
- PDF reports via WeasyPrint + Jinja2 delivered to Telegram on schedule.
- Charts embedded (Plotly + Kaleido): R bars, setup performance, equity curve, win/loss donut.

Done:
- `report_scheduler.py` — Israel-TZ scheduling, weekly (Sat 08:30) + monthly (1st 08:40), dedup.
- `report_renderer.py` — HTML→PDF, `build_weekly_report`, `build_monthly_report`, `build_summary_text`.
- `report_delivery.py` — `send_pdf`, `send_message`, 1024-char caption guard.
- `report_snapshot_store.py` — WoW/MoM comparison snapshots.
- `chart_generator.py` — 4 chart types, graceful None fallback.
- `analytics_engine.py` — `compute_period_analytics`, `compute_trader_development_score`, `compute_verdict`.
- Templates: `templates/weekly_report.html.j2`, `templates/monthly_report.html.j2`, `templates/report_base.css`.
- docker-compose: `report-scheduler` service added.

Validation:
- [x] pytest -q passes (test_report_scheduler.py, test_chart_generator.py, test_calculations_comprehensive.py)
- [x] Committed and pushed
- [ ] Deploy on Orange Pi: `docker compose up -d --build report-scheduler`
- [ ] Verify first weekly report arrives on Saturday 08:30 Israel time

---

### TASK-20260511-008 — Developer menu (🛠️) in Telegram

Status: validated
Assigned to: agent
Risk: Low
Affected services: telegram-bot

Goal:
- Admin-only developer actions accessible from Telegram without SSH.

Done:
- `🛠️ פיתוח` button in help sub-menu (admin-only).
- Manual IBKR sync, last sync result, system health, config display (tokens masked), log view, git pull.
- Rate-limited: 2 syncs/day, 3h cooldown between syncs.
- `_dev_sync_check()` / `_dev_sync_record()` with state file.
- `ibkr_sync_runner.py` extracted from `main.py` and reused.

Validation:
- [x] test_developer_menu.py passes
- [x] test_ibkr_sync_full.py: 35 tests pass
- [x] Committed and pushed
- [ ] Verify on Orange Pi

---

### TASK-20260511-001 — IBKR error classification + smart GetStatement retry

Status: validated
Source requirement: REQ-20260511-001
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (ibkr_sync_runner.py)

Goal:
- Classify IBKR Flex Query errors: temporary / fatal / rate_limit.
- Retry GetStatement up to 3× with wait per attempt.
- Immediate stop on fatal errors (prevents account lockout).

Done (implemented in `ibkr_sync_runner.py`):
- `IBKR_ERROR_CLASSES` dict: 17 codes mapped to (class, Hebrew description).
- `parse_flex_error(xml_text)` → classified error dict or None.
- `get_statement_with_retry(ref, token, max_retries, wait_sec)` → (xml, err).
- Fatal errors stop after 1 attempt; temporary errors retry up to max_retries.
- `run_ibkr_sync()` → structured `{"status", "code", "message", "nav"}`.
- 35 unit tests covering all 17 error codes and full pipeline.

Validation:
- [x] 35 tests pass (test_ibkr_sync_full.py)
- [x] All 17 known error codes tested and classified correctly
- [x] Fatal error stops after 1 attempt (no retry)
- [x] Temporary error retries exactly max_retries times
- [x] NAV extracted and written to config on success
- [x] Committed and pushed
- [ ] Deploy on Orange Pi and verify morning sync behavior

Files touched:
- ibkr_sync_runner.py (NEW — extracted from main.py)
- tests/test_ibkr_sync_full.py (NEW)

---

### TASK-20260511-007 — Phase G: Portfolio Heat Map + Earnings Risk Module + AI Context Export upgrade

Status: implemented
Source requirement: REQ-20260511-008
Assigned to: agent
Risk: Low
Affected services: dashboard, telegram-bot

Goal:
- Add Portfolio Heat Map (cluster-level exposure + open R + risk contribution).
- Add Earnings Risk Module: next earnings date, days-to-event, cushion verdict per open position.
- Upgrade AI Master Context Export: include management_mode, risk_basis, stat_bucket, ALGO note, next decisions section.

Plan:
1. `engine_core.py`: add `fetch_next_earnings_date(symbol)` using yfinance calendar.
2. `dashboard.py`: add Portfolio Heat Map section (EP / VCP / ALGO / concentration / cash row).
3. `dashboard.py`: add earnings risk warning per open position in Command Center expander.
4. `telegram_bot.py`: update AI context export command to include new fields.

Validation:
- [ ] Portfolio Heat Map renders with correct cluster groupings
- [ ] Earnings dates fetched without breaking dashboard load time
- [ ] AI export includes management_mode, risk_basis, ALGO disclaimer
- [ ] pytest -q passes
- [ ] Deployed and verified

Files touched:
- engine_core.py, dashboard.py, telegram_bot.py

Rollback:
- git revert — no Supabase schema changes, safe

---

### TASK-20260511-006 — Phase F: Actionability Layer + Mistake Classification + /health command

Status: implemented
Source requirement: REQ-20260511-006 / REQ-20260511-007
Assigned to: agent
Risk: Low
Affected services: telegram-bot, dashboard

Goal:
- Add `actionability` classification to all Telegram messages and alerts.
- Add `fmt_algo_risk_note()` to `telegram_formatters.py` using structured ALGO message template.
- Add `/health` Telegram command with 13 data integrity checks.
- Add `intent` and `mistake_classification` fields to campaign data.
- Add Data Quality Badges per position.

Plan:
1. `telegram_formatters.py`: add `fmt_algo_risk_note(symbol, open_r, exposure, reason)` with actionability field.
2. `telegram_bot.py`: add `/health` command — runs checklist and returns structured report.
3. `engine_core.py`: add `compute_data_quality_badge(position)` → returns badge emoji + label.
4. `dashboard.py`: display badges and intent labels per position in Command Center.
5. Update all existing alert generators to include actionability level.

Validation:
- [ ] /health returns all 13 checks
- [ ] ALGO positions never receive Action Required with exit instruction
- [ ] Data quality badge computed correctly for verified / external / broken cases
- [ ] pytest -q passes

Files touched:
- telegram_formatters.py, telegram_bot.py, engine_core.py, dashboard.py

Rollback:
- git revert — additive changes only, no schema changes

---

### TASK-20260511-005 — Phase E: Risk Deviation Engine + Giveback Monitor

Status: implemented
Source requirement: REQ-20260511-005
Assigned to: agent
Risk: Medium
Affected services: engine-core, risk-monitor, telegram-bot

Goal:
- Add `compute_risk_deviation(position)` to engine_core: deviation R = open loss / target risk USD, classified.
- Add `compute_giveback_from_peak(position)` to engine_core: tracks peak open R, measures giveback %.
- Wire ALGO guardrail thresholds into risk_monitor: alert at 1.5R / 2.0R / 3.0R open loss.
- Fire Profit Protection Checkpoints at 2R and 3R milestones (different text for manual vs ALGO).
- Add tests for deviation classification.

Plan:
1. `engine_core.py`: `compute_risk_deviation()` — five-tier classification (normal/minor/moderate/severe/system_event).
2. `engine_core.py`: `compute_giveback_from_peak()` — four-tier classification (natural/watch/tighten/protection_failure).
3. `risk_monitor.py`: per-position ALGO guardrail check using `compute_risk_deviation()`.
4. `risk_monitor.py`: Profit Protection Checkpoint alerts at 2R / 3R, separate text for manual vs ALGO.
5. `tests/test_risk_deviation.py`: unit tests for both functions.

Validation:
- [ ] Tests added and passing
- [ ] ALGO alerts use "Review Required" language, not exit instructions
- [ ] Manual positions receive management suggestion at checkpoints
- [ ] pytest -q passes
- [ ] Deployed on Orange Pi

Files touched:
- engine_core.py, risk_monitor.py, telegram_formatters.py, tests/test_risk_deviation.py

Rollback:
- git revert engine_core.py + risk_monitor.py — no schema changes

---

### TASK-20260511-004 — Phase D: Statistical isolation (stat_bucket + ALGO Risk Oversight Score)

Status: implemented
Source requirement: REQ-20260511-004
Assigned to: agent
Risk: Medium
Affected services: dashboard, engine-core, analytics_engine

Goal:
- Add `stat_bucket` field to campaign data: EP_MANUAL / VCP_MANUAL / ALGO_OBSERVED / TEST_PROBE / DATA_INCOMPLETE / BROKER_SYNC_ONLY.
- `analytics_engine.py`: separate stats into Discretionary / ALGO / Combined buckets.
- Dashboard shows three separate performance sections.
- ALGO positions get `ALGO Risk Oversight Score` instead of `Execution Score`.
- DATA_INCOMPLETE campaigns excluded from Expectancy and Win Rate.

Plan:
1. `engine_core.py`: add `classify_stat_bucket(campaign)` — derives bucket from setup_type + management_mode + data quality.
2. `analytics_engine.py` (extend from REQ-20260510 planned work): bucket-aware stats computation.
3. `dashboard.py`: Performance Matrix tab — add separate Discretionary / ALGO / Combined sections.
4. `engine_core.py`: add `compute_algo_risk_oversight_score(campaign)` — weighted 5-factor score.

Validation:
- [ ] stat_bucket correctly assigned for EP, VCP, ALGO campaigns
- [ ] Expectancy calculation excludes DATA_INCOMPLETE bucket
- [ ] ALGO Risk Oversight Score returns 0–100 value
- [ ] Dashboard shows three separate performance views
- [ ] pytest -q passes

Files touched:
- engine_core.py, analytics_engine.py, dashboard.py

Rollback:
- git revert — no Supabase schema changes (stat_bucket derived at runtime)

---

### TASK-20260511-003 — Phase C: Risk Basis + Risk Visibility Score + management_mode display

Status: implemented
Source requirement: REQ-20260511-002 / REQ-20260511-003
Assigned to: agent
Risk: Medium
Affected services: engine-core, dashboard, telegram-bot

Goal:
- Add `management_mode` to position data: manual_managed / system_assisted / algo_observed / unknown.
- Add `risk_basis` to position data: True / Target / Estimated / Unknown.
- Add `risk_visibility_score` (0–100) per position.
- Fix ALGO stop display: replace `$0.00` with `External / Unknown`.
- `unknown` mode positions excluded from quality statistics.

Plan:
1. `engine_core.py`: add `classify_management_mode(campaign)` — derives from setup_type + existing stop data.
2. `engine_core.py`: add `classify_risk_basis(campaign)` — True if stop known, Target if using target_risk_usd, else Estimated/Unknown.
3. `engine_core.py`: add `compute_risk_visibility_score(campaign)` → int 0–100.
4. `dashboard.py`: use management_mode to gate stop display — ALGO shows "External / Unknown" not "$0.00".
5. `telegram_formatters.py`: `fmt_position_card()` shows risk_basis badge.
6. All quality stats: filter out `unknown` management_mode positions.

Validation:
- [ ] ALGO positions show "External / Unknown" stop, not $0.00
- [ ] risk_basis correctly classified for positions with and without stops
- [ ] risk_visibility_score in range 0–100
- [ ] unknown mode excluded from quality stats
- [ ] pytest -q passes

Files touched:
- engine_core.py, dashboard.py, telegram_formatters.py

Rollback:
- git revert — additive, no schema changes

---

### TASK-20260511-002 — Phase B: ALGO Observer Mode — formal rules and display foundation

Status: implemented
Source requirement: REQ-20260511-002
Assigned to: agent
Risk: Low
Affected services: dashboard, telegram-bot

Goal:
- Establish ALGO Observer Mode as a formal, enforceable concept in the codebase.
- Add constant / config that lists known ALGO symbols (already partially in engine_core.py).
- Ensure no code path issues EP/VCP management instructions to ALGO positions.
- Document the formal rule in code comments and DATA_CONTRACTS.md.

Plan:
1. `engine_core.py`: add `ALGO_SYMBOLS` set and `is_algo_position(campaign)` helper.
2. Audit `telegram_bot.py` and `engine_core.py` for any code that sends stop-raise or exit instructions to ALGO positions — gate them with `is_algo_position()`.
3. `docs/DATA_CONTRACTS.md`: add management_mode and stat_bucket to contracts.
4. Add management_mode and risk_basis to `docs/DECISIONS.md` as architectural decisions.

Plan:
1. Add `is_algo_position()` to engine_core.
2. Audit existing management suggestion code paths.
3. Update DATA_CONTRACTS.md.
4. Update DECISIONS.md.

Validation:
- [ ] is_algo_position() returns True for known ALGO symbols
- [ ] No management suggestion code sends stop/exit instruction to ALGO positions
- [ ] DATA_CONTRACTS.md updated
- [ ] DECISIONS.md updated
- [ ] pytest -q passes

Files touched:
- engine_core.py, telegram_bot.py, docs/DATA_CONTRACTS.md, docs/DECISIONS.md

Rollback:
- git revert — code audit + doc changes only

---

### TASK-20260511-001 — IBKR error classification + smart GetStatement retry

Status: implemented
Source requirement: REQ-20260511-001
Assigned to: agent
Risk: Medium
Affected services: sentinel-bot (main.py only)

Goal:
- Classify IBKR Flex Query errors: temporary / fatal / rate_limit.
- Retry GetStatement up to 3× with 60s wait per hourly attempt (same ReferenceCode).
- Do not resend SendRequest within the same hourly attempt.
- Raise MAX_ATTEMPTS_PER_DAY from 3 to 5.
- Include error code + classification in every Telegram alert.
- Immediate stop-and-alert on fatal errors.

Plan:
1. Add `IBKR_ERROR_CLASSES` dict mapping code → (class, Hebrew description).
2. Extract `parse_flex_error(xml_text)` → returns (code, class, description) or None if success.
3. Extract `get_statement_with_retry(ref_code, token, max_retries=3, wait_sec=60)`.
4. Refactor `run_ibkr_sync()` to return structured dict {"status", "code", "message"}.
5. Update caller loop in `__main__` to act on status: fatal → skip day, temporary → count attempt, rate_limit → log only.
6. Update Telegram alerts to include code + class.
7. Add unit tests for error classification.

Progress log:
- 2026-05-11: Requirement documented. Waiting for additional topics before implementation.

Validation:
- [ ] Tests added for IBKR_ERROR_CLASSES and parse_flex_error
- [ ] pytest -q passes
- [ ] Manual smoke test: fatal error triggers immediate alert with code
- [ ] Manual smoke test: temporary error retries GetStatement before counting failure
- [ ] Deployed on Orange Pi

Blockers:
- Waiting for additional topics from user before starting implementation.

Files touched:
- main.py

Rollback:
- git revert on main.py + docker compose restart sentinel-bot

---

### TASK-20260510-004 — Adaptive risk engine + regime transparency + proactive alerts

Status: implemented
Source requirement: REQ-20260510-005 / REQ-20260510-006
Assigned to: agent
Risk: Medium
Affected services: telegram-bot, risk-monitor

Goal:
- Fix market regime report to show raw SPY/QQQ signals (not just verdict).
- Build adaptive risk engine based on last 50 closed campaigns (2x weight on last 10).
- Send proactive risk-change alerts via Telegram with ✅/❌ inline buttons.
- Confirmation flow: YES updates sentinel_config.json; NO prompts for mandatory reason.
- Log all decisions to risk_journal.json.
- Add /stats command for adherence statistics.
- Update RISK_LADDER to [0.35 … 2.50]%.

Plan:
1. engine_core.py: extend compute_market_regime to return raw signals dict.
2. telegram_formatters.py: update fmt_regime_report to show ✅/❌ per criterion; add fmt_adaptive_risk_block.
3. adaptive_risk_engine.py (new): RISK_LADDER, compute_closed_campaigns, compute_adaptive_risk, update_risk_pct, log_risk_journal, mark_adherence, compute_adherence_stats.
4. risk_monitor.py: send_telegram_with_keyboard helper + proactive alert at end of main() with 24h throttle.
5. telegram_bot.py: risk_confirm callback, risk_reject_reason state, /stats command.

Progress log:
- 2026-05-10: All changes implemented. 24/24 tests pass. Committed (5f85069). Not yet deployed.

Validation:
- [x] pytest -q: 24/24 pass
- [x] AST syntax check: all 3 modified files OK
- [x] Committed to main (5f85069)
- [ ] git push to origin/main
- [ ] Deploy on Orange Pi: docker compose restart telegram-bot risk-monitor
- [ ] Verify regime report shows ✅/❌ signals in Telegram
- [ ] Verify proactive risk alert arrives with buttons (requires ≥3 closed campaigns)
- [ ] Test YES button → sentinel_config.json updated + risk_journal.json entry written
- [ ] Test NO button → reason prompt appears → reason logged
- [ ] Test /stats command

Remaining follow-up (not started):
1. mark_adherence wired to sentinel_config.json watch (detect manual risk_pct changes outside Telegram).
2. Dashboard integration: show algorithm-recommended risk % vs actual, alert on manual deviation.
3. /stats to also show last N rejected reasons for pattern analysis.

Files touched:
- adaptive_risk_engine.py (NEW)
- engine_core.py
- telegram_formatters.py
- telegram_bot.py
- risk_monitor.py
- docs/USER_REQUIREMENTS.md

Rollback:
- git revert 5f85069 + docker compose restart telegram-bot risk-monitor
- risk_journal.json and risk_recommendations.json are local runtime files — not committed, safe to delete if needed

---

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
