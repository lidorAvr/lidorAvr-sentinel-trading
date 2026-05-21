# Meeting E1 — Behavioral Design (External Strategist)

External strategist, one-meeting engagement. Frameworks in play: BJ Fogg B=MAT, Nir Eyal Hooked (Trigger → Action → Variable Reward → Investment), James Clear habit-stacking, Kahneman System-1/System-2, Skinner variable-ratio reinforcement. I do not work here; I owe you outsider honesty, not internal politeness.

## Persona + lens

The founder is not a casual user. He is a sophisticated discretionary trader who already self-rejects with `"ללא הסבר"` and `"עדיין לא"` — that is not disengagement, that is a competent person refusing to spend cognition on a surface that hasn't earned it. The bot is treated as a **read-on-demand console**, not a partner. The goal is not to increase trade count; it is to make the 16:30 and 23:00 Telegram bells the moment he WANTS to look — because what arrives is something only Sentinel knows about HIM. Variable reward must come from his own history reflected back, not from market noise. Investment must be journaling-shaped: every tap makes the next message smarter. Anti-patterns: streak counters, confetti, FOMO, "the market is hot" pings. Those would make him uninstall in a week.

## 1. Edge Mirror

- **Trigger type:** external (16:30 push) → internal (curiosity about own pattern)
- **Mechanic:** Fogg Ability — make self-reflection effortless by pre-computing it. Hooked self-reward.
- **Variable reward shape:** self (different personal stat surfaces each open — sometimes hold-time, sometimes win-rate-by-hour, sometimes regime-fit)
- **Investment payback:** each open trains a "what surprised me?" 1-tap tag (👁/🤷/❌) that refines which stat surfaces next time.
- **Hebrew sample:**
  > 09:30 NY · אתה ב-S9 חיובי 4 ימים ברצף — בפעם הקודמת שזה קרה (12 במרץ) חתכת רווח מוקדם ב-AAPL. שווה לזכור היום.
  > [👁 ראיתי] [🤷 לא רלוונטי]
- **Sustainability:** 9/10 — the data pool (his own trades) grows monotonically; surfaces rotate.
- **MUST-have:** 9/10 — no other app on earth can say "in March you cut early in this exact regime."

## 2. Gate Receipts

- **Trigger type:** external (23:00) → relational (system as second opinion)
- **Mechanic:** Loss-aversion inversion — reframe the clamp not as restriction but as proof-of-value. Habit-stack onto end-of-day review.
- **Variable reward shape:** self (savings tally is non-linear — some weeks zero, some weeks dramatic)
- **Investment payback:** he can tap "agree / disagree retroactively" on past clamps → trains the gate model on his post-hoc judgment.
- **Hebrew sample:**
  > סגירה · החודש המערכת חסמה 3 העלאות סיכון. אחת מהן (14/05, NVDA) הייתה היום נגמרת ב-−1.4R. שתיים עדיין פתוחות לשיפוט.
  > [שפוט עכשיו]
- **Sustainability:** 8/10 — assumes clamp events keep happening; in calm regimes goes silent (which is fine, not noise).
- **MUST-have:** 10/10 — directly answers "why am I paying attention to this thing."

## 3. Sharp-Hour Whisper

- **Trigger type:** external, time-targeted to HIS personal Wins-After-Hour peak (not market open generically)
- **Mechanic:** BJ Fogg Prompt at peak Ability window. Habit-stack onto an existing strong moment.
- **Variable reward shape:** search (different "what to look at" each day — but never a ticker recommendation, only a question)
- **Investment payback:** he confirms/denies "sharp now?" → personal alertness curve self-tunes.
- **Hebrew sample:**
  > 17:42 · החלון שלך. ב-86% מהמקרים בשעה הזו לקחת החלטות חיוביות. שאלה להיום: יש פוזיציה אחת שאתה דוחה מלגעת בה? למה?
  > [חד] [לא חד היום]
- **Sustainability:** 9/10 — the curve refines forever; the question template rotates from a bank.
- **MUST-have:** 8/10 — feels like a coach who actually watched him.

## 4. Loss-Sequence Tripwire

