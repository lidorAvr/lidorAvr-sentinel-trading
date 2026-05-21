# Meeting Engagement E3 — Hebrew Copy, Sentinel Trading

**Brought in by**: external Hebrew/Israeli UX copywriter (TLV).
**Brief**: the founder said *"מבלבל וארוך"*. The real diagnosis: the bot speaks **at** him, not **to** him. I'm here to fix the voice, not the structure.
**Scope**: 12 surface drafts for market open + close, plus a voice palette and cultural notes.

---

## Persona + approach

One Israeli founder. Sophisticated. English-fluent. Trades in Hebrew because he **thinks** in Hebrew when money is on the line. He needs a voice that sounds like someone who's been watching him trade.

Optimising for: **specificity** (every message carries one fact only Sentinel knows about him), **calm** over urgent, **re-readable on day 90**, **honesty about data state**, **Hebrew written in Hebrew** — not back-translated.

Default register: **wry-direct**. No vocatives. No emojis unless one earns its place. No exclamation marks except where something genuinely earned one.

---

## 1. Pre-open — first ping of the day

**Use-case**: ~20 minutes before NYSE open. Daily anchor message. Sets tone for the session without pushing him to trade.

**Hebrew text**:

```
‏פתיחה בעוד 22 דק׳.
‏NAV: ${nav_usd} · חשיפה: {exposure_pct}%
‏שעה חלשה היסטורית אצלך — win-rate בפתיחה {open_winrate}% מול {baseline_winrate}% בשאר היום.
‏אין חובה להיכנס.
```

**Variables**: `{nav_usd}`, `{exposure_pct}`, `{open_winrate}` (his personal stat), `{baseline_winrate}` (his own non-open baseline).

**Voice-register**: direct-flat. The last line — *אין חובה להיכנס* — is the entire point. A friend telling him: you don't owe the market anything at 16:30.

**Failure mode**: feels preachy if shown on a day his open-hour is strong. Guard: only fire when `open_winrate < baseline_winrate - 5pp`. Otherwise drop the comparison line.

**MUST-have**: **9**

---

## 2. Pre-open — when his open-hour edge is real

**Use-case**: same slot, but the data says his open hour is actually his best.

**Hebrew text**:

```
‏פתיחה בעוד 18 דק׳.
‏זו שעת הזהב שלך — {open_winrate}% ב-{n_open_trades} עסקאות.
‏לא תירוץ להגדיל סייז. תירוץ להישאר ערני.
```

**Variables**: `{open_winrate}`, `{n_open_trades}` (sample size — important, prevents lying with small N).

**Voice-register**: wry. The last line is the anti-FOMO move — acknowledging the edge while explicitly refusing to weaponize it.

**Failure mode**: would feel manipulative if `n_open_trades < 25`. Guard: gate on sample size, fall back to draft #1.

**MUST-have**: **8**

---

## 3. Sizing nudge — chronic under-sizing on conviction names

**Use-case**: fires when a watchlist ticker shows persistent under-sizing vs. target on his historical conviction trades. Pre-open, contextual.

**Hebrew text**:

```
‏MRVL חוזר ל-watchlist.
‏ב-{n_trades} הכניסות האחרונות עליו היית ב-{avg_size_ratio}x מהיעד.
‏אם תיכנס היום — תכניס את הסייז שאתה באמת מאמין בו, או אל תיכנס.
```

**Variables**: `{n_trades}`, `{avg_size_ratio}` (e.g. `0.41`).

**Voice-register**: direct. Almost confrontational, but with the escape hatch — *או אל תיכנס*. That's the brother voice: pick one, don't half-ass.

**Failure mode**: rots if it fires every day on the same ticker. Guard: cooldown 7 days per symbol; only fire if he's actually about to look at the ticker (lookup or quote command in last 24h).

**MUST-have**: **10** — this is the kind of thing nobody else will tell him.

---

## 4. Clamp save — the weekly receipt

**Use-case**: Monday pre-open OR after-close on Sunday. The recurring reminder that the gates actually work.

**Hebrew text**:

```
‏90 הימים האחרונים:
‏{clamp_count} פעמים הגדלה נחסמה.
‏עלות משוערת שנחסכה: ${clamp_savings_usd}.
‏אומדן, לא חישוב מדויק — ההפסד הוויפותטי מבוסס על R ממוצע לעסקה.
```

**Variables**: `{clamp_count}`, `{clamp_savings_usd}`.

**Voice-register**: clinical-honest. The fourth line is non-negotiable — saying "אומדן" upfront earns the right to use the number at all. This is the *anti-fallback-as-truth* line the system needs.

**Failure mode**: turns into noise if shown daily. Guard: weekly only, and only when `clamp_count >= 3`.

**MUST-have**: **10**

---

## 5. Pre-open — data is stale, say it plainly

**Use-case**: market data feed is cached / delayed / partial. The bot still needs to ping but cannot pretend.

**Hebrew text**:

```
‏פתיחה בעוד 25 דק׳.
‏הנתונים שיש לי כרגע מ-{data_age_minutes} דק׳ אחורה (ספק: {data_source}).
‏לא הייתי בונה מהם החלטה. כשיתעדכן — אשלח שוב.
```

**Variables**: `{data_age_minutes}`, `{data_source}` (e.g. `polygon-cached`).

**Voice-register**: blunt-honest. *לא הייתי בונה מהם החלטה* is the line a friend says. A bank would say *"ייתכן עיכוב בנתונים"*. He'd ignore that.

**Failure mode**: would feel weak if it fires on minor staleness. Guard: only when `data_age_minutes > 10` or source is explicitly fallback tier.

**MUST-have**: **10** — this is what separates Sentinel from every other tool.

---

## 6. Disposition mirror — cut-winners signature

**Use-case**: weekly close (Friday) when the disposition data shows he's been cutting winners early relative to his own historical pattern.

**Hebrew text**:

```
‏סיכום שבוע — תבנית שזיהיתי:
‏ממוצע החזקה במנצחות השבוע: {avg_hold_winners_min} דק׳.
‏ממוצע ההיסטורי שלך: {hist_hold_winners_min} דק׳.
‏מוקדם מדי. אתה משאיר R על השולחן — {r_left_estimate}R לפי הסימולציה.
```

**Variables**: `{avg_hold_winners_min}`, `{hist_hold_winners_min}`, `{r_left_estimate}`.

**Voice-register**: coach-direct. Two-word verdict (*מוקדם מדי*) then the cost. No softening.

**Failure mode**: harsh if the week's sample is too small or if he had a legitimate macro reason (CPI, earnings). Guard: require `n_winners >= 4` and surface a one-tap *"היה לי טריגר ספציפי"* button.

**MUST-have**: **9**

---

## 7. Post-close — the day was flat, don't pretend otherwise

**Use-case**: end-of-day report when realized PnL is within ±0.2R and nothing material happened. Most bots will manufacture excitement here.

**Hebrew text**:

```
‏סגירה: יום שטוח. {realized_r}R, {n_trades} עסקאות.
‏לא כל יום צריך להיות סיפור.
‏מחר 09:30 NYC.
```

**Variables**: `{realized_r}` (signed, 2dp), `{n_trades}`.

**Voice-register**: dry. The middle line is the *whole* draft. This is what a sharp friend would write — explicit permission to have a boring day.

**Failure mode**: would feel dismissive if he actually felt the day was meaningful (e.g. avoided a bad setup). Guard: if `gate_clamp_today >= 1`, swap to draft #8.

**MUST-have**: **10**

---

## 8. Post-close — flat day, but the gates worked

**Use-case**: PnL flat, but Sentinel clamped at least one bad raise today.

**Hebrew text**:

```
‏סגירה: {realized_r}R, אבל לא זה הסיפור.
‏היום הגייטים חסמו אותך {gate_clamp_today} פעמים — בלי זה, ההערכה: {clamp_savings_today}.
‏יום שקט הוא לפעמים יום שעבד.
```

**Variables**: `{realized_r}`, `{gate_clamp_today}`, `{clamp_savings_today}` (with units and "כ-" prefix to signal estimate).

