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

### REQ-20260511-002 — ALGO Observer Mode: management_mode field and stop display

Status: approved
Owner: both
Area: risk engine / dashboard / Telegram
Priority: High

User request:
- Sentinel must not manage ALGO positions as if they were discretionary EP/VCP trades.
- Sentinel's role for ALGO: oversight, measurement, deviation alerting — not exit or stop instructions.
- Replace `Current Stop: $0.00` display with a meaningful ALGO-aware status.
- Add a formal `management_mode` field to every campaign/position.

management_mode values:
- `manual_managed`: user manages manually per EP/VCP rules
- `system_assisted`: Sentinel suggests; user approves
- `algo_observed`: external algo manages; Sentinel observes only
- `unknown`: missing — exclude from quality statistics until fixed

Stop display for ALGO:
- Do NOT show `Current Stop: $0.00`.
- Show: `Stop Status: Managed externally by ALGO / Stop Visibility: Unknown`.

Formal rule (must be enforced in code and display):
> Sentinel must not grade ALGO trades using discretionary EP/VCP management rules
> unless the ALGO rule-set is explicitly imported and mapped.

Acceptance criteria:
- [ ] `management_mode` field added to campaign data structure (engine_core or Supabase column)
- [ ] Dashboard and Telegram no longer show `$0.00` stop for ALGO positions
- [ ] ALGO positions show `Stop Status: External / Unknown` instead
- [ ] `unknown` mode positions excluded from quality statistics
- [ ] `algo_observed` positions excluded from EP/VCP execution discipline scoring

Related files:
- `engine_core.py`
- `dashboard.py`
- `telegram_formatters.py`
- `docs/DATA_CONTRACTS.md`

---

### REQ-20260511-003 — Risk Basis classification: True / Target / Estimated / Unknown

Status: approved
Owner: both
Area: risk engine / dashboard / Telegram
Priority: High

User request:
- Current system conflates R calculations from different bases, creating misleading statistics.
- Every R value must carry an explicit risk basis label.

Risk basis types:
- `True Risk R`: EP/VCP with real, known stop — enters all quality statistics
- `Target Risk R`: ALGO or trade without known stop — uses Target Risk USD as denominator
- `Estimated Risk R`: partial data, approximated stop
- `Unknown Risk R`: do not include in quality statistics

ALGO R formula: `ALGO_R = PnL / Target_Risk_USD`
This is `Target Risk Deviation`, NOT a manual stop violation.

Risk Visibility Score per position (0–100):
- 100: stop known, risk known, quantity known
- 80: stop known, minor gaps
- 60: Target Risk basis only
- 40: external ALGO, no visible stop
- 20: no stop, no rule, no Target Risk
- 0: broken data

Acceptance criteria:
- [ ] `risk_basis` field added to position data: True/Target/Estimated/Unknown
- [ ] `risk_visibility_score` computed per position (0–100)
- [ ] Dashboard shows risk basis and visibility score per position
- [ ] Telegram position cards include risk basis label
- [ ] R statistics filter: True Risk R only for EP/VCP quality metrics

Related files:
- `engine_core.py`
- `dashboard.py`
- `telegram_formatters.py`

---

### REQ-20260511-004 — Statistical isolation: Strategy Contamination Guard

Status: approved
Owner: both
Area: risk engine / dashboard
Priority: High

