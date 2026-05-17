# Mark — Methodology Alignment Review (Day 1)

**Reviewer:** Mark (Methodology Owner — Minervini SEPA canon)
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-14
**Scope:** Cross-team audit on Day 1 of new Hyperscaler + Marketing team formation, with Research team challenging SYSTEM_AUDIT_2026_05.md.

This review codifies what Minervini SEPA demands of the Sentinel codebase, scores each team's Day-1 direction against that bar, predicts the inter-team conflicts I expect to surface in mid-day standup, and issues my Sprint-10 directives.

---

## Section 1 — Methodology codification (with code evidence)

What the SEPA / Champion / Stock Market Wizards canon requires of the system, with each item traced to where it lives in code (or where it is missing). All paths are absolute under `/home/user/lidorAvr-sentinel-trading`.

### 1.1 Trend Template — 8 criteria

- Required by Mark: 8-criteria gate before any discretionary entry is "stage-2-qualified".
- Implemented: `engine_core.py:719` `compute_trend_template_full(symbol)` covers all 8 criteria:
  - c1 price > MA150 and > MA200 (`engine_core.py:754`)
  - c2 MA150 > MA200 (`engine_core.py:755`)
  - c3 MA200 uptrend ≥ 1 month / 21 bars (`engine_core.py:756`)
  - c4 MA50 > MA150 and > MA200 (`engine_core.py:757`)
  - c5 price > MA50 (`engine_core.py:758`)
  - c6 price ≥ 30% above 52w low (`engine_core.py:759`)
  - c7 price ≤ 25% below 52w high (`engine_core.py:760`)
  - c8 RS vs SPY 12m (`engine_core.py:761`)
- Legacy 5-criteria Telegram path: `engine_core.get_minervini_analysis()` (see `docs/DECISIONS.md` DEC-20260509-002). Decision was intentional to avoid breaking Hebrew Telegram formatting — but it means **two coexisting Trend Template definitions**. Mark accepts this short-term; unification is a Sprint 10/11 directive (see Section 4).
- Gap: 8-criteria result is **not** wired into open-position UI yet (`docs/USER_REQUIREMENTS.md:209` REQ-20260509-005 still unchecked: *"Trend Template 8-criteria result displayed in dashboard UI (not yet wired up)"*).

### 1.2 VCP setup detection

- Required by Mark: VCP is a discretionary setup with its own statistics bucket — never mixed with EP or ALGO.
- Implemented as a *labelling* convention, not as a pattern detector:
  - `engine_core.py:1235` `_MANUAL_SETUP_PREFIXES = ("VCP", "EP", "BREAKOUT", "SWING", "TREND", "MOMENTUM")`.
  - `engine_core.classify_stat_bucket()` at `engine_core.py:1238` returns `VCP_MANUAL` when `setup_type` starts with `VCP`.
  - VCP volume contraction text is surfaced in `engine_core.py:595` (`*אינדיקציית VCP ווליום:*`).
- Gap: there is no automatic *detector* that flags "this chart is forming a VCP" — the user labels the setup at journal time. Acceptable for now; an automated VCP detector is a Sprint 11+ research item (Daria backtesting framework prerequisite — `docs/SPRINT_9_PLAN.md:146`).

### 1.3 Stage analysis (Stage 1 / 2 / 3 / 4)

- Required by Mark: Weinstein/Minervini four-stage classification — only enter Stage 2 (advancing), avoid Stage 1 / 3 / 4.
- Implemented: **NOT IMPLEMENTED as Weinstein 1-4 stages.** A grep across the repo for `Stage 1|Stage 2|Stage 3|Stage 4|weinstein` returns zero hits.
- What exists instead: `engine_core.classify_trade_stage()` at `engine_core.py:185` returns `early / developing / advanced / runner / underwater` — these are **trade-lifecycle** stages keyed off `total_r`, not market-stage classification of the underlying chart.
- Implicit proxy: the 8-criteria Trend Template effectively *is* the Stage-2 filter (MA structure + MA200 uptrend + above 52w low + near 52w high). Mark's view: the proxy is sufficient for now; an explicit `compute_market_stage()` would be a Sprint 10+ "nice to have" but not a Red Line. Logged as a directive in Section 4.

### 1.4 Stop-loss discipline (7-8% max per Minervini, R-multiple expressed as % of equity)

