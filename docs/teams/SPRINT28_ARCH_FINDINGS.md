# Sprint-28 — Architecture 100/100 Structural-Health Re-Review (DOC-ONLY)

**Date:** 2026-05-18 · **Team:** 🏗️ Architecture (lead) · **Mode:** verification
only — NO code, NO commit, NO features, NO rewrites.
**Live state:** branch HEAD = **`168aaa2`** ("feat(sprint-27): execute
Sprint-26 findings — dashboard honesty, repo-hygiene, companion voice,
housekeeping"). Working tree clean. This is a re-run of the Sprint-26
96/100 review on the **post-Sprint-27** as-built tree, every claim
re-verified by direct `file:line` re-read on disk + a live CI-equivalent run.

> **Scope note (honest):** the Sprint-27 IMPL docs cited a `main` `c761967`
> baseline. `c761967` is still not a resolvable object in this repo (same as
> the Sprint-26 note). It is a cross-repo/upstream ref and does not affect this
> review — anchored strictly to the actual live HEAD `168aaa2`.

---

## Verdict

**Score: 99/100. Sprint-27 KEPT THE STRUCTURE CLEAN — and improved it.**
Sprint-27 closed the two structural items Sprint-26 was tracking (S26-R1 and
S26-R4) with minimal, well-bounded, additive changes. **No new fragile
coupling, no logic duplication, no dead code introduced.** No byte-locked file
was touched. The remaining 1 point is a single LOW test-suite-hygiene
fragility that Sprint-27 newly *aggravated* (it does not affect production
code or the authoritative CI gate).

**S26-R1 closed? → YES.** **S26-R4 closed? → YES (repo side).**

---

## S26-R1 — CLOSED (verified in source)

`telegram_bot.py` now has **zero** raw `.table(` data reads. The only textual
match (`telegram_bot.py:879`) is *inside the W4c explanatory comment*. The
actual open-position load in `_handle_addon_command` is:

```python
df = pd.DataFrame(repo.get_all_trades(supabase))     # telegram_bot.py:886
```

- **Clean module-boundary fix, no new coupling.** `repo` is the
  *already-imported* `import supabase_repository as repo`
  (`telegram_bot.py:10`) — **no new import, no new dependency edge**. `supabase`
  is the existing `bot_core` client. One-line swap; `_handle_addon_command`,
  the C1 `_require_active_dev_session` guard, the admin/secure-runner gate, and
  the B3 `_planned_cid` persistence are byte-unchanged (diff is +23/−? on
  `telegram_bot.py`, all inside the comment + the one swapped line + the
  humanized C1 string — no wholesale rewrite, CLAUDE.md #6 honored).
- **Byte-identical result.** `supabase_repository.get_all_trades(sb)`
  (`supabase_repository.py:22-23`) issues the identical
  `sb.table("trades").select("*").execute().data or []`. The only delta vs the
  old inline `res.data` is `.data → .data or []`; `pd.DataFrame(None)` and
  `pd.DataFrame([])` are `.equals()` so the consumed DataFrame is identical for
  every result shape (non-empty / `[]` / `None`). Pinned by
  `tests/test_sprint27_w4c_repo_parity.py` (8 tests, green).
- This residual survived Sprint-24→26 untouched; it is now structurally
  consistent with **every other** Supabase read in the file. The CLAUDE.md
  "extract Supabase repository layer" direction is now fully realized for
  `telegram_bot.py`.

---

## What was VERIFIED sound (the 99)

### A. New `dashboard_nav.py` helper — clean, pure, well-bounded
- 66 lines, **stdlib-only** (`from typing import Tuple` — nothing else; no
  streamlit, no engine, no account_state import). It is a true leaf, the
  cleanest possible extraction, unit-testable in isolation exactly like B1's
  `report_renderer._nav_disclosure_lines`. **No new coupling introduced.**
- `dashboard.py` integration (`:14-15` imports, `:111-118` render site) reads
  the **canonical** `account_state.load()` and routes through the helper,
  *replacing* the old divergent bare-`except` `load_settings` path for the
  prominent green box (closes Data D-F1 single-source divergence). The broker-
  fresh happy path is **byte-identical** (asserted byte-for-byte in
  `tests/test_sprint27_w1_dashboard_nav_honesty.py`, 24 tests). Zero KPI/math.
- **No dead code:** the old `load_settings` is still legitimately used
  elsewhere (`dashboard.py:55,61`) for the write-back/migration path; only the
  prominent NAV figure was rerouted. Not orphaned.

### B. Companion-voice additions — additive, zero-math, well-bounded
- **`report_renderer.whatnow_line`** (`:241-263`): composed ONLY from the
  EXISTING `compute_verdict` return (capture widened `verdict,_` →
  `verdict,verdict_class` — semantics untouched) + the existing `period_type`
  param + the B1 broker-fresh signal. Prepended; body byte-identical
  (`test_sprint25_b1_fallback_disclosure.py` frozen-literal pin updated, not
  weakened).
- **`telegram_portfolio.handle_portfolio_room`** (`:272,540-554`):
  `decision_syms` collected *during the existing loop* from the
  already-computed engine `status` — no new computation/data source; line
  prepended, `msg` body byte-identical. Empty-state disambiguation at `:245`.
- **`risk_monitor._daily_digest_text`** (`:439-475`): the `urgent` derivation
  was hoisted from inside-loop to a list-comp before it — **provably
  byte-identical**: identical `state ∈ (BROKEN,RUNNER,PROFIT_PROTECTION)`
  predicate, identical order, the per-row bullets and the `if urgent:` footer
  block are textually unchanged. Clean refactor, not a behavior change.
- Humanized C1/B3 strings: routing/return/zero-write security semantics
  byte-unchanged (verified in `telegram_bot.py` + `telegram_callbacks.py`
  diff); only user-facing wording warmed, still 100% honest.

### C. One bounded-duplication observation (NOT a defect — recorded)
The broker-fresh gate (`nav_source=="broker" and freshness=="fresh" and not
is_stale and ok`) is now spelled out in **three** sites:
`report_renderer._nav_disclosure_lines` (B1), `report_renderer._account_state_
broker_fresh` (W3), `dashboard_nav.nav_sidebar_render` (W1). This is a 4-term
boolean copied 3×, NOT a logic fork — each is independently test-pinned and
all three are byte-identical today. It is **acceptable bounded duplication**
(the alternative — a shared predicate import — would add a new coupling edge
into a pure leaf, which is worse for a 4-term constant). **Record-only**: if a
*fourth* site appears, extract a single `account_state.is_broker_fresh(acc)`
canonical predicate (additive, account_state is the natural owner). Not
actionable now; flagged so it cannot silently drift.

### D. Byte-lock machinery — SOUND and UNTOUCHED
- `tests/_byte_lock_baseline.py` last modified Sprint-25 (`b7fb1bf`) — **not
  touched by Sprint-27**. `git diff HEAD` empty for `engine_core.py`,
  `analytics_engine.py`, `period_data_probe.py`,
  `tests/_byte_lock_baselines/*`, LOCKED
  `tests/test_real_data_april_regression.py`.
- **Live integrity re-verified NOW:** `sha256sum` of `engine_core.py`,
  `analytics_engine.py`, `period_data_probe.py` each **MATCHES** its committed
  `.baseline`. The Sprint-27 commit touched no byte-locked file (full
  `--stat` confirms: source edits limited to dashboard/report_renderer/
  risk_monitor/telegram_*/dashboard_nav + tests + docs). Machinery sound.

### E. W2 untrack — structurally clean
`git ls-files` no longer lists `sentinel_config.json` (commit shows `−1`);
`.gitignore:3` still lists it (now *bites*, since the file is finally
untracked); a tracked `sentinel_config.example.json` template was added so
fresh clones still get a shape. **S26-R4 (the stale-NAV-on-pull data-loss
class) is closed on the repo side.** The host-safety step is correctly
documented as founder-only in `docs/DEPLOYMENT_RUNBOOK.md` (cannot be done by
the agent; a botched untrack-pull is the very fault being prevented).

---

## Structural risk (the −1)

### S28-R1 · LOW · Test-collection-order contamination newly aggravated
Running the new Sprint-27 W1/W3/W4c test files **in the same process before**
`test_sprint25_b1_fallback_disclosure.py` makes **4 B1 tests fail**
(`TestDegradedAndOnDemandCarryToken` ×3, `TestLockedAprilByteIdentical` ×1)
via shared-module state leakage in the dirty multi-file process.
**Proven NOT a production regression:** the B1 file passes **17/17 in
isolation**, and the **authoritative CI-equivalent command (default ordering)
passes 2088/0 at 72.02% coverage** — re-run live in this review, GREEN. The
W1 IMPL doc already disclosed an order-sensitivity here but attributed it to a
*pre-existing* B1 fixture; in fact the new Sprint-27 test modules **widen the
trigger surface** (more shared-module mocking). The risk is
**test-suite-hygiene / false-confidence**, not data/behavior: a future
unrelated reordering (or a `-p no:cacheprovider` CI variant) could turn a real
B1 regression invisible or surface a phantom failure.
**Severity:** LOW (CI gate is green on the authoritative command; production
code byte-identical). **Recommended future fix (governed, test-only,
additive):** make the Sprint-27 + B1 modules import-isolate their Supabase/
account_state mocks per-test (fixture-scoped, no module-global mutation) so
collection order can never change the result. Test-only, net-count-neutral,
mirrors the W4b self-containment precedent. **Not done here (DOC-only).**

### Carried-forward record-only debts (UNCHANGED from Sprint-26)
- **S26-R2** `analytics_engine` "never raises" contract leak (byte-locked →
  Mark-gated allowlist expansion only). NAV-Unify still reduces likelihood.
- **S26-R3** `_coerce_numeric` 3-way drift + ~21 bare `except:` (Engine-owned
  / byte-locked / accepted long-standing debt). Note: Sprint-27 added **no new
  bare `except:`** on a money path — `dashboard_nav` is exception-free, the
  dashboard reroute *removed* reliance on the old bare-`except` for the
  prominent figure.
None of these were closable this sprint and none were worsened.

---

## למנכ״ל — בשפה פשוטה

**האם המערכת עדיין בנויה חזק, והאם השינויים של אתמול שמרו עליה נקייה? כן — ואף
שיפרו. הציון עלה ל-99/100.**

- **הסיכון המבני העיקרי שנשאר מאתמול — נסגר.** הקריאה הישירה היחידה ל-Supabase
  ב-`telegram_bot.py` (שורה 872 בעבר) עוברת עכשיו דרך שכבת ה-DB המסודרת. שורה
  אחת, בלי import חדש, בלי צימוד חדש, אותה תוצאה בדיוק — מאומת בטסטים.
- **חוב הקונפיג נסגר בצד הקוד.** `sentinel_config.json` כבר לא נעקב ב-git, כך
  שעכשיו ה-gitignore באמת חוסם — `git pull` לא יכול יותר להחזיר NAV ישן.
  נוספה תבנית `sentinel_config.example.json`. נשאר רק צעד אחד בטיחותי בשרת
  שהוא באחריות המייסד (מתועד ב-runbook).
- **התוספות החדשות נקיות.** קובץ העזר החדש `dashboard_nav.py` הוא "עלה" טהור
  (בלי תלות בכלום), שורות ה-"מה עכשיו?" הן תצוגה בלבד (אפס מתמטיקה, המספרים
  זהים בית-בבית), והשכתוב הקטן ב-risk_monitor מוכח זהה לחלוטין. אין קוד מת,
  אין כפילות לוגיקה, אין צימוד שביר חדש.
- **מנגנון נעילת הקבצים הקריטיים — לא נגעו בו ועדיין תקין** (כל שלושת הקבצים
  תואמים לבסיס שלהם, אומת עכשיו).
- **הסתייגות קטנה אחת (לא קריטית):** סדר הרצת הטסטים החדשים בתוך אותו תהליך
  עלול להפיל 4 טסטים ישנים — אבל זו בעיית-היגיינה של חבילת הטסטים בלבד; בפקודת
  ה-CI הרשמית הכול ירוק (2088/0), והקוד בפרודקשן זהה בית-בבית.

**המסקנה: בטוח להמשיך בשיטה הנוכחית (שלבים קטנים + טסטים). אין צורך בשכתוב.**

## מה צריך לעשות

1. **המייסד (צעד שרת בלבד, מתועד):** לפני ה-pull שמביא את ה-untrack — לגבות
   `sentinel_config.json` ולוודא ש-NAV נשאר תקין על השרת (לפי `docs/
   DEPLOYMENT_RUNBOOK.md`). זה הצעד היחיד שנותר מ-S26-R4.
2. **הבא בתור (טסטים בלבד, אדיטיבי, סיכון אפס):** לבודד את המוקים של מודולי
   הטסט החדשים של Sprint-27 + B1 כך שסדר ההרצה לא ישנה תוצאה (S28-R1) — כדי
   שכשל אמיתי לא יוכל להתחבא וכשל-רפאים לא יופיע.
3. **לתיעוד בלבד (לא לעשות עכשיו):** אם יופיע מקום *רביעי* לבדיקת broker-fresh
   — לחלץ פרדיקט יחיד `account_state.is_broker_fresh()` (כרגע 3 עותקים, חוזה
   זהה, מקובל); חוזה "never raises" + `_coerce_numeric` + `except:` נשארים
   record-only (קבצים נעולים, דורש הרחבת allowlist מבוקרת).

---

## Explicitly OUT-OF-SCOPE (verified, not re-litigated)
Engine-owned coerce/math unification (Tier-C, byte-locked); any
`analytics_engine.py` / `engine_core.py` executable-line edit; the
account_state vs shape-B presentation difference (intentional D5); dashboard
password/auth (a NEW feature, founder security/topology decision — correctly
SKIPped by Sprint-27); F3 NaN-pnl exclusion (engine behavior on a locked path,
founder-gated); code-side RISK_LADDER change (money-methodology, founder-only);
`telegram_bot.py` wholesale rewrite; admin/dev-PIN gate logic;
secure_runner import-order invariant; docker-compose service commands
(re-verified: `telegram-bot: python3 telegram_bot_secure_runner.py` intact).

## Recommendation
Founder default: **no further structural code action required this cycle.**
The two Sprint-26 structural items are closed. S28-R1 is a test-only,
zero-risk, additive hygiene fix worth scheduling next. The W2 host-safety
step remains the single founder-only operational item. S26-R2/R3 stay
record-only pending an independently justified Mark-gated lock expansion.
