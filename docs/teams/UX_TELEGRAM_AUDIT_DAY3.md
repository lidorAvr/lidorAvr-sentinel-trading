# Telegram UX Audit — Day 3 (Adaptive UX Team)

> Branch: worktree of `claude/review-system-audit-FBZ2h`
> Author: Adaptive UX Team
> Date: 2026-05-15
> Status: Audit + IMPLEMENTED top fixes (code + tests) + deferred specs
> Founder feedback verbatim: "the Telegram UX is really not convenient."

---

## 0. Scope & method

Read the full Telegram surface end-to-end:
`telegram_bot.py`, `telegram_callbacks.py`, `telegram_menus.py`,
`telegram_portfolio.py`, `telegram_backlog.py`, `bot_helpers.py`,
`telegram_formatters.py`, `supabase_repository.py`, plus `engine_core.
get_open_positions_campaign` for the data shape.

Constraints honoured (CLAUDE.md / AGENTS.md): no wholesale rewrite of
`telegram_bot.py`; admin guard / anti-spam untouched; **stop-value math
unchanged** (selection-only change); ALGO never receives Sentinel stop
instructions; Hebrew RTL kept short and actionable; full pytest suite
green.

---

## 1. Full flow inventory & friction

| # | Flow | Entry point(s) | Friction observed |
|---|------|----------------|-------------------|
| F1 | Portfolio room ("חדר מצב") | `📊 מצב תיק`→`📊 חדר מצב`, `/portfolio` | Heavy: `get_all_trades` + per-position `evaluate_position_engine` + live prices + market regime + coaching + adaptive risk. Slow. Long multi-part message (split at 3900 chars). Re-run cost is high. `telegram_portfolio.py:211` |
| F2 | **Stop promotion ("קידום סטופ")** | ONLY a button at the very bottom of F1 (`telegram_portfolio.py:426`, callback `start_trail_flow`) | **BLOCKER (see §2).** Hidden behind heavy F1; requires typing a trade number; expires; forces heavy re-run per stop. |
| F3 | Drill-down X-ray | Inline `🔍 SYM` buttons under F1, `/trade SYMBOL` | OK. One tap. `telegram_callbacks.py:43`, `telegram_portfolio.py:51` |
| F4 | Market regime + adaptive risk | `📊 מצב תיק`→`🌡️ משטר שוק`, text | OK, one screen. `telegram_portfolio.py:153` |
| F5 | Journal completion ("Backlog") | `📚 יומן`→`🔍 סריקת יומן (Backlog)`, `/next` | **HIGH (see §3).** Mislabelled; linear one-item walker, not the grouped/sorted browsable backlog the founder expected. `telegram_backlog.py:14` |
| F6 | Legacy archive cleanup | `📚 יומן`→`🧹 ארכיון`, `/clean` | Destructive-ish bulk Supabase write with no confirmation; only protected by a 30-day age filter. `telegram_bot.py:347` |
| F7 | Stock analysis (5-crit) | `🔬 ניתוח`→`🔬 סקירת מניה`, `/analyze SYM` | Two-step (button → type symbol). Acceptable. `telegram_bot.py:340` |
| F8 | Trend Template (8-crit) | `🔬 ניתוח`→`🧠 ניתוח מינרביני`, `/mentor SYM` | Same two-step. Acceptable. `telegram_bot.py:312` |
| F9 | Add-on planner | `/addon SYMBOL …` (typed command only) | **MED.** No menu button, no discoverability; requires memorising the arg grammar. Inline confirm exists (good). `telegram_bot.py:483` |
| F10 | Runner decision (hold/tighten/partial) | Inline buttons on a risk_monitor alert | Good UX. `tighten` reuses typed-stop entry. `telegram_callbacks.py:113` |
| F11 | Adaptive risk confirm (YES/NO) | Inline buttons on alert; NO → typed reason | Good. `telegram_callbacks.py:103` |
| F12 | Developer menu | `🛠️ מפתח` (PIN-gated) | OK. Rate-limited, PIN-gated. |
| F13 | Adherence stats | `/stats` | OK. |
| F14 | Health | `/health`, dev menu | OK. |
| F15 | Help | `❓ עזרה`, `/help` | Two help texts diverge (`telegram_bot.py:268` vs `:372`). MED — minor truth/consistency issue. |
| F16 | Cancel | "ביטול"/"❌ ביטול"/`/cancel` | Good universal escape. `telegram_bot.py:51` |

