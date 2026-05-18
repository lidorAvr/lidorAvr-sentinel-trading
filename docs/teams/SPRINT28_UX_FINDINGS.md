# SPRINT-28 — Deep UX/UI + Emotional-Experience Review (DOC-ONLY, re-run of Sprint-26 on the post-Sprint-27 LIVE system)

**Reviewer:** Product / UX & Design lead
**Scope:** every user-facing surface AS IT IS NOW — Dashboard (`dashboard.py` +
`dashboard_nav.py`), Active Telegram (`telegram_bot.py`,
`telegram_callbacks.py`, `telegram_portfolio.py`,
`telegram_bot_secure_runner.py`, `telegram_devops.py`), Passive Telegram
(`report_renderer.py`, `report_open_book.py`, `risk_monitor.py`,
`period_data_probe.py`).
**Bar (unchanged):** does the user feel he has a *personal companion*, is
*genuinely in control*, is the system *accessible/personal enough to get
hooked*?
**Production:** LIVE on `168aaa2` (Sprint-27 W1+W2+W3+W4 deployed).
**Constraint:** NO code this round. Every fix is a recommendation; fixes become
future governed Phases.
**Gap noted:** `docs/teams/SPRINT28_RESEARCH_DOSSIER.md` is **absent** (same as
Sprint-26's missing dossier). This review proceeded from source only — flag for
the founder so the intended Sprint-28 brief is documented before the P1/P2
Phases.

---

## Executive verdict

Sprint-27 moved the system **from "honest institutional terminal" to "honest
institutional terminal that finally opens its mouth."** That is real progress
and the founder should feel it. Three things genuinely landed and landed well:
the dashboard NAV box is now **honest** (green only when truly Live), the
**"🧭 מה עכשיו?"** line now leads three Telegram surfaces, and the C1/B3
messages now read like a guardian instead of a vending machine.

But the review's core Sprint-26 thesis is **only ~40% closed**. The single
highest-impact item (P0-1, the companion lede) is now *present on Telegram* but
**absent on the dashboard** — the founder's most likely phone surface still
opens `🎯 Sentinel Pro Command Center (Institutional Edition)` with a chart.
The **most dangerous** Sprint-26 finding (P0-2, silence ≠ all-clear) is **still
open on the passive monitor** — `risk_monitor._send_daily_digest_if_due` still
`return`s on `not rows`, so a crashed monitor, a flat-but-healthy book, and an
empty book remain *indistinguishable silence*. And Sprint-27 introduced **one
new honesty defect of its own**: the humanized C1 message now says
"ונמשיך מכאן" ("we'll continue from here") while the code drops the pending
action — a warm sentence the system does not keep. For a product whose entire
soul is "never says something it can't back up," that is a regression in kind,
not just polish.

Net: the *voice* has arrived; the *coverage of the voice*, the *silence
problem*, and one *new copy-vs-behavior honesty crack* are what now stand
between this and addictive.

---

## What Sprint-27 GENUINELY improved (verified from source)

1. **Dashboard NAV honesty — W1 — fully delivered, clean.**
   `dashboard.py:111-118` now reads the canonical `acc_state.load()` and
   renders via `dashboard_nav.nav_sidebar_render`: a green
   `st.sidebar.success("🏦 Live IBKR NAV: …")` **only** when
   broker+fresh+ok+not-stale, else a non-green `st.sidebar.warning` reusing the
   verbatim B1 `freshness_label`. The exact "fallback-as-truth" class
   CLAUDE.md/AGENTS #1 forbids is closed on the dashboard, byte-identical on the
   happy path. **This is exactly the kind of fix to keep doing. Protect it.**
2. **"🧭 מה עכשיו?" line — W3 — landed on all three Telegram surfaces.**
   - Weekly/monthly summary: `report_renderer.whatnow_line` prepended at
     `build_summary_text` (`report_renderer.py:506,524,582`). It is **not
     generic and it does not contradict the body** — `verdict_class` is the
     *same* value `analytics_engine.compute_verdict` already returned, so
     "{p} חזק — המשמעת עבדה" sits directly above "✅ *שבוע חזק 💪*". Consistent
     by construction. Good.
   - Live חדר-מצב: `telegram_portfolio.py:540-552` — composed from
     already-computed engine `status` (the exact `CRITICAL_STATUSES` set), names
     the symbols that need a decision. This is the **sharpest** of the three —
     it is specific ("NVDA, HOOD דורשות החלטה"), actionable, and earned from
     real state, not a platitude.
   - Daily digest: `risk_monitor.py:450-458` — same urgent set, byte-identical
     body below.
3. **"silence ≠ all-clear" — PARTIALLY delivered.** The *interactive* חדר-מצב
   empty branch is now honest: `telegram_portfolio.py:251-253` replaced the
   green-check "✅ אין פוזיציות פתוחות" (reads as all-clear) with
   "📭 *אין פוזיציות פתוחות כרגע.* _זה לא אומר שהכול תקין/לא תקין … בדוק
   סנכרון נתונים._". Correct and well-worded. (But the *passive* path is not —
   see P0-1 below.)