- **Trigger type:** internal-via-external — only fires when his Loss-After-Sequence pattern is one step from triggering.
- **Mechanic:** Kahneman System-2 interrupt. Pre-commitment device. Habit-stack: "before the next click."
- **Variable reward shape:** self (sometimes it's protective, sometimes it confirms he's actually fine — variability matters)
- **Investment payback:** every interrupt logs his override reason → builds his own personal "tilt vocabulary."
- **Hebrew sample:**
  > שים לב · 2 הפסדים ברצף + שעה מחוץ לחלון החד שלך. בעבר הצירוף הזה הוביל ל-trade שלישי גרוע ב-7 מתוך 9 פעמים. עצור שלוש דקות?
  > [עצרתי] [לא רלוונטי הפעם — סיבה?]
- **Sustainability:** 10/10 — fires rarely by design; rarity preserves signal.
- **MUST-have:** 10/10 — this is the feature he'll tell people about.

## 5. Bucket Mirror

- **Trigger type:** external (close), relational (ALGO vs MANUAL "scoreboard against himself")
- **Mechanic:** Bandura self-efficacy — visible mastery feedback. Variable-ratio reinforcement.
- **Variable reward shape:** social-against-self (MANUAL-you vs ALGO-you vs DATA_INCOMPLETE-you)
- **Investment payback:** he can mark "this MANUAL trade was actually a system signal I executed" → reclassifies bucket, sharpens stat_bucket truth.
- **Hebrew sample:**
  > סגירה · השבוע: MANUAL 3W/1L · ALGO 2W/2L · DATA_INCOMPLETE 1. ה-MANUAL שלך מוביל ברצף שלישי. ALGO בפיגור — שווה ביקורת?
- **Sustainability:** 8/10 — only interesting while buckets diverge; if they converge, retire.
- **MUST-have:** 7/10 — sophisticated, but needs the divergence to stay alive.

## 6. Regime Memory

- **Trigger type:** external (open), triggered by regime transition detection
- **Mechanic:** Hooked variable reward (search) — surprise from his own archive.
- **Variable reward shape:** search (which past analog gets surfaced is unpredictable)
- **Investment payback:** he tags "analog accurate / analog wrong" → improves regime-similarity matcher.
- **Hebrew sample:**
  > פתיחה · המשטר היום דומה ל-22/01 (transition→bull, heat M21 חיובי). אז עשית +2.1R בשבועיים. גם אז התלבטת על הסיכון. מה החלטת בסוף?
- **Sustainability:** 9/10 — analog pool grows; each open generates a different match.
- **MUST-have:** 9/10 — "the system remembers things I forgot" is the single strongest pull.

## 7. Reconciliation Streak

- **Trigger type:** external (23:00), internal-pride driven (data-hygiene craftsmanship)
- **Mechanic:** Clear habit-stack — attach hygiene check to existing close ritual. Mastery, not gamification.
- **Variable reward shape:** self (gap shrinks/grows visibly; trend is the reward, not a number)
- **Investment payback:** every reconciliation tap creates an audit point → makes future broker drift detectable.
- **Hebrew sample:**
  > סגירה · פער ברוקר↔Sentinel: 0.12% (היה 0.41% לפני 30 יום). מגמה: מתכווצת. סריקה מהירה?
  > [אישור] [יש פער חדש]
- **Sustainability:** 9/10 — hygiene is a quiet long-term virtue, doesn't decay.
- **MUST-have:** 7/10 — not sexy, but craftsmen care about this.

## 8. Hold-Or-Cut Dialectic

- **Trigger type:** external (open), targets open positions only
- **Mechanic:** Pre-commitment + Fogg Motivation. Forces tiny System-2 articulation before market touches it.
- **Variable reward shape:** self (he sees his own past articulations vs outcomes)
- **Investment payback:** 1-line "thesis-of-the-day" per open position → builds a journaled position narrative he can audit at exit.
- **Hebrew sample:**
  > פתיחה · 3 פוזיציות פתוחות. ב-MSFT שינית עמדה לאחרונה (cut→hold ב-19/05). מה התזה שלך להיום במשפט אחד?
  > [תשובה: ___]
- **Sustainability:** 10/10 — journaling compounds; each entry makes the next exit smarter.
- **MUST-have:** 9/10 — turns Telegram into a thinking surface, not a status screen.

## 9. Rejected-Raise Echo

- **Trigger type:** external (open), recall-based — surfaces his OWN past rejections
- **Mechanic:** Cognitive consistency (Cialdini) — his past self speaks to his present self. NOT a nudge to accept; a nudge to be coherent.
- **Variable reward shape:** self (sometimes the past rejection looks wise, sometimes costly — both teach)
- **Investment payback:** he can attach a richer reason to old terse rejections ("ללא הסבר" → upgraded) → fills the journal gap that caused this whole meeting.
- **Hebrew sample:**
  > פתיחה · לפני 9 ימים דחית העלאה ל-0.85% עם "ללא הסבר". מאז: 2 ימים חיוביים, 1 שלילי. רוצה להוסיף סיבה עכשיו, בזמן שזה עוד טרי?
  > [הוסף סיבה] [דילוג]
