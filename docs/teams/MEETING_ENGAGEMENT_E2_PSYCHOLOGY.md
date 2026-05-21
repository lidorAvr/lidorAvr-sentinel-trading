# Engagement E2 — Trading Psychology Surfaces (External Coach Findings)

> External engagement. One meeting. Read-only artifact.
> Filed by: external trading-psychology coach (Steenbarger / Douglas / Tharp lineage).
> Scope: 10 Telegram surfaces that turn Sentinel from a pull-reference tool into a daily process mirror.

## Persona

Founder is a sophisticated, self-directed trader running real capital through Sentinel. Telegram-first, Hebrew RTL. Rejects friction. Rejected a 0.85% risk-raise twice in two minutes with no reason — that's not laziness, that's a system that asked for self-reflection without first earning it. He doesn't need motivation. He needs a mirror precise enough that ignoring it would feel sloppy.

Working assumption from Steenbarger: serious traders return daily to tools that **show them something about themselves they cannot see in the moment**. Not signals. Not market color. Self-data, surfaced at the moment of consequence.

Working assumption from Douglas: the edge is in the consistency of process, not the brilliance of any single trade. Surfaces must reinforce process even on losing days, especially on losing days.

Working assumption from Tharp: position-sizing is where psychology meets P&L. Sizing-accuracy drift (target vs actual) is the cleanest behavioral telemetry we have on him.

The ten surfaces below all draw from Sentinel's exclusive knowledge of *him*. None of them are market commentary.

---

## S1 — "מראת התזמון" (Time-of-Day Mirror)

- **Psychological mechanism**: state-dependent performance / circadian decision quality. Mirror-only.
- **Data assets**: `time_of_day_pnl` histogram per 30-min bucket, last 90 trading days; expectancy R per bucket.
- **When it fires**: market-open push, only if current local time falls in a bucket whose expectancy is in his bottom tercile.
- **Hebrew sample**:
  > בוקר טוב. בחלון 16:30–17:00 ב-90 הימים האחרונים: ממוצע 0.12R, סטיית-תקן 1.4R. החלון השני-הכי-רועש שלך. לא הוראה — תזכורת לפני שאתה לוחץ.
- **Doesn't say**: "אל תיכנס עכשיו." No directive. No FOMO inverse ("חכה ל-17:00 ואז תרוויח").
- **Risk**: founder learns the buckets and gamifies them → false confidence in "good" hours. Bound it: never quote a "good" bucket without also quoting its variance. Refuse to label buckets as ירוק/אדום.
- **MUST-have score**: **9** — this is the surface every prop desk wishes they had per-trader; it's pure self-alpha.

## S2 — "פער הסיזינג" (Sizing Drift)