---

## 2. Pain 1 deep-dive — Stop promotion (BLOCKER, FIXED)

### Old flow (pre-fix)

```
/portfolio  (HEAVY: engine per position, regime, coaching, adaptive risk)
   → long multi-part message
   → scroll to the very bottom
   → tap "🎯 הזן קידום סטופ"  (only entry point; callback start_trail_flow)
   → bot: "הקלד את מספר הטרייד מהרשימה (1-N)"
   → scroll BACK UP the long message to map number ↔ symbol
   → TYPE the number
   → type the new stop price
   → returns to main menu
   → to promote the next stop: repeat the ENTIRE heavy /portfolio run
```

Code evidence:
- Only entry point: `telegram_portfolio.py:426` (`start_trail_flow` button is
  appended after the drill buttons at the bottom of the heavy room).
- `start_trail_flow` required `user_state[chat_id]['temp_positions']`,
  populated ONLY by `handle_portfolio_room` (`telegram_portfolio.py:232`).
  On expiry: `"⚠️ המידע פג תוקף. לחץ שוב על 'חדר מצב'."`
  (`telegram_callbacks.py:60`, pre-fix).
- Typed-index step: `telegram_callbacks.py:57` set
  `action='select_trade_index'`; handler `telegram_bot.py:402`.
- Stop write: `repo.update_stop_for_campaign` via the `input_new_sl`
  handler (`telegram_bot.py:449`). **This math is correct and must not
  change.**

Friction tally to promote 4 stops: **4 heavy `/portfolio` re-runs, 4×
scroll-up-to-map, 4× typed number, 4× typed price, 4 expiry windows.**

### New flow (IMPLEMENTED)

New module `telegram_stop_promote.py` (additive; no `telegram_bot.py`
rewrite). New menu button `🎯 קידום סטופ` and `/promote`.

```
🎯 קידום סטופ   (or /promote, or the button now at bottom of /portfolio)
   → LIGHTWEIGHT fetch: repo.get_all_trades + ec.get_open_positions_campaign
     + ec.get_live_price  (NO evaluate_position_engine, NO regime,
     NO coaching, NO adaptive risk) — fast.
   → inline keyboard, one button per discretionary position:

      ┌─────────────────────────────┐
      │ 🎯 CAT   +1.99R             │
      │ 🎯 MSFT  +0.42R             │
      │ 🟠 QQQ — מנוהל חיצונית (ALGO)│
      │ ❌ סגור                      │
      └─────────────────────────────┘

   → ONE TAP selects the campaign (no typing, no scrolling)
   → bot: "✅ נבחר CAT | כניסה $… | סטופ נוכחי $… — הקלד סטופ חדש:"
   → type the new stop price
   → write via the EXISTING repo.update_stop_for_campaign (byte-identical)
   → bot: "🚀 הסטופ עודכן — CAT … בחר פוזיציה נוספת לקידום, או '❌ סגור'"
   → the SAME list is shown again immediately (no expiry, no heavy re-run)
   → promote the next stop with one tap. Repeat.
```

Friction to promote 4 stops now: **1 light fetch, 4× one-tap, 4× typed
price.** No heavy re-runs, no scroll-mapping, no expiry between picks.

### Why this is safe (Red Lines)

