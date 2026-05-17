# MARK — Sprint-25 Rulings: Production-Closure Polish (NO additions) — BINDING + Wave-2 gate

**Owner:** Mark (methodology & gate lead, Wave-2 gate). **Date:** 2026-05-17
**Branch:** continues the Sprint-24 line (`claude/review-system-audit-FBZ2h` lineage).
**Authority chain:** founder mandate (verbatim intent: a deep ALL-TEAMS review so the
CURRENT code is **100% production-closed** — a finishing/hardening pass, **NO new
features/additions**, only closing gaps and polishing what already exists);
DEC-20260516-021 + **Wave-2b** (Sprint-19 byte-lock governed-expansion precedent, B1/B3
landed as proven no-ops, founder "stop here" — i.e. Sprint-24 is closed, Sprint-25 is a
NEW founder-mandated wave, not a reopen of 24); DEC-20260516-020 + PRODUCTION-VALIDATED
(Sprint-23 probe split loss-free; the logged WS-C `-1`-sentinel constraint; the
pre-existing misleading ALGO "⚠️ stop לא תקין — תקן entry/stop" string — logged, NOT a
regression); DEC-20260516-019 + UPDATE + RECONCILIATION COMPLETE (Sprint-22 tz fix,
reconciled EXACT vs raw Supabase); `CLAUDE.md` (hard constraints, "Most fragile areas",
"accuracy > confidence", fallback/stale honesty); `AGENTS.md` (#1/#8, admin gate, no
secure_runner bypass, no `telegram_bot.py` wholesale rewrite, no secrets, no R/NAV/
campaign math without tests); `docs/SAFE_CHANGE_PROTOCOL.md`; `docs/DATA_CONTRACTS.md`;
`docs/TESTING_AND_DEPLOYMENT.md`; `.github/workflows/tests.yml`.

**Baseline full suite = 1898 passed, 0 failed** (DEC-021 Wave-2b verified).
**CI-equivalent command (BINDING reference):**
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-report=term --cov-fail-under=67`
with the CI env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_ID`, `SUPABASE_URL`,
`SUPABASE_KEY`, `DEV_PIN` set to the workflow's CI dummy values).

This sprint is a **finishing/hardening pass on existing code**. Its purpose is to make
the system *demonstrably* production-closed — not to grow it. Wave-1 is DOC-ONLY (this
ruling + the team audits). Wave-2 executes ONLY the founder-chosen tier, each item
Mark-gated against §5.

---

## Ruling 1 — Definition of "100% production-closed" (BINDING, checkable)

The CURRENT code is "100% production-closed" only if **every** criterion below is
objectively verifiable on the **committed, clean** tree (not a dirty worktree — §5.B):

1. **Money-affecting math is correct vs its own contract.** R, NAV, exposure,
   campaign aggregation, Expectancy, PF, Win-Rate, Net-R produce the
   contract-specified result for in-contract inputs. The DEC-019 reconciliation
   (April 10 / +$336 / +11.01R / PF 4.03 / WR 50% / 10 ALGO $+218 observe-only) and
   the LOCKED fixture (8 / +$180.49 / WR .375 / PF 2.626 / excl 2) both still hold.
2. **Fallback / stale / cached honesty (CLAUDE.md, DATA_CONTRACTS §"Core principle").**
   No user-facing path presents fallback/cached/default/estimated/incomplete data as
   exact truth. Every risk-sensitive report that *can* use a fallback discloses it.
3. **Admin gate + secure_runner intact.** `telegram_bot.py:241-247` admin/dev-PIN
   gate present (the `🛠️ מפתח` menu-open
   `dev_pin_is_configured()`/`dev_pin_session_active(chat_id)` check —
   Sprint-25 A2/S-4 corrected anchor: the prior "147-153" cite was WRONG;
   those lines are the `_send_probe_chunks` message-split loop, not a
   gate); `docker-compose.yml` Telegram service = `python3
   telegram_bot_secure_runner.py`; anti-spam/rate-limit/cooldown present.
4. **Secrets hygiene.** No token/credential/account number/PIN committed; tokens never
   appear in logs or returned dicts (`ibkr_sync_runner` rule).
5. **CI parity & green.** The CI-equivalent command above is GREEN on the committed
   tree, including `--cov-fail-under=67`. Local `pytest -q` parity confirmed.
