# Open Tasks (Action-Items) — Methodology Spec

**Author:** Mark (Methodology Owner — Minervini SEPA canon)
**Branch:** `claude/review-system-audit-FBZ2h`
**Date:** 2026-05-15
**Sprint:** 10 — "Open Tasks" engine
**Status:** authoritative methodology ruling for the engineering teams

This document defines **what tasks the engine may emit and on what authority**.
It is methodology, not implementation. Engineering owns the schema and code;
this owns the *rules*. It does not supersede `AGENTS.md` / `CLAUDE.md` /
`MARK_DAY3_GUARDRAILS.md` — it operationalizes them for the action-items engine.

Mandatory inputs read: `AGENTS.md` (invariants #1–#8 at `AGENTS.md:9-16`,
Red Lines `AGENTS.md:61-73`), `CLAUDE.md`, `docs/DECISIONS.md`
(DEC-20260511-001, DEC-20260515-002), `docs/teams/MARK_DAY3_GUARDRAILS.md`
(esp. §2.2 ratchet-up rule, §5 C3).

**Core principle (read first):** The Open Tasks engine is a **read-only
surface over the existing 10-state machine**. It does not introduce a single
new threshold or compute one new R/NAV/campaign number. Every trigger is an
already-shipped engine state or function. Tasks are *how the existing truth is
presented as an action with a lifecycle* — nothing more. (AGENTS.md invariant
#2; `MARK_DAY3_GUARDRAILS.md` §2.1 U2; CLAUDE.md hard constraint "Do not change
R, NAV, exposure, or campaign math without tests".)

---

## 1. Authoritative task ruleset table

One row = one actionable task type. **Trigger** cites the exact engine
state/function that already produces the signal — the tasks engine reads it,
it does not re-derive it. **Urgency** maps onto the existing `ALERT_PRIORITY`
tiers (`risk_monitor.py:56-79`); the tasks engine reuses these, it does not
invent a new severity scale. All file:line under
`/home/user/lidorAvr-sentinel-trading`.

| # | Task type | Trigger condition (existing engine, file:line) | Recommended action (Hebrew, short, RTL) | Urgency (existing tier) | Auto-closes when | ALGO / DATA_INCOMPLETE handling |
|---|---|---|---|---|---|---|
| T1 | **Close trade — stop hit** | `compute_position_state()` returns `BROKEN` via `_price_through_stop()` true (`engine_core.py:2018`, `:1744`). Mirrors `stop_breach` P0 / `broken_state` (`risk_monitor.py:58,63`). | ‏🔴 מחיר חצה את הסטופ — *סגור עכשיו*. אין שיקול דעת. | **P0** (`stop_breach`, `risk_monitor.py:58`) | Auto-closes only when campaign `has_open_quantity=False` (position actually closed). State leaving BROKEN by a price bounce does **not** auto-close — see §3 dedup. | Excluded. ALGO never emits T1 (DEC-20260511-001; §4 G2). DATA_INCOMPLETE cannot reach BROKEN (`engine_core.py:2013` returns first). |
| T2 | **Close trade — violation broken** | `compute_position_state()` returns `BROKEN` via `violation_score >= _VIOLATION_BROKEN` (=6) (`engine_core.py:2020-2022`, `:1708`). | ‏🔴 ניקוד חריגות שבור — *סגור / צמצם מיידית*. | **P0** (`broken_state` is P1 `risk_monitor.py:63`, but a confirmed BROKEN exit is an Action-Required exit → treat as P0 actionability; **not a new number** — same BROKEN state, escalated routing only) | Same as T1 (open quantity → 0). | Excluded (as T1). |
| T3 | **Protect profit / trail stop (RUNNER)** | `compute_position_state()` returns `RUNNER` (`engine_core.py:2024-2035`, `_R_RUNNER=5.0` `:1685`). Action level taken verbatim from `compute_suggested_trail_stop()` (`engine_core.py:1911`): R≥8→MA21, R≥5→MA50, else breakeven (`:1936-1946`, `_TRAIL_TIGHT/LOOSE` `:1889-1890`). | ‏🏃 Runner — הדק סטופ לפי ההמלצה ({basis}, ${stop}). אל תרופף. | **P1** (`runner_state`, `risk_monitor.py:64`) | Auto-closes when state leaves RUNNER **and** the suggested stop is no longer above the live stop (i.e. user already raised it; see §3). Requires user action otherwise. | Excluded. ALGO never gets a trail/stop task (DEC-20260511-001; §4 G2). DATA_INCOMPLETE cannot reach RUNNER. |
| T4 | **Tighten stop (PROFIT_PROTECTION)** | `compute_position_state()` returns `PROFIT_PROTECTION` (`engine_core.py:2037-2040`, `_R_PROFIT_PROTECT=2.0` `:1686`). Existing recommendation "שקול הדקת סטופ" (`risk_monitor.py:396`). | ‏🛡️ 2R+ — שקול הדקת סטופ להגנת רווח. | **P2** (informational protection; aligns with `profit_checkpoint` P2 `risk_monitor.py:69`; `PROFIT_CHECKPOINTS=[2.0,3.0]` `risk_monitor.py:40`) | Auto-closes on transition to RUNNER (→ T3 supersedes) or back below 2R, or on user "done". Advisory: a user "skip" is allowed and low-consequence. | Excluded (DATA_INCOMPLETE/ALGO cannot reach this state). |
| T5 | **Trim / exit decision (DEAD_MONEY)** | `compute_position_state()` returns `DEAD_MONEY` (`engine_core.py:2053-2061`; `_DEAD_MONEY_*` `:1696-1699`). Existing recommendation "שקול צמצום" (`risk_monitor.py:394`). | ‏⏳ הון מת — החלט: לצמצם / לצאת ולפנות הון. | **P3** (`dead_money_state`, `risk_monitor.py:75`) | Auto-closes on state transition (e.g. price makes a new high → leaves DEAD_MONEY) or user "done" recording the decision. | Excluded by construction (DEAD_MONEY unreachable for ALGO/DATA_INCOMPLETE). |
| T6 | **Review position (YELLOW_FLAG)** | `compute_position_state()` returns `YELLOW_FLAG` via `violation_score >= _VIOLATION_YELLOW_FLAG` (=2) (`engine_core.py:2048-2051`, `:1707`). Existing recommendation "מעקב צמוד" (`risk_monitor.py:395`). | ‏🟡 דגל צהוב — בדוק חריגה, החלט אם להדק/לצאת. | **P2** (review-level; below P1 broken, above P3 dead-money — reuses existing rank, no new tier) | Auto-closes when violation_score falls below 2 (state leaves YELLOW_FLAG) or user "done". | Excluded (unreachable for ALGO/DATA_INCOMPLETE). |
| T7 | **Acknowledge risk-cut (drawdown trigger)** | `adaptive_risk_engine` drawdown auto-cut: 30-day PnL ≤ `DRAWDOWN_TRIGGER_PCT` (−8%) of NAV → risk forced to `DRAWDOWN_CUT_TO_PCT` (0.40%) (`adaptive_risk_engine.py:27-29`). Portfolio-level, not per-campaign. | ‏🩸 ירידה ≥8% ב-30 יום — הסיכון הורד ל-0.40%. אשר שראית. | **P3** (`adaptive_risk`, `risk_monitor.py:77`; this is an acknowledgment, the cut already happened automatically) | Requires explicit user acknowledgment (it is an "I saw this" task, not a trade action). Does not auto-close — the cut is a fact; the ack is the lifecycle event. | N/A — portfolio-level, not a per-position numeric task. Must state plainly the cut already occurred (no fallback-as-truth, AGENTS.md #1). |
| T8 | **Info: ALGO deviation review** (optional, info-only) | `management_mode == "algo_observed"` → `ALGO_OBSERVED` (`engine_core.py:2007-2010`). Max actionability "Review Required" (DEC-20260511-001). | ‏🤖 ALGO — בקרה בלבד. אין פעולת ניהול מטעם Sentinel. | **P3** (`algo_visibility`, `risk_monitor.py:76`) — info only | Never an action task. Display/ack only; auto-clears when the campaign closes externally. | This *is* the ALGO handling: info-only, never a stop/exit/trim instruction (DEC-20260511-001; AGENTS.md #5/#8). |

**DATA_INCOMPLETE produces no numeric task at all.** When
`management_mode=="unknown"` or `original_campaign_risk<=0`
(`engine_core.py:2013`), the only permissible "task" is a non-numeric data
hygiene prompt ("‏⚠️ נתוני סיכון חסרים — השלם entry/stop כדי שהפוזיציה תיכלל").
It carries **no R, no $, no urgency tier**, and it must never be counted in any
stat (AGENTS.md invariant #8; DEC-20260511-001; `MARK_DAY3_GUARDRAILS.md` §2.3
U6 / §3.1 B1). Treat it as a "complete your data" notice, not an action-item.

---

## 2. Ruling on the 2 NEW rules

The founder's EXAMPLE rules — (a) "1R → move stop to breakeven", (b) "3R →
lock average profit" — were explicitly flagged as *examples to research, not
canon*. Ruling below. **No invented numbers**: every retained threshold is
anchored to an existing engine constant or an explicit Minervini principle.

### (a) "1R → move stop to breakeven" — REJECT the mechanical form, REPLACE

**Actual Minervini stance.** Minervini does **not** mechanically move the stop
to breakeven at "exactly +1R". In *Trade Like a Stock Market Wizard* (stop-loss
and "selling into strength" chapters) the discipline is: the initial stop is a
fixed maximum loss; you **raise the stop as the trade proves itself and as
structure develops** (price clears the base / pivot, prior consolidation, a
rising MA), and you sell strength rather than donate profit back. Breakeven is
a *consequence of the trade clearing risk and building structure*, not a fixed
"+1.0R" event. A rigid "1R → breakeven" can stop you out on normal post-breakout
volatility and is not Minervini.

**Corrected, defensible rule.** There is **no new "1R" task**. The
breakeven-raise behaviour is *already implemented* and is the correct one:
`compute_suggested_trail_stop()` returns `breakeven` as the floor case
(`engine_core.py:1944-1946`) and the state machine only escalates stop-tightening
through `WORKING` → `PROFIT_PROTECTION` (≥2R, `_R_PROFIT_PROTECT=2.0`
`engine_core.py:1686`) → `RUNNER`. The defensible rule is therefore:

> *Stop promotion toward breakeven and beyond is governed by the existing
> state ladder + `compute_suggested_trail_stop()`. The Open Tasks engine emits
> T3/T4 (RUNNER / PROFIT_PROTECTION). It does NOT emit a standalone "+1R →
> breakeven" task, because no engine constant defines a 1R breakeven event and
> inventing 1.0 would be a fabricated threshold (AGENTS.md #2;
> `MARK_DAY3_GUARDRAILS.md` A11 "stale default = silent methodology drift").*

Source: *Trade Like a Stock Market Wizard*, risk-management / sell-into-strength
chapters; engine constants `_R_PROFIT_PROTECT=2.0` (`engine_core.py:1686`),
`compute_suggested_trail_stop` breakeven case (`:1944-1946`);
`MARK_DAY3_GUARDRAILS.md` §2.2 (stops ratchet up, never down).

### (b) "3R → lock average profit" — REJECT as written, MAP to existing logic

**Actual Minervini stance.** Minervini locks in profit by **selling into
strength and trailing the stop up under structure (e.g. the 50-day / 21-day
MA)** — not by a mechanical "average profit lock at exactly 3R". "Lock average
profit" is undefined methodologically (average of what?) and "3R" is not an
engine constant.

**Corrected rule / mapping.** Reject the new rule. The 3R region is **already
covered**: `PROFIT_CHECKPOINTS=[2.0,3.0]` (`risk_monitor.py:40`) already fires a
P2 `profit_checkpoint` alert at 3R, and stop-trailing at scale is
`compute_suggested_trail_stop()` (R≥5→MA50, R≥8→MA21,
`engine_core.py:1936-1943`). The Open Tasks engine therefore maps "3R" onto:
the existing **T4 PROFIT_PROTECTION** task (≥2R, covers the 3R band) and, at
R≥5, **T3 RUNNER/trail**. **No new "3R lock" task is created** — doing so would
both invent a threshold and double-notify against the existing
`profit_checkpoint` alert (AGENTS.md invariant #7; §4 G5).

Source: *Trade Like a Stock Market Wizard* sell-into-strength / trailing-stop
chapters; engine constants `PROFIT_CHECKPOINTS` (`risk_monitor.py:40`),
`_TRAIL_LOOSE_R_THRESHOLD=5.0` / `_TRAIL_TIGHT_R_THRESHOLD=8.0`
(`engine_core.py:1889-1890`).

**Net ruling:** both NEW rules are *rejected as written* and *absorbed into
existing engine logic*. Sprint 10 ships **zero new numeric thresholds**.

---

## 3. Lifecycle methodology

**Task identity / dedup.** Exactly **one open task per
`(campaign_id, task_type)`**. `campaign_id` is the existing format
(`{SYMBOL}_{tradeID}`, DEC-20260512-004) — the tasks engine reads it, never
mints it. A new state-derived task for a campaign whose prior task is of a
*different* type **supersedes** the prior open task (close prior with
`reason=superseded`, open the new one). This mirrors the per-position dedup
discipline already mandated for alerts (AGENTS.md invariant #7; Red Line "Add a
recurring Telegram alert that does not check a per-position dedup flag";
`MARK_DAY3_GUARDRAILS.md` §2.4 U7).

**Auto-satisfied (no user action) — by state transition only:**
- A task is auto-closed when the underlying engine state that produced it no
  longer holds **and** the closing condition in column "Auto-closes when"
  (table §1) is met. The authority is the next `compute_position_state()`
  result for that campaign — the tasks engine never decides this itself.
- T1/T2 (BROKEN exit) auto-close **only** on `has_open_quantity=False` (the
  position is genuinely closed). A BROKEN→not-BROKEN flip caused by a price
  bounce does **not** auto-close a P0 exit task (it would launder away an
  unactioned critical exit) — it converts to `state=stale`, stays visible, and
  must be explicitly resolved by the user. (AGENTS.md #1 no fallback-as-truth /
  honesty; this is the analogue of "do not erase the signal",
  `MARK_DAY3_GUARDRAILS.md` U6.)

**Requires explicit user "done":**
- T7 (drawdown ack) — always; it is an acknowledgment, not a transition.
- T5/T6 — close on either state transition *or* an explicit user decision; the
  user "done" records that the discretionary decision was made.

**"Skip" semantics (methodological).** A "skip" means *the user consciously
chose not to act on this task* — it is a recorded decision, not a deletion.
- Skipping **P2/P3** (T4/T5/T6, advisory) is normal discretion: record
  `skipped`, with optional note, and stop re-notifying for that
  `(campaign_id, task_type)` until the state changes.
- **Skipping a P0 BROKEN exit (T1/T2) is NOT a silent drop.** It must be
  logged with timestamp + the user's note as an explicit
  `skipped_critical_exit` event (audit trail), the task stays visible (not
  closed), and re-notification follows the existing BROKEN cooldown
  (`STATE_ALERT_COOLDOWN["BROKEN"]=4h`, `risk_monitor.py:51`) — it must **not**
  be silenced. Skipping a P0 never deletes the task. (AGENTS.md invariants #1
  and #4; CLAUDE.md "Do not silently present fallback data as exact truth" /
  honesty; mirrors the explicit-confirm + audit pattern of
  `MARK_DAY3_GUARDRAILS.md` U4 and DEC-20260510-008.)

**Notes lifecycle.** Free-text notes attach to `done`/`skipped` events and are
operational metadata only — they are **never** trading data and must never
mutate Supabase trade rows (AGENTS.md invariant #4; CLAUDE.md "Do not mutate
Supabase from read-only flows"). Store with the local-JSON / `state_io`
atomic+locked pattern already mandated for shared state
(`MARK_DAY3_GUARDRAILS.md` U9; DEC-20260510-006).

---

## 4. Hard guardrails for the engineering teams (pass/fail)

Binary checklist. Any FAIL = the Open Tasks engine does not ship.

- [ ] **G1. Read-only over engine math.** The tasks engine introduces **no**
  new R / NAV / exposure / campaign math. Every trigger reads an existing
  `compute_position_state()` result or an existing `ALERT_PRIORITY` /
  checkpoint constant. `grep` the new module: zero new numeric trading
  thresholds; zero calls that recompute `original_campaign_risk` /
  `compute_r_true`. (AGENTS.md invariant #2; `MARK_DAY3_GUARDRAILS.md` U2;
  CLAUDE.md hard constraint.)
- [ ] **G2. ALGO_OBSERVED never yields a stop/exit/trim action task.** For
  `management_mode=="algo_observed"` the engine emits at most T8 (info-only,
  P3). No T1/T2/T3/T4/T5 ever for ALGO. (DEC-20260511-001; AGENTS.md #5/#8;
  `MARK_DAY3_GUARDRAILS.md` U5.)
- [ ] **G3. DATA_INCOMPLETE never yields a numeric task.** Only a non-numeric
  "complete your data" notice with no R/$/urgency, never counted in any stat.
  (AGENTS.md invariant #8; `MARK_DAY3_GUARDRAILS.md` §2.3 U6 / §3.1 B1;
  DEC-20260511-001.)
- [ ] **G4. No task may instruct a stop LOOSEN.** Any task whose action is a
  stop change must, for a long, only ever raise (`new_stop >= current_stop`).
  The ratchet-up rule just shipped (`MARK_DAY3_GUARDRAILS.md` §2.2 U3, §5 C3) —
  tasks must respect it. A task suggesting a lower stop = FAIL. Tasks describe
  the existing `compute_suggested_trail_stop()` output verbatim; they never
  compute their own stop.
- [ ] **G5. No double-notify vs existing push alerts.** Tasks **reuse** the
  `risk_monitor` per-position dedup + `STATE_ALERT_COOLDOWN`
  (`risk_monitor.py:49-53,81-99`) state; they do not emit a second independent
  notification stream for the same `(campaign_id, state)`. The Open Tasks list
  is a *view/lifecycle* over signals the monitor already raises — not a new
  alerter. (AGENTS.md invariant #7; Red Line; `MARK_DAY3_GUARDRAILS.md` §2.4
  U7/U8.)
- [ ] **G6. Read-only over Supabase.** Task derivation issues SELECTs only.
  The only writes are the user's explicit `done`/`skip`/`note` lifecycle
  events, stored in local JSON via the atomic+locked `state_io` path — never a
  `trades` table mutation. (AGENTS.md invariant #4; CLAUDE.md; DEC-20260510-006;
  `MARK_DAY3_GUARDRAILS.md` U9 / §3.2 B4.)
- [ ] **G7. Reuse `ALERT_PRIORITY` tiers; invent no new severity scale.**
  Urgency is exactly P0–P3 from `risk_monitor.py:56-79`. (AGENTS.md #2
  explainability.)
- [ ] **G8. P0 exit tasks cannot be silently auto-closed or silently
  skipped.** §3 lifecycle enforced: T1/T2 close only on real close; a P0 skip
  is an audited `skipped_critical_exit`, never a delete. (AGENTS.md #1/#4;
  CLAUDE.md honesty.)
- [ ] **G9. Admin-only.** The tasks surface is reachable only through the
  existing admin-gated Telegram path; no new unauthenticated entry point, no
  bypass of `telegram_bot_secure_runner.py`. (AGENTS.md invariant #3 / Red
  Line; CLAUDE.md hard constraint.)

---

## 5. Six predicted Sprint-10 conflicts + Mark's ruling

| # | Conflict | Teams | Mark's ruling |
|---|---|---|---|
| **K1** | UX wants a fast "mark all done" / "clear all tasks" sweep; lifecycle wants discrete per-task resolution | UX ↔ Mark | **Discrete wins.** A bulk "done" that closes a P0 BROKEN exit (T1/T2) with one tap is FAIL (G8, §3). UX may *bulk-dismiss P2/P3 advisory* tasks with a single confirm, but each P0/P1 resolution is an individual, explicit action. Mirrors `MARK_DAY3_GUARDRAILS.md` §5 C1. |
| **K2** | Founder/UX want the literal "1R→breakeven" and "3R→lock profit" tasks shipped as given | Founder/UX ↔ Mark | **Rejected as written (§2).** Both are absorbed into existing T3/T4 + `PROFIT_CHECKPOINTS`/`compute_suggested_trail_stop`. Zero new thresholds. Inventing 1.0R/3.0R task triggers = fabricated numbers (AGENTS.md #2). Non-negotiable. |
| **K3** | Engineering wants the tasks engine to compute its own "is this still actionable?" R check for snappy auto-close | Eng ↔ Mark | **Frozen.** Auto-close authority is the next `compute_position_state()` result only (§3, G1). The tasks engine must not run a parallel R/threshold computation — that is the `is_stat_countable`-style dilution attack vector (`MARK_DAY3_GUARDRAILS.md` A4, §5 C5). |
| **K4** | UX wants a richer urgency scale (e.g. "critical/high/med/low/info" with colors) distinct from P0–P3 | UX ↔ Mark | **Reuse P0–P3 (G7).** Map labels/colors for display, but the underlying tier is the existing `ALERT_PRIORITY`. A second severity taxonomy makes urgency unexplainable and drifts from the monitor (AGENTS.md #2). |
| **K5** | A BROKEN price bounce makes the task list "noisy"; UX wants the T1 task to auto-disappear when price recovers above the stop | UX ↔ Mark | **No auto-disappear (§3).** A P0 exit that was never actioned must not be laundered away by a transient bounce — it becomes `stale`, stays visible, needs explicit resolution (G8; analogue of `MARK_DAY3_GUARDRAILS.md` U6 "do not erase the signal"). |
| **K6** | Tasks engine wants to push its own Telegram notification per new task for visibility | Eng/UX ↔ Mark | **No second alert stream (G5).** Tasks reuse `risk_monitor` dedup + `STATE_ALERT_COOLDOWN`; the Open Tasks list is a view/lifecycle, not a new alerter. A per-task push that bypasses per-position dedup = FAIL (AGENTS.md #7, Red Line; `MARK_DAY3_GUARDRAILS.md` §2.4). |

---

## 6. Machine-readable ruleset block (Sprint-10 Wave-2 checkpoint)

The Wave-1 design proposed parsing this `.md` at runtime; the Wave-2 build
checkpoint **rejected runtime `.md` parsing as fragile**. Resolution that keeps
Mark the owner:

- The runtime ruleset is a typed Python constant `_RULESET` in `open_tasks.py`,
  transcribed **verbatim** from §1 / §2 above (every entry carries a
  `# spec:` comment citing the row here).
- This block below is the **audit source of truth**. A CI drift test
  (`tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`) re-reads
  the fenced block below and asserts `open_tasks._RULESET` matches it exactly.
  Any future divergence between Mark's ruling and the code fails CI loudly —
  Mark stays the owner; the `.md` is the audit source; the constant is the
  runtime source.
- Schema per `OPEN_TASKS_ENGINE_DESIGN.md` §1.6. `urgency` values are exactly
  the existing `ALERT_PRIORITY` tiers (`risk_monitor.py:56-79`); no new scale.
- States not listed (`NEW`, `PROVING`, `WORKING`) intentionally map to **no
  task** (§1: the table only lists actionable/observed states T1–T8).
- `BROKEN` collapses T1 (price-through-stop) and T2 (violation≥6) into one
  **P0** actionable exit task — the engine already collapses both into
  `state=BROKEN` (`engine_core.py:2019-2022`); the `reason` field on the
  engine `state_result` distinguishes T1 vs T2 for the "why" block, but the
  *task* and its P0 urgency are identical (spec §1 T1/T2).
- `DATA_INCOMPLETE` carries **no urgency** (`urgency: null`) and
  `info_only: true` — never counted, never numeric (§ "DATA_INCOMPLETE
  produces no numeric task at all"; AGENTS.md invariant #8).
- `RUNNER.suppress_when` = `current_stop_meets_suggested_within_trail_ma_buffer`:
  T3 `PROTECT_RUNNER_PROFIT` is **not emitted** when, for a long,
  `current_stop >= suggested_stop − (_TRAIL_MA_BUFFER_PCT × suggested_stop)`
  (short: symmetric, `+`), where `suggested_stop`/`basis` are
  `compute_suggested_trail_stop()`'s own output (`engine_core.py:1911-1960`)
  and `_TRAIL_MA_BUFFER_PCT` is read live from `engine_core.py:1887` (0.02).
  If `suggested_stop is None` / `basis=="none"` / `current_stop<=0`, the
  task **is** emitted (no suppression on absent/invalid engine output —
  AGENTS.md #1). Read-only over engine output: zero new R/NAV/campaign math
  (DEC-20260515-007; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G1/G4). A *material*
  tighten (gap > epsilon) surfaces unchanged.
- `ALGO_OBSERVED` may be rendered as a **single consolidated info panel**
  (not one row per ALGO position) showing, per position, ONLY the engine's
  existing observation fields (`management_mode`, `risk_basis`, the
  `ALGO_OBSERVED` state label `engine_core.py:1680`, and an external stop
  only if ALGO exposes one). It remains `info_only: true`, is **not** a
  `Task` (no lifecycle, never counted), contains **no** Sentinel-originated
  recommendation or stop, and uses descriptive (non-imperative) Hebrew only
  (DEC-20260515-006 conditional on this ruling; DEC-20260511-001;
  AGENTS.md #5/#8; `OPEN_TASKS_METHODOLOGY_SPEC.md` §4 G2). If unachievable,
  fall back to a single "מנוהל חיצונית — אין פעולת Sentinel" button.
- T7 (drawdown-ack) is **portfolio-level, not a per-position state** — it
  is out of the position-driven `derive_tasks(positions, …)` contract
  and is **deliberately NOT a row in the ```yaml block below and NOT in
  `open_tasks._RULESET`** (adding it either side breaks the
  bidirectional drift test `test_ruleset_matches_methodology_spec`). It
  is derived by a separate portfolio path keyed
  `(campaign_id="__PORTFOLIO__", task_type="ACK_DRAWDOWN_CUT")`, urgency
  **P3** (`ALERT_PRIORITY["adaptive_risk"]`, `risk_monitor.py:77`),
  `info_only:false` ack-task, triggered iff
  `adaptive_risk_engine.drawdown_auto_cut_recommendation()`
  (`adaptive_risk_engine.py:222-259`) returns non-`None` (read-only over
  the engine; constants `:27-29,33` read live, never copied). It emits
  **no** Telegram push (the push is `risk_monitor.py:938-997`; G5,
  §1.5). It never enters WR/Expectancy/any stat (`AGENTS.md` #8). Ack-
  only; auto-closes `reason=condition_cleared` when the engine call later
  returns `None` and the 48h settle elapsed — never as `done` unless the
  user acked (`AGENTS.md` #1; Mark Sprint-12 §1).

```yaml
# OWNED BY MARK — open_tasks._RULESET is transcribed verbatim from this block.
# Audit source of truth. Drift vs the runtime constant fails CI.
# spec rows: §1 task ruleset table T1–T8, §2 NEW-rules ruling.
PROFIT_PROTECTION:
  - task_type: TIGHTEN_STOP_PROFIT
    urgency: P2
    info_only: false
    action_he: "‏🛡️ 2R+ — שקול הדקת סטופ להגנת רווח."
RUNNER:
  - task_type: PROTECT_RUNNER_PROFIT
    urgency: P1
    info_only: false
    action_he: "‏🏃 Runner — הדק סטופ לפי ההמלצה ({basis}, ${stop}). אל תרופף."
    suppress_when: "current_stop_meets_suggested_within_trail_ma_buffer"
YELLOW_FLAG:
  - task_type: REVIEW_YELLOW_FLAG
    urgency: P2
    info_only: false
    action_he: "‏🟡 דגל צהוב — בדוק חריגה, החלט אם להדק/לצאת."
BROKEN:
  - task_type: EXECUTE_EXIT
    urgency: P0
    info_only: false
    action_he: "‏🔴 מחיר חצה את הסטופ / ניקוד חריגות שבור — *סגור עכשיו*. אין שיקול דעת."
DEAD_MONEY:
  - task_type: TRIM_OR_EXIT_DEAD_MONEY
    urgency: P3
    info_only: false
    action_he: "‏⏳ הון מת — החלט: לצמצם / לצאת ולפנות הון."
ALGO_OBSERVED:
  - task_type: ALGO_OBSERVE_ONLY
    urgency: P3
    info_only: true
    action_he: "‏🤖 ALGO — בקרה בלבד. אין פעולת ניהול מטעם Sentinel."
DATA_INCOMPLETE:
  - task_type: COMPLETE_RISK_DATA
    urgency: null
    info_only: true
    action_he: "‏⚠️ נתוני סיכון חסרים — השלם entry/stop כדי שהפוזיציה תיכלל."
```

---

— Mark
