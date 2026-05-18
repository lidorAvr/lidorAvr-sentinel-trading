# Sprint-28 — Test-Trustworthiness Re-Verification (DOC-ONLY, NO code)

**Date:** 2026-05-18 · **Wave:** Sprint-28 re-run of the Sprint-26 100/100
test-trust review on the **post-Sprint-27 LIVE state**.
**Scope:** Did Sprint-27 W4b actually CLOSE the Sprint-26 C1 env-dependency
(T1)? Is "green CI" now a *more* trustworthy proxy than at Sprint-26? Any
NEW flaky/order/regression introduced by Sprint-27? Verification only —
residuals become future governed-Phase recommendations; no code/tests this
wave.

**Live tree state (re-verified, not assumed):** working tree **clean**
(`git status --porcelain` empty), `HEAD = 168aaa2` — matches the mandate's
cited SHA exactly (the Sprint-26 P2-SHA reconciliation gap is now CLOSED:
mandate SHA == on-disk HEAD). HEAD commit: `feat(sprint-27): execute
Sprint-26 findings`. The deploy claim (2088 / 0 / 72.02%) is reproduced
**to the digit** below.

**CI-equivalent re-run (the EXACT `.github/workflows/tests.yml` command +
its env block `DEV_PIN=0000` / CI creds):**
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-report=term
--cov-fail-under=67` → **2088 passed, 0 failed, coverage 72.02%, 94.73s**.
Matches the deploy claim (2088 / 0 / 72.02% ≥ 67%) exactly. Runtime 94.7s
≪ the 10-min CI `timeout-minutes: 10` — comfortable headroom.

---

## Method

Read `TESTING_AND_DEPLOYMENT.md`, `SPRINT26_TESTING_FINDINGS.md` (the
C1/T2 gap + all residuals), `SPRINT27_SCOPE.md` (the W4b spec) +
`docs/teams/SPRINT27_W1_IMPL.md` / `SPRINT27_W3W4C_IMPL.md`,
`tests/test_sprint25_c1_devpin_enforcement.py` (the new
`_configured_dev_pin` autouse fixture), the three new Sprint-27 test files
(`test_sprint27_w1_dashboard_nav_honesty.py`,
`test_sprint27_w3_companion_voice.py`,
`test_sprint27_w4c_repo_parity.py`), `tests/_byte_lock_baseline.py`,
`tests/test_sprint25_byte_lock_redteam.py`, `.github/workflows/tests.yml`.
(No `SPRINT28_RESEARCH_DOSSIER.md` present — noted, not blocking.)

Then **executed** (not assumed): the EXACT CI command in CI env; the
EXACT CI command in a **BARE env** (`env -u DEV_PIN`, all other CI creds
present) — the decisive W4b proof, reproducing Sprint-26's bare-env method;
the C1 file standalone; the Sprint-26 T2 reproduction
(`test_developer_menu.py → test_sprint17_wave2.py`); the byte-lock
redteam; SHA-compared all 4 byte-lock baselines vs on-disk; ran the 3 new
Sprint-27 files together and interleaved with C1/B3 for leakage.

---

## The headline question — is the Sprint-26 C1 env-dependency (T1) CLOSED by W4b?

### **YES — CLOSED. Proven by execution.**

Sprint-26's T1 finding: `TestC1ValidSessionUnchanged` (5 tests) was green
in CI **only** because `tests.yml:51` sets `DEV_PIN: "0000"`;
`telegram_devops._DEV_PIN = os.getenv("DEV_PIN","")` is read at import and
the C1 guard fail-CLOSES when empty, so the 5 "valid-session-proceeds"
tests **failed in a bare env**. Sprint-26's executed proof: **bare-env full
suite = 5 failed / 2034 passed** (the 5 exactly `TestC1ValidSessionUnchanged`).

**Sprint-27 W4b fix (verified in source):**
`tests/test_sprint25_c1_devpin_enforcement.py:226-239` — a **class-scoped
`autouse=True` `_configured_dev_pin` fixture** on `TestC1ValidSessionUnchanged`:

```python
@pytest.fixture(autouse=True)
def _configured_dev_pin(self):
    import telegram_devops as devops
    _orig = devops._DEV_PIN
    devops._DEV_PIN = "0000"
    yield
    devops._DEV_PIN = _orig
