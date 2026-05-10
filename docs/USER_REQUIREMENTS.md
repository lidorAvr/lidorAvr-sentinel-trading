# User Requirements Registry

This file is the living source of user requirements, preferences, and requested product direction.

It exists to reduce repeated explanations and keep AI agents aligned with the user's actual goals.

## How to use this file

When the user asks for a new capability, change, rule, preference, or product direction, add it here before or during implementation.

Every requirement should be tracked from request to delivery.

## Requirement states

Use one of these states:

- `proposed` — user mentioned it, but scope is not fully defined
- `approved` — user explicitly approved the direction
- `in_progress` — agent is actively implementing it
- `implemented` — code/docs changed
- `validated` — tested in CI or manually on server
- `blocked` — cannot continue without missing access/data/decision
- `rejected` — intentionally not doing it

## Requirement template

```markdown
### REQ-YYYYMMDD-001 — Short title

Status: proposed / approved / in_progress / implemented / validated / blocked / rejected
Owner: user / agent / both
Area: Telegram / risk engine / dashboard / sync / database / deployment / docs
Priority: High / Medium / Low

User request:
- ...

Acceptance criteria:
- ...
- ...

Implementation notes:
- ...

Validation:
- [ ] tests added or updated
- [ ] CI passed
- [ ] manual server test completed
- [ ] user confirmed

Related files:
- ...
```

## Active requirements

### REQ-20260509-001 — Preserve truth in user-facing trading reports

Status: approved
Owner: both
Area: Telegram / risk engine / sync
Priority: High

User request:
- The system must show the user truth only.
- If live data is unavailable and fallback/cached/default values are used, reports must clearly say so.

Acceptance criteria:
- Telegram reports identify data source or uncertainty when relevant.
- NAV/account-size assumptions are not silently mixed.
- Risk and exposure numbers are not presented as exact if based on fallback data.

Implementation notes:
- Covered partially by telegram_bot_secure_runner.py (data source disclosure).
- NAV auto-update via IBKR improved in main.py (v16.0) — but server deployment pending.

Validation:
- [ ] NAV verified to auto-update from IBKR report (not just manual config)
- [ ] Telegram reports mark cached/estimated data correctly
- [ ] Server deployment of main.py v16.0 completed

Related files:
- `telegram_bot_secure_runner.py`
- `telegram_bot.py`
- `engine_core.py`
- `main.py`
- `docs/DATA_CONTRACTS.md`

---

### REQ-20260509-002 — Keep Telegram safe, clear, short, and Hebrew-friendly

Status: validated
Owner: both
Area: Telegram
Priority: High

User request:
- Telegram messages must be clear, accurate, not overloaded, and suitable for Hebrew RTL readers.
- The bot must include smart anti-spam behavior.

Acceptance criteria:
- Telegram service runs through `telegram_bot_secure_runner.py`.
- Admin-only access remains active.
- Rate limit and cooldown remain active.
- Long reports are split safely.
- Reports remain readable in Hebrew.

Implementation notes:
- telegram_bot_secure_runner.py is implemented and correct.
- Server deployment not yet validated.

Validation:
- [x] `docker compose ps` shows telegram-bot running through secure runner
- [x] Bot active and responding (confirmed 2026-05-10)
- [ ] `/portfolio`, `/next`, `/trade CAT` individually verified
- [ ] Rate limiting confirmed via rapid message test

Additional fix (2026-05-10):
- Overnight alert spam fixed: repeat "Broken" alerts now suppressed outside US market hours
  (11:00–21:00 UTC / 14:00–00:00 Israel, Mon–Fri).

Related files:
- `telegram_bot_secure_runner.py`
- `telegram_bot.py`
- `docker-compose.yml`
- `risk_monitor.py`

---

### REQ-20260509-003 — Support efficient AI-agent development

Status: validated
Owner: both
Area: docs / workflow
Priority: High

User request:
- The repo should contain context files so Claude Code and other AI agents can understand the project quickly.
- Agents should not break unrelated parts while improving one part.

Acceptance criteria:
- [x] Agent operating guide exists (AGENTS.md).
- [x] Claude-specific context exists (CLAUDE.md).
- [x] Data contracts exist (docs/DATA_CONTRACTS.md).
- [x] Safe change protocol exists (docs/SAFE_CHANGE_PROTOCOL.md).
- [x] Agent task and user requirement tracking exist and are updated.

Related files:
- `AGENTS.md`, `CLAUDE.md`, `docs/README.md`, `docs/AI_AGENT_CONTEXT.md`
- `docs/SAFE_CHANGE_PROTOCOL.md`, `docs/AGENT_TASKS.md`, `docs/USER_REQUIREMENTS.md`

---

### REQ-20260509-004 — Dashboard must be fast and responsive

Status: implemented
Owner: both
Area: dashboard
Priority: High

User request:
- Dashboard is very slow — takes too long to load between pages.
- All data should load within seconds without removing any features.