- Required by Mark: per-trade hard stop ≤ 7-8% below entry, R-multiple computed as `(entry − stop) × qty`.
- Implemented (computation): `engine_core.compute_original_campaign_risk()` and `engine_core.compute_r_true()` (see `docs/SYSTEM_AUDIT_2026_05.md` §2.3 Phase 4).
- Implemented (display): R-multiple is rendered in Telegram position cards (`telegram_formatters.fmt_position_card` referenced at `docs/SYSTEM_AUDIT_2026_05.md:388`).
- Implemented (account-level drawdown rule): `adaptive_risk_engine.py:27-29` enforces `DRAWDOWN_TRIGGER_PCT = -8.0` of NAV over a 30d rolling window → forced cut to `DRAWDOWN_CUT_TO_PCT = 0.40`. This is Mark's "bleeding-stop" floor from *Trade Like a Champion* ch.13 (cited verbatim at `adaptive_risk_engine.py:25-26`).
- **GAP — per-trade 7-8% rule is NOT explicitly enforced in code.** Search for `7%`, `0.07`, `0.08`, `max_stop_pct` returns nothing. The system tolerates stops set anywhere below entry. Validation only kicks in via `oversized_rate` in `analytics_engine` (post-mortem). Mark's Sprint-10 directive: add a soft warning at journal-time when `(entry − stop) / entry > 0.08`.

### 1.5 Risk per trade: dynamic via stat_bucket / heat_score

