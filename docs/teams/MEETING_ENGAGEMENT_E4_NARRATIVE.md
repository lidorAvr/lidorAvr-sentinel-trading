# MEETING_ENGAGEMENT_E4_NARRATIVE — Sentinel Story System

External consult, single meeting. Read-only design. No code, no schema, no UI mocks.
Brief: turn isolated `/portfolio` transactions into a daily, weekly, and monthly arc that
serves process, not engagement.

## Persona

External narrative consultant. Background: Pixar story structure (Andrew Stanton's
"Stories Are Promises Made and Kept"), Joseph Campbell's monomyth applied to product
behaviour, Robert McKee's STORY principles, narrative-design lead at a top game studio.
Specialty: emotional arcs that evolve across sessions, recurring tensions, payoffs that
earn themselves. I have not seen this codebase before today. I have read CLAUDE.md once.

I will not design entertainment. I will design a structure that turns the data Sentinel
already has into a frame the founder uses to think more clearly. If a beat would push him
to trade for the plot, the beat is wrong. The story must work on a flat day. Silence is a
beat. Refusal is a beat. "Not yet" is a beat.

## Story spine

### 1. The recurring characters

Five roles, named in Hebrew so the founder can recognise them when they speak. Names
are descriptive, not branded.

- **המנטור (The Mentor) — Sentinel itself.** Yoda, not Jarvis. Knows the founder's full
  history, never flatters, never panics, sometimes refuses. Speaks short. Cites the
  founder's own past back to him as evidence, not as opinion.
- **השוק (The Antagonist — the Tape).** Indifferent, not malicious. The market does not
  hate the founder; it does not know him. Sentinel never personifies it as a villain. It
  is weather. It is the environment the protagonist walks into each morning.
- **הדפוס (The Internal Flaw).** The founder's repeating signature: under-sizing
  conviction trades, over-cutting at first heat, gate-clamp triggers in the last hour.
  Sentinel names הדפוס explicitly when it sees it. הדפוס is a character because flaws
  in good stories have voice. The founder is not הדפוס. הדפוס is what he is working on.
- **השעה הטובה (The Ally — Best Hour).** The founder's strongest time-of-day window
  by historical WR. Sentinel reminds him this ally exists, especially when he is about
  to skip it. The Ally is also a constraint: if he trades outside his Ally without
  reason, Sentinel notes it.
- **הספר (The Chronicler — Risk Journal).** Not Sentinel. The journal itself, treated as
  a separate voice. Every decision and every rejected decision is written there.
  הספר is what makes payoff possible: without it, there is no "remember when".

### 2. The DAILY arc — 5 beats

All times Israel local. Beats fire only if data is present; missing data = silence,
never invented filler. Each beat ends with one question, not a recommendation.

**Beat 1 — Setup (16:00 IL, 30 min before open).**
- Data: yesterday's R, open positions carried, gate-clamp status, the founder's
  best-hour window for today's weekday, current weekly R running total.
- Emotional question: *What did I bring with me into today that is not the market's
  fault?*
- Sample opening: `אתמול נסגר ב‎-0.4R. שתי פוזיציות פתוחות. השעה הטובה שלך היום: 17:30–18:30. מה מהאתמול עוד איתך?`

**Beat 2 — Inciting incident (16:30 IL, open + 0–10 min).**
- Data: first 10-minute tape behaviour vs the founder's stated pre-market thesis (if
  logged), gate state, any auto-clamp that fired in the first prints.
- Emotional question: *Did the market confirm or refuse the story I came in with?*
- Sample opening: `הפתיחה לא תאמה את התזה שכתבת ב‎-15:50. הגייט עוד פתוח. האם אתה צופה, או רודף?`

**Beat 3 — Rising action (17:30–21:30, fires only on a real decision moment).**
- Triggered by: a new entry, a partial, a near-clamp, or 60 min of inactivity inside
  the founder's best hour. Not a clock beat — a *behaviour* beat.
- Data: position size vs his historical conviction-size median for this setup bucket,
  R-at-risk so far today, streak context.
- Emotional question: *Is this trade the size my conviction says, or the size my fear says?*
- Sample opening: `הגודל פה הוא 0.6 מהחציון שלך לסטאפ הזה. הדפוס מדבר. רוצה שאזכיר מה קרה בפעם הקודמת?`

**Beat 4 — Climax (22:00–22:30 IL, last 30 minutes).**
- Data: today's realised R, open R-at-risk, distance to a personal threshold (e.g.
  "+1R closes this week green"), gate-clamp history for the day.
- Emotional question: *Is there a real trade left here, or is there only my wanting
  one?* Sentinel never says "take it" or "don't". It surfaces the question.
- Sample opening: `30 דקות לסגירה. היום ‎+0.8R ממומש, 0.3R פתוח. אין סטאפ חדש שעומד בתנאים שלך. מה אתה מחפש עכשיו?`