Acceptance criteria:
- [x] Open position data loads in parallel (not sequentially).
- [x] No duplicate network calls for prices already fetched.
- [ ] Dashboard loads open positions in under 3 seconds (manual verification needed).
- [ ] No regression in displayed data or calculations.

Implementation notes:
- Added prefetch_symbols_parallel() using ThreadPoolExecutor (max 8 workers).
- Pre-warms engine_core YF_CACHE before the serial analysis loop.
- AI context export now reuses live_df prices instead of re-fetching.
- No changes to any calculation or formula.

Validation:
- [x] Code implemented and pushed
- [ ] Manual load-time test on Orange Pi server after deployment

Related files:
- `dashboard.py`

---

### REQ-20260509-005 — Math accuracy and Minervini alignment

Status: implemented
Owner: both
Area: risk engine / dashboard
Priority: High

User request:
- Verify all calculations are performed correctly and formulas are accurate.
- Separate planned calculations from actual results (planned risk vs actual risk, planned R:R vs actual R).
- Add missing Minervini metrics and statistics so the system can give smarter, more professional recommendations.
- The system's math, logic, and risk management should align with Mark Minervini's methodology from his two books.

Acceptance criteria:
- [x] Existing R-multiple, campaign aggregation, ATR, and distribution day math audited and confirmed correct.
- [x] Trend Template expanded from 5 to 8 criteria (compute_trend_template_full).
- [x] Initial risk % of NAV computed and graded per Minervini 1-2.5% rule.
- [x] R-per-day (capital efficiency) computed and labeled.
- [x] MAE/MFE (Max Adverse/Favorable Excursion) computed from price history.
- [x] Add-on quality check: validates pyramiding above entry only (Minervini rule).
- [x] Planned vs actual risk display in dashboard for open positions.
- [x] 21 deterministic unit tests added, all passing.
- [ ] Trend Template 8-criteria result displayed in dashboard UI (not yet wired up).
- [ ] Add-on quality result displayed in dashboard UI (not yet wired up).
- [ ] Planned vs actual section added to closed campaigns (Visual Journal tab).
- [ ] Target price field added to Supabase schema (blocked — HIGH risk schema change, separate task).
- [ ] All new metrics verified against real trade data on server.

Implementation notes:
- All 5 new functions are additive — no existing engine_core functions were modified.
- get_minervini_analysis() (Telegram-facing, 5-rule) left unchanged for backward compatibility.
- compute_trend_template_full() is the new full 8-criteria function, dashboard-only.
- MAE/MFE limited to 1-year history window; positions older than 1 year return None.
- Planned R:R (pre-entry target) requires target_price in Supabase — not implemented (blocked).

Validation:
- [x] pytest -q: 24/24 tests pass
- [ ] Dashboard planned-vs-actual section verified manually with real positions
- [ ] MAE/MFE values cross-checked against TradingView chart

Related files:
- `engine_core.py`
- `dashboard.py`
- `tests/test_trade_metrics.py`

---

### REQ-20260509-006 — IBKR sync: smart timing, retry logic, report retention

Status: implemented
Owner: both
Area: sync / deployment
Priority: High

Note: partially validated. Timezone bug found and fixed on 2026-05-10.
Full validation pending next morning sync at 07:xx Israel.

User request:
- IBKR sync should only attempt at times when reports are actually ready (07:00-11:00 Israel time).
- Retry mechanism: try once per hour, max 3 attempts, then alert via Telegram.
- Save last 3 IBKR XML reports for debugging.
- Stop retrying once a report is successfully received for the day.

Acceptance criteria:
- [x] Sync window: 07:00–11:00 Asia/Jerusalem (server timezone confirmed IDT +0300).
- [x] One attempt per clock-hour (not every 15-min poll tick).
- [x] State tracked in /app/ibkr_sync_state.json.
- [x] XML saved to /app/ibkr_reports/, last 3 kept.
- [x] Telegram alert sent after 3 failures.
- [x] Telegram success notification sent when report received.
- [ ] Deployed and verified on Orange Pi.
- [ ] First morning report received and XML file confirmed saved.

Implementation notes:
- main.py rewritten to v16.0. Old v15.0 used hour>=6 with no retry logic.
- IBKR reports are end-of-previous-day, typically ready 07:15-07:30 Israel time.
- Server timezone: Asia/Jerusalem (IDT +0300) — datetime.now() gives correct local time.

Validation:
- [x] Code implemented and pushed
- [x] Deployed on Orange Pi (2026-05-10)
- [x] Failure alert confirmed received after 3 failed attempts
- [x] Timezone bug found, fixed, and redeployed (ZoneInfo + TZ env var)
- [x] New Query ID (1503908) added to .env
- [ ] /app/ibkr_reports/ directory auto-created on first run (pending tomorrow)
- [ ] NAV verified in sentinel_config.json after morning sync (pending tomorrow)
- [ ] Report received at 07:xx Israel time (pending tomorrow)

Related files:
- `main.py`
- `docker-compose.yml`
- `requirements.txt`

## Completed / validated requirements

Move requirements here only after validation on server.
