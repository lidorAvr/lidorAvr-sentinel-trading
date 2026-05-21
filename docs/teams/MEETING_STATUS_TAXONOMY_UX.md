# Meeting — Position-Status Tag Taxonomy (UX / Hebrew Copy lens)

**Lens:** UX / Telegram + Hebrew Copy (TLV copywriter, E3 register).
**Trigger:** Founder saw `🔴 שבור` on JPM (1 day old, −0.01R) and on PLTR (20 days old, stalled at −0.25R). One word, two fundamentally different positions, both wrong. The label collapsed.
**Bindings already on the wall:** E3 register (`אצלך` + brother-voice), Mark §X3 (AI-copy mirrors Hebrew on §3-class wording), `engine_core.py:1755-1766` (existing 11 state labels), `engine_core.py:381-419` (`build_management_action`).
**Output:** read-only plan. ENGINE owns predicates; UX owns the words.

---

## Language failure diagnosis

### Case A — JPM, 1 day old, −0.01R, labelled `🔴 שבור`

In Hebrew, **שבור** is terminal. *כלי שבור*, *יד שבורה*, *לב שבור*. It names a structural end-state — something that *was* whole and now isn't. Applied to a 1-day-old position that has barely moved, it says: *the thesis is dead before the thesis had a chance to exist*. The founder reads the screenshot and the next thought is *"אבל אפילו לא נתתי לו לזוז."* That gap — between what the word claims and what he knows is true about the position — is the trust break.

**Failure mode (Mark §3-class):** **fallback-as-truth disguise.** The model lacks information (1 day of data is below the proving window — `_NEW_MAX_DAYS = 2`, `_PROVING_MIN_DAYS = 3`), but the label asserts a *verdict*. Silence about "I don't know yet" gets dressed up as "it's broken." That is exactly the pattern §3 outlaws: presenting absence-of-evidence as a confident state.

### Case B — PLTR, 20 days old, −0.25R, stalled, labelled `🔴 שבור`

Here the math says something real — the position has been a coffin for three weeks, no follow-through, R-drift mild but persistent. But the structure isn't broken: the stop hasn't been hit, the trend line is intact, the violation score is low. Calling it שבור tells the founder *"close it now, it's dead"* — a directive disguised as a state. He looks at the chart and sees a quiet position, not a corpse. Another trust break, opposite direction.

**Failure mode (Mark §3-class):** **invitation collapses into directive.** §3 anti-list (per `MARK_MEETING_UX_RULINGS.md` and prior `MARK_SPRINT11/§3` lineage) prohibits the system from issuing a hidden imperative under the guise of a label. *שבור* in Hebrew is action-bearing: it commands closure. But the underlying state is *no movement, no signal* — which deserves observation, not an exit order. The action line `יציאה / הידוק מידי` then *amplifies* the directive. State and action stack into a push the data hasn't earned.

**Unified diagnosis:** current `🔴 שבור` carries **three claims at once** — (1) the position was once whole, (2) it has structurally failed, (3) you should exit. A single label covering three claims is a category error. When any one is false (Case A: claim 1 false; Case B: claim 2 false), the label lies. Cure: split the claims so each label only carries what its predicate proves.

---

## New label proposals

### 1. `👀 מוקדם` — fresh + low-score (too-new-to-call)

‏**Hebrew label:** ‏`👀 מוקדם`
**English mirror (§X3):** `👀 Too Early`
**State constant suggestion:** `POSITION_STATE_TOO_EARLY`

**Predicate (for ENGINE to set):** `days_held <= _NEW_MAX_DAYS` AND score in the would-have-been-Broken band AND `violation_score < 6` AND price still above stop. I.e. the data is consistent with "broken" *only because* there isn't enough data yet to be consistent with anything else.

**Rationale:** *מוקדם* is the exact word a friend uses when you ask him *"מה דעתך?"* about something he can't read yet. It says nothing about the position's eventual fate — only about Sentinel's *epistemic position*. That is honest. It also passes the §3 fallback-as-truth test cleanly: the label literally names the absence of evidence.

**Register note (E3):** native Hebrew register. No foreign tech-speak. Single word. Re-readable on day 200 — *מוקדם* in May means the same thing in November. The eye emoji 👀 carries "watching" without "alarmed," and is not used by any of the existing 11 labels.