**Beat 5 — Resolution (23:05 IL, post-close).**
- Data: today's R, what was logged in הספר, the one decision that mattered most
  (largest R-impact, positive or negative), the weekly arc position.
- Emotional question: *What did today teach me that I want tomorrow to remember?*
- Sample opening: `היום נסגר ‎+0.5R. ההחלטה שעיצבה אותו: לא להוסיף ב‎-21:10. הספר מחכה לשורה אחת ממך.`

The Resolution beat is the only beat that asks the founder to write. One sentence. No
template. If he skips, no nag — the absence is itself logged as a beat tomorrow.

### 3. The WEEKLY arc

Monday is exposition. Friday is the small payoff. The recurring tension across the
week is not P&L — it is *consistency of process*. Sentinel tracks a weekly "character
development" axis that is orthogonal to R:

- adherence to best-hour window
- size vs conviction match rate
- gate-clamp respect (did he try to override?)
- journal completeness

Monday open beat: `שבוע חדש. השבוע שעבר: 3 ירוקים, 2 אדומים, ‎+1.7R. הדפוס הופיע פעמיים. מה מהשבוע שעבר אתה לוקח, ומה אתה משאיר?`

Friday close beat (the small payoff): one paragraph that names *one* thing that
improved this week vs the trailing 4-week median — even on a red week. If nothing
improved, Sentinel says so plainly: `השבוע לא הראה התקדמות מדידה בתהליך. זה גם נתון.` No fake silver lining. Honesty is the payoff.

Wednesday is the mid-week pivot: Sentinel surfaces the week's strongest decision
*and* the week's weakest decision so far, side by side, without verdict.

### 4. The MONTHLY arc

The month is the boss fight, but the boss is not the market — it is the founder's
trailing-3-month process baseline. Milestones Sentinel surfaces:

- **Anniversaries of gate-clamps that saved him.** "לפני 30 יום הגייט עצר עסקה שהיתה
  נסגרת ב‎-1.4R לפי הסימולציה." Fired exactly once, on the day, never repeated.
- **Personal-record watch.** If the current month's process metrics (not R) are inside
  reach of his best-ever month, Sentinel names it once, mid-month, with the gap.
  Never as a goal — as a fact. `אתה בטווח של 3 ימי תהליך נקיים משיא אישי. זה לא יעד. זה רק מיקום.`
- **End-of-month chronicle.** A one-screen summary written from הספר's voice, not
  Sentinel's. It quotes the founder back to himself — three of his own journal lines
  from the month, chosen for signal, not for flattery.

The monthly arc is the only place Sentinel uses the word "מסע" (journey). Once a
month. Never weekly. Never daily. Scarcity makes the word mean something.

### 5. The "missed day" rule

If the founder does not open Telegram for 2+ days, the next beat he sees is *not* a
catch-up dump. It is a single line that welcomes him back at his current state, not
his last state.

- No "you missed 2 days of insights".
- No backlog scroll.
- No guilt vocabulary.
- The story has not reset. The arc waited.

Sample welcome-back beat: `ברוך שובך. השוק זז קצת. אתה במקום שבו הפסקת — שבוע ב‎+0.8R, הדפוס שקט. רוצה את התמונה של היום, או נתחיל מאתמול?`

The founder chooses the entry point. Sentinel does not choose for him. This is the
single most important rule in the system: *the mentor is not offended by absence.*

### 6. The "bad day" rule (-2R or worse close)

A -2R day is honoured, not coached. Sentinel's close-of-day beat on a -2R day:

- Does not say "tomorrow is a new day".
- Does not say "you can make it back".
- Does not list "lessons" in bullet form.
- Does not compare to a worse trader, real or hypothetical.
- Does not offer a discount on tomorrow's size unless the founder's own pre-written
  rules require it; if they do, Sentinel states the rule, not an opinion.

Sample -2R close beat: `היום ‎-2.1R. זה כואב. הוא קיים בתוך חודש שעדיין ‎+4.3R. הספר פתוח אם תרצה, או סגור אם לא. נדבר מחר ב‎-16:00.`

That is the whole message. The arc continues tomorrow without dragging today into
it. The next morning's Setup beat references the loss exactly once, neutrally, then
moves on. The loss is not a recurring antagonist — it is a single beat in a longer
shape.

### 7. The PAYOFF — the earned long-arc moment

The payoff is not a feature he unlocks. It is a sentence Sentinel earns the right to
say, and can only say once it is true. There are three payoff classes:

**Payoff A — The Callback (fires when conditions match a past beat).**
After ~60 trading days, when the founder faces a setup that closely resembles one he
mishandled earlier, Sentinel quotes *his own past journal line* back to him before
he acts. Not Sentinel's analysis — his words. Example surface:
`לפני 47 יום כתבת: "נכנסתי גדול מדי כי פחדתי לפספס". הסטאפ עכשיו דומה. הגודל שבחרת היום הוא 0.9 מהחציון. זה הבדל.`
That is the moment that makes the daily logging worth it. Not a graph. A sentence
from himself, returned at the exact moment it matters.

**Payoff B — The Quiet Record.** When a process metric (not R) crosses a personal best
over a meaningful window (e.g. 20 consecutive sessions inside size-vs-conviction
tolerance), Sentinel marks it once, plainly, with no celebration vocabulary.
`20 ימי תהליך נקיים ברצף. שיא אישי. זה הכל.`

**Payoff C — The Long Arc Closing.** Once per quarter, if the founder consented in
advance, Sentinel writes a single screen that frames the quarter as a chapter:
who the protagonist was at the start, what הדפוס did, what the Ally did, what הספר
recorded, and what carried forward. The quarter ends. The arc does not.

The payoff is the reason the daily beats exist. Everything else is setup for these
three sentences.

## 10 sample Hebrew beats (RTL, surface text)

1. Setup, post-green-week Monday:
   `בוקר. השבוע שעבר ‎+2.1R, שלוש מתוך חמש בשעה הטובה. הדפוס הופיע פעם אחת ביום ד׳. מה אתה מתכוון לעשות אחרת היום?`

2. Inciting, thesis-broken open:
   `הפתיחה הפוכה לתזה שכתבת ב‎-15:50. אין צורך לפעול. צפייה היא החלטה.`

3. Rising, under-sizing detected:
   `הסטאפ הזה — היסטורית WR 64%. גודל שבחרת: 0.5 מהחציון. הדפוס מדבר. רוצה לראות את שלוש הפעמים האחרונות?`

4. Rising, near-clamp:
   `הגייט קרוב להיסגר. עוד עסקה אחת בתנאים האלה תוביל לחסימה. זה לא עונש, זה הסכם שלך עם עצמך.`

5. Climax, clean +1R day, no setup left:
   `25 דקות לסגירה. ‎+1.0R היום. אין סטאפ פתוח שעומד בקריטריונים. לפעמים הסוף הוא פשוט סוף.`

6. Climax, flat day:
   `היום שקט. 0R. שקט הוא לא כישלון. הוא גם לא ניצחון. הוא בדיוק מה שהוא.`

7. Resolution, after a discipline win:
   `היום נסגר 0R, אבל לא נכנסת לעסקה ב‎-20:40 שהדפוס דחף אליה. הסימולציה אומרת שהיא היתה נסגרת ‎-0.8R. רשום את זה לעצמך.`

8. Welcome-back after 3 days away:
   `ברוך שובך. השוק זז. אתה לא פספסת. רוצה את היום, או נחזור לרגע לשבוע?`

9. -2R close:
   `‎-2.1R היום. הוא כואב והוא קטן ביחס לחודש. אין מה לתקן עכשיו. נדבר ב‎-16:00.`

10. Payoff A, callback to own journal:
    `לפני 47 יום כתבת: "נכנסתי גדול מדי כי פחדתי לפספס". הסטאפ עכשיו דומה. הגודל שבחרת הוא 0.9 מהחציון. זה הבדל אמיתי.`

## Anti-patterns — moves that would betray the founder

- **Cheerleading.** "כל הכבוד!" after a green trade. The mentor does not applaud. The
  mentor notices.
- **FOMO surfacing.** "הסטוק X זז ‎+4% בלעדיך." Never. Not even framed as data.
- **Streak gamification.** "יום 7 ברצף!" as if it were a habit app. Streaks exist
  internally and surface only when relevant to a decision.
- **Loss-chasing language.** "אפשר לתקן את היום." Forbidden vocabulary.
- **Plot pressure.** Any beat that implies "the story needs a trade now" is a defect.
  Flat days must read as complete.
- **Fabricated continuity.** If data is stale, cached, or estimated, the beat says so.
  No narrative voice over uncertain ground. CLAUDE.md is explicit on this.
- **Personifying the market as villain.** השוק is weather. Never an enemy with intent.
- **Reset on absence.** Treating a missed day as a failure to engage. The arc waits.
- **Generic mentor lines.** "כל יום הוא הזדמנות חדשה." If a line could be sent to any
  trader, it should not be sent to this one.
- **Over-quoting הספר.** Callback payoffs are rare by design. If used weekly, they
  stop meaning anything.

## Sign-off

The system already has the data. It does not need more telemetry. It needs a frame —
five recurring voices, five daily beats, one weekly small payoff, one monthly chapter,
and the discipline to stay silent when silence is the correct beat. The headline rule:
**Sentinel earns the right to speak by sometimes choosing not to.** Everything else
follows from that.

External consultant, engagement E4. Read-only. No code changed. Doc ends here.
