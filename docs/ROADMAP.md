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

Status: in progress (partially complete)

Goals:

- Lock down campaign aggregation.
- Validate R calculations with sample rows.
- Protect partial sell / runner mode math.
- Document ALGO vs discretionary differences.
- Add ALGO Observer Mode: management_mode, risk_basis, risk_visibility_score.
- Add Risk Deviation Engine and Giveback Monitor.

Completed:
- Minervini metrics (initial risk, R/day, MAE/MFE, Trend Template full, add-on quality) ✅
- Adaptive risk engine (weighted win rate, risk ladder, proactive alerts, /stats) ✅
- `analytics_engine.py`: period analytics, profit factor, expectancy, dev score ✅
- Comprehensive math tests: R-multiples, PF edge cases, dev score bounds, oversized boundary ✅

Remaining tasks (→ TASK-20260511-002 through -005):
- ALGO Observer Mode foundation (TASK-20260511-002)
- management_mode + risk_basis + risk_visibility_score (TASK-20260511-003)
- Statistical isolation: stat_bucket + ALGO Risk Oversight Score (TASK-20260511-004)
- Risk Deviation Engine + Giveback Monitor (TASK-20260511-005)

## Phase 3B — ALGO Observer Mode and Risk Isolation

Status: planned (tasks defined 2026-05-11)

Guiding principle:
Sentinel is an oversight and measurement layer for ALGO positions, not a manager.
Sentinel must never issue stop-raise or exit instructions for externally managed ALGO positions.

Key deliverables (in priority order):
1. Replace `Current Stop: $0.00` with `External / Unknown` for ALGO positions.
2. Separate statistics: Discretionary (EP+VCP) / ALGO / Combined.
3. Add `risk_basis` field: True / Target / Estimated / Unknown.
4. Add ALGO Risk Deviation Alerts via risk_monitor.
5. Add Giveback Monitor.
6. Add System Health `/health` command + Data Quality Badges.
7. Add Actionability Layer (Action Required / Review Required / Observation / External Managed).
8. Add AI Master Context Export with ALGO state documentation.
9. Add Mistake Classification for closed campaigns.

Formal ALGO rule (must be enforced in code):
> Sentinel must not grade ALGO trades using EP/VCP management rules
> unless the ALGO rule-set is explicitly imported and mapped.

## Phase 4 — Telegram refactor

Status: planned (partially complete — telegram_formatters.py created, hierarchical menus done)

Goals:

- Split `telegram_bot.py` into smaller modules.
- Preserve existing flows.
- Make messages shorter and more consistent.
- Move secure runner protections into explicit code once safe.
- Apply Actionability Layer to all messages (→ TASK-20260511-006).

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

Status: in progress (partially complete)

Goals:

- Align dashboard calculations with `engine_core.py`.
- Show data freshness and Risk Visibility Score per position.
- Add Portfolio Heat Map (cluster-level exposure + open R) (→ TASK-20260511-007).
- Add Earnings Risk Module per open position (→ TASK-20260511-007).
- Add System Health tab (→ TASK-20260511-006).
- Separate statistics view: Discretionary / ALGO / Combined (→ TASK-20260511-004).
- Improve Hebrew display where relevant.

Completed:

- PDF weekly/monthly report service (WeasyPrint + Jinja2 + Plotly charts) ✅
- Weekly/monthly Telegram summary with Hebrew coaching insights ✅
- WoW/MoM comparison via snapshot store ✅
- Plotly charts embedded in PDF (campaign R bars, setup perf, equity curve, win/loss donut) ✅
- IBKR sync pipeline fully operational: ReferenceCode fix, gdcdyn URL, log_fn, raw response logging ✅ (session 6)
- Manual XML upload fallback: `📤 העלה דוח XML` in developer menu — confirmed working ✅ (session 6)

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
