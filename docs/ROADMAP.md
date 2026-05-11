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

Remaining module split:
- `telegram_handlers.py`
- `telegram_backlog.py`
- `telegram_portfolio.py`
- `telegram_callbacks.py`
- `supabase_repository.py`

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

Status: future

Goals:

- Smarter risk monitor.
- Better ALGO-aware alerts (guardrail thresholds, giveback, profit protection checkpoints).
- More accurate management suggestions with actionability classification.
- More automated journal/backlog workflows.

Rules:

- No automatic trade state mutation without explicit user-approved rules.
- ALGO positions must never receive automated exit instructions.
- Alerts must be bounded to avoid noise.
- Every automated suggestion must explain evidence, trigger, and actionability level.

## Parking lot

Ideas to consider later:

- GitHub Issues integration for tasks.
- Release notes automation.
- Structured JSON report outputs.
- Portfolio scenario simulator.
- Local command scripts for deploy and smoke tests.
