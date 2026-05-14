<!-- Sprint 7 #5: standardize PR hand-off to prevent the Sprint 6 incident class -->

## Summary

<!-- 1-3 sentences. What changes, and what user-visible problem does it solve. -->


## Test Plan

- [ ] `pytest --tb=short -q` — **N passed, 0 failures**
- [ ] Coverage gate `--cov-fail-under=67` passes (run locally first)
- [ ] New tests added for the change (or rationale why none)
- [ ] Manual smoke test on Telegram bot (or rationale why N/A)

## Hard constraints (per `CLAUDE.md`)

- [ ] Telegram admin protection unchanged
- [ ] `telegram_bot_secure_runner.py` still the production entrypoint
- [ ] No silent fallbacks — every fallback path sends an alert or logs explicitly
- [ ] Math changes have tests
- [ ] No Supabase mutations from read-only flows
- [ ] No wholesale rewrite of `telegram_bot.py`

## Network / external deps

- [ ] No new test reaches a public host (pytest-socket blocks this — if your test fails with `SocketBlockedError`, add a mock)
- [ ] Production network calls (yfinance, Supabase, Telegram) still have fail-open paths
- [ ] No new `except Exception: pass` patterns

## Migrations / human action required

<!-- If this PR includes a Supabase migration or other operator action, list it here.
     Compliance check: every merged migration must be applied in production. -->

- [ ] No migration in this PR  
  OR
- [ ] Migration: `migrations/<filename>.sql` — operator must apply in Supabase SQL Editor after merge
  - [ ] Verified with `python3 migrations/verify_migrations.py` post-apply
  - [ ] `bot_health` check turns green for the new table

## Risk classification

<!-- Per CLAUDE.md "Safe development approach" — classify before merging. -->

- [ ] **Low**: docs, tests, formatting, comments
- [ ] **Medium**: new feature, isolated module, doesn't change R/NAV/exposure math
- [ ] **High**: changes R/NAV/exposure math, modifies `telegram_bot.py` workflows, alters production wiring, schema migration

---

<!-- DO NOT EDIT BELOW THIS LINE -->
🤖 Generated/reviewed with Claude Code
