# Hyperscaler — Sprint 14 Addendum: Phase-A Compatibility

**Date:** 2026-05-15
**Team:** Hyperscaler
**Scope:** Sprint 14 — alert-spam remediation in `risk_monitor.py`
(anti-spam state persistence across cycles/deploys + `should_alert` /
ALGO / giveback alert-gate hardening).
**Governing:** `SPRINT14_PLAN.md`, `HYPERSCALER_PHASE_A_IMPL.md`,
`HYPERSCALER_SPRINT13_ADDENDUM.md`, `user_context.py`,
`migrations/verify_migrations.py` (ledger ends at `005 → open_tasks`),
DEC-20260515-002, DEC-20260515-005.
**Status:** Doc only. No code, no migration, no commit, no
`docker-compose.yml` edit. Phase B stays a pure no-op swap.

---

## 1. Sprint 14 is anti-spam state + alert-gate logic only — zero Phase-A surface

The remediation is entirely (a) making `should_alert` /
`last_alert_ts` / giveback-class / ALGO memory survive monitor cycles
and deploys, and (b) tightening the gate predicates. It introduces:

- **no DB schema change** — no `ALTER`, no new column, no new `*.sql`;
  `migrations/verify_migrations.py` unchanged (ledger stays at `005`);
- **no migration** — the anti-spam memory lives in
  `risk_monitor_state.json` (a runtime file), never in Supabase;
- **no `user_id` threading** — `risk_monitor.py` does not gain a
  `user_id` parameter or a `user_context` import; that stays
  **PR-A3+ deferred** (see `HYPERSCALER_PHASE_A_IMPL.md §2`);
- **no `get_user_constant()` rewiring** — the cooldown constants
  (`live_alert_repeat_cooldown_sec`, `giveback_cooldown_sec`, the
  `STATE_ALERT_COOLDOWN` map, `PROFIT_CHECKPOINTS`) keep being read as
  their own module-level constants exactly as today; they are only
  *mirrored* read-only in `_BUILTIN_DEFAULTS` (`user_context.py:208-215`).
  Sprint 14 changes alert *gating*, not those values, so the mirror does
  not drift and the single-user smoke test stays byte-identical.

Single-user runtime is **byte-identical**: the only behaviour change is
fewer duplicate pushes for the existing (single) user; the alert *set*
for any given state is unchanged in content, only de-duplicated.

## 2. `risk_monitor_state.json` is per-host runtime state — Phase-A neutral

`risk_monitor_state.json` is currently git-tracked (confirmed:
`git ls-files` lists it; absent from `.gitignore`) and runtime-mutated —
exactly the persistence root-cause in `SPRINT14_PLAN.md:19`. If Mark
rules it must be **gitignored + volume-persisted** (or moved to a
non-tracked path):

- It is **per-host process/runtime state** (anti-spam dedup memory:
  last-alert timestamps, last alert keys, giveback class), **not
  multi-tenant data**. It carries no `user_id`, no per-account ledger,
  no risk/NAV/campaign/stop math — moving or persisting it changes
  **zero** Phase-A surface and zero engine math.
- In a future multi-tenant world this dedup memory becomes
  **per-user** (each tenant has its own alert cadence), so the file
  would split per-user or move into a per-user keyspace. **That is
  out of Phase-A scope and requires no action now** — flagged here as
  a **Phase-B touchpoint** only (alongside PR-A5 state-file
  readers/writers, already deferred per `HYPERSCALER_PHASE_A_IMPL.md
  §2`; pre-condition: Research Issue N3 atomic-write fix). No code,
  no signature, no schema today.

## 3. A `docker-compose.yml` `volumes:` add is orchestration-only

`docker-compose.yml` already defines `volumes:` blocks on every service
and a top-level `volumes:` key; the `risk_monitor` service runs
`command: python risk_monitor.py`. If Mark rules a named/bind volume
must back the state file, that add:

- changes **no service `command:`** — `risk_monitor`'s
  `python risk_monitor.py` and `telegram-bot`'s
  `python3 telegram_bot_secure_runner.py` both stay verbatim
  (CLAUDE.md hard constraint; `secure_runner` untouched);
- is **container/storage orchestration only** — it changes *where the
  same bytes are stored across recreate*, not what any process does,
  not any Python module/import/signature, not the DB.

Net Phase-A delta of the compose change: **zero** — no schema, no
`user_id`, no resolver path; identical to the Sprint-13 finding that a
host-infra/orchestration change is Phase-A neutral
(`HYPERSCALER_SPRINT13_ADDENDUM.md §1`).

## 4. Zero billing / quota (DEC-20260515-005)

Sprint 14 introduces **no billing, payments, quota, rate-limit, tier,
or paywall** logic. Throttling/de-dup of *alerts* is trader-safety
noise control, not a usage quota or plan limit — it is unrelated to
the deferred billing surface. Closed free beta, invited users, no
public signup; billing stays deferred to Phase D.

## 5. Team-leads consolidation checklist (verify all 4)

1. **No schema / no migration / no `user_id`:** anti-spam state lives
   in `risk_monitor_state.json` (runtime file), not Supabase; no
   `ALTER`, no new column, no new `*.sql`; `verify_migrations.py`
   unchanged (ledger stays `005`); `risk_monitor.py` gains no `user_id`
   param or `user_context` import (PR-A3+ stays deferred).
2. **State file is per-host runtime, not multi-tenant data:**
   gitignore/move/volume-persist is Phase-A neutral (no `user_id`, no
   math); per-user split is a noted **Phase-B touchpoint only — no
   action now** (aligns with deferred PR-A5).
3. **Compose change is orchestration-only:** any `volumes:` add changes
   **no service `command:`**; `telegram_bot_secure_runner.py` and
   `python risk_monitor.py` untouched (CLAUDE.md hard constraint).
4. **Single-user byte-identical + zero billing:** fewer duplicate
   pushes only; the alert set per state is unchanged in content; real
   P0 escalations still fire (Mark-gated); no billing/quota/tier
   (DEC-20260515-005).
