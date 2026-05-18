# Sprint-29 — Testing/QA: Do Our Green Tests Catch What the REAL Telegram Report Shows? (DOC-ONLY, NO code)

**Date:** 2026-05-18 · **Wave:** Sprint-29 testing review.
**Question:** Our CI is green (2101 passed / 0 failed / 72.02%) on `HEAD 09dbec7`.
But the user's two real exported Telegram transcripts
(`/tmp/tg_report_1.txt` = 996 msgs, `/tmp/tg_report_2.txt` = 431 msgs)
show concrete rendered defects. **For each one: is there a test that would
catch the RENDERED form — or do real rendered defects slip through green CI?**

**DATA-SENSITIVITY:** This committed doc is STRUCTURAL only. NO live
NAV / position / P&L values are copied here. Defects are described by their
*shape* (glyph pattern, label-vs-label contradiction, silent-0 class), never
by the figures in the user's exports.

**Method (evidence ran, not assumed):** Read both exports (by region — they
exceed single-read limits); `engine_core.get_nav_with_freshness`
(`engine_core.py:1604-1640`); `bot_health.py:25-54`; `telegram_formatters.py`
L50/S9 block (`:44-86`, `:236-264`, `:453-500`); the deployed ALGO-1 test
(`tests/test_phase_algo1_recon_and_sample.py`, 297 lines); the Sprint-27
W1/W3 tests; `tests/test_bot_health.py`, `tests/test_bot_helpers.py`,
`tests/test_telegram_formatters.py`, `tests/test_telegram_portfolio.py`;
and `docs/teams/SPRINT28_TESTING_FINDINGS.md` (T3/T4 already flagged the
class of gap this review now *confirms with the user's real output*).

**Export-timeline classification (established by evidence, not assumed):**
`tg_report_1.txt` contains the L50 score+win-rate lines with **zero**
"מבוסס מדגם חלקי" / "מדגם נוכחי" disclosures (`grep -c` = 0) — it is
**PRE-deploy** rendered state. `tg_report_2.txt` contains the W-A3
disclosure (`grep -c` = 2) — it is **POST-deploy** and proves the W-A3
fix now *renders*. Both still show the unreconciled `L50(50)` literal.

---

## Defect-by-defect: is the RENDERED form test-pinned?

### D1 — Doubled "✅ ✅ NAV" glyph (also "⚠️ 🟠 NAV", "🔴 🟠 NAV") — **STILL-OPEN, UNTESTED. Sev: P1 (UX/honesty).**

**Rendered form (both exports, recurring — `tg_report_1` has 9 occurrences,
`tg_report_2` has 1):** `✅ ✅ NAV $… — עודכן לפני …ש׳`, and the
manual-NAV no-timestamp line renders as `⚠️ 🟠 NAV …` and `🔴 🟠 NAV …`.

**Root cause (verified in source):** `engine_core.get_nav_with_freshness()`
returns a `freshness_label` that **already begins with its own status
emoji** — `✅ NAV $…` (`engine_core.py:1617`), `🟠 NAV … אין timestamp`
(`:1634`), `🔴 NAV …` (`:1613`). `bot_health.py:48-54` then passes that
whole string into `ok()` / `warn()` / `bad()`, which **prepend a second
emoji** (`ok(msg) → f"✅ {msg}"` `:25`; `warn → ⚠️` `:26`; `bad → 🔴`
`:27`). Fresh+ok ⇒ `ok("✅ NAV …")` ⇒ **`✅ ✅ NAV …`**. Manual no-stamp
(stale ⇒ warn / critical ⇒ bad) ⇒ `⚠️ 🟠 …` / `🔴 🟠 …`. The report
patterns match this exactly.

**Is there a test that catches the RENDERED form? NO — and the existing
test actively *codifies the bug as correct*.** `tests/test_bot_health.py`
mocks `ec.get_nav_with_freshness` with **synthetic** labels that have NO
leading emoji (`"NAV fresh"`, `:58`) or a *different* emoji
(`"🚨 NAV קריטי"`, `:104`; `"⚠️ NAV ישן"`, `:113`). It therefore can
**never produce** the `✅ ✅` collision. Worse: `test_nav_critical_shows_red`
(`:101-108`) asserts BOTH `"🚨 NAV קריטי" in result` AND `"🔴" in result`
— i.e. it *expects* the double-emoji line `🔴 🚨 NAV …` and marks it green.
`test_bot_helpers.py` mocks the same function with emoji-less synthetic
labels too. **No test anywhere feeds the REAL `get_nav_with_freshness()`
string through `build_health_report()`.** This is exactly SPRINT28 **T4**
("formatter tests assert synthetic, not the locked/real fixture") — the
user's export is the live proof T4 was a real, not theoretical, gap.

**Gap:** No end-to-end pin: real `engine_core` NAV label → `bot_health`
wrapper → asserted single-emoji prefix (`assert result.count("NAV") and
not "✅ ✅" / not "🔴 🟠" in result`). **Severity P1** (every healthy
`/portfolio`/health render shows a glitched line; "double-✅" is the
*good* case — the bad cases mix `🔴 🟠` and `⚠️ 🟠`, which is confusing
exactly when NAV honesty matters most).

### D2 — "L50(50)=…" (score line) contradicts "L50 (8): 50%" (win-rate line) — and the SAME contradiction exists for S9 — **partially fixed (disclosure renders post-deploy) but the CONTRADICTION itself is STILL-OPEN and the rendered combination is NOT test-pinned. Sev: P1.** *(ALGO-1 W-A3 target.)*

**Rendered form:** Same `/portfolio` message shows
`▸ ציון … S9(9)=… | M21(21)=… | L50(50)=…` directly above
`▸ Win Rate — S9 (8): …% | L50 (8): …%`. The score line's `S9(9)` /
`M21(21)` / `L50(50)` are **hardcoded brand literals**
(`telegram_formatters.py:250`) — `(9)`/`(21)`/`(50)` are string constants,
not the real sample. The win-rate line (`:264`) uses the **real** counts
(`s9_stats['n']`, `l50_stats['n']`). When the true book is small the two
lines on screen flatly contradict each other (`(50)` vs `(8)`, **and
`(9)` vs `(8)`**).

**Did the deployed ALGO-1 W-A3 fix this? Only partially, and the test
*accepts the contradiction as correct*.** The fix only **appends a separate
disclosure line** (`_l50_sample_honesty_line`, `:69-86`) when L50<50; it
does **not** change the misleading `L50(50)` literal, and it does **nothing
at all** about the equally-contradictory hardcoded `S9(9)`. The ALGO-1 test
`TestWA3L50SampleHonesty` asserts the misleading literal is **still
present** (`test_sample_lt_50_honest_disclosure_adaptive_block`,
`:201`: `assert _expected_l50_score_line(rr) in out` — i.e. it *requires*
`L50(50)` to still render). And its `_risk_rec` fixture pins
`s9_stats={"n": 9}` (`:154`) — which **accidentally equals** the hardcoded
`S9(9)` literal, so the S9 contradiction is **invisible to the test by
fixture coincidence**.

**Export evidence of the timeline:** `tg_report_1` (pre-deploy) shows the
score+win-rate pair with **NO disclosure** — the raw contradiction the user
saw. `tg_report_2` (post-deploy) DOES contain the disclosure in *some*
renders — so W-A3's disclosure **is rendered-real** (good). BUT even in
`tg_report_2` the heat-thermometer block (`L50 [🟢🟢🟢🟢⚪] 86` +
`Win Rate — … L50 (8): …%`) and the score line `L50(50)=…` still render
the bare contradictory literal, sometimes WITHOUT the disclosure adjacent.

**Is the RENDERED combination test-pinned? NO.** ALGO-1 tests
`fmt_adaptive_risk_block` / `fmt_heat_thermometer` **in isolation** on
synthetic dicts. **No test asserts the two lines as they co-render** (score
literal AND win-rate real-N in one rendered block), and **no test catches
the S9(9)-vs-real-N contradiction at all**. Classify: W-A3
disclosure = **fixed-AND-renders (proven by `tg_report_2`)** but
**NOT rendered-combination-test-pinned**; the underlying
literal-vs-real contradiction (esp. S9) = **STILL-OPEN, UNTESTED**.
**Severity P1** (a risk-recommendation surface that internally contradicts
itself by 6x on sample size; SPRINT28 T4 again).

### D3 — Recon / realized-PnL silently 0 — **fixed in math AND has a parity test, but NOT pinned at the RENDERED `חדר מצב` text. Sev: P2 (was P0 before deploy).** *(ALGO-1 W-A2 target.)*

**Class:** Pre-fix `telegram_portfolio.py:473` read `c.get("net_pnl", 0)`
while the producer emits `total_pnl_usd` — realized PnL silently summed to
0, mis-banding the broker reconciliation. The deployed W-A2 (`HEAD
09dbec7`) switched to the real key.

**Is it tested? YES at the function/parity layer — well.**
`TestWA2ReconKeyParity` (`:65-140`) proves: producer emits `total_pnl_usd`
& never `net_pnl`; the pre-fix read was provably always 0.0; post-fix term
== dashboard realized oracle; and the *classifier band* changes from the
silent-bug mis-band to the truthful `"Balanced"`. This is a strong,
real (non-stub) pin of the fix and the LOCKED April invariant
(`:255-266`) is held byte-identical. Classify: **fixed-AND-test-pinned at
the math/classifier layer.**

**Gap (why still P2 not closed):** the pin stops at
`classify_broker_reconciliation(...)` **return dict**. No test asserts the
**rendered `🔭 חדר מצב` Telegram text** the user actually sees — i.e. that
the reconciliation *line string* now shows the non-zero realized term.
`test_telegram_portfolio.py` tests the `/trade` drill-down render, not the
`/portfolio` recon line. So a future *presentation-layer* regression
(formatting the right number wrongly, or dropping the line) would still be
green. **Severity P2** — math is correct & pinned; the last rendered inch
is not. Same structural class as D1/D2 (SPRINT28 T4).

### D4 — Report duplication / startup-spam — **STILL-OPEN, UNTESTED at the transcript level. Sev: P2.**

**Rendered form:** `tg_report_1` opens with the identical pair
"מערכת Sentinel באוויר" / "מערכת Sentinel עולה מחדש" **printed twice
back-to-back** (each `grep -c` = 2 at the head) before any user action —
a restart/duplicate-emit pattern. AGENTS.md invariant #7/#11 (anti-spam,
per-state dedup) governs this.