4. **Humanized C1 / B3 — wording landed, tone is right.**
   - B3 (`telegram_callbacks.py:335-338`): "🛡️ *עצרתי את החיזוק — {sym}*
     … לא כתבתי כלום, כדי להגן על הכסף שלך." This is **exactly** the Sprint-26
     P1-3 reframe — protective, specific, states plainly nothing was written.
     Genuinely feels like the system looking out for him. Excellent, and the
     zero-write behavior is verifiably untouched.
   - C1 (`telegram_bot.py:204-206`): warmer and still states "לא בוצעה שום
     פעולה" (no false reassurance). Tone improved — **but** see P1-1: the new
     copy now over-promises a resume the code does not perform.
5. **The protected assets survived.** `period_data_probe`'s "input ריק/כשל ≠
   0 סגירות" honesty (`period_data_probe.py:155-156`) intact; B1 NAV
   disclosure intact; ALGO observation-only discipline intact; anti-spam
   restraint intact; the W3 neutral-class line actively *reinforces* the
   probe's honesty. Nothing in the soul was traded for warmth. **This is the
   most important thing Sprint-27 got right: it layered voice ON TOP of
   honesty, not instead of it.**

---

## P0 — Hurts trust or usability NOW

### P0-1 — "silence ≠ all-clear" is STILL OPEN on the passive monitor (Sprint-26's most dangerous finding, only half-closed)
**Where:** `risk_monitor._send_daily_digest_if_due` (`risk_monitor.py:475-488`)
still does `if not rows: return` (`:485-486`) — when there are **zero open
positions**, NO digest is sent at all. There is **no positive daily
heartbeat** anywhere: `_touch_heartbeat` (`risk_monitor.py:20`,
`telegram_bot_secure_runner.py:27`) writes only an internal liveness *file*,
never a user-facing message. `grep` for any "all-clear / ער / נבדק לאחרונה /
דופק" user message returns **nothing**.
**Problem:** Sprint-26 P0-2 ("the most serious finding") and the Sprint-27
SCOPE *both* asked W3 to "disambiguate silence ≠ all-clear where a surface can
render empty." W3 fixed only the **interactive** surface (the user has to *go
ask*). On the **passive** surface — the one that is supposed to be the
always-there companion — a crashed risk-monitor, a closed market, a flat-but-
healthy book with positions, and an empty book are **all still identical total
silence** to the user. The single most dangerous state (system is down) still
looks exactly like the safest (you're fine). For a real-money tool this is the
top trust risk in the product and it is **still live**.
**Low-risk fix (future Phase):** the Sprint-26 P0-2 fix exactly as specified —
ONE calm once-daily positive heartbeat when the monitor ran and there are open
positions and zero alerts fired ("🟢 Sentinel ער · N פוז' · אין התראות · נבדק
HH:MM"), AND a separate "monitor ran, 0 positions — לא אומר שהכול תקין" line so
`not rows` is no longer mute. Liveness is already tracked
(`_touch_heartbeat`). Must be ONE line, anti-spam-respecting.
**Severity P0** — unchanged from Sprint-26; this is the same finding, still the
highest-stakes ambiguity in the product.

### P0-2 — The companion voice is absent on the dashboard — the founder's most-likely surface
**Where:** `dashboard.py:155` still `st.title("🎯 Sentinel Pro Command Center
(Institutional Edition)")`; `:21` page_title "Sentinel Command Center"; first
tab (`:769-772`) opens `Live Portfolio Allocation & Risk Heatmap` (chart-first).
There is **no "מצב היום" / "🧭 מה עכשיו?" strip** anywhere on the dashboard —
W3 shipped the line to the 3 *Telegram* surfaces only. The one honest signal
that *did* land (the NAV box) lives in the **sidebar**, which on mobile
collapses off-screen first (`initial_sidebar_state="expanded"` does not survive
a phone viewport).
**Problem:** Sprint-26 P1-4 explicitly flagged this and it is **entirely
untouched**. The founder opens the dashboard on his phone and the first thing
he sees is "Institutional Edition" and a treemap — *Bloomberg terminal*, not
*my companion*. The verdict line that now warmly greets him on Telegram is
nowhere here. Worse, the honest NAV warning — the one genuine W1 win — is in
the first thing a phone hides. The dashboard got *honesty* but no *voice*, and
the honesty it got is positioned where the phone won't show it.
**Low-risk fix:** port the existing `whatnow`/verdict + the NAV-freshness state
(already computed at `:111-118`) into a top-of-page "מצב היום" strip ABOVE the
tabs and ABOVE the fold; soften the title (drop "Institutional Edition"). Pure
presentation, reuses computed values. **This is now the single highest-impact
remaining UX change** (P0-1 is higher-stakes for *trust*; this is highest for
the *"hooked" / "companion"* goal the founder named as primary).

### P0-3 — Disclosure density is unranked AND now slightly worse (Sprint-26 P0-3 untouched; W3 lengthened the report)
**Where:** `report_renderer.build_summary_text` still appends, flat and
equal-weight, in one bubble: excluded (`_summary_excluded_lines`) + unlinked
(`_summary_unlinked_lines`) + open-book-cmp + open-book unlinked + NAV
disclosure (`_nav_disclosure_lines`) + (chart) thermometer — and now W3
*prepends* a new top line + blank separator (`:506,582`). No "ℹ️ הערות נתונים
(3)" collapse header exists (grep confirms).
**Problem:** Sprint-26 P0-3 (rank/collapse routine disclosures, promote only
the decision-relevant one) was **out of W3's scope and not done**. The report
is now *longer* (good lede on top, same flat caveat stack on the bottom). The
"trains the user to skim past *all* disclosures, including today's important
one" anxiety risk is **not reduced and marginally amplified**. The honesty
content remains an asset; the flat, un-prioritized layout remains the
liability — now sandwiching a strong opening line above an unchanged wall.
**Low-risk fix:** unchanged from Sprint-26 — visual hierarchy only: collapse
routine disclosures under one calm "ℹ️ הערות נתונים (N)" header, promote ONLY
the disclosure that is active+decision-relevant *this period* (e.g. a stale
NAV scaling today's R) to top-level. Zero wording/number change; verbatim
Mark-governed strings stay.

---

## P1 — Significant; erodes the "companion / in-control" feel

### P1-1 — NEW Sprint-27 honesty crack: the C1 message promises a resume the code does not perform
**Where:** `telegram_bot._require_active_dev_session` (`telegram_bot.py:196`)
sets `user_state[chat_id] = {"action": "awaiting_dev_pin"}` — the *originally
intended privileged action is discarded*. The new humanized copy
(`:204-206`) says **"הזן את ה-PIN ונמשיך מכאן"** ("enter the PIN and we'll
continue *from here*"). After a valid PIN (`:248-250`) the code only opens the
dev menu — the user is **not** returned to the action he was doing. The
success message (`:249`) still says generic "*פגישה פעילה ל-30 דקות*" with **no
actual expiry clock time**.
**Problem:** This is the *one place Sprint-27 made things worse on the
system's own terms*. CLAUDE.md's prime directive is "never present something
the system can't back up." The old blunt wording was honest-by-being-cold; the
new warm wording is **honest in tone but makes a promise the behavior breaks**
("continue from here" → actually dropped back to menu). For the founder, who
hits C1 more than any other gate while operating, this is a small daily
trust-paper-cut introduced by a UX fix. Sprint-26 P1-2's (a) state expiry time
and (b) soft pre-expiry nudge and (c) actually resume the pending action were
**all not done** — only the wording changed, and the wording now describes
behavior (c) that does not exist.
**Low-risk fix (UX + the resume that was already scoped in Sprint-26 P1-2):**
either (i) deliver the actual pending-action resume so "ונמשיך מכאן" becomes
true, or (ii) until then, change the copy to what the code *actually* does
("הזן PIN וחזור לתפריט המפתח") — the honest description. Plus the Sprint-26
P1-2 (a) explicit expiry clock on success and (b) ~5-min soft nudge. Security
(fail-closed, TTL, constant-time compare) untouched.

### P1-2 — No `/start`, no onboarding — first contact is still "Sentinel Standby" (Sprint-26 P1-1, untouched)
**Where:** `telegram_bot.py` — still no `commands=['start']` handler; unknown
text still falls to `🎯 *Sentinel Standby*\nמערכת מוכנה לפעולה…`
(`telegram_bot.py:835`).
**Problem:** Out of W3 scope, not done. A companion greets and orients you;
first contact is still a cold standby string. Misses the
"accessible/personal/hooked" hook at the exact first moment. The new "🧭 מה
עכשיו?" voice proves the system *can* speak warmly — making its silence at
hello more conspicuous now, not less.
**Low-risk fix (unchanged from Sprint-26):** warm `/start` + friendlier
fallback — one line of identity, the single most useful action, a pointer to
חדר מצב. Copy + one handler.

### P1-3 — The חדר-מצב "all-OK" line is good but still generic; the digest "all-OK" line is weaker
**Where:** `telegram_portfolio.py:544-545` non-critical branch:
"{n} פוז' במעקב, אין מצב קריטי — עבור על הכרטיסים, אין פעולה דחופה."
`risk_monitor.py:454-455`: "{n} פוז' תחת מעקב, אין פעולה דחופה — עקוב לפי
הפירוט." Both are honest (correctly *never* "הכול תקין") but generic.
**Problem:** The *critical* branch is sharp and personal (names symbols); the
*calm* branch is a flat reassurance with no personal texture — the exact moment
a companion could build the addictive "it knows me" feeling ("התיק יציב, הסטופ
שהידקת ב-NVDA מחזיק"). This is the gap between "useful" and "hooked." Not a
defect — a missed lever, and the single biggest *addictive* one (== Sprint-26
P2-2, still unaddressed).
**Low-risk fix (future Phase):** when calm, occasionally reflect one concrete
*personal* fact already in state (a tightened stop that held, a streak, an
adherence stat) instead of the generic clause. Reuses existing
`risk_journal`/adherence/MAE-MFE; presentation only.

### P1-4 — `decision_syms` can list many symbols inline; long-line RTL fatigue
**Where:** `telegram_portfolio.py:541-542` /
`risk_monitor.py:451-452` — `', '.join(decision_syms/urgent)` inline in the
lede with no cap.
**Problem:** With 6+ critical positions the "מה עכשיו?" line becomes a long
comma string mid-RTL — the one line that must scan instantly becomes the
hardest to scan. Low frequency but high-stakes (it only happens when things are
*bad*, exactly when clarity matters most).
**Low-risk fix:** cap at ~3 names + "+N נוספות" in the lede; full list stays in
the cards/detail below (already there). Presentation only.

---

## P2 — Polish; would make it *delightful* (Sprint-26 P2 list, status now)

- **P2-1 personal tone** — still uniformly procedural in the cards/bullets;
  the new lede is the only warm voice. *Not addressed; still backlog.*
- **P2-2 personalization / "being known"** — still nothing mirrors the user's
  own history back at him. **The single biggest missed *addictive* lever, still
  open.** (Folded into P1-3 above as the highest-value P2.)
- **P2-3 separators inconsistent** (`〰️`, `───`, `─────`, `SEP`) — unchanged.
- **P2-4 emoji semantics overloaded** (🚨/🔴 mean several things) — unchanged;
  W3 *added* 🧭 and 🛡️ (both used consistently — good, keep the discipline).
- **P2-5 `/help` flat** — still a flat list, not task-oriented — unchanged.
- **P2-6 backtick-dense numbers** — unchanged; the new lede is correctly
  prose-not-backtick (good model for the rest).
- **P2-7 missing research dossier** — `SPRINT26_RESEARCH_DOSSIER.md` now
  EXISTS; **`SPRINT28_RESEARCH_DOSSIER.md` is ABSENT.** Same gap, new sprint.

---

## Cross-check: do the disclosures build trust or create anxiety — NOW?

**Per-disclosure: still trust** (each honest line is right, untouched, intact).
**In aggregate: marginally MORE anxiety-shaped than Sprint-26**, because W3
added a strong top line but left the flat bottom caveat stack unranked — the
report grew, the wall didn't shrink (P0-3). The fix is still hierarchy, never
suppression.

**Is silence ever mistaken for "all good" — NOW?** **Yes, still — P0-1, and it
is still the most serious finding.** Interactive empty-state is fixed; the
passive monitor's silence (crash vs healthy vs empty) is **unchanged**. This is
the same Sprint-26 P0-2, half-closed.

**Does "🧭 מה עכשיו?" feel like a sharp personal mentor?** On the **critical**
branch and on live חדר-מצב: **yes** — specific, earned, names the symbols, does
not contradict the body, leads with NAV honesty when NAV isn't live. On the
**calm** branch and the **weekly/monthly** summary: **competent but generic** —
a correct sentence, not yet a mentor who *knows him*. It is no longer a
terminal; it is not yet addictive.

---

## למנכ״ל — חוויית המשתמש בשפה פשוטה

**האם זה *עכשיו* מרגיש כמו מלווה אישי?** **קרוב יותר — אבל עדיין לא לגמרי.**
אתמול (Sprint-27) שלושה דברים *באמת* עבדו, ואתה אמור להרגיש אותם:

1. **הדאשבורד כבר לא משקר על ה-NAV.** ירוק "Live" רק כשזה באמת חי; אחרת אזהרה
   כתומה כנה. זה תיקון אמיתי — **לשמור עליו.**
2. **יש סוף-סוף *קול* בראש שלושה מסכים בטלגרם** — שורת "🧭 מה עכשיו?". במצב
   קריטי ובחדר-מצב היא **חדה ואישית** (אומרת לך *אילו מניות* דורשות החלטה). זה
   בדיוק מה שביקשת.
3. **ההודעות של "עצרתי את החיזוק" ושל ה-PIN** נשמעות עכשיו כמו שומר-ראש, לא
   כמו מכונה. ה-B3 ("לא כתבתי כלום, כדי להגן על הכסף שלך") — **מצוין.**

**אבל — הדברים שאתמול *לא* סגר, ואחד שאתמול *שבר*:**

1. **הבעיה הכי מסוכנת עדיין פתוחה.** כשאין פוזיציות — או אם המנטר נופל — אתה
   *לא מקבל כלום*. שקט = או הכול טוב, או המערכת מתה, ואתה לא יכול לדעת. את זה
   ביקשנו לתקן והוא תוקן רק *חצי* (רק כשאתה נכנס לבד; לא בשקט היומי). **זו עדיין
   הסכנה מספר 1.**
2. **הקול לא הגיע לדאשבורד** — המסך שאתה הכי סביר לפתוח בנייד. הוא עדיין נפתח
   ב-"Institutional Edition" וגרף. אין שם "מצב היום". וההודעה הכנה היחידה
   ש*כן* נכנסה (ה-NAV) יושבת בסיידבר שהנייד מסתיר ראשון.
3. **אתמול נוצר סדק כנות חדש קטן:** הודעת ה-PIN אומרת "נמשיך מכאן" — אבל הקוד
   *לא* ממשיך מאיפה שהיית, הוא זורק אותך לתפריט. נימה חמה שמבטיחה משהו שהמערכת
   לא מקיימת. בשבילך, שנתקל בזה הכי הרבה — זו שריטת-אמון יומית קטנה.

**3–5 השינויים שיהפכו את זה למשהו שתתמכר אליו (לפי סדר השפעה):**
1. **דופק יומי חיובי + הודעת "0 פוזיציות"** — שורה אחת רגועה, כדי ששקט יהיה
   הרגעה ולא חוסר ודאות. (פותר את הסכנה מס' 1.)
2. **"מצב היום" בראש הדאשבורד + ריכוך הכותרת** — אותו קול שכבר יש בטלגרם,
   גם במסך שאתה פותח בנייד.
3. **לתקן את הסדק של ה-PIN** — או שהמערכת *באמת* ממשיכה מאיפה שהיית, או
   שהמילים יתארו את מה שהיא *באמת* עושה.
4. **לדרג את ההסתייגויות** — להבליט רק את זו שחשובה היום, השאר מקופל בשורה אחת.
5. **לשקף אותך לעצמך כשהכול רגוע** — "הסטופ שהידקת ב-NVDA מחזיק". זה הלחצן
   *הכי ממכר* ועדיין לא נגעו בו.

**שורה תחתונה:** Sprint-27 נתן לך *קול* — וזה גדול. עכשיו חסר לקול **כיסוי**
(דאשבורד + שקט), וצריך **לסתום סדק כנות אחד שהוא בעצמו פתח.** הנשמה (היושר)
שרדה במלואה — וזה הדבר הכי חשוב שאתמול עשה נכון.

---

## מה צריך לעשות

עדיפות לפעולות מנכ״ל (כל אחת Phase מנוהל בנפרד — אין קוד בסבב הזה):

1. **[P0] לאשר Phase: דופק יומי חיובי + הודעת "0 פוזיציות / המנטר רץ".**
   פותר את עמימות-השתיקה בערוץ הפסיבי — **הסכנה הכי גבוהה, עדיין פתוחה**
   מ-Sprint-26. שורה אחת, אנטי-ספאם.
2. **[P0] לאשר Phase: "מצב היום" בראש הדאשבורד + ריכוך הכותרת
   ("Institutional Edition" יורד) + העלאת אזהרת ה-NAV מעל הקיפול.**
   **ההשפעה הכי גבוהה למטרת "התמכרות/מלווה"** — שימוש חוזר בערכים שכבר מחושבים.
3. **[P1] לאשר Phase: תיקון סדק ה-C1** — או resume אמיתי של הפעולה הממתינה
   (כפי ש-Sprint-26 P1-2 כבר ביקש), או יישור הניסוח למה שהקוד באמת עושה; +
   שעת-פקיעה מפורשת + נדנוד רך. אבטחה ללא שינוי.
4. **[P0/P1] לאשר Phase: היררכיית הסתייגויות** — קיפול הרוטיניות תחת כותרת
   רגועה, הבלטת הרלוונטית-להיום בלבד. נוסח/מספרים ללא שינוי (מילים של Mark
   נשמרות). דחיפות עלתה: W3 *האריך* את הדוח.
5. **[P1] לאשר Phase: `/start` + fallback חם.** Copy + handler אחד.
6. **[P1] לאשר Phase: שיקוף אישי במצב רגוע + cap לרשימת הסימולים בשורת הלדה.**
7. **[P2] Backlog מענג:** טון אישי, מפרידים אחידים, מקרא אימוג'י, `/help`
   מבוסס-משימה.
8. **[Ops] לייצר `SPRINT28_RESEARCH_DOSSIER.md` החסר** לפני ה-Phases — אותה
   פערת-תיעוד שחזרה מ-Sprint-26.

**עיקרון מנחה (ללא שינוי):** לעולם לא להחליף יושר בחום — ולוודא שכל מילה
*חמה* שהמערכת אומרת, היא גם מילה שהמערכת *מקיימת*. הסדק של ה-C1 הוא התזכורת
שאפילו תיקון-UX יכול לפגוע בנשמה אם הניסוח מבטיח מה שההתנהגות לא נותנת.