User request:
- EP, VCP, and ALGO must not share the same performance statistics.
- Mixing them produces false conclusions (e.g., "my EP discipline is weak" when it's an ALGO issue).
- Every campaign must be assigned a `stat_bucket` that controls which statistics it enters.

stat_bucket values:
- `EP_MANUAL`: enters EP statistics
- `VCP_MANUAL`: enters VCP statistics
- `ALGO_OBSERVED`: enters ALGO statistics only
- `TEST_PROBE`: excluded from full performance metrics
- `DATA_INCOMPLETE`: excluded from all statistics
- `BROKER_SYNC_ONLY`: IBKR data only, no qualitative scoring

Required separate performance views:
- Discretionary (EP + VCP combined)
- ALGO only
- Combined portfolio

Per-view metrics: Win Rate, Avg Winner, Avg Loser, Profit Factor, Expectancy, Max Loss, Max Win,
Largest Giveback, Avg Holding Time, Risk Deviation, Exposure Contribution, Drawdown Contribution.

ALGO-specific metric replacing Execution Score:
- `ALGO Risk Oversight Score` (0–100): weighted across exposure compliance (25%),
  target risk deviation (25%), drawdown contribution (20%), giveback after profit (15%),
  consecutive loss frequency (15%).

Acceptance criteria:
- [ ] `stat_bucket` field added to campaign data
- [ ] `analytics_engine.py` separates stats into EP / VCP / ALGO / Combined buckets
- [ ] Dashboard shows three separate performance tabs/sections
- [ ] ALGO positions get `ALGO Risk Oversight Score`, not `Execution Score`
- [ ] DATA_INCOMPLETE campaigns never enter Expectancy or Win Rate calculations

Related files:
- `analytics_engine.py` (new or extended)
- `engine_core.py`
- `dashboard.py`

---

### REQ-20260511-005 — Risk Deviation Engine + Giveback Monitor + Profit Protection

Status: approved
Owner: both
Area: risk engine / Telegram / risk-monitor
Priority: High

User request:
- System must detect when a position deviates materially from its risk target.
- System must detect profit giveback (peak → current open R drop).
- These apply to all positions but with different response: manage (manual) vs alert-only (ALGO).

Risk Deviation Engine:
- `risk_deviation_r = actual_open_loss / target_risk_usd`
- Classification: ≤1R normal / 1–1.5R minor / 1.5–2R moderate / 2–3R severe / >3R system event
- For EP/VCP: potential discipline violation. For ALGO: `External Risk Deviation`, not manual error.

ALGO Guardrail alert thresholds (observe/alert only, no exit instruction):
- Open loss ≤ 0.75R: info only
- Open loss 1.0R: watch
- Open loss 1.5R: alert — target risk exceeded
- Open loss 2.0R: severe alert — verify algo is running correctly
- Open loss > 3.0R: system event — algo outside risk framework

Giveback Monitor:
- `giveback_from_peak_r = peak_open_r - current_open_r`
- Classification: ≤20% of peak profit: natural / 20–35%: watch / 35–50%: tighten / >50%: profit protection failure
- For manual: action suggestion. For ALGO: alert only.

Profit Protection Checkpoints (at 2R, 3R milestones):
- Manual: suggest stop raise / partial exit / trailing stop
- ALGO: `Profit Protection Checkpoint — Sentinel is not modifying ALGO management. Monitoring giveback.`

Acceptance criteria:
- [ ] `compute_risk_deviation(position)` added to `engine_core.py`
- [ ] `compute_giveback_from_peak(position)` added to `engine_core.py` (tracks peak_open_r in state)
- [ ] `risk_monitor.py` sends ALGO guardrail alerts at defined thresholds
- [ ] Alerts clearly labeled: manual = potential violation, ALGO = oversight alert
- [ ] Profit Protection Checkpoints fired at 2R and 3R milestones
- [ ] Tests for risk deviation classification

Related files:
- `engine_core.py`
- `risk_monitor.py`
- `telegram_formatters.py`

---

### REQ-20260511-006 — Actionability Layer and Telegram message architecture

Status: approved
Owner: both
Area: Telegram
Priority: High

User request:
- Every Sentinel message must declare whether it requires action, review, observation, or is a system alert.
- This prevents false urgency and prevents dismissing real alerts.

Actionability levels:
- `Action Required`: user must take a trade action
- `Review Required`: check something, action optional
- `Observation Only`: FYI, no action needed
- `System Health`: data/sync issue
- `External Managed`: algo is handling, Sentinel is observing

ALGO Telegram message template:
```
🧠 Sentinel Risk Note
Symbol: PLTR | Strategy: ALGO | Mode: External Managed
Open R: -1.42R (Target Risk Base) | Exposure: 6.1%
Actionability: Review Required
מה קרה: הפוזיציה חרגה מאזור מעקב רגיל ביחס לסיכון יעד.
Sentinel אינה יודעת חוקי יציאה. אין המלצת יציאה ידנית.
פעולה: לוודא שהאלגו פעיל ומחובר.
```

Acceptance criteria:
- [ ] `actionability` field added to all Telegram message generators
- [ ] ALGO positions never receive "Action Required" exit/stop instructions
- [ ] `telegram_formatters.py` includes `fmt_algo_risk_note()` template
- [ ] All existing alert types updated with actionability classification
- [ ] Manual positions still receive full management suggestions

Related files:
- `telegram_formatters.py`
- `telegram_bot.py`
- `risk_monitor.py`

---

### REQ-20260511-007 — System Health Monitor + Data Quality Badges + Position metadata

Status: approved
Owner: both
Area: dashboard / Telegram
Priority: High

User request:
- Data reliability is a prerequisite for everything else. Must surface it explicitly.
- `/health` Telegram command must check and report all critical data integrity indicators.
- Every position must display a data quality badge.
- Every position must have an `intent` field describing its role.
- Loss events must be classified by type (not all losses are equal).

/health checks:
IBKR Sync Status, Supabase Freshness, Last Execution Import, Lots Rebuild Status,
Campaign Truth Status, Risk Snapshot Freshness, Missing Stops, Unknown Risk Positions,
ALGO External Positions, Duplicate Campaigns, Open Quantity Mismatch, NAV Consistency,
Alert Engine Status.

Data Quality Badges (per position in dashboard and Telegram):
- ✅ Verified: complete data
- ⚠️ Partial: missing non-critical field
- 🟠 External: algo-managed
- 🔴 Broken: missing critical data
- 🧪 Probe: test trade
- 📊 Target-Based: R from Target Risk
- 🧮 True-Risk: R from actual stop

Position Intent field:
- `starter` / `probe` / `full_position` / `runner` / `earnings_hold` / `algo_signal` / `reentry`
- Probes and runners are not judged by the same standards as full positions.

Mistake Classification (for closed campaigns):
- `Good Loss`: loss per plan
- `Bad Loss`: unauthorized entry or stop not honored
- `System Loss`: algo/sync/order failure
- `Market Loss`: gap or extraordinary event
- `Data Loss`: unreliable calculation
- `Probe Loss`: planned small loss

Acceptance criteria:
- [ ] `/health` command added to `telegram_bot.py`
- [ ] Data quality badge computed per position in `engine_core.py` or `dashboard.py`
- [ ] `intent` field added to campaign data
- [ ] `mistake_classification` field available for closed campaigns
- [ ] Dashboard shows badges and intent labels per position
- [ ] `Probe Loss` and `Good Loss` excluded from discipline violation counts

Related files:
- `telegram_bot.py`
- `engine_core.py`
- `dashboard.py`

---

### REQ-20260511-008 — Portfolio Heat Map + Earnings Risk Module + AI Context Export upgrade

Status: approved
Owner: both
Area: dashboard / Telegram / AI export
Priority: Medium

User request:
- Dashboard must show portfolio risk by cluster (EP / VCP / ALGO / concentration / cash).
- System must surface earnings risk for open positions before the event.
- AI context export must explicitly document ALGO state to prevent AI advisors from giving wrong instructions.

Portfolio Heat Map (dashboard):
Cluster | Exposure % | Open R | Risk Contribution | Status
EP / VCP / ALGO / Single Stock Concentration / Cash

The system should say: "You are not at risk because of position count. You are at risk because of concentration, correlation, or an ALGO that is deviating."

Earnings Risk Module (per open position):
- Next Earnings Date, Days to Earnings, Current Open R, Realized Profit Taken, Remaining Size
- Output: "MTZ: X days to earnings. Cushion: Y R. Decision required: exit / reduce / hold runner."

AI Master Context Export additions:
- Explicit ALGO section: "ALGO positions are externally managed. Sentinel does not know internal stop/exit rules. ALGO R uses Target Risk Base. Do not classify missing stop as manual discipline violation."
- `stat_bucket` per position in export
- `risk_basis` per position in export
- `actionability` per alert in export
- `management_mode` per position in export
- Open questions and next required decisions section

Acceptance criteria:
- [ ] Portfolio Heat Map tab or section in dashboard
- [ ] Earnings risk module: next earnings date fetched per open position
- [ ] AI export includes management_mode, risk_basis, stat_bucket, ALGO note
- [ ] AI export includes "Next Required Decisions" section

Related files:
- `dashboard.py`
- `engine_core.py`
- `telegram_bot.py` (AI export command)

---

### REQ-20260512-001 — Telegram alerts must include inline decision buttons

Status: validated
Owner: user
Area: Telegram / risk_monitor
Priority: Medium

User request (2026-05-12):
- Actionable items in risk alerts (e.g. Runner Mode "✅ להחזיק", "🔒 הדק סטופ") should not remain
  as plain text. They should be presented as Telegram inline keyboard buttons.
- When the user clicks a button, the system must record the decision.
- The system must track and act on the decision in subsequent monitoring cycles.
- "לא משאירים דברים באוויר" — every alert that requires a decision must lead to one.

Acceptance criteria:
- [x] Runner Mode alert includes inline keyboard with ≥ 3 actionable buttons.
- [x] Clicking a button sends an acknowledgement and persists the decision.
- [x] Decision (+ timestamp) is saved to `management_notes` in Supabase or to state JSON.
- [x] Risk monitor reads the stored decision and suppresses duplicate alerts for 24h after "hold" decision.
- [x] Multi-step flows (e.g. "הדק סטופ" → ask for price → confirm) work without crashing the bot.
- [x] ALGO positions never get decision buttons that imply exit/stop instructions.

Implementation:
- See TASK-20260512-008.
- Production-confirmed: MRVL Runner alert produced buttons, user clicked Hold,
  follow-up alerts suppressed for 24h.

Related files:
- `risk_monitor.py`
- `telegram_callbacks.py` (post-Phase-4 home of the handler)
- `bot_helpers.py` (`_write_runner_decision`)
- `risk_monitor_state.json` (decision persistence)

---

### REQ-20260512-002 — Auto-import IBKR trades into Supabase + notify with backlog button

Status: validated
Owner: user
Area: sync / database / Telegram
Priority: High

User request (2026-05-12):
- After an IBKR sync (auto or manual), if new trades exist in the XML, the
  system must insert them into Supabase automatically.
- The user must receive a Telegram message stating "N new trades found".
- That message must include an inline button that opens the backlog journal
  (`get_next_missing`) so missing fields (setup, quality, stop, etc.) can be
  filled in.

Acceptance criteria:
- [x] Parse `<Trade>` elements from the saved Flex XML.
- [x] Skip trades already present in Supabase (deduplicate by `trade_id`).
- [x] Assign `campaign_id` using the production format
      `{SYMBOL}_{tradeID of first BUY}`; new BUYs without an open campaign
      start a fresh one; SELLs join the open campaign; closed campaigns
      (net qty = 0) do not attract the next BUY.
- [x] Store `quantity` signed (BUY positive, SELL negative) to remain
      compatible with `engine_core.get_open_positions_campaign`.
- [x] Send Hebrew Telegram message with inline "📚 פתח סריקת יומן" button.
- [x] Hook into manual sync via Telegram developer menu.
- [x] Hook into manual XML upload via Telegram developer menu.
- [x] Hook into auto-sync in `main.py` (sentinel-bot container — uses raw
      Telegram HTTP API since telebot SDK is not present there).
- [x] Inserted trade appears in `/portfolio` (חדר מצב) and on the dashboard.
- [ ] First successful auto-sync of the day produces the expected
      notification — pending observation in the next 07:00–11:00 window
      (see TASK-20260512-013).

Implementation:
- See TASK-20260512-010.
- New module: `ibkr_trade_importer.py`.

Related files:
- `ibkr_trade_importer.py`
- `supabase_repository.py` (`get_existing_trade_ids`, `insert_trades`)
- `telegram_devops.py` (`_import_and_notify`)
- `main.py` (`import_trades_and_notify`)
- `telegram_callbacks.py` (`open_backlog` callback)

---

### REQ-20260512-003 — Refactor `telegram_bot.py` for sustainable AI-agent development

Status: validated
Owner: agent (with user approval)
Area: code organization / maintainability
Priority: Medium

User intent (implicit, supports REQ-20260509-003):
- `telegram_bot.py` had grown to ~2000 lines, making AI-agent edits
  error-prone and tests hard to scope. Split into focused modules.

Acceptance criteria:
- [x] Module split preserves all public-facing flows.
- [x] `telegram_bot_secure_runner.py` continues to work without changes
      (uses `telegram_bot.bot.infinity_polling()`).
- [x] Existing tests pass; new modules covered by their own tests.
- [x] `telegram_bot.py` size reduced significantly.

Outcome:
- `telegram_bot.py`: ~2000 → 457 lines (−77%).
- 9 new modules; +113 new tests; 1088/1088 pass.

Implementation:
- See TASK-20260512-009.

---

### REQ-20260512-004 — Container DNS must not depend on local router

Status: validated
Owner: agent (operational fix)
Area: deployment / infra
Priority: Medium

User-observed problem (2026-05-12):
- Both auto and manual IBKR syncs were failing intermittently with
  `NameResolutionError`. Telegram polling was also seeing
  `Network is unreachable` errors.

Acceptance criteria:
- [x] Containers resolve DNS via public servers (`8.8.8.8`, `1.1.1.1`),
      not via the home router.
- [x] `socket.gethostbyname` for `api.telegram.org` and
      `www.interactivebrokers.com` succeed from inside the container.
- [x] Sync that had been failing now completes.

Implementation:
- See TASK-20260512-011.
- `docker-compose.yml`: `dns:` block per service.

---

## Completed / validated requirements

Move requirements here only after validation on server.