- **Stop-value math unchanged.** `handle_stop_promote_pick` only sets
  `user_state` (`selected_trade`, `action='input_new_sl'`,
  `promote_batch=True`) and hands off to the **pre-existing**
  `input_new_sl` handler. The write call `repo.update_stop_for_campaign(
  supabase, cid, new_sl)` is byte-identical to before — we changed *how
  the user selects*, never *how the stop is computed or written*.
- **No campaign math duplicated.** The button label's open-R uses the
  exact same formula already in `handle_portfolio_room`
  (`telegram_portfolio.py:277-278`); it is display-only and never feeds a
  write.
- **ALGO protected (DEC-20260511-001).** ALGO campaigns render as a
  non-actionable 🟠 info button (`callback_data="promote_algo_noop"` → an
  alert popup). `handle_stop_promote_pick` refuses an ALGO pick even if
  the callback is forged. Sentinel never issues an ALGO stop.
- **Legacy typed-index path kept as fallback.** `select_trade_index`
  handler in `telegram_bot.py` is untouched; `start_trail_flow` now shows
  the inline keyboard instead of asking to type, and when no positions
  are cached it opens the lightweight list instead of demanding a heavy
  `חדר מצב` re-run. Old muscle memory still works.
- Admin guard / anti-spam (telegram_bot_secure_runner.py) untouched.

### Files changed (Pain 1)

| File | Change |
|------|--------|
| `telegram_stop_promote.py` | NEW. `handle_stop_promote_entry`, `build_stop_promote_keyboard`, `handle_stop_promote_pick`, `_compute_open_r`. |
| `telegram_callbacks.py:54-96` | New routes `promote_open`, `promote_pick|<idx>`, `promote_algo_noop`; `start_trail_flow` now tap-only / lightweight fallback. |
| `telegram_bot.py` (re-export + `🎯 קידום סטופ`/`/promote` handler + `input_new_sl` batch-return) | Small additive edits; write logic byte-identical. |
| `telegram_menus.py:get_portfolio_menu` | Added `🎯 קידום סטופ` button. |
| `tests/test_telegram_stop_promote.py` | NEW (15 tests). |
| `tests/test_telegram_callbacks_promote.py` | NEW (6 tests). |

---

## 3. Pain 2 deep-dive — "Message backlog" mismatch (HIGH)

### Finding

The founder was told a "tasks split by symbol, sorted by symbol and date,
browsable backlog" exists and could not find the button. **It does not
exist.** What exists is `telegram_backlog.get_next_missing`
(`telegram_backlog.py:14`): a *linear, one-missing-field-at-a-time
walker* over `repo.get_incomplete_trades` (server-ordered by
`trade_date, trade_id`). It surfaces exactly one trade's next missing
field (setup → quality → initial_stop / score → image → notes), then
loops to the next. There is no grouped-by-symbol, no sorted browsable
list, no "jump to symbol X".

The label `🔍 סריקת יומן (Backlog)` actively set a false expectation:
"Backlog" implies a browsable queue.

### Implemented (low-risk, additive)

- **Truth-in-label fix.** Menu button relabelled to
  `🔍 השלמת יומן — הפריט הבא` ("Journal completion — next item"), which
  accurately describes the sequential walker. Old labels
  (`🔍 סריקת יומן (Backlog)`, `📚 ניהול יומן (Backlog)`, `/next`) still
  route correctly for backward compatibility (`telegram_bot.py`,
  `telegram_menus.py:get_journal_menu`). `get_next_missing` logic itself
  is **untouched** (it is on the fragile list — no behavioural change
  without a dedicated task).
- Tests in `tests/test_telegram_menus.py` and
  `tests/test_telegram_backlog.py` still pass (label assertion is
  substring `"יומן"`/`"Backlog"`).

### Deferred — grouped/sorted browsable backlog (DESIGNED, NOT BUILT)

Reason for deferral: it is a *new view over a Supabase read* that the
founder explicitly expects, but doing it well needs a new repository
query + a new paginated inline UI + tests; building it half-way is worse
than a precise spec. It is **additive and low-risk** when done as a
separate task. Precise spec:

**Repo layer** — add `supabase_repository.get_incomplete_grouped(sb)`:
reuse the existing `_INCOMPLETE_TRADES_QUERY`, but return rows grouped by
`symbol`, each group sorted by `trade_date` ascending, groups sorted by
symbol A→Z. Skip `setup_type == 'Legacy'` (same filter as
`get_next_missing`). Pure read; no mutation.

**UI** — new `telegram_backlog.handle_backlog_overview(chat_id)`:

```
📋 יומן — משימות פתוחות (12 פריטים, 5 סימולים)

🔹 CAT  (3)
   • 2026-04-30 BUY  — חסר: setup, סטופ
   • 2026-05-02 BUY  — חסר: איכות
   • 2026-05-09 SELL — חסר: ציון, תמונה
   [▶️ השלם CAT]
🔹 MSFT (1)
   • 2026-05-11 SELL — חסר: הערות ניהול
   [▶️ השלם MSFT]
   …
[⏭️ הפריט הבא (רציף)]   [❌ סגור]
```

Each `[▶️ השלם SYM]` inline button (`callback bl_sym|SYM`) drives the
**existing** `get_next_missing`-style step flow but filtered to that
symbol's campaign — so we reuse the proven write path and never duplicate
the completion logic. `[⏭️ הפריט הבא (רציף)]` = today's `get_next_missing`.

Constraints for the future task: read-only; Hebrew RTL short; one inline
keyboard, paginate if > ~8 symbols (Telegram message limits); add
`tests/test_telegram_backlog_overview.py` mirroring the existing backlog
test patterns; do NOT change `get_next_missing`'s write semantics.

---

## 4. Prioritised fix table

| Pain | Sev | Effort | Risk | File:line | Fix | Status |
|------|-----|--------|------|-----------|-----|--------|
| Stop promotion hidden behind heavy room, typed index, expiry, per-stop re-run | **BLOCKER** | M | Low (selection-only) | `telegram_portfolio.py:426`, `telegram_callbacks.py:54`, `telegram_bot.py:402,451` | New lightweight tap-only `telegram_stop_promote.py` + batch return | **DONE** |
| Backlog mislabelled / expectation mismatch | HIGH | S | Low | `telegram_menus.py:49`, `telegram_bot.py` | Truthful relabel + surface; grouped view spec'd | **DONE (relabel) / DEFERRED (grouped view, spec'd)** |
| Add-on planner has no discoverable entry (typed grammar only) | MED | S | Low | `telegram_bot.py:483` | Add a `📌 חיזוק (Add-On)` analysis-menu button → prompt for `SYMBOL` then reuse `/addon` | DEFERRED — spec below |
| Two divergent `/help` texts | MED | S | Low | `telegram_bot.py:268` vs `:372` | Collapse to one source-of-truth help string | DEFERRED — spec below |
| `/clean` does a bulk Supabase write with no confirm | MED | S | **Med (mutation)** | `telegram_bot.py:347` | Add an inline `אשר ניקוי / בטל` confirm before the write | DEFERRED — needs careful Supabase-mutation review |
| Portfolio room is one giant split message | LOW | L | Med | `telegram_portfolio.py:211` | Summary-first + per-symbol drill (bigger refactor) | DEFERRED |
| `/next` not advertised in main help, only in second help text | LOW | S | Low | `telegram_bot.py:372` | Fold into the canonical help | DEFERRED (with help consolidation) |

### Deferred fix specs (precise, so a follow-up task is mechanical)

- **Add-on discoverability:** add `📌 חיזוק (Add-On)` to
  `get_analysis_menu()`; on tap set `user_state action='addon_symbol'`,
  prompt "הקלד סימול לחיזוק"; on reply call the existing
  `_handle_addon_command(chat_id, f"/addon {SYM}")` (eligibility view).
  Pure additive; reuses the proven add-on engine and confirm flow.
