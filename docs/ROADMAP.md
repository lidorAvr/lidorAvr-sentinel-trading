# Sentinel Trading Roadmap

This roadmap keeps future development focused and prevents scattered AI-agent work.

## Guiding principle

Build a system that is accurate, safe, fast to extend, and aligned with the user's trading process.

## Phase 1 — Safety and agent-readiness

Status: **complete**

Goals:

- Add agent context docs.
- Add user requirement tracking.
- Add agent task tracking.
- Keep Telegram protected by secure runner.
- Keep deployment commands documented.

Done:

- `AGENTS.md`, `CLAUDE.md`, docs under `docs/`
- `telegram_bot_secure_runner.py`
- Docker Compose command updated for Telegram service
- Deployment verified on Orange Pi ✅
- Comprehensive test suite: 587 tests, 0 failures ✅

## Phase 2 — Data truth and NAV reliability

Status: **complete**

Goals:

- Define one explicit NAV/account-size source.
- Ensure all services read the same assumption.
- Add visible freshness/fallback labels.
- Add tests for fallback behavior.

Done:

- `account_state.py` — single source of truth for NAV (broker/deposited/fallback) ✅
- `DataFreshness` labels: fresh / stale / critical / unknown, with emoji indicators ✅
- Tests for live/cached/fallback reporting in `tests/test_data_validation.py` ✅
- Non-dict JSON guard prevents silent crash if config file corrupted ✅
- `sentinel_config.json` NAV key contract locked: `"nav"` everywhere, merge-on-write pattern ✅ (session 6)
- Dashboard NAV key bug fixed: `"current_nav"` → `"nav"`, `save_settings` no longer overwrites ✅ (session 6)

## Phase 3 — Risk and campaign engine hardening

Status: **complete**

Done:
- Minervini metrics (initial risk, R/day, MAE/MFE, Trend Template full, add-on quality) ✅
- Adaptive risk engine (weighted win rate, risk ladder, proactive alerts, /stats) ✅
- `analytics_engine.py`: period analytics, profit factor, expectancy, dev score ✅
- Comprehensive math tests: R-multiples, PF edge cases, dev score bounds, oversized boundary ✅

## Phase 3B — ALGO Observer Mode and Risk Isolation

Status: **complete**

Guiding principle:
Sentinel is an oversight and measurement layer for ALGO positions, not a manager.
Sentinel must never issue stop-raise or exit instructions for externally managed ALGO positions.

Done:
1. `External / Unknown` stop display for ALGO positions — `ALGO_SYMBOLS`, `is_algo_position()` ✅ (TASK-002)
2. `classify_management_mode()`, `classify_risk_basis()`, `compute_risk_visibility_score()` ✅ (TASK-003)
3. Statistical isolation: `classify_stat_bucket()`, `compute_algo_risk_oversight_score()`, `classify_mistake()`, Discretionary/ALGO/Combined sections in dashboard ✅ (TASK-004)
4. Risk Deviation Engine: `compute_risk_deviation()` (5-tier), `compute_giveback_from_peak()` (4-tier) ✅ (TASK-005)
5. Giveback Monitor + Profit Protection Checkpoints (2R/3R) wired in `risk_monitor.py` ✅ (TASK-005)
6. `/health` command (13 checks), `compute_data_quality_badge()` per position ✅ (TASK-006)
7. Actionability Layer: `fmt_actionability()`, `fmt_algo_risk_note()` in `telegram_formatters.py` ✅ (TASK-006)
8. AI Master Context Export in dashboard sidebar ✅ (TASK-007)
9. Mistake Classification for closed campaigns ✅ (TASK-006)

Formal ALGO rule (enforced in code via `is_algo_position()`):
> Sentinel must not grade ALGO trades using EP/VCP management rules
> unless the ALGO rule-set is explicitly imported and mapped.

## Phase 4 — Telegram refactor

Status: planned (partially complete — telegram_formatters.py created, hierarchical menus done)

Goals:

- Split `telegram_bot.py` into smaller modules.
- Preserve existing flows.
- Make messages shorter and more consistent.
- Move secure runner protections into explicit code once safe.
- Apply Actionability Layer to all messages — `fmt_actionability()` + `fmt_algo_risk_note()` done ✅ (TASK-006).