**Is it tested? NO test inspects a multi-message transcript for adjacent
duplicates / startup-burst.** Anti-spam tests (where present) target
`risk_monitor` per-position dedup flags, not the bot's
startup/status-emit path or transcript-level repetition. **No coverage**
of "same message emitted N× in a row." **Severity P2** (noise erodes
signal; invariant #7 is explicitly an AGENTS red line). Note: this may be
a runtime restart artifact rather than a code defect — but *that
distinction itself is untested*, so it cannot be ruled benign from CI.

### D5 — Number-shown-as-exact-when-fallback / manual — **DISCLOSURE renders, but it RIDES ON the D1 broken glyph; the honesty-line/glyph interaction is UNTESTED. Sev: P2.**

**Rendered form:** the manual no-timestamp NAV renders
`🔴 🟠 NAV $… — אין timestamp (הוגדר ידנית)` and `⚠️ 🟠 NAV …`. The
**honest wording is present** ("אין timestamp (הוגדר ידנית)" — good, this
is the AGENTS #1 / CLAUDE "say if fallback" behavior working). BUT it is
delivered through the **same doubled-emoji D1 defect**, so the single most
honesty-critical line (manual/stale NAV) is *also* the most visually
glitched. Tests assert the *wording* substring in isolation but **never
the wording+prefix as co-rendered through `bot_health`** — so the honest
text is pinned, the dishonest-looking *delivery* is not. **Severity P2**
(honesty content OK; presentation undermines it; same root as D1).

---

## Cross-reference to SPRINT28_TESTING_FINDINGS.md

SPRINT28 already flagged **T4** ("split/headline/probe + W3/W1 formatters
proven on hand-built synthetic dicts; the founder-verified LOCKED fixture
is never fed end-to-end through the render") as P2/polish, and **T3**
(coverage gate excludes `telegram_bot.py` / `bot_health` / scheduler /
secure_runner). **Sprint-29's finding: T4 is NOT P2-polish — the user's
real export proves it lets P1 rendered defects (D1 doubled glyph, D2
self-contradicting risk block) ship green.** The synthetic-fixture
shortcut is the single common root of D1, D2, D3-last-inch, D5. Recommend
T4 be **re-graded P1** and an end-to-end "real engine output → real
formatter → assert rendered string" harness be added (future governed
Phase — OUT this DOC-ONLY wave).

---

## Summary table

| ID | Rendered defect | Deployed fix? | RENDERED-form test? | Class | Sev |
|----|-----------------|---------------|---------------------|-------|-----|
| D1 | `✅ ✅ NAV` / `🔴 🟠` / `⚠️ 🟠` double glyph | none | **NO** — existing test codifies bug as correct | still-open-untested | **P1** |
| D2 | `L50(50)`/`S9(9)` literal vs real `(8)` win-rate | W-A3 (disclosure only) | disclosure renders (proven `tg_report_2`); **combination & S9-contradiction NOT pinned** | fixed-but-not-rendered-pinned / still-open (S9) | **P1** |
| D3 | recon realized-PnL silent-0 | W-A2 (`09dbec7`) | math/classifier **YES**; rendered `חדר מצב` line **NO** | fixed-AND-test-pinned (math) / not-rendered-pinned | P2 |
| D4 | startup message duplication/spam | none | **NO** transcript-level dedup test | still-open-untested | P2 |
| D5 | honest fallback text via broken D1 glyph | partial (wording honest) | wording pinned; co-rendered prefix **NO** | fixed-but-not-rendered-pinned | P2 |

**Net verdict:** Green CI (2101/0/72.02%) is an **honest math-regression
ratchet** (W-A2 parity + LOCKED April are genuinely pinned) but is **NOT a
trustworthy proxy for "the rendered Telegram report is correct."** Two P1
rendered defects (D1, D2) are visible in the user's real exports while CI is
green, because every formatter/health test asserts on **synthetic
hand-built dicts**, never the real engine output, and one test
(`test_nav_critical_shows_red`) actively **locks the D1 bug in as
expected**. The deployed ALGO-1 W-A2 fix IS rendered-real and
parity-pinned at the math layer; W-A3's disclosure IS rendered-real (proven
by `tg_report_2`) but the contradictory literal it sits next to is
**not reconciled and not combination-pinned** (and the identical S9
contradiction is wholly untested). SPRINT28 T4 is the common root and
should be re-graded **P1**.

---

## ## למנכ״ל — בשפה פשוטה

**האם ה"טסטים הירוקים" שלנו היו תופסים את התקלות שאתה רואה בדוח האמיתי
בטלגרם? התשובה הכנה: חלקית — וברוב המקרים החשובים, לא.**

- **המספרים נכונים.** התיקון שנפרס אתמול (התאמת הברוקר/רווח ממומש שהיה
  "מתאפס בשקט") — באמת תוקן, ויש לו טסט אמיתי וחזק שמוכיח שהמספר נכון.
  גם נעילת המספרים של אפריל עדיין מחזיקה. בצד החשבון — אפשר לסמוך.
- **אבל מה שאתה *רואה על המסך* — שם הבדיקות מפספסות.** שלוש דוגמאות
  מהדוח האמיתי שלך:
  1. שורת ה‑NAV מופיעה עם **שתי איקוני סטטוס כפולים** (למשל "✅ ✅",
     ולפעמים "🔴 🟠" / "⚠️ 🟠"). זה באג אמיתי בקוד — ואין שום טסט שתופס
     אותו; גרוע מכך, טסט קיים *מאשר את הצורה השבורה כ"תקינה"*.
  2. בלוק המלצת הסיכון **סותר את עצמו**: שורה אחת אומרת מדגם של 50 (וגם 9),
     והשורה שמתחתיה אומרת מדגם אמיתי קטן בהרבה. התיקון של אתמול הוסיף שורת
     הבהרה (וזה כן עובד ומופיע בדוח השני שלך — טוב), אבל לא תיקן את הסתירה
     עצמה, ואת הסתירה המקבילה ב‑S9 אף טסט לא בודק בכלל.
  3. הודעות ההפעלה **משוכפלות** בראש הדוח — אין טסט שבכלל מסתכל על רצף
     הודעות כדי לתפוס כפילות/ספאם.
- **למה זה קורה?** כל בדיקות ה"מראה" שלנו עובדות על נתונים מומצאים ביד,
  לא על הפלט האמיתי של המנוע. צוות הבדיקות כבר סימן את זה ב‑Sprint‑28
  (ממצא T4) אבל דורג כ"ליטוש קל" — **הדוח האמיתי שלך מוכיח שזה לא קל, זה
  מפיל באגים גלויים דרך CI ירוק.**
- **שורה תחתונה:** "ירוק" = המתמטיקה לא נשברה. "ירוק" ≠ "הדוח שאתה מקבל
  נראה נכון". הפער הגדול ביותר הוא שאין אצלנו אף בדיקה שמריצה את הפלט
  *האמיתי* דרך המעצב ובודקת את *המחרוזת שאתה בפועל רואה*.

## ## מה צריך לעשות

1. **(P1 — Phase עתידי) הרמת SPRINT28‑T4 ל‑P1 + הוספת harness "קצה‑לקצה
   למסך":** להריץ את הפלט האמיתי של `engine_core.get_nav_with_freshness`
   דרך `bot_health.build_health_report` ולקבוע (assert) שאין `✅ ✅` /
   `🔴 🟠` / `⚠️ 🟠` — וכן לתקן את הבאג עצמו (לא להוסיף איקון אם המחרוזת
   כבר מתחילה באחד). זה D1+D5.
2. **(P1 — Phase עתידי) טסט שמצמיד את שתי השורות *ביחד*** (שורת הציון +
   שורת ה‑Win Rate) כפי שהן באמת מתרנדרות, כולל מקרה מדגם קטן — ולתקן את
   הליטרל `L50(50)`/`S9(9)` כך שלא יסתור את ה‑N האמיתי. זה D2.
3. **(P2 — Phase עתידי) טסט רמת‑תמליל לכפילות/ספאם:** לוודא שאותה הודעת
   מערכת לא נפלטת פעמיים ברצף (D4), ולברר אם זו תקלת קוד או ארטיפקט
   restart — ולכסות את ההבחנה הזו.
4. **(P2 — Phase עתידי) להרחיב את שער הכיסוי (SPRINT28‑T3)** לכלול את
   `bot_health.py` / `telegram_bot.py` / `report_scheduler.py`, בלי
   להוריד את הסף הקיים — כדי שרגרסיה בנתיב הרינדור לא תהיה שקופה ל‑CI.
5. **(תיעוד — נסגר בגל זה)** ה‑classification של שלושת מצבי הייצוא
   (pre‑deploy / post‑deploy / fixed‑rendered) מתועד למעלה לפי ראיות.

**אין לבצע קוד/בדיקות בגל הזה — DOC‑ONLY. אלה המלצות ל‑Phases עתידיים
מבוקרים בלבד; אף red‑line ב‑AGENTS.md/CLAUDE.md לא נחצה.**