**Rejected alternates:** *🆕 חדש — עוד לא הוכיח* (overloads existing `🆕 חדש`; two labels with *חדש* collide); *🧐 בהשגחה* (too clinical, hospital chart); *🤔 לא ברור* (uncertain-shrug — reads as Sentinel doesn't know its job). *מוקדם* shifts uncertainty onto *time*, not Sentinel's competence.

---

### 2. `❄️ קופא` — old + stalled (no movement, structure intact)

‏**Hebrew label:** ‏`❄️ קופא`
**English mirror (§X3):** `❄️ Stalled`
**State constant suggestion:** `POSITION_STATE_STALLED`

**Predicate (for ENGINE to set):** `days_held >= 7` (or whatever ENGINE picks above the proving window) AND `|R| < 0.5` AND `follow_through_score < ~45` AND `violation_score < 6` AND price still above stop. The position is sitting. Not bleeding, not working, not breaking — *frozen*.

**Rationale:** *קופא* is movement-language, not death-language. A frozen position can thaw or it can stay frozen — both are possible futures. That dual possibility is what the founder sees on the PLTR chart, and the label finally matches what he sees. It's also a verb-shape in Hebrew (present-active), which carries *ongoing-ness* — perfect for a state that's defined by the *absence* of an event.

**Disambiguation from `⏳ Dead Money`:** ENGINE already has `⏳ Dead Money` (constants at `engine_core.py:1779-1783`). Bands overlap; ENGINE owns the boundary. UX preference: ‏`❄️ קופא` for shorter dwell (≈7-14d, intact structure); `⏳ Dead Money` for deeper time-cost band (>14d, follow-through actively weak). *קופא* says "watch this," *Dead Money* says "the capital is the problem now." Not synonyms.

**Register note (E3):** native Hebrew. *קופא* has the cadence E3 #2 (wry-protective) values — names the phenomenon without moralizing. Re-readable on day 90 because the metaphor is concrete (ice) and not market-jargon.

**Rejected alternates:** *🪦 חניון* (gravestone too final, ages badly); *😴 ישן* (anthropomorphizes — reads as commentary on the founder); *⌛ תקוע* (slight negative valence — bleeds toward "broken"; *קופא* stays neutral).

---

### 3. `🔴 שבור` — RESERVED: genuine structural failure ONLY

‏**Hebrew label:** ‏`🔴 שבור` (unchanged)
**English mirror (§X3):** `🔴 Broken` (unchanged)
**State constant:** `POSITION_STATE_BROKEN` (existing)

**Predicate (binding, narrowed):** price has traded **through the stop** OR `violation_score >= 6`. Nothing else. If neither of those is true, the label is not available to ENGINE.

**Rationale:** *שבור* keeps its full Hebrew weight — terminal, structural, action-bearing — *because* it is now only emitted when the structure is actually broken. The word earns its volume by being rare. Today it gets fired ~weekly across the book and has rotted; once narrowed to the predicate above it fires ~monthly per name, and when it does, the founder reads it and acts.

**Register note (E3):** this is the one label where the directive-energy of Hebrew is *appropriate*, because the underlying state is itself directive (stop has been hit / structure has violated). The action line should stay strong (see §"Action-line copy" below).

**No alternate proposed** — the existing label is correct *once the predicate is tightened*. Renaming `שבור` would lose hard-won muscle memory.

---

## Action-line copy per new label

`build_management_action` currently maps statuses to `(action, trigger, suggested_stop)`. New status branches needed. The Mark §3 anti-list (invitation, not directive) governs every line below. No imperatives that aren't earned by the predicate.

### `👀 מוקדם` — Too Early

```python
elif status == "👀 מוקדם":
    if mgt_state == "runner_mode":
        # not reachable under predicate; if it is, fall through to working logic
        action, trigger = "החזק כרגיל", "Runner — מוקדם מדי לשנות משהו"
    else:
        action, trigger = "תן לזה לזוז", "עוד לא מספיק ימים להכריע"
    suggested_stop = current_stop
```

‏**Action text:** ‏`תן לזה לזוז`
‏**Trigger text:** ‏`עוד לא מספיק ימים להכריע`

**Why this passes §3:** the verb *לתת* (to allow) is the opposite of directive — it removes Sentinel from the loop. The trigger names *Sentinel's* limitation ("not enough days"), not the position's failure. The stop is unchanged because there's no new information to act on. This is the textbook §3 honest-uncertainty surface.

### `❄️ קופא` — Stalled

```python
elif status == "❄️ קופא":
    if mgt_state == "runner_mode":
        action, trigger = "לא להוסיף ל-Runner", "תנועה נעצרה — אין סיבה להגדיל"
    else:
        action, trigger = "לא להוסיף. שווה לבדוק תזה",
                          "אין תנועה — בדוק אם הסיפור עוד תקף"
    suggested_stop = current_stop  # never tighten on stall alone
```

‏**Action text:** ‏`לא להוסיף. שווה לבדוק תזה`
‏**Trigger text:** ‏`אין תנועה — בדוק אם הסיפור עוד תקף`

**Why this passes §3:** *שווה לבדוק* (it's worth checking) is the canonical invitation construction from E3 — it offers without demanding. The action is **a negative scope** (don't add) plus **a research prompt** (re-examine the thesis), never an exit order. Stop is held — stalling alone is not a tightening trigger; only structural deterioration is.

### `🔴 שבור` — Broken (existing line unchanged, but now correctly rare)

Existing: ‏`יציאה / הידוק מידי` / ‏`המבנה נשבר`. **Keep as-is.** Once the predicate is tight, this directive is earned: stop hit OR violation_score ≥ 6 *is* the moment Sentinel should speak loudly. The whole point of narrowing the label is so this action line keeps its authority.

---

## Drilldown lines (one-liner per new tag, RTL-clean)

These appear in `/portfolio` drilldown under the tag. Each starts with U+200F (`‏`) for clean RTL on Telegram clients.

### `👀 מוקדם`

```
‏פוזיציה בת {days_held} ימים. מוקדם מדי לסמן הצלחה או כישלון — תן לתזה לעבוד.
```

Variables: `{days_held}` (integer, 1-2 expected).
Notes: states the *time fact* (days) so the founder can verify Sentinel isn't bluffing; ends on a thesis-respecting close. No numbers about R or score — those are the very numbers that look bad and that the label is *deliberately not relying on*.

### `❄️ קופא`

```
‏{days_held} ימים, R={total_r:+.2f}, follow-through={ft_score}. מבנה תקין, תנועה אפסית — שווה לבדוק אם הסיפור עוד שם.
```

Variables: `{days_held}`, `{total_r}` (signed, 2dp, e.g. `-0.25`), `{ft_score}` (0-100).
Notes: surfaces the three numbers that *prove* the diagnosis (time elapsed, R magnitude small, follow-through weak) — so the founder sees the math behind the label. *מבנה תקין* explicitly disambiguates from `שבור`. The closing clause is the same invitation as the action line; consistency reinforces the register.

### `🔴 שבור` (drilldown also tightens)

```
‏מבנה נשבר: {violation_reason}. R={total_r:+.2f} · stop {stop_state}.
```

Variables: `{violation_reason}` (e.g. "סטופ חצה", "violation_score=7"), `{stop_state}` ("הופעל" / "קרוב מאוד"). The drilldown now *names which structural fact* triggered `שבור`. The founder forwarding the screenshot can answer "why broken?" with one glance, instead of guessing.

---

## Anti-patterns — what NOT to add

Tempting labels I'd kill on sight:

1. **`📉 חלש`** — looks innocent, rots fastest. *חלש* is a market-commentary word (every analyst on TV says it), not a state word. It would creep into use anywhere a position is mildly red, and within two weeks it would be on half the book. We already have `🟠 Weak` for the *score-band* case at the stock level; importing it to the position level just duplicates labels without adding information. **Kill.**

2. **`🚨 סכנה` / `⚠️ זהירות`** — FOMO/alarm triggers. Tells the founder to *feel something* before stating *what happened*. The E3 anti-clichés list explicitly outlaws *זהירות!* with exclamation energy ("cries wolf — use the data, not the punctuation"). Position labels are state descriptions; alarms belong to a separate channel (the bot's notification layer), never on a portfolio tag. **Kill.**

3. **`🎯 קרוב ליעד`** — sounds useful, is actually market-commentary drift. The label would invite Sentinel to comment on what *might* happen ("close to target!") rather than what *is* (state). It also creates FOMO-pressure to *not* exit early because "we're close" — directly fighting the disposition-mirror work in the E3 brief. **Kill.**

4. **`💤 שקט`** (borderline) — *שקט* in Hebrew is positive-valenced (peaceful, calm) and would *flatter* a stalled position. *קופא* is neutral-to-mildly-negative — matches reality. **Skip.**

---

## Sign-off

*שבור* wasn't a bad word — it was being asked to do three jobs. Splitting it into ‏`👀 מוקדם` (too early to know), ‏`❄️ קופא` (frozen, watch the thesis), and ‏`🔴 שבור` (structure actually failed) restores each word to a single job, lets the founder forward any screenshot without flinching, and survives day-90 because none of the new labels lean on market-commentary, FOMO, or untracked emotion — only on facts ENGINE can prove. §X3 mirror is the safety net: *Too Early* / *Stalled* / *Broken* are the binding English forms; drift is a §3-class defect.

— UX / Telegram + Hebrew Copy lens. Predicates to ENGINE; words above are binding.
