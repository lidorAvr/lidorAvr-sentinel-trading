# Sprint-29 — Research Report-Map (live Telegram output vs system)

**Team:** Research. **Mode:** DOC-ONLY (no code, no tests, no commit).
**Live HEAD at review:** `09dbec7` (Sprint-27 W1/W3/W4c + Phase ALGO-1
W-A2/W-A3 deployed). **Evidence:** two real founder Telegram exports
(`/tmp/tg_report_1.txt` 996 msgs, `/tmp/tg_report_2.txt` 431 msgs).
Cross-ref: `ALGO_INVESTIGATION_1.md`, `ALGO_TEAM_CHARTER.md`,
`SPRINT27_W1_IMPL.md`, `SPRINT27_W3W4C_IMPL.md`, `PHASE_ALGO1_IMPL.md`,
`docs/DATA_CONTRACTS.md`, `docs/MODULE_MAP.md`, `CLAUDE.md`.

> **DATA-SENSITIVITY (binding).** This doc is STRUCTURAL only. No live NAV,
> position size, or P&L value is copied here. Issues are described by
> section / shape / wording. (The recon $-figures the founder asked us to
> seed-verify are named only as the two ALGO-1 anchor magnitudes, already
> public in `ALGO_INVESTIGATION_1.md`; no new live numbers introduced.)

> **Accuracy over confidence.** The exports STRADDLE the Sprint-27/ALGO-1
> deploy. Deploy boundary is dateable in `tg_report_2`: the W3 "🧭 מה עכשיו?"
> companion line first appears at msg-block ~line 4005 and the ALGO-1 W-A3
> "L50 מבוסס מדגם חלקי" honesty line first at ~4307. Everything earlier =
> PRE-deploy; everything from ~4005 on = POST-deploy. This split is what
> lets us classify each finding fixed / open / new with evidence.

---

## 1. Report-type / section map (what actually appears in live output)