**Voice-register**: warm-clinical. *לא זה הסיפור* is the framing inversion — telling him where to actually look.

**Failure mode**: smug if overused. Guard: max once per week per "saved" framing.

**MUST-have**: **9**

---

## 9. Algo-oversight nudge — when intervention paid off vs. when it didn't

**Use-case**: weekly review of his JPM algo decisions vs. his manual interventions.

**Hebrew text**:

```
‏שבוע אלגו:
‏התערבת {n_interventions} פעמים. תוצאה נטו: {intervention_net_r}R.
‏לא התערבת ב-{n_let_run} מקרים. תוצאה נטו: {let_run_net_r}R.
‏השבוע — האלגו ניצח אותך. אל תקרא לזה כישלון, תקרא לזה דאטה.
```

**Variables**: `{n_interventions}`, `{intervention_net_r}`, `{n_let_run}`, `{let_run_net_r}`.

**Voice-register**: direct-mature. The last sentence is the line that earns him trust — reframing without lying. If he won the week, swap to *"השבוע — אתה ניצחת את האלגו. שווה לבדוק אם זה תבנית או מזל."* Same DNA.

**Failure mode**: turns into a scoreboard he chases. Guard: never display in real time, only weekly. Never as a notification — only when he opens the summary.

**MUST-have**: **9**

---

## 10. Regime mismatch — his bucket isn't today's bucket

**Use-case**: pre-open. The market regime classifier flags today as a regime where his historical edge is weakest.

**Hebrew text**:

```
‏הרג׳ים היום: {regime_today}.
‏ההיסטוריה שלך בו: {regime_winrate}% ב-{regime_n} עסקאות, {regime_avg_r}R בממוצע.
‏לא אומר לך לא לסחור. אומר לך לדעת איפה אתה עומד.
```

**Variables**: `{regime_today}` (e.g. `chop-low-vol`), `{regime_winrate}`, `{regime_n}`, `{regime_avg_r}`.

**Voice-register**: advisor. The verb choice *לדעת איפה אתה עומד* is intentionally Hebrew-idiomatic — that exact phrase in English would be flat. In Hebrew it carries weight.

**Failure mode**: paternalistic if it fires when the edge is only marginally negative. Guard: only when `regime_winrate < baseline - 8pp` and `regime_n >= 20`.

**MUST-have**: **8**

---

## 11. Streak honesty — three green days in a row

**Use-case**: end of a 3+ day winning streak. The moment most retail systems start cheering. Sentinel does the opposite.

**Hebrew text**:

```
‏3 ימים ירוקים ברצף. {streak_r}R מצטבר.
‏היסטורית, יום 4 אצלך הוא {day4_winrate}% — נמוך מהממוצע שלך.
‏לא ביש מזל. עייפות החלטה.
```

**Variables**: `{streak_r}`, `{day4_winrate}` (his actual day-after-streak win-rate).

**Voice-register**: wry-protective. *עייפות החלטה* is the kind of Hebrew phrase he'll remember — names a real phenomenon without sounding clinical.

**Failure mode**: would feel like a jinx if it shows daily during streaks. Guard: show once at end of day 3, suppress on day 4 morning (let the data work, not the message).

**MUST-have**: **10**

---

## 12. Friday close — the weekly arc

**Use-case**: Friday after close. The one message of the week he should actually re-read on Saturday morning over coffee.

**Hebrew text**:

```
‏שבוע {week_num} — סגירה.
‏{realized_r_week}R · win-rate {wr_week}% · sizing accuracy {size_acc_week}%.
‏השורה שאני שומר לך לשבוע הבא: {weekly_signature_line}.
‏שבת שקטה.
```

**Variables**: `{week_num}` (e.g. `21/2026`), `{realized_r_week}`, `{wr_week}`, `{size_acc_week}`, `{weekly_signature_line}` (one Sentinel-generated sentence — e.g. *"הגדלות שנחסמו חסכו לך יותר ממה שעסקאות חדשות הוסיפו"*).

**Voice-register**: closing-the-week. *שבת שקטה* is the only sign-off in the whole system. Earned by being Friday. Israeli, not religious — just true.

