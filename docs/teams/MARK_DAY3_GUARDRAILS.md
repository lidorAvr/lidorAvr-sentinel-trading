# Mark — Day-3 Methodology Guardrails

**Author:** Mark (Methodology Owner — Minervini SEPA canon)
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Scope:** Verification guardrails the parent session MUST run during the Day-3
consolidation "team meeting" before committing Phase A (Hyperscaler `user_context`),
the UX stop-promotion / backlog overhaul, and Marketing V1.

This document is **pass/fail oriented**. Each check is binary. If any **BLOCKER**
check fails, the parent does NOT commit — full stop. This supersedes nothing in
`AGENTS.md` / `CLAUDE.md`; it operationalizes them for Day-3.

Mandatory inputs read for this doc: `AGENTS.md` (invariants #1-#8, Red Lines),
`CLAUDE.md`, `docs/DECISIONS.md` (DEC-20260515-001..005, DEC-20260511-001,
DEC-20260512-003/004), `docs/teams/MARK_ALIGNMENT_REVIEW.md` (§4 directives 1-8),
`docs/teams/DAY1_MIDDAY_STANDUP.md`, `docs/teams/HYPERSCALER_PHASE_A_SPEC.md`,
`docs/teams/USER_CONTEXT_INTERFACE_SPEC.md`, `docs/SYSTEM_AUDIT_2026_05.md` §5.6.

---

## 0. Severity legend

| Tag | Meaning |
|---|---|
| **BLOCKER** | Failing this means do NOT commit. Methodology / Red Line breach. |
| **HARD** | Must pass; a documented, time-boxed exception requires Mark sign-off. |
| **SOFT** | Should pass; a failure is logged as a follow-up, not a commit blocker. |

All file:line references are absolute under `/home/user/lidorAvr-sentinel-trading`.
AGENTS.md invariant numbers refer to `AGENTS.md:9-16` (Prime Directive 1-8),
Red Lines at `AGENTS.md:61-73`.

---

## 1. Phase A / `user_context` guardrails (verify checklist)

Run against the Hyperscaler implementation of `HYPERSCALER_PHASE_A_SPEC.md` +
`USER_CONTEXT_INTERFACE_SPEC.md`.

### 1.1 Red Lines are module constants, NOT profile fields — **BLOCKER**

- [ ] **A1.** `grep -n "mix_algo_into_wr" user_context.py` shows it ONLY inside
  `MODULE_LEVEL_INVARIANTS` (USER_CONTEXT_INTERFACE_SPEC §5, lines 344-354). It is
  NOT a field of `UserProfile` (§3 dataclass). FAIL if it appears as a dataclass
  field or a `_BUILTIN_DEFAULTS` key. (AGENTS.md invariant #8; Mark directive #1.)
- [ ] **A2.** The four non-overridable invariants are all present in
  `MODULE_LEVEL_INVARIANTS` with the exact values:
  `mix_algo_into_wr=False`, `admin_only_telegram=True`,
  `data_incomplete_in_stats=False`, `secure_runner_required=True`,
  `fallback_data_as_truth=False` (invariants #1, #3, #8; CLAUDE.md:21-24).
- [ ] **A3.** `get_user_constant(name, user_id)` returns the invariant value
  **before** any profile resolution and **ignores `user_id`** for invariant keys
  (USER_CONTEXT_INTERFACE_SPEC §4 resolution order step 1, §5 caller pattern).
  Test `test_invariants_cannot_be_overridden_by_profile` (spec §8 test 4) must
  exist and pass: a `UserProfile(constants={"mix_algo_into_wr": True})` STILL
  yields `False`. FAIL if absent.
- [ ] **A4.** `engine_core.is_stat_countable()` signature is **unchanged** —
  still `is_stat_countable(bucket)` with NO `profile` / `user_id` parameter
  (`engine_core.py:1261`; Mark directive #1; Phase A spec §1 hard invariant,
  §4.9 "engine_core untouched", §10 acceptance). FAIL on sight if a
  `profile`/`user_id` arg was added — this is the dilution attack vector
  (`MARK_ALIGNMENT_REVIEW.md` §2c).
- [ ] **A5.** Belt-and-suspenders: a test asserts
  `get_user_constant("mix_algo_into_wr") == False` AND that this equals the
  effective behaviour of `is_stat_countable("ALGO_OBSERVED") is False` and
  `is_stat_countable("DATA_INCOMPLETE") is False` (spec §10 open-Q6, two
  checks one truth).

### 1.2 Single methodology profile only (DEC-20260515-002) — **BLOCKER**

- [ ] **A6.** `MethodologyProfile` enum has exactly ONE active member:
  `MINERVINI_STRICT = "minervini_strict"`. Any of `minervini_relaxed`,
  `oneill_classic`, `swing_low_risk` must be commented-out / inert, NOT
  selectable in V1 (USER_CONTEXT_INTERFACE_SPEC §3; DEC-20260515-002:707-720).
- [ ] **A7.** No code path lets a user *set* `methodology_profile` in V1
  (field is system-set per DEC-002). No onboarding step offers a profile
  selector (Day-1 conflict #6 ruling: signup → strict, no selector).
  FAIL if a `/settings` or onboarding handler writes `methodology_profile`.
- [ ] **A8.** A full *custom* profile is permanently rejected — there is no
  generic free-form methodology override surface (DEC-20260515-002:716).
  `profile.constants` is permitted ONLY for keys in `_BUILTIN_DEFAULTS` and
  may NEVER collide with `MODULE_LEVEL_INVARIANTS` (spec §3 field table,
  §4 resolution step 4-6).

### 1.3 Zero behaviour change for the existing user — **BLOCKER**

- [ ] **A9.** The single-user smoke test exists and is wired into CI for
  **every** Phase A PR (Mark directive #2; Phase A spec §6, §8, §10).
  Concretely: `scripts/phase_a_smoke_compare.py` and/or
  `tests/test_byte_identical_founder.py` (USER_CONTEXT spec §8 integration test).
- [ ] **A10.** Smoke test asserts **byte-identical** for the sentinel user
  (`00000000-0000-0000-0000-000000000001`):
  WR, Expectancy, PF, total_r, profit_factor (days=30/90/365), heat_score,
  adaptive recommendation direction + recommended_risk_pct, NAV /
  target_risk_usd / freshness_label, one dry risk_monitor cycle's alert
  count + alert text (timestamps stripped), `/portfolio` row count + R values
  (Phase A spec §6.1, §10). FAIL if any number moves.
- [ ] **A11.** `_BUILTIN_DEFAULTS` values match HEAD code exactly. Spot-check
  the methodology-critical ones: `risk_ladder == [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`
  (`adaptive_risk_engine.py:20`); `drawdown_trigger_pct == -8.0`;
  `risk_settle_hours == 48.0`; trail thresholds `8.0`/`5.0`
  (`engine_core.py:1889-1890`). A stale default here = silent methodology drift.
  (USER_CONTEXT spec §4 `_BUILTIN_DEFAULTS`; note `SPRINT_9_PLAN.md` ladder is
  STALE, code wins — `MARK_ALIGNMENT_REVIEW.md` §1.5.)
- [ ] **A12.** `DEFAULT_USER_ID` unset must **not** crash and must fall back to
  the sentinel UUID with a one-shot stderr warning (Phase A spec §2, §4.1).
  Mark's prod `.env` does not have it yet; a missed deploy var must still run
  byte-identically. FAIL if `bot_core` raises `SystemExit` on missing
  `DEFAULT_USER_ID`.

### 1.4 Migrations additive / reversible / no trade-data mutation — **BLOCKER**

- [ ] **A13.** Migrations `003`/`004` are `ADD COLUMN ... IF NOT EXISTS ...
  DEFAULT '00000000-0000-0000-0000-000000000001'`, additive only. No `ALTER`
  of existing columns, no `DELETE`, no `UPDATE` of any business field
  (only the `user_id` backfill `WHERE user_id IS NULL`). Quantity sign
  semantics (DEC-20260512-003) and `campaign_id` format (DEC-20260512-004)
  are untouched (Phase A spec §3).
- [ ] **A14.** Reverse DDL exists for both and is non-destructive
  (`DROP INDEX; ALTER TABLE ... DROP COLUMN`) — no business data lost on
  rollback (Phase A spec §3, §7.1).
- [ ] **A15.** `test_sentinel_matches_migration_default` exists: the Python
  `SENTINEL_USER_ID` literal == the SQL `DEFAULT` literal in `003`
  (Phase A spec §4.1, §6) — guards code/SQL drift.
- [ ] **A16.** `migrations/verify_migrations.py` `MIGRATIONS` list extended
  with `003`/`004` and `verify_migrations.py` exits 0 post-migration with
  `SELECT COUNT(*) ... WHERE user_id IS NULL == 0` for both tables
  (Phase A spec §3, §10).
- [ ] **A17.** Files Mark hard-froze are untouched (Phase A spec §4.9, §10):
  `telegram_bot_secure_runner.py`, `engine_core.py` (no signature changes),
  `account_state.py`, `docker-compose.yml` (telegram-bot still runs
  `telegram_bot_secure_runner.py` — CLAUDE.md current production wiring),
  `sentinel_config.json`. `7500.0` fallback NAV NOT removed (Phase B).

> **Note on `user_context` dual spec:** Phase A spec §4.1 ships a *minimal*
> `user_context.py` (just `get_current_user_id()`); USER_CONTEXT_INTERFACE_SPEC
> ships the *full* `UserProfile`/`get_user_constant` surface. Either is
> acceptable for Day-3 PROVIDED the invariant checks A1-A5 hold for whatever
> surface is committed. If only the minimal module ships, A6-A8 are N/A
> (no profile surface yet) but `MethodologyProfile` MUST NOT appear with
> multiple active values anywhere.

---

## 2. UX stop-promotion guardrails

The redesign may change **only HOW a position is SELECTED** for a stop change.
It must NOT change the stop math, the write path, or the disclosure honesty.

### 2.1 Write path & math unchanged — **BLOCKER**

- [ ] **U1.** Every stop write still goes through
  `supabase_repository.update_stop_for_campaign(sb, campaign_id, stop_price[, user_id])`
  (`supabase_repository.py:67-68`). No new direct
  `sb.table("trades").update({"stop_loss": ...})` introduced anywhere. Current
  callers: `telegram_bot.py:423` (`tighten_stop`), `telegram_bot.py:449`
  (`input_new_sl`). FAIL if the redesign adds a bypass write.
- [ ] **U2.** No change to R / risk math. `compute_original_campaign_risk`,
  `compute_r_true`, `get_campaign_risk_metrics` untouched (AGENTS.md invariant
  #2; CLAUDE.md "Do not change R, NAV, exposure, or campaign math without
  tests"). The redesign is selection UX, not engine.

### 2.2 Stops only ratchet UP for longs — **BLOCKER**

This is the central Minervini rule and the **current code GAP**: the existing
flow (`telegram_bot.py:417-454`, actions `tighten_stop` / `input_new_sl`)
accepts ANY `float(text)` and writes it via `update_stop_for_campaign` with
**no comparison to the existing stop**. The redesign MUST close this gap, not
inherit it.

- [ ] **U3.** No path lets a user set a stop that **loosens** an existing stop
  (for a long: `new_stop < current_stop`) without an **explicit, separate
  confirmation step** that names the loosening in plain Hebrew (e.g.
  "אזהרה: סטופ חדש *נמוך* מהקיים — זה מנוגד למתודולוגיה. לאשר?"). A silent
  accept = FAIL. (Minervini "stops ratchet up, never down" — `MARK_ALIGNMENT_REVIEW.md`
  §1.4/§1.7; CLAUDE.md "Do not change ... campaign math".) The button "🔒
  הדק סטופ" / "tighten" wording must not be usable to *loosen* without the
  warning — the label implies tighten-only.
- [ ] **U4.** The confirmation, if the user proceeds, writes an `audit_log`
  entry recording before/after stop and that a loosen was explicitly
  confirmed (AGENTS.md invariant #4 — Supabase trade records mutated only
  when the user action explicitly requires it; mirrors DEC-20260510-008
  "explicit confirm" pattern). Default answer is NO.
- [ ] **U5.** ALGO-observed campaigns: the stop-promotion flow MUST NOT offer a
  stop-raise / management action for `management_mode == "algo_observed"`
  positions (DEC-20260511-001 — Sentinel is observer-only for ALGO; max
  actionability "Review Required"). Selecting an ALGO position for stop
  promotion = FAIL.

### 2.3 Data-completeness gating not bypassed — **HARD**

- [ ] **U6.** The new selection flow must not present a `DATA_INCOMPLETE`
  campaign (no valid `original_campaign_risk`) as if it had a clean stop, and
  must not let a stop edit "launder" a DATA_INCOMPLETE campaign into a
  countable one without the missing data actually being supplied
  (AGENTS.md invariant #8; `SYSTEM_AUDIT_2026_05.md` §5.6 — DATA_INCOMPLETE is
  what process-discipline stats measure; do not erase the signal).

### 2.4 Batch flow respects anti-spam / state dedup — **BLOCKER**

- [ ] **U7.** A batch / multi-position stop loop must NOT enable rapid-fire
  writes that bypass the per-position dedup state or anti-spam timing
  (AGENTS.md invariant #3 and #7; Red Lines "Remove anti-spam behavior",
  "Add a recurring Telegram alert that does not check a per-position dedup
  flag"). Each stop write is a discrete, individually-confirmed action; a
  batch UI may *queue* selections but each commit is one explicit confirm.
  An "apply to all" with a single tap that issues N writes = FAIL.
- [ ] **U8.** Batch flow must not generate N alert messages that bypass the
  `risk_monitor` cooldown / `STATE_ALERT_COOLDOWN` model
  (`risk_monitor.py:39-51`). Confirmation echoes are user-initiated replies
  (allowed); they must not seed recurring monitor alerts without the existing
  per-position dedup flag in `risk_monitor_state.json`.
- [ ] **U9.** Note Issue N3 (`SYSTEM_AUDIT_2026_05.md` §5.7, RESOLVED via
  `state_io.py` atomic write + `flock`): a batch stop flow that writes
  `risk_monitor_state.json` (e.g. clearing a dedup flag on stop change) MUST
  use the `state_io` atomic/locked path, not a raw `open(...,"w")`. FAIL on a
  new non-atomic writer.

### 2.5 Hebrew output stays disclosure-honest — **HARD**

- [ ] **U10.** All redesigned Hebrew messages: short, RTL-friendly, and
  explicit about fallback / cached / estimated data (AGENTS.md invariant #1
  and #6; CLAUDE.md output style; `MODULE_LEVEL_INVARIANTS.fallback_data_as_truth=False`).
  A stop-confirmation screen showing a "current stop" sourced from a fallback
  must label it as such. No fallback-as-truth.
- [ ] **U11.** Confirmation copy states the new stop value the user is about to
  write (echo-back), so a fat-finger is visible before commit. (Mirrors the
  existing `input_new_sl` echo at `telegram_bot.py:412,450`.)

---

## 3. UX backlog / journal guardrails

### 3.1 No ALGO / DATA_INCOMPLETE leak into edge stats — **BLOCKER**

- [ ] **B1.** The journal / backlog flow must NEVER let `ALGO_OBSERVED` or
  `DATA_INCOMPLETE` campaigns enter Win Rate / Expectancy / PF (AGENTS.md
  invariant #8; Red Line "Mix ALGO campaigns into Win Rate or Expectancy";
  `SYSTEM_AUDIT_2026_05.md` §5.6 — Issue F, RESOLVED, must NOT regress).
  Any new aggregation introduced by the backlog UI must route through
  `engine_core.is_stat_countable()` (`engine_core.py:1261`) exactly like
  `adaptive_risk_engine._is_disc` and `dashboard.py:374-380`. FAIL if the
  backlog computes its own WR/expectancy without the filter.
- [ ] **B2.** Regression guard exists:
  `tests/test_analytics_engine.py::TestStatBucketExclusion` (9 tests, the
  Issue-F fix) is green AND any new backlog-stats code has an analogous test
  proving WR-excluding-ALGO != WR-including-ALGO on a mixed fixture
  (`SYSTEM_AUDIT_2026_05.md` §5.6; Mark directive #2 philosophy). FAIL if the
  backlog adds stats with zero `stat_bucket`/`ALGO`/`DATA_INCOMPLETE` coverage.

### 3.2 Sorted/grouped views are display-only — **BLOCKER**

- [ ] **B3.** A "sorted by symbol / date" (or any reordered/grouped) view is
  **display-only**: it must NOT recompute, re-derive, or alter campaign stats,
  `campaign_id` (DEC-20260512-004), quantity sign (DEC-20260512-003),
  `original_campaign_risk`, or any R value. Sorting changes row order, nothing
  else. (AGENTS.md invariant #2 — R/PnL math explainable and stable; same R
  regardless of which screen — `MARK_ALIGNMENT_REVIEW.md` §2b.) FAIL if a sort
  handler writes to Supabase or recomputes a metric.
- [ ] **B4.** The backlog read path is read-only w.r.t. Supabase (AGENTS.md
  invariant #4; CLAUDE.md "Do not mutate Supabase from read-only flows").
  Browsing/sorting issues SELECTs only; the only writes are explicit journal
  edits the user deliberately submits.

---

## 4. Marketing guardrails (V1 copy)

Re-stating the hard **do-NOT-publish** list. Any V1 marketing copy is checked
by the Mark "claim audit" grep gate (Mark directive #6): grep for
`AI`, `endorsed`, `Minervini`, `investment advice`, `buy and hold`,
`social trading`, `copy trading`, plus `%`, `PnL`, `backtest`, `return`.

### 4.1 Do NOT publish — **BLOCKER**

- [ ] **M1.** **No performance numbers.** No win-rate %, no PnL, no returns,
  no synthetic backtest figures, no founder PnL (DEC-20260515-004 — process/
  demo only, no numbers; `DAY1_MIDDAY_STANDUP.md` conflict #4). Process /
  behaviour demos only ("how it cuts drawdown", "how the state machine
  reacts"). FAIL on any quantitative performance claim.
- [ ] **M2.** **No "AI" claim.** Sentinel is rule-based + statistics, not an AI
  trading system. Forbidden: "AI-powered", "machine learning signals", "AI
  risk model". Allowed: "rule-based decision support, statistics-driven risk
  sizing" (`MARK_ALIGNMENT_REVIEW.md` §2d.3; Day-1 conflict #5 — honesty AND
  compliance both reject). FAIL on any "AI"-as-signal-engine framing.
- [ ] **M3.** **No investment advice.** The phrase "investment advice" must not
  appear; Sentinel is a *personal trading intelligence* tool, not advice
  (`MARK_ALIGNMENT_REVIEW.md` §2d.2). Also NOT buy-and-hold, NOT social
  trading, NOT copy trading (6 anti-positioning statements).
- [ ] **M4.** **Minervini = acknowledgment only.** Permitted: "built on
  principles from *Trade Like a Stock Market Wizard* / *Trade Like a Champion*"
  under fair use, with footnote. Forbidden: "endorsed by Mark Minervini",
  "the Minervini system", "your Minervini co-pilot", any logo/trademark, any
  hero-line name use (DEC-20260515-001 — acknowledgment only, not branding;
  `MARK_ALIGNMENT_REVIEW.md` §2d.1). FAIL on name-as-brand/endorsement.
- [ ] **M5.** Launch framing consistent with DEC-20260515-003 (Israel-only,
  Hebrew-first — no premature global/English promises) and DEC-20260515-005
  (closed free beta, no public signup / no pricing claims). SOFT — flag, not
  block, unless it implies a paid public launch (then HARD).

---

## 5. Predicted Day-3 conflicts + Mark's ruling

| # | Conflict | Teams | Mark's ruling |
|---|---|---|---|
| **C1** | UX wants a fast "apply stop to all" batch loop; anti-spam/state dedup wants discrete confirmed writes | UX ↔ Mark/Risk | **Discrete confirm wins.** Batch UI may queue selections but each commit is one explicit user confirm (U7). No single-tap N-writes. AGENTS.md #3/#7. Non-negotiable. |
| **C2** | Hyperscaler wants config-per-user breadth; DEC-002 says single profile only | Hyperscaler ↔ Mark | **DEC-20260515-002 stands.** One `minervini_strict` profile in V1; `profile.constants` only for `_BUILTIN_DEFAULTS` keys, never invariants. Multi-profile = Sprint 13. Custom profile = permanently rejected. |
| **C3** | UX stop-promotion "make it one tap" vs the ratchet-up rule needing a loosen-confirmation | UX ↔ Mark | **Ratchet rule wins.** A loosen requires an explicit, named, default-NO confirmation + audit_log (U3/U4). One-tap is fine ONLY for tighten (new_stop ≥ current). This *closes* the current code gap at `telegram_bot.py:417-454`; the redesign must not inherit the silent-accept. |
| **C4** | Marketing wants a credibility number ("cuts drawdown by X%"); DEC-004 says no numbers | Marketing ↔ Mark | **DEC-20260515-004 stands.** Show the *mechanism* (drawdown auto-cut at -8%/30d → 0.40% floor, the 10-state machine), never a quantified outcome. "X%" is a performance number → blocked (M1). |
| **C5** | Hyperscaler/UX want `get_user_constant`-style indirection over `is_stat_countable` for "consistency"; Mark wants the pure function frozen | Hyperscaler/UX ↔ Mark | **Pure function frozen.** `is_stat_countable(bucket)` keeps its parameter-free signature (A4). The invariant is *additionally* mirrored in `MODULE_LEVEL_INVARIANTS` as belt-and-suspenders (A5), but the engine function is the truth and is not routed through profile resolution. Mark directive #1. |
| **C6** | Backlog "sorted/grouped" view tempts a recompute for "nicer rollups"; invariant #2 wants stable R everywhere | UX ↔ Mark | **Display-only wins.** Sorting/grouping changes row order only — no recompute, no write (B3/B4). Same R on every screen or the math is not explainable (AGENTS.md #2). |

---

## 6. Mark's sign-off criteria for the Day-3 consolidation

The parent commits **only if ALL of the following are true** (every BLOCKER
above passes; HARD items pass or carry a Mark-approved time-boxed exception):

1. **Phase A invariants intact:** A1-A8 all pass. `is_stat_countable()`
   signature unchanged (A4). Single `minervini_strict` profile only (A6-A8).
2. **Phase A zero-drift proven:** A9-A12 pass — the single-user smoke test
   exists, runs in CI, and is byte-identical (WR/Expectancy/PF/total_r/
   heat_score/NAV/alerts). No number moved.
3. **Phase A migrations safe:** A13-A17 pass — additive, reversible, no
   trade-data mutation, frozen files untouched, secure_runner wiring intact.
4. **Stop-promotion safe:** U1-U5, U7, U8 pass — write path unchanged, no
   silent stop-loosen, ALGO excluded, no batch anti-spam bypass, no new
   non-atomic state writer (U9). U6/U10/U11 pass or carry a Mark exception.
5. **Backlog safe:** B1-B4 pass — no ALGO/DATA_INCOMPLETE leak (Issue F not
   regressed), sorted views display-only, read path read-only.
6. **Marketing clean:** M1-M4 pass the claim-audit grep with zero hits; M5
   not implying a paid public launch.
7. **Tests green:** `pytest -q` passes on the branch (full suite — the
   Issue-F `TestStatBucketExclusion` and Issue-N3 `test_state_io` suites
   included and green).
8. **Docs honest:** any data that is fallback / stale / cached / estimated is
   labelled as such in code and Hebrew output (AGENTS.md #1; CLAUDE.md "When
   uncertain"). No fallback presented as exact truth anywhere in the new
   flows.

If any BLOCKER fails: **do not commit.** Re-scope the failing team's change to
a smaller, safe increment and re-run this checklist. Accuracy over confidence.

— Mark