| # | Report / section (as rendered) | Surface trigger | Code path that renders it | Matches contract / methodology? |
|---|---|---|---|---|
| R1 | `🔭 חדר מצב - דו"ח ריכוז פוזיציות:` (open-book, per-position cards) | `/portfolio` open-book | `telegram_portfolio.py` `handle_portfolio_room` → `tf.fmt_position_card` | Mostly. Per-card RS/exposure/state OK. ALGO cards correctly say "פיקוח בלבד — Sentinel אינה מנהלת יציאות אלגו" (DEC-20260511-001 #8 holds). |
| R2 | `📊 סיכום תיק הפיקוד:` (open-book summary footer) incl. `מצב התאמה מול ברוקר` recon line + `בסיס הון לסיכון: NAV (…)` | end of R1 | `telegram_portfolio.py:472-490` (`are.compute_closed_campaigns` → `_db_net_pnl` → `tf.classify/fmt_broker_reconciliation`) | **NO — see F1.** Recon line renders TWO different gaps + TWO different severity bands for the same state on the same surface, POST-deploy. |
| R3 | `🎯 המלצת סיכון אדפטיבי` block (heat score, S9/M21/L50 score line, Win-Rate sub-line, risk-ladder up/down) | appended to regime + open-book summary | `telegram_formatters.py:fmt_adaptive_risk_block` (~:246-267) | Partial — see F2/F3. Score line still hardcodes `S9(9) M21(21) L50(50)`; ALGO-1 W-A3 adds an honest disclosure line below it but does NOT correct the lying literal. |
| R4 | `🌡️ דו"ח משטר שוק` (market regime, 4/4 base, exposure split אלגו/EP) | regime menu | `telegram_formatters.py:fmt_regime_report` | OK structurally. Exposure split disc/ALGO consistent with `engine_core` cluster constants. |
| R5 | `🚨 Sentinel Live Alert` (per-position alert card) | `risk_monitor.py` tier-1 | `risk_monitor.py` Live Alert path → card formatter | OK. ALGO cards show observe-only action; `טריגר:` sometimes renders EMPTY (trailing label with no value) — see F6. |
| R6 | `📉 Giveback Alert — …` (zone-transition) | `risk_monitor.py` giveback | `risk_monitor.py` zone-change logic | OK — zone-change firing, ALGO variant says "פיקוח בלבד — Sentinel אינה מנהלת יציאות אלגו". Matches Giveback zone contract. |
| R7 | `🔴 טרייד שבור — SYM` / `📋 משימות פתוחות` (open-tasks) | tasks menu / state machine | open-tasks engine + `telegram_bot.py` | OK structurally. "כל הפוזיציות מנוהלות חיצונית/חסרות נתונים" empty-state honest. |
| R8 | `🛡️ Sentinel — דוח שבועי / דוח חודשי` (weekly/monthly summary text) | scheduler / on-demand | `report_renderer.build_summary_text` | Partial — see F4/F5. W3 "🧭 מה עכשיו?" prepend now present POST-deploy. Period-noun + empty-April mislabels. |
| R9 | `🌡️ מד חום מסחר` heat block inside R8 (S9/M21/L50 bars + Win-Rate) | inside R8 | `telegram_formatters.py:fmt_heat_thermometer` (~:483-500) | Partial — bare `L50 [bar] N` had no N; ALGO-1 W-A3 now appends honest disclosure POST-deploy (confirmed rendering). |
| R10 | `🏥 Sentinel System Health` (13 checks incl. NAV / ALGO Positions / Missing Stops) | `/health` | `bot_health.py` | **NO — see F7.** NAV check renders a DOUBLED status glyph. |
| R11 | `ℹ️ מקור נתונים: Live/Cached …` data-source footer | every risk-sensitive report | secure-runner / formatter footer | OK — present on all risk surfaces (CLAUDE.md #1 disclosure intact). |
| R12 | `✅/🟡/🔴/🟠 NAV $… — עודכן/אין timestamp` freshness line | open-book footer + health | `engine_core.get_nav_with_freshness` `:1604-1640` consumed by `bot_helpers.get_nav_and_risk` / `bot_health` | Self-consistent value/freshness (F8 negative), BUT doubled-glyph in R10 (F7). |
| R13 | `🧭 מה עכשיו?` W3 companion line | top of R2 / R8 / digest | `report_renderer.whatnow_line` / `telegram_portfolio` prepend / `risk_monitor._daily_digest_text` | OK POST-deploy — confirmed rendering correctly (F4 fixed). |
| R14 | ALGO-cluster line `🤖 בקרת אשכול אלגו: ▸ חשיפה אלגו: N%` | R2 footer | `telegram_portfolio` summary | OK — ALGO cluster shown separately; symbol universe matches doctrine (F-ALGO negative). |
| R15 | WS-C diagnostic dump (`… risk_valid=✗ initial_stop invalid (-1)…`, `הכרעת WS-C`) | dev/diagnostic | engine diagnostic export | Honest (flags `-1` sentinel ALGO rows as not-counted) — matches stat_bucket contract. |

---

## 2. Report finding → fixed-by-deployed / still-open / new

| ID | Finding (structural) | Surface | Pre-deploy evidence | Post-deploy evidence | Classification |
|----|----------------------|---------|---------------------|----------------------|----------------|
| **F1** | **Two different broker-reconciliation gaps + two different severity bands for the SAME state on the SAME surface (`📊 סיכום תיק הפיקוד`).** This is ALGO-1 R-ALGO-2 made visible in live output: the חדר-מצב recon shows the smaller "Material Gap" magnitude in most renders, but a later render of the identical footer shows the larger ALGO-1 "Critical Data Gap" magnitude. | R2 | חדר-מצב recon = the smaller (Material) figure repeatedly | The SAME footer renders BOTH: the smaller "פער מהותי" magnitude AND, in a later identical-surface render, the larger "פער נתונים קריטי" magnitude — **both AFTER the deploy markers**. | **STILL-OPEN (most critical).** W-A2 keyed-fix deployed, but the trader still sees contradictory recon numbers/bands post-deploy. Either the fix only shifted the bug, or a residual closed-vs-all / open-PnL non-determinism (ALGO-1 §1 explicitly flagged this residual) makes recon non-deterministic across renders. Money-truth. |
| **F2** | **Adaptive-risk score line hardcodes `S9(9) | M21(21) | L50(50)`** while the Win-Rate sub-line on the very next line shows the true `(8)` / `(9)` count → self-contradiction inside one block (`L50(50)` next to `L50 (8)`). | R3 | Present everywhere pre-deploy | Score line STILL says `S9(9)…L50(50)`; W-A3 appends `⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: N/50` below it. | **PARTIALLY fixed (ALGO-1 W-A3).** Disclosure added & confirmed rendering, but the lying literal `(9)/(21)/(50)` was deliberately left byte-identical by W-A3 scope. The internal contradiction the founder seeded is **still on screen**. |
| **F3** | Heat block (R9) bare `L50 [bar] score` had **no sample size at all**. | R9 | bare `L50 [🟢..] 86` no N | `⚠️ L50 מבוסס מדגם חלקי — מדגם נוכחי: 7/50 …` now appended (confirmed). | **FIXED-by-deployed (ALGO-1 W-A3).** |
| **F4** | Weekly/monthly summary verdict said **"🔴 שבוע ללא עסקאות" inside a MONTHLY report** (period-noun mismatch). Also: no companion next-step line at top. | R8/R13 | Monthly April report rendered "**שבוע** ללא עסקאות" | Later monthly April renders correctly "**חודש** ללא עסקאות"; W3 "🧭 מה עכשיו?" line now prepended. | **FIXED-by-deployed (Sprint-27 W3** wired `period_type→period_word` into `compute_verdict`; companion line confirmed). |
| **F5** | On-demand **Monthly "אפריל 2026" returns 0 campaigns / $0 / "ללא עסקאות"** — contradicts the LOCKED April regression (8 countable campaigns, positive realized, PF≈2.63). | R8 | April monthly empty pre-deploy | April monthly STILL renders empty post-deploy (later msgs). | **STILL-OPEN / NEW (high).** Either a period-window/snapshot empty-state bug OR the DB genuinely had no April rows synced at run-time (IBKR 1001 sync failures are all over the logs). Trader saw a misleading "no trades in April" for a month the locked fixture says was profitable. Engine/Data must disambiguate window-bug vs data-sync-gap. |
| **F6** | Live Alert card sometimes renders a trailing `‏טריגר:` label with **empty value** (no trigger text). | R5 | present | present (not in deploy scope) | **STILL-OPEN (low, cosmetic-honesty).** A dangling label reads as missing data; should suppress the label when empty. |
| **F7** | **System Health NAV check renders a DOUBLED status glyph**: `✅ ✅ NAV …`, `🔴 🟠 NAV …`, `⚠️ 🟠 NAV …`. Root: `bot_health.py:25-54` `ok()/warn()/bad()` prepend `✅/⚠️/🔴`, but are passed `engine_core.get_nav_with_freshness()['freshness_label']` which **already begins with its own emoji** (`engine_core.py:1613-1634`). | R10 | `✅ ✅ NAV` / `🔴 🟠 NAV` / `⚠️ 🟠 NAV` present | still present (bot_health.py untouched by Sprint-27/ALGO-1) | **NEW (low sev, real). Seed-verified TRUE.** Not in any deployed scope (Sprint-27 touched `dashboard_nav`/`report_renderer`/`telegram_formatters`/`telegram_portfolio`; ALGO-1 touched `telegram_formatters`/`telegram_portfolio`). `bot_health.py` never strips the label's leading glyph. Also note the glyph DISAGREES (`🔴`+`🟠`, `⚠️`+`🟠`) — wrapper severity vs label severity can diverge. |
| **F8** | NAV value/freshness self-consistency across messages. | R12 | — | — | **NEGATIVE (no defect).** NAV values shown track the IBKR sync-log updates over time; no single message self-contradicts value vs freshness. The label value & tier are single-sourced (`engine_core.py:1604-1617` tiers from canonical freshness). Variance across time = expected sync cadence, not a bug. |
| **F-ALGO** | ALGO symbol universe in report vs Mark doctrine targets. | R10/R14 | — | — | **NEGATIVE (consistent).** Health "ALGO Positions — 5 סמלים: HOOD, JPM, TSLA, QQQ, PLTR" exactly equals `engine_core.ALGO_SYMBOL_LIMITS` keys (QQQ/TSLA/JPM/PLTR/HOOD). Charter per-symbol watch (HOOD/PLTR) = the symbols showing `🔴 Broken` ALGO alerts in the tail. Segregation holds (ALGO not stat-countable). |

---

## 3. Top areas the other 8 leads must scrutinise hardest

1. **F1 — recon non-determinism (ALGO Data-Integrity + Engine + Data leads).**
   This is the single most serious live finding. The trader sees TWO
   different broker-reconciliation gaps AND two different severity bands
   ("פער מהותי" vs "פער נתונים קריטי") for the same state on the same
   `סיכום תיק הפיקוד` surface — **post-deploy**, i.e. the W-A2 one-key fix
   did NOT make it converge. ALGO-1 §1 explicitly warned of a residual
   "closed-vs-all" definitional nuance + open-PnL/live-price variance; the
   live output proves that residual is now user-visible as a flapping
   number/band. Doctrine concern: this recon line sits directly above an
   adaptive block that **recommends raising risk 0.60%→0.85%** while the
   recon is unclean — exactly the R-ALGO-1/6 gate gap.

2. **F5 — empty April monthly (Engine + Data + Testing leads).**
   On-demand monthly for "אפריל 2026" renders 0 campaigns / $0 / "ללא
   עסקאות", contradicting the LOCKED April regression ground truth. Must
   disambiguate: period-window/snapshot empty-state bug vs runtime
   data-sync gap (IBKR 1001 failures are pervasive in the logs). Either way
   the user was shown a misleading "nothing happened in April".

3. **F2 — adaptive score-line self-contradiction (ALGO Stats + UX leads).**
   W-A3 added an honest disclosure but deliberately left the lying
   `S9(9) M21(21) L50(50)` literal byte-identical. The block now shows both
   "L50(50)" and "L50 (8)" and a "9/50" disclosure — three different sample
   readings in one block. Decide whether the literal itself should be
   corrected (founder-gated, since the score values are unchanged but the
   parenthetical is fictional) — this directly feeds the false-confidence
   the founder flagged into a money (risk-raise) decision.

Secondary: **F7** (health double-glyph — low sev, trivial but real,
unowned), **F6** (empty `טריגר:` label).

---

## למנכ״ל — בשפה פשוטה

- **המפה:** עברנו על מה שבאמת הופיע אצלך בטלגרם (לא על הקוד בלבד).
  הייצוא חוצה את ההטמעה האחרונה — אז לכל ממצא סימנּו: כבר תוקן / עדיין פתוח / חדש.
- **מה כבר תוקן ועובד אצלך:** שורת "🧭 מה עכשיו?" מופיעה עכשיו בראש הדוחות;
  הדוח החודשי כבר לא כותב "שבוע" בטעות; ושורת היושר על מדגם ה-L50 הקטן
  ("מדגם נוכחי: N/50") מופיעה עכשיו במדחום החום. כל אלה אומתו בייצוא עצמו.
- **הבעיה הכי חמורה שעדיין פתוחה:** מספר ה"התאמה לברוקר" בחדר־מצב **עדיין
  לא יציב** — באותו מסך בדיוק, פעם הוא מראה פער אחד ("פער מהותי") ופעם פער
  אחר וגדול יותר ("פער נתונים קריטי"), וזה קורה **גם אחרי** התיקון שהוטמע.
  זה יושב בדיוק מעל ההמלצה להעלות סיכון. זה הסעיף מס' 1 לבדיקה.
- **בעיה נוספת:** דוח חודשי ל"אפריל 2026" שנשלח אליך הראה **0 עסקאות / $0**
  בזמן שלפי הנתון הנעול אפריל היה חודש רווחי. צריך לברר אם זה באג בחלון
  התקופה או שבאמת לא היו נתונים מסונכרנים באותו רגע (היו הרבה כשלי סנכרון
  IBKR 1001 בלוגים).
- **שני הדגלים שביקשת לאמת:** (1) ה-"✅ ✅ NAV" הכפול — **אמיתי**, באג חדש
  קטן בדוח הבריאות (`bot_health.py`), לא נכלל באף הטמעה. (2) "L50(50)" ליד
  "L50 (8)" — **אמיתי**, תוקן חלקית: נוספה שורת יושר, אבל הכיתוב המטעה עצמו
  עדיין מוצג (זה ביודעין מחוץ להיקף התיקון שהוטמע).
- **אלגו וה-NAV:** ההפרדה של אלגו וזהות סמלי האלגו תקינות; ערכי ה-NAV
  עקביים מול הסנכרון — אין שם פגם.

## מה צריך לעשות (Research — דיווח בלבד, ללא קוד)

1. להעביר את המפה ל-8 הלידים; F1 (אי-יציבות ההתאמה) ל-ALGO Data-Integrity
   + Engine + Data; F5 (אפריל ריק) ל-Engine + Data + Testing.
2. אף תיקון לא רץ כאן — Research הוא דיווח בלבד. כל תיקון = Phase ממשל
   נפרד, founder-gated, עם הוכחה נקובה (byte-identical / behavior).
3. F1 ו-F5 הם money-truth → לפי `SAFE_CHANGE_PROTOCOL` high-risk: מבחן
   רגרסיה קודם, שינוי קטן, ללא נגיעה בקבצים נעולים.