Completed extractions:
- `supabase_repository.py` ✅ (dependency-injected repo layer, 24 tests)
- `telegram_menus.py` ✅ (all menu/keyboard builders, 20 tests)
- `bot_core.py` ✅ (shared bot/supabase/user_state/RTL instances)
- `bot_helpers.py` ✅ (pure helpers, 15 tests)
- `telegram_callbacks.py` ✅ (all @bot.callback_query_handler routes)
- `telegram_backlog.py` ✅ (get_next_missing journal flow, 16 tests)
- `telegram_portfolio.py` ✅ (handle_drilldown + handle_market_regime + handle_portfolio_room, 23 tests)
- `bot_health.py` ✅ (build_health_report — 13-check system health, 15 tests)
- `telegram_devops.py` ✅ (IBKR sync rate-limiter, manual-sync thread, XML upload — 28+5 tests updated)

Status: **Phase 4 complete** — `telegram_bot.py` reduced from ~2000 → 457 lines (-77%).
Remaining content is `handle_all_messages` routing (short if/elif blocks) and
`handle_document_upload` — extracting them further would add abstraction overhead
without meaningful complexity reduction.

Rules:

- Refactor only one concern at a time.
- Do not mix feature work with refactor.
- Keep Docker command on secure runner until protections are moved and tested.

## Phase 5 — Dashboard and reporting upgrades

Status: **complete**

Done:

- PDF weekly/monthly report service (WeasyPrint + Jinja2 + Plotly charts) ✅
- Weekly/monthly Telegram summary with Hebrew coaching insights ✅
- WoW/MoM comparison via snapshot store ✅
- Plotly charts embedded in PDF (campaign R bars, setup perf, equity curve, win/loss donut) ✅
- IBKR sync pipeline fully operational: ReferenceCode fix, gdcdyn URL, log_fn, raw response logging ✅ (session 6)
- Manual XML upload fallback: `📤 העלה דוח XML` in developer menu — confirmed working ✅ (session 6)
- Portfolio Heat Map (cluster-level exposure + open R) ✅ (TASK-007)
- Earnings Risk Module per open position (`fetch_next_earnings_date()`) ✅ (TASK-007)
- Data freshness + Risk Visibility Score per position in dashboard ✅
- Separate statistics view: Discretionary / ALGO / Combined ✅ (TASK-004)

## Phase 6 — Automation and intelligence layer

Status: **complete** (session 8, 2026-05-12)

Done (24-module spec — Phases 1–6 on branch `claude/review-dev-roadmap-6K19V` → main):

**Phase 1 — Risk Basis Engine** ✅
- Risk computation (R_true, R_target, original_campaign_risk, frozen_target_risk)
- Capital at risk, protected profit, giveback USD/%, giveback severity
- Sizing ratio (7 tiers), data scope + sample size context

**Phase 2 — Position State Machine** ✅
- 10 states with priority ordering
- Event-risk flag (earnings proximity, manual positions only)
- `compute_position_state()` + `get_position_state_display_label()`

**Phase 3 — State Machine wiring** ✅
- State-change alerts: Runner / Broken / Dead Money / Breakeven Protocol
- Enriched checkpoint alerts with Phase 1 values
- State persistence in `risk_monitor_state.json`

**Phase 4 — ALGO Oversight** ✅
- Portfolio-level visibility (avg score < 60 → alert)
- Per-symbol cap breach detection
- Per-position: loss streak alerts (yellow/orange), deep loss (≤ −2R) gate
- All alerts: oversight language only, no exit/stop instructions

**Phase 5 — Anti-Spam / Alert State Table** ✅
- `STATE_ALERT_COOLDOWN`: RUNNER/BROKEN 4h, DEAD_MONEY 12h (oscillation protection)
- `ALERT_PRIORITY` dict: explicit P0–P3 for all 14 alert types
- `_should_fire_state_alert()`: unified dedup gate

**Phase 6 — Master Context Export** ✅
- `build_position_context_data()` helper (testable, Streamlit-free)
- Dashboard Section 2+4 enriched with State / Sizing / EventRisk / Protected Profit / Breakeven

**Test suite: 925 tests, 0 failures** (329 new tests across 6 test files)

Rules (preserved throughout):
- No automatic trade state mutation without explicit user-approved rules.
- ALGO positions never receive automated exit instructions.
- All alerts bounded to avoid noise (dedup + cooldown + market-hours gate).

## Phase 7 — Minervini Team Review Cycle (Meetings 1 + 2)

Status: **complete** — Sprint 1 + Sprint 2 shipped. See `docs/SPRINT_1_2_REPORT.md`.

**Sprint 1 — Production Reliability** (commit `dc1afa5`)
- `ec.get_campaign_risk_metrics(row)` — single source of truth for 1R
- 3 silent failures in `risk_monitor.py` now send Telegram alerts
- `_require_env()` startup validation
- Mid-loop state checkpoint

