# SPRINT-29 — MARK · The system judged against the ACTUAL Telegram output the trader received (DOC-ONLY, NO code)

**Owner:** Mark (methodology & gate lead). **Date:** 2026-05-18.
**Target:** the *rendered* product — `/tmp/tg_report_1.txt` (996 msgs) +
`/tmp/tg_report_2.txt` (431 msgs) — judged against my doctrine
(`ALGO_TEAM_CHARTER.md` §Doctrine ⟨memo⟩, `ALGO_INVESTIGATION_1.md`,
`SPRINT28_MARK_FINDINGS.md`, `AGENTS.md`, `CLAUDE.md`).
**Live code cross-checked at HEAD `09dbec7`** (Sprint-27 + Phase ALGO-1
`R-ALGO-2`/`R-ALGO-3` deployed).

**Method note (honesty):** I judged the message the trader *actually saw on
the phone*, then traced each gap to current source to classify
**fixed-by-deployed / still-open / new**. The exports straddle the deploy:
the final cluster (`מעודכן: 18/05 06:21`, `דוח IBKR 2026-05-18`) carries the
**new L50 honesty line** (post-`R-ALGO-3`) yet *also still* the **two-number
recon contradiction** — i.e. the export captured the system mid-/pre-deploy
on the recon path. I treat the rendered defect as the evidence and the code
at `09dbec7` as the truth for fixed/open.

---

## Per-area verdict — rendered vs doctrine

### 1. ALGO observe-only & segregation — AS RENDERED — ✅ HOLDS (doctrine-correct)
This is the strongest area in the live output.
- HOOD/PLTR/TSLA ALGO cards render `🟠 מנוהל חיצונית`, `סטופ: מנוהל חיצונית`,
  `פיקוח: מידע בלבד — Sentinel אינה מנהלת יציאות אלגו`.
- The ALGO Broken **Live Alert** (`HOOD … סטטוס: 🔴 Broken` →
  `פעולה: מנוהל חיצונית — בקרה בלבד`) issues **no manual exit** — exactly
  DEC-20260511-001 #8 / charter §1.
- The ALGO **Giveback** (`TSLA … כשל הגנת רווח … פיקוח בלבד — Sentinel אינה
  מנהלת יציאות אלגו`) correctly suppresses the cut/tighten instruction that
  the manual EP/VCP Giveback *does* give (`PWR … לשקול הדקת סטופ / מימוש
  חלקי`). Manual vs ALGO action language is correctly bifurcated as rendered.
- The dedicated ALGO block (`🤖 ALGO — מנוהל חיצונית. בקרה בלבד … אינו נספר
  בסטטיסטיקה … מה ש-Sentinel רואה — לא הוראת פעולה`) plus
  `נתוני ALGO = בק-טסט … לא טראק-רקורד חי` is precisely the sample/segregation
  honesty the memo demands.
- The weekly report renders ALGO closed separately and non-counted:
  `🔭 3 קמפייני ALGO נסגרו … ממומש לא-מאומת: $… (לא נספר ב-edge)`, and the
  open-book splits `דיסקרציוני` vs `ALGO (פיקוח בלבד · לא הוראה)`. WR/Exp/PF
  exclude ALGO/DATA_INCOMPLETE (period-probe shows every ALGO row
  `bucket=ALGO_OBSERVED · נספר=לא`). **Verdict: doctrine met, as rendered.**

### 2. Broker-recon truth (R-ALGO-2) — RENDERED CONTRADICTION — FIXED-BY-DEPLOYED
**As rendered, the trader saw two different recon numbers for the same state
in the same export:** חדר-מצב = `פער מהותי. פער $190.29`; the
master/adaptive-risk summary = `פער נתונים קריטי. פער $510.52`. This is the
memo's exact "$510 vs $190" money-truth defect, *on the phone*, including a
band disagreement (`מהותי` vs `קריטי`). **Confirmed fixed in deployed code:**
`telegram_portfolio.py:481` now sums the correct producer key
`c.get("total_pnl_usd", 0)` (was the no-match `"net_pnl"` → silent `0.0` that
dropped ALL realized PnL). The rendered contradiction is a **pre-/mid-deploy
artifact**. **Residual (honest disclosure, not a regression):** dashboard
sums all `pnl_usd` incl. open-partial/ALGO vs חדר-מצב `compute_closed_campaigns`
closed-only — a small definitional gap that remains and must stay disclosed,
per `ALGO_INVESTIGATION_1` §1. **Verdict: the dominant defect is fixed; verify
on the next post-deploy export that the two numbers/bands converge.**