**Failure mode**: the `weekly_signature_line` is the whole risk. If it's generic ("שבוע טוב!"), kill the message. Guard: only emit if the line passes a specificity check — must contain a number or a named pattern from his data.

**MUST-have**: **10**

---

## Hebrew voice palette — 5 registers across the system

1. **Direct-flat** — pre-open, neutral days. Short clauses, no adjectives. *"פתיחה בעוד 22 דק׳. NAV: $X."* Default.
2. **Wry-protective** — streaks, clamp saves, anywhere the bot prevents self-harm. Names the phenomenon (*עייפות החלטה*, *הגדלה מתוך אופוריה*). Never moralizes.
3. **Coach-direct** — disposition mirrors, sizing nudges. Verdict-first (*"מוקדם מדי"*), cost-second, escape-hatch-third. Brother voice.
4. **Clinical-honest** — cached/estimated/modeled data. Uses *אומדן*, *הערכה*, *מבוסס על*. Earns the right to quote numbers.
5. **Closing** — Friday / end-of-month only. Sparing. *שבת שקטה*. Anchors the rhythm.

(Reserved sixth: **incident-flat** — *"נתון נשבר. לא מציג מספרים עד שיתוקן."* No apologies, no "אנחנו עובדים על זה". Just status.)

---

## What the founder probably wants but won't say

1. **Someone willing to tell him to stop** — and mean it. Israeli sophisticated users *especially* resent cheerleaders. He's been told he's smart his whole life. What's missing is a system willing to say *"היום לא יום שלך — אל תיכנס"*. Western trading tools won't, because their KPI is engagement. Sentinel's KPI is his P&L — the opposite.

2. **Hebrew that wasn't translated.** A real Israeli sentence has a rhythm — short clause, comma, sharper clause. *"לא ביש מזל. עייפות החלטה."* That cadence doesn't exist in translated copy. If a sentence would survive literal back-translation into English, it's probably bad Hebrew.

3. **A bot that remembers — using *אצלך*.** *"שעת הזהב שלך"*, *"היסטורית אצלך…"*. American copy says "users like you". Israeli copy that lands says *"אצלך"* — singular, personal, earned by the data.

4. **Permission to have a boring day.** The biggest cultural mismatch between US trading tools and an Israeli founder: the assumption that every session must be a story. He runs a business; trading is one slot in his day. *"לא כל יום צריך להיות סיפור"* is the bot he opens on day 200. *"crush it today!"* is uninstalled by day 14.

---

## Anti-clichés — Hebrew phrases I'd outlaw

- **"בהצלחה!"** — empty. Signal, not blessing.
- **"היי {name}, מה שלומך?"** — vocatives kill register. He knows it's for him.
- **"קדימה!" / "יאללה!"** — pushes him to trade. Off-mission.
- **"שלום למשתמש היקר"** — corporate-banking. Inhuman.
- **"אנחנו ממליצים…"** — there's no "we". Use *"שווה לשקול"* or just state the fact.
- **"חשוב לציין כי…"** — translator-Hebrew. Drop the preamble, say the thing.
- **"מעולה!" / "כל הכבוד!"** — patronizing on a green day.
- **"זהירות!" / "אזהרה!"** with exclamation marks — cries wolf. Use the data, not the punctuation.
- **"בוקר טוב, היום הוא יום נהדר לסחור"** — every word is wrong.
- **Excessive emojis** — one or two per week, max.
- **"AI-powered" / "אינטליגנציה מלאכותית"** in user-facing copy — he doesn't care. He cares what it says about *him*.

---

## Sign-off

The diagnosis isn't *"מבלבל וארוך"*. It's *"זר"*. The bot sounds like a stranger. The fix isn't shorter messages — it's messages that prove the bot has been watching. Every draft above carries one fact that only Sentinel knows about him. That's the unlock.

If I had to leave one rule on the wall of the team room: **every Hebrew sentence in this system should be one a friend could have written about him last night.** If it could have been written about anyone — kill it.

— External copywriter, TLV. One meeting. Out.
