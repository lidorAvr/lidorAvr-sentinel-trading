# Sprint-29 — Architecture: Structural Review FROM the Real Rendered Telegram Output (DOC-ONLY)

**Date:** 2026-05-18 · **Team:** Architecture (lead) · **Mode:** inference-only —
NO code, NO tests, NO commit. Symptoms read from the **actual rendered output**,
then traced back to a suspected render path by `file:line` re-read on disk.
**Live state:** branch HEAD = **`09dbec7`** ("fix(phase-algo1): R-ALGO-2 recon
money-truth fix + R-ALGO-3 L50 sample honesty"). Working tree clean.
**Inputs:** `/tmp/tg_report_1.txt` (995 MSG blocks) + `/tmp/tg_report_2.txt`
(430 MSG blocks) — real Telegram captures.
**Data-sensitivity:** STRUCTURAL only — no live NAV/position/P&L value is
reproduced here; only normalized shapes, variant counts and `file:line`.

> **Timeline anchor (critical):** the exports were captured against NAV/recon
> values that the **today** deploy `09dbec7` changes. Several symptoms below
> are therefore *exports-predate-deploy* artifacts — classified per-item as
> **fixed-by-deployed / still-open / new**.

---

## Verdict (one line)

**Is the system rendering the report cleanly/consistently? NO — not yet.** The
output is *honest* but visibly produced by **multiple un-deduplicated render
passes and two-layer icon ownership**. The single biggest structural smell is
**alert/report re-emission without effective idempotency** (a status-keyed
anti-spam gate that price-noise defeats), closely followed by a **double
status-glyph bug** where two render layers each prepend their own emoji.

---

## Structural symptoms → suspected root path → severity → status

### S29-1 · Alert state-flap re-spam (no effective idempotency) · HIGH · STILL-OPEN
**Symptom (real output):** in `tg_report_1.txt` the **same** campaign
`CAT_9409547470` Live Alert fires **5×** inside a ~65-line burst
(lines 3875/3895/3907/3919/3940), the status oscillating
`🟡 תקין אך במעקב → 🔥 Power → 🟡 → 🔥 → 🟡` on sub-1% price wiggles
(`$906→$902→$903→$901`). 116 Live Alerts for **9** distinct symbol+campaign
pairs in one capture; CAT alone 32×. 15 consecutive byte-identical MSG blocks
detected.
**Suspected root path:** `risk_monitor.py` anti-spam gate keys the dedup
memory on a `(symbol, state)`-class tuple with `STATE_ALERT_COOLDOWN`
(`risk_monitor.py:71-120`). A status **flip** is treated as a legitimate
"transition" and bypasses the cooldown, so a position straddling a
classification boundary re-alerts on every poll. The Sprint-14 persistence
(`8de481a`/`2308113`) fixed *cross-pull* survival, not *intra-window
oscillation* at a boundary. Effect = AGENTS.md #7 anti-spam intent partially
defeated by dedup-key granularity.
**Status:** **STILL-OPEN.** Untouched by `09dbec7` (which only edited
`telegram_portfolio.py` + `telegram_formatters.py`). This is the largest
visible structural smell. Not previously flagged in SPRINT28_ARCH_FINDINGS or
ALGO_INVESTIGATION_1 (R-ALGO-8 mentions per-position dedup as a *future*
state-machine, not this as-built flap). Effectively **NEW for this review**.

### S29-2 · Doubled status glyph — two render layers own the icon · MEDIUM · NEW
**Symptom (real output):** the System-Health NAV line renders as
`‏✅ ✅ NAV $… — עודכן לפני …` (doubled check; 9 distinct occurrences in file1,
1 in file2) and the manual-NAV line as **three** divergent forms for **one
state**: `‏⚠️ 🟠 NAV … אין timestamp`, `‏🔴 🟠 NAV … אין timestamp`, and the
same **without** the `‏` bidi prefix (`⚠️ 🟠 NAV …`). 4 normalized variants of
one concept.
**Suspected root path (traced):** `engine_core.py:1615/1617/1634` returns a
`freshness_label` that **already begins with its own emoji** (`✅ NAV…` /
`🟡 NAV…` / `🟠 NAV… (הוגדר ידנית)`). `bot_health.py:50-54` then wraps it again
via `bad()`/`warn()`/`ok()` which **prepend `🔴 ` / `⚠️ ` / `✅ `**
(`bot_health.py:25-27`). `ok(✅ NAV…) → ✅ ✅ NAV…`; `bad(🟠 …) → 🔴 🟠 …`;
`warn(🟠 …) → ⚠️ 🟠 …`. Two layers each believe they own the status glyph =
classic divergent/duplicated rendering-path defect. The missing/present `‏`
bidi prefix is a second, independent inconsistency on the same line family
(other footers — `מקור נתונים`, the Live-Alert header — are uniformly
prefixed: 94×/116× one variant, so the inconsistency is **localized** to the
NAV status line, confirming a single divergent builder, not a global RTL
issue).
**Status:** **NEW.** Dates to `8de481a` (2026-05-12); un-flagged by
Sprint-26/27/28 and ALGO_INVESTIGATION_1. Not in scope of `09dbec7`. No test
pins the double-prefix (`tests/test_bot_health.py` has no `✅ ✅` assertion).

### S29-3 · L50 two-path window-size divergence · MEDIUM · FIXED-BY-DEPLOYED (mitigated, not eliminated)
**Symptom (real output):** in `tg_report_2.txt` the **same report** prints
`S9(9)=86 | M21(21)=86 | L50(50)=86` (hardcoded literal **50**) immediately
above `Win Rate — S9 (8): 50% | L50 (8): 50%` (true N). 44 `L50(50)` literal
occurrences vs `L50 (8)/(9)/(7)` true-N occurrences in the same captures —
two code paths render the same L50 concept with contradictory window sizes
side-by-side. The heat thermometer path showed **no N at all**
(`L50 [🟢🟢🟢🟢⚪] 86`).
**Suspected root path:** `telegram_formatters.py:250` still emits the literal
`L50(50)` (= ALGO_INVESTIGATION_1 §2 / R-ALGO-3, `:204`/`:435` class).
**Status:** **FIXED-BY-DEPLOYED — partially.** `09dbec7` added
`telegram_formatters.py:49-86,251-…` which, when the true L50 sample `<50`,
**appends** an honest `⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: N/50` disclosure
(wired to the existing `engine_core.get_sample_size_context`). This closes the
*honesty* gap (the trader is now told the sample is partial). **But the
structural smell remains:** the `L50(50)` literal is **kept** beside the true
`L50 (N)` — the two-path divergence is now *disclosed*, not *unified*. The
exports predate the deploy so they show the pre-fix (un-disclosed) form;
post-deploy the contradiction is annotated, not removed. Record-only:
single-source the window-size token if a 4th L50 surface appears.

### S29-4 · Reconciliation single-number-but-two-derivations · HIGH · FIXED-BY-DEPLOYED
**Symptom (real output):** `tg_report_2.txt` shows the חדר-מצב recon line
`מצב התאמה מול ברוקר: פער מהותי. פער $190.29 …` (9×). Per
ALGO_INVESTIGATION_1 §1 the dashboard/master path renders a *different* gap
for the **same** state (the documented $510.51-vs-$190.29 class) — two code
paths, one concept, divergent numbers; the חדר-מצב side was the buggy
`c.get("net_pnl",0)`-always-`0.0` path (`telegram_portfolio.py:473` old).
**Suspected root path:** wrong dict-key in the חדר-מצב recon input.
**Status:** **FIXED-BY-DEPLOYED.** `09dbec7` changed
`telegram_portfolio.py:481` to `c.get("total_pnl_usd",0)` (verified in source,
with the R-ALGO-2 comment block `:473-481`), pinned by new
`tests/test_phase_algo1_recon_and_sample.py` (13). The exports predate the
deploy, so the `$190.29` they show is the **pre-fix** value; the structural
divergence root is closed in source (the residual closed-vs-all definitional
nuance is documented, not hidden — ALGO_INVESTIGATION_1 §1 caveat).

### S29-5 · Whole-report re-emission volume · LOW(structural) · STILL-OPEN(by-design-ish)
**Symptom:** the full חדר-מצב concentration report renders **41×** within 995
MSG blocks of one capture; the command-guide / main-menu / "מצב תיק" headers
recur 39-42× each. Much is legitimate (user re-invokes `/portfolio`), but the
sheer ratio + the S29-1 alert bursts indicate **no output-coalescing /
idempotency layer** between the scheduler, the live-alert path and the
on-demand path — three render entry points emitting overlapping content with
no shared "did we just send this?" gate.
**Suspected root path:** scheduler (`report_scheduler.py:_build_system_health`
et al.) + `risk_monitor` live path + `telegram_portfolio.handle_portfolio_room`
each render independently; no cross-path dedup. Same family as S29-1.
**Status:** **STILL-OPEN**, lower severity (mostly user-driven), but it
*amplifies* S29-1's visibility. Record-only unless paired with the S29-1 fix.

### S29-6 · `✅ Sentinel Bot מחובר` / standby banner repetition · LOW · STILL-OPEN
**Symptom:** the connect/standby banner + "סנכרון IBKR מתוזמן…" pair recurs
27× in file2 — fires on every (re)start/poll with no first-class
"already-announced this session" suppression.
**Status:** STILL-OPEN, cosmetic; same missing-idempotency family as S29-1/5.

---

## Cross-reference reconciliation

- **SPRINT28_ARCH_FINDINGS (S26-R1):** `telegram_bot.py` Supabase-read
  extraction — **confirmed still closed**; nothing in the exports indicates a
  regression there. S28-R1 (test-collection-order) is test-only and not
  observable in rendered output — out of scope here.
- **ALGO_INVESTIGATION_1:** R-ALGO-2 (recon) and R-ALGO-3 (L50) are the S29-4
  and S29-3 symptoms above; both addressed by `09dbec7` (R-ALGO-2 fully,
  R-ALGO-3 by disclosure). R-ALGO-8 (per-position dedup state machine) is the
  *governed-future* answer to S29-1 but the **as-built flap (S29-1) was not
  itself characterized from real output before** — this review adds that.
- **New / not previously flagged:** S29-1 (status-keyed flap re-spam as a live
  symptom) and S29-2 (double status-glyph two-layer ownership).

---

## למנכ״ל — בשפה פשוטה

**האם המערכת מציגה את הדו"ח בצורה נקייה ועקבית? עדיין לא לגמרי.** הדו"ח *כן
ישר* (אומר את האמת על נתונים חלקיים), אבל מהפלט האמיתי רואים שהוא מיוצר
בכמה "צינורות הדפסה" שלא מתואמים ביניהם.

- **הריח המבני הגדול ביותר:** **ספאם התראות.** אותה התראה על אותה פוזיציה
  (CAT) נשלחה 5 פעמים ברצף תוך דקות, כי הסטטוס "ריצד" בין 🟡 ל-🔥 על תזוזת
  מחיר זעירה. מנגנון מניעת-הכפילות מזהה שינוי-סטטוס כ"אירוע חדש" ולכן עוקף את
  ההשהיה. זה מציף אותך בהודעות וקובר את ההתראות החשובות. **פתוח — לא נגעו בו
  בהעלאה של היום.**
- **באג ויזואלי:** שורת ה-NAV בבריאות-המערכת יוצאת עם **שני סימני ✅✅** (ובמצב
  ידני עם 🔴🟠 או ⚠️🟠), כי שתי שכבות קוד שונות כל אחת מוסיפה אייקון משלה לאותה
  שורה. זו אותה תופעה ביסוד — שני מסלולים מציירים את אותו דבר אחרת. **חדש,
  לא דווח קודם.**
- **מה כבר תוקן:** באג מספר ההתאמה ($510 מול $190) ובעיית ה-L50 (שכתב "50"
  כשיש 9) — **שניהם טופלו בהעלאה של היום** (`09dbec7`). היצוא שבדקנו צולם
  *לפני* ההעלאה, לכן הוא עדיין מראה את המצב הישן. ה-L50 תוקן בדרך של *גילוי*
  ("מדגם חלקי N/50") — האמת נאמרת, אבל ה"50" המטעה עדיין מודפס לצידה.

**מסקנה:** המערכת ישרה אבל "רועשת". הניקיון המבני הבא הוא **דדופ אמיתי
להתראות**, ואחריו תיקון ה-✅✅. הנתונים — תקינים אחרי ההעלאה של היום.

## מה צריך לעשות

1. **S29-1 (הכי דחוף, founder-gated, HIGH):** להחליף את מפתח הדדופ מ-
   `(symbol, status)` לדדופ עם היסטרזיס/דביקות-מצב — שינוי-סטטוס לא יפתח
   מחדש את חלון ההשהיה אם הוא חוזר אחורה תוך X דקות. זהו בדיוק תחום R-ALGO-8;
   מומלץ Phase ממשל נפרד עם טסט-רגרסיה ל"ריצוד CAT" (כיום אין כיסוי לדפוס הזה).
2. **S29-2 (LOW-MED, בטוח, אדיטיבי):** לקבוע **בעלות יחידה** על אייקון
   הסטטוס — או ש-`engine_core` יחזיר תווית בלי אייקון ו-`bot_health` יוסיף, או
   הפוך. + לאחד את קידומת ה-bidi `‏` בשורת ה-NAV. טסט קצר ש-`✅ ✅` לעולם לא
   מודפס.
3. **S29-3 (record-only):** ה-L50 מגולה — מספיק להיום. אם יופיע מקור L50
   רביעי, לאחד את אסימון גודל-החלון למקור-אמת יחיד.
4. **S29-4:** סגור בקוד (`09dbec7`). אין פעולה — רק לוודא שהיצוא הבא (אחרי
   ההעלאה) כבר מראה מספר התאמה אחד עקבי בין דשבורד לחדר-מצב.
5. **S29-5/6 (record-only):** אם מטפלים ב-S29-1, להוסיף שכבת
   "כבר-שלחנו-זאת" משותפת לשלושת מסלולי ההדפסה (scheduler / live / on-demand).

---

## Explicitly OUT-OF-SCOPE (not re-litigated)

Engine/analytics math & byte-locked files (untouched by `09dbec7`,
`--stat` confirms only `telegram_portfolio.py`/`telegram_formatters.py`+tests);
docker-compose service command (`telegram-bot: python3
telegram_bot_secure_runner.py` intact); admin/dev-PIN gates; the dashboard
recon derivation itself (data-team owned — only its *divergence symptom* noted
via ALGO_INVESTIGATION_1); S28-R1 test-collection hygiene (not output-visible).

## Recommendation

Founder default: **S29-1 is the one structural fix worth scheduling next**
(governed Phase, founder-gated, HIGH, R-ALGO-8 family) — it is the dominant
smell in the real output. S29-2 is a small, safe, additive cleanup that can
ride alongside. S29-3/4 are handled by today's deploy (3 by disclosure, 4
fully). No rewrite; small-step + tests, per CLAUDE.md.