6. **Locked-path integrity.** All carried byte-locked paths (Ruling 3) are
   git-diff-EMPTY / byte-identical on the committed tree.
7. **Data-contract conformance.** stat_bucket, management_mode, risk_basis,
   risk_visibility_score, alert-key, Giveback-zone, Sizing-Leak, Daily-Digest, NAV,
   Supabase-write contracts hold as written in `DATA_CONTRACTS.md`.
8. **No silent-zero / silent all-False.** No comparison/aggregation can yield a
   silent `0`/all-False that *looks like* a real result (the DEC-019 tz class of
   defect); honest zeros must be distinguishable from defective zeros.
9. **Test reliability.** No flaky/order-dependent test; **no test that depends on
   working-tree-vs-index `git diff` state passing only on a dirty/clean tree
   inconsistently** (the Sprint-24 byte-lock family is committed-tree-correct — it
   MUST stay correct post-commit; see §5.B). No test deleted/weakened to go green.

Any criterion failing ⇒ NOT production-closed ⇒ a P0 or P1 finding (§4), classified
as polish / CLOSURE-FIX / ADDITION per Ruling 2.

---

## Ruling 2 — The "polish, no additions" boundary (BINDING)

Every Wave-1 finding gets exactly one tag:

### ADMISSIBLE — "polish" (in scope)
- **Pure byte-preserving polish:** dead/unreachable-code removal; comment/docstring
  correctness fix; provably-identical internal dedupe; test-reliability fix that
  changes no production byte; CI hardening (e.g. making the CI check run on the
  committed tree); doc/contract-text correction. No observable behavior change.
- **Bug fix where existing behavior is wrong vs ITS OWN contract** — but see the
  crucial nuance below: this is a *behavior change* and is **NOT** pure polish.

### CLOSURE-FIX (founder-decision-required) — admissible ONLY with explicit founder go-ahead
A finding where the production behavior is **genuinely wrong vs its own
documented/intended contract**, so fixing it is exactly the "production closure" the
founder wants — but the fix **changes observable production behavior** (bytes,
numbers, a string, a branch). This is distinct from byte-preserving polish and from an
ADDITION. It MUST be:
- classified explicitly as **CLOSURE-FIX (founder-decision-required)**;
- presented with the exact contract it violates, the precise diff of behavior, and a
  named regression proof;
- **never shipped unilaterally** — only on explicit per-item founder go-ahead
  (Tier-B, §6).
Rationale: "when unsure whether a change is cleanup or behavior, it is behavior;
accuracy over confidence" (CLAUDE.md / Sprint-24 Ruling 1). A genuinely-wrong
behavior may be the whole point of "production closure" — but the founder, not the
agent, decides to change production behavior.

### OUT — an ADDITION (flagged, never built)
Any **new** feature, flag, command, alert, endpoint, metric, report, config key,
schema field, or new user-facing capability — even a "small/obvious/useful" one.
Additions are **OUT of Sprint-25 entirely**: they may be *flagged* in the audit as
future backlog, but **never built** this sprint. A helper that adds capability (vs
de-duplicating provably-identical existing logic) is an ADDITION.

### Boundary edge calls (BINDING)
- Hardening that changes no observable behavior (e.g. a defensive guard that can never
  fire on in-contract inputs, proven) = **polish**. A guard that *changes* an
  out-of-contract result = **CLOSURE-FIX**.
- The misleading ALGO "⚠️ stop לא תקין — תקן entry/stop" string is a production
  behavior on a validated path → changing it is a **CLOSURE-FIX
  (founder-decision-required)**. Sprint-25 may **RECOMMEND** the closure-fix with a
  proof strategy; it may **NOT** unilaterally change it (carried OUT per Sprint-24
  Ruling 1; reaffirmed §3).
- WS-C and the `-1`-sentinel question stay **DEFERRED** (not analysed, not touched) —
  reopening them is an ADDITION-class scope expansion, OUT.

---

## Ruling 3 — Carried invariants (STILL BINDING)

Unchanged and overriding. A Wave-2 deliverable that regresses ANY of these = automatic
non-negotiable FAIL (§5, Ruling 4 of every prior sprint, reaffirmed):

