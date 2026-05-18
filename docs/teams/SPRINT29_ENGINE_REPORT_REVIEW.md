# Sprint-29 — Engine Report-Review: are the NUMBERS the trader sees correct? (DOC-ONLY, NO code)

**Date:** 2026-05-18 · **Reviewer:** Engine team lead
**Live state:** HEAD `09dbec7` (`fix(phase-algo1): R-ALGO-2 recon money-truth fix + R-ALGO-3 L50 sample honesty`), clean tree.
**Inputs:** `/tmp/tg_report_1.txt` (996 lines of KPI extract scope), `/tmp/tg_report_2.txt` (431 lines of KPI extract scope).
**Method:** every rendered KPI re-derived from SOURCE at HEAD `09dbec7` (`analytics_engine.py`, `adaptive_risk_engine.py`, `engine_core.py`, `report_renderer.py`, `telegram_portfolio.py`, `telegram_formatters.py`) and cross-checked vs `docs/teams/ALGO_INVESTIGATION_1.md` (R-ALGO-2/3) and `docs/teams/SPRINT28_ENGINE_FINDINGS.md`. LOCKED April + ALGO-1 tests re-run live.

> **Data-sensitivity:** structural only. Number-CLASSES and relationships described; the founder's live NAV / P&L / position / recon values are NOT copied into this committed doc.

---

## 0. Headline verdict

The **engine math is correct** — every formula re-derived clean, LOCKED April byte-identical, ALGO-1 changed **zero engine numbers** (proven below). **BUT the exports were rendered BEFORE today's ALGO-1 deploy**, so two surfaces in the extracts show **stale/now-superseded numbers**, and several pre-existing **presentation contradictions** remain live at HEAD (R-ALGO-3 fix is additive, did NOT correct the lying literal). One worst issue: the on-phone reconciliation number in the exports is the **known-wrong R-ALGO-2 value** — that specific defect is **FIXED by the deployed HEAD**, but the *export the user is looking at* still shows the wrong one.

---

## 1. Rendered-number → correct? table

