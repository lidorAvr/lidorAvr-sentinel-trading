# Sprint 25 — Team-Leads Meeting (Consolidation): Production-Closure Deep Review (NO additions)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h`
**Wave-1:** DOC-ONLY, 8/8 teams, zero code. **Suite:** 1898 passed, 0 failed; CI-equivalent **independently re-verified GREEN on the committed tree** (Testing + Ops both ran the exact `pytest --cov … --cov-fail-under=67`).

Wave-1 commits: `3306361` Mark · `e6adbe2` Engine · `490f11e` Arch · `c139337` Security+Telegram · `a759bc2` Data · `33c1829` Testing · `01fc6e1` Ops.

## The headline finding (3 teams converged)

**The byte-lock family is INERT in CI.** Ops F1 + Testing P0-1/P0-2: every Sprint-19/22/23/24 "byte-identical" lock uses `git diff -- <file>` (working-tree vs **index**) → on a clean CI checkout the diff is **empty** → every assertion is **vacuously true**. The LOCKED April regression is "locked" by *narrative only* (no hash/AST guard) yet its fixtures feed 3 money-proofs. **The protection over the founder-reconciled money-math is not actually enforced where merges gate.** `1a9213a` fixed one symptom; the family is still commit-state-dependent. This is the single largest production-trust gap — and closing it is *pure byte-preserving test-infra polish* (no production behavior change).

## Cross-team convergence

- **Fallback-as-truth** (Telegram P0-1 + Data F1/F2 + Engine F3): NAV/price/NaN-pnl fallbacks silently presented as exact in the Telegram decision surface — CLAUDE.md #1 violation, 3 independent teams.
- **Dev-PIN gate not enforced** (Security S-1/2/3, P0): privileged dev handlers (Git Pull+Deploy `subprocess`, IBKR sync, XML upload→Supabase insert+NAV overwrite, config dump, on-demand) reachable by typing the persistent-keyboard button text with **no active PIN session**; `DEV_PIN` unset disables the gate.
- **Latent money-math divergence** (Engine F1+F2, P1): analytics keys SELL off `side`; adaptive_risk_engine + engine_core off `sign(quantity)` → on the DATA_CONTRACTS-documented positive-qty SELL, campaigns silently never close (wrong heat/streak/WR + drawdown-autocut can *raise* risk into a drawdown; phantom open positions distort NAV exposure).

## Tiered menu (per MARK_SPRINT25_RULINGS)

### Tier-A — pure byte-preserving polish (no behavior change, no addition; Mark-gated, agent-safe)
- **A1 CI/lock-integrity** (Ops F1 + Testing P0-1/P0-2/P1-1/P1-3): byte-locks compare committed `HEAD`; real hash/AST guard on the LOCKED April regression; anchor `test_secure_runner.py` to repo root; harden Sprint-19 anchors; bind proof *bodies* not just class names. **Highest value — makes the money-math protection real in CI.** Production code stays byte-identical (provable).
- **A2 dead-code + doc-drift** (Arch F5/F6, Security S-4, Data P2/P3): remove dead `/help` block + dead import + divergent coerce comment; correct the wrong `telegram_bot.py:147-153` gate anchor everywhere (incl. CLAUDE.md + MARK rulings); stale `verify_migrations` docstring; DATA_CONTRACTS clarifications.
- **A3 latent-flake** (Ops F4): fix the `_ssock`/`calc_fig` unraisable so the suite is deterministic.

### Tier-B — CLOSURE-FIX (wrong-vs-contract; founder decision; additive-disclosure, low risk)
- **B1 fallback-as-truth disclosure** (Telegram P0-1 + Data F1/F2): NAV/price source+freshness+fallback line in `build_summary_text` + the 0-closed/PDF-degraded Telegram path. Additive presentation; **zero `analytics_engine.py` change** (keeps Sprint-19 lock + Sprint-22 + LOCKED April byte-identical).
- **B2 primary-report length guard** (Telegram P1-1): apply the DEC-020 loss-free split to weekly/monthly summary so an over-limit report isn't silently swallowed.
- **B3 Supabase write-race** (Arch F3): persist planned `campaign_id` in Add-On pending state + guarded fallback (additive 1-key; byte-identical normal case).

### Tier-C — CLOSURE-FIX in fragile/safety areas (explicit per-item founder go-ahead)
- **C1 dev-PIN enforcement** (Security S-1/2/3): re-assert `dev_pin_session_active` over the privileged dev-handler region + fail-closed when `DEV_PIN` unset. `telegram_bot.py` (fragile) — but the most safety-critical (code-deploy / NAV-overwrite / Supabase-write without PIN).
- **C2 SELL/BUY classifier unification** (Engine F1+F2): one shared side-first classifier so positive-qty SELL closes campaigns in adaptive_risk_engine + engine_core. Fragile; provably byte-identical vs LOCKED April (its SELLs are negative-qty).

### OUT — ADDITION (flagged, not built)
Dashboard app-auth (Security S-12); NULL-pnl disclosure counter (Data F5); migration HTML-tag cleanup (migration edit OUT, Data P2 F4); WS-C / `-1`-sentinel (DEFERRED).

## Parent recommendation
**Tier-A in full** (pure polish, zero behavior risk, and A1 closes the single biggest production-trust gap — it is exactly "make the current code production-closed" with no additions). Then, of the CLOSURE-FIXes, the two most production-critical given CLAUDE.md hard constraints are **C1 (dev-PIN — real-money safety)** and **B1 (fallback-as-truth — decision honesty)**. B2/B3/C2 are strong but second-order. Founder chooses scope; no code until then.
