# Sprint 24 — Plan: Quality Consolidation (behavior-preserving)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** DEC-20260516-021. Founder: "ישיבת צוות מלאה מפורטת — להפוך את הקיים לטוב/יעיל/נוח יותר, לא להוסיף".
**Structure:** Wave 1 (parallel, **DOC-ONLY audit**) → checkpoint → **founder picks the tier** → Wave 2 (execute only the chosen, Mark-gated subset) → consolidation.

## Mandate (strict)
NO new features. NO behavior change. NO math change. Make the EXISTING code better: remove duplication / dead code, improve reuse, efficiency, clarity, maintainability, operational convenience — the CLAUDE.md "Preferred refactor direction" (gradual extraction + tests per extraction; NEVER a giant rewrite).

## Hard constraints (whole sprint)
Byte-identical for ALL production-validated & locked paths (Sprint-22 tz fix; Sprint-23 probe split; LOCKED `test_real_data_april_regression.py`; 920be95/bcf32f5/Sprint-16..23; WS-B `unlinked_*`). No R/NAV/exposure/campaign/Expectancy math change. No admin/dev-PIN gate removal; no secure_runner bypass; no `telegram_bot.py` wholesale rewrite; no Supabase mutation from read-only flows. WS-C DEFERRED (incl. the logged `-1`-sentinel constraint — not touched here). No migration/compose/schema. Every accepted change test-backed + behavior-preserving. Baseline full suite **1879**.

## Wave 1 — full-team audit (parallel, DOC-ONLY, no code)
Each team delivers a prioritized table: `area · file:line evidence · problem · proposed behavior-preserving improvement · risk (low/med/high) · value · byte-identical proof strategy · tests needed`. Fragile-area items (engine_core, telegram_bot, NAV config, docker-compose) = **HIGH**, require explicit founder go-ahead.

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT24_RULINGS.md` — the BINDING definition of an *allowed* improvement here (behavior-preserving + byte-identical for every production-validated/locked path + test-backed + no math/feature/gate/secure_runner/wholesale-rewrite); the risk-classification rubric; the value/risk ranking method; the explicit "a quality sprint must NOT regress Sprint-22/23 or any locked path" invariant and how each Wave-2 item must prove byte-identical; what is OUT of scope (anything that changes a production-validated Telegram output's bytes — incl. the misleading ALGO "תקן entry/stop" wording — is a behavior change, NOT a cleanup, unless founder explicitly reclassifies); the Wave-2 pass/fail gate (suite ≥1879, all locked/validated paths byte-identical, per-item proof).
- **🏗️ Architecture:** `SPRINT24_ARCH_AUDIT.md` — structure audit: duplication (e.g. the multiple Telegram senders/splitters `main.send_telegram` / `risk_monitor.send_telegram` / `telegram_portfolio._send_long_message` / new `telegram_bot._send_probe_chunks`; repeated `pd.to_datetime`/numeric-coerce loops in `analytics_engine.py:30-33` vs `period_data_probe.py:164-168`; repeated period/tz helpers), dead/unused code, inconsistent patterns, module-boundary smells, and the concrete CLAUDE.md extraction candidates (Telegram formatting helpers / Supabase repository layer / portfolio report builder / risk-NAV config helper) — each as a SMALL gradual extraction with a byte-identical strategy. Risk-classified.
- **⚙️ Engine:** `SPRINT24_ENGINE_AUDIT.md` — math-bearing code (engine_core.py / analytics_engine.py) efficiency & clarity WITHOUT changing any result: redundant recomputation, repeated full-frame scans, the duplicated coerce/tz-normalize logic (could be ONE shared pure helper reused by the probe — byte-identical), unclear names/dead branches in the campaign-aggregation path. Every item MUST state its byte-identical proof (locked April regression + tz-aware==naive + full suite). HIGH risk by default (most-fragile per CLAUDE.md).
- **🚀 Hyperscaler:** `SPRINT24_OPS_AUDIT.md` (≤180 words) — operational efficiency, NO infra change: per-call `load_dotenv()`+`create_client()` in `_fetch_trades_df` (re-created every fetch), redundant Supabase round-trips, the `_fetch_trades_df` docstring "4-week" vs actual `weeks=8` lookback inconsistency (doc/clarity fix only), log noise/levels, import-time cost. No schema/migration/compose; verify_migrations stays 005.

## Checkpoint
Parent consolidates Wave-1 into ONE prioritized, risk-tiered menu (`SPRINT24_FINDINGS.md`): Tier-A (low-risk, high-value, byte-identical-trivial — e.g. dead code, doc fixes, safe dedupe), Tier-B (medium — shared-helper extractions with strong tests), Tier-C (high — fragile-area refactors, founder-gated). Independently verifies the cited `file:line` evidence is real and each "behavior-preserving" claim is plausible.

## Founder decision (after checkpoint)
Founder chooses which tier(s) Wave-2 executes (default recommendation: Tier-A only, then reassess). NO fragile-area edit without explicit founder go-ahead.

## Wave 2 (only the chosen subset)
Each item: small change + tests + byte-identical proof (locked regression + production-validated paths unchanged) + suite ≥1879. Consolidation doc + per-item proof.

## Carried
🟢 Smoke-test (Sprint 11–23) CLOSED. WS-C (DEFERRED; binding `-1`-sentinel constraint logged in DEC-020). NULL-`campaign_id` repair runbook (founder data task). Per-user Phase-B. ALGO Oversight Gate (DEC-20260515-014).
