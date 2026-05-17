# SPRINT-26 — Deep UX/UI + Emotional-Experience Review (DOC-ONLY)

**Reviewer:** Product / UX & Design lead
**Scope:** every user-facing surface — Dashboard (`dashboard.py`), Active Telegram
(`telegram_bot.py`, `telegram_callbacks.py`, `telegram_portfolio.py`,
`telegram_menus.py`, `telegram_formatters.py`, `telegram_bot_secure_runner.py`,
`telegram_devops.py`), Passive Telegram (`report_renderer.py`,
`report_open_book.py`, `report_scheduler.py`, `period_data_probe.py`,
`risk_monitor.py`).
**Bar:** does the user feel he has a *personal companion*, is *genuinely in
control*, is the system *accessible and personally-tailored enough to become
addictive*?
**Production:** live on `main` `c761967` (all phases deployed). Sprint-26
research dossier (`docs/teams/SPRINT26_RESEARCH_DOSSIER.md`) is **absent** — this
review works from source only and notes the gap.
**Constraint reminder:** NO code this round. Every fix is a recommendation;
fixes become future governed Phases.

---

## Executive verdict

The system is **analytically world-class and almost pathologically honest** —
but it currently behaves like an *institutional risk terminal*, not a *personal
companion*. It tells the user the truth, exhaustively, in dense paragraphs of
backticked numbers and disclosure clauses. It rarely tells him **what it thinks
he should do next, in one line, like a mentor who knows him**. The honesty
machinery (B1/B3/Sprint-19/20/21) is genuinely excellent and must be protected
— but it has crowded out warmth, narrative, and a sense of "this thing is *for
me*." The trader will respect it. He will not yet feel *hooked* by it.

The single highest-impact change is a **persistent "מה עכשיו?" / one-line verdict
+ next action at the very top of every primary surface** (חדר מצב, weekly/
monthly report, daily digest). Everything else is amplification.

---

## P0 — Hurts trust or usability now

### P0-1 — There is no companion "voice" at the top of anything; the lede is buried
**Where:** `telegram_portfolio.handle_portfolio_room` (the message opens
`🔭 חדר מצב - דו"ח ריכוז פוזיציות:` then immediately dumps position cards);
`report_renderer.build_summary_text` (verdict line is line 4, after the header,
*below* a blank line, then 4 dense KPI rows); `risk_monitor._daily_digest_text`
(opens with a divider, then a flat bullet list).
**Problem:** Every primary surface front-loads *layout* and *raw data* and makes
the human scroll/parse to discover "am I OK, and what should I do?". A companion
leads with a one-sentence read on *you*: "תיק יציב, סיכון תחת שליטה — אין פעולה
דרושה היום" or "‎2 פוזיציות דורשות החלטה: NVDA, HOOD." Right now the user has to
*reconstruct* that sentence himself from R-values. This is the core reason it
feels like a terminal, not a mentor.
**Low-risk fix (future Phase):** Add a single computed headline line — verdict
emoji + 4–8 word state + the one next action — as the FIRST line of: חדר מצב,
the weekly/monthly Telegram summary, and the daily digest. Data already exists
(status, action_short, urgent[] in the digest, `compute_verdict`). Pure
presentation re-order; no math change.

