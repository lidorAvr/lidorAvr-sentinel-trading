# Sprint 13 — Plan & Team-Leads Meeting

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Theme:** Operational hardening + data hygiene (from live-deploy findings).
**Structure:** same proven rhythm — Wave 1 (4 parallel teams, doc-only) → team-leads checkpoint → Wave 2 (build) → consolidation/integration.

## Inputs (live findings this session)

1. **Stale Docker network on `--build` deploy (HIGH, infra).** A `git pull && docker compose up -d --build` (the `🔄 Git Pull + Deploy` path via `deploy_watcher.sh`) left the telegram-bot container with no route out (`[Errno 101] Network is unreachable`) while the host + DNS were fine. `docker compose down && up -d` (network recreate) fixed it. **`deploy_watcher.sh` does NOT `down` before `up --build`, so every future button-deploy can recur this.** `deploy_watcher.sh` + docker-compose is a CLAUDE.md *most-fragile area* (production wiring) — conservative change only, Mark-ruled, with rollback.
2. **Missing stops (55 rows: MSGE, SNEX, TSLA, JPM, HP).** Sprint 12 added a `/health` notice only. Open question: what is the *methodology-safe* remediation? Stops must never be fabricated (AGENTS.md #1/#8). Mark rules the safe path (notice-only vs surface as actionable data-completion items vs legacy-classify).
3. **Sprint 11/12 live smoke-test outstanding.** Deployed (`7c88ea7`) and full-suite-green (1609), but NOT yet founder-UI-verified (the network outage pre-empted it; founder chose to proceed). Tracked, not blocking — recommend running it after Sprint 13 deploy.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (team lead — gates Wave 2):** `MARK_SPRINT13_RULINGS.md`
  - Rule the **safe `deploy_watcher.sh` change**: which sequence (e.g. `down` then `up -d --build`, or `up -d --build --force-recreate`) minimizes both the stale-network risk and downtime; the hard rule that it must NOT alter `docker-compose.yml` service commands (secure_runner stays — CLAUDE.md hard constraint); a mandatory post-deploy connectivity self-check + what it should do on failure (log/alert, never silently leave a dead bot); explicit rollback. Cite `deploy_watcher.sh` lines.
  - Rule the **missing-stops remediation**: which of {notice-only / surface as actionable real-stop-completion items via the existing journal-backlog or Open Tasks / legacy-classify the truly-archived ones via the now-gated /clean} is methodology-safe; the absolute rule that no stop value is ever fabricated and these rows never enter WR/Expectancy (#8).
  - 10-item pass/fail checklist for the team-leads consolidation.
- **🏗️ Architecture + 🛠️ Infra:** `SPRINT13_DESIGN.md` — concrete design for the `deploy_watcher.sh` change (consume Mark's ruling; ⟨MARK⟩ slots), the post-deploy connectivity probe, the manual verification + rollback procedure (it's a host systemd-run bash script — not unit-testable; design the verification), and the missing-stops surface (per Mark). Explicit "will NOT change" list (docker-compose service commands, secure_runner, risk/NAV/campaign math).
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT13_ADDENDUM.md` (short) — confirm none of Sprint 13 needs a migration / threads user_id; the missing-stops surface, if it stores anything, reuses the existing `open_tasks`/journal contracts with the sentinel user_id. Phase-A byte-identical.
- **📣 Marketing:** `MARKETING_SPRINT13_WEEK3.md` — execute week-3 of the closed-beta calendar (MARKETING_V1.md §5), deltas-only vs week 2, DEC-001..009 compliant, no numbers.

## Checkpoint
Parent independently verifies Mark's grounding (the `deploy_watcher.sh` lines, that the design does not touch `docker-compose.yml` service commands / secure_runner, missing-stops never fabricates) before releasing Wave 2.

## Wave 2
Single coherent build against the locked design + Mark's rulings; tests where testable; full suite stays green (baseline **1609**); no `docker-compose.yml` service-command change; no new migration.

## Integration ("הטמעה") note
The `deploy_watcher.sh` change only takes effect on the Pi once the updated script is on disk AND the `deploy-watcher` systemd service re-reads it — that is a **manual host step** (the watcher cannot safely hot-swap the very script running the deploy). The consolidation will document the exact one-time host procedure + rollback.

## Out of scope (carried)
Hyperscaler PR-A3+ (only when moving past single-user); broad data backfill beyond the 55 flagged rows; anything not listed above.
