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

---

### REQ-20260510-001 — Dashboard performance: eliminate residual slow loads

Status: implemented
Owner: both
Area: dashboard
Priority: High

User request:
- Dashboard is still very slow despite the parallel prefetch added in the previous session.
- All data should load within seconds on repeated interactions, not just first load.

Acceptance criteria:
- [x] `_warm_symbol_cache` fetches "1y" history (same period as MAE/MFE and Trend Template — no cache miss)
- [x] SPY + QQQ added to parallel prefetch so regime and RS calculations are pre-warmed
- [x] `compute_market_regime` wrapped in `@st.cache_data(ttl=600)` — not recomputed on every Streamlit re-run
- [x] `compute_live_portfolio_data` TTL raised from 180s to 300s
- [ ] Load time measured on Orange Pi under 3 seconds on second interaction (manual test pending)

Implementation notes:
- Root causes found: (1) _warm_symbol_cache fetched "6mo" but MAE/MFE and TT need "1y" → cache miss per position. (2) SPY/QQQ were fetched synchronously in sidebar before any parallel warmup. (3) market regime was recomputed on every Streamlit re-run despite slow upstream calls.
- Fix is fully additive — no formula or data changes.

Related files:
- `dashboard.py`

---

### REQ-20260510-002 — Dashboard enrichment: Minervini depth + visual intelligence

Status: implemented
Owner: both
Area: dashboard
Priority: High

User request:
- Dashboard is too sparse. Missing data, explanations, and depth.
- Show Trend Template 8 criteria per position.
- Show Add-on quality (pyramiding check).
- Show strengths and weaknesses of the system.
- Show understanding of strategy, where performance is strong, where it's weak.

Acceptance criteria:
- [x] Trend Template 8-criteria shown per open position in Command Center expander (4th column)
- [x] Add-on quality (pyramiding above entry) shown per open position
- [x] New "🧠 Minervini Mentor" tab: avg TT score, win/loss streak, strengths, weaknesses, coaching insights
- [x] Visual Journal: days held + R-per-day + actual vs planned risk shown per closed campaign
- [ ] Wire analyze_addon_quality for closed campaigns (Visual Journal tab) — not yet done
- [ ] Trend Template tab or dedicated section for all open positions at once — not yet done
- [ ] target_price in Supabase for true planned R:R — blocked (schema change)

Related files:
- `dashboard.py`
- `engine_core.py`

---

### REQ-20260510-003 — Telegram: RTL formatting, hierarchical menus, Minervini commands

Status: implemented
Owner: both
Area: Telegram
Priority: High

User request:
- Telegram messages are not RTL-friendly — too cluttered or missing important info.
- Too many buttons on the main menu — overwhelming.
- Want hierarchical menus: main category → sub-menu.
- Want to upgrade to a cleaner, more actionable format.

Acceptance criteria:
- [x] Main menu reduced to 4 categories: מצב תיק / ניתוח / יומן / עזרה
- [x] Sub-menus per category with back button
- [x] telegram_formatters.py created: RTL formatting helpers (fmt_position_card, fmt_summary_footer, fmt_regime_report, fmt_minervini_trend_template)
- [x] /mentor SYMBOL command: full 8-criteria Trend Template in Telegram
- [x] 🧠 ניתוח מינרביני מלא button in analysis sub-menu
- [x] Regime report uses tf.fmt_regime_report() (cleaner RTL)
- [x] Minervini coaching insight appended to /portfolio summary
- [ ] fmt_position_card() used in /portfolio loop (portfolio loop still uses inline strings — planned for Phase 4 refactor)
- [ ] Rate limit / rapid message test not yet done

Related files:
- `telegram_bot.py`
- `telegram_formatters.py`

---

### REQ-20260510-004 — Minervini as system mentor

Status: implemented
Owner: both
Area: risk engine / dashboard / Telegram
Priority: High

User request:
- Continue integrating Mark Minervini's methodology, thinking, and recommendations.
- The system should feel like Minervini is a mentor sitting inside it.
- Provide coaching, context, strengths, weaknesses — not just numbers.

Acceptance criteria:
- [x] generate_minervini_coaching() in engine_core: coaching insights based on win_rate, expectancy, streak, regime, oversized positions
- [x] Insights rendered in Minervini Mentor tab (dashboard)
- [x] Insights appended to /portfolio Telegram report (top 2 insights)
- [x] Trend Template 8 criteria per position with color-coded score
- [x] Add-on quality check (pyramiding discipline) per position
- [ ] Per-closed-campaign Trend Template retrospective (not yet done)
- [ ] "Weekly mentor review" automated Telegram message (not yet done — future feature)

Related files:
- `engine_core.py`
- `dashboard.py`
- `telegram_bot.py`

---

### REQ-20260510-005 — Regime report data transparency

Status: implemented
Owner: both
Area: Telegram / risk engine
Priority: High

User request:
- The market regime report showed only the final verdict (🔥 Hot) without explaining the underlying data.
- User needs to see WHAT the verdict is based on: actual SPY/QQQ prices vs their MAs.

Acceptance criteria:
- [x] `compute_market_regime` returns `signals` dict with raw values (spy_close, spy_ma20, spy_ma50, qqq_close, qqq_ma20, boolean signals, score/max_score).
- [x] `fmt_regime_report` renders each criterion with ✅/❌ and actual dollar values.
- [x] Score shown as N/4 (or N/3 if QQQ unavailable).
- [ ] Verified on server with live data after deployment.

