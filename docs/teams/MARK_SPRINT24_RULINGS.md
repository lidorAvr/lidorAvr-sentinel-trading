# MARK — Sprint-24 Rulings: Quality Consolidation (behavior-preserving) — BINDING + Wave-2 gate

**Owner:** Mark (methodology lead, Wave-2 gate). **Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Authority:** DEC-20260516-021 (this sprint); DEC-20260516-020 + PRODUCTION-VALIDATED
(Sprint-23 probe split, loss-free, the logged WS-C `-1`-sentinel constraint — **NOT**
addressed here); DEC-20260516-019 + UPDATE + RECONCILIATION COMPLETE (Sprint-22 tz fix,
reconciled EXACT vs raw Supabase); DEC-20260511-001 (#8 ALGO observer);
`AGENTS.md` (#1/#8, admin gate, no secure_runner bypass, no `telegram_bot.py` wholesale
rewrite, no secrets, no R/NAV/campaign math change without tests); `CLAUDE.md`
("Preferred refactor direction" — gradual extraction + tests per extraction, NEVER a
giant rewrite; "Most fragile areas"; "accuracy > confidence");
`docs/teams/SPRINT24_PLAN.md`. **Baseline full suite = 1879** (collected & confirmed).

This is a **quality** sprint. Nothing in it may change what the system *does* — only how
clearly/efficiently it does it. Wave-1 is DOC-ONLY. Wave-2 executes ONLY the
founder-chosen tier, each item Mark-gated against the gate in §6.

---

## Ruling 1 — Definition of an ALLOWED improvement (BINDING)

An improvement is admissible in Sprint-24 **only if ALL five hold**:

1. **Behavior-preserving** — no observable change to any output, number, message
   string, side-effect, ordering, or error/empty branch.
2. **Byte-identical for every production-validated / locked path** —
   the Sprint-22 tz fix (`analytics_engine.py:34+` single-point tz-normalization,
   DEC-019); the Sprint-23 probe split (loss-free, `telegram_bot.py` caller-side
   chunker + `period_data_probe.py` 100% untouched, DEC-020); the LOCKED
   `tests/test_real_data_april_regression.py` (8 campaigns / +$180.49 / WR .375 /
   PF 2.626 / excl 2); commits 920be95 / bcf32f5 / Sprint-16..23; WS-B `unlinked_*`.
3. **Test-backed** — a test (existing or new) demonstrates equivalence; "looks safe"
   is not a proof.
4. **A gradual extraction, NOT a rewrite** — per CLAUDE.md: extract one small shared
   helper / delete one dead block at a time, with tests per extraction. No bulk
   restructuring; no `telegram_bot.py` wholesale rewrite (AGENTS.md red line).
5. **Within the CLAUDE.md preferred direction** — Telegram formatting helpers,
   Supabase repository layer, portfolio report builder, risk/NAV config helper, dead
   code, duplicate-logic dedupe via a *provably identical* pure helper.

### Explicitly OUT of scope (a BEHAVIOR change, not a cleanup)

- **Any change to a production-validated Telegram output's bytes.** This explicitly
  includes the misleading ALGO "⚠️ stop לא תקין — תקן entry/stop" wording flagged in
  DEC-20260516-020 (PRODUCTION-VALIDATED §, pre-existing Sprint-21 behaviour, logged,
  NOT a regression). It reads as an improvement but it *changes a production-validated
  string* → it is a behavior change, **OUT** unless the founder explicitly reclassifies
  it as a separate fix outside this quality sprint.
- Any R / NAV / exposure / campaign-aggregation / Expectancy / PF / Win-Rate math
  change (AGENTS.md red line; CLAUDE.md hard constraint).
- Any new feature, flag, command, or alert.
- Any change to the admin/dev-PIN gate (`telegram_bot.py:147-153`), the secure_runner,
  `docker-compose.yml`, a DB migration, or the schema (`verify_migrations` stays 005).
- **WS-C stays DEFERRED**, including the logged `-1`-sentinel constraint
  (DEC-20260516-020 PRODUCTION-VALIDATED §) — not analysed, not touched.
- Any change to `period_data_probe.py` (Sprint-22 tz-mirror + Sprint-23 contract +
  READ-ONLY / no-secrets AST proof are all byte-locked).

---

## Ruling 2 — Risk-classification rubric (BINDING; assign to EVERY Wave-1 item)

- **LOW** — dead/unreachable code removal; comment/docstring correctness fix (e.g. the
  `_fetch_trades_df` "4-week" vs actual `weeks=8` docstring noted in the OPS audit
  scope — text-only); pure-internal dedupe whose byte-identity is *trivially* provable
  (literal-equal substitution, no signature/behaviour surface). No fragile-area file.
- **MEDIUM** — extraction of a *shared pure helper* used by ≥2 call-sites, where
  equivalence needs a real (but strong and complete) test argument — e.g. one shared
  coerce/`to_datetime` helper reused by `analytics_engine.py:29-32` and
  `period_data_probe.py:163-168` (duplication is real, evidence confirmed). Allowed
  ONLY if the helper is a *provable identity* vs the original inlined code AND it does
  not edit a fragile-area file's behaviour.
- **HIGH** — ANY edit inside a most-fragile area: `engine_core.py`,
  `telegram_bot.py`, NAV/account config, `docker-compose.yml` (CLAUDE.md "Most
  fragile areas"; AGENTS.md critical areas). HIGH items require **explicit founder
  go-ahead before Wave-2 touches them** (DEC-021 process). Default: not executed.

Note: a "shared helper" that *lives in* or is *imported into* a fragile-area module's
hot path inherits HIGH unless the extraction provably leaves that module's bytes
unchanged (e.g. helper added in a new module; fragile module unchanged).

---

## Ruling 3 — Byte-identical proof obligation (BINDING; per Wave-2 item)

Every Wave-2 item MUST carry an explicit, named proof of behavior-preservation. The
admissible proof forms are:

- **Dead-code removal:** static proof of unreachability (no caller / import-graph dead)
  + full suite unchanged at 1879.
- **Comment/docstring-only:** diff touches only comment/string-doc bytes, zero
  executable bytes; full suite unchanged.
- **Shared pure-helper extraction:** the extracted function is a *provable identity*
  vs the original inlined code (same inputs → same outputs, same exception behaviour,
  same dtype/tz handling — especially the tz-naive/tz-aware coerce path which is
  Sprint-22-load-bearing), demonstrated by: (a) the LOCKED April regression
  byte-identical; (b) tz-aware bounds == tz-naive bounds == 8/+$180.49 (DEC-019
  invariant) where the helper touches the analytics/probe coerce path; (c) the
  Sprint-23 probe split still loss-free (concatenated parts == single-string oracle)
  where Telegram delivery is in scope; (d) the full suite all-unchanged.
- **No item may rely on "no test failed" alone** — it must name *which* validated path
  its proof covers.

---

## Ruling 4 — The "do no harm" invariant (OVERRIDING gate)

A quality sprint that regresses **ANY** Sprint-22 behaviour, **ANY** Sprint-23
behaviour, or **ANY** locked path is an **automatic, non-negotiable FAIL** — this
overrides every value/efficiency/clarity argument. Concretely, an automatic FAIL if:
the LOCKED April regression is not byte-identical; the Sprint-22 tz-aware==tz-naive
numbers move by any amount; the Sprint-23 probe is not loss-free or not 3 plain-text
RTL parts of the same content; any engine/analytics headline number changes; the
admin/dev-PIN gate, secure_runner, compose, or a migration changes; or WS-C is touched.
There is no "small acceptable regression" in a behavior-preserving sprint.

---

## Ruling 5 — Prioritization method (value ÷ risk) + tiering (BINDING)

Rank every Wave-1 candidate by **value ÷ risk**, then the parent consolidates into:

- **Tier-A** — LOW risk, high value, byte-identity trivial (dead code, doc/comment
  fixes, literal-safe dedupe). Highest value/risk.
- **Tier-B** — MEDIUM risk (shared-pure-helper extractions with strong, complete
  tests). Admissible only with a Ruling-3 identity proof.
- **Tier-C** — HIGH risk (fragile-area refactors: engine_core / telegram_bot / NAV
  config / compose). Founder-gated; never executed without explicit go-ahead.

**Default recommended Wave-2 scope: Tier-A ONLY, then reassess.** Tier-B only if the
founder opts in after the checkpoint; Tier-C only with explicit per-item founder
go-ahead. This matches DEC-021 ("default recommendation: Tier-A only, then reassess")
and CLAUDE.md gradualism.

---

## Ruling 6 — Wave-2 pass/fail checklist (BINDING GATE — ALL 10 must pass)

A Wave-2 deliverable PASSES only if **every** item is true; any single failure = the
whole Wave-2 FAILS (Ruling 4):

1. Full suite **≥ 1879** passed (no deletions to make it green; new tests only add).
2. LOCKED `tests/test_real_data_april_regression.py` **byte-identical** (8 / +$180.49 /
   WR .375 / PF 2.626 / excl 2 unchanged).
3. Sprint-22 tz numbers unchanged: tz-aware bounds == tz-naive == April 8/+$180.49 and
   weekly 0/excl-3 (DEC-019 invariant).
4. Sprint-23 probe still **loss-free**: concatenated sent parts == single-string
   oracle, same 3 plain-text RTL parts, `period_data_probe.py` byte-identical.
5. **No engine/analytics math diff** — no R/NAV/exposure/campaign/Expectancy/PF/WR
   value changes anywhere.
6. No change to the admin/dev-PIN gate, secure_runner, `docker-compose.yml`, any
   migration, or the schema (`verify_migrations` == 005).
7. Each shipped item is **test-backed AND carries a named Ruling-3 proof**.
8. No `telegram_bot.py` wholesale rewrite (AGENTS.md red line); changes there, if any,
   are small additive and founder-approved (Tier-C).
9. **WS-C untouched** — including the logged `-1`-sentinel constraint; the misleading
   ALGO "תקן entry/stop" string unchanged (OUT per Ruling 1).
10. Fragile-area (engine_core / telegram_bot / NAV config / compose) items appear in
    the diff **only if the founder explicitly approved that specific item**.

---

## Closing direction

Wave-1 teams: deliver DOC-ONLY tables with real `file:line` evidence, a Ruling-2 risk
tag, and a Ruling-3 proof strategy per row — no code. The single best, lowest-risk
consolidation here is the confirmed shared coerce/`to_datetime` duplication
(`analytics_engine.py:29-32` ≅ `period_data_probe.py:163-168`) — but it sits on the
Sprint-22 tz-load-bearing path, so it is **MEDIUM at best and only admissible with a
full identity proof**, not a Tier-A freebie. When unsure whether a change is "cleanup"
or "behavior", it is **behavior** — accuracy over confidence (CLAUDE.md). The default
Wave-2 recommendation stands: **Tier-A only, then reassess.**