| # | Rendered KPI (class) | Where (source) | Correct? | Fixed / Open / New | Sev |
|---|---|---|---|---|---|
| 1 | **Broker-recon gap** ("פער מהותי. פער $X") in חדר-מצב | `telegram_portfolio.py:472-490` → classifier `:484` | **Export WRONG** (the value shown is the R-ALGO-2 buggy figure: realized closed-campaign PnL silently dropped to 0.0, gap understated) | **FIXED-by-deployed** — HEAD `09dbec7` reads `c.get("total_pnl_usd",0)` (`telegram_portfolio.py:481`), so the LIVE recon now equals the dashboard oracle (`dashboard.py:424`). Export predates fix. | **HIGH (money-truth)** |
| 2 | **Heat score-line** `S9(9)=… \| M21(21)=… \| L50(50)=…` | `telegram_formatters.py:250` (hardcoded literals) | **Misleading** — `(9)/(21)/(50)` are hardcoded, NOT the true sample. With ~9 (or fewer) disc campaigns, `[:50]` of N<50 = N; "L50(50)" asserts a 50-sample that does not exist | **STILL-OPEN at HEAD** — R-ALGO-3 fix only *appends* a disclosure line when true L50 sample <50; it does **not** correct the misleading `L50(50)` literal itself. Disclosure absent in these (pre-deploy) exports. | MED |
| 3 | **L50 / S9 sample contradiction same block**: score line says `S9(9)…L50(50)` but next line `Win Rate — S9 (8): 50% \| L50 (8): 50%` (also seen as `(9)…(9)`) | score `:250` vs WR `:262-264` / `:498-500` | **Internally contradictory as rendered** — both lines correct *individually* (`s9_stats["n"]`, `l50_stats["n"]` are the TRUE n; the score line's `(9)/(50)` are fictional literals). The contradiction is the literal vs the true-n on adjacent lines. | **STILL-OPEN at HEAD** (same root as #2; fix is additive only) | MED |
| 4 | **Heat score format inconsistency**: `(ציון: 30%)` / `43%` / `33%` in report_1 vs `(ציון: 100/100)` / `92/100` in report_2 — SAME metric class, two formats; `%` form is wrong (it is a 0-100 index, not a percentage) | current code `telegram_formatters.py:243` emits `/100`; the `%` form is from an OLDER code state at export time | **report_1 form WRONG label** (`%` on a non-percentage); report_2 `/100` correct. Confirms report_1 is a much older export. | **FIXED-by-deployed** (the live `/100` form at `:243` is correct; the `%` renderer no longer exists in tree) | LOW |
| 5 | **Win-rate label collision**: "מינרביני: שיעור הצלחה 25%" vs adaptive "שיעור הצלחה (10 אחרונות): 30%" in the SAME portfolio block | Minervini WR vs `recent_10_wr` (`adaptive_risk_engine.py:546`) | **Both correct but ambiguous** — different denominators (countable WR vs S9 disc-only window), both labeled "שיעור הצלחה" with no scope disambiguation | **STILL-OPEN** (pre-existing presentation; not ALGO-1 scope) | LOW |
| 6 | **Open-R per position** ("Open R (צף): -0.5R … Target Risk Base") | `engine_core` compute_position_state Open-R path | **Correct** — values consistent with Target-Risk-Base label; ALGO positions correctly flagged "מנוהל חיצונית / מידע בלבד" (observe-only holds) | n/a | — |
| 7 | **Giveback R math** ("שיא: 1.67R → נוכחי: 0.85R / ויתור: 0.82R (49% מהשיא)") | risk_monitor giveback path | **Correct** — `1.67−0.85 = 0.82`; `0.82/1.67 = 49%`. All sampled giveback alerts (25%, 22%, 15%, 20%…) recompute exactly. Internally consistent. | n/a | — |
| 8 | **Giveback $ (portfolio summary)** ("סיכון ויתור רווח צף (Giveback): $X") | `telegram_portfolio` summary | **Correct, snapshot** — a floating live-price-derived figure; varies sample-to-sample (e.g. $47→$64→$94 across runs), correctly labeled "צף". Not asserted as exact. | n/a | — |
| 9 | **Weekly/Monthly KPIs** `Realized PnL $+0 \| Net R +0.00R \| Expectancy +0.00R \| PF 0.00` for "0 campaigns closed" period | `analytics_engine` aggregate / `report_renderer` | **Correct & honestly disclosed** — period has 0 closed campaigns ("✅ 0 קמפיינים נסגרו… אין נתוני ביצועים ממומשים"); zeros are the right answer and the open-book line is separately shown. WR/Exp correctly exclude ALGO/incomplete (AGENTS.md #8). | n/a | — |
| 10 | **ALGO cluster figures** ("חשיפה אלגו: X% מהקרן", "✅ ALGO Positions — 5 סמלים") | telegram_portfolio ALGO block | **Correct & segregated** — ALGO exposure shown as its own cluster line; does NOT contaminate Win Rate / Expectancy / PF / heat / risk-raise (verified `adaptive_risk_engine.py:452-458,480-484`; `engine_core.is_stat_countable`). DEC-20260511-001 #8 holds in code. | n/a (partial total-leak per ALGO_INV §3 unchanged; disclosed, not silent) | — |
| 11 | **NAV** ("NAV $7,9XX — אין timestamp (הוגדר ידנית)" / "עודכן לפני 0.0ש׳") | NAV config | **Correctly disclosed as fallback** — manual/no-timestamp NAV is explicitly badged as estimate-not-live, with the IBKR-verify footer on every message. Honest per CLAUDE.md / AGENTS.md #1. | n/a | — |

---

## 2. Fixed / Open / New summary

- **FIXED-by-deployed (confirmed in current code at HEAD `09dbec7`):**
  - **#1 recon gap** — `telegram_portfolio.py:481` now reads the correct producer key `total_pnl_usd`; the buggy `net_pnl`→always-0.0 path is gone. The LIVE on-phone recon number is now correct (matches dashboard). *The exports still show the old wrong value because they predate the deploy.*
  - **#4 heat `%` label** — the live renderer emits `ציון: X/100` (`telegram_formatters.py:243`); the misleading `%` form seen in report_1 no longer exists in the tree.

- **STILL-OPEN at HEAD (live now):**
  - **#2 / #3** — the score line literal `S9(9) | M21(21) | L50(50)` is **still hardcoded** (`telegram_formatters.py:250`). R-ALGO-3's fix is purely *additive* (appends an honest "מדגם נוכחי: N/50" line **only when true L50 sample <50**); it does **not** rewrite the lying `(50)` literal, so the internal contradiction between the score line and the true-n Win-Rate line persists on the live surface. (The new disclosure does at least flag small samples — partial mitigation.)
  - **#5** dual "שיעור הצלחה" with different denominators, no scope tag — pre-existing, not ALGO-1 scope.

- **NEW (Sprint-29):** none. No new numeric defect introduced. Every issue is either fixed-by-deployed or a pre-existing presentation gap already triaged in ALGO_INVESTIGATION_1.md (R-ALGO-3 / R-ALGO-4).

- **Invariants re-confirmed (all HOLD):**
  - LOCKED April regression re-run live ⇒ **2 passed** (8 campaigns / +$180.49 / WR .375 / PF 2.6262 / excl 2). Byte-identical.
  - ALGO-1 phase test `tests/test_phase_algo1_recon_and_sample.py` ⇒ **13 passed** (recon-key parity, L50 honesty).
  - Sprint-22/23/24 + Sprint-27/28 invariants intact; ALGO observe-only & segregation unchanged; ALGO-1 touched only `telegram_portfolio.py` + `telegram_formatters.py` + new tests (engine_core / analytics_engine / adaptive_risk_engine / LOCKED fixture / byte-lock baselines / docker-compose / secure_runner = **0-diff**). **ALGO-1 changed ZERO engine numbers — confirmed.**

---

## 3. The one worst issue

**#1 — the broker-reconciliation gap in חדר-מצב** (the screen the trader reads daily on the phone). In the exports it shows the **R-ALGO-2 wrong value** (realized closed-campaign PnL silently zeroed → understated/false-band gap — could read "balanced/minor" when there is a real gap, or the wrong "material/critical"). **Status: FIXED by the deployed HEAD `09dbec7`** (single-key fix `net_pnl`→`total_pnl_usd`, `telegram_portfolio.py:481`, pinned by a new parity test). **Caveat:** the exports were captured *before* this deploy, so the recon number in the screenshots is the OLD wrong one — anyone reading those specific exports is reading a wrong number that the live bot no longer produces. A residual closed-vs-all definitional nuance (ALGO_INV §1) remains and is disclosed, not hidden.

---

## למנכ״ל — בשפה פשוטה

**האם המספרים שאתה רואה בדוח אמינים? כן — עם הסתייגות אחת חשובה לגבי הצילומים שבידך.**

- **המנוע עצמו תקין.** כל חישובי הכסף — רווח/הפסד, R, אחוז הצלחה, תוחלת, Profit Factor, NAV, חיתוך בירידה, הפרדת אלגו — נבדקו משורת-הקוד ויצאו נכון. הרגרסיה הנעולה של אפריל יצאה **בדיוק אותו דבר**. העבודה של היום (ALGO-1) **לא הזיזה אף מספר מנוע** — הוכח.
- **המספר הכי בעייתי — "ההתאמה לברוקר" בחדר-מצב — כבר תוקן בקוד החי.** עד היום הוא הציג מספר שגוי (כל הרווח מהעסקאות הסגורות התאפס בשקט). **ההפצה של היום מתקנת את זה.** אבל שים לב: **הצילומים שבידך צולמו לפני התיקון** — לכן בצילומים האלה המספר עדיין השגוי הישן. בבוט החי כעת המספר כבר נכון.
- **עדיין פתוח (תצוגתי, לא כסף):** שורת הציון עדיין כותבת "L50(50)" גם כשאין 50 עסקאות — היא סותרת את שורת אחוז ההצלחה שמתחתיה שמראה את המספר האמיתי. תיקון ה-L50 של היום רק *הוסיף* שורת אזהרה כשהמדגם קטן — הוא לא תיקן את הכותרת המטעה עצמה. זה לא משפיע על כסף, רק על אמון בקריאה.
- **אלגו, NAV, Giveback — תקינים ומגולים נכון.** אלגו לא מזהם את הסטטיסטיקה; NAV ידני מסומן בבירור כהערכה; חישוב ה-Giveback מדויק.

**שורה תחתונה: סמוך על המספרים בבוט החי. אל תסמוך על מספר ה"התאמה לברוקר" בצילומים הישנים — הוא כבר לא המספר שהמערכת מציגה.**

## מה צריך לעשות

1. **לבדוק ידנית מספר אחד:** הפעל `/portfolio` עכשיו (אחרי ההפצה) והצלב את מספר **"ההתאמה לברוקר / פער"** מול דשבורד ה-master ומול דף ה-IBKR. הוא אמור כעת להיות **זהה לדשבורד** (לא המספר שבצילומים).
2. **כלום דחוף בקוד.** המנוע נקי, התיקון הקריטי כבר חי. אין באג חדש.
3. **להחליט על R-ALGO-3 שלב-ב' (תצוגתי, סיכון אפסי):** לתקן את הכותרת "L50(50)" עצמה כך שתציג את המספר האמיתי, לא רק להוסיף שורת אזהרה לידה. הסרת הסתירה הפנימית בין שורת הציון לשורת אחוז ההצלחה. founder-gated, לא דחוף, ללא שינוי מספר כסף.
4. **לזרוק/לסמן את הצילומים הישנים** ככאלה שצולמו לפני הפצת ALGO-1 — כל החלטה שמתבססת על מספר ההתאמה שבהם מבוססת על נתון שגוי שכבר תוקן.

— Engine team, Sprint-29 (DOC-ONLY; no code changed; no commit/push).