- **Help consolidation:** delete the second handler at
  `telegram_bot.py:367-368`; keep the richer one at `:268-283`; add the
  missing `/next`, `/promote`, `/clean`, `/addon` lines. Update
  `tests/test_ux_formatting_comprehensive.py` if it asserts help content.
- **`/clean` confirm:** wrap the bulk update in an inline
  `✅ אשר ניקוי (N) / ❌ בטל`; only run `repo.update_trade` loop after
  `clean_confirm|YES`. Touches a Supabase-mutation path → must be its own
  task with explicit review (AGENTS.md Red Line #4).

---

## 5. AGENTS.md / methodology risk flags

1. **Stop-discipline integrity (checked, OK).** The new flow does not
   widen, auto-suggest, or pre-fill a stop value. The user still types
   the new stop; the write path is byte-identical. No erosion of the
   "cut losses" discipline. The lightweight entry intentionally does NOT
   show a "suggested stop" to avoid nudging the user away from their own
   discipline.
2. **ALGO never instructed (checked, OK).** ALGO campaigns are
   non-actionable in the new keyboard and refused server-side in
   `handle_stop_promote_pick`. No ALGO stop-raise path was created
   (DEC-20260511-001, AGENTS.md Red Line).
3. **No stats contamination.** Nothing in the new flow touches Win Rate /
   Expectancy / closed-campaign stats. ALGO/DATA_INCOMPLETE exclusion
   invariants are untouched.
4. **No new recurring alert.** This is a user-initiated flow only; no
   risk_monitor changes; anti-spam dedup invariants untouched.
5. **Fallback honesty (pre-existing, flagged not fixed).** `_compute_
   open_r` and `handle_portfolio_room` fall back to entry price when
   `ec.get_live_price` returns `None`, and the open-R then silently uses
   entry-as-current. The button shows `R N/A` only when *original risk*
   is missing, not when the price is a fallback. This pre-exists our
   change and is unchanged by it, but per CLAUDE.md ("clear about
   fallback/cached data") a future task should label price-fallback rows.
   Flagged here; out of scope for a selection-only fix.
6. **`/clean` mutation (pre-existing).** Bulk Supabase write with no
   confirmation (`telegram_bot.py:347`). AGENTS.md Red Line #4 ("Supabase
   trade records must not be mutated unless the user action explicitly
   requires it") — a tap on `🧹 ארכיון` is arguably implicit consent for
   a 30-day-protected backfill, but a confirm step is warranted. Flagged;
   deferred (mutation-path change needs its own review).

---

## 6. What we changed vs. deferred (summary)

**Implemented (code + tests, full suite green):**
- Tap-only, no-scroll, no-type-the-number stop promotion via
  `telegram_stop_promote.py` + `🎯 קידום סטופ` / `/promote`.
- Lightweight entry point (no heavy `evaluate_position_engine` / regime /
  coaching) that re-uses existing fetch helpers; no campaign math
  duplicated; stop-write byte-identical.
- Batch-friendly: after each promotion the same list reappears with no
  expiry and no heavy re-run.
- `start_trail_flow` upgraded to tap-only with a lightweight fallback
  (no forced heavy room re-run); legacy typed-index path retained.
- Backlog menu truthfully relabelled (`🔍 השלמת יומן — הפריט הבא`); old
  labels still route.

**Deferred (specified precisely, not guessed):**
- Grouped-by-symbol / sorted browsable backlog view (full spec in §3).
- Add-on menu discoverability; `/help` consolidation; `/clean` confirm;
  portfolio-room summary-first refactor; price-fallback labelling
  (specs in §4 / §5).

**Test delta:** worktree pre-existing baseline 1424 collected (this
worktree already carries sibling teams' +70 over the clean-branch 1354);
**+21 new tests** (15 `test_telegram_stop_promote.py`, 6
`test_telegram_callbacks_promote.py`); **1445 passed, 0 regressions.**