- **Sustainability:** 10/10 — every rejection is fuel; backfilling thin journal entries is endless.
- **MUST-have:** 10/10 — directly fixes the exact friction signal that produced this engagement.

## 10. End-Of-Day Verdict

- **Trigger type:** external (23:00) — single closing artifact
- **Mechanic:** Habit-stack terminal ritual. Variable-ratio: the "verdict" template changes nightly.
- **Variable reward shape:** self (the system grades the PROCESS, not the P&L — sometimes a losing day gets a green verdict, sometimes a winning day gets yellow)
- **Investment payback:** he confirms/overrides verdict → trains the process-grading model. Builds a process-quality time series independent of P&L.
- **Hebrew sample:**
  > 23:00 · ירוק תהליכי. P&L היום שלילי, אבל: לא חרגת מסיכון, סגירה במחיר תזה, אין trade-after-loss. תהליך נקי.
  > [מסכים] [לא מסכים — למה]
- **Sustainability:** 10/10 — decouples engagement from market mood; works in any regime.
- **MUST-have:** 10/10 — "the only system that praises me on a losing day for trading well" is unique and durable.

## Cross-cuts

Patterns that recur across the ten — these are the design DNA, not the individual ideas:

- **Self-as-variable-reward.** Every idea pulls from his own archive. Market data is never the surprise; he is. This is the only sustainable variable reward for a sophisticated user — markets eventually feel like noise, but personal patterns keep deepening.
- **Investment is journaling.** Every tap leaves a residue (tag, override reason, thesis, retroactive judgment). Six months in, the journal IS the moat. Without the investment loop these are just push notifications.
- **Verdicts on process, not P&L.** Rewarding outcomes encourages outcome bias. Rewarding process is what makes him trade BETTER not MORE — directly serves the brief.
- **Rare-fire > daily-fire for the high-stakes nudges.** #4 (Tripwire) and #2 (Gate Receipts) gain power from scarcity. Daily-fire ideas (#1, #8, #10) are journaling habits — different cadence, different role.
- **Two-tap maximum.** Every surface offers a 1-tap dismiss AND a 1-tap deepen. Never three taps. Never a form.
- **Honesty about data state.** Where Sentinel doesn't have live data (DATA_INCOMPLETE bucket, recon gap, cached prices), the surface must say so. CLAUDE.md prime directive is also a trust-equity move: opacity destroys the loop faster than missing data does.

## What to AVOID (anti-patterns I'd flag in this team)

- **Streaks and "don't break the chain."** Sophisticated traders see through this immediately. Also creates a perverse incentive to over-engage on flat days.
- **Confetti, badges, levels, XP.** Patronizing. He will mute the bot within 72 hours.
- **Market-event triggers** ("SPY just broke 5200!"). Generic. Doesn't use Sentinel's unique data. Will rot into noise.
- **FOMO language** ("don't miss," "last chance," "smart traders are…"). Violates the "trade better not more" constraint. Also dishonest.
- **Predictable rewards.** A daily "your score is X" message dies in two weeks because the variability disappears. The reward must surprise.
- **Hiding data quality.** Showing a "live" number that is actually a 4-hour cache violates CLAUDE.md and shatters trust permanently. Always label freshness.
- **Generic motivational copy.** "אתה יכול לעשות את זה!" — he will uninstall.
- **Loss-aversion exploitation that distorts process.** E.g., "you'd be up 3R if you'd accepted that raise" — this is the exact distortion the brief forbids.

## Sign-off

These ten are not equally important. If this team ships only three, ship **#9 Rejected-Raise Echo** (fixes the literal friction that triggered this meeting), **#4 Loss-Sequence Tripwire** (the feature he'll tell people about), and **#10 End-Of-Day Verdict** (decouples engagement from market mood and makes process visible). The other seven are excellent but those three are the spine.

One more honest note before I leave the room: the reason `/portfolio` is pull-only today isn't a missing feature — it's that nothing the bot says is yet about HIM. The fastest path to engagement is not new triggers; it's making the existing 00:00 daily summary contain ONE sentence that only Sentinel could write. Start there, then layer these.

— External Strategist, Meeting E1
