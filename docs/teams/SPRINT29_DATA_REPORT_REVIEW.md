# Sprint-29 — Data / Supabase: Rendered Telegram Report Honesty Review (DOC-ONLY)

**Date:** 2026-05-18 · **Mode:** DOC-ONLY (no code, no schema, no migration).
**Live state re-verified from source:** HEAD `09dbec7`
("fix(phase-algo1): R-ALGO-2 recon money-truth fix + R-ALGO-3 L50 sample honesty").
**Inputs:** real Telegram exports `/tmp/tg_report_1.txt` (996 messages / 11,469 lines)
+ `/tmp/tg_report_2.txt` (431 / 4,515 lines), incl. embedded sentinel-bot sync logs.
**DATA-SENSITIVITY:** this committed doc is STRUCTURAL only — NO live NAV /
position / P&L value is reproduced. Numbers below are token-shapes, not figures.

> **The exports PREDATE today's deploy.** They were captured against the
> pre-`09dbec7` code (the buggy `c.get("net_pnl",0)` recon key and the
> un-disclosed "L50(50)" literal are both still *visible behavior* in the
> extracts). Every issue is classified **fixed-by-deployed / still-open /
> new** by re-verifying the **current** code at HEAD, not the extracts.

---

## 1. Rendered data-honesty surface table