### 3. Sample / L50 honesty (R-ALGO-3) — PARTIALLY FIXED-BY-DEPLOYED + NEW residual
The old export shows the lie: `S9(9)=86 | M21(21)=86 | L50(50)=86` with no
caveat. The post-deploy cluster shows the **new honest line**:
`⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: 9/50 — סטטיסטיקה ראשונית בלבד — אין
לאשר הגדלת סיכון אגרסיבית` (and `7/50`) — confirmed in code
(`telegram_formatters.py:85`, wired to `engine_core.get_sample_size_context`).
**This is a real, deployed honesty win — the disclosure now reaches the phone.**
**NEW (still-open, presentation):** the deployed fix is *additive only* —
`telegram_formatters.py:250` still hard-codes the literal `L50(50)`. So the
rendered message now reads `… | L50(50)=92` immediately followed by
`⚠️ … מדגם נוכחי: 9/50` — a **self-contradiction on adjacent lines**. The
caveat rescues honesty, but a disciplined eye still sees a fictional "50" in
the headline score line. Recommend a follow-up to render `L50(N)` truthfully
(B1 class, presentation-only, byte-identical when N≥50).

### 4. Risk-raise discipline (R-ALGO-1 / R-ALGO-6) — RENDERED VIOLATION — STILL-OPEN (HIGH)
**This is the gap that matters most for a disciplined trader.** In a single
rendered message the trader was offered:
`מצב התאמה מול ברוקר: פער נתונים קריטי. פער $510.52` **and four lines below**
`⬆️ … סיכון מוצע: 0.85% ($67 לעסקה)` (raise 0.60→0.85) — *while two ALGO
positions render `🔴 Broken`*. The חדר-מצב variant pairs `פער מהותי $190.29`
with the same `0.85%` proposal. My doctrine is explicit: **do NOT raise risk
while broker-recon is unclean OR ≥1 ALGO position is Broken OR sample too
small ("clean truth before aggressiveness").** The deployed scope was
`R-ALGO-2`+`R-ALGO-3` only; the 4-gate is **not** shipped. As rendered the
report still actively *invites* the forbidden risk-raise. **STILL-OPEN,
highest-priority.**

### 5. Probation / Kill-Switch / Re-entry / Risk-Breach-Review (R-ALGO-8) — STILL-OPEN
Searched both exports end-to-end: **no `Kill-Switch`, no `Probation`/`השעיה`,
no `Algo Risk Breach Review`, no `No Re-entry Boost`** string anywhere. HOOD
renders `🔴 Broken` repeatedly across many reports and PLTR renders `🔴 Broken`
at `R חשבון: -0.39R`; neither ever surfaces the memo's per-symbol probation,
the `0.50R-` Kill-Switch threshold, or the Risk-Breach-Review alert. The only
"no-add" strings (`לא להוסיף. שקול צמצום`, `🚫 לא להוסיף לפני בסיס חדש`) are
the **generic manual EP/VCP Yellow-Flag** path — not ALGO probation. The
state machine my doctrine demands **does not exist as rendered**. STILL-OPEN
(charter R-ALGO-8, observe-only, founder-gated — out of the shipped scope).

### 6. NAV / freshness honesty + the doubled "✅ ✅" glyph — MIXED
- NAV value reads canonical (`account_state.load`), NAV-Unify intact; the
  weekly/חדר-מצב footer (`ℹ️ מקור נתונים: Live/Cached … יש להתייחס לנתון
  כהערכה`) and `נתונים: חי 🟢 · מעודכן: 18/05 06:21` are honest. No
  fallback-as-truth NAV in the rendered figures. ✅
