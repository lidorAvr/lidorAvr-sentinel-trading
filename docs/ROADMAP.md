# Sentinel Trading Roadmap

This roadmap keeps future development focused and prevents scattered AI-agent work.

## Guiding principle

Build a system that is accurate, safe, fast to extend, and aligned with the user's trading process.

## Phase 1 — Safety and agent-readiness

Status: in progress

Goals:

- Add agent context docs.
- Add user requirement tracking.
- Add agent task tracking.
- Keep Telegram protected by secure runner.
- Keep deployment commands documented.

Done:

- `AGENTS.md`
- `CLAUDE.md`
- docs under `docs/`
- `telegram_bot_secure_runner.py`
- Docker Compose command updated for Telegram service

Remaining:

- Verify deployment on Orange Pi.
- Strengthen tests on `main`.

## Phase 2 — Data truth and NAV reliability

Status: planned

Goals:

- Define one explicit NAV/account-size source.
- Ensure all services read the same assumption.
- Add visible freshness/fallback labels.
- Add tests for fallback behavior.

Suggested tasks:

- Create `config.py` or `account_state.py`.
- Add `DataFreshness` enum or simple source labels.
- Add tests for live/cached/fallback reporting.
- Add server validation checklist.

## Phase 3 — Risk and campaign engine hardening

Status: planned

Goals:

- Lock down campaign aggregation.
- Validate R calculations with sample rows.
- Protect partial sell / runner mode math.
- Document ALGO vs discretionary differences.

Suggested tasks:

- Add trade-row fixtures.
- Add campaign scenarios:
  - single buy open
  - partial sell runner
  - add-on buy
  - final close
  - missing stop
  - ALGO position

## Phase 4 — Telegram refactor

Status: planned

Goals:

- Split `telegram_bot.py` into smaller modules.
- Preserve existing flows.
- Make messages shorter and more consistent.
- Move secure runner protections into explicit code once safe.

Suggested module split:

- `telegram_handlers.py`
- `telegram_formatters.py`
- `telegram_backlog.py`
- `telegram_portfolio.py`
- `telegram_callbacks.py`
- `supabase_repository.py`

Rules:

- Refactor only one concern at a time.
- Do not mix feature work with refactor.
- Keep Docker command on secure runner until protections are moved and tested.

## Phase 5 — Dashboard and reporting upgrades

Status: planned

Goals:

- Align dashboard calculations with `engine_core.py`.
- Show data freshness.
- Add portfolio/risk summaries.
- Improve Hebrew display where relevant.

## Phase 6 — Automation and intelligence layer

Status: future

Goals:

- Smarter risk monitor.
- Better alerts.
- More accurate management suggestions.
- More automated journal/backlog workflows.

Rules:

- No automatic trade state mutation without explicit user-approved rules.
- Alerts must be bounded to avoid noise.
- Every automated suggestion must explain evidence and trigger.

## Parking lot

Ideas to consider later:

- GitHub Issues integration for tasks.
- Release notes automation.
- Structured JSON report outputs.
- Dedicated test fixtures folder.
- Local command scripts for deploy and smoke tests.
- Portfolio scenario simulator.
