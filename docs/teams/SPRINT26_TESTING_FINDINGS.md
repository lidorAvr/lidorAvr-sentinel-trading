# Sprint-26 — Test-Trustworthiness Re-Verification (DOC-ONLY, NO code)

**Date:** 2026-05-17 · **Wave:** Sprint-26 100/100 test-trust review of the LIVE system
**Scope:** Is "green CI" a *trustworthy* proxy for "the system really works"?
Verification only — gaps become future governed-Phase recommendations, no
code/tests this wave.

**Live tree state (re-verified, not assumed):** working tree **clean**
(`git status --porcelain` empty), `HEAD = 068d056`. NOTE: the mandate cites
`c761967`; the on-disk HEAD short-SHA is `068d056`. The suite/coverage
numbers match the deploy claim **exactly** (below), so this is the same
logical deploy state — but the SHA mismatch should be reconciled by Ops
(P2-SHA, flag only).

**CI-equivalent re-run (the EXACT `.github/workflows/tests.yml` command +
its env block `DEV_PIN=0000` / CI creds):**
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-report=term
--cov-fail-under=67` → **2039 passed, 0 failed, coverage 72.02%, 97.6s**.
Matches the deploy claim (2039 / 0 / 72.02% ≥ 67%) to the digit. Runtime
97.6s ≪ the 10-min CI `timeout-minutes: 10` — comfortable headroom.

---

## Method

Read `TESTING_AND_DEPLOYMENT.md`, `SPRINT25_TESTING_AUDIT.md`,
`tests/_byte_lock_baseline.py`, `tests/test_sprint25_byte_lock_redteam.py`,
the per-phase proofs (`test_phase_*`, `test_sprint24_b1b3_byte_identical`),
`tests/conftest.py`, `.github/workflows/tests.yml`, the C1 enforcement +
sprint17 wave-2 tests, `SPRINT26_RESEARCH_DOSSIER.md`,
`SPRINT26_SECURITY_FINDINGS.md`. Then **executed** (not assumed): the full
CI command with and without the CI env block; the C1/sprint17 tests in
bare env, CI env, isolation, and several cross-file orders;
`test_secure_runner.py` from `/tmp` (foreign CWD); SHA-compared all four
byte-lock baselines vs on-disk; ran the byte-lock RED-on-violation +
markers + socket-enforcement proofs under the CI command.

---

## What Sprint-25 flagged and is now genuinely CLOSED (re-verified by execution)

| Sprint-25 ID | Status now | Proof I ran |
|---|---|---|
| P0-1 "LOCKED" April fixture had **no integrity guard** | **CLOSED** | `tests/_byte_lock_baselines/test_real_data_april_regression.py.baseline` exists; SHA256(on-disk) == SHA256(baseline). `assert_byte_identical("tests/test_real_data_april_regression.py")` is GREEN and the RED-redteam proves it goes RED on a committed-style tamper. |
| Sprint-25 A1 — byte-lock family was **vacuous in CI** (`git diff` empty on clean checkout) | **CLOSED** | Lock redesigned to commit-state-AGNOSTIC committed-baseline SHA (`tests/_byte_lock_baseline.py`, no `subprocess`/`git` — AST-verified by `test_sprint25_byte_lock_redteam.py`). All 4 baselines (`analytics_engine`, `period_data_probe`, `engine_core`, April) byte-match on-disk. Redteam = **28 passed** under CI cmd, incl. RED-on-tamper + fail-closed-on-missing-baseline. |
| P1-1 `test_secure_runner.py` bare CWD path (Sprint-25 "highest value") | **CLOSED** | Ran `test_secure_runner.py` from `/tmp` → **35 passed** (Sprint-25 proved 3-fail from `/tmp`; now path-anchored). The sole secure-runner content guard is robust. |
| P1-3 proof-existence didn't bind proof CONTENT | **CLOSED** | `test_sprint24_b1b3_byte_identical.py` now carries real `DataFrame.equals()` partition + full-frame oracles **and** `assert_byte_identical(...)` on the (now baseline-guarded) April fixture — the binding contract is content, not a name substring. |
| Per-phase proofs are real, not stubs | **CONFIRMED real** | Assertion counts: archf1=15, b3=30, engine_p2p3=43, c2=50, navunify=99, sprint24-b1b3=29 substantive asserts. The only two `pass` lines (test_phase_b3 L200/L214) are `except Exception: pass` race-simulation scaffolding, not stub test bodies. No `skip`/`xfail`/`assert True`-only stubs in the phase proofs. |
| Coverage gate honest | **HONEST as a ratchet** | 72.02% real (analytics 99 / adaptive 88 / addon 86 / engine_core 60). `--cov-fail-under=67` enforced and passes with buffer. Caveat unchanged from Sprint-25 P2-1 — see T3 below. |
| Flaky/asyncio/socket | **No new flake**; sockets enforced | `pytest-socket` `disable_socket()` per-test in conftest; zero `async def test`. No order-randomization plugin, so default order is deterministic (relevant to T2). |

**Net:** every P0/P1 Sprint-25 finding that was a *real* trust hole is
closed and I verified each by execution, not by reading the closure note.
The byte-lock chain — the money-math oracle protection — is now genuinely
enforcing in CI exactly where merges gate.

---

## The remaining test-trust gaps (verified by execution; all latent, none failing in real CI)

### T1 — C1 `DEV_PIN` env-dependency: green-in-CI / RED-bare (the inverse Sprint-24 class) — **P1, closure-fix recommendation**

`tests/test_sprint25_c1_devpin_enforcement.py::TestC1ValidSessionUnchanged`
(5 tests: git-pull / ibkr-sync / xml-arm / doc-upload / on-demand-report).

`telegram_devops._DEV_PIN = os.getenv("DEV_PIN", "")` is read **at import
time**. The C1 guard fail-CLOSES when `_DEV_PIN == ""`. These 5 tests grant
a session and assert the privileged action **proceeds** — which it only
does if `DEV_PIN` is set.

**Executed proof (not assumed):**
- Bare env (no `DEV_PIN`), full suite: **5 failed / 2034 passed**. The 5
  are exactly `TestC1ValidSessionUnchanged`.
- CI env (`DEV_PIN=0000`, the block in `tests.yml:46-52`), full suite:
  **2039 passed / 0**.

**Is it benign or a latent CI lie?** It is **benign in real CI today**,
because `.github/workflows/tests.yml` explicitly sets `DEV_PIN: "0000"`. It
is the *inverse* of the Sprint-24 bug class (Sprint-24 = green-local /
red-CI false alarm; this = green-CI / red-bare). It is a **latent CI lie
iff the env block is ever removed/renamed** — at which point CI would go
red with a confusing `Thread not called` message that looks like a real
regression, masking or mimicking an actual C1 break. The mandate's
"`test_sprint17_wave2`" label for this is a **misattribution**: the
env-dependent failures live in `test_sprint25_c1_devpin_enforcement.py`,
not sprint17 (sprint17's own `TestScopeBDevMenuGated` /
`TestScopeBCrossProcessCreds` pass bare in isolation — see T2 for their
distinct issue). The Sprint-26 research dossier item #4 independently
flagged this same env-dependency; this review confirms it by execution and
pins the exact file/class.

**Severity:** P1. **value÷risk:** high (the fragile coupling is a single
CI env line; a 1-line `pytest.skip`/`monkeypatch.setenv("DEV_PIN",...)`
self-containment removes the env coupling with zero behavior risk).
**Tag:** closure-fix (recommended for a future governed Phase — OUT this
DOC-ONLY wave). **Named proof strategy —
`TestC1ValidSessionUnchanged` env-self-containment:** have the `tb`
fixture (or a class-level fixture) `monkeypatch.setenv("DEV_PIN","0000")`
**and** reload/patch `telegram_devops._DEV_PIN` so the authorized-path
tests no longer depend on the CI env block; re-prove 5-pass from a bare
env.

### T2 — `test_sprint17_wave2.py` cross-file `sys.modules`-stub order-dependency — **P1, closure-fix recommendation**

`TestScopeBNoSnapshotMutation`, `TestScopeBCrossProcessCreds`,
`TestScopeBDevMenuGated`.

**Executed proof:** sprint17 **alone** (CI env) → 35 passed. But
`test_developer_menu.py` → `test_sprint17_wave2.py` → **10 failed**
(`test_button_in_developer_menu_only`, the CrossProcessCreds pair, the
snapshot-mutation test). Cause: a *preceding* telegram test file leaves
polluting `telebot`/menu stubs in `sys.modules` that sprint17's Scope-B
tests do not defensively reset (unlike the C1 file's `tb` fixture, which
saves/restores its own dedicated stub set). In the **default pytest
collection order** sprint17 collects favorably and the full suite is
2039/0 (re-proven via `-k "sprint17 or C1ValidSession"` → 40 passed) — so
it is **green today purely by coincidence of alphabetical default order**,
with no order-randomization plugin to expose it.

**Is it benign or a latent CI lie?** Benign today; a **latent CI lie iff**
default collection order changes (new test file inserted alphabetically
before sprint17, a `-p randomly`, or a `testpaths`/rootdir change). Same
structural class as Sprint-24 (green only because the harness happens to
start in a favorable state).

**Severity:** P1. **value÷risk:** medium-high (the fix is the same
save/restore-`sys.modules` discipline the C1 `tb` fixture already
demonstrates; zero behavior risk). **Tag:** closure-fix (future Phase —
OUT). **Named proof strategy:** give the sprint17 Scope-B classes a
fixture that saves & force-replaces `telebot`/`telebot.types`/
`telegram_menus`/`supabase`/`dotenv` (mirroring the C1 `tb` fixture) and
restores on teardown; prove order-invariance by running
`test_developer_menu.py` → `test_sprint17_wave2.py` (currently 10-fail →
must be 0-fail).

### T3 — Coverage gate covers only 4 libraries; production-critical services uncovered — **P2, addition (OUT, flag — unchanged from Sprint-25 P2-1)**

`--cov=` list = `engine_core / adaptive_risk_engine / analytics_engine /
addon_risk_engine` only. `telegram_bot.py`, `report_scheduler.py`,
`telegram_bot_secure_runner.py`, `risk_monitor.py`, `dashboard.py`,
`main.py` — the files that actually run in Docker, and CLAUDE.md's "most
fragile" `telegram_bot.py` — are **not in the coverage gate**.
`engine_core.py` at 60% line coverage = ~432 unmeasured statements
(campaign-aggregation / market-data branches). The gate is an honest
**regression ratchet for 4 math libraries**, NOT a production-trust signal
for the running services. There ARE 2039 tests touching these services
(C1/secure-runner/scheduler are heavily behaviorally tested), but a
silent dead-path regression in them is **invisible to the coverage
ratchet**. **Severity:** P2. **Tag:** addition (OUT — flag for a future
coverage-expansion Phase; no new tests this wave).

### T4 — Formatter/headline tests assert on synthetic, not the locked fixture — **P2, polish (flag — unchanged from Sprint-25 P2-2)**

The split/headline/probe formatters are proven on hand-built synthetic
book dicts; the founder-verified locked `_april_df` is never fed end-to-end
through `build_open_book → headline/probe split`. The money-affecting
*input* to those formatters is never the locked oracle. Mirrors CLAUDE.md
"do not present fallback as exact truth" at the test level. **Severity:**
P2. **Tag:** polish (future Phase — OUT, flag).

### T5 — Unpinned dev deps — **P3, flag (unchanged from Sprint-25 P3-2)**

`requirements-dev.txt` pins NO versions (`pytest`, `pytest-cov`,
`pytest-socket` unpinned). A future `pytest-cov` major bump could change
nested-collection/cov behavior. Reproducibility/supply-chain note only.
**Tag:** flag.

---

## Verdict

**Not 100/100 — but the trust chain is materially STRONGER than Sprint-25
and there is NO production-critical untested path that is failing.** Every
Sprint-25 P0/P1 *real* trust hole (vacuous byte-lock in CI, unguarded
April oracle, bare-CWD secure-runner guard, name-only proof binding) is
**closed and re-verified by execution**, and the full CI-equivalent is
honestly 2039/0/72.02% in <100s. The residual gaps (T1, T2) are **two
distinct latent env/order dependencies that are GREEN today only because
two fragile defaults happen to hold** (the CI `DEV_PIN=0000` env line, and
pytest's alphabetical collection order). Neither is failing in real CI;
both are exactly the Sprint-24 *class* the mandate prioritizes and should
be self-contained in a future governed Phase so "green" cannot become a
lie via an unrelated change.

| ID | Finding | Sev | value÷risk | Tag |
|----|---------|-----|-----------|-----|
| T1 | C1 `DEV_PIN` env-dependency (5 tests, green-CI/red-bare) | P1 | high | closure-fix (OUT) |
| T2 | sprint17 cross-file `sys.modules` order-dependency | P1 | med-high | closure-fix (OUT) |
| T3 | Coverage gate misses telegram/scheduler/secure_runner/dashboard | P2 | medium | addition (OUT, flag) |
| T4 | Formatter tests assert synthetic, not locked fixture | P2 | low-med | polish (flag) |
| T5 | Unpinned dev deps | P3 | low | flag |
| P2-SHA | mandate cites `c761967`, on-disk HEAD `068d056` (numbers match) | — | — | reconcile w/ Ops (flag) |

---

## ## למנכ״ל — בשפה פשוטה

**האם "טסטים ירוקים" באמת אומרים שהמערכת עובדת? כן — עם הסתייגות אחת
ברורה.**

- כל 2039 הבדיקות עוברות, כיסוי 72% (מעל הסף 67%), והכל רץ בפחות מ‑100
  שניות. בדקתי בעצמי, לא הסתמכתי על דיווח.
- **התיקונים הקריטיים מ‑Sprint‑25 באמת בוצעו ואומתו:** מנגנון נעילת
  המספרים (האורקל של רווח/הפסד אפריל +$180.49) כבר *באמת תופס* שינוי לא
  מורשה גם ב‑CI, ולא רק "נראה ירוק" כמו קודם.
- **ההסתייגות:** 5 בדיקות (של מנגנון ה‑PIN למפתח) ירוקות ב‑CI רק כי קובץ
  ה‑CI מגדיר `DEV_PIN=0000`. בסביבה בלי המשתנה הזה הן נכשלות. זה לא באג
  במערכת ולא סכנה לכסף — זה תלוי‑סביבה. כל עוד שורת ה‑`DEV_PIN` בקובץ
  ה‑CI לא נמחקת, "ירוק" אמין. אם מישהו ימחק אותה, CI יאדים בהודעה מבלבלת
  שתיראה כמו תקלה אמיתית. בעיה דומה (קטנה יותר) קיימת בקובץ sprint17,
  שירוק רק בגלל סדר ריצה מקרי.
- **שורה תחתונה למנכ"ל:** אפשר לסמוך על "ירוק" היום. זה לא 100/100 כי
  שתי תלויות חבויות צריכות להיסגר כדי ש"ירוק" לא יוכל להפוך לשקר ע"י
  שינוי לא קשור בעתיד. אין שום נתיב קריטי בפרודקשן (טלגרם / מתזמן
  דוחות / secure runner / דשבורד) שנכשל — הם פשוט לא נכללים במדד הכיסוי,
  אבל כן נבדקים התנהגותית.

## ## מה צריך לעשות

1. **(P1, Phase עתידי) לנתק את 5 בדיקות ה‑C1 מסביבת ה‑CI** — שהבדיקה
   תגדיר בעצמה `DEV_PIN` (`monkeypatch.setenv` + רענון
   `telegram_devops._DEV_PIN`), כך ש"ירוק" לא יהיה תלוי בשורה אחת בקובץ
   ה‑CI. הוכחה: לרוץ בסביבה ריקה ולקבל 5/5 ירוק.
2. **(P1, Phase עתידי) לבודד את sprint17 Scope‑B** עם fixture
   ששומר/משחזר את ה‑`sys.modules` (בדיוק כמו ה‑fixture שכבר קיים בקובץ
   ה‑C1). הוכחה: `test_developer_menu.py` ואז `test_sprint17_wave2.py`
   = 0 כשלים.
3. **(P2, מאוחר יותר) להרחיב את שער הכיסוי** לכלול לפחות
   `telegram_bot_secure_runner.py` ו‑`report_scheduler.py` (השירותים
   הקריטיים שרצים ב‑Docker), בלי להוריד את הסף הקיים.
4. **(תיעוד) להוסיף הגנה ל‑CI:** הערה מפורשת בקובץ `tests.yml` ש‑
   `DEV_PIN`/הקרדנציאלס חובה, ולשקול meta‑test ש"נכשל בבירור" עם הודעה
   מובנת אם `DEV_PIN` חסר (במקום 5 כשלים מבלבלים).
5. **(reconcile) ליישר את ה‑SHA:** המנדט מצטט `c761967`, ה‑HEAD בפועל
   `068d056` (המספרים זהים — אותו deploy לוגי). שתאשר Ops.

**אין לבצע קוד/בדיקות בגל הזה — אלה המלצות ל‑Phases עתידיים מבוקרים בלבד.**