```

Assessment of the fixture itself:
- **Self-contained:** sets `devops._DEV_PIN = "0000"` directly (does not
  depend on the `os.environ` / `tests.yml` env line at all).
- **State-restoring, no leakage:** captures `_orig` and restores it on
  teardown — symmetric to (and ordered correctly with) the `tb` fixture's
  own dedicated `sys.modules` save/restore. It patches the *module
  constant* the guard actually reads (`_DEV_PIN`), not the env var, so it
  is robust even though `_DEV_PIN` is import-time-bound.
- **Assertions unchanged:** the 5 test bodies are byte-identical to
  Sprint-26; only the precondition is now locally guaranteed. It is the
  exact symmetric mirror of the already-existing
  `TestC1FailClosedWhenUnset._unset_dev_pin` (which sets `_DEV_PIN = ""`)
  — so the file now *self-contains both ends* of the PIN-configured axis.

**The decisive executed bare-env proof (Sprint-26's exact method):**

| Run | Env | Result |
|---|---|---|
| EXACT CI command | CI env (`DEV_PIN=0000`) | **2088 passed / 0 failed / 72.02%** |
| EXACT CI command | **BARE env (`env -u DEV_PIN`)** | **2088 passed / 0 failed / 72.02%** |

In Sprint-26 the identical bare-env full-suite run was **5 failed**. It is
now **0 failed**. The C1 "green" no longer depends on the `tests.yml`
`DEV_PIN=0000` line — **T1 is genuinely CLOSED**, and the closure was
verified by running the suite with that env line's value absent, not by
reading the closure note.

*(Standalone-file footnote, NOT a W4b defect:* running
`tests/test_sprint25_c1_devpin_enforcement.py` **alone** yields `27 passed,
5 errors` — but the errors are a `telebot.util.validate_token` "Token must
contain a colon" `ERROR` from the **real `telebot` library** being imported
before the file's own `tb` stub installs, which only happens when NO prior
test file has stubbed `telebot` in `sys.modules`. This is a *pre-existing
collection-isolation* artifact of the C1 file (unrelated to W4b and
unrelated to `DEV_PIN` — note it is an `ERROR`, not the Sprint-26
`Thread not called` DEV_PIN `FAILED`). In the **authoritative full suite**
— CI env AND bare env — earlier files stub `telebot` first and the C1 file
is **0-fail/0-error in both**. Flagged below as R1.)*

---

## Sprint-25/26 findings — status now (re-verified by execution)

| ID | Status now | Proof I ran |
|---|---|---|
| **T1** — C1 `DEV_PIN` env-dependency (green-CI / red-bare) | **CLOSED by W4b** | Bare-env EXACT CI command = **2088/0** (Sprint-26: 5-fail bare). Fixture is self-contained + state-restoring + assertions unchanged. |
| **T2** — sprint17 cross-file `sys.modules` order-dependency | **STILL OPEN — unchanged, benign, NOT worsened** | `test_developer_menu.py → test_sprint17_wave2.py` = **10 failed** (the SAME 10 Sprint-26 listed). Default-order full suite = 2088/0. See R2. |
| Byte-lock family still enforces | **CONFIRMED enforcing** | Redteam **13 passed**; `test_unauthorized_committed_edit_fails_red` uses `pytest.raises(AssertionError, match="NOT byte-identical")`; `..._missing_baseline_fails_closed_not_vacuous`; `..._uses_no_git_subprocess` (AST); CWD-anchored. All 4 baselines SHA256(on-disk)==SHA256(baseline): analytics_engine / engine_core / period_data_probe / April LOCKED — **MATCH**. |
| New Sprint-27 tests real, not stubs | **CONFIRMED substantive** | W1 = 24 tests (byte-identical pre-W1 string oracle + REAL `account_state.load()` driven through real config files); W3 = 17 (frozen pre-W3 body literal, byte-identical-body proof, C1/B3 honesty asserts); W4c = 8 (old-vs-new `DataFrame.equals()` parity for list/`[]`/`None` + end-to-end `get_open_positions_campaign`). The 3 together = **49 passed**; interleaved with C1+B3 = **62 passed** (no leakage — per-load private mocks hold). Zero `skip`/`xfail`/`assert True`-only stubs. |
| Coverage gate honest | **HONEST as a ratchet (unchanged)** | 72.02% real (analytics 99 / adaptive 88 / addon 86 / engine_core 60). `--cov-fail-under=67` enforced, passes with buffer. T3 caveat unchanged. |
| P2-SHA (Sprint-26: mandate `c761967` vs on-disk `068d056`) | **CLOSED** | Mandate cites `168aaa2`; on-disk `HEAD == 168aaa2` exactly. No reconciliation outstanding. |
| No new flake / sockets enforced | **No NEW flake from Sprint-27** | `pytest-socket` `disable_socket()` per-test in conftest; zero `async def test`; the 3 new files isolate module loading with per-load private mocks. No order-randomization plugin → default order deterministic. |

**Net:** Sprint-27 closed the single biggest Sprint-26 gap (T1) and the
P2-SHA reconciliation, introduced **no new** flaky/order/regression, and
its new tests are real content not stubs. The byte-lock money-math oracle
chain still genuinely enforces in CI. Trust in "green" is materially
**higher** than at Sprint-26.

---

## Remaining test-trust gaps (verified by execution; all latent, none failing in real CI)

### R2 (was T2) — sprint17 cross-file `sys.modules` order-dependency — **P1, STILL OPEN, closure-fix recommendation**

`test_developer_menu.py → test_sprint17_wave2.py` → **10 failed** —
byte-for-byte the same 10 Sprint-26 listed (`TestScopeB*` +
`TestHeadlineByteIdentical*` + `TestGovernorAdvisoryOnly` +
`TestEngineAlgoShortcircuitPreserved`). A preceding telegram test file
leaves polluting `telebot`/menu/engine stubs in `sys.modules` that
sprint17's classes do not defensively save/restore (unlike the C1 file's
`tb` fixture). Green in the **default pytest collection order** (full suite
2088/0); a **latent CI lie iff** default order changes (a new file inserted
alphabetically before sprint17, `-p randomly`, a `testpaths`/rootdir
change). **Note on scope wording:** `SPRINT27_SCOPE.md` W4b text said it
covered "the 5 `TestC1ValidSessionUnchanged` **+ the sprint17
order-dependency**" — but the delivered W4b (`_configured_dev_pin`) fixed
**only C1**; sprint17 Scope-B got **no** save/restore-`sys.modules`
discipline. T2 is **unchanged and NOT worsened**, but the scope's
sprint17 clause is **unfulfilled** (W4b under-delivered vs its own spec on
this sub-item). **Severity:** P1. **value÷risk:** med-high (the fix is the
same save/restore-`sys.modules` discipline the C1 `tb` fixture already
demonstrates; zero behavior risk). **Tag:** closure-fix (future Phase —
OUT this wave). **Named proof strategy:** give sprint17 Scope-B a fixture
that saves & force-replaces `telebot`/`telebot.types`/`telegram_menus`/
`supabase`/`dotenv`/`engine_core` and restores on teardown; prove
`test_developer_menu.py → test_sprint17_wave2.py` goes 10-fail → 0-fail.

### R1 (NEW observation, NOT a regression) — C1 file standalone-collection `telebot` error — **P2, flag**

`tests/test_sprint25_c1_devpin_enforcement.py` run **in isolation** =
`27 passed, 5 errors` (`telebot.util.validate_token` rejecting
`ci-test-token`). Cause: the real `telebot` is importable; the C1 file's
`tb` fixture force-replaces `sys.modules["telebot"]`, but the
`TestC1ValidSessionUnchanged` error path imports the real `telebot` at
collection before the fixture runs **only when no earlier file has already
stubbed it**. **Benign in real CI** (full suite, CI *and* bare env, is
2088/0 — earlier files stub `telebot` first) and is the **same structural
class as R2** (greenness depends on a favorable collection prefix), NOT a
W4b defect (it is an `ERROR`/token issue, distinct from the Sprint-26
DEV_PIN `FAILED`). The proper closure (a real `telebot` stub at the C1
file's module top, mirroring the W3 file's pattern) is part of the same
self-containment Phase as R2. **Severity:** P2. **Tag:** flag /
closure-fix (future Phase — OUT).

### T3 — Coverage gate covers only 4 libraries — **P2, addition (OUT, flag — unchanged from Sprint-26)**

`--cov=` = `engine_core / adaptive_risk_engine / analytics_engine /
addon_risk_engine` only. `telegram_bot.py`, `report_scheduler.py`,
`telegram_bot_secure_runner.py`, `risk_monitor.py`, `dashboard.py`,
`main.py`, and the new `dashboard_nav.py` — the files that actually run in
Docker, plus CLAUDE.md's "most fragile" `telegram_bot.py` (which W4c just
edited) — are **not in the coverage gate**. `engine_core.py` 60% = ~432
unmeasured statements. Honest **regression ratchet for 4 math libraries**,
NOT a production-trust signal for the running services (they ARE heavily
behaviorally tested — 2088 tests — but a silent dead-path regression is
invisible to the ratchet). **Severity:** P2. **Tag:** addition (OUT, flag).

### T4 — Formatter/headline tests assert on synthetic, not the locked fixture — **P2, polish (flag — unchanged)**

The split/headline/probe (and now the W3 companion-line / W1 sidebar)
formatters are proven on hand-built synthetic dicts; the founder-verified
LOCKED `_april_df` is never fed end-to-end through
`build_open_book → headline/probe split`. **Severity:** P2. **Tag:** polish
(OUT, flag).

### T5 — Unpinned dev deps — **P3, flag (unchanged)**

`requirements-dev.txt` pins NO versions. A future `pytest-cov`/`-socket`
major bump could change collection/cov behavior. Reproducibility note only.
**Tag:** flag.

---

## Verdict

**Not 100/100 — but the trust chain is materially STRONGER than Sprint-26,
the single biggest Sprint-26 gap (T1) is genuinely CLOSED, and there is NO
production-critical untested path failing.** The post-Sprint-27 CI-equivalent
is honestly **2088 / 0 / 72.02%** in <95s, and — the decisive proof —
**also 2088 / 0 in a BARE env with no `DEV_PIN`** (Sprint-26 was 5-fail
bare), so "green" no longer depends on the fragile `tests.yml` env line.
Sprint-27 W4b's `_configured_dev_pin` fixture is correctly self-contained,
state-restoring, leak-free, with assertions unchanged. The byte-lock
money-math oracle chain still genuinely enforces (redteam RED-on-tamper,
all 4 baselines SHA-match). The new Sprint-27 tests are substantive content
(byte-identical oracles, real-config drives, parity `.equals()`), not
stubs, and introduce no new flake. **Two latent collection-order
dependencies remain** (R2 sprint17 — Sprint-26's T2, unchanged & **not
worsened** but NOT closed despite W4b's scope wording; R1 the C1 file's own
standalone-`telebot` artifact) — both green today only by favorable
default collection order, both the same Sprint-24 *class*, both should be
self-contained in one future governed Phase. The Sprint-26 P2-SHA
reconciliation is also now closed (mandate SHA == HEAD).

| ID | Finding | Sev | value÷risk | Tag |
|----|---------|-----|-----------|-----|
| T1 | C1 `DEV_PIN` env-dependency | — | — | **CLOSED by W4b (bare-env 2088/0)** |
| P2-SHA | mandate SHA vs on-disk HEAD | — | — | **CLOSED (168aaa2 == HEAD)** |
| R2 (was T2) | sprint17 cross-file `sys.modules` order-dep | P1 | med-high | closure-fix (OUT) — W4b scope clause unfulfilled |
| R1 (new) | C1 file standalone-collection `telebot` error | P2 | medium | flag / closure-fix (OUT) |
| T3 | Coverage gate misses telegram/scheduler/secure_runner/dashboard | P2 | medium | addition (OUT, flag) |
| T4 | Formatter tests assert synthetic, not locked fixture | P2 | low-med | polish (flag) |
| T5 | Unpinned dev deps | P3 | low | flag |

---

## ## למנכ״ל — בשפה פשוטה

**האם אפשר לסמוך על "טסטים ירוקים" *עוד יותר* מאתמול? כן — והתיקון של אתמול
באמת עבד.**

- כל 2088 הבדיקות עוברות, כיסוי 72% (מעל הסף 67%), הכול רץ בפחות מ‑95
  שניות. בדקתי בעצמי, לא הסתמכתי על דיווח.
- **התיקון של אתמול (Sprint‑27 W4b) — האם עבד? כן, בוודאות.** ב‑Sprint‑26
  מצאנו ש‑5 בדיקות (מנגנון ה‑PIN למפתח) ירוקות ב‑CI *רק* כי קובץ ה‑CI
  מגדיר `DEV_PIN=0000`; בסביבה בלי המשתנה הזה הן נכשלו (5 כשלים). אתמול
  הוסיפו תיקון שגורם לבדיקות עצמן להגדיר את ה‑PIN בעצמן. **הרצתי היום את
  כל החבילה בסביבה ריקה, בלי `DEV_PIN` בכלל — וקיבלתי 2088 עוברות, 0
  כשלים** (ב‑Sprint‑26 זה היה 5 כשלים). כלומר "ירוק" כבר *לא* תלוי בשורה
  אחת בקובץ ה‑CI. הפער הכי גדול שמצאנו אתמול — **נסגר באמת**.
- **מנגנון נעילת המספרים** (האורקל של רווח/הפסד אפריל +$180.49) עדיין
  *באמת תופס* שינוי לא מורשה — בדקתי שהוא עדיין "מאדים" כשמשנים בכוונה.
- **הבדיקות החדשות שנכתבו אתמול אמיתיות** — לא "בדיקות ריקות". הן באמת
  משוות מספרים ומבנים, לא סתם עוברות.
- **שתי הסתייגויות שנשארו (קטנות, לא סכנה לכסף):** קובץ בדיקה ישן בשם
  sprint17 עדיין ירוק רק בגלל סדר ריצה מקרי (זה *לא* החמיר, אבל גם *לא*
  נסגר — האיפיון של אתמול אמר שהוא יטופל אבל בפועל טופל רק החלק של ה‑PIN).
  ועוד תופעה דומה קטנה בקובץ ה‑PIN עצמו כשרצים אותו לבד. שתיהן ירוקות
  במציאות, צריך לסגור אותן בעתיד כדי ש"ירוק" לא יוכל להפוך לשקר ע"י שינוי
  לא קשור.
- **שורה תחתונה למנכ"ל:** אפשר לסמוך על "ירוק" יותר מאתמול. התיקון של אתמול
  עבד ואומת בהרצה אמיתית בסביבה ריקה. זה עדיין לא 100/100 כי תלות סדר‑ריצה
  אחת (sprint17) נשארה פתוחה. אין שום נתיב קריטי בפרודקשן שנכשל.

## ## מה צריך לעשות

1. **(P1, Phase עתידי) לסגור את sprint17 (R2 / Sprint‑26 T2)** — לתת
   למחלקות Scope‑B של sprint17 fixture ששומר/משחזר את ה‑`sys.modules`
   (בדיוק כמו ה‑`tb` fixture שכבר קיים בקובץ ה‑C1). הוכחה:
   `test_developer_menu.py` ואז `test_sprint17_wave2.py` = 0 כשלים
   (כיום 10). **הערה:** האיפיון של W4b הבטיח לכלול את זה אך בפועל סגר רק
   C1 — הסעיף הזה נשאר חוב מ‑Sprint‑27.
2. **(P2, באותו Phase) לסגור את R1** — להוסיף stub אמיתי ל‑`telebot`
   בראש קובץ ה‑C1 (כמו שעושה קובץ W3), כך שהרצתו לבד לא תיתן 5 errors.
3. **(P2, מאוחר יותר) להרחיב את שער הכיסוי** לכלול לפחות
   `telegram_bot_secure_runner.py` ו‑`report_scheduler.py` (וכעת גם
   `dashboard_nav.py`/`telegram_bot.py` שנגעו ב‑Sprint‑27), בלי להוריד
   את הסף הקיים.
4. **(תיעוד) הגנת CI:** הערה מפורשת בקובץ `tests.yml` ש‑`DEV_PIN`/
   הקרדנציאלס חובה (גם אם C1 כבר לא תלוי בזה — הגנה רעיונית), ולשקול
   meta‑test "נכשל בבירור" עם הודעה מובנת אם קרדנציאל קריטי חסר.
5. **(reconcile — נסגר)** ה‑SHA במנדט (`168aaa2`) תואם ל‑HEAD בפועל
   (`168aaa2`) — אין עוד פער SHA לסגור.

**אין לבצע קוד/בדיקות בגל הזה — אלה המלצות ל‑Phases עתידיים מבוקרים בלבד.**