- **Psychological mechanism**: loss aversion + Tharp's position-sizing-as-confession. Defensive exploit.
- **Data assets**: target_R per trade vs realized_R notional ratio, rolling 20 trades. (He's at 0.41x target on MRVL recently — Sentinel knows this.)
- **When it fires**: market-open, only if rolling sizing-accuracy <0.7 or >1.3.
- **Hebrew sample**:
  > 20 העסקאות האחרונות: סיזינג ממוצע 0.58x מהיעד. כשהיעד היה ברור, הידיים היו זהירות. שווה לשאול את עצמך אם זו אינטואיציה לגיטימית או הססנות.
- **Doesn't say**: "תגדיל פוזיציה." Never push toward more size. The question is about *self-knowledge*, not throughput.
- **Risk**: misread as nag → he mutes it. Bound it: fires max once/week; phrasing is investigative, not corrective.
- **MUST-have score**: **10** — this is the single surface most likely to make him forward a screenshot to himself.

## S3 — "חתימת הדיספוזיציה" (Disposition Signature)

- **Psychological mechanism**: disposition effect (Shefrin/Statman). Mirror-only.
- **Data assets**: cut-winners-early rate vs let-losers-run rate, 60-day window, vs his own baseline.
- **When it fires**: market-close, only when delta from baseline >1σ.
- **Hebrew sample**:
  > סגירה: השבוע חתכת מנצחות ב-0.7R בממוצע מתחת לטרגט, והחזקת מפסידות 0.4R מעבר לסטופ. זו לא טעות חד-פעמית — זה דפוס שחזר 3 שבועות ברצף.
- **Doesn't say**: "תן לרווחים לרוץ." Cliché. Only data, no slogan.
- **Risk**: framing a streak as a "pattern" when it's noise. Bound it: require 3-week persistence + statistical significance before firing.
- **MUST-have score**: **9** — Douglas would call this the core mirror.

## S4 — "יומן הסירובים" (Rejection Journal)

- **Psychological mechanism**: counterfactual reasoning + decision-quality vs outcome-quality (Annie Duke). Defensive.
- **Data assets**: every rejected suggestion (incl. the 0.85% raise rejected twice), with subsequent 5-day price action of the underlying.
- **When it fires**: weekly close (Friday), summarizes the week's rejections.
- **Hebrew sample**:
  > השבוע סירבת ל-4 הצעות. 3 מהן היו צודקות בדיעבד (הצלת 1.2R). אחת — העלאת סיכון 0.85% ביום ג' — בדיעבד הייתה מוסיפה 0.6R. הסירוב עצמו לגיטימי. השאלה: היה לו נימוק, או היה רק "לא עכשיו"?
- **Doesn't say**: "טעית שסירבת." Never. Decision quality ≠ outcome quality.
- **Risk**: hindsight bias weaponized against him. Bound it: ALWAYS report both correct and incorrect rejections; never frame outcome as verdict on decision.
- **MUST-have score**: **10** — directly addresses the exact behavior in the brief (silent rejection without reason).

## S5 — "טריגר הרצף" (Streak Trigger)

- **Psychological mechanism**: tilt detection / pre-tilt antecedents. Defensive.
- **Data assets**: loss-streak triggers — what preceded his last 5 losing sequences (time, regime, sizing, hour-since-prior-trade, recent gate-clamps).
- **When it fires**: streak-triggered (2 consecutive losses OR -1.5R day), once.
- **Hebrew sample**:
  > 2 הפסדים ברצף היום. ב-4 מתוך 5 הרצפים הקודמים שלך, העסקה השלישית נכנסה תוך 38 דקות מהשנייה ועם סיזינג 1.2x מהממוצע. רק תזכורת לפני הבאה.
- **Doesn't say**: "עצור למשך היום." Not your call as a tool. Anti-paternalistic.
- **Risk**: self-fulfilling — he sees "streak" and tilts. Bound it: framed as historical pattern, never as prediction. Never use word "תפסיק".
- **MUST-have score**: **10** — this is the surface that pays for the whole engagement on one bad afternoon.

## S6 — "הקלאמפ ששמר עליך" (Gate-Clamp Save)

- **Psychological mechanism**: process-trust reinforcement (Douglas: building belief in the system). Mirror.
- **Data assets**: gate-clamp history — every time the 4-gate clamped sizing, with realized outcome had the un-clamped size been used.
- **When it fires**: market-close, on days a clamp fired.
- **Hebrew sample**:
  > היום ה-4-gate הוריד פוזיציה ב-NVDA מ-0.9% ל-0.5%. בסגירה: ההפסד היה 0.7R. ללא הקלאמפ: 1.26R. הגייט עבד. שמור.
- **Doesn't say**: "תודה לגייט." No anthropomorphism. Just math.
- **Risk**: cherry-picking — only showing wins of the gate. Bound it: also show clamp-cost days (when clamp left R on the table); over time the balance must be honest.
- **MUST-have score**: **8** — builds trust in the system precisely on days he might second-guess it.

## S7 — "התפלגות ה-R שלך" (Your R Distribution)

- **Psychological mechanism**: anchoring defense / variance acceptance. Mirror.
- **Data assets**: personal R-distribution — mean, σ, skew, tails, hit-rate. Updated rolling.
- **When it fires**: market-open, Mondays only.
- **Hebrew sample**:
  > פתיחת שבוע. ההתפלגות שלך: ממוצע +0.18R, σ=1.6R, hit-rate 47%, זנב ימני (top 5%) +3.4R, זנב שמאלי -2.1R. אתה לא טריידר של hit-rate, אתה טריידר של זנב. שמור על הזנב.
- **Doesn't say**: "כוון להעלות hit-rate." That would push him into the wrong KPI for his style.
- **Risk**: he over-identifies with the tail and over-trades fishing for it. Bound it: pair with sizing-discipline note when tail-fishing is detected.
- **MUST-have score**: **9** — defines his identity-as-trader in numbers; powerful weekly anchor.

## S8 — "האאוטסורסינג ל-ALGO" (ALGO Outsourcing Pattern)

- **Psychological mechanism**: cognitive offloading / decision fatigue tracking. Mirror.
- **Data assets**: % of decisions delegated to ALGO this week vs his rolling mean, conditioned on time-of-day.
- **When it fires**: weekly close.
- **Hebrew sample**:
  > השבוע: 64% מההחלטות הועברו ל-ALGO (ממוצע 90 יום: 51%). הקפיצה כולה מ-15:00 והלאה. שווה לבדוק: עייפות, או שזה הזמן שבו ה-ALGO באמת טוב יותר ממך?
- **Doesn't say**: "תפסיק לסמוך על ALGO" / "תסמוך יותר על ALGO." Neither direction. Only the observation.
- **Risk**: framing delegation as weakness. Bound it: explicitly include the alternative reading ("ה-ALGO באמת טוב יותר") in the message.
- **MUST-have score**: **7** — high alpha-on-self but lower urgency than S2/S4/S5.

## S9 — "אישור הרגיים" (Regime-Conditional Win Rate)

- **Psychological mechanism**: recency bias defense / regime-aware framing. Mirror.
- **Data assets**: win-rate and expectancy conditioned on current detected market regime (trend / chop / vol-expansion), vs his own per-regime historical baseline.
- **When it fires**: market-open, when current regime ≠ yesterday's regime.
- **Hebrew sample**:
  > המשטר עבר ל-chop. ההיסטוריה שלך ב-chop: hit-rate 38%, ממוצע +0.04R. ב-trend: 54% ו-+0.31R. לא להפסיק לסחור — להוריד ציפיות ולהדק קריטריונים.
- **Doesn't say**: "שב בצד עד שיחזור trend." Never benching him.
- **Risk**: regime classification is noisy and he might over-trust the label. Bound it: always show classifier confidence; if <70%, surface degrades to "משטר לא ברור."
- **MUST-have score**: **8** — calibrates expectations daily without paternalism.

## S10 — "החלטה ללא נימוק" (Reason-Free Decision Counter)

- **Psychological mechanism**: meta-cognition prompt (Steenbarger's journal-as-mirror). Defensive.
- **Data assets**: count of decisions in last 7 days marked "ללא הסבר" / "עדיין לא" / null-reason.
- **When it fires**: market-close Friday, only if count ≥3.
- **Hebrew sample**:
  > השבוע: 5 החלטות בלי נימוק רשום. לא רע בהכרח — לפעמים אינטואיציה היא הנימוק. אבל אם תוכל לכתוב מילה אחת ליד הבאה, ההיסטוריה שלך תלמד מהר יותר.
- **Doesn't say**: "אתה חייב לתעד הכל." Friction without payoff = mute.
- **Risk**: nagging. Bound it: ≥3 threshold + max 1x/week + framed as future-self benefit, not present-self obligation.
- **MUST-have score**: **9** — directly metabolizes the exact behavior that triggered this engagement.

---

## Patterns across the 10

1. **Every surface uses self-data, not market data.** No surface tells him what NVDA will do. Every surface tells him what *he* tends to do.
2. **No surface gives a directive.** No "buy / sell / stop / increase." Surfaces end on questions or observations, never on imperatives.
3. **Every surface has firing-rate discipline.** Streak (S5), Monday (S7), Friday (S4/S8/S10), regime-change (S9), threshold-only (S2/S3/S10). Nothing fires daily by default — boredom is the enemy.
4. **Decision quality is separated from outcome quality** (S4 most explicitly; also S5, S6). This is the Annie Duke / Douglas axis. Without it, every losing day becomes a referendum on the trader.
5. **Variance is always shown with means.** A bucket's expectancy without its σ is a lie of omission (S1, S7). Sentinel never hides dispersion.
6. **Hebrew is short, direct, no English jargon, no emojis-as-affect.** Surfaces read like a quiet colleague, not a coach with a clipboard.

## Anti-patterns I'd reject

These look attractive. I'd kill them.

- **"Daily streak — 7 days of journaling!"** Gamification breaks process. The day he misses, he tilts to defend the streak. Casino mechanic. Reject.
- **"Today's motivational quote from Mark Douglas."** Patronizing. He's read the book. Quotes are noise. Reject.
- **"Leaderboard vs other Sentinel users."** Even hypothetically — social comparison destroys process. He's a sample size of one and that's the point. Reject.
- **"Predict the close — gamify your read."** Conditions him to value prediction over process. Tharp would walk out of the room. Reject.
- **"Auto-suggest a trade when sizing is below target."** This crosses from mirror to push. The whole engagement collapses. Hard reject.

## Sign-off

The founder doesn't need more information. He has a production system. What he needs is for that system to *show him to himself* at the two moments he's most plastic: market-open (intention) and market-close (reflection). The ten surfaces above are the smallest set that, deployed with the firing-rate discipline specified, would turn Sentinel from a reference tool into the thing he'd feel naked trading without.

Three surfaces are the spine: **S4 (Rejection Journal), S5 (Streak Trigger), S2 (Sizing Drift)**. If only three ship, ship those.

The rest of the work is restraint — not adding more surfaces, but refusing to add the wrong ones.

— external psychology engagement, one-meeting brief, filed read-only.