- Required by Mark: position size derived from a windowed performance read, not a static % of NAV.
- Implemented:
  - `adaptive_risk_engine.RISK_LADDER = [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (`adaptive_risk_engine.py:20`) — **note this has been tightened from the older `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` documented in `docs/SPRINT_9_PLAN.md:206` and `docs/SYSTEM_AUDIT_2026_05.md:714`.** The system is now tighter than the canonical Minervini "0.5%-1.25%" envelope — Mark approves the tightening: it removes the non-monotonic 2.50 outlier and lowers the upper rail to 2.00%, which matches *Trade Like a Champion*'s real recommendation.
  - Three-window heat score: S9 (50%) + M21 (30%) + L50 (20%), `adaptive_risk_engine.py:446-450`.
  - **Only discretionary (`_MANUAL`) campaigns enter the heat score** — `compute_closed_campaigns` filters `stat_bucket` to ensure ALGO is excluded (`docs/AI_AGENT_CONTEXT.md:36-40`). This is the AGENTS.md Red Line #8 enforced in code.

### 1.6 Win Rate ≥ 50%, average win ≥ 1.5× average loss, profit factor ≥ 2

- Required by Mark: a "tradeable edge" = WR ≥ 50% AND payoff ≥ 1.5 AND PF ≥ 2.
- Implemented:
  - `analytics_engine.compute_period_analytics()` at `analytics_engine.py:14-58` computes WR, expectancy, PF over closed campaigns in the period.
  - Coaching layer surfaces shortfall: `engine_core.generate_minervini_coaching()` at `engine_core.py:793` warns when `expectancy < 0`, `payoff < 1.5`, `wr < 40%`.
  - Heat score penalises violations: `adaptive_risk_engine._window_heat_score` at `adaptive_risk_engine.py:296` — `pf < 1.0` → score-15; `0 < payoff < 0.8` → score-15.
- **Critical alignment point:** `engine_core.is_stat_countable()` at `engine_core.py:1261` excludes `ALGO_OBSERVED` and `DATA_INCOMPLETE` from these stats. This is the literal AGENTS.md Red Line #8: *"Win Rate and Expectancy must never include DATA_INCOMPLETE or ALGO_OBSERVED campaigns."* Defended.

### 1.7 Cut losses immediately, run winners

- Required by Mark: BROKEN state must fire fast; RUNNER state must not be downgraded prematurely.
- Implemented in `engine_core.compute_position_state()` at `engine_core.py:1963`:
  - BROKEN priority is third — only ALGO_OBSERVED and DATA_INCOMPLETE precede it (`engine_core.py:2017-2022`). Stop-violation OR violation_score ≥ 6 → BROKEN.
  - RUNNER at `engine_core.py:2024-2035`: open_r ≥ 5R OR (realized ≥ original_risk AND open_qty > 0 AND follow_through ≥ minimum). The follow_through gate **was** a `None` neutral pass (audit §5.3) but is now **correctly computed** — `risk_monitor.py:741` calls `ec.compute_follow_through(...)` and passes a real value into `compute_position_state`. **The audit is stale on this point** (see Section 2b — Research challenge).
- ATR trail buffer (Sprint 8 #26): `engine_core.py:1890` defines `_TRAIL_LOOSE_R_THRESHOLD = 5.0` — at open_r ≥ 5R trail under MA50 (loose), letting the runner run. Defended.

### 1.8 Cash is a position (de-risk in cold regime)

- Required by Mark: in correction/downtrend, exposure should fall toward 0-25% and risk-per-trade should step down.
- Implemented:
  - `engine_core.generate_minervini_coaching()` at `engine_core.py:803-804` fires explicit coaching: *"שוק בירידה — מינרביני: 'הגן על ההון שלך. הקטן חשיפה ל-0-25%'"*.
  - Cold regime maps to `direction = "down_fast"` in adaptive_risk_engine (`heat_score < 40 OR loss_streak ≥ 3` → step down two ladder rungs — `adaptive_risk_engine.py:485`).
  - Drawdown auto-cut overrides any heat-based "up" recommendation when 30d PnL ≤ -8% NAV (`adaptive_risk_engine.py:549-558`).
- Gap: no explicit "cash exposure target" metric is computed — exposure% is shown but not graded against a regime-conditioned target band. Sprint 10+ enhancement.

### 1.9 48h settle period after a risk change — psychological cooldown

- Required by Mark: after confirming a risk change, no further risk recommendations for 48h — prevents whipsaw and forces psychological commitment.
- Implemented: `RISK_SETTLE_HOURS = 48.0` (`adaptive_risk_engine.py:33`); `get_risk_settle_info()` at `adaptive_risk_engine.py:73` reads `risk_changed_ts` from `sentinel_config.json` and reports `active=True` for 48h after a confirm.
- Risk monitor gate: alerts only fire when *not* in settle period AND direction has changed (`docs/SYSTEM_AUDIT_2026_05.md:346-348`).
- Gap: the 48h figure is unvalidated empirically — `docs/SPRINT_9_PLAN.md:151` lists "48h Settle Period empirical validation" as Sprint 10+ out-of-scope. Acceptable.

---

## Section 2 — Team-by-team alignment check

### 2a. Sprint 9 priorities (5)

**Priority 1 — Morning Briefing view (`docs/SPRINT_9_PLAN.md:20-37`)**
- Methodology alignment: **partial.** The proposed top-3 sections (regime → urgent positions → adaptive risk + drawdown) cover the *risk* side well. They do **not** surface methodology signals: TT score, RS rank, volume-contraction status, distribution-day count, breakouts within 3% of pivot.
- My ask to Maya/Lior: add a 2-line "Methodology pulse" section above today's adaptive risk — e.g., `"TT avg open: 7.2/10 | RS leaders: 2 | bases within pivot: 1"`. Without it, the briefing is a risk dashboard, not a *trading* dashboard. This is a NICE-TO-HAVE for Sprint 9, MUST-HAVE for Sprint 10.

**Priority 2 — engine_core coverage 56% → 75%**
- Methodology alignment: **neutral but enabling.** Tests are tests. However, coverage targets should specifically include `compute_trend_template_full`, `compute_follow_through`, `compute_position_state` (the methodology-critical paths). Chris should not bring coverage up by testing trivial helpers and leaving these untested.
- My ask to Chris: in the "top 5 uncovered functions" pass at the start of Sprint 9, prioritise the four functions listed above. Coverage gained on `compute_trend_template_full` is worth 5x the coverage gained on a string formatter.

**Priority 3 — audit_logger 8/8 + drawdown P0 alert wiring**
- Methodology alignment: **fully aligned.** Drawdown auto-cut is the Champion ch.13 "stop the bleeding" rule. Mark already approved the override in Sprint 8 (`adaptive_risk_engine.py:25-26`). Wiring the P0 alert in risk_monitor closes the loop: code knows → code alerts → user confirms → adherence logged.
- Threshold check: `DRAWDOWN_TRIGGER_PCT = -8.0` and `DRAWDOWN_CUT_TO_PCT = 0.40` (`adaptive_risk_engine.py:27-28`). Mark's verdict: numbers are correct; -8% / 30d is the Champion threshold; 0.40% floor is below Jordan's 0.50% target and is the right *forced* floor. **Defended.**
- Caveat: `risk_monitor.py` must consume `result.get("override") == "drawdown_auto_cut"` AND bypass the 24h adaptive cooldown AND the 48h settle period (Jordan, confirm before merge). Settle period defers risk *changes*; a drawdown auto-cut is not a discretionary change, it's a hard rule — settle must not gate it. Add a test.

**Priority 4 — Heat score multiplicative refactor (proposal at `docs/SPRINT_9_PLAN.md:95-103`)**
- Methodology alignment: **strongly approved, with one fix.**
- Current additive bug (`docs/SPRINT_9_PLAN.md:90-92`): WR=70%, payoff=0.5, PF=0.8 → score ≈ 58 → trader looks "OK". This is exactly the "you're losing money but feel like you're winning" pattern Minervini warns about in *Stock Market Wizards* — average loss > average win is a losing system regardless of WR.
- Proposed multiplicative form correctly collapses to ~9 in that case, firing `down_fast`. ✅
- **Fix I require before merge:** the `payoff_factor = clamp(payoff / 2.0, 0.3, 2.0)` formula is "centered at payoff=2.0". Minervini's red line is payoff < 1.0 (average loss bigger than average win). The clamp floor `0.3` means even payoff=0.1 only multiplies by 0.3 — too forgiving. Use `clamp(payoff / 2.0, 0.15, 2.0)` so a catastrophic 0.1 payoff multiplies by 0.15, not 0.30. This makes a 70% / 0.1-payoff / 0.5-PF system score ~4 — emphatically `down_fast`. Daria can validate.
- Acceptance criterion `correlates with old score in normal range (r > 0.7)`: agreed for "normal" range. **In the catastrophic regime, low correlation is the point** — the refactor must diverge from the old score there.

**Priority 5 — BACKING_OFF state**
- Methodology alignment: **fully aligned with Mark's mental model.** The trigger definition — was ≥ +1R within last N days, now ≤ -0.3R, broke MA10 — is Minervini's "the trade was working and stopped working" pattern, the *exact* gap between WORKING (still working) and BROKEN (already through stop).
- The priority order proposed (BROKEN > BACKING_OFF > RUNNER > WORKING) is **wrong**. A position that hit RUNNER (≥ 5R) and is giving back is not "backing off" — it's a Giveback-Monitor case, not a BACKING_OFF case. Correct order: `BROKEN > BACKING_OFF > PROFIT_PROTECTION > RUNNER > WORKING`. If a position once hit 5R, drops to 4R, and breaks MA10, the answer is **Giveback Monitor zone watch, not BACKING_OFF**. BACKING_OFF is for the 1-2R range that never advanced to PROFIT_PROTECTION.
- My ask to David: tighten the rule — `was_peak_r in [1.0, 2.0) within last 7 days AND current open_r ≤ -0.3R AND broke MA10`. Excludes positions that ever hit 2R+ (those belong to Giveback Monitor).

### 2b. Research team

Research team's report at `docs/teams/RESEARCH_FINDINGS_DAY1.md` does not exist on disk as of writing. Predicting their angle: they will challenge `docs/SYSTEM_AUDIT_2026_05.md` claims and surface what is now **stale** in that audit.

**My view on the methodology-critical items they should prioritise:**

1. **Silent failure on `live_price = None`** (audit §5.1, file `risk_monitor.py:578`). The current code (`risk_monitor.py:594-602`) **now alerts** before falling back to entry_price. This is good — but Mark's stricter view: in the live-price-None case the position's `open_r` is now computed against the *entry* price, which means open_r = 0 every cycle. **Methodology cost: a position bleeding -3R will silently appear flat in the digest.** Research should escalate this — the position must be flagged with `live_price_unavailable=True` and excluded from `is_stat_countable` for the duration, not displayed as flat.

2. **`engine_res ok=False` silent skip** (audit §5.1, `risk_monitor.py:604`). Current code (`risk_monitor.py:633-640`) **now alerts** with the engine error and `continue`. Audit is stale. ✅

3. **`follow_through_score = None` always** (audit §5.3). This is the audit's biggest stale claim. Code at `risk_monitor.py:741` **now correctly computes follow_through** via `ec.compute_follow_through()` and passes it to `compute_position_state`. The Sprint-8 fix exists; the audit text predates it.
   - Research must confirm/deny. If they push back on this claim and confirm it's fixed: **good, audit doc needs update**. If they find a code path where it's still None: that's a critical Sprint-10 fix.

4. **`initial_stop = 0` masks position** (audit §5.1, `risk_monitor.py:589`). Current code at `risk_monitor.py:610-618` **now alerts** via `get_campaign_risk_metrics(..._risk_metrics["valid"])`. ✅

**Push-back I want Research to make:** the audit doc is now ~1 sprint stale on three of the five silent-failure claims. Research's job today is to confirm which are still real and which are doc rot, then update SYSTEM_AUDIT_2026_05.md or supersede it. **Doc rot is methodology-critical** because new agents (Hyperscaler, Marketing) will read these claims and replicate them in their team docs. False precedents compound.

**The one Research priority I do NOT want diluted:** the 3-way inconsistency of `original_campaign_risk` definition (audit §4.1). Three modules, three slightly different formulas. This **still produces R values that differ between dashboard, monitor, and reports**. That is the literal AGENTS.md Prime Directive #2 violation — "NAV, risk, R-multiple, exposure, and PnL math must remain explainable." If R changes depending on which screen you look at, the math is not explainable. The recent `get_campaign_risk_metrics()` consolidation in `engine_core` is the right direction; all three readers must be migrated to that single function.

### 2c. Hyperscaler team — methodology profiles

Hyperscaler design at `docs/teams/HYPERSCALER_DESIGN_V0.md` does not exist on disk yet. Predicting their core proposal: per-user "methodology profile" selector (Minervini-strict / Minervini-relaxed / O'Neill / generic).

**Mark's verdict — conditional approval with hard constraints:**

- **Methodology profiles can exist as long as none of them silently mix ALGO into WR / Expectancy / PF.** This is AGENTS.md Red Line #8 (`AGENTS.md:16` and `AGENTS.md:72`). It must remain a **HARD-CODED CONSTANT** in the codebase, NOT a profile flag, NOT a user toggle.
  - Concrete: `engine_core.is_stat_countable()` at `engine_core.py:1261` must keep its current signature — `bool` returning False for `STAT_BUCKET_ALGO` and `STAT_BUCKET_DATA_INCOMPLETE` always. No profile parameter, ever.
  - If Hyperscaler proposes `is_stat_countable(bucket, profile)` with profile "relaxed" returning True for ALGO_OBSERVED → **rejected on sight**. This is the methodology dilution attack vector.

- **Minervini-strict must be the default profile** for any new user. Not a switch. Not a setup wizard step. The first thing a new tenant gets is Minervini-strict; opting out requires an explicit configuration change with a logged audit entry.

- **Acceptable profile parameters (safe to vary per tenant):**
  - TT criteria threshold (8/8 strict vs 7/8 relaxed) — but only the *score threshold* used for UI labels, never for `is_stat_countable`.
  - RISK_LADDER caps (top of ladder 1.50% vs 2.00% — but ladder floor 0.25% is non-negotiable).
  - Drawdown trigger -8% (default) vs -6% (more conservative). May tighten, may not loosen.
  - Follow-through window 10d (default) vs 15d.
  - 48h settle period vs 72h.

- **Non-negotiable across all profiles:**
  - ALGO never enters discretionary WR/Expectancy/PF.
  - DATA_INCOMPLETE never enters any stats.
  - 7-8% per-trade stop guideline (when implemented — see Section 4).
  - Drawdown auto-cut override exists (threshold tunable per profile).
  - Telegram admin protection (`telegram_bot_secure_runner.py`) cannot be disabled by any profile.

- **Migration smoke test required:** Hyperscaler's first PR must include `tests/test_methodology_profile_default.py` that:
  - asserts a new user gets `profile = "minervini_strict"`.
  - asserts `compute_period_analytics()` on a fixture with mixed ALGO + EP campaigns returns identical WR/Expectancy/PF as the pre-Hyperscaler `main` branch.
  - **Same fixture, same numbers, byte-for-byte.** If those numbers move, methodology has been silently diluted.

### 2d. Marketing team

Marketing plan at `docs/teams/MARKETING_PLAN_V0.md` does not exist on disk. Predicting their angle: positioning, public claims, name-dropping options.

**Mark's verdict:**

1. **Name-dropping Minervini in public:**
   - Avoid. The system implements Minervini-derived methodology (Trend Template, VCP, SEPA-aligned risk ladders, 48h settle, drawdown auto-cut). It is **not licensed by Minervini Private Access**, has no endorsement, and Mark Minervini has not reviewed the codebase.
   - Acceptable public framing: *"implements published Minervini methodology"* with a footnote citing *Trade Like a Stock Market Wizard* and *Trade Like a Champion*. Books are public; the methodology is public; citing them is fair use.
   - Unacceptable: *"endorsed by Mark Minervini"*, *"the Minervini system"*, any logo, any trademark. Trademark violation + ethics issue. **Legal directive: any marketing copy must be reviewed for this before publication.**

2. **Anti-positioning (compliance critical):**
   - **NOT a buy-and-hold tool.** Sentinel is a momentum / breakout discipline tool. Buy-and-hold marketing would mislead users into Stage-4 disasters.
   - **NOT a social trading / copy trading tool.** Sentinel does not publish trades, does not allow following another trader's portfolio, does not aggregate community signals. Marketing must never imply this.
   - **NOT giving investment advice.** Sentinel is a *personal trading intelligence* system (`docs/AI_AGENT_CONTEXT.md:5-7`). Every Telegram message that resembles advice is gated by methodology rules and labelled. The phrase "investment advice" must never appear in marketing.
   - **NOT an "AI trading system".** This is the lie I will not allow.
     - Sentinel is rule-based + statistics. Trend Template is deterministic. Heat score is a weighted formula. The "AI" in `docs/AI_AGENT_CONTEXT.md` refers to *AI agents that maintain the codebase*, not AI that generates signals.
     - Marketing claim that survives audit: *"rule-based decision support, statistics-driven risk sizing"*. Honest, accurate, defensible.
     - Marketing claim that does NOT survive: *"AI-powered trading", "machine learning signals", "AI risk model"*. Honesty over hype. If we are still using a rule engine, we say rule engine.

3. **Public metrics:** see Section 3 conflict #2 — private real data vs synthetic backtest.

---

## Section 3 — Predicted cross-team conflicts (5-8)

### Conflict 1 — `follow_through_score` minimum: per-profile threshold or hard-coded?
**Teams:** Research vs Hyperscaler
- Research wants to confirm/raise the `follow_through_score` minimum for RUNNER (currently neutral `None`-pass; computed minimum at `_RUNNER_FOLLOW_THROUGH_MIN` per `engine_core.py:2030`).
- Hyperscaler wants every threshold per-user-configurable.
- **My resolution:** the FT minimum is a *display* threshold (which positions get labelled RUNNER on screen). It may be per-profile. The FT score *value* itself is computed by a single formula (`engine_core.compute_follow_through` at `engine_core.py:1772`). Profile = display threshold only. The 50-pts peak-gain / 25-pts new-high / 25-pts vol-ratio weights are methodology constants — Minervini's "wizards continue" pattern. **Non-tunable.**

### Conflict 2 — Public metrics: synthetic backtest vs anonymised real
**Teams:** Marketing vs Founder (privacy) vs Research (truthfulness)
- Marketing wants public-facing performance numbers: WR, PF, expectancy.
- Founder's real track record is private.
- Research will (correctly) push back on synthetic backtest data being labelled as "Sentinel performance".
- **My resolution:** publish *only* the methodology rules and their backtest performance on a public stock universe (e.g., S&P 1500, 2020-2025) with explicit disclosure: *"Backtest of the methodology on a public universe, not user-account performance. Past performance does not predict future results."* Do not publish anonymised real founder data — even anonymised it leaks position concentrations. Backtested-methodology-on-public-universe is the only honest option.

### Conflict 3 — Multi-user vs `telegram_bot_secure_runner.py` admin gate
**Teams:** Hyperscaler vs Security (Eyal) vs Mark
- Hyperscaler wants to relax `ADMIN_CHAT_ID` single-admin to multi-user tenancy.
- `telegram_bot_secure_runner.py:43` enforces `chat_id != str(ADMIN_ID)` → `unauthorized`. The wrapper is intentional (`CLAUDE.md:20`, *"Do not bypass `telegram_bot_secure_runner.py` in production"*).
- **My resolution:** move from a single `TELEGRAM_ADMIN_ID` env var to a `TELEGRAM_ADMIN_IDS` (comma-separated list of int IDs) **inside the same secure runner**. Same guard, same rate limiter, same truth-suffix injector. Each ID gets its own rate-limit window. Tenant data isolation goes *into* Supabase RLS (Eyal owns this). The secure runner stays — multi-admin is a config change, NOT a runner rewrite.

### Conflict 4 — Morning Briefing: risk-focused vs methodology-focused
**Teams:** Telegram UX (Maya, Lior) vs Mark
- Maya/Lior want a clean risk dashboard layout (regime → urgent → adaptive).
- Mark wants a methodology pulse line (TT scores, RS leaders, bases near pivot).
- **My resolution:** Sprint 9 ships the risk-focused layout as planned (Maya's wireframe was already approved Meeting 2). Sprint 10 adds the "Methodology pulse" line as the new top section. Avoid feature creep mid-sprint.

### Conflict 5 — "AI" in marketing copy
**Teams:** Marketing vs Mark vs Compliance
- Marketing will want "AI-powered" for SEO and consumer recognition.
- Mark refuses (Section 2d.3 above) on honesty grounds.
- Compliance will refuse on regulatory grounds (SEC/FINRA scrutiny of AI trading claims since 2024).
- **My resolution:** consensus is automatic — both honesty and compliance reject "AI-powered". Marketing must use *"rule-based decision support"* or similar. No exception.

### Conflict 6 — Methodology profile defaults: opt-in vs opt-out
**Teams:** Hyperscaler vs Marketing vs Mark
- Hyperscaler will want "let the user pick their profile on signup" (drives engagement).
- Marketing will agree (more product-style).
- Mark requires: **Minervini-strict is the only default.** No selector at signup. Profile-switching is buried in advanced settings.
- **My resolution:** signup → strict. Advanced settings → "Try the relaxed profile (you will be warned about reduced quality gates)". The warning is non-dismissable; an audit-log entry is written on every profile switch.

### Conflict 7 — Drawdown auto-cut bypasses 48h settle: methodology rule vs UX
**Teams:** Risk Mgmt (Jordan) vs Telegram UX (Maya) vs Mark
- Jordan: drawdown auto-cut must fire immediately, even within 48h settle period.
- Maya: 48h settle exists to prevent whipsaw alerts — if it's bypassed, why have it?
- **My resolution:** 48h settle gates **discretionary** recommendations (`up` / `down_fast`). Drawdown auto-cut is a **hard rule**, not a recommendation. They live on different alert paths. Risk monitor must encode this: `if drawdown_override: fire_p0_unconditionally`. Add a test (`tests/test_risk_monitor_drawdown.py::test_drawdown_p0_bypasses_settle_period`).

### Conflict 8 — Audit doc rot: who owns stale audit claims
**Teams:** Research vs Documentation Owner (nobody) vs Mark
- Research will surface ≥ 3 stale claims in SYSTEM_AUDIT_2026_05.md (the follow_through, engine_res, initial_stop silent-failure claims are stale because the fixes shipped Sprint 7-8).
- No team owns the audit doc.
- **My resolution:** Research team OWNS the audit doc going forward. SYSTEM_AUDIT_2026_05.md becomes a living document, refreshed at the end of every sprint as part of sprint-lessons. Stale claims are an incident, not a doc-rot footnote.

---

## Section 4 — Mark's directives for Sprint 10

1. **Methodology profile schema must hard-code `mix_algo_into_wr: false` as a Python constant, not a config flag.** The bucket exclusion in `engine_core.is_stat_countable()` (`engine_core.py:1261`) stays a pure function with no profile parameter. Hyperscaler's PR for profiles must pass a test that proves a "relaxed" profile cannot make `is_stat_countable("ALGO_OBSERVED")` return True.

2. **All Hyperscaler migrations must include a "single-user identity" smoke test.** Test fixture: original-single-user prod database. Run analytics. Assert WR, Expectancy, PF, total_r, profit_factor are byte-for-byte identical to pre-Hyperscaler `main`. If any number moves, the migration is rejected.

3. **Per-trade 7-8% stop-loss soft warning.** Add `engine_core.validate_initial_stop_pct(entry, initial_stop, max_pct=0.08)` returning `{"ok": True}` or `{"ok": False, "actual_pct": float, "warning": str}`. Wire it into the journal flow (`telegram_backlog.py`) to soft-warn when the user enters a stop > 8% below entry. **Soft warning only — user can override** (this is opinionated guidance, not an iron gate; some strategies legitimately use wider stops on lower-volatility names).

4. **Audit doc ownership.** Research team becomes the owner of `docs/SYSTEM_AUDIT_2026_05.md` (or its successor). Audit doc is refreshed end-of-sprint, every sprint, by Research. Stale-claim incidents are tracked.

5. **Single source of truth for `original_campaign_risk`.** Migrate all three readers (`risk_monitor`, `analytics_engine`, `adaptive_risk_engine`) to the new `engine_core.get_campaign_risk_metrics()` consolidation. Remove the duplicate implementations in `adaptive_risk_engine.py:147` and `analytics_engine.py:250` (referenced in audit §4.1). One function, one R per campaign, everywhere.

6. **Marketing copy review gate.** Any public marketing copy (web, social, email) must pass a "claim audit": grep for `AI`, `endorsed`, `Minervini`, `investment advice`, `buy and hold`, `social trading`, `copy trading`. Each hit gets approved/edited/rejected by Mark before publication. Implement as a pre-commit hook on the marketing repo (or a checklist if no separate repo).

7. **Drawdown override is not gated by settle period.** Risk monitor must call `drawdown_auto_cut_recommendation` before checking `get_risk_settle_info().active`. P0 alert fires immediately. Test required: `test_drawdown_p0_bypasses_settle_period`.

8. **Heat score multiplicative refactor (Sprint 9 priority 4) must use `payoff_factor` clamp floor `0.15`, not `0.30`.** A 0.1 payoff multiplies by 0.15 → catastrophic-regime correctly triggers `down_fast`. Daria validates on 5+ historical examples.

---

## Appendix — methodology references (file / doc:line)

### Codified methodology
- Trend Template (8 criteria): `engine_core.py:719-790` (`compute_trend_template_full`)
- Trend Template (legacy 5, Telegram): `engine_core.get_minervini_analysis()` per `docs/DECISIONS.md` DEC-20260509-002
- VCP labelling: `engine_core.py:1235` (`_MANUAL_SETUP_PREFIXES`), `engine_core.py:1238` (`classify_stat_bucket`)
- Trade lifecycle stages (NOT Weinstein 1-4): `engine_core.py:185` (`classify_trade_stage`)
- Follow-through score: `engine_core.py:1762-1820` (`compute_follow_through`, with Minervini wizard threshold 7%)
- Position state machine (10 states): `engine_core.py:1963-2070+` (`compute_position_state`)
- ATR trail buffer (loose at 5R): `engine_core.py:1890` (`_TRAIL_LOOSE_R_THRESHOLD = 5.0`)

### Risk math
- Original campaign risk: `engine_core.compute_original_campaign_risk` (Phase 4 per audit §2.3)
- R-multiple computation: `engine_core.compute_r_true`
- Capital at risk USD: `engine_core.compute_capital_at_risk_usd`
- Risk deviation classifier: `engine_core.compute_risk_deviation` (≤1R / 1-1.5 / 1.5-2 / 2-3 / >3 system event)
- Giveback from peak: `engine_core.compute_giveback_from_peak` (20% / 35% / 50% thresholds)

### Adaptive risk + drawdown
- Risk ladder (tightened): `adaptive_risk_engine.py:20` `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`
- Drawdown trigger: `adaptive_risk_engine.py:27-29` (-8% NAV / 30d → 0.40% floor)
- Heat score (current additive): `adaptive_risk_engine.py:296-331` (`_window_heat_score`)
- 48h settle period: `adaptive_risk_engine.py:33`, `adaptive_risk_engine.py:73-95` (`get_risk_settle_info`)
- S9/M21/L50 windows + weights: `adaptive_risk_engine.py:446-450` (50% / 30% / 20%)

### Stat bucket separation (Red Line #8)
- AGENTS.md invariant: `AGENTS.md:16` (Prime Directive 8), `AGENTS.md:72` (Red Line: do not mix ALGO into WR/Expectancy)
- Bucket classification: `engine_core.py:1238` (`classify_stat_bucket`)
- Countability gate: `engine_core.py:1261` (`is_stat_countable`)
- Discretionary filter: `engine_core.py:1266` (`is_discretionary_bucket`)
- Doc reference: `docs/AI_AGENT_CONTEXT.md:26-40` (stat scope separation)

### Telegram protections
- Secure runner wrapper: `telegram_bot_secure_runner.py:40-60` (`guard_decision`)
- Admin gate: `telegram_bot_secure_runner.py:30,43`
- Rate limit + cooldown: 8 msgs / 60s, 90s cooldown — `telegram_bot_secure_runner.py:32-34`
- Truth suffix injection: `telegram_bot_secure_runner.py:69-77`

### Methodology guardrails in docs
- Prime Directives: `AGENTS.md:5-16`
- Red Lines: `AGENTS.md:61-73`
- CLAUDE.md hard constraints: `CLAUDE.md:21-30`
- Stat scope separation: `docs/AI_AGENT_CONTEXT.md:26-40`
- Alert tiers: `docs/AI_AGENT_CONTEXT.md:42-68`
- ALGO Observer Mode (no exit/stop instructions): `docs/DECISIONS.md` DEC-20260511-001
- Risk basis classification: `docs/USER_REQUIREMENTS.md` REQ-20260511-003
- Strategy Contamination Guard: `docs/USER_REQUIREMENTS.md` REQ-20260511-004

### Sprint 9 references cited in this review
- Sprint 9 plan: `docs/SPRINT_9_PLAN.md`
- Morning briefing spec: `docs/SPRINT_9_PLAN.md:20-37`
- Heat score multiplicative proposal: `docs/SPRINT_9_PLAN.md:95-103`
- BACKING_OFF state definition: `docs/SPRINT_9_PLAN.md:114-130`
- Drawdown P0 wiring: `docs/SPRINT_9_PLAN.md:56-78`
- Coverage 75% target: `docs/SPRINT_9_PLAN.md:39-55`

### Audit doc stale claims (cross-reference for Research team)
- `docs/SYSTEM_AUDIT_2026_05.md:155` claims `follow_through_score` is always `None` → STALE, fixed at `risk_monitor.py:741`.
- `docs/SYSTEM_AUDIT_2026_05.md:524-526` "live price = None silent" → STALE, alert added at `risk_monitor.py:594-602`.
- `docs/SYSTEM_AUDIT_2026_05.md:526` "engine_res ok=False silent skip" → STALE, alert added at `risk_monitor.py:633-640`.
- `docs/SYSTEM_AUDIT_2026_05.md:526` "initial_stop=0 silent" → STALE, alert added at `risk_monitor.py:610-618`.
- `docs/SYSTEM_AUDIT_2026_05.md:206,714` lists OLD risk ladder `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` → STALE, code now `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]` (`adaptive_risk_engine.py:20`).
- `docs/SYSTEM_AUDIT_2026_05.md:483-491` `original_campaign_risk` 3-way inconsistency → **STILL VALID** until directive #5 lands.
