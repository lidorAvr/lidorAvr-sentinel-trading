# Sprint 11 — Plan & Smoke-Test Findings

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Source:** Founder live smoke-test of the deployed Sprint-10 Open Tasks build on the Orange Pi (clean deploy verified: secure-runner admin guard + hardening active; `[user_context] DEFAULT_USER_ID unset — sentinel` = expected Phase-A byte-identical).
**Decisions locked:** DEC-20260515-006 (ALGO consolidated + non-binding recs), -007 (suppress no-op RUNNER task), -008 (user-facing audit review), -009 (rate-limit unchanged).

## Findings catalog

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | RUNNER MRVL: current stop $157.70 ≈ engine suggestion $158.11 → noise task for a $0.41 move | HIGH (methodology) | DEC-007: suppress when `current_stop ≥ suggested − ε`; Mark sets ε (Wave 1) |
| 2 | "Open-R … (snapshot — לא מאומת כעת)" wording implies a pending verification that never comes | LOW (UX) | Reword: it is the value at task creation; the list re-derives live every open. No decision — Wave 2 |
| 3 | After done/skip the bot re-derives ALL tasks from scratch (every lifecycle handler calls `handle_open_tasks_entry` → full `list_tasks` re-pipeline) | HIGH (UX/perf) | Cache derived list + update the acted task in-place & re-render; mirror the stop-promote batch pattern. No decision — Wave 2 |
| 4 | Some inline buttons have text too long to read | MEDIUM (UX) | Short label (symbol + urgency glyph + tag); full action text only in the detail card. No decision — Wave 2 |
| 5 | ALGO task tap = dead-end popup; founder wants one consolidated ALGO button → disclaimer + per-position observed recommendation | FEATURE (red-line-adjacent) | DEC-006: build it info-only; **gated on Mark's observer-safe ruling** (Wave 1) |
| 6 | No P0 tasks / no trades below stop | — | Not a bug. P0 path not exercisable live now; covered by `tests/test_open_tasks.py` + `test_telegram_tasks.py` |
| 7 | "הזן קידום סטופ" (button under חדר מצב) lists unnecessary ALGO buttons | MEDIUM (UX) | Filter ALGO out of `build_stop_promote_keyboard` entirely (module already intends "discretionary only"). No decision — Wave 2 |
| 8 | Ratchet-up guard: MRVL $157.70 → $1.00 (explicit confirm) → restored $157.70 | ✅ | Works as designed. Audit row `stop_loosen_override` for MRVL is the expected test artifact |
| 9 | No bot surface for the audit trail | FEATURE | DEC-008: user-facing read-only review surface (not dev menu). Read path added to `audit_logger` (additive). Wave 1 design + Wave 2 build |
| 10 | Rate-limit tripped mid-test | discuss | DEC-009: unchanged (guardrail working). No code change |
| 11 | Health: "Missing Stops — 55 rows (MSGE, SNEX, TSLA, JPM, HP)" | pre-existing (data hygiene) | Not introduced by Sprint 10. Logged for a separate data-hygiene pass; not Sprint 11 scope |

## Direct answers given to the founder
- **"When is the Open-R verified?"** — never separately by design; the engine re-derives live every time `📋 משימות פתוחות` opens. The engine is the single source of truth; the snapshot is only the "why at creation". Wording fix = finding #2.
- **"How does the user see the audit log?"** — currently not via the bot (`audit_logger` is write-only by design). DEC-008 changes this with a deliberate additive read path.

## Sprint 11 structure (same proven rhythm)

### Wave 1 — methodology/design (parallel, gates the risky parts)
- **🧠 Mark** — rulings doc: (a) DEC-006 observer-safe ALGO form — exact non-binding Hebrew wording, why it does NOT breach DEC-20260511-001 / invariants #5/#8, and the hard rule "no `Task` object, never counted"; (b) DEC-007 RUNNER suppression `epsilon` (methodological threshold + exact condition vs `compute_suggested_trail_stop`); (c) confirm #2 reword is methodology-neutral; (d) guardrails for the DEC-008 audit-review surface (read-only, no fallback-as-truth #1).
- **🏗️ Architecture + 🤝 UX** — design doc: DEC-008 user audit-review surface (additive `audit_logger` read fn contract; menu placement = normal user menu, not dev; Hebrew most-recent-first format; admin-only via secure_runner already), the #3 cache-and-update-in-place pattern (reuse the stop-promote batch approach), the #4 short-label scheme, and #7 ALGO-out-of-stop-promote.

### Checkpoint
Parent verifies Mark's rulings keep the ALGO observer + #1/#8 red lines and that the audit read path is genuinely read-only.

### Wave 2 — build (single coherent agent, against the locked design)
Implements #1 (engine-suggestion suppression), #5 (consolidated ALGO info per Mark), #9 (audit-review surface + additive read fn), #3 (efficiency), #4 (labels), #2 (wording), #7 (stop-promote ALGO filter) — with tests; full suite must stay green (baseline 1523).

### Consolidate + integrate
Parent independent guardrail verification → commit by explicit filenames → founder redeploys (no new migration expected; if a migration is added it follows the 003 pattern and is flagged).

## Out of scope (logged)
- #11 missing-stops data hygiene (separate pass).
- Day-3 carryover still open: `/clean` confirmation gate; price-fallback labelling.
- T7 portfolio-level drawdown-ack task (from Sprint 10 deferred).