**Sprint 2 — Methodology Fidelity** (commit `e319fcb`)
- `compute_follow_through()` — Minervini "wizards continue" scorer (LONG + SHORT)
- `follow_through_score` wired into `compute_position_state` (was always `None`)
- Heat Score: Wizard payoff threshold (≥3.0 → +24), gap fills, sharper streak penalty
- SIGTERM/SIGINT graceful shutdown

**Merge:** PR #15 merges `claude/review-dev-roadmap-6K19V` → `main`.
**Tests: 1182 passing** (was 1153).

## Phase 8 — Meeting 3 & New Departments

Status: **complete** — Sprint 3 shipped. See `docs/SPRINT_3_REPORT.md`.

**Sprint 3 — Production Reliability + Calibration** (5 commits on `claude/review-dev-roadmap-6K19V`)

**Calibration:**
- `_FT_PEAK_FULL_PCT` 10.0 → 7.0 (empirically validated Minervini wizard threshold)
- payoff < 0.8 penalty -12 → -15 (Mark's red line)
- RISK_LADDER revised to `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (uniform cadence)
- `profit_factor` sentinel unified to `math.inf` (analytics + adaptive risk + display)

**Production reliability:**
- `analytics_engine.py:250` → `get_campaign_risk_metrics()` (LONG/SHORT + fallback)
- `bot_core.py` fail-fast validation (TOKEN, ADMIN_ID int-check, SUPABASE credentials)
- `docker-compose.yml` hardened (healthcheck, mem_limit 1.5 GB, log rotation, named volume)

**Test infrastructure:**
- `tests/conftest.py` — 4 shared fixtures (mock_supabase, mock_yfinance, sample positions)
- `tests/test_integration.py` — 7 cross-module integration tests
- `pytest.ini` markers (unit / integration / slow)
- `requirements-dev.txt` pytest-cov added

**Tests: 1191 passing** (was 1182 — +9 new tests).

**Still open for Meeting 4:**
1. Heat Score visualization in Telegram (S9/M21/L50 thermometer) — Maya's requirement
2. Add-On Engine Phase 2 (Supabase schema + dashboard + alerts)
3. 48h Settle Period empirical validation
4. SSH setup on Orange Pi (user action)
5. `fmt_heat_thermometer()` in `telegram_formatters.py`
6. Safe Markdown splitting in `telegram_portfolio.py`
7. Developer menu PIN gate

## Phase 9 — Meeting 4 & Sprint 4

Status: **complete** — 2026-05-13

Mark's Final Verdict Meeting 4: **8.6/10** → Sprint 4 delivered.

**Sprint 4 — completed:**
1. ✅ Real Healthchecks — mtime-based liveness probes (4 services + tests)
2. ✅ GitHub Actions CI — `claude/**` branch coverage added
3. ✅ `compute_suggested_trail_stop()` — RUNNER trailing stop in engine_core.py + wired into risk_monitor.py
4. ✅ `fmt_heat_thermometer()` — visual S9/M21/L50 thermometer bar in telegram_formatters.py
5. ✅ `/addon` inline keyboard [אשר/בטל] — confirmation flow in telegram_bot.py + telegram_callbacks.py
6. ✅ Developer menu PIN gate (`DEV_PIN` env var, 30-min session) — telegram_devops.py + telegram_bot.py
7. ✅ `ADMIN_ID > 0` validation — bot_core.py fail-fast
8. ✅ `docs/DESIGN_SYSTEM.md` — emoji/icon palette, heat labels, position states, healthcheck table
9. ✅ Tests: 1201/1201 (+6 trailing stop, +4 healthcheck vs Sprint 3's 1195)

**Still open for Meeting 5:**
- Add-On Engine Phase 2 — Supabase schema + `/addon` dashboard
- 48h Settle Period — empirical validation (production data needed)
- SSH setup on Orange Pi — user action
- Merge PR #15 → main — requires human approval
- E2E test `test_e2e_risk_monitor.py`
- Coverage report baseline (≥75% enforced by pytest-cov)

## Phase 10 — Meeting 5 & Sprint 5

Status: **planned** — see `docs/CHATGPT_TEAM_PROMPT_V4.md`.

## Parking lot

Ideas to consider later:

- GitHub Issues integration for tasks.
- Release notes automation.
- Structured JSON report outputs.
- Portfolio scenario simulator.
- Local command scripts for deploy and smoke tests.