### P0-2 — Silence is ambiguous; "no alert" ≠ "all good" is never stated
**Where:** `risk_monitor.py` only speaks on threshold/zone/escalation events
and one daily digest (21:00–22:00 UTC, Mon–Fri, skipped if `not rows`).
**Problem:** Between events the companion is *mute*. A user who hears nothing
cannot tell: (a) all positions healthy, (b) market closed, (c) monitor crashed,
(d) no open positions. For a real-money tool this ambiguity is an active trust
risk — the most dangerous state ("system is down") looks identical to the safest
("you're fine"). The digest's closing line `_(ללא פעולה נוספת? הדאשבורד עדכני)_`
is the only nod to this and it is parenthetical, italic, and easy to miss.
**Low-risk fix:** A once-daily positive "all-clear" heartbeat when there are
open positions and zero alerts fired ("‎🟢 Sentinel ער · ‎N פוזיציות · אין
התראות · נבדק לאחרונה HH:MM"). Liveness is already tracked
(`secure_runner` heartbeat files; `bot_health`). Turns silence into a *reassuring
presence* — directly serves "in control" + "companion."

### P0-3 — Disclosure density can read as anxiety, not honesty
**Where:** `report_renderer.build_summary_text` 0-closed branch can stack, in
one Telegram bubble: empty-state L1–L3 + price-fallback warning + open-book
cross-period + unlinked-BUY + excluded-manual + excluded-ALGO + unlinked-SELL +
NAV-disclosure + heat thermometer. Also `telegram_portfolio.handle_portfolio_room`
footer: risk-capital-basis + broker-reconciliation + Minervini coaching +
adaptive-risk block + NAV-stale + price-fallback list — all appended sequentially.
**Problem:** The honesty is correct and must stay. But *un-prioritized* honesty
reads as a system that is nervous about itself. Six caveat blocks of equal
visual weight, every report, trains the user to skim past *all* of them —
including the one that matters today. Trust comes from honesty that is
*calm and ranked*, not exhaustive and flat.
**Low-risk fix:** Visual hierarchy only — collapse routine disclosures under one
calm header ("ℹ️ הערות נתונים (3)") and promote only the disclosure that is
*active and decision-relevant this period* (e.g. a stale NAV that is scaling
today's R) to top-level. Zero wording/number change — the verbatim Mark-governed
strings stay; only their grouping/prominence changes.

---

## P1 — Significant; erodes the "companion / in-control" feel

### P1-1 — No onboarding / `/start`; first contact is "Sentinel Standby"
**Where:** `telegram_bot.py` — no `commands=['start']` handler; unknown text
falls to the generic `"🎯 *Sentinel Standby*\nמערכת מוכנה לפעולה..."`. The
ONLINE boot message is `v3.7 — תפריט מפתח פעיל`.
**Problem:** A companion greets you and orients you. The current first
impression is a cold standby string and a version number aimed at a developer.
Nothing says *what this is for you* or *what to tap first*. Misses the entire
"accessible / personally-tailored / addictive" hook at the exact moment it
matters most.
**Low-risk fix:** A warm `/start` (and a friendlier fallback) — one line of
identity ("אני Sentinel — שומר על התיק והסיכון שלך"), the single most useful
action, and a pointer to חדר מצב. Pure copy + one handler.

### P1-2 — C1 dev-PIN gate is correct but the friction is not humane for a solo owner
**Where:** `_require_active_dev_session` (`telegram_bot.py`), `telegram_devops`
(`_PIN_SESSION_DURATION = 1800`s / 30 min; rate-limit 5-min window).
**Problem:** The gate is *security-correct* and must keep its fail-closed
behavior (do not weaken). But the **experience** for the legitimate sole owner
is unkind: a 30-min session that expires silently, then a privileged tap throws
`🔐 פעולת מפתח דורשת PIN פעיל / הפגישה אינה פעילה או פגה` mid-task with no
indication of *how long was left* or *that it was about to expire*. The
persistent dev keyboard stays visible after expiry, inviting taps that bounce.
For the founder this is the surface he hits most when actively operating —
repeated friction here directly damages "in control."
**Low-risk fix (UX only, security unchanged):** (a) on successful PIN, state the
expiry time explicitly; (b) a soft "session expires in ~5 min — tap to extend"
nudge before silent expiry; (c) on refusal, keep the *intended action* pending
so re-entering the PIN resumes it instead of dropping the user back to main.
No change to the constant-time compare, the 30-min TTL, or fail-closed.

### P1-3 — B3 race-refusal wording is honest but blunt and slightly disorienting
**Where:** `telegram_callbacks.py` addon_confirm race branch:
`❌ *ביטול: הפוזיציה השתנתה — {sym}* / הפוזיציה הפתוחה עבור הסמל השתנתה מאז
שתכננת את החיזוק. / הרץ /addon מחדש.`
**Problem:** Correct and safe. But it reads like a system rejection, not a
mentor protecting the user. It does not say *what changed* or *why this is the
system looking out for him* — so a refusal of a real-money action feels like a
fault, not a save. "In control" requires understanding *why* the system
intervened.
**Low-risk fix:** Reframe as protective and specific: lead with "מנעתי כתיבה
על קמפיין שונה — הפוזיציה ב-{sym} התחלפה מאז התכנון (הגנה על הכסף שלך)" then
the re-run instruction. Wording only; the zero-write behavior is untouched.

### P1-4 — Dashboard buries the human's first question under institutional chrome
**Where:** `dashboard.py` — title `🎯 Sentinel Pro Command Center (Institutional
Edition)`; first tab opens `Live Portfolio Allocation & Risk Heatmap`; the
trader's actual state (am I OK / what's at risk / what to do) is distributed
across the sidebar (Adaptive Risk, Reconciliation) and treemaps.
**Problem:** Mixed Hebrew/English ("Institutional Edition", "Command Center",
"Performance Matrix") plus chart-first layout signals *Bloomberg terminal*, not
*my companion*. There is no single "today, for you" panel above the fold. On a
phone (founder's likely device) the sidebar — which holds Adaptive Risk and
Reconciliation, the most decision-relevant items — collapses off-screen first.
**Low-risk fix:** A top-of-Command-Center "מצב היום" strip: verdict line,
open risk, #positions needing a decision, NAV freshness — reusing existing
computed values. Soften the title. Recommendation only; no calculation reuse
change beyond surfacing.

### P1-5 — Latency with no companion-grade waiting affordance
**Where:** `handle_portfolio_room` ("⏳ *שואב נתונים ומרכיב דו"ח...*"),
`handle_drilldown`, dashboard `compute_live_portfolio_data` (TTL caches, parallel
prefetch, per-symbol yfinance). Heavy paths can take many seconds.
**Problem:** A flat "⏳ שואב נתונים..." for a multi-second live fetch makes the
companion feel slow and unresponsive — the opposite of "always-there." No
progress sense, no "this is worth the wait" framing.
**Low-risk fix:** Progressive/stepped status ("מושך מחירים חיים ל-N פוזיציות…"
already exists in the dashboard spinner — port that specificity to Telegram) or
send the headline line immediately and stream the detail. Presentation only.

---

## P2 — Polish; would make it *delightful*

- **P2-1 — Tone is uniformly procedural.** Alerts/digests use clipped imperatives
  ("בצע יציאה", "שקול צמצום", "עקוב"). Correct, but never *personal*. A
  companion occasionally acknowledges the human ("שבוע חזק — המשמעת שלך
  השתלמה", "הפעם ויתרת על רווח — נדבר על זה"). `report_scheduler` coaching
  insights are the closest thing; they are buried at the bottom. Promote and
  warm them.
- **P2-2 — No personalization signal.** Nothing in any surface reflects *this
  user's* history back at him ("הסטופ שהידקת ב-NVDA — עבד"). `risk_journal`,
  adherence stats, MAE/MFE all exist; none is mirrored conversationally. This
  is the single biggest missed *addictive* lever — being *known* is what hooks.
- **P2-3 — Inconsistent separators/visual language** across surfaces: `〰️×9`
  (portfolio), `───` (digest), `SEP` (formatters), `─────` (runner). Minor, but
  a companion has *one* visual identity.
- **P2-4 — Emoji semantics overloaded.** 🚨 means Live Alert, critical status,
  execution breach, and ALGO event; 🔴 means loss, Broken, and severe. The user
  must context-disambiguate. A small fixed legend / consistent mapping helps.
- **P2-5 — `/help` is a flat command list,** not task-oriented ("רוצה לראות מה
  קורה עכשיו? → חדר מצב"). Discoverability is functional, not inviting.
- **P2-6 — Numbers are backtick-dense.** Lines like
  `Open R: \`{open_r:.2f}R\` | סטטוס: ... | פעולה: ...` are scannable for a
  quant, fatiguing for daily emotional use. Selective bolding of the *one* number
  that matters per card would reduce cognitive load.
- **P2-7 — Sprint-26 research dossier missing.** `docs/teams/
  SPRINT26_RESEARCH_DOSSIER.md` does not exist; this review proceeded from
  source. Flag for the founder so future UX phases have the intended brief.

---

## What is genuinely excellent — PROTECT THIS

1. **Radical, governed honesty.** B1 NAV/fallback disclosure, B3 zero-write
   race refusal, Sprint-19/20/21 open-book / excluded / unlinked disclosures,
   `period_data_probe`'s "input ריק/כשל ≠ 0 סגירות", the price-fallback labels.
   This is the system's soul and its single biggest *trust* asset. **Do not
   trade honesty for warmth — layer warmth on top of it.** The fix for P0-3 is
   *hierarchy*, never *removal*.
2. **Fail-closed C1 dev gate.** Security posture is correct (unset DEV_PIN
   denies). P1-2 is purely about *kindness around* the gate, not weakening it.
3. **ALGO observation-only discipline.** Consistently "פיקוח בלבד · לא הוראה,"
   never an instruction. Honest about the boundary of the system's authority —
   exactly what a trustworthy companion does.
4. **Anti-spam restraint in `risk_monitor`.** Zone-change firing, cooldowns,
   escalation-only re-alerts. The companion does not nag. Protect this — P0-2's
   heartbeat must be ONE calm daily line, not a return to noise.
5. **RTL discipline.** Consistent `RTL`/`{RTL}` prefixing and `.ltr` PDF
   wrapping — Hebrew renders correctly. Solid, accessible baseline.
6. **Graceful degradation everywhere** (PDF→text, charts→None, NAV fallback).
   The companion never hard-fails in the user's face.

---

## Cross-check: do the disclosures build trust or create anxiety?

**Per-disclosure: trust.** Each individual honest line (stale NAV, $0 fallback,
unlinked trades) is exactly right and increases trust — the user can rely on
the system never lying to him. **In aggregate, presentation: mild anxiety.**
Six equal-weight caveat blocks every report, with no ranking, signals a system
unsure of its own data and trains skim-past behavior. The content is an asset;
the *flat, un-prioritized layout* is the liability. Fix is hierarchy (P0-3),
never suppression.

**Is silence ever mistaken for "all good"?** **Yes — P0-2, and this is the most
serious finding.** A healthy portfolio, a closed market, no open positions, and
a crashed monitor are all *indistinguishable* to the user (total silence). For
a real-money companion this is the highest-stakes ambiguity in the product. A
single daily positive-presence heartbeat resolves it without reintroducing
spam.

---

## למנכ״ל — חוויית המשתמש בשפה פשוטה

**האם זה מרגיש כמו מלווה אישי?** עדיין לא לגמרי. המערכת **מדויקת, ישרה
וחכמה בצורה יוצאת דופן** — היא אף פעם לא תשקר לך, וזה נכס ענק. אבל כרגע היא
מדברת כמו *מסוף מסחר מוסדי*: הרבה מספרים, הרבה הסתייגויות, מעט "אני כאן בשבילך".
היא נותנת לך את כל האמת — אבל לא אומרת לך, במשפט אחד, *מה היא חושבת שכדאי
לעשות עכשיו*, כמו מנטור שמכיר אותך.

**איפה זה מענג:** היושר. כשמחיר לא חי, כש-NAV ישן, כשעסקה לא מקושרת — היא
אומרת לך בדיוק. כשתכננת חיזוק והפוזיציה התחלפה — היא **עצרה את הכתיבה** והגנה
על הכסף שלך. ההתראות לא מציפות אותך. זה בדיוק מה שגורם לבטוח בה. **לשמור על
זה בכל מחיר.**

**איפה זה מאכזב:**
1. אין משפט פתיחה שאומר "אתה בסדר / יש 2 החלטות לקבל" — צריך לחפש את זה לבד.
2. כשהיא שותקת — אי אפשר לדעת אם הכול טוב או שהיא נפלה. זו הבעיה הכי מסוכנת.
3. ערימת הסתייגויות שוות-משקל בכל דוח — נכון, אבל מלחיץ ומאמן אותך לדלג על
   *הכול*, כולל מה שחשוב היום.
4. אין "שלום, אני Sentinel" — המפגש הראשון הוא מחרוזת קרה למפתחים.
5. ה-PIN של המפתח (נכון מבחינת אבטחה — לא לגעת) פוקע בשקט ומתסכל אותך באמצע
   פעולה.

**3–5 שינויים שיהפכו את זה למשהו שתתמכר אליו:**
1. **שורת מנטור אחת בראש כל מסך** — "מה המצב + מה לעשות עכשיו", במשפט.
2. **דופק יומי חיובי** — שורה אחת רגועה: "‎🟢 ער · הכול תחת שליטה · נבדק HH:MM",
   כדי ששקט יהיה הרגעה ולא חוסר ודאות.
3. **לדרג את ההסתייגויות** — להבליט רק את זו שחשובה היום, השאר מקופל בשורה אחת.
4. **קבלת פנים חמה** — `/start` שמציג מי היא ומה הכי שווה ללחוץ.
5. **לשקף אותך לעצמך** — מדי פעם "הסטופ שהידקת — עבד", "השמעת שלך השתלמה". זה
   מה שיוצר התמכרות: להרגיש *מוכר*.

**שורה תחתונה:** יש לך מנוע אמון מצוין. חסר לו *קול*. השינוי הכי משמעותי בודד:
**שורת ורדיקט + פעולה אחת בראש כל מסך.**

---

## מה צריך לעשות

עדיפות לפעולות מנכ״ל (כל אחת הופכת ל-Phase מנוהל בנפרד — אין קוד בסבב הזה):

1. **[P0] לאשר Phase: "שורת מנטור" בראש חדר מצב + דוח שבועי/חודשי + דייג'סט
   יומי.** Re-order תצוגתי בלבד, אפס שינוי מתמטי. **ההשפעה הכי גבוהה.**
2. **[P0] לאשר Phase: דופק יומי חיובי אחד** כשיש פוזיציות פתוחות ואפס התראות —
   פותר את עמימות השתיקה (הסיכון הכי מסוכן). שורה אחת, ללא ספאם.
3. **[P0] לאשר Phase: היררכיית הסתייגויות** — קיפול הרוטיניות תחת כותרת רגועה,
   הבלטת הרלוונטית-להיום בלבד. נוסח/מספרים ללא שינוי (מילים של Mark נשמרות).
4. **[P1] לאשר Phase: `/start` + fallback חם + ריכוך כותרת הדאשבורד.** Copy
   בלבד + handler אחד.
5. **[P1] לאשר Phase: ריכוך חוויית C1 (אבטחה ללא שינוי)** — הצגת זמן פקיעה,
   נדנוד רך לפני פקיעה, חידוש פעולה ממתינה אחרי PIN.
6. **[P1] לאשר Phase: ניסוח-מחדש מגן לסירוב מרוץ B3** — מילים בלבד, התנהגות
   אפס-כתיבה ללא שינוי.
7. **[P2] Backlog מענג:** טון אישי, שיקוף היסטוריה, שפה חזותית אחידה, מקרא
   אימוג'י, `/help` מבוסס-משימה.
8. **[Ops] להחליט על `SPRINT26_RESEARCH_DOSSIER.md` החסר** — לייצר אותו לפני
   ה-Phases של P1/P2 כדי שהכוונה תהיה מתועדת.

**עיקרון מנחה לכל ה-Phases:** לעולם לא להחליף יושר בחום. להוסיף חום *מעל*
היושר. היושר הוא הנשמה — הקול הוא מה שחסר.