Implementation notes:
- `engine_core.py compute_market_regime` now returns `signals` key inside `data` dict — backward compatible.
- `telegram_formatters.py fmt_regime_report` renders the signals section only when `signals` key exists.

Related files:
- `engine_core.py`
- `telegram_formatters.py`

---

### REQ-20260510-006 — Adaptive risk engine: proactive risk sizing recommendations

Status: implemented
Owner: both
Area: risk engine / Telegram
Priority: High

User request:
- Bot is passive (only responds to commands). Should proactively recommend risk adjustments.
- Risk sizing based on last 50 closed campaigns; last 10 get 2x weight.
- Strong period (weighted WR ≥ 60%, no 3-loss streak): step up risk by one level.
- Weak period (weighted WR < 40% OR 3+ consecutive losses): step down fast (two levels).
- Neutral: hold current level.
- Output must show both % of NAV and dollar amount per trade.
- Confirmation via Telegram buttons: ✅ updates config; ❌ requires mandatory written reason.
- All decisions logged to risk_journal.json.
- Track adherence statistics (/stats command).
- Risk ladder: min 0.35%, max 2.50%.

Acceptance criteria:
- [x] `adaptive_risk_engine.py` created: `compute_closed_campaigns`, `compute_adaptive_risk`, `compute_adherence_stats`, `mark_adherence`, `log_risk_journal`, `update_risk_pct`.
- [x] RISK_LADDER: [0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]%.
- [x] Weighted win rate: last 10 campaigns weight=2, campaigns 11–50 weight=1.
- [x] Streak detection: consecutive wins/losses from most recent campaign.
- [x] Recommendations logged to `risk_recommendations.json` (last 200 entries).
- [x] `fmt_adaptive_risk_block` added to `telegram_formatters.py`.
- [x] Adaptive risk block in `🌡️ משטר שוק` and `/portfolio` (📊 חדר מצב) Telegram reports.
- [x] Proactive alert in `risk_monitor.py` with InlineKeyboard YES/NO, 24h throttle per direction.
- [x] YES callback: updates `sentinel_config.json` via `update_risk_pct`, marks adherence, logs to risk_journal.
- [x] NO callback: asks for mandatory written reason, logs rejection + reason to risk_journal.
- [x] `/stats` command: shows total/evaluated/followed/not_followed/adherence_pct + last 10 icons.
- [ ] `mark_adherence` wired to sentinel_config.json watch (detect manual changes outside Telegram).
- [ ] Dashboard integration: show algorithm-suggested risk % vs actual, alert on manual deviation.
- [ ] Verified on server with real closed campaign data after deployment.

Implementation notes:
- `adaptive_risk_engine.py` is standalone — no existing code was modified except import + wiring blocks.
- Adaptive risk block silently skips (try/except) on error — never breaks the main Telegram report.
- `followed` field in log is `null` until user responds to Telegram button (or `mark_adherence` called).
- `risk_journal.json` (500 entries) is the canonical decision log; `risk_recommendations.json` (200 entries) is the adherence tracker.
- Both JSON files are runtime-only — not committed to git.

Related files:
- `adaptive_risk_engine.py` (new)
- `telegram_formatters.py`
- `telegram_bot.py`
- `risk_monitor.py`
- `risk_recommendations.json` (runtime, auto-created)
- `risk_journal.json` (runtime, auto-created)

---

### REQ-20260511-001 — IBKR Flex Query: error classification + smart retry policy

Status: approved
Owner: both
Area: sync (main.py)
Priority: High

User request:
- Current sync treats all failures the same. Need to distinguish temporary vs fatal vs rate-limit errors.
- Alert messages must include the specific error code and its classification.
- GetStatement should be retried up to 3 times (60s apart) using the same ReferenceCode before counting the attempt as failed.
- SendRequest should not be re-sent within the same hourly attempt.

Error classification (per IBKR documentation):
- Temporary (retry next hour): 1001, 1004, 1005, 1006, 1007, 1008, 1009, 1019, 1021
- Fatal/config (alert immediately, do not retry): 1012, 1013, 1014, 1015, 1016, 1017, 1020
- Rate limit: 1018

Accepted sync policy:
- Primary run: 07:00 Asia/Jerusalem
- Retry window: 08:00, 09:00, 10:00, 11:00
- Max SendRequest attempts per business date: 5 (was: 3)
- Max GetStatement retries per ReferenceCode: 3, 60 seconds apart
- Final action if still failed at 11:00: alert only, include error code and classification

Acceptance criteria:
- [ ] `run_ibkr_sync()` returns structured result (success/temporary/fatal/rate_limit + code + message)
- [ ] GetStatement retried up to 3× with 60s wait using same ReferenceCode
- [ ] SendRequest not re-sent within same hourly attempt
- [ ] MAX_ATTEMPTS_PER_DAY raised from 3 to 5
- [ ] Telegram alert includes error code, classification, and human-readable explanation
- [ ] Fatal errors trigger immediate alert and skip all further retries for that day
- [ ] Rate limit (1018) logged but not counted as a config failure
- [ ] Tests added for error classification logic

Implementation notes:
- Keep `run_ibkr_sync()` signature compatible — caller loop in `__main__` handles state machine.
- Add `IBKR_ERROR_CLASSES` dict: code → ("temporary"|"fatal"|"rate_limit", Hebrew description).
- Extract `get_statement_with_retry(ref_code, token, max_retries=3, wait_sec=60)` helper.
- Return structured dict instead of bool: `{"status": "success"|"temporary"|"fatal"|"rate_limit", "code": int, "message": str}`

Related files:
- `main.py`

---

## Completed / validated requirements

Move requirements here only after validation on server.