1. **Sprint-22 tz numbers:** tz-aware bounds == tz-naive bounds == April
   8/+$180.49/WR .375/PF 2.626/excl 2; weekly 0 discretionary / excl 3 ALGO. The
   single-point tz-normalization in `analytics_engine.py` is load-bearing — strip-tz
   direction only, no math change.
2. **Sprint-23 probe:** loss-free (chunk, never truncate — #1); same plain-text RTL
   multi-part shape; **`period_data_probe.py` byte-locked** (Sprint-22 tz-mirror +
   READ-ONLY + no-secrets AST proof byte-identical).
3. **LOCKED `tests/test_real_data_april_regression.py`** byte-identical
   (8 / +$180.49 / WR .375 / PF 2.626 / excl 2) — not edited, not re-asserted.
4. **Sprint-24 Wave-2b:** B1 (`_cnt` hoist) + B3 (`_coerce_numeric`) stay as the
   proven byte-identical no-ops; the **expanded Sprint-19 byte-lock**
   (`tests/test_sprint19_headline_comparison.py::test_analytics_engine_git_diff_empty`
   with `_SPRINT24_AUTHORIZED_REMOVED`/`_SPRINT24_AUTHORIZED` closed literal sets +
   self-reference hardening) and its **paired proof**
   (`tests/test_sprint24_b1b3_byte_identical.py::TestSprint24B1B3ByteIdentical`) are
   both BINDING and byte-locked. No existing Sprint-20/21/22 lock clause may be
   modified. Any further `analytics_engine.py` edit MUST be additive or go through the
   SAME governed, Mark-gated, founder-authorized lock-expansion ritual (NOT relaxed to
   go green).
5. **No R / NAV / exposure / campaign-aggregation / Expectancy / PF / Win-Rate / Net-R
   math change without a named regression proof** (AGENTS.md red line; CLAUDE.md hard
   constraint). #8 ALGO segregation (no ALGO/DATA_INCOMPLETE in WR/Expectancy)
   inviolable.
6. **No change to** the admin/dev-PIN gate, `telegram_bot_secure_runner.py`,
   `docker-compose.yml`, any DB migration, or the schema (`verify_migrations` == 005)
   **without explicit founder go-ahead**.
7. **`engine_core.py` is the most-fragile area;** **no `telegram_bot.py` wholesale
   rewrite** (AGENTS.md red line) — narrow additive only, founder-gated.
8. **WS-C and the `-1`-sentinel constraint DEFERRED;** the misleading ALGO "תקן
   entry/stop" string is logged (Sprint-24 OUT) — Sprint-25 may RECOMMEND a
   closure-fix but may NOT unilaterally change it.
9. Preserve commits 920be95 / bcf32f5 / Sprint-16..24 byte-stable invariants and the
   WS-B `unlinked_*` block.

---

## Ruling 4 — Severity rubric (BINDING; assign to EVERY Wave-1 finding)

- **P0** — blocks production / a correctness or safety risk: a money-affecting math
  error vs contract; a secret committed; admin gate or secure_runner bypassable; a
  silent-zero/all-False that misrepresents truth; a fallback shown as exact truth on a
  risk-sensitive path; CI red on the committed tree.
- **P1** — production-quality gap: a contract violation that does not (yet) corrupt a
  headline number; a test that passes only on a dirty/clean tree inconsistently; a
  missing fallback disclosure on a lower-risk path; CI parity ambiguity.
- **P2** — robustness/maintainability: dead code, real provable duplication,
  defensive-guard gaps that cannot fire on in-contract inputs.
- **P3** — nit: comment/docstring drift, naming, cosmetic.

**Every finding row MUST carry:** `severity (P0–P3)` + `value÷risk` +
`tag {polish | CLOSURE-FIX(founder) | ADDITION-OUT}` + a **named proof strategy**
(which validated path the proof covers — "no test failed" alone is NEVER a proof;
reuse the Sprint-24 Ruling-3 proof forms).

---

## Ruling 5 — Wave-2 pass/fail GATE checklist (BINDING — ALL must pass)

A Wave-2 deliverable PASSES only if **every** item is true; any single failure ⇒ the
whole Wave-2 FAILS (no "small acceptable regression" in a closure/polish sprint):

**A. Suite & proof**
1. Full suite **≥ 1898** passed, 0 failed — **no test deleted or weakened to go
   green**; new tests only add.
2. **CI-equivalent command GREEN** (`pytest … --cov-fail-under=67` + CI env) — and
   verified on the **COMMITTED, clean tree**, not a dirty worktree.
3. Each shipped item is **test-backed AND carries a named proof** covering the
   specific validated path it touches.

**B. The Sprint-24 CI-miss lesson (BINDING verification method)**
4. Because the byte-lock family asserts on **working-tree-vs-index `git diff`**, a
   green run on a *dirty* tree does NOT prove the committed state is green. Wave-2
   verification MUST: commit the change, then run the full suite + CI-equivalent
   command **on the clean committed tree** (`git status` clean), and re-run the
   byte-lock tests there. A pre-commit-only green is insufficient evidence.

**C. Carried locked paths byte-identical (Ruling 3)**
5. `tests/test_real_data_april_regression.py`, `period_data_probe.py`,
   `engine_core.py`, `docker-compose.yml`, the Sprint-19 lock + its Sprint-24 paired
   proof — all git-diff EMPTY / byte-identical on the committed tree.
6. Sprint-22 tz numbers unchanged; Sprint-23 probe loss-free & same shape; no
   R/NAV/exposure/campaign/Expectancy/PF/WR/Net-R value change anywhere.
7. No admin/dev-PIN gate, secure_runner, compose, migration, or schema change unless
   the founder explicitly approved that specific item.

**D. No additions; behavior changes only by explicit gate**
8. **No ADDITION shipped** (no new feature/flag/command/alert/endpoint/metric).
9. Every behavior-changing item in the diff is a **CLOSURE-FIX with explicit per-item
   founder go-ahead** and a named regression proof — never a unilateral change.
10. `telegram_bot.py`: no wholesale rewrite; any change small additive +
    founder-approved. WS-C / `-1`-sentinel / the ALGO "תקן entry/stop" string
    untouched (RECOMMEND-only).

---

## Ruling 6 — Tiering method + default recommendation (BINDING)

Rank every Wave-1 finding by **value ÷ risk**, then the parent consolidates into:

- **Tier-A — pure-safe polish.** LOW risk, byte-preserving: dead-code removal,
  comment/doc/contract-text correction, provably-identical dedupe,
  test-reliability/CI-hardening fixes that change zero production bytes. Byte-identity
  trivially or strongly provable; no fragile-area behavior change. Highest value/risk.
- **Tier-B — CLOSURE-FIX (founder-gated).** A genuinely-wrong-vs-contract production
  behavior whose fix changes observable behavior. Admissible **only** with explicit
  per-item founder go-ahead + a named regression proof. The misleading ALGO string and
  any "honest zero vs silent zero" hardening with an output delta live here.
- **Tier-C — fragile-area (founder-gated).** ANY edit inside `engine_core.py`,
  `telegram_bot.py`, NAV/account config, `docker-compose.yml`, secure_runner, the
  admin gate, a migration/schema, or the Sprint-19/Sprint-24 lock family. Never
  executed without explicit per-item founder go-ahead; lock-family edits additionally
  require the governed Mark-gated expansion ritual (Sprint-24 Wave-2b precedent).

**Default recommended Wave-2 scope: Tier-A ONLY, then reassess.** Tier-B only if the
founder opts in per-item after the checkpoint; Tier-C only with explicit per-item
founder go-ahead. This matches CLAUDE.md gradualism and the Sprint-24 default. A
"production-closed" sprint closes gaps with the *least* behavior risk first; genuine
CLOSURE-FIXes are surfaced and recommended, not smuggled in as "polish".

---

## Closing direction

Wave-1 teams: deliver DOC-ONLY tables with real `file:line` evidence, a Ruling-4
severity + value÷risk + polish/CLOSURE-FIX/ADDITION tag + a named proof strategy per
row — **no code**. The single biggest methodological risk this sprint is the
**polish↔CLOSURE-FIX boundary**: a genuinely-wrong production behavior (e.g. the
misleading ALGO string, or any latent silent-zero) is *exactly* what "100%
production-closed" should fix — but fixing it is a behavior change the founder must
authorize, not the agent. Default stands: **Tier-A only, then reassess; CLOSURE-FIXes
RECOMMENDED, never unilateral; additions flagged, never built.** When unsure whether a
finding is polish or behavior, it is **behavior** — accuracy over confidence
(CLAUDE.md).