| # | Surface (as the trader reads it) | What the export shows | Honest? | Current-code verdict |
|---|----------------------------------|-----------------------|---------|----------------------|
| H1 | **Footer** `ℹ️ מקור נתונים: Live/Cached … יש להתייחס לנתון כהערכה ולאמת מול IBKR לפני פעולה` | Present on every report-bearing message (portfolio, regime, health) | ✅ honest **and the body honors it** (H2–H5) | OK — not a blanket alibi; body carries its own per-value disclosures |
| H2 | **NAV freshness line** — manual/no-timestamp case `🟠 NAV $7,922 — אין timestamp (הוגדר ידנית)` | Shown in `/portfolio`, regime, health while NAV was hand-set | ✅ honest — explicitly says "no timestamp / set manually", NOT shown as live | OK — `engine_core.get_nav_with_freshness` D3 branch (`engine_core.py:1634`) |
| H3 | **NAV freshness line** — fresh-broker case `✅ ✅ NAV $7,934 — עודכן לפני 0.0ש׳` (doubled `✅ ✅`) | Doubled green glyph on broker-fresh NAV in **health report only** | ✅ honest (semantics correct); ⚠️ **cosmetic glyph-doubling** | OK-with-blemish — `bot_health.ok()` (`bot_health.py:54`) prefixes `✅` onto an already-`✅`-prefixed `freshness_label`. Same for `🔴 🟠` on the manual case (`bad()`). Pure cosmetics; freshness routing (`is_stale`/`is_critical`) is correct. **NEW (cosmetic, P3).** |
| H4 | **NAV value drift across messages** ($7,922 manual → $7,934 → $7,961 → $7,971 → $8,020 fresh) vs sync-log (`NAV updated: $7,934.27`, `$8,034.27`, XML `NAV=7970.79`) | Different NAV per message, each correctly tagged with its own freshness/age | ✅ honest — each figure is labelled with its true source+age; drift = real successive syncs, not contamination | OK — no figure is restated as exact across a stale boundary; manual→fresh transition is disclosed each time |
| H5 | **Open-R "snapshot" token** `• Open-R: +9.81R (snapshot — לא מאומת כעת)` (open-tasks card) | Shown on every task card; card header also `נתונים: חי 🟢` | ✅ honest — the R value is explicitly flagged "snapshot — not verified now" | OK — number shown but never asserted as verified truth |
| H6 | **Recon / PnL gap line** `מצב התאמה מול ברוקר: <band>. פער $X …` | **NOT present in either export's `חדר מצב`** (the recon `try/except: pass` block did not emit on the captured runs) | n/a in extract | **R-ALGO-2 — see §2.** The defect is the *number*, not the wording; fixed at HEAD. |
| H7 | **L50 / sample line (legacy block)** `שיעור הצלחה (50 אחרונות): 30%` | Export 1 `/portfolio` adaptive block — labelled "50 אחרונות" with **no true-N disclosure** | ❌ **false confidence in extract** | **R-ALGO-3 — fixed at HEAD (§3).** |
| H8 | **L50 / sample line (multi-window block)** `S9(9)=86 \| M21(21)=86 \| L50(50)=86` + `Win Rate — S9 (8): 50% \| L50 (8): 50%` | Export 2 — hardcoded `L50(50)` literal with only 8 real campaigns; sibling Win-Rate line *does* show true `(8)` | ⚠️ **partially misleading in extract** (literal `(50)` lies, `(8)` honest) | **R-ALGO-3 — fixed at HEAD (§3).** |
| H9 | **ALGO-vs-manual segregation in figures** | Position cards tag `🏷️ ALGO \| 🟠 מנוהל חיצונית`; `🤖 בקרת אשכול אלגו: חשיפה אלגו X%` separate; Win-Rate / heat / adaptive-risk computed off countable (EP/VCP) only; `סה"כ רווח צף` is the **floating** total (open positions, not realized ALGO drag) | ✅ honest — ALGO clearly segregated in every figure the trader acts on; ALGO P&L disclosed as its own cluster | OK — segregation holds where it must (AGENTS #8 / DEC-20260511-001 #8 intact in code); only the disclosed-and-labelled realized total ("(all)/(DB)", §3 of ALGO-Inv-1) carries ALGO — that line is **not in these `/portfolio` extracts** |
| H10 | **System Health** `🔴 🟠 NAV $7,922 — אין timestamp` + `⚠️ IBKR Sync — אחרון: —` + `Supabase — טרייד אחרון: 2026-05-07` | Health honestly down-grades to 🔴 and names every degraded input | ✅ honest — never paints a stale/manual state green | OK |

---

## 2. R-ALGO-2 — the silently-`0` recon money-truth bug

**Was the trader reading a wrong recon number?** On the recon surface, **yes,
pre-deploy.** The `חדר מצב` recon gap was
`NAV − (deposited + realized_DB_PnL + open_PnL)`, but the realized term was
`sum(c.get("net_pnl",0) …)`. `adaptive_risk_engine.compute_closed_campaigns`
emits realized PnL under **`total_pnl_usd`** and **never** `net_pnl`
(`adaptive_risk_engine.py:205`), so `net_pnl` matched no key ⇒ the realized
term was **always `0.0`** ⇒ the gap was inflated by the entire realized
closed-campaign P&L ⇒ a *false* "Balanced/Minor" or a *false* "Critical" band
could render on the phone, while the recon **wording** ("הסיבה לא אומתה …
דורש אימות ידני") stayed innocent — i.e. a wrong number presented inside an
honest-sounding sentence.

**Confirm deployed fix corrects the rendered value:** ✅ **YES.**
`telegram_portfolio.py:481` now reads
`sum(float(c.get("total_pnl_usd",0) or 0) for c in _closed_for_rec)` — the
producer's real key. The recon realized term now equals the dashboard oracle
`camp_df['pnl_usd'].sum()` quantity, so the rendered gap/band reflects truth.
Test-pinned: `tests/test_phase_algo1_recon_and_sample.py` proves the pre-fix
read was provably `0.0`, the post-fix sum equals the dashboard realized oracle,
and the classifier band now reflects truth. One-site key change; engine /
analytics / LOCKED-April git-diff empty (commit `09dbec7` stat).

> **Why it is not a visible wrong *number* in these two extracts:** the recon
> block is wrapped `try/except: pass` and did not emit on the captured
> `/portfolio` runs (no `מצב התאמה מול ברוקר` line anywhere in 16k lines).
> The defect was real on that surface in production; it is **fixed-by-deployed**.
> **Status: FIXED-BY-DEPLOYED. Severity (pre-deploy): HIGH, money-truth.**

---

## 3. R-ALGO-3 — "L50" false confidence on a risk-raise read-out

**Was the trader reading false confidence?** **Yes, pre-deploy** — visible in
*both* exports: `שיעור הצלחה (50 אחרונות): 30%` (Export 1) and `L50(50)=86`
(Export 2) with only 8–9 real closed campaigns. The `(50)` is a hardcoded
literal feeding the heat score that drives the risk-raise recommendation —
false confidence into a money decision. (The sibling `L50 (8)` Win-Rate line
was already honest, so the pre-deploy state was *partially* disclosed.)

**Confirm deployed fix:** ✅ **YES.** `telegram_formatters.py:43-86` adds
`_l50_true_sample()` + `_l50_sample_honesty_line()`, wired into **both**
display paths — the score line (`:250-255`) and the heat thermometer
(`:486-493`). When the true L50 sample `< 50` it appends
`⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: N/50 — <label>`, where `<label>` is
**reused verbatim** from the pre-existing `engine_core.get_sample_size_context`
(no invented UX, engine 0-diff). When `N ≥ 50` the helper returns `None` ⇒ the
existing literal is byte-identical (zero KPI change). Test-pinned in
`tests/test_phase_algo1_recon_and_sample.py` (W-A3). The literal `L50(50)` is
intentionally preserved for byte-identity, but it is **no longer the only
signal** — the honest qualifier now sits directly beneath it.
**Status: FIXED-BY-DEPLOYED. Severity (pre-deploy): MEDIUM, false-confidence.**

---

## 4. Fixed / Open / New summary

| ID | Surface | Pre-deploy in extract | Current code (HEAD `09dbec7`) | Sev | Class |
|----|---------|-----------------------|-------------------------------|-----|-------|
| **R-ALGO-2** | חדר-מצב recon gap/band | wrong (realized term silently `0`) | **FIXED-BY-DEPLOYED** — correct producer key, test-pinned | HIGH (money-truth) | bug-fix |
| **R-ALGO-3** | L50 / heat sample label | false confidence (`(50)`/"50 אחרונות") | **FIXED-BY-DEPLOYED** — honest `N/50` qualifier wired both paths | MED (false-conf) | honesty-fix |
| **H3** | doubled `✅ ✅` / `🔴 🟠` NAV glyph in health | cosmetic glyph-doubling | **STILL-OPEN (NEW, cosmetic)** — `bot_health.ok/bad` re-prefixes a glyph-prefixed `freshness_label` | P3 | cosmetic |
| **D-F2** | `migrations/005` stray `</content>` | n/a (not rendered) | STILL-OPEN (carried, non-prod) | P2 | hygiene |
| **D-F3** | NULL `pnl_usd` SELL → silent `$0`, no counter | n/a (latent) | STILL-OPEN (carried, latent) | P2 | latent |
| H1,H2,H4,H5,H9,H10 | footer / NAV / snapshot / segregation | honest | OK — body honors disclosures | — | — |

**P0/P1: none.** The two pre-deploy money/confidence defects on surfaces the
trader actually reads (R-ALGO-2 recon, R-ALGO-3 L50) are **closed by today's
deploy** and test-pinned. The only residuals are one **new cosmetic** glyph
double (P3, zero data-honesty impact — semantics are correct) and the two
carried non-production P2s from Sprint-28.

---

## למנכ״ל — בשפה פשוטה

**האם אפשר לבטוח שמה שהדו"ח בטלגרם מציג זה אמיתי וכן? כן — עם הסתייגות
אחת קטנה וקוסמטית בלבד.**

- **הדו"ח שאתה קורא בנייד היום — כן, כן ואמין.** הפוטר ("מקור נתונים:
  Live/Cached … אמת מול IBKR") הוא לא תירוץ-שמיכה: הגוף עצמו מתייג כל
  ערך — NAV ידני מסומן במפורש "אין timestamp (הוגדר ידנית)", Open-R
  במשימות מסומן "snapshot — לא מאומת כעת", ה-NAV הטרי מסומן עם הגיל
  האמיתי שלו. שום מספר fallback/ישן לא מוצג כאמת מדויקת.
- **שני הפגמים שהיו בצילומים — תוקנו אתמול ואומתו מול הקוד.**
  1. **מספר ההתאמה לברוקר (R-ALGO-2):** היה באג שאיפס בשקט את כל הרווח
     הממומש בחישוב → פער שגוי, פס "מאוזן/קריטי" שקרי. **תוקן** (מפתח
     אחד, `total_pnl_usd`), עם מבחן השוואה לדשבורד. *הצילומים מלפני
     התיקון, ובהם המספר הזה בכלל לא הופיע — הבאג היה אמיתי בפרודקשן
     ונסגר.*
  2. **"L50" עם 8–9 עסקאות (R-ALGO-3):** היה כתוב "L50(50)" כאילו יש
     50 — ביטחון-שווא בהמלצת העלאת הסיכון. **תוקן** — עכשיו מופיעה שורת
     יושר "מדגם נוכחי: N/50 — מדגם קטן מדי" בשני המסכים.
- **אלגו לא מזהם החלטות.** Win Rate / מד-חום / המלצת הסיכון מחושבים רק
  על EP/VCP; אלגו מוצג כאשכול נפרד ומתויג בכל כרטיס. אין דליפת אלגו
  למספר שאתה מקבל בו החלטה ידנית בצילומים האלה.
- **ההסתייגות היחידה (קוסמטית, לא אמת):** במסך ה-Health בלבד יש סמל
  כפול `✅ ✅` / `🔴 🟠` לפני שורת ה-NAV. זה כפילות אייקון בלבד —
  המשמעות (טרי/ישן/ידני) **נכונה**. לא מטעה, רק מכוער.

**שורה תחתונה:** כן — מה שהדו"ח מציג הוא אמיתי וכן. שני הפגמים האמיתיים
נסגרו אתמול ואומתו מול המקור. נשאר רק כתם ויזואלי אחד וזניח.

## מה צריך לעשות

1. **לא לגעת בשבוע זה במה שתוקן** — R-ALGO-2 / R-ALGO-3 סגורים, נעולים
   עם מבחנים. כל עריכה עתידית ל-`telegram_portfolio.py:481` או
   ל-`_l50_sample_honesty_line` חייבת הוכחת byte-identical על המסלול
   הנקי + מבחני `test_phase_algo1_recon_and_sample.py` ירוקים.
2. **H3 (קוסמטי, P3, NEW):** Phase תצוגה-בלבד עתידי קטן — להסיר את
   האייקון הכפול ב-`bot_health.py` (לתת ל-`ok/warn/bad` לזהות שה-
   `freshness_label` כבר נושא אייקון, או לפצל את האייקון מהטקסט במקור
   `engine_core.py:1613-1634`). אפס שינוי משמעות. לא דחוף — לא בעיית אמת.
3. **D-F2 / D-F3 (P2, carried, OUT):** ללא שינוי — backlog ממשל עתידי
   (היגיינת מיגרציה 005; מונה-גילוי ל-SELL עם `pnl_usd` ריק). Latent /
   לא-פרודקשן, כמו בספרינט-28.
4. **לאמת אחרי כל deploy עתידי:** להריץ `/portfolio` ולוודא ששורת
   `מצב התאמה מול ברוקר` מציגה פער שמתיישב עם הדשבורד (שמירה על תיקון
   R-ALGO-2), ושבמדגם <50 מופיעה שורת ה-`N/50` (שמירה על R-ALGO-3).
