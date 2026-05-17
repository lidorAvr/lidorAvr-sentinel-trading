# Sprint 14 — Plan & Team-Leads Meeting (Alert-Spam Remediation)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Severity:** HIGH — alert fatigue is actively dangerous: repeated non-actionable pushes bury a genuine P0 (`CAT 22:33 🚨 קריטי | יציאה מיידית | מחיר נוכחי נמוך מסטופ`).
**Structure:** Wave 1 (4 parallel teams, doc-only) → team-leads checkpoint → Wave 2 (build) → consolidation.

## Evidence (founder's live Telegram, 19:36–22:34)

- **PWR `🔥 Power / החזקה (מובילה) / המבנה תקין`** — 7 near-identical pushes in ~2.5h (20:07, 20:44, 20:56, 21:39, 21:52, 22:16, 22:34). Position is FINE, unchanged (Open R 1.3R every time). Pure noise.
- **HOOD (ALGO, `מנוהל חיצונית — בקרה בלבד`)** — 21:08 Weak, 21:20 Broken, 21:45 Broken. ALGO is observer-only (DEC-20260511-001) yet it push-spams.
- **Giveback PWR** — 19:36 and 19:42 (6 min apart) despite `GIVEBACK_COOLDOWN_SEC = 6h`.
- **Legitimate, MUST keep firing:** `CAT 22:33` P0 critical exit (price < stop). The remediation must NOT blanket-suppress real escalations.

## Grounded root-cause suspects (parent investigation, cite for the teams)

- `risk_monitor.py:149-173` `should_alert`: **`if prev is None: return True`** (line 151) — unconditional re-alert when prior state is absent.
- `risk_monitor.py:130-137` `build_position_alert_key` = `{status, action, sizing}` (excludes trigger/price) → for a healthy held position the key is STABLE; the gate at :169 *would* suppress IF `prev` persisted. So the failure is most likely **`prev` / `last_alert_ts` / giveback-class memory NOT surviving between monitor cycles or across deploys**, not the gate logic.
- `risk_monitor_state.json` is **git-tracked (not gitignored)**, runtime-mutated, with `.pre-deploy.*` / `.pre-mitigation.*` backups observed on the Pi. This session ran many `docker compose up -d --build --force-recreate` + `git pull` deploys → strong candidate: each deploy resets the anti-spam memory (file reverted by `git pull` and/or not volume-persisted across container recreate).
- ALGO observer-only positions still traverse the live-alert push path with no ALGO-specific throttle.
- Giveback dedup failing the same way (6h cooldown ineffective) → same persistence root cause.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (team lead — gates Wave 2):** `MARK_SPRINT14_RULINGS.md`
  - The authoritative **alert policy**: which states/conditions are push-worthy vs pull-only (Open Tasks); the correct re-alert cadence per priority tier (P0–P3, risk_monitor.py:55-79); the absolute rule that **real P0 escalations (price<stop / →Broken / critical-exit) always fire** and must never be suppressed by any anti-spam change. Rule ALGO push policy (observer-only — DEC-20260511-001: should ALGO push at all, or P0-only?). Rule the giveback re-alert policy. Rule whether a healthy held position (`Power/hold/structure-intact`, unchanged) should EVER push (likely: no — it is the position working; move to the pull surface).
  - Rule the **state-persistence requirement**: anti-spam memory MUST survive monitor cycles AND deploys; rule whether `risk_monitor_state.json` must be gitignored + volume-persisted (and that doing so changes no risk/NAV/campaign math).
  - 12-item pass/fail checklist for the consolidation, citing AGENTS.md invariants (esp. the anti-spam / no-recurring-without-dedup rule) + DEC IDs; explicit "must STILL fire" cases.
- **🏗️ Architecture + 🛠️ Infra:** `SPRINT14_DESIGN.md` — (1) confirm the persistence root cause in code (is `risk_monitor_state.json` volume-mounted in `docker-compose.yml`? is it loaded before `should_alert`? does `git pull` revert it?); (2) design the fix per Mark: persist/ignore the state file correctly (gitignore + volume, or move to a non-tracked path) AND/OR harden `should_alert`/giveback/ALGO gating — minimal, no risk-math change, no `docker-compose.yml` service-command change (secure_runner stays; a `volumes:` add is allowed if Mark rules it). ⟨MARK⟩ slots for all policy numbers. Wave-2 test plan (the dedup/persistence logic IS unit-testable — design the tests; baseline 1620).
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT14_ADDENDUM.md` (short) — confirm no migration / no user_id threading; if the state file moves/persists, Phase-A byte-identical, single-user.
- **📣 Marketing:** `MARKETING_SPRINT14_WEEK4.md` — week-4 of the closed-beta calendar; note alert-spam as a known issue gating wider Ring expansion (testers must not be spammed). Deltas-only, DEC-001..009.

## Checkpoint
Parent verifies Mark's grounding (the `should_alert`/persistence claims), that the design changes no risk/NAV/campaign math and no `docker-compose.yml` service command, and that every "must STILL fire" P0 case is preserved.

## Hard constraints (carry into Wave 2)
No risk/NAV/campaign/stop math change. No `docker-compose.yml` service-command change (a `volumes:` mount may be added ONLY if Mark rules it; secure_runner untouched). No new migration. Real P0 escalations must keep firing. Full suite green (baseline 1620). `risk_monitor.py` is a CLAUDE.md most-fragile area — minimal, Mark-gated, tested.

## Out of scope (carried)
Sprint 11/12/13 live founder-UI smoke-test still outstanding. Hyperscaler PR-A3+. Auto-deploy watcher install (DEC-20260515-010 — manual deploy.sh stands).