- **The doubled glyph is REAL and STILL-OPEN (NEW, LOW/cosmetic):** System
  Health renders `✅ ✅ NAV $7,921 — עודכן לפני 8.8ש׳`. Root cause confirmed:
  `bot_health.py:54 ok(nav_info["freshness_label"])` prepends `✅ ` (`:25`)
  onto a label that **already** begins with `✅` (`engine_core.py:1617`).
  **Not** a fallback-as-truth breach — 8.8h is genuinely fresh
  (`NAV_STALE_HOURS=24`), so green is methodologically correct; this is a
  pure double-prefix presentation bug. Untouched by the ALGO-1 deploy
  (not in scope). It does not distort a number but it is sloppy on a *health*
  panel and erodes trust in the panel's own self-report. Recommend a one-line
  de-dup (don't `ok()`-wrap an already-iconned label).

### 7. The W3 "🧭 מה עכשיו?" mentor line — AS RENDERED — ✅ SHARP, not noise
Every rendered instance is a faithful, non-contradictory summary of a signal
the surface already computes:
- חדר-מצב: `🧭 מה עכשיו? 2 פוז' דורשות החלטה: HOOD, PLTR — ראה כרטיסים למטה.`
  — names the exact Broken ALGO symbols and points down; correct and
  actionable.
- Weekly: `🧭 מה עכשיו? תוצאה מעורבת — אין דרישה דחופה; עבור על הקמפיינים
  בדוח.` — matches the `שבוע מעורב` verdict; no false all-clear.
It leads with the disciplined-trader question and never over-claims. **Keep
it.** *One caveat consistent with §4:* on the message where it says "no urgent
demand", the SAME message proposes a risk-raise under a critical recon gap —
the mentor line is locally correct but the page it sits on still contains the
§4 violation. The fix belongs in §4 (gate the raise), not in this line.

---

## Fixed / Open / New — summary

| Area | Seeded flag | Rendered evidence | Code @ `09dbec7` | Verdict |
|---|---|---|---|---|
| ALGO observe-only / segregation | charter §1, AGENTS #8 | observe-only on every ALGO card/alert/Giveback | unchanged, intact | ✅ holds |
| R-ALGO-2 recon two-number | confirmed bug | `$190.29` חדר-מצב vs `$510.52` master, same export | one-key fix shipped (`telegram_portfolio.py:481`) | **FIXED-by-deployed** (verify next export; residual closed-vs-all disclosed) |
| R-ALGO-3 L50 honesty | confirmed | new `⚠️ … מדגם נוכחי: 9/50` line now on phone | wired (`telegram_formatters.py:85`) | **FIXED-by-deployed** (disclosure) |
| R-ALGO-3 residual literal | — | `L50(50)=92` still printed above the caveat | `:250` literal unchanged | **NEW / still-open** (presentation, B1) |
| R-ALGO-1/6 risk-raise gate | ⟨memo⟩ | `0.85%` proposed under `פער קריטי $510.52` + 2 ALGO Broken | no 4-gate; Heat-only | **STILL-OPEN — HIGHEST** |
| R-ALGO-8 probation/Kill-Switch | ⟨memo⟩ | no probation/Kill-Switch/Breach string anywhere | not implemented | **STILL-OPEN** |
| Doubled `✅ ✅` NAV glyph | prompt | `✅ ✅ NAV $7,921 …` in System Health | `bot_health.py:54`+`:25` double-prefix | **NEW / still-open** (LOW/cosmetic, not honesty) |
| Empty `טריגר:` on ALGO Live Alert | observation | `טריגר:` blank on HOOD Broken alert | not in scope | minor/still-open (cosmetic) |
| W3 "מה עכשיו?" | Sprint-27 surface | accurate, actionable, no false all-clear | unchanged | ✅ keep |

---

## Gaps that matter for a disciplined trader (ranked)

1. **Risk-raise offered while data is unclean / ALGO Broken (§4).** The single
   most dangerous rendered behavior: the report literally proposes 0.60→0.85
   next to "critical data gap" and 2 Broken ALGO. This trains exactly the
   wrong reflex. R-ALGO-1/6 (4-gate) must gate the raise on
   recon-clean ∧ no-Broken-ALGO ∧ sample-OK.
2. **No probation / Kill-Switch state as rendered (§5).** HOOD/PLTR sit
   `Broken` for many cycles with only a generic "externally managed" line.
   Observe-only is correctly held — but observe-only ≠ silent. The trader
   needs the rendered `Algo Under Watch` / `0.50R- Risk-Breach-Review` *alert*
   (no manual exit) the memo requires.
3. **L50 headline still lies above its own caveat (§3).** Honesty is rescued
   by the new line, but a fictional "(50)" still prints — finish the job:
   render the true N in the score line too.
4. **Doubled `✅ ✅` (§6) — cosmetic but on the health panel** that exists to
   make the trader trust the system; a self-contradicting glyph there is a
   poor look. One-line fix.

---

## למנכ״ל — חוות דעת מארק (שפה פשוטה)

מנכ״ל, הפעם לא בדקתי את הקוד — בדקתי את ההודעות **שאתה באמת קיבלת בנייד**, מול
השיטה שלי.

**האם הדוח שאתה מקבל משרת את השיטה? חלקית — לא עדיין במלואו.**

מה **טוב ואמיתי**: ההפרדה של אלגו עובדת מצוין על המסך — כל כרטיס/התראת אלגו
כתוב "מנוהל חיצונית, פיקוח בלבד", Sentinel לא מוציאה אותך מאלגו, ואלגו לא נספר
בסטטיסטיקה. גם שורת **"🧭 מה עכשיו?"** חדה, נכונה, ולא רעש. שני באגים שזיהינו
כבר **תוקנו ונפרסו**: (1) שני מספרי ההתאמה לברוקר — בייצוא ראית שני מספרים
שונים לאותו מצב; בקוד החי זה תוקן (שורה אחת). (2) ה-"L50" — עכשיו מופיעה בנייד
שורת אזהרה כנה "מדגם נוכחי: 9/50 — אין לאשר הגדלת סיכון אגרסיבית". זה בדיוק
מה שביקשתי.

מה **עדיין פתוח ומסוכן**: בדוח שאתה מקבל המערכת **מציעה להגדיל סיכון
(0.60%→0.85%) בדיוק כשהיא בעצמה כותבת "פער נתונים קריטי" ושתי פוזיציות אלגו
"שבורות"**. זו ההפרה החמורה ביותר מול השיטה שלי — "אמת נקייה לפני אגרסיביות".
בנוסף, אין בנייד שום מנגנון השעיה/Kill-Switch ל-HOOD/PLTR — הן "שבורות" שוב
ושוב ומקבלות רק שורה גנרית. ועוד פינה קוסמטית: ב-System Health כתוב `✅ ✅` כפול
על שורת ה-NAV (לא טעות בכסף — סתם כפילות מכוערת במסך שאמור לבסס אמון).

**שורה תחתונה:** הליבה ישרה, ההפרדה מצוינת, שני תיקונים נפרסו — אבל הדוח עדיין
*מזמין* אותך להעלות סיכון כשאסור. עד שזה ייסגר, הדוח לא משרת את המשמעת שלי
במלואו.

## מה צריך לעשות

1. **תיקון #1 (הכי דחוף, money-affecting):** שער 4-השערים על העלאת הסיכון
   (`R-ALGO-1`/`R-ALGO-6`) — לא להציע 0.85% כש: פער-ברוקר לא נקי / יש פוזיציית
   אלגו "שבורה" / מדגם קטן מדי. Phase ממשל נפרד, founder-gated, byte-identical
   כשכל השערים ירוקים.
2. **תיקון #2:** מכונת ההשעיה/Kill-Switch ל-HOOD/PLTR (`R-ALGO-8`) — התראה
   בלבד, **ללא יציאה ידנית** (observe-only נשמר), עם dedup אנטי-ספאם.
3. **תיקון #3 (קל, B1):** להסיר את ה-"L50(50)" הפיקטיבי משורת הציון עצמה —
   להציג את ה-N האמיתי גם שם (זהה בית-לבית כש-N≥50).
4. **תיקון #4 (קוסמטי, שורה אחת):** לבטל את ה-`✅ ✅` הכפול ב-`bot_health.py`.
5. **אימות:** על הייצוא הבא שאחרי הפריסה — לוודא ששני מספרי/הבנדים של ההתאמה
   לברוקר התכנסו (R-ALGO-2 נפרס; השארית "סגור מול הכל" נשארת מגולה, לא מוסתרת).
