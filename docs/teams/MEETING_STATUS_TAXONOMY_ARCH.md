# Meeting — Status Taxonomy — ARCH ruling

ARCH ruling on the two-classifier divergence (`compute_position_state` vs `map_score_to_status`), API surface, byte-lock baseline refresh procedure, and cross-cut safety. READ-ONLY plan; ENGINE owns code.

## Unification ruling — HARMONIZED, not unified

The two classifiers stay **two functions**; ENGINE's proposed `map_score_to_status` extension (`docs/teams/MEETING_STATUS_TAXONOMY_ENGINE.md:101-109`, new args `age_days` / `open_r` / `has_new_high_since_entry`) is approved. They do NOT collapse into one. Rationale:

1. **Different inputs, different domains.** `compute_position_state` (`engine_core.py:2047-2158`) is a *position-management* classifier — needs `management_mode`, `realized_pnl`, `original_campaign_risk`, `days_to_earnings`, `current_stop`. `map_score_to_status` (`engine_core.py:366-379`) is a *stock-chart trend* classifier — needs only a momentum score + features. Unifying forces the chart classifier to receive position-only data it has no business with (e.g. earnings risk doesn't belong in "סטטוס שוק" trend label).
2. **ARCH F1 precedent.** Phase ARCH-F1 (`docs/teams/PHASE_ARCHF1_SCOPE.md:25-28`, **Decision B = OUT**) explicitly chose to **document the divergence** between `account_state.load()` and `engine_core.get_nav_with_freshness()` rather than unify, because "genuinely different fallbacks/shape → unifying changes which contract a path sees (money-affecting)". Same shape here: the two classifiers have *genuinely different contracts* (10-state position management vs 5-bucket trend label). Unifying changes which contract `/portfolio` main card vs drilldown sees → display drift on every existing position. F1 precedent rules: HARMONIZE, do not unify.
3. **Sprint-25 helper consolidation precedent.** Phase ARCH-F1 step 2 (`PHASE_ARCHF1_SCOPE.md:23`) consolidated only the *duplicated reader* (`get_account_settings`), not the divergent NAV resolvers. The pattern: de-duplicate **byte-identical** code; keep **logically-distinct** functions distinct, and prove non-contradiction via a parity oracle. Apply that here.
4. **What "harmonized" requires.** A new acceptance test (`tests/test_status_taxonomy_harmony.py`, owned by TESTING) asserts: for every (score, position-state) co-output, the **BROKEN axis cannot diverge** — i.e. if `compute_position_state == POSITION_STATE_DEAD_MONEY` and `map_score_to_status == "🔴 Broken"` for the same inputs, that is a RED test. The PLTR-class divergence becomes a CI-gated invariant, not a hope.

**Role assignment (explicit, in `docs/MODULE_MAP.md` follow-up):**
- `compute_position_state` (`engine_core.py:2047-2158`) → "position management state" — what the trader DOES with the position (hold / protect / cut / runner). Surfaces: `/portfolio` drilldown, risk-monitor `_daily_digest_text` (`risk_monitor.py:553+`), open-tasks engine (`open_tasks.py:6, 86, 427`), AI Master Context Export sidebar (`dashboard.py:867, 1077-1081`).
- `map_score_to_status` (`engine_core.py:366-379`) → "stock-chart trend label" — what the chart is DOING (Power / Healthy / Yellow / Weak / Broken). Surfaces: `/portfolio` main card "סטטוס שוק" (`telegram_portfolio.py:525`), `evaluate_position_engine` `status` field, dashboard `Status` column (`dashboard.py:227, 271, 1132`).

These two roles are documented in `MODULE_MAP.md` as part of this change (ARCH owns the doc-only follow-up; not in ENGINE's edit scope).

## Module-placement decision — engine_core (inline), NOT a new module

ENGINE's proposed change is the surgical extension of an existing engine function. Three architectural reasons to keep it inline in `engine_core.py`, not extract to a `position_taxonomy.py`:

1. **`map_score_to_status` is engine math, not a leaf primitive.** The `engagement_suppression.py` pattern (`engagement_suppression.py:1-13`) is justified because suppression is a *cross-service gate* called by `risk_monitor.py` AND `report_scheduler.py` with **zero engine dependency** ("stdlib only ... no imports from engine / formatters / bot"). `map_score_to_status` is the opposite: it lives inside `evaluate_position_engine` (`engine_core.py:460`), uses the engine's `features` dict, and has no out-of-engine caller. Extracting it creates a circular-ish import (the new module would need to be imported back into `engine_core.evaluate_position_engine`) and dilutes engine cohesion.
2. **`MODULE_MAP.md` already names it as engine-resident.** `MODULE_MAP.md:7` lists `engine_core.py` as the "Core analytical engine"; `:42` lists `evaluate_position_engine` as a top-level engine responsibility. `map_score_to_status` is its callee. Splitting it out fragments the engine surface for one feature.
3. **Leaf-vs-engine trade-off.** A leaf module is correct when the helper is **stateless, dependency-free, multi-consumer**. `compute_position_state` shows the counter-pattern: it stays in `engine_core.py:2047` despite being a tight, self-contained function — because it is engine math consumed by engine callers. Same fate for the extended `map_score_to_status`.

**Decision: the extension lands inline at `engine_core.py:366-379`.** New constants (`_DEAD_MONEY_AGE_MIN`, `_NEW_AGE_MAX`, etc.) co-locate with the existing engine constants at `engine_core.py:1744-1765`.

## Byte-lock refresh procedure — surgical, Mark-gated

`engine_core.py` is byte-locked. The 7 byte-lock test files referencing `engine_core.py.baseline` (via `tests/_byte_lock_baseline.py::assert_byte_identical`):

1. `tests/test_sprint24_wave2_refactor.py:231`
2. `tests/test_sprint25_byte_lock_redteam.py:46-52, :185-186`
3. `tests/test_phase_algo2.py:400`
4. `tests/test_phase_algo2a.py:555`
5. `tests/test_phase_algobt1.py:344`
6. `tests/test_phase_report1.py:332`
7. `tests/test_phase_report2.py:524` (+ `tests/test_phase_report3.py:701` is an 8th — the founder's "7" is the Sprint-24/25 redteam set; the report3 lock is the post-Sprint-25 same-mechanism use)

All 8 use the **same baseline file**: `tests/_byte_lock_baselines/engine_core.py.baseline`. The refresh touches ONE artifact, not 7+ files.

**Baseline pin commits** (per `git log --oneline -1 -- <baseline>`):
- `tests/_byte_lock_baselines/engine_core.py.baseline` → `5a0f2cb` (phase-navunify — Arch-F1 Decision B, Option β)
- `tests/_byte_lock_baselines/analytics_engine.py.baseline` → `b926e6e` (phase-engine-p2p3)
- `tests/_byte_lock_baselines/period_data_probe.py.baseline` → `b7fb1bf` (Sprint-25 Wave-2A)
- `tests/_byte_lock_baselines/test_real_data_april_regression.py.baseline` → `b7fb1bf` (Sprint-25 Wave-2A)

**Refresh ritual** (from `tests/_byte_lock_baseline.py:31-37`, "Authorized-change ritual"):
1. Land the ENGINE edit to `engine_core.py:366-379` + the new `_DEAD_MONEY_AGE_MIN` / `_NEW_AGE_MAX` constants on the SAME commit that regenerates `tests/_byte_lock_baselines/engine_core.py.baseline` (verbatim `cp engine_core.py tests/_byte_lock_baselines/engine_core.py.baseline`).
2. The Sprint-25 redteam (`test_sprint25_byte_lock_redteam.py:185-186`) re-asserts byte-identity against the NEW baseline → GREEN.
3. The 4 phase locks (algo2, algo2a, algobt1, report1, report2, report3) all read the SAME baseline file → GREEN automatically.
4. No `analytics_engine.py` / `period_data_probe.py` / `test_real_data_april_regression.py` baseline touched (their pins at `b926e6e` / `b7fb1bf` stay).
5. The April fixture (`test_real_data_april_regression.py`) MUST stay byte-identical (see §Default-behavior preservation).

The Wave-3A.1 `compute_market_regime.confidence` rollback happened because the baseline-regen was attempted out-of-ritual (founder not consulted on baseline rewrite). Tonight's "C + autonomous full development" authorization closes that gate.

## Cross-cut concerns — urgent-state sets must NOT silently widen

Two call-sites consume the classifier outputs as **urgent / critical sets**:

1. **`risk_monitor.py:525-529`** — `_WHATNOW_URGENT_STATES = (POSITION_STATE_BROKEN, POSITION_STATE_RUNNER, POSITION_STATE_PROFIT_PROTECTION)`. This is the *position-state* classifier — UNCHANGED by ENGINE's proposal (the new tags live in `map_score_to_status`, not `compute_position_state`). **Safe.** The Sprint-30 G3 comment (`:580-585`) explicitly pins this tuple as byte-identical to the prior inline literal — any future expansion is gated by that test.
2. **`telegram_portfolio.py:357`** — `_WHATNOW_CRITICAL = ("🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו")`. **`telegram_portfolio.py:560-561`** — `_CRITICAL_STATUS = ("🚨 קריטי", "🔴 Broken", "🚨 חריגת סיכון אלגו")`. Both read the *score-bucket* classifier's `"🔴 Broken"` string. **Risk:** if the new "⏳ Stalled / Dead Money" tag is interpreted as a soft-broken urgent decision-state, it would *incorrectly* leak into "🧭 מה עכשיו?" lede and into the suppression suppress-list at `:572`. **ARCH ruling:** the new tags "🆕 New / Watching" and "⏳ Stalled / Dead Money" are **NOT urgent**, NOT critical, NOT decision-states. They are *informational refinements* of what used to be the catch-all "🔴 Broken" default. The two tuples at `telegram_portfolio.py:357, 560` must NOT include the new strings. UX owns the call on whether a SEPARATE "watch list" lede surfaces the Stalled tag later; that is a follow-up, not this sprint.
3. **`dashboard.py:867-880, 1077-1081`** — AI Master Context Export reads `position_state` (state-machine label) AND `Status` (score-bucket string, `dashboard.py:227, 271`). Both surfaces print verbatim. Coherence requires: if `position_state == DEAD_MONEY` then `Status` MUST be "⏳ Stalled / Dead Money" or "🔴 Broken" (never "🟢 Healthy"). The harmony parity test (above) closes this.

## Default-behavior preservation

The LOCKED April fixture (`tests/test_real_data_april_regression.py`, baseline at `b7fb1bf`) MUST stay byte-stable. ENGINE's predicate guards (`MEETING_STATUS_TAXONOMY_ENGINE.md:122-141`) achieve this:
- New tags fire ONLY when the new kwargs (`age_days`, `open_r`, `has_new_high_since_entry`) are provided.
- Existing call-sites (`engine_core.py:460`, `:479` inside `evaluate_position_engine`) pass them; OTHER existing test call-sites that omit them get the old "🔴 Broken" default (`MEETING_STATUS_TAXONOMY_ENGINE.md:139-141`).
- The April fixture's recorded `Status` strings are byte-identical because the April data does not contain a row that newly trips Stalled/New thresholds (age_days < 5 AND no-new-high since entry AND open_r negative AND score < 40 simultaneously) — TESTING must confirm this with a dry-run **before** the commit lands. If any April row newly trips, the fixture baseline must regenerate ON THE SAME commit (founder gate).

## Sign-off

- **Unification ruling:** HARMONIZED (two classifiers, parity-tested for BROKEN-axis non-contradiction).
- **Module placement:** inline `engine_core.py:366-379` (NOT a new `position_taxonomy.py`).
- **Byte-lock refresh:** ONE artifact (`tests/_byte_lock_baselines/engine_core.py.baseline`), regenerated on the same commit as the engine edit; 8 byte-lock tests pass automatically.
- **Top architectural risk:** the two `_CRITICAL_STATUS` tuples in `telegram_portfolio.py:357, 560` silently absorbing the new "⏳ Stalled / Dead Money" tag if a future refactor uses substring matching ("Broken" in status). The harmony parity test + an explicit "Stalled is NOT critical" unit assertion close this. TESTING owns both.

**Companion-doc coherence (ARCH cross-check):** ENGINE's proposal at `docs/teams/MEETING_STATUS_TAXONOMY_ENGINE.md:90` defines ordering "hard_rule → Power → Healthy → Yellow Flag → Weak → Tag 1 (New) → Tag 2 (Stalled) → Tag 4 (Broken default)". ARCH approves this ordering — it preserves the existing 5-bucket cascade and inserts the new tags as a *refinement of the Broken default*, not as a re-entry point above existing thresholds. UX and MARK should agree on the Hebrew copy of the two new labels before commit (Hebrew rendering must remain RTL-friendly per CLAUDE.md).

**Out-of-scope (explicit, ARCH ruling):** (a) no change to `compute_position_state` signature or 10-state taxonomy; (b) no change to `risk_monitor._WHATNOW_URGENT_STATES`; (c) no change to `account_state.py` / `engine_core.get_nav_with_freshness` (ARCH-F1 invariants intact); (d) no new module file; (e) no callback / command / migration / schema change. The blast radius is exactly two edits: `engine_core.py` (the function + new threshold constants) and `tests/_byte_lock_baselines/engine_core.py.baseline` (regenerated verbatim).

ARCH cleared for ENGINE to implement on founder go-ahead.
